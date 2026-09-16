"""Acquire publisher source files without distributing them with WACC.

The acquisition catalogue points at publisher-controlled locations. Downloads must match
the reviewed file hash or an explicitly configured OAG report-content fingerprint.
Files that require an account, an interactive export or a user-supplied historical copy
are described as manual acquisitions instead.
"""

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "sources" / "permissions.json"
CATALOGUE = ROOT / "sources" / "acquisition.json"
DEFAULT_DESTINATION = ROOT / "sources" / "files"
MAX_BYTES = 64 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 WACC-source-acquisition/1.0"
)


def source_directory(destination=None):
    return Path(destination or os.environ.get('WACC_SOURCES') or DEFAULT_DESTINATION).expanduser().resolve()


def local_path(directory, name):
    direct = directory / name
    if direct.exists():
        return direct
    matches = list(directory.rglob(name)) if directory.exists() else []
    return matches[0] if len(matches) == 1 else direct


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


def _safe_filename(name: str) -> str:
    if not name or name in (".", "..") or any(c in name for c in "/\\\n\r*?[]"):
        raise ValueError("Unsafe source filename: %r" % name)
    return name


def load_catalogue(
    manifest: Path = MANIFEST, catalogue: Path = CATALOGUE
) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
    permissions = json.loads(manifest.read_text(encoding="utf-8"))["files"]
    acquisition = json.loads(catalogue.read_text(encoding="utf-8"))["files"]
    entries = {_safe_filename(item["filename"]): item for item in permissions}
    methods = {_safe_filename(item["filename"]): item for item in acquisition}
    if set(entries) != set(methods):
        missing = sorted(set(entries) - set(methods))
        extra = sorted(set(methods) - set(entries))
        raise ValueError("Acquisition catalogue mismatch; missing=%r extra=%r" % (missing, extra))
    return entries, methods


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


class _OAGReport(HTMLParser):
    """Fingerprint the full report header/body, excluding dynamic site forms/scripts."""
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.sections = []
        self.tokens = []

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get('class') or '').split()
        if not self.depth and tag == 'div':
            selected = [c for c in ('new-report-header', 'new-report__body') if c in classes]
            if selected:
                self.sections.extend(selected)
                self.depth = 1
        elif self.depth and tag not in self.VOID:
            self.depth += 1
        if self.depth:
            self.tokens.append(('start', tag, sorted(attrs, key=lambda pair: (pair[0], pair[1] or ''))))

    def handle_endtag(self, tag):
        if self.depth and tag not in self.VOID:
            self.tokens.append(('end', tag))
            self.depth -= 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self.depth and data.strip():
            self.tokens.append(('text', ' '.join(data.split())))


def report_digest(body):
    parser = _OAGReport()
    parser.feed(body.decode('utf-8'))
    if parser.depth or parser.sections != ['new-report-header', 'new-report__body'] or len(parser.tokens) < 20:
        raise ValueError('OAG report header/body is missing, duplicated or incomplete')
    return hashlib.sha256(json.dumps(parser.tokens, ensure_ascii=False).encode('utf-8')).hexdigest()


def matches_review(entry, body):
    if hashlib.sha256(body).hexdigest() == entry['sha256']:
        return True
    review = entry.get('content_verification', {})
    if (review.get('method') == 'oag-report-v1'
            and entry['filename'].startswith('oag-') and entry['filename'].endswith('.html')
            and urlparse(entry.get('source_url', '')).hostname == 'audit.wa.gov.au'):
        try:
            return report_digest(body) == review['sha256']
        except (UnicodeError, ValueError, KeyError):
            return False
    return False


