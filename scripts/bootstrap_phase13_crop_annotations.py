from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import build_phase13_crop_annotation_manifest


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap a Phase 13 crop annotation manifest from a real crop dataset.")
    parser.add_argument("--dataset", type=Path, required=True, help="Phase 13 real crop dataset JSON path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase13_crop_annotations.json"), help="Output annotation manifest path.")
    args = parser.parse_args()

    payload = build_phase13_crop_annotation_manifest(_load_json(args.dataset))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
