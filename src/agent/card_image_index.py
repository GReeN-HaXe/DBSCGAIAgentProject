from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from typing import Iterable


SUPPORTED_CARD_IMAGE_SUFFIXES = {".webp", ".png", ".jpg", ".jpeg", ".ppm"}
_PROMO_SUFFIX_PATTERN = re.compile(r"(?:-?PR\d*|-?P\d+|-?ALT\d*|-?REPRINT\d*)$", re.IGNORECASE)
_RARITY_SUFFIX_PATTERN = re.compile(r"(?:-?GDR|-?SCR|-?SPR|-?SR|-?R|-?C|-?UC)$", re.IGNORECASE)
_CARD_NUMBER_PADDING_PATTERN = re.compile(r"^([A-Z]+\d*)-(\d{1,2})([A-Z]?)$")


@dataclass(frozen=True)
class CardImageMatch:
    table_name: str
    record_id: int
    base_id: int | None
    card_number: str
    card_name: str
    image_path: str
    image_format: str
    match_type: str


def load_card_number_index(db_path: Path) -> dict[str, list[dict[str, object]]]:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        index: dict[str, list[dict[str, object]]] = {}
        for table_name, base_id_column in (("cards", None), ("variants", "base_id")):
            columns = ["id", "card_number", "card_name"]
            if base_id_column is not None:
                columns.append(base_id_column)
            query = f"SELECT {', '.join(columns)} FROM {table_name} WHERE card_number IS NOT NULL AND TRIM(card_number) <> ''"
            for row in cur.execute(query):
                record_id = int(row[0])
                card_number = str(row[1]).strip()
                card_name = str(row[2] or "").strip()
                base_id = int(row[3]) if base_id_column is not None and row[3] is not None else None
                index.setdefault(card_number.upper(), []).append(
                    {
                        "table_name": table_name,
                        "record_id": record_id,
                        "base_id": base_id,
                        "card_number": card_number,
                        "card_name": card_name,
                    }
                )
        return index
    finally:
        conn.close()


def _normalize_stem(stem: str) -> str:
    return re.sub(r"[^A-Z0-9-]", "", stem.upper())


def _normalize_card_number_padding(card_number: str) -> str:
    match = _CARD_NUMBER_PADDING_PATTERN.match(card_number)
    if match is None:
        return card_number
    prefix, sequence, suffix = match.groups()
    return f"{prefix}-{sequence.zfill(3)}{suffix}"


def _extract_candidate_card_number(stem: str, known_numbers: Iterable[str]) -> tuple[str | None, str]:
    normalized = _normalize_stem(stem)
    if normalized in known_numbers:
        return normalized, "exact_stem"
    padded_normalized = _normalize_card_number_padding(normalized)
    if padded_normalized in known_numbers:
        return padded_normalized, "normalized_number_padding"
    promo_normalized = _PROMO_SUFFIX_PATTERN.sub("", normalized)
    promo_normalized = promo_normalized.rstrip("-")
    if promo_normalized in known_numbers:
        return promo_normalized, "normalized_promo_suffix"
    padded_promo_normalized = _normalize_card_number_padding(promo_normalized)
    if padded_promo_normalized in known_numbers:
        return padded_promo_normalized, "normalized_promo_suffix"
    matches = [number for number in known_numbers if number in normalized]
    if not matches:
        return None, "unmatched"
    matches.sort(key=len, reverse=True)
    return matches[0], "substring_stem"


def normalize_card_image_stem_to_base(stem: str) -> str:
    normalized = _normalize_stem(stem)
    stripped = _PROMO_SUFFIX_PATTERN.sub("", normalized).rstrip("-")
    stripped = _RARITY_SUFFIX_PATTERN.sub("", stripped).rstrip("-")
    return _normalize_card_number_padding(stripped)


