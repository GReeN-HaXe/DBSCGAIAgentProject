from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_trace(path: Path, action_types: list[str]) -> None:
    payload = {
        "trace": {
            "actions": [
                {
                    "example_index": index,
                    "action_type": action_type,
                    "action_family": "combat" if "attack" in action_type else "progression",
                    "phase": "main",
                    "actor_kind": "ai",
                    "player_id": 1,
                    "state_snapshot": {
                        "active_player": 1,
                        "battle_step": "",
                        "counter_window_kind": "",
                        "players": {
                            "1": {
                                "hand_size": 5,
                                "life_size": 8,
                                "energy_size": 2,
                                "energy_resting_count": 0,
                                "battle_size": 1,
                                "unison_size": 0,
                                "drop_size": 0,
                                "warp_size": 0,
                            },
                            "2": {
                                "hand_size": 5,
                                "life_size": 8,
                                "energy_size": 2,
                                "battle_size": 0,
                                "unison_size": 0,
                                "drop_size": 0,
                                "warp_size": 0,
                            },
                        },
                    },
                }
                for index, action_type in enumerate(action_types)
            ]
        }
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_phase22_benchmark_dataset_script(tmp_path: Path) -> None:
    good_trace = tmp_path / "good_trace.json"
    bad_trace = tmp_path / "bad_trace.json"
    output_path = tmp_path / "dataset.json"
    summary_path = tmp_path / "summary.json"
    _write_trace(good_trace, ["charge_from_hand", "play_card_from_hand", "declare_attack"])
    _write_trace(bad_trace, ["end_charge"])
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_phase22_benchmark_dataset.py",
            "--input",
            str(good_trace),
            str(bad_trace),
            "--output",
            str(output_path),
            "--summary-output",
            str(summary_path),
            "--min-actions",
            "2",
            "--min-unique-action-types",
            "2",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    dataset = json.loads(output_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert dataset["example_count"] == 3
    assert summary["included_count"] == 1
    assert summary["skipped_count"] == 1
    assert dataset["secret_auto_summary"]["total_opportunity_count"] == 0


def test_build_phase22_benchmark_dataset_accepts_review_traces(tmp_path: Path) -> None:
    review_trace = tmp_path / "review_trace.json"
    output_path = tmp_path / "dataset_review.json"
    summary_path = tmp_path / "summary_review.json"
    payload = {
        "schema_version": "ai_match_review_trace.v1",
        "winner_id": 2,
        "turn_number": 5,
        "phase": "main",
        "stop_reason": "winner_decided",
        "total_actions": 12,
        "decision_trace": [
            {
                "step_index": 1,
                "actor_player_id": 1,
                "turn_number": 1,
                "phase": "charge",
                "chosen_action_type": "charge_from_hand",
                "chosen_action_text": "charge_from_hand hand_index=0",
                "state_snapshot": {
                    "active_player": 1,
                    "battle_step": "",
                    "counter_window_kind": "",
                    "players": {
                        "1": {"hand_size": 6, "life_size": 8, "energy_size": 0, "energy_resting_count": 0, "battle_size": 0, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                        "2": {"hand_size": 6, "life_size": 8, "energy_size": 0, "battle_size": 0, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                    },
                },
            },
            {
                "step_index": 2,
                "actor_player_id": 1,
                "turn_number": 1,
                "phase": "main",
                "chosen_action_type": "play_card_from_hand",
                "chosen_action_text": "play_card_from_hand hand_index=0",
                "state_snapshot": {
                    "active_player": 1,
                    "battle_step": "",
                    "counter_window_kind": "",
                    "players": {
                        "1": {"hand_size": 5, "life_size": 8, "energy_size": 1, "energy_resting_count": 0, "battle_size": 0, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                        "2": {"hand_size": 6, "life_size": 8, "energy_size": 0, "battle_size": 0, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                    },
                },
            },
        ],
    }
    review_trace.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_phase22_benchmark_dataset.py",
            "--input",
            str(review_trace),
            "--output",
            str(output_path),
            "--summary-output",
            str(summary_path),
            "--min-actions",
            "2",
            "--min-unique-action-types",
            "2",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    dataset = json.loads(output_path.read_text(encoding="utf-8"))
    assert dataset["example_count"] == 2
    assert dataset["examples"][0]["action_signature"].startswith("charge_from_hand")


def test_build_phase22_benchmark_dataset_summary_includes_secret_auto_counts(tmp_path: Path) -> None:
    review_trace = tmp_path / "review_secret.json"
    output_path = tmp_path / "dataset_secret.json"
    summary_path = tmp_path / "summary_secret.json"
    payload = {
        "schema_version": "human_match_review_trace.v1",
        "decision_trace": [
            {
                "step_index": 1,
                "actor_player_id": 1,
                "turn_number": 1,
                "phase": "charge",
                "chosen_action_type": "charge_from_hand",
                "chosen_action_text": "charge_from_hand hand_index=0",
                "state_snapshot": {"players": {}},
            },
            {
                "step_index": 2,
                "actor_player_id": 1,
                "turn_number": 1,
                "phase": "main",
                "chosen_action_type": "play_card_from_hand",
                "chosen_action_text": "play_card_from_hand hand_index=0",
                "state_snapshot": {"players": {}},
            },
        ],
        "final_state_snapshot": {
            "secret_auto_summary": {
                "opportunity_count": 2,
                "pending_count": 0,
                "blocked_count": 2,
                "preblocked_count": 1,
                "status_counts": {
                    "blocked_limit_per_turn": 1,
                    "blocked_once_per_turn": 1,
                },
            }
        },
    }
    review_trace.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_phase22_benchmark_dataset.py",
            "--input",
            str(review_trace),
            "--output",
            str(output_path),
            "--summary-output",
            str(summary_path),
            "--min-actions",
            "2",
            "--min-unique-action-types",
            "2",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    dataset = json.loads(output_path.read_text(encoding="utf-8"))
    assert dataset["secret_auto_summary"]["total_opportunity_count"] == 2
    assert dataset["secret_auto_summary"]["total_preblocked_count"] == 1
    assert summary["secret_auto_summary"]["trace_count_with_secret_auto_opportunities"] == 1
    assert summary["secret_auto_summary"]["total_opportunity_count"] == 2
    assert summary["secret_auto_summary"]["total_preblocked_count"] == 1
    assert summary["secret_auto_summary"]["status_counts"]["blocked_limit_per_turn"] == 1


def test_run_ai_match_batch_script_writes_seeded_outputs(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    normalized_dir = tmp_path / "normalized"
    summary_path = tmp_path / "batch_summary.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_ai_match_batch.py",
            "--count",
            "2",
            "--start-index",
            "7",
            "--digits",
            "3",
            "--output-dir",
            str(raw_dir),
            "--summary-output",
            str(summary_path),
            "--normalize",
            "--normalized-output-dir",
            str(normalized_dir),
            "--max-actions",
            "12",
            "--seed",
            "11",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["count"] == 2
    assert summary["normalize"] is True
    assert len(summary["outputs"]) == 2
    assert summary["outputs"][0]["seed"] == 11
    assert summary["outputs"][1]["seed"] == 12
    assert Path(summary["outputs"][0]["raw_output"]).exists()
    assert Path(summary["outputs"][0]["review_output"]).exists()
    assert Path(summary["outputs"][0]["training_output"]).exists()
