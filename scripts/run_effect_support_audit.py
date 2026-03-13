from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.deck_setup import import_deckplanet_deck_text
from src.db import SQLiteCardRepository
from src.game.effect_support_audit import build_effect_support_audit


_JSON_CARD_ID_RE = re.compile(r'"(?:card_id|hand_card_id|source_card_id|attacker_card_id|target_card_id)"\s*:\s*(\d+)')
_TEXT_CARD_ID_RE = re.compile(r"\bcard_id=(\d+)\b")


def _candidate_skill_card_ids(db_path: Path, *, limit: int | None = None) -> list[int]:
    conn = sqlite3.connect(str(db_path))
    try:
        sql = "SELECT id FROM cards WHERE COALESCE(card_skill_unstyled, '') != '' ORDER BY id"
        if limit is not None and limit > 0:
            sql += f" LIMIT {int(limit)}"
        rows = conn.execute(sql).fetchall()
    finally:
        conn.close()
    return [int(row[0]) for row in rows]


def _collect_paths(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        for match in sorted(glob.glob(pattern)):
            path = Path(match)
            if path.is_file():
                paths.append(path)
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(path)
    return ordered


def _card_ids_from_deckplanet_files(paths: list[Path], *, db_path: Path) -> tuple[set[int], dict[str, object]]:
    ids: set[int] = set()
    unresolved: dict[str, list[str]] = {}
    for path in paths:
        payload = import_deckplanet_deck_text(db_path=db_path, raw=path.read_text(encoding="utf-8"))
        ids.add(int(payload["leader_id"]))
        ids.update(int(card_id) for card_id in payload["deck_ids"])
        ids.update(int(card_id) for card_id in payload["z_deck_ids"])
        if payload["unresolved_card_numbers"]:
            unresolved[str(path)] = list(payload["unresolved_card_numbers"])
    return ids, {
        "deck_file_count": len(paths),
        "unique_card_id_count": len(ids),
        "unresolved_by_file": unresolved,
    }


def _card_ids_from_trace_files(paths: list[Path]) -> tuple[set[int], dict[str, object]]:
    ids: set[int] = set()
    for path in paths:
        text = path.read_text(encoding="utf-8")
        ids.update(int(value) for value in _JSON_CARD_ID_RE.findall(text))
        ids.update(int(value) for value in _TEXT_CARD_ID_RE.findall(text))
    return ids, {
        "trace_file_count": len(paths),
        "unique_card_id_count": len(ids),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit effect support by reusable skill-text family and real project usage.")
    parser.add_argument("--db-path", type=Path, default=ROOT / "dbdatabase" / "dbs_masters.db", help="Path to SQLite card DB.")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "effect_support_audit.json", help="Output audit JSON path.")
    parser.add_argument("--top-families", type=int, default=30, help="Number of top global/priority families to include.")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit on DB skill cards scanned (0 = all).")
    parser.add_argument("--deckplanet-glob", action="append", default=[], help="Glob for DeckPlanet deck text files. Can be passed multiple times.")
    parser.add_argument("--trace-glob", action="append", default=[], help="Glob for recent trace JSON files. Can be passed multiple times.")
    args = parser.parse_args()

    repo = SQLiteCardRepository(args.db_path)
    card_ids = _candidate_skill_card_ids(args.db_path, limit=(args.limit if args.limit > 0 else None))
    deck_paths = _collect_paths(list(args.deckplanet_glob))
    trace_paths = _collect_paths(list(args.trace_glob))
    deck_card_ids, deck_summary = _card_ids_from_deckplanet_files(deck_paths, db_path=args.db_path)
    trace_card_ids, trace_summary = _card_ids_from_trace_files(trace_paths)

    payload = build_effect_support_audit(
        repo,
        card_ids,
        priority_card_ids=sorted(deck_card_ids | trace_card_ids),
        top_families=int(args.top_families),
    )
    payload["inputs"] = {
        "db_path": str(args.db_path),
        "deckplanet_globs": list(args.deckplanet_glob),
        "trace_globs": list(args.trace_glob),
        "scan_limit": int(args.limit),
    }
    payload["priority_sources"] = {
        "deckplanet": {
            **deck_summary,
            "files": [str(path) for path in deck_paths],
        },
        "traces": {
            **trace_summary,
            "files": [str(path) for path in trace_paths],
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
