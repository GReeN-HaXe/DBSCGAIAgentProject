from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import analyze_phase14_errors


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize confusion pairs and hardest misses from a Phase 14 evaluation artifact.")
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--top-confusions-limit", type=int, default=20)
    parser.add_argument("--hardest-rows-limit", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase14_error_analysis.json"))
    args = parser.parse_args()

    payload = analyze_phase14_errors(
        _load_json(args.evaluation),
        top_confusions_limit=int(args.top_confusions_limit),
        hardest_rows_limit=int(args.hardest_rows_limit),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
