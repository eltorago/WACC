"""Explicit publisher downloads, local version history and atomic corpus updates."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
import uuid

from .contracts import PolicyError, fingerprint
from .documents import MAX_BYTES, extract_worker, local_file
from .reports import write_output

PAGES = {
    'wa-csp': 'https://www.wa.gov.au/government/publications/2024-wa-government-cyber-security-policy',
    'aescsf': 'https://www.aemo.com.au/initiatives/major-programs/cyber-security/aescsf-framework-and-resources',
    'ism': 'https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/ism/ism-oscal-releases',
}
ISM_CATALOG = 'https://raw.githubusercontent.com/AustralianCyberSecurityCentre/ism-oscal/main/ISM_catalog.json'
FILENAMES = {'wa-csp':'wa-cyber-security-policy.pdf','aescsf':'aescsf-framework-core.xlsx','ism':'ISM_catalog.json'}
HOSTS = {'wa-csp':{'www.wa.gov.au','wa.gov.au'}, 'aescsf':{'www.aemo.com.au','aemo.com.au'},
         'ism':{'raw.githubusercontent.com'}}
IMPORT_VERSION = 'publisher-2'


def cache_root():
    default = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share'))) / 'WACC/frameworks'
    return local_file(os.environ.get('WACC_FRAMEWORK_CACHE', str(default)))


def approved_url(url, framework):
    parsed = urlsplit(url)
    if (framework not in HOSTS or parsed.scheme != 'https' or parsed.hostname not in HOSTS[framework]
            or parsed.username or parsed.password or parsed.port not in (None,443)):
        raise PolicyError('Framework download must remain on its official publisher host.', 5)
    if framework == 'ism' and not parsed.path.startswith('/AustralianCyberSecurityCentre/ism-oscal/'):
        raise PolicyError('Unexpected ISM repository path.', 5)
    return url


def download(url, framework):
    approved_url(url, framework)
    class Redirects(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, message, headers, newurl):
            approved_url(newurl, framework)
            return super().redirect_request(request, fp, code, message, headers, newurl)
    request = Request(url, headers={'User-Agent':'WACC-framework-update/1.0','Accept':'*/*'})
    started = time.monotonic()
    with build_opener(Redirects()).open(request, timeout=20) as response:
        approved_url(response.geturl(), framework)
        length = response.headers.get('Content-Length')
        if length and int(length) > MAX_BYTES:
            raise PolicyError('Framework download exceeds 16 MiB.', 5)
        parts, total = [], 0
        while True:
            block = response.read(65536)
            if not block:
                break
            total += len(block)
            if total > MAX_BYTES or time.monotonic()-started > 45:
                raise PolicyError('Framework download exceeded its size or time limit.', 5)
            parts.append(block)
        return b''.join(parts), response.geturl()


class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.href, self.label = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a':
            self.href, self.label = dict(attrs).get('href'), []

    def handle_data(self, data):
        if self.href:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == 'a' and self.href:
            self.links.append((self.href, ' '.join(' '.join(self.label).split())))
            self.href, self.label = None, []


def discover(framework):
    if framework == 'ism':
        return ISM_CATALOG
    body, page = download(PAGES[framework], framework)
    parser = Links(); parser.feed(body.decode('utf-8'))
    candidates = []
    for href, label in parser.links:
        url = urljoin(page, href)
        text = label.casefold()
        path = urlsplit(url).path.casefold()
        if framework == 'wa-csp':
            match = path.endswith('.pdf') and 'cyber security policy' in text and '2024' in text and 'overview' not in text and 'ecosystem' not in text
            rank = 1
        else:
            match = path.endswith('.xlsx') and 'aescsf' in text and 'core' in text and 'toolkit' not in text
            version = re.search(r'\bv(?:ersion)?\s*(\d+)\b', text)
            rank = int(version.group(1)) if version else 1
        if match:
            approved_url(url, framework)
            candidates.append((rank, url))
    if not candidates:
        raise PolicyError('Could not locate the framework download on the publisher page. Open ' + PAGES[framework] + ' and import the file manually.', 5)
    top = max(rank for rank, _ in candidates)
    urls = {url for rank, url in candidates if rank == top}
    if len(urls) != 1:
        raise PolicyError('Publisher lists multiple possible framework files; select the correct one for manual import.', 5)
    return urls.pop()


def _index(root):
    try:
        return _read_index(root)
    except PolicyError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise PolicyError('The framework update index is unreadable. Saved assessments can still be opened.', 5)


def _read_index(root):
    path = local_file(root/'current.json')
    if not path.exists():
        return {'schemaVersion':1,'frameworks':{}}
    if path.stat().st_size > 65536:
        raise PolicyError('Framework index exceeds supported limits.', 5)
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schemaVersion') != 1 or not isinstance(data.get('frameworks'),dict) or not set(data['frameworks']) <= set(PAGES):
        raise PolicyError('Invalid framework update index.', 5)
    return data


def current(framework):
    try:
        return _read_current(framework)
    except PolicyError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise PolicyError('A cached framework is incomplete or unreadable. Saved assessments can still be opened.', 5)


def _read_current(framework):
    root = cache_root()
    item = _index(root)['frameworks'].get(framework)
    if item is None:
        return None
    version = item['version']
    if not re.fullmatch(r'[0-9a-f]{64}-publisher-\d+', version):
        raise PolicyError('Invalid cached framework version.', 5)
    folder = local_file(root/'versions'/framework/version)
    path = local_file(folder/'framework.json')
    source = local_file(folder/FILENAMES[framework])
    if path.stat().st_size > 16*1024*1024 or source.stat().st_size > MAX_BYTES:
        raise PolicyError('Cached framework exceeds supported limits.', 5)
    value = json.loads(path.read_text(encoding='utf-8'))
    if fingerprint(value) != item['digest'] or value['framework']['id'] != framework:
        raise PolicyError('Cached framework does not match its recorded fingerprint.', 5)
    if hashlib.sha256(source.read_bytes()).hexdigest() != value['framework']['sourceHash']:
        raise PolicyError('Cached publisher file changed after import.', 5)
    if not 1 <= len(value['requirements']) <= 20000 or any(r['frameworkId'] != framework or 'obligations' in r for r in value['requirements']):
        raise PolicyError('Invalid framework records in update cache.', 5)
    return value


def version_suffix():
    items = _index(cache_root())['frameworks']
    return '-local-' + fingerprint({key:value['digest'] for key,value in items.items()})[:12] if items else ''


@contextmanager
def update_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    lock = root/'update.lock'
    try:
        handle = lock.open('x')
    except FileExistsError:
        raise PolicyError('Another framework update is running.', 6)
    try:
        handle.close()
        yield
    finally:
        lock.unlink(missing_ok=True)


def update(frameworks=None, local_import=None, progress=None):
    selected = list(dict.fromkeys(frameworks if frameworks is not None else PAGES))
    if not selected or not set(selected) <= set(PAGES) or (local_import and len(selected) != 1):
        raise PolicyError('Select WA CSP, ASD ISM or AESCSF; manual import accepts one framework at a time.', 2)
    root = cache_root()
    results = []
    with update_lock(root):
        for key in selected:
            if progress: progress('Checking ' + key + '…')
            stage = root/('.stage-' + uuid.uuid4().hex)
            stage.mkdir()
            try:
                if local_import:
                    source = local_file(local_import)
                    if source.stat().st_size > MAX_BYTES:
                        raise PolicyError('Framework file exceeds 16 MiB.', 5)
                    body, uri = source.read_bytes(), PAGES[key]
                    acquisition = 'User-selected local import; latest version not verified online'
                else:
                    body, uri = download(discover(key), key)
                    acquisition = 'Downloaded from official publisher source'
                path = stage/FILENAMES[key]
                path.write_bytes(body)
                parsed = extract_worker(path, framework=key)
                metadata = parsed['framework']
                metadata['sourceUri'] = PAGES[key]
                metadata['extractHash'] = fingerprint(parsed['requirements'])
                old = current(key)
                if old and len(parsed['requirements']) < 0.8*len(old['requirements']):
                    raise PolicyError('The new file has over 20% fewer requirements. Kept the current version for manual investigation.', 5)
                checked = datetime.now(timezone.utc).isoformat()
                parsed.update(downloadUri=uri, retrievedAt=checked, acquisition=acquisition, parserVersion=IMPORT_VERSION)
                version = metadata['sourceHash'] + '-' + IMPORT_VERSION
                folder = root/'versions'/key/version
                index = _index(root)
                previous = index['frameworks'].get(key)
                if previous and previous['version'] == version:
                    results.append(dict(framework=key,status='Unchanged',edition=metadata['edition'],requirements=len(parsed['requirements']),checkedAt=checked,sourceUri=uri))
                    continue
                write_output(stage/'framework.json', json.dumps(parsed,ensure_ascii=False,indent=2))
                folder.parent.mkdir(parents=True,exist_ok=True)
                if folder.exists():
                    # Reusing an older version preserves its original acquisition record.
                    existing = json.loads((folder/'framework.json').read_text(encoding='utf-8'))
                    if existing['framework']['sourceHash'] != metadata['sourceHash'] or existing['requirements'] != parsed['requirements']:
                        raise PolicyError('Existing cached version differs; update was not activated.', 5)
                    parsed = existing
                else:
                    os.replace(stage, folder)
                index['frameworks'][key] = dict(version=version,digest=fingerprint(parsed),checkedAt=checked)
                write_output(root/'current.json',json.dumps(index,indent=2),force=True)
                results.append(dict(framework=key,status='Updated',edition=metadata['edition'],requirements=len(parsed['requirements']),checkedAt=checked,sourceUri=uri))
            except Exception as error:
                message = str(error) if isinstance(error, PolicyError) else ('Publisher blocked automated access; download from ' + PAGES[key] + ' and use Import framework file.' if isinstance(error,HTTPError) and error.code in (401,403) else 'Download or parsing failed; the previous framework version is unchanged. Check the publisher page and local folder access.')
                results.append(dict(framework=key,status='Failed',message=message,sourceUri=PAGES[key]))
            finally:
                if stage.exists():
                    assert stage.resolve().parent == root.resolve() and stage.name.startswith('.stage-')
                    shutil.rmtree(stage)
    return results
