import json
from pathlib import Path

import jsonschema
import pytest

from db.models import Company, create_company, get_company
from enrichment.enrich_company import ENRICH_SCHEMA, apply_enrichment_result
from enrichment.outreach import OUTREACH_SCHEMA, apply_outreach_result

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

SAMPLE_ENRICHMENT_RESPONSE = {
    "domain": "example-utilities.nl",
    "hq_city": "Rotterdam",
    "hq_country": "NL",
    "other_sites": [{"city": "Antwerp", "country": "BE", "type": "office"}],
    "industry": "District heating utility",
    "industry_category": "utilities_energy",
    "employee_range": "1000-4999",
    "revenue_range_eur": "250M-500M EUR",
    "sap_status": "s4hana",
    "sap_signals": ["Job post for SAP S/4HANA FI-CA consultant, June 2026"],
    "likely_modules": ["S/4HANA", "FI-CA", "SOM"],
    "module_confidence": "medium",
    "brim_components_likely": ["SOM", "FI-CA", "RAR"],
    "brim_evidence": ["https://example.com/press/billing-transformation"],
    "brim_evidence_flags": {
        "mentions_brim_or_hybris": True,
        "mentions_rar": False,
        "mentions_billing_job_postings": True,
        "mentions_billing_case_study": True,
        "strong_subscription_usage_model": False,
    },
    "fit_rationale": "Utility with confirmed S/4HANA and active BRIM-adjacent hiring.",
    "recent_events": [
        {
            "title": "Billing platform modernisation announced",
            "source": "Company press release",
            "date": "2026-05-12",
            "url": "https://example.com/press/billing-transformation",
            "summary": "Announced a multi-year billing transformation programme.",
            "themes": ["billing", "s4hana"],
        }
    ],
    "s4_migration_status": "in_flight",
    "einvoicing_pressure": "medium",
    "recommended_action": "Reach out about their billing transformation programme this week.",
    "outreach_angles": ["Reference the June 2026 FI-CA job post directly."],
}

SAMPLE_OUTREACH_RESPONSE = {
    "linkedin_message": "Saw your FI-CA posting - worth a quick call on BRIM/RAR resourcing?",
    "email": "Subject: BRIM/RAR support for your billing transformation\n\nBody text here.",
    "call_opener_bullets": ["FI-CA hiring", "Billing transformation", "Ask for 15 minutes"],
}


def test_enrich_schema_file_matches_module_constant():
    with open(PROMPTS_DIR / "enrich_company_schema.json") as f:
        assert json.load(f) == ENRICH_SCHEMA


def test_outreach_schema_file_matches_module_constant():
    with open(PROMPTS_DIR / "generate_outreach_schema.json") as f:
        assert json.load(f) == OUTREACH_SCHEMA


def test_sample_enrichment_response_validates_against_schema():
    jsonschema.validate(instance=SAMPLE_ENRICHMENT_RESPONSE, schema=ENRICH_SCHEMA)


def test_sample_outreach_response_validates_against_schema():
    jsonschema.validate(instance=SAMPLE_OUTREACH_RESPONSE, schema=OUTREACH_SCHEMA)


def test_invalid_enrichment_response_fails_validation():
    bad = dict(SAMPLE_ENRICHMENT_RESPONSE)
    bad["sap_status"] = "definitely_sap"  # not in enum
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=ENRICH_SCHEMA)


def test_apply_enrichment_result_scores_and_persists():
    company_id = create_company(Company(name="Rotterdam Heat NV"))
    apply_enrichment_result(company_id, SAMPLE_ENRICHMENT_RESPONSE)

    company = get_company(company_id)
    assert company.domain == "example-utilities.nl"
    assert company.hq_city == "Rotterdam"
    assert company.sap_status == "s4hana"
    assert company.likely_modules == ["S/4HANA", "FI-CA", "SOM"]
    assert company.last_event_date == "2026-05-12"
    # utilities_energy(35) + 1000-4999(15) + s4hana(20) + evidence capped(20) = 90
    assert company.brim_score == 90
    assert company.priority_tier == "A"
    assert "Total: 90/100" in company.brim_score_reason
    assert "confirmed S/4HANA and active BRIM" in company.brim_score_reason


def test_apply_outreach_result_persists_formatted_blocks():
    company_id = create_company(Company(name="Rotterdam Heat NV"))
    apply_outreach_result(company_id, SAMPLE_OUTREACH_RESPONSE)

    company = get_company(company_id)
    assert len(company.outreach_angles) == 3
    assert "LinkedIn message" in company.outreach_angles[0]
    assert "Email" in company.outreach_angles[1]
    assert "Call opener" in company.outreach_angles[2]
