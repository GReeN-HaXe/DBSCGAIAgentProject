from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db import SQLiteCardRepository


def pytest_configure(config: pytest.Config) -> None:
    if config.option.basetemp:
        return
    local_root = ROOT / ".pytest_tmp"
    local_root.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = local_root / f"run_{os.getpid()}"


@pytest.fixture(scope="session")
def db_path() -> Path:
    path = ROOT / "dbdatabase" / "dbs_masters.db"
    if not path.exists():
        pytest.skip(f"DB not found: {path}")
    return path


@pytest.fixture(scope="session")
def repo(db_path: Path) -> SQLiteCardRepository:
    return SQLiteCardRepository(db_path)


@pytest.fixture(scope="session")
def conn(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()
