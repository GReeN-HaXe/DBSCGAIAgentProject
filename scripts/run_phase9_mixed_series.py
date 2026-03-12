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
    parser = argparse.ArgumentParser(description="Run repeated selfplay-vs-mixed comparisons across multiple external sets.")
    parser.add_argument("--self-play-dataset", type=Path, required=True, help="Self-play-only Phase 7 dataset.")
    parser.add_argument("--external-set", type=Path, nargs="+", action="append", required=True, help="External input set; repeat the flag for multiple sets.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase9_mixed_series"), help="Output directory.")
    parser.add_argument("--model-type", choices=["frequency", "backoff"], default="backoff", help="Model type.")
    parser.add_argument("--target-field", choices=["action_type", "action_family"], default="action_type", help="Target field.")
    args = parser.parse_args()

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, object]] = []
    for idx, external_group in enumerate(args.external_set):
        run_dir = args.artifacts_dir / f"run_{idx + 1}"
        _run(
            [
                sys.executable,
                "scripts/compare_phase9_selfplay_vs_mixed.py",
                "--self-play-dataset",
                str(args.self_play_dataset),
                "--external-input",
                *[str(path) for path in external_group],
                "--artifacts-dir",
                str(run_dir),
                "--model-type",
                str(args.model_type),
                "--target-field",
                str(args.target_field),
            ]
        )
        report = _load_json(run_dir / "phase9_selfplay_vs_mixed_report.json")
        runs.append(
            {
                "run_index": idx + 1,
                "external_inputs": [str(path) for path in external_group],
                "report_path": str(run_dir / "phase9_selfplay_vs_mixed_report.json"),
                "top1_delta_mixed_minus_selfplay": float(report.get("top1_delta_mixed_minus_selfplay", 0.0) or 0.0),
            }
        )
    best = max(runs, key=lambda row: float(row.get("top1_delta_mixed_minus_selfplay", 0.0) or 0.0), default=None)
    summary = {
        "run_count": len(runs),
        "runs": runs,
        "best_run": best,
        "avg_top1_delta_mixed_minus_selfplay": 0.0 if not runs else sum(float(row.get("top1_delta_mixed_minus_selfplay", 0.0) or 0.0) for row in runs) / float(len(runs)),
    }
    out = args.artifacts_dir / "phase9_mixed_series_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()
