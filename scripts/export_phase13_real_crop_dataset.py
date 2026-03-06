from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import export_phase13_real_crop_dataset


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a real crop-image dataset from frame images and labeled boxes.")
    parser.add_argument("--frame-manifest", type=Path, required=True, help="Frame manifest JSON path.")
    parser.add_argument("--labeled", type=Path, required=True, help="Labeled detection manifest JSON path.")
    parser.add_argument("--crops-output-dir", type=Path, default=Path("artifacts/phase13_real_crops"), help="Directory where crop images will be written.")
    parser.add_argument("--crop-image-format", choices=["ppm", "png", "jpg"], default="ppm", help="Crop image format.")
    parser.add_argument("--validation-ratio", type=float, default=0.2, help="Validation split ratio.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase13_real_crop_dataset.json"), help="Dataset manifest output path.")
    args = parser.parse_args()

    payload = export_phase13_real_crop_dataset(
        frame_manifest=_load_json(args.frame_manifest),
        labeled_manifest=_load_json(args.labeled),
        crops_output_dir=args.crops_output_dir,
        crop_image_format=str(args.crop_image_format),
        validation_ratio=float(args.validation_ratio),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
