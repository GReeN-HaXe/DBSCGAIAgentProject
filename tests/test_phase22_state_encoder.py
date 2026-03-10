from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from src.agent.phase14_torch import has_torch_support
from src.agent.phase22_state_encoder import (
    PHASE22_DISTRIBUTION_SCHEMA_VERSION,
    PHASE22_COMPARE_SCHEMA_VERSION,
    PHASE22_EVAL_SCHEMA_VERSION,
    PHASE22_MODEL_SCHEMA_VERSION,
    compare_phase22_vs_backoff,
    evaluate_phase22_state_encoder,
    summarize_phase22_target_distribution,
    train_phase22_state_encoder,
)


def _dataset() -> dict[str, object]:
    return {
        "schema_version": "phase7.v1",
        "examples": [
            {
                "split": "train",
                "example_index": 0,
                "turn_number": 1,
                "action_type": "play_card_from_hand",
                "action_signature": "play_card_from_hand|card=BT1-001",
                "decision_class": "play_development",
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
                    "self_energy_size_bucket": "2",
                    "self_battle_size_bucket": "1",
                    "opponent_battle_size_bucket": "0",
                    "opponent_life_bucket": "7+",
                    "self_board_state": "single",
                    "opponent_board_state": "empty",
                    "is_pressure_window": False,
                    "is_curve_play": False,
                    "is_existing_board_extension": True,
                    "is_empty_board_setup": False,
                    "has_other_attackers": False,
                },
                "phase": "main",
                "actor_role_bucket": "ai",
                "has_identity_resolution": True,
                "state_features": {
                    "battle_step": "",
                    "counter_window_kind": "",
                    "active_player": 1,
                    "self_hand_size": 6,
                    "self_life_size": 8,
                    "self_energy_size": 2,
                    "self_energy_resting_count": 0,
                    "self_battle_size": 1,
                    "self_unison_size": 0,
                    "self_drop_size": 0,
                    "self_warp_size": 0,
                    "opponent_hand_size": 6,
                    "opponent_life_size": 8,
                    "opponent_energy_size": 1,
                    "opponent_battle_size": 0,
                    "opponent_unison_size": 0,
                    "opponent_drop_size": 0,
                    "opponent_warp_size": 0,
                    "self_identity_resolution_count": 1,
                    "self_has_identity_resolution": True,
                    "self_primary_resolved_signature": "BT1-001",
                    "opponent_identity_resolution_count": 0,
                    "opponent_has_identity_resolution": False,
                    "opponent_primary_resolved_signature": "",
                },
            },
            {
                "split": "train",
                "example_index": 1,
                "turn_number": 2,
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
                    "self_energy_size_bucket": "3+",
                    "self_battle_size_bucket": "2",
                    "opponent_battle_size_bucket": "1",
                    "opponent_life_bucket": "7+",
                    "self_board_state": "wide",
                    "opponent_board_state": "single",
                    "is_pressure_window": False,
                    "is_curve_play": False,
                    "is_existing_board_extension": False,
                    "is_empty_board_setup": False,
                    "has_other_attackers": True,
                },
                "phase": "battle",
                "actor_role_bucket": "ai",
                "has_identity_resolution": True,
                "state_features": {
                    "battle_step": "offense",
                    "counter_window_kind": "",
                    "active_player": 1,
                    "self_hand_size": 4,
                    "self_life_size": 7,
                    "self_energy_size": 3,
                    "self_energy_resting_count": 1,
                    "self_battle_size": 2,
                    "self_unison_size": 0,
                    "self_drop_size": 1,
                    "self_warp_size": 0,
                    "opponent_hand_size": 5,
                    "opponent_life_size": 7,
                    "opponent_energy_size": 2,
                    "opponent_battle_size": 1,
                    "opponent_unison_size": 0,
                    "opponent_drop_size": 0,
                    "opponent_warp_size": 0,
                    "self_identity_resolution_count": 1,
                    "self_has_identity_resolution": True,
                    "self_primary_resolved_signature": "BT1-002",
                    "opponent_identity_resolution_count": 1,
                    "opponent_has_identity_resolution": True,
                    "opponent_primary_resolved_signature": "BT1-003",
                },
            },
            {
                "split": "validation",
                "example_index": 2,
                "turn_number": 1,
                "action_type": "play_card_from_hand",
                "action_signature": "play_card_from_hand|card=BT1-001",
                "decision_class": "play_development",
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
                    "self_energy_size_bucket": "2",
                    "self_battle_size_bucket": "1",
                    "opponent_battle_size_bucket": "0",
                    "opponent_life_bucket": "7+",
                    "self_board_state": "single",
                    "opponent_board_state": "empty",
                    "is_pressure_window": False,
                    "is_curve_play": False,
                    "is_existing_board_extension": True,
                    "is_empty_board_setup": False,
                    "has_other_attackers": False,
                },
                "phase": "main",
                "actor_role_bucket": "ai",
                "has_identity_resolution": True,
                "state_features": {
                    "battle_step": "",
                    "counter_window_kind": "",
                    "active_player": 1,
                    "self_hand_size": 5,
                    "self_life_size": 8,
                    "self_energy_size": 2,
                    "self_energy_resting_count": 0,
                    "self_battle_size": 1,
                    "self_unison_size": 0,
                    "self_drop_size": 0,
                    "self_warp_size": 0,
                    "opponent_hand_size": 6,
                    "opponent_life_size": 8,
                    "opponent_energy_size": 1,
                    "opponent_battle_size": 0,
                    "opponent_unison_size": 0,
                    "opponent_drop_size": 0,
                    "opponent_warp_size": 0,
                    "self_identity_resolution_count": 1,
                    "self_has_identity_resolution": True,
                    "self_primary_resolved_signature": "BT1-001",
                    "opponent_identity_resolution_count": 0,
                    "opponent_has_identity_resolution": False,
                    "opponent_primary_resolved_signature": "",
                },
            },
        ],
    }


