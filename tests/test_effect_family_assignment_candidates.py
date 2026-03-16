from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from src.game.effect_family_assignment_candidates import build_effect_family_assignment_candidates


_TMP_ROOT = Path("artifacts/test_tmp_effect_family_assignment_candidates")


def _reset_tmp_dir(name: str) -> Path:
    path = _TMP_ROOT / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_build_effect_family_assignment_candidates_finds_high_confidence_counter_matches() -> None:
    mapping_report = {
        "unmapped_priority_cards": [
            {"card_id": 6, "combined_count": 60, "trace_count": 55, "deck_count": 5},
            {"card_id": 4726, "combined_count": 32, "trace_count": 28, "deck_count": 4},
        ]
    }
    tmp_path = _reset_tmp_dir("candidate_core")
    db_path = tmp_path / "cards.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, card_number TEXT, card_name TEXT, card_type TEXT, card_skill_unstyled TEXT)")
        conn.executemany(
            "INSERT INTO cards (id, card_number, card_name, card_type, card_skill_unstyled) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    6,
                    "BT14-019",
                    "Dyspo, Thwarting the Enemy",
                    "BATTLE",
                    "[Counter: Attack] Negate the attack, then play this card in Rest Mode. If you negated a Leader Card's attack with this skill, your opponent can't attack with their Leader Card for the turn.",
                ),
                (
                    4726,
                    "BT5-012",
                    "Master Roshi, Martial Expert",
                    "BATTLE",
                    "[Super Combo][Auto][Sparking 5] When you combo with this card, if your Leader Card is red, draw 1 card.",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    payload = build_effect_family_assignment_candidates(
        mapping_report,
        db_path=db_path,
        known_family_ids={"self_comboed:auto_draw_n"},
        top_n=10,
    )
    assert payload["schema_version"] == "effect_family_assignment_candidates.v1"
    assert payload["summary"]["candidate_count"] == 2
    assert payload["summary"]["auto_apply_safe_count"] == 1
    assert payload["candidates"][0]["card_id"] == 6
    assert payload["candidates"][0]["family_id"] == "counter_attack:counter_negate_attack_play_self_attack_restriction"
    assert payload["candidates"][0]["auto_apply_safe"] is True
    assert payload["candidates"][1]["card_id"] == 4726
    assert payload["candidates"][1]["family_id"] == "self_comboed:auto_draw_n"
    assert payload["candidates"][1]["family_already_in_catalog"] is True
    assert payload["candidates"][1]["auto_apply_safe"] is False


def test_build_effect_family_assignment_candidates_script_writes_json() -> None:
    tmp_path = _reset_tmp_dir("candidate_script")
    db_path = tmp_path / "cards.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, card_number TEXT, card_name TEXT, card_type TEXT, card_skill_unstyled TEXT)")
        conn.execute(
            "INSERT INTO cards (id, card_number, card_name, card_type, card_skill_unstyled) VALUES (?, ?, ?, ?, ?)",
            (
                6,
                "BT14-019",
                "Dyspo, Thwarting the Enemy",
                "BATTLE",
                "[Counter: Attack] Negate the attack, then play this card in Rest Mode.",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    mapping_path = tmp_path / "mapping.json"
    family_path = tmp_path / "family.json"
    output_path = tmp_path / "candidates.json"
    mapping_path.write_text(
        json.dumps({"unmapped_priority_cards": [{"card_id": 6, "combined_count": 10, "trace_count": 9, "deck_count": 1}]}, indent=2),
        encoding="utf-8",
    )
    family_path.write_text(json.dumps({"families": []}, indent=2), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_effect_family_assignment_candidates.py",
            "--mapping-report",
            str(mapping_path),
            "--family-report",
            str(family_path),
            "--db-path",
            str(db_path),
            "--top-n",
            "10",
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["candidate_count"] == 1
    assert payload["candidates"][0]["card_id"] == 6
