from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from src.agent.phase10_vision import (
    PHASE10_BENCHMARK_SCHEMA_VERSION,
    PHASE10_DETECTION_SCHEMA_VERSION,
    PHASE10_EVENT_SCHEMA_VERSION,
    PHASE10_IDENTITY_ENRICHMENT_SCHEMA_VERSION,
    PHASE10_REVIEW_SCHEMA_VERSION,
    MockFrameRecognizer,
    apply_detection_review,
    benchmark_detection_manifest,
    enrich_detections_with_phase15_identity,
    infer_events_from_detections,
    reviewed_detections_to_external_match,
)
from src.agent.phase10_history import summarize_phase10_benchmark_history
from src.agent.phase13_visual_learning import build_phase13_feature_cache, build_phase13_reference_image_dataset
from src.agent.phase15_metric import evaluate_phase15_triplet_retrieval, has_torch_support, train_phase15_triplet_model
from src.agent.phase9_external import build_video_frame_manifest


def _frame_manifest(tmp_path) -> dict[str, object]:
    return build_video_frame_manifest(
        video_path=tmp_path / "match.mp4",
        output_dir=tmp_path / "frames",
        every_n_seconds=1.0,
        frame_count=3,
        extracted=False,
        ffmpeg_path="ffmpeg",
    )


def _write_ppm(path: Path, color: tuple[int, int, int]) -> None:
    pixel = f"{color[0]} {color[1]} {color[2]}"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join([((pixel + " ") * 8).rstrip() for _ in range(8)])
    path.write_text(f"P3\n8 8\n255\n{rows}\n", encoding="utf-8")


def _build_phase15_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    images = []
    for index, color in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255)), start=1):
        path = tmp_path / f"BT1-00{index}.ppm"
        _write_ppm(path, color)
        images.append(path)
    manifest = {
        "schema_version": "card_image_reference_manifest.v1",
        "cards": [
            {
                "card_number": f"BT1-00{index}",
                "primary_image_path": str(path),
                "card_name": f"Card {index}",
                "table_name": "cards",
                "record_id": index,
                "image_count": 1,
                "match_type": "exact_stem",
            }
            for index, path in enumerate(images, start=1)
        ],
    }
    dataset = build_phase13_feature_cache(
        build_phase13_reference_image_dataset(
            manifest,
            split_mode="paired_views",
            train_views=("original", "flip_h"),
            validation_views=("darken",),
        )
    )
    model = train_phase15_triplet_model(dataset, epochs=1, steps_per_epoch=2, batch_size=2, hidden_dim=8, embedding_dim=4)
    _ = evaluate_phase15_triplet_retrieval(model, dataset, gallery_split="train", query_split="validation", top_k_values=(1, 2))
    production_dir = tmp_path / "phase15_production"
    production_dir.mkdir(parents=True, exist_ok=True)
    model_path = production_dir / "phase15_triplet_model.json"
    feature_cache_path = tmp_path / "feature_cache.json"
    summary_path = production_dir / "phase15_production_summary.json"
    model_path.write_text(json.dumps(model, indent=2), encoding="utf-8")
    feature_cache_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps({"feature_cache_path": str(feature_cache_path)}, indent=2), encoding="utf-8")
    return production_dir, model_path, feature_cache_path


def _frame_manifest_with_images(tmp_path) -> dict[str, object]:
    manifest = build_video_frame_manifest(
        video_path=tmp_path / "match.mp4",
        output_dir=tmp_path / "frames_out",
        every_n_seconds=1.0,
        frame_count=2,
        extracted=True,
        ffmpeg_path="ffmpeg",
    )
    for frame, color in zip(manifest["frames"], ((255, 0, 0), (0, 255, 0)), strict=False):
        relative = Path(str(frame["relative_path"])).with_suffix(".ppm")
        frame["relative_path"] = str(relative)
        _write_ppm((tmp_path / "frames_out" / relative), color)
    return manifest


def test_phase10_mock_recognizer_and_event_inference_shape(tmp_path) -> None:
    manifest = _frame_manifest(tmp_path)
    recognizer = MockFrameRecognizer()
    detections = recognizer.detect(manifest)
    assert detections["schema_version"] == PHASE10_DETECTION_SCHEMA_VERSION
    assert len(detections["detections"]) == 3
    inferred = infer_events_from_detections(detections)
    assert inferred["schema_version"] == PHASE10_EVENT_SCHEMA_VERSION
    assert inferred["event_count"] == 3


