from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from src.agent.phase10_vision import build_detection_manifest
from src.agent.phase12_visual import export_phase13_real_crop_dataset, render_synthetic_phase12_frames
from src.agent.phase13_visual_learning import (
    PHASE13_CROP_ANNOTATION_SCHEMA_VERSION,
    PHASE13_EVAL_SCHEMA_VERSION,
    PHASE13_MODEL_SCHEMA_VERSION,
    apply_phase13_crop_annotation_review,
    build_phase13_crop_annotation_manifest,
    compare_phase13_visual_models,
    evaluate_phase13_visual_model,
    summarize_phase13_experiment_history,
    train_phase13_visual_model,
)
from src.agent.phase9_external import build_video_frame_manifest


def _frame_manifest(tmp_path: Path, *, frame_count: int = 4) -> dict[str, object]:
    return build_video_frame_manifest(
        video_path=tmp_path / "match.mp4",
        output_dir=tmp_path / "frames_stub",
        every_n_seconds=1.0,
        frame_count=frame_count,
        extracted=False,
        ffmpeg_path="ffmpeg",
    )


def _labeled_manifest(tmp_path: Path) -> dict[str, object]:
    frame_manifest = _frame_manifest(tmp_path)
    detections = []
    for frame in frame_manifest["frames"]:
        assert isinstance(frame, dict)
        frame_index = int(frame["frame_index"])
        detections.append(
            {
                "frame_index": frame_index,
                "timestamp_seconds": float(frame["timestamp_seconds"]),
                "objects": [
                    {
                        "label": "leader_card",
                        "seat": 1,
                        "bbox": {"x": 0.08, "y": 0.68, "w": 0.16, "h": 0.20},
                        "confidence": 0.95,
                    },
                    {
                        "label": "battle_card" if frame_index % 2 == 0 else "unison_card",
                        "seat": 2,
                        "bbox": {"x": 0.72, "y": 0.08, "w": 0.16, "h": 0.20},
                        "confidence": 0.94,
                    },
                    {
                        "label": "phase_marker",
                        "seat": None,
                        "phase": "draw" if frame_index % 2 == 0 else "charge",
                        "bbox": {"x": 0.42, "y": 0.02, "w": 0.14, "h": 0.08},
                        "confidence": 0.93,
                    },
                ],
            }
        )
    return build_detection_manifest(
        video_manifest=frame_manifest,
        detections=detections,
        recognizer_name="phase13_labeled_reference",
    )