def test_phase22_train_eval_or_explicit_runtime_error() -> None:
    dataset = _dataset()
    if not has_torch_support():
        try:
            train_phase22_state_encoder(dataset, epochs=1)
        except RuntimeError as exc:
            assert "requirements-torch.txt" in str(exc)
            return
        raise AssertionError("expected RuntimeError when torch is unavailable")
    model = train_phase22_state_encoder(dataset, epochs=5, batch_size=2, hidden_dim=16, embedding_dim=8)
    assert model["schema_version"] == PHASE22_MODEL_SCHEMA_VERSION
    evaluation = evaluate_phase22_state_encoder(model, dataset, split="validation", batch_size=2)
    assert evaluation["schema_version"] == PHASE22_EVAL_SCHEMA_VERSION
    assert evaluation["example_count"] == 1
    assert evaluation["top_k_accuracy"]["1"] >= 0.0
    assert evaluation["top_k_accuracy"]["3"] >= evaluation["top_k_accuracy"]["1"]


def test_phase22_compare_helper() -> None:
    payload = compare_phase22_vs_backoff(
        phase22_eval={"model_name": "phase22_state_encoder", "target_field": "action_signature", "split": "validation", "top1_accuracy": 0.8, "identity_resolved_example_rate": 1.0},
        baseline_eval={"model_name": "backoff_frequency_policy", "target_field": "action_signature", "split": "validation", "top1_accuracy": 0.6},
    )
    assert payload["schema_version"] == PHASE22_COMPARE_SCHEMA_VERSION
    assert payload["phase22_wins"] is True


def test_phase22_target_distribution_supports_decision_class() -> None:
    payload = summarize_phase22_target_distribution(_dataset(), target_field="decision_class", split="train")
    assert payload["schema_version"] == PHASE22_DISTRIBUTION_SCHEMA_VERSION
    assert payload["label_count"] == 2


def test_phase22_pipeline_script(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(json.dumps(_dataset(), indent=2), encoding="utf-8")
    artifacts_dir = tmp_path / "phase22_pipeline"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase22_state_pipeline.py",
            "--dataset",
            str(dataset_path),
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
            "--artifacts-dir",
            str(artifacts_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if not has_torch_support():
        assert result.returncode != 0
        assert "requirements-torch.txt" in (result.stdout + result.stderr)
        return
    assert result.returncode == 0, result.stderr
    manifest = json.loads((artifacts_dir / "phase22_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "pass"


def test_phase22_pipeline_skips_single_class_dataset(tmp_path: Path) -> None:
    dataset = _dataset()
    for row in dataset["examples"]:
        row["action_type"] = "detected_frame_state"
        row["action_signature"] = "detected_frame_state"
        row["decision_class"] = "detected_frame_state"
        row["action_family"] = "other"
    dataset_path = tmp_path / "dataset_single_class.json"
    dataset_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    artifacts_dir = tmp_path / "phase22_skip"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase22_state_pipeline.py",
            "--dataset",
            str(dataset_path),
            "--artifacts-dir",
            str(artifacts_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((artifacts_dir / "phase22_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "skipped"
    assert manifest["reason"] == "insufficient_target_classes"
