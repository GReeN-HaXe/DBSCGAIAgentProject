from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dbdatabase.source_text_patches import (
    DEFAULT_PATCH_PATH,
    apply_source_text_patches_to_export_payload,
    apply_source_text_patches_to_sqlite,
    load_source_text_patches_json,
    source_text_patch_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply checked-in source text corrections to DBS export sources.")
    parser.add_argument("--patches", type=Path, default=DEFAULT_PATCH_PATH, help="Path to source text patch manifest.")
    parser.add_argument("--json-path", type=Path, default=Path("dbdatabase/dbs_masters_full.json"), help="Path to JSON export source.")
    parser.add_argument("--db-path", type=Path, default=Path("dbdatabase/dbs_masters.db"), help="Path to SQLite DB source.")
    parser.add_argument("--summary-path", type=Path, default=Path("artifacts/source_text_patch_summary.json"), help="Summary JSON output path.")
    args = parser.parse_args()

    patches = load_source_text_patches_json(args.patches)

    payload = json.loads(args.json_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"expected top-level JSON list in {args.json_path}")
    patched_payload, json_summary = apply_source_text_patches_to_export_payload(payload, patches)
    args.json_path.write_text(json.dumps(patched_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    sqlite_summary = apply_source_text_patches_to_sqlite(args.db_path, patches)

    summary = source_text_patch_summary(
        json_summary=json_summary,
        sqlite_summary=sqlite_summary,
        patch_count=len(patches),
    )
    args.summary_path.parent.mkdir(parents=True, exist_ok=True)
    args.summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Applied {len(patches)} source text patch(es).")
    print(f"Updated JSON: {args.json_path}")
    print(f"Updated SQLite DB: {args.db_path}")
    print(f"Wrote summary: {args.summary_path}")


if __name__ == "__main__":
    main()
