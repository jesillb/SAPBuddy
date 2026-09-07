from scoring.brim_score import compute_score


def test_strong_telco_candidate_scores_tier_a():
    result = compute_score(
        industry_category="telco",
        employee_range="5000+",
        sap_status="s4hana",
        s4_migration_status="completed",
        evidence={
            "mentions_brim_or_hybris": True,
            "mentions_rar": True,
            "mentions_billing_job_postings": True,
        },
    )
    # 35 (industry) + 20 (size) + 20 (sap) + 20 (evidence, capped) = 100 -> capped/tier A
    assert result.score == 95
    assert result.tier == "A"
    assert any("telco" in line.lower() or "Telco" in line for line in result.breakdown)


def test_weak_unknown_company_scores_tier_c():
    result = compute_score(
        industry_category="other",
        employee_range="<250",
        sap_status="unknown",
        s4_migration_status="unknown",
        evidence={},
    )
    assert result.score == 10  # 5 (industry) + 5 (size) + 0 + 0
    assert result.tier == "C"


def test_mid_saas_company_scores_tier_b():
    result = compute_score(
        industry_category="saas_tech_subscription",
        employee_range="250-999",
        sap_status="likely_sap",
        s4_migration_status="unknown",
        evidence={"strong_subscription_usage_model": True},
    )
    # 25 + 10 + 5 + 5 = 45
    assert result.score == 45
    assert result.tier == "B"


def test_score_evidence_bonus_is_capped_at_20():
    result = compute_score(
        industry_category="utilities_energy",
        employee_range="5000+",
        sap_status="s4hana",
        s4_migration_status="completed",
        evidence={
            "mentions_brim_or_hybris": True,  # 15
            "mentions_rar": True,  # 10 -> would be 25 uncapped, capped to 20
            "mentions_billing_job_postings": True,
            "mentions_billing_case_study": True,
            "strong_subscription_usage_model": True,
        },
    )
    # 35 (industry) + 20 (size) + 20 (sap) + 20 (evidence, capped from 50) = 95
    assert result.score == 95
    assert result.tier == "A"


def test_planned_s4_migration_counts_as_likely_s4hana():
    result = compute_score(
        industry_category="other",
        employee_range="unknown",
        sap_status="unknown",
        s4_migration_status="planned",
        evidence={},
    )
    assert "likely S/4HANA" in "\n".join(result.breakdown)
