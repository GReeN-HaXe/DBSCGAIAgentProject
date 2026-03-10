from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import build_phase13_feature_cache


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a cached Phase 13 feature dataset from crop/reference images.")
    parser.add_argument("--dataset", type=Path, required=True, help="Phase 13 dataset JSON path.")
    parser.add_argument("--max-examples", type=int, default=0, help="Maximum number of examples to process. Use 0 for all.")
    parser.add_argument("--progress-every", type=int, default=50, help="Print progress every N examples. Use 0 to disable.")
    parser.add_argument("--checkpoint-every", type=int, default=250, help="Write partial progress every N examples. Use 0 to write only once at the end.")
    parser.add_argument("--resume-if-exists", action="store_true", help="Resume from the output file if it already exists.")
    parser.add_argument("--patch-grid-size", type=int, default=2, help="Patch-grid size for visual features.")
    parser.add_argument("--hist-bins", type=int, default=4, help="Histogram bin count for visual features.")
    parser.add_argument("--gray-hist-bins", type=int, default=8, help="Grayscale histogram bin count.")
    parser.add_argument("--edge-grid-size", type=int, default=2, help="Edge-grid size for gradient features.")
    parser.add_argument("--disable-rgb-patch", action="store_true", help="Disable RGB patch-grid features.")
    parser.add_argument("--disable-rgb-hist", action="store_true", help="Disable RGB histogram features.")
    parser.add_argument("--disable-gray-hist", action="store_true", help="Disable grayscale histogram features.")
    parser.add_argument("--disable-edge-grid", action="store_true", help="Disable edge-grid features.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase13_feature_cache.json"), help="Feature-cache output path.")
    args = parser.parse_args()

    dataset = _load_json(args.dataset)
    examples = dataset.get("examples", [])
    if not isinstance(examples, list):
        examples = []
    target_examples = list(examples[: int(args.max_examples)]) if int(args.max_examples) > 0 else list(examples)
    config = {
        "patch_grid_size": int(args.patch_grid_size),
        "hist_bins": int(args.hist_bins),
        "gray_hist_bins": int(args.gray_hist_bins),
        "edge_grid_size": int(args.edge_grid_size),
        "enable_rgb_patch": 0 if bool(args.disable_rgb_patch) else 1,
        "enable_rgb_hist": 0 if bool(args.disable_rgb_hist) else 1,
        "enable_gray_hist": 0 if bool(args.disable_gray_hist) else 1,
        "enable_edge_grid": 0 if bool(args.disable_edge_grid) else 1,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    existing_examples: list[dict[str, object]] = []
    if bool(args.resume_if_exists) and args.output.exists():
        existing = _load_json(args.output)
        loaded_examples = existing.get("examples", [])
        if isinstance(loaded_examples, list):
            existing_examples = [row for row in loaded_examples if isinstance(row, dict)]
        print(f"resuming_from={len(existing_examples)}")

    checkpoint_every = max(0, int(args.checkpoint_every))
    if checkpoint_every == 0:
        payload = build_phase13_feature_cache(
            {**dataset, "examples": target_examples},
            max_examples=0,
            progress_every=int(args.progress_every),
            feature_config=config,
        )
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote: {args.output}")
        return

    processed = len(existing_examples)
    while processed < len(target_examples):
        chunk_end = min(len(target_examples), processed + checkpoint_every)
        chunk_payload = build_phase13_feature_cache(
            {**dataset, "examples": target_examples[processed:chunk_end]},
            max_examples=0,
            progress_every=int(args.progress_every),
            feature_config=config,
        )
        chunk_examples = chunk_payload.get("examples", [])
        if not isinstance(chunk_examples, list):
            chunk_examples = []
        existing_examples.extend(row for row in chunk_examples if isinstance(row, dict))
        payload = {
            **dataset,
            "schema_version": str(chunk_payload.get("schema_version", "phase13.feature_cache.v1")),
            "target_type": chunk_payload.get("target_type", dataset.get("target_type", "")),
            "feature_config": chunk_payload.get("feature_config", config),
            "card_count": int(dataset.get("card_count", len(existing_examples)) or len(existing_examples)),
            "example_count": len(existing_examples),
            "examples": existing_examples,
        }
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        processed = len(existing_examples)
        print(f"checkpointed={processed}")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
