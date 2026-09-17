"""Suggested assessments, selected from the control's own subject text.

These are local templates, not publisher procedures or observed findings. A match
provides an assessment starting point; applicability and sampling remain explicit.
"""
import re

# Specific topics precede broader ones. Do not match framework names or query terms:
# an assessment must follow the requirement, not the search that retrieved it.
PROFILES = [
 (r'(?=.*\bpersonal information\b)(?=.*\b(?:request\w*|denial)\b)(?=.*\b(?:access|correction)\b)(?=.*\b(?:individual|person)\b)',
  'People may be unable to obtain or correct their records, leaving decisions based on inaccurate information or requests unresolved.',
  'Sample access and correction case files. Check identity, the applicable legal route, receipt date, decision, reasons and response date. '
  'Trace corrections into the affected records and inspect any refusal or delay reasons. Compare each response with the period and permitted outcomes stated in the provision.',
  ('nist-800-53:si-18',)),
 (r'\b(?:privacy impact assessment|automated decision.making process)\b',
  'A new use of personal information or an automated decision could harm people if privacy impacts are missed or remain untreated.',
  'Inspect the written impact assessment, affected information, potential harm, recommendations and approvals. '
  'Check it predates the activity or significant change where required, and trace recommendations to completed actions. '
  'For automated decisions, inspect harm and bias reviews, notices, human-review requests and periodic evaluations.',
  ('nist-800-53:ra-8',)),
 (r'(?=.*\bpersonal information\b)(?=.*\b(?:collect\w*|secondary purpose|primary purpose|policies on its handling)\b)',
  'Unnecessary collection or use of personal information beyond its authorised purpose could harm people and expose the organisation to complaints.',
  'Compare sampled collection fields, uses and disclosures with written purposes, collection notices and the applicable consent or legal basis. '
  'Check necessity, exceptions and actual data flows. Inspect the privacy policy and records of changed or secondary uses.',
  ('nist-800-53:pt-2', 'nist-800-53:pt-3')),
 ('(?=.*\\bprivileg\\w*\\b)(?=.*\\b(request\\w*|validat\\w*|approv\\w*)\\b)',
  'Granting administrator access without checking the need could allow unauthorised changes, disclosure of '
  'sensitive information or disruption of services.',
  'Examine a sample of initial privileged-access requests, including rejected requests and exceptions. '
  'Compare the recorded business need and authorisation with the permissions actually granted and the '
  'activation date. Interview the approving owner about how requests are validated. Test a sample against '
  'the approval workflow to establish whether access was enabled before validation.',
  ('nist-800-53:ac-2', 'nist-800-53:ac-6.5')),
 ('(?=.*\\b(logs?|logging|audit '
  '(?:records?|information))\\b)(?=.*\\b(protect\\w*|unauthori[sz]ed|tamper\\w*)\\b)',
  'If people can alter or delete security records without permission, an attacker could hide what happened '
  'and delay the investigation.',
  'Examine permissions and protection settings for log stores and logging tools. Compare access with '
  'authorised roles, including administrator access. Interview the log owner about access approval and '
  'changes. Using an authorised test account and test records, verify that unauthorised reading, alteration '
  'and deletion are blocked and recorded.',
  ('nist-800-53:au-9',)),
 ('(?=.*\\b(logs?|audit records?)\\b)(?=.*\\b(retain\\w*|retention)\\b)',
  'Deleting security records too soon could prevent the organisation from understanding an incident and '
  'establishing which information or services were affected.',
  'Examine the required retention period, storage configuration and oldest available records for sampled log '
  'sources. Retrieve records from the start of that period and check completeness and readability. Interview '
  'the owner about capacity limits and deletion exceptions. Compare actual availability with the period '
  'stated in the control.',
  ('nist-800-53:au-11',)),
 ('(?=.*\\b(logs?|audit records?)\\b)(?=.*\\b(review\\w*|analys\\w*|analyz\\w*)\\b)',
  'Security records that are not reviewed could leave an attack unnoticed, giving it more time to disrupt '
  'services or expose information.',
  'Examine completed log reviews, alerts and investigation records for the assessment period. Interview the '
  'responsible analysts about review criteria and escalation. Trace a sample of relevant events to '
  'documented investigation and action, and compare review dates with the required frequency.',
  ('nist-800-53:au-6',)),
 ('\\b(multi.factor|mfa)\\b',
  'A stolen password could let an attacker enter business systems, steal information or interrupt services '
  'if a second identity check is missing.',
  'Export authentication policies, application coverage and sign-in logs. Reconcile them to in-scope users, '
  'privileged accounts and remote entry points. With an authorised test account, verify that access requires '
  'the prescribed factors; check legacy authentication, exclusions and recovery paths for bypasses. Record '
  'uncovered applications and accounts for follow-up.',
  ('nist-800-53:ia-2',)),
 ('\\b(backups?|backed up|restor\\w*|disaster recovery|business continuity)\\b',
  'If backups cannot be restored, an outage or ransomware attack could stop services for longer and '
  'permanently destroy important information.',
  'Reconcile backup and recovery coverage to critical services and their dependencies. Inspect job results, '
  'retention, access separation and failed-job follow-up. Witness an authorised restore in an isolated '
  'environment, verify recovered data integrity, and compare measured recovery time and data loss with '
  'approved recovery objectives. Record coverage gaps and failed recovery steps.',
  ('nist-800-53:cp-9', 'nist-800-53:cp-10')),
 ('\\b(patch\\w*|vulnerabilit\\w*|security updates?)\\b',
  'Unfixed software weaknesses could let attackers steal information or stop important services.',
  'Reconcile the asset inventory with vulnerability scans and patch deployment records, including unmanaged '
  'and unsupported assets. Sample internet-facing and critical systems; compare detection and remediation '
  'timestamps with the applicable deadlines. Verify the installed fix or rescan result, rather than ticket '
  'closure alone. Record overdue exposure, affected services and approved exceptions.',
  ('nist-800-53:si-2',)),
 ('\\b(logs?|logging|logged|audit (?:trail|records?)|monitoring|detection)\\b',
  'If security events are missed or not investigated, an attack could continue unnoticed and cause greater '
  'harm.',
  'Map in-scope systems to required event sources and detection use cases. Inspect event collection, '
  'timestamps, retention, access restrictions and alert ownership. Generate an authorised benign test event '
  'and trace it from source through collection, alerting and triage. Sample recent alerts for investigation '
  'and closure evidence; record missing sources and response gaps.',
  ('nist-800-53:au-6', 'nist-800-53:si-4')),
 ('\\b(encrypt\\w*|cryptograph\\w*|cipher\\w*|key length)\\b',
  'If information is not securely protected, someone who obtains it could read or change confidential '
  'business data.',
  'Identify in-scope data stores and transmission paths. Inspect effective encryption settings, protocols, '
  'algorithms and key management records against the control parameters. Sample actual connections or '
  'storage configurations and check key access, rotation and recovery arrangements. Record unprotected paths '
  'and unsupported cryptographic settings.',
  ('nist-800-53:sc-13',)),
 ('\\b(privileg\\w*|access|permissions?|accounts?|password\\w*|credentials?)\\b',
  'People with unnecessary access could misuse sensitive information or make changes that interrupt '
  'important services.',
  'Export effective accounts, roles and permissions and reconcile them to approved access and current '
  'personnel or service owners. Sample privileged, changed and departed-user accounts. Verify approval, '
  'least privilege, timely removal and access-review follow-up; where authorised, test that an unapproved '
  'operation is denied. Record excess access and orphaned accounts.',
  ('nist-800-53:ac-2', 'nist-800-53:ac-6')),
 ('\\b(incident\\w*|notifi\\w*)\\b',
  'Slow incident handling or missed notifications could increase disruption and delay help for affected '
  'people.',
  'Inspect the incident plan, reporting criteria, contact list and decision responsibilities. Walk through a '
  'realistic scenario with the response team. Sample incidents and compare the applicable trigger, '
  'escalation, decision and notification timestamps with the stated requirements. Verify that exercise and '
  'incident actions have owners and closure evidence.',
  ('nist-800-53:ir-4', 'nist-800-53:ir-6')),
 ('\\b(train\\w*|awareness|educat\\w*)\\b',
  'Staff who do not recognise threats or know how to respond could make mistakes that lead to data loss or '
  'service disruption.',
  'Reconcile training coverage to current staff, contractors and role-specific responsibilities. Inspect '
  'content, completion records and overdue follow-up. Use an approved exercise or knowledge check to verify '
  'that participants can recognise and report a relevant scenario. Record uncovered roles and demonstrated '
  'capability gaps.',
  ('nist-800-53:at-2',)),
 ('\\b(suppliers?|third.part\\w*|contracts?|outsourc\\w*)\\b',
  'A supplier security failure could expose information or interrupt the services that depend on that '
  'supplier.',
  'Reconcile critical suppliers to the service and data inventory. Sample contracts, due diligence, access '
  'arrangements and ongoing assurance against the stated requirement. Verify that identified supplier '
  'weaknesses are tracked and that incident, recovery and exit responsibilities can be exercised. Record '
  'missing obligations and unresolved dependencies.',
  ('nist-800-53:sr-6',)),
 ('\\b(configur\\w*|harden\\w*|application control|allowlist\\w*|macros?)\\b',
  'Unsafe system settings could let an attacker run harmful software, steal information or interrupt '
  'services.',
  'Inspect the approved configuration baseline and effective settings on a sample of in-scope systems. '
  'Include critical systems and known exceptions. Compare deployed settings with the specific requirement '
  'and, where authorised, test the relevant restriction using a benign example. Record configuration drift, '
  'bypasses and unsupported exceptions.',
  ('nist-800-53:cm-6',))]

