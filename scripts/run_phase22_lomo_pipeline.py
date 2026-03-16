from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip())
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _dataset_secret_auto_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("secret_auto_summary", {})
    if not isinstance(summary, dict):
        return {
            "trace_count_with_secret_auto_opportunities": 0,
            "total_opportunity_count": 0,
            "total_pending_count": 0,
            "total_blocked_count": 0,
            "total_preblocked_count": 0,
            "status_counts": {},
        }
    status_counts_raw = summary.get("status_counts", {})
    status_counts = dict(status_counts_raw) if isinstance(status_counts_raw, dict) else {}
    return {
        "trace_count_with_secret_auto_opportunities": int(summary.get("trace_count_with_secret_auto_opportunities", 0) or 0),
        "total_opportunity_count": int(summary.get("total_opportunity_count", 0) or 0),
        "total_pending_count": int(summary.get("total_pending_count", 0) or 0),
        "total_blocked_count": int(summary.get("total_blocked_count", 0) or 0),
        "total_preblocked_count": int(summary.get("total_preblocked_count", 0) or 0),
        "status_counts": {str(key): int(value) for key, value in status_counts.items()},
    }


def _fold_name(path: Path) -> str:
    stem = path.stem.strip()
    return stem if stem else "fold"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run leave-one-matchup-out Phase 22 evaluation across benchmark datasets."
    )
    parser.add_argument("--dataset", nargs="+", type=Path, required=True, help="Two or more Phase 22 benchmark dataset JSON paths.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase22_lomo"))
    parser.add_argument("--target-field", choices=["action_type", "action_family", "action_signature", "decision_class"], default="decision_class")
    parser.add_argument("--train-split", choices=["train", "validation", "all"], default="train")
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--embedding-dim", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--progress-every", type=int, default=0)
    parser.add_argument("--summary-output", type=Path, default=None)
    args = parser.parse_args()

    if len(args.dataset) < 2:
        raise ValueError("need at least 2 datasets for leave-one-matchup-out evaluation")

    artifacts_dir = args.artifacts_dir
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.summary_output or (artifacts_dir / "phase22_lomo_summary.json")

    fold_rows: list[dict[str, Any]] = []
    overall_secret_status_counts: dict[str, int] = {}
    overall_holdout_secret_trace_count = 0
    overall_holdout_secret_opportunity_count = 0
    overall_holdout_secret_pending_count = 0
    overall_holdout_secret_blocked_count = 0
    overall_holdout_secret_preblocked_count = 0
    for holdout_path in args.dataset:
        train_inputs = [path for path in args.dataset if path != holdout_path]
        fold_name = _fold_name(holdout_path)
        fold_dir = artifacts_dir / fold_name
        fold_dir.mkdir(parents=True, exist_ok=True)
        merged_train_path = fold_dir / "phase22_lomo_train.json"
        merged_train_summary_path = fold_dir / "phase22_lomo_train_summary.json"
        holdout_payload = _load_json(holdout_path)
        holdout_secret_summary = _dataset_secret_auto_summary(holdout_payload)

        _run(
            [
                sys.executable,
                "scripts/build_phase22_merged_benchmark.py",
                "--input",
                *[str(path) for path in train_inputs],
                "--output",
                str(merged_train_path),
                "--summary-output",
                str(merged_train_summary_path),
            ]
        )

        _run(
            [
                sys.executable,
                "scripts/run_phase22_generalization_pipeline.py",
                "--train-dataset",
                str(merged_train_path),
                "--eval-dataset",
                str(holdout_path),
                "--run-name",
                f"phase22_lomo_{fold_name}",
                "--artifacts-dir",
                str(fold_dir),
                "--target-field",
                str(args.target_field),
                "--train-split",
                str(args.train_split),
                "--eval-split",
                str(args.eval_split),
                "--epochs",
                str(args.epochs),
                "--batch-size",
                str(args.batch_size),
                "--hidden-dim",
                str(args.hidden_dim),
                "--embedding-dim",
                str(args.embedding_dim),
                "--learning-rate",
                str(args.learning_rate),
                "--device",
                str(args.device),
                "--progress-every",
                str(args.progress_every),
            ]
        )

        batch_eval_path = fold_dir / "phase22_generalization_batch_eval.json"
        batch_eval = _load_json(batch_eval_path)
        merged_train_summary = _load_json(merged_train_summary_path)
        dataset_rows = batch_eval.get("datasets", [])
        if not isinstance(dataset_rows, list) or not dataset_rows:
            raise ValueError(f"expected one evaluated dataset row in {batch_eval_path}")
        holdout_metrics = dataset_rows[0]
        fold_rows.append(
            {
                "fold_name": fold_name,
                "holdout_dataset": str(holdout_path.resolve()),
                "train_dataset_count": len(train_inputs),
                "example_count": int(holdout_metrics.get("example_count", 0) or 0),
                "top1_accuracy": float(holdout_metrics.get("top1_accuracy", 0.0) or 0.0),
                "top_k_accuracy": dict(holdout_metrics.get("top_k_accuracy", {}))
                if isinstance(holdout_metrics.get("top_k_accuracy"), dict)
                else {},
                "artifacts_dir": str(fold_dir.resolve()),
                "production_dir": str((fold_dir / "production").resolve()),
                "batch_eval": str(batch_eval_path.resolve()),
                "holdout_secret_auto_summary": holdout_secret_summary,
                "train_secret_auto_summary": dict(merged_train_summary.get("secret_auto_summary", {}))
                if isinstance(merged_train_summary.get("secret_auto_summary"), dict)
                else {},
            }
        )
        overall_holdout_secret_trace_count += int(holdout_secret_summary.get("trace_count_with_secret_auto_opportunities", 0) or 0)
        overall_holdout_secret_opportunity_count += int(holdout_secret_summary.get("total_opportunity_count", 0) or 0)
        overall_holdout_secret_pending_count += int(holdout_secret_summary.get("total_pending_count", 0) or 0)
        overall_holdout_secret_blocked_count += int(holdout_secret_summary.get("total_blocked_count", 0) or 0)
        overall_holdout_secret_preblocked_count += int(holdout_secret_summary.get("total_preblocked_count", 0) or 0)
        status_counts = holdout_secret_summary.get("status_counts", {})
        if isinstance(status_counts, dict):
            for status, count in status_counts.items():
                label = str(status)
                overall_secret_status_counts[label] = int(overall_secret_status_counts.get(label, 0)) + int(count)

    overall_example_count = sum(int(row["example_count"]) for row in fold_rows)
    overall_top1 = (
        sum(float(row["top1_accuracy"]) * int(row["example_count"]) for row in fold_rows) / float(overall_example_count)
        if overall_example_count
        else 0.0
    )
    average_top1 = (
        sum(float(row["top1_accuracy"]) for row in fold_rows) / float(len(fold_rows))
        if fold_rows
        else 0.0
    )
    payload = {
        "schema_version": "phase22.lomo.v1",
        "target_field": str(args.target_field),
        "dataset_count": len(args.dataset),
        "overall_example_count": overall_example_count,
        "overall_top1_accuracy_weighted": overall_top1,
        "overall_top1_accuracy_macro": average_top1,
        "holdout_secret_auto_summary": {
            "trace_count_with_secret_auto_opportunities": int(overall_holdout_secret_trace_count),
            "total_opportunity_count": int(overall_holdout_secret_opportunity_count),
            "total_pending_count": int(overall_holdout_secret_pending_count),
            "total_blocked_count": int(overall_holdout_secret_blocked_count),
            "total_preblocked_count": int(overall_holdout_secret_preblocked_count),
            "status_counts": {status: int(overall_secret_status_counts[status]) for status in sorted(overall_secret_status_counts)},
        },
        "folds": fold_rows,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {summary_path}")


if __name__ == "__main__":
    main()
