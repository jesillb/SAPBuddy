"""Company detail / dossier page."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.database import init_db  # noqa: E402
from db.models import get_company, update_company  # noqa: E402
from enrichment.claude_client import ClaudeNotConfiguredError, is_configured as claude_configured  # noqa: E402
from enrichment.enrich_company import enrich_company  # noqa: E402
from enrichment.outreach import regenerate_outreach  # noqa: E402

st.set_page_config(page_title="Company dossier", layout="wide")
init_db()

# Prefer session_state (set by in-app navigation buttons - reliable across
# st.switch_page, unlike query params set on the same rerun as the switch).
# Fall back to the URL query param so a dossier link can be bookmarked/shared.
company_id_raw = st.session_state.get("selected_company_id") or st.query_params.get("company_id")
if not company_id_raw:
    st.info("No company selected. Go back to the dashboard and open a dossier from the table.")
    st.page_link("main.py", label="Back to dashboard", icon="⬅️")
    st.stop()

company = get_company(int(company_id_raw))
if company is None:
    st.error(f"No company found with id={company_id_raw}")
    st.page_link("main.py", label="Back to dashboard", icon="⬅️")
    st.stop()

st.session_state["selected_company_id"] = company.id
st.query_params["company_id"] = str(company.id)

st.page_link("main.py", label="Back to dashboard", icon="⬅️")

tier_color = {"A": "🟢", "B": "🟡", "C": "⚪"}.get(company.priority_tier, "⚪")
st.title(f"{tier_color} {company.name}")
st.caption(f"{company.hq_city or 'Unknown city'}, {company.hq_country or 'Unknown country'}")

col_actions = st.columns([1, 1, 3])
with col_actions[0]:
    if st.button("Re-run enrichment"):
        if not claude_configured():
            st.error("Set ANTHROPIC_API_KEY before enriching.")
        else:
            with st.spinner("Calling Claude..."):
                try:
                    enrich_company(company.id)
                    st.success("Enrichment updated.")
                    st.rerun()
                except ClaudeNotConfiguredError as exc:
                    st.error(str(exc))
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Enrichment failed: {exc}")

st.divider()

# ---------------------------------------------------------------------------
# Firmographics
# ---------------------------------------------------------------------------
st.subheader("Firmographics")
f1, f2, f3, f4 = st.columns(4)
f1.metric("Industry", company.industry or "Unknown")
f2.metric("Employees", company.employee_range or "Unknown")
f3.metric("Revenue (EUR)", company.revenue_range_eur or "Unknown")
f4.metric("Domain", company.domain or "Unknown")

if company.other_sites:
    st.markdown("**Other sites**")
    for site in company.other_sites:
        st.markdown(f"- {site.get('city', '?')}, {site.get('country', '?')} ({site.get('type', '?')})")

st.divider()

# ---------------------------------------------------------------------------
# SAP footprint
# ---------------------------------------------------------------------------
st.subheader("SAP footprint")
sap_col1, sap_col2 = st.columns(2)
sap_col1.markdown(f"**Status:** `{company.sap_status}`")
sap_col1.markdown(f"**Module confidence:** `{company.module_confidence or 'unknown'}`")
sap_col2.markdown(f"**S/4HANA migration:** `{company.s4_migration_status}`")
sap_col2.markdown(f"**E-invoicing pressure:** `{company.einvoicing_pressure}`")

if company.likely_modules:
    st.markdown("**Likely modules:** " + " ".join(f"`{m}`" for m in company.likely_modules))

if company.sap_signals:
    st.markdown("**Signals**")
    for signal in company.sap_signals:
        st.markdown(f"- {signal}")
else:
    st.caption("No SAP signals recorded yet. Run enrichment to populate this.")

st.divider()

# ---------------------------------------------------------------------------
# BRIM fit
# ---------------------------------------------------------------------------
st.subheader("BRIM fit")
score_col, tag_col = st.columns([1, 2])
with score_col:
    st.metric("BRIM score", f"{company.brim_score}/100", delta=f"Tier {company.priority_tier}")
    st.progress(min(max(company.brim_score, 0), 100) / 100)
with tag_col:
    if company.brim_components_likely:
        st.markdown("**Likely components:** " + " ".join(f"`{c}`" for c in company.brim_components_likely))
    if company.brim_score_reason:
        st.markdown("**Why this score**")
        for line in company.brim_score_reason.split("\n"):
            if line.strip():
                st.markdown(f"- {line.strip()}")

if company.brim_evidence:
    st.markdown("**Evidence**")
    for item in company.brim_evidence:
        st.markdown(f"- {item}")

st.divider()

# ---------------------------------------------------------------------------
# Recent events
# ---------------------------------------------------------------------------
st.subheader("Recent events")
if company.recent_events:
    for event in company.recent_events[:5]:
        with st.container(border=True):
            st.markdown(f"**{event.get('title', 'Untitled')}** &nbsp;·&nbsp; {event.get('date', 'undated')}")
            st.caption(f"{event.get('source', '')} {event.get('url', '')}".strip())
            st.write(event.get("summary", ""))
            if event.get("themes"):
                st.caption(", ".join(event["themes"]))
else:
    st.caption("No recent events recorded yet.")

st.divider()

# ---------------------------------------------------------------------------
# Outreach
# ---------------------------------------------------------------------------
st.subheader("Outreach")
st.markdown(f"**Recommended action:** {company.recommended_action or 'Run enrichment to generate a recommendation.'}")

if st.button("Regenerate outreach angles"):
    if not claude_configured():
        st.error("Set ANTHROPIC_API_KEY before generating outreach copy.")
    else:
        with st.spinner("Calling Claude..."):
            try:
                regenerate_outreach(company.id)
                st.success("Outreach copy regenerated.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Outreach generation failed: {exc}")

if company.outreach_angles:
    for block in company.outreach_angles:
        st.code(block, language=None)
else:
    st.caption("No outreach copy yet. Run enrichment or click 'Regenerate outreach angles'.")

st.divider()

# ---------------------------------------------------------------------------
# Notes / contact tracking
# ---------------------------------------------------------------------------
st.subheader("Notes")
notes = st.text_area("Notes", value=company.notes or "", label_visibility="collapsed", height=100)
if st.button("Save notes"):
    update_company(company.id, notes=notes)
    st.success("Saved.")
