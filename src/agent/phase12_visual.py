from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.util
import math
from pathlib import Path
from typing import Any, Iterable

from src.agent.phase10_vision import benchmark_detection_manifest, build_detection_manifest


PHASE12_CROP_DATASET_SCHEMA_VERSION = "phase12.crop_dataset.v1"
PHASE12_MODEL_SCHEMA_VERSION = "phase12.visual_centroid_model.v1"
PHASE12_EVAL_SCHEMA_VERSION = "phase12.visual_eval.v1"
PHASE12_SUPPORTED_IMAGE_SUFFIXES = (".ppm", ".png", ".jpg", ".jpeg")
PHASE13_REAL_CROP_DATASET_SCHEMA_VERSION = "phase13.real_crop_dataset.v1"


def _parse_ppm_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        tokens.extend(line.split())
    return tokens


def read_ppm_image(path: Path) -> dict[str, Any]:
    tokens = _parse_ppm_tokens(path.read_text(encoding="utf-8"))
    if len(tokens) < 4 or tokens[0] != "P3":
        raise ValueError(f"unsupported PPM format in {path}")
    width = int(tokens[1])
    height = int(tokens[2])
    max_value = int(tokens[3])
    expected = width * height * 3
    values = [int(token) for token in tokens[4 : 4 + expected]]
    if len(values) != expected:
        raise ValueError(f"invalid pixel count in {path}")
    pixels: list[list[tuple[int, int, int]]] = []
    index = 0
    for _ in range(height):
        row: list[tuple[int, int, int]] = []
        for _ in range(width):
            row.append((values[index], values[index + 1], values[index + 2]))
            index += 3
        pixels.append(row)
    return {
        "width": width,
        "height": height,
        "max_value": max_value,
        "pixels": pixels,
    }


def write_ppm_image(path: Path, *, width: int, height: int, pixels: list[list[tuple[int, int, int]]]) -> None:
    lines = ["P3", f"{width} {height}", "255"]
    for row in pixels:
        lines.append(" ".join(f"{r} {g} {b}" for r, g, b in row))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def has_pillow_support() -> bool:
    return importlib.util.find_spec("PIL") is not None


def _require_pillow() -> Any:
    if not has_pillow_support():
        raise ValueError("Pillow is required for png/jpg image support")
    from PIL import Image

    return Image


