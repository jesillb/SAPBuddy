"""BRIM likelihood scoring.

Pure, deterministic Python logic so the recruiter can see exactly why a
company scored the way it did, and so the weights can be tuned without
touching the Claude prompts. See README.md "BRIM scoring logic" for the
rationale behind each weight.
"""
from __future__ import annotations

from dataclasses import dataclass, field

INDUSTRY_WEIGHTS = {
    "telco": 35,
    "utilities_energy": 35,
    "media_streaming": 30,
    "transport_mobility": 30,
    "saas_tech_subscription": 25,
    "manufacturing_industrial_service": 15,
    "other": 5,
}

EMPLOYEE_RANGE_WEIGHTS = {
    "5000+": 20,
    "1000-4999": 15,
    "250-999": 10,
    "<250": 5,
    "unknown": 0,
}

SAP_STATUS_WEIGHTS = {
    "s4hana": 20,  # confirmed S/4HANA
    "confirmed_sap": 10,  # confirmed ECC with transformation signals
    "likely_sap": 5,
    "ecc": 10,
    "unknown": 0,
}

# "Likely S/4HANA" is expressed via s4_migration_status rather than sap_status,
# so it is handled separately in compute_score.
LIKELY_S4_BONUS = 15

EVIDENCE_WEIGHTS = {
    "mentions_brim_or_hybris": 15,
    "mentions_rar": 10,
    "mentions_billing_job_postings": 10,
    "mentions_billing_case_study": 10,
    "strong_subscription_usage_model": 5,
}

INDUSTRY_LABELS = {
    "telco": "Telco",
    "utilities_energy": "Utilities/energy",
    "media_streaming": "Media/streaming",
    "transport_mobility": "Transport/mobility",
    "saas_tech_subscription": "SaaS/tech with subscription/usage",
    "manufacturing_industrial_service": "Manufacturing/industrial with service contracts",
    "other": "Other",
}


@dataclass
class ScoreResult:
    score: int
    tier: str
    breakdown: list = field(default_factory=list)

    @property
    def reason_text(self) -> list:
        return self.breakdown


def _tier_for_score(score: int) -> str:
    if score >= 70:
        return "A"
    if score >= 40:
        return "B"
    return "C"


def compute_score(
    industry_category: str = "other",
    employee_range: str = "unknown",
    sap_status: str = "unknown",
    s4_migration_status: str = "unknown",
    evidence: dict | None = None,
) -> ScoreResult:
    """Compute a 0-100 BRIM fit score plus a human-readable breakdown.

    industry_category: one of INDUSTRY_WEIGHTS keys.
    employee_range: one of EMPLOYEE_RANGE_WEIGHTS keys.
    sap_status: db companies.sap_status value (unknown/likely_sap/confirmed_sap/s4hana/ecc).
    s4_migration_status: unknown/planned/in_flight/completed - "planned" or
        "in_flight" without a confirmed s4hana sap_status is treated as
        "likely S/4HANA" for scoring purposes.
    evidence: dict of booleans, keys from EVIDENCE_WEIGHTS.
    """
    evidence = evidence or {}
    breakdown = []
    score = 0

    industry_category = industry_category if industry_category in INDUSTRY_WEIGHTS else "other"
    industry_points = INDUSTRY_WEIGHTS[industry_category]
    score += industry_points
    breakdown.append(f"Industry fit ({INDUSTRY_LABELS[industry_category]}): +{industry_points}")

    employee_range = employee_range if employee_range in EMPLOYEE_RANGE_WEIGHTS else "unknown"
    size_points = EMPLOYEE_RANGE_WEIGHTS[employee_range]
    score += size_points
    breakdown.append(f"Size/complexity ({employee_range} employees): +{size_points}")

    if sap_status == "s4hana":
        sap_points = SAP_STATUS_WEIGHTS["s4hana"]
        sap_label = "confirmed S/4HANA"
    elif sap_status in ("confirmed_sap", "ecc") and s4_migration_status in ("planned", "in_flight", "completed"):
        sap_points = SAP_STATUS_WEIGHTS["confirmed_sap"]
        sap_label = "confirmed ECC with transformation signals"
    elif s4_migration_status in ("planned", "in_flight"):
        sap_points = LIKELY_S4_BONUS
        sap_label = "likely S/4HANA (migration signalled)"
    elif sap_status == "likely_sap":
        sap_points = SAP_STATUS_WEIGHTS["likely_sap"]
        sap_label = "likely SAP"
    elif sap_status in ("confirmed_sap", "ecc"):
        sap_points = SAP_STATUS_WEIGHTS["confirmed_sap"]
        sap_label = "confirmed SAP (ECC)"
    else:
        sap_points = 0
        sap_label = "unknown SAP footprint"
    score += sap_points
    breakdown.append(f"SAP footprint ({sap_label}): +{sap_points}")

    evidence_points = 0
    evidence_notes = []
    for key, weight in EVIDENCE_WEIGHTS.items():
        if evidence.get(key):
            evidence_points += weight
            evidence_notes.append(key.replace("_", " "))
    evidence_points = min(evidence_points, 20)
    score += evidence_points
    if evidence_notes:
        breakdown.append(f"BRIM/RAR evidence ({', '.join(evidence_notes)}): +{evidence_points}")
    else:
        breakdown.append("BRIM/RAR evidence (none found): +0")

    score = max(0, min(100, score))
    tier = _tier_for_score(score)
    breakdown.append(f"Total: {score}/100 -> Tier {tier}")

    return ScoreResult(score=score, tier=tier, breakdown=breakdown)
