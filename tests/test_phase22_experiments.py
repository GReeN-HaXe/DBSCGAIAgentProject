from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from src.agent.phase22_experiments import (
    build_phase22_experiment_history_row,
    build_phase22_model_manifest,
    phase22_experiment_history_row_to_dict,
    summarize_phase22_experiment_history,
)
from src.agent.phase14_torch import has_torch_support
from src.agent.phase22_state_encoder import train_phase22_state_encoder, evaluate_phase22_state_encoder


def test_phase22_manifest_and_history_helpers() -> None:
    compare_payload = {
        "phase22_top1_accuracy": 0.91,
        "baseline_top1_accuracy": 0.88,
        "top1_lift": 0.03,
        "phase22_wins": True,
        "baseline_model_name": "backoff_frequency_policy",
    }
    manifest = build_phase22_model_manifest(
        run_name="phase22_test",
        dataset_path="artifacts/dataset.json",
        model_path="artifacts/model.json",
        eval_path="artifacts/eval.json",
        baseline_model_path="artifacts/baseline_model.json",
        baseline_eval_path="artifacts/baseline_eval.json",
        compare_path="artifacts/compare.json",
        target_field="decision_class",
        train_split="train",
        eval_split="validation",
        model_payload={
            "model_name": "phase22_state_encoder",
            "schema_version": "phase22.state_encoder.v1",
            "example_count": 100,
            "hidden_dim": 128,
            "embedding_dim": 16,
            "epochs": 20,
            "learning_rate": 1e-3,
        },
        eval_payload={
            "example_count": 50,
            "identity_resolved_example_rate": 0.25,
        },
        baseline_eval_payload={"model_name": "backoff_frequency_policy"},
        compare_payload=compare_payload,
    )
    assert manifest["schema_version"] == "phase22.manifest.v1"
    assert manifest["metrics"]["top1_lift"] == 0.03
    assert manifest["phase22_summary"]["hidden_dim"] == 128

    row = phase22_experiment_history_row_to_dict(
        build_phase22_experiment_history_row(
            run_name="phase22_test",
            model_name="phase22_state_encoder",
            baseline_model_name="backoff_frequency_policy",
            target_field="decision_class",
            train_split="train",
            eval_split="validation",
            example_count=50,
            top1_accuracy=0.91,
            baseline_top1_accuracy=0.88,
            top1_lift=0.03,
            wins=True,
            status="pass",
            manifest_path="artifacts/manifest.json",
        )
    )
    summary = summarize_phase22_experiment_history([row])
    assert summary["best_top1_lift"] == 0.03
    assert summary["win_rate"] == 1.0