FALLBACKS = {
    'document': ('Outdated or unused security procedures can leave staff unsure what to do, increasing the chance of mistakes that disrupt services or expose information.', 'Inspect the approved policy, plan or procedure, its scope, owner and review history. Trace each relevant requirement to an implemented activity and sample operational evidence. Record requirements that lack implementation, ownership or current approval.'),
    'responsibility': ('Without someone responsible for security decisions, known problems may remain unfixed until they cause data loss or service disruption.', 'Verify assigned decision rights, role acceptance, resourcing and escalation paths. Sample recent security decisions and overdue actions to confirm that the accountable owner acted and followed through.'),
    'periodic': ('Missed security checks can allow problems to grow unnoticed and increase the chance of data loss or service disruption.', 'Obtain the scheduled check and completed records for the assessment period. Compare actual dates and coverage with the requirement, and trace identified issues through remediation and verification.'),
    'prohibition': ('If a prohibited action is still possible, it could undermine security protections and put information or services at risk.', 'Identify the prohibited action and where it could occur. Inspect preventative settings and exception records, then use an authorised benign test to verify enforcement. Search operational records for prohibited instances and document any bypass.'),
}


def guidance(text, archetype):
    for pattern, risk, assessment, _ in PROFILES:
        if re.search(pattern, text, re.I):
            return risk, assessment
    return FALLBACKS.get(archetype, (
        'An ineffective security control can leave the organisation exposed to service disruption or misuse of information.',
        'Translate the requirement below into observable acceptance criteria with the control owner. Identify the in-scope services, existing implementation and evidence source. Inspect a risk-based sample and demonstrate whether each criterion is met. Where the requirement states an outcome, trace it to the activities and measures used to achieve that outcome.'
    ))


RECORD_RESULT = ('Record the scope, sample, evidence references and result for each acceptance criterion. '
                 'Describe any exception, its affected systems and the follow-up required.')


def assessment_sources(text):
    """Curated subject connections, not publisher mappings or equivalent controls."""
    for pattern, _, _, sources in PROFILES:
        if re.search(pattern, text, re.I):
            return sources
    return ()
