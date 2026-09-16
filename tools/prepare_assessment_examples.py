"""Build authored policy prompts and fictional examples; no publisher text copied."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Stable references follow the locally acquired 2024 policy. Each prompt is WACC's.
PROMPTS = '''
1.1a|Manage cyber risk through the accountable authority.
1.1b|Assign executive responsibility for cyber security.
1.1c|Consider risks to other WA entities and share relevant risks with DGov.
1.1d|Fund and resource continuing policy implementation.
1.2a|Give the cyber security executive authority to implement the policy.
1.2b|Provide the executive with the skills and resources needed.
1.2c|Report implementation progress to the accountable authority.
1.2d|Notify DGov of a changed cyber security executive within five days.
1.3|Maintain enough skilled people to operate cyber security.
1.4a|Align security governance with the department's objectives.
1.4b|Make cyber risks visible to decision makers.
1.4c|Set security objectives and review current maturity.
1.4d|Oversee third-party security arrangements.
1.4e|Maintain plans for implementing the policy.
1.4f|Plan continuity, incident response and recovery.
1.4g|Obtain assurance that security controls work, including ACSC controls.
1.5a|Assess offshore data risks against WA offshoring guidance.
1.5b|Use WA public cloud risk assessment guidance for offshoring decisions.
1.5c|Apply WA information classification when assessing offshore data.
1.6|Oversee secure disposal of devices and storage media.
1.7|Oversee timely identification and remediation of vulnerabilities.
1.8|Operate a vulnerability disclosure program.
1.9a|Follow whole-of-government cyber directions or obtain an exemption.
1.9b|Consider DGov threat intelligence and advice.
2.1a|Record devices, servers and ICT equipment in the inventory.
2.1b|Record applications and their servers.
2.1c|Record critical databases and information assets.
2.1d|Record relevant staff and third-party providers.
2.1e|Record the department's social media applications.
2.1f|Record system dependencies and related risks.
2.1g|Record future cyber security needs.
2.1h|Record applicable legal and regulatory obligations.
2.2a|Assess cyber risk within the department's risk framework.
2.2b|Use the department's ICT and business context in risk assessments.
2.2c|Include known threats and vulnerabilities in risk assessments.
2.2d|Include critical information assets in risk assessments.
2.2e|Assess responsibilities shared with managed service providers.
2.2f|Assess procurement and supply chain risks; reassess when systems, threats or operations change.
3.1.1a|Meet Essential Eight Level One using the November 2022 model; progress to Level Two where appropriate.
3.1.1b|Use risk assessments to decide where higher Essential Eight maturity is needed.
3.1.2|Implement the Further Five, or document a risk-based decision for exclusions.
3.1.3a|Decide which remaining ACSC strategies are needed to manage risk.
3.1.3b|Decide which other controls are needed, including for operational technology.
3.2a|Deliver cyber awareness training each year.
3.2b|Deliver tailored training for specialist and sensitive roles.
3.3|Manage and monitor corporate and BYO mobile devices, harden their apps and address overseas travel risks.
3.4|Consider information security in new procurement and renegotiable contract extensions.
3.4.1a|Assess procurement risks to confidentiality, integrity and availability, including information sensitivity.
3.4.1b|Check suppliers' security maturity and relevant independent assessments.
3.4.1c|Assess security risks in the supply chain.
3.4.1d|Assess security in software procurement, development and integration.
3.4.1e|Prefer independently assessed offerings, such as IRAP, for high-risk managed and cloud services.
3.4.1f|Document which security responsibilities belong to the supplier and the department.
3.4.1g|Check supplier and subcontractor insurance against the risks.
3.4.1h|Consider WA offshoring requirements before procurement.
3.4.2a|Require suppliers to report incidents to the department within 24 hours of detection.
3.4.2b|Require suppliers to maintain relevant security certifications during the contract.
3.4.2c|Require protection of department information throughout the contract.
3.4.2d|Require secure disposal or return of department data when a contract ends.
3.4.2e|Include penalties or termination rights for security failures.
3.4.2f|Include other relevant ACSC contractual security requirements.
3.5|Control physical access to ICT assets and protect them from damage.
3.6a|Manage account creation, changes and removal through the personnel lifecycle.
3.6b|Limit account access to the privileges needed.
3.6c|Apply password filtering to all user accounts.
3.6d|Align authentication with WA Government guidance.
3.6e|Use protective DNS.
3.6f|Improve network controls supporting access security.
3.7a|Consider insurance for the department's own cyber incident losses.
3.7b|Consider insurance for third-party claims arising from cyber incidents.
4.1a|Analyse adverse events and escalate suspected incidents for triage.
4.1b|Review adverse events at least every 24 hours during normal operations and report suspected incidents.
4.1c|Assess the likely business impact of adverse events.
4.1d|Share acquired threat intelligence with DGov within 24 hours.
4.2a|Use a SIEM with continuing incident detection and response for assets and networks.
4.2b|Align data sources and detections with DGov's MITRE ATT&CK baseline.
4.2c|Share SIEM incident information with DGov's SOC through integration or delegated access.
5.1a|Keep an incident response plan available for immediate use.
5.1b|Plan to triage incidents and determine a response within four hours.
5.1c|Plan to notify DGov of confirmed incidents within 24 hours of detection.
5.1d|Plan to report relevant incidents to ACSC through ReportCyber within 24 hours.
5.1e|Align the response plan with WA CSICF and ACSC response guidance.
5.2|Exercise incident response at least annually.
5.3|Refer ransom demands to DGov and WA Police; reserve payment approval to SECC.
6.1|Demonstrate restoration within the timeframes set in continuity or incident plans.
6.2|Review significant incidents, update recovery plans where needed and send DGov the PIR within 20 working days of detection.
'''

# Evidence references and observations below are entirely fictional.
SECTIONS = {
 '1.1': ('Executive risk minutes', 'Accountable authority', 'Risk ownership was informal.', 'Quarterly risk reporting and funding were approved.', 'Four quarterly reviews tracked decisions and overdue actions.'),
 '1.2': ('Cyber executive delegation and reports', 'Cyber security executive', 'Executive delegation and reporting were being drafted.', 'Delegation was signed; reporting and change notification were in use.', 'Delegation, reporting and notification records were sampled and reviewed.'),
 '1.3': ('Security workforce plan', 'ICT director', 'Coverage depended on one administrator.', 'A security lead and managed service covered daily operations.', 'Leave cover and incident surge capacity were tested.'),
 '1.4': ('Security governance pack', 'Cyber security executive', 'Governance documents existed in draft only.', 'Approved governance and implementation plans covered most services.', 'Committee reviews and assurance samples tracked exceptions to closure.'),
 '1.5': ('Cloud offshoring risk assessment', 'Information owner', 'Cloud locations and classifications were not consistently recorded.', 'Major cloud services had classification and offshoring assessments.', 'All cloud services were reviewed; contract and location changes were checked.'),
 '1.6': ('Device disposal certificates', 'ICT operations manager', 'Disposal records were incomplete.', 'An approved disposal process captured certificates for new disposals.', 'A sample of retired devices reconciled to sanitisation certificates.'),
 '1.7': ('Vulnerability register and remediation tickets', 'ICT operations manager', 'Scans were irregular and fixes had no agreed deadlines.', 'Monthly scans and remediation targets covered most devices.', 'Exceptions were reviewed and a sample of fixes was rescanned.'),
 '1.8': ('Vulnerability disclosure register', 'Security lead', 'No public disclosure route existed.', 'A disclosure mailbox and handling procedure were operating.', 'A test report reached the responder and met the response target.'),
 '1.9': ('DGov direction and intelligence register', 'Security lead', 'Advice was stored in individual mailboxes.', 'Directions and advice were logged with responsible owners.', 'Monthly reviews checked action completion and exemption expiry.'),
 '2.1': ('ICT and information asset register', 'Enterprise architect', 'Spreadsheets covered only core servers and devices.', 'The inventory covered major systems, owners and obligations.', 'Quarterly reconciliation checked discovery, ownership and dependencies.'),
 '2.2': ('Cyber risk register', 'Risk manager', 'Cyber risks were recorded without consistent business context.', 'The risk register covered key assets, suppliers and treatment owners.', 'Reviews after service changes checked threats, shared duties and treatments.'),
 '3.1.1': ('Essential Eight assessment workbook', 'Security lead', 'The baseline assessment identified gaps across all eight strategies.', 'Most Level One requirements were deployed; legacy app exceptions remained.', 'Testing confirmed Level One across all eight; higher-risk services had a Level Two plan.'),
 '3.1.2': ('Further Five assessment', 'Security lead', 'Email protection and personnel checks existed but other controls were incomplete.', 'The five strategies were deployed across most services.', 'Samples tested all five strategies; remaining segmentation work was tracked.'),
 '3.1.3': ('Additional control selection register', 'Risk manager', 'Additional controls had not been selected consistently.', 'Risk reviews selected extra controls for critical and supplier services.', 'Annual review verified control choices against current threats and service changes.'),
 '3.2': ('Training completion and role matrix', 'People services manager', 'General awareness reached 42% of staff; tailored training was planned.', 'Annual training reached 88%; specialist role sessions were introduced.', 'Completion reached 98%; missed sessions and role changes were followed up.'),
 '3.3': ('Mobile compliance and travel register', 'Endpoint manager', 'Only a portion of corporate mobiles were managed.', 'Corporate mobiles were enrolled; BYO and travel coverage was incomplete.', 'Compliance sampling included BYO, application settings and travel returns.'),
 '3.4': ('Procurement security screening register', 'Procurement manager', 'Security review was requested late and inconsistently.', 'New purchases and renewable contracts used security screening.', 'Procurement samples confirmed screening before approvals.'),
 '3.4.1': ('Supplier due diligence files', 'Procurement manager', 'Supplier checks covered price and availability more than security.', 'High-risk suppliers had risk, certification and shared-responsibility reviews.', 'A supplier sample verified assessment scope, insurance and data location checks.'),
 '3.4.2': ('Contract security clause review', 'Contract manager', 'Legacy contracts lacked consistent security clauses.', 'New contracts contained clauses; legacy renewals remained in progress.', 'Contract sampling confirmed required clauses and recorded remaining legacy gaps.'),
 '3.5': ('Site access review and visitor log', 'Facilities manager', 'Key and visitor records were not routinely reconciled.', 'Access lists and visitor sign-in were operating for critical rooms.', 'Access samples and a site inspection verified physical safeguards.'),
 '3.6': ('Identity, DNS and network review', 'Identity manager', 'Leaver, privileged access and password filtering gaps were known.', 'Most accounts and networks used the approved baseline; exceptions remained.', 'Account, password filter, DNS and network tests verified implementation.'),
 '3.7': ('Cyber insurance decision paper', 'Chief finance officer', 'The department had not assessed cyber insurance needs.', 'Risk and coverage reviews informed the insurance decision.', 'Renewal review tested loss scenarios against first- and third-party cover.'),
 '4.1': ('SOC event review and escalation log', 'SOC manager', 'Alerts were reviewed intermittently without impact triage.', 'Daily reviews and escalation operated during business hours.', 'Timestamp samples confirmed event review and intelligence-sharing deadlines.'),
 '4.2': ('SIEM coverage and DGov integration review', 'SOC manager', 'Logs from critical systems were fragmented.', 'Core logs and detection rules were in place; DGov integration was being completed.', 'Detection exercises verified coverage and incident transfer; legacy logs remained an action.'),
 '5.1': ('Incident response plan and exercise log', 'Incident manager', 'An old plan omitted notification deadlines and offline access.', 'The plan included triage and reporting deadlines and had an initial exercise.', 'An exercise verified offline access, four-hour triage and 24-hour reporting.'),
 '5.2': ('Annual incident exercise report', 'Incident manager', 'No annual exercise had been completed.', 'A tabletop exercise identified coordination gaps.', 'The annual exercise retested actions and recorded accountable owners.'),
 '5.3': ('Ransomware response decision record', 'Incident manager', 'Escalation and ransom authority were unclear in the plan.', 'The playbook named DGov, WA Police and SECC authority.', 'The exercise checked demand referral and the approval escalation route.'),
 '6.1': ('Restore exercise and recovery time report', 'Service continuity manager', 'Backups existed but business recovery times were untested.', 'A partial restore succeeded; critical service recovery targets were not all met.', 'A timed restoration met approved recovery targets and included business verification.'),
 '6.2': ('Post-incident review and action log', 'Incident manager', 'There was no agreed lessons-learned process.', 'A PIR template and DGov reporting workflow had been introduced.', 'A simulated incident tested the 20-working-day report and recovery-plan updates.'),
}

def main():
    # This script uses identifiers only from the acquired extract to verify coverage.
    source = json.loads((ROOT/'data/corpus/wa-csp.json').read_text(encoding='utf-8'))
    lookup = {r['identifier']: r for r in source['records']}
    areas = ['Govern','Identify','Protect','Detect','Respond','Recover']
    requirements = []
    for line in PROMPTS.strip().splitlines():
        key, prompt = line.split('|', 1)
        section = lookup[key]['section_number']
        requirements.append(dict(id=key, area=areas[int(key[0])-1], prompt=prompt,
                                 section=section, evidence=SECTIONS[section][0]))
    assert {r['id'] for r in requirements} == set(lookup)
    catalogue = dict(schema='wacc-wa-csp-2024-v1', policy='WA Cyber Security Policy 2024',
                     source_url='https://www.wa.gov.au/system/files/2024-12/wacybersecuritypolicy.pdf',
                     attribution='Policy reference: State of Western Australia, Department of the Premier and Cabinet. Assessment prompts and rating scale: WACC.',
                     areas=areas, requirements=requirements)
    (ROOT/'data/department-assessment-policy.json').write_text(json.dumps(catalogue,indent=2)+'\n',encoding='utf-8')
    examples=[]
    for year in [2023,2024,2025]:
        rows=[]
        for i,r in enumerate(requirements):
            evidence,owner,*observations=SECTIONS[r['section']]
            # Successive years never regress. Technical delivery lags governance.
            score = ([0,1,1,2][i%4] if year==2023 else
                     [2,2,3,3][i%4] if year==2024 else [3,4,4,4][i%4])
            if r['section'] in ('3.1.1','3.1.2','4.2','6.1'):
                score={2023:1,2024:2,2025:3}[year]
            action = ('Test remaining coverage and close exceptions.' if score==3 else
                      'Maintain scheduled review and repeat the evidence sample.' if score==4 else
                      'Complete coverage, obtain approval and test implementation.' if score==2 else
                      'Assign an owner and complete the implementation plan.' if score==1 else
                      'Define the process, scope and delivery milestones.')
            rows.append(dict(id=r['id'],rating=str(score),evidence=f'DSW-{year}-{r["id"]}: {evidence}. {observations[year-2023]}',
                             owner=owner,action=action,due=f'{year+1}-06-30',exclusion=''))
        examples.append(dict(department='Department of Silly Walks',year=year,
                             date=f'{year}-12-31',assessor='Fictional Security Assurance Team',
                             scope='All departmental ICT, cloud services and suppliers. Fictional demonstration data.',
                             retrospective='Yes' if year==2023 else 'No',rows=rows,
                             authority='Director General (fictional)',
                             approval_date=f'{year}-12-20' if year==2025 else '',
                             air_status={2023:'Retrospective example',2024:'Prepared',2025:'Submitted'}[year],
                             air_reference=f'DSW-AIR-{year} (fictional)' if year>=2024 else '',
                             exemptions='No approved exemptions recorded.'))
    (ROOT/'data/department-assessment-examples.json').write_text(json.dumps(examples,indent=2)+'\n',encoding='utf-8')

if __name__ == '__main__':
    main()