def test_phase22_promote_and_report_scripts(tmp_path: Path) -> None:
    summary_path = tmp_path / "phase22_sweep_summary.json"
    output_best = tmp_path / "phase22_best_config.json"
    report_path = tmp_path / "phase22_report.md"
    compare_path = tmp_path / "phase22_compare.json"

    summary_path.write_text(
        json.dumps(
            {
                "schema_version": "phase22.sweep.v1",
                "profile": "standard",
                "target_field": "decision_class",
                "config_count": 3,
                "best": {
                    "config_name": "h128_e20_lr1e3",
                    "top1_lift": 0.03,
                    "top1_accuracy": 0.91,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    compare_path.write_text(
        json.dumps(
            {
                "schema_version": "phase22.compare.v1",
                "target_field": "decision_class",
                "phase22_top1_accuracy": 0.91,
                "baseline_top1_accuracy": 0.88,
                "top1_lift": 0.03,
                "phase22_wins": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    promote = subprocess.run(
        [
            sys.executable,
            "scripts/promote_phase22_best.py",
            "--summary",
            str(summary_path),
            "--output",
            str(output_best),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert promote.returncode == 0, promote.stderr
    best_payload = json.loads(output_best.read_text(encoding="utf-8"))
    assert best_payload["best"]["config_name"] == "h128_e20_lr1e3"

    report = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase22_report.py",
            "--compare",
            str(compare_path),
            "--sweep-summary",
            str(summary_path),
            "--output",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert report.returncode == 0, report.stderr
    markdown = report_path.read_text(encoding="utf-8")
    assert "Phase 22 Report" in markdown
    assert "decision_class" in markdown
    assert "h128_e20_lr1e3" in markdown


def test_phase22_promote_production_and_runtime_scripts(tmp_path: Path) -> None:
    if not has_torch_support():
        return
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(
        json.dumps(
            {
                "schema_version": "phase7.v1",
                "examples": [
                    {
                        "split": "train",
                        "example_index": 0,
                        "action_type": "play_card_from_hand",
                        "action_signature": "play_card_from_hand|card=BT1-001",
                        "decision_class": "play_development",
                        "action_family": "resource_development",
                        "phase": "main",
                        "actor_role_bucket": "ai",
                        "has_identity_resolution": False,
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
                            "opponent_hand_size": 5,
                            "opponent_life_size": 8,
                            "opponent_energy_size": 1,
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
                        "action_type": "end_turn",
                        "action_signature": "end_turn",
                        "decision_class": "end_turn_after_development",
                        "action_family": "turn_management",
                        "phase": "main",
                        "actor_role_bucket": "ai",
                        "has_identity_resolution": False,
                        "state_features": {
                            "battle_step": "",
                            "counter_window_kind": "",
                            "active_player": 1,
                            "self_hand_size": 4,
                            "self_life_size": 8,
                            "self_energy_size": 2,
                            "self_energy_resting_count": 1,
                            "self_battle_size": 1,
                            "self_unison_size": 0,
                            "self_drop_size": 1,
                            "self_warp_size": 0,
                            "opponent_hand_size": 5,
                            "opponent_life_size": 8,
                            "opponent_energy_size": 1,
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
                        "action_type": "play_card_from_hand",
                        "action_signature": "play_card_from_hand|card=BT1-001",
                        "decision_class": "play_development",
                        "action_family": "resource_development",
                        "phase": "main",
                        "actor_role_bucket": "ai",
                        "has_identity_resolution": False,
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
                            "opponent_hand_size": 5,
                            "opponent_life_size": 8,
                            "opponent_energy_size": 1,
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
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    manifest_path = run_dir / "phase22_manifest.json"
    model_path = run_dir / "phase22_state_model.json"
    eval_path = run_dir / "phase22_state_eval.json"
    baseline_model_path = run_dir / "phase22_baseline_model.json"
    baseline_eval_path = run_dir / "phase22_baseline_eval.json"
    compare_path = run_dir / "phase22_compare.json"
    dataset_payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    model_payload = train_phase22_state_encoder(
        dataset_payload,
        split="train",
        target_field="decision_class",
        epochs=2,
        batch_size=2,
        hidden_dim=16,
        embedding_dim=8,
    )
    eval_payload = evaluate_phase22_state_encoder(
        model_payload,
        dataset_payload,
        split="validation",
        batch_size=2,
    )
    model_path.write_text(json.dumps(model_payload, indent=2), encoding="utf-8")
    eval_path.write_text(json.dumps(eval_payload, indent=2), encoding="utf-8")
    baseline_model_path.write_text(json.dumps({"model_name": "backoff_frequency_policy"}, indent=2), encoding="utf-8")
    baseline_eval_path.write_text(
        json.dumps(
            {
                "model_name": "backoff_frequency_policy",
                "target_field": "decision_class",
                "split": "validation",
                "top1_accuracy": 0.8,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    compare_path.write_text(
        json.dumps(
            {
                "schema_version": "phase22.compare.v1",
                "phase22_model_name": "phase22_state_encoder",
                "baseline_model_name": "backoff_frequency_policy",
                "target_field": "decision_class",
                "split": "validation",
                "phase22_top1_accuracy": 1.0,
                "baseline_top1_accuracy": 0.8,
                "top1_lift": 0.2,
                "phase22_wins": True,
                "identity_resolved_example_rate": 0.0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
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
                "metrics": {
                    "phase22_top1_accuracy": 1.0,
                    "baseline_top1_accuracy": 0.8,
                    "top1_lift": 0.2,
                    "phase22_wins": True,
                    "example_count": 1,
                    "identity_resolved_example_rate": 0.0,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    best_config_path = tmp_path / "phase22_best_config.json"
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
    production_dir = tmp_path / "production"
    production_summary = production_dir / "phase22_production_summary.json"

    promote = subprocess.run(
        [
            sys.executable,
            "scripts/promote_phase22_production.py",
            "--best-config",
            str(best_config_path),
            "--production-dir",
            str(production_dir),
            "--output",
            str(production_summary),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert promote.returncode == 0, promote.stderr
    production_summary_payload = json.loads(production_summary.read_text(encoding="utf-8"))
    assert "training_dataset_secret_auto_summary" in production_summary_payload
    assert production_summary_payload["training_dataset_secret_auto_summary"]["total_opportunity_count"] == 0

    eval_output = production_dir / "phase22_production_eval.json"
    evaluate = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase22_production_eval.py",
            "--production-dir",
            str(production_dir),
            "--dataset",
            str(dataset_path),
            "--split",
            "validation",
            "--output",
            str(eval_output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert evaluate.returncode == 0, evaluate.stderr
    eval_payload = json.loads(eval_output.read_text(encoding="utf-8"))
    assert "top_k_accuracy" in eval_payload

    query_output = production_dir / "phase22_query_result.json"
    query = subprocess.run(
        [
            sys.executable,
            "scripts/query_phase22_production.py",
            "--production-dir",
            str(production_dir),
            "--dataset",
            str(dataset_path),
            "--split",
            "validation",
            "--query-index",
            "0",
            "--output",
            str(query_output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert query.returncode == 0, query.stderr
    query_payload = json.loads(query_output.read_text(encoding="utf-8"))
    assert query_payload["row"]["decision_class"] == "play_development"


def test_phase22_closeout_report_surfaces_secret_auto_counts(tmp_path: Path) -> None:
    best_config = tmp_path / "best.json"
    generalization = tmp_path / "generalization_batch_eval.json"
    lomo = tmp_path / "lomo.json"
    output = tmp_path / "closeout.md"

    best_config.write_text(
        json.dumps(
            {
                "target_field": "decision_class",
                "best": {
                    "config_name": "phase22_best",
                    "hidden_dim": 128,
                    "epochs": 20,
                    "learning_rate": 0.001,
                    "manifest_path": "artifacts/phase22_manifest.json",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    generalization.write_text(
        json.dumps(
            {
                "dataset_count": 2,
                "overall_example_count": 10,
                "overall_top1_accuracy": 0.75,
                "datasets": [
                    {"dataset_path": "a.json", "top1_accuracy": 0.8},
                    {"dataset_path": "b.json", "top1_accuracy": 0.7},
                ],
                "secret_auto_summary": {
                    "trace_count_with_secret_auto_opportunities": 2,
                    "total_opportunity_count": 5,
                    "total_pending_count": 0,
                    "total_blocked_count": 4,
                    "total_preblocked_count": 2,
                    "status_counts": {"blocked_limit_per_turn": 3, "blocked_once_per_turn": 1},
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    lomo.write_text(
        json.dumps(
            {
                "dataset_count": 2,
                "overall_top1_accuracy_weighted": 0.73,
                "overall_top1_accuracy_macro": 0.72,
                "holdout_secret_auto_summary": {
                    "trace_count_with_secret_auto_opportunities": 1,
                    "total_opportunity_count": 2,
                    "total_pending_count": 0,
                    "total_blocked_count": 2,
                    "total_preblocked_count": 1,
                    "status_counts": {"blocked_limit_per_turn": 2},
                },
                "folds": [
                    {"fold_name": "a", "top1_accuracy": 0.74},
                    {"fold_name": "b", "top1_accuracy": 0.70},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase22_closeout_report.py",
            "--best-config",
            str(best_config),
            "--generalization-batch-eval",
            str(generalization),
            "--lomo-summary",
            str(lomo),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    markdown = output.read_text(encoding="utf-8")
    assert "Phase 22 Closeout" in markdown
    assert "generalized_secret_auto_summary" in markdown
    assert "lomo_holdout_secret_auto_summary" in markdown
    assert "total_opportunity_count: `5`" in markdown
    assert "total_preblocked_count: `1`" in markdown
