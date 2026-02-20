from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from src.db.interfaces import CardNotFoundError, CardQuery, CardRepository, InvalidCardRecordError
from src.domain.models import CardData

BASE_COLUMNS = [
    "id",
    "card_number",
    "card_name",
    "card_series",
    "card_rarity",
    "card_type",
    "card_color",
    "energy_cost_int",
    "combo_cost_int",
    "combo_power_int",
    "power_int",
    "card_energy_cost",
    "card_combo_cost",
    "card_combo_power",
    "card_power",
    "card_skill_unstyled",
    "card_skill_html",
    "card_traits_json",
    "card_character_json",
    "card_era_json",
    "keywords_json",
    "z_energy_cost",
    "is_banned",
    "is_limited",
    "limited_to",
    "card_back_name",
    "card_back_power",
    "card_back_skill_unstyled",
    "card_back_skill_html",
    "card_back_traits_json",
    "card_back_character_json",
    "card_back_era_json",
    "has_counter",
    "has_counter_attack",
    "has_counter_play",
    "has_activate_main",
    "has_activate_battle",
    "has_auto",
    "has_permanent",
    "ignores_barrier",
    "grants_triple_strike",
    "has_draw",
    "max_draw",
    "max_power_reduction",
    "has_barrier",
]


def _load_list(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return tuple(str(item) for item in parsed)
    except json.JSONDecodeError:
        return ()
    return ()


def _to_bool(value: int | None) -> bool:
    return bool(value or 0)


class SQLiteCardRepository(CardRepository):
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _validate_identity(self, row: sqlite3.Row) -> None:
        if row["id"] is None or not row["card_number"] or not row["card_name"]:
            raise InvalidCardRecordError("Record is missing required identity fields.")

    def _map_row(self, row: sqlite3.Row, source_table: str) -> CardData:
        self._validate_identity(row)
        row_keys = set(row.keys())
        base_id = row["base_id"] if "base_id" in row_keys else None
        return CardData(
            id=row["id"],
            card_number=row["card_number"],
            card_name=row["card_name"],
            source_table=source_table,
            base_id=base_id,
            card_series=row["card_series"],
            card_rarity=row["card_rarity"],
            card_type=row["card_type"],
            card_color=row["card_color"],
            energy_cost_int=row["energy_cost_int"],
            combo_cost_int=row["combo_cost_int"],
            combo_power_int=row["combo_power_int"],
            power_int=row["power_int"],
            card_energy_cost=row["card_energy_cost"],
            card_combo_cost=row["card_combo_cost"],
            card_combo_power=row["card_combo_power"],
            card_power=row["card_power"],
            card_skill_unstyled=row["card_skill_unstyled"],
            card_skill_html=row["card_skill_html"],
            z_energy_cost=row["z_energy_cost"],
            card_back_name=row["card_back_name"],
            card_back_power=row["card_back_power"],
            card_back_skill_unstyled=row["card_back_skill_unstyled"],
            card_back_skill_html=row["card_back_skill_html"],
            traits=_load_list(row["card_traits_json"]),
            character_tags=_load_list(row["card_character_json"]),
            era_tags=_load_list(row["card_era_json"]),
            keywords=_load_list(row["keywords_json"]),
            back_traits=_load_list(row["card_back_traits_json"]),
            back_character_tags=_load_list(row["card_back_character_json"]),
            back_era_tags=_load_list(row["card_back_era_json"]),
            is_banned=_to_bool(row["is_banned"]),
            is_limited=_to_bool(row["is_limited"]),
            limited_to=row["limited_to"],
            has_counter=_to_bool(row["has_counter"]),
            has_counter_attack=_to_bool(row["has_counter_attack"]),
            has_counter_play=_to_bool(row["has_counter_play"]),
            has_activate_main=_to_bool(row["has_activate_main"]),
            has_activate_battle=_to_bool(row["has_activate_battle"]),
            has_auto=_to_bool(row["has_auto"]),
            has_permanent=_to_bool(row["has_permanent"]),
            ignores_barrier=_to_bool(row["ignores_barrier"]),
            grants_triple_strike=_to_bool(row["grants_triple_strike"]),
            has_draw=_to_bool(row["has_draw"]),
            max_draw=row["max_draw"],
            max_power_reduction=row["max_power_reduction"],
            has_barrier=_to_bool(row["has_barrier"]),
        )

    def get_by_id(self, card_id: int, *, source_table: str = "cards") -> CardData:
        if source_table not in {"cards", "variants"}:
            raise ValueError("source_table must be 'cards' or 'variants'.")
        columns = BASE_COLUMNS if source_table == "cards" else ["base_id", *BASE_COLUMNS]
        sql = f"SELECT {', '.join(columns)} FROM {source_table} WHERE id = ?"
        with self._connect() as conn:
            row = conn.execute(sql, (card_id,)).fetchone()
        if row is None:
            raise CardNotFoundError(f"No card found with id={card_id} in {source_table}.")
        return self._map_row(row, source_table)

    def get_by_number(self, card_number: str, *, include_variants: bool = True) -> list[CardData]:
        rows: list[CardData] = []
        with self._connect() as conn:
            rowset = conn.execute(
                f"SELECT {', '.join(BASE_COLUMNS)} FROM cards WHERE card_number = ? ORDER BY id",
                (card_number,),
            ).fetchall()
            rows.extend(self._map_row(row, "cards") for row in rowset)
            if include_variants:
                variant_cols = ["base_id", *BASE_COLUMNS]
                rowset = conn.execute(
                    f"SELECT {', '.join(variant_cols)} FROM variants WHERE card_number = ? ORDER BY id",
                    (card_number,),
                ).fetchall()
                rows.extend(self._map_row(row, "variants") for row in rowset)
        return rows

    def list_by_ids(self, ids: Iterable[int], *, source_table: str = "cards") -> list[CardData]:
        if source_table not in {"cards", "variants"}:
            raise ValueError("source_table must be 'cards' or 'variants'.")
        ids_list = list(dict.fromkeys(int(x) for x in ids))
        if not ids_list:
            return []
        placeholders = ", ".join("?" for _ in ids_list)
        columns = BASE_COLUMNS if source_table == "cards" else ["base_id", *BASE_COLUMNS]
        sql = f"SELECT {', '.join(columns)} FROM {source_table} WHERE id IN ({placeholders}) ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(sql, ids_list).fetchall()
        return [self._map_row(row, source_table) for row in rows]

    def search(self, query: CardQuery) -> list[CardData]:
        clauses = []
        params: list[object] = []

        if not query.include_banned:
            clauses.append("COALESCE(is_banned, 0) = 0")
        if query.name_contains:
            clauses.append("LOWER(card_name) LIKE ?")
            params.append(f"%{query.name_contains.lower()}%")
        if query.card_number:
            clauses.append("card_number = ?")
            params.append(query.card_number)
        if query.colors:
            placeholders = ", ".join("?" for _ in query.colors)
            clauses.append(f"card_color IN ({placeholders})")
            params.extend(sorted(query.colors))
        if query.card_types:
            placeholders = ", ".join("?" for _ in query.card_types)
            clauses.append(f"card_type IN ({placeholders})")
            params.extend(sorted(query.card_types))

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(query.limit, 500))

        results: list[CardData] = []
        with self._connect() as conn:
            card_sql = f"""
                SELECT {", ".join(BASE_COLUMNS)}
                FROM cards
                {where_sql}
                ORDER BY id
                LIMIT ?
            """
            card_rows = conn.execute(card_sql, [*params, limit]).fetchall()
            results.extend(self._map_row(row, "cards") for row in card_rows)

            if query.include_variants and len(results) < limit:
                variant_cols = ["base_id", *BASE_COLUMNS]
                variant_sql = f"""
                    SELECT {", ".join(variant_cols)}
                    FROM variants
                    {where_sql}
                    ORDER BY id
                    LIMIT ?
                """
                remaining = limit - len(results)
                variant_rows = conn.execute(variant_sql, [*params, remaining]).fetchall()
                results.extend(self._map_row(row, "variants") for row in variant_rows)
        return results
