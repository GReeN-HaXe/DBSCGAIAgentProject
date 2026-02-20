from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from src.db.interfaces import CardRepository
from src.domain.models import CardData
from src.game.effect_rules import EffectRule


_WS_RE = re.compile(r"\s+")
_PLAY_TRIGGER_RE = re.compile(r"(?:if [^:]{1,120}:\s*)?when (?:this card is played(?: from your hand)?|you play this card)")
_ATTACK_TRIGGER_RE = re.compile(r"(?:if [^:]{1,120}:\s*)?when this card attacks")
_COMBO_TRIGGER_RE = re.compile(r"(?:if [^:]{1,120}:\s*)?when this card is used in a combo")
_COMBO_DRAW_RE = re.compile(r"(?:if [^:]{1,120}:\s*)?when this card is used in a combo.*?draw (\d+) card")
_COMBO_BATTLE_END_PLAY_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?at the end of a battle in which this card was used in a combo(?: from your (?:hand|life|energy|drop area))?.*?play this card from (?:your )?drop"
)
_TURN_END_SWITCH_ACTIVE_RE = re.compile(r"(?:if [^:]{1,120}:\s*)?at the end of your turn, switch this card to active mode")
_ACTIVATE_MAIN_DRAW_RE = re.compile(r"\[activate:\s*main\][^:]{0,200}:\s*draw (\d+) card")
_PLAY_TOP_IF_COLOR_ADD_HAND_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card is played(?: from your hand)?(?: or discarded by [^:]{1,120})?.*?"
    r"look at the top card of your deck; if it's a (red|blue|green|yellow|black)\b.*?you may add it to your hand.*?otherwise,?\s*place it at the bottom of your deck"
)
_OWNER_BLACK_BATTLE_PLAYED_FROM_WARP_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when a black battle card is played from your warp.*?this card gains \[wormhole\] for the turn"
)
_PLAY_ADD_TOP_DECK_TO_ENERGY_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card is played.*?add the top card of your deck to your energy in rest mode"
)
_TURN_END_SWITCH_UP_TO_N_ENERGY_ACTIVE_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?at the end of your turn, switch up to (\d+) of your(?: (.+?))? energy to active mode"
)
_SELF_KO_UNISON_POWER_REDUCE_RE = re.compile(
    r"when this card is ko['’]?d.*?choose up to (\d+) of your opponent'?s unison card.*?gets? -\s*(\d+) power"
)
_PLAY_FROM_HAND_PLAY_FROM_DECK_RE = re.compile(
    r"when this card is played from your hand, choose up to (\d+) (.+?) from your deck, play it"
)
_COMBO_FROM_HAND_PLAY_FROM_HAND_RE = re.compile(
    r"when this card is used in a combo from your hand, choose up to (\d+) (.+?) in your hand and play it(?: in rest mode)?"
)
_PLAY_GAIN_CONTROL_OPP_UNISON_RE = re.compile(
    r"when this card is played from your hand, choose (?:up to )?(\d+) of your opponent'?s unison cards? and gain control of it"
)
_PLAY_LOOK_TOP_ADD_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card is played( from your hand)?[^.]{0,300}?"
    r"look at up to (\d+) cards? from (?:the )?top of your deck, add up to (\d+) (.+?) among them(?:[^.]{0,240})?(?:\s|[—―-])to your hand"
)


def _normalize_text(raw: str | None) -> str:
    text = (raw or "").lower()
    text = text.replace("<br>", ". ").replace("[br]", ". ").replace("—", " - ")
    return _WS_RE.sub(" ", text.strip())


def _once_per_turn(text: str) -> bool:
    return ("[once per turn]" in text) or ("once per turn" in text)


def _split_choose_one_branches(text: str) -> list[str]:
    marker = "choose one"
    if marker not in text:
        return [text]
    idx = text.find(marker)
    if idx < 0:
        return [text]
    prefix = text[:idx]
    tail = text[idx:]
    if "・" not in tail:
        return [text]
    parts = [p.strip(" .;-") for p in tail.split("・")[1:] if p.strip(" .;-")]
    if not parts:
        return [text]
    return [f"{prefix} {part}".strip() for part in parts]


