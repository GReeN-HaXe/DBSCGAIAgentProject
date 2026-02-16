# tag_cards.py
# Adds derived skill tags + parses skills for fast competitive querying.

import re
import sqlite3
from typing import Optional, Tuple

DB_PATH = "dbs_masters.db"

# --- helpers -------------------------------------------------

def combined_text(front: Optional[str], back: Optional[str]) -> str:
    a = (front or "").strip()
    b = (back or "").strip()
    if a and b:
        return a + "\n" + b
    return a or b

def has(pattern: str, text: str) -> int:
    return 1 if re.search(pattern, text, flags=re.IGNORECASE) else 0

def max_draw(text: str) -> int:
    # captures "Draw 2 cards", "draw 1 card", etc.
    nums = [int(n) for n in re.findall(r"\bdraw\s+(\d+)\s+card", text, flags=re.IGNORECASE)]
    return max(nums) if nums else 0

def max_power_reduction(text: str) -> int:
    # captures "-30000 power", "-25000 power", etc. Keep the maximum magnitude.
    nums = [int(n) for n in re.findall(r"-\s*(\d{3,5})\s*power", text, flags=re.IGNORECASE)]
    return max(nums) if nums else 0

def compute_tags(text: str) -> Tuple[int, int, int, int, int, int, int, int, int, int]:
    # Timing / keywords
    has_counter          = has(r"\bcounter\s*:", text)
    has_counter_attack   = has(r"\bcounter\s*:\s*attack\b", text)
    has_counter_play     = has(r"\bcounter\s*:\s*play\b", text)
    has_activate_main    = has(r"\bactivate\s*:\s*main\b", text)
    has_activate_battle  = has(r"\bactivate\s*:\s*battle\b", text)
    has_auto             = has(r"\bauto\b", text)
    has_permanent        = has(r"\bpermanent\b", text)
    has_barrier          = has(r"\bBarrier\b", text)

    # Interaction / win pressure
    ignores_barrier = has(r"\bignoring\s+\[Barrier\]\b", text)
    grants_triple_strike = has(r"\btriple\s+strike\b", text)

    return (
        has_counter,
        has_counter_attack,
        has_counter_play,
        has_activate_main,
        has_activate_battle,
        has_auto,
        has_permanent,
        has_barrier,
        ignores_barrier,
        grants_triple_strike,
        1 if max_draw(text) > 0 else 0,
    )

# --- schema changes -----------------------------------------

CARD_COLS = [
    ("has_counter", "INTEGER DEFAULT 0"),
    ("has_counter_attack", "INTEGER DEFAULT 0"),
    ("has_counter_play", "INTEGER DEFAULT 0"),
    ("has_activate_main", "INTEGER DEFAULT 0"),
    ("has_activate_battle", "INTEGER DEFAULT 0"),
    ("has_auto", "INTEGER DEFAULT 0"),
    ("has_permanent", "INTEGER DEFAULT 0"),
    ("has_barrier", "INTEGER DEFAULT 0"),
    ("ignores_barrier", "INTEGER DEFAULT 0"),
    ("grants_triple_strike", "INTEGER DEFAULT 0"),
    ("has_draw", "INTEGER DEFAULT 0"),
    ("max_draw", "INTEGER DEFAULT 0"),
    ("max_power_reduction", "INTEGER DEFAULT 0"),
]

def add_columns(conn: sqlite3.Connection, table: str) -> None:
    cur = conn.cursor()
    existing = {row[1].lower() for row in cur.execute(f"PRAGMA table_info({table});").fetchall()}
    for col, decl in CARD_COLS:
        if col.lower() not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl};")
    conn.commit()

# --- tagging -------------------------------------------------

def tag_table(conn: sqlite3.Connection, table: str) -> None:
    cur = conn.cursor()

    # fetch in batches to keep memory stable
    cur.execute(f"SELECT id, card_skill_unstyled, card_back_skill_unstyled FROM {table};")

    updates = []
    batch = 1000
    count = 0

    for row in cur:
        card_id = row[0]
        front = row[1]
        back = row[2]
        text = combined_text(front, back)

        (
            has_counter,
            has_counter_attack,
            has_counter_play,
            has_activate_main,
            has_activate_battle,
            has_auto,
            has_permanent,
            has_barrier,
            ignores_barrier,
            grants_triple_strike,
            has_draw_flag,
        ) = compute_tags(text)

        md = max_draw(text)
        mpr = max_power_reduction(text)

        updates.append((
            has_counter,
            has_counter_attack,
            has_counter_play,
            has_activate_main,
            has_activate_battle,
            has_auto,
            has_permanent,
            has_barrier,
            ignores_barrier,
            grants_triple_strike,
            has_draw_flag,
            md,
            mpr,
            card_id
        ))

        count += 1
        if len(updates) >= batch:
            cur.executemany(
                f"""UPDATE {table}
                    SET has_counter=?,
                        has_counter_attack=?,
                        has_counter_play=?,
                        has_activate_main=?,
                        has_activate_battle=?,
                        has_auto=?,
                        has_permanent=?,
                        has_barrier=?,
                        ignores_barrier=?,
                        grants_triple_strike=?,
                        has_draw=?,
                        max_draw=?,
                        max_power_reduction=?
                    WHERE id=?;""",
                updates
            )
            conn.commit()
            updates.clear()
            print(f"{table}: tagged {count} rows...")

    # flush remaining
    if updates:
        cur.executemany(
            f"""UPDATE {table}
                SET has_counter=?,
                    has_counter_attack=?,
                    has_counter_play=?,
                    has_activate_main=?,
                    has_activate_battle=?,
                    has_auto=?,
                    has_permanent=?,
                    has_barrier=?,
                    ignores_barrier=?,
                    grants_triple_strike=?,
                    has_draw=?,
                    max_draw=?,
                    max_power_reduction=?
                WHERE id=?;""",
            updates
        )
        conn.commit()

    print(f"{table}: tagging complete. Total rows tagged: {count}")

def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    # Add columns to both tables
    add_columns(conn, "cards")
    add_columns(conn, "variants")

    # Tag them
    tag_table(conn, "cards")
    tag_table(conn, "variants")

    conn.close()
    print("✅ Done. Skill parsing columns added and populated.")

if __name__ == "__main__":
    main()
