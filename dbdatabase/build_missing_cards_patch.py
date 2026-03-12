from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dbdatabase.createdb import norm_str, to_int, to_json_text


CARD_COLUMNS = [
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
]

VARIANT_COLUMNS = [
    "id",
    "base_id",
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
]


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _card_values(row: dict[str, Any]) -> list[Any]:
    return [
        row.get("id"),
        norm_str(row.get("card_number")),
        norm_str(row.get("card_name")),
        norm_str(row.get("card_series")),
        norm_str(row.get("card_rarity")),
        norm_str(row.get("card_type")),
        norm_str(row.get("card_color")),
        to_int(row.get("card_energy_cost")),
        to_int(row.get("card_combo_cost")),
        to_int(row.get("card_combo_power")),
        to_int(row.get("card_power")),
        norm_str(row.get("card_energy_cost")),
        norm_str(row.get("card_combo_cost")),
        norm_str(row.get("card_combo_power")),
        norm_str(row.get("card_power")),
        norm_str(row.get("card_skill_unstyled")),
        norm_str(row.get("card_skill")),
        to_json_text(row.get("card_traits")),
        to_json_text(row.get("card_character")),
        to_json_text(row.get("card_era")),
        to_json_text(row.get("keywords")),
        norm_str(row.get("z_energy_cost")),
        1 if row.get("is_banned") else 0,
        1 if row.get("is_limited") else 0,
        row.get("limited_to") if row.get("limited_to") is not None else None,
        norm_str(row.get("card_back_name")),
        norm_str(row.get("card_back_power")),
        norm_str(row.get("card_back_skill_unstyled")),
        norm_str(row.get("card_back_skill")),
        to_json_text(row.get("card_back_traits")),
        to_json_text(row.get("card_back_character")),
        to_json_text(row.get("card_back_era")),
    ]


def _variant_values(variant: dict[str, Any], base_id: int) -> list[Any]:
    return [
        variant.get("id"),
        base_id,
        norm_str(variant.get("card_number")),
        norm_str(variant.get("card_name")),
        norm_str(variant.get("card_series")),
        norm_str(variant.get("card_rarity")),
        norm_str(variant.get("card_type")),
        norm_str(variant.get("card_color")),
        to_int(variant.get("card_energy_cost")),
        to_int(variant.get("card_combo_cost")),
        to_int(variant.get("card_combo_power")),
        to_int(variant.get("card_power")),
        norm_str(variant.get("card_energy_cost")),
        norm_str(variant.get("card_combo_cost")),
        norm_str(variant.get("card_combo_power")),
        norm_str(variant.get("card_power")),
        norm_str(variant.get("card_skill_unstyled")),
        norm_str(variant.get("card_skill")),
        to_json_text(variant.get("card_traits")),
        to_json_text(variant.get("card_character")),
        to_json_text(variant.get("card_era")),
        to_json_text(variant.get("keywords")),
        norm_str(variant.get("z_energy_cost")),
        1 if variant.get("is_banned") else 0,
        1 if variant.get("is_limited") else 0,
        variant.get("limited_to") if variant.get("limited_to") is not None else None,
        norm_str(variant.get("card_back_name")),
        norm_str(variant.get("card_back_power")),
        norm_str(variant.get("card_back_skill_unstyled")),
        norm_str(variant.get("card_back_skill")),
        to_json_text(variant.get("card_back_traits")),
        to_json_text(variant.get("card_back_character")),
        to_json_text(variant.get("card_back_era")),
    ]


def _insert_sql(table_name: str, columns: list[str], values: list[Any]) -> str:
    literals = ", ".join(_sql_literal(value) for value in values)
    cols = ", ".join(columns)
    return f"INSERT OR REPLACE INTO {table_name} ({cols}) VALUES ({literals});"


def build_missing_cards_patch(export_payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    cards = export_payload.get("cards", [])
    if not isinstance(cards, list):
        cards = []
    statements: list[str] = [
        "-- Missing DBS Masters cards patch generated from DeckPlanet API export",
        "BEGIN TRANSACTION;",
    ]
    base_count = 0
    variant_count = 0
    found_numbers: list[str] = []
    for row in cards:
        if not isinstance(row, dict):
            continue
        base_id = row.get("id")
        if base_id is None:
            continue
        statements.append(_insert_sql("cards", CARD_COLUMNS, _card_values(row)))
        base_count += 1
        found_numbers.append(str(row.get("card_number", "")))
        for variant in row.get("variants") or []:
            if not isinstance(variant, dict):
                continue
            statements.append(_insert_sql("variants", VARIANT_COLUMNS, _variant_values(variant, int(base_id))))
            variant_count += 1
    statements.append("COMMIT;")
    summary = {
        "schema_version": "deckplanet.missing_cards_patch_summary.v1",
        "requested_count": int(export_payload.get("requested_count", 0) or 0),
        "found_count": int(export_payload.get("found_count", 0) or 0),
        "missing_count": int(export_payload.get("missing_count", 0) or 0),
        "base_cards_in_patch": base_count,
        "variants_in_patch": variant_count,
        "found_card_numbers": found_numbers,
        "missing_card_numbers": list(export_payload.get("missing_card_numbers", [])),
    }
    return "\n".join(statements) + "\n", summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an SQL patch file from the DeckPlanet missing-card export.")
    parser.add_argument("--input", type=Path, default=Path("artifacts/deckplanet_missing_cards_api.json"), help="Missing-card export JSON path.")
    parser.add_argument("--output-sql", type=Path, default=Path("artifacts/deckplanet_missing_cards_patch.sql"), help="SQL patch output path.")
    parser.add_argument("--output-summary", type=Path, default=Path("artifacts/deckplanet_missing_cards_patch_summary.json"), help="Patch summary JSON path.")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {args.input}")
    sql_text, summary = build_missing_cards_patch(payload)
    args.output_sql.parent.mkdir(parents=True, exist_ok=True)
    args.output_sql.write_text(sql_text, encoding="utf-8")
    args.output_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote: {args.output_sql}")
    print(f"wrote: {args.output_summary}")
    print(
        f"base_cards_in_patch={summary.get('base_cards_in_patch', 0)} "
        f"variants_in_patch={summary.get('variants_in_patch', 0)} "
        f"missing_count={summary.get('missing_count', 0)}"
    )


if __name__ == "__main__":
    main()
