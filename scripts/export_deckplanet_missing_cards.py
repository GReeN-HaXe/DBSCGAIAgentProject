from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin
from urllib.request import Request, urlopen


CARD_NUMBER_PATTERN = re.compile(r"\b[A-Z]{1,4}\d{0,2}-\d{3}\b")
IMAGE_URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+?\.(?:webp|png|jpg|jpeg)")


def _http_get_text(url: str, *, user_agent: str, timeout_seconds: float) -> str:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", errors="replace")


def _http_download(url: str, destination: Path, *, user_agent: str, timeout_seconds: float) -> None:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout_seconds) as response:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.read())


def _load_missing_bases(path: Path) -> list[str]:
    rows: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            card_number = str(row.get("base_card_number", "")).strip().upper()
            if card_number:
                rows.append(card_number)
    return rows


def _extract_image_candidates_for_card(html: str, card_number: str) -> list[str]:
    windows: list[str] = []
    for match in re.finditer(re.escape(card_number), html, flags=re.IGNORECASE):
        start = max(0, match.start() - 4000)
        end = min(len(html), match.end() + 4000)
        windows.append(html[start:end])
    candidates: list[str] = []
    for chunk in windows:
        candidates.extend(IMAGE_URL_PATTERN.findall(chunk))
        for rel in re.findall(r"""(?:src|href)=["']([^"']+\.(?:webp|png|jpg|jpeg))["']""", chunk, flags=re.IGNORECASE):
            candidates.append(rel)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(key)
    return deduped


def _choose_best_image_candidate(candidates: Iterable[str], *, base_url: str) -> str | None:
    normalized = [urljoin(base_url, item) for item in candidates]
    ranked = sorted(
        normalized,
        key=lambda url: (
            0 if "deckplanet" in url.lower() else 1,
            0 if url.lower().endswith(".webp") else 1,
            len(url),
        ),
    )
    return None if not ranked else ranked[0]


def export_deckplanet_missing_cards(
    *,
    missing_csv: Path,
    output_dir: Path,
    output_json: Path,
    max_pages: int,
    delay_seconds: float,
    timeout_seconds: float,
    user_agent: str,
) -> dict[str, object]:
    base_url = "https://www.deckplanet.net/dbs_masters/card-db?sort=-&page={page}"
    missing = _load_missing_bases(missing_csv)
    remaining = set(missing)
    found: list[dict[str, object]] = []
    not_found: list[str] = []

    for page in range(1, max_pages + 1):
        if not remaining:
            break
        page_url = base_url.format(page=page)
        html = _http_get_text(page_url, user_agent=user_agent, timeout_seconds=timeout_seconds)
        page_hits = [card for card in list(remaining) if re.search(re.escape(card), html, flags=re.IGNORECASE)]
        for card_number in page_hits:
            candidates = _extract_image_candidates_for_card(html, card_number)
            best = _choose_best_image_candidate(candidates, base_url=page_url)
            if best is None:
                continue
            extension = Path(best).suffix.lower() or ".webp"
            destination = output_dir / f"{card_number}{extension}"
            try:
                _http_download(best, destination, user_agent=user_agent, timeout_seconds=timeout_seconds)
            except Exception as exc:  # pragma: no cover - network/runtime dependent
                found.append(
                    {
                        "card_number": card_number,
                        "page_url": page_url,
                        "image_url": best,
                        "status": "download_failed",
                        "error": str(exc),
                    }
                )
                remaining.discard(card_number)
                continue
            found.append(
                {
                    "card_number": card_number,
                    "page_url": page_url,
                    "image_url": best,
                    "image_path": str(destination),
                    "status": "downloaded",
                }
            )
            remaining.discard(card_number)
        time.sleep(max(0.0, delay_seconds))

    not_found = sorted(remaining)
    payload = {
        "schema_version": "deckplanet_missing_cards_export.v1",
        "source": "https://www.deckplanet.net/dbs_masters/card-db?sort=-&page=1",
        "requested_count": len(missing),
        "downloaded_count": sum(1 for row in found if row.get("status") == "downloaded"),
        "failed_count": sum(1 for row in found if row.get("status") != "downloaded"),
        "not_found_count": len(not_found),
        "found": found,
        "not_found": not_found,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Heuristic DeckPlanet exporter for missing base card images.")
    parser.add_argument("--missing-csv", type=Path, default=Path("artifacts/card_image_missing_bases.csv"), help="Missing-base CSV produced by summarize_unmatched_card_images.py.")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/deckplanet_missing_cards"), help="Directory where downloaded images will be stored.")
    parser.add_argument("--output-json", type=Path, default=Path("artifacts/deckplanet_missing_cards_export.json"), help="Export manifest JSON path.")
    parser.add_argument("--max-pages", type=int, default=400, help="Maximum DeckPlanet card-db pages to scan.")
    parser.add_argument("--delay-seconds", type=float, default=0.5, help="Delay between page requests.")
    parser.add_argument("--timeout-seconds", type=float, default=20.0, help="Request timeout in seconds.")
    parser.add_argument("--user-agent", type=str, default="dbsAIAgent/1.0 (+local tooling)", help="HTTP User-Agent header.")
    args = parser.parse_args()

    payload = export_deckplanet_missing_cards(
        missing_csv=args.missing_csv,
        output_dir=args.output_dir,
        output_json=args.output_json,
        max_pages=int(args.max_pages),
        delay_seconds=float(args.delay_seconds),
        timeout_seconds=float(args.timeout_seconds),
        user_agent=str(args.user_agent),
    )
    print(f"wrote: {args.output_json}")
    print(
        f"downloaded_count={payload.get('downloaded_count', 0)} "
        f"failed_count={payload.get('failed_count', 0)} "
        f"not_found_count={payload.get('not_found_count', 0)}"
    )


if __name__ == "__main__":
    main()
