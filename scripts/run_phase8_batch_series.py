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
    parser = argparse.ArgumentParser(description="Run repeated self-play series and batch experiments, then aggregate results.")
    parser.add_argument("--runs", type=int, default=3, help="Number of repeated self-play series runs.")
    parser.add_argument("--games-per-run", type=int, default=2, help="Games per generated self-play dataset.")
    parser.add_argument("--max-actions", type=int, default=40, help="Action cap per self-play game.")
    parser.add_argument("--seed", type=int, default=41, help="Base seed for repeated runs.")
    parser.add_argument("--model-type", choices=["frequency", "backoff"], default="backoff", help="Model type used in batch runs.")
    parser.add_argument("--target-field", choices=["action_type", "action_family"], default="action_type", help="Target field for batch runs.")
    parser.add_argument("--slice-field", type=str, default="setup.archetype_pair", help="Slice field for batch runs.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase8_batch_series"), help="Output directory.")
    args = parser.parse_args()

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, object]] = []
    for idx in range(max(1, int(args.runs))):
        run_dir = args.artifacts_dir / f"series_run_{idx + 1}"
        dataset_path = run_dir / "self_play_dataset.json"
        _run(
            [
                sys.executable,
                "scripts/generate_phase8_self_play_dataset.py",
                "--games",
                str(max(1, int(args.games_per_run))),
                "--max-actions",
                str(max(1, int(args.max_actions))),
                "--seed",
                str(int(args.seed) + idx),
                "--output",
                str(dataset_path),
            ]
        )
        _run(
            [
                sys.executable,
                "scripts/run_phase8_batch_experiments.py",
                "--dataset",
                str(dataset_path),
                "--slice-field",
                str(args.slice_field),
                "--model-type",
                str(args.model_type),
                "--target-field",
                str(args.target_field),
                "--artifacts-dir",
                str(run_dir / "batch"),
            ]
        )
        batch_summary = _load_json(run_dir / "batch" / "phase8_batch_summary.json")
        promotion = batch_summary.get("promotion_summary", {})
        runs.append(
            {
                "run_index": idx + 1,
                "dataset_path": str(dataset_path),
                "batch_summary_path": str(run_dir / "batch" / "phase8_batch_summary.json"),
                "run_count": int(batch_summary.get("run_count", 0) or 0),
                "promoted_run_count": int(promotion.get("promoted_run_count", 0) or 0),
                "best_promoted": promotion.get("best_promoted"),
            }
        )
    best_promoted_candidates = [row["best_promoted"] for row in runs if isinstance(row.get("best_promoted"), dict)]
    best_promoted = None
    if best_promoted_candidates:
        best_promoted = sorted(
            best_promoted_candidates,
            key=lambda row: (-float(row.get("top1_accuracy", 0.0) or 0.0), str(row.get("slice_value", ""))),
        )[0]
    summary = {
        "run_count": len(runs),
        "runs": runs,
        "total_promoted_runs": sum(int(row.get("promoted_run_count", 0) or 0) for row in runs),
        "best_promoted_overall": best_promoted,
    }
    out = args.artifacts_dir / "phase8_batch_series_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()

