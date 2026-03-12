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
PHASE13_REFERENCE_DATASET_SCHEMA_VERSION = "phase13.reference_image_dataset.v1"
PHASE13_MODEL_SCHEMA_VERSION = "phase13.visual_histogram_knn.v1"
PHASE13_EVAL_SCHEMA_VERSION = "phase13.visual_eval.v1"
PHASE13_FEATURE_CACHE_SCHEMA_VERSION = "phase13.feature_cache.v1"
PHASE13_TARGET_OBJECT_ROLE = "object_role"
PHASE13_TARGET_CARD_IDENTITY = "card_identity"
DEFAULT_PHASE13_FEATURE_CONFIG = {
    "patch_grid_size": 2,
    "hist_bins": 4,
    "gray_hist_bins": 8,
    "edge_grid_size": 2,
    "enable_rgb_patch": 1,
    "enable_rgb_hist": 1,
    "enable_gray_hist": 1,
    "enable_edge_grid": 1,
}
DEFAULT_PHASE13_REFERENCE_TRAIN_VIEWS = ("original", "flip_h", "brighten")
DEFAULT_PHASE13_REFERENCE_VALIDATION_VIEWS = ("darken",)


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


def build_phase13_reference_image_dataset(
    reference_manifest: dict[str, Any],
    *,
    validation_ratio: float = 0.2,
    split_mode: str = "paired_views",
    train_views: Iterable[str] = DEFAULT_PHASE13_REFERENCE_TRAIN_VIEWS,
    validation_views: Iterable[str] = DEFAULT_PHASE13_REFERENCE_VALIDATION_VIEWS,
) -> dict[str, Any]:
    cards = reference_manifest.get("cards", [])
    if not isinstance(cards, list):
        cards = []
    split_mod = max(2, int(round(1.0 / max(0.01, validation_ratio))))
    normalized_split_mode = str(split_mode or "paired_views").strip().lower()
    normalized_train_views = [str(view).strip().lower() for view in train_views if str(view).strip()]
    normalized_validation_views = [str(view).strip().lower() for view in validation_views if str(view).strip()]
    if not normalized_train_views:
        normalized_train_views = ["original"]
    if normalized_split_mode == "paired_views" and not normalized_validation_views:
        normalized_validation_views = ["darken"]
    examples: list[dict[str, Any]] = []
    for index, row in enumerate(cards):
        if not isinstance(row, dict):
            continue
        card_number = str(row.get("card_number", "")).strip()
        image_path = str(row.get("primary_image_path", "")).strip()
        if not card_number or not image_path:
            continue
        if normalized_split_mode == "disjoint_card":
            split = "validation" if (index % split_mod) == 0 else "train"
            view_specs = [(split, "original")]
        elif normalized_split_mode == "paired_views":
            view_specs = [("train", view) for view in normalized_train_views] + [
                ("validation", view) for view in normalized_validation_views
            ]
        else:
            raise ValueError(f"unsupported split_mode={split_mode!r}")
        for object_index, (split, reference_view) in enumerate(view_specs):
            examples.append(
                {
                    "frame_index": index,
                    "object_index": object_index,
                    "source_image_path": image_path,
                    "crop_image_path": image_path,
                    "crop_width": None,
                    "crop_height": None,
                    "bbox": {},
                    "label": card_number,
                    "seat": None,
                    "phase": None,
                    "signature": card_number,
                    "card_name": str(row.get("card_name", "")),
                    "table_name": str(row.get("table_name", "")),
                    "record_id": int(row.get("record_id", 0) or 0),
                    "image_count": int(row.get("image_count", 0) or 0),
                    "match_type": str(row.get("match_type", "")),
                    "split": split,
                    "reference_view": reference_view,
                }
            )
    return {
        "schema_version": PHASE13_REFERENCE_DATASET_SCHEMA_VERSION,
        "source_schema_version": str(reference_manifest.get("schema_version", "")),
        "target_type": PHASE13_TARGET_CARD_IDENTITY,
        "split_mode": normalized_split_mode,
        "train_views": normalized_train_views,
        "validation_views": normalized_validation_views,
        "card_count": sum(1 for row in cards if isinstance(row, dict)),
        "example_count": len(examples),
        "validation_ratio": float(validation_ratio),
        "examples": examples,
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


def _dataset_target_type(crop_dataset: dict[str, Any]) -> str:
    target_type = str(crop_dataset.get("target_type", "")).strip().lower()
    if target_type:
        return target_type
    schema_version = str(crop_dataset.get("schema_version", "")).strip().lower()
    if schema_version == PHASE13_REFERENCE_DATASET_SCHEMA_VERSION:
        return PHASE13_TARGET_CARD_IDENTITY
    examples = crop_dataset.get("examples", [])
    if isinstance(examples, list) and examples:
        first = examples[0]
        if isinstance(first, dict):
            signature = str(first.get("signature", "")).strip().upper()
            bbox = first.get("bbox")
            if signature and "-" in signature and (bbox == {} or bbox is None):
                return PHASE13_TARGET_CARD_IDENTITY
    return PHASE13_TARGET_OBJECT_ROLE


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


def _gray_histogram_features(image: dict[str, Any], *, bins: int = 8) -> dict[str, float]:
    pixels = image.get("pixels", [])
    if not isinstance(pixels, list):
        return {}
    values: list[float] = []
    for row in pixels:
        if not isinstance(row, list):
            continue
        for r, g, b in row:
            values.append((0.299 * r) + (0.587 * g) + (0.114 * b))
    total = len(values) or 1
    counts = [0 for _ in range(bins)]
    step = 256 / bins
    for value in values:
        index = min(bins - 1, int(value // step))
        counts[index] += 1
    return {f"gray_hist_{idx}": (count / total) for idx, count in enumerate(counts)}


def _edge_grid_features(image: dict[str, Any], *, grid_size: int = 2) -> dict[str, float]:
    pixels = image.get("pixels", [])
    width = int(image.get("width", 0) or 0)
    height = int(image.get("height", 0) or 0)
    if not isinstance(pixels, list) or width <= 1 or height <= 1:
        return {}
    gray: list[list[float]] = []
    for row in pixels:
        if not isinstance(row, list):
            gray.append([0.0 for _ in range(width)])
            continue
        gray.append([(0.299 * r) + (0.587 * g) + (0.114 * b) for r, g, b in row])
    magnitudes = [[0.0 for _ in range(width)] for _ in range(height)]
    for y in range(height):
        for x in range(width):
            left = gray[y][max(0, x - 1)]
            right = gray[y][min(width - 1, x + 1)]
            up = gray[max(0, y - 1)][x]
            down = gray[min(height - 1, y + 1)][x]
            gx = right - left
            gy = down - up
            magnitudes[y][x] = math.sqrt((gx * gx) + (gy * gy))
    features: dict[str, float] = {}
    for gy in range(grid_size):
        for gx in range(grid_size):
            x0 = int(gx * width / grid_size)
            x1 = max(x0 + 1, int((gx + 1) * width / grid_size))
            y0 = int(gy * height / grid_size)
            y1 = max(y0 + 1, int((gy + 1) * height / grid_size))
            bucket: list[float] = []
            for y in range(y0, min(y1, height)):
                for x in range(x0, min(x1, width)):
                    bucket.append(magnitudes[y][x])
            count = len(bucket) or 1
            features[f"edge_{gy}_{gx}_mean"] = sum(bucket) / count
    return features


def _normalize_feature_config(feature_config: dict[str, Any] | None) -> dict[str, int]:
    config = dict(DEFAULT_PHASE13_FEATURE_CONFIG)
    if isinstance(feature_config, dict):
        for key in (
            "patch_grid_size",
            "hist_bins",
            "gray_hist_bins",
            "edge_grid_size",
            "enable_rgb_patch",
            "enable_rgb_hist",
            "enable_gray_hist",
            "enable_edge_grid",
        ):
            if key in feature_config:
                try:
                    config[key] = max(1, int(feature_config[key]))
                except (TypeError, ValueError):
                    continue
    return config


def _copy_image(image: dict[str, Any]) -> dict[str, Any]:
    pixels = image.get("pixels", [])
    return {
        **image,
        "pixels": [[tuple(pixel) for pixel in row] for row in pixels] if isinstance(pixels, list) else [],
    }


def _transform_reference_view(image: dict[str, Any], reference_view: str) -> dict[str, Any]:
    view = str(reference_view or "original").strip().lower()
    if view in {"", "original"}:
        return image
    pixels = image.get("pixels", [])
    if not isinstance(pixels, list):
        return image
    working = _copy_image(image)
    working_pixels = working.get("pixels", [])
    if view == "flip_h":
        working["pixels"] = [list(reversed(row)) for row in working_pixels]
        return working
    if view == "flip_v":
        working["pixels"] = list(reversed(working_pixels))
        return working

    def _shift(value: int, delta: int) -> int:
        return max(0, min(255, int(value) + int(delta)))

    adjusted_pixels: list[list[tuple[int, int, int]]] = []
    if view == "brighten":
        delta = 24
        for row in working_pixels:
            adjusted_pixels.append([(_shift(r, delta), _shift(g, delta), _shift(b, delta)) for r, g, b in row])
        working["pixels"] = adjusted_pixels
        return working
    if view == "darken":
        delta = -24
        for row in working_pixels:
            adjusted_pixels.append([(_shift(r, delta), _shift(g, delta), _shift(b, delta)) for r, g, b in row])
        working["pixels"] = adjusted_pixels
        return working
    return image


def extract_phase13_visual_features_from_image(
    image: dict[str, Any],
    *,
    feature_config: dict[str, Any] | None = None,
) -> dict[str, float]:
    config = _normalize_feature_config(feature_config)
    features: dict[str, float] = {}
    if int(config["enable_rgb_patch"]) > 0:
        features.update(_patch_grid_features(image, grid_size=int(config["patch_grid_size"])))
    if int(config["enable_rgb_hist"]) > 0:
        features.update(_histogram_features(image, bins=int(config["hist_bins"])))
    if int(config["enable_gray_hist"]) > 0:
        features.update(_gray_histogram_features(image, bins=int(config["gray_hist_bins"])))
    if int(config["enable_edge_grid"]) > 0:
        features.update(_edge_grid_features(image, grid_size=int(config["edge_grid_size"])))
    return features


def extract_phase13_visual_features(crop_image_path: Path, *, feature_config: dict[str, Any] | None = None) -> dict[str, float]:
    image = read_image(crop_image_path)
    return extract_phase13_visual_features_from_image(image, feature_config=feature_config)


def enrich_phase13_crop_dataset_features(
    crop_dataset: dict[str, Any],
    *,
    max_examples: int = 0,
    progress_every: int = 0,
    feature_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = _normalize_feature_config(feature_config if feature_config is not None else crop_dataset.get("feature_config"))
    examples = crop_dataset.get("examples", [])
    if not isinstance(examples, list):
        examples = []
    if max_examples > 0:
        examples = examples[:max_examples]
    enriched: list[dict[str, Any]] = []
    total_examples = len(examples)
    for index, row in enumerate(examples, start=1):
        if not isinstance(row, dict):
            continue
        existing_features = row.get("visual_features", {})
        if isinstance(existing_features, dict) and existing_features:
            enriched.append(dict(row))
            if progress_every > 0 and (index % progress_every == 0 or index == total_examples):
                print(f"[phase13-enrich] processed {index}/{total_examples} examples")
            continue
        crop_image_path = Path(str(row.get("crop_image_path", "")))
        if crop_image_path.exists():
            image = read_image(crop_image_path)
            image = _transform_reference_view(image, str(row.get("reference_view", "original")))
            row = {
                **row,
                "visual_features": extract_phase13_visual_features_from_image(image, feature_config=config),
            }
        enriched.append(row)
        if progress_every > 0 and (index % progress_every == 0 or index == total_examples):
            print(f"[phase13-enrich] processed {index}/{total_examples} examples")
    return {
        **crop_dataset,
        "feature_config": config,
        "examples": enriched,
    }


def build_phase13_feature_cache(
    crop_dataset: dict[str, Any],
    *,
    max_examples: int = 0,
    progress_every: int = 0,
    feature_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = enrich_phase13_crop_dataset_features(
        crop_dataset,
        max_examples=max_examples,
        progress_every=progress_every,
        feature_config=feature_config,
    )
    return {
        **enriched,
        "schema_version": PHASE13_FEATURE_CACHE_SCHEMA_VERSION,
        "target_type": _dataset_target_type(crop_dataset),
    }


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
    max_examples: int = 0,
    progress_every: int = 0,
    feature_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dataset = enrich_phase13_crop_dataset_features(
        crop_dataset,
        max_examples=max_examples,
        progress_every=progress_every,
        feature_config=feature_config,
    )
    examples = _filtered_examples(dataset, split)
    train_rows: list[dict[str, Any]] = []
    label_counts: Counter[str] = Counter()
    total_examples = len(examples)
    for index, row in enumerate(examples, start=1):
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
        if progress_every > 0 and (index % progress_every == 0 or index == total_examples):
            print(f"[phase13-train] processed {index}/{total_examples} examples")
    return {
        "schema_version": PHASE13_MODEL_SCHEMA_VERSION,
        "model_name": "phase13_visual_histogram_knn",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_type": _dataset_target_type(crop_dataset),
        "feature_config": _normalize_feature_config(feature_config if feature_config is not None else dataset.get("feature_config")),
        "train_split": str(split),
        "example_count": len(train_rows),
        "source_example_count": total_examples,
        "k_neighbors": int(k_neighbors),
        "global_majority_signature": "" if not label_counts else sorted(label_counts.items(), key=lambda item: (-item[1], item[0]))[0][0],
        "feature_keys": sorted(train_rows[0]["visual_features"].keys()) if train_rows else [],
        "examples": train_rows,
    }


def _feature_distance(a: dict[str, float], b: dict[str, float], keys: list[str]) -> float:
    return math.sqrt(sum((float(a.get(key, 0.0)) - float(b.get(key, 0.0))) ** 2 for key in keys))


def rank_phase13_visual_signatures(
    model: dict[str, Any],
    crop_image_path: Path,
    *,
    top_k: int = 10,
) -> list[dict[str, float | str]]:
    sample = extract_phase13_visual_features(crop_image_path, feature_config=model.get("feature_config"))
    return rank_phase13_visual_features(model, sample, top_k=top_k)


def rank_phase13_visual_features(
    model: dict[str, Any],
    sample: dict[str, float],
    *,
    top_k: int = 10,
) -> list[dict[str, float | str]]:
    rows = model.get("examples", [])
    keys = [str(key) for key in model.get("feature_keys", [])] if isinstance(model.get("feature_keys", []), list) else []
    if not isinstance(rows, list) or not rows or not keys:
        fallback = str(model.get("global_majority_signature", ""))
        return [] if not fallback else [{"signature": fallback, "confidence": 0.0, "distance": 0.0}]
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
    selected = ranked[: max(1, int(top_k))]
    return [
        {
            "signature": signature,
            "distance": float(distance),
            "confidence": max(0.0, 1.0 - (distance / max(1.0, math.sqrt(len(keys)) * 255.0))),
        }
        for distance, signature in selected
    ]


def predict_phase13_visual_signature(model: dict[str, Any], crop_image_path: Path) -> tuple[str, float]:
    nearest = rank_phase13_visual_signatures(model, crop_image_path, top_k=max(1, int(model.get("k_neighbors", 3) or 3)))
    if not nearest:
        return str(model.get("global_majority_signature", "")), 0.0
    k = max(1, int(model.get("k_neighbors", 3) or 3))
    votes = Counter(str(item["signature"]) for item in nearest[:k])
    if not nearest or not votes:
        return str(model.get("global_majority_signature", "")), 0.0
    best_signature = sorted(votes.items(), key=lambda item: (-item[1], item[0]))[0][0]
    avg_distance = sum(float(item["distance"]) for item in nearest[:k]) / len(nearest[:k])
    keys = [str(key) for key in model.get("feature_keys", [])] if isinstance(model.get("feature_keys", []), list) else []
    confidence = max(0.0, 1.0 - (avg_distance / max(1.0, math.sqrt(len(keys)) * 255.0))) if keys else 0.0
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
    target_type = str(model.get("target_type", "") or _dataset_target_type(crop_dataset))
    if target_type != PHASE13_TARGET_OBJECT_ROLE:
        raise ValueError(
            "evaluate_phase13_visual_model only supports object_role models. "
            f"Received target_type={target_type!r}."
        )
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
        "target_type": target_type,
        "frame_count": int(benchmark.get("frame_count", 0) or 0),
        "object_precision": float(benchmark.get("object_precision", 0.0) or 0.0),
        "object_recall": float(benchmark.get("object_recall", 0.0) or 0.0),
        "frame_exact_match_rate": float(benchmark.get("frame_exact_match_rate", 0.0) or 0.0),
        "benchmark": benchmark,
    }


def evaluate_phase13_identity_model(
    *,
    model: dict[str, Any],
    crop_dataset: dict[str, Any],
    split: str = "validation",
    progress_every: int = 0,
    top_k_values: Iterable[int] = (1, 5, 10),
) -> dict[str, Any]:
    target_type = str(model.get("target_type", "") or _dataset_target_type(crop_dataset))
    if target_type != PHASE13_TARGET_CARD_IDENTITY:
        raise ValueError(
            "evaluate_phase13_identity_model only supports card_identity models. "
            f"Received target_type={target_type!r}."
        )
    dataset = enrich_phase13_crop_dataset_features(crop_dataset, progress_every=progress_every)
    examples = _filtered_examples(dataset, split)
    total_examples = len(examples)
    correct = 0
    top_k_hits: dict[int, int] = {int(k): 0 for k in top_k_values if int(k) > 0}
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(examples, start=1):
        crop_path = Path(str(row.get("crop_image_path", "")))
        if not crop_path.exists():
            continue
        row_features = row.get("visual_features", {})
        if not isinstance(row_features, dict) or not row_features:
            row_features = extract_phase13_visual_features(crop_path, feature_config=model.get("feature_config"))
        rankings = rank_phase13_visual_features(
            model,
            {str(key): float(value) for key, value in row_features.items()},
            top_k=max(top_k_hits.keys(), default=1),
        )
        predicted_signature = str(rankings[0]["signature"]) if rankings else str(model.get("global_majority_signature", ""))
        confidence = float(rankings[0]["confidence"]) if rankings else 0.0
        expected_signature = str(row.get("signature", ""))
        is_correct = predicted_signature == expected_signature
        if is_correct:
            correct += 1
        for k in top_k_hits:
            if expected_signature in {str(item["signature"]) for item in rankings[:k]}:
                top_k_hits[k] += 1
        rows.append(
            {
                "index": index - 1,
                "crop_image_path": str(crop_path),
                "expected_signature": expected_signature,
                "predicted_signature": predicted_signature,
                "confidence": float(confidence),
                "correct": bool(is_correct),
                "top_predictions": rankings[:10],
            }
        )
        if progress_every > 0 and (index % progress_every == 0 or index == total_examples):
            print(f"[phase13-identity-eval] processed {index}/{total_examples} examples")
    accuracy = (correct / total_examples) if total_examples else 0.0
    return {
        "schema_version": PHASE13_EVAL_SCHEMA_VERSION,
        "model_name": str(model.get("model_name", "")),
        "target_type": target_type,
        "split": str(split),
        "example_count": total_examples,
        "top1_accuracy": accuracy,
        "top_k_accuracy": {str(k): ((hits / total_examples) if total_examples else 0.0) for k, hits in sorted(top_k_hits.items())},
        "correct_count": correct,
        "rows": rows,
    }


def compare_phase13_visual_models(*, trained_eval: dict[str, Any], baseline_eval: dict[str, Any]) -> dict[str, Any]:
    trained_target_type = str(trained_eval.get("target_type", "")).strip().lower()
    baseline_target_type = str(baseline_eval.get("target_type", "")).strip().lower()
    if trained_target_type and baseline_target_type and trained_target_type != baseline_target_type:
        raise ValueError(
            "cannot compare Phase 13 models with different target types: "
            f"{trained_target_type!r} vs {baseline_target_type!r}"
        )
    trained_exact = float(trained_eval.get("frame_exact_match_rate", 0.0) or 0.0)
    baseline_exact = float(baseline_eval.get("frame_exact_match_rate", 0.0) or 0.0)
    trained_precision = float(trained_eval.get("object_precision", 0.0) or 0.0)
    baseline_precision = float(baseline_eval.get("object_precision", 0.0) or 0.0)
    return {
        "schema_version": "phase13.compare.v1",
        "target_type": trained_target_type or baseline_target_type or "",
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
