from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.game.effect_family_shortlist import build_effect_family_shortlist


def test_build_effect_family_shortlist_ranks_priority_missing_first() -> None:
    audit = {
        "top_priority_families": [
            {
                "template": "priority missing",
                "card_count": 8,
                "implemented_card_count": 1,
                "priority_card_count": 3,
                "priority_implemented_card_count": 0,
                "example_card_id": 1,
                "example_card_number": "BT1-001",
                "example_card_name": "Priority Missing",
                "handler_counts": {"x": 1},
                "trigger_counts": {"self_played": 1},
                "diagnostic_counts": {},
            },
            {
                "template": "implemented family",
                "card_count": 5,
                "implemented_card_count": 5,
                "priority_card_count": 2,
                "priority_implemented_card_count": 2,
                "example_card_id": 2,
                "example_card_number": "BT1-002",
                "example_card_name": "Done",
                "handler_counts": {"y": 2},
                "trigger_counts": {"self_played": 2},
                "diagnostic_counts": {},
            },
        ],
        "extractor_report": {
            "unmatched_top_templates": [
                {
                    "template": "global unmatched",
                    "count": 9,
                    "example_card_id": 3,
                }
            ]
        },
    }
    payload = build_effect_family_shortlist(audit, top_n=5)
    assert payload["schema_version"] == "effect_family_shortlist.v1"
    assert payload["shortlist"][0]["template"] == "priority missing"
    assert payload["shortlist"][0]["recommended_action"] == "extend_existing_family"
    assert all(row["template"] != "implemented family" for row in payload["shortlist"])


def test_build_effect_family_shortlist_script_writes_json(tmp_path: Path) -> None:
    audit = {
        "top_priority_families": [
            {
                "template": "priority missing",
                "card_count": 4,
                "implemented_card_count": 0,
                "priority_card_count": 1,
                "priority_implemented_card_count": 0,
                "example_card_id": 1,
                "example_card_number": "BT1-001",
                "example_card_name": "Priority Missing",
                "handler_counts": {},
                "trigger_counts": {},
                "diagnostic_counts": {},
            }
        ],
        "extractor_report": {"unmatched_top_templates": []},
    }
    input_path = tmp_path / "audit.json"
    output_path = tmp_path / "shortlist.json"
    input_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_effect_family_shortlist.py",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--top-n",
            "10",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["shortlist_count"] == 1
    assert payload["shortlist"][0]["template"] == "priority missing"


def test_build_effect_family_shortlist_merges_stats_for_truncated_unmatched_template() -> None:
    audit = {
        "families": [
            {
                "template": "long implemented family text with extra suffix",
                "card_count": 2,
                "implemented_card_count": 2,
                "priority_card_count": 0,
                "priority_implemented_card_count": 0,
                "example_card_id": 7,
                "example_card_number": "DB3-071",
                "example_card_name": "Implemented",
                "handler_counts": {"z": 2},
                "trigger_counts": {"self_left_battle_area": 2},
                "diagnostic_counts": {},
            }
        ],
        "top_priority_families": [],
        "extractor_report": {
            "unmatched_top_templates": [
                {
                    "template": "long implemented family text...",
                    "count": 2,
                    "example_card_id": 7,
                }
            ]
        },
    }
    payload = build_effect_family_shortlist(audit, top_n=5)
    row = payload["shortlist"][0]
    assert row["implemented_card_count"] == 2
    assert row["recommended_action"] == "extend_existing_family"
    assert row["handler_counts"] == {"z": 2}


def test_build_effect_family_shortlist_excludes_fully_implemented_non_priority_family() -> None:
    audit = {
        "families": [
            {
                "template": "implemented counter family",
                "card_count": 1,
                "implemented_card_count": 1,
                "priority_card_count": 0,
                "priority_implemented_card_count": 0,
                "example_card_id": 203,
                "example_card_number": "BT15-080",
                "example_card_name": "Yajirobe, Confronting Invasion",
                "handler_counts": {"counter_play_self_rest_then_ko_attacking_battle_if_trait_and_opponent_draw_n": 1},
                "trigger_counts": {"counter_attack": 1},
                "diagnostic_counts": {},
            }
        ],
        "top_priority_families": [],
        "extractor_report": {
            "unmatched_top_templates": [
                {
                    "template": "real unmatched family",
                    "count": 1,
                    "example_card_id": 361,
                }
            ]
        },
    }
    payload = build_effect_family_shortlist(audit, top_n=5)
    templates = [row["template"] for row in payload["shortlist"]]
    assert "implemented counter family" not in templates
    assert templates == ["real unmatched family"]
