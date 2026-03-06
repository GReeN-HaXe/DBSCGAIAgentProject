from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import apply_phase13_crop_annotation_review


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply reviewed crop annotations back onto a Phase 13 crop dataset.")
    parser.add_argument("--dataset", type=Path, required=True, help="Phase 13 real crop dataset JSON path.")
    parser.add_argument("--annotations", type=Path, required=True, help="Phase 13 crop annotation manifest JSON path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase13_reviewed_crop_dataset.json"), help="Reviewed crop dataset output path.")
    args = parser.parse_args()

    payload = apply_phase13_crop_annotation_review(_load_json(args.dataset), _load_json(args.annotations))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
