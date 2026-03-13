from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.game.effect_family_shortlist import build_effect_family_shortlist


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a ranked effect-family implementation shortlist from an audit artifact.")
    parser.add_argument("--input", type=Path, default=Path("artifacts/effect_support_audit.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/effect_family_shortlist.json"))
    parser.add_argument("--top-n", type=int, default=20)
    args = parser.parse_args()

    audit = json.loads(args.input.read_text(encoding="utf-8"))
    payload = build_effect_family_shortlist(audit, top_n=int(args.top_n))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
