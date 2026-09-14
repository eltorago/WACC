"""Suggested uplift assessments, selected from the control's own subject text.

These are local templates, not publisher procedures or observed findings. A match
provides an assessment starting point; applicability and sampling remain explicit.
"""
import re

# Specific topics precede broader ones. Do not match framework names or query terms:
# an assessment must follow the requirement, not the search that retrieved it.
PROFILES = [
    (r'\b(multi.factor|mfa)\b',
     'If authentication can be completed without the required additional factor, an attacker with a stolen password could access business systems, expose data or disrupt services.',
     'Export authentication policies, application coverage and sign-in logs. Reconcile them to in-scope users, privileged accounts and remote entry points. With an authorised test account, verify that access requires the prescribed factors; check legacy authentication, exclusions and recovery paths for bypasses. Record uncovered applications and accounts as uplift actions.'),
    (r'\b(backups?|backed up|restor\w*|disaster recovery|business continuity)\b',
     'If recovery arrangements do not work for critical systems and data, ransomware, corruption or equipment failure could cause prolonged service outages and permanent data loss.',
     'Reconcile backup and recovery coverage to critical services and their dependencies. Inspect job results, retention, access separation and failed-job follow-up. Witness an authorised restore in an isolated environment, verify recovered data integrity, and compare measured recovery time and data loss with approved recovery objectives. Record coverage gaps and failed recovery steps.'),
    (r'\b(patch\w*|vulnerabilit\w*|security updates?)\b',
     'If exploitable vulnerabilities remain on exposed or critical assets, an attacker could compromise those systems, move into connected environments and disrupt services or steal data.',
     'Reconcile the asset inventory with vulnerability scans and patch deployment records, including unmanaged and unsupported assets. Sample internet-facing and critical systems; compare detection and remediation timestamps with the applicable deadlines. Verify the installed fix or rescan result, rather than ticket closure alone. Record overdue exposure, affected services and approved exceptions.'),
    (r'\b(logs?|logging|logged|audit (?:trail|records?)|monitoring|detection)\b',
     'If relevant security events are not captured, protected and acted on, malicious activity could remain undetected and responders may lack the evidence needed to contain an incident.',
     'Map in-scope systems to required event sources and detection use cases. Inspect event collection, timestamps, retention, access restrictions and alert ownership. Generate an authorised benign test event and trace it from source through collection, alerting and triage. Sample recent alerts for investigation and closure evidence; record missing sources and response gaps.'),
    (r'\b(encrypt\w*|cryptograph\w*|cipher\w*|key length)\b',
     'If sensitive information is protected with ineffective cryptography or exposed keys, unauthorised parties could read or alter it, causing disclosure, integrity loss and disruption to trusted services.',
     'Identify in-scope data stores and transmission paths. Inspect effective encryption settings, protocols, algorithms and key management records against the control parameters. Sample actual connections or storage configurations and check key access, rotation and recovery arrangements. Record unprotected paths and unsupported cryptographic settings.'),
    (r'\b(privileg\w*|access|permissions?|accounts?|password\w*|credentials?)\b',
     'If access exceeds authorised business need or is not removed promptly, compromised or misused accounts could expose sensitive data, change critical configurations or interrupt services.',
     'Export effective accounts, roles and permissions and reconcile them to approved access and current personnel or service owners. Sample privileged, changed and departed-user accounts. Verify approval, least privilege, timely removal and access-review follow-up; where authorised, test that an unapproved operation is denied. Record excess access and orphaned accounts.'),
    (r'\b(incident\w*|notifi\w*)\b',
     'If incident escalation and reporting arrangements fail, containment could be delayed and affected services or stakeholders may remain exposed while required notifications are missed.',
     'Inspect the incident plan, reporting criteria, contact list and decision responsibilities. Walk through a realistic scenario with the response team. Sample incidents and compare the applicable trigger, escalation, decision and notification timestamps with the stated requirements. Verify that exercise and incident actions have owners and closure evidence.'),
    (r'\b(train\w*|awareness|educat\w*)\b',
     'If personnel cannot recognise threats or carry out their security responsibilities, avoidable errors and delayed reporting could enable compromise or increase the impact of an incident.',
     'Reconcile training coverage to current staff, contractors and role-specific responsibilities. Inspect content, completion records and overdue follow-up. Use an approved exercise or knowledge check to verify that participants can recognise and report a relevant scenario. Record uncovered roles and demonstrated capability gaps.'),
    (r'\b(suppliers?|third.part\w*|contracts?|outsourc\w*)\b',
     'If supplier security obligations and oversight are ineffective, a supplier compromise or service failure could expose organisational data and disrupt dependent business services.',
     'Reconcile critical suppliers to the service and data inventory. Sample contracts, due diligence, access arrangements and ongoing assurance against the stated requirement. Verify that identified supplier weaknesses are tracked and that incident, recovery and exit responsibilities can be exercised. Record missing obligations and unresolved dependencies.'),
    (r'\b(configur\w*|harden\w*|application control|allowlist\w*|macros?)\b',
     'If system settings permit unnecessary functionality or unapproved execution, an attacker could exploit the exposed capability to run malicious code, gain persistence or compromise business data.',
     'Inspect the approved configuration baseline and effective settings on a sample of in-scope systems. Include critical systems and known exceptions. Compare deployed settings with the specific requirement and, where authorised, test the relevant restriction using a benign example. Record configuration drift, bypasses and unsupported exceptions.'),
]

FALLBACKS = {
    'document': ('If security requirements are undocumented, outdated or not put into practice, teams could implement inconsistent protections and leave critical services exposed to preventable incidents.', 'Inspect the approved policy, plan or procedure, its scope, owner and review history. Trace each relevant requirement to an implemented activity and sample operational evidence. Record requirements that lack implementation, ownership or current approval.'),
    'responsibility': ('If security decisions have no accountable owner or resources, remediation could be delayed and known exposure could persist across critical services.', 'Verify assigned decision rights, role acceptance, resourcing and escalation paths. Sample recent security decisions and overdue actions to confirm that the accountable owner acted and followed through.'),
    'periodic': ('If recurring security checks lapse, changes and unresolved weaknesses could accumulate without detection, increasing the exposure of business services.', 'Obtain the scheduled check and completed records for the assessment period. Compare actual dates and coverage with the requirement, and trace identified issues through remediation and verification.'),
    'prohibition': ('If the prohibited activity is possible in the assessed environment, users or attackers could bypass the intended protection and expose affected systems or information.', 'Identify the prohibited action and where it could occur. Inspect preventative settings and exception records, then use an authorised benign test to verify enforcement. Search operational records for prohibited instances and document any bypass.'),
}


def guidance(text, archetype):
    for pattern, risk, assessment in PROFILES:
        if re.search(pattern, text, re.I):
            return risk, assessment
    return FALLBACKS.get(archetype, (
        'If this requirement is not implemented and operating across its intended scope, the affected service may retain security exposure that is not captured in the uplift plan.',
        'Translate the requirement below into observable acceptance criteria with the control owner. Identify the in-scope services, existing implementation and evidence source. Inspect a risk-based sample and demonstrate whether each criterion is met. Where the requirement states an outcome, trace it to the activities and measures used to achieve that outcome.'
    ))


RECORD_RESULT = ('Record scope, sample selection, evidence references and unmet acceptance criteria. '
                 'For each gap, identify the affected service, interim protection, remediation action, '
                 'accountable owner, target date and retest needed to close it. Set priority using '
                 'the actual exposure and business impact; a missing document alone is not a risk rating.')
