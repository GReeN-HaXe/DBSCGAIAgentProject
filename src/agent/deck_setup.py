from __future__ import annotations

import sqlite3
from pathlib import Path


def parse_card_id_text(raw: str) -> list[int]:
    cleaned = raw.replace(",", " ").replace(";", " ").replace("\t", " ")
    ids: list[int] = []
    for part in cleaned.split():
        part = part.strip()
        if not part or part.startswith("#"):
            continue
        ids.append(int(part))
    return ids


def read_card_ids_file(path: Path) -> list[int]:
    text = path.read_text(encoding="utf-8")
    return parse_card_id_text(text)


def _fetch_card_types(db_path: Path, card_ids: list[int]) -> dict[int, str]:
    if not card_ids:
        return {}
    placeholders = ", ".join("?" for _ in card_ids)
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            f"SELECT id, card_type FROM cards WHERE id IN ({placeholders})",
            [int(x) for x in card_ids],
        ).fetchall()
    finally:
        conn.close()
    return {int(r[0]): str(r[1] or "").upper() for r in rows}


def validate_leader_and_deck(*, db_path: Path, leader_id: int, deck_ids: list[int], expected_deck_size: int = 60) -> None:
    if expected_deck_size > 0 and len(deck_ids) != expected_deck_size:
        raise ValueError(f"Deck must contain exactly {expected_deck_size} cards; got {len(deck_ids)}.")
    ids = [int(leader_id), *[int(x) for x in deck_ids]]
    type_map = _fetch_card_types(db_path, ids)
    if int(leader_id) not in type_map:
        raise ValueError(f"Leader id not found in DB: {leader_id}")
    if type_map[int(leader_id)] != "LEADER":
        raise ValueError(f"Leader id {leader_id} is not a LEADER (found {type_map[int(leader_id)]}).")
    missing = [cid for cid in deck_ids if int(cid) not in type_map]
    if missing:
        raise ValueError(f"Deck contains unknown card ids: {missing[:10]}")
    bad = [cid for cid in deck_ids if type_map[int(cid)] == "LEADER"]
    if bad:
        raise ValueError(f"Deck cannot contain LEADER cards: {bad[:10]}")


def load_sample_game_setup_from_db(db_path: Path, *, deck_size: int = 60) -> tuple[int, list[int], int, list[int]]:
    conn = sqlite3.connect(str(db_path))
    try:
        leaders = conn.execute(
            "SELECT id FROM cards WHERE UPPER(card_type)='LEADER' ORDER BY id LIMIT 2"
        ).fetchall()
        deck_rows = conn.execute(
            "SELECT id FROM cards WHERE UPPER(card_type)!='LEADER' ORDER BY id LIMIT ?",
            (deck_size * 2,),
        ).fetchall()
    finally:
        conn.close()
    if len(leaders) < 2:
        raise ValueError("DB does not contain at least 2 LEADER cards.")
    if len(deck_rows) < deck_size * 2:
        raise ValueError(f"DB does not contain enough non-leader cards for two {deck_size}-card decks.")
    p1_leader = int(leaders[0][0])
    p2_leader = int(leaders[1][0])
    deck_ids = [int(r[0]) for r in deck_rows]
    return p1_leader, deck_ids[:deck_size], p2_leader, deck_ids[deck_size : deck_size * 2]
