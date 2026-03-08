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

    payload = build_phase13_feature_cache(
        _load_json(args.dataset),
        max_examples=int(args.max_examples),
        progress_every=int(args.progress_every),
        feature_config={
            "patch_grid_size": int(args.patch_grid_size),
            "hist_bins": int(args.hist_bins),
            "gray_hist_bins": int(args.gray_hist_bins),
            "edge_grid_size": int(args.edge_grid_size),
            "enable_rgb_patch": 0 if bool(args.disable_rgb_patch) else 1,
            "enable_rgb_hist": 0 if bool(args.disable_rgb_hist) else 1,
            "enable_gray_hist": 0 if bool(args.disable_gray_hist) else 1,
            "enable_edge_grid": 0 if bool(args.disable_edge_grid) else 1,
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
