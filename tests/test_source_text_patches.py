from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import shutil

from dbdatabase.source_text_patches import (
    apply_source_text_patches_to_export_payload,
    apply_source_text_patches_to_sqlite,
    load_source_text_patches_json,
)


PATCH_PATH = Path("dbdatabase/source_text_patches.json")
JSON_PATH = Path("dbdatabase/dbs_masters_full.json")
DB_PATH = Path("dbdatabase/dbs_masters.db")


def test_apply_source_text_patches_to_export_payload_updates_base_and_variants() -> None:
    payload = [
        {
            "id": 10,
            "card_number": "BT1-001",
            "card_skill_unstyled": "bad text",
            "card_skill": "<b>bad text</b>",
            "variants": [
                {
                    "id": 11,
                    "card_number": "BT1-001_PR",
                    "card_skill_unstyled": "bad text",
                    "card_skill": "<b>bad text</b>",
                }
            ],
        }
    ]
    patches = [
        {
            "card_number": "BT1-001",
            "fields": {
                "card_skill_unstyled": "good text",
                "card_skill": "<b>good text</b>",
            },
            "apply_to_variants": True,
        }
    ]

    patched, summary = apply_source_text_patches_to_export_payload(payload, patches)

    assert patched[0]["card_skill_unstyled"] == "good text"
    assert patched[0]["card_skill"] == "<b>good text</b>"
    assert patched[0]["variants"][0]["card_skill_unstyled"] == "good text"
    assert patched[0]["variants"][0]["card_skill"] == "<b>good text</b>"
    assert summary["cards_touched"] == 2
    assert summary["fields_applied"] == 4


def test_apply_source_text_patches_to_sqlite_updates_cards_and_variants() -> None:
    scratch = Path("artifacts/test_source_text_patch_sqlite")
    if scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True, exist_ok=True)
    db_path = scratch / "patched.sqlite"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, card_number TEXT UNIQUE, card_skill_unstyled TEXT, card_skill_html TEXT)")
        conn.execute("CREATE TABLE variants (id INTEGER PRIMARY KEY, base_id INTEGER, card_number TEXT UNIQUE, card_skill_unstyled TEXT, card_skill_html TEXT)")
        conn.execute(
            "INSERT INTO cards (id, card_number, card_skill_unstyled, card_skill_html) VALUES (?,?,?,?)",
            (10, "BT1-001", "bad text", "<b>bad text</b>"),
        )
        conn.execute(
            "INSERT INTO variants (id, base_id, card_number, card_skill_unstyled, card_skill_html) VALUES (?,?,?,?,?)",
            (11, 10, "BT1-001_PR", "bad text", "<b>bad text</b>"),
        )
        conn.commit()
    finally:
        conn.close()

    patches = [
        {
            "card_number": "BT1-001",
            "fields": {
                "card_skill_unstyled": "good text",
                "card_skill": "<b>good text</b>",
            },
            "apply_to_variants": True,
        }
    ]
    summary = apply_source_text_patches_to_sqlite(db_path, patches)

    conn = sqlite3.connect(str(db_path))
    try:
        base = conn.execute(
            "SELECT card_skill_unstyled, card_skill_html FROM cards WHERE card_number = ?",
            ("BT1-001",),
        ).fetchone()
        variant = conn.execute(
            "SELECT card_skill_unstyled, card_skill_html FROM variants WHERE card_number = ?",
            ("BT1-001_PR",),
        ).fetchone()
    finally:
        conn.close()

    assert base == ("good text", "<b>good text</b>")
    assert variant == ("good text", "<b>good text</b>")
    assert summary["cards_touched"] == 2
    shutil.rmtree(scratch, ignore_errors=True)


def test_checked_in_source_text_patch_manifest_matches_bt27_100_sources() -> None:
    patches = load_source_text_patches_json(PATCH_PATH)
    bt27_100 = next(row for row in patches if row["card_number"] == "BT27-100")
    fields = bt27_100["fields"]

    export_payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    export_row = next(row for row in export_payload if row.get("card_number") == "BT27-100")
    assert export_row["card_skill_unstyled"] == fields["card_skill_unstyled"]
    assert export_row["card_skill"] == fields["card_skill"]

    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            "SELECT card_skill_unstyled, card_skill_html FROM cards WHERE card_number = ?",
            ("BT27-100",),
        ).fetchone()
    finally:
        conn.close()

    assert row == (fields["card_skill_unstyled"], fields["card_skill"])
