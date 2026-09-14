"""Rate the frequency of every Control workspace topic in the assessable corpus."""
from collections import Counter
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wacc.archetypes import classify
from wacc.control_workspace import TOPICS
from wacc.serve import State


# These patterns represent every workspace topic rather than broad security domains.
# A corpus entry may support more than one topic, so topic counts intentionally overlap.
TOPIC_PATTERNS = {
    "RM": (
        "Cybersecurity risk assessment",
        r"\b(risk assessments?|risk analysis|assess(?:ing|ed)? (?:the )?(?:cyber ?security|"
        r"security) risk|risk register|risk treatment plans?)\b",
    ),
    "ST": (
        "Security testing and assurance",
        r"\b(penetration test(?:ing|s)?|security control assessments?|control assessments?|"
        r"security testing|independent assessment|red team(?:ing)?|assurance activities)\b",
    ),
    "MW": (
        "Mobile and wireless security",
        r"\b(mobile devices?|wireless (?:access|networks?|communications?|security)|"
        r"wi-?fi|bluetooth)\b",
    ),
    "PI": (
        "Privacy and personal information",
        r"\b(personally identifiable information|personal information|privacy risk|"
        r"privacy program|privacy controls?|privacy impact assessment)\b",
    ),
    "PW": (
        "Password security",
        r"\b(passwords?|passphrases?|password managers?)\b",
    ),
    "AD": (
        "Active Directory security",
        r"\b(active directory|ad ds|domain controllers?|domain admins?|dcsync|"
        r"kerberos|ntlm|ldap signing|service principal names?|spns?|group managed "
        r"service accounts?|gmsas?|sid filtering|unconstrained delegation|krbtgt|"
        r"entra connect|ad fs|ad cs)\b",
    ),
    "IA": (
        "Identity and access management",
        r"\b(access control|access (?:rights|permissions|authori[sz]ations)|account "
        r"(?:management|lifecycle|provisioning|deprovisioning)|identity (?:management|"
        r"lifecycle|governance)|identities and credentials|user accounts?|service "
        r"accounts?|authenticator management)\b",
    ),
    "PA": (
        "Privileged access",
        r"\b(privileged (?:access|accounts?|users?|operations?)|administrative "
        r"(?:access|accounts?|privileges?)|administrator accounts?|least privilege|"
        r"elevated privilege|domain admin)\b",
    ),
    "BR": (
        "Backup and recovery",
        r"\b(backups?|backed up|restor(?:e|ation|ations|ing)|disaster recovery|"
        r"recovery (?:time|point|plans?|copies|data)|reconstitution)\b",
    ),
    "SM": (
        "Security monitoring",
        r"\b(event logs?|audit logs?|audit records?|central(?:ised|ized) logging|"
        r"log (?:collection|monitoring|retention|review)|security monitoring|"
        r"intrusion detection|continuous monitoring)\b",
    ),
    "VM": (
        "Vulnerability management",
        r"\b(vulnerabilit\w*|patch(?:es|ed|ing)?|security updates?|"
        r"vulnerability scanning|unsupported software|end.of.support)\b",
    ),
    "MF": (
        "Multi-factor authentication",
        r"\b(multi.factor authentication|multifactor authentication|two.factor "
        r"authentication|second factor|mfa)\b",
    ),
    "AP": (
        "Application control",
        r"\b(application control|application allowlist\w*|software allowlist\w*|"
        r"allow.by.exception|permit.by.exception|authori[sz]ed software|"
        r"unauthori[sz]ed (?:software|code|scripts?|libraries))\b",
    ),
    "CK": (
        "Cryptographic keys and algorithms",
        r"\b(cryptographic (?:keys?|algorithms?|protocols?|protection)|key management|"
        r"key (?:length|size|generation|storage|destruction|revocation)|cryptoperiod|"
        r"cipher suites?|approved cryptography|security strength)\b",
    ),
    "MD": (
        "Media sanitisation and disposal",
        r"\b(saniti[sz](?:e|ed|es|ing|ation)|secure disposal|media (?:disposal|"
        r"destruction|saniti[sz]ation)|degauss\w*|cryptographic erase|destroy media)\b",
    ),
    "IN": (
        "Incident notification timeframes",
        r"\b(incident (?:notification|reporting)|report (?:a |the )?cyber security "
        r"incident|notify .*cyber security incident|notifiable incident|"
        r"within (?:4|12|24|72) hours)\b",
    ),
    "IR": (
        "Incident response and management",
        r"\b(incident (?:management|response|handling|analysis|containment|eradication|"
        r"recovery|triage|declaration|lessons.learned)|post.incident reviews?|response "
        r"plans?|response exercises?)\b",
    ),
    "SC": (
        "Supply chain and third-party risk",
        r"\b(supply chain|suppliers?|third.part(?:y|ies)|service providers?|"
        r"outsourc\w*|vendors?|subcontractors?)\b",
    ),
    "DP": (
        "Data protection",
        r"\b(data (?:classification|categorization|protection|inventory|sensitivity|"
        r"handling|retention|loss prevention|exfiltration)|information (?:classification|"
        r"categorization|handling|flow)|sensitive (?:data|information)|data at rest|"
        r"data in transit)\b",
    ),
    "UH": (
        "User application hardening",
        r"\b(user application hardening|office productivity suites?|pdf software|"
        r"web browsers?.{0,30}harden|browser hardening|child processes?|"
        r"object linking and embedding|ole packages?)\b",
    ),
    "OM": (
        "Restrict Microsoft Office macros",
        r"\b(microsoft office macros?|office macros?|macro settings?|macro security|"
        r"trusted publishers?|trusted locations?|win32 api calls?)\b",
    ),
    "GV": (
        "Governance and cybersecurity program management",
        r"\b(cyber ?security governance|cyber ?security program|risk management "
        r"strategy|accountable authorit\w*|risk executive|governance arrangements?|"
        r"security governance|program oversight)\b",
    ),
    "PS": (
        "Personnel security",
        r"\b(personnel security|personnel screening|pre.employment screening|"
        r"background checks?|personnel (?:termination|transfer)|rescreen\w*|"
        r"security clearances?|employment screening)\b",
    ),
    "PH": (
        "Physical security",
        r"\b(physical (?:security|access|protection|barriers?)|facility access|"
        r"security zones?|secure areas?|physical perimeter|visitor access|"
        r"access cards?|security guards?)\b",
    ),
    "AM": (
        "Asset inventory and configuration/change management",
        r"\b(asset (?:inventory|inventories|register|management)|enterprise asset "
        r"inventory|software inventory|system component inventory|configuration "
        r"(?:baseline|baselines|management|change control)|change management|"
        r"secure configurations?)\b",
    ),
    "NA": (
        "Network architecture and segmentation",
        r"\b(network (?:architecture|segmentation|segregation|boundaries)|security "
        r"zones?|boundary protection|managed interfaces?|demilitari[sz]ed zone|"
        r"network zones?|segment(?:ed|ing) networks?)\b",
    ),
    "AW": (
        "Security awareness and workforce training",
        r"\b(security awareness|cyber ?security awareness|literacy training|"
        r"role.based training|role.specific training|security culture|"
        r"workforce (?:training|development)|awareness training)\b",
    ),
    "OT": (
        "Operational technology security",
        r"\b(operational technology|ot (?:assets?|networks?|systems?|environment|"
        r"environments|security|playbooks?)|it and ot|it.ot segmentation|"
        r"industrial control systems?|scada|field devices?)\b",
    ),
    "SD": (
        "Secure software development",
        r"\b(secure (?:software|application) development|software development life.?cycle|"
        r"system development life.?cycle|secure coding|threat model(?:ling|ing)|code "
        r"reviews?|application security testing|developer testing)\b",
    ),
    "BC": (
        "Business continuity and resilience",
        r"\b(business continuity|continuity plans?|contingency plans?|continuity of "
        r"operations|business impact analysis|recovery objectives?|minimum operations|"
        r"essential (?:mission|business) functions)\b",
    ),
}

