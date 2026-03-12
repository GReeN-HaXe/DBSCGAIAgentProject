from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://api.deckplanet.net/cardsearch/dbs_masters_cards"
DEFAULT_FILTER = '{"_and":[{"status":{"_eq":"published"}},{"variant_of":{"id":{"_null":true}}}]}'
DEFAULT_DEEP = '{"variants":{"_limit":-1,"_sort":"card_number","_filter":{"status":{"_eq":"published"}}}}'


def _load_missing_card_numbers(path: Path) -> list[str]:
    rows: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            card_number = str(row.get("base_card_number", "")).strip().upper()
            if card_number:
                rows.append(card_number)
    return rows


def _extract_total_pages(payload: dict[str, Any]) -> int | None:
    meta = payload.get("meta", {})
    if not isinstance(meta, dict):
        return None
    for key in ("last_page", "pageCount", "total_pages"):
        value = meta.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _fetch_page(*, page: int, timeout_seconds: float) -> dict[str, Any]:
    params = {
        "page": page,
        "filter": DEFAULT_FILTER,
        "deep": DEFAULT_DEEP,
    }
    response = requests.get(BASE_URL, params=params, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected response payload type for page {page}")
    return payload


def _card_number_from_row(row: dict[str, Any]) -> str:
    return str(row.get("card_number", "")).strip().upper()


def export_cards(
    *,
    output_json: Path,
    timeout_seconds: float = 30.0,
    delay_seconds: float = 0.3,
    max_pages: int | None = None,
) -> dict[str, Any]:
    all_cards: list[dict[str, Any]] = []
    page = 1
    total_pages: int | None = None

    while True:
        if max_pages is not None and page > max_pages:
            break
        if total_pages is not None and page > total_pages:
            break

        print(f"Pulling page {page}...")
        payload = _fetch_page(page=page, timeout_seconds=timeout_seconds)
        data = payload.get("data", [])
        if not isinstance(data, list):
            data = []
        all_cards.extend(data)

        discovered_total_pages = _extract_total_pages(payload)
        if discovered_total_pages is not None:
            total_pages = discovered_total_pages

        if not data:
            break
        page += 1
        time.sleep(max(0.0, delay_seconds))

    result = {
        "schema_version": "deckplanet.full_export.v1",
        "source": BASE_URL,
        "card_count": len(all_cards),
        "cards": all_cards,
    }
    output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Export complete. Total cards: {len(all_cards)}")
    print(f"wrote: {output_json}")
    return result


def export_missing_cards(
    *,
    missing_csv: Path,
    output_json: Path,
    timeout_seconds: float = 30.0,
    delay_seconds: float = 0.3,
    max_pages: int | None = None,
) -> dict[str, Any]:
    missing_numbers = _load_missing_card_numbers(missing_csv)
    remaining = set(missing_numbers)
    found: list[dict[str, Any]] = []
    page = 1
    total_pages: int | None = None

    while remaining:
        if max_pages is not None and page > max_pages:
            break
        if total_pages is not None and page > total_pages:
            break

        print(f"Pulling page {page}...")
        payload = _fetch_page(page=page, timeout_seconds=timeout_seconds)
        data = payload.get("data", [])
        if not isinstance(data, list):
            data = []

        discovered_total_pages = _extract_total_pages(payload)
        if discovered_total_pages is not None:
            total_pages = discovered_total_pages

        for row in data:
            if not isinstance(row, dict):
                continue
            card_number = _card_number_from_row(row)
            if card_number in remaining:
                found.append(row)
                remaining.discard(card_number)

        if not data:
            break
        page += 1
        time.sleep(max(0.0, delay_seconds))

    result = {
        "schema_version": "deckplanet.missing_cards_export.v1",
        "source": BASE_URL,
        "requested_count": len(missing_numbers),
        "found_count": len(found),
        "missing_count": len(remaining),
        "missing_card_numbers": sorted(remaining),
        "cards": found,
    }
    output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Missing-card export complete. Found: {len(found)} Remaining: {len(remaining)}")
    print(f"wrote: {output_json}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="DeckPlanet DBS Masters export utility.")
    parser.add_argument("--mode", choices=["full", "missing"], default="full", help="Export full dataset or only missing card numbers.")
    parser.add_argument("--output", type=Path, default=Path("dbs_masters_full.json"), help="Output JSON path.")
    parser.add_argument("--missing-csv", type=Path, default=Path("artifacts/card_image_missing_bases.csv"), help="Missing-base CSV used in missing mode.")
    parser.add_argument("--timeout-seconds", type=float, default=30.0, help="HTTP request timeout.")
    parser.add_argument("--delay-seconds", type=float, default=0.3, help="Delay between page requests.")
    parser.add_argument("--max-pages", type=int, default=None, help="Optional page limit for debugging.")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.mode == "missing":
        export_missing_cards(
            missing_csv=args.missing_csv,
            output_json=args.output,
            timeout_seconds=float(args.timeout_seconds),
            delay_seconds=float(args.delay_seconds),
            max_pages=args.max_pages,
        )
        return

    export_cards(
        output_json=args.output,
        timeout_seconds=float(args.timeout_seconds),
        delay_seconds=float(args.delay_seconds),
        max_pages=args.max_pages,
    )


if __name__ == "__main__":
    main()
