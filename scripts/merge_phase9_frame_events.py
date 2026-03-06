from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import merge_frame_events_into_external_match


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge frame-derived events into a Phase 9 external match artifact.")
    parser.add_argument("--match", type=Path, required=True, help="Phase 9 external match JSON path.")
    parser.add_argument("--frame-events", type=Path, required=True, help="Frame-event JSON path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase9_external_match_merged.json"), help="Merged output JSON path.")
    args = parser.parse_args()

    frame_payload = _load_json(args.frame_events)
    if "manifest_path" not in frame_payload:
        frame_payload["manifest_path"] = str(args.frame_events)
    merged = merge_frame_events_into_external_match(_load_json(args.match), frame_payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