def index_local_card_images(image_dir: Path, db_path: Path) -> dict[str, object]:
    card_index = load_card_number_index(db_path)
    known_numbers = set(card_index.keys())
    matched: list[dict[str, object]] = []
    unmatched: list[dict[str, str]] = []
    if not image_dir.exists():
        raise ValueError(f"image directory not found: {image_dir}")
    for path in sorted(image_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_CARD_IMAGE_SUFFIXES:
            continue
        card_number, match_type = _extract_candidate_card_number(path.stem, known_numbers)
        if card_number is None:
            unmatched.append(
                {
                    "image_path": str(path),
                    "stem": path.stem,
                }
            )
            continue
        for row in card_index.get(card_number, []):
            matched.append(
                {
                    "table_name": str(row["table_name"]),
                    "record_id": int(row["record_id"]),
                    "base_id": row["base_id"],
                    "card_number": str(row["card_number"]),
                    "card_name": str(row["card_name"]),
                    "image_path": str(path),
                    "image_format": suffix.lstrip("."),
                    "match_type": match_type,
                }
            )
    return {
        "schema_version": "card_image_index.v1",
        "db_path": str(db_path),
        "image_dir": str(image_dir),
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
        "matched": matched,
        "unmatched": unmatched,
    }


def build_card_image_reference_manifest(index_payload: dict[str, object]) -> dict[str, object]:
    matched = index_payload.get("matched", [])
    if not isinstance(matched, list):
        matched = []
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in matched:
        if not isinstance(row, dict):
            continue
        card_number = str(row.get("card_number", "")).strip()
        if not card_number:
            continue
        grouped.setdefault(card_number, []).append(row)

    def _rank(row: dict[str, object]) -> tuple[int, int, str]:
        table_rank = 0 if str(row.get("table_name", "")) == "cards" else 1
        match_type = str(row.get("match_type", ""))
        match_rank = {
            "exact_stem": 0,
            "normalized_number_padding": 1,
            "normalized_promo_suffix": 2,
            "substring_stem": 3,
        }.get(match_type, 9)
        return (table_rank, match_rank, str(row.get("image_path", "")))

    cards: list[dict[str, object]] = []
    for card_number in sorted(grouped.keys()):
        rows = sorted(grouped[card_number], key=_rank)
        primary = rows[0]
        cards.append(
            {
                "card_number": card_number,
                "primary_image_path": str(primary.get("image_path", "")),
                "primary_image_format": str(primary.get("image_format", "")),
                "card_name": str(primary.get("card_name", "")),
                "table_name": str(primary.get("table_name", "")),
                "record_id": int(primary.get("record_id", 0) or 0),
                "match_type": str(primary.get("match_type", "")),
                "image_count": len({str(row.get("image_path", "")) for row in rows}),
                "images": [
                    {
                        "image_path": str(row.get("image_path", "")),
                        "image_format": str(row.get("image_format", "")),
                        "table_name": str(row.get("table_name", "")),
                        "record_id": int(row.get("record_id", 0) or 0),
                        "match_type": str(row.get("match_type", "")),
                    }
                    for row in rows
                ],
            }
        )
    return {
        "schema_version": "card_image_reference_manifest.v1",
        "image_dir": str(index_payload.get("image_dir", "")),
        "card_count": len(cards),
        "cards": cards,
    }


def summarize_unmatched_card_images(index_payload: dict[str, object]) -> dict[str, object]:
    unmatched = index_payload.get("unmatched", [])
    if not isinstance(unmatched, list):
        unmatched = []
    grouped: dict[str, list[dict[str, str]]] = {}
    junk: list[dict[str, str]] = []
    for row in unmatched:
        if not isinstance(row, dict):
            continue
        stem = str(row.get("stem", "")).strip()
        base = normalize_card_image_stem_to_base(stem)
        if not base or len(base) < 4 or "-" not in base:
            junk.append({"stem": stem, "image_path": str(row.get("image_path", ""))})
            continue
        grouped.setdefault(base, []).append(
            {
                "stem": stem,
                "image_path": str(row.get("image_path", "")),
            }
        )
    missing = [
        {
            "base_card_number": base,
            "file_count": len(rows),
            "stems": sorted({row["stem"] for row in rows}),
            "image_paths": [row["image_path"] for row in rows],
        }
        for base, rows in sorted(grouped.items())
    ]
    return {
        "schema_version": "card_image_missing_base_summary.v1",
        "missing_base_count": len(missing),
        "junk_file_count": len(junk),
        "missing_bases": missing,
        "junk_files": junk,
    }
