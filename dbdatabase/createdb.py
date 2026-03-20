# createdb.py
# Build a local SQLite database from DeckPlanet DBS Masters export JSON.
# - Stores base cards (variant_of == null) in `cards`
# - Stores print variants (nested `variants`) in `variants`
# - Preserves leader back-side fields (card_back_*)
# - Uses *_unstyled skill text for clean searching/processing
#
# Usage:
#   python createdb.py
#
# Input:
#   dbs_masters_full.json   (in the same folder, or change INPUT_JSON below)
#
# Output:
#   dbs_masters.db          (SQLite DB in the same folder)

import json
import sqlite3
from pathlib import Path
import sys
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dbdatabase.source_text_patches import DEFAULT_PATCH_PATH, apply_source_text_patches_to_export_payload, load_source_text_patches_json

DB_DIR = Path(__file__).resolve().parent
INPUT_JSON = str(DB_DIR / "dbs_masters_full.json")
OUTPUT_DB = str(DB_DIR / "dbs_masters.db")
MISSING_CARDS_PATCH_SQL = ROOT / "artifacts" / "deckplanet_missing_cards_patch.sql"
MISSING_CARDS_PATCH_SUMMARY = ROOT / "artifacts" / "deckplanet_missing_cards_patch_summary.json"


def norm_str(x: Any) -> Optional[str]:
    """Normalize strings: empty/whitespace/'-'/'—'/full-width spaces -> None."""
    if x is None:
        return None
    if not isinstance(x, str):
        x = str(x)
    s = x.strip()
    if s in ("", "-", "—"):
        return None
    # Some fields use full-width spaces like "　"
    if s.replace("　", "").strip() == "":
        return None
    return s


def to_int(x: Any) -> Optional[int]:
    """Convert numeric strings to int safely; return None if not purely digits."""
    s = norm_str(x)
    if s is None:
        return None
    if s.isdigit():
        return int(s)
    return None


def to_json_text(x: Any) -> str:
    """Store arrays/objects as compact JSON text."""
    if x is None:
        return "[]"
    if isinstance(x, (list, dict)):
        return json.dumps(x, ensure_ascii=False, separators=(",", ":"))
    return json.dumps([x], ensure_ascii=False, separators=(",", ":"))


def apply_missing_cards_patch(conn: sqlite3.Connection) -> dict[str, Any] | None:
    if not MISSING_CARDS_PATCH_SQL.exists():
        return None

    conn.commit()
    sql_text = MISSING_CARDS_PATCH_SQL.read_text(encoding="utf-8")
    conn.executescript(sql_text)
    conn.commit()

    if not MISSING_CARDS_PATCH_SUMMARY.exists():
        return {}
    summary = json.loads(MISSING_CARDS_PATCH_SUMMARY.read_text(encoding="utf-8"))
    if isinstance(summary, dict):
        return summary
    return {}


