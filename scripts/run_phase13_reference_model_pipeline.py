from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper. Phase 13 reference-model evaluation now uses card-identity evaluation, not gameplay object-role evaluation."
    )
    parser.add_argument("--reference-dataset", type=Path, default=Path("artifacts/phase13_reference_image_dataset.json"))
    parser.add_argument("--frame-manifest", type=Path, required=False, help="Ignored by the compatibility wrapper.")
    parser.add_argument("--labeled", type=Path, required=False, help="Ignored by the compatibility wrapper.")
    parser.add_argument("--run-name", type=str, default="phase13_reference_run")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase13_reference_pipeline"))
    parser.add_argument("--max-reference-examples", type=int, default=128)
    parser.add_argument("--stage-timeout-seconds", type=int, default=600)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation")
    args = parser.parse_args()

    print(
        "[phase13-reference] note: card-identity and object-role tasks are now separated. "
        "Delegating to scripts/run_phase13_reference_identity_pipeline.py"
    )
    cmd = [
        sys.executable,
        "scripts/run_phase13_reference_identity_pipeline.py",
        "--reference-dataset",
        str(args.reference_dataset),
        "--run-name",
        str(args.run_name),
        "--artifacts-dir",
        str(args.artifacts_dir),
        "--max-reference-examples",
        str(int(args.max_reference_examples)),
        "--stage-timeout-seconds",
        str(int(args.stage_timeout_seconds)),
        "--progress-every",
        str(int(args.progress_every)),
        "--eval-split",
        str(args.eval_split),
    ]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
