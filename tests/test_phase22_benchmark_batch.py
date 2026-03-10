from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_review_trace(path: Path, action_types: list[str]) -> None:
    payload = {
        "schema_version": "ai_match_review_trace.v1",
        "winner_id": 2,
        "turn_number": 3,
        "phase": "main",
        "stop_reason": "winner_decided",
        "total_actions": len(action_types),
        "decision_trace": [
            {
                "step_index": index + 1,
                "actor_player_id": 1,
                "turn_number": 1 + (index // 3),
                "phase": "main",
                "chosen_action_type": action_type,
                "chosen_action_text": action_type,
                "state_snapshot": {
                    "active_player": 1,
                    "battle_step": "",
                    "counter_window_kind": "",
                    "players": {
                        "1": {
                            "hand_size": 5,
                            "life_size": 8,
                            "energy_size": 1,
                            "energy_resting_count": 0,
                            "battle_size": 1,
                            "unison_size": 0,
                            "drop_size": 0,
                            "warp_size": 0,
                        },
                        "2": {
                            "hand_size": 5,
                            "life_size": 8,
                            "energy_size": 1,
                            "battle_size": 0,
                            "unison_size": 0,
                            "drop_size": 0,
                            "warp_size": 0,
                        },
                    },
                },
            }
            for index, action_type in enumerate(action_types)
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_phase22_benchmark_batch_script(tmp_path: Path) -> None:
    source_dir = tmp_path / "normalized"
    output_dir = tmp_path / "datasets"
    batch_summary = tmp_path / "batch_summary.json"
    _write_review_trace(source_dir / "match_a_001_review.json", ["charge_from_hand", "play_card_from_hand", "end_turn"])
    _write_review_trace(source_dir / "match_a_002_review.json", ["charge_from_hand", "declare_attack", "end_turn"])
    _write_review_trace(source_dir / "match_b_001_review.json", ["charge_from_hand", "play_card_from_hand", "declare_attack", "end_turn"])

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_phase22_benchmark_batch.py",
            "--group",
            f"group_a={source_dir.as_posix()}/match_a_*_review.json",
            "--group",
            f"group_b={source_dir.as_posix()}/match_b_*_review.json",
            "--output-dir",
            str(output_dir),
            "--summary-output",
            str(batch_summary),
            "--min-actions",
            "3",
            "--min-unique-action-types",
            "2",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    group_a = json.loads((output_dir / "group_a.json").read_text(encoding="utf-8"))
    group_b = json.loads((output_dir / "group_b.json").read_text(encoding="utf-8"))
    summary = json.loads(batch_summary.read_text(encoding="utf-8"))

    assert group_a["example_count"] == 6
    assert group_b["example_count"] == 4
    assert summary["dataset_count"] == 2
    assert summary["datasets"][0]["group_name"] == "group_a"


def test_build_phase22_merged_benchmark_script(tmp_path: Path) -> None:
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    output = tmp_path / "merged.json"
    summary = tmp_path / "merged_summary.json"
    left.write_text(
        json.dumps(
            {
                "schema_version": "phase7.v1",
                "example_count": 2,
                "trajectory_count": 1,
                "sources": ["trace_a"],
                "split_counts": {"train": 1, "validation": 1},
                "trajectories": [{"source_name": "trace_a"}],
                "examples": [{"split": "train"}, {"split": "validation"}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    right.write_text(
        json.dumps(
            {
                "schema_version": "phase7.v1",
                "example_count": 3,
                "trajectory_count": 1,
                "sources": ["trace_b"],
                "split_counts": {"train": 2, "validation": 1},
                "trajectories": [{"source_name": "trace_b"}],
                "examples": [{"split": "train"}, {"split": "train"}, {"split": "validation"}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_phase22_merged_benchmark.py",
            "--input",
            str(left),
            str(right),
            "--output",
            str(output),
            "--summary-output",
            str(summary),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    merged = json.loads(output.read_text(encoding="utf-8"))
    merged_summary = json.loads(summary.read_text(encoding="utf-8"))
    assert merged["example_count"] == 5
    assert merged["trajectory_count"] == 2
    assert merged["split_counts"]["train"] == 3
    assert merged["split_counts"]["validation"] == 2
    assert merged_summary["merged_example_count"] == 5
    assert merged_summary["input_count"] == 2
