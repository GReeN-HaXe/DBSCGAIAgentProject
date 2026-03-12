from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import build_phase15_production_summary


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote an existing Phase 15 run into canonical production artifacts.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, default=None)
    parser.add_argument("--feature-cache-path", type=str, default="")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/phase15_production"))
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_json(args.manifest.resolve())
    retrieval = _load_json(args.retrieval.resolve())
    model = _load_json(args.model.resolve())
    comparison = _load_json(args.comparison.resolve()) if args.comparison else {}
    summary = build_phase15_production_summary(
        phase15_manifest=manifest,
        phase15_retrieval=retrieval,
        phase15_model=model,
        comparison_payload=comparison,
        feature_cache_path=str(args.feature_cache_path or ""),
    )

    summary_path = output_dir / "phase15_production_summary.json"
    manifest_copy = output_dir / "phase15_triplet_manifest.json"
    retrieval_copy = output_dir / "phase15_triplet_retrieval.json"
    model_copy = output_dir / "phase15_triplet_model.json"
    comparison_copy = output_dir / "phase15_vs_phase14_compare.json"
    config_path = output_dir / "phase15_best_config.json"

    shutil.copy2(args.manifest.resolve(), manifest_copy)
    shutil.copy2(args.retrieval.resolve(), retrieval_copy)
    shutil.copy2(args.model.resolve(), model_copy)
    if args.comparison:
        shutil.copy2(args.comparison.resolve(), comparison_copy)

    training = manifest.get("training", {})
    if not isinstance(training, dict):
        training = {}
    if not training:
        training = model
    config = {
        "model_family": "phase15_triplet_mlp",
        "epochs": int(training.get("epochs", 0) or 0),
        "steps_per_epoch": int(training.get("steps_per_epoch", 0) or 0),
        "batch_size": int(training.get("batch_size", 0) or 0),
        "hidden_dim": int(training.get("hidden_dim", 0) or 0),
        "embedding_dim": int(training.get("embedding_dim", 0) or 0),
        "learning_rate": float(training.get("learning_rate", 0.0) or 0.0),
        "margin": float(training.get("margin", 0.0) or 0.0),
        "negative_mining": str(training.get("negative_mining", "")),
        "negative_pool_size": int(training.get("negative_pool_size", 0) or 0),
    }

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"wrote: {summary_path}")
    print(f"wrote: {config_path}")


if __name__ == "__main__":
    main()
