from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from src.agent.phase10_vision import MockFrameRecognizer, build_detection_manifest
from src.agent.phase12_visual import (
    PHASE12_CROP_DATASET_SCHEMA_VERSION,
    PHASE12_EVAL_SCHEMA_VERSION,
    PHASE12_MODEL_SCHEMA_VERSION,
    PHASE12_SUPPORTED_IMAGE_SUFFIXES,
    build_phase12_crop_dataset,
    compare_phase12_visual_models,
    evaluate_phase12_visual_model,
    has_pillow_support,
    read_image,
    read_ppm_image,
    render_synthetic_phase12_frames,
    run_phase12_visual_model,
    summarize_phase12_experiment_history,
    train_phase12_visual_model,
    write_image,
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
        recognizer_name="phase12_labeled_reference",
    )


def test_phase12_render_dataset_train_eval_shape(tmp_path: Path) -> None:
    frame_manifest = _frame_manifest(tmp_path)
    labeled = _labeled_manifest(tmp_path)
    rendered = render_synthetic_phase12_frames(
        frame_manifest=frame_manifest,
        labeled_manifest=labeled,
        output_dir=tmp_path / "rendered",
    )
    first_frame_path = Path(rendered["output_dir"]) / Path(rendered["frames"][0]["relative_path"])
    image = read_ppm_image(first_frame_path)
    assert image["width"] == 64

    dataset = build_phase12_crop_dataset(
        frame_manifest=rendered,
        labeled_manifest=labeled,
        validation_ratio=0.25,
    )
    assert dataset["schema_version"] == PHASE12_CROP_DATASET_SCHEMA_VERSION
    assert dataset["example_count"] == 12

    model = train_phase12_visual_model(dataset, split="all")
    assert model["schema_version"] == PHASE12_MODEL_SCHEMA_VERSION
    predicted = run_phase12_visual_model(
        model=model,
        frame_manifest=rendered,
        proposal_manifest=labeled,
    )
    assert predicted["recognizer_name"] == "phase12_visual_centroid"

    trained_eval = evaluate_phase12_visual_model(
        model=model,
        frame_manifest=rendered,
        proposal_manifest=labeled,
        labeled_manifest=labeled,
    )
    assert trained_eval["schema_version"] == PHASE12_EVAL_SCHEMA_VERSION
    assert trained_eval["frame_exact_match_rate"] == 1.0

    baseline_benchmark = evaluate_phase12_visual_model(
        model={"model_name": "empty", "centroids": {}},
        frame_manifest=rendered,
        proposal_manifest=labeled,
        labeled_manifest=labeled,
    )
    comparison = compare_phase12_visual_models(trained_eval=trained_eval, baseline_eval=baseline_benchmark)
    assert comparison["promoted"] is True


def test_phase13_step1_real_image_support_api(tmp_path: Path) -> None:
    assert ".png" in PHASE12_SUPPORTED_IMAGE_SUFFIXES
    ppm_path = tmp_path / "sample.ppm"
    write_image(
        ppm_path,
        width=2,
        height=1,
        pixels=[[(255, 0, 0), (0, 255, 0)]],
    )
    ppm_image = read_image(ppm_path)
    assert ppm_image["width"] == 2

    if has_pillow_support():
        png_path = tmp_path / "sample.png"
        write_image(
            png_path,
            width=2,
            height=1,
            pixels=[[(10, 20, 30), (40, 50, 60)]],
        )
        png_image = read_image(png_path)
        assert png_image["width"] == 2
        assert png_image["pixels"][0][0] == (10, 20, 30)


def test_phase12_history_summary() -> None:
    summary = summarize_phase12_experiment_history(
        [
            {"run_name": "r1", "model_name": "m1", "frame_exact_match_rate": "0.4", "promoted": "fail"},
            {"run_name": "r2", "model_name": "m2", "frame_exact_match_rate": "0.9", "promoted": "pass"},
        ]
    )
    assert summary["best_run_name"] == "r2"
    assert summary["promoted_rate"] == 0.5


def test_phase12_scripts_and_pipeline(tmp_path: Path) -> None:
    frame_manifest = _frame_manifest(tmp_path)
    labeled = _labeled_manifest(tmp_path)
    frame_manifest_path = tmp_path / "frame_manifest.json"
    labeled_path = tmp_path / "labeled.json"
    rendered_manifest_path = tmp_path / "rendered_manifest.json"
    dataset_path = tmp_path / "crop_dataset.json"
    model_path = tmp_path / "visual_model.json"
    prediction_path = tmp_path / "predictions.json"
    eval_path = tmp_path / "eval.json"
    pipeline_dir = tmp_path / "pipeline"
    report_path = tmp_path / "phase12_report.md"

    frame_manifest_path.write_text(json.dumps(frame_manifest, indent=2), encoding="utf-8")
    labeled_path.write_text(json.dumps(labeled, indent=2), encoding="utf-8")

    render_result = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase12_synthetic_frames.py",
            "--frame-manifest",
            str(frame_manifest_path),
            "--labeled",
            str(labeled_path),
            "--output-dir",
            str(tmp_path / "rendered"),
            "--manifest-output",
            str(rendered_manifest_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert render_result.returncode == 0, render_result.stderr

    dataset_result = subprocess.run(
        [
            sys.executable,
            "scripts/build_phase12_crop_dataset.py",
            "--frame-manifest",
            str(rendered_manifest_path),
            "--labeled",
            str(labeled_path),
            "--output",
            str(dataset_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert dataset_result.returncode == 0, dataset_result.stderr

    train_result = subprocess.run(
        [sys.executable, "scripts/train_phase12_visual_model.py", "--dataset", str(dataset_path), "--split", "all", "--output", str(model_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert train_result.returncode == 0, train_result.stderr

    run_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase12_visual_classifier.py",
            "--model",
            str(model_path),
            "--frame-manifest",
            str(rendered_manifest_path),
            "--proposal-manifest",
            str(labeled_path),
            "--output",
            str(prediction_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run_result.returncode == 0, run_result.stderr

    eval_result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_phase12_visual_model.py",
            "--model",
            str(model_path),
            "--frame-manifest",
            str(rendered_manifest_path),
            "--proposal-manifest",
            str(labeled_path),
            "--labeled",
            str(labeled_path),
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
            "scripts/run_phase12_visual_pipeline.py",
            "--frame-manifest",
            str(frame_manifest_path),
            "--train-labeled",
            str(labeled_path),
            "--eval-labeled",
            str(labeled_path),
            "--run-name",
            "phase12_test_run",
            "--artifacts-dir",
            str(pipeline_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert pipeline_result.returncode == 0, pipeline_result.stderr
    manifest = json.loads((pipeline_dir / "phase12_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "pass"
    assert manifest["metrics"]["promoted"] is True

    report_result = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase12_closeout_report.py",
            "--manifest",
            str(pipeline_dir / "phase12_manifest.json"),
            "--history-summary",
            str(pipeline_dir / "phase12_history_summary.json"),
            "--output",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert report_result.returncode == 0, report_result.stderr
    assert "# Phase 12 Closeout" in report_path.read_text(encoding="utf-8")

    rendered_manifest = json.loads(rendered_manifest_path.read_text(encoding="utf-8"))
    baseline = MockFrameRecognizer().detect(rendered_manifest)
    assert baseline["schema_version"] == "phase10.detections.v1"
