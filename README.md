# SAP BRIM Targeting Tool

An internal dashboard for a recruitment consultant working the SAP BRIM/RAR
niche (SOM, Convergent Charging, Convergent Invoicing, FI-CA, plus SAP RAR)
in Benelux. Upload a CSV of company names, enrich each one with public web
data via the Claude API, and get a scored, filterable list of accounts most
likely to need SAP BRIM/RAR talent - with recent events and ready-to-send
outreach copy for each one.

This is an MVP built for speed and daily usefulness, not perfection. It uses
public data only; there is no paid SAP installed-base dataset behind it, so
treat scores and inferred SAP footprints as informed hypotheses to verify,
not ground truth.

## Stack

- **Python 3.11+**
- **Streamlit** - the whole UI (`app/main.py` + `app/pages/`)
- **SQLite** - single file DB, plain `sqlite3` (no ORM), schema in `db/database.py`
- **Anthropic Claude API** - structured JSON-schema outputs, plus Claude's
  built-in `web_search` tool for real, current research on each company

## Required environment variables

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes, for enrichment | Claude API key. Also what enables live web search - no separate search API/key needed. The app runs and browses without it; enrichment/outreach calls fail with a clear message until it's set. |
| `SAPBUDDY_CLAUDE_MODEL` | No | Overrides the Claude model used for enrichment/outreach calls. Defaults to `claude-opus-5`. |
| `SAPBUDDY_CLAUDE_MAX_TOKENS` | No | Max output tokens per Claude call. Defaults to `12000` (enrichment calls do several web searches before answering, so they need more headroom than a plain completion). |
| `SAPBUDDY_WEB_SEARCH_MAX_USES` | No | Caps how many searches Claude can run per company during enrichment. Defaults to `5`. Each search is billed separately from tokens - see [Anthropic's web search pricing](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool) - so this is also a per-company cost cap. |
| `SAPBUDDY_DB_PATH` | No | Overrides the SQLite file path. Defaults to `data/sapbuddy.db`. |

Enrichment now always uses Claude's server-side `web_search` tool (no local
search API to configure) - Claude runs its own searches, reads real results,
and only marks a field "unknown" when search genuinely turns up nothing. It
runs automatically as part of the same API call as the structured output, so
there's no separate search step in the code.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # required for enrichment
streamlit run app/main.py
```

Open the URL Streamlit prints (usually http://localhost:8501). The database
file is created automatically on first run at `data/sapbuddy.db`.

A sample CSV is at `data/sample_companies.csv` if you want to try the import
flow immediately.

## How it works

1. **Import** - upload a CSV with `company_name` (required), `website`/`domain`,
   `country`, `tags` (comma-separated). Rows are upserted into the `companies`
   table, matched on name+domain.
2. **Enrich** - for each company, `enrichment/enrich_company.py` calls
   Claude once with `prompts/enrich_company_prompt.md`, Anthropic's
   server-side `web_search` tool enabled, and
   `prompts/enrich_company_schema.json` as the structured-output schema
   (`output_config.format: json_schema`). Claude runs its own searches,
   reads the results, and its final answer is guaranteed to match the
   schema - no manual JSON parsing/repair, and no local search step to
   maintain. The parsed result is then run through the deterministic
   Python scoring function (`scoring/brim_score.py`) to get `brim_score`
   and `priority_tier`, and everything is persisted to the `companies` row.
3. **Dashboard** (`app/main.py`) - filter by country, industry, priority
   tier, score range, S/4 migration status, e-invoicing pressure. Select a
   row to open its dossier. Export the filtered list as CSV.
4. **Dossier** (`app/pages/1_Company_Detail.py`) - firmographics, SAP
   footprint, BRIM fit breakdown, recent events, and outreach copy
   (LinkedIn message, email, call-opener bullets), with a button to
   regenerate outreach copy via `prompts/generate_outreach_prompt.md`.
5. **Weekly plan** (`app/pages/2_Weekly_Plan.py`) - the Monday-morning
   screen: newest Tier A accounts, accounts with the freshest events, and a
   random Tier A sample for today's outreach.

## BRIM scoring logic

Scoring is plain Python (`scoring/brim_score.py`), not something Claude
decides - so it's auditable and easy to retune. Claude infers the *inputs*
(industry category, employee range, SAP status, BRIM/RAR evidence flags);
Python turns those into a 0-100 score, capped at 100:

- **Industry fit (max 40 in practice, no hard cap beyond the table)**
  - Telco: +35 · Utilities/energy: +35 · Media/streaming: +30 ·
    Transport/mobility: +30 · SaaS/tech with subscription/usage: +25 ·
    Manufacturing/industrial with service contracts: +15 · Other: +5
- **Size/complexity (max 20)**
  - 5,000+ employees: +20 · 1,000-4,999: +15 · 250-999: +10 · <250: +5
- **SAP footprint (max 20)**
  - Confirmed S/4HANA: +20 · Confirmed ECC with transformation signals: +10
    · Likely S/4HANA (migration planned/in flight): +15 · Likely SAP: +5 ·
    Unknown: 0
- **BRIM/RAR evidence (capped at 20)**
  - Direct mention of SAP BRIM / Hybris Billing / Subscription Billing: +15
  - Direct mention of SAP RAR / Revenue Accounting: +10
  - Job posts for "high-volume billing" / "convergent invoicing" /
    "rating engine": +10
  - Case study on billing/revenue transformation: +10
  - Strong subscription/usage revenue model described: +5

`priority_tier` follows the final score: **A** &ge;70, **B** 40-69, **C** &lt;40.

To adjust weights, edit `scoring/brim_score.py` (`INDUSTRY_WEIGHTS`,
`EMPLOYEE_RANGE_WEIGHTS`, `SAP_STATUS_WEIGHTS`, `EVIDENCE_WEIGHTS`,
`LIKELY_S4_BONUS`) and the tier thresholds in `_tier_for_score`. No prompt
changes are needed for weight tuning - only the inputs Claude infers are
prompt-driven.

## Tests

```bash
pytest
```

Covers DB CRUD/filtering, the scoring function across tiers, and validating
sample Claude-shaped responses against the JSON schemas (plus that
`apply_enrichment_result`/`apply_outreach_result` persist correctly).

## Limitations

- Public data only - no paid SAP installed-base feed. Treat `sap_status`,
  `likely_modules`, and `brim_score` as leads to qualify, not confirmed
  facts.
- Web search quality depends on what's actually indexed and findable - a
  company with a quiet public footprint will still come back mostly
  "unknown" rather than hallucinated. Always sanity-check `brim_evidence`
  and `recent_events` links before using them in outreach.
- Each enrichment call runs up to `SAPBUDDY_WEB_SEARCH_MAX_USES` searches,
  billed separately from tokens - budget accordingly for large imports.
- CSV import matches on name+domain for upserts; near-duplicate company
  names (e.g. "Proximus" vs "Proximus NV") will create separate rows.
- Enrichment in the UI runs synchronously, one company at a time - fine for
  MVP-sized batches (tens of companies), not built for large-scale batch
  runs.
