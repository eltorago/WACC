"""Exercise the real workbooks, untrusted uploads, persistence and HTTP workflow."""
import copy
import io
import json
from pathlib import Path
import re
import shutil
import sys
import threading
import unittest
from unittest.mock import patch
import uuid
import zipfile
from xml.etree import ElementTree as ET
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wacc import department_assessments as a
from wacc.department_workspace import render
from wacc import packaging


def workbook(year=2025):
    return (a.ROOT/'examples/assessments'/f'department-of-silly-walks-{year}.xlsx').read_bytes()


def mutate(payload, sheet='sheet2.xml', updates=None, transform=None):
    output=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(payload)) as original, zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as changed:
        for member in original.infolist():
            data=original.read(member.filename)
            if member.filename=='xl/worksheets/'+sheet:
                root=ET.fromstring(data)
                for address,value in (updates or {}).items():
                    cell=next(c for c in root.iter(a.NS+'c') if c.get('r')==address)
                    for child in list(cell): cell.remove(child)
                    cell.set('t','inlineStr')
                    ET.SubElement(ET.SubElement(cell,a.NS+'is'),a.NS+'t').text=value
                if transform: transform(root)
                data=ET.tostring(root)
            changed.writestr(member.filename,data)
    return output.getvalue()


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=a.ROOT/('.wacc-assessment-test-'+uuid.uuid4().hex)
        self.store=a.Store(self.temp)

    def tearDown(self):
        if self.temp.exists(): shutil.rmtree(self.temp)

    def test_real_examples_and_formula_caches(self):
        records=[a.parse_workbook(workbook(y)) for y in (2023,2024,2025)]
        self.assertEqual([a.scores(r)['score'] for r in records],[1.0,2.44,3.7])
        for year,record in zip((2023,2024,2025),records):
            self.assertEqual(len(record['rows']),86)
            self.assertEqual(record['date'],f'{year}-12-31')
            self.assertEqual(record['retrospective'],'Yes' if year==2023 else 'No')
            cells=a._read_sheets(workbook(year))['Overview']
            self.assertAlmostEqual(float(cells['E12'][0]),a.scores(record)['score'],places=2)
        for area in a.POLICY['areas']:
            values=[a.scores(r,area)['score'] for r in records]
            self.assertLess(values[0],values[1]); self.assertLess(values[1],values[2])

    def test_policy_coverage(self):
        self.assertEqual(len(a.REQUIREMENTS),86)
        path=a.ROOT/'data/corpus/wa-csp.json'
        if path.exists():
            source=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(set(a.REQUIREMENTS),{r['identifier'] for r in source['records']})

    def test_blank_template_can_be_completed(self):
        payload=(a.ROOT/'examples/assessments/wa-csp-2024-template.xlsx').read_bytes()
        with self.assertRaisesRegex(a.AssessmentError,'department name'): a.parse_workbook(payload)
        payload=mutate(payload,'sheet1.xml',{'B5':'Test agency','B7':'2026-12-31','B8':'Assessor','B9':'All services'})
        record=a.parse_workbook(payload)
        self.assertIsNone(a.scores(record)['score']); self.assertEqual(a.scores(record)['missing'],86)

    def test_missing_and_excluded_do_not_inflate_scores(self):
        partial=a.parse_workbook(mutate(workbook(),updates={'D7':'Not assessed'}))
        self.assertIsNone(a.scores(partial)['score'])
        self.assertEqual(a.scores(partial)['missing'],1)
        with self.assertRaisesRegex(a.AssessmentError,'exclusion'):
            a.parse_workbook(mutate(workbook(),updates={'D7':'N/A'}))
        record=a.parse_workbook(mutate(workbook(),updates={'D7':'N/A','I7':'Approved exclusion'}))
        self.assertEqual(a.scores(record)['excluded'],1)
        other=a.parse_workbook(workbook(2024))
        self.assertEqual(len(a.comparable_ids([record,other])),85)
        self.assertNotIn('1.1a',a.comparable_ids([record,other]))

    def test_zero_is_a_valid_rating(self):
        record=a.parse_workbook(mutate(workbook(),updates={'D7':'0'}))
        self.assertEqual(a.scores(record)['rated'],86)

    def test_input_validation(self):
        cases=[({'D7':'5'},'choose'),({'D7':'2.5'},'choose'),({'A7':'fake'},'unknown'),
               ({'A8':'1.1a'},'duplicate'),({'E7':''},'evidence'),({'H7':'tomorrow'},'date'),
               ({'C7':'Changed assessment'},'prompt changed')]
        for updates,expected in cases:
            with self.subTest(updates=updates),self.assertRaisesRegex(a.AssessmentError,expected):
                a.parse_workbook(mutate(workbook(),updates=updates))

    def test_metadata_validation(self):
        cases=[({'B6':'2025.5'},'whole year'),({'B7':'2024-12-31'},'within'),
               ({'B10':'2025 policy'},'version 1'),({'B11':'v2'},'version 1'),({'B8':''},'assessor')]
        for updates,expected in cases:
            with self.subTest(updates=updates),self.assertRaisesRegex(a.AssessmentError,expected):
                a.parse_workbook(mutate(workbook(),'sheet1.xml',updates))
        with self.assertRaisesRegex(a.AssessmentError,'Retrospective'):
            a.parse_workbook(mutate(workbook(2023),'sheet1.xml',{'B12':'No'}))

    def test_missing_row_rejected(self):
        def remove(root):
            data=root.find(a.NS+'sheetData')
            data.remove(next(r for r in data if r.get('r')=='7'))
        with self.assertRaisesRegex(a.AssessmentError,'Missing 1'):
            a.parse_workbook(mutate(workbook(),transform=remove))

    def test_air_approval_and_reference(self):
        record=a.parse_workbook(workbook())
        self.assertEqual(record['reporting']['air_status'],'Submitted')
        for cell,expected in [('B33','accountable authority'),('B34','approval date'),('B36','AIR reference')]:
            with self.subTest(cell=cell),self.assertRaisesRegex(a.AssessmentError,expected):
                a.parse_workbook(mutate(workbook(),'sheet1.xml',{cell:''}))

    def test_department_case_normalisation(self):
        self.store.import_files([('2024.xlsx',workbook(2024))])
        self.store.import_files([('2025.xlsx',mutate(workbook(),'sheet1.xml',{'B5':' DEPARTMENT OF SILLY WALKS '}))])
        self.assertEqual({r['department'] for r in self.store.all()},{'Department of Silly Walks'})

    def test_trend_uses_selected_year_for_change(self):
        self.store.import_files([(f'{y}.xlsx',workbook(y)) for y in (2023,2024,2025)])
        page=render(self.store,'token',{'year':['2023']})
        self.assertIn('<strong>+0.00</strong>',page)
        self.assertIn('Change since 2023',page)

    def test_no_applicable_requirements_is_not_zero(self):
        record=a.parse_workbook(workbook())
        for row in record['rows']: row['rating']='N/A'
        self.assertIsNone(a.scores(record)['score'])
        self.assertEqual(a.scores(record)['excluded'],86)

    def test_formulas_in_inputs_rejected_and_summary_cache_ignored(self):
        def formula(root):
            cell=next(c for c in root.iter(a.NS+'c') if c.get('r')=='D7')
            ET.SubElement(cell,a.NS+'f').text='4'
        with self.assertRaisesRegex(a.AssessmentError,'instead of a formula'):
            a.parse_workbook(mutate(workbook(),transform=formula))
        record=a.parse_workbook(mutate(workbook(),'sheet1.xml',{'E12':'0'}))
        self.assertEqual(a.scores(record)['score'],3.7)

    def test_malformed_and_oversize_workbooks(self):
        for data in (b'',b'bad zip',b'x'*(a.MAX_UPLOAD+1)):
            with self.assertRaises(a.AssessmentError):a.parse_workbook(data)
        with self.assertRaisesRegex(a.AssessmentError,'Only .xlsx'):a.parse_workbook(workbook(),'macro.xlsm')
        def huge_cell(root):
            next(root.iter(a.NS+'c')).set('r','XFD999999')
        with self.assertRaises(a.AssessmentError):a.parse_workbook(mutate(workbook(),transform=huge_cell))
        for name,data in [('xl/vbaProject.bin',b'macro'),('../escape',b'escape'),('xl/oversize.xml',b'x'*(9*1024*1024))]:
            stream=io.BytesIO(workbook())
            with zipfile.ZipFile(stream,'a',zipfile.ZIP_DEFLATED) as archive:archive.writestr(name,data)
            with self.assertRaises(a.AssessmentError):a.parse_workbook(stream.getvalue())
        with self.assertRaises(a.AssessmentError):a._xml(b'<!DOCTYPE x [<!ENTITY y "x">]><x>&y;</x>')

    def test_import_is_atomic_and_survives_restart(self):
        files=[(n,(a.ROOT/'examples/assessments'/n).read_bytes()) for n in a.EXAMPLES]
        with self.assertRaises(a.AssessmentError): self.store.import_files(files+[('bad.xlsx',b'bad')])
        self.assertEqual(self.store.all(),[])
        self.store.import_files(files)
        self.assertEqual(len(a.Store(self.temp).all()),3)
        self.store.import_files(files)
        self.assertEqual(len(self.store.all()),3)
        revised=mutate(workbook(),updates={'D7':'2'})
        with self.assertRaisesRegex(a.AssessmentError,'already exists'):
            self.store.import_files([('revised.xlsx',revised)])
        self.store.import_files([('revised.xlsx',revised)],replace=True)
        self.assertEqual(len(self.store.all()),3)
        self.assertEqual(next(r for r in self.store.all() if r['year']==2025)['rows'][0]['rating'],'2')

    def test_duplicate_years_in_one_batch_rejected(self):
        with self.assertRaisesRegex(a.AssessmentError,'one workbook'):
            self.store.import_files([('one.xlsx',workbook()),('two.xlsx',workbook())])

    def test_ui_escaping_chart_filters_and_links(self):
        payload=mutate(workbook(),'sheet1.xml',{'B5':'<script>alert(1)</script>'})
        self.store.import_files([('test.xlsx',payload)])
        page=render(self.store,'token',{'area':['Recover']})
        self.assertNotIn('<script>alert(1)</script>',page)
        self.assertIn('&lt;script&gt;alert(1)',page)
        self.assertIn('<svg',page); self.assertIn('2025: 3.70',page)
        self.assertIn('6.1',page); self.assertNotIn('DSW-2025-1.1a',page)

    def test_private_storage_and_authored_workbook_packaging(self):
        shipped=packaging.would_ship(str(a.ROOT))
        self.assertTrue(packaging.AUTHORED_WORKBOOKS.issubset(set(shipped)))
        self.assertFalse(any(p.startswith(str(Path('data/local'))) for p in shipped))
        self.assertIn('/data/local/',packaging.gitignore())
        self.assertEqual(packaging.check(str(a.ROOT)),[])

    def test_workbook_dropdowns_filters_and_freeze_panes(self):
        with zipfile.ZipFile(io.BytesIO(workbook())) as archive:
            sheet=ET.fromstring(archive.read('xl/worksheets/sheet2.xml'))
            self.assertTrue(list(sheet.iter(a.NS+'dataValidation')))
            self.assertTrue(list(sheet.iter(a.NS+'tablePart')))
            pane=next(sheet.iter(a.NS+'pane'))
            self.assertEqual(pane.get('ySplit'),'6');self.assertEqual(pane.get('xSplit'),'2')