def _extract_common_conditions(text: str) -> dict[str, int | str | bool]:
    params: dict[str, int | str | bool] = {}
    m_leader = re.search(r"(if your leader[^:]{0,200}):", text)
    if m_leader:
        params["requires_leader"] = m_leader.group(1).strip()
    m_mono_energy = re.search(r"if all of your energy is mono-(red|blue|green|yellow|black)", text)
    if m_mono_energy:
        params["requires_mono_energy"] = m_mono_energy.group(1).strip()
    if "ignoring [barrier]" in text or "ignoring barrier" in text:
        params["ignores_barrier"] = True
    if "rest mode" in text:
        params["rest_mode_only"] = True
    return params


def _infer_x_expression(text: str) -> str | None:
    t = text.lower()
    # Common templated "where X is equal to ..." phrasings.
    if "where x is equal to the number of your energy" in t:
        return "expr:owner_energy_count"
    if "where x is equal to the number of your opponent's battle cards" in t:
        return "expr:opponent_battle_count"
    if "where x is equal to the number of your battle cards" in t:
        return "expr:owner_battle_count"
    if "where x is equal to the number of markers on this card" in t or "where x is equal to this card's markers" in t:
        return "expr:source_markers"
    return None


def _extract_max_targets(text: str) -> int | str:
    m_targets = re.search(r"choose up to (\d+) of your opponent'?s battle card", text)
    if m_targets:
        return int(m_targets.group(1))
    if re.search(r"choose up to x of your opponent'?s battle card", text):
        expr = _infer_x_expression(text)
        if expr is not None:
            return expr
    return 1


