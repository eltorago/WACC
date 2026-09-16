"""Additional real Sentinel schemas and contributing WA CSP 2024 checks.

Transport is independent of the rules. Policy deadlines and inventory scope are
authored assessment context, kept outside the native Microsoft event rows.
"""
import math
from datetime import timedelta
from .department_assessments import AssessmentError, REQUIREMENTS

TABLE_SCHEMAS = {
    'DeviceTvmSoftwareInventory': ('DeviceId', 'SoftwareVendor', 'SoftwareName', 'SoftwareVersion'),
    'DeviceTvmSoftwareVulnerabilities': ('DeviceId', 'SoftwareVendor', 'SoftwareName', 'SoftwareVersion', 'CveId'),
    'AuditLogs': ('Id', 'AADTenantId', 'ActivityDisplayName', 'Result'),
    'AZFWNetworkRule': ('_ResourceId', 'SourceIp', 'DestinationIp', 'DestinationPort', 'Protocol', 'Action'),
    'SecurityIncident': ('IncidentName', 'Status'),
    'AddonAzureBackupJobs': ('JobUniqueId', 'BackupItemUniqueId', 'JobOperation', 'JobStatus'),
}
WORKSPACE_IN_DESCRIPTOR = ('AuditLogs', 'AddonAzureBackupJobs')
EXTRA_SCOPE = ('identity_user_ids', 'firewall_resource_ids', 'incident_names', 'backup_item_ids')


def validate_context(m):
    from .telemetry import stamp, _text
    for key in EXTRA_SCOPE:
        values = m.get(key, [])
        if not isinstance(values, list) or len(values)>10000 or any(not isinstance(v,str) or not v or len(v)>1000 for v in values):
            raise AssessmentError(f'{key} must be a list of scoped identifiers.')
        if len(set(v.casefold() for v in values)) != len(values): raise AssessmentError(f'Remove duplicate {key}.')
    for key in ('patch_deadlines', 'restore_targets'):
        values = m.get(key, [])
        if not isinstance(values, list) or len(values)>100: raise AssessmentError(f'{key} must contain at most 100 criteria.')
        seen = set()
        for v in values:
            if not isinstance(v,dict): raise AssessmentError(f'Each {key} entry must be an object.')
            _text(v.get('reference'), 'Assessment criterion reference')
            if key == 'patch_deadlines':
                for field in ('device_id','cve_id','software_name'): _text(v.get(field), field, 160)
                if v['device_id'] not in m['device_ids']: raise AssessmentError('Patch criteria must identify an in-scope device.')
                stamp(v.get('due'))
                unique = (v['device_id'],v['cve_id'],v['software_name'])
            else:
                if v.get('backup_item_id') not in m.get('backup_item_ids',[]): raise AssessmentError('Restore targets must identify an in-scope backup item.')
                hours = v.get('max_duration_hours')
                if type(hours) not in (int,float) or not math.isfinite(hours) or not 0<hours<=8760:
                    raise AssessmentError('Restore duration targets must be positive hours, up to one year.')
                unique = v['backup_item_id']
            if unique in seen: raise AssessmentError(f'Duplicate criterion in {key}.')
            seen.add(unique)


def row_scope_and_identity(table, row, manifest, when):
    from .telemetry import _dynamic
    if table.startswith('DeviceTvm'):
        scope = row['DeviceId'] in manifest['device_ids']
        key = (row['DeviceId'],row['SoftwareVendor'],row['SoftwareName'],row['SoftwareVersion'],row.get('CveId',''))
    elif table == 'AuditLogs':
        targets = _dynamic(row.get('TargetResources'),list)
        if targets is None or any(not isinstance(v,dict) for v in targets): raise AssessmentError('AuditLogs.TargetResources must be a JSON array of target objects.')
        scope = any(str(v.get('id','')).casefold() in {s.casefold() for s in manifest.get('identity_user_ids',[])} for v in targets)
        return scope, (table,row['Id'])
    elif table == 'AZFWNetworkRule':
        scope = row['_ResourceId'].casefold() in {v.casefold() for v in manifest.get('firewall_resource_ids',[])}
        key = (row['_ResourceId'],row['SourceIp'],row['DestinationIp'],str(row['DestinationPort']),row['Protocol'],str(row.get('SourcePort','')))
    elif table == 'SecurityIncident':
        scope = row['IncidentName'] in manifest.get('incident_names',[])
        key = (row['IncidentName'],)
    else:
        scope = row['BackupItemUniqueId'] in manifest.get('backup_item_ids',[])
        key = (row['JobUniqueId'],)
    # Incident/job state changes and TVM snapshots are legitimate successive records.
    # Different payloads at the same identity/time are ambiguous, not two observations.
    return scope, (table,)+key+(when.isoformat(),)