RATING_BANDS = (
    (200, 5, "Very high"),
    (100, 4, "High"),
    (50, 3, "Medium"),
    (20, 2, "Low"),
    (0, 1, "Very low"),
)


def frequency_rating(count):
    for minimum, score, label in RATING_BANDS:
        if count >= minimum:
            return score, label
    raise AssertionError("rating bands must include zero")


def assessable_entries(state):
    entries = []
    seen = set()
    for control in state.corpus.controls.values():
        if classify(control, state.relations.ancestors(control.uid))[2] is not None:
            continue
        text = state.relations.quotable_text(control.uid)
        if control.title and not control.title_is_shared:
            text = control.title + " " + text
        fingerprint = (control.framework_key, " ".join(text.casefold().split()))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        entries.append((control, text))
    return entries


def measure(state):
    rated_topics = {topic for topic, _ in TOPIC_PATTERNS.values()}
    workspace_topics = set(TOPICS)
    if rated_topics != workspace_topics:
        missing = sorted(workspace_topics - rated_topics)
        unknown = sorted(rated_topics - workspace_topics)
        raise ValueError(
            f"frequency patterns are out of sync with the workspace; "
            f"missing={missing}, unknown={unknown}"
        )
    entries = assessable_entries(state)
    framework_totals = Counter(control.framework_key for control, _ in entries)
    ranked = []
    for code, (topic, pattern) in TOPIC_PATTERNS.items():
        hits = [control for control, text in entries if re.search(pattern, text, re.I)]
        counts = Counter(control.framework_key for control in hits)
        score, rating = frequency_rating(len(hits))
        ranked.append({
            "code": code,
            "topic": topic,
            "controls": len(hits),
            "frameworks": len(counts),
            "frequency_score": score,
            "frequency_rating": rating,
            "mean_framework_share": round(
                sum(counts[key] / framework_totals[key] for key in framework_totals)
                / len(framework_totals) * 100,
                2,
            ),
            "per_framework": dict(sorted(counts.items())),
            "sample_uids": [control.uid for control in hits[:8]],
        })
    ranked.sort(key=lambda row: (-row["controls"], -row["frameworks"], row["topic"]))
    for position, row in enumerate(ranked, 1):
        row["rank"] = position
    rating_distribution = Counter(row["frequency_rating"] for row in ranked)
    return {
        "method": (
            "Explicit phrase matches for each Control workspace topic against "
            "assessable corpus entries. Duplicate text within a framework is counted once; "
            "topics overlap. Counts measure how often the corpus states the subject, not its "
            "importance, implementation priority or compliance status."
        ),
        "rating_scale": {
            "5 - Very high": "200 or more matching entries",
            "4 - High": "100 to 199 matching entries",
            "3 - Medium": "50 to 99 matching entries",
            "2 - Low": "20 to 49 matching entries",
            "1 - Very low": "fewer than 20 matching entries",
        },
        "rating_distribution": {
            label: rating_distribution[label]
            for _, _, label in RATING_BANDS
        },
        "patterns": {
            code: {"topic": topic, "pattern": pattern}
            for code, (topic, pattern) in TOPIC_PATTERNS.items()
        },
        "loaded_controls": len(state.corpus.controls),
        "eligible_entries": len(entries),
        "eligible_frameworks": len(framework_totals),
        "topics": ranked,
    }


if __name__ == "__main__":
    report = measure(State())
    target = Path(__file__).resolve().parents[1] / "data/validation/topic_prevalence.json"
    target.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("Eligible:", report["eligible_entries"], "frameworks:", report["eligible_frameworks"])
    for row in report["topics"]:
        print(
            "%2d  %-2s  %-9s  %4d entries  %2d frameworks  %s"
            % (
                row["rank"],
                row["code"],
                row["frequency_rating"],
                row["controls"],
                row["frameworks"],
                row["topic"],
            )
        )
