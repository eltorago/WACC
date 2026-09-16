"""Compare SCF's framework inventory with WACC; never export SCF control prose."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from wacc.io.xlsx import Workbook

# Column names are edition-specific. A mapping is evidence of overlap, not coverage.
PRIORITIES = [
    ('CSA CCM 4.1.0','CSA\nCCM\n4.1.0','Next','Cloud customer/provider responsibilities and assurance. Obtain the official CCM under its publisher terms before importing requirements.'),
    ('ISO 27017:2015','ISO \n27017\n2015','Licensed source needed','Cloud security responsibilities. Acquire licensed ISO text; SCF references do not license the standard or replace its requirements.'),
    ('ISO 27018:2025','ISO \n27018\n2025','Licensed source needed','Personal data in public cloud. Acquire the current licensed standard from ISO or an authorised distributor.'),
    ('AICPA TSC 2017:2022','AICPA\nTSC 2017:2022 (used for SOC 2)','Next','Provider assurance: obtain the criteria and each supplier’s assurance report; a SOC 2 report is entity-specific, not a generic certificate.'),
    ('NIST SP 800-207','NIST\n800-207','Next','Cloud and hybrid zero-trust architecture; complements the existing CISA maturity model.'),
    ('ISO 27001:2022','ISO\n27001\n2022','Licensed source needed','Management-system assurance. Obtain licensed publisher text; do not infer certification from control overlap.'),
    ('ISO 27002:2022','ISO\n27002\n2022','Licensed source needed','General controls guidance. Obtain licensed publisher text before a full requirements import.'),
    ('ASD Essential Eight','APAC\nAustralia\nEssential 8\n2024','Added; edition review','WACC imports the current publisher page labelled November 2023. SCF labels its column 2024; no automatic transfer of these mappings.'),
    ('ASD ISM','APAC\nAustralia\nISM\nMarch 2026','Already present; different edition','WACC uses September 2026; SCF uses March 2026. Compare changes before accepting SCF mappings.'),
    ('CIS Controls','CIS\nCSC\n8.1','Already present; different edition','WACC uses v8; SCF uses v8.1. The Microsoft workbook’s v8 references are kept separate.'),
    ('NIST CSF 2.0','NIST\nCSF\n2.0','Already present','Same named edition. SCF cross-references remain publisher assertions, not compliance determinations.'),
    ('NIST SP 800-53 R5','NIST\n800-53\nR5','Already present; minor revision unspecified','SCF names R5 without WACC’s 5.2.0 minor revision. No automatic SCF-to-800-53 links are imported.'),
]


def generate(path):
    book=Workbook(path)
    header,rows=book.table('SCF 2026.2')
    rows=[r for r in rows if len(r)>3 and re.fullmatch(r'[A-Z]+-\d+(?:\.\d+)*',r[2])]
    _,focal=book.table('Focal Documents')
    inventory={r[1]:r for r in focal if len(r)>=6}
    columns=[]
    for i in range(33,285):
        title=header[i]
        meta=inventory.get(title,[])
        columns.append({'column':title.replace('\n',' '),'mapped_scf_controls':sum(bool(r[i].strip()) for r in rows),
                        'source_url':meta[5] if meta else '', 'document':meta[4] if meta else title.replace('\n',' ')})
    priorities=[]
    for title,column,status,reason in PRIORITIES:
        i=header.index(column)
        meta=inventory.get(column,[])
        priorities.append(dict(title=title,status=status,reason=reason,mapped_scf_controls=sum(bool(r[i].strip()) for r in rows),source_url=meta[5] if meta else 'https://github.com/securecontrolsframework/securecontrolsframework'))
    data=dict(reviewed_on='2026-09-16',source='SCF 2026.2',sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
              scf_controls=len(rows),mapping_columns=len(columns),focal_documents=len(focal),priorities=priorities,inventory=columns)
    (ROOT/'data/framework-review.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['# Framework coverage review','',
           'Reviewed 16 September 2026 against the SCF 2026.2 workbook. SCF is used as an inventory of referenced frameworks; its control prose is not reproduced in this report. The workbook stays local.',
           '',f'The workbook contains {len(rows):,} SCF controls, {len(columns)} external mapping columns and {len(focal)} focal-document metadata rows. Columns include editions, profiles and overlays; these are not counts of distinct frameworks.',
           '', 'Counts below mean SCF controls with a non-empty mapping cell. They are not counts of target controls, independent mentions, legal applicability or evidence of compliance.',
           '', '## Cloud and Microsoft 365 priorities','',
           'This pass adds SCF as a locally imported meta-framework, ASD Essential Eight, Microsoft cloud security benchmark v1 and seven CISA SCuBA Microsoft 365 baselines. MCSB and SCuBA were selected from Microsoft, ACSC and WA OAG context even though they are absent from SCF’s inventory. MCSB v2 is a preview; this import explicitly uses the complete v1 workbook.',
           '', '| Framework | Status | SCF controls mapped | Why it matters / acquisition |','|---|---|---:|---|']
    for x in priorities:
        lines.append('| [%s](%s) | %s | %d | %s |'%(x['title'],x['source_url'],x['status'],x['mapped_scf_controls'],x['reason']))
    lines += ['', '## Scope and provenance','',
              'WA legislation, policy and OAG guidance already in WACC remain relevant even when SCF does not name them. CISA federal baselines are informational for WA organisations. US-specific data types, reporting recipients and mandatory language must be assessed for local applicability.',
              '', 'Imported SCF links are limited to resolvable NIST CSF 2.0 references. Generic NIST R5 and older ATT&CK, ISM and CIS columns are not silently translated to the loaded editions. Workspace technical checks are independently authored from the separately cited ACSC, Microsoft and CISA guidance.',
              '', 'The complete mapping-column inventory and non-empty counts are in `data/framework-review.json`. To reproduce: `python tools/framework_gap_report.py`. Source: https://github.com/securecontrolsframework/securecontrolsframework', '']
    (ROOT/'docs').mkdir(exist_ok=True)
    (ROOT/'docs/framework-coverage-review.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Wrote framework review:',len(columns),'mapping columns,',len(priorities),'priorities')


if __name__=='__main__':
    generate(ROOT/'sources/files/secure-controls-framework-scf-2026-2.xlsx')
