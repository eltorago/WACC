"""Evidence semantics, hostile inputs, Azure reads and the full HTTP workflow."""
import copy
import io
import json
from pathlib import Path
import re
import shutil
import sys
import threading
import unittest
import uuid
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wacc import telemetry as t
from wacc import telemetry_azure as azure
from wacc import department_assessments as a
from wacc.telemetry_workspace import render, assessment_panel


def assessment(year=2025):
    return a.parse_workbook((a.ROOT/'examples/assessments'/f'department-of-silly-walks-{year}.xlsx').read_bytes())


def changed(table=None, transform=None, manifest_change=None, year=2025):
    files = dict(t.example_files(year)); m = json.loads(files['manifest.json'])
    if table:
        descriptor = next(f for f in m['files'] if f['table'] == table)
        rows = [r for _, r in t._rows(files.pop(descriptor['name']), descriptor['format'])]
        rows = transform(rows)
        descriptor.update(name=table+'.jsonl', format='jsonl'); descriptor.pop('sha256', None)
        files[descriptor['name']] = '\n'.join(json.dumps(r) for r in rows).encode()
    if manifest_change: manifest_change(m)
    files['manifest.json'] = json.dumps(m).encode()
    return list(files.items())


def finding(files, id_):
    m, events, quality, _, _ = t.parse(files, assessment())
    return next(f for f in t.evaluate(assessment(), m, events, quality) if f['id'] == id_)


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = a.ROOT/('.wacc-telemetry-test-'+uuid.uuid4().hex)
        self.store = a.Store(self.temp)
        self.store.import_files([(f'{y}.xlsx',(a.ROOT/'examples/assessments'/f'department-of-silly-walks-{y}.xlsx').read_bytes()) for y in (2023,2024,2025)])
        self.validation = t.ValidationStore(self.store)

    def tearDown(self):
        if self.temp.exists(): shutil.rmtree(self.temp)

    def test_three_native_examples_and_csv(self):
        from wacc.packaging import would_ship, gitignore
        shipping = {p.replace('\\', '/') for p in would_ship(str(a.ROOT))}
        for year in (2023,2024,2025):
            self.assertIn(f'examples/telemetry/{year}/manifest.json', shipping)
            self.assertIn(f'!/examples/telemetry/{year}/manifest.json', gitignore())
            for name, data in t.example_files(year):
                self.assertNotIn(b'\r', data, f'{year}/{name}: keep LF bytes so Git checkout preserves hashes')
            m, events, q, _, _ = t.parse(t.example_files(year), assessment(year))
            self.assertEqual(q['count_mismatches'], [])
            self.assertEqual(q['unreconciled_tables'], [])
            self.assertEqual(q['outside_scope'], 0)
            findings = t.evaluate(assessment(year), m, events, q)
            self.assertEqual(len(findings), 14)
            self.assertEqual(findings[0]['status'], 'Potential overstatement' if year==2025 else 'Gap observed')
            self.assertTrue(all(f['sources'][0].startswith('https://learn.microsoft.com/') for f in findings))

    def test_2025_expected_story(self):
        m, e, q, _, _ = t.parse(t.example_files(), assessment())
        f = {f['id']: f for f in t.evaluate(assessment(),m,e,q)}
        self.assertEqual({k for k,v in f.items() if v['status']=='Potential overstatement'}, {'TV-AC','TV-MFA'})
        self.assertEqual(sum(v['status']=='Supports observed operation' for v in f.values()),9)
        self.assertIn('MFA or a strong/reused claim: 2', f['TV-MFA']['summary'])
        self.assertIn('Failed/non-interactive sign-ins excluded: 1', f['TV-MFA']['summary'])

    def test_audit_only_is_not_proof_of_bypass(self):
        files = changed(manifest_change=lambda m:m.update(expected_block_tests=[]))
        self.assertEqual(finding(files, 'TV-AC')['status'],'Needs review')

    def test_no_application_events_is_not_a_pass(self):
        files = changed('DeviceEvents', lambda rows:[r for r in rows if not r['ActionType'].startswith('AppControl')], lambda m:m.update(expected_block_tests=[]))
        self.assertEqual(finding(files, 'TV-AC')['status'],'No evidence')

    def test_negative_test_must_match_hash_device_and_time(self):
        for key, value in [('sha1','f'*40),('device_id','3'*40),('start','2025-12-16T09:59:00Z')]:
            def edit(m):
                m['expected_block_tests'][0][key]=value
                if key=='start': m['expected_block_tests'][0]['end']='2025-12-16T10:02:00Z'
            self.assertNotEqual(finding(changed(manifest_change=edit),'TV-AC')['status'],'Potential overstatement')

    def test_passwordless_and_reused_mfa_claims(self):
        base = dict(ResultType='0', IsInteractive=True, ConditionalAccessStatus='notApplied',AuthenticationRequirement='singleFactorAuthentication')
        for method, detail in [('FIDO2 security key',''),('Windows Hello for Business',''),('Previously satisfied','MFA requirement satisfied by claim in the token')]:
            row = dict(base, AuthenticationDetails=[dict(succeeded=True,authenticationMethod=method,authenticationStepResultDetail=detail)])
            self.assertEqual(t.mfa_result(row,True),'support')
            self.assertEqual(t.mfa_result(row,False),'review')

    def test_failed_and_noninteractive_signins_are_not_mfa_gaps(self):
        row=dict(ResultType='500121',IsInteractive=True)
        self.assertEqual(t.mfa_result(row,True),'ignore')
        self.assertEqual(t.mfa_result(dict(row,ResultType='0',IsInteractive=False),True),'ignore')

    def test_mfa_requirement_or_empty_details_does_not_prove_mfa(self):
        for detail in ('[]','invalid',None,'[null]'):
            self.assertEqual(t.mfa_result(dict(ResultType='0',IsInteractive=True,AuthenticationRequirement='multiFactorAuthentication',AuthenticationDetails=detail),True),'review')

    def test_unfinalised_mfa_details_cannot_flag_overstatement(self):
        f=finding(changed(manifest_change=lambda m:m.update(authentication_details_final=False)),'TV-MFA')
        self.assertEqual(f['status'],'Needs review')

    def test_conflicting_signin_versions_need_review(self):
        def alter(rows):
            original=copy.deepcopy(rows[0]); original['AuthenticationDetails']='[]'; rows.append(original); return rows
        files=changed('SigninLogs',alter)
        _,events,q,_,_=t.parse(files,assessment())
        self.assertEqual(q['conflicting_events'],1)
        self.assertEqual(sum(e.get('conflicted',False) for e in events),2)

    def test_old_sensor_record_does_not_prove_current_coverage(self):
        def old(rows):
            for r in rows:r['TimeGenerated']='2025-12-01T00:00:00Z'
            return rows
        self.assertEqual(finding(changed('DeviceInfo',old),'TV-EDR')['status'],'Needs review')

    def test_missing_sensor_fields_are_unknown(self):
        def alter(rows):
            for r in rows:r.pop('SensorHealthState')
            return rows
        self.assertEqual(finding(changed('DeviceInfo',alter),'TV-EDR')['status'],'Needs review')

    def test_unknown_or_conflicting_recent_sensor_state_does_not_pass(self):
        def unknown(rows):
            rows[0]['SensorHealthState']='Unknown';return rows
        self.assertEqual(finding(changed('DeviceInfo',unknown),'TV-EDR')['status'],'Needs review')
        def conflict(rows):
            rows.append(dict(rows[0],SensorHealthState='Inactive'))
            rows.append(dict(rows[0],TimeGenerated='2025-12-28T00:00:00Z'))
            return rows
        self.assertEqual(finding(changed('DeviceInfo',conflict),'TV-EDR')['status'],'Needs review')

    def test_missing_antivirus_remediation_needs_followup(self):
        def alter(rows):
            for r in rows:
                if r['ActionType']=='AntivirusDetection':r['AdditionalFields']='{}'
            return rows
        self.assertEqual(finding(changed('DeviceEvents',alter),'TV-AV')['status'],'Needs review')

    def test_duplicates_deduplicate_by_full_record_not_report_counter(self):
        files=changed('DeviceInfo',lambda rows:rows+[copy.deepcopy(rows[0])])
        _,events,q,_,_=t.parse(files,assessment())
        self.assertEqual(q['duplicates'],1)
        self.assertEqual(sum(e['table']=='DeviceInfo' for e in events),3)
        self.assertIn('DeviceInfo',q['count_mismatches'])

    def test_outside_time_and_scope_cannot_support_assessment(self):
        def alter(rows):
            rows[0]['TimeGenerated']='2024-12-29T12:00:00Z';rows[1]['DeviceId']='f'*40;return rows
        _,events,q,_,_=t.parse(changed('DeviceInfo',alter),assessment())
        self.assertEqual(q['outside_window'],1);self.assertEqual(q['outside_scope'],1)
        self.assertEqual(sum(e['table']=='DeviceInfo' for e in events),1)

    def test_wrong_workspace_or_entra_tenant_rejected(self):
        for table,key in [('DeviceInfo','TenantId'),('SigninLogs','AADTenantId')]:
            def alter(rows):rows[0][key]='00000000-0000-4000-8000-000000000000';return rows
            with self.assertRaises(a.AssessmentError):t.parse(changed(table,alter),assessment())

    def test_missing_expected_table_is_not_silently_ignored(self):
        files=[(n,b) for n,b in t.example_files() if n!='DeviceEvents.jsonl']
        with self.assertRaisesRegex(a.AssessmentError,'match the manifest'):t.parse(files,assessment())

    def test_manifest_rejects_bad_scope_window_and_year(self):
        for change in [dict(year=2024),dict(start='2025-01-01'),dict(end='2027-01-01T00:00:00Z'),dict(device_ids='all'),dict(expected_rows=[]),dict(sensor_freshness_days=0),dict(department={})]:
            with self.subTest(change=change),self.assertRaises(a.AssessmentError):
                t.parse(changed(manifest_change=lambda m:m.update(change)),assessment())

    def test_hostile_bundle_and_rows_are_bounded(self):
        cases=[('x.json',b'[]'),('x.json',b'{"a":1,"a":2}'),('manifest.json',b'{"schema":NaN}'),('../manifest.json',b'{}'),('NUL.json',b'{}')]
        for case in cases:
            with self.subTest(case=case),self.assertRaises(a.AssessmentError):t.parse([case],assessment())
        with patch.object(t,'MAX_ROWS',1),self.assertRaisesRegex(a.AssessmentError,'50,000'):t.parse(t.example_files(),assessment())
        with patch.object(t,'MAX_BYTES',5),self.assertRaises(a.AssessmentError):t.parse(t.example_files(),assessment())

    def test_bad_row_types_and_hash_fail_without_partial_import(self):
        files=dict(t.example_files()); files['DeviceInfo.jsonl']+=b'\n{}'
        with self.assertRaisesRegex(a.AssessmentError,'SHA-256'):self.validation.import_files(list(files.items()),assessment()['key'])
        self.assertEqual(self.validation.all(),[])
        with self.assertRaises(a.AssessmentError):t.parse(changed('DeviceInfo',lambda rows:[dict(rows[0],ReportId={})]),assessment())

    def test_bundle_provenance_and_review_history(self):
        before=self.store.all()
        report=self.validation.import_files([('example.json',t.example_bundle())],assessment()['key'])
        self.validation.review(report['id'],'TV-MFA','More evidence needed','Reviewer One','Review Conditional Access exception CHG-42.')
        saved=self.validation.review(report['id'],'TV-MFA','Confirmed gap','Reviewer Two','Exception expired; owner assigned.')
        self.assertEqual(len(saved['findings'][1]['reviews']),2)
        self.assertEqual(before,self.store.all())
        for f in saved['files']:
            original=self.validation.path/report['id']/'originals'/f['name']
            self.assertEqual(t.digest(original.read_bytes()),f['sha256'])

    def test_changed_assessment_marks_run_stale_and_blocks_review(self):
        report=self.validation.import_files(t.example_files(),assessment()['key'])
        path=self.store.path/'records.json'; records=json.loads(path.read_text())
        next(r for r in records if r['year']==2025)['sha256']='different'
        path.write_text(json.dumps(records))
        with self.assertRaisesRegex(a.AssessmentError,'assessment changed'):
            self.validation.review(report['id'],'TV-MFA','Confirmed gap','A','B')
        page=render(self.store,'token',{'run':[report['id']]})
        self.assertIn('workbook has changed',page);self.assertNotIn('Save review',page)

    def test_ui_escapes_evidence_and_review_notes(self):
        files=changed(manifest_change=lambda m:m.update(scope_reference='<script>alert(1)</script>'))
        report=self.validation.import_files(files,assessment()['key'])
        self.validation.review(report['id'],'TV-MFA','More evidence needed','<img>','<script>bad()</script>')
        page=render(self.store,'token',{'run':[report['id']]})
        self.assertIn('&lt;script&gt;',page);self.assertNotIn('<script>alert',page);self.assertNotIn('<script>bad',page)
        self.assertIn('TV-MFA',page);self.assertIn('Export coverage and provenance',page)

    def test_annual_view_separates_ratings_and_evidence(self):
        self.validation.import_files(t.example_files(),assessment()['key'])
        page=assessment_panel(self.store,self.store.all(),assessment())
        self.assertIn('2 gaps',page);self.assertIn('9 supported',page);self.assertIn('2023',page)

    def test_every_policy_requirement_has_an_evidence_route(self):
        from wacc.telemetry_policy import policy_coverage
        report=self.validation.import_files(t.example_files(),assessment()['key'])
        coverage=policy_coverage(report)
        self.assertEqual({r['id'] for r in coverage},set(a.REQUIREMENTS))
        self.assertEqual(len([r for r in coverage if r['checks']]),12)
        self.assertIn('risk register',next(r for r in coverage if r['id']=='2.2a')['evidence'])
        self.assertFalse(next(r for r in coverage if r['id']=='3.2a')['checks'])
        self.assertIn('WA policy coverage',render(self.store,'token',{'run':[report['id']]}))

    def test_extra_native_schemas_do_not_require_invented_endpoint_columns(self):
        m,events,q,_,_=t.parse(t.example_files(),assessment())
        self.assertEqual(q['outside_scope'],0)
        for e in events:
            if e['table'] in ('AuditLogs','SecurityIncident','AddonAzureBackupJobs','AZFWNetworkRule'):
                self.assertNotIn('DeviceId',e['row']);self.assertNotIn('ReportId',e['row'])
            if e['table'] in ('AuditLogs','AddonAzureBackupJobs'):self.assertNotIn('TenantId',e['row'])

    def test_descriptor_workspace_and_new_scope_are_checked(self):
        def wrong(m):
            next(f for f in m['files'] if f['table']=='AuditLogs')['workspace_id']='wrong'
        with self.assertRaises(a.AssessmentError):t.parse(changed(manifest_change=wrong),assessment())
        files=changed(manifest_change=lambda m:m.update(identity_user_ids=[],firewall_resource_ids=[],incident_names=[],backup_item_ids=[],restore_targets=[]))
        _,events,q,_,_=t.parse(files,assessment())
        self.assertEqual(q['outside_scope'],7)
        self.assertFalse(any(e['table'] in ('AuditLogs','SecurityIncident','AddonAzureBackupJobs','AZFWNetworkRule') for e in events))

    def test_vulnerability_requires_a_specific_documented_deadline(self):
        self.assertEqual(finding(t.example_files(),'TV-PATCH')['status'],'Needs review')
        def overdue(m):m['patch_deadlines'][0]['due']='2025-12-20T00:00:00Z'
        self.assertEqual(finding(changed(manifest_change=overdue),'TV-PATCH')['status'],'Potential overstatement')
        self.assertEqual(finding(changed(manifest_change=lambda m:m.update(patch_deadlines=[])),'TV-PATCH')['status'],'Needs review')
        def no_update(rows):rows[0]['CveTags']=['NoSecurityUpdate'];return rows
        self.assertEqual(finding(changed('DeviceTvmSoftwareVulnerabilities',no_update,overdue),'TV-PATCH')['status'],'Needs review')
        self.assertEqual(finding(changed('DeviceTvmSoftwareVulnerabilities',lambda rows:[]),'TV-PATCH')['status'],'No evidence')

    def test_restore_uses_plan_target_and_latest_job_status(self):
        self.assertEqual(finding(t.example_files(),'TV-RESTORE')['status'],'Supports observed operation')
        self.assertEqual(finding(changed(manifest_change=lambda m:m.update(restore_targets=[])),'TV-RESTORE')['status'],'Needs review')
        def slow(rows):
            rows[1]['JobDurationInSecs']=18000;return rows
        self.assertEqual(finding(changed('AddonAzureBackupJobs',slow),'TV-RESTORE')['status'],'Potential overstatement')
        for invalid in (True, None, -1, 'unknown'):
            with self.subTest(duration=invalid):
                def bad_duration(rows):rows[1]['JobDurationInSecs']=invalid;return rows
                self.assertEqual(finding(changed('AddonAzureBackupJobs',bad_duration),'TV-RESTORE')['status'],'Needs review')
        def revised(rows):
            rows.append(dict(rows[1],JobStatus='InProgress',TimeGenerated='2025-12-27T07:00:00Z'));return rows
        self.assertEqual(finding(changed('AddonAzureBackupJobs',revised),'TV-RESTORE')['status'],'Supports observed operation')
        def latest_fail(rows):
            rows.append(dict(rows[1],JobStatus='Failed',TimeGenerated='2025-12-27T19:00:00Z'));return rows
        self.assertEqual(finding(changed('AddonAzureBackupJobs',latest_fail),'TV-RESTORE')['status'],'Needs review')

    def test_incident_status_does_not_prove_human_triage(self):
        def quick(rows):
            rows[0]['FirstModifiedTime']='2025-12-23T08:01:00Z';rows[0]['ModifiedBy']='Automation';return rows
        self.assertEqual(finding(changed('SecurityIncident',quick),'TV-TRIAGE')['status'],'Needs review')
        def delayed(rows):rows[0]['FirstModifiedTime']='2025-12-23T20:00:00Z';return rows
        result=finding(changed('SecurityIncident',delayed),'TV-TRIAGE')
        self.assertEqual(result['status'],'Needs review');self.assertIn('after four hours: 1',result['summary'])

    def test_failed_identity_changes_and_role_assignments_need_review(self):
        def failed(rows):rows[0]['Result']='failure';return rows
        self.assertEqual(finding(changed('AuditLogs',failed),'TV-IAM')['status'],'Needs review')
        def invalid(rows):rows[0]['Result']=123;return rows
        self.assertEqual(finding(changed('AuditLogs',invalid),'TV-IAM')['status'],'Needs review')
        self.assertEqual(finding(t.example_files(),'TV-PRIV')['status'],'Needs review')

    def test_firewall_allow_is_not_automatically_a_policy_breach(self):
        def allowed(rows):rows[0]['Action']='Allow';return rows
        self.assertEqual(finding(changed('AZFWNetworkRule',allowed),'TV-NET')['status'],'Needs review')
        def invalid(rows):rows[0]['Action']=123;return rows
        self.assertEqual(finding(changed('AZFWNetworkRule',invalid),'TV-NET')['status'],'Needs review')

    def test_old_six_table_exports_still_import(self):
        original=dict(t.example_files());m=json.loads(original['manifest.json'])
        m['files']=[f for f in m['files'] if f['table'] in t.CORE_TABLES]
        m['expected_rows']={k:v for k,v in m['expected_rows'].items() if k in t.CORE_TABLES}
        files=[('manifest.json',json.dumps(m).encode())]+[(f['name'],original[f['name']]) for f in m['files']]
        report=self.validation.import_files(files,assessment()['key'])
        self.assertEqual(report['quality']['unreconciled_tables'],[])
        self.assertEqual(next(f for f in report['findings'] if f['id']=='TV-RESTORE')['status'],'No evidence')

    def test_adls_only_accepts_public_azure_paths(self):
        good=azure.storage_url('waccdemo123','am-deviceevents','WorkspaceResourceId=/subscriptions/demo/y=2025/PT05M.json')
        self.assertTrue(good.startswith('https://waccdemo123.dfs.core.windows.net/'))
        for account,container,path in [('evil.example','logs','x'),('waccdemo123','logs','../secret'),('waccdemo123','logs','/x'),('waccdemo123','logs','a\\b')]:
            with self.assertRaises(a.AssessmentError):azure.storage_url(account,container,path)

    def test_adls_read_only_requests_and_no_token_saved(self):
        original=dict(t.example_files()); manifest=json.loads(original['manifest.json'])
        manifest.update(source_kind='adls-gen2',azure={'account':'waccdemo123'})
        for f in manifest['files']:f.update(filesystem='sentinel-exports',adls_path=f['name'])
        class Response(io.BytesIO):
            status=200;headers={'ETag':'test-etag','Last-Modified':'Wed, 16 Sep 2026 01:00:00 GMT'}
        requests=[]
        def opened(req,timeout):
            requests.append(req);return Response(original[req.full_url.rsplit('/',1)[-1]])
        with patch.object(azure.shutil,'which',return_value='az'),patch.object(azure.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='secret-token',stderr='')) as cli,patch.object(azure,'build_opener',return_value=SimpleNamespace(open=opened)):
            files=azure.fetch_files(manifest,assessment())
        report=self.validation.import_files(files,assessment()['key'])
        self.assertNotIn('secret-token',json.dumps(report))
        self.assertTrue(all(r.get_method()=='GET' for r in requests))
        self.assertIn('https://storage.azure.com/',cli.call_args.args[0])
        self.assertEqual(report['manifest']['files'][0]['download']['etag'],'test-etag')

    def test_adls_redirect_and_cli_errors_hide_secrets(self):
        with self.assertRaises(a.AssessmentError):azure.NoRedirect().redirect_request(None,None,302,'',{},'https://evil.example')
        manifest=json.loads(dict(t.example_files())['manifest.json']);manifest.update(source_kind='adls-gen2',azure={'account':'waccdemo123'})
        for f in manifest['files']:f.update(filesystem='sentinel-exports',adls_path=f['name'])
        with patch.object(azure.shutil,'which',return_value='az'),patch.object(azure.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='secret',stderr='secret')):
            with self.assertRaises(a.AssessmentError) as raised:azure.fetch_files(manifest,assessment())
        self.assertNotIn('secret',str(raised.exception))


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=a.ROOT/('.wacc-telemetry-http-'+uuid.uuid4().hex)
        self.store=a.Store(self.temp)
        self.record=self.store.import_files([('2025.xlsx',(a.ROOT/'examples/assessments/department-of-silly-walks-2025.xlsx').read_bytes())])[0]
        from wacc.serve import _handler
        with patch.dict('os.environ',{'WACC_ASSESSMENTS':str(self.temp)}):self.server=ThreadingHTTPServer(('127.0.0.1',0),_handler(None))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        _,body=self.request('GET','/assessments/validation')
        self.token=re.search(r'name="token" value="([^"]+)"',body.decode())[1]

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        if self.temp.exists():shutil.rmtree(self.temp)

    def request(self,method,path,body=None,headers=None):
        conn=HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        try:
            conn.request(method,path,body,headers or {});response=conn.getresponse();return response.status,response.read()
        finally:conn.close()

    def post(self,path,fields,files=None,origin=None):
        boundary='wacc-test-boundary';parts=[]
        for key,value in fields.items():parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        for name,data in files or []:parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+data+b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode());headers={'Content-Type':'multipart/form-data; boundary='+boundary}
        if origin:headers['Origin']=origin
        return self.request('POST',path,b''.join(parts),headers)

    def test_demo_review_download_flow(self):
        status,body=self.post('/assessments/validation/demo',{'token':self.token,'assessment':self.record['key']})
        self.assertEqual(status,200);url=json.loads(body)['location'];run=url.split('run=')[1]
        status,page=self.request('GET',url);self.assertEqual(status,200);self.assertIn(b'Potential overstatement',page)
        status,_=self.post('/assessments/validation/review',dict(token=self.token,run=run,finding='TV-AC',decision='Confirmed gap',reviewer='Test Reviewer',note='Test approval confirmed.'))
        self.assertEqual(status,200)
        status,body=self.request('GET','/assessments/validation/report?run='+run)
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['findings'][0]['reviews'][0]['decision'],'Confirmed gap')
        self.assertEqual(self.request('GET','/assessments/validation/example?year=2025')[0],200)
        self.assertEqual(self.request('GET','/assessments/validation/queries')[0],200)

    def test_real_multipart_upload_and_csrf(self):
        for token,origin in [('bad',None),(self.token,'https://evil.example')]:
            status,_=self.post('/assessments/validation/import',{'token':token,'assessment':self.record['key']},t.example_files(),origin)
            self.assertEqual(status,400)
        status,body=self.post('/assessments/validation/import',{'token':self.token,'assessment':self.record['key']},t.example_files())
        self.assertEqual(status,200,body)

    def test_unknown_runs_and_missing_files(self):
        self.assertEqual(self.request('GET','/assessments/validation?run=../bad')[0],400)
        self.assertEqual(self.request('GET','/assessments/validation/report?run=missing')[0],404)
        status,_=self.post('/assessments/validation/import',{'token':self.token,'assessment':self.record['key']},[('x.json',b'{}')])
        self.assertEqual(status,400)


if __name__=='__main__':unittest.main(verbosity=2)
