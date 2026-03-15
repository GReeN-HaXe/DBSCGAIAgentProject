from __future__ import annotations

import re
from typing import Iterable

from src.db.interfaces import CardRepository
from src.domain.models import CardData


_WS_RE = re.compile(r"\s+")
_COUNTER_HIDDEN_COST_RE = re.compile(
    r"\[counter:\s*(?:attack|play|counter|battle card attack)\].{0,260}?choose 1 of your (.+?) battle cards? and switch it to hidden mode:"
)
_ACTIVATE_MAIN_HIDDEN_COST_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?choose 1 of your (.+?) battle cards? and switch it to hidden mode:"
)
_ACTIVATE_BATTLE_HIDDEN_COST_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,260}?choose 1 (?:(?:of your )?(.+?) battle cards?|(.+?) card in your battle area) and switch (?:it|them) to hidden mode:"
)
_ACTIVATE_MAIN_HIDDEN_BATTLE_OR_ENERGY_COST_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?choose 1 (.+?) card in your battle area or energy and switch it to hidden mode:"
)
_ACTIVATE_BATTLE_DROP_HIDDEN_MODE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,260}?choose 1 hidden mode card in your battle area and place it into (?:its|that card's) owner'?s drop:"
)
_COUNTER_ALT_REST_HIDDEN_BATTLE_RE = re.compile(
    r"activate this card's \[counter\] skill from your hand by switching 1 hidden mode card in your battle area to rest mode instead of paying its energy cost"
)
_COUNTER_ALT_LIFE_TO_HAND_RE = re.compile(
    r"\[permanent\](?:\s*\[sparking\s+(\d+)\])?.{0,220}?activate this card's \[counter\] skill from your hand by adding 1 card from your life to your hand instead of paying its energy cost"
)


def _normalize_text(raw: str | None) -> str:
    text = (raw or "").lower()
    text = text.replace("<br>", ". ").replace("[br]", ". ").replace("—", " - ").replace("―", " - ")
    return _WS_RE.sub(" ", text.strip())


def _extract_allowed_colors(descriptor: str) -> str:
    colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black|white)\b", descriptor.lower())))
    return ",".join(colors)


def _extract_required_leader_colors(text: str) -> str:
    matches = re.findall(r"if your leader(?: card)? is (?:a |an )?(red|blue|green|yellow|black|white)", text.lower())
    colors = sorted(set(matches))
    return ",".join(colors)


def extract_skill_cost_rules_from_card(card: CardData) -> dict[str, list[dict[str, int | str | bool]]]:
    text = _normalize_text(card.card_skill_unstyled)
    if not text:
        return {}
    rules: dict[str, list[dict[str, int | str | bool]]] = {}

    m_counter_hidden = _COUNTER_HIDDEN_COST_RE.search(text)
    if m_counter_hidden:
        descriptor = m_counter_hidden.group(1).strip()
        params: dict[str, int | str | bool] = {"kind": "switch_owner_battle_to_hidden", "amount": 1}
        allowed_colors = _extract_allowed_colors(descriptor)
        if allowed_colors:
            params["allowed_colors"] = allowed_colors
        rules["counter_from_hand"] = [params]

    m_activate_hidden = _ACTIVATE_MAIN_HIDDEN_COST_RE.search(text)
    if m_activate_hidden:
        descriptor = m_activate_hidden.group(1).strip()
        params = {"kind": "switch_owner_battle_to_hidden", "amount": 1}
        allowed_colors = _extract_allowed_colors(descriptor)
        if allowed_colors:
            params["allowed_colors"] = allowed_colors
        rules["activate_main"] = [params]

    m_activate_battle_hidden = _ACTIVATE_BATTLE_HIDDEN_COST_RE.search(text)
    if m_activate_battle_hidden:
        descriptor = str(m_activate_battle_hidden.group(1) or m_activate_battle_hidden.group(2) or "").strip()
        params = {"kind": "switch_owner_battle_to_hidden", "amount": 1}
        allowed_colors = _extract_allowed_colors(descriptor)
        if allowed_colors:
            params["allowed_colors"] = allowed_colors
        rules["activate_battle"] = [params]

    m_activate_hidden_battle_or_energy = _ACTIVATE_MAIN_HIDDEN_BATTLE_OR_ENERGY_COST_RE.search(text)
    if m_activate_hidden_battle_or_energy:
        descriptor = m_activate_hidden_battle_or_energy.group(1).strip()
        params = {"kind": "switch_owner_battle_or_energy_to_hidden", "amount": 1}
        allowed_colors = _extract_allowed_colors(descriptor)
        if allowed_colors:
            params["allowed_colors"] = allowed_colors
        rules["activate_main"] = [params]

    m_activate_battle_drop_hidden = _ACTIVATE_BATTLE_DROP_HIDDEN_MODE_RE.search(text)
    if m_activate_battle_drop_hidden:
        rules["activate_battle"] = [
            {
                "kind": "send_owner_hidden_mode_battle_to_drop",
                "amount": 1,
            }
        ]

    if _COUNTER_ALT_REST_HIDDEN_BATTLE_RE.search(text):
        params = {
            "kind": "rest_owner_hidden_mode_battle",
            "amount": 1,
        }
        required_leader_colors = _extract_required_leader_colors(text)
        if required_leader_colors:
            params["required_leader_colors"] = required_leader_colors
        rules["counter_alternate_from_hand"] = [params]

    m_counter_alt_life = _COUNTER_ALT_LIFE_TO_HAND_RE.search(text)
    if m_counter_alt_life:
        params = {
            "kind": "add_life_to_hand",
            "amount": 1,
        }
        sparking = m_counter_alt_life.group(1)
        if sparking:
            params["requires_sparking"] = int(sparking)
        rules["counter_alternate_from_hand"] = [params]

    return rules


def build_skill_cost_rules_for_cards(
    repo: CardRepository,
    card_ids: Iterable[int],
) -> dict[int, dict[str, list[dict[str, int | str | bool]]]]:
    mapped: dict[int, dict[str, list[dict[str, int | str | bool]]]] = {}
    for card in repo.list_by_ids(card_ids, source_table="cards"):
        rules = extract_skill_cost_rules_from_card(card)
        if rules:
            mapped[card.id] = rules
    return mapped
