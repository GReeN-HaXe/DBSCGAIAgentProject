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
_PLAIN_MARKER_ACTIVATE_RE = re.compile(
    r"\[\s*([+-]\d+)\s*\]\s*\[activate(?::)?\s*(main|battle|main/battle)\]"
)
_ACTIVATE_MAIN_Z_ENERGY_TO_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,220}?place (\d+) of your z-energy into (?:its|their) owner'?s drop\s*:"
)
_ACTIVATE_MAIN_HAND_TO_WARP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,220}?send (\d+) card from your hand to (?:its|their) owner'?s warp\s*:"
)
_COUNTER_ALT_REST_HIDDEN_BATTLE_RE = re.compile(
    r"activate this card's \[counter\] skill from your hand by switching 1 hidden mode card in your battle area to rest mode instead of paying its energy cost"
)
_COUNTER_ALT_LIFE_TO_HAND_RE = re.compile(
    r"\[(?:permanent|permament)\](?:\s*\[sparking\s+(\d+)\])?.{0,220}?activate this card's \[counter\] skill from your hand by adding (?:1|a) card from (?:your|our) life (?:to|o) your hand(?: .{0,180}?)? instead of paying its energy cost"
)
_COUNTER_ALT_DROP_TO_WARP_ONLY_RE = re.compile(
    r"\[(?:permanent|permament)\].{0,220}?activate this card's \[counter\] skill from your hand by sending (\d+) (.+?) cards? from your drop to (?:its|their) owner'?s warp instead of paying its energy cost"
)
_COUNTER_ALT_ALL_DROP_TO_WARP_RE = re.compile(
    r"\[(?:permanent|permament)\].{0,220}?activate this card's \[counter\] skill from your hand by sending all the cards in your drop to (?:its|their) owner'?s warp instead of paying its energy cost"
)
_COUNTER_ALT_RETURN_BATTLE_TO_HAND_RE = re.compile(
    r"\[(?:permanent|permament)\].{0,220}?activate this card's \[counter\] skill from your hand by returning 1 (.+?) from your battle area to your hand instead of paying its energy cost"
)
_COUNTER_ALT_REST_LEADER_RE = re.compile(
    r"\[(?:permanent|permament)\].{0,220}?activate this card's \[counter\] skill from your hand by switching your (.+?) leader to rest mode instead of paying its energy cost"
)
_COUNTER_ALT_REDUCED_ENERGY_RE = re.compile(
    r"\[(?:permanent|permament)\].{0,220}?activate this card's \[counter\] skill from your hand by paying \((\d+)\) instead of (?:its|this card's) energy cost"
)
_COUNTER_ALT_HIDDEN_TO_DROP_RE = re.compile(
    r"\[(?:permanent|permament)\].{0,220}?activate this card's \[counter\] skill from your hand by choosing 1 hidden mode card in your battle area and placing it into (?:its|their) owner'?s drop instead of paying its energy cost"
)
_COUNTER_ALT_REDUCE_OWNER_BATTLE_POWER_RE = re.compile(
    r"\[(?:permanent|permament)\].{0,220}?activate this card's \[counter\] skill from your hand by choosing (\d+) of your (.+?) battle cards? and reducing their power by (-?\d+) for the turn instead of paying its energy cost"
)


def _normalize_text(raw: str | None) -> str:
    text = (raw or "").lower()
    text = text.replace("<br>", ". ").replace("[br]", ". ").replace("—", " - ").replace("―", " - ")
    return _WS_RE.sub(" ", text.strip())


def _extract_allowed_colors(descriptor: str) -> str:
    colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black|white)\b", descriptor.lower())))
    return ",".join(colors)


def _extract_required_leader_colors(text: str) -> str:
    matches = re.findall(r"if your leader(?: card)? is (?:a |an )?(?:mono-)?(red|blue|green|yellow|black|white)", text.lower())
    colors = sorted(set(matches))
    return ",".join(colors)


