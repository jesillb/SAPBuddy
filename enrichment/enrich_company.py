"""Enrichment pipeline: Claude researches the company via live web search,
scores it, and saves the result."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from db.models import get_company, update_company
from enrichment.claude_client import WEB_SEARCH_TOOL, call_structured
from scoring.brim_score import compute_score

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

SYSTEM_PROMPT = (
    "You are an expert SAP market analyst who specialises in SAP BRIM "
    "(Billing and Revenue Innovation Management: SOM, Convergent Charging, "
    "Convergent Invoicing, FI-CA) and SAP RAR (Revenue Accounting and "
    "Reporting). You help a recruitment consultant in Benelux who places "
    "SAP BRIM/RAR specialists identify which companies most likely need "
    "that talent, based on real, current public information. You have a "
    "web_search tool - use it to research the company before answering; "
    "do not rely on memorised knowledge alone, since it may be stale. You "
    "are careful and evidence-based: only claim a signal when a search "
    "result actually supports it. When you find little or nothing, say so "
    "plainly (mark fields unknown) rather than guessing. Never fabricate "
    "URLs, dates, or quotes - only cite sources you actually retrieved."
)

with open(PROMPTS_DIR / "enrich_company_schema.json") as f:
    ENRICH_SCHEMA = json.load(f)


def _build_user_prompt(company_name: str, domain: str, country: str) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    return f"""Research this company for SAP BRIM/RAR recruitment targeting. Today's date is {today}.

**Company name:** {company_name}
**Known domain:** {domain or 'unknown'}
**Known country:** {country or 'unknown'}

**Use the web_search tool** to run searches along these lines (adapt to what
you actually find, and stop once you have enough to answer confidently -
you don't need to run every query if early results already answer it):

- "{company_name}" SAP
- "{company_name}" S/4HANA
- "{company_name}" SAP BRIM (or "Hybris Billing" / "Subscription Billing")
- "{company_name}" billing OR convergent invoicing OR rating engine (incl. job postings)
- "{company_name}" revenue recognition OR SAP RAR
- "{company_name}" news {today[:4]} (recent company news/events in general)

**Domain context for this niche:**

- Typical target industries: telco, utilities, media/streaming, transport/mobility,
  SaaS/tech with subscription models, industrials with service contracts.
- SAP BRIM components: SOM (Subscription Order Management), CC (Convergent
  Charging), CI (Convergent Invoicing), FI-CA (Contract Accounting).
- SAP RAR (Revenue Accounting & Reporting) matters for IFRS 15 / ASC 606
  compliance, especially for subscription/usage revenue recognition.
- Belgium's B2B e-invoicing mandate (Peppol, structured e-invoicing) took
  effect 1 Jan 2026 and is a realistic trigger for billing/AP transformation
  work at Belgian and Belgium-trading companies.

**Instructions:**

1. Infer firmographics (HQ, other sites, industry, size, revenue) from what
   you find. Leave fields empty/"unknown" rather than guessing when search
   doesn't support it.
2. Infer SAP footprint: sap_status, sap_signals (short evidence strings
   citing what you found), likely_modules, module_confidence.
3. Assess BRIM/RAR fit: brim_components_likely, brim_evidence (quotes/URLs
   from real search results), and brim_evidence_flags (booleans used by the
   scoring formula - only set true when a search result genuinely supports it).
4. Write a short fit_rationale a recruiter can read in 10 seconds.
5. Extract up to 5 recent_events relevant to S/4HANA, billing, revenue
   recognition, e-invoicing, or major business change - only real events
   you found via search, with real dates/sources/URLs.
6. Set s4_migration_status and einvoicing_pressure from the evidence.
7. Write recommended_action (one sentence, what to do this week) and 3-5
   outreach_angles: concrete, specific hooks tied to this company's actual
   signals - not generic recruiter copy.

Once your research is done, return JSON that exactly matches the provided
schema as your final answer. Do not include any extra text, markdown, or
commentary outside that JSON."""


def enrich_company(company_id: int) -> None:
    """Enrich a single company in place: Claude researches it via live web
    search, scores it, and the result is persisted to the DB."""
    company = get_company(company_id)
    if company is None:
        raise ValueError(f"No company with id={company_id}")

    user_prompt = _build_user_prompt(company.name, company.domain, company.hq_country)

    result = call_structured(SYSTEM_PROMPT, user_prompt, ENRICH_SCHEMA, tools=[WEB_SEARCH_TOOL])
    apply_enrichment_result(company_id, result)


def apply_enrichment_result(company_id: int, result: dict) -> None:
    """Score a parsed Claude enrichment result and persist it. Split out
    from enrich_company() so tests can exercise parsing/scoring without a
    live API call."""
    score_result = compute_score(
        industry_category=result.get("industry_category", "other"),
        employee_range=result.get("employee_range", "unknown"),
        sap_status=result.get("sap_status", "unknown"),
        s4_migration_status=result.get("s4_migration_status", "unknown"),
        evidence=result.get("brim_evidence_flags", {}),
    )

    reason_lines = list(score_result.breakdown)
    fit_rationale = result.get("fit_rationale", "").strip()
    if fit_rationale:
        reason_lines.append(fit_rationale)

    recent_events = result.get("recent_events", [])
    last_event_date = None
    dates = sorted((e.get("date") for e in recent_events if e.get("date")), reverse=True)
    if dates:
        last_event_date = dates[0]

    update_company(
        company_id,
        domain=result.get("domain") or None,
        hq_city=result.get("hq_city") or None,
        hq_country=result.get("hq_country") or None,
        other_sites=result.get("other_sites", []),
        industry=result.get("industry") or None,
        employee_range=result.get("employee_range") or None,
        revenue_range_eur=result.get("revenue_range_eur") or None,
        sap_status=result.get("sap_status", "unknown"),
        sap_signals=result.get("sap_signals", []),
        likely_modules=result.get("likely_modules", []),
        module_confidence=result.get("module_confidence") or None,
        brim_score=score_result.score,
        brim_score_reason="\n".join(reason_lines),
        brim_components_likely=result.get("brim_components_likely", []),
        brim_evidence=result.get("brim_evidence", []),
        recent_events=recent_events,
        last_event_date=last_event_date,
        s4_migration_status=result.get("s4_migration_status", "unknown"),
        einvoicing_pressure=result.get("einvoicing_pressure", "low"),
        priority_tier=score_result.tier,
        recommended_action=result.get("recommended_action") or None,
        outreach_angles=result.get("outreach_angles", []),
    )
