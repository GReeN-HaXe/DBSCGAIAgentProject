from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db import SQLiteCardRepository
from src.game.effect_rule_extractor import (
    build_effect_rules_with_diagnostics_and_report,
)
from src.game.effect_rules import save_effect_rules_json


def _candidate_card_ids(db_path: Path, *, limit: int | None) -> list[int]:
    conn = sqlite3.connect(str(db_path))
    try:
        sql = (
            "SELECT id FROM cards "
            "WHERE COALESCE(card_skill_unstyled, '') != '' "
            "AND ("
            "COALESCE(has_auto, 0) = 1 "
            "OR COALESCE(has_draw, 0) = 1 "
            "OR LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[auto]%' "
            "OR LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[activate: main]%' "
            "OR LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[activate main]%' "
            "OR LOWER(COALESCE(card_skill_unstyled, '')) LIKE '%[activate: battle]%' "
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
    parser = argparse.ArgumentParser(description="Build effect catalog JSON from card skill text.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=ROOT / "dbdatabase" / "dbs_masters.db",
        help="Path to source card SQLite database.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dbdatabase" / "effect_catalog.json",
        help="Path to output effect catalog JSON.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional max candidate cards (0 means all).")
    parser.add_argument(
        "--strict-report",
        type=str,
        default=str(ROOT / "dbdatabase" / "effect_catalog_strict_report.json"),
        help="Path to optional diagnostics report JSON (set to empty string to skip).",
    )
    parser.add_argument(
        "--top-unmatched",
        type=int,
        default=20,
        help="Number of top unmatched skill templates to include in report.",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        raise FileNotFoundError(f"Database not found: {args.db_path}")

    repo = SQLiteCardRepository(args.db_path)
    card_ids = _candidate_card_ids(args.db_path, limit=(args.limit if args.limit > 0 else None))
    rules, diagnostics, report = build_effect_rules_with_diagnostics_and_report(
        repo,
        card_ids,
        top_unmatched=args.top_unmatched,
    )
    save_effect_rules_json(args.output, rules)

    strict_report_raw = str(args.strict_report).strip()
    strict_report_path = Path(strict_report_raw) if strict_report_raw else None
    if strict_report_path is not None:
        strict_report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(report)
        payload["diagnostics"] = {str(k): v for k, v in sorted(diagnostics.items())}
        strict_report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    total_rules = sum(len(v) for v in rules.values())
    print(f"Candidates scanned: {len(card_ids)}")
    print(f"Cards with extracted rules: {len(rules)}")
    print(f"Total extracted rules: {total_rules}")
    print(f"Wrote catalog: {args.output}")
    if strict_report_path is not None:
        print(f"Wrote strict report: {strict_report_path}")


if __name__ == "__main__":
    main()
