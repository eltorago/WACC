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


class StrategiesParser(HTMLParser):
    """Only the five-column strategy table, with its publisher category rows."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cell = None; self.row = []; self.category = ''; self.records = []

    def handle_starttag(self, tag, attrs):
        if tag == 'tr': self.row = []
        if tag in ('td', 'th'): self.cell = []
        if tag in ('br', 'p') and self.cell is not None: self.cell.append(' ')

    def handle_data(self, text):
        if self.cell is not None: self.cell.append(text)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell = None
        if tag == 'tr':
            if len(self.row) == 1 and self.row[0].startswith('Mitigation strateg'):
                self.category = self.row[0].rstrip(':')
            elif len(self.row) == 5 and self.row[0] in ('Essential', 'Excellent', 'Very Good', 'Good', 'Limited'):
                if not self.category: raise ValueError('Strategy without category')
                self.records.append((self.category, *self.row))


class StrategyDetailsParser(HTMLParser):
    """Preserve each strategy's rationale/guidance under its own heading."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.heading = None; self.active = False; self.title = None; self.records = {}

    def handle_starttag(self, tag, attrs):
        if tag in ('h2', 'h3'): self.heading = []
        if tag in ('p', 'li', 'h4', 'br') and self.title: self.records[self.title].append('\n')

    def handle_data(self, text):
        if self.heading is not None: self.heading.append(text)
        elif self.title: self.records[self.title].append(text)

    def handle_endtag(self, tag):
        if tag in ('h2', 'h3') and self.heading is not None:
            heading = ' '.join(''.join(self.heading).split()); self.heading = None
            if tag == 'h2':
                self.active = heading.startswith('Mitigation strateg'); self.title = None
            elif self.active:
                self.title = heading; self.records[heading] = []


STRATEGY_TITLES = [
    'Application control', 'Patch applications', 'Configure Microsoft Office macro settings',
    'User application hardening', 'Automated dynamic analysis of email and web content run in a sandbox',
    'Email content filtering', 'Web content filtering', 'Deny corporate computers direct internet connectivity',
    'Operating system generic exploit mitigation', 'Server application hardening', 'Operating system hardening',
    'Antivirus software using heuristics and reputation ratings', 'Control removable storage media and connected devices',
    'Block spoofed emails', 'User education', 'Antivirus software with up-to-date signatures',
    'TLS encryption between email servers', 'Restrict administrative privileges', 'Patch operating systems',
    'Multi-factor authentication', 'Disable local administrator accounts', 'Network segmentation',
    'Protect authentication credentials', 'Non-persistent virtualised sandboxed environment',
    'Software-based application firewall, blocking incoming network traffic',
    'Software-based application firewall, blocking outgoing network traffic',
    'Outbound web and email data loss prevention', 'Continuous incident detection and response',
    'Host-based intrusion detection/prevention system', 'Endpoint detection and response software',
    'Hunt to discover incidents', 'Network-based intrusion detection/prevention system', 'Capture network traffic',
    'Regular backups', 'Business continuity and disaster recovery plans', 'System recovery capabilities',
    'Personnel management',
]


def strategies(corpus, framework, path):
    parser = StrategiesParser(); parser.feed(Path(path).read_text(encoding='utf-8'))
    if len(parser.records) != 37 or len({r[0] for r in parser.records}) != 5:
        raise ValueError('Expected 37 strategies in five categories in the February 2017 table')
    details_path = Path(path).with_name('asd-strategies-details-2017.html')
    details = StrategyDetailsParser()
    if details_path.exists():
        details.feed(details_path.read_text(encoding='utf-8'))
        if set(details.records) != set(STRATEGY_TITLES):
            raise ValueError('Mitigation details headings do not match the reviewed 37 strategies')
    for i, (category, rating, text, resistance, upfront, ongoing) in enumerate(parser.records):
        title = STRATEGY_TITLES[i]
        if not text.startswith(title): raise ValueError('Strategy table order/content changed: '+title)
        attributes = {'source_url': framework.source_url,
            'identifier_note': 'S01-S37 are WACC row locators, not publisher control identifiers.',
            'edition_note': 'February 2017 guidance. Historical software examples and timeframes are preserved; use current ISM and Essential Eight requirements for present-day assessments.',
            'relative_effectiveness': rating, 'user_resistance': resistance,
            'upfront_cost': upfront, 'ongoing_cost': ongoing}
        if title in details.records:
            attributes['implementation_examples'] = '\n'.join(' '.join(line.split()) for line in ''.join(details.records[title]).splitlines() if line.strip())
            attributes['implementation_source_url'] = framework.source_url.replace('strategies-to-mitigate-cybersecurity-incidents', 'strategies-to-mitigate-cyber-security-incidents-mitigation-details')
        corpus.add_control(Control(framework_key=framework.key, identifier='S%02d' % (i+1),
            title=title, text=text, section_ref=category, origin=Origin.GENERATED,
            attributes=attributes, publisher_tags={'effectiveness_2017': rating}))
    return {'controls': 37, 'categories': 5, 'mitigation_details': len(details.records)}


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
