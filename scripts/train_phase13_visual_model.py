from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import train_phase13_visual_model


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Phase 13 visual k-NN model from a real crop dataset.")
    parser.add_argument("--dataset", type=Path, required=True, help="Phase 13 real/reviewed crop dataset JSON path.")
    parser.add_argument("--split", choices=["train", "validation", "all"], default="train", help="Training split.")
    parser.add_argument("--k-neighbors", type=int, default=3, help="k for k-NN prediction.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase13_visual_model.json"), help="Output model path.")
    args = parser.parse_args()

    payload = train_phase13_visual_model(_load_json(args.dataset), split=str(args.split), k_neighbors=int(args.k_neighbors))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
