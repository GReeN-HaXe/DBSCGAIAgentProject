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

from src.agent import has_torch_support


def _run(cmd: list[str], *, stage_name: str, timeout_seconds: int) -> float:
    print(f"[phase16-cnn] start: {stage_name}")
    print(f"[phase16-cnn] cmd: {' '.join(cmd)}")
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        raise RuntimeError(f"stage timed out after {elapsed:.1f}s: {stage_name}") from exc
    elapsed = time.perf_counter() - started
    print(f"[phase16-cnn] done: {stage_name} ({elapsed:.1f}s)")
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")
    return elapsed


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate a bounded Phase 16 CNN pipeline.")
    parser.add_argument("--dataset", type=Path, default=Path("artifacts/phase13_reference_image_dataset.json"))
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase16_cnn"))
    parser.add_argument("--run-name", type=str, default="phase16_cnn_run")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--image-size", type=int, default=32)
    parser.add_argument("--embedding-dim", type=int, default=128)
    parser.add_argument("--max-train-examples", type=int, default=1024)
    parser.add_argument("--max-gallery-examples", type=int, default=1024)
    parser.add_argument("--max-query-examples", type=int, default=512)
    parser.add_argument("--stage-timeout-seconds", type=int, default=1800)
    args = parser.parse_args()

    if not has_torch_support():
        raise RuntimeError("PyTorch is not installed. Install requirements-torch.txt first.")

    dataset = args.dataset.resolve()
    artifacts_dir = args.artifacts_dir.resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifacts_dir / "phase16_cnn_model.json"
    retrieval_path = artifacts_dir / "phase16_cnn_retrieval.json"
    manifest_path = artifacts_dir / "phase16_cnn_manifest.json"

    stage_timings = [
        {
            "stage": "train_cnn_model",
            "duration_seconds": _run(
                [
                    sys.executable,
                    str((ROOT / "scripts" / "train_phase16_cnn_model.py").resolve()),
                    "--dataset",
                    str(dataset),
                    "--split",
                    "train",
                    "--epochs",
                    str(int(args.epochs)),
                    "--batch-size",
                    str(int(args.batch_size)),
                    "--learning-rate",
                    str(float(args.learning_rate)),
                    "--image-size",
                    str(int(args.image_size)),
                    "--embedding-dim",
                    str(int(args.embedding_dim)),
                    "--max-examples",
                    str(int(args.max_train_examples)),
                    "--output",
                    str(model_path),
                ],
                stage_name="train_cnn_model",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        },
        {
            "stage": "evaluate_cnn_retrieval",
            "duration_seconds": _run(
                [
                    sys.executable,
                    str((ROOT / "scripts" / "evaluate_phase16_cnn_retrieval.py").resolve()),
                    "--model",
                    str(model_path),
                    "--dataset",
                    str(dataset),
                    "--gallery-split",
                    "train",
                    "--query-split",
                    "validation",
                    "--batch-size",
                    str(int(args.batch_size) * 2),
                    "--max-gallery-examples",
                    str(int(args.max_gallery_examples)),
                    "--max-query-examples",
                    str(int(args.max_query_examples)),
                    "--output",
                    str(retrieval_path),
                ],
                stage_name="evaluate_cnn_retrieval",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        },
    ]

    retrieval = _load_json(retrieval_path)
    recall = retrieval.get("recall_at_k", {})
    if not isinstance(recall, dict):
        recall = {}
    manifest = {
        "schema_version": "phase16.cnn_manifest.v1",
        "status": "pass",
        "run_name": str(args.run_name),
        "artifacts": {
            "dataset": str(dataset),
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
            "batch_size": int(args.batch_size),
            "learning_rate": float(args.learning_rate),
            "image_size": int(args.image_size),
            "embedding_dim": int(args.embedding_dim),
            "max_train_examples": int(args.max_train_examples),
            "max_gallery_examples": int(args.max_gallery_examples),
            "max_query_examples": int(args.max_query_examples),
        },
        "stage_timings": stage_timings,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {manifest_path}")


if __name__ == "__main__":
    main()