def _read_once(url: str) -> Tuple[bytes, str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(request, timeout=20) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_BYTES:
            raise ValueError("remote file is larger than %d bytes" % MAX_BYTES)
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("remote file is larger than %d bytes" % MAX_BYTES)
        return body, response.headers.get_content_type(), response.geturl()


def _read(url):
    for attempt in range(2):
        try:
            return _read_once(url)
        except HTTPError as error:
            if attempt or error.code not in (429, 500, 502, 503, 504):
                raise
        except (URLError, TimeoutError):
            if attempt:
                raise
        time.sleep(0.5)


def _remote_digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _archive_member(body: bytes, member: str) -> Optional[bytes]:
    if not body.startswith(b"PK"):
        return None
    try:
        with ZipFile(BytesIO(body)) as archive:
            matches = [name for name in archive.namelist() if Path(name).name == member]
            if len(matches) == 1 and archive.getinfo(matches[0]).file_size <= MAX_BYTES:
                return archive.read(matches[0])
            return None
    except (BadZipFile, KeyError):
        return None


def _looks_html(body: bytes, content_type: str) -> bool:
    return content_type in ("text/html", "application/xhtml+xml") or body.lstrip()[:20].lower().startswith(
        (b"<!doctype html", b"<html")
    )


def _candidate_links(body: bytes, base_url: str, filename: str) -> List[str]:
    parser = _Links()
    parser.feed(body.decode("utf-8", errors="ignore"))
    suffix = Path(filename).suffix.lower()
    words = {w.lower() for w in Path(filename).stem.replace("_", " ").replace("-", " ").split() if len(w) > 3}

    def score(url: str) -> Tuple[int, int, str]:
        path = urlparse(url).path.lower()
        basename = Path(path).name
        exact = 1000 if basename == filename.lower() else 0
        overlap = sum(10 for word in words if word in path)
        useful = 5 if any(part in path for part in ("download", "attachment", "/pdfs/", "/files/")) else 0
        return (exact + overlap + useful, -len(url), url)

    links = []
    for href in parser.hrefs:
        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc != urlparse(base_url).netloc:
            continue
        path = parsed.path.lower()
        if suffix and not (path.endswith(suffix) or "download" in path or "attachment" in path):
            continue
        links.append(url)
    return sorted(dict.fromkeys(links), key=score, reverse=True)[:6]


def _write_verified(destination: Path, body: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=destination.name + ".", dir=str(destination.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def acquire_one(
    entry: Dict,
    method: Dict,
    destination_dir: Path,
    force: bool = False,
) -> Tuple[str, str]:
    """Return ``(state, detail)`` for one source.

    States are ``available``, ``downloaded``, ``manual`` and ``failed``.
    """
    name = _safe_filename(entry["filename"])
    destination = local_path(destination_dir, name)
    expected = entry["sha256"].lower()
    if destination.is_file() and matches_review(entry, destination.read_bytes()) and (not force or method['method'] == 'manual'):
        return "available", "reviewed source already present"
    if method["method"] == "manual":
        return "manual", method["instructions"]

    seeds = method.get("urls", [])
    if isinstance(seeds, str):
        seeds = [seeds]
    queue = [(url, 0) for url in seeds]
    visited = set()
    errors = []
    while queue and len(visited) < 10:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            body, content_type, final_url = _read(url)
        except (HTTPError, URLError, OSError, ValueError) as error:
            errors.append("%s: %s" % (url, error))
            continue
        if matches_review(entry, body):
            _write_verified(destination, body)
            return "downloaded", final_url
        member = method.get("archive_member")
        extracted = _archive_member(body, member) if member else None
        if extracted is not None and _remote_digest(extracted) == expected:
            _write_verified(destination, extracted)
            return "downloaded", "%s (%s)" % (final_url, member)
        if _looks_html(body, content_type) and Path(name).suffix.lower() not in ('.html', '.htm') and depth == 0:
            queue.extend((link, 1) for link in _candidate_links(body, final_url, name) if link not in visited)
            errors.append('%s: landing page did not contain the reviewed document' % final_url)
        else:
            errors.append("%s: SHA-256 did not match the reviewed edition" % final_url)
    detail = errors[-1] if errors else "no downloadable publisher URL is configured"
    detail += '. Existing files were kept. ' + method.get('instructions', 'Retry later or obtain the reviewed edition from the publisher; changed bytes require an edition review.')
    return "failed", detail


def acquire(
    names: Optional[Iterable[str]] = None,
    destination: Optional[Path] = None,
    force: bool = False,
    progress=None,
) -> List[Tuple[str, str, str]]:
    entries, methods = load_catalogue()
    destination = source_directory(destination)
    # Acquisition and redistribution are separate decisions. Sources marked as local-only
    # may still be downloaded from their publisher; the packaging rules keep every file
    # in this cache out of Git and release archives.
    selected = list(names) if names else list(entries)
    unknown = sorted(set(selected) - set(entries))
    if unknown:
        raise ValueError("Unknown source file: %s" % ", ".join(unknown))
    def one(name: str) -> Tuple[str, str, str]:
        try:
            return (name,) + acquire_one(entries[name], methods[name], destination, force=force)
        except (OSError, ValueError, BadZipFile) as error:
            return name, 'failed', str(error)

    with ThreadPoolExecutor(max_workers=min(3, max(1, len(selected)))) as pool:
        pending = {pool.submit(one, name): name for name in selected}
        results = {}
        for future in as_completed(pending):
            row = future.result()
            results[row[0]] = row
            if progress:
                progress(row)
        return [results[name] for name in selected]


def status(destination=None, names=None):
    entries, methods = load_catalogue()
    directory = source_directory(destination)
    rows = []
    for name in names or entries:
        if name not in entries:
            raise ValueError('Unknown source file: ' + name)
        path = local_path(directory, name)
        state = 'missing'
        if path.is_file():
            state = 'available' if matches_review(entries[name], path.read_bytes()) else 'changed'
        rows.append(dict(filename=name, state=state, method=methods[name]['method'],
                         instructions=methods[name].get('instructions', ''),
                         urls=methods[name].get('urls', [])))
    return rows


def import_downloads(folder, destination=None, names=None):
    """Copy matching reviewed files from a chosen folder; never move or alter originals."""
    entries, _ = load_catalogue()
    selected = list(names) if names else list(entries)
    for name in selected:
        if name not in entries:
            raise ValueError('Unknown source file: ' + name)
    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError('Import folder does not exist: ' + str(folder))
    directory = source_directory(destination)
    by_hash = {entries[n]['sha256']: n for n in selected}
    content_entries = [entries[n] for n in selected if entries[n].get('content_verification')]
    results = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BYTES:
            continue
        name = by_hash.get(digest(path))
        if not name and path.suffix.lower() in ('.html', '.htm'):
            body = path.read_bytes()
            name = next((entry['filename'] for entry in content_entries if matches_review(entry, body)), None)
        if name:
            target = local_path(directory, name)
            body = path.read_bytes()
            if not matches_review(entries[name], body):
                results.append((name, 'failed', 'File changed during import; not copied.'))
                continue
            if not target.is_file() or not matches_review(entries[name], target.read_bytes()):
                _write_verified(target, body)
            results.append((name, 'imported', path.name))
    return results


def describe() -> List[Tuple[str, str, str]]:
    entries, methods = load_catalogue()
    rows = []
    for name, entry in entries.items():
        method = methods[name]
        detail = ' '.join(filter(None, [method.get("instructions"), ", ".join(method.get("urls", []))]))
        rows.append((name, method["method"], detail))
    return rows
