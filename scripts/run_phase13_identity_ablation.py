from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


ABLATION_CONFIGS = [
    {
        "name": "rgb_grid2_hist4",
        "patch_grid_size": 2,
        "hist_bins": 4,
        "gray_hist_bins": 8,
        "edge_grid_size": 2,
        "enable_rgb_patch": 1,
        "enable_rgb_hist": 1,
        "enable_gray_hist": 0,
        "enable_edge_grid": 0,
    },
    {
        "name": "rgb_gray_grid2_hist4",
        "patch_grid_size": 2,
        "hist_bins": 4,
        "gray_hist_bins": 8,
        "edge_grid_size": 2,
        "enable_rgb_patch": 1,
        "enable_rgb_hist": 1,
        "enable_gray_hist": 1,
        "enable_edge_grid": 0,
    },
    {
        "name": "rgb_gray_edge_grid2",
        "patch_grid_size": 2,
        "hist_bins": 4,
        "gray_hist_bins": 8,
        "edge_grid_size": 2,
        "enable_rgb_patch": 1,
        "enable_rgb_hist": 1,
        "enable_gray_hist": 1,
        "enable_edge_grid": 1,
    },
    {
        "name": "rgb_gray_edge_grid3",
        "patch_grid_size": 3,
        "hist_bins": 8,
        "gray_hist_bins": 16,
        "edge_grid_size": 3,
        "enable_rgb_patch": 1,
        "enable_rgb_hist": 1,
        "enable_gray_hist": 1,
        "enable_edge_grid": 1,
    },
    {
        "name": "gray_edge_only",
        "patch_grid_size": 2,
        "hist_bins": 4,
        "gray_hist_bins": 16,
        "edge_grid_size": 3,
        "enable_rgb_patch": 0,
        "enable_rgb_hist": 0,
        "enable_gray_hist": 1,
        "enable_edge_grid": 1,
    },
]


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 13 card-identity feature ablations and rank the results.")
    parser.add_argument("--dataset", type=Path, default=Path("artifacts/phase13_reference_image_dataset.json"), help="Phase 13 reference dataset JSON path.")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/phase13_identity_ablation"), help="Ablation artifact directory.")
    parser.add_argument("--max-examples", type=int, default=256, help="Maximum number of examples to process. Use 0 for all.")
    parser.add_argument("--progress-every", type=int, default=25, help="Print progress every N examples. Use 0 to disable.")
    parser.add_argument("--eval-split", choices=["train", "validation", "all"], default="validation", help="Evaluation split.")
    args = parser.parse_args()

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    for config in ABLATION_CONFIGS:
        run_dir = args.artifacts_dir / str(config["name"])
        run_dir.mkdir(parents=True, exist_ok=True)
        cache_path = run_dir / "feature_cache.json"
        model_path = run_dir / "model.json"
        eval_path = run_dir / "eval.json"
        _run(
            [
                sys.executable,
                "scripts/build_phase13_feature_cache.py",
                "--dataset",
                str(args.dataset),
                "--max-examples",
                str(int(args.max_examples)),
                "--progress-every",
                str(int(args.progress_every)),
                "--patch-grid-size",
                str(int(config["patch_grid_size"])),
                "--hist-bins",
                str(int(config["hist_bins"])),
                "--gray-hist-bins",
                str(int(config["gray_hist_bins"])),
                "--edge-grid-size",
                str(int(config["edge_grid_size"])),
                *(["--disable-rgb-patch"] if int(config["enable_rgb_patch"]) == 0 else []),
                *(["--disable-rgb-hist"] if int(config["enable_rgb_hist"]) == 0 else []),
                *(["--disable-gray-hist"] if int(config["enable_gray_hist"]) == 0 else []),
                *(["--disable-edge-grid"] if int(config["enable_edge_grid"]) == 0 else []),
                "--output",
                str(cache_path),
            ]
        )
        _run(
            [
                sys.executable,
                "scripts/train_phase13_visual_model.py",
                "--dataset",
                str(cache_path),
                "--split",
                "train",
                "--k-neighbors",
                "1",
                "--max-examples",
                str(int(args.max_examples)),
                "--progress-every",
                "0",
                "--patch-grid-size",
                str(int(config["patch_grid_size"])),
                "--hist-bins",
                str(int(config["hist_bins"])),
                "--gray-hist-bins",
                str(int(config["gray_hist_bins"])),
                "--edge-grid-size",
                str(int(config["edge_grid_size"])),
                *(["--disable-rgb-patch"] if int(config["enable_rgb_patch"]) == 0 else []),
                *(["--disable-rgb-hist"] if int(config["enable_rgb_hist"]) == 0 else []),
                *(["--disable-gray-hist"] if int(config["enable_gray_hist"]) == 0 else []),
                *(["--disable-edge-grid"] if int(config["enable_edge_grid"]) == 0 else []),
                "--output",
                str(model_path),
            ]
        )
        _run(
            [
                sys.executable,
                "scripts/evaluate_phase13_identity_model.py",
                "--model",
                str(model_path),
                "--dataset",
                str(cache_path),
                "--split",
                str(args.eval_split),
                "--progress-every",
                str(int(args.progress_every)),
                "--output",
                str(eval_path),
            ]
        )
        eval_payload = _load_json(eval_path)
        results.append(
            {
                "config_name": str(config["name"]),
                "patch_grid_size": int(config["patch_grid_size"]),
                "hist_bins": int(config["hist_bins"]),
                "gray_hist_bins": int(config["gray_hist_bins"]),
                "edge_grid_size": int(config["edge_grid_size"]),
                "top1_accuracy": float(eval_payload.get("top1_accuracy", 0.0) or 0.0),
                "top5_accuracy": float((eval_payload.get("top_k_accuracy", {}) or {}).get("5", 0.0) or 0.0),
                "top10_accuracy": float((eval_payload.get("top_k_accuracy", {}) or {}).get("10", 0.0) or 0.0),
                "evaluation_path": str(eval_path),
            }
        )
    ranking = sorted(results, key=lambda row: (-float(row["top1_accuracy"]), -float(row["top5_accuracy"]), str(row["config_name"])))
    summary = {
        "schema_version": "phase13.identity_ablation.v1",
        "dataset": str(args.dataset),
        "max_examples": int(args.max_examples),
        "eval_split": str(args.eval_split),
        "runs": results,
        "ranking": ranking,
        "best": ranking[0] if ranking else None,
    }
    summary_path = args.artifacts_dir / "phase13_identity_ablation_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote: {summary_path}")


if __name__ == "__main__":
    main()
