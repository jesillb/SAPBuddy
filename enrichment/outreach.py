"""Regenerate tailored outreach copy (LinkedIn message, email, call opener)
for a single company, via Claude structured output."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from db.models import get_company, update_company
from enrichment.claude_client import call_structured

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

SYSTEM_PROMPT = (
    "You are an expert SAP BRIM/RAR recruitment copywriter working for a "
    "Benelux-focused consultant who places SAP BRIM (SOM/CC/CI/FI-CA) and "
    "SAP RAR specialists into high-volume subscription and usage billing "
    "environments (telco, utilities, media/streaming, transport, SaaS, "
    "industrials with service contracts). Write like an experienced "
    "recruiter, not a marketer: concrete, specific, no buzzwords, no "
    "exclamation marks, no \"I hope this finds you well\"."
)

with open(PROMPTS_DIR / "generate_outreach_schema.json") as f:
    OUTREACH_SCHEMA = json.load(f)


def _company_profile_json(company) -> str:
    profile = asdict(company)
    profile.pop("notes", None)
    profile.pop("last_contacted_at", None)
    return json.dumps(profile, indent=2)


def _build_user_prompt(company) -> str:
    profile_json = _company_profile_json(company)
    return f"""Write outreach copy for this enriched company profile:

```json
{profile_json}
```

Ground everything in the specific signals in this profile (industry,
likely_modules, brim_components_likely, recent_events, brim_score_reason,
s4_migration_status, einvoicing_pressure) - do not write generic copy that
could apply to any company. If einvoicing_pressure is medium/high, it's
fair game as a timely hook (Belgium's B2B e-invoicing mandate, Peppol,
from 1 Jan 2026).

Produce:

1. **linkedin_message** - short, casual-professional, one clear ask
   (e.g. a 15-minute call about their billing/RAR resourcing).
2. **email** - a subject line (as the first line, "Subject: ...") plus a
   100-180 word body: one line of specific context about the company, one
   line on why that implies a BRIM/RAR resourcing need, one clear call to
   action.
3. **call_opener_bullets** - exactly 3 bullets a recruiter can glance at
   30 seconds before dialling: the hook, the likely pain point, the ask.

Return JSON that exactly matches the provided schema. Do not include any
extra text outside the JSON."""


def regenerate_outreach(company_id: int) -> dict:
    """Call Claude for fresh outreach copy, persist it into
    outreach_angles, and return the raw result dict."""
    company = get_company(company_id)
    if company is None:
        raise ValueError(f"No company with id={company_id}")

    result = call_structured(SYSTEM_PROMPT, _build_user_prompt(company), OUTREACH_SCHEMA)
    apply_outreach_result(company_id, result)
    return result


def apply_outreach_result(company_id: int, result: dict) -> None:
    angles = [
        f"LinkedIn message:\n{result.get('linkedin_message', '')}",
        f"Email:\n{result.get('email', '')}",
        "Call opener:\n" + "\n".join(f"- {b}" for b in result.get("call_opener_bullets", [])),
    ]
    update_company(company_id, outreach_angles=angles)
