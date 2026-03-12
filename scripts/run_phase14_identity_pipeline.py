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
    build_phase14_identity_history_row,
    has_torch_support,
    phase14_identity_history_row_to_dict,
    summarize_phase14_identity_history,
)


def _run(cmd: list[str], *, stage_name: str, timeout_seconds: int) -> float:
    print(f"[phase14-torch] start: {stage_name}")
    print(f"[phase14-torch] cmd: {' '.join(cmd)}")
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        raise RuntimeError(f"stage timed out after {elapsed:.1f}s: {stage_name}") from exc
    elapsed = time.perf_counter() - started
    print(f"[phase14-torch] done: {stage_name} ({elapsed:.1f}s)")
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")
    return elapsed


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _append_history_csv(path: Path, row: dict[str, str]) -> list[dict[str, str]]:
    existing: list[dict[str, str]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as handle:
            existing = list(csv.DictReader(handle))
    rows = [*existing, row]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate the Phase 14 PyTorch identity model.")
    parser.add_argument("--feature-cache", type=Path, default=Path("artifacts/phase13_reference_identity_feature_cache.json"))
    parser.add_argument("--run-name", type=str, default="phase14_identity_run")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase14_identity_pipeline"))
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--progress-every", type=int, default=5)
    parser.add_argument("--stage-timeout-seconds", type=int, default=1800)
    parser.add_argument("--history-csv", type=Path, default=None)
    parser.add_argument("--history-summary-output", type=Path, default=None)
    args = parser.parse_args()
    feature_cache = args.feature_cache.resolve()

    if not has_torch_support():
        raise RuntimeError(
            "PyTorch is not installed. Install the dependencies in requirements-torch.txt, then rerun."
        )

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = args.artifacts_dir.resolve()
    model_path = artifacts_dir / "phase14_torch_model.json"
    eval_path = artifacts_dir / "phase14_torch_eval.json"
    manifest_path = artifacts_dir / "phase14_torch_manifest.json"
    history_csv = args.history_csv.resolve() if args.history_csv else (artifacts_dir / "phase14_identity_history.csv")
    history_summary_output = (
        args.history_summary_output.resolve()
        if args.history_summary_output
        else (artifacts_dir / "phase14_identity_history_summary.json")
    )

    stage_timings = [
        {
            "stage": "train_torch_model",
            "duration_seconds": _run(
                [
                    sys.executable,
                    "scripts/train_phase14_torch_model.py",
                    "--dataset",
                    str(feature_cache),
                    "--split",
                    "train",
                    "--epochs",
                    str(int(args.epochs)),
                    "--batch-size",
                    str(int(args.batch_size)),
                    "--hidden-dim",
                    str(int(args.hidden_dim)),
                    "--learning-rate",
                    str(float(args.learning_rate)),
                    "--seed",
                    str(int(args.seed)),
                    "--device",
                    str(args.device),
                    "--progress-every",
                    str(int(args.progress_every)),
                    "--output",
                    str(model_path),
                ],
                stage_name="train_torch_model",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        },
        {
            "stage": "evaluate_torch_model",
            "duration_seconds": _run(
                [
                    sys.executable,
                    "scripts/evaluate_phase14_torch_model.py",
                    "--model",
                    str(model_path),
                    "--dataset",
                    str(feature_cache),
                    "--split",
                    str(args.eval_split),
                    "--batch-size",
                    str(max(64, int(args.batch_size))),
                    "--output",
                    str(eval_path),
                ],
                stage_name="evaluate_torch_model",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        },
    ]

    eval_payload = _load_json(eval_path)
    top_k_accuracy = eval_payload.get("top_k_accuracy", {})
    history_row = build_phase14_identity_history_row(
        run_name=str(args.run_name),
        top1_accuracy=float(eval_payload.get("top1_accuracy", 0.0) or 0.0),
        top5_accuracy=float((top_k_accuracy.get("5", 0.0) if isinstance(top_k_accuracy, dict) else 0.0) or 0.0),
        top10_accuracy=float((top_k_accuracy.get("10", 0.0) if isinstance(top_k_accuracy, dict) else 0.0) or 0.0),
        example_count=int(eval_payload.get("example_count", 0) or 0),
        manifest_path=str(manifest_path),
    )
    history_rows = _append_history_csv(history_csv, phase14_identity_history_row_to_dict(history_row))
    history_summary = summarize_phase14_identity_history(history_rows)
    history_summary_output.write_text(json.dumps(history_summary, indent=2), encoding="utf-8")

    manifest = {
        "schema_version": "phase14.identity_manifest.v1",
        "status": "pass",
        "run_name": str(args.run_name),
        "artifacts": {
            "feature_cache": str(feature_cache),
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
            "model_label_count": int(eval_payload.get("model_label_count", 0) or 0),
            "dataset_label_count": int(eval_payload.get("dataset_label_count", 0) or 0),
            "unseen_expected_label_count": int(eval_payload.get("unseen_expected_label_count", 0) or 0),
            "unseen_example_count": int(eval_payload.get("unseen_example_count", 0) or 0),
        },
        "stage_timings": stage_timings,
        "history": history_summary,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {manifest_path}")


if __name__ == "__main__":
    main()