def _extract_required_leader_traits(text: str) -> str:
    match = re.search(
        r"if your leader(?: card)? is (?:a |an )?(?:(?:mono-)?(?:red|blue|green|yellow|black|white))(?:\s+([^.:,\[]+?))?\s+card",
        text.lower(),
    )
    if match is None:
        fallback = re.search(r"if your leader(?: card)? is (?:a |an )?([^.:,\[]+?)\s+card", text.lower())
        if fallback is None:
            return ""
        raw = str(fallback.group(1) or "")
    else:
        raw = str(match.group(1) or "")
    cleaned = raw.replace("<", " ").replace(">", " ").replace("≪", " ").replace("≫", " ").replace("?", " ")
    cleaned = re.sub(r"\b(red|blue|green|yellow|black|white|mono-black|mono-red|mono-blue|mono-green|mono-yellow|mono-white)\b", " ", cleaned)
    cleaned = re.sub(r"[^0-9a-z ,/.-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    if not cleaned:
        return ""
    parts = [part.strip() for part in re.split(r"\bor\b|/|,", cleaned) if part.strip()]
    return ",".join(parts)


def _extract_life_at_most_requirement(text: str) -> int | None:
    match = re.search(r"your life is at (\d+) or less", text.lower())
    if match is None:
        return None
    return int(match.group(1))


def _extract_energy_colors_at_least_requirement(text: str) -> int | None:
    match = re.search(r"there are (\d+) or more colors in your energy", text.lower())
    if match is None:
        return None
    return int(match.group(1))


def _extract_requires_multicolor_in_energy(text: str) -> bool:
    return "if you have a multicolor card in your energy" in text.lower()


def _extract_requires_only_energy_colors(text: str) -> str:
    matches = re.findall(r"if you have only (red|blue|green|yellow|black|white) cards in your energy", text.lower())
    colors = sorted(set(matches))
    return ",".join(colors)


def _extract_requires_all_energy_rested(text: str) -> bool:
    return "all of your energy is in rest mode" in text.lower()


def _extract_wrapper_values(descriptor: str, *, open_char: str, close_char: str) -> str:
    pattern = re.escape(open_char) + r"\s*([^" + re.escape(close_char) + r"]+?)\s*" + re.escape(close_char)
    values = sorted(set(match.strip().lower() for match in re.findall(pattern, descriptor) if match.strip()))
    return ",".join(values)


def _extract_owner_in_play_requirement(text: str) -> dict[str, int | str | bool]:
    match = re.search(r"if you have (?:a |an )?([^.]+?) in play", text.lower())
    return _extract_owner_presence_requirement(match.group(1).strip(), scope="in_play") if match is not None else {}


def _extract_owner_battle_area_requirement(text: str) -> dict[str, int | str | bool]:
    match = re.search(r"if you have (?:a |an )?([^.]+?) in your battle area", text.lower())
    return _extract_owner_presence_requirement(match.group(1).strip(), scope="battle_area") if match is not None else {}


def _extract_owner_presence_requirement(descriptor: str, *, scope: str) -> dict[str, int | str | bool]:
    prefix = "owner_in_play" if scope == "in_play" else "owner_battle_area"
    params: dict[str, int | str | bool] = {
        "requires_owner_in_play" if scope == "in_play" else "requires_owner_battle_area": True
    }
    allowed_colors = _extract_allowed_colors(descriptor)
    if allowed_colors:
        params[f"{prefix}_allowed_colors"] = allowed_colors
    required_traits = _extract_wrapper_values(descriptor, open_char="≪", close_char="≫")
    if required_traits:
        params[f"{prefix}_required_traits"] = required_traits
    required_characters = _extract_wrapper_values(descriptor, open_char="<", close_char=">")
    if required_characters:
        params[f"{prefix}_required_characters"] = required_characters
    if "extra" in descriptor:
        params[f"{prefix}_required_card_types"] = "EXTRA"
    elif "battle" in descriptor:
        params[f"{prefix}_required_card_types"] = "BATTLE"
    elif "unison" in descriptor:
        params[f"{prefix}_required_card_types"] = "UNISON"
    if "multicolor" in descriptor:
        params[f"{prefix}_requires_multicolor"] = True
    energy_cost_match = re.search(r"energy cost of (\d+) or more", descriptor)
    if energy_cost_match is not None:
        params[f"{prefix}_min_energy_cost"] = int(energy_cost_match.group(1))
    return params


def _extract_owner_drop_to_warp_cost(text: str) -> dict[str, int | str | bool]:
    match = re.search(r"and sending (\d+) (.+?) cards? from your drop to their owner'?s warp instead of paying its energy cost", text.lower())
    if match is None:
        return {}
    descriptor = match.group(2).strip()
    params: dict[str, int | str | bool] = {
        "kind": "send_owner_drop_to_warp",
        "amount": int(match.group(1)),
    }
    allowed_colors = _extract_allowed_colors(descriptor)
    if allowed_colors:
        params["allowed_colors"] = allowed_colors
    required_traits = _extract_wrapper_values(descriptor, open_char="≪", close_char="≫")
    if required_traits:
        params["required_traits"] = required_traits
    required_characters = _extract_wrapper_values(descriptor, open_char="<", close_char=">")
    if required_characters:
        params["required_characters"] = required_characters
    if "battle" in descriptor:
        params["required_card_types"] = "BATTLE"
    elif "extra" in descriptor:
        params["required_card_types"] = "EXTRA"
    elif "unison" in descriptor:
        params["required_card_types"] = "UNISON"
    return params


def _extract_face_up_z_deck_requirement(text: str) -> dict[str, int | str | bool]:
    match = re.search(r"if you have (\d+) or more face-up (.+?) cards? in your z-deck", text.lower())
    if match is None:
        return {}
    descriptor = match.group(2).strip()
    params: dict[str, int | str | bool] = {
        "requires_owner_face_up_z_deck_count_at_least": int(match.group(1)),
    }
    allowed_colors = _extract_allowed_colors(descriptor)
    if allowed_colors:
        params["owner_face_up_z_deck_allowed_colors"] = allowed_colors
    required_traits = _extract_wrapper_values(descriptor, open_char="≪", close_char="≫")
    if required_traits:
        params["owner_face_up_z_deck_required_traits"] = required_traits
    required_characters = _extract_wrapper_values(descriptor, open_char="<", close_char=">")
    if required_characters:
        params["owner_face_up_z_deck_required_characters"] = required_characters
    if "battle" in descriptor:
        params["owner_face_up_z_deck_required_card_types"] = "BATTLE"
    elif "extra" in descriptor:
        params["owner_face_up_z_deck_required_card_types"] = "EXTRA"
    elif "unison" in descriptor:
        params["owner_face_up_z_deck_required_card_types"] = "UNISON"
    return params


def _extract_requires_z_energy_at_least(text: str) -> int | None:
    match = re.search(r"you have (\d+) or more z-energy", text.lower())
    if match is None:
        return None
    return int(match.group(1))


def _extract_requires_opponent_energy_at_least(text: str) -> int | None:
    match = re.search(r"your opponent has (\d+) or more energy", text.lower())
    if match is None:
        return None
    return int(match.group(1))


def _extract_required_name_tokens(descriptor: str) -> str:
    brace_values = _extract_wrapper_values(descriptor, open_char="{", close_char="}")
    if brace_values:
        return brace_values
    return ""


def _extract_filtered_cost_step(kind: str, descriptor: str, amount: int) -> dict[str, int | str | bool]:
    params: dict[str, int | str | bool] = {
        "kind": kind,
        "amount": amount,
    }
    allowed_colors = _extract_allowed_colors(descriptor)
    if allowed_colors:
        params["allowed_colors"] = allowed_colors
    required_traits = _extract_wrapper_values(descriptor, open_char="≪", close_char="≫")
    if required_traits:
        params["required_traits"] = required_traits
    required_characters = _extract_wrapper_values(descriptor, open_char="<", close_char=">")
    if required_characters:
        params["required_characters"] = required_characters
    required_name_contains = _extract_required_name_tokens(descriptor)
    if required_name_contains:
        params["required_name_contains"] = required_name_contains
    if "battle" in descriptor:
        params["required_card_types"] = "BATTLE"
    elif "extra" in descriptor:
        params["required_card_types"] = "EXTRA"
    elif "unison" in descriptor:
        params["required_card_types"] = "UNISON"
    if "multicolor" in descriptor:
        params["requires_multicolor"] = True
    energy_cost_match = re.search(r"energy cost of (\d+) or more", descriptor)
    if energy_cost_match is not None:
        params["min_energy_cost"] = int(energy_cost_match.group(1))
    return params


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

    for m_plain_marker_activate in _PLAIN_MARKER_ACTIVATE_RE.finditer(text):
        delta = int(m_plain_marker_activate.group(1))
        mode = str(m_plain_marker_activate.group(2) or "").strip().lower()
        step = {
            "kind": "add_markers" if delta > 0 else "remove_markers",
            "amount": abs(delta),
        }
        contexts = (
            ["activate_main_unison", "activate_battle_unison"]
            if mode == "main/battle"
            else [f"activate_{mode}_unison"]
        )
        for context in contexts:
            rules[context] = [step]

    m_activate_main_z_energy_to_drop = _ACTIVATE_MAIN_Z_ENERGY_TO_DROP_RE.search(text)
    if m_activate_main_z_energy_to_drop:
        rules["activate_main_warp"] = [
            {
                "kind": "send_owner_z_energy_to_drop",
                "amount": int(m_activate_main_z_energy_to_drop.group(1)),
            }
        ]

    m_activate_main_hand_to_warp = _ACTIVATE_MAIN_HAND_TO_WARP_RE.search(text)
    if m_activate_main_hand_to_warp:
        rules["activate_main_unison"] = [
            {
                "kind": "send_owner_hand_to_warp",
                "amount": int(m_activate_main_hand_to_warp.group(1)),
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
        params: dict[str, int | str | bool] = {
            "kind": "add_life_to_hand",
            "amount": 1,
        }
        required_leader_colors = _extract_required_leader_colors(text)
        if required_leader_colors:
            params["required_leader_colors"] = required_leader_colors
        required_leader_traits = _extract_required_leader_traits(text)
        if required_leader_traits:
            params["required_leader_traits"] = required_leader_traits
        life_at_most = _extract_life_at_most_requirement(text)
        if life_at_most is not None:
            params["requires_life_at_most"] = life_at_most
        energy_colors_at_least = _extract_energy_colors_at_least_requirement(text)
        if energy_colors_at_least is not None:
            params["requires_energy_colors_at_least"] = energy_colors_at_least
        if _extract_requires_multicolor_in_energy(text):
            params["requires_multicolor_in_energy"] = True
        only_energy_colors = _extract_requires_only_energy_colors(text)
        if only_energy_colors:
            params["requires_only_energy_colors"] = only_energy_colors
        if _extract_requires_all_energy_rested(text):
            params["requires_all_energy_rested"] = True
        params.update(_extract_owner_in_play_requirement(text))
        params.update(_extract_owner_battle_area_requirement(text))
        params.update(_extract_face_up_z_deck_requirement(text))
        sparking = m_counter_alt_life.group(1)
        if sparking:
            params["requires_sparking"] = int(sparking)
        steps: list[dict[str, int | str | bool]] = [params]
        drop_to_warp_cost = _extract_owner_drop_to_warp_cost(text)
        if drop_to_warp_cost:
            steps.append(drop_to_warp_cost)
        rules["counter_alternate_from_hand"] = steps

    m_counter_alt_drop_to_warp_only = _COUNTER_ALT_DROP_TO_WARP_ONLY_RE.search(text)
    if m_counter_alt_drop_to_warp_only and "counter_alternate_from_hand" not in rules:
        descriptor = m_counter_alt_drop_to_warp_only.group(2).strip()
        params = _extract_filtered_cost_step("send_owner_drop_to_warp", descriptor, int(m_counter_alt_drop_to_warp_only.group(1)))
        required_leader_colors = _extract_required_leader_colors(text)
        if required_leader_colors:
            params["required_leader_colors"] = required_leader_colors
        required_leader_traits = _extract_required_leader_traits(text)
        if required_leader_traits:
            params["required_leader_traits"] = required_leader_traits
        life_at_most = _extract_life_at_most_requirement(text)
        if life_at_most is not None:
            params["requires_life_at_most"] = life_at_most
        requires_z_energy_at_least = _extract_requires_z_energy_at_least(text)
        if requires_z_energy_at_least is not None:
            params["requires_z_energy_at_least"] = requires_z_energy_at_least
        rules["counter_alternate_from_hand"] = [params]

    if _COUNTER_ALT_ALL_DROP_TO_WARP_RE.search(text):
        params = {
            "kind": "send_all_owner_drop_to_warp",
            "amount": 1,
        }
        required_leader_colors = _extract_required_leader_colors(text)
        if required_leader_colors:
            params["required_leader_colors"] = required_leader_colors
        required_leader_traits = _extract_required_leader_traits(text)
        if required_leader_traits:
            params["required_leader_traits"] = required_leader_traits
        life_at_most = _extract_life_at_most_requirement(text)
        if life_at_most is not None:
            params["requires_life_at_most"] = life_at_most
        rules["counter_alternate_from_hand"] = [params]

    m_counter_alt_return_battle = _COUNTER_ALT_RETURN_BATTLE_TO_HAND_RE.search(text)
    if m_counter_alt_return_battle:
        descriptor = m_counter_alt_return_battle.group(1).strip()
        params = _extract_filtered_cost_step("return_owner_battle_to_hand", descriptor, 1)
        required_leader_colors = _extract_required_leader_colors(text)
        if required_leader_colors:
            params["required_leader_colors"] = required_leader_colors
        required_leader_traits = _extract_required_leader_traits(text)
        if required_leader_traits:
            params["required_leader_traits"] = required_leader_traits
        rules["counter_alternate_from_hand"] = [params]

    m_counter_alt_rest_leader = _COUNTER_ALT_REST_LEADER_RE.search(text)
    if m_counter_alt_rest_leader:
        descriptor = m_counter_alt_rest_leader.group(1).strip()
        params = {
            "kind": "rest_owner_leader",
            "amount": 1,
        }
        required_leader_colors = _extract_required_leader_colors(text)
        if required_leader_colors:
            params["required_leader_colors"] = required_leader_colors
        required_leader_traits = _extract_filtered_cost_step("noop", descriptor, 1).get("required_traits")
        if required_leader_traits:
            params["required_leader_traits"] = str(required_leader_traits)
        required_leader_characters = _extract_filtered_cost_step("noop", descriptor, 1).get("required_characters")
        if required_leader_characters:
            existing = str(params.get("required_leader_traits", "")).strip()
            params["required_leader_traits"] = ",".join(part for part in [existing, str(required_leader_characters)] if part)
        rules["counter_alternate_from_hand"] = [params]

    m_counter_alt_reduced_energy = _COUNTER_ALT_REDUCED_ENERGY_RE.search(text)
    if m_counter_alt_reduced_energy:
        params = {
            "kind": "rest_energy",
            "amount": int(m_counter_alt_reduced_energy.group(1)),
        }
        required_leader_colors = _extract_required_leader_colors(text)
        if required_leader_colors:
            params["required_leader_colors"] = required_leader_colors
        required_leader_traits = _extract_required_leader_traits(text)
        if required_leader_traits:
            params["required_leader_traits"] = required_leader_traits
        requires_z_energy_at_least = _extract_requires_z_energy_at_least(text)
        if requires_z_energy_at_least is not None:
            params["requires_z_energy_at_least"] = requires_z_energy_at_least
        rules["counter_alternate_from_hand"] = [params]

    if _COUNTER_ALT_HIDDEN_TO_DROP_RE.search(text):
        params = {
            "kind": "send_owner_hidden_mode_battle_to_drop",
            "amount": 1,
        }
        required_leader_colors = _extract_required_leader_colors(text)
        if required_leader_colors:
            params["required_leader_colors"] = required_leader_colors
        required_leader_traits = _extract_required_leader_traits(text)
        if required_leader_traits:
            params["required_leader_traits"] = required_leader_traits
        requires_opponent_energy_at_least = _extract_requires_opponent_energy_at_least(text)
        if requires_opponent_energy_at_least is not None:
            params["requires_opponent_energy_at_least"] = requires_opponent_energy_at_least
        rules["counter_alternate_from_hand"] = [params]

    m_counter_alt_reduce_owner_battle_power = _COUNTER_ALT_REDUCE_OWNER_BATTLE_POWER_RE.search(text)
    if m_counter_alt_reduce_owner_battle_power:
        descriptor = m_counter_alt_reduce_owner_battle_power.group(2).strip()
        params = _extract_filtered_cost_step(
            "reduce_owner_battle_power_for_turn",
            descriptor,
            int(m_counter_alt_reduce_owner_battle_power.group(1)),
        )
        params["required_card_types"] = "BATTLE"
        params["power_delta"] = int(m_counter_alt_reduce_owner_battle_power.group(3))
        required_leader_colors = _extract_required_leader_colors(text)
        if required_leader_colors:
            params["required_leader_colors"] = required_leader_colors
        required_leader_traits = _extract_required_leader_traits(text)
        if required_leader_traits:
            params["required_leader_traits"] = required_leader_traits
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
