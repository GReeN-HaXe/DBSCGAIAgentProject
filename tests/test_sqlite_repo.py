from __future__ import annotations

import sqlite3

import pytest

from src.db import CardNotFoundError, CardQuery


def _first_value(conn: sqlite3.Connection, sql: str):
    row = conn.execute(sql).fetchone()
    return None if row is None else row[0]


def test_get_by_id_returns_card(repo, conn: sqlite3.Connection) -> None:
    card_id = _first_value(conn, "SELECT id FROM cards ORDER BY id LIMIT 1")
    assert card_id is not None

    card = repo.get_by_id(card_id)

    assert card.id == card_id
    assert card.card_number
    assert card.card_name
    assert card.source_table == "cards"


def test_get_by_id_unknown_raises(repo) -> None:
    with pytest.raises(CardNotFoundError):
        repo.get_by_id(-1)


def test_get_by_number_from_cards_only(repo, conn: sqlite3.Connection) -> None:
    card_number = _first_value(conn, "SELECT card_number FROM cards ORDER BY id LIMIT 1")
    assert card_number is not None

    cards = repo.get_by_number(card_number, include_variants=False)

    assert cards
    assert all(card.card_number == card_number for card in cards)
    assert all(card.source_table == "cards" for card in cards)


def test_list_by_ids_returns_expected_ids(repo, conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT id FROM cards ORDER BY id LIMIT 3").fetchall()
    ids = [row[0] for row in rows]
    assert ids

    cards = repo.list_by_ids(ids)

    assert [card.id for card in cards] == sorted(ids)
    assert all(card.source_table == "cards" for card in cards)


def test_search_name_contains_case_insensitive(repo, conn: sqlite3.Connection) -> None:
    card_name = _first_value(conn, "SELECT card_name FROM cards WHERE card_name IS NOT NULL LIMIT 1")
    assert card_name is not None

    token = next((part for part in card_name.split() if len(part) >= 3), None)
    if token is None:
        pytest.skip("Could not derive a search token from card_name.")

    query = CardQuery(name_contains=token.lower(), include_variants=False, limit=25)
    results = repo.search(query)

    assert results
    assert any(token.lower() in card.card_name.lower() for card in results)


def test_search_excludes_banned_by_default(repo, conn: sqlite3.Connection) -> None:
    banned_number = _first_value(
        conn,
        "SELECT card_number FROM cards WHERE COALESCE(is_banned, 0) = 1 LIMIT 1",
    )
    if banned_number is None:
        pytest.skip("No banned cards found in dataset.")

    default_results = repo.search(
        CardQuery(card_number=banned_number, include_variants=False, include_banned=False, limit=10)
    )
    included_results = repo.search(
        CardQuery(card_number=banned_number, include_variants=False, include_banned=True, limit=10)
    )

    assert default_results == []
    assert included_results
    assert any(card.is_banned for card in included_results)


def test_variant_includes_base_id_when_available(repo, conn: sqlite3.Connection) -> None:
    variant_id = _first_value(conn, "SELECT id FROM variants ORDER BY id LIMIT 1")
    if variant_id is None:
        pytest.skip("No variants found in dataset.")

    variant = repo.get_by_id(variant_id, source_table="variants")

    assert variant.source_table == "variants"
    assert variant.base_id is not None
