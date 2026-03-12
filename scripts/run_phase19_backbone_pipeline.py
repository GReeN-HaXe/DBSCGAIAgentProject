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

from src.agent import compare_phase19_vs_phase17_retrieval, has_torchvision_support


def _run(cmd: list[str], *, stage_name: str, timeout_seconds: int) -> float:
    print(f"[phase19-backbone] start: {stage_name}")
    print(f"[phase19-backbone] cmd: {' '.join(cmd)}")
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        raise RuntimeError(f"stage timed out after {elapsed:.1f}s: {stage_name}") from exc
    elapsed = time.perf_counter() - started
    print(f"[phase19-backbone] done: {stage_name} ({elapsed:.1f}s)")
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")
    return elapsed


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate the Phase 19 stronger-backbone pipeline.")
    parser.add_argument("--dataset", type=Path, default=Path("artifacts/phase13_reference_image_dataset.json"))
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase19_backbone"))
    parser.add_argument("--run-name", type=str, default="phase19_backbone_run")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--image-size", type=int, default=96)
    parser.add_argument("--weights-mode", choices=["default", "none"], default="default")
    parser.add_argument("--freeze-backbone-epochs", type=int, default=0)
    parser.add_argument("--max-train-examples", type=int, default=512)
    parser.add_argument("--max-gallery-examples", type=int, default=512)
    parser.add_argument("--max-query-examples", type=int, default=256)
    parser.add_argument("--stage-timeout-seconds", type=int, default=3600)
    args = parser.parse_args()

    if not has_torchvision_support():
        raise RuntimeError("PyTorch/torchvision are not installed. Install requirements-torch.txt first.")

    dataset = args.dataset.resolve()
    artifacts_dir = args.artifacts_dir.resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifacts_dir / "phase19_resnet50_model.json"
    retrieval_path = artifacts_dir / "phase19_resnet50_retrieval.json"
    phase17_path = artifacts_dir / "phase17_resnet18_retrieval.json"
    compare_path = artifacts_dir / "phase19_vs_phase17_compare.json"
    manifest_path = artifacts_dir / "phase19_backbone_manifest.json"

    stage_timings = [
        {
            "stage": "train_phase19_resnet50_model",
            "duration_seconds": _run(
                [
                    sys.executable,
                    str((ROOT / "scripts" / "train_phase19_resnet50_model.py").resolve()),
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
                    "--max-examples",
                    str(int(args.max_train_examples)),
                    "--weights-mode",
                    str(args.weights_mode),
                    "--freeze-backbone-epochs",
                    str(int(args.freeze_backbone_epochs)),
                    "--output",
                    str(model_path),
                ],
                stage_name="train_phase19_resnet50_model",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        },
        {
            "stage": "evaluate_phase19_resnet50_retrieval",
            "duration_seconds": _run(
                [
                    sys.executable,
                    str((ROOT / "scripts" / "evaluate_phase19_resnet50_retrieval.py").resolve()),
                    "--model",
                    str(model_path),
                    "--dataset",
                    str(dataset),
                    "--gallery-split",
                    "train",
                    "--query-split",
                    "validation",
                    "--batch-size",
                    str(max(32, int(args.batch_size) * 2)),
                    "--max-gallery-examples",
                    str(int(args.max_gallery_examples)),
                    "--max-query-examples",
                    str(int(args.max_query_examples)),
                    "--output",
                    str(retrieval_path),
                ],
                stage_name="evaluate_phase19_resnet50_retrieval",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        },
        {
            "stage": "evaluate_phase17_resnet18_retrieval_baseline",
            "duration_seconds": _run(
                [
                    sys.executable,
                    str((ROOT / "scripts" / "evaluate_phase17_resnet18_retrieval.py").resolve()),
                    "--model",
                    str((artifacts_dir.parent / "phase17_backbone_default_2048" / "phase17_resnet18_model.json").resolve()
                        if int(args.max_train_examples) == 2048 and str(args.weights_mode) == "default"
                        else (artifacts_dir.parent / "phase17_backbone_default_512_freeze1" / "phase17_resnet18_model.json").resolve()),
                    "--dataset",
                    str(dataset),
                    "--gallery-split",
                    "train",
                    "--query-split",
                    "validation",
                    "--batch-size",
                    str(max(32, int(args.batch_size) * 2)),
                    "--max-gallery-examples",
                    str(int(args.max_gallery_examples)),
                    "--max-query-examples",
                    str(int(args.max_query_examples)),
                    "--output",
                    str(phase17_path),
                ],
                stage_name="evaluate_phase17_resnet18_retrieval_baseline",
                timeout_seconds=int(args.stage_timeout_seconds),
            ),
        },
    ]

    model = _load_json(model_path)
    retrieval = _load_json(retrieval_path)
    phase17 = _load_json(phase17_path)
    compare = compare_phase19_vs_phase17_retrieval(phase19_retrieval=retrieval, phase17_retrieval=phase17)
    compare_path.write_text(json.dumps(compare, indent=2), encoding="utf-8")

    recall = retrieval.get("recall_at_k", {})
    if not isinstance(recall, dict):
        recall = {}
    manifest = {
        "schema_version": "phase19.backbone_manifest.v1",
        "status": "pass",
        "run_name": str(args.run_name),
        "artifacts": {
            "dataset": str(dataset),
            "model": str(model_path),
            "retrieval": str(retrieval_path),
            "phase17_retrieval": str(phase17_path),
            "compare": str(compare_path),
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
            "phase19_vs_phase17_mrr_lift": float(compare.get("mrr_lift", 0.0) or 0.0),
            "phase19_vs_phase17_recall_at_1_lift": float(compare.get("recall_at_1_lift", 0.0) or 0.0),
        },
        "training": {
            "epochs": int(args.epochs),
            "batch_size": int(args.batch_size),
            "learning_rate": float(args.learning_rate),
            "image_size": int(args.image_size),
            "weights_mode": str(args.weights_mode),
            "weights_loaded": bool(model.get("weights_loaded", False)),
            "freeze_backbone_epochs": int(model.get("freeze_backbone_epochs", 0) or 0),
            "max_train_examples": int(args.max_train_examples),
            "max_gallery_examples": int(args.max_gallery_examples),
            "max_query_examples": int(args.max_query_examples),
        },
        "stage_timings": stage_timings,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote: {compare_path}")
    print(f"wrote: {manifest_path}")


if __name__ == "__main__":
    main()
