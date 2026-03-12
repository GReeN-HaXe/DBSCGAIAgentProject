from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.phase22_state_encoder import compare_phase22_vs_backoff, summarize_phase22_target_distribution
from src.agent.phase22_experiments import build_phase22_model_manifest


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 22 structured-state pipeline and compare against backoff.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--run-name", type=str, default="phase22_run")
    parser.add_argument("--target-field", choices=["action_type", "action_family", "action_signature", "decision_class"], default="action_signature")
    parser.add_argument("--train-split", choices=["train", "validation", "all"], default="train")
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--embedding-dim", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--progress-every", type=int, default=0)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase22_pipeline"))
    args = parser.parse_args()

    artifacts_dir = args.artifacts_dir
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifacts_dir / "phase22_state_model.json"
    eval_path = artifacts_dir / "phase22_state_eval.json"
    baseline_model_path = artifacts_dir / "phase22_baseline_model.json"
    baseline_eval_path = artifacts_dir / "phase22_baseline_eval.json"
    compare_path = artifacts_dir / "phase22_compare.json"
    manifest_path = artifacts_dir / "phase22_manifest.json"
    dataset = _load_json(args.dataset)
    distribution = summarize_phase22_target_distribution(
        dataset,
        target_field=str(args.target_field),
        split=str(args.train_split),
    )
    if int(distribution.get("label_count", 0) or 0) < 2:
        manifest = {
            "schema_version": "phase22.pipeline.v1",
            "status": "skipped",
            "run_name": str(args.run_name),
            "dataset_path": str(args.dataset),
            "target_field": str(args.target_field),
            "train_split": str(args.train_split),
            "eval_split": str(args.eval_split),
            "reason": "insufficient_target_classes",
            "target_distribution": distribution,
            "artifacts": {
                "phase22_model": "",
                "phase22_eval": "",
                "baseline_model": "",
                "baseline_eval": "",
                "compare": "",
            },
            "metrics": {},
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"wrote: {manifest_path}")
        print("phase22 skipped: insufficient target classes")
        return

    _run(
        [
            sys.executable,
            "scripts/train_phase22_state_encoder.py",
            "--dataset",
            str(args.dataset),
            "--train-split",
            str(args.train_split),
            "--eval-split",
            str(args.eval_split),
            "--target-field",
            str(args.target_field),
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
            "--output",
            str(model_path),
            "--eval-output",
            str(eval_path),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/train_phase7_model.py",
            "--dataset",
            str(args.dataset),
            "--model-type",
            "backoff",
            "--target-field",
            str(args.target_field),
            "--context-mode",
            "identity",
            "--train-split",
            str(args.train_split),
            "--eval-split",
            str(args.eval_split),
            "--output",
            str(baseline_model_path),
            "--eval-output",
            str(baseline_eval_path),
        ]
    )

    phase22_eval = _load_json(eval_path)
    baseline_eval = _load_json(baseline_eval_path)
    compare_payload = compare_phase22_vs_backoff(phase22_eval=phase22_eval, baseline_eval=baseline_eval)
    compare_path.write_text(json.dumps(compare_payload, indent=2), encoding="utf-8")
    model_payload = _load_json(model_path)
    manifest = build_phase22_model_manifest(
        run_name=str(args.run_name),
        dataset_path=str(args.dataset),
        model_path=str(model_path),
        eval_path=str(eval_path),
        baseline_model_path=str(baseline_model_path),
        baseline_eval_path=str(baseline_eval_path),
        compare_path=str(compare_path),
        target_field=str(args.target_field),
        train_split=str(args.train_split),
        eval_split=str(args.eval_split),
        model_payload=model_payload,
        eval_payload=phase22_eval,
        baseline_eval_payload=baseline_eval,
        compare_payload=compare_payload,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {compare_path}")
    print(f"wrote: {manifest_path}")


if __name__ == "__main__":
    main()
