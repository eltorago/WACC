"""Bounded text extraction. Run parsers in a disposable worker, never in the UI."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import time
import unicodedata
import zipfile
from xml.etree import ElementTree as ET

from .contracts import PolicyError

MAX_BYTES = 16 * 1024 * 1024
MAX_TEXT = 2_000_000
FORMATS = (".txt", ".md", ".docx", ".pdf")
INPUT_FORMATS = (*FORMATS, '.zip')
PARSER_VERSION = "bounded-text-1"
NORMALISER_VERSION = "nfkc-casefold-spans-1"


def local_file(path):
    path = Path(path).absolute()
    if str(path).startswith(("\\\\", "//")):
        raise PolicyError("Use a local working directory; network paths are not supported.")
    for parent in (path, *path.parents):
        if parent.exists() and (parent.is_symlink() or getattr(parent.stat(), "st_file_attributes", 0) & 1024):
            raise PolicyError("Linked or reparse-point input paths are not supported.")
    return path


def select(paths, recurse=False):
    found = []
    for value in paths:
        path = local_file(value)
        if not path.exists():
            raise PolicyError("A selected input does not exist.")
        if path.is_dir():
            for directory, subdirs, files in os.walk(path, followlinks=False):
                subdirs[:] = sorted(d for d in subdirs if not (Path(directory, d).is_symlink() or getattr(Path(directory, d).stat(), "st_file_attributes", 0) & 1024)) if recurse else []
                found.extend(local_file(Path(directory, name)) for name in sorted(files) if Path(name).suffix.lower() in INPUT_FORMATS)
        else:
            if path.suffix.lower() not in INPUT_FORMATS:
                raise PolicyError("Select PDF, DOCX, TXT, Markdown or a ZIP containing these documents.")
            found.append(path)
    found = sorted(set(found), key=lambda p: str(p).casefold())
    if not found or len(found) > 250:
        raise PolicyError("Select between 1 and 250 supported documents.")
    return found


def expand_inputs(paths):
    """List archive members without extracting files onto the computer."""
    inputs, skipped = [], []
    for path in paths:
        if path.suffix.lower() != '.zip':
            inputs.append((path, None))
            continue
        if path.stat().st_size > MAX_BYTES:
            raise PolicyError('ZIP exceeds the 16 MiB input limit.')
        try:
            with checked_archive(path.read_bytes()) as archive:
                for info in sorted(archive.infolist(), key=lambda value: value.filename.casefold()):
                    if info.is_dir():
                        continue
                    if PurePosixPath(info.filename).suffix.lower() in FORMATS:
                        inputs.append((path, info.filename))
                    else:
                        skipped.append(str(path) + ' / ' + info.filename)
        except zipfile.BadZipFile:
            raise PolicyError('The selected ZIP cannot be read.')
    if not inputs or len(inputs) > 250:
        raise PolicyError('Select between 1 and 250 supported documents, including files inside ZIPs.')
    return inputs, skipped


def normalise(text):
    chars, spans = [], []
    for index, char in enumerate(text):
        for letter in unicodedata.normalize("NFKC", char).casefold():
            if letter.isspace():
                if chars and chars[-1] == " ":
                    spans[-1][1] = index + 1
                    continue
                letter = " "
            chars.append(letter)
            spans.append([index, index + 1])
    return "".join(chars), spans


def checked_archive(data):
    archive = zipfile.ZipFile(io.BytesIO(data))
    infos = archive.infolist()
    names = [i.filename for i in infos]
    if len(infos) > 2048 or len(set(names)) != len(names) or sum(i.file_size for i in infos) > 32 * 1024 * 1024:
        raise PolicyError("Archive exceeds entry or expansion limits.")
    for info in infos:
        # ZipInfo normalises backslashes on Windows and truncates NULs. Check
        # the original central-directory name before trusting that normalisation.
        raw_name = info.orig_filename
        p = PurePosixPath(raw_name)
        if (p.is_absolute() or ".." in p.parts or "\\" in raw_name or ":" in raw_name or '\x00' in raw_name
                or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1
                or info.file_size > 16 * 1024 * 1024 or info.file_size / max(1, info.compress_size) > 200):
            raise PolicyError("Unsafe or excessively compressed archive entry.")
    return archive


def extract(path, member=None):
    path = local_file(path)
    if path.stat().st_size > MAX_BYTES:
        raise PolicyError("Document exceeds the 16 MiB input limit.")
    data = path.read_bytes()
    archive_hash = None
    if member is not None:
        archive_hash = hashlib.sha256(data).hexdigest()
        with checked_archive(data) as archive:
            if member not in archive.namelist() or PurePosixPath(member).suffix.lower() not in FORMATS:
                raise PolicyError('Unsupported or missing ZIP member.')
            data = archive.read(member)
    digest = hashlib.sha256(data).hexdigest()
    result = dict(id=digest, sha256=digest, name=path.name if member is None else path.name + ' / ' + member,
                  path=str(path), format=PurePosixPath(member).suffix.lower() if member else path.suffix.lower(),
                  status="Ready", approvalStatus="unknown", effectiveDate=None, included=True,
                  warnings=[], passages=[], parserVersion=PARSER_VERSION)
    if member is not None:
        result.update(archiveMember=member, archiveHash=archive_hash)

    text_length = 0

    def add(text, locator):
        nonlocal text_length
        if not text.strip():
            return
        text_length += len(text)
        if len(text) > 100_000 or text_length > MAX_TEXT:
            raise PolicyError("Extracted text exceeds supported limits.")
        result["passages"].append(dict(id="%s:p%d" % (digest, len(result["passages"]) + 1), text=text, locator=locator))

    if result["format"] in (".txt", ".md"):
        if b"\x00" in data or data.startswith((b"PK", b"%PDF")):
            raise PolicyError("File contents do not match the selected text format.")
        text = data.decode("utf-8-sig")
        heading = ''
        for match in re.finditer(r"[^\r\n]+(?:\r?\n(?!\r?\n)[^\r\n]+)*", text):
            if match.group().startswith('#'):
                heading = match.group().splitlines()[0].lstrip('# ').strip()
            add(match.group(), dict(kind="paragraph", start=match.start(), end=match.end(), line=text.count("\n", 0, match.start()) + 1, heading=heading))
    elif result["format"] == ".docx":
        with checked_archive(data) as archive:
            names = archive.namelist()
            if "word/document.xml" not in names or any("vbaproject" in n.lower() for n in names):
                raise PolicyError("Not a supported macro-free DOCX document.")
            raw = archive.read("word/document.xml")
            if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                raise PolicyError("XML declarations with external entities are not supported.")
            root = ET.fromstring(raw)
            w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            def walk(node, depth=0):
                if depth > 64:
                    raise PolicyError("DOCX XML nesting exceeds supported limits.")
                for child in node:
                    walk(child, depth + 1)
            walk(root)
            body = root.find(w + "body")
            if body is None:
                raise PolicyError("DOCX document body is missing.")
            heading = ""
            def para_text(node):
                return "".join(n.text or "" if n.tag == w + "t" else "\n" for n in node.iter() if n.tag in (w + "t", w + "br", w + "tab"))
            for index, node in enumerate(body, 1):
                if node.tag == w + "p":
                    text = para_text(node)
                    style = node.find(".//" + w + "pStyle")
                    if style is not None and "heading" in style.get(w + "val", "").lower():
                        heading = text
                    add(text, dict(kind="paragraph", paragraph=index, heading=heading))
                elif node.tag == w + "tbl":
                    for row, tr in enumerate(node.findall(w + "tr"), 1):
                        for cell, tc in enumerate(tr.findall(w + "tc"), 1):
                            add("\n".join(para_text(p) for p in tc.findall(w + "p")), dict(kind="tableCell", table=index, row=row, cell=cell, heading=heading))
            if any(n.startswith(("word/header", "word/footer", "word/footnotes", "word/endnotes")) for n in names):
                result["warnings"].append("Headers, footers and notes are not evaluated; review them separately.")
            if root.find(".//" + w + "drawing") is not None or root.find(".//" + w + "altChunk") is not None:
                result["warnings"].append("Embedded images or alternate content require manual inspection.")
    elif result["format"] == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise PolicyError("File contents do not match PDF format.")
        try:
            from pypdf import PdfReader, __version__
        except ImportError:
            raise PolicyError("PDF parser unavailable. Use the offline dependency bundle or a TXT/DOCX copy.")
        result["parserVersion"] += "/pypdf-" + __version__
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted or len(reader.pages) > 300:
            raise PolicyError("Encrypted PDFs and PDFs exceeding 300 pages are unsupported.")
        for number, page in enumerate(reader.pages, 1):
            content = page.get_contents()
            if content is not None and len(content.get_data()) > 8 * 1024 * 1024:
                raise PolicyError("PDF page content exceeds supported limits.")
            text = page.extract_text() or ""
            if not text.strip():
                result["warnings"].append("Page %d has no extractable text; transcription may be required." % number)
            for match in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text):
                add(match.group(), dict(kind="pageText", page=number, start=match.start(), end=match.end(), boundingBox=None))
    else:
        raise PolicyError("Unsupported document format.")
    if not result["passages"]:
        result["warnings"].append("No usable text was extracted.")
    if result["warnings"]:
        result["status"] = "Incomplete"
    return result


def extract_worker(path, cancel=None, timeout=30, framework=None, member=None):
    args = [sys.executable, "--extract-worker"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "wacc.policy.worker"]
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    started = time.monotonic()
    payload = json.dumps({"path": str(path), "framework": framework, "member": member}).encode()
    release = None
    try:
        from .worker_limits import constrain
        release = constrain(process)
        while True:
            if cancel and cancel.is_set():
                raise KeyboardInterrupt
            if time.monotonic() - started > timeout:
                raise PolicyError("Document extraction timed out.")
            try:
                stdout, _ = process.communicate(payload, timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                payload = None
        try:
            response = json.loads(stdout)
        except (ValueError, UnicodeError):
            raise PolicyError('Parser worker stopped before completing extraction, possibly due to a resource limit.')
        if "error" in response:
            raise PolicyError(response["error"])
        return response
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()
        if release:
            release()
