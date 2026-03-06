from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from src.agent.phase10_vision import MockFrameRecognizer, build_detection_manifest
from src.agent.phase11_vision_learning import (
    PHASE11_EVAL_SCHEMA_VERSION,
    PHASE11_MODEL_SCHEMA_VERSION,
    compare_phase11_recognizers,
    evaluate_phase11_recognizer_model,
    run_phase11_recognizer_model,
    summarize_phase11_experiment_history,
    train_phase11_recognizer_model,
)
from src.agent.phase9_external import build_video_frame_manifest


def _frame_manifest(tmp_path: Path, *, frame_count: int = 4) -> dict[str, object]:
    return build_video_frame_manifest(
        video_path=tmp_path / "match.mp4",
        output_dir=tmp_path / "frames",
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
                        "bbox": {"x": 0.10, "y": 0.70, "w": 0.12, "h": 0.20},
                        "confidence": 0.95,
                    },
                    {
                        "label": "leader_card",
                        "seat": 2,
                        "bbox": {"x": 0.78, "y": 0.10, "w": 0.12, "h": 0.20},
                        "confidence": 0.94,
                    },
                    {
                        "label": "phase_marker",
                        "seat": None,
                        "phase": "draw" if frame_index % 2 == 0 else "charge",
                        "bbox": {"x": 0.45, "y": 0.02, "w": 0.10, "h": 0.05},
                        "confidence": 0.93,
                    },
                ],
            }
        )
    return build_detection_manifest(
        video_manifest=frame_manifest,
        detections=detections,
        recognizer_name="labeled_reference",
    )


def test_phase11_train_run_eval_compare_shape(tmp_path: Path) -> None:
    labeled = _labeled_manifest(tmp_path)
    frame_manifest = _frame_manifest(tmp_path)
    model = train_phase11_recognizer_model([labeled])
    assert model["schema_version"] == PHASE11_MODEL_SCHEMA_VERSION

    predicted = run_phase11_recognizer_model(model, frame_manifest)
    assert predicted["recognizer_name"] == "phase11_frequency_recognizer"

    trained_eval = evaluate_phase11_recognizer_model(
        model=model,
        frame_manifest=frame_manifest,
        labeled_manifest=labeled,
    )
    assert trained_eval["schema_version"] == PHASE11_EVAL_SCHEMA_VERSION
    assert trained_eval["frame_exact_match_rate"] == 1.0

    baseline_benchmark = evaluate_phase11_recognizer_model(
        model={"model_name": "phase11_frequency_recognizer", "feature_fields": [], "contexts": {}, "global_templates": []},
        frame_manifest=frame_manifest,
        labeled_manifest=labeled,
    )
    comparison = compare_phase11_recognizers(trained_eval=trained_eval, baseline_eval=baseline_benchmark)
    assert comparison["promoted"] is True


def test_phase11_history_summary() -> None:
    summary = summarize_phase11_experiment_history(
        [
            {
                "run_name": "r1",
                "model_name": "m1",
                "frame_exact_match_rate": "0.5",
                "promoted": "fail",
            },
            {
                "run_name": "r2",
                "model_name": "m2",
                "frame_exact_match_rate": "1.0",
                "promoted": "pass",
            },
        ]
    )
    assert summary["total_runs"] == 2
    assert summary["best_run_name"] == "r2"
    assert summary["promoted_rate"] == 0.5


def test_phase11_scripts_and_pipeline(tmp_path: Path) -> None:
    frame_manifest = _frame_manifest(tmp_path)
    labeled = _labeled_manifest(tmp_path)
    train_path = tmp_path / "train.json"
    eval_frame_path = tmp_path / "frame_manifest.json"
    eval_labeled_path = tmp_path / "eval_labeled.json"
    model_path = tmp_path / "model.json"
    detections_path = tmp_path / "detections.json"
    eval_path = tmp_path / "eval.json"
    pipeline_dir = tmp_path / "pipeline"
    report_path = tmp_path / "phase11_report.md"

    train_path.write_text(json.dumps(labeled, indent=2), encoding="utf-8")
    eval_frame_path.write_text(json.dumps(frame_manifest, indent=2), encoding="utf-8")
    eval_labeled_path.write_text(json.dumps(labeled, indent=2), encoding="utf-8")

    train_result = subprocess.run(
        [sys.executable, "scripts/train_phase11_recognizer.py", "--input", str(train_path), "--output", str(model_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert train_result.returncode == 0, train_result.stderr

    run_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase11_recognizer.py",
            "--model",
            str(model_path),
            "--frame-manifest",
            str(eval_frame_path),
            "--output",
            str(detections_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run_result.returncode == 0, run_result.stderr

    eval_result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_phase11_recognizer.py",
            "--model",
            str(model_path),
            "--frame-manifest",
            str(eval_frame_path),
            "--labeled",
            str(eval_labeled_path),
            "--output",
            str(eval_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert eval_result.returncode == 0, eval_result.stderr
    eval_payload = json.loads(eval_path.read_text(encoding="utf-8"))
    assert eval_payload["frame_exact_match_rate"] == 1.0

    pipeline_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase11_training_pipeline.py",
            "--train-input",
            str(train_path),
            "--eval-frame-manifest",
            str(eval_frame_path),
            "--eval-labeled",
            str(eval_labeled_path),
            "--run-name",
            "phase11_test_run",
            "--artifacts-dir",
            str(pipeline_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert pipeline_result.returncode == 0, pipeline_result.stderr
    manifest = json.loads((pipeline_dir / "phase11_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "pass"
    assert manifest["metrics"]["promoted"] is True

    report_result = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase11_closeout_report.py",
            "--manifest",
            str(pipeline_dir / "phase11_manifest.json"),
            "--history-summary",
            str(pipeline_dir / "phase11_history_summary.json"),
            "--output",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert report_result.returncode == 0, report_result.stderr
    assert "# Phase 11 Closeout" in report_path.read_text(encoding="utf-8")