def test_phase10_recognizer_and_infer_scripts(tmp_path) -> None:
    frame_manifest_path = tmp_path / "frame_manifest.json"
    detection_path = tmp_path / "detections.json"
    events_path = tmp_path / "events.json"
    frame_manifest_path.write_text(json.dumps(_frame_manifest(tmp_path), indent=2), encoding="utf-8")

    detect_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase10_mock_recognizer.py",
            "--frame-manifest",
            str(frame_manifest_path),
            "--output",
            str(detection_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert detect_result.returncode == 0, detect_result.stderr
    detections = json.loads(detection_path.read_text(encoding="utf-8"))
    assert detections["schema_version"] == PHASE10_DETECTION_SCHEMA_VERSION

    infer_result = subprocess.run(
        [
            sys.executable,
            "scripts/infer_phase10_events.py",
            "--detection-manifest",
            str(detection_path),
            "--output",
            str(events_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert infer_result.returncode == 0, infer_result.stderr
    events = json.loads(events_path.read_text(encoding="utf-8"))
    assert events["schema_version"] == PHASE10_EVENT_SCHEMA_VERSION
    assert events["event_count"] == 3


def test_phase10_review_convert_and_benchmark_shape(tmp_path) -> None:
    manifest = _frame_manifest(tmp_path)
    detections = MockFrameRecognizer().detect(manifest)
    reviewed = apply_detection_review(
        detections,
        corrections=[
            {
                "frame_index": 0,
                "object_index": 2,
                "updates": {"phase": "draw"},
            }
        ],
        reviewer="qa",
        notes="fixed phase marker",
    )
    assert reviewed["review"]["schema_version"] == PHASE10_REVIEW_SCHEMA_VERSION
    assert reviewed["detections"][0]["objects"][2]["phase"] == "draw"

    external_match = reviewed_detections_to_external_match(
        reviewed,
        match_id="ext_phase10_001",
        source_name="phase10_test",
        reviewer="qa",
    )
    assert external_match["schema_version"] == "phase9.external_match.v1"
    assert external_match["source_type"] == "phase10_detection_review"
    assert external_match["review"]["review_status"] == "reviewed"

    benchmark = benchmark_detection_manifest(reviewed, reviewed)
    assert benchmark["schema_version"] == PHASE10_BENCHMARK_SCHEMA_VERSION
    assert benchmark["frame_exact_match_rate"] == 1.0


def test_phase10_identity_enrichment_shape(tmp_path) -> None:
    if not has_torch_support():
        return
    production_dir, model_path, feature_cache_path = _build_phase15_fixture(tmp_path)
    manifest = _frame_manifest_with_images(tmp_path)
    detections = MockFrameRecognizer().detect(manifest)
    enriched = enrich_detections_with_phase15_identity(
        detections,
        frame_manifest=manifest,
        crops_output_dir=tmp_path / "identity_crops",
        crop_image_format="ppm",
        top_k=2,
        production_dir=production_dir,
        model_path=model_path,
        feature_cache_path=feature_cache_path,
    )
    assert enriched["identity_enrichment"]["schema_version"] == PHASE10_IDENTITY_ENRICHMENT_SCHEMA_VERSION
    assert enriched["identity_enrichment"]["enriched_object_count"] >= 2
    leader = enriched["detections"][0]["objects"][0]
    assert leader["resolved_signature"] == "BT1-001"
    assert len(leader["identity_candidates"]) == 2
    inferred = infer_events_from_detections(enriched)
    assert inferred["events"][0]["zone_snapshot"]["1"]["detected_objects"][0]["resolved_signature"] == "BT1-001"


def test_phase10_review_supports_add_remove_operations(tmp_path) -> None:
    detections = MockFrameRecognizer().detect(_frame_manifest(tmp_path))
    reviewed = apply_detection_review(
        detections,
        corrections=[
            {
                "frame_index": 1,
                "operation": "add",
                "object": {
                    "label": "battle_card",
                    "seat": 1,
                    "bbox": {"x": 0.2, "y": 0.3, "w": 0.1, "h": 0.2},
                    "confidence": 0.9,
                },
            },
            {
                "frame_index": 1,
                "object_index": 0,
                "operation": "remove",
            },
        ],
        reviewer="qa",
    )
    labels = [obj["label"] for obj in reviewed["detections"][1]["objects"]]
    assert "battle_card" in labels
    assert labels.count("leader_card") == 1


def test_phase10_review_convert_and_benchmark_scripts(tmp_path) -> None:
    frame_manifest_path = tmp_path / "frame_manifest.json"
    detections_path = tmp_path / "detections.json"
    reviewed_path = tmp_path / "reviewed_detections.json"
    external_match_path = tmp_path / "external_match.json"
    benchmark_path = tmp_path / "benchmark.json"
    corrections_path = tmp_path / "corrections.json"

    frame_manifest_path.write_text(json.dumps(_frame_manifest(tmp_path), indent=2), encoding="utf-8")
    corrections_path.write_text(
        json.dumps(
            [
                {
                    "frame_index": 0,
                    "object_index": 2,
                    "updates": {"phase": "draw"},
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    detect_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase10_mock_recognizer.py",
            "--frame-manifest",
            str(frame_manifest_path),
            "--output",
            str(detections_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert detect_result.returncode == 0, detect_result.stderr

    review_result = subprocess.run(
        [
            sys.executable,
            "scripts/review_phase10_detections.py",
            "--input",
            str(detections_path),
            "--corrections",
            str(corrections_path),
            "--reviewer",
            "qa",
            "--output",
            str(reviewed_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert review_result.returncode == 0, review_result.stderr
    reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
    assert reviewed["review"]["schema_version"] == PHASE10_REVIEW_SCHEMA_VERSION

    convert_result = subprocess.run(
        [
            sys.executable,
            "scripts/convert_phase10_reviewed_to_external_match.py",
            "--input",
            str(reviewed_path),
            "--match-id",
            "ext_phase10_script_001",
            "--source-name",
            "phase10_script",
            "--output",
            str(external_match_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert convert_result.returncode == 0, convert_result.stderr
    external_match = json.loads(external_match_path.read_text(encoding="utf-8"))
    assert external_match["schema_version"] == "phase9.external_match.v1"

    benchmark_result = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_phase10_recognizer.py",
            "--predicted",
            str(reviewed_path),
            "--labeled",
            str(reviewed_path),
            "--output",
            str(benchmark_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert benchmark_result.returncode == 0, benchmark_result.stderr
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    assert benchmark["schema_version"] == PHASE10_BENCHMARK_SCHEMA_VERSION
    assert benchmark["frame_exact_match_rate"] == 1.0


def test_phase10_pipeline_history_and_closeout_scripts(tmp_path) -> None:
    frame_manifest_path = tmp_path / "frame_manifest.json"
    labeled_path = tmp_path / "labeled.json"
    corrections_path = tmp_path / "corrections.json"
    artifacts_dir = tmp_path / "phase10_pipeline"
    history_summary_path = artifacts_dir / "phase10_benchmark_history_summary.json"
    report_path = tmp_path / "phase10_closeout.md"

    manifest = _frame_manifest(tmp_path)
    frame_manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    labeled_path.write_text(json.dumps(MockFrameRecognizer().detect(manifest), indent=2), encoding="utf-8")
    corrections_path.write_text(
        json.dumps([{"frame_index": 0, "object_index": 2, "operation": "update", "updates": {"phase": "draw"}}], indent=2),
        encoding="utf-8",
    )

    pipeline_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase10_pipeline.py",
            "--frame-manifest",
            str(frame_manifest_path),
            "--corrections",
            str(corrections_path),
            "--match-id",
            "phase10_pipeline_001",
            "--labeled-detections",
            str(labeled_path),
            "--artifacts-dir",
            str(artifacts_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert pipeline_result.returncode == 0, pipeline_result.stderr
    pipeline_manifest = json.loads((artifacts_dir / "phase10_pipeline_manifest.json").read_text(encoding="utf-8"))
    assert pipeline_manifest["status"] == "pass"
    assert Path(pipeline_manifest["artifacts"]["phase7_dataset"]).exists()

    history_summary = json.loads(history_summary_path.read_text(encoding="utf-8"))
    assert history_summary["total_runs"] == 1
    assert summarize_phase10_benchmark_history(
        [
            {
                "run_name": "r1",
                "recognizer_name": "mock_frame_recognizer",
                "frame_exact_match_rate": "1.0",
                "object_precision": "1.0",
                "object_recall": "1.0",
                "status": "pass",
            }
        ]
    )["best_frame_exact_match_rate"] == 1.0

    report_result = subprocess.run(
        [
            sys.executable,
            "scripts/render_phase10_closeout_report.py",
            "--pipeline-manifest",
            str(artifacts_dir / "phase10_pipeline_manifest.json"),
            "--history-summary",
            str(history_summary_path),
            "--output",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert report_result.returncode == 0, report_result.stderr
    report_text = report_path.read_text(encoding="utf-8")
    assert "# Phase 10 Closeout" in report_text


def test_phase10_pipeline_optional_identity_enrichment(tmp_path) -> None:
    if not has_torch_support():
        return
    _production_dir, model_path, feature_cache_path = _build_phase15_fixture(tmp_path)
    frame_manifest_path = tmp_path / "frame_manifest_identity.json"
    labeled_path = tmp_path / "labeled_identity.json"
    corrections_path = tmp_path / "corrections_identity.json"
    artifacts_dir = tmp_path / "phase10_pipeline_identity"

    manifest = _frame_manifest_with_images(tmp_path)
    frame_manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    labeled_path.write_text(json.dumps(MockFrameRecognizer().detect(manifest), indent=2), encoding="utf-8")
    corrections_path.write_text(json.dumps([], indent=2), encoding="utf-8")

    pipeline_result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase10_pipeline.py",
            "--frame-manifest",
            str(frame_manifest_path),
            "--corrections",
            str(corrections_path),
            "--match-id",
            "phase10_pipeline_identity_001",
            "--labeled-detections",
            str(labeled_path),
            "--artifacts-dir",
            str(artifacts_dir),
            "--enable-phase15-identity",
            "--identity-top-k",
            "2",
            "--identity-model",
            str(model_path),
            "--identity-feature-cache",
            str(feature_cache_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert pipeline_result.returncode == 0, pipeline_result.stderr
    pipeline_manifest = json.loads((artifacts_dir / "phase10_pipeline_manifest.json").read_text(encoding="utf-8"))
    assert pipeline_manifest["identity_summary"]["enriched_object_count"] >= 2
    enriched_payload = json.loads((artifacts_dir / "phase10_identity_enriched_detections.json").read_text(encoding="utf-8"))
    assert enriched_payload["detections"][0]["objects"][0]["resolved_signature"] == "BT1-001"
