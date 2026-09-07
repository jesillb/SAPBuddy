"""Monday-morning planning view: where to focus outreach this week."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.database import init_db  # noqa: E402
from db.models import list_companies, random_companies  # noqa: E402

st.set_page_config(page_title="Weekly plan", layout="wide")
init_db()

st.title("This week's plan")
st.caption("Three lists. Work top to bottom.")
st.page_link("main.py", label="Back to dashboard", icon="⬅️")


def _company_row(c, reason: str):
    cols = st.columns([3, 1, 1, 4, 1])
    cols[0].markdown(f"**{c.name}**")
    cols[1].markdown(f"`{c.priority_tier}`")
    cols[2].markdown(f"{c.brim_score}")
    cols[3].caption(reason)
    if cols[4].button("Open", key=f"open_{reason[:8]}_{c.id}"):
        st.session_state["selected_company_id"] = c.id
        st.switch_page("pages/1_Company_Detail.py")


st.divider()
st.subheader("🆕 Top 20 new Tier A accounts")
new_tier_a = list_companies(priority_tiers=["A"], order_by="created_at DESC, brim_score DESC", limit=20)
if new_tier_a:
    for c in new_tier_a:
        _company_row(c, f"Added {c.created_at[:10] if c.created_at else 'unknown'}")
else:
    st.caption("No Tier A accounts yet - import and enrich some companies first.")

st.divider()
st.subheader("📰 Top 10 accounts with fresh S/4HANA or billing events")
fresh_events = [
    c
    for c in list_companies(order_by="last_event_date DESC, brim_score DESC", limit=200)
    if c.last_event_date
][:10]
if fresh_events:
    for c in fresh_events:
        _company_row(c, f"Event on {c.last_event_date}")
else:
    st.caption("No dated events recorded yet.")

st.divider()
st.subheader("🎲 Random 10 from Tier A for today's outreach")
if st.button("Shuffle"):
    st.session_state.pop("random_tier_a", None)
if "random_tier_a" not in st.session_state:
    st.session_state["random_tier_a"] = random_companies(["A"], 10)
random_tier_a = st.session_state["random_tier_a"]
if random_tier_a:
    for c in random_tier_a:
        _company_row(c, "Pick of the day")
else:
    st.caption("No Tier A accounts yet.")