def extract_effect_rules_from_card(card: CardData) -> list[EffectRule]:
    text = _normalize_text(card.card_skill_unstyled)
    if not text:
        return []

    rules: list[EffectRule] = []
    once = _once_per_turn(text)
    for branch in _split_choose_one_branches(text):
        # [Auto] When this card is played... draw X card(s)
        m_play_draw = re.search(r"(?:if [^:]{1,120}:\s*)?when (?:this card is played(?: from your hand)?|you play this card).*?draw (\d+) card", branch)
        if m_play_draw:
            amount = int(m_play_draw.group(1))
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_draw_n",
                    handler_params={"amount": amount},
                    once_per_turn=once,
                )
            )

        # [Auto] When this card attacks... draw X card(s)
        m_attack_draw = re.search(r"(?:if [^:]{1,120}:\s*)?when this card attacks.*?draw (\d+) card", branch)
        if m_attack_draw:
            amount = int(m_attack_draw.group(1))
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_draw_n",
                    handler_params={"amount": amount},
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is used in a combo... draw X card(s)
        m_combo_draw = _COMBO_DRAW_RE.search(branch)
        if m_combo_draw:
            amount = int(m_combo_draw.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_draw_n",
                    handler_params={"amount": amount, **extra},
                    once_per_turn=once,
                )
            )

        # [Auto] At the end of a battle in which this card was used in a combo... play this card from your Drop...
        if _COMBO_BATTLE_END_PLAY_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rest = "rest mode" in branch
            rules.append(
                EffectRule(
                    trigger="self_comboed_battle_end",
                    handler_id="auto_play_self_from_combo_on_battle_end",
                    handler_params={"resting": rest, **extra},
                    once_per_turn=once,
                )
            )

        # [Auto] At the end of your turn, switch this card to Active Mode.
        if _TURN_END_SWITCH_ACTIVE_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="turn_end",
                    handler_id="auto_switch_self_active_on_turn_end",
                    handler_params={**extra},
                    once_per_turn=once,
                )
            )

        # [Activate: Main] ... : Draw N card(s).
        m_activate_main_draw = _ACTIVATE_MAIN_DRAW_RE.search(branch)
        if m_activate_main_draw:
            amount = int(m_activate_main_draw.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="auto_draw_n",
                    handler_params={"amount": amount, **extra},
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is played... look at top card; if it's COLOR ... add to hand, else bottom.
        m_top_if_color = _PLAY_TOP_IF_COLOR_ADD_HAND_RE.search(branch)
        if m_top_if_color:
            color = m_top_if_color.group(1).strip().lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_top_deck_add_if_color_on_play",
                    handler_params={"required_color": color, "move_to_bottom_on_fail": True, **extra},
                    once_per_turn=once,
                )
            )

        # [Auto] When a black Battle Card is played from your Warp, this card gains [Wormhole] for the turn.
        if _OWNER_BLACK_BATTLE_PLAYED_FROM_WARP_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_battle_played_from_warp",
                    handler_id="auto_gain_wormhole_on_owner_black_battle_played_from_warp",
                    handler_params={**extra},
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is played... add the top card of your deck to your energy in Rest Mode.
        if _PLAY_ADD_TOP_DECK_TO_ENERGY_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_add_top_deck_to_energy_rest_on_play",
                    handler_params={**extra},
                    once_per_turn=once,
                )
            )

        # [Auto] At the end of your turn, switch up to N of your energy to Active Mode.
        m_turn_end_energy = _TURN_END_SWITCH_UP_TO_N_ENERGY_ACTIVE_RE.search(branch)
        if m_turn_end_energy:
            max_targets = int(m_turn_end_energy.group(1))
            energy_desc = str(m_turn_end_energy.group(2) or "").lower()
            colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black)\b", energy_desc)))
            requires_multicolor = "multicolor" in energy_desc
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {"max_targets": max_targets, **extra}
            if colors:
                params["allowed_colors"] = ",".join(colors)
            if requires_multicolor:
                params["requires_multicolor"] = True
            rules.append(
                EffectRule(
                    trigger="turn_end",
                    handler_id="auto_switch_up_to_n_owner_energy_active_on_turn_end",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is KO'd... choose up to N opponent Unison cards and it gets -X power.
        m_unison_ko_reduce = _SELF_KO_UNISON_POWER_REDUCE_RE.search(branch)
        if m_unison_ko_reduce:
            max_targets = int(m_unison_ko_reduce.group(1))
            amount = int(m_unison_ko_reduce.group(2))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_koed",
                    handler_id="auto_power_reduce_opponent_unison_on_self_ko",
                    handler_params={
                        "max_targets": max_targets,
                        "power_delta": -amount,
                        "target_policy": "first",
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is played from your hand... choose up to N ... from your deck, play it.
        m_play_from_deck = _PLAY_FROM_HAND_PLAY_FROM_DECK_RE.search(branch)
        if m_play_from_deck:
            max_targets = int(m_play_from_deck.group(1))
            descriptor = m_play_from_deck.group(2).lower()
            colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black)\b", descriptor)))
            m_power = re.search(r"(\d+)\s*power or less", descriptor)
            max_power = int(m_power.group(1)) if m_power else -1
            rest_mode = "rest mode" in branch
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {"max_targets": max_targets, "max_power": max_power, "requires_played_from": "hand", **extra}
            if colors:
                params["allowed_colors"] = ",".join(colors)
            if rest_mode:
                params["rest_mode"] = True
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_play_up_to_n_from_owner_deck_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is used in a combo from your hand... choose up to N ... in your hand and play it.
        m_combo_play_from_hand = _COMBO_FROM_HAND_PLAY_FROM_HAND_RE.search(branch)
        if m_combo_play_from_hand:
            max_targets = int(m_combo_play_from_hand.group(1))
            descriptor = m_combo_play_from_hand.group(2).lower()
            colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black)\b", descriptor)))
            m_cost = re.search(r"energy cost of (\d+) or less", descriptor)
            max_cost = int(m_cost.group(1)) if m_cost else -1
            rest_mode = "in rest mode" in branch
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {"max_targets": max_targets, "max_cost": max_cost, **extra}
            if colors:
                params["allowed_colors"] = ",".join(colors)
            if rest_mode:
                params["rest_mode"] = True
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_play_up_to_n_from_owner_hand_on_self_combo",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is played from your hand... choose up to N opponent Unison cards and gain control.
        m_gain_unison = _PLAY_GAIN_CONTROL_OPP_UNISON_RE.search(branch)
        if m_gain_unison:
            max_targets = int(m_gain_unison.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_gain_control_opponent_unison_on_play",
                    handler_params={"max_targets": max_targets, "target_policy": "first", **extra},
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is played... look at top N; add up to 1 matching card to hand.
        m_top_search = _PLAY_LOOK_TOP_ADD_TO_HAND_RE.search(branch)
        if m_top_search:
            played_from_hand = bool((m_top_search.group(1) or "").strip())
            look_count = int(m_top_search.group(2))
            max_add = int(m_top_search.group(3))
            descriptor = m_top_search.group(4).lower()
            m_cost = re.search(r"energy cost of (\d+) or less", descriptor)
            if m_cost is None:
                m_cost = re.search(r"energy cost of (\d+) or less", branch)
            max_cost = int(m_cost.group(1)) if m_cost else -1
            colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black)\b", descriptor)))
            required_card_type = "BATTLE" if "battle card" in descriptor else ""
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "look_count": look_count,
                "max_add": max_add,
                "max_cost": max_cost,
                **extra,
            }
            if colors:
                params["allowed_colors"] = ",".join(colors)
            if required_card_type:
                params["required_card_type"] = required_card_type
            if played_from_hand:
                params["requires_played_from"] = "hand"
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_look_top_add_up_to_one_to_hand_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is played... choose up to N opponent Battle Card(s)... KO ...
        if _PLAY_TRIGGER_RE.search(branch) and "ko" in branch and "opponent" in branch and "battle card" in branch:
            max_targets = _extract_max_targets(branch)
            m_cost = re.search(r"energy cost of (\d+) or less", branch)
            max_cost = int(m_cost.group(1)) if m_cost else -1
            extra = _extract_common_conditions(branch)
            if isinstance(max_targets, int) and max_targets <= 1:
                rules.append(
                    EffectRule(
                        trigger="self_played",
                        handler_id="auto_ko_opponent_battle_on_play",
                        handler_params={"max_cost": max_cost, **extra},
                        once_per_turn=once,
                    )
                )
            else:
                rules.append(
                    EffectRule(
                        trigger="self_played",
                        handler_id="auto_ko_up_to_n_opponent_battle_on_play",
                        handler_params={"max_targets": max_targets, "max_cost": max_cost, "target_policy": "first", **extra},
                        once_per_turn=once,
                    )
                )

        # [Auto] When this card is played... choose up to N opponent Battle Card(s)... gets -X power ...
        if _PLAY_TRIGGER_RE.search(branch) and ("get -" in branch or "gets -" in branch) and "opponent" in branch and "battle card" in branch:
            max_targets = _extract_max_targets(branch)
            m_cost = re.search(r"energy cost of (\d+) or less", branch)
            max_cost = int(m_cost.group(1)) if m_cost else -1
            m_power = re.search(r"get[s]? -\s*(\d+) power", branch)
            if m_power:
                extra = _extract_common_conditions(branch)
                rules.append(
                    EffectRule(
                        trigger="self_played",
                        handler_id="auto_power_reduce_up_to_n_on_play",
                        handler_params={
                            "max_targets": max_targets,
                            "max_cost": max_cost,
                            "target_policy": "first",
                            "power_delta": -int(m_power.group(1)),
                            **extra,
                        },
                        once_per_turn=once,
                    )
                )

    # De-duplicate exact duplicates.
    uniq: dict[tuple[str, str, tuple[tuple[str, int | str | bool], ...], bool], EffectRule] = {}
    for rule in rules:
        key = (rule.trigger, rule.handler_id, tuple(sorted(rule.handler_params.items())), rule.once_per_turn)
        uniq[key] = rule
    return list(uniq.values())


