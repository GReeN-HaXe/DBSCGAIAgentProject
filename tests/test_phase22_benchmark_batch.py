from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from src.agent.phase14_torch import has_torch_support


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


def _write_human_trace(path: Path, action_types: list[str]) -> None:
    payload = {
        "trace": {
            "total_actions": len(action_types),
            "winner_id": 1,
            "final_turn_number": 3,
            "final_phase": "main",
            "human_player_id": 1,
            "setup": {"mode": "fresh", "deck_source": "db_sample"},
            "actions": [
                {
                    "timestamp_utc": f"2026-01-01T00:00:0{index}Z",
                    "actor_kind": "human" if index % 2 == 0 else "ai",
                    "player_id": 1 if index % 2 == 0 else 2,
                    "turn_number": 1 + (index // 2),
                    "phase": "main",
                    "action": action_type,
                    "action_type": action_type,
                    "state_snapshot": {
                        "active_player": 1 if index % 2 == 0 else 2,
                        "turn_number": 1 + (index // 2),
                        "phase": "main",
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
                                "energy_resting_count": 0,
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


def test_normalize_human_trace_batch_and_benchmark_builder(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw_human"
    normalized_dir = tmp_path / "normalized_human"
    normalization_summary = tmp_path / "human_norm_summary.json"
    dataset_output = tmp_path / "human_dataset.json"
    dataset_summary = tmp_path / "human_dataset_summary.json"

    _write_human_trace(raw_dir / "human_vs_ai_trace_001.json", ["charge_from_hand", "play_card_from_hand", "end_turn"])
    _write_human_trace(raw_dir / "human_vs_ai_trace_002.json", ["charge_from_hand", "declare_attack", "end_turn"])

    normalize = subprocess.run(
        [
            sys.executable,
            "scripts/normalize_human_trace_batch.py",
            "--input-glob",
            f"{raw_dir.as_posix()}/*.json",
            "--output-dir",
            str(normalized_dir),
            "--summary-output",
            str(normalization_summary),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert normalize.returncode == 0, normalize.stderr

    review_one = normalized_dir / "human_vs_ai_trace_001_review.json"
    training_one = normalized_dir / "human_vs_ai_trace_001_training.jsonl"
    assert review_one.exists()
    assert training_one.exists()
    review_payload = json.loads(review_one.read_text(encoding="utf-8"))
    assert review_payload["schema_version"] == "human_match_review_trace.v1"
    assert review_payload["decision_count"] == 3

    build = subprocess.run(
        [
            sys.executable,
            "scripts/build_phase22_benchmark_dataset.py",
            "--input",
            str(normalized_dir / "human_vs_ai_trace_001_review.json"),
            str(normalized_dir / "human_vs_ai_trace_002_review.json"),
            "--output",
            str(dataset_output),
            "--summary-output",
            str(dataset_summary),
            "--min-actions",
            "3",
            "--min-unique-action-types",
            "2",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr
    dataset = json.loads(dataset_output.read_text(encoding="utf-8"))
    summary = json.loads(dataset_summary.read_text(encoding="utf-8"))
    assert dataset["example_count"] == 6
    assert summary["included_count"] == 2


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


def test_run_phase22_lomo_pipeline_script(tmp_path: Path) -> None:
    if not has_torch_support():
        return
    dataset_a = tmp_path / "a.json"
    dataset_b = tmp_path / "b.json"
    lomo_dir = tmp_path / "lomo"
    summary = lomo_dir / "phase22_lomo_summary.json"

    dataset_a.write_text(
        json.dumps(
            {
                "schema_version": "phase7.v1",
                "example_count": 4,
                "trajectory_count": 1,
                "sources": ["trace_a"],
                "split_counts": {"train": 2, "validation": 2},
                "trajectories": [],
                "examples": [
                    {
                        "split": "train",
                        "source_name": "trace_a",
                        "turn_number": 1,
                        "phase": "charge",
                        "actor_role_bucket": "ai",
                        "action_type": "charge_from_hand",
                        "action_signature": "charge_from_hand|card=card_id=1",
                        "decision_class": "charge_opening",
                        "action_family": "resource_development",
                        "action_features": {
                            "attacker_zone": "",
                            "target_zone": "",
                            "target_player": "",
                            "source_zone": "",
                            "is_leader_attack": False,
                            "is_battle_attack": False,
                            "is_leader_target": False,
                            "is_battle_target": False,
                            "turn_bucket": "opening",
                            "self_energy_size_bucket": "0",
                            "self_battle_size_bucket": "0",
                            "opponent_battle_size_bucket": "0",
                            "opponent_life_bucket": "7+",
                            "self_board_state": "empty",
                            "opponent_board_state": "empty",
                            "is_pressure_window": False,
                            "is_curve_play": False,
                            "is_existing_board_extension": False,
                            "is_empty_board_setup": False,
                            "has_other_attackers": False,
                        },
                        "has_identity_resolution": False,
                        "state_features": {
                            "active_player": 1,
                            "battle_step": "",
                            "counter_window_kind": "",
                            "self_hand_size": 6,
                            "self_life_size": 8,
                            "self_energy_size": 0,
                            "self_energy_resting_count": 0,
                            "self_battle_size": 0,
                            "self_unison_size": 0,
                            "self_drop_size": 0,
                            "self_warp_size": 0,
                            "opponent_hand_size": 6,
                            "opponent_life_size": 8,
                            "opponent_energy_size": 0,
                            "opponent_battle_size": 0,
                            "opponent_unison_size": 0,
                            "opponent_drop_size": 0,
                            "opponent_warp_size": 0,
                            "self_identity_resolution_count": 0,
                            "self_has_identity_resolution": False,
                            "self_primary_resolved_signature": "",
                            "opponent_identity_resolution_count": 0,
                            "opponent_has_identity_resolution": False,
                            "opponent_primary_resolved_signature": "",
                        },
                    },
                    {
                        "split": "train",
                        "source_name": "trace_a",
                        "turn_number": 2,
                        "phase": "battle",
                        "actor_role_bucket": "ai",
                        "action_type": "declare_attack",
                        "action_signature": "declare_attack|attacker_zone=leader|target_zone=leader",
                        "decision_class": "attack_leader_with_leader",
                        "action_family": "combat",
                        "action_features": {
                            "attacker_zone": "leader",
                            "target_zone": "leader",
                            "target_player": "2",
                            "source_zone": "",
                            "is_leader_attack": True,
                            "is_battle_attack": False,
                            "is_leader_target": True,
                            "is_battle_target": False,
                            "turn_bucket": "opening",
                            "self_energy_size_bucket": "1",
                            "self_battle_size_bucket": "0",
                            "opponent_battle_size_bucket": "0",
                            "opponent_life_bucket": "7+",
                            "self_board_state": "empty",
                            "opponent_board_state": "empty",
                            "is_pressure_window": False,
                            "is_curve_play": False,
                            "is_existing_board_extension": False,
                            "is_empty_board_setup": False,
                            "has_other_attackers": False,
                        },
                        "has_identity_resolution": False,
                        "state_features": {
                            "active_player": 1,
                            "battle_step": "offense",
                            "counter_window_kind": "",
                            "self_hand_size": 5,
                            "self_life_size": 8,
                            "self_energy_size": 1,
                            "self_energy_resting_count": 0,
                            "self_battle_size": 0,
                            "self_unison_size": 0,
                            "self_drop_size": 0,
                            "self_warp_size": 0,
                            "opponent_hand_size": 6,
                            "opponent_life_size": 8,
                            "opponent_energy_size": 0,
                            "opponent_battle_size": 0,
                            "opponent_unison_size": 0,
                            "opponent_drop_size": 0,
                            "opponent_warp_size": 0,
                            "self_identity_resolution_count": 0,
                            "self_has_identity_resolution": False,
                            "self_primary_resolved_signature": "",
                            "opponent_identity_resolution_count": 0,
                            "opponent_has_identity_resolution": False,
                            "opponent_primary_resolved_signature": "",
                        },
                    },
                    {
                        "split": "validation",
                        "source_name": "trace_a",
                        "turn_number": 1,
                        "phase": "charge",
                        "actor_role_bucket": "ai",
                        "action_type": "charge_from_hand",
                        "action_signature": "charge_from_hand|card=card_id=2",
                        "decision_class": "charge_opening",
                        "action_family": "resource_development",
                        "action_features": {
                            "attacker_zone": "",
                            "target_zone": "",
                            "target_player": "",
                            "source_zone": "",
                            "is_leader_attack": False,
                            "is_battle_attack": False,
                            "is_leader_target": False,
                            "is_battle_target": False,
                            "turn_bucket": "opening",
                            "self_energy_size_bucket": "0",
                            "self_battle_size_bucket": "0",
                            "opponent_battle_size_bucket": "0",
                            "opponent_life_bucket": "7+",
                            "self_board_state": "empty",
                            "opponent_board_state": "empty",
                            "is_pressure_window": False,
                            "is_curve_play": False,
                            "is_existing_board_extension": False,
                            "is_empty_board_setup": False,
                            "has_other_attackers": False,
                        },
                        "has_identity_resolution": False,
                        "state_features": {
                            "active_player": 1,
                            "battle_step": "",
                            "counter_window_kind": "",
                            "self_hand_size": 6,
                            "self_life_size": 8,
                            "self_energy_size": 0,
                            "self_energy_resting_count": 0,
                            "self_battle_size": 0,
                            "self_unison_size": 0,
                            "self_drop_size": 0,
                            "self_warp_size": 0,
                            "opponent_hand_size": 6,
                            "opponent_life_size": 8,
                            "opponent_energy_size": 0,
                            "opponent_battle_size": 0,
                            "opponent_unison_size": 0,
                            "opponent_drop_size": 0,
                            "opponent_warp_size": 0,
                            "self_identity_resolution_count": 0,
                            "self_has_identity_resolution": False,
                            "self_primary_resolved_signature": "",
                            "opponent_identity_resolution_count": 0,
                            "opponent_has_identity_resolution": False,
                            "opponent_primary_resolved_signature": "",
                        },
                    },
                    {
                        "split": "validation",
                        "source_name": "trace_a",
                        "turn_number": 2,
                        "phase": "battle",
                        "actor_role_bucket": "ai",
                        "action_type": "declare_attack",
                        "action_signature": "declare_attack|attacker_zone=leader|target_zone=leader",
                        "decision_class": "attack_leader_with_leader",
                        "action_family": "combat",
                        "action_features": {
                            "attacker_zone": "leader",
                            "target_zone": "leader",
                            "target_player": "2",
                            "source_zone": "",
                            "is_leader_attack": True,
                            "is_battle_attack": False,
                            "is_leader_target": True,
                            "is_battle_target": False,
                            "turn_bucket": "opening",
                            "self_energy_size_bucket": "1",
                            "self_battle_size_bucket": "0",
                            "opponent_battle_size_bucket": "0",
                            "opponent_life_bucket": "7+",
                            "self_board_state": "empty",
                            "opponent_board_state": "empty",
                            "is_pressure_window": False,
                            "is_curve_play": False,
                            "is_existing_board_extension": False,
                            "is_empty_board_setup": False,
                            "has_other_attackers": False,
                        },
                        "has_identity_resolution": False,
                        "state_features": {
                            "active_player": 1,
                            "battle_step": "offense",
                            "counter_window_kind": "",
                            "self_hand_size": 5,
                            "self_life_size": 8,
                            "self_energy_size": 1,
                            "self_energy_resting_count": 0,
                            "self_battle_size": 0,
                            "self_unison_size": 0,
                            "self_drop_size": 0,
                            "self_warp_size": 0,
                            "opponent_hand_size": 6,
                            "opponent_life_size": 8,
                            "opponent_energy_size": 0,
                            "opponent_battle_size": 0,
                            "opponent_unison_size": 0,
                            "opponent_drop_size": 0,
                            "opponent_warp_size": 0,
                            "self_identity_resolution_count": 0,
                            "self_has_identity_resolution": False,
                            "self_primary_resolved_signature": "",
                            "opponent_identity_resolution_count": 0,
                            "opponent_has_identity_resolution": False,
                            "opponent_primary_resolved_signature": "",
                        },
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    dataset_b.write_text(dataset_a.read_text(encoding="utf-8"), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase22_lomo_pipeline.py",
            "--dataset",
            str(dataset_a),
            str(dataset_b),
            "--artifacts-dir",
            str(lomo_dir),
            "--epochs",
            "2",
            "--batch-size",
            "2",
            "--hidden-dim",
            "16",
            "--embedding-dim",
            "8",
            "--progress-every",
            "0",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "phase22.lomo.v1"
    assert payload["dataset_count"] == 2
    assert len(payload["folds"]) == 2
