"""Bounded Sentinel exports and traceable comparisons with department assessments.

The manifest is WACC metadata. Event files retain Microsoft's table column names.
Ratings remain as submitted; findings and reviewer decisions are separate records.
"""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import threading
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from .department_assessments import AssessmentError, ROOT

SCHEMA = 'wacc-sentinel-evidence-v1'
RULE_VERSION = '2026-09-16.1'
MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 50000
TABLES = ('DeviceEvents', 'DeviceInfo', 'DeviceProcessEvents', 'DeviceNetworkEvents',
          'DeviceLogonEvents', 'SigninLogs')
SOURCES = {
    'application': 'https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/operations/querying-application-control-events-centrally-using-advanced-hunting',
    'mfa': 'https://learn.microsoft.com/en-us/entra/identity/authentication/howto-mfa-reporting',
    'asr': 'https://learn.microsoft.com/en-us/defender-endpoint/attack-surface-reduction-rules-reference',
    'antivirus': 'https://learn.microsoft.com/en-us/defender-endpoint/detect-block-potentially-unwanted-apps-microsoft-defender-antivirus',
    'export': 'https://learn.microsoft.com/en-us/azure/azure-monitor/logs/logs-data-export',
    'lake': 'https://learn.microsoft.com/en-us/azure/sentinel/datalake/kql-queries',
    'wa': 'https://soc.cyber.wa.gov.au/onboarding/#7-migrating-sentinel-to-defender-xdr-portal',
}
for _table in TABLES:
    SOURCES[_table] = 'https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/' + _table.lower()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _json(data):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise AssessmentError('Duplicate JSON field: ' + k[:80])
            result[k] = v
        return result
    try:
        return json.loads(data, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, RecursionError) as exc:
        raise AssessmentError('Invalid JSON. Use UTF-8 JSON or JSON lines without duplicate fields.') from exc


def stamp(value):
    try:
        value = re.sub(r'(\.\d{6})\d+', r'\1', str(value))  # Sentinel can emit 100 ns precision; Python uses microseconds.
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise AssessmentError('Use ISO 8601 timestamps with a timezone, for example 2025-12-01T00:00:00Z.') from exc


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', value):
        raise AssessmentError('Use simple filenames without folders, spaces or special characters.')
    if value.endswith('.') or re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', value.split('.')[0]):
        raise AssessmentError('Use a filename that is not a reserved Windows device name.')
    return value


