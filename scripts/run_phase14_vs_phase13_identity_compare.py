from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import compare_phase14_vs_phase13_identity, has_torch_support
from src.agent import (
    build_phase14_compare_history_row,
    phase14_compare_history_row_to_dict,
    summarize_phase14_compare_history,
)


def _run(cmd: list[str], *, stage_name: str, timeout_seconds: int) -> float:
    print(f"[phase14-compare] start: {stage_name}")
    print(f"[phase14-compare] cmd: {' '.join(cmd)}")
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        raise RuntimeError(f"stage timed out after {elapsed:.1f}s: {stage_name}") from exc
    elapsed = time.perf_counter() - started
    print(f"[phase14-compare] done: {stage_name} ({elapsed:.1f}s)")
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
        import csv

        with path.open("r", encoding="utf-8", newline="") as handle:
            existing = list(csv.DictReader(handle))
    rows = [*existing, row]
    path.parent.mkdir(parents=True, exist_ok=True)
    import csv

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Phase 13 KNN vs Phase 14 PyTorch on the same identity feature cache.")
    parser.add_argument("--feature-cache", type=Path, required=True)
    parser.add_argument("--run-name", type=str, default="phase14_vs_phase13_compare")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase14_vs_phase13_compare"))
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--stage-timeout-seconds", type=int, default=1800)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--history-csv", type=Path, default=None)
    parser.add_argument("--history-summary-output", type=Path, default=None)
    parser.add_argument("--min-top1-lift", type=float, default=0.0)
    parser.add_argument("--fail-on-no-promotion", action="store_true")
    args = parser.parse_args()

    if not has_torch_support():
        raise RuntimeError("PyTorch is not installed. Install requirements-torch.txt first.")

    feature_cache = args.feature_cache.resolve()
    artifacts_dir = args.artifacts_dir.resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    phase13_model_path = artifacts_dir / "phase13_identity_model.json"
    phase13_eval_path = artifacts_dir / "phase13_identity_eval.json"
    phase14_dir = artifacts_dir / "phase14_pipeline"
    phase14_eval_path = phase14_dir / "phase14_torch_eval.json"
    phase14_manifest_path = phase14_dir / "phase14_torch_manifest.json"
    compare_path = artifacts_dir / "phase14_vs_phase13_compare.json"
    manifest_path = artifacts_dir / "phase14_vs_phase13_compare_manifest.json"
    history_csv = args.history_csv.resolve() if args.history_csv else (artifacts_dir / "phase14_compare_history.csv")
    history_summary_output = (
        args.history_summary_output.resolve()
        if args.history_summary_output
        else (artifacts_dir / "phase14_compare_history_summary.json")
    )

    stage_timings = []
    stage_timings.append(
        {
            "stage": "train_phase13",
            "duration_seconds": _run(
                [
                    sys.executable,
                    "scripts/train_phase13_visual_model.py",
                    "--dataset",
                    str(feature_cache),
                    "--split",
                    "train",
                    "--k-neighbors",
                    "1",
                    "--output",
                    str(phase13_model_path),
                ],
                stage_name="train_phase13",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        }
    )
    stage_timings.append(
        {
            "stage": "evaluate_phase13",
            "duration_seconds": _run(
                [
                    sys.executable,
                    "scripts/evaluate_phase13_identity_model.py",
                    "--model",
                    str(phase13_model_path),
                    "--dataset",
                    str(feature_cache),
                    "--split",
                    str(args.eval_split),
                    "--output",
                    str(phase13_eval_path),
                ],
                stage_name="evaluate_phase13",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        }
    )
    stage_timings.append(
        {
            "stage": "run_phase14",
            "duration_seconds": _run(
                [
                    sys.executable,
                    "scripts/run_phase14_identity_pipeline.py",
                    "--feature-cache",
                    str(feature_cache),
                    "--run-name",
                    str(args.run_name),
                    "--artifacts-dir",
                    str(phase14_dir),
                    "--eval-split",
                    str(args.eval_split),
                    "--epochs",
                    str(int(args.epochs)),
                    "--batch-size",
                    str(int(args.batch_size)),
                    "--hidden-dim",
                    str(int(args.hidden_dim)),
                    "--learning-rate",
                    str(float(args.learning_rate)),
                ],
                stage_name="run_phase14",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        }
    )

    phase13_eval = _load_json(phase13_eval_path)
    phase14_eval = _load_json(phase14_eval_path)
    phase14_manifest = _load_json(phase14_manifest_path)
    comparison = compare_phase14_vs_phase13_identity(phase14_eval=phase14_eval, phase13_eval=phase13_eval)
    compare_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    promoted = bool(comparison.get("phase14_wins", False)) and float(comparison.get("top1_lift", 0.0) or 0.0) >= float(
        args.min_top1_lift
    )
    history_row = build_phase14_compare_history_row(
        run_name=str(args.run_name),
        top1_lift=float(comparison.get("top1_lift", 0.0) or 0.0),
        top5_lift=float(comparison.get("top5_lift", 0.0) or 0.0),
        top10_lift=float(comparison.get("top10_lift", 0.0) or 0.0),
        phase14_wins=bool(comparison.get("phase14_wins", False)),
        manifest_path=str(manifest_path),
    )
    history_rows = _append_history_csv(history_csv, phase14_compare_history_row_to_dict(history_row))
    history_summary = summarize_phase14_compare_history(history_rows)
    history_summary_output.write_text(json.dumps(history_summary, indent=2), encoding="utf-8")
    manifest = {
        "schema_version": "phase14.compare_manifest.v1",
        "status": "pass" if (not args.fail_on_no_promotion or promoted) else "fail",
        "run_name": str(args.run_name),
        "artifacts": {
            "feature_cache": str(feature_cache),
            "phase13_model": str(phase13_model_path),
            "phase13_evaluation": str(phase13_eval_path),
            "phase14_manifest": str(phase14_manifest_path),
            "phase14_evaluation": str(phase14_eval_path),
            "comparison": str(compare_path),
            "history_csv": str(history_csv),
            "history_summary": str(history_summary_output),
        },
        "metrics": comparison,
        "phase14_metrics": phase14_manifest.get("metrics", {}),
        "promotion": {
            "min_top1_lift": float(args.min_top1_lift),
            "promoted": promoted,
        },
        "stage_timings": stage_timings,
        "history": history_summary,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {compare_path}")
    print(f"wrote: {manifest_path}")
    if args.fail_on_no_promotion and not promoted:
        raise SystemExit("phase14_compare_promotion_failed")


if __name__ == "__main__":
    main()
