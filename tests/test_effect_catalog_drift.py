from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_effect_catalog import _candidate_card_ids as _script_candidate_card_ids
from src.db import SQLiteCardRepository
from src.game.effect_rule_extractor import build_effect_rules_for_cards
from src.game.effect_rules import (
    default_effect_catalog_path,
    load_effect_rule_overrides_json,
    load_effect_rules_json,
    merge_effect_rule_overrides,
    serialize_effect_catalog,
)


CATALOG_PATH = default_effect_catalog_path()
OVERRIDES_PATH = Path("dbdatabase/effect_catalog_overrides.json")
DB_PATH = Path("dbdatabase/dbs_masters.db")


def _candidate_card_ids(db_path: Path) -> list[int]:
    return _script_candidate_card_ids(db_path, limit=None)


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
    existing_payload = serialize_effect_catalog(load_effect_rules_json(CATALOG_PATH))
    assert rebuilt_payload == existing_payload, (
        "effect catalog drift detected; regenerate with "
        "`python scripts/build_effect_catalog.py` and commit the updated JSON."
    )


def test_build_effect_catalog_candidate_query_includes_swap_spirit_boost_super_combo_card() -> None:
    if not DB_PATH.exists():
        pytest.skip(f"db not found: {DB_PATH}")
    assert 433 in _candidate_card_ids(DB_PATH)
