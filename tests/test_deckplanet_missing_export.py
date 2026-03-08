from __future__ import annotations

from pathlib import Path

from scripts.export_deckplanet_missing_cards import (
    _choose_best_image_candidate,
    _extract_image_candidates_for_card,
    _load_missing_bases,
)


def test_deckplanet_missing_export_helpers(tmp_path: Path) -> None:
    csv_path = tmp_path / "missing.csv"
    csv_path.write_text("base_card_number,file_count\nBT20-029,3\nBT21-003,2\n", encoding="utf-8")
    missing = _load_missing_bases(csv_path)
    assert missing == ["BT20-029", "BT21-003"]

    html = """
    <div class="card">
      <span>BT20-029</span>
      <img src="/images/cards/BT20-029.webp">
      <a href="/dbs_masters/card/BT20-029">details</a>
    </div>
    """
    candidates = _extract_image_candidates_for_card(html, "BT20-029")
    assert "/images/cards/BT20-029.webp" in candidates
    chosen = _choose_best_image_candidate(candidates, base_url="https://www.deckplanet.net/dbs_masters/card-db?sort=-&page=1")
    assert chosen == "https://www.deckplanet.net/images/cards/BT20-029.webp"
