from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from src.agent.phase10_vision import build_detection_manifest, benchmark_detection_manifest


PHASE11_MODEL_SCHEMA_VERSION = "phase11.recognizer_frequency.v1"
PHASE11_EVAL_SCHEMA_VERSION = "phase11.recognizer_eval.v1"
DEFAULT_PHASE11_FEATURE_FIELDS = ("frame_index_parity", "timestamp_bucket")


def _frame_features(frame: dict[str, Any]) -> dict[str, str]:
    frame_index = int(frame.get("frame_index", 0) or 0)
    timestamp = float(frame.get("timestamp_seconds", 0.0) or 0.0)
    return {
        "frame_index_parity": "even" if frame_index % 2 == 0 else "odd",
        "timestamp_bucket": str(int(timestamp)),
    }


def build_phase11_feature_key(
    frame: dict[str, Any],
    feature_fields: tuple[str, ...] = DEFAULT_PHASE11_FEATURE_FIELDS,
) -> str:
    features = _frame_features(frame)
    return "|".join(f"{field}={features.get(field, '')}" for field in feature_fields)


def _object_signature(obj: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(obj.get("label", "")),
        "" if obj.get("seat") is None else str(obj.get("seat")),
        str(obj.get("phase", "")),
    )


def _average_bbox(boxes: list[dict[str, float]]) -> dict[str, float]:
    if not boxes:
        return {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0}
    return {
        axis: sum(float(box.get(axis, 0.0) or 0.0) for box in boxes) / len(boxes)
        for axis in ("x", "y", "w", "h")
    }


def train_phase11_recognizer_model(
    labeled_manifests: Iterable[dict[str, Any]],
    *,
    feature_fields: tuple[str, ...] = DEFAULT_PHASE11_FEATURE_FIELDS,
) -> dict[str, Any]:
    manifests = list(labeled_manifests)
    context_counts: dict[str, Counter[tuple[str, str, str]]] = defaultdict(Counter)
    object_boxes: dict[str, dict[tuple[str, str, str], list[dict[str, float]]]] = defaultdict(lambda: defaultdict(list))
    object_confidences: dict[str, dict[tuple[str, str, str], list[float]]] = defaultdict(lambda: defaultdict(list))
    global_counts: Counter[tuple[str, str, str]] = Counter()
    frame_total = 0

    for manifest in manifests:
        detections = manifest.get("detections", [])
        if not isinstance(detections, list):
            continue
        for frame in detections:
            if not isinstance(frame, dict):
                continue
            frame_total += 1
            key = build_phase11_feature_key(frame, feature_fields)
            objects = frame.get("objects", [])
            if not isinstance(objects, list):
                objects = []
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                sig = _object_signature(obj)
                context_counts[key][sig] += 1
                global_counts[sig] += 1
                bbox = obj.get("bbox", {})
                if isinstance(bbox, dict):
                    object_boxes[key][sig].append(
                        {
                            "x": float(bbox.get("x", 0.0) or 0.0),
                            "y": float(bbox.get("y", 0.0) or 0.0),
                            "w": float(bbox.get("w", 0.0) or 0.0),
                            "h": float(bbox.get("h", 0.0) or 0.0),
                        }
                    )
                object_confidences[key][sig].append(float(obj.get("confidence", 1.0) or 1.0))

    global_majority = [sig for sig, _ in sorted(global_counts.items(), key=lambda item: (-item[1], item[0]))[:3]]
    contexts_payload: dict[str, dict[str, Any]] = {}
    for key, counts in context_counts.items():
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        templates: list[dict[str, Any]] = []
        for sig, count in ranked:
            label, seat, phase = sig
            boxes = object_boxes[key][sig]
            confs = object_confidences[key][sig]
            templates.append(
                {
                    "label": label,
                    "seat": None if seat == "" else int(seat),
                    "phase": phase or None,
                    "count": int(count),
                    "bbox": _average_bbox(boxes),
                    "confidence": 0.0 if not confs else (sum(confs) / len(confs)),
                }
            )
        contexts_payload[key] = {"templates": templates}

    return {
        "schema_version": PHASE11_MODEL_SCHEMA_VERSION,
        "model_name": "phase11_frequency_recognizer",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "feature_fields": list(feature_fields),
        "manifest_count": len(manifests),
        "frame_count": frame_total,
        "global_templates": [
            {
                "label": label,
                "seat": None if seat == "" else int(seat),
                "phase": phase or None,
            }
            for label, seat, phase in global_majority
        ],
        "contexts": contexts_payload,
    }


