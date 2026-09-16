"""Validate XLSX self-assessments and keep imported records in local storage."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import threading
import unicodedata
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT/'data/department-assessment-policy.json').read_text(encoding='utf-8'))
REQUIREMENTS = {r['id']: r for r in POLICY['requirements']}
RATINGS = {'0': 'Not started', '1': 'Planned', '2': 'Partly implemented',
           '3': 'Implemented', '4': 'Tested and reviewed',
           'Not assessed': 'Not assessed', 'N/A': 'Not applicable'}
HEADERS = ['Requirement ID','Area','Assessment prompt','Rating','Evidence','Owner',
           'Next action','Due date','Exclusion reason','Score','Policy reference']
EXAMPLES = [f'department-of-silly-walks-{year}.xlsx' for year in (2023,2024,2025)]
DOWNLOADS = EXAMPLES + ['wa-csp-2024-template.xlsx']
MAX_UPLOAD = 5 * 1024 * 1024
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


class AssessmentError(ValueError):
    """A workbook or import cannot be used; safe to show the reason to the user."""


def _xml(data):
    declarations=data.replace(b'\x00',b'').upper()
    if b'<!DOCTYPE' in declarations or b'<!ENTITY' in declarations:
        raise AssessmentError('XML declarations are not supported in assessment files.')
    return ET.fromstring(data)


def _read_sheets(payload):
    """Small bounded reader. Never extract ZIP members or evaluate formulas/links."""
    if not payload or len(payload)>MAX_UPLOAD:
        raise AssessmentError('Choose an XLSX file smaller than 5 MB.')
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            items = archive.infolist()
            names = [i.filename for i in items]
            if len(items)>200 or len(names)!=len(set(names)) or sum(i.file_size for i in items)>20*1024*1024:
                raise AssessmentError('Workbook is too large or contains duplicate parts.')
            for item in items:
                name=item.filename
                if (item.file_size>8*1024*1024 or item.flag_bits&1 or
                    item.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED) or
                    name.startswith('/') or '..' in name.split('/') or '\\' in name or
                    'vbaproject' in name.lower() or 'externallink' in name.lower()):
                    raise AssessmentError('Use an unencrypted XLSX without macros or external workbook links.')
            shared=[]
            if 'xl/sharedStrings.xml' in names:
                root=_xml(archive.read('xl/sharedStrings.xml'))
                shared=[''.join(t.text or '' for t in si.iter(NS+'t')) for si in root]
            rels=_xml(archive.read('xl/_rels/workbook.xml.rels'))
            targets={r.get('Id'):r.get('Target','') for r in rels if r.get('TargetMode')!='External'}
            workbook=_xml(archive.read('xl/workbook.xml'))
            props=workbook.find(NS+'workbookPr')
            if props is not None and props.get('date1904') in ('1','true'):
                raise AssessmentError('Use the template date system (1900) for assessment dates.')
            result={}
            for sheet in workbook.iter(NS+'sheet'):
                title=sheet.get('name')
                if title not in ('Overview','Assessment'):
                    continue
                if title in result:
                    raise AssessmentError('Duplicate assessment sheet.')
                target=targets[sheet.get(REL+'id')]
                target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
                if target not in names:
                    raise AssessmentError('Workbook worksheet is missing.')
                root=_xml(archive.read(target))
                cells={}
                for cell in root.iter(NS+'c'):
                    address=cell.get('r','')
                    match=re.fullmatch(r'([A-Z]{1,2})([1-9][0-9]{0,3})',address)
                    if not match or int(match[2])>500:
                        raise AssessmentError('Assessment sheets may contain at most 500 rows and 52 columns.')
                    col=0
                    for char in match[1]: col=col*26+ord(char)-64
                    if col>52 or address in cells:
                        raise AssessmentError('Invalid or duplicate assessment cell.')
                    value=cell.find(NS+'v')
                    text=value.text or '' if value is not None else ''
                    if cell.get('t')=='s': text=shared[int(text)]
                    elif cell.get('t')=='inlineStr': text=''.join(t.text or '' for t in cell.iter(NS+'t'))
                    if len(text)>4000:
                        raise AssessmentError('Keep each assessment entry below 4,000 characters.')
                    cells[address]=(text.strip(), cell.find(NS+'f') is not None)
                result[title]=cells
            if set(result)!= {'Overview','Assessment'}:
                raise AssessmentError('Use the WACC template with Overview and Assessment sheets.')
            return result
    except AssessmentError:
        raise
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError, IndexError, RuntimeError, OSError) as exc:
        raise AssessmentError('The file is not a readable WACC assessment XLSX.') from exc


def _value(sheet,cell):
    value,formula=sheet.get(cell,('',False))
    if formula:
        raise AssessmentError(f'{cell}: enter a value instead of a formula in assessment inputs.')
    return value


def _date(value,field,required=False):
    if not value and not required: return ''
    try:
        # Excel stores calendar dates as numbers; accept dates entered as ISO text too.
        if re.fullmatch(r'\d+(?:\.0+)?',value):
            number=int(float(value))
            parsed=date(1899,12,30)+timedelta(days=number)
        else: parsed=date.fromisoformat(value)
        if not 2000<=parsed.year<=2100: raise ValueError()
        return parsed.isoformat()
    except (ValueError,OverflowError) as exc:
        raise AssessmentError(f'{field}: use a date between 2000 and 2100 (YYYY-MM-DD).') from exc


def parse_workbook(payload,filename='assessment.xlsx'):
    if not filename.lower().endswith('.xlsx'):
        raise AssessmentError('Only .xlsx assessments are supported.')
    sheets=_read_sheets(payload)
    overview=sheets['Overview']
    labels=['Department','Assessment year','Assessment date','Assessor','Scope',
            'Policy edition','Template version','Retrospective']
    meta={}
    for row,label in enumerate(labels,5):
        if _value(overview,f'A{row}')!=label:
            raise AssessmentError('Overview fields changed. Download a fresh template.')
        meta[label]=_value(overview,f'B{row}')
    if meta['Policy edition']!=POLICY['policy'] or meta['Template version']!=POLICY['schema']:
        raise AssessmentError('This importer uses the WA Cyber Security Policy 2024 template, version 1.')
    department=' '.join(unicodedata.normalize('NFKC',meta['Department']).split())
    if not department or len(department)>120 or any(ord(c)<32 for c in department):
        raise AssessmentError('Enter a department name of 1 to 120 characters.')
    if not re.fullmatch(r'20\d{2}|2100',meta['Assessment year']):
        raise AssessmentError('Assessment year must be a whole year between 2000 and 2100.')
    year=int(meta['Assessment year'])
    assessed=_date(meta['Assessment date'],'Assessment date',True)
    if int(assessed[:4])!=year:
        raise AssessmentError('Assessment date must fall within the assessment year.')
    if not meta['Assessor'] or not meta['Scope']:
        raise AssessmentError('Enter the assessor and the assessment scope.')
    if meta['Retrospective'] not in ('Yes','No') or (year<2024 and meta['Retrospective']!='Yes'):
        raise AssessmentError('Years before 2024 must be marked Retrospective: Yes.')
    reporting={}
    for n,(label,key) in enumerate([('Accountable authority','authority'),('Approval date','approval_date'),
                                  ('AIR status','air_status'),('AIR reference','air_reference'),
                                  ('Exemptions reference','exemptions')],33):
        if _value(overview,f'A{n}')!=label:
            raise AssessmentError('Approval and reporting fields changed. Download a fresh template.')
        reporting[key]=_value(overview,f'B{n}')
    reporting['approval_date']=_date(reporting['approval_date'],'Approval date')
    if reporting['air_status'] not in ('Not requested','Not submitted','Prepared','Approved','Submitted','Retrospective example'):
        raise AssessmentError('Choose an AIR status from the template list.')
    if reporting['air_status'] in ('Approved','Submitted') and not (reporting['authority'] and reporting['approval_date']):
        raise AssessmentError('An approved or submitted AIR needs the accountable authority and approval date.')
    if reporting['air_status']=='Submitted' and not reporting['air_reference']:
        raise AssessmentError('Record the submitted AIR reference.')
    sheet=sheets['Assessment']
    for i,header in enumerate(HEADERS):
        if _value(sheet,f'{chr(65+i)}6')!=header:
            raise AssessmentError('Assessment columns changed. Keep the template headings on row 6.')
    rows=[]; seen=set()
    row_numbers=sorted({int(re.search(r'\d+',key)[0]) for key in sheet if int(re.search(r'\d+',key)[0])>6})
    for n in row_numbers:
        values=[_value(sheet,f'{col}{n}') for col in 'ABCDEFGHI']
        if not any(values): continue
        key,area,prompt,rating,evidence,owner,action,due,exclusion=values
        if key not in REQUIREMENTS: raise AssessmentError(f'Row {n}: unknown requirement ID {key!r}.')
        if key in seen: raise AssessmentError(f'Row {n}: duplicate requirement {key}.')
        if area!=REQUIREMENTS[key]['area'] or prompt!=REQUIREMENTS[key]['prompt']:
            raise AssessmentError(f'{key}: the policy area or assessment prompt changed. Keep the template criteria.')
        rating=rating or 'Not assessed'
        if rating not in RATINGS: raise AssessmentError(f'{key}: choose 0, 1, 2, 3, 4, Not assessed or N/A.')
        if rating=='N/A' and not exclusion: raise AssessmentError(f'{key}: explain the exclusion before choosing N/A.')
        if rating in ('3','4') and not evidence: raise AssessmentError(f'{key}: add evidence for an implemented or tested rating.')
        rows.append(dict(id=key,rating=rating,evidence=evidence,owner=owner,action=action,
                         due=_date(due,f'{key} due date'),exclusion=exclusion))
        seen.add(key)
    missing=set(REQUIREMENTS)-seen
    if missing: raise AssessmentError(f'Missing {len(missing)} requirement rows. Keep all rows; use Not assessed or N/A where needed.')
    record=dict(schema=POLICY['schema'],department=department,year=year,date=assessed,
                assessor=meta['Assessor'],scope=meta['Scope'],retrospective=meta['Retrospective'],
                reporting=reporting, rows=sorted(rows,key=lambda r:list(REQUIREMENTS).index(r['id'])),
                filename=Path(filename.replace('\\','/')).name[:160],
                sha256=hashlib.sha256(payload).hexdigest())
    record['key']=hashlib.sha256((department.casefold()+'|'+str(year)).encode()).hexdigest()[:32]
    return record


def scores(record,area=None,ids=None):
    rows=[r for r in record['rows'] if (area is None or REQUIREMENTS[r['id']]['area']==area)
          and (ids is None or r['id'] in ids)]
    applicable=[r for r in rows if r['rating']!='N/A']
    reviewed=[r for r in applicable if r['rating'] in ('0','1','2','3','4')]
    complete=len(reviewed)==len(applicable) and bool(applicable)
    return dict(total=len(rows),excluded=len(rows)-len(applicable),rated=len(reviewed),
                missing=len(applicable)-len(reviewed),
                score=round(sum(int(r['rating']) for r in reviewed)/len(reviewed),2) if complete else None,
                implemented=sum(r['rating'] in ('3','4') for r in applicable))


def comparable_ids(records):
    """Compare the same applicable requirements in every selected year."""
    return set.intersection(*({r['id'] for r in a['rows'] if r['rating']!='N/A'} for a in records)) if records else set()


class Store:
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else Path(os.environ.get('WACC_ASSESSMENTS', ROOT/'data/local/assessments'))
        self.lock=threading.Lock()

    def all(self):
        with self.lock:
            return self._load()

    def _load(self):
        path=self.path/'records.json'
        if not path.exists(): return []
        try: return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise AssessmentError('Assessment storage cannot be read. Restore records.json from your backup.') from exc

    def import_files(self,files,replace=False):
        records=[parse_workbook(data,name) for name,data in files]
        if not records: raise AssessmentError('Select at least one assessment workbook.')
        if len({r['key'] for r in records})!=len(records):
            raise AssessmentError('Choose only one workbook for each department and year.')
        with self.lock:
            existing={r['key']:r for r in self._load()}
            names={r['department'].casefold():r['department'] for r in existing.values()}
            for r in records:
                r['department']=names.setdefault(r['department'].casefold(),r['department'])
                old=existing.get(r['key'])
                if old and old['sha256']!=r['sha256'] and not replace:
                    raise AssessmentError(f'{r["department"]}, {r["year"]} already exists. Select Replace existing years to update it.')
            now=datetime.now(timezone.utc).isoformat()
            for r in records:
                old=existing.get(r['key'])
                r['imported_at']=old['imported_at'] if old and old['sha256']==r['sha256'] else now
                existing[r['key']]=r
            self.path.mkdir(parents=True,exist_ok=True)
            temp=self.path/('records-'+uuid.uuid4().hex+'.tmp')
            try:
                temp.write_text(json.dumps(list(existing.values()),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                os.replace(temp,self.path/'records.json')
            finally:
                if temp.exists(): temp.unlink()
        return records
