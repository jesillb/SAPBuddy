import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point every test at a fresh throwaway SQLite file."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("SAPBUDDY_DB_PATH", str(db_path))
    from db.database import init_db

    init_db()
    yield db_path
