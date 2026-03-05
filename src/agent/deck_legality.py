from __future__ import annotations

from collections import Counter
from typing import Any


def validate_deck_legality(
    *,
    repo: Any,
    leader_id: int,
    deck_ids: list[int],
    expected_deck_size: int = 60,
    max_copies_per_card_number: int = 4,
    enforce_banlist: bool = True,
) -> None:
    if expected_deck_size > 0 and len(deck_ids) != expected_deck_size:
        raise ValueError(f"Deck must contain exactly {expected_deck_size} cards; got {len(deck_ids)}.")

    leader = repo.get_by_id(int(leader_id), source_table="cards")
    leader_type = str(getattr(leader, "card_type", "") or "").upper()
    if leader_type != "LEADER":
        raise ValueError(f"Leader id {leader_id} is not a LEADER (found {leader_type or 'UNKNOWN'}).")

    count_by_id = Counter(int(x) for x in deck_ids)
    data_by_id: dict[int, Any] = {}
    for card_id in count_by_id.keys():
        data_by_id[card_id] = repo.get_by_id(card_id, source_table="cards")

    for card_id, card in data_by_id.items():
        ctype = str(getattr(card, "card_type", "") or "").upper()
        if ctype == "LEADER":
            raise ValueError(f"Deck cannot contain LEADER cards: [{card_id}]")

    count_by_number: Counter[str] = Counter()
    for card_id, amount in count_by_id.items():
        card = data_by_id[card_id]
        number = str(getattr(card, "card_number", "") or str(card_id))
        count_by_number[number] += int(amount)

    over_copy = [(num, cnt) for num, cnt in count_by_number.items() if cnt > int(max_copies_per_card_number)]
    if over_copy:
        num, cnt = over_copy[0]
        raise ValueError(f"Deck exceeds copy limit for card_number {num}: {cnt} > {max_copies_per_card_number}")

    if not enforce_banlist:
        return

    for card_id, amount in count_by_id.items():
        card = data_by_id[card_id]
        if bool(getattr(card, "is_banned", False)):
            raise ValueError(f"Deck contains banned card id: {card_id}")
        if bool(getattr(card, "is_limited", False)):
            limited_to_raw = getattr(card, "limited_to", None)
            try:
                allowed = int(limited_to_raw) if limited_to_raw is not None else 1
            except (TypeError, ValueError):
                allowed = 1
            if int(amount) > int(allowed):
                raise ValueError(f"Deck exceeds limited card id {card_id}: {amount} > {allowed}")
