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
    MockFrameRecognizer,
    benchmark_detection_manifest,
    build_phase12_experiment_history_row,
    compare_phase12_visual_models,
    phase12_experiment_history_row_to_dict,
    summarize_phase12_experiment_history,
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
    parser = argparse.ArgumentParser(description="Run the Phase 12 visual recognition pipeline end to end.")
    parser.add_argument("--frame-manifest", type=Path, required=True, help="Frame manifest JSON path.")
    parser.add_argument("--train-labeled", type=Path, nargs="+", required=True, help="Training labeled detection manifests.")
    parser.add_argument("--eval-labeled", type=Path, required=True, help="Evaluation labeled detection manifest.")
    parser.add_argument("--run-name", type=str, default="phase12_run", help="Experiment run name.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase12_pipeline"), help="Output artifact directory.")
    parser.add_argument("--history-csv", type=Path, default=None, help="Optional experiment history CSV path.")
    parser.add_argument("--history-summary-output", type=Path, default=None, help="Optional history summary JSON path.")
    args = parser.parse_args()

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    rendered_manifest_path = args.artifacts_dir / "phase12_rendered_frames.json"
    dataset_path = args.artifacts_dir / "phase12_crop_dataset.json"
    model_path = args.artifacts_dir / "phase12_visual_model.json"
    prediction_path = args.artifacts_dir / "phase12_visual_predictions.json"
    trained_eval_path = args.artifacts_dir / "phase12_visual_eval.json"
    baseline_eval_path = args.artifacts_dir / "phase12_baseline_eval.json"
    compare_path = args.artifacts_dir / "phase12_compare.json"
    manifest_path = args.artifacts_dir / "phase12_manifest.json"

    _run(
        [
            sys.executable,
            "scripts/render_phase12_synthetic_frames.py",
            "--frame-manifest",
            str(args.frame_manifest),
            "--labeled",
            str(args.eval_labeled),
            "--output-dir",
            str(args.artifacts_dir / "frames"),
            "--manifest-output",
            str(rendered_manifest_path),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/build_phase12_crop_dataset.py",
            "--frame-manifest",
            str(rendered_manifest_path),
            "--labeled",
            str(args.train_labeled[0]),
            "--output",
            str(dataset_path),
        ]
    )
    _run([sys.executable, "scripts/train_phase12_visual_model.py", "--dataset", str(dataset_path), "--output", str(model_path)])
    _run(
        [
            sys.executable,
            "scripts/run_phase12_visual_classifier.py",
            "--model",
            str(model_path),
            "--frame-manifest",
            str(rendered_manifest_path),
            "--proposal-manifest",
            str(args.eval_labeled),
            "--output",
            str(prediction_path),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/evaluate_phase12_visual_model.py",
            "--model",
            str(model_path),
            "--frame-manifest",
            str(rendered_manifest_path),
            "--proposal-manifest",
            str(args.eval_labeled),
            "--labeled",
            str(args.eval_labeled),
            "--output",
            str(trained_eval_path),
        ]
    )

    rendered_manifest = _load_json(rendered_manifest_path)
    eval_labeled = _load_json(args.eval_labeled)
    baseline_predicted = MockFrameRecognizer().detect(rendered_manifest)
    baseline_benchmark = benchmark_detection_manifest(baseline_predicted, eval_labeled)
    baseline_eval = {
        "schema_version": "phase12.visual_eval.v1",
        "model_name": "mock_frame_recognizer",
        "frame_count": int(baseline_benchmark.get("frame_count", 0) or 0),
        "object_precision": float(baseline_benchmark.get("object_precision", 0.0) or 0.0),
        "object_recall": float(baseline_benchmark.get("object_recall", 0.0) or 0.0),
        "frame_exact_match_rate": float(baseline_benchmark.get("frame_exact_match_rate", 0.0) or 0.0),
        "benchmark": baseline_benchmark,
    }
    baseline_eval_path.write_text(json.dumps(baseline_eval, indent=2), encoding="utf-8")

    trained_eval = _load_json(trained_eval_path)
    comparison = compare_phase12_visual_models(trained_eval=trained_eval, baseline_eval=baseline_eval)
    compare_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    history_csv = args.history_csv or (args.artifacts_dir / "phase12_history.csv")
    history_summary_output = args.history_summary_output or (args.artifacts_dir / "phase12_history_summary.json")
    history_row = build_phase12_experiment_history_row(
        run_name=str(args.run_name),
        model_name=str(trained_eval.get("model_name", "")),
        frame_exact_match_rate=float(trained_eval.get("frame_exact_match_rate", 0.0) or 0.0),
        object_precision=float(trained_eval.get("object_precision", 0.0) or 0.0),
        object_recall=float(trained_eval.get("object_recall", 0.0) or 0.0),
        promoted=bool(comparison.get("promoted", False)),
        manifest_path=str(manifest_path),
    )
    history_rows = _append_history_csv(history_csv, phase12_experiment_history_row_to_dict(history_row))
    history_summary = summarize_phase12_experiment_history(history_rows)
    history_summary_output.write_text(json.dumps(history_summary, indent=2), encoding="utf-8")

    manifest = {
        "schema_version": "phase12.manifest.v1",
        "status": "pass",
        "run_name": str(args.run_name),
        "artifacts": {
            "rendered_frame_manifest": str(rendered_manifest_path),
            "crop_dataset": str(dataset_path),
            "model": str(model_path),
            "predictions": str(prediction_path),
            "trained_eval": str(trained_eval_path),
            "baseline_eval": str(baseline_eval_path),
            "comparison": str(compare_path),
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