def _predict_objects_for_frame(model: dict[str, Any], frame: dict[str, Any]) -> list[dict[str, Any]]:
    feature_fields = tuple(str(item) for item in model.get("feature_fields", []) if item) or DEFAULT_PHASE11_FEATURE_FIELDS
    key = build_phase11_feature_key(frame, feature_fields)
    contexts = model.get("contexts", {})
    if isinstance(contexts, dict):
        context_payload = contexts.get(key)
        if isinstance(context_payload, dict):
            templates = context_payload.get("templates", [])
            if isinstance(templates, list) and templates:
                objects: list[dict[str, Any]] = []
                for item in templates:
                    if not isinstance(item, dict):
                        continue
                    obj = {
                        "label": str(item.get("label", "")),
                        "seat": item.get("seat"),
                        "bbox": dict(item.get("bbox", {})) if isinstance(item.get("bbox"), dict) else {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
                        "confidence": float(item.get("confidence", 0.5) or 0.5),
                    }
                    if item.get("phase") is not None:
                        obj["phase"] = str(item.get("phase"))
                    objects.append(obj)
                return objects
    global_templates = model.get("global_templates", [])
    if not isinstance(global_templates, list):
        global_templates = []
    objects = []
    for item in global_templates:
        if not isinstance(item, dict):
            continue
        obj = {
            "label": str(item.get("label", "")),
            "seat": item.get("seat"),
            "bbox": {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
            "confidence": 0.5,
        }
        if item.get("phase") is not None:
            obj["phase"] = str(item.get("phase"))
        objects.append(obj)
    return objects


def run_phase11_recognizer_model(
    model: dict[str, Any],
    frame_manifest: dict[str, Any],
) -> dict[str, Any]:
    frames = frame_manifest.get("frames", [])
    if not isinstance(frames, list):
        frames = []
    detections: list[dict[str, Any]] = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        detections.append(
            {
                "frame_index": int(frame.get("frame_index", 0) or 0),
                "timestamp_seconds": float(frame.get("timestamp_seconds", 0.0) or 0.0),
                "objects": _predict_objects_for_frame(model, frame),
            }
        )
    return build_detection_manifest(
        video_manifest=frame_manifest,
        detections=detections,
        recognizer_name=str(model.get("model_name", "phase11_frequency_recognizer")),
    )


def evaluate_phase11_recognizer_model(
    *,
    model: dict[str, Any],
    frame_manifest: dict[str, Any],
    labeled_manifest: dict[str, Any],
) -> dict[str, Any]:
    predicted = run_phase11_recognizer_model(model, frame_manifest)
    benchmark = benchmark_detection_manifest(predicted, labeled_manifest)
    return {
        "schema_version": PHASE11_EVAL_SCHEMA_VERSION,
        "model_name": str(model.get("model_name", "")),
        "frame_count": int(benchmark.get("frame_count", 0) or 0),
        "object_precision": float(benchmark.get("object_precision", 0.0) or 0.0),
        "object_recall": float(benchmark.get("object_recall", 0.0) or 0.0),
        "frame_exact_match_rate": float(benchmark.get("frame_exact_match_rate", 0.0) or 0.0),
        "benchmark": benchmark,
    }


def compare_phase11_recognizers(
    *,
    trained_eval: dict[str, Any],
    baseline_eval: dict[str, Any],
) -> dict[str, Any]:
    trained_exact = float(trained_eval.get("frame_exact_match_rate", 0.0) or 0.0)
    baseline_exact = float(baseline_eval.get("frame_exact_match_rate", 0.0) or 0.0)
    trained_precision = float(trained_eval.get("object_precision", 0.0) or 0.0)
    baseline_precision = float(baseline_eval.get("object_precision", 0.0) or 0.0)
    return {
        "schema_version": "phase11.compare.v1",
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
class Phase11ExperimentHistoryRow:
    timestamp_utc: str
    run_name: str
    model_name: str
    frame_exact_match_rate: float
    object_precision: float
    object_recall: float
    promoted: str
    manifest_path: str


def build_phase11_experiment_history_row(
    *,
    run_name: str,
    model_name: str,
    frame_exact_match_rate: float,
    object_precision: float,
    object_recall: float,
    promoted: bool,
    manifest_path: str,
) -> Phase11ExperimentHistoryRow:
    return Phase11ExperimentHistoryRow(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        run_name=str(run_name),
        model_name=str(model_name),
        frame_exact_match_rate=float(frame_exact_match_rate),
        object_precision=float(object_precision),
        object_recall=float(object_recall),
        promoted="pass" if promoted else "fail",
        manifest_path=str(manifest_path),
    )


def phase11_experiment_history_row_to_dict(row: Phase11ExperimentHistoryRow) -> dict[str, str]:
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


def summarize_phase11_experiment_history(rows: Iterable[dict[str, str]], *, recent_window: int = 20) -> dict[str, Any]:
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
