from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import MockFrameRecognizer


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the mock Phase 10 frame recognizer on a frame manifest.")
    parser.add_argument("--frame-manifest", type=Path, required=True, help="Phase 9 frame manifest JSON path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase10_mock_detections.json"), help="Detection manifest output path.")
    args = parser.parse_args()

    recognizer = MockFrameRecognizer()
    payload = recognizer.detect(_load_json(args.frame_manifest))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
