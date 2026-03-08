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


def _run(cmd: list[str], *, stage_name: str, timeout_seconds: int) -> float:
    print(f"[phase14-sweep] start: {stage_name}")
    print(f"[phase14-sweep] cmd: {' '.join(cmd)}")
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        raise RuntimeError(f"stage timed out after {elapsed:.1f}s: {stage_name}") from exc
    elapsed = time.perf_counter() - started
    print(f"[phase14-sweep] done: {stage_name} ({elapsed:.1f}s)")
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a batch sweep of Phase 14 PyTorch identity configs.")
    parser.add_argument("--feature-cache", type=Path, required=True)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase14_sweep"))
    parser.add_argument("--profile", choices=["quick", "standard", "extended"], default="standard")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--stage-timeout-seconds", type=int, default=1800)
    args = parser.parse_args()

    feature_cache = args.feature_cache.resolve()
    artifacts_dir = args.artifacts_dir.resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    configs = _configs_from_profile(args.profile)

    results: list[dict[str, object]] = []
    for config in configs:
        run_name = str(config["name"])
        run_dir = artifacts_dir / run_name
        duration = _run(
            [
                sys.executable,
                "scripts/run_phase14_identity_pipeline.py",
                "--feature-cache",
                str(feature_cache),
                "--run-name",
                run_name,
                "--artifacts-dir",
                str(run_dir),
                "--epochs",
                str(int(config["epochs"])),
                "--batch-size",
                str(int(args.batch_size)),
                "--hidden-dim",
                str(int(config["hidden_dim"])),
                "--learning-rate",
                str(float(config["learning_rate"])),
                "--seed",
                str(int(args.seed)),
                "--eval-split",
                str(args.eval_split),
            ],
            stage_name=f"run_{run_name}",
            timeout_seconds=int(args.stage_timeout_seconds),
        )
        manifest = _load_json(run_dir / "phase14_torch_manifest.json")
        metrics = manifest.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        results.append(
            {
                "config_name": run_name,
                "hidden_dim": int(config["hidden_dim"]),
                "epochs": int(config["epochs"]),
                "learning_rate": float(config["learning_rate"]),
                "top1_accuracy": float(metrics.get("top1_accuracy", 0.0) or 0.0),
                "top5_accuracy": float(metrics.get("top5_accuracy", 0.0) or 0.0),
                "top10_accuracy": float(metrics.get("top10_accuracy", 0.0) or 0.0),
                "example_count": int(metrics.get("example_count", 0) or 0),
                "duration_seconds": duration,
                "manifest_path": str(run_dir / "phase14_torch_manifest.json"),
            }
        )

    ranking = sorted(
        results,
        key=lambda row: (
            -float(row.get("top1_accuracy", 0.0) or 0.0),
            -float(row.get("top5_accuracy", 0.0) or 0.0),
            -float(row.get("top10_accuracy", 0.0) or 0.0),
            float(row.get("duration_seconds", 0.0) or 0.0),
            str(row.get("config_name", "")),
        ),
    )
    best = ranking[0] if ranking else {}
    summary = {
        "schema_version": "phase14.sweep.v1",
        "feature_cache": str(feature_cache),
        "profile": str(args.profile),
        "config_count": len(results),
        "best": best,
        "ranking": ranking,
    }
    summary_path = artifacts_dir / "phase14_sweep_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote: {summary_path}")


if __name__ == "__main__":
    main()
