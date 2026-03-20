from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.game.effect_family_mapping import build_effect_family_mapping_report_from_paths
from src.game.effect_rules import load_effect_rules_json


def _expand_globs(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        if Path(pattern).is_absolute():
            paths.extend(sorted(Path(p) for p in glob.glob(pattern)))
            continue
        paths.extend(sorted(ROOT.glob(pattern)))
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Map active deck/trace cards to effect families from the effect catalog.")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=ROOT / "dbdatabase" / "effect_catalog.json",
        help="Path to effect catalog JSON.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=ROOT / "dbdatabase" / "dbs_masters.db",
        help="Path to local SQLite card DB.",
    )
    parser.add_argument(
        "--deckplanet-glob",
        action="append",
        default=[],
        help="Glob for DeckPlanet deck exports. Can be passed multiple times.",
    )
    parser.add_argument(
        "--trace-glob",
        action="append",
        default=[],
        help="Glob for raw trace JSON files. Can be passed multiple times.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "effect_family_mapping_report.json",
        help="Path to output mapping report JSON.",
    )
    args = parser.parse_args()

    if not args.catalog.exists():
        raise FileNotFoundError(f"Effect catalog not found: {args.catalog}")
    if not args.db_path.exists():
        raise FileNotFoundError(f"Card DB not found: {args.db_path}")

    rules = load_effect_rules_json(args.catalog)
    deck_globs = list(args.deckplanet_glob) or ["artifacts/deckplanet_decks/*.txt"]
    trace_globs = list(args.trace_glob) or ["artifacts/phase22_source/*.json"]
    payload = build_effect_family_mapping_report_from_paths(
        db_path=args.db_path,
        rules=rules,
        deck_paths=_expand_globs(deck_globs),
        trace_paths=_expand_globs(trace_globs),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Priority cards: {payload['summary']['priority_card_count']}")
    print(f"Mapped priority cards: {payload['summary']['mapped_priority_card_count']}")
    print(f"Unmapped priority cards: {payload['summary']['unmapped_priority_card_count']}")
    print(f"Wrote report: {args.output}")


if __name__ == "__main__":
    main()
