from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from src.agent.card_image_index import (
    build_card_image_reference_manifest,
    index_local_card_images,
    load_card_number_index,
    normalize_card_image_stem_to_base,
    summarize_unmatched_card_images,
)


def _build_test_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, card_number TEXT, card_name TEXT)")
        cur.execute("CREATE TABLE variants (id INTEGER PRIMARY KEY, base_id INTEGER, card_number TEXT, card_name TEXT)")
        cur.execute("INSERT INTO cards (id, card_number, card_name) VALUES (1, 'BT1-001', 'Card A')")
        cur.execute("INSERT INTO cards (id, card_number, card_name) VALUES (2, 'BT1-002', 'Card B')")
        cur.execute("INSERT INTO variants (id, base_id, card_number, card_name) VALUES (10, 1, 'BT1-001', 'Card A Alt')")
        conn.commit()
    finally:
        conn.close()


def test_card_image_index_matches_local_files(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _build_test_db(db_path)
    (image_dir / "BT1-001.webp").write_text("fake", encoding="utf-8")
    (image_dir / "BT1-002 extra.webp").write_text("fake", encoding="utf-8")
    (image_dir / "unknown_card.webp").write_text("fake", encoding="utf-8")

    index = load_card_number_index(db_path)
    assert "BT1-001" in index

    payload = index_local_card_images(image_dir, db_path)
    assert payload["matched_count"] == 3
    assert payload["unmatched_count"] == 1


def test_card_image_index_normalizes_promo_suffixes_and_builds_reference(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _build_test_db(db_path)
    (image_dir / "BT1-001_PR2.webp").write_text("fake", encoding="utf-8")
    (image_dir / "BT1-001_ALT.webp").write_text("fake", encoding="utf-8")

    payload = index_local_card_images(image_dir, db_path)
    assert payload["matched_count"] == 4
    assert payload["unmatched_count"] == 0
    assert any(row["match_type"] == "normalized_promo_suffix" for row in payload["matched"])

    reference = build_card_image_reference_manifest(payload)
    assert reference["card_count"] == 1
    assert reference["cards"][0]["card_number"] == "BT1-001"
    assert reference["cards"][0]["image_count"] == 2


def test_card_image_index_summarizes_true_missing_bases(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _build_test_db(db_path)
    (image_dir / "BT10-088_PR2.webp").write_text("fake", encoding="utf-8")
    (image_dir / "BT10-088_GDR.webp").write_text("fake", encoding="utf-8")
    (image_dir / "d.webp").write_text("fake", encoding="utf-8")

    assert normalize_card_image_stem_to_base("BT10-088_PR2") == "BT10-088"
    assert normalize_card_image_stem_to_base("BT10-088_GDR") == "BT10-088"

    payload = index_local_card_images(image_dir, db_path)
    summary = summarize_unmatched_card_images(payload)
    assert summary["missing_base_count"] == 1
    assert summary["junk_file_count"] == 1
    assert summary["missing_bases"][0]["base_card_number"] == "BT10-088"


def test_card_image_index_normalizes_zero_padded_card_numbers(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _build_test_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO cards (id, card_number, card_name) VALUES (3, 'BT29-048', 'Card C')")
        conn.commit()
    finally:
        conn.close()

    (image_dir / "BT29-48.webp").write_text("fake", encoding="utf-8")

    assert normalize_card_image_stem_to_base("BT29-48") == "BT29-048"

    payload = index_local_card_images(image_dir, db_path)
    assert payload["matched_count"] == 1
    assert payload["unmatched_count"] == 0
    assert payload["matched"][0]["card_number"] == "BT29-048"
    assert payload["matched"][0]["match_type"] == "normalized_number_padding"


def test_card_image_index_script(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _build_test_db(db_path)
    (image_dir / "BT1-001.webp").write_text("fake", encoding="utf-8")

    output_json = tmp_path / "card_image_index.json"
    matched_csv = tmp_path / "matched.csv"
    unmatched_csv = tmp_path / "unmatched.csv"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/index_local_card_images.py",
            "--image-dir",
            str(image_dir),
            "--db-path",
            str(db_path),
            "--output-json",
            str(output_json),
            "--output-matched-csv",
            str(matched_csv),
            "--output-unmatched-csv",
            str(unmatched_csv),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["matched_count"] == 2
    assert matched_csv.exists()

    reference_json = tmp_path / "reference.json"
    reference_result = subprocess.run(
        [
            sys.executable,
            "scripts/build_card_image_reference_manifest.py",
            "--index-json",
            str(output_json),
            "--output",
            str(reference_json),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert reference_result.returncode == 0, reference_result.stderr
    reference = json.loads(reference_json.read_text(encoding="utf-8"))
    assert reference["card_count"] == 1

    missing_json = tmp_path / "missing.json"
    missing_csv = tmp_path / "missing.csv"
    junk_csv = tmp_path / "junk.csv"
    missing_result = subprocess.run(
        [
            sys.executable,
            "scripts/summarize_unmatched_card_images.py",
            "--index-json",
            str(output_json),
            "--output-json",
            str(missing_json),
            "--output-missing-csv",
            str(missing_csv),
            "--output-junk-csv",
            str(junk_csv),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing_result.returncode == 0, missing_result.stderr
    summary = json.loads(missing_json.read_text(encoding="utf-8"))
    assert "missing_base_count" in summary
