# CLAUDE.md

Guidance for Claude Code (and any future contributor) working in this repo.

## Stack

- Python 3.11+, Streamlit UI (`app/`), SQLite via plain `sqlite3` (`db/`),
  Anthropic Claude API for enrichment (`enrichment/`), deterministic scoring
  in plain Python (`scoring/`), prompts/schemas in `prompts/`.
- No ORM, no JS build step, no background job queue - this is an internal
  MVP dashboard. Keep it that way unless there's a concrete reason to add
  complexity.

## Commands

```bash
pip install -r requirements.txt
streamlit run app/main.py
pytest
```

Required env var for enrichment: `ANTHROPIC_API_KEY`. See README.md for the
full list and what each one does.

## Key conventions

- **No hardcoded secrets.** Read credentials from `os.environ` only. Never
  commit `.streamlit/secrets.toml` or `.env` files (already gitignored).
- **Structured outputs for every Claude call.** Use `output_config: {"format":
  {"type": "json_schema", "schema": ...}}` on `client.messages.create()`
  (see `enrichment/claude_client.py::call_structured`). Don't parse free-text
  JSON out of a plain completion.
- **Prompts and schemas live in `prompts/`,** as Markdown + JSON Schema
  files, not inlined as Python strings buried in logic. When a prompt or
  schema changes, update the corresponding `.md`/`.json` file there (and the
  copies embedded in `enrichment/enrich_company.py` /
  `enrichment/outreach.py`'s docstrings/system prompts, which should stay in
  sync with the schema files - `tests/test_enrichment_parsing.py` asserts
  the schema files match the constants Python actually calls with).
- **Scoring is Python, not Claude.** `scoring/brim_score.py` is the single
  source of truth for `brim_score`/`priority_tier`. Claude only supplies the
  inputs (industry category, employee range, SAP status, evidence flags).
  Tune weights there, not in the prompt.
- **Plan before multi-file changes.** For anything touching more than one
  or two files (e.g. adding a DB column, changing the enrichment schema),
  sketch the plan - which files, in what order - before editing, especially
  since a DB column change touches `db/database.py`, `db/models.py`, the
  enrichment schema/prompt, and the UI simultaneously.
- **Keep JSON-serialized columns in sync.** List/dict-valued DB columns
  (`other_sites`, `sap_signals`, `likely_modules`, `brim_components_likely`,
  `brim_evidence`, `recent_events`, `outreach_angles`, `tags`) are declared
  in `db/models.py::JSON_FIELDS` and (de)serialized automatically by
  `Company.from_row`/`to_row_dict`/`update_company`. Add new list/dict
  columns there, not with ad-hoc `json.dumps` calls elsewhere.
- **Tests for core logic.** DB CRUD, scoring, and schema-validated parsing
  have tests in `tests/`. Add a test alongside any change to scoring
  weights or the enrichment/outreach schemas.