def read_image(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".ppm":
        return read_ppm_image(path)
    if suffix not in PHASE12_SUPPORTED_IMAGE_SUFFIXES:
        raise ValueError(f"unsupported image format: {path.suffix}")
    image_module = _require_pillow()
    with image_module.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        pixels: list[list[tuple[int, int, int]]] = []
        raw = list(rgb.getdata())
        index = 0
        for _ in range(height):
            row: list[tuple[int, int, int]] = []
            for _ in range(width):
                px = raw[index]
                row.append((int(px[0]), int(px[1]), int(px[2])))
                index += 1
            pixels.append(row)
        return {
            "width": width,
            "height": height,
            "max_value": 255,
            "pixels": pixels,
        }


def write_image(path: Path, *, width: int, height: int, pixels: list[list[tuple[int, int, int]]]) -> None:
    suffix = path.suffix.lower()
    if suffix == ".ppm":
        write_ppm_image(path, width=width, height=height, pixels=pixels)
        return
    if suffix not in PHASE12_SUPPORTED_IMAGE_SUFFIXES:
        raise ValueError(f"unsupported image format: {path.suffix}")
    image_module = _require_pillow()
    image = image_module.new("RGB", (width, height))
    flat: list[tuple[int, int, int]] = []
    for row in pixels:
        flat.extend((int(r), int(g), int(b)) for r, g, b in row)
    image.putdata(flat)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _bbox_to_pixel_bounds(image: dict[str, Any], bbox: dict[str, Any]) -> tuple[int, int, int, int]:
    width = int(image.get("width", 0) or 0)
    height = int(image.get("height", 0) or 0)
    x0 = max(0, min(width - 1, int(float(bbox.get("x", 0.0) or 0.0) * width)))
    y0 = max(0, min(height - 1, int(float(bbox.get("y", 0.0) or 0.0) * height)))
    x1 = max(x0 + 1, min(width, int(math.ceil((float(bbox.get("x", 0.0) or 0.0) + float(bbox.get("w", 0.0) or 0.0)) * width))))
    y1 = max(y0 + 1, min(height, int(math.ceil((float(bbox.get("y", 0.0) or 0.0) + float(bbox.get("h", 0.0) or 0.0)) * height))))
    return x0, y0, x1, y1


def _crop_pixels(image: dict[str, Any], bbox: dict[str, Any]) -> list[tuple[int, int, int]]:
    pixels = image.get("pixels", [])
    if not isinstance(pixels, list):
        return []
    x0, y0, x1, y1 = _bbox_to_pixel_bounds(image, bbox)
    out: list[tuple[int, int, int]] = []
    for y in range(y0, y1):
        row = pixels[y]
        if not isinstance(row, list):
            continue
        for x in range(x0, x1):
            out.append(row[x])
    return out


def _crop_pixel_grid(image: dict[str, Any], bbox: dict[str, Any]) -> tuple[list[list[tuple[int, int, int]]], tuple[int, int]]:
    pixels = image.get("pixels", [])
    if not isinstance(pixels, list):
        return [], (0, 0)
    x0, y0, x1, y1 = _bbox_to_pixel_bounds(image, bbox)
    out: list[list[tuple[int, int, int]]] = []
    for y in range(y0, y1):
        row = pixels[y]
        if not isinstance(row, list):
            continue
        out.append([row[x] for x in range(x0, x1)])
    width = max(0, x1 - x0)
    height = max(0, y1 - y0)
    return out, (width, height)


def _mean_rgb(pixels: list[tuple[int, int, int]]) -> dict[str, float]:
    if not pixels:
        return {"mean_r": 0.0, "mean_g": 0.0, "mean_b": 0.0}
    count = len(pixels)
    return {
        "mean_r": sum(rgb[0] for rgb in pixels) / count,
        "mean_g": sum(rgb[1] for rgb in pixels) / count,
        "mean_b": sum(rgb[2] for rgb in pixels) / count,
    }


def _object_signature(obj: dict[str, Any]) -> str:
    seat = "" if obj.get("seat") is None else str(obj.get("seat"))
    phase = "" if obj.get("phase") is None else str(obj.get("phase"))
    return f"{str(obj.get('label', ''))}|{seat}|{phase}"


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


def _resolve_frame_image_paths(frame_manifest: dict[str, Any], *, frame_root: Path | None = None) -> dict[int, Path]:
    output_dir = frame_root or Path(str(frame_manifest.get("output_dir", "")))
    frames = frame_manifest.get("frames", [])
    if not isinstance(frames, list):
        return {}
    mapping: dict[int, Path] = {}
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        frame_index = int(frame.get("frame_index", 0) or 0)
        relative_path = Path(str(frame.get("relative_path", "")))
        mapping[frame_index] = output_dir / relative_path
    return mapping


def build_phase12_crop_dataset(
    *,
    frame_manifest: dict[str, Any],
    labeled_manifest: dict[str, Any],
    frame_root: Path | None = None,
    validation_ratio: float = 0.2,
) -> dict[str, Any]:
    frame_paths = _resolve_frame_image_paths(frame_manifest, frame_root=frame_root)
    detections = labeled_manifest.get("detections", [])
    if not isinstance(detections, list):
        detections = []
    examples: list[dict[str, Any]] = []
    for frame in detections:
        if not isinstance(frame, dict):
            continue
        frame_index = int(frame.get("frame_index", 0) or 0)
        image_path = frame_paths.get(frame_index)
        if image_path is None or not image_path.exists():
            continue
        image = read_image(image_path)
        objects = frame.get("objects", [])
        if not isinstance(objects, list):
            objects = []
        for object_index, obj in enumerate(objects):
            if not isinstance(obj, dict):
                continue
            bbox = obj.get("bbox", {})
            if not isinstance(bbox, dict):
                continue
            crop = _crop_pixels(image, bbox)
            features = _mean_rgb(crop)
            split = "validation" if (frame_index % max(2, int(round(1.0 / max(0.01, validation_ratio))))) == 0 else "train"
            examples.append(
                {
                    "frame_index": frame_index,
                    "object_index": object_index,
                    "image_path": str(image_path),
                    "bbox": dict(bbox),
                    "label": str(obj.get("label", "")),
                    "seat": obj.get("seat"),
                    "phase": obj.get("phase"),
                    "signature": _object_signature(obj),
                    "features": features,
                    "split": split,
                }
            )
    return {
        "schema_version": PHASE12_CROP_DATASET_SCHEMA_VERSION,
        "frame_count": len({int(row["frame_index"]) for row in examples}),
        "example_count": len(examples),
        "validation_ratio": float(validation_ratio),
        "examples": examples,
    }


def export_phase13_real_crop_dataset(
    *,
    frame_manifest: dict[str, Any],
    labeled_manifest: dict[str, Any],
    crops_output_dir: Path,
    crop_image_format: str = "ppm",
    frame_root: Path | None = None,
    validation_ratio: float = 0.2,
) -> dict[str, Any]:
    normalized_format = str(crop_image_format).strip().lower().lstrip(".")
    if normalized_format not in {"ppm", "png", "jpg", "jpeg"}:
        raise ValueError(f"unsupported crop_image_format: {crop_image_format}")
    frame_paths = _resolve_frame_image_paths(frame_manifest, frame_root=frame_root)
    detections = labeled_manifest.get("detections", [])
    if not isinstance(detections, list):
        detections = []
    examples: list[dict[str, Any]] = []
    crops_output_dir.mkdir(parents=True, exist_ok=True)
    extension = ".jpg" if normalized_format == "jpeg" else f".{normalized_format}"
    split_mod = max(2, int(round(1.0 / max(0.01, validation_ratio))))

    for frame in detections:
        if not isinstance(frame, dict):
            continue
        frame_index = int(frame.get("frame_index", 0) or 0)
        image_path = frame_paths.get(frame_index)
        if image_path is None or not image_path.exists():
            continue
        image = read_image(image_path)
        objects = frame.get("objects", [])
        if not isinstance(objects, list):
            objects = []
        for object_index, obj in enumerate(objects):
            if not isinstance(obj, dict):
                continue
            bbox = obj.get("bbox", {})
            if not isinstance(bbox, dict):
                continue
            crop_grid, (crop_width, crop_height) = _crop_pixel_grid(image, bbox)
            if crop_width <= 0 or crop_height <= 0 or not crop_grid:
                continue
            crop_name = f"frame_{frame_index:05d}_obj_{object_index:03d}{extension}"
            crop_path = crops_output_dir / crop_name
            write_image(crop_path, width=crop_width, height=crop_height, pixels=crop_grid)
            features = _mean_rgb([pixel for row in crop_grid for pixel in row])
            split = "validation" if (frame_index % split_mod) == 0 else "train"
            examples.append(
                {
                    "frame_index": frame_index,
                    "object_index": object_index,
                    "source_image_path": str(image_path),
                    "crop_image_path": str(crop_path),
                    "crop_width": crop_width,
                    "crop_height": crop_height,
                    "bbox": dict(bbox),
                    "label": str(obj.get("label", "")),
                    "seat": obj.get("seat"),
                    "phase": obj.get("phase"),
                    "signature": _object_signature(obj),
                    "features": features,
                    "split": split,
                }
            )
    return {
        "schema_version": PHASE13_REAL_CROP_DATASET_SCHEMA_VERSION,
        "frame_count": len({int(row["frame_index"]) for row in examples}),
        "example_count": len(examples),
        "validation_ratio": float(validation_ratio),
        "crop_image_format": normalized_format,
        "crops_output_dir": str(crops_output_dir),
        "examples": examples,
    }


def _filtered_examples(dataset: dict[str, Any], split: str) -> list[dict[str, Any]]:
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        return []
    return [row for row in examples if isinstance(row, dict) and (split == "all" or row.get("split") == split)]


def train_phase12_visual_model(
    dataset: dict[str, Any],
    *,
    split: str = "train",
) -> dict[str, Any]:
    examples = _filtered_examples(dataset, split)
    grouped: dict[str, list[dict[str, float]]] = {}
    for row in examples:
        signature = str(row.get("signature", ""))
        features = row.get("features", {})
        if not signature or not isinstance(features, dict):
            continue
        grouped.setdefault(signature, []).append(
            {
                "mean_r": float(features.get("mean_r", 0.0) or 0.0),
                "mean_g": float(features.get("mean_g", 0.0) or 0.0),
                "mean_b": float(features.get("mean_b", 0.0) or 0.0),
            }
        )
    centroids: dict[str, dict[str, float]] = {}
    for signature, rows in grouped.items():
        count = len(rows)
        centroids[signature] = {
            "mean_r": sum(item["mean_r"] for item in rows) / count,
            "mean_g": sum(item["mean_g"] for item in rows) / count,
            "mean_b": sum(item["mean_b"] for item in rows) / count,
        }
    return {
        "schema_version": PHASE12_MODEL_SCHEMA_VERSION,
        "model_name": "phase12_visual_centroid",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "train_split": str(split),
        "example_count": len(examples),
        "centroids": centroids,
    }


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    return math.sqrt(sum((float(a.get(key, 0.0)) - float(b.get(key, 0.0))) ** 2 for key in ("mean_r", "mean_g", "mean_b")))


def predict_phase12_signature(model: dict[str, Any], features: dict[str, Any]) -> tuple[str, float]:
    centroids = model.get("centroids", {})
    if not isinstance(centroids, dict) or not centroids:
        return "", 0.0
    sample = {
        "mean_r": float(features.get("mean_r", 0.0) or 0.0),
        "mean_g": float(features.get("mean_g", 0.0) or 0.0),
        "mean_b": float(features.get("mean_b", 0.0) or 0.0),
    }
    ranked = sorted(
        (
            (signature, _distance(sample, centroid))
            for signature, centroid in centroids.items()
            if isinstance(centroid, dict)
        ),
        key=lambda item: (item[1], item[0]),
    )
    if not ranked:
        return "", 0.0
    signature, dist = ranked[0]
    confidence = max(0.0, 1.0 - (dist / 255.0))
    return signature, confidence


def run_phase12_visual_model(
    *,
    model: dict[str, Any],
    frame_manifest: dict[str, Any],
    proposal_manifest: dict[str, Any],
    frame_root: Path | None = None,
) -> dict[str, Any]:
    frame_paths = _resolve_frame_image_paths(frame_manifest, frame_root=frame_root)
    proposals = proposal_manifest.get("detections", [])
    if not isinstance(proposals, list):
        proposals = []
    predicted_frames: list[dict[str, Any]] = []
    for frame in proposals:
        if not isinstance(frame, dict):
            continue
        frame_index = int(frame.get("frame_index", 0) or 0)
        image_path = frame_paths.get(frame_index)
        if image_path is None or not image_path.exists():
            continue
        image = read_image(image_path)
        objects = frame.get("objects", [])
        if not isinstance(objects, list):
            objects = []
        predicted_objects: list[dict[str, Any]] = []
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            bbox = obj.get("bbox", {})
            if not isinstance(bbox, dict):
                continue
            features = _mean_rgb(_crop_pixels(image, bbox))
            signature, confidence = predict_phase12_signature(model, features)
            predicted_objects.append(_signature_to_object(signature, bbox=bbox, confidence=confidence))
        predicted_frames.append(
            {
                "frame_index": frame_index,
                "timestamp_seconds": float(frame.get("timestamp_seconds", 0.0) or 0.0),
                "objects": predicted_objects,
            }
        )
    return build_detection_manifest(
        video_manifest=frame_manifest,
        detections=predicted_frames,
        recognizer_name=str(model.get("model_name", "phase12_visual_centroid")),
    )


def evaluate_phase12_visual_model(
    *,
    model: dict[str, Any],
    frame_manifest: dict[str, Any],
    proposal_manifest: dict[str, Any],
    labeled_manifest: dict[str, Any],
    frame_root: Path | None = None,
) -> dict[str, Any]:
    predicted = run_phase12_visual_model(
        model=model,
        frame_manifest=frame_manifest,
        proposal_manifest=proposal_manifest,
        frame_root=frame_root,
    )
    benchmark = benchmark_detection_manifest(predicted, labeled_manifest)
    return {
        "schema_version": PHASE12_EVAL_SCHEMA_VERSION,
        "model_name": str(model.get("model_name", "")),
        "frame_count": int(benchmark.get("frame_count", 0) or 0),
        "object_precision": float(benchmark.get("object_precision", 0.0) or 0.0),
        "object_recall": float(benchmark.get("object_recall", 0.0) or 0.0),
        "frame_exact_match_rate": float(benchmark.get("frame_exact_match_rate", 0.0) or 0.0),
        "benchmark": benchmark,
    }


def compare_phase12_visual_models(*, trained_eval: dict[str, Any], baseline_eval: dict[str, Any]) -> dict[str, Any]:
    trained_exact = float(trained_eval.get("frame_exact_match_rate", 0.0) or 0.0)
    baseline_exact = float(baseline_eval.get("frame_exact_match_rate", 0.0) or 0.0)
    return {
        "schema_version": "phase12.compare.v1",
        "trained_model_name": str(trained_eval.get("model_name", "")),
        "baseline_model_name": str(baseline_eval.get("model_name", "")),
        "trained_frame_exact_match_rate": trained_exact,
        "baseline_frame_exact_match_rate": baseline_exact,
        "frame_exact_match_lift": trained_exact - baseline_exact,
        "promoted": trained_exact >= baseline_exact,
    }


@dataclass(frozen=True)
class Phase12ExperimentHistoryRow:
    timestamp_utc: str
    run_name: str
    model_name: str
    frame_exact_match_rate: float
    object_precision: float
    object_recall: float
    promoted: str
    manifest_path: str


def build_phase12_experiment_history_row(
    *,
    run_name: str,
    model_name: str,
    frame_exact_match_rate: float,
    object_precision: float,
    object_recall: float,
    promoted: bool,
    manifest_path: str,
) -> Phase12ExperimentHistoryRow:
    return Phase12ExperimentHistoryRow(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        run_name=str(run_name),
        model_name=str(model_name),
        frame_exact_match_rate=float(frame_exact_match_rate),
        object_precision=float(object_precision),
        object_recall=float(object_recall),
        promoted="pass" if promoted else "fail",
        manifest_path=str(manifest_path),
    )


def phase12_experiment_history_row_to_dict(row: Phase12ExperimentHistoryRow) -> dict[str, str]:
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


def summarize_phase12_experiment_history(rows: Iterable[dict[str, str]], *, recent_window: int = 20) -> dict[str, Any]:
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


def render_synthetic_phase12_frames(
    *,
    frame_manifest: dict[str, Any],
    labeled_manifest: dict[str, Any],
    output_dir: Path,
    width: int = 64,
    height: int = 64,
    image_format: str = "ppm",
) -> dict[str, Any]:
    color_map = {
        "leader_card": (220, 60, 60),
        "phase_marker": (60, 220, 60),
        "battle_card": (60, 60, 220),
        "unison_card": (220, 220, 60),
    }
    normalized_format = str(image_format).strip().lower().lstrip(".")
    if normalized_format not in {"ppm", "png", "jpg", "jpeg"}:
        raise ValueError(f"unsupported image_format: {image_format}")
    detections = labeled_manifest.get("detections", [])
    if not isinstance(detections, list):
        detections = []
    labeled_by_index = {
        int(frame.get("frame_index", 0) or 0): frame
        for frame in detections
        if isinstance(frame, dict)
    }
    frames = frame_manifest.get("frames", [])
    if not isinstance(frames, list):
        frames = []
    rendered_frames: list[dict[str, Any]] = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        frame_index = int(frame.get("frame_index", 0) or 0)
        pixels = [[(15, 15, 15) for _ in range(width)] for _ in range(height)]
        labeled = labeled_by_index.get(frame_index, {})
        objects = labeled.get("objects", []) if isinstance(labeled, dict) else []
        if not isinstance(objects, list):
            objects = []
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            bbox = obj.get("bbox", {})
            if not isinstance(bbox, dict):
                continue
            x0 = max(0, min(width - 1, int(float(bbox.get("x", 0.0) or 0.0) * width)))
            y0 = max(0, min(height - 1, int(float(bbox.get("y", 0.0) or 0.0) * height)))
            x1 = max(x0 + 1, min(width, int(math.ceil((float(bbox.get("x", 0.0) or 0.0) + float(bbox.get("w", 0.0) or 0.0)) * width))))
            y1 = max(y0 + 1, min(height, int(math.ceil((float(bbox.get("y", 0.0) or 0.0) + float(bbox.get("h", 0.0) or 0.0)) * height))))
            color = color_map.get(str(obj.get("label", "")), (180, 180, 180))
            for y in range(y0, y1):
                for x in range(x0, x1):
                    pixels[y][x] = color
        extension = ".jpg" if normalized_format == "jpeg" else f".{normalized_format}"
        relative_path = Path("frames") / f"frame_{frame_index:05d}{extension}"
        write_image(output_dir / relative_path, width=width, height=height, pixels=pixels)
        rendered_frames.append(
            {
                "frame_index": frame_index,
                "timestamp_seconds": float(frame.get("timestamp_seconds", 0.0) or 0.0),
                "relative_path": str(relative_path),
            }
        )
    return {
        **frame_manifest,
        "output_dir": str(output_dir),
        "frames": rendered_frames,
    }
