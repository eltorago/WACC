"""Read explicitly selected ADLS Gen2 files using the operator's Azure CLI login."""
import json
import re
import shutil
import subprocess
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .department_assessments import AssessmentError
from .telemetry import MAX_BYTES, validate_manifest


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AssessmentError('Storage redirects are not accepted. Check the account and file path.')


def storage_url(account, filesystem, path):
    if not isinstance(account, str) or not re.fullmatch('[a-z0-9]{3,24}', account):
        raise AssessmentError('Use an Azure public-cloud storage account name (3–24 lower-case letters/digits).')
    if not isinstance(filesystem, str) or not re.fullmatch('[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]', filesystem) or '--' in filesystem:
        raise AssessmentError('Use a valid ADLS filesystem/container name.')
    if (not isinstance(path, str) or not path or len(path) > 1024 or '\\' in path
            or any(p in ('', '.', '..') for p in path.split('/')) or any(ord(c) < 32 for c in path)):
        raise AssessmentError('Use a relative ADLS file path without traversal or empty segments.')
    return f'https://{account}.dfs.core.windows.net/{filesystem}/' + quote(path, safe='/=')


def fetch_files(manifest, assessment):
    validate_manifest(manifest, assessment)
    if manifest['source_kind'] != 'adls-gen2': raise AssessmentError('Set source_kind to adls-gen2 for an Azure read.')
    config = manifest.get('azure', {})
    if not isinstance(config, dict): raise AssessmentError('Set azure.account in the manifest.')
    urls = [storage_url(config.get('account'), f.get('filesystem'), f.get('adls_path')) for f in manifest['files']]
    cli = shutil.which('az')
    if not cli: raise AssessmentError('Install Azure CLI and run az login for the storage tenant first.')
    try:
        result = subprocess.run([cli, 'account', 'get-access-token', '--resource', 'https://storage.azure.com/',
                                 '--tenant', manifest['entra_tenant_id'], '--query', 'accessToken', '--output', 'tsv',
                                 '--only-show-errors'], capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AssessmentError('Azure CLI could not obtain a storage token. Check your login and retry.') from exc
    token = result.stdout.strip()
    if result.returncode or not token or any(c.isspace() for c in token):
        raise AssessmentError('Azure CLI did not return a storage token. Run az login for the manifest tenant and retry.')
    opener = build_opener(NoRedirect())
    files = []; total = 0
    # Validate every destination before obtaining credentials or making any request.
    for descriptor, url in zip(manifest['files'], urls):
        request = Request(url, headers={'Authorization':'Bearer '+token, 'x-ms-version':'2023-08-03'})
        try:
            with opener.open(request, timeout=30) as response:
                payload = response.read(MAX_BYTES-total+1)
                if response.status != 200: raise AssessmentError('Storage did not return a complete file.')
                length = response.headers.get('Content-Length')
                if length and (not length.isdigit() or int(length) != len(payload)):
                    raise AssessmentError('Storage file is incomplete or exceeds the download limit. Narrow the export and retry.')
                descriptor['download'] = dict(etag=response.headers.get('ETag', ''), last_modified=response.headers.get('Last-Modified', ''))
        except HTTPError as exc:
            raise AssessmentError(f'Storage returned HTTP {exc.code}. Check the selected file and Storage Blob Data Reader access.') from None
        except (URLError, OSError, HTTPException) as exc:
            raise AssessmentError('Storage could not be reached. Check DNS, firewall/private endpoint access and file paths.') from None
        total += len(payload)
        if total > MAX_BYTES: raise AssessmentError('The selected Azure files exceed 20 MB. Narrow the evidence window.')
        files.append((descriptor['name'], payload))
    files.insert(0, ('manifest.json', json.dumps(manifest, indent=2).encode()))
    return files


def command(args):
    from pathlib import Path
    from .department_assessments import Store
    from .telemetry import ValidationStore, _json
    try:
        store = Store()
        path = Path(args.manifest)
        if path.stat().st_size > 1024*1024: raise AssessmentError('Manifest exceeds 1 MB.')
        manifest = _json(path.read_bytes())
        if not isinstance(manifest, dict): raise AssessmentError('The manifest must be a JSON object.')
        assessment = next((a for a in store.all() if a['department'].casefold() == str(manifest.get('department', '')).casefold() and a['year'] == manifest.get('year')), None)
        if not assessment: raise AssessmentError('Import the department/year workbook in Assessments first.')
        validate_manifest(manifest, assessment)
        if args.adls:
            files = fetch_files(manifest, assessment)
        else:
            files = [('manifest.json', path.read_bytes())]
            total = len(files[0][1])
            for f in manifest['files']:
                child = path.parent/f['name']
                total += child.stat().st_size
                if total > MAX_BYTES: raise AssessmentError('The selected files exceed 20 MB.')
                files.append((f['name'], child.read_bytes()))
        report = ValidationStore(store).import_files(files, assessment['key'])
        print('Validation saved. Open http://127.0.0.1:8765/assessments/validation?run='+report['id'])
        for f in report['findings']: print(f['id']+': '+f['status'])
        return 0
    except (AssessmentError, OSError) as exc:
        print('Validation failed: '+(str(exc) if isinstance(exc, AssessmentError) else 'Cannot read or save the selected local files.'))
        return 1
