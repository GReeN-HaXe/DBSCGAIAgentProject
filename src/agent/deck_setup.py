from __future__ import annotations

import re
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


_DECKPLANET_LINE_RE = re.compile(r"^\s*(?:(\d+)\s*x?\s+)?(.+?)\s*\[([A-Z0-9]+-\d{2,3}[A-Z]?)\]\s*$", re.IGNORECASE)
_SECTION_LEADER = {"leader", "leaders"}
_SECTION_MAIN = {"deck", "main", "main deck", "maindeck"}
_SECTION_SIDE = {"side", "side deck", "sidedeck"}
_SECTION_Z = {"z deck", "z-deck", "zdeck"}


def parse_deckplanet_deck_text(raw: str) -> dict[str, object]:
    section = "main"
    entries: list[dict[str, object]] = []
    ignored_lines: list[str] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower().replace("_", " ").strip().rstrip(":").strip()
        if lowered in _SECTION_LEADER:
            section = "leader"
            continue
        if lowered in _SECTION_MAIN:
            section = "main"
            continue
        if lowered in _SECTION_SIDE:
            section = "side"
            continue
        if lowered in _SECTION_Z:
            section = "z"
            continue
        match = _DECKPLANET_LINE_RE.match(line)
        if match is None:
            ignored_lines.append(line)
            continue
        quantity = int(match.group(1) or 1)
        card_name = str(match.group(2)).strip()
        card_number = match.group(3).upper()
        entries.append(
            {
                "section": section,
                "quantity": quantity,
                "card_number": card_number,
                "card_name": card_name,
                "raw_line": line,
            }
        )
    return {
        "entries": entries,
        "ignored_lines": ignored_lines,
    }


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


def _fetch_card_rows_by_numbers(db_path: Path, card_numbers: list[str]) -> dict[str, tuple[int, str]]:
    if not card_numbers:
        return {}
    placeholders = ", ".join("?" for _ in card_numbers)
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            f"SELECT id, card_type, UPPER(card_number) FROM cards WHERE UPPER(card_number) IN ({placeholders})",
            [str(x).upper() for x in card_numbers],
        ).fetchall()
    finally:
        conn.close()
    return {str(row[2]).upper(): (int(row[0]), str(row[1] or "").upper()) for row in rows}


def import_deckplanet_deck_text(*, db_path: Path, raw: str) -> dict[str, object]:
    parsed = parse_deckplanet_deck_text(raw)
    entries = list(parsed["entries"])
    card_numbers = sorted({str(entry["card_number"]).upper() for entry in entries})
    resolved_rows = _fetch_card_rows_by_numbers(db_path, card_numbers)

    leader_id: int | None = None
    deck_ids: list[int] = []
    z_deck_ids: list[int] = []
    unresolved: list[str] = []
    warnings: list[str] = []

    for entry in entries:
        card_number = str(entry["card_number"]).upper()
        quantity = int(entry["quantity"])
        section = str(entry["section"])
        row = resolved_rows.get(card_number)
        if row is None:
            unresolved.append(card_number)
            continue
        card_id, card_type = row
        if section == "side":
            continue
        if section == "leader" or card_type == "LEADER":
            if leader_id is not None and leader_id != card_id:
                raise ValueError(f"Multiple leader cards found in deck import: {leader_id} and {card_id}")
            leader_id = card_id
            continue
        target = z_deck_ids if section == "z" else deck_ids
        target.extend([card_id] * quantity)

    if leader_id is None:
        raise ValueError("No leader card could be resolved from the imported deck text.")
    if unresolved:
        warnings.append(f"Unresolved card_numbers: {sorted(set(unresolved))[:20]}")
    if z_deck_ids:
        warnings.append("Z-deck entries were resolved, but play_vs_ai.py currently ignores Z-deck imports.")
    return {
        "leader_id": int(leader_id),
        "deck_ids": deck_ids,
        "z_deck_ids": z_deck_ids,
        "unresolved_card_numbers": sorted(set(unresolved)),
        "ignored_lines": list(parsed["ignored_lines"]),
        "warnings": warnings,
    }


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
