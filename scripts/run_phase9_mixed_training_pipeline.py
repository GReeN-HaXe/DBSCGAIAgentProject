from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a mixed dataset and run the Phase 8 training pipeline on it.")
    parser.add_argument("--self-play-input", type=Path, nargs="*", default=[], help="Phase 7 self-play trace/dataset inputs.")
    parser.add_argument("--external-input", type=Path, nargs="*", default=[], help="Reviewed Phase 9 external match inputs.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase9_mixed_training"), help="Output artifact directory.")
    parser.add_argument("--model-type", choices=["frequency", "backoff"], default="backoff", help="Model type for Phase 8 training.")
    parser.add_argument("--target-field", choices=["action_type", "action_family"], default="action_type", help="Target field for training.")
    parser.add_argument("--train-split", choices=["train", "validation", "all"], default="train", help="Train split.")
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation", help="Eval split.")
    args = parser.parse_args()

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = args.artifacts_dir / "phase9_mixed_dataset.json"
    _run(
        [
            sys.executable,
            "scripts/build_phase9_mixed_dataset.py",
            *([ "--self-play-input", *[str(path) for path in args.self_play_input] ] if args.self_play_input else []),
            *([ "--external-input", *[str(path) for path in args.external_input] ] if args.external_input else []),
            "--output",
            str(dataset_path),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/run_phase8_training_pipeline.py",
            "--dataset",
            str(dataset_path),
            "--run-name",
            "phase9_mixed_training",
            "--model-type",
            str(args.model_type),
            "--target-field",
            str(args.target_field),
            "--train-split",
            str(args.train_split),
            "--eval-split",
            str(args.eval_split),
            "--artifacts-dir",
            str(args.artifacts_dir / "phase8_training"),
        ]
    )


if __name__ == "__main__":
    main()
