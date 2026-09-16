"""Create fictional Sentinel table rows; never collect or contact a real tenant."""
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = '11111111-1111-4111-8111-111111111111'
TENANT = '22222222-2222-4222-8222-222222222222'
DEVICES = [str(n)*40 for n in (3, 4, 5)]
USERS = [f'66666666-6666-4666-8666-{n:012}' for n in (1, 2, 3)]
APP = '77777777-7777-4777-8777-777777777777'
TEST_HASH = 'a'*40
FIREWALL = '/subscriptions/99999999-9999-4999-8999-999999999999/resourceGroups/silly-walks/providers/Microsoft.Network/azureFirewalls/demo-firewall'
BACKUP_ITEM = 'fictional-vault;silly-walks;records-server'


def build(year):
    tables = {t: [] for t in ('DeviceEvents', 'DeviceInfo', 'DeviceProcessEvents', 'DeviceNetworkEvents', 'DeviceLogonEvents', 'SigninLogs')}
    for table in ('DeviceTvmSoftwareInventory','DeviceTvmSoftwareVulnerabilities','AuditLogs','AZFWNetworkRule','SecurityIncident','AddonAzureBackupJobs'):
        tables[table] = []
    def device(table, n, action=None, when='29T12:00:00Z', **fields):
        row = dict(TimeGenerated=f'{year}-12-{when}', TenantId=WORKSPACE, Type=table,
                   DeviceId=DEVICES[n], DeviceName=f'sw-laptop-{n+1:02}.example.invalid',
                   ReportId=len(tables[table])+1)
        if action: row['ActionType'] = action
        row.update(fields); tables[table].append(row)
    for n in range(3):
        healthy = year == 2025 or (year == 2024 and n < 2) or (year == 2023 and n == 0)
        device('DeviceInfo', n, OSPlatform='Windows11', OnboardingStatus='Onboarded',
               SensorHealthState='Active' if healthy else 'Inactive')
        device('DeviceEvents', n, 'AppControlCodeIntegrityPolicyBlocked' if n == 0 and year >= 2024 else 'AppControlCodeIntegrityPolicyAudited',
               when='15T10:00:00Z', FileName='unapproved-demo.exe', FolderPath='C:\\WACC-Test', SHA1=TEST_HASH,
               InitiatingProcessFileName='explorer.exe', AdditionalFields=json.dumps({'PolicyName':'Silly Walks approved applications'}))
        device('DeviceProcessEvents', n, 'ProcessCreated', FileName='notepad.exe', FolderPath='C:\\Windows\\System32',
               SHA1='b'*40, ProcessId=1200+n, ProcessCommandLine='notepad.exe', AccountName=f'demo.user{n+1}', AccountDomain='SILLYWALKS')
        device('DeviceNetworkEvents', n, 'ConnectionSuccess', RemoteIP=f'192.0.2.{20+n}', RemotePort=443,
               LocalIP=f'198.51.100.{10+n}', LocalPort=50000+n, Protocol='Tcp', RemoteUrl='service.example.invalid',
               InitiatingProcessFileName='msedge.exe')
        device('DeviceLogonEvents', n, 'LogonSuccess', LogonType='Interactive', AccountName=f'demo.user{n+1}',
               AccountDomain='SILLYWALKS', IsLocalAdmin=False)
    # A harmless, pre-approved negative test executed on laptop 2 in every year.
    device('DeviceProcessEvents', 1, 'ProcessCreated', when='15T10:00:01Z', FileName='unapproved-demo.exe',
           FolderPath='C:\\WACC-Test', SHA1=TEST_HASH, ProcessId=2200, ProcessCommandLine='C:\\WACC-Test\\unapproved-demo.exe')
    if year == 2025:
        # Laptop 3 has no application-control event in this sample.
        tables['DeviceEvents'] = [e for e in tables['DeviceEvents'] if e['DeviceId'] != DEVICES[2]]
    device('DeviceEvents', 0, 'AsrOfficeChildProcessBlocked' if year >= 2024 else 'AsrOfficeChildProcessAudited',
           when='20T09:00:00Z', FileName='demo-child.exe', InitiatingProcessFileName='winword.exe')
    if year == 2024:
        device('DeviceEvents', 2, 'AsrLsassCredentialTheftAudited', when='20T09:01:00Z', FileName='demo-agent.exe')
    device('DeviceEvents', 0, 'AntivirusDetection', when='21T08:00:00Z', FileName='fictional-pua.exe',
           FolderPath='C:\\WACC-Test', SHA1='c'*40,
           AdditionalFields=json.dumps({'ThreatName':'PUA:Win32/FictionalDemo', 'WasExecutingWhileDetected':False, 'WasRemediated':year==2025}))
    def signin(n, method, requirement, detail, ca='success', result='0', suffix=0):
        details = [dict(authenticationStepDateTime=f'{year}-12-22T08:{n:02}:00Z', authenticationMethod=method,
                        succeeded=result=='0', authenticationStepResultDetail=detail,
                        authenticationStepRequirement='Multifactor authentication' if requirement=='multiFactorAuthentication' else 'Primary authentication')]
        tables['SigninLogs'].append(dict(TimeGenerated=f'{year}-12-22T08:{n:02}:00Z', TenantId=WORKSPACE, AADTenantId=TENANT,
            Type='SigninLogs', Id=f'88888888-8888-4888-8888-{year*100+n*10+suffix:012}',
            UserId=USERS[n], UserPrincipalName=f'demo.user{n+1}@sillywalks.example.invalid', AppId=APP,
            AppDisplayName='Silly Walks demo records', IPAddress=f'192.0.2.{60+n}', IsInteractive=True,
            ResultType=result, ConditionalAccessStatus=ca, AuthenticationRequirement=requirement,
            AuthenticationDetails=json.dumps(details)))
    signin(0, 'Mobile app notification' if year > 2023 else 'Password',
           'multiFactorAuthentication' if year > 2023 else 'singleFactorAuthentication',
           'MFA successfully completed' if year > 2023 else 'Correct password', 'success' if year > 2023 else 'notApplied')
    signin(1, 'Password', 'singleFactorAuthentication', 'Correct password', 'notApplied')
    # Explicit regression example: single-factor label with a previously satisfied MFA claim.
    signin(2, 'Previously satisfied', 'singleFactorAuthentication', 'MFA requirement satisfied by claim in the token')
    signin(1, 'Mobile app notification', 'multiFactorAuthentication', 'User declined the authentication', 'failure', '500121', 1)
    for n in range(1 if year==2023 else 3):
        tables['DeviceTvmSoftwareInventory'].append(dict(TimeGenerated=f'{year}-12-29T12:00:00Z',TenantId=WORKSPACE,
            Type='DeviceTvmSoftwareInventory',DeviceId=DEVICES[n],DeviceName=f'sw-laptop-{n+1:02}.example.invalid',
            OSPlatform='Windows11',SoftwareVendor='fictional_vendor',SoftwareName='demo_records_client',SoftwareVersion='2.0'))
    # Placeholder CVE and product are fictional. The columns and values' types are native.
    tables['DeviceTvmSoftwareVulnerabilities'].append(dict(TimeGenerated=f'{year}-12-29T12:00:00Z',TenantId=WORKSPACE,
        Type='DeviceTvmSoftwareVulnerabilities',DeviceId=DEVICES[0],DeviceName='sw-laptop-01.example.invalid',
        SoftwareVendor='fictional_vendor',SoftwareName='demo_records_client',SoftwareVersion='2.0',CveId='CVE-2099-99999',
        VulnerabilitySeverityLevel='High',CveTags=[],RecommendedSecurityUpdate='Fictional security update',RecommendedSecurityUpdateId='DEMO-UPDATE-01'))
    for n,activity in enumerate(('Add user','Delete user','Add member to role')):
        tables['AuditLogs'].append(dict(TimeGenerated=f'{year}-12-18T09:{n:02}:00Z',AADTenantId=TENANT,
            Type='AuditLogs',ActivityDateTime=f'{year}-12-18T09:{n:02}:00Z',Id=f'aaaaaaaa-aaaa-4aaa-8aaa-{year*10+n:012}',
            ActivityDisplayName=activity,OperationName=activity,Category='RoleManagement' if n==2 else 'UserManagement',
            Result='failure' if year==2023 and n==1 else 'success',
            InitiatedBy={'user':{'id':USERS[0],'userPrincipalName':'demo.admin@sillywalks.example.invalid'}},
            TargetResources=[{'id':USERS[n],'type':'User','userPrincipalName':f'demo.user{n+1}@sillywalks.example.invalid',
                              'modifiedProperties':[{'displayName':'Role.DisplayName','oldValue':'null','newValue':'"Global Reader"'}] if n==2 else []}]))
    tables['AZFWNetworkRule'].append(dict(TimeGenerated=f'{year}-12-20T10:00:00Z',TenantId=WORKSPACE,
        Type='AZFWNetworkRule',_ResourceId=FIREWALL,Action='Allow' if year==2023 else 'Deny',Protocol='TCP',
        SourceIp='192.0.2.10',SourcePort=51000,DestinationIp='198.51.100.40',DestinationPort=3389,
        Policy='demo-network-policy',RuleCollectionGroup='demo-boundary',RuleCollection='demo-segmentation',Rule='demo-admin-boundary'))
    incident=f'bbbbbbbb-bbbb-4bbb-8bbb-{year:012}'
    tables['SecurityIncident'].append(dict(TimeGenerated=f'{year}-12-23T18:00:00Z',TenantId=WORKSPACE,Type='SecurityIncident',
        IncidentName=incident,IncidentNumber=year,Title='Fictional endpoint alert investigation',Status='Active',Severity='Medium',
        CreatedTime=f'{year}-12-23T08:00:00Z',FirstModifiedTime=f'{year}-12-23T{14 if year==2023 else 9:02}:00:00Z',
        LastModifiedTime=f'{year}-12-23T18:00:00Z',Owner={'assignedTo':'Demo analyst'},ProviderName='Microsoft Sentinel'))
    for n,operation in enumerate(('Backup','Restore')):
        tables['AddonAzureBackupJobs'].append(dict(TimeGenerated=f'{year}-12-27T18:00:00Z',Type='AddonAzureBackupJobs',
            JobUniqueId=f'cccccccc-cccc-4ccc-8ccc-{year*10+n:012}',BackupItemUniqueId=BACKUP_ITEM,
            BackupItemFriendlyName='Silly Walks records server',JobOperation=operation,JobStartDateTime=f'{year}-12-27T06:00:00Z',
            JobStatus='Failed' if year==2023 and n==0 else 'Completed',JobDurationInSecs=(21600 if year==2023 else 7200) if n else 1800,
            VaultName='fictional-vault',JobFailureCode='DemoFailure' if year==2023 and n==0 else ''))
    folder = ROOT/'examples/telemetry'/str(year); folder.mkdir(parents=True, exist_ok=True)
    manifest = dict(schema='wacc-sentinel-evidence-v1', department='Department of Silly Walks', year=year,
                    source_kind='fictional-example', start=f'{year}-12-01T00:00:00Z', end=f'{year+1}-01-01T00:00:00Z',
                    workspace_id=WORKSPACE, entra_tenant_id=TENANT,
                    scope_reference=f'Fictional December {year} sample: inventory SW-ASSET-{year}; all three devices and three users accessing the demo records app.',
                    device_ids=DEVICES, mfa_user_ids=USERS, mfa_app_ids=[APP], authentication_details_final=True,
                    identity_user_ids=USERS,firewall_resource_ids=[FIREWALL],incident_names=[incident],backup_item_ids=[BACKUP_ITEM],
                    patch_deadlines=[dict(device_id=DEVICES[0],cve_id='CVE-2099-99999',software_name='demo_records_client',
                                         due=f'{year}-12-{30 if year==2025 else 20}T00:00:00Z',reference=f'Fictional patch schedule SW-PATCH-{year}')],
                    restore_targets=[dict(backup_item_id=BACKUP_ITEM,max_duration_hours=4,reference=f'Fictional recovery plan SW-DR-{year}: restore job target four hours')],
                    sensor_freshness_days=7, expected_rows={t:len(rows) for t,rows in tables.items()},
                    expected_block_tests=[dict(device_id=DEVICES[1], sha1=TEST_HASH, start=f'{year}-12-15T09:59:00Z',
                                               end=f'{year}-12-15T10:02:00Z', reference=f'Fictional approved test SW-AC-{year}-01: demo executable must be blocked')], files=[])
    for table, rows in tables.items():
        format_ = 'csv' if table=='SigninLogs' and year==2025 else 'jsonl'
        if format_ == 'csv':
            output=io.StringIO(newline=''); writer=csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator='\n'); writer.writeheader(); writer.writerows(rows)
            data=output.getvalue().encode()
        else:
            data=('\n'.join(json.dumps(r) for r in rows)+'\n').encode()
        name=table+'.'+format_; (folder/name).write_bytes(data)
        manifest['files'].append(dict(name=name, table=table, format=format_, sha256=hashlib.sha256(data).hexdigest()))
        if table in ('AuditLogs','AddonAzureBackupJobs'): manifest['files'][-1]['workspace_id']=WORKSPACE
    (folder/'manifest.json').write_bytes((json.dumps(manifest, indent=2)+'\n').encode())


if __name__ == '__main__':
    for year in (2023, 2024, 2025): build(year)
    print('Created fictional Sentinel logs for 2023, 2024 and 2025.')
