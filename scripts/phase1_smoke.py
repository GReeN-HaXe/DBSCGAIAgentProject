from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db import CardQuery, SQLiteCardRepository


def main() -> None:
    db_path = Path("dbdatabase/dbs_masters.db")
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    repo = SQLiteCardRepository(db_path)

    first = repo.search(CardQuery(limit=1))
    if not first:
        print("No cards found.")
        return

    card = first[0]
    print("Loaded card:")
    print(f"  id={card.id} number={card.card_number} name={card.card_name}")
    print(f"  type={card.card_type} color={card.card_color} power={card.power_int}")
    print(f"  keywords={list(card.keywords)[:5]}")

    same_number = repo.get_by_number(card.card_number, include_variants=True)
    print(f"Found {len(same_number)} record(s) for card_number={card.card_number}.")


if __name__ == "__main__":
    main()
