"""Company model and CRUD helpers for the SAP BRIM Targeting Tool."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from db.database import connection_scope

JSON_FIELDS = {
    "other_sites",
    "sap_signals",
    "likely_modules",
    "brim_components_likely",
    "brim_evidence",
    "recent_events",
    "outreach_angles",
    "tags",
}

VALID_SAP_STATUS = {"unknown", "likely_sap", "confirmed_sap", "s4hana", "ecc"}
VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_S4_STATUS = {"unknown", "planned", "in_flight", "completed"}
VALID_PRESSURE = {"low", "medium", "high"}
VALID_TIER = {"A", "B", "C"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Company:
    id: Optional[int] = None
    name: str = ""
    domain: Optional[str] = None
    hq_country: Optional[str] = None
    hq_city: Optional[str] = None
    other_sites: list = field(default_factory=list)
    industry: Optional[str] = None
    employee_range: Optional[str] = None
    revenue_range_eur: Optional[str] = None
    sap_status: str = "unknown"
    sap_signals: list = field(default_factory=list)
    likely_modules: list = field(default_factory=list)
    module_confidence: Optional[str] = None
    brim_score: int = 0
    brim_score_reason: Optional[str] = None
    brim_components_likely: list = field(default_factory=list)
    brim_evidence: list = field(default_factory=list)
    recent_events: list = field(default_factory=list)
    last_event_date: Optional[str] = None
    s4_migration_status: str = "unknown"
    einvoicing_pressure: str = "low"
    priority_tier: str = "C"
    recommended_action: Optional[str] = None
    outreach_angles: list = field(default_factory=list)
    last_contacted_at: Optional[str] = None
    notes: Optional[str] = None
    tags: list = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Company":
        data = dict(row)
        for key in JSON_FIELDS:
            raw = data.get(key)
            data[key] = json.loads(raw) if raw else []
        return cls(**{f.name: data.get(f.name) for f in fields(cls)})

    def to_row_dict(self) -> dict:
        data = {}
        for f in fields(self):
            if f.name == "id":
                continue
            value = getattr(self, f.name)
            if f.name in JSON_FIELDS:
                value = json.dumps(value if value is not None else [])
            data[f.name] = value
        return data


COLUMNS = [f.name for f in fields(Company) if f.name != "id"]


def create_company(company: Company) -> int:
    now = _now()
    company.created_at = company.created_at or now
    company.updated_at = now
    if company.sap_status not in VALID_SAP_STATUS:
        company.sap_status = "unknown"
    if company.s4_migration_status not in VALID_S4_STATUS:
        company.s4_migration_status = "unknown"
    if company.einvoicing_pressure not in VALID_PRESSURE:
        company.einvoicing_pressure = "low"
    if company.priority_tier not in VALID_TIER:
        company.priority_tier = "C"

    data = company.to_row_dict()
    cols = ", ".join(COLUMNS)
    placeholders = ", ".join(f":{c}" for c in COLUMNS)
    with connection_scope() as conn:
        cur = conn.execute(
            f"INSERT INTO companies ({cols}) VALUES ({placeholders})", data
        )
        return cur.lastrowid


def get_company(company_id: int) -> Optional[Company]:
    with connection_scope() as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE id = ?", (company_id,)
        ).fetchone()
        return Company.from_row(row) if row else None


def get_company_by_name_domain(name: str, domain: Optional[str]) -> Optional[Company]:
    with connection_scope() as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE name = ? AND COALESCE(domain, '') = ?",
            (name, domain or ""),
        ).fetchone()
        return Company.from_row(row) if row else None


def update_company(company_id: int, **field_updates: Any) -> None:
    if not field_updates:
        return
    field_updates["updated_at"] = _now()
    set_clauses = []
    params: dict[str, Any] = {}
    for key, value in field_updates.items():
        if key in JSON_FIELDS and not isinstance(value, str):
            value = json.dumps(value if value is not None else [])
        set_clauses.append(f"{key} = :{key}")
        params[key] = value
    params["id"] = company_id
    sql = f"UPDATE companies SET {', '.join(set_clauses)} WHERE id = :id"
    with connection_scope() as conn:
        conn.execute(sql, params)


def upsert_from_csv_row(
    name: str,
    domain: Optional[str] = None,
    country: Optional[str] = None,
    tags: Optional[list] = None,
) -> tuple[int, bool]:
    """Create or update a company from a CSV import row.

    Returns (company_id, created) where created is False if an existing
    record (matched on name+domain) was updated instead.
    """
    existing = get_company_by_name_domain(name, domain)
    if existing:
        updates: dict[str, Any] = {}
        if country and not existing.hq_country:
            updates["hq_country"] = country
        if tags:
            merged = sorted(set(existing.tags) | set(tags))
            updates["tags"] = merged
        if updates:
            update_company(existing.id, **updates)
        return existing.id, False

    company = Company(
        name=name,
        domain=domain,
        hq_country=country,
        tags=tags or [],
    )
    return create_company(company), True


def list_companies(
    countries: Optional[Iterable[str]] = None,
    industries: Optional[Iterable[str]] = None,
    priority_tiers: Optional[Iterable[str]] = None,
    score_min: Optional[int] = None,
    score_max: Optional[int] = None,
    s4_statuses: Optional[Iterable[str]] = None,
    einvoicing_pressures: Optional[Iterable[str]] = None,
    order_by: str = "brim_score DESC, updated_at DESC",
    limit: Optional[int] = None,
) -> list[Company]:
    clauses = []
    params: list[Any] = []

    def _in_clause(column: str, values: Optional[Iterable[str]]):
        values = list(values) if values else []
        if values:
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{column} IN ({placeholders})")
            params.extend(values)

    _in_clause("hq_country", countries)
    _in_clause("industry", industries)
    _in_clause("priority_tier", priority_tiers)
    _in_clause("s4_migration_status", s4_statuses)
    _in_clause("einvoicing_pressure", einvoicing_pressures)

    if score_min is not None:
        clauses.append("brim_score >= ?")
        params.append(score_min)
    if score_max is not None:
        clauses.append("brim_score <= ?")
        params.append(score_max)

    sql = "SELECT * FROM companies"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    with connection_scope() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [Company.from_row(r) for r in rows]


def random_companies(priority_tiers: Iterable[str], limit: int) -> list[Company]:
    tiers = list(priority_tiers)
    placeholders = ", ".join("?" for _ in tiers)
    sql = f"SELECT * FROM companies WHERE priority_tier IN ({placeholders}) ORDER BY RANDOM() LIMIT ?"
    with connection_scope() as conn:
        rows = conn.execute(sql, [*tiers, limit]).fetchall()
        return [Company.from_row(r) for r in rows]


def list_distinct_values(column: str) -> list[str]:
    assert column in {"hq_country", "industry", "s4_migration_status", "einvoicing_pressure", "priority_tier"}
    with connection_scope() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT {column} FROM companies WHERE {column} IS NOT NULL AND {column} != '' ORDER BY {column}"
        ).fetchall()
        return [r[0] for r in rows]


def count_companies() -> int:
    with connection_scope() as conn:
        return conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