def _latest(events, fields):
    from .telemetry import stamp
    result = {}
    for e in events:
        key = tuple(str(e['row'].get(f,'')) for f in fields)
        if key not in result or stamp(e['time']) > stamp(result[key]['time']): result[key] = e
    return list(result.values())


def extend_findings(manifest, events, add):
    from .telemetry import stamp, _dynamic
    clean = [e for e in events if not e.get('conflicted')]
    rows = lambda table: [e for e in clean if e['table']==table]
    fresh = stamp(manifest['end']) - timedelta(days=manifest.get('sensor_freshness_days',7))

    inventory = [e for e in _latest([e for e in events if e['table']=='DeviceTvmSoftwareInventory'],
                 ('DeviceId','SoftwareVendor','SoftwareName','SoftwareVersion')) if not e.get('conflicted') and stamp(e['time'])>=fresh]
    devices = {e['row']['DeviceId'] for e in inventory}
    add('TV-ASSET','Software inventory',['AM-01'],['2.1a','2.1b'],
        'none' if not inventory else 'review' if len(devices)<len(manifest['device_ids']) else 'support',
        f'Recent software inventory: {len(inventory)} entries across {len(devices)} of {len(manifest["device_ids"])} declared devices.',
        'Reconcile device, application and version records with the asset register, including servers outside Defender coverage.', inventory,'DeviceTvmSoftwareInventory')

    vulnerabilities = [e for e in _latest([e for e in events if e['table']=='DeviceTvmSoftwareVulnerabilities'],
                       ('DeviceId','SoftwareVendor','SoftwareName','SoftwareVersion','CveId')) if not e.get('conflicted') and stamp(e['time'])>=fresh]
    overdue = []
    for e in vulnerabilities:
        r = e['row']; tags = _dynamic(r.get('CveTags'),list) or []
        for deadline in manifest.get('patch_deadlines',[]):
            if (r['DeviceId']==deadline['device_id'] and r['CveId']==deadline['cve_id'] and r['SoftwareName']==deadline['software_name']
                    and stamp(e['time'])>stamp(deadline['due']) and r.get('RecommendedSecurityUpdateId')
                    and 'NoSecurityUpdate' not in tags):
                overdue.append(dict(**e, test_reference=deadline['reference']))
    high = sum(e['row'].get('VulnerabilitySeverityLevel') in ('High','Critical') for e in vulnerabilities)
    add('TV-PATCH','Vulnerability remediation',['VM-01'],['3.1.1a'],
        'gap' if overdue else 'review' if vulnerabilities else 'none',
        f'Recent vulnerability observations: {len(vulnerabilities)}; high/critical: {high}; beyond a documented patch deadline: {len(overdue)}.',
        'Verify the software version, available update, deadline and exception. An empty vulnerability export does not establish patch compliance.',
        overdue+[e for e in vulnerabilities if not any(e['sha256']==o['sha256'] for o in overdue)],'DeviceTvmSoftwareVulnerabilities')

    audit = rows('AuditLogs')
    lifecycle = [e for e in audit if e['row']['ActivityDisplayName'] in ('Add user','Update user','Delete user')]
    success = [e for e in lifecycle if str(e['row']['Result']).lower()=='success']
    add('TV-IAM','Account lifecycle',['IA-01'],['3.6a'],
        'review' if len(success)<len(lifecycle) else 'support' if success else 'none',
        f'Account creation/change/removal events: {len(lifecycle)}; successful: {len(success)}.',
        'Match the target user and change time to joiner, mover or leaver records and approvals.',lifecycle,'AuditLogs')
    privilege = [e for e in audit if e['row']['ActivityDisplayName'] in ('Add member to role','Remove member from role','Add eligible member to role','Remove eligible member from role')]
    add('TV-PRIV','Privileged access changes',['IA-02','PA-01','PA-04'],['3.6b'],
        'review' if privilege else 'none',
        f'Role assignment/removal events requiring approval checks: {len(privilege)}.',
        'Match each role, target user and initiator to an approved request and current access review.',privilege,'AuditLogs')

    firewall = rows('AZFWNetworkRule')
    denied = [e for e in firewall if str(e['row']['Action']).lower()=='deny']
    add('TV-NET','Network boundary enforcement',['NA-01','NA-02'],['3.6f'],
        'support' if denied else 'review' if firewall else 'none',
        f'Firewall rule matches: {len(firewall)}; denied connections: {len(denied)}.',
        'Compare the matched rules and permitted flows with the approved network design. Review default-deny coverage and exceptions.',firewall,'AZFWNetworkRule')

    incidents = _latest([e for e in events if e['table']=='SecurityIncident'],('IncidentName',))
    slow = []; unknown = []
    for e in incidents:
        r = e['row']
        try:
            delay = (stamp(r.get('FirstModifiedTime'))-stamp(r.get('CreatedTime'))).total_seconds()/3600
            if e.get('conflicted') or delay<0: unknown.append(e)
            elif delay>4: slow.append(e)
        except AssessmentError: unknown.append(e)
    add('TV-TRIAGE','Incident review and triage',['SM-03','IN-01','IR-02'],['4.1a','4.1b','5.1b'],
        'review' if incidents else 'none',
        f'Incidents: {len(incidents)}; first recorded change after four hours: {len(slow)}; timing unclear: {len(unknown)}.',
        'Read the incident timeline and analyst notes to establish detection, triage, response and daily review times. A status change or automated update is not a triage decision.',incidents,'SecurityIncident')

    jobs = _latest([e for e in events if e['table']=='AddonAzureBackupJobs'],('JobUniqueId',))
    backups = [e for e in jobs if str(e['row']['JobOperation']).lower()=='backup']
    complete = [e for e in backups if not e.get('conflicted') and e['row']['JobStatus']=='Completed']
    items = {e['row']['BackupItemUniqueId'] for e in complete}
    add('TV-BACKUP','Backup job outcomes',['BR-01','BR-02'],['3.1.1a'],
        'none' if not backups else 'review' if len(complete)<len(backups) or len(items)<len(manifest.get('backup_item_ids',[])) else 'support',
        f'Backup jobs: {len(backups)}; completed: {len(complete)}; protected items with a completed job: {len(items)}.',
        'Reconcile jobs with the backup schedule and protected asset list. Inspect failed jobs, recovery-point retention and isolation settings.',backups,'AddonAzureBackupJobs')
    restores = [e for e in jobs if str(e['row']['JobOperation']).lower() in ('restore','recovery')]
    met = []; exceeded = []; unresolved = []
    for e in restores:
        r = e['row']; target = next((v for v in manifest.get('restore_targets',[]) if v['backup_item_id']==r['BackupItemUniqueId']),None)
        try: duration = float(r.get('JobDurationInSecs')) if type(r.get('JobDurationInSecs')) in (int,float,str) else float('nan')
        except (TypeError,ValueError): duration = float('nan')
        if e.get('conflicted') or not target or r['JobStatus']!='Completed' or not math.isfinite(duration) or duration<0: unresolved.append(e)
        elif duration>target['max_duration_hours']*3600: exceeded.append(dict(**e,test_reference=target['reference']))
        else: met.append(dict(**e,test_reference=target['reference']))
    add('TV-RESTORE','Restore duration',['BR-03'],['6.1'],
        'gap' if exceeded else 'review' if unresolved else 'support' if met else 'none',
        f'Restore jobs within the documented job target: {len(met)}; exceeded: {len(exceeded)}; need review: {len(unresolved)}.',
        'Check the plan’s recovery target and restore-test report. Confirm application availability and data integrity after the job completed.',exceeded+unresolved+met,'AddonAzureBackupJobs')


def policy_coverage(report):
    """All 86 criteria stay visible; a telemetry slice is not a full-policy pass."""
    result = []
    for id_, requirement in REQUIREMENTS.items():
        checks = [f for f in report['findings'] if id_ in f['policies']]
        result.append(dict(id=id_, area=requirement['area'], prompt=requirement['prompt'],
                           checks=[f['id'] for f in checks], evidence=requirement['evidence'],
                           status='Log evidence and document review' if checks else 'Document or separate test required'))
    return result
