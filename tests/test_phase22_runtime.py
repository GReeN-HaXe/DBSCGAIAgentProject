from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from src.agent.phase14_torch import has_torch_support
from src.agent.phase22_state_encoder import evaluate_phase22_state_encoder, train_phase22_state_encoder


def _dataset() -> dict[str, object]:
    return {
        "schema_version": "phase7.v1",
        "examples": [
            {
                "split": "train",
                "example_index": 0,
                "source_name": "trace_a",
                "action_type": "charge_from_hand",
                "action_signature": "charge_from_hand|card=card_id=1",
                "decision_class": "charge_opening",
                "action_family": "resource_development",
                "phase": "charge",
                "actor_role_bucket": "ai",
                "has_identity_resolution": False,
                "state_features": {
                    "battle_step": "",
                    "counter_window_kind": "",
                    "active_player": 1,
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
                "example_index": 1,
                "source_name": "trace_a",
                "action_type": "declare_attack",
                "action_signature": "declare_attack|attacker_zone=leader|target_zone=leader",
                "decision_class": "attack_leader_with_leader",
                "action_family": "combat",
                "phase": "battle",
                "actor_role_bucket": "ai",
                "has_identity_resolution": False,
                "state_features": {
                    "battle_step": "offense",
                    "counter_window_kind": "",
                    "active_player": 1,
                    "self_hand_size": 5,
                    "self_life_size": 8,
                    "self_energy_size": 1,
                    "self_energy_resting_count": 0,
                    "self_battle_size": 1,
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
                "example_index": 2,
                "source_name": "trace_b",
                "action_type": "charge_from_hand",
                "action_signature": "charge_from_hand|card=card_id=2",
                "decision_class": "charge_opening",
                "action_family": "resource_development",
                "phase": "charge",
                "actor_role_bucket": "ai",
                "has_identity_resolution": False,
                "state_features": {
                    "battle_step": "",
                    "counter_window_kind": "",
                    "active_player": 1,
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
                "example_index": 3,
                "source_name": "trace_b",
                "action_type": "declare_attack",
                "action_signature": "declare_attack|attacker_zone=leader|target_zone=leader",
                "decision_class": "attack_leader_with_leader",
                "action_family": "combat",
                "phase": "battle",
                "actor_role_bucket": "ai",
                "has_identity_resolution": False,
                "state_features": {
                    "battle_step": "offense",
                    "counter_window_kind": "",
                    "active_player": 1,
                    "self_hand_size": 5,
                    "self_life_size": 8,
                    "self_energy_size": 1,
                    "self_energy_resting_count": 0,
                    "self_battle_size": 1,
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
    }


def test_phase22_batch_eval_and_report_scripts(tmp_path: Path) -> None:
    if not has_torch_support():
        return
    dataset = _dataset()
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")

    model_payload = train_phase22_state_encoder(
        dataset,
        split="train",
        target_field="decision_class",
        epochs=2,
        batch_size=2,
        hidden_dim=16,
        embedding_dim=8,
    )
    eval_payload = evaluate_phase22_state_encoder(model_payload, dataset, split="validation", batch_size=2)
    baseline_eval = {
        "model_name": "backoff_frequency_policy",
        "target_field": "decision_class",
        "split": "validation",
        "top1_accuracy": 0.5,
    }
    compare_payload = {
        "phase22_top1_accuracy": float(eval_payload["top1_accuracy"]),
        "baseline_top1_accuracy": 0.5,
        "top1_lift": float(eval_payload["top1_accuracy"]) - 0.5,
        "phase22_wins": float(eval_payload["top1_accuracy"]) > 0.5,
        "baseline_model_name": "backoff_frequency_policy",
    }

    production_dir = tmp_path / "phase22_production"
    production_dir.mkdir()
    manifest_path = production_dir / "phase22_manifest.json"
    model_path = production_dir / "phase22_state_model.json"
    eval_path = production_dir / "phase22_state_eval.json"
    baseline_model_path = production_dir / "phase22_baseline_model.json"
    baseline_eval_path = production_dir / "phase22_baseline_eval.json"
    compare_path = production_dir / "phase22_compare.json"
    best_config_path = tmp_path / "phase22_best_config.json"
    summary_path = production_dir / "phase22_production_summary.json"

    model_path.write_text(json.dumps(model_payload, indent=2), encoding="utf-8")
    eval_path.write_text(json.dumps(eval_payload, indent=2), encoding="utf-8")
    baseline_model_path.write_text(json.dumps({"model_name": "backoff_frequency_policy"}, indent=2), encoding="utf-8")
    baseline_eval_path.write_text(json.dumps(baseline_eval, indent=2), encoding="utf-8")
    compare_path.write_text(json.dumps(compare_payload, indent=2), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "phase22.manifest.v1",
                "status": "pass",
                "run_name": "phase22_test",
                "model_name": "phase22_state_encoder",
                "baseline_model_name": "backoff_frequency_policy",
                "target_field": "decision_class",
                "train_split": "train",
                "eval_split": "validation",
                "dataset_path": str(dataset_path),
                "artifacts": {
                    "phase22_model": str(model_path),
                    "phase22_eval": str(eval_path),
                    "baseline_model": str(baseline_model_path),
                    "baseline_eval": str(baseline_eval_path),
                    "compare": str(compare_path),
                },
                "metrics": compare_payload,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    best_config_path.write_text(
        json.dumps(
            {
                "schema_version": "phase22.best_config.v1",
                "profile": "standard",
                "target_field": "decision_class",
                "best": {
                    "config_name": "h128_e20_lr1e3",
                    "hidden_dim": 128,
                    "epochs": 20,
                    "learning_rate": 0.001,
                    "manifest_path": str(manifest_path),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    promote = subprocess.run(
        [
            sys.executable,
            "scripts/promote_phase22_production.py",
            "--best-config",
            str(best_config_path),
            "--production-dir",
            str(production_dir),
            "--output",
            str(summary_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert promote.returncode == 0, promote.stderr

    batch_eval_path = production_dir / "phase22_batch_eval.json"
    batch_eval = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase22_batch_eval.py",
            "--dataset",
            str(dataset_path),
            "--production-dir",
            str(production_dir),
            "--output",
            str(batch_eval_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert batch_eval.returncode == 0, batch_eval.stderr
    batch_payload = json.loads(batch_eval_path.read_text(encoding="utf-8"))
    assert batch_payload["dataset_count"] == 1
    assert batch_payload["datasets"][0]["per_source"][0]["source_name"] == "trace_b"
    assert batch_payload["datasets"][0]["per_source"][0]["example_count"] == 2

    report_path = production_dir / "phase22_batch_eval_report.md"
    report = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase22_batch_eval_report.py",
            "--input",
            str(batch_eval_path),
            "--output",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert report.returncode == 0, report.stderr
    markdown = report_path.read_text(encoding="utf-8")
    assert "Phase 22 Batch Evaluation" in markdown
    assert "trace_b" in markdown

    error_path = production_dir / "phase22_error_analysis.json"
    error_run = subprocess.run(
        [
            sys.executable,
            "scripts/analyze_phase22_errors.py",
            "--dataset",
            str(dataset_path),
            "--production-dir",
            str(production_dir),
            "--output",
            str(error_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert error_run.returncode == 0, error_run.stderr
    error_payload = json.loads(error_path.read_text(encoding="utf-8"))
    assert error_payload["schema_version"] == "phase22.error_analysis.v1"
    assert "per_source" in error_payload

    error_report_path = production_dir / "phase22_error_report.md"
    error_report = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase22_error_report.py",
            "--input",
            str(error_path),
            "--output",
            str(error_report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert error_report.returncode == 0, error_report.stderr
    error_markdown = error_report_path.read_text(encoding="utf-8")
    assert "Phase 22 Error Analysis" in error_markdown
