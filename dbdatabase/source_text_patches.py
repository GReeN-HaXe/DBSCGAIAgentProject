from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_PATCH_PATH = Path("dbdatabase/source_text_patches.json")

JSON_TO_SQLITE_FIELD_MAP = {
    "card_skill": "card_skill_html",
    "card_back_skill": "card_back_skill_html",
}


def load_source_text_patches_json(path: str | Path = DEFAULT_PATCH_PATH) -> list[dict[str, Any]]:
    patch_path = Path(path)
    payload = json.loads(patch_path.read_text(encoding="utf-8"))
    return normalize_source_text_patches(payload)


def normalize_source_text_patches(payload: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        patches_raw = payload
    elif isinstance(payload, dict):
        patches_raw = payload.get("patches", [])
    else:
        patches_raw = []
    normalized: list[dict[str, Any]] = []
    for row in patches_raw:
        if not isinstance(row, dict):
            continue
        card_number = str(row.get("card_number") or "").strip()
        if not card_number:
            continue
        fields = row.get("fields", {})
        if not isinstance(fields, dict):
            continue
        normalized_fields = {
            str(key): value
            for key, value in fields.items()
            if str(key).strip()
        }
        if not normalized_fields:
            continue
        normalized.append(
            {
                "card_number": card_number,
                "fields": normalized_fields,
                "reason": str(row.get("reason") or "").strip(),
                "apply_to_variants": bool(row.get("apply_to_variants", True)),
            }
        )
    return normalized


def apply_source_text_patches_to_export_payload(
    export_payload: list[dict[str, Any]],
    patches: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    patched_payload = deepcopy(export_payload)
    rows_by_number = {str(row.get("card_number") or "").strip(): row for row in patched_payload if isinstance(row, dict)}
    variant_rows_by_base_number: dict[str, list[dict[str, Any]]] = {}
    for row in patched_payload:
        if not isinstance(row, dict):
            continue
        base_number = str(row.get("card_number") or "").strip()
        for variant in row.get("variants") or []:
            if not isinstance(variant, dict):
                continue
            variant_rows_by_base_number.setdefault(base_number, []).append(variant)
    cards_touched = 0
    fields_applied = 0
    touched_numbers: list[str] = []
    for patch in patches:
        card_number = str(patch.get("card_number") or "").strip()
        row = rows_by_number.get(card_number)
        if row is None:
            continue
        card_touched = False
        for field_name, field_value in dict(patch.get("fields", {})).items():
            if row.get(field_name) != field_value:
                row[field_name] = field_value
                fields_applied += 1
                card_touched = True
        if card_touched:
            cards_touched += 1
            touched_numbers.append(card_number)
        if bool(patch.get("apply_to_variants", True)):
            for variant in variant_rows_by_base_number.get(card_number, []):
                variant_touched = False
                for field_name, field_value in dict(patch.get("fields", {})).items():
                    if variant.get(field_name) != field_value:
                        variant[field_name] = field_value
                        fields_applied += 1
                        variant_touched = True
                if variant_touched:
                    cards_touched += 1
                    touched_numbers.append(str(variant.get("card_number") or card_number))
    summary = {
        "patch_count": len(patches),
        "cards_touched": cards_touched,
        "fields_applied": fields_applied,
        "touched_card_numbers": touched_numbers,
    }
    return patched_payload, summary


def apply_source_text_patches_to_sqlite(
    db_path: str | Path,
    patches: list[dict[str, Any]],
) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    try:
        cards_touched = 0
        fields_applied = 0
        touched_numbers: list[str] = []
        for patch in patches:
            card_number = str(patch.get("card_number") or "").strip()
            if not card_number:
                continue
            assignments: list[str] = []
            values: list[Any] = []
            for field_name, field_value in dict(patch.get("fields", {})).items():
                sqlite_field = JSON_TO_SQLITE_FIELD_MAP.get(str(field_name), str(field_name))
                assignments.append(f"{sqlite_field} = ?")
                values.append(field_value)
            if not assignments:
                continue
            values.append(card_number)
            cur = conn.execute(
                f"UPDATE cards SET {', '.join(assignments)} WHERE card_number = ?",
                values,
            )
            variant_rows = 0
            if bool(patch.get("apply_to_variants", True)):
                base_row = conn.execute("SELECT id FROM cards WHERE card_number = ?", (card_number,)).fetchone()
                base_id = int(base_row[0]) if base_row is not None and base_row[0] is not None else -1
                variant_cur = conn.execute(
                    f"UPDATE variants SET {', '.join(assignments)} WHERE base_id = ?",
                    [*values[:-1], base_id],
                )
                variant_rows = int(variant_cur.rowcount or 0)
            if cur.rowcount > 0:
                cards_touched += cur.rowcount
                fields_applied += len(assignments) * cur.rowcount
                touched_numbers.append(card_number)
            if variant_rows > 0:
                cards_touched += variant_rows
                fields_applied += len(assignments) * variant_rows
                touched_numbers.append(card_number)
        conn.commit()
        return {
            "patch_count": len(patches),
            "cards_touched": cards_touched,
            "fields_applied": fields_applied,
            "touched_card_numbers": touched_numbers,
        }
    finally:
        conn.close()


def source_text_patch_summary(
    *,
    json_summary: dict[str, Any] | None = None,
    sqlite_summary: dict[str, Any] | None = None,
    patch_count: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": "dbs.source_text_patch_summary.v1",
        "patch_count": int(patch_count),
        "json_summary": dict(json_summary or {}),
        "sqlite_summary": dict(sqlite_summary or {}),
    }
