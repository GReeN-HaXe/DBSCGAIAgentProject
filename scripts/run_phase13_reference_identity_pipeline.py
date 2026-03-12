from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    build_phase13_identity_history_row,
    has_pillow_support,
    phase13_identity_history_row_to_dict,
    summarize_phase13_identity_history,
)


def _run(cmd: list[str], *, stage_name: str, timeout_seconds: int) -> float:
    print(f"[phase13-identity] start: {stage_name}")
    print(f"[phase13-identity] cmd: {' '.join(cmd)}")
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        raise RuntimeError(f"stage timed out after {elapsed:.1f}s: {stage_name}") from exc
    elapsed = time.perf_counter() - started
    print(f"[phase13-identity] done: {stage_name} ({elapsed:.1f}s)")
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")
    return elapsed


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def _append_history_csv(path: Path, row: dict[str, str]) -> list[dict[str, str]]:
    existing: list[dict[str, str]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as handle:
            existing = list(csv.DictReader(handle))
    rows = [*existing, row]
    fieldnames = list(row.keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def _dataset_requires_pillow(dataset: dict[str, object]) -> tuple[bool, list[str]]:
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        return False, []
    suffixes: set[str] = set()
    for row in examples:
        if not isinstance(row, dict):
            continue
        suffix = Path(str(row.get("crop_image_path", ""))).suffix.lower()
        if suffix:
            suffixes.add(suffix)
    needs_pillow = any(suffix in {".png", ".jpg", ".jpeg", ".webp"} for suffix in suffixes)
    return needs_pillow, sorted(suffixes)


def _limit_dataset(dataset: dict[str, object], *, max_examples: int) -> dict[str, object]:
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        return dict(dataset)
    if max_examples <= 0 or len(examples) <= max_examples:
        return dict(dataset)
    limited_examples = list(examples[:max_examples])
    return {
        **dataset,
        "example_count": len(limited_examples),
        "card_count": len(limited_examples),
        "examples": limited_examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate a Phase 13 card-identity model on the reference-image corpus.")
    parser.add_argument("--reference-dataset", type=Path, default=Path("artifacts/phase13_reference_image_dataset.json"), help="Phase 13 reference-image dataset JSON path.")
    parser.add_argument("--run-name", type=str, default="phase13_reference_identity_run", help="Experiment run name.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase13_reference_identity_pipeline"), help="Output artifact directory.")
    parser.add_argument("--max-reference-examples", type=int, default=128, help="Maximum number of reference-image examples to use for this run. Use 0 to disable the limit.")
    parser.add_argument("--stage-timeout-seconds", type=int, default=600, help="Per-stage timeout in seconds.")
    parser.add_argument("--progress-every", type=int, default=25, help="Print training/eval progress every N examples. Use 0 to disable.")
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation", help="Dataset split to evaluate.")
    parser.add_argument("--history-csv", type=Path, default=None, help="Optional identity experiment history CSV path.")
    parser.add_argument("--history-summary-output", type=Path, default=None, help="Optional identity experiment history summary JSON path.")
    args = parser.parse_args()

    reference_dataset = _load_json(args.reference_dataset)
    needs_pillow, suffixes = _dataset_requires_pillow(reference_dataset)
    if needs_pillow and not has_pillow_support():
        suffix_list = ", ".join(suffixes) if suffixes else "unknown"
        raise RuntimeError(
            "reference dataset contains image formats that require Pillow "
            f"({suffix_list}), but Pillow is not installed. "
            "Install vision dependencies first, then rerun this pipeline."
        )

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    stage_timings: list[dict[str, object]] = []
    limited_dataset_path = args.artifacts_dir / "phase13_reference_identity_dataset_limited.json"
    feature_cache_path = args.artifacts_dir / "phase13_reference_identity_feature_cache.json"
    model_path = args.artifacts_dir / "phase13_reference_identity_model.json"
    eval_path = args.artifacts_dir / "phase13_reference_identity_eval.json"
    manifest_path = args.artifacts_dir / "phase13_reference_identity_manifest.json"
    history_csv = args.history_csv or (args.artifacts_dir / "phase13_reference_identity_history.csv")
    history_summary_output = args.history_summary_output or (args.artifacts_dir / "phase13_reference_identity_history_summary.json")

    limited_dataset = _limit_dataset(reference_dataset, max_examples=int(args.max_reference_examples))
    limited_dataset_path.write_text(json.dumps(limited_dataset, indent=2), encoding="utf-8")
    print(
        "[phase13-identity] reference examples: "
        f"{limited_dataset.get('example_count', 0)} / {reference_dataset.get('example_count', 0)}"
    )

    stage_timings.append(
        {
            "stage": "build_feature_cache",
            "duration_seconds": _run(
                [
                    sys.executable,
                    "scripts/build_phase13_feature_cache.py",
                    "--dataset",
                    str(limited_dataset_path),
                    "--max-examples",
                    str(int(args.max_reference_examples) if int(args.max_reference_examples) > 0 else 0),
                    "--progress-every",
                    str(int(args.progress_every)),
                    "--output",
                    str(feature_cache_path),
                ],
                stage_name="build_feature_cache",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        }
    )
    stage_timings.append(
        {
            "stage": "train_identity_model",
            "duration_seconds": _run(
                [
                    sys.executable,
                    "scripts/train_phase13_visual_model.py",
                    "--dataset",
                    str(feature_cache_path),
                    "--split",
                    "train",
                    "--k-neighbors",
                    "1",
                    "--max-examples",
                    str(int(args.max_reference_examples) if int(args.max_reference_examples) > 0 else 0),
                    "--progress-every",
                    str(int(args.progress_every)),
                    "--output",
                    str(model_path),
                ],
                stage_name="train_identity_model",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        }
    )
    stage_timings.append(
        {
            "stage": "evaluate_identity_model",
            "duration_seconds": _run(
                [
                    sys.executable,
                    "scripts/evaluate_phase13_identity_model.py",
                    "--model",
                    str(model_path),
                    "--dataset",
                    str(feature_cache_path),
                    "--split",
                    str(args.eval_split),
                    "--progress-every",
                    str(int(args.progress_every)),
                    "--output",
                    str(eval_path),
                ],
                stage_name="evaluate_identity_model",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        }
    )

    eval_payload = _load_json(eval_path)
    top_k_accuracy = eval_payload.get("top_k_accuracy", {})
    history_row = build_phase13_identity_history_row(
        run_name=str(args.run_name),
        top1_accuracy=float(eval_payload.get("top1_accuracy", 0.0) or 0.0),
        top5_accuracy=float((top_k_accuracy.get("5", 0.0) if isinstance(top_k_accuracy, dict) else 0.0) or 0.0),
        top10_accuracy=float((top_k_accuracy.get("10", 0.0) if isinstance(top_k_accuracy, dict) else 0.0) or 0.0),
        example_count=int(eval_payload.get("example_count", 0) or 0),
        manifest_path=str(manifest_path),
    )
    history_rows = _append_history_csv(history_csv, phase13_identity_history_row_to_dict(history_row))
    history_summary = summarize_phase13_identity_history(history_rows)
    history_summary_output.write_text(json.dumps(history_summary, indent=2), encoding="utf-8")
    manifest = {
        "schema_version": "phase13.reference_identity_manifest.v1",
        "status": "pass",
        "run_name": str(args.run_name),
        "artifacts": {
            "reference_dataset": str(args.reference_dataset),
            "reference_dataset_limited": str(limited_dataset_path),
            "feature_cache": str(feature_cache_path),
            "model": str(model_path),
            "evaluation": str(eval_path),
            "history_csv": str(history_csv),
            "history_summary": str(history_summary_output),
        },
        "metrics": {
            "target_type": str(eval_payload.get("target_type", "")),
            "split": str(eval_payload.get("split", "")),
            "top1_accuracy": float(eval_payload.get("top1_accuracy", 0.0) or 0.0),
            "top5_accuracy": float((top_k_accuracy.get("5", 0.0) if isinstance(top_k_accuracy, dict) else 0.0) or 0.0),
            "top10_accuracy": float((top_k_accuracy.get("10", 0.0) if isinstance(top_k_accuracy, dict) else 0.0) or 0.0),
            "example_count": int(eval_payload.get("example_count", 0) or 0),
            "reference_example_count": int(limited_dataset.get("example_count", 0) or 0),
            "reference_example_count_total": int(reference_dataset.get("example_count", 0) or 0),
        },
        "stage_timings": stage_timings,
        "history": history_summary,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {manifest_path}")


if __name__ == "__main__":
    main()