def build_effect_rules_for_cards(repo: CardRepository, card_ids: Iterable[int]) -> dict[int, list[EffectRule]]:
    mapped: dict[int, list[EffectRule]] = {}
    for card in repo.list_by_ids(card_ids, source_table="cards"):
        rules = extract_effect_rules_from_card(card)
        if rules:
            mapped[card.id] = rules
    return mapped


def diagnose_unresolved_patterns(card: CardData, rules: list[EffectRule]) -> list[str]:
    text = _normalize_text(card.card_skill_unstyled)
    if not text:
        return []
    notes: list[str] = []
    has_play_draw = any(r.trigger == "self_played" and r.handler_id == "auto_draw_n" for r in rules)
    has_attack_draw = any(r.trigger == "self_attacks" and r.handler_id == "auto_draw_n" for r in rules)
    has_combo_draw = any(r.trigger == "self_comboed" and r.handler_id == "auto_draw_n" for r in rules)
    has_ko = any(r.handler_id in {"auto_ko_opponent_battle_on_play", "auto_ko_up_to_n_opponent_battle_on_play"} for r in rules)
    has_reduce = any(r.handler_id == "auto_power_reduce_up_to_n_on_play" for r in rules)

    if re.search(r"(?:if [^:]{1,120}:\s*)?when (?:this card is played(?: from your hand)?|you play this card).*?draw \d+ card", text) and not has_play_draw:
        notes.append("missed_play_draw")
    if re.search(r"(?:if [^:]{1,120}:\s*)?when this card attacks.*?draw \d+ card", text) and not has_attack_draw:
        notes.append("missed_attack_draw")
    if _COMBO_DRAW_RE.search(text) and not has_combo_draw:
        notes.append("missed_combo_draw")
    if _PLAY_TRIGGER_RE.search(text) and "ko" in text and "opponent" in text and "battle card" in text and not has_ko:
        notes.append("missed_play_ko")
    if _PLAY_TRIGGER_RE.search(text) and "gets -" in text and "opponent" in text and "battle card" in text and not has_reduce:
        notes.append("missed_play_power_reduce")
    return notes


