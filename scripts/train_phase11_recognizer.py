from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import train_phase11_recognizer_model


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Phase 11 recognizer from labeled detection manifests.")
    parser.add_argument("--input", type=Path, nargs="+", required=True, help="One or more labeled Phase 10 detection manifests.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase11_recognizer_model.json"), help="Trained recognizer model output path.")
    args = parser.parse_args()

    model = train_phase11_recognizer_model([_load_json(path) for path in args.input])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
