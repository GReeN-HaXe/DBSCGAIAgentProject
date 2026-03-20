from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.game.effect_catalog_report import build_effect_family_report
from src.game.effect_rules import default_effect_catalog_path, load_effect_rules_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a family-level report from the effect catalog.")
    parser.add_argument(
        "--input",
        type=Path,
        default=default_effect_catalog_path(ROOT),
        help="Path to effect catalog merged JSON, shard manifest JSON, or shard directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "effect_family_report.json",
        help="Path to output family report JSON.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Effect catalog not found: {args.input}")

    rules = load_effect_rules_json(args.input)
    report = build_effect_family_report(rules)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Families: {report['summary']['family_count']}")
    print(f"Card rules: {report['summary']['card_rule_count']}")
    print(f"Effect rules: {report['summary']['effect_rule_count']}")
    print(f"Wrote report: {args.output}")


if __name__ == "__main__":
    main()