class AssessmentHTTPTests(unittest.TestCase):
    def setUp(self):
        from wacc.serve import _handler
        self.temp=a.ROOT/('.wacc-assessment-http-test-'+uuid.uuid4().hex)
        with patch.dict('os.environ',{'WACC_ASSESSMENTS':str(self.temp)}):
            handler=_handler(None)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.port=self.server.server_address[1]
        status,body=self.request('GET','/assessments')
        self.assertEqual(status,200)
        self.token=re.search(r'name="token" value="([^"]+)"',body.decode())[1]

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        if self.temp.exists():shutil.rmtree(self.temp)

    def request(self,method,path,body=None,headers=None):
        conn=HTTPConnection('127.0.0.1',self.port,timeout=10)
        try:
            conn.request(method,path,body,headers or {});response=conn.getresponse()
            return response.status,response.read()
        finally:conn.close()

    def upload(self,token,files):
        parts=[f'--test\r\nContent-Disposition: form-data; name="token"\r\n\r\n{token}\r\n'.encode()]
        for name,data in files:
            parts.extend([f'--test\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n'.encode(),data,b'\r\n'])
        parts.append(b'--test--\r\n')
        return self.request('POST','/assessments/import',b''.join(parts),{'Content-Type':'multipart/form-data; boundary=test'})

    def test_upload_download_and_examples(self):
        code,body=self.upload(self.token,[('2023.xlsx',workbook(2023)),('2024.xlsx',workbook(2024)),('2025.xlsx',workbook())])
        self.assertEqual(code,200,body)
        code,page=self.request('GET',json.loads(body)['location'])
        for text in (b'1.00',b'2.44',b'3.70',b'<svg',b'DSW-2025-'):
            self.assertIn(text,page)
        code,body=self.request('GET','/assessments/download/department-of-silly-walks-2025.xlsx')
        self.assertEqual(code,200);self.assertEqual(body,workbook())
        self.assertEqual(self.request('GET','/assessments/download/records.json')[0],404)
        self.assertEqual(self.request('POST','/assessments/examples','token='+self.token,{'Content-Type':'application/x-www-form-urlencoded'})[0],303)

    def test_token_origin_and_invalid_upload(self):
        self.assertEqual(self.upload('wrong',[('2025.xlsx',workbook())])[0],400)
        self.assertEqual(self.upload(self.token,[('bad.xlsx',b'bad')])[0],400)
        self.assertEqual(self.request('POST','/assessments/examples','token='+self.token,{'Origin':'https://foreign.example'})[0],400)
        self.assertEqual(a.Store(self.temp).all(),[])


if __name__=='__main__':unittest.main()