def _real_crop_dataset(tmp_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    frame_manifest = _frame_manifest(tmp_path)
    labeled = _labeled_manifest(tmp_path)
    rendered = render_synthetic_phase12_frames(
        frame_manifest=frame_manifest,
        labeled_manifest=labeled,
        output_dir=tmp_path / "rendered",
    )
    dataset = export_phase13_real_crop_dataset(
        frame_manifest=rendered,
        labeled_manifest=labeled,
        crops_output_dir=tmp_path / "crops",
        crop_image_format="ppm",
        validation_ratio=0.25,
    )
    return dataset, labeled


def test_phase13_annotation_bootstrap_and_apply(tmp_path: Path) -> None:
    dataset, _ = _real_crop_dataset(tmp_path)
    annotations = build_phase13_crop_annotation_manifest(dataset)
    assert annotations["schema_version"] == PHASE13_CROP_ANNOTATION_SCHEMA_VERSION
    first = annotations["annotations"][0]
    first["status"] = "reviewed"
    first["notes"] = "checked"
    reviewed = apply_phase13_crop_annotation_review(dataset, annotations)
    assert reviewed["examples"][0]["annotation_status"] == "reviewed"
    assert reviewed["examples"][0]["annotation_notes"] == "checked"


def test_phase13_visual_model_shape(tmp_path: Path) -> None:
    dataset, labeled = _real_crop_dataset(tmp_path)
    annotations = build_phase13_crop_annotation_manifest(dataset)
    reviewed = apply_phase13_crop_annotation_review(dataset, annotations)
    model = train_phase13_visual_model(reviewed, split="all", k_neighbors=1)
    assert model["schema_version"] == PHASE13_MODEL_SCHEMA_VERSION
    trained_eval = evaluate_phase13_visual_model(
        model=model,
        proposal_manifest=labeled,
        labeled_manifest=labeled,
        crop_dataset=reviewed,
    )
    assert trained_eval["schema_version"] == PHASE13_EVAL_SCHEMA_VERSION
    assert trained_eval["frame_exact_match_rate"] == 1.0
    baseline_eval = {
        "model_name": "phase12_visual_centroid",
        "frame_exact_match_rate": 0.0,
        "object_precision": 0.0,
    }
    comparison = compare_phase13_visual_models(trained_eval=trained_eval, baseline_eval=baseline_eval)
    assert comparison["promoted"] is True


def test_phase13_history_summary() -> None:
    summary = summarize_phase13_experiment_history(
        [
            {"run_name": "r1", "model_name": "m1", "frame_exact_match_rate": "0.5", "promoted": "fail"},
            {"run_name": "r2", "model_name": "m2", "frame_exact_match_rate": "1.0", "promoted": "pass"},
        ]
    )
    assert summary["best_run_name"] == "r2"
    assert summary["promoted_rate"] == 0.5


def test_phase13_scripts_and_pipeline(tmp_path: Path) -> None:
    frame_manifest = _frame_manifest(tmp_path)
    labeled = _labeled_manifest(tmp_path)
    frame_manifest_path = tmp_path / "frame_manifest.json"
    labeled_path = tmp_path / "labeled.json"
    phase13_dir = tmp_path / "phase13"
    frame_manifest_path.write_text(json.dumps(frame_manifest, indent=2), encoding="utf-8")
    labeled_path.write_text(json.dumps(labeled, indent=2), encoding="utf-8")

    pipeline_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase13_visual_pipeline.py",
            "--frame-manifest",
            str(frame_manifest_path),
            "--labeled",
            str(labeled_path),
            "--run-name",
            "phase13_test_run",
            "--artifacts-dir",
            str(phase13_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert pipeline_result.returncode == 0, pipeline_result.stderr
    manifest = json.loads((phase13_dir / "phase13_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "pass"
    assert manifest["metrics"]["promoted"] is True

    annotation_bootstrap_result = subprocess.run(
        [
            sys.executable,
            "scripts/bootstrap_phase13_crop_annotations.py",
            "--dataset",
            str(phase13_dir / "phase13_real_crop_dataset.json"),
            "--output",
            str(phase13_dir / "manual_annotations.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert annotation_bootstrap_result.returncode == 0, annotation_bootstrap_result.stderr

    apply_result = subprocess.run(
        [
            sys.executable,
            "scripts/apply_phase13_crop_reviews.py",
            "--dataset",
            str(phase13_dir / "phase13_real_crop_dataset.json"),
            "--annotations",
            str(phase13_dir / "manual_annotations.json"),
            "--output",
            str(phase13_dir / "manual_reviewed_dataset.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert apply_result.returncode == 0, apply_result.stderr

    train_result = subprocess.run(
        [
            sys.executable,
            "scripts/train_phase13_visual_model.py",
            "--dataset",
            str(phase13_dir / "manual_reviewed_dataset.json"),
            "--split",
            "all",
            "--k-neighbors",
            "1",
            "--output",
            str(phase13_dir / "manual_phase13_model.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert train_result.returncode == 0, train_result.stderr

    eval_result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_phase13_visual_model.py",
            "--model",
            str(phase13_dir / "manual_phase13_model.json"),
            "--proposal-manifest",
            str(labeled_path),
            "--labeled",
            str(labeled_path),
            "--dataset",
            str(phase13_dir / "manual_reviewed_dataset.json"),
            "--output",
            str(phase13_dir / "manual_phase13_eval.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert eval_result.returncode == 0, eval_result.stderr
    eval_payload = json.loads((phase13_dir / "manual_phase13_eval.json").read_text(encoding="utf-8"))
    assert eval_payload["frame_exact_match_rate"] == 1.0

    report_result = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase13_closeout_report.py",
            "--manifest",
            str(phase13_dir / "phase13_manifest.json"),
            "--history-summary",
            str(phase13_dir / "phase13_history_summary.json"),
            "--output",
            str(phase13_dir / "phase13_report.md"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert report_result.returncode == 0, report_result.stderr
    assert "# Phase 13 Closeout" in (phase13_dir / "phase13_report.md").read_text(encoding="utf-8")