def _text(value, label, limit=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise AssessmentError(f'{label} must contain 1–{limit} characters.')
    return value.strip()


def validate_manifest(m, assessment):
    if not isinstance(m, dict) or m.get('schema') != SCHEMA:
        raise AssessmentError('Use a WACC Sentinel evidence manifest or example bundle.')
    if str(m.get('department', '')).casefold() != assessment['department'].casefold() or m.get('year') != assessment['year']:
        raise AssessmentError('The manifest department and year must match the selected assessment.')
    start, end = stamp(m.get('start')), stamp(m.get('end'))
    if start >= end or start.year != assessment['year'] or end > datetime(assessment['year']+1, 1, 1, tzinfo=timezone.utc):
        raise AssessmentError('The evidence window must fall within the assessment year; end is exclusive.')
    for key in ('workspace_id', 'entra_tenant_id'):
        if not isinstance(m.get(key), str) or not re.fullmatch(r'[0-9a-fA-F-]{36}', m[key]):
            raise AssessmentError(f'Set {key} to a UUID.')
        try: uuid.UUID(m[key])
        except ValueError as exc: raise AssessmentError(f'Invalid {key}.') from exc
    _text(m.get('scope_reference'), 'Scope reference')
    if m.get('source_kind') not in ('fictional-example', 'adls-gen2', 'sentinel-lake-csv', 'sentinel-export'):
        raise AssessmentError('Choose fictional-example, adls-gen2, sentinel-lake-csv or sentinel-export as source_kind.')
    for key in ('device_ids', 'mfa_user_ids', 'mfa_app_ids'):
        values = m.get(key)
        if not isinstance(values, list) or len(values) > 10000 or any(not isinstance(x, str) or not x or len(x)>160 for x in values):
            raise AssessmentError(f'{key} must be a list of identifiers (empty means no declared scope).')
        if len(values) != len(set(values)):
            raise AssessmentError(f'Remove duplicate {key}.')
    if type(m.get('authentication_details_final', False)) is not bool:
        raise AssessmentError('authentication_details_final must be true or false.')
    days = m.get('sensor_freshness_days', 7)
    if type(days) is not int or not 1 <= days <= 30:
        raise AssessmentError('sensor_freshness_days must be between 1 and 30.')
    files = m.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= 50:
        raise AssessmentError('List 1–50 event files in the manifest.')
    names = []
    for f in files:
        if not isinstance(f, dict): raise AssessmentError('Each file needs name, table and format fields.')
        names.append(_name(f.get('name')))
        if f.get('table') not in TABLES or f.get('format') not in ('jsonl', 'csv'):
            raise AssessmentError('Use a supported Sentinel table with jsonl or csv format.')
        if f.get('sha256') and not re.fullmatch('[0-9a-f]{64}', str(f['sha256'])):
            raise AssessmentError('File SHA-256 values must contain 64 lower-case hex characters.')
    if len(names) != len(set(names)) or 'manifest.json' in names:
        raise AssessmentError('Each event file needs a unique name other than manifest.json.')
    counts = m.get('expected_rows', {})
    if not isinstance(counts, dict) or any(k not in TABLES or type(v) is not int or v < 0 for k, v in counts.items()):
        raise AssessmentError('expected_rows must map supported table names to non-negative row counts.')
    tests = m.get('expected_block_tests', [])
    if not isinstance(tests, list) or len(tests) > 100:
        raise AssessmentError('List no more than 100 approved application-control test cases.')
    for test in tests:
        if not isinstance(test, dict) or test.get('device_id') not in m['device_ids'] or not re.fullmatch('[0-9a-f]{40}', str(test.get('sha1', ''))):
            raise AssessmentError('Each block test needs an in-scope device_id and a SHA-1 file hash.')
        if not start <= stamp(test.get('start')) < stamp(test.get('end')) <= end:
            raise AssessmentError('Block test times must fall within the evidence window.')
        _text(test.get('reference'), 'Block test approval reference')
    return m


def unpack(files):
    """Accept manifest + native files, or a transport bundle containing their text."""
    if not files or len(files) > 51 or sum(len(b) for _, b in files) > MAX_BYTES:
        raise AssessmentError('Choose a manifest and logs totalling at most 20 MB (50 event files).')
    if len(files) == 1:
        bundle = _json(files[0][1])
        if isinstance(bundle, dict) and 'manifest' in bundle and 'files' in bundle:
            try:
                files = [('manifest.json', json.dumps(bundle['manifest']).encode())] + [
                    (f['name'], f['text'].encode('utf-8')) for f in bundle['files']]
            except (TypeError, KeyError, AttributeError) as exc:
                raise AssessmentError('The bundle must contain a manifest and a list of named text files.') from exc
    result = {}
    if len(files) > 51 or sum(len(b) for _, b in files) > MAX_BYTES:
        raise AssessmentError('The expanded bundle exceeds the file or size limit.')
    for name, data in files:
        _name(name)
        if name in result: raise AssessmentError('Duplicate upload filename: ' + name)
        result[name] = data
    if 'manifest.json' not in result:
        raise AssessmentError('Include manifest.json alongside the event files.')
    return result


def _rows(data, format_):
    try:
        text = data.decode('utf-8-sig')
        if format_ == 'jsonl':
            for line, row in enumerate(text.splitlines(), 1):
                if row.strip(): yield line, _json(row)
        else:
            reader = csv.DictReader(io.StringIO(text), strict=True)
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise AssessmentError('CSV needs unique column headings.')
            for row in reader:
                if None in row or None in row.values(): raise AssessmentError('CSV row and header lengths differ.')
                yield reader.line_num, row
    except (UnicodeError, csv.Error) as exc:
        raise AssessmentError('Use UTF-8 CSV or JSON lines. CSV fields containing JSON must be quoted.') from exc


def parse(files, assessment):
    try:
        return _parse(files, assessment)
    except (TypeError, KeyError, AttributeError, OverflowError, RecursionError) as exc:
        raise AssessmentError('The manifest or event has an invalid field type. Check it against the examples.') from exc


def _parse(files, assessment):
    files = unpack(files)
    manifest = validate_manifest(_json(files['manifest.json']), assessment)
    if set(files) != {'manifest.json'} | {f['name'] for f in manifest['files']}:
        raise AssessmentError('Uploaded files must match the manifest exactly. Include empty files for tables with no events.')
    start, end = stamp(manifest['start']), stamp(manifest['end'])
    quality = dict(rows=0, duplicates=0, outside_window=0, outside_scope=0)
    counts = Counter(); seen = set(); events = []; summaries = []; identities = {}
    for descriptor in manifest['files']:
        name, table = descriptor['name'], descriptor['table']
        data = files[name]; sha = digest(data)
        if descriptor.get('sha256') and sha != descriptor['sha256']:
            raise AssessmentError(f'{name}: SHA-256 does not match the manifest.')
        summaries.append(dict(name=name, table=table, sha256=sha, bytes=len(data)))
        for line, row in _rows(data, descriptor['format']):
            quality['rows'] += 1
            if quality['rows'] > MAX_ROWS: raise AssessmentError('Limit each validation to 50,000 rows; narrow the evidence window.')
            if not isinstance(row, dict) or not row.get('TimeGenerated'):
                raise AssessmentError(f'{name}, record {line}: expected a Sentinel row with TimeGenerated.')
            when = stamp(row['TimeGenerated'])
            if str(row.get('TenantId', '')).lower() != manifest['workspace_id'].lower():
                raise AssessmentError(f'{name}, record {line}: TenantId must match the Log Analytics workspace ID.')
            if row.get('Type') and row['Type'] != table:
                raise AssessmentError(f'{name}, record {line}: Type does not match the manifest table.')
            required = ('Id', 'UserId', 'AppId', 'ResultType', 'AADTenantId') if table == 'SigninLogs' else ('DeviceId', 'ReportId')
            if any(row.get(k) is None or str(row.get(k)) == '' for k in required):
                raise AssessmentError(f'{name}, record {line}: missing required columns: {", ".join(required)}.')
            if any(not isinstance(row[k], (str, int)) or isinstance(row[k], bool) for k in required):
                raise AssessmentError(f'{name}, record {line}: identifiers and result codes must be strings or numbers.')
            if table != 'SigninLogs' and not re.fullmatch(r'\d+', str(row['ReportId'])):
                raise AssessmentError(f'{name}, record {line}: ReportId must be a non-negative integer.')
            if table == 'SigninLogs' and str(row['AADTenantId']).lower() != manifest['entra_tenant_id'].lower():
                raise AssessmentError(f'{name}, record {line}: AADTenantId does not match the Entra tenant.')
            if table not in ('DeviceInfo', 'SigninLogs') and not isinstance(row.get('ActionType'), str):
                raise AssessmentError(f'{name}, record {line}: missing ActionType.')
            if not start <= when < end:
                quality['outside_window'] += 1
                continue
            counts[table] += 1
            canonical = json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
            fingerprint = digest(table.encode()+b'\n'+canonical)
            if fingerprint in seen:
                quality['duplicates'] += 1
                continue
            seen.add(fingerprint)
            scoped = (row['UserId'] in manifest['mfa_user_ids'] and row['AppId'] in manifest['mfa_app_ids']) if table == 'SigninLogs' else row['DeviceId'] in manifest['device_ids']
            if not scoped:
                quality['outside_scope'] += 1
                continue
            identity = (table, str(row['Id'])) if table == 'SigninLogs' else (table, row['DeviceId'], when.isoformat(), str(row['ReportId']))
            identities.setdefault(identity, []).append(len(events))
            events.append(dict(table=table, row=row, time=when.isoformat(), file=name, line=line, sha256=fingerprint))
    conflicts = [indexes for indexes in identities.values() if len(indexes)>1]
    quality['conflicting_events'] = len(conflicts)
    for indexes in conflicts:
        for index in indexes: events[index]['conflicted'] = True
    quality['table_rows'] = {t: counts[t] for t in TABLES}
    quality['scope_rows'] = dict(Counter(e['table'] for e in events))
    quality['count_mismatches'] = [t for t, n in manifest.get('expected_rows', {}).items() if counts[t] != n]
    quality['unreconciled_tables'] = [t for t in TABLES if t not in manifest.get('expected_rows', {})]
    quality['first_event'] = min((e['time'] for e in events), default=None)
    quality['last_event'] = max((e['time'] for e in events), default=None)
    return manifest, events, quality, summaries, files


def _dynamic(value, type_):
    if isinstance(value, str):
        try: value = _json(value)
        except AssessmentError: return None
    return value if isinstance(value, type_) else None


def mfa_result(row, final):
    """Never infer an MFA bypass from AuthenticationRequirement alone."""
    if str(row.get('ResultType')) != '0' or str(row.get('IsInteractive')).lower() != 'true':
        return 'ignore'
    details = _dynamic(row.get('AuthenticationDetails'), list)
    if not final or not details or any(not isinstance(d, dict) for d in details): return 'review'
    successful = [d for d in details if str(d.get('succeeded')).lower() == 'true']
    for step in successful:
        method = str(step.get('authenticationMethod', '')).lower()
        result = str(step.get('authenticationStepResultDetail', '')).lower()
        if (str(step.get('authenticationStepRequirement', '')).lower() == 'multifactor authentication'
                or method in ('fido2 security key', 'fido2', 'windows hello for business', 'passwordless phone sign-in')
                or result in ('mfa requirement satisfied by claim in the token',
                              'mfa requirement satisfied by claim provided by external provider',
                              'mfa requirement satisfied by strong authentication')):
            return 'support'
    # A candidate for review, not a finding of intent or proof of every token claim.
    if (successful and all(str(s.get('authenticationMethod', '')).lower() == 'password' for s in successful)
            and row.get('AuthenticationRequirement') == 'singleFactorAuthentication'
            and str(row.get('ConditionalAccessStatus')).lower() == 'notapplied'):
        return 'gap'
    return 'review'


def evaluate(assessment, manifest, events, quality):
    ratings = {r['id']: r['rating'] for r in assessment['rows']}
    findings = []
    def add(id_, title, controls, policies, signal, summary, action, refs, source):
        claimed = {p: ratings.get(p, 'Not assessed') for p in policies}
        status = {'support':'Supports observed operation', 'review':'Needs review', 'none':'No evidence',
                  'gap':'Potential overstatement' if any(v in ('3', '4') for v in claimed.values()) else 'Gap observed'}[signal]
        findings.append(dict(id=id_, title=title, controls=controls, policies=claimed, status=status,
                             summary=summary, action=action, evidence=refs, sources=[SOURCES[source]], reviews=[]))
    clean = [e for e in events if not e.get('conflicted')]
    device = [e for e in clean if e['table'] == 'DeviceEvents']
    actions = lambda names: [e for e in device if e['row']['ActionType'] in names]
    blocked = actions({'AppControlCodeIntegrityPolicyBlocked', 'AppControlExecutableBlocked',
                       'AppControlPackagedAppBlocked', 'AppControlScriptBlocked', 'AppControlCIScriptBlocked'})
    audited = actions({'AppControlCodeIntegrityPolicyAudited', 'AppControlExecutableAudited',
                       'AppControlPackagedAppAudited', 'AppControlScriptAudited', 'AppControlCIScriptAudited'})
    execution = []
    for test in manifest.get('expected_block_tests', []):
        for e in clean:
            row = e['row']
            if (e['table'] == 'DeviceProcessEvents' and row.get('ActionType') == 'ProcessCreated'
                    and row['DeviceId'] == test['device_id'] and str(row.get('SHA1', '')).lower() == test['sha1']
                    and stamp(test['start']) <= stamp(e['time']) < stamp(test['end'])):
                execution.append(dict(**e, test_reference=test['reference']))
    signal = 'gap' if execution else 'review' if audited else 'support' if blocked else 'none'
    add('TV-AC', 'Application control', ['AP-01', 'AP-02'], ['3.1.1a'], signal,
        f'Programs that ran when the test required a block: {len(execution)}. Block events: {len(blocked)}; audit events: {len(audited)}.',
        'Inspect the named device’s effective WDAC/AppLocker policies, exclusions and test approval. Check whether an audit policy coexists with an enforced policy.',
        execution + blocked + audited, 'application')

    auth = {k: [] for k in ('support', 'gap', 'review', 'ignore')}
    for e in events:
        if e['table'] == 'SigninLogs': auth['review' if e.get('conflicted') else mfa_result(e['row'], manifest.get('authentication_details_final', False))].append(e)
    signal = 'gap' if auth['gap'] else 'review' if auth['review'] else 'support' if auth['support'] else 'none'
    add('TV-MFA', 'Multi-factor authentication', ['MF-01', 'PA-03'], ['3.1.1a', '3.6d'], signal,
        f'MFA or a strong/reused claim: {len(auth["support"])} sign-ins. Password only, no Conditional Access applied: {len(auth["gap"])}. Unclear authentication: {len(auth["review"])}. Failed/non-interactive sign-ins excluded: {len(auth["ignore"])}.',
        'Review the final sign-in authentication steps, token context, applicable Conditional Access policies and approved exceptions for the named users and apps.',
        auth['gap'] + auth['review'] + auth['support'], 'mfa')

    latest = {}
    for e in events:
        if e['table'] == 'DeviceInfo' and (e['row']['DeviceId'] not in latest or stamp(e['time']) > stamp(latest[e['row']['DeviceId']]['time'])):
            latest[e['row']['DeviceId']] = e
    fresh = stamp(manifest['end']) - timedelta(days=manifest.get('sensor_freshness_days', 7))
    unhealthy = [e for e in latest.values() if not e.get('conflicted') and stamp(e['time']) >= fresh
                 and (e['row'].get('OnboardingStatus') in ('Offboarded', 'Can be onboarded')
                      or e['row'].get('SensorHealthState') in ('Inactive', 'ImpairedCommunication', 'NoSensorData'))]
    healthy = [e for e in latest.values() if not e.get('conflicted') and stamp(e['time']) >= fresh and e['row'].get('OnboardingStatus') == 'Onboarded' and e['row'].get('SensorHealthState') == 'Active']
    missing = len(manifest['device_ids']) - len(healthy) - len(unhealthy)
    signal = 'gap' if unhealthy else 'review' if missing else 'support' if healthy else 'none'
    add('TV-EDR', 'Endpoint sensor coverage', ['SM-01', 'AM-01'], ['4.2a'], signal,
        f'{len(healthy)} of {len(manifest["device_ids"])} declared devices have recent active, onboarded sensors; {len(unhealthy)} report another state; {missing} lack a current, complete status.',
        'Reconcile the device IDs with the asset inventory and inspect sensor health at the end of the evidence window. Missing records need collection or retention checks.',
        unhealthy + list(latest.values()), 'DeviceInfo')

    asr_block = actions({'AsrOfficeChildProcessBlocked', 'AsrLsassCredentialTheftBlocked'})
    asr_audit = actions({'AsrOfficeChildProcessAudited', 'AsrLsassCredentialTheftAudited'})
    add('TV-ASR', 'Attack surface reduction', ['UH-02'], ['3.1.1a'],
        'review' if asr_audit else 'support' if asr_block else 'none',
        f'Office child-process / credential-theft rules: {len(asr_block)} block events; {len(asr_audit)} audit events.',
        'Confirm the applicable ASR rule and exclusions on the affected device. An audit event records observation rather than prevention.',
        asr_audit + asr_block, 'asr')

    activity = [e for e in clean if e['table'] in ('DeviceProcessEvents', 'DeviceNetworkEvents', 'DeviceLogonEvents')]
    observed = {e['table'] for e in activity}
    missing_tables = set(('DeviceProcessEvents', 'DeviceNetworkEvents', 'DeviceLogonEvents')) - observed
    devices = {e['row']['DeviceId'] for e in activity}
    add('TV-LOG', 'Central endpoint logging', ['SM-01', 'SM-03'], ['4.2a'],
        'none' if not activity else 'review' if missing_tables or len(devices) < len(manifest['device_ids']) else 'support',
        f'{len(activity)} process, network and logon events from {len(devices)} declared devices. Missing activity tables: {", ".join(sorted(missing_tables)) or "none"}.',
        'Compare export counts, connector health and retention with Sentinel. Obtain analyst review records for the event-review control.',
        activity, 'export')

    av = actions({'AntivirusDetection'})
    pending = [e for e in av if str((_dynamic(e['row'].get('AdditionalFields'), dict) or {}).get('WasRemediated')).lower() != 'true']
    add('TV-AV', 'Antivirus detection and follow-up', ['SM-03', 'IR-02'], ['4.1a'],
        'review' if pending else 'support' if av else 'none',
        f'Antivirus detections: {len(av)}. Events without recorded remediation: {len(pending)}.',
        'Open the related Defender alert and device timeline. Match remediation and case closure records; an initial detection can precede remediation.',
        pending + [e for e in av if e not in pending], 'antivirus')
    # Store references once per finding; payloads are small but may contain sensitive evidence.
    for finding in findings:
        finding['evidence'] = list({(e['file'], e['line']): e for e in finding['evidence']}.values())
    return findings


class ValidationStore:
    def __init__(self, assessment_store):
        self.assessments = assessment_store
        self.path = assessment_store.path / 'validation'
        self.lock = threading.Lock()

    def all(self, assessment_key=None):
        with self.lock:
            try:
                records = [json.loads(p.read_text(encoding='utf-8')) for p in self.path.glob('*/report.json') if re.fullmatch('[0-9a-f]{32}', p.parent.name)]
            except (OSError, ValueError) as exc:
                raise AssessmentError('Validation storage cannot be read. Restore it from your backup.') from exc
        return sorted([r for r in records if assessment_key is None or r['assessment_key'] == assessment_key], key=lambda r: r['created_at'], reverse=True)

    def get(self, run_id):
        return next((r for r in self.all() if r['id'] == run_id), None)

    def import_files(self, files, assessment_key):
        assessment = next((a for a in self.assessments.all() if a['key'] == assessment_key), None)
        if not assessment: raise AssessmentError('Import and select the annual assessment first.')
        manifest, events, quality, summaries, originals = parse(files, assessment)
        report = dict(id=uuid.uuid4().hex, schema=SCHEMA, rule_version=RULE_VERSION,
                      assessment_key=assessment_key, assessment_sha256=assessment['sha256'],
                      created_at=datetime.now(timezone.utc).isoformat(), manifest=manifest,
                      files=summaries, manifest_sha256=digest(originals['manifest.json']), quality=quality,
                      findings=evaluate(assessment, manifest, events, quality))
        with self.lock:
            self.path.mkdir(parents=True, exist_ok=True)
            temporary = self.path / ('.pending-' + report['id'])
            try:
                (temporary/'originals').mkdir(parents=True)
                for name, data in originals.items(): (temporary/'originals'/name).write_bytes(data)
                (temporary/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
                os.replace(temporary, self.path/report['id'])
            finally:
                if temporary.exists(): shutil.rmtree(temporary)
        return report

    def review(self, run_id, finding_id, decision, reviewer, note):
        if decision not in ('Confirmed gap', 'Explained exception', 'Evidence accepted', 'More evidence needed'):
            raise AssessmentError('Choose a review decision.')
        _text(reviewer, 'Reviewer', 120); _text(note, 'Review note', 2000)
        with self.lock:
            if not re.fullmatch('[0-9a-f]{32}', run_id): raise AssessmentError('Unknown validation run.')
            path = self.path/run_id/'report.json'
            if not path.exists(): raise AssessmentError('Unknown validation run.')
            report = json.loads(path.read_text(encoding='utf-8'))
            current = next((a for a in self.assessments.all() if a['key'] == report['assessment_key']), None)
            if not current or current['sha256'] != report['assessment_sha256']:
                raise AssessmentError('The assessment changed. Import the logs again to compare the current ratings.')
            finding = next((f for f in report['findings'] if f['id'] == finding_id), None)
            if not finding: raise AssessmentError('Unknown check.')
            finding['reviews'].append(dict(decision=decision, reviewer=reviewer.strip(), note=note.strip(), at=datetime.now(timezone.utc).isoformat()))
            temp = path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
            try:
                temp.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
                os.replace(temp, path)
            finally:
                if temp.exists(): temp.unlink()
        return report


def example_files(year=2025):
    folder = ROOT/'examples/telemetry'/str(year)
    manifest = (folder/'manifest.json').read_bytes()
    return [('manifest.json', manifest)] + [(f['name'], (folder/f['name']).read_bytes()) for f in _json(manifest)['files']]


def example_bundle(year=2025):
    files = example_files(year)
    return json.dumps(dict(manifest=_json(files[0][1]), files=[dict(name=n, text=b.decode()) for n, b in files[1:]]), indent=2).encode()
