from __future__ import annotations

import json
from pathlib import Path

from dbdatabase import dbsdatabasescrapping as scraping


def test_export_missing_cards_filters_requested_numbers(tmp_path: Path, monkeypatch) -> None:
    missing_csv = tmp_path / "missing.csv"
    output_json = tmp_path / "missing_export.json"
    missing_csv.write_text("base_card_number,file_count\nBT10-088,5\nBT20-029,3\n", encoding="utf-8")

    pages = {
        1: {
            "meta": {"last_page": 2},
            "data": [
                {"card_number": "BT10-088", "card_name": "A"},
                {"card_number": "BT1-001", "card_name": "Ignore"},
            ],
        },
        2: {
            "meta": {"last_page": 2},
            "data": [
                {"card_number": "BT20-029", "card_name": "B"},
            ],
        },
    }

    def fake_fetch_page(*, page: int, timeout_seconds: float):
        return pages[page]

    monkeypatch.setattr(scraping, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(scraping.time, "sleep", lambda _: None)

    payload = scraping.export_missing_cards(
        missing_csv=missing_csv,
        output_json=output_json,
        timeout_seconds=1.0,
        delay_seconds=0.0,
    )
    assert payload["found_count"] == 2
    assert payload["missing_count"] == 0
    assert [row["card_number"] for row in payload["cards"]] == ["BT10-088", "BT20-029"]

    written = json.loads(output_json.read_text(encoding="utf-8"))
    assert written["found_count"] == 2


def test_export_missing_cards_reports_unresolved(tmp_path: Path, monkeypatch) -> None:
    missing_csv = tmp_path / "missing.csv"
    output_json = tmp_path / "missing_export.json"
    missing_csv.write_text("base_card_number,file_count\nBT10-088,5\nBT20-029,3\n", encoding="utf-8")

    def fake_fetch_page(*, page: int, timeout_seconds: float):
        return {"meta": {"last_page": 1}, "data": [{"card_number": "BT10-088", "card_name": "A"}]}

    monkeypatch.setattr(scraping, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(scraping.time, "sleep", lambda _: None)

    payload = scraping.export_missing_cards(
        missing_csv=missing_csv,
        output_json=output_json,
        timeout_seconds=1.0,
        delay_seconds=0.0,
    )
    assert payload["found_count"] == 1
    assert payload["missing_count"] == 1
    assert payload["missing_card_numbers"] == ["BT20-029"]
