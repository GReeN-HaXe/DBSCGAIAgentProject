from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.db import SQLiteCardRepository
from src.game.effect_rule_extractor import build_effect_rules_for_cards
from src.game.effect_rules import load_effect_rule_overrides_json, merge_effect_rule_overrides, serialize_effect_catalog


CATALOG_PATH = Path("dbdatabase/effect_catalog.json")
OVERRIDES_PATH = Path("dbdatabase/effect_catalog_overrides.json")
DB_PATH = Path("dbdatabase/dbs_masters.db")


def _candidate_card_ids(db_path: Path) -> list[int]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT id FROM cards "
            "WHERE COALESCE(card_skill_unstyled, '') != '' "
            "AND ("
            "COALESCE(has_auto, 0) = 1 "
            "OR COALESCE(has_draw, 0) = 1 "
            "OR LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[auto]%' "
            "OR LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[activate: main]%' "
            "OR LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[activate main]%' "
            "OR LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[activate: battle]%' "
            "OR LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[activate: main/battle]%' "
            "OR LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[activate main/battle]%' "
            "OR LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[counter:%' "
            ") "
            "ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [int(r[0]) for r in rows]


def test_effect_catalog_matches_current_extractor_output() -> None:
    if not DB_PATH.exists():
        pytest.skip(f"db not found: {DB_PATH}")
    if not CATALOG_PATH.exists():
        pytest.skip(f"catalog not found: {CATALOG_PATH}")

    repo = SQLiteCardRepository(DB_PATH)
    card_ids = _candidate_card_ids(DB_PATH)
    rebuilt = build_effect_rules_for_cards(repo, card_ids)
    if OVERRIDES_PATH.exists():
        rebuilt = merge_effect_rule_overrides(rebuilt, load_effect_rule_overrides_json(OVERRIDES_PATH))
    rebuilt_payload = serialize_effect_catalog(rebuilt)
    existing_payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert rebuilt_payload == existing_payload, (
        "effect catalog drift detected; regenerate with "
        "`python scripts/build_effect_catalog.py` and commit the updated JSON."
    )
