"""Import unmodified publisher controls from locally acquired sources."""
import re
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile

from ..io.xlsx import Workbook
from ..model import Control, Link, Origin, Provenance, normalise_identifier


def scf(corpus, framework, path):
    book = Workbook(path)
    header, rows = book.table('SCF 2026.2')
    columns = {name: i for i, name in enumerate(header)}
    count = links = 0
    for row in rows:
        if len(row) < 4 or not re.fullmatch(r'[A-Z]+-\d+(?:\.\d+)*', row[2]):
            continue
        control = Control(framework_key=framework.key, identifier=row[2], title=row[1],
                          text=row[3], section_ref=row[0], origin=Origin.GENERATED,
                          attributes={'source_url':framework.source_url})
        corpus.add_control(control)
        count += 1
        # Exact named edition only. Generic NIST R5 does not identify the loaded
        # 5.2.0 minor revision. Older ISM, CIS and ATT&CK columns are not transferred.
        for column, target_key, pattern in (
            ('NIST\nCSF\n2.0', 'csf', r'[A-Z]{2}\.[A-Z]{2}-\d+'),
        ):
            value = row[columns[column]] if len(row) > columns[column] else ''
            for identifier in dict.fromkeys(re.findall(pattern, value)):
                target = corpus.control(target_key + ':' + normalise_identifier(identifier))
                if target:
                    corpus.add_link(Link(control.uid,target.uid,Provenance.PUBLISHED,
                        basis='SCF 2026.2 mapping column: '+column.replace('\n',' '),
                        asserted_by='Secure Controls Framework Council'))
                    links += 1
    return {'controls':count,'published_references':links}


def mcsb(corpus, framework, path):
    book = Workbook(path)
    count = links = 0
    for sheet in book.sheet_names:
        header, rows = book.table(sheet)
        if not header or header[0] != 'ID':
            continue
        for row in rows:
            record = dict(zip(header,row))
            if not re.fullmatch(r'[A-Z]{2}-\d+',record.get('ID','')):
                continue
            control = Control(framework_key=framework.key,identifier=record['ID'],
                title=record['Recommendation'].strip(),text=record['Security Principle'],
                section_ref=sheet,origin=Origin.GENERATED,
                attributes={'implementation_examples':record.get('Azure Guidance',''),
                            'source_url':framework.source_url})
            corpus.add_control(control)
            count += 1
            # The workbook names CIS v8 and NIST r4. WACC has CIS v8 and NIST r5;
            # only the former is an edition-compatible published cross-reference.
            for identifier in dict.fromkeys(re.findall(r'(?m)^\s*(\d+\.\d+)\b',record.get('CIS Controls v8 ID(s)',''))):
                target = corpus.control('cis-controls:'+identifier)
                if target:
                    corpus.add_link(Link(control.uid,target.uid,Provenance.PUBLISHED,
                        basis='Microsoft cloud security benchmark v1, CIS Controls v8 mapping',
                        asserted_by='Microsoft'))
                    links += 1
    return {'controls':count,'published_references':links}


class EssentialEightParser(HTMLParser):
    """Read Appendix A-C table rows; D repeats them as a comparison table."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.heading = None
        self.level = None
        self.cell = None
        self.row = []
        self.strategy = ''
        self.records = []

    def handle_starttag(self, tag, attrs):
        if tag == 'h2': self.heading = []
        if tag == 'tr': self.row = []
        if tag == 'td' and self.level: self.cell = []
        if tag in ('br','p') and self.cell is not None: self.cell.append(' ')

    def handle_data(self, data):
        if self.heading is not None: self.heading.append(data)
        if self.cell is not None: self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == 'h2' and self.heading is not None:
            title = ''.join(self.heading).strip()
            self.level = {'Appendix A: Maturity Level One':'ML1',
                          'Appendix B: Maturity Level Two':'ML2',
                          'Appendix C: Maturity Level Three':'ML3'}.get(title)
            self.heading = None
        if tag == 'td' and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        if tag == 'tr' and self.level and self.row:
            if len(self.row) == 2: self.strategy = self.row[0]
            self.records.append((self.level,self.strategy,self.row[-1]))


E8_STRATEGIES = {
    'Patch applications':'PA', 'Patch operating systems':'PO',
    'Multi-factor authentication':'MFA', 'Restrict administrative privileges':'RAP',
    'Restrict administrator privileges':'RAP', 'Application control':'AC',
    'Restrict Microsoft Office macros':'MAC', 'User application hardening':'UAH',
    'Regular backups':'RB',
}


def essential_eight(corpus, framework, path):
    parser = EssentialEightParser()
    parser.feed(Path(path).read_text(encoding='utf-8'))
    counters = {}
    for level, strategy, text in parser.records:
        if strategy not in E8_STRATEGIES:
            raise ValueError('Unrecognised Essential Eight strategy: '+strategy)
        prefix = level+'-'+E8_STRATEGIES[strategy]
        counters[prefix] = counters.get(prefix,0)+1
        corpus.add_control(Control(framework_key=framework.key,
            identifier=prefix+'-%02d'%counters[prefix],title=strategy,text=text,
            section_ref=level+' > '+strategy,origin=Origin.GENERATED,
            publisher_tags={'essential_eight_maturity':level},
            attributes={'identifier_note':'WACC locator: maturity level, strategy and row in the publisher table.',
                        'source_url':framework.source_url}))
    if len(counters) != 24:
        raise ValueError('Expected eight strategies in each of three Essential Eight maturity tables')
    return {'controls':len(parser.records),'strategy_levels':len(counters)}


def scuba(corpus, framework, path):
    """Read the seven current baselines; exclude superseded/removed policies."""
    products = {'aad','exo','powerbi','powerplatform','securitysuite','sharepoint','teams'}
    count = 0
    seen = set()
    with ZipFile(path) as archive:
        for name in archive.namelist():
            if '/PowerShell/ScubaGear/baselines/' not in name or Path(name).stem not in products or not name.endswith('.md'):
                continue
            product = Path(name).stem
            seen.add(product)
            content = archive.read(name).decode('utf-8-sig')
            for match in re.finditer(r'^#### (MS\.[A-Z]+\.[\d.]+v\d+)\s*\n(.*?)(?=^####? |\Z)', content, re.M|re.S):
                identifier, block = match.groups()
                statement = re.split(r'<!--Policy:|\[!\[|^- _Rationale:', block.strip(), maxsplit=1, flags=re.M)[0].strip()
                corpus.add_control(Control(framework_key=framework.key,identifier=identifier,
                    title=identifier,text=statement,section_ref=product,origin=Origin.GENERATED,
                    attributes={'source_url':'https://github.com/cisagov/ScubaGear/blob/2f8c8241a5753a83a502d06688ce82081023dd0a/PowerShell/ScubaGear/baselines/'+product+'.md',
                                'applicability':'US federal baseline; informative for WA entities. Assess applicability and licensing locally.'}))
                count += 1
    if seen != products or count < 100:
        raise ValueError('Incomplete SCuBA Microsoft 365 baseline archive')
    return {'controls':count,'products':len(seen)}
