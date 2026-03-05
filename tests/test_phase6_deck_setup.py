from __future__ import annotations

import sqlite3

from src.agent.deck_setup import (
    load_sample_game_setup_from_db,
    parse_card_id_text,
    validate_leader_and_deck,
)


def _build_test_db(path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, card_type TEXT)")
        conn.execute("INSERT INTO cards (id, card_type) VALUES (1, 'LEADER')")
        conn.execute("INSERT INTO cards (id, card_type) VALUES (2, 'LEADER')")
        for i in range(1000, 1120):
            conn.execute("INSERT INTO cards (id, card_type) VALUES (?, 'BATTLE')", (i,))
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
