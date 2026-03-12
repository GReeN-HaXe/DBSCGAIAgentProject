from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

from src.agent.phase9_external import apply_external_review, normalize_external_match, reconstruct_external_match


PHASE10_DETECTION_SCHEMA_VERSION = "phase10.detections.v1"
PHASE10_EVENT_SCHEMA_VERSION = "phase10.events.v1"
PHASE10_REVIEW_SCHEMA_VERSION = "phase10.reviewed_detections.v1"
PHASE10_BENCHMARK_SCHEMA_VERSION = "phase10.benchmark.v1"
PHASE10_IDENTITY_ENRICHMENT_SCHEMA_VERSION = "phase10.identity_enrichment.v1"


class FrameRecognizer(Protocol):
    def detect(self, frame_manifest: dict[str, Any]) -> dict[str, Any]:
        ...


CARD_LIKE_LABELS = {"leader_card", "battle_card", "unison_card", "z_battle_card"}


def build_detection_manifest(
    *,
    video_manifest: dict[str, Any],
    detections: list[dict[str, Any]],
    recognizer_name: str,
) -> dict[str, Any]:
    return {
        "schema_version": PHASE10_DETECTION_SCHEMA_VERSION,
        "recognizer_name": str(recognizer_name),
        "video_manifest_path": str(video_manifest.get("video_path", "")),
        "frame_count": int(video_manifest.get("frame_count", 0) or 0),
        "detections": detections,
    }


class MockFrameRecognizer:
    def __init__(self, *, default_confidence: float = 0.75) -> None:
        self.default_confidence = float(default_confidence)

    def detect(self, frame_manifest: dict[str, Any]) -> dict[str, Any]:
        frames = frame_manifest.get("frames", [])
        if not isinstance(frames, list):
            frames = []
        detections: list[dict[str, Any]] = []
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            frame_index = int(frame.get("frame_index", 0) or 0)
            timestamp = float(frame.get("timestamp_seconds", 0.0) or 0.0)
            detections.append(
                {
                    "frame_index": frame_index,
                    "timestamp_seconds": timestamp,
                    "objects": [
                        {
                            "label": "leader_card",
                            "seat": 1,
                            "bbox": {"x": 0.10, "y": 0.70, "w": 0.12, "h": 0.20},
                            "confidence": self.default_confidence,
                        },
                        {
                            "label": "leader_card",
                            "seat": 2,
                            "bbox": {"x": 0.78, "y": 0.10, "w": 0.12, "h": 0.20},
                            "confidence": self.default_confidence,
                        },
                        {
                            "label": "phase_marker",
                            "seat": None,
                            "phase": "main" if frame_index % 2 == 0 else "charge",
                            "bbox": {"x": 0.45, "y": 0.02, "w": 0.10, "h": 0.05},
                            "confidence": self.default_confidence - 0.05,
                        },
                    ],
                }
            )
        return build_detection_manifest(
            video_manifest=frame_manifest,
            detections=detections,
            recognizer_name="mock_frame_recognizer",
        )


