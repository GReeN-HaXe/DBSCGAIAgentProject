from __future__ import annotations

import json
import subprocess
import sys

from src.agent.dataset import (
    DATASET_SCHEMA_VERSION,
    build_phase7_dataset,
    build_phase7_examples_from_trace_artifact,
    build_phase7_trajectories,
)
from src.agent.replay import compute_trace_hash


def _trace_artifact() -> dict[str, object]:
    payload = {
        "total_actions": 2,
        "winner_id": 1,
        "final_turn_number": 3,
        "final_phase": "main",
        "human_player_id": 1,
        "setup": {"seed": 11, "deck_source": "synthetic"},
        "actions": [
            {
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "actor_kind": "human",
                "player_id": 1,
                "turn_number": 1,
                "phase": "main",
                "action": "play_card_from_hand hand_index=0",
            "action_type": "play_card_from_hand",
            "state_snapshot": {
                    "active_player": 1,
                    "turn_number": 1,
                    "phase": "main",
                    "battle_step": None,
                    "counter_window_kind": None,
                    "players": {
                        "1": {"hand_size": 6, "life_size": 8, "energy_size": 0, "energy_resting_count": 0, "battle_size": 0, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                        "2": {"hand_size": 6, "life_size": 8, "energy_size": 0, "energy_resting_count": 0, "battle_size": 0, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                    },
                },
            },
            {
                "timestamp_utc": "2026-01-01T00:00:01Z",
                "actor_kind": "ai",
                "player_id": 2,
                "turn_number": 1,
                "phase": "battle",
                "action": "declare_attack attacker_zone=leader target_zone=leader target_player=1",
                "action_type": "declare_attack",
                "resolved_signatures_by_seat": {"1": ["BT1-001"], "2": ["BT1-002"]},
                "state_snapshot": {
                    "active_player": 2,
                    "turn_number": 1,
                    "phase": "battle",
                    "battle_step": "offense",
                    "counter_window_kind": None,
                    "resolved_signatures_by_seat": {"1": ["BT1-001"], "2": ["BT1-002"]},
                    "players": {
                        "1": {"hand_size": 5, "life_size": 8, "energy_size": 1, "energy_resting_count": 1, "battle_size": 1, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                        "2": {"hand_size": 6, "life_size": 8, "energy_size": 1, "energy_resting_count": 0, "battle_size": 0, "unison_size": 0, "drop_size": 0, "warp_size": 0},
                    },
                },
            },
        ],
    }
    return {"trace": payload, "trace_hash": compute_trace_hash(payload)}


def test_phase7_build_examples_from_trace_artifact_shape() -> None:
    artifact = _trace_artifact()
    examples = build_phase7_examples_from_trace_artifact(artifact, source_name="play_trace.json")
    assert len(examples) == 2
    assert examples[0]["schema_version"] == DATASET_SCHEMA_VERSION
    assert examples[0]["source_name"] == "play_trace.json"
    assert examples[0]["trace_hash"] == artifact["trace_hash"]
    assert examples[0]["is_human_action"] is True
    assert examples[0]["actor_role_bucket"] == "human"
    assert examples[0]["action_family"] == "resource_development"
    assert examples[0]["did_player_win"] is True
    assert examples[0]["setup"]["seed"] == 11
    assert examples[0]["state_features"]["self_hand_size"] == 6
    assert examples[0]["state_features"]["opponent_life_size"] == 8
    assert examples[0]["decision_class"] == "play_development"
    assert examples[0]["action_features"]["attacker_zone"] == ""
    assert examples[0]["action_features"]["is_leader_attack"] is False
    assert examples[0]["action_features"]["self_board_state"] == "empty"
    assert examples[0]["action_features"]["is_empty_board_setup"] is True
    assert examples[0]["terminal_reward"] == 1.0
    assert examples[0]["value_target"] == 1.0
    assert examples[0]["turns_to_end"] == 2
    assert examples[0]["split"] in {"train", "validation"}
    assert examples[1]["is_human_action"] is False
    assert examples[1]["actor_role_bucket"] == "ai"
    assert examples[1]["action_family"] == "combat"
    assert examples[1]["did_player_win"] is False
    assert examples[1]["state_features"]["battle_step"] == "offense"
    assert examples[1]["state_features"]["self_energy_size"] == 1
    assert examples[1]["decision_class"] == "attack_leader_with_leader"
    assert examples[1]["action_features"]["attacker_zone"] == "leader"
    assert examples[1]["action_features"]["is_leader_attack"] is True
    assert examples[1]["action_features"]["is_battle_attack"] is False
    assert examples[1]["action_features"]["opponent_life_bucket"] == "7+"
    assert examples[1]["action_features"]["has_other_attackers"] is False
    assert examples[1]["terminal_reward"] == -1.0
    assert examples[1]["value_target"] == 0.0
    assert examples[1]["has_identity_resolution"] is True
    assert examples[1]["resolved_signatures_by_seat"]["1"] == ["BT1-001"]
    assert examples[1]["resolved_signatures_by_seat"]["2"] == ["BT1-002"]


def test_phase7_build_dataset_aggregates_sources() -> None:
    dataset = build_phase7_dataset(
        [_trace_artifact(), _trace_artifact()],
        source_names=["a.json", "b.json"],
        validation_ratio=0.5,
    )
    assert dataset["schema_version"] == DATASET_SCHEMA_VERSION
    assert dataset["example_count"] == 4
    assert dataset["trajectory_count"] == 2
    assert dataset["sources"] == ["a.json", "b.json"]
    assert dataset["split_counts"]["train"] + dataset["split_counts"]["validation"] == 4
    assert isinstance(dataset["trajectories"], list)
    assert len(dataset["trajectories"]) == 2


def test_phase7_build_trajectories_groups_examples_per_match() -> None:
    trajectories = build_phase7_trajectories([_trace_artifact()], source_names=["trace_a.json"], validation_ratio=0.5)
    assert len(trajectories) == 1
    trajectory = trajectories[0]
    assert trajectory["source_name"] == "trace_a.json"
    assert trajectory["total_actions"] == 2
    assert trajectory["action_types"] == ["play_card_from_hand", "declare_attack"]
    assert len(trajectory["examples"]) == 2


def test_phase7_export_script_writes_jsonl(tmp_path) -> None:
    input_path = tmp_path / "trace.json"
    output_path = tmp_path / "dataset.jsonl"
    input_path.write_text(json.dumps(_trace_artifact(), indent=2), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/export_phase7_dataset.py",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--format",
            "jsonl",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 2
    assert rows[0]["schema_version"] == DATASET_SCHEMA_VERSION


def test_phase7_export_script_writes_dataset_json_with_split_counts(tmp_path) -> None:
    input_path = tmp_path / "trace.json"
    output_path = tmp_path / "dataset.json"
    input_path.write_text(json.dumps(_trace_artifact(), indent=2), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/export_phase7_dataset.py",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--validation-ratio",
            "0.5",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == DATASET_SCHEMA_VERSION
    assert payload["split_counts"]["train"] + payload["split_counts"]["validation"] == 2


def test_phase7_evaluate_dataset_script_writes_metrics(tmp_path) -> None:
    input_path = tmp_path / "trace.json"
    dataset_path = tmp_path / "dataset.json"
    output_path = tmp_path / "eval.json"
    input_path.write_text(json.dumps(_trace_artifact(), indent=2), encoding="utf-8")

    export_result = subprocess.run(
        [
            sys.executable,
            "scripts/export_phase7_dataset.py",
            "--input",
            str(input_path),
            "--output",
            str(dataset_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert export_result.returncode == 0, export_result.stderr

    eval_result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_phase7_dataset.py",
            "--dataset",
            str(dataset_path),
            "--split",
            "all",
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert eval_result.returncode == 0, eval_result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["profile"] == "balanced"
    assert payload["split"] == "all"
    assert payload["example_count"] == 2
    assert "top1_accuracy" in payload
    assert "family_accuracy" in payload
    assert payload["identity_resolved_example_count"] == 1
    assert payload["identity_resolution_slices"]["with_identity"]["example_count"] == 1
    assert payload["identity_resolution_slices"]["without_identity"]["example_count"] == 1


def test_phase7_compare_profiles_script_writes_ranking(tmp_path) -> None:
    input_path = tmp_path / "trace.json"
    dataset_path = tmp_path / "dataset.json"
    output_path = tmp_path / "compare.json"
    input_path.write_text(json.dumps(_trace_artifact(), indent=2), encoding="utf-8")

    export_result = subprocess.run(
        [
            sys.executable,
            "scripts/export_phase7_dataset.py",
            "--input",
            str(input_path),
            "--output",
            str(dataset_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert export_result.returncode == 0, export_result.stderr

    compare_result = subprocess.run(
        [
            sys.executable,
            "scripts/compare_phase7_profiles.py",
            "--dataset",
            str(dataset_path),
            "--split",
            "all",
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert compare_result.returncode == 0, compare_result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["split"] == "all"
    assert len(payload["ranking"]) == 3
    assert payload["ranking"][0]["rank"] == 1
    assert "identity_resolution_rankings" in payload
    assert "with_identity" in payload["identity_resolution_rankings"]
    assert "without_identity" in payload["identity_resolution_rankings"]
