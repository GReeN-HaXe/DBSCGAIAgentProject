from __future__ import annotations

import html
import re
from typing import Iterable

from src.db.interfaces import CardRepository
from src.domain.models import CardData


_WS_RE = re.compile(r"\s+")
_CIRCLED_NUMERIC_COSTS = {
    "①": 1,
    "②": 2,
    "③": 3,
    "④": 4,
    "⑤": 5,
    "⑥": 6,
    "⑦": 7,
    "⑧": 8,
    "⑨": 9,
    "⑩": 10,
}
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
_ACTIVATE_BATTLE_SELF_FROM_COMBO_TO_DROP_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,220}?place this card in its owner'?s drop area from your combo area\s*:"
)
_ACTIVATE_BATTLE_SELF_FROM_LEADER_UNDER_TO_WARP_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,260}?send this card from under your (?:<[^>]+>\s+)?z-leader to (?:its|their) owner'?s warp\s*:",
    re.IGNORECASE,
)
_PLAIN_MARKER_ACTIVATE_RE = re.compile(
    r"\[\s*(?:unison\s+)?([+-]\d+)\s*\]\s*\[activate(?::)?\s*(main|battle|main/battle)\]"
)
_ACTIVATE_MAIN_Z_ENERGY_TO_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,220}?place (\d+) of your z-energy into (?:its|their) owner'?s drop\s*:"
)
_ACTIVATE_MAIN_BATTLE_Z_ENERGY_TO_DROP_AND_REMOVE_SELF_RE = re.compile(
    r"\[activate(?::)?\s*(main|battle)\].{0,340}?(?:you\s+)?place (\d+) of your z-energy (?:into|in) (?:(?:its|their) owner'?s drop|your drop(?: area)?)\s*,?\s*(?:then|and)?\s*(?:you\s+)?remove this card from the game\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_ENERGY_TO_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,220}?place (\d+) of your energy into (?:its|their) owner'?s drop(?:[^:]{0,120})?\s*:"
)
_ACTIVATE_MAIN_LIFE_TO_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?add (\d+) card(?:s)? from your life to your hand\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_REST_SELF_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?switch this card to rest mode\s*:",
    re.IGNORECASE,
)
_ACTIVATE_BATTLE_ENERGY_TO_DROP_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,220}?place (\d+) of your energy into (?:its|their) owner'?s drop\s*:"
)
_ACTIVATE_BATTLE_DISCARD_HAND_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,220}?discard (\d+) card(?:s)? from your hand\s*:",
    re.IGNORECASE,
)
_ACTIVATE_BATTLE_Z_ENERGY_UNDER_SELF_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,280}?place (\d+) (.+?) card from your z-energy under this card\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_BATTLE_ENERGY_TO_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main/battle\].{0,220}?place (\d+) of your energy into (?:its|their) owner'?s drop\s*:"
)
_ACTIVATE_MAIN_BATTLE_DROP_TO_BOTTOM_DECK_RE = re.compile(
    r"\[activate(?::)?\s*main/battle\].{0,320}?place (\d+) (.+?) from your drop at the bottom of (?:its|their) owner'?s deck\s*:"
)
_ACTIVATE_MAIN_OTHER_BATTLE_TO_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?choose (\d+) of your (.+?) cards? and place it in its owner'?s drop area\s*:"
)
_ACTIVATE_MAIN_HAND_TO_WARP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,220}?send (\d+) card from your hand to (?:its|their) owner'?s warp\s*:"
)
_ACTIVATE_MAIN_SEND_SELF_FROM_HAND_TO_WARP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?send this card from your hand to (?:(?:your|the) warp|(?:its|their )?owner'?s warp)\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_HAND_TO_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?place (\d+) card(?:s)? from your hand in (?:the )?drop area\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_HAND_TO_BOTTOM_DECK_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?place (\d+) card(?:s)? from your hand at the bottom of your deck(?: in any order)?\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_DISCARD_SELF_FROM_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\](?:(?!<br>|\[(?:auto|activate|counter|permanent|blocker|barrier)\b).){0,220}?discard this card from your hand\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_DISCARD_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\](?:(?!<br>|\[(?:auto|activate|counter|permanent|blocker|barrier)\b).){0,220}?discard (\d+) card(?:s)? from your hand\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_DIRECT_DISCARD_HAND_TO_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?choose (\d+) (.+?) cards? in your hand and discard (?:it|them)\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLACE_SELF_IN_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main\](?:(?!<br>|\[(?:auto|activate|counter|permanent|blocker|barrier)\b).){0,260}?place this card in (?:your drop|it'?s owner'?s drop area|its owner'?s drop area)\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_REMOVE_OPPONENT_BATTLE_TO_REMOVED_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?(?:remove (\d+) of your opponent'?s (.+?) from the game|choose (\d+) of your opponent'?s (.+?) and remove (?:it|them) from the game|choose (\d+) (.+?) (?:in|from) your opponent'?s battle area and remove (?:it|them) from the game)\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_REMOVE_OWNER_BATTLE_TO_REMOVED_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?(?:remove (\d+) of your (.+?) from the game|choose (\d+) of your (.+?) and remove (?:it|them) from the game|choose (\d+) (.+?) (?:in|from) your battle area and remove (?:it|them) from the game)\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_BATTLE_OWNER_BATTLE_TO_WARP_RE = re.compile(
    r"\[activate(?::)?\s*(main|battle|main/battle)\].{0,360}?choose 1 of your (.+?) battle cards? with an energy cost of (\d+)\s+and send it to (?:its|their) owner'?s warp\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_DROP_TO_WARP_RE = re.compile(
    r"\[activate(?::)?\s*main\](?:(?!<br>|\[(?:auto|activate|counter|permanent|blocker|barrier)\b).){0,260}?send (\d+) (?:(.+?) )?cards? from your drop to (?:its|their) owner'?s warp\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_SEND_SELF_TO_WARP_RE = re.compile(
    r"\[activate(?::)?\s*main\](?:(?!<br>|\[(?:auto|activate|counter|permanent|blocker|barrier)\b).){0,260}?send this card to (?:(?:the )?warp|(?:its|their )?owner'?s warp)(?:\s*:|,\s*and\b)",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_REMOVE_SELF_IN_DROP_AND_DISCARD_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\](?:(?!<br>|\[(?:auto|activate|counter|permanent|blocker|barrier)\b).){0,320}?remove this card in the drop from the game,\s*and you discard (\d+) card(?:s)? from your hand\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_REMOVE_SELF_TO_REMOVED_RE = re.compile(
    r"\[activate(?::)?\s*main\](?:(?!<br>|\[(?:auto|activate|counter|permanent|blocker|barrier)\b).){0,260}?remove this card from the game\s*:",
    re.IGNORECASE,
)
_ACTIVATE_BATTLE_REMOVE_SELF_TO_REMOVED_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,260}?remove this card from the game\s*:"
)
_ACTIVATE_MAIN_BATTLE_REMOVE_SELF_TO_REMOVED_RE = re.compile(
    r"\[activate(?::)?\s*(main|battle|main/battle)\].{0,260}?remove this card from the game\s*:",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_SPIRIT_BOOST_RE = re.compile(
    r"\[activate(?::)?\s*main\](?:.{0,120}?)?\[spirit boost\s+(\d+)\]"
)
_ACTIVATE_MAIN_REMOVE_TOTAL_DROP_AND_WARP_TO_REMOVED_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?remove (\d+) total cards? in your drop and warp from the game\s*:"
)
_AUTO_ON_PLAY_Z_ENERGY_TO_DROP_RE = re.compile(
    r"place (\d+) of your z-energy into (?:its|their) owner'?s drop\s*:\s*when this card is played,\s*activate this skill",
    re.IGNORECASE,
)
_AUTO_ON_PLAY_HAND_TO_BOTTOM_DECK_RE = re.compile(
    r"place (\d+) card(?:s)? from your hand at the bottom of your deck(?: in any order)?\s*:\s*when this card is played",
    re.IGNORECASE,
)
_AUTO_ON_OPPONENT_COMBO_Z_ENERGY_TO_DROP_RE = re.compile(
    r"place (\d+) of your z-energy into (?:its|their) owner'?s drop\s*:\s*when your opponent uses cards? in a combo",
    re.IGNORECASE,
)
_AUTO_ON_COMBO_SINGLE_ENERGY_TO_DROP_RE = re.compile(
    r"\[auto\]\((red|blue|green|yellow|black|white)\)(?:.{0,220}?)?:\s*when (?:this card is used in a combo|you combo with this card)",
    re.IGNORECASE,
)
_AUTO_ON_COMBO_GENERIC_ENERGY_TO_DROP_RE = re.compile(
    r"\[auto\]\s*([①②③④⑤⑥⑦⑧⑨⑩])(?:.{0,220}?)?:\s*when (?:this card is used in a combo|you combo with this card)",
    re.IGNORECASE,
)
_AUTO_ON_COMBO_LEADER_UNDER_TO_DROP_RE = re.compile(
    r"place (\d+) (.+?) from under your leader in (?:its|their) owner'?s drop\s*:\s*when (?:this card is used in a combo|you combo with this card)",
    re.IGNORECASE,
)
_AUTO_ON_COMBO_OPPONENT_BATTLE_TO_REMOVED_RE = re.compile(
    r"(?:remove (\d+) of your opponent'?s (.+?) from the game|choose (\d+) of your opponent'?s (.+?) and remove (?:it|them) from the game|choose (\d+) (.+?) (?:in|from) your opponent'?s battle area and remove (?:it|them) from the game)\s*:\s*when (?:this card is used in a combo|you combo with this card)",
    re.IGNORECASE,
)
_AUTO_ON_PLAY_OPPONENT_BATTLE_TO_REMOVED_RE = re.compile(
    r"(?:remove (\d+) of your opponent'?s (.+?) from the game|choose (\d+) of your opponent'?s (.+?) and remove (?:it|them) from the game|choose (\d+) (.+?) (?:in|from) your opponent'?s battle area and remove (?:it|them) from the game)\s*:\s*when (?:this card is played|you play this card)",
    re.IGNORECASE,
)
_AUTO_ON_SELF_DROP_ENERGY_TO_DROP_RE = re.compile(
    r"\[auto\]\{(\d+)\}(?:.{0,260}?)?:\s*when this card is placed into (?:its|their) owner'?s drop from your hand or from under your leader by your leader'?s skill",
    re.IGNORECASE,
)
_AUTO_ON_OWNER_COMBO_SPIRIT_BOOST_RE = re.compile(
    r"\[auto\](?:.{0,140}?)?\[spirit boost\s+(\d+)\](?:.{0,260}?)?(?::\s*)?(?:if [^:]{1,220}:\s*)?when (?:one of your|you use) .+? in a combo",
    re.IGNORECASE,
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
_COUNTER_ALT_LEADER_UNDER_TO_DROP_RE = re.compile(
    r"\[(?:permanent|permament)\].{0,260}?activate this card's \[counter\] skill from your hand (?:(?:without paying (?:its|this card'?s) energy cost by placing (\d+) (.+?) from under your leader in (?:its owner'?s|their owners?') drops?)|(?:by placing (\d+) (.+?) from under your leader in (?:its owner'?s|their owners?') drops? instead of paying (?:its|this card'?s) energy cost))"
)
_COUNTER_ALT_OWNER_BATTLE_UNDER_TO_DROP_RE = re.compile(
    r"\[(?:permanent|permament)\].{0,320}?activate this card's \[counter\] skill from your hand (?:(?:without paying (?:its|this card'?s) energy cost by placing (\d+) cards? from under (.+?) in your battle area in (?:its owner'?s|their owners?') drop area)|(?:by placing (\d+) cards? from under (.+?) in your battle area in (?:its owner'?s|their owners?') drop area instead of paying (?:its|this card'?s) energy cost))",
    re.IGNORECASE,
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
_COUNTER_DIRECT_DISCARD_HAND_TO_DROP_RE = re.compile(
    r"\[counter:\s*(?:attack|play|counter|battle card attack)\].{0,220}?choose (\d+) (.+?) cards? in your hand and place (?:it|them) in your drop area\s*:"
)


def _normalize_text(raw: str | None) -> str:
    text = str(raw or "")
    text = re.sub(r"<badge[^>]*>\s*([^<]+?)\s*</badge>", lambda m: f"[{m.group(1)}]", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", ". ", text, flags=re.IGNORECASE)
    text = html.unescape(text).lower()
    text = text.replace("[br]", ". ").replace("—", " - ").replace("―", " - ")
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
    if cleaned.startswith("and ") or "you choose" in cleaned:
        return ""
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


def _extract_leader_under_to_drop_cost(descriptor: str, amount: int) -> dict[str, int | str | bool]:
    params: dict[str, int | str | bool] = {
        "kind": "send_owner_leader_under_to_drop",
        "amount": amount,
    }
    descriptor_lc = descriptor.lower()
    allowed_colors = _extract_allowed_colors(descriptor_lc)
    if allowed_colors:
        params["allowed_colors"] = allowed_colors
    required_traits = _extract_wrapper_values(descriptor, open_char="â‰ª", close_char="â‰«")
    if required_traits:
        params["required_traits"] = required_traits
    required_characters = _extract_wrapper_values(descriptor, open_char="<", close_char=">")
    if required_characters:
        params["required_characters"] = required_characters
    if "z-leader" in descriptor_lc or "z leader" in descriptor_lc:
        params["required_card_types"] = "Z-LEADER"
    elif "leader" in descriptor_lc and "non-leader" not in descriptor_lc and "non-leaders" not in descriptor_lc:
        params["required_card_types"] = "LEADER"
    elif "z-battle" in descriptor_lc or "z battle" in descriptor_lc:
        params["required_card_types"] = "Z-BATTLE"
    elif "battle" in descriptor_lc:
        params["required_card_types"] = "BATTLE"
    elif "extra" in descriptor_lc:
        params["required_card_types"] = "EXTRA"
    elif "unison" in descriptor_lc:
        params["required_card_types"] = "UNISON"
    if "non-leader" in descriptor_lc or "non-leaders" in descriptor_lc:
        params["forbidden_card_types"] = "LEADER,Z-LEADER"
    return params


def _extract_owner_battle_under_to_drop_cost(descriptor: str, amount: int) -> dict[str, int | str | bool]:
    params: dict[str, int | str | bool] = {
        "kind": "send_owner_battle_under_to_drop",
        "amount": amount,
    }
    descriptor_lc = descriptor.lower()
    allowed_colors = _extract_allowed_colors(descriptor_lc)
    if allowed_colors:
        params["required_host_allowed_colors"] = allowed_colors
    required_traits = _extract_wrapper_values(descriptor, open_char="≪", close_char="≫")
    if required_traits:
        params["required_host_required_traits"] = required_traits
    required_characters = _extract_wrapper_values(descriptor, open_char="<", close_char=">")
    if required_characters:
        params["required_host_required_characters"] = required_characters
    required_name_contains = _extract_required_name_tokens(descriptor)
    if required_name_contains:
        params["required_host_name_contains"] = required_name_contains.upper()
    if "z-battle" in descriptor_lc or "z battle" in descriptor_lc:
        params["required_host_card_types"] = "Z-BATTLE"
    elif "battle" in descriptor_lc:
        params["required_host_card_types"] = "BATTLE"
    elif "extra" in descriptor_lc:
        params["required_host_card_types"] = "EXTRA"
    elif "unison" in descriptor_lc:
        params["required_host_card_types"] = "UNISON"
    return params


def _extract_z_energy_under_self_cost(descriptor: str, amount: int) -> dict[str, int | str | bool]:
    params = _extract_filtered_cost_step("send_owner_z_energy_under_self", descriptor, amount)
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


def _extract_plain_token_name(descriptor: str) -> str:
    cleaned = str(descriptor or "").strip()
    cleaned_lc = cleaned.lower()
    if "token" not in cleaned_lc or "non-token" in cleaned_lc:
        return ""
    cleaned = re.sub(r"^(?:of\s+)?your opponent'?s\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:of\s+)?your\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bin your opponent'?s battle area\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bin your battle area\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bfrom your opponent'?s battle area\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bfrom your battle area\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.")
    if cleaned.lower().endswith("tokens"):
        cleaned = cleaned[:-1]
    return cleaned.strip()


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
    elif "token" in descriptor.lower():
        token_name = _extract_plain_token_name(descriptor)
        if token_name:
            params["required_name_contains"] = token_name.upper()
    if "battle" in descriptor:
        params["required_card_types"] = "BATTLE"
    elif "extra" in descriptor:
        params["required_card_types"] = "EXTRA"
    elif "unison" in descriptor:
        params["required_card_types"] = "UNISON"
    elif "token" in descriptor.lower():
        params["required_card_types"] = "BATTLE"
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

    if _ACTIVATE_BATTLE_SELF_FROM_COMBO_TO_DROP_RE.search(text):
        rules["activate_battle_combo"] = [
            {
                "kind": "send_self_from_combo_to_drop",
                "amount": 1,
            }
        ]

    if _ACTIVATE_BATTLE_SELF_FROM_LEADER_UNDER_TO_WARP_RE.search(text):
        rules["activate_battle_leader_under"] = [
            {
                "kind": "send_self_from_leader_under_to_warp",
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
            rules.setdefault(context, []).append(step)

    m_activate_main_battle_drop_to_bottom_deck = _ACTIVATE_MAIN_BATTLE_DROP_TO_BOTTOM_DECK_RE.search(text)
    if m_activate_main_battle_drop_to_bottom_deck:
        amount = int(m_activate_main_battle_drop_to_bottom_deck.group(1))
        descriptor = str(m_activate_main_battle_drop_to_bottom_deck.group(2) or "").strip()
        step = _extract_filtered_cost_step("send_owner_drop_to_bottom_deck", descriptor, amount)
        rules.setdefault("activate_main_unison", []).append(step)
        rules.setdefault("activate_battle_unison", []).append(dict(step))

    m_activate_main_z_energy_to_drop = _ACTIVATE_MAIN_Z_ENERGY_TO_DROP_RE.search(text)
    m_activate_main_battle_z_energy_to_drop_and_remove_self = _ACTIVATE_MAIN_BATTLE_Z_ENERGY_TO_DROP_AND_REMOVE_SELF_RE.search(text)
    if m_activate_main_battle_z_energy_to_drop_and_remove_self:
        context = "activate_battle" if str(m_activate_main_battle_z_energy_to_drop_and_remove_self.group(1) or "").strip().lower() == "battle" else "activate_main"
        rules.setdefault(context, []).append(
            {
                "kind": "send_owner_z_energy_to_drop",
                "amount": int(m_activate_main_battle_z_energy_to_drop_and_remove_self.group(2)),
            }
        )
        rules.setdefault(context, []).append({"kind": "send_self_to_removed", "amount": 1})
    elif m_activate_main_z_energy_to_drop:
        rules["activate_main_warp"] = [
            {
                "kind": "send_owner_z_energy_to_drop",
                "amount": int(m_activate_main_z_energy_to_drop.group(1)),
            }
        ]

    m_activate_main_energy_to_drop = _ACTIVATE_MAIN_ENERGY_TO_DROP_RE.search(text)
    if m_activate_main_energy_to_drop:
        rules["activate_main"] = [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": int(m_activate_main_energy_to_drop.group(1)),
            }
        ]
    m_activate_main_life_to_hand = _ACTIVATE_MAIN_LIFE_TO_HAND_RE.search(text)
    if m_activate_main_life_to_hand:
        rules.setdefault("activate_main", []).append(
            {
                "kind": "add_life_to_hand",
                "amount": int(m_activate_main_life_to_hand.group(1)),
            }
        )
    if _ACTIVATE_MAIN_REST_SELF_RE.search(text):
        rules.setdefault("activate_main", []).insert(
            0,
            {
                "kind": "rest_self",
                "amount": 1,
            },
        )

    m_activate_battle_energy_to_drop = _ACTIVATE_BATTLE_ENERGY_TO_DROP_RE.search(text)
    if m_activate_battle_energy_to_drop:
        rules["activate_battle"] = [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": int(m_activate_battle_energy_to_drop.group(1)),
            }
        ]
    m_activate_battle_discard_hand = _ACTIVATE_BATTLE_DISCARD_HAND_RE.search(text)
    if m_activate_battle_discard_hand:
        rules.setdefault("activate_battle", []).append(
            {
                "kind": "send_owner_hand_to_drop",
                "amount": int(m_activate_battle_discard_hand.group(1)),
            }
        )
    m_activate_battle_z_energy_under_self = _ACTIVATE_BATTLE_Z_ENERGY_UNDER_SELF_RE.search(text)
    if m_activate_battle_z_energy_under_self:
        rules.setdefault("activate_battle", []).append(
            _extract_z_energy_under_self_cost(
                str(m_activate_battle_z_energy_under_self.group(2) or "").strip(),
                int(m_activate_battle_z_energy_under_self.group(1)),
            )
        )

    m_activate_main_battle_energy_to_drop = _ACTIVATE_MAIN_BATTLE_ENERGY_TO_DROP_RE.search(text)
    if m_activate_main_battle_energy_to_drop:
        amount = int(m_activate_main_battle_energy_to_drop.group(1))
        rules["activate_main"] = [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": amount,
            }
        ]
        rules["activate_battle"] = [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": amount,
            }
        ]

    m_activate_main_other_battle_to_drop = _ACTIVATE_MAIN_OTHER_BATTLE_TO_DROP_RE.search(text)
    if m_activate_main_other_battle_to_drop:
        amount = int(m_activate_main_other_battle_to_drop.group(1))
        descriptor = str(m_activate_main_other_battle_to_drop.group(2) or "").strip()
        rules["activate_main"] = [_extract_filtered_cost_step("send_other_battle_to_drop", descriptor, amount)]

    m_activate_main_remove_opponent_battle_to_removed = _ACTIVATE_MAIN_REMOVE_OPPONENT_BATTLE_TO_REMOVED_RE.search(text)
    if m_activate_main_remove_opponent_battle_to_removed:
        amount = int(
            m_activate_main_remove_opponent_battle_to_removed.group(1)
            or m_activate_main_remove_opponent_battle_to_removed.group(3)
            or m_activate_main_remove_opponent_battle_to_removed.group(5)
            or 0
        )
        descriptor = str(
            m_activate_main_remove_opponent_battle_to_removed.group(2)
            or m_activate_main_remove_opponent_battle_to_removed.group(4)
            or m_activate_main_remove_opponent_battle_to_removed.group(6)
            or ""
        ).strip()
        rules.setdefault("activate_main", []).append(_extract_filtered_cost_step("send_opponent_battle_to_removed", descriptor, amount))

    m_activate_main_remove_owner_battle_to_removed = _ACTIVATE_MAIN_REMOVE_OWNER_BATTLE_TO_REMOVED_RE.search(text)
    if m_activate_main_remove_owner_battle_to_removed:
        amount = int(
            m_activate_main_remove_owner_battle_to_removed.group(1)
            or m_activate_main_remove_owner_battle_to_removed.group(3)
            or m_activate_main_remove_owner_battle_to_removed.group(5)
            or 0
        )
        descriptor = str(
            m_activate_main_remove_owner_battle_to_removed.group(2)
            or m_activate_main_remove_owner_battle_to_removed.group(4)
            or m_activate_main_remove_owner_battle_to_removed.group(6)
            or ""
        ).strip()
        if "opponent" not in descriptor.lower():
            target_context = "activate_main_unison" if _PLAIN_MARKER_ACTIVATE_RE.search(text) else "activate_main"
            rules.setdefault(target_context, []).append(_extract_filtered_cost_step("send_owner_battle_to_removed", descriptor, amount))

    m_activate_main_battle_owner_battle_to_warp = _ACTIVATE_MAIN_BATTLE_OWNER_BATTLE_TO_WARP_RE.search(text)
    if m_activate_main_battle_owner_battle_to_warp:
        mode = str(m_activate_main_battle_owner_battle_to_warp.group(1) or "").strip().lower()
        descriptor = str(m_activate_main_battle_owner_battle_to_warp.group(2) or "").strip()
        exact_energy_cost = int(m_activate_main_battle_owner_battle_to_warp.group(3) or 0)
        step = _extract_filtered_cost_step("send_owner_battle_to_warp", descriptor, 1)
        step["required_card_types"] = "BATTLE"
        if exact_energy_cost > 0:
            step["exact_energy_cost"] = exact_energy_cost
        contexts = (
            ["activate_main", "activate_battle"]
            if mode == "main/battle"
            else [f"activate_{mode}"]
        )
        for context in contexts:
            rules.setdefault(context, []).append(dict(step))

    m_activate_main_hand_to_warp = _ACTIVATE_MAIN_HAND_TO_WARP_RE.search(text)
    if m_activate_main_hand_to_warp:
        rules["activate_main_unison"] = [
            {
                "kind": "send_owner_hand_to_warp",
                "amount": int(m_activate_main_hand_to_warp.group(1)),
            }
        ]
    if _ACTIVATE_MAIN_SEND_SELF_FROM_HAND_TO_WARP_RE.search(text):
        rules["activate_main_hand"] = [
            {
                "kind": "send_self_from_hand_to_warp",
                "amount": 1,
            }
        ]
    m_activate_main_hand_to_drop = _ACTIVATE_MAIN_HAND_TO_DROP_RE.search(text)
    if m_activate_main_hand_to_drop:
        rules.setdefault("activate_main", []).append(
            {
                "kind": "send_owner_hand_to_drop",
                "amount": int(m_activate_main_hand_to_drop.group(1)),
            }
        )
    m_activate_main_hand_to_bottom_deck = _ACTIVATE_MAIN_HAND_TO_BOTTOM_DECK_RE.search(text)
    if m_activate_main_hand_to_bottom_deck:
        rules.setdefault("activate_main", []).append(
            {
                "kind": "send_owner_hand_to_bottom_deck",
                "amount": int(m_activate_main_hand_to_bottom_deck.group(1)),
            }
        )
    m_activate_main_remove_self_in_drop_and_discard_hand = _ACTIVATE_MAIN_REMOVE_SELF_IN_DROP_AND_DISCARD_HAND_RE.search(text)
    m_activate_main_discard_hand = _ACTIVATE_MAIN_DISCARD_HAND_RE.search(text)
    m_activate_main_direct_discard_hand = _ACTIVATE_MAIN_DIRECT_DISCARD_HAND_TO_DROP_RE.search(text)
    if m_activate_main_direct_discard_hand:
        descriptor = str(m_activate_main_direct_discard_hand.group(2) or "").strip()
        rules["activate_main"] = [
            _extract_filtered_cost_step("discard_hand", descriptor, int(m_activate_main_direct_discard_hand.group(1)))
        ]
    if m_activate_main_discard_hand and m_activate_main_remove_self_in_drop_and_discard_hand is None:
        rules["activate_main"] = [
            {
                "kind": "discard_hand",
                "amount": int(m_activate_main_discard_hand.group(1)),
            }
        ]
    if _ACTIVATE_MAIN_DISCARD_SELF_FROM_HAND_RE.search(text):
        rules["activate_main_hand"] = [
            {
                "kind": "send_self_from_hand_to_drop",
                "amount": 1,
            }
        ]
    if _ACTIVATE_MAIN_PLACE_SELF_IN_DROP_RE.search(text):
        rules.setdefault("activate_main", []).append(
            {
                "kind": "send_self_to_drop",
                "amount": 1,
            }
        )
    m_activate_main_spirit_boost = _ACTIVATE_MAIN_SPIRIT_BOOST_RE.search(text)
    if m_activate_main_spirit_boost:
        rules.setdefault("activate_main", []).insert(
            0,
            {
                "kind": "remove_owner_unison_markers",
                "amount": int(m_activate_main_spirit_boost.group(1)),
            },
        )
    m_activate_main_drop_to_warp = _ACTIVATE_MAIN_DROP_TO_WARP_RE.search(text)
    if m_activate_main_drop_to_warp:
        amount = int(m_activate_main_drop_to_warp.group(1))
        descriptor = str(m_activate_main_drop_to_warp.group(2) or "").strip()
        rules.setdefault("activate_main", []).append(_extract_filtered_cost_step("send_owner_drop_to_warp", descriptor, amount))
    if _ACTIVATE_MAIN_SEND_SELF_TO_WARP_RE.search(text):
        rules.setdefault("activate_main", []).append({"kind": "send_self_to_warp", "amount": 1})
    if m_activate_main_remove_self_in_drop_and_discard_hand:
        rules.setdefault("activate_main", []).append({"kind": "send_self_to_removed", "amount": 1})
        rules.setdefault("activate_main", []).append(
            {"kind": "discard_hand", "amount": int(m_activate_main_remove_self_in_drop_and_discard_hand.group(1))}
        )
    if _ACTIVATE_MAIN_REMOVE_SELF_TO_REMOVED_RE.search(text) and m_activate_main_battle_z_energy_to_drop_and_remove_self is None:
        rules.setdefault("activate_main", []).append({"kind": "send_self_to_removed", "amount": 1})
    if _ACTIVATE_BATTLE_REMOVE_SELF_TO_REMOVED_RE.search(text) and (
        m_activate_main_battle_z_energy_to_drop_and_remove_self is None
        or str(m_activate_main_battle_z_energy_to_drop_and_remove_self.group(1) or "").strip().lower() != "battle"
    ):
        rules.setdefault("activate_battle", []).append({"kind": "send_self_to_removed", "amount": 1})
    m_activate_main_battle_remove_self = _ACTIVATE_MAIN_BATTLE_REMOVE_SELF_TO_REMOVED_RE.search(text)
    if m_activate_main_battle_remove_self and m_activate_main_battle_z_energy_to_drop_and_remove_self is None:
        mode = str(m_activate_main_battle_remove_self.group(1) or "").strip().lower()
        contexts = (
            ["activate_main", "activate_battle"]
            if mode == "main/battle"
            else [f"activate_{mode}"]
        )
        for context in contexts:
            if not any(step.get("kind") == "send_self_to_removed" for step in rules.get(context, [])):
                rules.setdefault(context, []).append({"kind": "send_self_to_removed", "amount": 1})
    m_activate_main_remove_total_drop_and_warp = _ACTIVATE_MAIN_REMOVE_TOTAL_DROP_AND_WARP_TO_REMOVED_RE.search(text)
    if m_activate_main_remove_total_drop_and_warp:
        rules["activate_main"] = [
            {
                "kind": "send_owner_drop_and_warp_to_removed",
                "amount": int(m_activate_main_remove_total_drop_and_warp.group(1)),
            }
        ]

    m_auto_on_play_z_energy_to_drop = _AUTO_ON_PLAY_Z_ENERGY_TO_DROP_RE.search(text)
    if m_auto_on_play_z_energy_to_drop:
        rules["auto_on_play_battle"] = [
            {
                "kind": "send_owner_z_energy_to_drop",
                "amount": int(m_auto_on_play_z_energy_to_drop.group(1)),
            }
        ]
    m_auto_on_play_hand_to_bottom_deck = _AUTO_ON_PLAY_HAND_TO_BOTTOM_DECK_RE.search(text)
    if m_auto_on_play_hand_to_bottom_deck:
        rules["auto_on_play_battle"] = [
            {
                "kind": "send_owner_hand_to_bottom_deck",
                "amount": int(m_auto_on_play_hand_to_bottom_deck.group(1)),
            }
        ]
    m_auto_on_opponent_combo_z_energy_to_drop = _AUTO_ON_OPPONENT_COMBO_Z_ENERGY_TO_DROP_RE.search(text)
    if m_auto_on_opponent_combo_z_energy_to_drop:
        rules["auto_on_opponent_combo_battle"] = [
            {
                "kind": "send_owner_z_energy_to_drop",
                "amount": int(m_auto_on_opponent_combo_z_energy_to_drop.group(1)),
            }
        ]
    m_auto_on_owner_combo_spirit_boost = _AUTO_ON_OWNER_COMBO_SPIRIT_BOOST_RE.search(text)
    if m_auto_on_owner_combo_spirit_boost:
        rules.setdefault("auto_on_owner_combo_battle", []).insert(
            0,
            {
                "kind": "remove_owner_unison_markers",
                "amount": int(m_auto_on_owner_combo_spirit_boost.group(1)),
            },
        )
    m_auto_on_combo_energy_to_drop = _AUTO_ON_COMBO_SINGLE_ENERGY_TO_DROP_RE.search(text)
    if m_auto_on_combo_energy_to_drop:
        rules["auto_on_combo_battle"] = [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": 1,
                "allowed_colors": str(m_auto_on_combo_energy_to_drop.group(1) or "").strip().lower(),
            }
        ]
    m_auto_on_combo_generic_energy_to_drop = _AUTO_ON_COMBO_GENERIC_ENERGY_TO_DROP_RE.search(text)
    if m_auto_on_combo_generic_energy_to_drop:
        rules["auto_on_combo_battle"] = [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": int(_CIRCLED_NUMERIC_COSTS.get(str(m_auto_on_combo_generic_energy_to_drop.group(1) or "").strip(), 0)),
            }
        ]
    m_auto_on_combo_leader_under_to_drop = _AUTO_ON_COMBO_LEADER_UNDER_TO_DROP_RE.search(text)
    if m_auto_on_combo_leader_under_to_drop:
        rules["auto_on_combo_battle"] = [
            _extract_leader_under_to_drop_cost(
                str(m_auto_on_combo_leader_under_to_drop.group(2) or "").strip(),
                int(m_auto_on_combo_leader_under_to_drop.group(1)),
            )
        ]
    m_auto_on_combo_opponent_battle_to_removed = _AUTO_ON_COMBO_OPPONENT_BATTLE_TO_REMOVED_RE.search(text)
    if m_auto_on_combo_opponent_battle_to_removed:
        rules["auto_on_combo_battle"] = [
            _extract_filtered_cost_step(
                "send_opponent_battle_to_removed",
                str(
                    m_auto_on_combo_opponent_battle_to_removed.group(2)
                    or m_auto_on_combo_opponent_battle_to_removed.group(4)
                    or m_auto_on_combo_opponent_battle_to_removed.group(6)
                    or ""
                ).strip(),
                int(
                    m_auto_on_combo_opponent_battle_to_removed.group(1)
                    or m_auto_on_combo_opponent_battle_to_removed.group(3)
                    or m_auto_on_combo_opponent_battle_to_removed.group(5)
                    or 0
                ),
            )
        ]
    m_auto_on_play_opponent_battle_to_removed = _AUTO_ON_PLAY_OPPONENT_BATTLE_TO_REMOVED_RE.search(text)
    if m_auto_on_play_opponent_battle_to_removed:
        rules["auto_on_play_battle"] = [
            _extract_filtered_cost_step(
                "send_opponent_battle_to_removed",
                str(
                    m_auto_on_play_opponent_battle_to_removed.group(2)
                    or m_auto_on_play_opponent_battle_to_removed.group(4)
                    or m_auto_on_play_opponent_battle_to_removed.group(6)
                    or ""
                ).strip(),
                int(
                    m_auto_on_play_opponent_battle_to_removed.group(1)
                    or m_auto_on_play_opponent_battle_to_removed.group(3)
                    or m_auto_on_play_opponent_battle_to_removed.group(5)
                    or 0
                ),
            )
        ]
    m_auto_on_self_drop_energy_to_drop = _AUTO_ON_SELF_DROP_ENERGY_TO_DROP_RE.search(text)
    if m_auto_on_self_drop_energy_to_drop:
        rules["auto_on_self_drop"] = [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": int(m_auto_on_self_drop_energy_to_drop.group(1)),
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

    m_counter_alt_leader_under_to_drop = _COUNTER_ALT_LEADER_UNDER_TO_DROP_RE.search(text)
    if m_counter_alt_leader_under_to_drop and "counter_alternate_from_hand" not in rules:
        amount = int(
            (m_counter_alt_leader_under_to_drop.group(1) or m_counter_alt_leader_under_to_drop.group(3) or "0")
        )
        descriptor = str(
            m_counter_alt_leader_under_to_drop.group(2) or m_counter_alt_leader_under_to_drop.group(4) or ""
        ).strip()
        params = _extract_leader_under_to_drop_cost(
            descriptor,
            amount,
        )
        required_leader_colors = _extract_required_leader_colors(text)
        if required_leader_colors:
            params["required_leader_colors"] = required_leader_colors
        required_leader_traits = _extract_required_leader_traits(text)
        if required_leader_traits:
            params["required_leader_traits"] = required_leader_traits
        rules["counter_alternate_from_hand"] = [params]

    m_counter_alt_owner_battle_under_to_drop = _COUNTER_ALT_OWNER_BATTLE_UNDER_TO_DROP_RE.search(text)
    if m_counter_alt_owner_battle_under_to_drop and "counter_alternate_from_hand" not in rules:
        amount = int(
            (m_counter_alt_owner_battle_under_to_drop.group(1) or m_counter_alt_owner_battle_under_to_drop.group(3) or "0")
        )
        descriptor = str(
            m_counter_alt_owner_battle_under_to_drop.group(2) or m_counter_alt_owner_battle_under_to_drop.group(4) or ""
        ).strip()
        params = _extract_owner_battle_under_to_drop_cost(descriptor, amount)
        required_leader_colors = _extract_required_leader_colors(text)
        if required_leader_colors:
            params["required_leader_colors"] = required_leader_colors
        required_leader_traits = _extract_required_leader_traits(text)
        if required_leader_traits:
            params["required_leader_traits"] = required_leader_traits
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

    m_counter_direct_discard_hand = _COUNTER_DIRECT_DISCARD_HAND_TO_DROP_RE.search(text)
    if m_counter_direct_discard_hand:
        descriptor = m_counter_direct_discard_hand.group(2).strip()
        params = _extract_filtered_cost_step("discard_hand", descriptor, int(m_counter_direct_discard_hand.group(1)))
        required_leader_colors = _extract_required_leader_colors(text)
        if required_leader_colors:
            params["required_leader_colors"] = required_leader_colors
        required_leader_traits = _extract_required_leader_traits(text)
        if required_leader_traits:
            params["required_leader_traits"] = required_leader_traits
        rules["counter_from_hand"] = [params]

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

