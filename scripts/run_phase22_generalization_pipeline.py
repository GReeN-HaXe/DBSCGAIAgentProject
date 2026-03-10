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


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a generalized Phase 22 model on a merged benchmark dataset and evaluate it across held-out benchmark datasets.")
    parser.add_argument("--train-dataset", type=Path, required=True, help="Merged Phase 22 benchmark dataset JSON path.")
    parser.add_argument("--eval-dataset", nargs="+", type=Path, required=True, help="One or more benchmark datasets for held-out batch evaluation.")
    parser.add_argument("--run-name", type=str, default="phase22_generalization")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase22_generalization"))
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
    args = parser.parse_args()

    artifacts_dir = args.artifacts_dir
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    pipeline_dir = artifacts_dir / "pipeline"
    production_dir = artifacts_dir / "production"
    best_config_path = artifacts_dir / "phase22_best_config.json"
    production_summary_path = production_dir / "phase22_production_summary.json"
    batch_eval_path = artifacts_dir / "phase22_generalization_batch_eval.json"
    summary_path = artifacts_dir / "phase22_generalization_summary.json"

    _run(
        [
            sys.executable,
            "scripts/run_phase22_state_pipeline.py",
            "--dataset",
            str(args.train_dataset),
            "--run-name",
            str(args.run_name),
            "--artifacts-dir",
            str(pipeline_dir),
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

    manifest_path = pipeline_dir / "phase22_manifest.json"
    best_config = {
        "schema_version": "phase22.best_config.v1",
        "profile": "manual",
        "target_field": str(args.target_field),
        "best": {
            "config_name": f"h{int(args.hidden_dim)}_e{int(args.epochs)}_lr{str(args.learning_rate).replace('.', '')}",
            "hidden_dim": int(args.hidden_dim),
            "epochs": int(args.epochs),
            "learning_rate": float(args.learning_rate),
            "manifest_path": str(manifest_path.resolve()),
        },
    }
    best_config_path.write_text(json.dumps(best_config, indent=2), encoding="utf-8")
    print(f"wrote: {best_config_path}")

    _run(
        [
            sys.executable,
            "scripts/promote_phase22_production.py",
            "--best-config",
            str(best_config_path),
            "--production-dir",
            str(production_dir),
            "--output",
            str(production_summary_path),
        ]
    )

    batch_cmd = [
        sys.executable,
        "scripts/run_phase22_batch_eval.py",
        "--production-dir",
        str(production_dir),
        "--output",
        str(batch_eval_path),
        "--split",
        str(args.eval_split),
    ]
    for dataset_path in args.eval_dataset:
        batch_cmd.extend(["--dataset", str(dataset_path)])
    # run_phase22_batch_eval expects all dataset paths after one --dataset
    batch_cmd = [
        sys.executable,
        "scripts/run_phase22_batch_eval.py",
        "--dataset",
        *[str(path) for path in args.eval_dataset],
        "--production-dir",
        str(production_dir),
        "--output",
        str(batch_eval_path),
        "--split",
        str(args.eval_split),
    ]
    _run(batch_cmd)

    summary = {
        "schema_version": "phase22.generalization.v1",
        "train_dataset": str(args.train_dataset.resolve()),
        "eval_datasets": [str(path.resolve()) for path in args.eval_dataset],
        "target_field": str(args.target_field),
        "pipeline_manifest": str(manifest_path.resolve()),
        "best_config": str(best_config_path.resolve()),
        "production_summary": str(production_summary_path.resolve()),
        "batch_eval": str(batch_eval_path.resolve()),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote: {summary_path}")


if __name__ == "__main__":
    main()