def infer_events_from_detections(detection_manifest: dict[str, Any]) -> dict[str, Any]:
    detections = detection_manifest.get("detections", [])
    if not isinstance(detections, list):
        detections = []
    events: list[dict[str, Any]] = []
    current_turn = 1
    for idx, frame in enumerate(detections):
        if not isinstance(frame, dict):
            continue
        objects = frame.get("objects", [])
        if not isinstance(objects, list):
            objects = []
        phase = "unknown"
        for obj in objects:
            if isinstance(obj, dict) and str(obj.get("label", "")) == "phase_marker":
                phase = str(obj.get("phase", "unknown"))
                break
        if idx > 0 and phase == "charge":
            current_turn += 1
        events.append(
            {
                "timestamp_seconds": float(frame.get("timestamp_seconds", 0.0) or 0.0),
                "turn_number": current_turn,
                "phase": phase,
                "actor_seat": 1 if idx % 2 == 0 else 2,
                "actor_name": "",
                "action_type": "detected_frame_state",
                "action_text": f"frame_{int(frame.get('frame_index', 0) or 0)}",
                "confidence": max(
                    (
                        float(obj.get("confidence", 0.0) or 0.0)
                        for obj in objects
                        if isinstance(obj, dict)
                    ),
                    default=0.0,
                ),
                "zone_snapshot": {
                    str(obj.get("seat")): {
                        "detected_labels": [str(item.get("label", "")) for item in objects if isinstance(item, dict) and item.get("seat") == obj.get("seat")],
                        "detected_objects": [
                            {
                                "label": str(item.get("label", "")),
                                "resolved_signature": str(item.get("resolved_signature", "")),
                                "identity_confidence": float(item.get("identity_confidence", 0.0) or 0.0),
                            }
                            for item in objects
                            if isinstance(item, dict) and item.get("seat") == obj.get("seat")
                        ],
                    }
                    for obj in objects
                    if isinstance(obj, dict) and obj.get("seat") is not None
                },
            }
        )
    return {
        "schema_version": PHASE10_EVENT_SCHEMA_VERSION,
        "recognizer_name": str(detection_manifest.get("recognizer_name", "")),
        "event_count": len(events),
        "events": events,
    }


def apply_detection_review(
    detection_manifest: dict[str, Any],
    *,
    corrections: list[dict[str, Any]],
    reviewer: str,
    review_status: str = "reviewed",
    notes: str = "",
) -> dict[str, Any]:
    reviewed = deepcopy(detection_manifest)
    detections = reviewed.get("detections", [])
    if not isinstance(detections, list):
        detections = []
    applied = 0
    for correction in corrections:
        if not isinstance(correction, dict):
            continue
        try:
            frame_index = int(correction.get("frame_index", -1))
        except (TypeError, ValueError):
            continue
        operation = str(correction.get("operation", "update")).strip().lower() or "update"
        object_index_raw = correction.get("object_index", -1)
        updates = correction.get("updates", {})
        new_object = correction.get("object", {})
        if frame_index < 0:
            continue
        target_frame = next(
            (
                frame
                for frame in detections
                if isinstance(frame, dict) and int(frame.get("frame_index", -1)) == frame_index
            ),
            None,
        )
        if not isinstance(target_frame, dict):
            continue
        objects = target_frame.get("objects", [])
        if not isinstance(objects, list):
            continue
        if operation == "add":
            if not isinstance(new_object, dict):
                continue
            objects.append(dict(new_object))
            applied += 1
            continue
        try:
            object_index = int(object_index_raw)
        except (TypeError, ValueError):
            continue
        if object_index < 0 or object_index >= len(objects) or not isinstance(objects[object_index], dict):
            continue
        if operation == "remove":
            del objects[object_index]
            applied += 1
            continue
        if operation == "update":
            if not isinstance(updates, dict):
                continue
            objects[object_index] = {**objects[object_index], **updates}
            applied += 1
    reviewed["detections"] = detections
    reviewed["review"] = {
        "schema_version": PHASE10_REVIEW_SCHEMA_VERSION,
        "review_status": str(review_status),
        "reviewer": str(reviewer),
        "notes": str(notes),
        "correction_count": len([row for row in corrections if isinstance(row, dict)]),
        "applied_correction_count": applied,
    }
    return reviewed


