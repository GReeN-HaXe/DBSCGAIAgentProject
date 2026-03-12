from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import normalize_external_match


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a manually annotated external match into the Phase 9 schema.")
    parser.add_argument("--input", type=Path, required=True, help="Annotated external match JSON path.")
    parser.add_argument("--match-id", type=str, required=True, help="Stable match id for the imported artifact.")
    parser.add_argument("--source-name", type=str, default="external_manual", help="Human-readable source name.")
    parser.add_argument("--source-type", type=str, default="manual_annotation", help="Source type label.")
    parser.add_argument("--video-path", type=str, default=None, help="Optional linked video path.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase9_external_match.json"), help="Output JSON path.")
    args = parser.parse_args()

    payload = normalize_external_match(
        _load_json(args.input),
        match_id=str(args.match_id),
        source_name=str(args.source_name),
        source_type=str(args.source_type),
        video_path=args.video_path,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
