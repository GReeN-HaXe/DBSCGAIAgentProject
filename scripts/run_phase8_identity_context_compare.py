from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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


def _identity_coverage(dataset: dict[str, object]) -> dict[str, object]:
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        examples = []
    total = len([row for row in examples if isinstance(row, dict)])
    resolved = len([row for row in examples if isinstance(row, dict) and bool(row.get("has_identity_resolution"))])
    return {
        "example_count": total,
        "identity_resolved_example_count": resolved,
        "identity_resolved_example_rate": (float(resolved) / float(total)) if total else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run paired Phase 8 baseline vs identity-context experiments on the same dataset.")
    parser.add_argument("--dataset", type=Path, required=True, help="Phase 7 dataset JSON path.")
    parser.add_argument("--run-name", type=str, default="phase8_identity_compare", help="Logical run name prefix.")
    parser.add_argument("--model-type", choices=["frequency", "backoff"], default="backoff", help="Model family to train.")
    parser.add_argument("--target-field", choices=["action_type", "action_family"], default="action_type", help="Target field for training.")
    parser.add_argument("--train-split", choices=["train", "validation", "all"], default="train", help="Dataset split used for training.")
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation", help="Dataset split used for evaluation.")
    parser.add_argument("--profiles", nargs="+", default=["balanced", "aggressive", "control"], help="Heuristic profiles to compare against.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase8_identity_compare"), help="Output directory.")
    args = parser.parse_args()

    dataset = _load_json(args.dataset)
    coverage = _identity_coverage(dataset)
    args.artifacts_dir.mkdir(parents=True, exist_ok=True)

    baseline_dir = args.artifacts_dir / "baseline"
    identity_dir = args.artifacts_dir / "identity"

    common = [
        "--dataset",
        str(args.dataset),
        "--model-type",
        str(args.model_type),
        "--target-field",
        str(args.target_field),
        "--train-split",
        str(args.train_split),
        "--eval-split",
        str(args.eval_split),
        "--profiles",
        *[str(item) for item in args.profiles],
    ]

    _run(
        [
            sys.executable,
            "scripts/run_phase8_training_pipeline.py",
            *common,
            "--run-name",
            f"{args.run_name}_baseline",
            "--context-mode",
            "baseline",
            "--artifacts-dir",
            str(baseline_dir),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/run_phase8_training_pipeline.py",
            *common,
            "--run-name",
            f"{args.run_name}_identity",
            "--context-mode",
            "identity",
            "--artifacts-dir",
            str(identity_dir),
        ]
    )

    baseline_manifest = _load_json(baseline_dir / "phase8_model_manifest.json")
    identity_manifest = _load_json(identity_dir / "phase8_model_manifest.json")
    baseline_top1 = float(((baseline_manifest.get("metrics", {}) if isinstance(baseline_manifest.get("metrics"), dict) else {}).get("model_top1_accuracy", 0.0) or 0.0))
    identity_top1 = float(((identity_manifest.get("metrics", {}) if isinstance(identity_manifest.get("metrics"), dict) else {}).get("model_top1_accuracy", 0.0) or 0.0))
    baseline_identity_rate = float(((baseline_manifest.get("metrics", {}) if isinstance(baseline_manifest.get("metrics"), dict) else {}).get("identity_resolved_example_rate", 0.0) or 0.0))
    identity_identity_rate = float(((identity_manifest.get("metrics", {}) if isinstance(identity_manifest.get("metrics"), dict) else {}).get("identity_resolved_example_rate", 0.0) or 0.0))

    payload = {
        "schema_version": "phase8.identity_context_compare.v1",
        "dataset_path": str(args.dataset),
        "dataset_identity_coverage": coverage,
        "model_type": str(args.model_type),
        "target_field": str(args.target_field),
        "train_split": str(args.train_split),
        "eval_split": str(args.eval_split),
        "artifacts": {
            "baseline_dir": str(baseline_dir),
            "identity_dir": str(identity_dir),
            "baseline_manifest": str(baseline_dir / "phase8_model_manifest.json"),
            "identity_manifest": str(identity_dir / "phase8_model_manifest.json"),
        },
        "baseline": {
            "context_mode": "baseline",
            "top1_accuracy": baseline_top1,
            "identity_resolved_example_rate": baseline_identity_rate,
        },
        "identity": {
            "context_mode": "identity",
            "top1_accuracy": identity_top1,
            "identity_resolved_example_rate": identity_identity_rate,
        },
        "comparison": {
            "top1_lift_identity_minus_baseline": identity_top1 - baseline_top1,
            "dataset_has_identity_signal": bool(coverage["identity_resolved_example_count"]),
        },
    }
    out = args.artifacts_dir / "phase8_identity_context_compare.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()
