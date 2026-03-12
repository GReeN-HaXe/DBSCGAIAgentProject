from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from src.agent.phase13_visual_learning import build_phase13_feature_cache, build_phase13_reference_image_dataset
from src.agent.phase14_torch import (
    PHASE14_COMPARE_SCHEMA_VERSION,
    PHASE14_COMPARE_HISTORY_SCHEMA_VERSION,
    PHASE14_EVAL_SCHEMA_VERSION,
    PHASE14_MODEL_SCHEMA_VERSION,
    PHASE14_ERROR_ANALYSIS_SCHEMA_VERSION,
    PHASE14_EMBEDDING_ANALYSIS_SCHEMA_VERSION,
    PHASE14_EMBEDDING_COMPARE_SCHEMA_VERSION,
    PHASE14_EMBEDDING_RETRIEVAL_SCHEMA_VERSION,
    PHASE14_RETRIEVAL_SCHEMA_VERSION,
    PHASE14_RETRIEVAL_COMPARISON_SCHEMA_VERSION,
    analyze_phase14_embedding_retrieval,
    analyze_phase14_errors,
    compare_phase14_embedding_vs_classifier_retrieval,
    build_phase14_compare_history_row,
    compare_phase14_vs_phase13_identity,
    compare_phase14_retrieval_runs,
    evaluate_phase14_embedding_retrieval,
    evaluate_phase14_retrieval,
    evaluate_phase14_torch_model,
    has_torch_support,
    phase14_compare_history_row_to_dict,
    summarize_phase14_compare_history,
    train_phase14_torch_model,
)


def _reference_dataset(tmp_path: Path) -> dict[str, object]:
    image_a = tmp_path / "BT1-001.ppm"
    image_b = tmp_path / "BT1-002.ppm"
    image_c = tmp_path / "BT1-003.ppm"
    image_a.write_text("P3\n1 1\n255\n255 0 0\n", encoding="utf-8")
    image_b.write_text("P3\n1 1\n255\n0 255 0\n", encoding="utf-8")
    image_c.write_text("P3\n1 1\n255\n0 0 255\n", encoding="utf-8")
    manifest = {
        "schema_version": "card_image_reference_manifest.v1",
        "cards": [
            {
                "card_number": "BT1-001",
                "primary_image_path": str(image_a),
                "card_name": "Card A",
                "table_name": "cards",
                "record_id": 1,
                "image_count": 1,
                "match_type": "exact_stem",
            },
            {
                "card_number": "BT1-002",
                "primary_image_path": str(image_b),
                "card_name": "Card B",
                "table_name": "cards",
                "record_id": 2,
                "image_count": 1,
                "match_type": "exact_stem",
            },
            {
                "card_number": "BT1-003",
                "primary_image_path": str(image_c),
                "card_name": "Card C",
                "table_name": "cards",
                "record_id": 3,
                "image_count": 1,
                "match_type": "exact_stem",
            },
        ],
    }
    dataset = build_phase13_reference_image_dataset(manifest, validation_ratio=0.34, split_mode="disjoint_card")
    for row in dataset["examples"]:
        row["split"] = "train"
    return build_phase13_feature_cache(dataset)


def test_phase14_torch_train_and_eval_or_explicit_runtime_error(tmp_path: Path) -> None:
    dataset = _reference_dataset(tmp_path)
    if not has_torch_support():
        with pytest.raises(RuntimeError, match="requirements-torch.txt"):
            train_phase14_torch_model(dataset, split="train", epochs=1)
        return

    model = train_phase14_torch_model(dataset, split="train", epochs=5, batch_size=2, hidden_dim=8, progress_every=0)
    assert model["schema_version"] == PHASE14_MODEL_SCHEMA_VERSION
    evaluation = evaluate_phase14_torch_model(model, dataset, split="train", batch_size=2)
    assert evaluation["schema_version"] == PHASE14_EVAL_SCHEMA_VERSION
    assert evaluation["example_count"] == 3