def enrich_detections_with_phase15_identity(
    detection_manifest: dict[str, Any],
    *,
    frame_manifest: dict[str, Any],
    crops_output_dir: Path,
    crop_image_format: str = "ppm",
    top_k: int = 5,
    production_dir: Path | None = None,
    model_path: Path | None = None,
    summary_path: Path | None = None,
    feature_cache_path: Path | None = None,
    card_like_labels: set[str] | None = None,
) -> dict[str, Any]:
    from src.agent.phase12_visual import export_phase13_real_crop_dataset
    from src.agent.phase15_runtime import query_phase15_production_crop

    reviewed = deepcopy(detection_manifest)
    labels_to_enrich = {str(label).strip().lower() for label in (card_like_labels or CARD_LIKE_LABELS)}
    crop_dataset = export_phase13_real_crop_dataset(
        frame_manifest=frame_manifest,
        labeled_manifest=reviewed,
        crops_output_dir=crops_output_dir,
        crop_image_format=crop_image_format,
        validation_ratio=0.2,
    )
    examples = crop_dataset.get("examples", [])
    if not isinstance(examples, list):
        examples = []
    detections = reviewed.get("detections", [])
    if not isinstance(detections, list):
        detections = []
    frame_by_index = {int(frame.get("frame_index", -1) or -1): frame for frame in detections if isinstance(frame, dict)}
    object_lookup: dict[tuple[int, int], dict[str, Any]] = {}
    for frame in detections:
        if not isinstance(frame, dict):
            continue
        frame_index = int(frame.get("frame_index", -1) or -1)
        objects = frame.get("objects", [])
        if not isinstance(objects, list):
            continue
        for object_index, obj in enumerate(objects):
            if not isinstance(obj, dict):
                continue
            if str(obj.get("label", "")).strip().lower() in labels_to_enrich:
                objects[object_index] = {
                    **obj,
                    "identity_candidates": [],
                    "resolved_signature": "",
                    "identity_confidence": 0.0,
                    "identity_crop_image_path": "",
                }
                object_lookup[(frame_index, object_index)] = objects[object_index]
    enriched_count = 0
    skipped_count = 0
    for row in examples:
        if not isinstance(row, dict):
            continue
        if str(row.get("label", "")).strip().lower() not in labels_to_enrich:
            skipped_count += 1
            continue
        crop_path = Path(str(row.get("crop_image_path", "")))
        if not crop_path.exists():
            skipped_count += 1
            continue
        prediction = query_phase15_production_crop(
            crop_image_path=crop_path,
            top_k=int(top_k),
            production_dir=production_dir,
            model_path=model_path,
            summary_path=summary_path,
            feature_cache_path=feature_cache_path,
        )
        predictions = prediction.get("predictions", [])
        if not isinstance(predictions, list):
            predictions = []
        frame_index = int(row.get("frame_index", -1) or -1)
        object_index = int(row.get("object_index", -1) or -1)
        target = object_lookup.get((frame_index, object_index))
        if not isinstance(target, dict):
            frame = frame_by_index.get(frame_index)
            objects = frame.get("objects", []) if isinstance(frame, dict) else []
            bbox = row.get("bbox", {})
            if not isinstance(objects, list) or not isinstance(bbox, dict):
                skipped_count += 1
                continue
            target = next(
                (
                    obj
                    for obj in objects
                    if isinstance(obj, dict)
                    and str(obj.get("label", "")).strip().lower() == str(row.get("label", "")).strip().lower()
                    and isinstance(obj.get("bbox"), dict)
                    and obj.get("bbox") == bbox
                ),
                None,
            )
        if not isinstance(target, dict):
            skipped_count += 1
            continue
        top_prediction = predictions[0] if predictions else {}
        target["identity_candidates"] = [
            {
                "rank": int(item.get("rank", 0) or 0),
                "signature": str(item.get("signature", "")),
                "score": float(item.get("score", 0.0) or 0.0),
            }
            for item in predictions
            if isinstance(item, dict)
        ]
        target["resolved_signature"] = str(top_prediction.get("signature", ""))
        target["identity_confidence"] = float(top_prediction.get("score", 0.0) or 0.0)
        target["identity_crop_image_path"] = str(crop_path)
        enriched_count += 1
    reviewed["detections"] = detections
    reviewed["identity_enrichment"] = {
        "schema_version": PHASE10_IDENTITY_ENRICHMENT_SCHEMA_VERSION,
        "resolver_name": "phase15_production",
        "top_k": int(top_k),
        "crop_image_format": str(crop_image_format),
        "crops_output_dir": str(crops_output_dir),
        "enriched_object_count": enriched_count,
        "skipped_object_count": skipped_count,
    }
    return reviewed


