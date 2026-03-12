from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import build_phase12_crop_dataset


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Phase 12 visual crop dataset from frames and labeled detections.")
    parser.add_argument("--frame-manifest", type=Path, required=True, help="Rendered frame manifest JSON path.")
    parser.add_argument("--labeled", type=Path, required=True, help="Labeled detection manifest JSON path.")
    parser.add_argument("--validation-ratio", type=float, default=0.2, help="Validation split ratio.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase12_crop_dataset.json"), help="Output dataset path.")
    args = parser.parse_args()

    payload = build_phase12_crop_dataset(
        frame_manifest=_load_json(args.frame_manifest),
        labeled_manifest=_load_json(args.labeled),
        validation_ratio=float(args.validation_ratio),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
