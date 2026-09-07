from db.models import (
    Company,
    create_company,
    get_company,
    list_companies,
    list_distinct_values,
    update_company,
    upsert_from_csv_row,
)


def test_create_and_get_company():
    company = Company(name="Acme Utilities", hq_country="NL", industry="Utilities")
    company_id = create_company(company)

    fetched = get_company(company_id)
    assert fetched is not None
    assert fetched.name == "Acme Utilities"
    assert fetched.hq_country == "NL"
    assert fetched.brim_score == 0
    assert fetched.priority_tier == "C"
    assert fetched.other_sites == []


def test_update_company_json_fields_roundtrip():
    company_id = create_company(Company(name="Streamly", hq_country="BE"))
    update_company(
        company_id,
        likely_modules=["S/4HANA", "FI-CA"],
        recent_events=[{"title": "Go-live", "source": "press", "date": "2026-01-01", "url": "", "summary": "", "themes": ["s4hana"]}],
        brim_score=72,
        priority_tier="A",
    )
    fetched = get_company(company_id)
    assert fetched.likely_modules == ["S/4HANA", "FI-CA"]
    assert fetched.recent_events[0]["title"] == "Go-live"
    assert fetched.brim_score == 72
    assert fetched.priority_tier == "A"


def test_upsert_from_csv_row_creates_then_updates():
    company_id, created = upsert_from_csv_row("Telco NV", domain="telco.example", country="BE", tags=["priority"])
    assert created is True

    company_id_2, created_2 = upsert_from_csv_row("Telco NV", domain="telco.example", country="BE", tags=["hot"])
    assert created_2 is False
    assert company_id_2 == company_id

    fetched = get_company(company_id)
    assert set(fetched.tags) == {"priority", "hot"}


def test_list_companies_filters_by_tier_and_score():
    a = create_company(Company(name="A Co", hq_country="NL", priority_tier="A", brim_score=80))
    create_company(Company(name="C Co", hq_country="NL", priority_tier="C", brim_score=10))

    results = list_companies(priority_tiers=["A"])
    assert [c.id for c in results] == [a]

    results = list_companies(score_min=50)
    assert len(results) == 1
    assert results[0].name == "A Co"


def test_list_distinct_values():
    create_company(Company(name="X", hq_country="NL"))
    create_company(Company(name="Y", hq_country="BE"))
    create_company(Company(name="Z", hq_country="NL"))

    countries = list_distinct_values("hq_country")
    assert countries == ["BE", "NL"]
