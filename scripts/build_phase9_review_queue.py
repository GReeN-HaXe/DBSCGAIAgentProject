from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import build_phase9_review_queue


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Phase 9 review queue manifest from multiple external matches.")
    parser.add_argument("--input", type=Path, nargs="+", required=True, help="One or more Phase 9 external match JSON files.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase9_review_queue.json"), help="Output queue manifest path.")
    args = parser.parse_args()

    payload = build_phase9_review_queue([_load_json(path) for path in args.input])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
