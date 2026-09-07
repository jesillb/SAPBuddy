"""SAP BRIM Targeting Tool - main dashboard: import companies, filter, export."""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.database import init_db  # noqa: E402
from db.models import count_companies, list_companies, list_distinct_values, upsert_from_csv_row  # noqa: E402
from enrichment.claude_client import is_configured as claude_configured  # noqa: E402
from enrichment.enrich_company import enrich_company  # noqa: E402

st.set_page_config(page_title="SAP BRIM Targeting Tool", layout="wide")
init_db()

st.title("SAP BRIM Targeting Tool")
st.caption("High-volume subscription & usage billing targets across Benelux. What do I do with this today?")

if not claude_configured():
    st.warning(
        "ANTHROPIC_API_KEY is not set - enrichment will fail until it is exported. "
        "Import and browsing still work.",
        icon="⚠️",
    )

# ---------------------------------------------------------------------------
# Import companies
# ---------------------------------------------------------------------------
with st.expander("Import companies", expanded=True):
    st.markdown(
        "CSV columns: **company_name** (required), `website`/`domain`, `country`, `tags` (comma-separated)."
    )
    uploaded = st.file_uploader("Upload CSV", type=["csv"])

    # Streamlit keeps the uploaded file across reruns (e.g. when the
    # "Enrich all" button below is clicked), so guard against re-importing
    # the same file on every rerun.
    upload_signature = (
        (uploaded.name, uploaded.size, getattr(uploaded, "file_id", None)) if uploaded is not None else None
    )
    if uploaded is not None and st.session_state.get("last_processed_upload") != upload_signature:
        content = uploaded.getvalue().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]

        if "company_name" not in fieldnames:
            st.error("CSV must include a 'company_name' column.")
        else:
            created_ids, updated_count = [], 0
            for raw_row in reader:
                row = {k.strip().lower(): (v or "").strip() for k, v in raw_row.items() if k}
                name = row.get("company_name")
                if not name:
                    continue
                domain = row.get("domain") or row.get("website") or None
                country = row.get("country") or None
                tags_raw = row.get("tags") or ""
                tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

                company_id, created = upsert_from_csv_row(name, domain, country, tags)
                if created:
                    created_ids.append(company_id)
                else:
                    updated_count += 1

            st.session_state["last_processed_upload"] = upload_signature
            st.session_state["last_import_ids"] = created_ids
            st.success(f"Imported: {len(created_ids)} new, {updated_count} updated.")

    pending_ids = st.session_state.get("last_import_ids", [])
    if pending_ids:
        st.write(f"{len(pending_ids)} newly imported companies are not yet enriched.")
        if st.button(f"Enrich all {len(pending_ids)} imported companies", type="primary"):
            if not claude_configured():
                st.error("Set ANTHROPIC_API_KEY before enriching.")
            else:
                progress = st.progress(0.0)
                status = st.empty()
                errors = []
                for i, cid in enumerate(pending_ids, start=1):
                    status.text(f"Enriching company {i}/{len(pending_ids)} (id={cid})...")
                    try:
                        enrich_company(cid)
                    except Exception as exc:  # noqa: BLE001 - surface all enrichment failures to the user
                        errors.append(f"id={cid}: {exc}")
                    progress.progress(i / len(pending_ids))
                status.empty()
                st.session_state["last_import_ids"] = []
                if errors:
                    st.warning("Enrichment finished with errors:\n" + "\n".join(errors))
                else:
                    st.success("Enrichment complete.")
                st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
st.sidebar.header("Filters")

available_countries = list_distinct_values("hq_country")
default_countries = [c for c in available_countries if c in ("NL", "BE", "LU")] or available_countries
countries = st.sidebar.multiselect("Country", options=available_countries, default=default_countries)

available_industries = list_distinct_values("industry")
industries = st.sidebar.multiselect("Industry", options=available_industries, default=[])

tiers = st.sidebar.multiselect("Priority tier", options=["A", "B", "C"], default=["A"])

score_min, score_max = st.sidebar.slider("BRIM score range", 0, 100, (0, 100))

s4_statuses = st.sidebar.multiselect(
    "S/4HANA migration status",
    options=["unknown", "planned", "in_flight", "completed"],
    default=[],
)

einvoicing_pressures = st.sidebar.multiselect(
    "E-invoicing pressure",
    options=["low", "medium", "high"],
    default=[],
)

companies = list_companies(
    countries=countries or None,
    industries=industries or None,
    priority_tiers=tiers or None,
    score_min=score_min,
    score_max=score_max,
    s4_statuses=s4_statuses or None,
    einvoicing_pressures=einvoicing_pressures or None,
)

st.subheader(f"{len(companies)} target accounts")

if not companies:
    st.info("No companies match the current filters. Import a CSV above, or widen the filters.")
else:
    table_rows = [
        {
            "id": c.id,
            "name": c.name,
            "country": c.hq_country,
            "industry": c.industry,
            "brim_score": c.brim_score,
            "priority_tier": c.priority_tier,
            "s4_migration_status": c.s4_migration_status,
            "last_event_date": c.last_event_date,
            "recommended_action": c.recommended_action,
        }
        for c in companies
    ]
    df = pd.DataFrame(table_rows)

    event = st.dataframe(
        df.drop(columns=["id"]),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="dashboard_table",
    )

    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        selected_company = companies[selected_rows[0]]
        if st.button(f"Open dossier -> {selected_company.name}", type="primary"):
            st.session_state["selected_company_id"] = selected_company.id
            st.switch_page("pages/1_Company_Detail.py")

    export_df = pd.DataFrame([
        {**row, **{"id": row["id"]}} for row in table_rows
    ])
    st.download_button(
        "Export filtered list as CSV",
        data=export_df.to_csv(index=False).encode("utf-8"),
        file_name="sapbuddy_targets.csv",
        mime="text/csv",
    )

st.sidebar.divider()
st.sidebar.page_link("pages/2_Weekly_Plan.py", label="Monday planning view", icon="📅")
