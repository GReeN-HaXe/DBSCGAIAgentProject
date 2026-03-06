from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any, Iterable

from src.agent.phase12_visual import (
    PHASE13_REAL_CROP_DATASET_SCHEMA_VERSION,
    read_image,
    write_image,
)


PHASE13_CROP_ANNOTATION_SCHEMA_VERSION = "phase13.crop_annotations.v1"
PHASE13_MODEL_SCHEMA_VERSION = "phase13.visual_histogram_knn.v1"
PHASE13_EVAL_SCHEMA_VERSION = "phase13.visual_eval.v1"


def build_phase13_crop_annotation_manifest(crop_dataset: dict[str, Any]) -> dict[str, Any]:
    examples = crop_dataset.get("examples", [])
    if not isinstance(examples, list):
        examples = []
    items: list[dict[str, Any]] = []
    for index, row in enumerate(examples):
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "annotation_index": index,
                "crop_image_path": str(row.get("crop_image_path", "")),
                "source_image_path": str(row.get("source_image_path", row.get("image_path", ""))),
                "frame_index": int(row.get("frame_index", 0) or 0),
                "object_index": int(row.get("object_index", 0) or 0),
                "current_label": str(row.get("label", "")),
                "current_signature": str(row.get("signature", "")),
                "bbox": dict(row.get("bbox", {})) if isinstance(row.get("bbox"), dict) else {},
                "status": "unreviewed",
                "reviewed_label": str(row.get("label", "")),
                "reviewed_signature": str(row.get("signature", "")),
                "notes": "",
            }
        )
    return {
        "schema_version": PHASE13_CROP_ANNOTATION_SCHEMA_VERSION,
        "example_count": len(items),
        "annotations": items,
    }


def apply_phase13_crop_annotation_review(
    crop_dataset: dict[str, Any],
    annotation_manifest: dict[str, Any],
) -> dict[str, Any]:
    examples = crop_dataset.get("examples", [])
    annotations = annotation_manifest.get("annotations", [])
    if not isinstance(examples, list):
        examples = []
    if not isinstance(annotations, list):
        annotations = []
    reviewed_examples = [dict(row) for row in examples if isinstance(row, dict)]
    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue
        try:
            index = int(annotation.get("annotation_index", -1))
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= len(reviewed_examples):
            continue
        row = dict(reviewed_examples[index])
        reviewed_label = str(annotation.get("reviewed_label", row.get("label", "")))
        reviewed_signature = str(annotation.get("reviewed_signature", row.get("signature", "")))
        status = str(annotation.get("status", "unreviewed"))
        row.update(
            {
                "label": reviewed_label,
                "signature": reviewed_signature,
                "annotation_status": status,
                "annotation_notes": str(annotation.get("notes", "")),
            }
        )
        reviewed_examples[index] = row
    return {**crop_dataset, "examples": reviewed_examples}


def _patch_grid_features(image: dict[str, Any], *, grid_size: int = 2) -> dict[str, float]:
    pixels = image.get("pixels", [])
    width = int(image.get("width", 0) or 0)
    height = int(image.get("height", 0) or 0)
    if not isinstance(pixels, list) or width <= 0 or height <= 0:
        return {}
    features: dict[str, float] = {}
    for gy in range(grid_size):
        for gx in range(grid_size):
            x0 = int(gx * width / grid_size)
            x1 = max(x0 + 1, int((gx + 1) * width / grid_size))
            y0 = int(gy * height / grid_size)
            y1 = max(y0 + 1, int((gy + 1) * height / grid_size))
            bucket: list[tuple[int, int, int]] = []
            for y in range(y0, min(y1, height)):
                row = pixels[y]
                if not isinstance(row, list):
                    continue
                for x in range(x0, min(x1, width)):
                    bucket.append(row[x])
            count = len(bucket) or 1
            features[f"patch_{gy}_{gx}_r"] = sum(rgb[0] for rgb in bucket) / count
            features[f"patch_{gy}_{gx}_g"] = sum(rgb[1] for rgb in bucket) / count
            features[f"patch_{gy}_{gx}_b"] = sum(rgb[2] for rgb in bucket) / count
    return features