def build_effect_rules_with_diagnostics(
    repo: CardRepository,
    card_ids: Iterable[int],
) -> tuple[dict[int, list[EffectRule]], dict[int, list[str]]]:
    mapped: dict[int, list[EffectRule]] = {}
    diagnostics: dict[int, list[str]] = {}
    for card in repo.list_by_ids(card_ids, source_table="cards"):
        rules = extract_effect_rules_from_card(card)
        if rules:
            mapped[card.id] = rules
        notes = diagnose_unresolved_patterns(card, rules)
        if notes:
            diagnostics[card.id] = notes
    return mapped, diagnostics


def _skill_template_signature(raw: str | None) -> str:
    text = _normalize_text(raw)
    if not text:
        return ""
    text = re.sub(r"\d+", "<n>", text)
    text = re.sub(r"\bcards\b", "card", text)
    text = re.sub(r"\bx\b", "<x>", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 220:
        return text[:220].rstrip() + "..."
    return text


def build_effect_rules_with_diagnostics_and_report(
    repo: CardRepository,
    card_ids: Iterable[int],
    *,
    top_unmatched: int = 20,
) -> tuple[dict[int, list[EffectRule]], dict[int, list[str]], dict[str, object]]:
    mapped: dict[int, list[EffectRule]] = {}
    diagnostics: dict[int, list[str]] = {}
    trigger_counts: Counter[str] = Counter()
    handler_counts: Counter[str] = Counter()
    diagnostic_counts: Counter[str] = Counter()
    unmatched_templates: Counter[str] = Counter()
    unmatched_examples: dict[str, int] = {}
    scanned = 0

    for card in repo.list_by_ids(card_ids, source_table="cards"):
        scanned += 1
        rules = extract_effect_rules_from_card(card)
        if rules:
            mapped[card.id] = rules
            for rule in rules:
                trigger_counts[rule.trigger] += 1
                handler_counts[rule.handler_id] += 1
        else:
            signature = _skill_template_signature(card.card_skill_unstyled)
            if signature:
                unmatched_templates[signature] += 1
                unmatched_examples.setdefault(signature, card.id)

        notes = diagnose_unresolved_patterns(card, rules)
        if notes:
            diagnostics[card.id] = notes
            for note in notes:
                diagnostic_counts[note] += 1

    report: dict[str, object] = {
        "candidates_scanned": scanned,
        "cards_with_rules": len(mapped),
        "cards_without_rules": scanned - len(mapped),
        "cards_with_diagnostics": len(diagnostics),
        "total_extracted_rules": sum(len(v) for v in mapped.values()),
        "coverage": {
            "by_trigger": dict(sorted(trigger_counts.items())),
            "by_handler": dict(sorted(handler_counts.items())),
        },
        "diagnostic_counts": dict(sorted(diagnostic_counts.items())),
        "unmatched_top_templates": [
            {
                "template": template,
                "count": count,
                "example_card_id": unmatched_examples[template],
            }
            for template, count in unmatched_templates.most_common(max(int(top_unmatched), 0))
        ],
    }
    return mapped, diagnostics, report
