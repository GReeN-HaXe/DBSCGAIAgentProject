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
    parser = argparse.ArgumentParser(description="Run repeated self-play dataset generations and aggregate the outputs.")
    parser.add_argument("--runs", type=int, default=3, help="Number of self-play dataset runs to generate.")
    parser.add_argument("--games-per-run", type=int, default=2, help="Self-play games per generated dataset.")
    parser.add_argument("--max-actions", type=int, default=40, help="Action cap per self-play game.")
    parser.add_argument("--seed", type=int, default=31, help="Base seed for repeated runs.")
    parser.add_argument("--shuffle-decks", action="store_true", help="Shuffle decks in each generated run.")
    parser.add_argument("--p1-profile", type=str, default="balanced", help="P1 heuristic profile.")
    parser.add_argument("--p2-profile", type=str, default="balanced", help="P2 heuristic profile.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase8_self_play_series"), help="Output directory.")
    args = parser.parse_args()

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, object]] = []
    for idx in range(max(1, int(args.runs))):
        out = args.artifacts_dir / f"self_play_run_{idx + 1}.json"
        cmd = [
            sys.executable,
            "scripts/generate_phase8_self_play_dataset.py",
            "--games",
            str(max(1, int(args.games_per_run))),
            "--max-actions",
            str(max(1, int(args.max_actions))),
            "--seed",
            str(int(args.seed) + idx),
            "--p1-profile",
            str(args.p1_profile),
            "--p2-profile",
            str(args.p2_profile),
            "--output",
            str(out),
        ]
        if args.shuffle_decks:
            cmd.append("--shuffle-decks")
        _run(cmd)
        payload = _load_json(out)
        runs.append(
            {
                "run_index": idx + 1,
                "path": str(out),
                "example_count": int(payload.get("example_count", 0) or 0),
                "trajectory_count": int(payload.get("trajectory_count", 0) or 0),
                "sources": len(payload.get("sources", [])) if isinstance(payload.get("sources"), list) else 0,
            }
        )
    summary = {
        "run_count": len(runs),
        "total_examples": sum(int(item["example_count"]) for item in runs),
        "total_trajectories": sum(int(item["trajectory_count"]) for item in runs),
        "avg_examples_per_run": 0.0 if not runs else sum(int(item["example_count"]) for item in runs) / float(len(runs)),
        "runs": runs,
    }
    out = args.artifacts_dir / "phase8_self_play_series_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()
