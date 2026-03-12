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

from src.agent import compare_phase15_vs_phase14_embedding, has_torch_support


def _run(cmd: list[str], *, stage_name: str, timeout_seconds: int) -> float:
    print(f"[phase15-triplet] start: {stage_name}")
    print(f"[phase15-triplet] cmd: {' '.join(cmd)}")
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        raise RuntimeError(f"stage timed out after {elapsed:.1f}s: {stage_name}") from exc
    elapsed = time.perf_counter() - started
    print(f"[phase15-triplet] done: {stage_name} ({elapsed:.1f}s)")
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")
    return elapsed


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate the Phase 15 explicit triplet embedding pipeline.")
    parser.add_argument("--feature-cache", type=Path, required=True)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase15_triplet"))
    parser.add_argument("--run-name", type=str, default="phase15_triplet_run")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--steps-per-epoch", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--hidden-dim", type=int, default=256)
    parser.add_argument("--embedding-dim", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=5e-4)
    parser.add_argument("--margin", type=float, default=0.2)
    parser.add_argument("--negative-mining", choices=["random", "hard"], default="random")
    parser.add_argument("--negative-pool-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--gallery-split", choices=["train", "validation", "all"], default="train")
    parser.add_argument("--query-split", choices=["train", "validation", "all"], default="validation")
    parser.add_argument("--stage-timeout-seconds", type=int, default=1800)
    parser.add_argument("--phase14-baseline", type=Path, default=None)
    args = parser.parse_args()

    if not has_torch_support():
        raise RuntimeError("PyTorch is not installed. Install requirements-torch.txt first.")

    feature_cache = args.feature_cache.resolve()
    artifacts_dir = args.artifacts_dir.resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifacts_dir / "phase15_triplet_model.json"
    retrieval_path = artifacts_dir / "phase15_triplet_retrieval.json"
    compare_path = artifacts_dir / "phase15_vs_phase14_compare.json"
    manifest_path = artifacts_dir / "phase15_triplet_manifest.json"

    stage_timings = [
        {
            "stage": "train_triplet_model",
            "duration_seconds": _run(
                [
                    sys.executable,
                    str((ROOT / "scripts" / "train_phase15_triplet_model.py").resolve()),
                    "--dataset",
                    str(feature_cache),
                    "--split",
                    "train",
                    "--epochs",
                    str(int(args.epochs)),
                    "--steps-per-epoch",
                    str(int(args.steps_per_epoch)),
                    "--batch-size",
                    str(int(args.batch_size)),
                    "--hidden-dim",
                    str(int(args.hidden_dim)),
                    "--embedding-dim",
                    str(int(args.embedding_dim)),
                    "--learning-rate",
                    str(float(args.learning_rate)),
                    "--margin",
                    str(float(args.margin)),
                    "--negative-mining",
                    str(args.negative_mining),
                    "--negative-pool-size",
                    str(int(args.negative_pool_size)),
                    "--seed",
                    str(int(args.seed)),
                    "--output",
                    str(model_path),
                ],
                stage_name="train_triplet_model",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        },
        {
            "stage": "evaluate_triplet_retrieval",
            "duration_seconds": _run(
                [
                    sys.executable,
                    str((ROOT / "scripts" / "evaluate_phase15_triplet_retrieval.py").resolve()),
                    "--model",
                    str(model_path),
                    "--dataset",
                    str(feature_cache),
                    "--gallery-split",
                    str(args.gallery_split),
                    "--query-split",
                    str(args.query_split),
                    "--output",
                    str(retrieval_path),
                ],
                stage_name="evaluate_triplet_retrieval",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        },
    ]

    retrieval = _load_json(retrieval_path)
    compare_payload: dict[str, object] = {}
    baseline_path = args.phase14_baseline.resolve() if args.phase14_baseline else None
    if baseline_path and baseline_path.exists():
        compare_payload = compare_phase15_vs_phase14_embedding(
            phase15_retrieval=retrieval,
            phase14_retrieval=_load_json(baseline_path),
        )
        compare_path.write_text(json.dumps(compare_payload, indent=2), encoding="utf-8")

    recall = retrieval.get("recall_at_k", {})
    if not isinstance(recall, dict):
        recall = {}
    manifest = {
        "schema_version": "phase15.triplet_manifest.v1",
        "status": "pass",
        "run_name": str(args.run_name),
        "artifacts": {
            "feature_cache": str(feature_cache),
            "model": str(model_path),
            "retrieval": str(retrieval_path),
        },
        "metrics": {
            "target_type": str(retrieval.get("target_type", "")),
            "gallery_split": str(retrieval.get("gallery_split", "")),
            "query_split": str(retrieval.get("query_split", "")),
            "example_count": int(retrieval.get("example_count", 0) or 0),
            "mean_reciprocal_rank": float(retrieval.get("mean_reciprocal_rank", 0.0) or 0.0),
            "mean_found_rank": float(retrieval.get("mean_found_rank", 0.0) or 0.0),
            "recall_at_1": float(recall.get("1", 0.0) or 0.0),
            "recall_at_5": float(recall.get("5", 0.0) or 0.0),
            "recall_at_10": float(recall.get("10", 0.0) or 0.0),
            "recall_at_20": float(recall.get("20", 0.0) or 0.0),
        },
        "training": {
            "epochs": int(args.epochs),
            "steps_per_epoch": int(args.steps_per_epoch),
            "batch_size": int(args.batch_size),
            "hidden_dim": int(args.hidden_dim),
            "embedding_dim": int(args.embedding_dim),
            "learning_rate": float(args.learning_rate),
            "margin": float(args.margin),
            "negative_mining": str(args.negative_mining),
            "negative_pool_size": int(args.negative_pool_size),
        },
        "phase14_comparison": compare_payload,
        "stage_timings": stage_timings,
    }
    if compare_payload:
        manifest["artifacts"]["phase14_comparison"] = str(compare_path)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {manifest_path}")


if __name__ == "__main__":
    main()