def _histogram_features(image: dict[str, Any], *, bins: int = 4) -> dict[str, float]:
    pixels = image.get("pixels", [])
    if not isinstance(pixels, list):
        return {}
    channel_values = {"r": [], "g": [], "b": []}
    for row in pixels:
        if not isinstance(row, list):
            continue
        for r, g, b in row:
            channel_values["r"].append(r)
            channel_values["g"].append(g)
            channel_values["b"].append(b)
    features: dict[str, float] = {}
    step = 256 / bins
    for channel, values in channel_values.items():
        total = len(values) or 1
        counts = [0 for _ in range(bins)]
        for value in values:
            index = min(bins - 1, int(value // step))
            counts[index] += 1
        for idx, count in enumerate(counts):
            features[f"hist_{channel}_{idx}"] = count / total
    return features


def extract_phase13_visual_features(crop_image_path: Path) -> dict[str, float]:
    image = read_image(crop_image_path)
    features: dict[str, float] = {}
    features.update(_patch_grid_features(image))
    features.update(_histogram_features(image))
    return features


def enrich_phase13_crop_dataset_features(crop_dataset: dict[str, Any]) -> dict[str, Any]:
    examples = crop_dataset.get("examples", [])
    if not isinstance(examples, list):
        examples = []
    enriched: list[dict[str, Any]] = []
    for row in examples:
        if not isinstance(row, dict):
            continue
        crop_image_path = Path(str(row.get("crop_image_path", "")))
        if crop_image_path.exists():
            row = {
                **row,
                "visual_features": extract_phase13_visual_features(crop_image_path),
            }
        enriched.append(row)
    return {**crop_dataset, "examples": enriched}


def _filtered_examples(dataset: dict[str, Any], split: str) -> list[dict[str, Any]]:
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        return []
    return [row for row in examples if isinstance(row, dict) and (split == "all" or row.get("split") == split)]


def train_phase13_visual_model(
    crop_dataset: dict[str, Any],
    *,
    split: str = "train",
    k_neighbors: int = 3,
) -> dict[str, Any]:
    dataset = enrich_phase13_crop_dataset_features(crop_dataset)
    examples = _filtered_examples(dataset, split)
    train_rows: list[dict[str, Any]] = []
    label_counts: Counter[str] = Counter()
    for row in examples:
        features = row.get("visual_features", {})
        signature = str(row.get("signature", ""))
        if not signature or not isinstance(features, dict):
            continue
        train_rows.append(
            {
                "signature": signature,
                "label": str(row.get("label", "")),
                "crop_image_path": str(row.get("crop_image_path", "")),
                "visual_features": {str(key): float(value) for key, value in features.items()},
            }
        )
        label_counts[signature] += 1
    return {
        "schema_version": PHASE13_MODEL_SCHEMA_VERSION,
        "model_name": "phase13_visual_histogram_knn",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "train_split": str(split),
        "example_count": len(train_rows),
        "k_neighbors": int(k_neighbors),
        "global_majority_signature": "" if not label_counts else sorted(label_counts.items(), key=lambda item: (-item[1], item[0]))[0][0],
        "feature_keys": sorted(train_rows[0]["visual_features"].keys()) if train_rows else [],
        "examples": train_rows,
    }


def _feature_distance(a: dict[str, float], b: dict[str, float], keys: list[str]) -> float:
    return math.sqrt(sum((float(a.get(key, 0.0)) - float(b.get(key, 0.0))) ** 2 for key in keys))


def predict_phase13_visual_signature(model: dict[str, Any], crop_image_path: Path) -> tuple[str, float]:
    rows = model.get("examples", [])
    keys = [str(key) for key in model.get("feature_keys", [])] if isinstance(model.get("feature_keys", []), list) else []
    if not isinstance(rows, list) or not rows or not keys:
        return str(model.get("global_majority_signature", "")), 0.0
    sample = extract_phase13_visual_features(crop_image_path)
    ranked: list[tuple[float, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        features = row.get("visual_features", {})
        if not isinstance(features, dict):
            continue
        signature = str(row.get("signature", ""))
        ranked.append((_feature_distance(sample, {str(k): float(v) for k, v in features.items()}, keys), signature))
    ranked.sort(key=lambda item: (item[0], item[1]))
    k = max(1, int(model.get("k_neighbors", 3) or 3))
    nearest = ranked[:k]
    votes = Counter(signature for _, signature in nearest)
    if not nearest or not votes:
        return str(model.get("global_majority_signature", "")), 0.0
    best_signature = sorted(votes.items(), key=lambda item: (-item[1], item[0]))[0][0]
    avg_distance = sum(distance for distance, _ in nearest) / len(nearest)
    confidence = max(0.0, 1.0 - (avg_distance / max(1.0, math.sqrt(len(keys)) * 255.0)))
    return best_signature, confidence


def _signature_to_object(signature: str, *, bbox: dict[str, Any], confidence: float) -> dict[str, Any]:
    parts = signature.split("|")
    label = parts[0] if parts else ""
    seat = None
    if len(parts) > 1 and parts[1] != "":
        seat = int(parts[1])
    phase = parts[2] if len(parts) > 2 and parts[2] != "" else None
    obj: dict[str, Any] = {
        "label": label,
        "seat": seat,
        "bbox": dict(bbox),
        "confidence": float(confidence),
    }
    if phase is not None:
        obj["phase"] = phase
    return obj


def run_phase13_visual_model(
    *,
    model: dict[str, Any],
    proposal_manifest: dict[str, Any],
    crop_dataset: dict[str, Any],
) -> dict[str, Any]:
    examples = crop_dataset.get("examples", [])
    if not isinstance(examples, list):
        examples = []
    frame_rows: dict[int, list[dict[str, Any]]] = {}
    timestamps: dict[int, float] = {}
    for row in examples:
        if not isinstance(row, dict):
            continue
        frame_index = int(row.get("frame_index", 0) or 0)
        bbox = row.get("bbox", {})
        crop_path = Path(str(row.get("crop_image_path", "")))
        if not isinstance(bbox, dict) or not crop_path.exists():
            continue
        signature, confidence = predict_phase13_visual_signature(model, crop_path)
        frame_rows.setdefault(frame_index, []).append(_signature_to_object(signature, bbox=bbox, confidence=confidence))
    detections = proposal_manifest.get("detections", [])
    if isinstance(detections, list):
        for frame in detections:
            if isinstance(frame, dict):
                timestamps[int(frame.get("frame_index", 0) or 0)] = float(frame.get("timestamp_seconds", 0.0) or 0.0)
    predicted = [
        {
            "frame_index": frame_index,
            "timestamp_seconds": timestamps.get(frame_index, 0.0),
            "objects": frame_rows[frame_index],
        }
        for frame_index in sorted(frame_rows.keys())
    ]
    video_manifest = {
        "video_path": str(crop_dataset.get("crops_output_dir", "")),
        "frame_count": len(predicted),
    }
    from src.agent.phase10_vision import build_detection_manifest

    return build_detection_manifest(
        video_manifest=video_manifest,
        detections=predicted,
        recognizer_name=str(model.get("model_name", "phase13_visual_histogram_knn")),
    )


def evaluate_phase13_visual_model(
    *,
    model: dict[str, Any],
    proposal_manifest: dict[str, Any],
    labeled_manifest: dict[str, Any],
    crop_dataset: dict[str, Any],
) -> dict[str, Any]:
    from src.agent.phase10_vision import benchmark_detection_manifest

    predicted = run_phase13_visual_model(
        model=model,
        proposal_manifest=proposal_manifest,
        crop_dataset=crop_dataset,
    )
    benchmark = benchmark_detection_manifest(predicted, labeled_manifest)
    return {
        "schema_version": PHASE13_EVAL_SCHEMA_VERSION,
        "model_name": str(model.get("model_name", "")),
        "frame_count": int(benchmark.get("frame_count", 0) or 0),
        "object_precision": float(benchmark.get("object_precision", 0.0) or 0.0),
        "object_recall": float(benchmark.get("object_recall", 0.0) or 0.0),
        "frame_exact_match_rate": float(benchmark.get("frame_exact_match_rate", 0.0) or 0.0),
        "benchmark": benchmark,
    }


def compare_phase13_visual_models(*, trained_eval: dict[str, Any], baseline_eval: dict[str, Any]) -> dict[str, Any]:
    trained_exact = float(trained_eval.get("frame_exact_match_rate", 0.0) or 0.0)
    baseline_exact = float(baseline_eval.get("frame_exact_match_rate", 0.0) or 0.0)
    trained_precision = float(trained_eval.get("object_precision", 0.0) or 0.0)
    baseline_precision = float(baseline_eval.get("object_precision", 0.0) or 0.0)
    return {
        "schema_version": "phase13.compare.v1",
        "trained_model_name": str(trained_eval.get("model_name", "")),
        "baseline_model_name": str(baseline_eval.get("model_name", "")),
        "trained_frame_exact_match_rate": trained_exact,
        "baseline_frame_exact_match_rate": baseline_exact,
        "trained_object_precision": trained_precision,
        "baseline_object_precision": baseline_precision,
        "frame_exact_match_lift": trained_exact - baseline_exact,
        "object_precision_lift": trained_precision - baseline_precision,
        "promoted": trained_exact >= baseline_exact,
    }


@dataclass(frozen=True)
class Phase13ExperimentHistoryRow:
    timestamp_utc: str
    run_name: str
    model_name: str
    frame_exact_match_rate: float
    object_precision: float
    object_recall: float
    promoted: str
    manifest_path: str


def build_phase13_experiment_history_row(
    *,
    run_name: str,
    model_name: str,
    frame_exact_match_rate: float,
    object_precision: float,
    object_recall: float,
    promoted: bool,
    manifest_path: str,
) -> Phase13ExperimentHistoryRow:
    return Phase13ExperimentHistoryRow(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        run_name=str(run_name),
        model_name=str(model_name),
        frame_exact_match_rate=float(frame_exact_match_rate),
        object_precision=float(object_precision),
        object_recall=float(object_recall),
        promoted="pass" if promoted else "fail",
        manifest_path=str(manifest_path),
    )


def phase13_experiment_history_row_to_dict(row: Phase13ExperimentHistoryRow) -> dict[str, str]:
    return {
        "timestamp_utc": row.timestamp_utc,
        "run_name": row.run_name,
        "model_name": row.model_name,
        "frame_exact_match_rate": str(row.frame_exact_match_rate),
        "object_precision": str(row.object_precision),
        "object_recall": str(row.object_recall),
        "promoted": row.promoted,
        "manifest_path": row.manifest_path,
    }


def summarize_phase13_experiment_history(rows: Iterable[dict[str, str]], *, recent_window: int = 20) -> dict[str, Any]:
    items = list(rows)
    recent = items[-max(1, int(recent_window)) :] if items else []

    def _f(item: dict[str, str], key: str) -> float:
        try:
            return float(item.get(key, "0"))
        except (TypeError, ValueError):
            return 0.0

    best = max(items, key=lambda item: _f(item, "frame_exact_match_rate"), default=None)
    latest = items[-1] if items else None
    recent_avg = (sum(_f(item, "frame_exact_match_rate") for item in recent) / len(recent)) if recent else 0.0
    promoted_rate = (
        sum(1 for item in items if str(item.get("promoted", "")).strip().lower() == "pass") / len(items)
        if items
        else 0.0
    )
    return {
        "total_runs": len(items),
        "recent_window": len(recent),
        "recent_avg_frame_exact_match_rate": recent_avg,
        "promoted_rate": promoted_rate,
        "latest_run_name": "" if latest is None else str(latest.get("run_name", "")),
        "latest_model_name": "" if latest is None else str(latest.get("model_name", "")),
        "latest_frame_exact_match_rate": 0.0 if latest is None else _f(latest, "frame_exact_match_rate"),
        "best_run_name": "" if best is None else str(best.get("run_name", "")),
        "best_model_name": "" if best is None else str(best.get("model_name", "")),
        "best_frame_exact_match_rate": 0.0 if best is None else _f(best, "frame_exact_match_rate"),
    }
