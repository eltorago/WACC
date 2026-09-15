"""Acquire publisher source files without distributing them with WACC.

The acquisition catalogue points at publisher-controlled locations. Downloads are only
accepted when their SHA-256 matches the reviewed entry in ``sources/permissions.json``.
Files that require an account, an interactive export or a user-supplied historical copy
are described as manual acquisitions instead.
"""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import tempfile
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


def _read(url: str) -> Tuple[bytes, str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(request, timeout=120) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_BYTES:
            raise ValueError("remote file is larger than %d bytes" % MAX_BYTES)
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("remote file is larger than %d bytes" % MAX_BYTES)
        return body, response.headers.get_content_type(), response.geturl()


def _remote_digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _archive_member(body: bytes, member: str) -> Optional[bytes]:
    if not body.startswith(b"PK"):
        return None
    try:
        with ZipFile(BytesIO(body)) as archive:
            matches = [name for name in archive.namelist() if Path(name).name == member]
            return archive.read(matches[0]) if len(matches) == 1 else None
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
        path = parsed.path.lower()
        if suffix and not (path.endswith(suffix) or "download" in path or "attachment" in path):
            continue
        links.append(url)
    return sorted(dict.fromkeys(links), key=score, reverse=True)[:30]


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
    destination = destination_dir / name
    expected = entry["sha256"].lower()
    if destination.is_file() and digest(destination) == expected and not force:
        return "available", "reviewed bytes already present"
    if method["method"] == "manual":
        return "manual", method["instructions"]

    seeds = method.get("urls", [])
    if isinstance(seeds, str):
        seeds = [seeds]
    queue = list(seeds)
    visited = set()
    errors = []
    while queue:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            body, content_type, final_url = _read(url)
        except (HTTPError, URLError, OSError, ValueError) as error:
            errors.append("%s: %s" % (url, error))
            continue
        if _remote_digest(body) == expected:
            _write_verified(destination, body)
            return "downloaded", final_url
        member = method.get("archive_member")
        extracted = _archive_member(body, member) if member else None
        if extracted is not None and _remote_digest(extracted) == expected:
            _write_verified(destination, extracted)
            return "downloaded", "%s (%s)" % (final_url, member)
        if _looks_html(body, content_type):
            queue.extend(link for link in _candidate_links(body, final_url, name) if link not in visited)
        else:
            errors.append("%s: SHA-256 did not match the reviewed edition" % final_url)
    detail = errors[-1] if errors else "no downloadable publisher URL is configured"
    return "failed", detail


def acquire(
    names: Optional[Iterable[str]] = None,
    destination: Path = DEFAULT_DESTINATION,
    force: bool = False,
) -> List[Tuple[str, str, str]]:
    entries, methods = load_catalogue()
    # Acquisition and redistribution are separate decisions. Sources marked as local-only
    # may still be downloaded from their publisher; the packaging rules keep every file
    # in this cache out of Git and release archives.
    selected = list(names) if names else list(entries)
    unknown = sorted(set(selected) - set(entries))
    if unknown:
        raise ValueError("Unknown source file: %s" % ", ".join(unknown))
    def one(name: str) -> Tuple[str, str, str]:
        return (name,) + acquire_one(entries[name], methods[name], destination, force=force)

    with ThreadPoolExecutor(max_workers=min(3, max(1, len(selected)))) as pool:
        return list(pool.map(one, selected))


def describe() -> List[Tuple[str, str, str]]:
    entries, methods = load_catalogue()
    rows = []
    for name, entry in entries.items():
        method = methods[name]
        detail = method.get("instructions") or ", ".join(method.get("urls", []))
        rows.append((name, method["method"], detail))
    return rows
