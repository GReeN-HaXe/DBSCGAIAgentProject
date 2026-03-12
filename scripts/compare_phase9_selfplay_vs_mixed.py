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


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Phase 8 training on self-play-only data vs mixed self-play+external data.")
    parser.add_argument("--self-play-dataset", type=Path, required=True, help="Self-play-only Phase 7 dataset.")
    parser.add_argument("--external-input", type=Path, nargs="*", default=[], help="Reviewed Phase 9 external match inputs.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase9_selfplay_vs_mixed"), help="Output artifact directory.")
    parser.add_argument("--model-type", choices=["frequency", "backoff"], default="backoff", help="Model type for training.")
    parser.add_argument("--target-field", choices=["action_type", "action_family"], default="action_type", help="Target field.")
    args = parser.parse_args()

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    selfplay_dir = args.artifacts_dir / "selfplay_only"
    mixed_dir = args.artifacts_dir / "mixed"

    _run(
        [
            sys.executable,
            "scripts/run_phase8_training_pipeline.py",
            "--dataset",
            str(args.self_play_dataset),
            "--run-name",
            "selfplay_only",
            "--model-type",
            str(args.model_type),
            "--target-field",
            str(args.target_field),
            "--artifacts-dir",
            str(selfplay_dir),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/run_phase9_mixed_training_pipeline.py",
            "--self-play-input",
            str(args.self_play_dataset),
            *([ "--external-input", *[str(path) for path in args.external_input] ] if args.external_input else []),
            "--artifacts-dir",
            str(mixed_dir),
            "--model-type",
            str(args.model_type),
            "--target-field",
            str(args.target_field),
        ]
    )
    selfplay_manifest = _load_json(selfplay_dir / "phase8_model_manifest.json")
    mixed_manifest = _load_json(mixed_dir / "phase8_training" / "phase8_model_manifest.json")
    selfplay_top1 = float(selfplay_manifest.get("metrics", {}).get("model_top1_accuracy", 0.0) or 0.0)
    mixed_top1 = float(mixed_manifest.get("metrics", {}).get("model_top1_accuracy", 0.0) or 0.0)
    payload = {
        "model_type": str(args.model_type),
        "target_field": str(args.target_field),
        "selfplay_only": selfplay_manifest,
        "mixed": mixed_manifest,
        "top1_delta_mixed_minus_selfplay": mixed_top1 - selfplay_top1,
    }
    out = args.artifacts_dir / "phase9_selfplay_vs_mixed_report.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()
