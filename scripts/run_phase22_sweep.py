from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.phase22_experiments import (
    build_phase22_experiment_history_row,
    phase22_experiment_history_row_to_dict,
    summarize_phase22_experiment_history,
)


def _run(cmd: list[str], *, stage_name: str, timeout_seconds: int) -> float:
    print(f"[phase22-sweep] start: {stage_name}")
    print(f"[phase22-sweep] cmd: {' '.join(cmd)}")
    started = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
    elapsed = time.perf_counter() - started
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip())
    print(f"[phase22-sweep] done: {stage_name} ({elapsed:.1f}s)")
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")
    return elapsed


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _configs_from_profile(profile: str) -> list[dict[str, int | float | str]]:
    normalized = str(profile or "standard").strip().lower()
    if normalized == "quick":
        return [
            {"name": "h64_e10_lr1e3", "hidden_dim": 64, "epochs": 10, "learning_rate": 1e-3},
            {"name": "h128_e10_lr1e3", "hidden_dim": 128, "epochs": 10, "learning_rate": 1e-3},
        ]
    if normalized == "standard":
        return [
            {"name": "h64_e20_lr1e3", "hidden_dim": 64, "epochs": 20, "learning_rate": 1e-3},
            {"name": "h128_e20_lr1e3", "hidden_dim": 128, "epochs": 20, "learning_rate": 1e-3},
            {"name": "h256_e20_lr5e4", "hidden_dim": 256, "epochs": 20, "learning_rate": 5e-4},
        ]
    if normalized == "extended":
        return [
            {"name": "h64_e20_lr1e3", "hidden_dim": 64, "epochs": 20, "learning_rate": 1e-3},
            {"name": "h128_e20_lr1e3", "hidden_dim": 128, "epochs": 20, "learning_rate": 1e-3},
            {"name": "h256_e20_lr5e4", "hidden_dim": 256, "epochs": 20, "learning_rate": 5e-4},
            {"name": "h256_e30_lr1e3", "hidden_dim": 256, "epochs": 30, "learning_rate": 1e-3},
            {"name": "h384_e20_lr5e4", "hidden_dim": 384, "epochs": 20, "learning_rate": 5e-4},
        ]
    raise ValueError(f"unsupported profile={profile!r}")


def _append_history(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    existing: list[dict[str, str]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as fh:
            existing = list(csv.DictReader(fh))
    merged = existing + rows
    fieldnames = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a batch sweep of Phase 22 state encoder configs.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase22_sweep"))
    parser.add_argument("--profile", choices=["quick", "standard", "extended"], default="standard")
    parser.add_argument("--target-field", choices=["action_type", "action_family", "action_signature", "decision_class"], default="decision_class")
    parser.add_argument("--train-split", choices=["train", "validation", "all"], default="train")
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--embedding-dim", type=int, default=16)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--progress-every", type=int, default=0)
    parser.add_argument("--stage-timeout-seconds", type=int, default=1800)
    parser.add_argument("--history-csv", type=Path, default=None)
    parser.add_argument("--history-summary-json", type=Path, default=None)
    args = parser.parse_args()

    dataset = args.dataset.resolve()
    artifacts_dir = args.artifacts_dir.resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    configs = _configs_from_profile(args.profile)

    results: list[dict[str, object]] = []
    history_rows: list[dict[str, str]] = []
    for config in configs:
        run_name = str(config["name"])
        run_dir = artifacts_dir / run_name
        duration = _run(
            [
                sys.executable,
                "scripts/run_phase22_state_pipeline.py",
                "--dataset",
                str(dataset),
                "--run-name",
                run_name,
                "--artifacts-dir",
                str(run_dir),
                "--target-field",
                str(args.target_field),
                "--train-split",
                str(args.train_split),
                "--eval-split",
                str(args.eval_split),
                "--epochs",
                str(int(config["epochs"])),
                "--batch-size",
                str(int(args.batch_size)),
                "--hidden-dim",
                str(int(config["hidden_dim"])),
                "--embedding-dim",
                str(int(args.embedding_dim)),
                "--learning-rate",
                str(float(config["learning_rate"])),
                "--device",
                str(args.device),
                "--progress-every",
                str(int(args.progress_every)),
            ],
            stage_name=f"run_{run_name}",
            timeout_seconds=int(args.stage_timeout_seconds),
        )
        manifest = _load_json(run_dir / "phase22_manifest.json")
        metrics = manifest.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        result_row = {
            "config_name": run_name,
            "hidden_dim": int(config["hidden_dim"]),
            "epochs": int(config["epochs"]),
            "learning_rate": float(config["learning_rate"]),
            "top1_accuracy": float(metrics.get("phase22_top1_accuracy", 0.0) or 0.0),
            "baseline_top1_accuracy": float(metrics.get("baseline_top1_accuracy", 0.0) or 0.0),
            "top1_lift": float(metrics.get("top1_lift", 0.0) or 0.0),
            "phase22_wins": bool(metrics.get("phase22_wins", False)),
            "duration_seconds": duration,
            "manifest_path": str(run_dir / "phase22_manifest.json"),
        }
        results.append(result_row)
        history_rows.append(
            phase22_experiment_history_row_to_dict(
                build_phase22_experiment_history_row(
                    run_name=run_name,
                    model_name=str(manifest.get("model_name", "phase22_state_encoder")),
                    baseline_model_name=str(manifest.get("baseline_model_name", "backoff_frequency_policy")),
                    target_field=str(manifest.get("target_field", args.target_field)),
                    train_split=str(manifest.get("train_split", args.train_split)),
                    eval_split=str(manifest.get("eval_split", args.eval_split)),
                    example_count=int(metrics.get("example_count", 0) or 0),
                    top1_accuracy=float(metrics.get("phase22_top1_accuracy", 0.0) or 0.0),
                    baseline_top1_accuracy=float(metrics.get("baseline_top1_accuracy", 0.0) or 0.0),
                    top1_lift=float(metrics.get("top1_lift", 0.0) or 0.0),
                    wins=bool(metrics.get("phase22_wins", False)),
                    status=str(manifest.get("status", "pass")),
                    manifest_path=str(run_dir / "phase22_manifest.json"),
                )
            )
        )

    ranking = sorted(
        results,
        key=lambda row: (
            -float(row.get("top1_lift", 0.0) or 0.0),
            -float(row.get("top1_accuracy", 0.0) or 0.0),
            float(row.get("duration_seconds", 0.0) or 0.0),
            str(row.get("config_name", "")),
        ),
    )
    best = ranking[0] if ranking else {}
    summary = {
        "schema_version": "phase22.sweep.v1",
        "dataset": str(dataset),
        "profile": str(args.profile),
        "target_field": str(args.target_field),
        "config_count": len(results),
        "best": best,
        "ranking": ranking,
    }
    summary_path = artifacts_dir / "phase22_sweep_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote: {summary_path}")

    if args.history_csv is not None:
        _append_history(args.history_csv, history_rows)
        print(f"wrote: {args.history_csv}")
    if args.history_summary_json is not None and args.history_csv is not None:
        with args.history_csv.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        history_summary = summarize_phase22_experiment_history(rows)
        args.history_summary_json.write_text(json.dumps(history_summary, indent=2), encoding="utf-8")
        print(f"wrote: {args.history_summary_json}")


if __name__ == "__main__":
    main()
