from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from src.game.effect_family_mapping import (
    build_effect_family_mapping_report,
    collect_trace_card_counts,
)
from src.game.effect_rules import EffectRule, save_effect_rules_json


_TMP_ROOT = Path("artifacts/test_tmp_effect_family_mapping")


def _reset_tmp_dir(name: str) -> Path:
    path = _TMP_ROOT / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_build_effect_family_mapping_report_ranks_priority_cards_and_unmapped() -> None:
    rules = {
        101: (
            EffectRule(
                trigger="self_played",
                handler_id="auto_draw_n",
                handler_params={"amount": 1},
                family_id="self_played:auto_draw_n",
                provenance="extractor",
            ),
        ),
        202: (
            EffectRule(
                trigger="owner_leader_attacks",
                handler_id="auto_draw_n",
                handler_params={"amount": 1},
                family_id="owner_leader_attacks:auto_draw_n",
                provenance="manual_override",
            ),
        ),
    }
    payload = build_effect_family_mapping_report(
        rules,
        card_metadata={
            101: {"card_number": "BT1-001", "card_name": "Mapped Battle", "card_skill_unstyled": "[Auto] Draw 1."},
            202: {"card_number": "BT1-002", "card_name": "Mapped Leader", "card_skill_unstyled": "[Auto] Draw 1."},
            303: {"card_number": "BT1-003", "card_name": "Unmapped Trace Card", "card_skill_unstyled": "[Activate: Main] Test."},
        },
        deck_card_counts={101: 4, 202: 1},
        trace_card_counts={101: 2, 202: 1, 303: 3},
    )

    assert payload["schema_version"] == "effect_family_mapping_report.v1"
    assert payload["summary"]["priority_card_count"] == 3
    assert payload["summary"]["mapped_priority_card_count"] == 2
    assert payload["summary"]["unmapped_priority_card_count"] == 1
    assert payload["summary"]["intentionally_skipped_priority_card_count"] == 0
    assert payload["priority_cards"][0]["card_id"] == 101
    assert payload["priority_cards"][0]["combined_count"] == 6
    assert payload["priority_cards"][0]["family_ids"] == ["self_played:auto_draw_n"]
    assert payload["priority_cards"][1]["card_id"] == 303
    assert payload["priority_cards"][1]["mapped"] is False
    assert payload["unmapped_priority_cards"][0]["card_id"] == 303
    assert payload["top_priority_families"][0]["family_id"] == "self_played:auto_draw_n"
    assert payload["top_priority_families"][0]["combined_count"] == 6


def test_build_effect_family_mapping_report_separates_skillless_skips_from_unmapped() -> None:
    payload = build_effect_family_mapping_report(
        {},
        card_metadata={
            303: {"card_number": "BT1-003", "card_name": "Actionable Unmapped", "card_skill_unstyled": "[Activate: Main] Test."},
            404: {"card_number": "BT1-004", "card_name": "Skillless Skip", "card_skill_unstyled": "-"},
        },
        deck_card_counts={404: 2},
        trace_card_counts={303: 3},
    )

    assert payload["summary"]["priority_card_count"] == 2
    assert payload["summary"]["mapped_priority_card_count"] == 0
    assert payload["summary"]["raw_unmapped_priority_card_count"] == 2
    assert payload["summary"]["unmapped_priority_card_count"] == 1
    assert payload["summary"]["intentionally_skipped_priority_card_count"] == 1
    assert payload["unmapped_priority_cards"][0]["card_id"] == 303
    assert payload["intentionally_skipped_priority_cards"][0]["card_id"] == 404
    assert payload["priority_cards"][0]["intentionally_skipped"] is False
    assert any(row["card_id"] == 404 and row["intentionally_skipped"] is True for row in payload["priority_cards"])


def test_collect_trace_card_counts_handles_human_and_ai_trace_shapes() -> None:
    tmp_path = _reset_tmp_dir("trace_shapes")
    human_trace = tmp_path / "human_trace.json"
    ai_trace = tmp_path / "ai_trace.json"
    summary = tmp_path / "summary.json"

    human_trace.write_text(
        json.dumps(
            {
                "trace": {
                    "setup": {"p1_leader_id": 202, "p2_leader_id": 303},
                    "actions": [
                        {
                            "action": "play_card_from_hand hand_index=0 card=card_id=101",
                            "hand_card_id": 101,
                            "source_card_id": None,
                            "attacker_card_id": None,
                            "target_card_id": None,
                        }
                    ],
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ai_trace.write_text(
        json.dumps(
            {
                "setup": {"p1_leader_id": 202},
                "decision_trace": [
                    {
                        "chosen_action_text": "declare_attack attacker_card=card_id=101 target_card=card_id=303",
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    summary.write_text(json.dumps({"summary": True}, indent=2), encoding="utf-8")

    counts, included = collect_trace_card_counts([human_trace, ai_trace, summary])
    assert counts[101] == 3
    assert counts[202] == 2
    assert counts[303] == 2
    assert str(summary).replace("/", "\\") not in included


def test_build_effect_family_mapping_report_script_writes_json() -> None:
    tmp_path = _reset_tmp_dir("script")
    db_path = tmp_path / "cards.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, card_number TEXT, card_name TEXT, card_type TEXT, card_skill_unstyled TEXT)")
        conn.executemany(
            "INSERT INTO cards (id, card_number, card_name, card_type, card_skill_unstyled) VALUES (?, ?, ?, ?, ?)",
            [
                (101, "BT1-001", "Mapped Battle", "BATTLE", "[Auto] Draw 1."),
                (202, "BT1-002", "Mapped Leader", "LEADER", "[Auto] Draw 1."),
                (303, "BT1-003", "Unmapped Trace Card", "BATTLE", "[Activate: Main] Test."),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    catalog_path = tmp_path / "effect_catalog.json"
    save_effect_rules_json(
        catalog_path,
        {
            101: (
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_draw_n",
                    handler_params={"amount": 1},
                    family_id="self_played:auto_draw_n",
                    provenance="extractor",
                ),
            )
        },
    )

    deck_dir = tmp_path / "decks"
    deck_dir.mkdir(parents=True, exist_ok=True)
    (deck_dir / "sample_deck.txt").write_text(
        "\n".join(
            [
                "Leader",
                "Mapped Leader [BT1-002]",
                "Deck",
                "4 Mapped Battle [BT1-001]",
                "1 Unmapped Trace Card [BT1-003]",
            ]
        ),
        encoding="utf-8",
    )

    trace_dir = tmp_path / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    (trace_dir / "sample_trace.json").write_text(
        json.dumps(
            {
                "trace": {
                    "setup": {"p1_leader_id": 202},
                    "actions": [
                        {
                            "action": "declare_attack attacker_card=card_id=101 target_card=card_id=303",
                            "hand_card_id": None,
                            "source_card_id": None,
                            "attacker_card_id": 101,
                            "target_card_id": 303,
                        }
                    ],
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "effect_family_mapping_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_effect_family_mapping_report.py",
            "--catalog",
            str(catalog_path),
            "--db-path",
            str(db_path),
            "--deckplanet-glob",
            str(deck_dir / "*.txt"),
            "--trace-glob",
            str(trace_dir / "*.json"),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["priority_card_count"] == 3
    assert payload["summary"]["mapped_priority_card_count"] == 1
    assert payload["summary"]["unmapped_priority_card_count"] == 2
    assert payload["summary"]["intentionally_skipped_priority_card_count"] == 0
    assert payload["priority_cards"][0]["card_id"] == 101