def reviewed_detections_to_external_match(
    detection_manifest: dict[str, Any],
    *,
    match_id: str,
    source_name: str,
    reviewer: str = "phase10_system",
    review_status: str = "reviewed",
    notes: str = "",
) -> dict[str, Any]:
    events_payload = infer_events_from_detections(detection_manifest)
    raw_match = normalize_external_match(
        {
            "events": events_payload.get("events", []),
            "video_path": detection_manifest.get("video_manifest_path", ""),
            "review_status": review_status,
            "reviewer": reviewer,
            "notes": notes,
        },
        match_id=match_id,
        source_name=source_name,
        source_type="phase10_detection_review",
        video_path=str(detection_manifest.get("video_manifest_path", "")),
    )
    reconstructed = reconstruct_external_match(raw_match)
    return apply_external_review(
        reconstructed,
        reviewer=reviewer,
        review_status=review_status,
        notes=notes,
    )


def benchmark_detection_manifest(
    predicted_manifest: dict[str, Any],
    labeled_manifest: dict[str, Any],
) -> dict[str, Any]:
    predicted_frames = predicted_manifest.get("detections", [])
    labeled_frames = labeled_manifest.get("detections", [])
    if not isinstance(predicted_frames, list):
        predicted_frames = []
    if not isinstance(labeled_frames, list):
        labeled_frames = []
    labeled_by_index = {
        int(frame.get("frame_index", -1) or -1): frame
        for frame in labeled_frames
        if isinstance(frame, dict)
    }
    total_labeled_objects = 0
    total_predicted_objects = 0
    matched_labels = 0
    exact_frames = 0
    frame_rows: list[dict[str, Any]] = []
    for predicted in predicted_frames:
        if not isinstance(predicted, dict):
            continue
        frame_index = int(predicted.get("frame_index", -1) or -1)
        labeled = labeled_by_index.get(frame_index, {})
        predicted_objects = predicted.get("objects", [])
        labeled_objects = labeled.get("objects", []) if isinstance(labeled, dict) else []
        if not isinstance(predicted_objects, list):
            predicted_objects = []
        if not isinstance(labeled_objects, list):
            labeled_objects = []
        predicted_labels = sorted(str(obj.get("label", "")) for obj in predicted_objects if isinstance(obj, dict))
        labeled_labels = sorted(str(obj.get("label", "")) for obj in labeled_objects if isinstance(obj, dict))
        local_matches = 0
        remaining = list(labeled_labels)
        for label in predicted_labels:
            if label in remaining:
                remaining.remove(label)
                local_matches += 1
        total_predicted_objects += len(predicted_labels)
        total_labeled_objects += len(labeled_labels)
        matched_labels += local_matches
        frame_exact = predicted_labels == labeled_labels
        if frame_exact:
            exact_frames += 1
        frame_rows.append(
            {
                "frame_index": frame_index,
                "predicted_object_count": len(predicted_labels),
                "labeled_object_count": len(labeled_labels),
                "matched_label_count": local_matches,
                "exact_match": frame_exact,
            }
        )
    precision = (matched_labels / total_predicted_objects) if total_predicted_objects else 0.0
    recall = (matched_labels / total_labeled_objects) if total_labeled_objects else 0.0
    frame_count = len(frame_rows)
    exact_match_rate = (exact_frames / frame_count) if frame_count else 0.0
    return {
        "schema_version": PHASE10_BENCHMARK_SCHEMA_VERSION,
        "recognizer_name": str(predicted_manifest.get("recognizer_name", "")),
        "frame_count": frame_count,
        "object_precision": precision,
        "object_recall": recall,
        "label_match_count": matched_labels,
        "predicted_object_count": total_predicted_objects,
        "labeled_object_count": total_labeled_objects,
        "frame_exact_match_rate": exact_match_rate,
        "frames": frame_rows,
    }
