from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import render_synthetic_phase12_frames


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Render synthetic PPM frames from labeled detections for Phase 12.")
    parser.add_argument("--frame-manifest", type=Path, required=True, help="Frame manifest JSON path.")
    parser.add_argument("--labeled", type=Path, required=True, help="Labeled detection manifest JSON path.")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/phase12_frames"), help="Output frame directory.")
    parser.add_argument("--image-format", choices=["ppm", "png", "jpg", "webp"], default="ppm", help="Rendered frame image format.")
    parser.add_argument("--manifest-output", type=Path, default=None, help="Optional rendered frame-manifest output path.")
    args = parser.parse_args()

    payload = render_synthetic_phase12_frames(
        frame_manifest=_load_json(args.frame_manifest),
        labeled_manifest=_load_json(args.labeled),
        output_dir=args.output_dir,
        image_format=str(args.image_format),
    )
    out = args.manifest_output or (args.output_dir / "phase12_rendered_frame_manifest.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()
