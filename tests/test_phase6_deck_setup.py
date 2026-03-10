from __future__ import annotations

import sqlite3

from src.agent.deck_setup import (
    import_deckplanet_deck_text,
    load_sample_game_setup_from_db,
    parse_card_id_text,
    parse_deckplanet_deck_text,
    validate_leader_and_deck,
)


def _build_test_db(path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, card_type TEXT, card_number TEXT)")
        conn.execute("INSERT INTO cards (id, card_type, card_number) VALUES (1, 'LEADER', 'BT1-001')")
        conn.execute("INSERT INTO cards (id, card_type, card_number) VALUES (2, 'LEADER', 'BT1-002')")
        for i in range(1000, 1120):
            conn.execute("INSERT INTO cards (id, card_type, card_number) VALUES (?, 'BATTLE', ?)", (i, f'BT9-{i - 999:03d}'))
        conn.commit()
    finally:
        conn.close()


def test_phase6_parse_card_id_text_handles_csv_and_space() -> None:
    ids = parse_card_id_text("1001,1002\n1003 1004")
    assert ids == [1001, 1002, 1003, 1004]


def test_phase6_load_sample_game_setup_from_db(tmp_path) -> None:
    db = tmp_path / "cards.db"
    _build_test_db(db)
    p1_leader, p1_deck, p2_leader, p2_deck = load_sample_game_setup_from_db(db, deck_size=60)
    assert p1_leader == 1
    assert p2_leader == 2
    assert len(p1_deck) == 60
    assert len(p2_deck) == 60


def test_phase6_validate_leader_and_deck_rejects_leader_in_deck(tmp_path) -> None:
    db = tmp_path / "cards.db"
    _build_test_db(db)
    bad_deck = [1] + list(range(1000, 1059))
    try:
        validate_leader_and_deck(db_path=db, leader_id=1, deck_ids=bad_deck, expected_deck_size=60)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Deck cannot contain LEADER cards" in str(exc)


def test_phase6_parse_deckplanet_deck_text_sections() -> None:
    raw = "\n".join(
        [
            "_____Leader_____",
            "Leader One [BT1-001]",
            "_____Main Deck_____",
            "4 Card A [BT9-001]",
            "2 Card B [BT9-002]",
            "_____Z Deck_____",
            "3 Z Card [BT9-003]",
            "_____Side Deck_____",
            "1 Side Card [BT9-004]",
        ]
    )
    parsed = parse_deckplanet_deck_text(raw)
    entries = parsed["entries"]
    assert len(entries) == 5
    assert entries[0]["section"] == "leader"
    assert entries[1]["section"] == "main"
    assert entries[3]["section"] == "z"
    assert entries[4]["section"] == "side"


def test_phase6_import_deckplanet_deck_text_resolves_leader_and_main_deck(tmp_path) -> None:
    db = tmp_path / "cards.db"
    _build_test_db(db)
    raw = "\n".join(
        [
            "_____Leader_____",
            "Leader One [BT1-001]",
            "_____Main Deck_____",
            "4 Card A [BT9-001]",
            "2 Card B [BT9-002]",
            "_____Z Deck_____",
            "3 Z Card [BT9-003]",
        ]
    )
    payload = import_deckplanet_deck_text(db_path=db, raw=raw)
    assert payload["leader_id"] == 1
    assert payload["deck_ids"] == [1000, 1000, 1000, 1000, 1001, 1001]
    assert payload["z_deck_ids"] == [1002, 1002, 1002]
    assert payload["unresolved_card_numbers"] == []
