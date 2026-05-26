from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from src.db import SQLiteCardRepository
from src.game.effect_support_audit import build_effect_support_audit


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE cards (
                id INTEGER PRIMARY KEY,
                card_number TEXT,
                card_name TEXT,
                card_series TEXT,
                card_rarity TEXT,
                card_type TEXT,
                card_color TEXT,
                energy_cost_int INTEGER,
                combo_cost_int INTEGER,
                combo_power_int INTEGER,
                power_int INTEGER,
                card_energy_cost TEXT,
                card_combo_cost TEXT,
                card_combo_power TEXT,
                card_power TEXT,
                card_skill_unstyled TEXT,
                card_skill_html TEXT,
                card_traits_json TEXT,
                card_character_json TEXT,
                card_era_json TEXT,
                keywords_json TEXT,
                z_energy_cost TEXT,
                is_banned INTEGER,
                is_limited INTEGER,
                limited_to INTEGER,
                card_back_name TEXT,
                card_back_power TEXT,
                card_back_skill_unstyled TEXT,
                card_back_skill_html TEXT,
                card_back_traits_json TEXT,
                card_back_character_json TEXT,
                card_back_era_json TEXT,
                has_counter INTEGER,
                has_counter_attack INTEGER,
                has_counter_play INTEGER,
                has_activate_main INTEGER,
                has_activate_battle INTEGER,
                has_auto INTEGER,
                has_permanent INTEGER,
                ignores_barrier INTEGER,
                grants_triple_strike INTEGER,
                has_draw INTEGER,
                max_draw INTEGER,
                max_power_reduction INTEGER,
                has_barrier INTEGER
            )
            """
        )
        rows = [
            (
                1, "TEST-001", "Leader One", "", "", "LEADER", "Red", 0, 0, 0, 5000, "", "", "", "",
                "[Auto] When this card attacks, draw 1 card.", "", "[]", "[]", "[]", "[]", "", 0, 0, 0, "", "", "", "", "[]", "[]", "[]",
                0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0,
            ),
            (
                2, "TEST-002", "Battle Two", "", "", "BATTLE", "Blue", 2, 0, 5000, 15000, "", "", "", "",
                "[Auto] When this card attacks, draw 1 card.", "", "[]", "[]", "[]", "[]", "", 0, 0, 0, "", "", "", "", "[]", "[]", "[]",
                0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0,
            ),
            (
                3, "TEST-003", "Battle Three", "", "", "BATTLE", "Green", 2, 0, 5000, 15000, "", "", "", "",
                "[Activate: Main] Choose 1 card in your hand and discard it.", "", "[]", "[]", "[]", "[]", "", 0, 0, 0, "", "", "", "", "[]", "[]", "[]",
                0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            ),
            (
                4, "TEST-004", "Skillless Four", "", "", "BATTLE", "Black", 1, 0, 5000, 5000, "", "", "", "",
                "-", "", "[]", "[]", "[]", "[]", "", 0, 0, 0, "", "", "", "", "[]", "[]", "[]",
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            ),
        ]
        conn.executemany(
            "INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def test_build_effect_support_audit_prioritizes_unimplemented_family(tmp_path: Path) -> None:
    db_path = tmp_path / "cards.db"
    _make_db(db_path)
    repo = SQLiteCardRepository(db_path)

    payload = build_effect_support_audit(repo, [1, 2, 3], priority_card_ids=[3], top_families=5)

    assert payload["schema_version"] == "effect_support_audit.v1"
    assert payload["summary"]["priority_card_count"] == 1
    assert payload["summary"]["priority_cards_without_rules"] == 1
    assert payload["summary"]["priority_intentionally_skipped_cards"] == 0
    assert payload["top_global_families"][0]["card_count"] >= 1
    assert payload["top_priority_families"][0]["priority_card_count"] == 1
    assert payload["priority_unimplemented_cards"][0]["card_id"] == 3


def test_build_effect_support_audit_tracks_unresolved_example_and_enriches_unmatched_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "cards.db"
    _make_db(db_path)
    repo = SQLiteCardRepository(db_path)

    payload = build_effect_support_audit(repo, [1, 2, 3], priority_card_ids=[3], top_families=5)

    unresolved_family = next(row for row in payload["families"] if row["example_card_id"] == 3)
    assert unresolved_family["unresolved_example_card_id"] == 3
    assert unresolved_family["unresolved_example_card_number"] == "TEST-003"
    assert unresolved_family["unresolved_example_card_name"] == "Battle Three"

    unmatched = next(row for row in payload["extractor_report"]["unmatched_top_templates"] if row["example_card_id"] == 3)
    assert unmatched["example_card_number"] == "TEST-003"
    assert unmatched["example_card_name"] == "Battle Three"


def test_build_effect_support_audit_separates_skillless_skips_from_priority_unimplemented(tmp_path: Path) -> None:
    db_path = tmp_path / "cards.db"
    _make_db(db_path)
    repo = SQLiteCardRepository(db_path)

    payload = build_effect_support_audit(repo, [1, 2, 3, 4], priority_card_ids=[3, 4], top_families=5)

    assert payload["summary"]["priority_card_count"] == 2
    assert payload["summary"]["priority_cards_without_rules"] == 1
    assert payload["summary"]["priority_intentionally_skipped_cards"] == 1
    assert payload["coverage"]["priority"]["cards_without_rules"] == 1
    assert payload["coverage"]["priority"]["intentionally_skipped_cards"] == 1
    assert [row["card_id"] for row in payload["priority_unimplemented_cards"]] == [3]
    assert [row["card_id"] for row in payload["intentionally_skipped_priority_cards"]] == [4]


def test_run_effect_support_audit_script_collects_decks_and_traces(tmp_path: Path) -> None:
    db_path = tmp_path / "cards.db"
    _make_db(db_path)
    deck_path = tmp_path / "deck.txt"
    trace_path = tmp_path / "trace.json"
    output_path = tmp_path / "audit.json"

    deck_path.write_text(
        "Leader One [TEST-001]\nMain Deck:\n4 Battle Three [TEST-003]\n",
        encoding="utf-8",
    )
    trace_path.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "action": "declare_attack attacker_card=card_id=2 target_card=card_id=1",
                        "hand_card_id": 3,
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_effect_support_audit.py",
            "--db-path",
            str(db_path),
            "--deckplanet-glob",
            str(deck_path),
            "--trace-glob",
            str(trace_path),
            "--output",
            str(output_path),
            "--top-families",
            "5",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["priority_sources"]["deckplanet"]["deck_file_count"] == 1
    assert payload["priority_sources"]["traces"]["trace_file_count"] == 1
    assert payload["summary"]["priority_card_count"] >= 3
    assert any(row["card_id"] == 3 for row in payload["priority_unimplemented_cards"])
