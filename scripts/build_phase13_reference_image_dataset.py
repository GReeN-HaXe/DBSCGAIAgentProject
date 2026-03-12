from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import build_phase13_reference_image_dataset


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Phase 13 reference-image dataset from the canonical card-image manifest.")
    parser.add_argument("--reference-manifest", type=Path, default=Path("artifacts/card_image_reference_manifest_post_patch.json"), help="Reference manifest JSON path.")
    parser.add_argument("--validation-ratio", type=float, default=0.2, help="Validation split ratio.")
    parser.add_argument("--split-mode", choices=["paired_views", "disjoint_card"], default="paired_views", help="How to split the reference dataset.")
    parser.add_argument("--train-views", nargs="*", default=["original", "flip_h", "brighten"], help="Reference-view transforms to include in the train split.")
    parser.add_argument("--validation-views", nargs="*", default=["darken"], help="Reference-view transforms to include in the validation split.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase13_reference_image_dataset.json"), help="Reference dataset output path.")
    args = parser.parse_args()

    payload = build_phase13_reference_image_dataset(
        _load_json(args.reference_manifest),
        validation_ratio=float(args.validation_ratio),
        split_mode=str(args.split_mode),
        train_views=[str(view) for view in args.train_views],
        validation_views=[str(view) for view in args.validation_views],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")
    print(f"card_count={payload.get('card_count', 0)}")
    print(f"example_count={payload.get('example_count', 0)}")


if __name__ == "__main__":
    main()