def main() -> None:
    # Load dataset
    data_text = Path(INPUT_JSON).read_text(encoding="utf-8")
    cards = json.loads(data_text)
    if Path(DEFAULT_PATCH_PATH).exists():
        patches = load_source_text_patches_json(DEFAULT_PATCH_PATH)
        cards, _ = apply_source_text_patches_to_export_payload(cards, patches)

    conn = sqlite3.connect(OUTPUT_DB)
    cur = conn.cursor()

    # Performance pragmas (safe for local build)
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA temp_store=MEMORY;")

    # Drop & recreate (optional: comment these out if you want incremental updates)
    cur.execute("DROP TABLE IF EXISTS variants;")
    cur.execute("DROP TABLE IF EXISTS cards;")

    # Main tables
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cards (
      id                     INTEGER PRIMARY KEY,
      card_number            TEXT UNIQUE,
      card_name              TEXT,
      card_series            TEXT,
      card_rarity            TEXT,
      card_type              TEXT,
      card_color             TEXT,

      energy_cost_int        INTEGER,
      combo_cost_int         INTEGER,
      combo_power_int        INTEGER,
      power_int              INTEGER,

      card_energy_cost       TEXT,
      card_combo_cost        TEXT,
      card_combo_power       TEXT,
      card_power             TEXT,

      card_skill_unstyled    TEXT,
      card_skill_html        TEXT,

      card_traits_json       TEXT,
      card_character_json    TEXT,
      card_era_json          TEXT,
      keywords_json          TEXT,

      z_energy_cost          TEXT,

      is_banned              INTEGER,
      is_limited             INTEGER,
      limited_to             INTEGER,

      -- Leader backside (if present)
      card_back_name               TEXT,
      card_back_power              TEXT,
      card_back_skill_unstyled     TEXT,
      card_back_skill_html         TEXT,
      card_back_traits_json        TEXT,
      card_back_character_json     TEXT,
      card_back_era_json           TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS variants (
      id                     INTEGER PRIMARY KEY,
      base_id                INTEGER,
      card_number            TEXT UNIQUE,
      card_name              TEXT,
      card_series            TEXT,
      card_rarity            TEXT,
      card_type              TEXT,
      card_color             TEXT,

      energy_cost_int        INTEGER,
      combo_cost_int         INTEGER,
      combo_power_int        INTEGER,
      power_int              INTEGER,

      card_energy_cost       TEXT,
      card_combo_cost        TEXT,
      card_combo_power       TEXT,
      card_power             TEXT,

      card_skill_unstyled    TEXT,
      card_skill_html        TEXT,

      card_traits_json       TEXT,
      card_character_json    TEXT,
      card_era_json          TEXT,
      keywords_json          TEXT,

      z_energy_cost          TEXT,

      is_banned              INTEGER,
      is_limited             INTEGER,
      limited_to             INTEGER,

      card_back_name               TEXT,
      card_back_power              TEXT,
      card_back_skill_unstyled     TEXT,
      card_back_skill_html         TEXT,
      card_back_traits_json        TEXT,
      card_back_character_json     TEXT,
      card_back_era_json           TEXT,

      FOREIGN KEY(base_id) REFERENCES cards(id)
    );
    """)

    # Helpful indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(card_name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cards_number ON cards(card_number);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cards_color ON cards(card_color);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cards_type ON cards(card_type);")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_variants_name ON variants(card_name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_variants_number ON variants(card_number);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_variants_base ON variants(base_id);")

    def upsert_card(row: dict) -> None:
        cur.execute("""
        INSERT OR REPLACE INTO cards (
          id, card_number, card_name, card_series, card_rarity, card_type, card_color,
          energy_cost_int, combo_cost_int, combo_power_int, power_int,
          card_energy_cost, card_combo_cost, card_combo_power, card_power,
          card_skill_unstyled, card_skill_html,
          card_traits_json, card_character_json, card_era_json, keywords_json,
          z_energy_cost, is_banned, is_limited, limited_to,
          card_back_name, card_back_power, card_back_skill_unstyled, card_back_skill_html,
          card_back_traits_json, card_back_character_json, card_back_era_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
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
        ))

    def insert_variant(variant: dict, base_id: int) -> None:
        cols = [
            "id","base_id","card_number","card_name","card_series","card_rarity","card_type","card_color",
            "energy_cost_int","combo_cost_int","combo_power_int","power_int",
            "card_energy_cost","card_combo_cost","card_combo_power","card_power",
            "card_skill_unstyled","card_skill_html",
            "card_traits_json","card_character_json","card_era_json","keywords_json",
            "z_energy_cost","is_banned","is_limited","limited_to",
            "card_back_name","card_back_power","card_back_skill_unstyled","card_back_skill_html",
            "card_back_traits_json","card_back_character_json","card_back_era_json"
        ]

        values = (
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
        )

        # Safety check to prevent mismatched placeholders forever
        if len(cols) != len(values):
            raise RuntimeError(f"Variant insert mismatch: {len(cols)} cols vs {len(values)} values")

        placeholders = ",".join(["?"] * len(cols))
        cur.execute(
            f"INSERT OR REPLACE INTO variants ({','.join(cols)}) VALUES ({placeholders})",
            values
        )

    # Build DB
    base_count = 0
    variant_count = 0
    skipped_variant_refs = 0

    for row in cards:
        # Insert only base prints (variant_of == null)
        if row.get("variant_of") is not None:
            continue

        upsert_card(row)
        base_id = row.get("id")
        base_count += 1

        # Variants might contain dicts (full objects) or ints (IDs). Skip non-dicts.
        for v in (row.get("variants") or []):
            if not isinstance(v, dict):
                skipped_variant_refs += 1
                continue
            insert_variant(v, base_id)
            variant_count += 1

        # Commit in chunks for speed/memory safety
        if base_count % 500 == 0:
            conn.commit()
            print(f"Inserted {base_count} base cards... variants so far: {variant_count}")

    conn.commit()
    missing_cards_summary = apply_missing_cards_patch(conn)
    conn.close()

    print("\nDatabase build complete.")
    print(f"Base cards inserted: {base_count}")
    print(f"Variants inserted:  {variant_count}")
    if missing_cards_summary is not None:
        print(
            "Missing-cards patch applied: "
            f"base_cards_in_patch={int(missing_cards_summary.get('base_cards_in_patch', 0) or 0)} "
            f"variants_in_patch={int(missing_cards_summary.get('variants_in_patch', 0) or 0)}"
        )
    if skipped_variant_refs:
        print(f"Skipped variant id references (non-dict entries): {skipped_variant_refs}")
    print(f"Output DB: {OUTPUT_DB}")


if __name__ == "__main__":
    main()
