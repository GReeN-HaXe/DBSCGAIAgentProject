from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db import SQLiteCardRepository
from src.game.skill_cost_rule_extractor import build_skill_cost_rules_for_cards
from src.game.skill_costs import save_skill_cost_rules_json


def _candidate_card_ids(db_path: Path, *, limit: int | None) -> list[int]:
    conn = sqlite3.connect(str(db_path))
    try:
        sql = (
            "SELECT id FROM cards "
            "WHERE COALESCE(card_skill_unstyled, '') != '' "
            "AND ("
            "LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[activate: main]%' "
            "OR LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[activate main]%' "
            "OR LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[counter:%' "
            ") "
            "ORDER BY id"
        )
        if limit is not None and limit > 0:
            sql += f" LIMIT {int(limit)}"
        rows = conn.execute(sql).fetchall()
    finally:
        conn.close()
    return [int(r[0]) for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build skill cost catalog JSON from card skill text.")
    parser.add_argument("--db-path", type=Path, default=ROOT / "dbdatabase" / "dbs_masters.db")
    parser.add_argument("--output", type=Path, default=ROOT / "dbdatabase" / "skill_cost_catalog.json")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    repo = SQLiteCardRepository(args.db_path)
    card_ids = _candidate_card_ids(args.db_path, limit=(args.limit if args.limit > 0 else None))
    rules = build_skill_cost_rules_for_cards(repo, card_ids)
    save_skill_cost_rules_json(args.output, rules)
    print(f"Candidates scanned: {len(card_ids)}")
    print(f"Cards with extracted skill costs: {len(rules)}")
    print(f"Wrote catalog: {args.output}")


if __name__ == "__main__":
    main()