def test_phase14_pipeline_script_or_explicit_missing_dependency(tmp_path: Path) -> None:
    dataset = _reference_dataset(tmp_path)
    feature_cache_path = tmp_path / "phase13_feature_cache.json"
    artifact_dir = tmp_path / "phase14_pipeline"
    feature_cache_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase14_identity_pipeline.py",
            "--feature-cache",
            str(feature_cache_path),
            "--epochs",
            "2",
            "--batch-size",
            "2",
            "--hidden-dim",
            "8",
            "--eval-split",
            "train",
            "--progress-every",
            "0",
            "--artifacts-dir",
            str(artifact_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    if not has_torch_support():
        assert result.returncode != 0
        assert "requirements-torch.txt" in (result.stderr + result.stdout)
        return

    assert result.returncode == 0, result.stderr
    manifest = json.loads((artifact_dir / "phase14_torch_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "pass"


def test_phase14_eval_handles_unseen_validation_labels(tmp_path: Path) -> None:
    dataset = _reference_dataset(tmp_path)
    dataset["examples"][0]["split"] = "train"
    dataset["examples"][1]["split"] = "train"
    dataset["examples"][2]["split"] = "validation"

    if not has_torch_support():
        with pytest.raises(RuntimeError, match="requirements-torch.txt"):
            train_phase14_torch_model(dataset, split="train", epochs=1)
        return

    model = train_phase14_torch_model(dataset, split="train", epochs=3, batch_size=1, hidden_dim=4, progress_every=0)
    evaluation = evaluate_phase14_torch_model(model, dataset, split="validation", batch_size=1)
    assert evaluation["example_count"] == 1
    assert evaluation["unseen_expected_label_count"] == 1
    assert evaluation["unseen_example_count"] == 1
    assert evaluation["rows"][0]["expected_seen_in_training"] is False


def test_phase14_compare_helper() -> None:
    comparison = compare_phase14_vs_phase13_identity(
        phase14_eval={
            "target_type": "card_identity",
            "split": "validation",
            "model_name": "phase14_torch_mlp",
            "top1_accuracy": 0.75,
            "top_k_accuracy": {"5": 0.9, "10": 0.95},
            "example_count": 128,
        },
        phase13_eval={
            "target_type": "card_identity",
            "split": "validation",
            "model_name": "phase13_visual_histogram_knn",
            "top1_accuracy": 0.4,
            "top_k_accuracy": {"5": 0.6, "10": 0.75},
            "example_count": 128,
        },
    )
    assert comparison["schema_version"] == PHASE14_COMPARE_SCHEMA_VERSION
    assert comparison["phase14_wins"] is True
    assert comparison["top1_lift"] > 0.0


def test_phase14_compare_history_summary() -> None:
    row = build_phase14_compare_history_row(
        run_name="phase14_compare_run",
        top1_lift=0.5,
        top5_lift=0.7,
        top10_lift=0.8,
        phase14_wins=True,
        manifest_path="artifacts/phase14_compare_manifest.json",
    )
    assert row["schema_version"] == PHASE14_COMPARE_HISTORY_SCHEMA_VERSION
    summary = summarize_phase14_compare_history([phase14_compare_history_row_to_dict(row)])
    assert summary["run_count"] == 1
    assert summary["best_top1_lift"] == 0.5
    assert summary["phase14_win_rate_recent"] == 1.0


def test_phase14_sweep_report_script(tmp_path: Path) -> None:
    summary_path = tmp_path / "phase14_sweep_summary.json"
    report_path = tmp_path / "phase14_sweep_report.md"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": "phase14.sweep.v1",
                "profile": "quick",
                "config_count": 2,
                "best": {
                    "config_name": "h128_e10_lr1e3",
                    "top1_accuracy": 0.8,
                    "top5_accuracy": 0.95,
                    "top10_accuracy": 0.99,
                },
                "ranking": [
                    {
                        "config_name": "h128_e10_lr1e3",
                        "hidden_dim": 128,
                        "epochs": 10,
                        "learning_rate": 0.001,
                        "top1_accuracy": 0.8,
                        "top5_accuracy": 0.95,
                        "top10_accuracy": 0.99,
                        "duration_seconds": 10.0,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase14_sweep_report.py",
            "--summary",
            str(summary_path),
            "--output",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "# Phase 14 Sweep Report" in report_path.read_text(encoding="utf-8")


def test_phase14_retrieval_helper() -> None:
    retrieval = evaluate_phase14_retrieval(
        {
            "model_name": "phase14_torch_mlp",
            "target_type": "card_identity",
            "split": "validation",
            "rows": [
                {
                    "expected_signature": "BT1-001",
                    "predicted_signature": "BT1-001",
                    "top_predictions": [
                        {"signature": "BT1-001", "confidence": 0.8},
                        {"signature": "BT1-002", "confidence": 0.1},
                    ],
                },
                {
                    "expected_signature": "BT1-002",
                    "predicted_signature": "BT1-003",
                    "top_predictions": [
                        {"signature": "BT1-003", "confidence": 0.7},
                        {"signature": "BT1-002", "confidence": 0.2},
                    ],
                },
            ],
        },
        top_k_values=(1, 2),
    )
    assert retrieval["schema_version"] == PHASE14_RETRIEVAL_SCHEMA_VERSION
    assert retrieval["mean_reciprocal_rank"] == pytest.approx(0.75)
    assert retrieval["recall_at_k"]["1"] == 0.5
    assert retrieval["recall_at_k"]["2"] == 1.0


def test_phase14_error_analysis_helper() -> None:
    analysis = analyze_phase14_errors(
        {
            "model_name": "phase14_torch_mlp",
            "target_type": "card_identity",
            "split": "validation",
            "example_count": 3,
            "rows": [
                {
                    "expected_signature": "BT1-001",
                    "predicted_signature": "BT1-002",
                    "correct": False,
                    "crop_image_path": "a.webp",
                    "top_predictions": [{"signature": "BT1-002", "confidence": 0.9}],
                },
                {
                    "expected_signature": "BT1-001",
                    "predicted_signature": "BT1-002",
                    "correct": False,
                    "crop_image_path": "b.webp",
                    "top_predictions": [{"signature": "BT1-002", "confidence": 0.8}],
                },
                {
                    "expected_signature": "BT1-003",
                    "predicted_signature": "BT1-003",
                    "correct": True,
                    "crop_image_path": "c.webp",
                    "top_predictions": [{"signature": "BT1-003", "confidence": 0.95}],
                },
            ],
        }
    )
    assert analysis["schema_version"] == PHASE14_ERROR_ANALYSIS_SCHEMA_VERSION
    assert analysis["top_confusions"][0]["count"] == 2


def test_phase14_retrieval_comparison_helper() -> None:
    comparison = compare_phase14_retrieval_runs(
        [
            {
                "run_name": "run_a",
                "example_count": 100,
                "mean_reciprocal_rank": 0.7,
                "mean_found_rank": 2.0,
                "recall_at_k": {"1": 0.5, "5": 0.9, "10": 0.95, "20": 0.97},
            },
            {
                "run_name": "run_b",
                "example_count": 100,
                "mean_reciprocal_rank": 0.8,
                "mean_found_rank": 1.8,
                "recall_at_k": {"1": 0.6, "5": 0.92, "10": 0.96, "20": 0.98},
            },
        ]
    )
    assert comparison["schema_version"] == PHASE14_RETRIEVAL_COMPARISON_SCHEMA_VERSION
    assert comparison["best"]["run_name"] == "run_b"


def test_phase14_embedding_retrieval_or_missing_dependency(tmp_path: Path) -> None:
    dataset = _reference_dataset(tmp_path)
    dataset["examples"][0]["split"] = "train"
    dataset["examples"][1]["split"] = "train"
    dataset["examples"][2]["split"] = "validation"
    if not has_torch_support():
        with pytest.raises(RuntimeError, match="requirements-torch.txt"):
            train_phase14_torch_model(dataset, split="train", epochs=1)
        return
    model = train_phase14_torch_model(dataset, split="train", epochs=3, batch_size=1, hidden_dim=4, progress_every=0)
    retrieval = evaluate_phase14_embedding_retrieval(
        model,
        dataset,
        gallery_split="train",
        query_split="validation",
        top_k_values=(1, 2),
    )
    assert retrieval["schema_version"] == PHASE14_EMBEDDING_RETRIEVAL_SCHEMA_VERSION
    assert retrieval["example_count"] == 1


def test_phase14_embedding_vs_classifier_compare_helper() -> None:
    comparison = compare_phase14_embedding_vs_classifier_retrieval(
        classifier_retrieval={
            "target_type": "card_identity",
            "example_count": 128,
            "model_name": "phase14_torch_mlp",
            "mean_reciprocal_rank": 0.7,
            "recall_at_k": {"1": 0.6, "5": 0.9, "10": 0.95},
        },
        embedding_retrieval={
            "target_type": "card_identity",
            "example_count": 128,
            "model_name": "phase14_torch_mlp",
            "mean_reciprocal_rank": 0.95,
            "recall_at_k": {"1": 0.9, "5": 0.99, "10": 1.0},
        },
    )
    assert comparison["schema_version"] == PHASE14_EMBEDDING_COMPARE_SCHEMA_VERSION
    assert comparison["embedding_wins"] is True
    assert comparison["mrr_lift"] > 0.0


def test_phase14_embedding_analysis_helper() -> None:
    analysis = analyze_phase14_embedding_retrieval(
        {
            "model_name": "phase14_torch_mlp",
            "target_type": "card_identity",
            "gallery_split": "train",
            "query_split": "validation",
            "rows": [
                {
                    "expected_signature": "BT1-001",
                    "found_rank": 1,
                    "crop_image_path": "a.webp",
                    "top_predictions": [{"signature": "BT1-001", "score": 0.99}],
                },
                {
                    "expected_signature": "BT1-002",
                    "found_rank": 3,
                    "crop_image_path": "b.webp",
                    "top_predictions": [{"signature": "BT1-003", "score": 0.88}],
                },
                {
                    "expected_signature": "BT1-002",
                    "found_rank": 4,
                    "crop_image_path": "c.webp",
                    "top_predictions": [{"signature": "BT1-003", "score": 0.77}],
                },
            ],
        }
    )
    assert analysis["schema_version"] == PHASE14_EMBEDDING_ANALYSIS_SCHEMA_VERSION
    assert analysis["perfect_hit_count"] == 1
    assert analysis["top_confusions"][0]["count"] == 2
