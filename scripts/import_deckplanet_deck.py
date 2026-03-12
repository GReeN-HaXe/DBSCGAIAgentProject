from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.deck_setup import import_deckplanet_deck_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a DeckPlanet deck text export into local DB card ids.")
    parser.add_argument("--input", type=Path, required=True, help="DeckPlanet deck text export path.")
    parser.add_argument("--db-path", type=Path, default=Path("dbdatabase/dbs_masters.db"), help="Path to local SQLite card DB.")
    parser.add_argument("--output-json", type=Path, required=True, help="Output JSON summary path.")
    parser.add_argument("--output-deck-file", type=Path, default=None, help="Optional output file containing main-deck card ids.")
    parser.add_argument("--output-leader-file", type=Path, default=None, help="Optional output file containing the resolved leader id.")
    parser.add_argument("--output-z-deck-file", type=Path, default=None, help="Optional output file containing Z-deck card ids.")
    args = parser.parse_args()

    payload = import_deckplanet_deck_text(
        db_path=args.db_path,
        raw=args.input.read_text(encoding="utf-8"),
    )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output_json}")

    if args.output_deck_file is not None:
        args.output_deck_file.parent.mkdir(parents=True, exist_ok=True)
        args.output_deck_file.write_text(
            "\n".join(str(card_id) for card_id in payload["deck_ids"]) + "\n",
            encoding="utf-8",
        )
        print(f"wrote: {args.output_deck_file}")
    if args.output_leader_file is not None:
        args.output_leader_file.parent.mkdir(parents=True, exist_ok=True)
        args.output_leader_file.write_text(f"{payload['leader_id']}\n", encoding="utf-8")
        print(f"wrote: {args.output_leader_file}")
    if args.output_z_deck_file is not None:
        args.output_z_deck_file.parent.mkdir(parents=True, exist_ok=True)
        args.output_z_deck_file.write_text(
            "\n".join(str(card_id) for card_id in payload["z_deck_ids"]) + ("\n" if payload["z_deck_ids"] else ""),
            encoding="utf-8",
        )
        print(f"wrote: {args.output_z_deck_file}")


if __name__ == "__main__":
    main()
