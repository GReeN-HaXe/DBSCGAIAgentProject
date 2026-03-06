from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    PHASE12_MODEL_SCHEMA_VERSION,
    build_phase13_experiment_history_row,
    compare_phase13_visual_models,
    phase13_experiment_history_row_to_dict,
    summarize_phase13_experiment_history,
)


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip())
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 13 real-crop visual pipeline end to end.")
    parser.add_argument("--frame-manifest", type=Path, required=True, help="Frame manifest JSON path.")
    parser.add_argument("--labeled", type=Path, required=True, help="Labeled detection manifest JSON path.")
    parser.add_argument("--run-name", type=str, default="phase13_run", help="Experiment run name.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase13_pipeline"), help="Output artifact directory.")
    parser.add_argument("--history-csv", type=Path, default=None, help="Optional experiment history CSV path.")
    parser.add_argument("--history-summary-output", type=Path, default=None, help="Optional history summary JSON path.")
    args = parser.parse_args()

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    rendered_manifest_path = args.artifacts_dir / "phase13_rendered_frames.json"
    crop_dataset_path = args.artifacts_dir / "phase13_real_crop_dataset.json"
    annotation_path = args.artifacts_dir / "phase13_crop_annotations.json"
    reviewed_dataset_path = args.artifacts_dir / "phase13_reviewed_crop_dataset.json"
    model_path = args.artifacts_dir / "phase13_visual_model.json"
    eval_path = args.artifacts_dir / "phase13_visual_eval.json"
    baseline_eval_path = args.artifacts_dir / "phase13_baseline_eval.json"
    comparison_path = args.artifacts_dir / "phase13_compare.json"
    manifest_path = args.artifacts_dir / "phase13_manifest.json"
    phase12_baseline_model_path = args.artifacts_dir / "phase12_baseline_model.json"

    _run(
        [
            sys.executable,
            "scripts/render_phase12_synthetic_frames.py",
            "--frame-manifest",
            str(args.frame_manifest),
            "--labeled",
            str(args.labeled),
            "--output-dir",
            str(args.artifacts_dir / "frames"),
            "--manifest-output",
            str(rendered_manifest_path),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/export_phase13_real_crop_dataset.py",
            "--frame-manifest",
            str(rendered_manifest_path),
            "--labeled",
            str(args.labeled),
            "--crops-output-dir",
            str(args.artifacts_dir / "crops"),
            "--crop-image-format",
            "ppm",
            "--output",
            str(crop_dataset_path),
        ]
    )
    _run([sys.executable, "scripts/bootstrap_phase13_crop_annotations.py", "--dataset", str(crop_dataset_path), "--output", str(annotation_path)])
    _run(
        [
            sys.executable,
            "scripts/apply_phase13_crop_reviews.py",
            "--dataset",
            str(crop_dataset_path),
            "--annotations",
            str(annotation_path),
            "--output",
            str(reviewed_dataset_path),
        ]
    )
    _run([sys.executable, "scripts/train_phase13_visual_model.py", "--dataset", str(reviewed_dataset_path), "--split", "all", "--output", str(model_path)])
    _run(
        [
            sys.executable,
            "scripts/evaluate_phase13_visual_model.py",
            "--model",
            str(model_path),
            "--proposal-manifest",
            str(args.labeled),
            "--labeled",
            str(args.labeled),
            "--dataset",
            str(reviewed_dataset_path),
            "--output",
            str(eval_path),
        ]
    )

    _run(
        [
            sys.executable,
            "scripts/train_phase12_visual_model.py",
            "--dataset",
            str(crop_dataset_path),
            "--split",
            "all",
            "--output",
            str(phase12_baseline_model_path),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/evaluate_phase12_visual_model.py",
            "--model",
            str(phase12_baseline_model_path),
            "--frame-manifest",
            str(rendered_manifest_path),
            "--proposal-manifest",
            str(args.labeled),
            "--labeled",
            str(args.labeled),
            "--output",
            str(baseline_eval_path),
        ]
    )

    trained_eval = _load_json(eval_path)
    baseline_eval = _load_json(baseline_eval_path)
    comparison = compare_phase13_visual_models(trained_eval=trained_eval, baseline_eval=baseline_eval)
    comparison_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    history_csv = args.history_csv or (args.artifacts_dir / "phase13_history.csv")
    history_summary_output = args.history_summary_output or (args.artifacts_dir / "phase13_history_summary.json")
    history_row = build_phase13_experiment_history_row(
        run_name=str(args.run_name),
        model_name=str(trained_eval.get("model_name", "")),
        frame_exact_match_rate=float(trained_eval.get("frame_exact_match_rate", 0.0) or 0.0),
        object_precision=float(trained_eval.get("object_precision", 0.0) or 0.0),
        object_recall=float(trained_eval.get("object_recall", 0.0) or 0.0),
        promoted=bool(comparison.get("promoted", False)),
        manifest_path=str(manifest_path),
    )
    history_rows = _append_history_csv(history_csv, phase13_experiment_history_row_to_dict(history_row))
    history_summary = summarize_phase13_experiment_history(history_rows)
    history_summary_output.write_text(json.dumps(history_summary, indent=2), encoding="utf-8")

    manifest = {
        "schema_version": "phase13.manifest.v1",
        "status": "pass",
        "run_name": str(args.run_name),
        "artifacts": {
            "rendered_frame_manifest": str(rendered_manifest_path),
            "real_crop_dataset": str(crop_dataset_path),
            "annotation_manifest": str(annotation_path),
            "reviewed_crop_dataset": str(reviewed_dataset_path),
            "model": str(model_path),
            "trained_eval": str(eval_path),
            "baseline_eval": str(baseline_eval_path),
            "comparison": str(comparison_path),
            "history_csv": str(history_csv),
            "history_summary": str(history_summary_output),
        },
        "metrics": {
            "trained_frame_exact_match_rate": float(trained_eval.get("frame_exact_match_rate", 0.0) or 0.0),
            "baseline_frame_exact_match_rate": float(baseline_eval.get("frame_exact_match_rate", 0.0) or 0.0),
            "frame_exact_match_lift": float(comparison.get("frame_exact_match_lift", 0.0) or 0.0),
            "promoted": bool(comparison.get("promoted", False)),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {manifest_path}")


if __name__ == "__main__":
    main()
