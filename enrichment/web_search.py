"""Web content gathering for enrichment.

If SEARCH_API_KEY and SEARCH_API_ENDPOINT are set, queries a generic search
API (expected to accept `?q=<query>&key=<key>` and return JSON with a
`results: [{title, snippet, url}]` shape - adjust `_call_search_api` to match
your provider). Otherwise falls back to a stub so the app is runnable
without any search API key configured.
"""
from __future__ import annotations

import os

import requests

SEARCH_API_KEY = os.environ.get("SEARCH_API_KEY")
SEARCH_API_ENDPOINT = os.environ.get("SEARCH_API_ENDPOINT")

QUERY_TEMPLATES = [
    '"{name}" SAP',
    '"{name}" "S/4HANA"',
    '"{name}" "SAP BRIM"',
    '"{name}" billing',
    '"{name}" revenue recognition',
]


def search_configured() -> bool:
    return bool(SEARCH_API_KEY and SEARCH_API_ENDPOINT)


def _call_search_api(query: str, timeout: float = 15.0) -> list[dict]:
    resp = requests.get(
        SEARCH_API_ENDPOINT,
        params={"q": query, "key": SEARCH_API_KEY},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("results", [])


def _stub_content(company_name: str, domain: str | None, country: str | None) -> str:
    return (
        f"[No search API configured - SAPBuddy stub content]\n"
        f"Company: {company_name}\n"
        f"Domain: {domain or 'unknown'}\n"
        f"Country: {country or 'unknown'}\n\n"
        "No live web data was retrieved. Set SEARCH_API_KEY and "
        "SEARCH_API_ENDPOINT to enable real search, or paste findings into "
        "the company's notes field and re-run enrichment manually. Base any "
        "inference on general knowledge of this company/industry only where "
        "genuinely confident, otherwise mark fields as unknown."
    )


def gather_web_content(company_name: str, domain: str | None = None, country: str | None = None) -> str:
    """Return a single text blob of raw web content for the enrichment prompt."""
    if not search_configured():
        return _stub_content(company_name, domain, country)

    sections = []
    for template in QUERY_TEMPLATES:
        query = template.format(name=company_name)
        try:
            results = _call_search_api(query)
        except (requests.RequestException, ValueError):
            continue
        if not results:
            continue
        lines = [f"## Query: {query}"]
        for r in results[:5]:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            lines.append(f"- {title}\n  {snippet}\n  {url}")
        sections.append("\n".join(lines))

    if not sections:
        return _stub_content(company_name, domain, country)
    return "\n\n".join(sections)
