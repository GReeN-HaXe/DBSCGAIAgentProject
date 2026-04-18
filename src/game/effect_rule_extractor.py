from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import replace
from typing import Iterable

from src.db.interfaces import CardRepository
from src.domain.models import CardData
from src.game.effect_rules import EffectRule


_WS_RE = re.compile(r"\s+")
_PLAY_TRIGGER_RE = re.compile(r"(?:if [^:]{1,120}:\s*)?when (?:this card is played(?: from your hand)?|you play this card)")
_PLAY_DELAYED_TOKEN_RE = re.compile(
    r"(?:if [^:]{1,320}:\s*)?when (?:this card is played(?: from your hand)?|you play this card)(?:,\s*activate this skill)?(?:,\s*if [^,.\[]{1,180})?(?:(?:[^.\[]|\.(?!\s*(?:\[|$)))){0,360}?at the end of your opponent'?s next turn,\s*play (\d+) ([^(\n]+?tokens?)(?: with (\d+) power)?(?: in rest mode)? in your (opponent'?s )?battle area",
    re.IGNORECASE,
)
_PLAY_IMMEDIATE_TOKEN_RE = re.compile(
    r"(?:if [^:]{1,320}:\s*)?when (?:this card is played(?: from your hand)?|you play this card)(?:,\s*if [^,.\[]{1,180})?(?:(?:[^.\[]|\[[^\]]+\])){0,260}?\bplay (?:up to )?(\d+) ([^(\n]+?tokens?)(?: \((\d+) power,\s*(\d+) combo cost,\s*(?:and\s*)?(\d+) combo power\)| with (\d+) power)?(?: in rest mode)?(?:,?\s*and (?:it|that card|they) gain(?:s)? ((?:\[[^\]]+\](?:\s*(?:,|and)\s*)?)+)(?: until the end of (?:your opponent'?s next )?turn| for the turn))?(?:[,;]?\s*and (?:that card|that token|those cards|they) get(?:s)? \+\d+ power for the turn)?",
    re.IGNORECASE,
)
_PLAY_IMMEDIATE_TOKEN_POST_CREATED_POWER_RE = re.compile(
    r"(?:if [^:]{1,320}:\s*)?when (?:this card is played(?: from your hand)?|you play this card)(?:,\s*if [^,.\[]{1,180})?(?:(?:[^.\[]|\[[^\]]+\])){0,260}?\bplay (?:up to )?(\d+) ([^(\n]+?tokens?)(?: \((\d+) power,\s*(\d+) combo cost,\s*(?:and\s*)?(\d+) combo power\)| with (\d+) power)?(?: in rest mode)?[,;]?\s*and (?:that card|that token|those cards|they) get(?:s)? \+(\d+) power for the turn",
    re.IGNORECASE,
)
_LEADER_PLACED_TRIGGER_RE = re.compile(r"(?:if [^:]{1,160}:\s*)?when this card is placed in your leader area", re.IGNORECASE)
_ATTACK_TRIGGER_RE = re.compile(r"(?:if [^:]{1,120}:\s*)?when this card attacks")
_COMBO_TRIGGER_RE = re.compile(r"(?:if [^:]{1,120}:\s*)?when (?:this card is used in a combo|you combo with this card)")
_COMBO_PLAY_TOKEN_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when (?:this card is used in a combo|you combo with this card)(?: from your (hand|battle area))?(?:[^.\[]){0,220}?\bplay (?:up to )?(\d+) ([^(\n]+?token)(?: \((\d+) power,\s*(\d+) combo cost,\s*(?:and\s*)?(\d+) combo power\)| with (\d+) power)?(?: in rest mode)?(?: in your (opponent'?s )?battle area)?(?:,?\s*and (?:it|that token|that card|they) gain(?:s)? ((?:\[[^\]]+\](?:\s*(?:,|and)\s*)?)+)(?: until the end of (?:your opponent'?s next )?turn| for the turn))?",
    re.IGNORECASE,
)
_COMBO_TRIGGER_FROM_HAND_OPPONENT_BOTTOM_DECK_HAND_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand,\s*your opponent chooses (\d+) cards? in their hand and places? (?:it|them) at the bottom of their deck",
    re.IGNORECASE,
)
_COMBO_TRIGGER_FROM_HAND_SWITCH_OPPONENT_LEADER_OR_BATTLE_REST_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand,\s*choose up to (\d+) of your opponent's leader cards? or battle cards? and switch (?:it|them) to rest mode",
    re.IGNORECASE,
)
_COMBO_TRIGGER_RETURN_OPPONENT_COMBO_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,180}:\s*)?when (?:this card is used in a combo|you combo with this card),\s*choose up to (\d+) cards? in your opponent's combo area and return (?:it|them) to (?:its|their) owner'?s hand",
    re.IGNORECASE,
)
_COMBO_TRIGGER_FROM_HAND_SWITCH_OWNER_ENERGY_ACTIVE_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand,\s*choose up to (\d+) of your (.+?) energy and switch (?:it|them) to active mode",
    re.IGNORECASE,
)
_COMBO_TRIGGER_FROM_HAND_PLACE_DECK_CARD_IN_DROP_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand,\s*choose up to (\d+) (.+?) from your deck,\s*place (?:it|them) in your drop area,\s*then shuffle your deck",
    re.IGNORECASE,
)
_COMBO_TRIGGER_ADD_UP_TO_N_FROM_OWNER_DECK_TO_HAND_RE = re.compile(
    r"when (?:this card is used in a combo|you combo with this card)(?: from your (hand|battle area))?,\s*add up to (\d+) (.+?) from your deck to your hand,\s*then shuffle your deck",
    re.IGNORECASE,
)
_COMBO_TRIGGER_FROM_HAND_SELF_GAIN_COMBO_POWER_PER_DROP_AND_WARP_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand,\s*this card gets \+(\d+) combo power for the duration of the turn for each card in your drop area and warp(?:.*?up to a maximum of (\d+))?",
    re.IGNORECASE,
)
_COMBO_TRIGGER_FROM_HAND_SELF_GAIN_FLAT_COMBO_POWER_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand(?:[^.\[]){0,220}?this card gets \+(\d+) combo power for (?:the duration of the turn|the battle)(?! for each card)",
    re.IGNORECASE,
)
_COMBO_TRIGGER_SELF_GAIN_FLAT_COMBO_POWER_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:this card is used in a combo|you combo with this card)(?: from your (hand|battle area))?(?:[^.\[]){0,220}?this card gets \+(\d+) combo power for (?:the duration of the turn|the battle)(?! for each card)",
    re.IGNORECASE,
)
_COMBO_TRIGGER_FROM_HAND_BUFF_OTHER_COMBO_CARD_RE = re.compile(
    r"(?:if [^:]{1,180}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand(?:[^.\[]){0,220}?choose 1 card (?:(?:other than this card in your combo area)|(?:in your combo area other than this card)) and it gets \+(\d+) combo power for the battle",
    re.IGNORECASE,
)
_COMBO_TRIGGER_BUFF_OWNER_BATTLE_FOR_BATTLE_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when (?:this card is used in a combo|you combo with this card)(?: from your hand)?(?:[^.\[]){0,220}?choose up to (\d+) of your (.+?) cards? and (?:it gets|they get) \+(\d+) power for the battle",
    re.IGNORECASE,
)
_COMBO_TRIGGER_BUFF_ATTACKING_OWNER_BATTLE_WITH_KEYWORD_RE = re.compile(
    r"when (?:this card is used in a combo|you combo with this card)(?: from your (hand|battle area))?,\s*choose up to (\d+) attacking (.+?) card(?:s)? and (?:it|they) gain(?:s)? \[([^\]]+)\] for the duration of the battle",
    re.IGNORECASE,
)
_COMBO_TRIGGER_SELF_GAIN_COMBO_POWER_OPTIONAL_BOTTOM_DECK_DRAW_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when (?:this card is used in a combo|you combo with this card),\s*(?:this card|it) gets \+(\d+) combo power for the battle(?:, then|\.\s*additionally,)?\s*you may (?:(?:choose )?(\d+)\s*card(?:s)?(?: in your hand)? and place (?:it|them)|place (\d+)\s*card(?:s)? from your hand) at the bottom of your deck\.\s*if you do, draw (\d+) cards?",
    re.IGNORECASE,
)
_OWNER_COMBOED_CARD_GAIN_COMBO_POWER_AND_DRAW_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when one of your (.+?) is used in a combo,\s*it gets \+(\d+) combo power for the battle,\s*then draw (\d+) card",
    re.IGNORECASE,
)
_OWNER_COMBO_DRAW_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when (?:one of your|you use) (.+?) in a combo,\s*draw (\d+) card",
    re.IGNORECASE,
)
_OWNER_COMBO_SWITCH_SELF_ACTIVE_RE = re.compile(
    r"(?:if [^:]{1,180}:\s*)?when you use a card in a combo,\s*switch this card to active mode",
    re.IGNORECASE,
)
_OWNER_COMBO_ADD_MARKER_AND_SELF_POWER_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when you use (.+?) in a combo,\s*add a marker to this card and it gets \+(\d+) power for the turn",
    re.IGNORECASE,
)
_OWNER_COMBO_REMOVE_MARKERS_FROM_OPP_UNISON_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when you use (.+?) in a combo,\s*choose up to (\d+) of your opponent'?s unisons? and remove (\d+) markers? from (?:it|them)",
    re.IGNORECASE,
)
_OWNER_COMBO_SEND_OPP_DROP_TO_WARP_ELSE_DRAW_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when you use (.+?) in a combo,\s*your opponent sends (\d+) battle cards? from their drop area to their warp;\s*if there are no battle cards in your opponent'?s drop area,\s*draw (\d+) card",
    re.IGNORECASE,
)
_OWNER_COMBO_PLAY_SELF_FROM_UNDER_LEADER_OR_HAND_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when you use (.+?) in a combo,\s*play this card from under your leader or from your hand",
    re.IGNORECASE,
)
_OWNER_OTHER_BATTLE_PLAYED_PLACE_FROM_OWNER_COMBO_UNDER_OWNER_LEADER_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when your ([^\[]+?) card is played,\s*place up to (\d+) (.+?) from your combo area under your leader",
    re.IGNORECASE,
)
_OWNER_OTHER_BATTLE_PLAYED_PLAY_TOKEN_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when (?:you play|your) (.+?) card(?: in your battle area)?(?: is played)?(?:[^.\[]){0,220}?\bplay (?:up to )?(\d+) ([^(\n]+?tokens?)",
    re.IGNORECASE,
)
_OWNER_OTHER_TOKEN_PLAYED_BY_OWNER_EXTRA_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when a ([^(\n]+?token) is played by the skill on one of your extra cards,\s*play (?:up to )?(\d+) ([^(\n]+?tokens?)(?: with (\d+) power)?(?: in your opponent'?s battle area)?",
    re.IGNORECASE,
)
_OWNER_BATTLE_LEFT_PLACE_FROM_OWNER_DROP_UNDER_OWNER_LEADER_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when your ([^\[]+?) leaves the battle area,\s*place up to (\d+) (.+?) from your drop(?: area)? under your leader",
    re.IGNORECASE,
)
_OWNER_BATTLE_LEFT_PLAY_TOKEN_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when your ([^\[]+?) (?:is )?(?:removed from|leaves) (?:a |the )?battle area(?: by a skill or ko'?d)?[,;]?\s*play (?:up to )?(\d+) ([^(\n]+?token)",
    re.IGNORECASE,
)
_OWNER_BATTLE_LEFT_BY_OPPONENT_SKILL_OPPONENT_DISCARDS_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when one of your battle cards? is removed from your battle area by an opponent'?s skill,\s*your opponent chooses (\d+) cards? in their hand and discards (?:it|them)",
    re.IGNORECASE,
)
_SELF_LEFT_BATTLE_CHOOSE_PLAY_FROM_OWNER_DECK_OR_HAND_OR_DRAW_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when this card is removed from your battle area by an opponent'?s skill or ko'?d,\s*choose one.*?"
    r"choose up to (\d+) (.+?) card with an energy cost of (\d+) from your deck or hand,\s*play it,\s*then shuffle your deck if you looked through it\.\s*.*?draw (\d+) card",
    re.IGNORECASE | re.DOTALL,
)
_SELF_LEFT_BATTLE_CHOOSE_PLAY_FROM_OWNER_DECK_OR_HAND_OR_OPPONENT_DISCARD_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when this card is removed from your battle area by an opponent'?s skill or ko'?d,\s*choose one.*?"
    r"choose up to (\d+) (.+?) card with an energy cost of (\d+) from your deck or hand,\s*play it,\s*then shuffle your deck if you looked through it\.\s*.*?"
    r"your opponent chooses (\d+) cards? in their hand and discards (?:it|them)",
    re.IGNORECASE | re.DOTALL,
)
_OWNER_COMBO_USE_SELF_FROM_BATTLE_IN_COMBO_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when you use (.+?) in a combo,\s*you may use this card from a battle area in a combo\.\s*if you do,\s*play this card from (?:its|their) owner'?s drop at the end of the battle",
    re.IGNORECASE,
)
_OPPONENT_COMBO_BOTTOM_DECK_HAND_AND_NEGATE_SELF_FOR_BATTLE_RE = re.compile(
    r"when your opponent uses cards? in a combo,\s*(?:you opponent|your opponent) places (\d+) cards? from their hand at the bottom of their deck, then you negate this skill for the battle",
    re.IGNORECASE,
)
_COUNTER_DELAYED_TOKEN_RE = re.compile(
    r"(?:additionally,\s*)?at the end of the turn,\s*play (\d+) ([^(\n]+?token)(?: with (\d+) power)?(?: in rest mode)? in your (opponent'?s )?battle area",
    re.IGNORECASE,
)
_COUNTER_IMMEDIATE_TOKEN_RE = re.compile(
    r"(?:negate the attack,\s*then|then)\s*play (\d+) ([^(\n]+?tokens?)(?: \((\d+) power,\s*(\d+) combo cost,\s*(?:and\s*)?(\d+) combo power\)| with (\d+) power)?(?: in rest mode)?(?:,?\s*and (?:it|that token|that card|they) gain(?:s)? ((?:\[[^\]]+\](?:\s*(?:,|and)\s*)?)+)(?: until the end of (?:your opponent'?s next )?turn| for the turn))?",
    re.IGNORECASE,
)
_OWNER_UNION_ACTIVATED_PLAY_TOKEN_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when you activate a \[union\] skill,\s*play (?:up to )?(\d+) ([^(\n]+?token)(?: \((\d+) power,\s*(\d+) combo cost,\s*(?:and\s*)?(\d+) combo power\)| with (\d+) power)?(?: in rest mode)?",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_DELAYED_TOKEN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,360}?at the end of the turn,\s*play (?:up to )?(\d+) ([^(\n]+?token)(?: \((\d+) power,\s*(\d+) combo cost,\s*(?:and\s*)?(\d+) combo power\)| with (\d+) power)?(?: in rest mode)?",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_BATTLE_IMMEDIATE_TOKEN_RE = re.compile(
    r"\[activate(?::)?\s*(main|battle)\].{0,320}?\bplay (?:up to )?(\d+) ([^(\n]+?tokens?)(?: \((\d+) power,\s*(\d+) combo cost,\s*(?:and\s*)?(\d+) combo power\)| with (\d+) power)?(?: in rest mode)?(?:,?\s*and (?:it|that token|that card|they) gain(?:s)? ((?:\[[^\]]+\](?:\s*(?:,|and)\s*)?)+)(?: until the end of (?:your opponent'?s next )?turn| for the turn))?",
    re.IGNORECASE,
)
_TOKEN_THEN_CHOOSE_ALL_OWNER_BATTLE_GAIN_KEYWORD_RE = re.compile(
    r"then choose all of your (.+?) and they gain \[([^\]]+)\](?: until the end of your opponent'?s next turn| until the end of your opponent'?s turn| for the turn)",
    re.IGNORECASE,
)
_MAIN_PHASE_PLAY_TOKEN_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?at the start of your (opponent'?s )?main phase,\s*play (?:up to )?(\d+) ([^(\n]+?tokens?)(?: \((\d+) power,\s*(\d+) combo cost,\s*(?:and\s*)?(\d+) combo power\)| with (\d+) power)?(?: in rest mode)?(?: in your (opponent'?s )?battle area)?",
    re.IGNORECASE,
)
_MAIN_PHASE_PLAY_TOKEN_UNTIL_COUNT_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?at the start of your (opponent'?s )?main phase,\s*play ([^(\n]+?tokens?) until you have (\d+) ([^(\n]+?tokens?) in your battle area",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_THEN_PLAY_TOKEN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?play this card from your hand(?: in rest mode)?,\s*(?:then|and)\s*play (?:up to )?(\d+) ([^(\n]+?token)(?: \((\d+) power,\s*(\d+) combo cost,\s*(?:and\s*)?(\d+) combo power\)| with (\d+) power)?(?: in rest mode)?(?:,?\s*and it gains ((?:\[[^\]]+\](?:\s*(?:,|and)\s*)?)+)(?: until the end of (?:your opponent'?s next )?turn| for the turn))?",
    re.IGNORECASE,
)
_TOKEN_THEN_COMBO_FROM_OWNER_ZONE_RE = re.compile(
    r"play (?:up to )?\d+ [^(\n]+?token(?: \([^)]*\)| with \d+ power)?(?: in rest mode)?,\s*then use up to (\d+) (.+?) from your (drop|warp)(?: area)? in a combo(?: with its skills negated for the turn)?",
    re.IGNORECASE,
)
_TOKEN_THEN_ADD_FROM_OWNER_LIFE_TO_HAND_RE = re.compile(
    r"play (?:up to )?\d+ [^(\n]+?token(?: \([^)]*\)| with \d+ power)?(?: in rest mode)?,\s*then add up to (\d+) cards? from your life to your hand",
    re.IGNORECASE,
)
_PLAY_TOKEN_THEN_PLACE_OPPONENT_BATTLE_UNDER_SELF_RE = re.compile(
    r"play (?:up to )?\d+ [^(\n]+?token(?: \([^)]*\)| with \d+ power)?(?: in rest mode)?,\s*then choose up to (\d+) of your opponent'?s battle cards? and place (?:it|them) under this card",
    re.IGNORECASE,
)
_TOKEN_GAIN_KEYWORDS_RE = re.compile(
    r"play (?:up to )?\d+ [^(\n]+?tokens?(?: \([^)]*\)| with \d+ power)?(?: in rest mode)?(?:[\s\S]{0,120}?)\b(?:it|that token|that card|they)\b gain(?:s)? ((?:\[[^\]]+\](?:\s*(?:,|and)\s*)?)+)",
    re.IGNORECASE,
)
_PLAY_OR_COMBO_DRAW_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card(?: in your hand)? is played or used in a combo.*?draw (\d+) card"
)
_ATTACK_DRAW_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card attacks(?:[^.\[]){0,200}?draw (\d+) card"
)
_ATTACK_PLAY_TOKEN_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card attacks(?:[^.\[]){0,240}?\bplay (?:up to )?(\d+) ([^(\n]+?token)(?: \((\d+) power,\s*(\d+) combo cost,\s*(?:and\s*)?(\d+) combo power\)| with (\d+) power)?(?: in rest mode)?",
    re.IGNORECASE,
)
_ATTACK_PLAY_A_TOKEN_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card attacks(?:[^.\[]){0,240}?\bplay a ([^(\n]+?token)(?: \((\d+) power,\s*(\d+) combo cost,\s*(?:and\s*)?(\d+) combo power\)| with (\d+) power)?(?: in rest mode)?",
    re.IGNORECASE,
)
_ATTACK_ADD_UP_TO_N_FROM_OWNER_LIFE_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card attacks(?:[^.\[]){0,220}?add up to (\d+) cards? from your life to your hand",
    re.IGNORECASE,
)
_LEADER_ATTACK_ADD_LIFE_TO_HAND_THEN_DRAW_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card attacks a leader card,\s*you may choose (?:up to )?(\d+) cards? in your life and add (?:it|them) to your hand\.\s*if you do so,\s*draw (\d+) card",
    re.IGNORECASE,
)
_LEADER_ATTACK_PLACE_UP_TO_N_FROM_OWNER_HAND_INTO_DROP_THEN_DRAW_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card attacks a leader card,\s*you may choose (?:up to )?(\d+) (.+?) (?:in|from) your hand and place (?:it|them) in your drop area\.\s*if you do so,\s*draw (\d+) card",
    re.IGNORECASE,
)
_OWNER_BATTLE_ATTACKS_GAIN_POWER_THEN_ADD_UP_TO_N_FROM_OWNER_DECK_OR_LIFE_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when one of your battle cards attacks,\s*it gets \+(\d+) power for the duration of the turn,\s*then choose up to (\d+) (.+?) from your deck or life and add (?:it|them) to your hand",
    re.IGNORECASE,
)
_SELF_AEGIS_PLACE_TOP_N_FROM_OPPONENT_DECK_IF_NO_OTHER_OWNER_MATCHING_RE = re.compile(
    r"when this card activates \[aegis\],\s*if there are no (.+?) cards? in play in your battle area other than this card,\s*place (\d+) cards? from the top of your opponent'?s deck in their drop area",
    re.IGNORECASE,
)
_FIELD_EXTRA_PLACED_ADD_UP_TO_N_FROM_OWNER_DECK_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card is placed in a battle area,\s*choose up to (\d+) (.+?) from your deck,\s*add (?:it|them) to your hand(?:,\s*then shuffle your deck)?",
    re.IGNORECASE,
)
_FIELD_EXTRA_PLACED_RESTRICT_UP_TO_N_OPPONENT_BATTLE_SKILLS_WHILE_SELF_IN_BATTLE_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card is placed in a battle area,\s*choose up to (\d+) of your opponent'?s battle cards? and (?:it|they) can'?t activate skills while this card is in a battle area",
    re.IGNORECASE,
)
_FIELD_EXTRA_PLACED_GRANT_KEYWORD_TO_UP_TO_N_OWNER_BATTLE_WHILE_SELF_IN_BATTLE_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card is placed in a battle area,\s*choose up to (\d+) of your (.+?) battle cards? and (?:it|they) gains? \[([^\]]+)\] while this card is in a battle area",
    re.IGNORECASE,
)
_ATTACK_PLACE_UP_TO_N_OPPONENT_BATTLE_UNDER_SELF_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card attacks,\s*choose up to (\d+) of your opponent'?s battle cards? and place it under this card",
    re.IGNORECASE,
)
_ATTACK_DISCARD_AND_NEXT_TURN_PLAY_AND_Z_ENERGY_FROM_WARP_RE = re.compile(
    r"send (\d+) cards? from under this card to your warp:\s*when this card attacks,\s*your opponent discards (\d+) cards? from their hand,\s*and at the (?:start|beginning) of your next turn,\s*you choose up to 1 each of (.+?) and (.+?) cards? with an energy cost of (\d+) from your warp,\s*then play up to (\d+) of them and add up to (\d+) of them to your z-energy",
    re.IGNORECASE,
)
_ATTACK_OR_BLOCKER_SWITCH_SELF_ACTIVE_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card attacks or activates the \[blocker\] skill,\s*switch this card to active mode",
    re.IGNORECASE,
)
_ATTACK_MAY_DISCARD_HAND_THEN_SWITCH_UP_TO_N_OWNER_BATTLE_ACTIVE_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card attacks,\s*you may place (\d+) card(?:s)? from your hand in the drop area\.\s*if you do so,\s*choose up to (\d+) (.+?) in your battle area and switch (?:it|them) to active mode",
    re.IGNORECASE,
)
_ATTACK_PAY_LIFE_GAIN_POWER_AND_KEYWORD_RE = re.compile(
    r"add (\d+) cards? from your life to your hand:\s*when this card attacks, it gets \+(\d+) power(?: and \[([^\]]+)\])? for the turn"
)
_OWNER_LEADER_ATTACK_ADD_FROM_HAND_TO_LIFE_RE = re.compile(
    r"when your leader card attacks, you may choose (\d+) (.+?) card in your hand and add it to your life"
)
_OWNER_LEADER_ATTACK_LOOK_TOP_ADD_TO_HAND_RE = re.compile(
    r"when your leader card attacks, look at up to (\d+) cards? from (?:the )?top of your deck, add up to (\d+) (.+?) among them(?:[^.]{0,240})?(?:\s|[-\u2014\u2015])to your hand"
)
_OWNER_LEADER_ATTACK_LOOK_TOP_ADD_DIRECT_TO_HAND_RE = re.compile(
    r"when your leader card attacks, look at up to (\d+) cards? from (?:the )?top of your deck, add up to (\d+) (.+?) to your hand"
)
_LEADER_SELF_ATTACK_LOOK_TOP_ADD_TO_HAND_RE = re.compile(
    r"when this card attacks, look at up to (\d+) cards? from (?:the )?top of your deck, add up to (\d+) (.+?) among them(?:[^.]{0,240})?(?:\s|[-\u2014\u2015])to your hand"
)
_LEADER_SELF_ATTACK_LOOK_TOP_ADD_DIRECT_TO_HAND_RE = re.compile(
    r"when this card attacks, look at up to (\d+) cards? from (?:the )?top of your deck, add up to (\d+) (.+?) to your hand"
)
_COMBO_DRAW_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:(?:this card(?: in your battle area)?) is used in a combo|you combo with this card).*?draw (\d+) card",
    re.IGNORECASE,
)
_ADDED_TO_Z_ENERGY_DRAW_RE = re.compile(
    r"(?:if [^:]{1,180}:\s*)?when this card is added to z-energy,\s*draw (\d+) card",
    re.IGNORECASE,
)
_ADDED_TO_Z_ENERGY_OWNER_BATTLE_GAIN_POWER_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card is added to z-energy,\s*choose up to (\d+) of your (.+?) battle cards? and (?:it gets|they get) \+(\d+) power for the turn",
    re.IGNORECASE,
)
_ADDED_TO_Z_ENERGY_SWITCH_OPPONENT_BOARD_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?(?:when this card attacks or )?when this card is added to z-energy,\s*choose up to (\d+) of your opponent's battle cards? or unisons? and switch (?:it|them) to rest mode",
    re.IGNORECASE,
)
_PLACED_UNDER_OWNER_CARD_POWER_REDUCE_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when this card in your hand,\s*z-energy,\s*or combo area is placed under your (.+?) card,\s*choose up to (\d+) of your opponent's battle cards? and (?:it gets|they get) -(\d+) power for the turn",
    re.IGNORECASE,
)
_PLACED_UNDER_OWNER_LEADER_ADD_DECK_TO_HAND_DISCARD_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when this card in your hand is placed under your (.+?) leader,\s*add up to a total of (\d+) (.+?)[\s-]+from your deck to your hand,\s*place (\d+) card(?:s)? from your hand into your drop(?: area)?,\s*then shuffle your deck",
    re.IGNORECASE,
)
_PLACED_UNDER_OWNER_LEADER_DRAW_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when this card(?: in your (hand|battle area|hand or battle area))? is placed under your (.+?) leader,\s*draw (\d+) card",
    re.IGNORECASE,
)
_PLACED_UNDER_OWNER_LEADER_OWNER_LEADER_GAIN_POWER_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when this card(?: in your (hand|battle area|hand or battle area))? is placed under your (.+?) leader,\s*your leader gets \+(\d+) power for the turn",
    re.IGNORECASE,
)
_SELF_PLACED_INTO_DROP_USE_IN_COMBO_FROM_DROP_RE = re.compile(
    r"(?:if [^:]{1,320}:\s*)?when your leader card'?s skill places this card in a drop area from under your leader(?: card)?,\s*use this card in a combo from your drop area",
    re.IGNORECASE,
)
_SELF_PLACED_INTO_DROP_DRAW_AND_PLAY_SELF_FROM_DROP_RE = re.compile(
    r"(?:if [^:]{1,320}:\s*)?when this card is placed into (?:its|their) owner'?s drop from your hand or from under your leader by your leader'?s skill,\s*draw (\d+) card and play this card from your drop with (\d+) markers? on it",
    re.IGNORECASE,
)
_PLACED_UNDER_OWNER_CARD_GRANT_KEYWORDS_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when this card(?: in your hand| in your z-energy| in your combo area)? is placed under (?:your |a )(.+?),\s*the card on top of this card gains ((?:\[[^\]]+\](?:\s*(?:,|and)\s*)?)*) until the end of your opponent'?s turn",
    re.IGNORECASE,
)
_PLACED_UNDER_OWNER_CARD_PLACE_NAMED_FROM_OWNER_DECK_UNDER_NAMED_HOST_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when this card in your hand is placed under a \{([^}]+)\} in your battle area,\s*place up to (\d+) \{([^}]+)\} from your deck under a \{([^}]+)\} in your battle area,\s*then shuffle your deck",
    re.IGNORECASE,
)
_PLACED_UNDER_OWNER_CARD_PLACE_FROM_OWNER_DECK_UNDER_TARGET_HOST_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when this card in your hand is placed under a \{([^}]+)\} in your battle area,\s*place up to (\d+) (.+?) from your deck under a (.+?) in your battle area,\s*then shuffle your deck",
    re.IGNORECASE,
)
_PLACED_UNDER_OWNER_CARD_SWITCH_OWNER_BOARD_REVEALED_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when this card is placed under a (.+?) card with a \[union\] skill,\s*choose up to (\d+) of your cards? and switch (?:it|them) to revealed mode",
    re.IGNORECASE,
)
_OWNER_CARD_PLACED_UNDER_NAMED_HOST_REST_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when a card is placed under a \{([^}]+)\} in your battle area,\s*choose up to (\d+) of your opponent's battle cards? and switch (?:it|them) to rest mode",
    re.IGNORECASE,
)
_SELF_PLACED_UNDER_BY_UNION_REST_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when this card is placed under another card by \[union\],\s*choose up to (\d+) of your opponent's battle cards?(?:,\s*ignoring \[barrier\])?,\s*and switch (?:it|them) to rest mode",
    re.IGNORECASE,
)
_SELF_PLACED_UNDER_BY_UNION_OPPONENT_NEXT_MAIN_ENERGY_RESTAND_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when this card is placed under another card by \[union\],\s*activate this skill\.\s*at the beginning of your opponent's next main phase,\s*choose up to (\d+) of your (.+?) energy and switch (?:it|them) to active mode",
    re.IGNORECASE,
)
_COMBO_BATTLE_END_PLAY_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?at the end of a battle in which this card (?:was|is) used in a combo(?: from your (?:hand|life|energy|drop area))?.*?play this card from (?:your )?drop"
)
_COMBO_FROM_HAND_BATTLE_END_PLAY_SELF_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?at the end of the battle after you combo with this card from your hand(?:[^.\[]){0,220}?play this card(?: in rest mode)?",
    re.IGNORECASE,
)
_COMBO_FROM_HAND_WITH_OWNER_BATTLE_PLAY_AT_BATTLE_END_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand with (?:an?|1) (.+?) card in battle,\s*play this card at the end of the battle",
    re.IGNORECASE,
)
_COMBO_FROM_HAND_BATTLE_END_ADD_SELF_TO_Z_ENERGY_RE = re.compile(
    r"(?:if [^:]{1,200}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand,\s*add this card from your drop to your z-energy at the end of the battle",
    re.IGNORECASE,
)
_COMBO_FROM_BATTLE_BATTLE_END_ADD_SELF_TO_Z_ENERGY_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card in your battle area is used in a combo,\s*draw \d+ card and add this card to (?:its|their) owner'?s z-energy",
    re.IGNORECASE,
)
_COMBO_FROM_HAND_BATTLE_END_WARP_SELF_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand(?:[^.\[]){0,260}?(?:send this card to|(?:this card )?is sent to) (?:its|their) owner'?s warp at the end of the battle",
    re.IGNORECASE,
)
_ATTACK_COMBO_FROM_OWNER_ZONE_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?(?:whe|when) this card attacks,\s*use up to (\d+) (.+?) from your (drop|warp) in a combo(?:,?\s*and (?:it|they) get -(\d+) combo power)? with (?:its|their) skills? negated for the turn"
)
_ATTACK_COMBO_NAMED_FROM_UNDER_NAMED_HOST_THEN_DRAW_AND_GAIN_KEYWORD_RE = re.compile(
    r"(?:if [^:]{1,180}:\s*)?when this card attacks,\s*use up to (\d+) \{([^}]+)\} under a \{([^}]+)\} in your battle area in a combo\.\s*if you do,\s*draw (\d+) card,\s*and this card gains \[([^\]]+)\] for the battle",
    re.IGNORECASE,
)
_ATTACK_SELF_GAIN_POWER_PER_OWNER_WARP_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card attacks,\s*this card gains \+(\d+) power for each card in your warp"
)
_TURN_END_SWITCH_ACTIVE_RE = re.compile(r"(?:if [^:]{1,120}:\s*)?at the end of your turn, switch this card to active mode")
_TURN_END_PLACE_UP_TO_N_FROM_OWNER_DROP_UNDER_OWNER_LEADER_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?at the end of your turn,\s*place up to (\d+) (.+?) from your drop under your leader",
    re.IGNORECASE,
)
_TURN_END_PLACE_SELF_FROM_UNDER_OWNER_LEADER_ON_TOP_OF_OWNER_LEADER_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?at the end of your (opponent'?s )?turn,\s*place this card from under your (z-leader|leader) on top of your leader",
    re.IGNORECASE,
)
_TURN_END_PLACE_SELF_FROM_OWNER_ENERGY_INTO_DROP_AFTER_LIFE_REVEAL_RE = re.compile(
    r"at the end of your next turn after you place this card in your energy with this skill,\s*if this card is in your energy,\s*place it in (?:its|this card'?s) owner'?s drop(?: area)?",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_DRAW_RE = re.compile(r"\[activate(?::)?\s*main\][^.]{0,200}?(?::\s*)?draw (\d+) card")
_ACTIVATE_BATTLE_DRAW_RE = re.compile(r"\[activate(?::)?\s*battle\][^.]{0,200}?(?::\s*)?draw (\d+) card")
_ACTIVATE_MAIN_REST_NAMED_HOST_PLACE_SELF_AND_NAMED_DECK_UNDER_CHOSEN_RE = re.compile(
    r"\[activate(?::)?\s*main\][^.]{0,160}?(?:\(([^)]*)\))?[^:]{0,220}?choose 1 \{([^}]+)\} in your battle area and switch it to rest mode:\s*place this card from your hand and up to (\d+) \{([^}]+)\} from your deck under the chosen card,\s*then shuffle your deck",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_REST_NAMED_HOST_PLACE_EACH_NAMED_HAND_UNDER_CHOSEN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,420}?choose (?:up to )?1 \{([^}]+)\} in your battle area,\s*switch it to rest mode,\s*place 1 \{([^}]+)\} and 1 \{([^}]+)\} from your hand under the chosen card,\s*then shuffle your deck",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_DRAW_AND_PLAY_NAMED_FROM_OWNER_HAND_UNDER_NAMED_HOST_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?draw (\d+) card and play up to (\d+) \{([^}]+)\} under a \{([^}]+)\} in your battle area",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLACE_N_FROM_OWNER_HAND_UNDER_NAMED_HOST_THEN_DRAW_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?place (\d+) cards? from your hand under a \{([^}]+)\} in your battle area:\s*draw (\d+) cards?",
    re.IGNORECASE,
)
_AUTO_ATTACK_DRAW_ADD_FROM_BATTLE_OR_DROP_TO_Z_ENERGY_THEN_PLACE_FROM_BATTLE_OR_DROP_UNDER_NAMED_HOST_RE = re.compile(
    r"when this card attacks,\s*draw (\d+) card(?:s)?,\s*place this card from the battle area in (?:its|their) owner'?s drop at the end of the battle,\s*choose up to (\d+) (.+?) in your battle area or drop,\s*add it to your z-energy with its skills negated for the turn,\s*then choose up to (\d+) (.+?) in your battle area or drop and place it under \{([^}]+)\} in your battle area",
    re.IGNORECASE,
)
_AUTO_BATTLE_END_OWNER_GREEN_ATTACKER_KO_OPPONENT_BATTLE_PLACE_UNDER_SELF_RE = re.compile(
    r"at the end of a battle where one of your green battle cards attacks and kos? an opponent'?s battle card,\s*place that card under this card from your opponent'?s drop area",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_REST_ANY_NUMBER_OWNER_BATTLES_AND_PLACE_TOP_DECK_UNDER_NAMED_HOST_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,420}?switch this card to rest mode:\s*you may choose any number of your battle cards and switch them to rest mode\.\s*if you do,\s*for each battle card switched to rest mode by this skill other than this card,\s*you may place the top card of your deck under a \{([^}]+)\} in your battle area",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLAY_NAMED_FROM_OWNER_DROP_AND_GAIN_POWER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,360}?play up to (\d+) \{([^}]+)\} from your drop and that card gets \+(\d+) power for the turn",
    re.IGNORECASE,
)
_PLAYED_REST_NAMED_HOST_PLACE_UP_TO_N_EITHER_NAMED_FROM_HAND_UNDER_IT_THEN_KO_IF_PLACED_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?choose 1 \{([^}]+)\} from your battle area,? and switch it to rest mode:\s*when this card is played,\s*place up to (\d+) \{([^}]+)\} or \{([^}]+)\} from your hand under the chosen card\.\s*if you placed a card,\s*choose up to (\d+) of your opponent'?s battle cards? with an energy cost of (\d+) or less and ko it",
    re.IGNORECASE,
)
_LEADER_PLACED_ACTIVATE_UP_TO_N_NAMED_FIELD_EXTRA_FROM_OWNER_DECK_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is placed in your leader area,\s*activate up to (\d+) \{([^}]+)\} from your deck",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_BATTLE_DRAW_RE = re.compile(r"\[activate(?::)?\s*main/battle\][^.]{0,200}?(?::\s*)?draw (\d+) card")
_ACTIVATE_MAIN_BATTLE_CHOOSE_OWNER_CARDS_GAIN_POWER_FOR_TURN_RE = re.compile(
    r"\[activate(?::)?\s*(?:main|main/battle)\].{0,340}?choose (?:up to )?(\d+) of your(?: (.+?))? cards? and (?:it gets|they get) \+(\d+) power for (?:the duration of )?the turn"
)
_ACTIVATE_MAIN_BATTLE_SWITCH_UP_TO_N_OWNER_CARDS_ACTIVE_AND_GAIN_KEYWORD_IF_SELF_SWITCHED_RE = re.compile(
    r"\[activate(?::)?\s*(main/battle|main|battle)\].{0,360}?choose up to (\d+) of your cards,\s*switch them to active mode,\s*and if you switched this card to active mode by this skill,\s*it gains \[([^\]]+)\] for the turn",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_BATTLE_SWITCH_UP_TO_N_OWNER_BATTLE_ACTIVE_GENERAL_RE = re.compile(
    r"\[activate(?::)?\s*(main/battle|main|battle)\].{0,360}?choose up to (\d+) of your(?: (.+?))? battle cards?\s*and switch (?:it|them) to active mode",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_THEN_PLACE_ALL_OPPONENT_REST_BATTLE_AND_UNISON_INTO_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?play this card from your hand\s*then\s*choose all of your opponent'?s rest mode battle cards? and unisons?,\s*ignoring \[barrier\],\s*and place them into their owner'?s drops?",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_REMOVE_SELF_NEGATE_OPPONENT_LEADER_SKILLS_AND_RESTRICT_REST_ACTIVE_RE = re.compile(
    r"\[activate(?::)?\s*main\]\s*remove this card from the game:\s*negate the skills of your opponent'?s leader until the end of your opponent'?s turn,\s*then choose up to (\d+) of your opponent'?s rest mode cards? and (?:it|they) can'?t switch to active mode until the end of your opponent'?s turn",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_DRAW_THEN_CHOOSE_OWNER_CARDS_GAIN_POWER_FOR_TURN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,360}?draw (\d+) card(?:s)?,\s*then choose (?:up to )?(\d+) of your(?: (.+?))? cards? and (?:it gets|they get) \+(\d+) power for (?:the duration of )?the turn",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_CHOOSE_OWNER_LEADER_OR_BATTLE_GAIN_POWER_AND_KEYWORD_FOR_TURN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,360}?choose your leader(?: card)? or (\d+) of your battle cards?,?\s*and it gets \+(\d+) power and \[([^\]]+)\] for (?:the duration of )?the turn",
    re.IGNORECASE,
)
_ACTIVATE_BATTLE_CHOOSE_OWNER_CARDS_GAIN_POWER_FOR_TURN_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,340}?choose up to (\d+) of your (.+?) and (?:it gets|they get) \+(\d+) power for the turn"
)
_ACTIVATE_MAIN_DRAW_LIFE_BOUNCE_AND_OPTIONAL_MAIN_PHASE_ENERGY_SWITCH_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,520}?draw (\d+) card(?:,\s*choose (\d+) card in your life and add it to your hand)?(?:,\s*then|\s*then)?\s*choose up to (\d+) of your opponent's battle cards? with an energy cost of (\d+) and return it to (?:its|their) owner's hand(?:,\s*then at the start of your opponent's next main phase,\s*choose up to (\d+) (.+?) in your energy and switch (?:it|them) to active mode)?",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_DRAW_AND_SWITCH_UP_TO_N_OPPONENT_BATTLE_OR_UNISON_ACTIVE_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,360}?draw (\d+) card(?:s)?,?\s*and choose up to (\d+) of your opponent'?s battle cards? and/or unisons?,?\s*ignoring \[barrier\],?\s*and switch (?:it|them) to active mode",
    re.IGNORECASE,
)
_ACTIVATE_EXTRA_MAIN_BATTLE_PLAY_UP_TO_N_EACH_OF_TWO_FROM_OWNER_DECK_OR_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main/battle\].{0,360}?play up to (\d+) each of <([^>]+)> and <([^>]+)> cards?-both (red|blue|green|yellow|black|white) and with an energy cost of (\d+)-from your deck and/or drop(?: area)?(?: in rest mode)?"
)
_ACTIVATE_EXTRA_MAIN_BATTLE_ADD_UP_TO_N_FROM_OWNER_DECK_TO_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main/battle\].{0,260}?add up to (\d+) (.+?) from your deck to your hand"
)
_ACTIVATE_MAIN_BATTLE_PLACE_UP_TO_N_NAMED_FIELD_EXTRA_FROM_OWNER_Z_DECK_RE = re.compile(
    r"\[activate(?::)?\s*(main/battle|main|battle)\].{0,420}?place up to (\d+) \{([^}]+)\} or \{([^}]+)\} from your z-deck in the battle area",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_IF_DO_DRAW_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?(?::\s*|if you do,\s*)draw (\d+) card"
)
_ACTIVATE_MAIN_BOTTOM_DECK_UP_TO_N_OPPONENT_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?choose up to (\d+) of your opponent'?s battle cards?(?: with an energy cost of (\d+) or less)?(?:,\s*ignoring \[barrier\])?,?\s*and place (?:it|them) at the bottom of (?:its|their) owner'?s deck",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_OPTIONAL_SEND_HAND_TO_WARP_DRAW_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?you may choose (\d+) card in your hand and send it to your warp\.\s*if you do, draw (\d+) card"
)
_ACTIVATE_MAIN_OPPONENT_DISCARDS_N_FROM_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,220}?your opponent discards (\d+) card(?:s)? (?:from )?(?:their|his or her) hand"
)
_ACTIVATE_MAIN_PLACE_UP_TO_N_FROM_UNDER_NAMED_OWNER_BATTLE_INTO_DROP_THEN_OPPONENT_DISCARDS_SAME_COUNT_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,420}?place up to (\d+) cards? from under a \{([^}]+)\} in your battle area in their owners'? drop areas?;\s*your opponent discards cards equal to the number of cards you placed in drop areas this way",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_REVEAL_OPPONENT_HAND_PLAY_UP_TO_N_BATTLE_TO_OPPONENT_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,420}?your opponent reveals their hand,\s*and you choose up to (\d+) battle cards? with an energy cost of (\d+) or less from it and play (?:it|them) in your opponent'?s battle area",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_LOOK_OPPONENT_HAND_PLAY_UP_TO_N_BATTLE_TO_OPPONENT_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,420}?look at your opponent'?s hand and play up to (\d+) battle cards? from it in your opponent'?s battle area(?: in rest mode)?",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_WIN_GAME_IF_OPPONENT_OWNED_UNDER_SELF_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?if there are (\d+) cards? owned by your opponent under this card:\s*you win the game",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_DEAL_DAMAGE_PER_GOD_BATTLE_COLORS_AND_OPTIONAL_WIN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,420}?if your leader card is a <([^>]+)> card:\s*deal (\d+) damage to your opponent for every (\d+) colors? on (?:≪|â‰ª)?([^≫â‰«]+?)(?:≫|â‰«)? cards? in your battle area\.\s*\((\d+) damage max\.\)\s*additionally,\s*if you have (\d+) or more multicolor (?:≪|â‰ª)?([^≫â‰«]+?)(?:≫|â‰«)? cards? in play,\s*you win the game",
    re.IGNORECASE,
)
_OWNER_OPPONENT_ATTACKS_REST_SELF_REDIRECT_TO_MATCHING_OWNER_BATTLE_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?(?:and you switch this card to rest mode:\s*)?when your opponent attacks,\s*choose (?:up to )?1 of your green battle cards in rest mode with the same .*?special trait as your leader card and switch the target of attack to that card",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_DRAW_DISCARD_AND_PLACE_FROM_DROP_UNDER_LEADER_THEN_SWITCH_SELF_ACTIVE_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,420}?draw (\d+) card and discard (\d+) card from your hand\..{0,220}?if your leader is a (.+?)\s+card.{0,220}?place up to (\d+) (.+?)(?:-|\s+)from your drop under your leader,\s*and at the end of the turn,\s*switch this card to active mode",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_DRAW_AND_PLACE_FROM_DECK_OR_DROP_UNDER_LEADER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,420}?draw (\d+) card(?:s)?,\s*place up to (\d+) (.+?)(?:-|\s+)from your deck or drop under your leader",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLACE_SELF_UNDER_MATCHING_OWNER_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?choose up to (\d+) of your (.+?) cards? with an energy cost of (\d+) or more and without cards that have the same name as this card under it,\s*then place this card under it",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLACE_UP_TO_N_OPPONENT_BATTLE_UNDER_HOST_ABOVE_SOURCE_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,360}?if this card is under a (.+?) card:\s*choose up to (\d+) of your opponent's battle cards? and place it under a (.+?) card on top of this card,\s*then switch a (.+?) card on top of this card to active mode at the end of the turn",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_BATTLE_UNDER_DRAW_AND_KO_BY_HOST_POWER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?this card is under a (.+?) battle card:\s*draw (\d+) card(?:s)?,\s*choose up to (\d+) of your opponent's battle cards? with power less than or equal to the card on top of this card,\s*then ko (?:it|them)",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLACE_SELF_UNDER_OWNER_BATTLE_DRAW_AND_BOUNCE_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,340}?choose (?:up to )?(\d+) of your (.+?) battle cards?(.*?)and place this card under it:\s*draw (\d+) card(?:s)?,\s*then choose up to (\d+) of your opponent's battle cards? and return (?:it|them) to (?:its|their) owner'?s hand",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLACE_SELF_UNDER_MATCHING_OWNER_BATTLE_THEN_BOTTOM_DECK_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?place this card under a (.+?) battle card:\s*choose up to (\d+) of your opponent's battle cards? and place it at the bottom of (?:its|their) owner'?s deck",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLACE_SELF_UNDER_OWNER_BATTLE_THEN_PLAY_FROM_OWNER_DECK_OR_HAND_ON_TOP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,460}?"
    r"choose(?: up to)? (\d+) (?:of your )?(.+?) cards? with an energy cost of (\d+)(?: or (\d+))?(?: in your battle area)? and place this card under it:\s*"
    r"(?:play|choose) up to (\d+) (.+?) (?:from|in) your deck or hand(?:,\s*play (?:it|them))? on top of the chosen card in active mode",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLACE_SELF_UNDER_OWNER_BATTLE_THEN_PLAY_FROM_OWNER_DECK_OR_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,460}?"
    r"choose(?: up to)? (\d+) (?:of your )?(.+?) cards? with an energy cost of (\d+)(?: or (\d+))?(?: in your battle area)? and place this card under it:\s*"
    r"choose up to (\d+) (.+?) (?:from|in) your deck or hand,\s*play (?:it|them),\s*then shuffle your deck if you looked through it",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLACE_SELF_IN_OWNER_DROP_THEN_PLAY_FROM_OWNER_DECK_OR_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\](?:\([^)]*\))?,?\s*if your leader card is a (.+?) card and you place this card in (?:its|their) owner'?s drop area:\s*"
    r"choose up to (\d+) (.+?) card with an energy cost (?:(?:between (\d+) and (\d+))|(?:of (\d+) or (\d+))|(?:of (\d+))) (?:in|from) your deck or hand,\s*"
    r"play it,\s*then shuffle your deck if you looked through it\.?",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLAY_UP_TO_N_FROM_OWNER_Z_DECK_OR_Z_ENERGY_RE = re.compile(
    r"\[(?:\+|-)?\d+\]\s*\[activate(?::)?\s*main\].{0,360}?play up to (\d+) (.+?) from your z-deck or z-energy(?: with (?:its|their) skills negated for the game)?"
)
_ACTIVATE_BATTLE_SELF_GAIN_POWER_AND_KEYWORD_FOR_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?this card gets \+(\d+) power and \[([^\]]+)\] for (?:the|this) battle"
)
_ACTIVATE_BATTLE_SELF_GAIN_POWER_FOR_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?this card gets \+(\d+) power for (?:the|this) battle",
    re.IGNORECASE,
)
_ACTIVATE_BATTLE_OWNER_LEADER_GAIN_POWER_AND_KEYWORD_FOR_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?if your leader(?: card)? is .{0,140}?, it gets \+(\d+) power and \[([^\]]+)\] for (?:the|this|the duration of the) battle"
)
_ACTIVATE_BATTLE_CHOOSE_OWNER_LEADER_GAIN_POWER_FOR_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?up to \d+ of your leaders? gets \+(\d+) power for the battle",
    re.IGNORECASE,
)
_ACTIVATE_BATTLE_OWNER_LEADER_GAIN_KEYWORD_FOR_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?your leader gains \[([^\]]+)\] for the battle",
    re.IGNORECASE,
)
_ACTIVATE_BATTLE_CHOOSE_OWNER_CARDS_GAIN_POWER_FOR_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?choose up to (\d+) of your(?: (.+?))? cards? and (?:it gets|they get) \+(\d+) power for (?:the|this) battle"
)
_ACTIVATE_BATTLE_CHOOSE_CARD_GAIN_POWER_FOR_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,220}?choose up to (\d+) (.+?) card and it gets \+(\d+) power for the battle",
    re.IGNORECASE,
)
_ACTIVATE_BATTLE_CHOOSE_OWNER_CARDS_GAIN_KEYWORD_FOR_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?choose up to (\d+) of your(?: (.+?))? cards? and (?:it gains|they gain) \[([^\]]+)\] for the battle",
    re.IGNORECASE,
)
_ACTIVATE_BATTLE_USE_SELF_FROM_DROP_IN_COMBO_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,260}?use this card from your drop in a combo",
    re.IGNORECASE,
)
_ACTIVATE_BATTLE_SELF_GAIN_POWER_PER_OWNER_WARP_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?for each card in your warp,\s*this card gets \+(\d+) power for the battle"
)
_ACTIVATE_BATTLE_SWITCH_SELF_ACTIVE_AND_GAIN_POWER_FOR_TURN_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,240}?switch this card to active mode and it gets \+(\d+) power for the turn"
)
_ACTIVATE_BATTLE_SWITCH_UP_TO_N_OWNER_BATTLE_ACTIVE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,340}?choose up to (\d+) of your (.+?) cards? with energy costs? of (\d+) and (\d+) power or less in your battle area and switch (?:it|them) to active mode"
)
_ACTIVATE_MAIN_CHOOSE_ALL_OWNER_BATTLE_GAIN_KEYWORD_UNTIL_OPP_TURN_END_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,300}?choose all (.+?) cards? in your battle area\.\s*they gain \[([^\]]+)\].{0,160}?until the end of your opponent'?s next turn"
)
_ACTIVATE_MAIN_GRANT_NEXT_EX_EVOLVE_FROM_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?the next time you activate \[ex-evolve\] on your (.+?) card during this turn,\s*it can also activate from (?:its|their) owner'?s drop"
)
_ACTIVATE_MAIN_BATTLE_REDUCE_NEXT_EXTRA_SKILL_COST_RE = re.compile(
    r"\[activate(?::)?\s*main/battle\].{0,360}?the next time you activate an? \[activate\] skill on an? (.+?) extra from your hand during this turn,\s*reduce the skill cost by \{?(\d+)\}?"
)
_ACTIVATE_MAIN_BATTLE_REDUCE_NEXT_ARRIVAL_SKILL_COST_RE = re.compile(
    r"\[activate(?::)?\s*(main|battle)\].{0,420}?the next time (?:you|your) activate \[arrival\s+([^\]]+)\] on (.+?) card(?: with an energy cost of (\d+))? in your hand(?: during this turn)?[,:]\s*reduce the skill cost by (?:\{([^}]+)\}|\(([^)]+)\)|(\d+))",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_BATTLE_REDUCE_NEXT_Z_AWAKEN_COST_RE = re.compile(
    r"\[activate(?::)?\s*(main|battle)\].{0,420}?reduce the \[z-awaken\] skill cost (?:on|of) (.+?) in your z-deck by (?:\{([^}]+)\}|\(([^)]+)\)|(\d+))(?: and reduce its z-energy cost by (\d+))?.{0,40}?for the turn",
    re.IGNORECASE,
)
_AUTO_ON_PLAY_REDUCE_NEXT_Z_AWAKEN_COST_RE = re.compile(
    r"when this card is played.{0,420}?reduce the \[z-awaken\] skill cost (?:on|of) (.+?) in your z-deck by (?:\{([^}]+)\}|\(([^)]+)\)|(\d+))(?: and reduce its z-energy cost by (\d+))?.{0,40}?for the turn",
    re.IGNORECASE,
)
_AUTO_ON_PLAY_GRANT_NEXT_MATCHING_UNION_PLAY_KEYWORD_RE = re.compile(
    r"when this card is played.{0,420}?during this turn,\s*the next time you play (.+?) card with \[union\],\s*it gains \[([^\]]+)\] for the turn",
    re.IGNORECASE,
)
_ACTIVATE_BATTLE_KO_UP_TO_N_OPP_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?choose up to (\d+) of your opponent'?s battle cards?\s*(?:,|and|then)?\s*ko (?:it|them)"
)
_ACTIVATE_MAIN_KO_UP_TO_N_OPP_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,360}?choose (?:up to )?(\d+) of your opponent'?s battle cards?\s*(?:,|and|then)?\s*ko (?:it|them)",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_LOOK_TOP_ADD_TO_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?look at up to (\d+) cards? from (?:the )?top of your deck,\s*(?:add|choose) up to (\d+) (.+?) among them(?:[^.]{0,240})?(?:\s|[â€”â€•-])to your hand"
)
_ACTIVATE_MAIN_LOOK_TOP_SEND_TO_OWNER_WARP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?look at up to (\d+) cards? from (?:the )?top of your deck, send up to (\d+) (.+?) among them to (?:its|their) owner'?s warp"
)
_ACTIVATE_MAIN_LOOK_TOP_SEND_DIRECT_TO_OWNER_WARP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?look at up to (\d+) cards? from (?:the )?top of your deck, send up to (\d+) (.+?) to (?:its|their) owner'?s warp"
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,240}?play this card from your hand"
)
_ACTIVATE_MAIN_GAIN_KEYWORD_FROM_UNDER_SELF_UNTIL_OPPONENT_TURN_END_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?choose up to \d+ keyword skill on a card placed under this card,\s*and this card gains that skill until the end of your opponent'?s next turn",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_THEN_SWITCH_UP_TO_N_OPPONENT_BATTLE_REST_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,360}?play this card from your hand,\s*then choose up to (\d+) of your opponent'?s battle cards? and switch (?:it|them) to rest mode",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_THEN_REVEAL_AND_PLACE_UNDER_SELF_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,420}?play this card from your hand,\s*choose up to (\d+) card in your opponent'?s battle area and switch it to revealed mode,\s*then choose up to (\d+) of your opponent'?s battle cards? and place it under this card",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_AND_PLACE_MATCHING_OWNER_BATTLE_UNDER_SELF_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?choose (\d+) (.+?) card in your battle area:\s*play this card from your hand and place the chosen card under it",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLACE_SELF_UNDER_OWNER_LEADER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?place this card under your leader(?: card)?\.?\s*$",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_MOVE_UNDER_LEADER_TO_Z_ENERGY_THEN_PLACE_SELF_FROM_DROP_UNDER_OWNER_LEADER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?you may add (\d+) (red|blue|green|yellow|black|white) (extra|battle|unison|z-extra|z-battle|z-unison)s? from under your leader to your z-energy\. if you do, place this card from your drop under your leader",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_UNDER_LEADER_THEN_KO_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,360}?play this card from under (?:(?:your )?\{([^}]+)\}|your <([^>]+)> leader|your leader),\s*then choose up to (\d+) of your opponent'?s battle cards?(.+?)ko (?:it|them)",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_UNDER_LEADER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?play this card from under (?:(?:your )?\{([^}]+)\}|your <([^>]+)> leader|your leader)\.?\s*$",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLACE_SELF_FROM_UNDER_LEADER_ON_TOP_OF_LEADER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,420}?if (?:a|an)\s+(?:<([^>]+)>|\{([^}]+)\}) card is under your leader and you place (\d+) card(?:s)? from under (?:a|an|your)\s+(.+?) card in your battle area in (?:its|their) owner'?s drop:\s*place this card from under your leader on top of your leader(?:,\s*and if you placed a card,\s*you may switch your leader to active mode)?",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_REMOVE_SELF_AND_PLACE_FROM_UNDER_LEADER_ON_TOP_OF_LEADER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,420}?if there are (\d+) or more cards under a \{([^}]+)\} in your battle area:\s*remove this card from the game,\s*place up to (\d+) (.+?) from under your leader on top of your leader(?:,\s*and if you placed a card,\s*you may switch your leader to active mode)?",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_BATTLE_PLAY_UP_TO_N_FROM_UNDER_SELF_AND_PLACE_SELF_UNDER_PLAYED_RE = re.compile(
    r"\[activate(?::)?\s*(main|battle)\].{0,420}?play up to (\d+) (.+?) from under this card,\s*and place this card under the played card"
)
_ACTIVATE_MAIN_BATTLE_PLAY_SELF_FROM_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main/battle\].{0,320}?play this card from your hand"
)
_ACTIVATE_MAIN_BATTLE_PLAY_SELF_FROM_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main/battle\].{0,360}?play this card from your drop(?: area)?",
    re.IGNORECASE,
)
_ACTIVATE_BATTLE_SEND_UP_TO_N_OPPONENT_COMBO_TO_DROP_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?choose up to (\d+) battle cards? with a combo cost of (\d+) in your opponent'?s combo area and place (?:it|them) in (?:its|their) owner'?s drop area",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_SELF_GAIN_POWER_THEN_RETURN_UP_TO_N_OPPONENT_BATTLE_TO_HAND_RE = re.compile(
    r"\[[+-]\d+\]\[activate(?::)?\s*main\].{0,320}?this card gets \+(\d+) power for the turn,\s*then choose up to (\d+) of your opponent'?s battle cards? with an energy cost of (\d+) or less and return (?:it|them) to (?:its|their) owner'?s hand",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_OPPONENT_CHOOSES_N_HAND_TO_WARP_RE = re.compile(
    r"\[[+-]\d+\]\[activate(?::)?\s*main\].{0,220}?your opponent chooses (\d+) cards? in their hand and sends (?:it|them) to their warp",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_KO_UP_TO_N_OPPONENT_BATTLE_AT_LEAST_CURRENT_ENERGY_RE = re.compile(
    r"\[[+-]\d+\]\[activate(?::)?\s*main\].{0,260}?choose up to (\d+) of your opponent'?s battle cards? with energy costs? greater than or equal to their current energy and ko them",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLACE_SELF_UNDER_OWNER_LEADER_IF_DO_PLAY_UP_TO_N_FROM_DECK_RE = re.compile(
    r"\[[+-]\d+\]\[activate(?::)?\s*main\].{0,420}?you may place this card under your leader card\.\s*if you do,\s*play up to (\d+) (.+?) with (\d+) power or less from your deck,\s*then shuffle your deck",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLAY_UP_TO_N_FROM_OWNER_HAND_WITH_ORIGINAL_COST_RE = re.compile(
    r"\[[+-]\d+\]\[activate(?::)?\s*main\].{0,360}?choose up to (\d+) (.+?) with an original energy cost of (\d+) in your hand and play it\.?",
    re.IGNORECASE,
)
_AUTO_OWNER_ACTIVATE_EXTRA_FROM_HAND_ADD_MARKERS_RE = re.compile(
    r"\[auto\].{0,220}?when you activate an? (.+?) extra from your hand,\s*add (\d+) marker(?:s)? to this card"
)
_ACTIVATE_BATTLE_PLAY_SELF_FROM_HAND_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?play this card from your hand(?:,\s*then your opponent discards (\d+) card from their hand)?"
)
_ACTIVATE_BATTLE_ADD_UP_TO_N_FROM_OWNER_DECK_TO_HAND_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?add up to (\d+) (.+?) from your deck to your hand",
    re.IGNORECASE,
)
_ACTIVATE_BATTLE_PLAY_SELF_FROM_UNDER_LEADER_AND_BOTTOM_DECK_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,360}?play this card from under (?:(?:your )?\{([^}]+)\}|your <([^>]+)> leader|your leader),\s*and at the end of the turn,\s*if this card is in play,\s*place it at the bottom of (?:its|this card'?s) owner'?s deck",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_WARP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,240}?play this card from your warp"
)
_ACTIVATE_MAIN_SEND_SELF_TO_WARP_PLAY_SELF_NEXT_TURN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?send this card to (?:(?:the )?warp|(?:(?:its|their)\s+)?owner'?s warp)\s*:\s*at the beginning of your next turn(?:[^.]{0,200})?play this card from the warp in (?:its|their) owner'?s battle area",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_SEND_SELF_TO_WARP_AND_PLAY_SELF_NEXT_TURN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?send this card to (?:(?:the )?warp|(?:(?:its|their)\s+)?owner'?s warp),\s*and play (?:this card|it) from the warp in (?:its|their) owner'?s battle area at the (?:beginning|start) of your next turn",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_SEND_SELF_TO_WARP_PLAY_UP_TO_N_FROM_OWNER_HAND_THEN_RETURN_SELF_NEXT_TURN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,420}?send this card to (?:(?:the )?warp|(?:(?:its|their)\s+)?owner'?s warp)\s*:\s*choose up to (\d+) (.+?) (?:from|in) your hand and play it\.\s*at the (?:start|beginning) of your next turn,\s*add this card to your hand from your warp",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_SEND_SELF_FROM_HAND_TO_WARP_AND_PLAY_SELF_OPPONENT_NEXT_TURN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?send this card from your hand to (?:(?:your|the) warp|(?:its|their )?owner'?s warp)\s*:\s*at the end of your opponent'?s next turn,\s*play the card you sent to your warp with this skill from your warp",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_ACTIVATE_UP_TO_N_NAMED_FIELD_EXTRA_FROM_OWNER_DECK_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?activate up to (\d+) \{([^}]+)\} from your deck(?:,\s*shuffle your deck)?(?:,\s*and negate this skill for the game)?",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_ACTIVATE_UP_TO_N_NAMED_FIELD_EXTRA_FROM_OWNER_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?choose (?:up to )?(\d+) \{([^}]+)\} in your drop area and activate it",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_WARP_WITH_MARKERS_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?play this card with (\d+) markers? on it from your warp"
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_OR_WARP_WITH_MARKERS_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?play this card with (\d+) markers? on it from your hand or warp"
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_IN_REST_MODE_WITH_MARKERS_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?play this card from your hand in rest mode with (?:(\d+) markers?|a marker) on it",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_DRAW_GAIN_KEYWORD_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,240}?draw (\d+) card(?:s)?[,;]?\s*and this card gains \[([^\]]+)\] for the turn"
)
_ACTIVATE_MAIN_SELF_GAIN_POWER_AND_KEYWORD_FOR_TURN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?this card gets \+(\d+) power and \[([^\]]+)\] for (?:the duration of the |the )turn"
)
_ACTIVATE_MAIN_SELF_GAIN_KEYWORDS_FOR_TURN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?this card gains \[([^\]]+)\](?: and \[([^\]]+)\])(?: and \[([^\]]+)\])? for the turn"
)
_ACTIVATE_DRAW_PLAY_SELF_AND_GAIN_KEYWORD_UNTIL_OPP_TURN_END_RE = re.compile(
    r"\[activate(?::)?\s*(main|battle)\].{0,360}?draw (\d+) card(?:s)?[,;]?\s*play this card from your hand[,;]?\s*and this card gains \[([^\]]+)\] until the end (?:of|fo) your opponent'?s turn"
)
_ACTIVATE_BATTLE_DRAW_SWITCH_SELF_ACTIVE_AND_POWER_REDUCE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,360}?draw (\d+) card(?:s)?[,;]?\s*switch this card to active mode[,;]?\s*then choose up to (\d+) of your opponent'?s battle cards? and (?:it gets|they get) -(\d+) power for the turn"
)
_ACTIVATE_MAIN_DROP_OWNER_HIDDEN_MODE_DRAW_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?choose 1 hidden mode card in your battle area and place it into (?:its|that card's) owner'?s drop:\s*draw (\d+) card"
)
_ACTIVATE_MAIN_SWITCH_OWNER_BATTLE_TO_HIDDEN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?choose 1 of your (.+?) battle cards? and switch it to hidden mode"
)
_ACTIVATE_MAIN_SWITCH_SELF_TO_HIDDEN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,220}?switch this card to hidden mode"
)
_ACTIVATE_MAIN_SELF_GAIN_HIDDEN_COST_TARGET_FRONT_POWER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?choose 1 of your (.+?) battle cards? and switch it to hidden mode:\s*increase this card'?s power by the original power on the front of the card that was switched to hidden mode by this skill for the turn"
)
_ACTIVATE_BATTLE_SELF_GAIN_POWER_AND_KEYWORD_FOR_TURN_RE = re.compile(
    r"(?:\[[^\]]+\])*\[activate(?::)?\s*battle\].{0,220}?this card gets \+(\d+) power and \[([^\]]+)\] for (?:the duration of )?the turn",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_OWNER_TARGET_GAIN_HIDDEN_COST_TARGET_FRONT_POWER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,380}?choose 1 of your (.+?) battle cards? and switch it to hidden mode:\s*choose up to 1 of your leaders? or up to 1 of your (.+?) battle cards? and increase that card'?s power by the original power on the front of the card that was switched to hidden mode by this skill for the turn"
)
_ACTIVATE_MAIN_KO_OPP_BATTLE_AND_BUFF_OWNER_LEADER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,380}?choose 1 (.+?) card in your battle area or energy and switch it to hidden mode:\s*choose up to 1 of your opponent'?s battle cards?, ko it, and your (.+?) leader gets \+(\d+) power for the turn"
)
_ACTIVATE_MAIN_BUFF_OWNER_LEADER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,380}?choose up to 1 of your leaders?,?\s*and it gets \+(\d+) power for the turn",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_BUFF_OWNER_LEADER_AND_RESTRICT_MATCHING_OPP_ATTACK_RE = re.compile(
    r"(?:\[[^\]]+\])*\[activate(?::)?\s*main\].{0,220}?1 of your (.+?) leader(?: cards?)? gets \+(\d+) power for the turn;\s*your opponent'?s (.+?) can'?t attack during your opponent'?s next turn",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_SEND_UP_TO_N_OPP_BATTLE_TO_WARP_RE = re.compile(
    r"\[activate(?::)?\s*main(?:/battle)?\].{0,320}?choose up to (\d+) of your opponent'?s battle cards?(?:[^.]{0,220})?send (?:it|them) to (?:the warp|(?:its|their) owner'?s warp)"
)
_COUNTER_ATTACK_SEND_UP_TO_N_ATTACKING_BATTLE_TO_WARP_RE = re.compile(
    r"\[counter(?::)?\s*attack\].{0,320}?choose up to (\d+) attacking battle cards?(?:[^.]{0,220})?send (?:it|them) to (?:the warp|(?:its|their) owner'?s warp)",
    re.IGNORECASE,
)
_COUNTER_ATTACK_DRAW_AND_SEND_UP_TO_ONE_EACH_FROM_ALL_BATTLES_TO_WARP_RE = re.compile(
    r"\[counter(?::)?\s*attack\].{0,360}?draw (\d+) card(?:s)?,\s*then choose up to 1 each of (.+?) and (.+?) cards? from among all the cards in you and your opponent'?s battle areas and send (?:it|them) to their owners'? warps",
    re.IGNORECASE,
)
_PLAY_CARD_SENT_TO_WARP_BY_SOURCE_SKILL_LATER_RE = re.compile(
    r"at the end of your opponent'?s next turn,\s*play the card sent to (?:the|their) warp (?:by|with) this skill(?: from (?:the|your) warp)? (?:in|to) (?:its|their)(?: owner'?s)? battle area(?: with its skills negated for the turn)?(?: in rest mode)?",
    re.IGNORECASE,
)
_PLAY_ALL_WARPED_BY_SOURCE_SKILL_AT_OPPONENT_NEXT_TURN_END_RE = re.compile(
    r"at the end of your opponent'?s next turn,\s*(?:negate the skills of all cards? sent to a? warp(?:s)? by this skill for the turn and )?play (?:(?:any|all) cards? sent to a? warp(?:s)? by this skill|them) (?:to|into|in) their owners'? battle areas(?: with their skills negated for the turn)?(?: in rest mode)?",
    re.IGNORECASE,
)
_PLAY_ALL_WARPED_BY_SOURCE_SKILL_LATER_RE = re.compile(
    r"at the end of the turn,\s*(?:negate the skills of all cards? sent to a? warp(?:s)? by this skill for the turn and )?play (?:(?:any|all) cards? sent to a? warp(?:s)? by this skill|them) (?:to|into) their owners'? battle areas(?: with their skills negated for the turn)?(?: in rest mode)?",
    re.IGNORECASE,
)
_COUNTER_PLAY_CARD_SENT_TO_WARP_BY_SOURCE_SKILL_LATER_RE = re.compile(
    r"at the end of the turn,\s*your opponent plays the card sent to the warp (?:by|with) this skill(?: from the warp)? in (?:its|their) owner'?s battle area(?: in rest mode)?",
    re.IGNORECASE,
)
_COUNTER_PLAY_ALL_WARPED_BY_SOURCE_SKILL_LATER_RE = re.compile(
    r"at the end of the turn,\s*play all the cards sent to (?:their owners'? )?warps? by this skill into their owners'? battle areas wi?t[h]? their skills negated for the turn",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_SEND_UP_TO_N_OPP_DROP_BATTLE_TO_WARP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?send up to (\d+) battle cards? from your opponent'?s drop area to their warp"
)
_ACTIVATE_MAIN_SEND_TOP_DECK_TO_OWNER_WARP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,220}?send up to (\d+) cards? from (?:the )?top of your deck to (?:its|their) owner'?s warp(?: and switch this card to active mode)?"
)
_ACTIVATE_MAIN_ADD_UP_TO_N_FROM_OWNER_WARP_TO_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?add up to (\d+) (.+?) from your warp to your hand"
)
_ACTIVATE_MAIN_PLACE_SELF_UNDER_NAMED_OWNER_BATTLE_THEN_ADD_FROM_DECK_TO_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,360}?choose 1 \{([^}]+)\} in your battle area:\s*place this card under the chosen card,\s*add up to (\d+) \{([^}]+)\} from your deck to your hand(?:,\s*then shuffle your deck)?",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_REST_ACTIVE_OPP_CARD_ELSE_GAIN_CONTROL_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,460}?if your leader card is (.+?) and you choose 1 of your opponent'?s cards? in active mode:\s*your opponent may switch the chosen card to rest mode\.\s*if they don'?t,\s*choose up to (\d+) of your opponent'?s battle cards? and gain control of it",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_SEND_SELF_TO_WARP_OPPONENT_CHOOSE_BATTLE_KO_IF_NOT_TRAIT_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?send this card to its owner'?s warp:\s*your opponent chooses 1 of their battle cards?;\s*if it'?s a non-(?:≪|â‰ª)?([^≫â‰«]+?)(?:≫|â‰«)? card,\s*ko it",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_SWITCH_OWNER_BOARD_TO_REVEALED_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?choose 1 card in your battle area and switch it to revealed mode"
)
_ACTIVATE_MAIN_SWITCH_ALL_OPP_BATTLE_TO_REVEALED_THEN_KO_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?choose all the cards? in your opponent'?s battle area and switch (?:it|them) to revealed mode,\s*then choose up to (\d+) of your opponent'?s battle cards? and ko (?:it|them)"
)
_ATTACK_SWITCH_UP_TO_N_OPP_BATTLE_HIDDEN_THEN_REVEAL_OPP_TURN_END_RE = re.compile(
    r"when this card attacks, choose up to (\d+) of your opponent'?s battle cards?, switch (?:it|them) to hidden mode, then switch (?:it|them) to revealed mode at the end of your opponent'?s turn"
)
_PLAY_SWITCH_UP_TO_N_OPP_BATTLE_HIDDEN_THEN_REVEAL_TURN_END_RE = re.compile(
    r"when this card is played(?: from your hand)?(?:[^.]{0,180})?choose up to (\d+) of your opponent'?s battle cards?, switch (?:it|them) to hidden mode, then switch (?:it|them) to revealed mode at the end of the turn"
)
_PLAY_SWITCH_UP_TO_N_OWNER_BOARD_TO_REVEALED_RE = re.compile(
    r"when this card is played(?: from your hand)?(?:[^.]{0,200})?choose up to (\d+) (?:(?:of your )?(.*?) )?cards? in your battle area and switch (?:it|them) to revealed mode"
)
_PLAY_SWITCH_UP_TO_N_ANY_PLAYER_BOARD_TO_REVEALED_RE = re.compile(
    r"when this card is played(?: from your hand)?(?:[^.]{0,200})?choose up to (\d+) player'?s cards? and switch (?:it|them) to revealed mode"
)
_PLAY_SWITCH_UP_TO_N_OWNER_BATTLE_TO_HIDDEN_RE = re.compile(
    r"when this card is played(?: from your hand)?(?:[^.]{0,200})?choose up to (\d+) (?:(?:of your )?(.*?) )?cards?(?: in your battle area)? and switch (?:it|them) to hidden mode"
)
_PLAY_FROM_UNDER_BY_SKILL_GAIN_POWER_AND_KEYWORD_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played from under a card by a skill,\s*this card gets \+(\d+) power and \[([^\]]+)\] for the turn"
)
_PLAYED_UNDER_NAMED_HOST_GAIN_POWER_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played under a \{([^}]+)\} in your battle area,\s*this card gets \+(\d+) power for the turn",
    re.IGNORECASE,
)
_PLAYED_UNDER_NAMED_HOST_GAIN_POWER_AND_COMBO_REST_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played under a \{([^}]+)\} in your battle area,\s*this card gets \+(\d+) power and you may use this card in a combo in rest mode for the turn",
    re.IGNORECASE,
)
_MAIN_PHASE_PLAY_FROM_UNDER_SELF_AND_PLACE_SELF_UNDER_PLAYED_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?at the start of your (opponent'?s )?main phase,\s*play up to (\d+) (.+?) from under this card,\s*and place this card under the played card"
)
_MAIN_PHASE_PLAY_FROM_OWNER_HAND_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?at the start of your (opponent'?s )?main phase,\s*play up to (\d+) (.+?) from your hand(?: in rest mode)?"
)
_MAIN_PHASE_PLAY_FROM_OWNER_DROP_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?at the start of your (opponent'?s )?main phase,\s*play up to (\d+) (.+?) from your drop(?: area)?(?: in rest mode)?"
)
_MAIN_PHASE_PLAY_FROM_OWNER_DECK_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?at the start of your (opponent'?s )?main phase,\s*play up to (\d+) (.+?) from your deck(?: with (\d+) markers? on it)?(?: in rest mode)?(?:,\s*then shuffle your deck)?"
)
_MAIN_PHASE_PLAY_FROM_OWNER_HAND_ON_TOP_OF_SELF_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?at the start of your (opponent'?s )?main phase,\s*choose up to (\d+) (.+?) in your hand and play it on top of this card"
)
_MAIN_PHASE_DRAW_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?at the start of your (opponent'?s )?main phase,\s*draw (\d+) card"
)
_MAIN_PHASE_DRAW_SWITCH_LEADER_AND_ENERGY_ACTIVE_AND_GRANT_KEYWORD_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?at the start of your (opponent'?s )?main phase,\s*draw (\d+) card,\s*switch up to (\d+) of your leaders? and up to (\d+) of your energy to active mode,\s*and your leader gains \[([^\]]+)\] for the turn"
)
_MAIN_PHASE_SWITCH_UP_TO_N_OWNER_ENERGY_ACTIVE_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?at the start of your (opponent'?s )?main phase,\s*choose up to (\d+) of your(?: (.+?))? energy and switch (?:it|them) to active mode"
)
_MAIN_PHASE_SWITCH_SELF_ACTIVE_AND_GAIN_KEYWORD_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?at the start of your (opponent'?s )?main phase,\s*switch this card to active mode,\s*and it gains \[([^\]]+)\] for the turn"
)
_PLAY_BUFF_UP_TO_N_OWNER_BATTLE_WITH_MIN_CHAR_NAMES_GAIN_KEYWORD_UNTIL_OPP_TURN_END_RE = re.compile(
    r"when this card is played(?: from your hand)?(?:[^.]{0,220})?choose up to (\d+) of your battle cards with (\d+) or more character names including <([^>]+)> and (?:it|they) gain(?:s)? \[([^\]]+)\] until the end of your opponent'?s turn"
)
_PLAY_DRAW_AND_SWITCH_SELF_TO_HIDDEN_RE = re.compile(
    r"when this card is played(?: from your hand)?(?:[^.]{0,120})?draw (\d+) card(?:s)? and switch this card to hidden mode"
)
_SWITCHED_TO_HIDDEN_OWNER_LEADER_GAIN_POWER_UNTIL_OPP_TURN_END_RE = re.compile(
    r"when this card in a battle area is switched to hidden mode by one of your skills,\s*your leader gets \+(\d+) power until the end of your opponent'?s turn"
)
_SWITCHED_TO_HIDDEN_OWNER_CARD_GAIN_KEYWORD_UNTIL_OPP_TURN_END_RE = re.compile(
    r"when this card in a battle area is switched to hidden mode by one of your skills,\s*choose up to (\d+) of your (.+?) cards? and (?:it|they) gains? \[([^\]]+)\] until the end of your opponent'?s turn"
)
_SWITCHED_TO_REVEALED_SELF_GAIN_POWER_AND_KEYWORD_RE = re.compile(
    r"when this card is switched to revealed mode,\s*(?:this card|it) gets \+(\d+) power and \[([^\]]+)\] for the turn"
)
_SWITCHED_TO_REVEALED_OR_HIDDEN_OWNER_CARD_GAIN_POWER_RE = re.compile(
    r"when this card is switched to revealed mode or hidden mode,\s*choose up to (\d+) of your (.+?) cards? and (?:it|they) gets? \+(\d+) power for the turn"
)
_SWITCHED_TO_REVEALED_OWNER_CARD_GAIN_POWER_RE = re.compile(
    r"when this card is switched to revealed mode,\s*choose up to (\d+) of your (.+?) cards? and (?:it|they) gets? \+(\d+) power for the turn"
)
_SWITCHED_TO_REVEALED_OWNER_CARD_GAIN_KEYWORD_RE = re.compile(
    r"when this card is switched to revealed mode,\s*choose up to (\d+) of your (.+?) cards? and (?:it|they) gains? \[([^\]]+)\] for the turn"
)
_SWITCHED_TO_REVEALED_OR_HIDDEN_KO_OPP_BATTLE_RE = re.compile(
    r"when this card is switched to revealed mode or hidden mode,\s*choose up to (\d+) of your opponent'?s battle cards? and ko (?:it|them)"
)
_HIDDEN_BATTLE_TO_DROP_OWNER_CARD_GAIN_POWER_RE = re.compile(
    r"when this hidden mode card in a battle area is placed into its owner'?s drop,\s*choose up to (\d+) of your (.+?) cards? and (?:it|they) gets? \+(\d+) power for the turn"
)
_PLAY_TOP_IF_COLOR_ADD_HAND_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card is played(?: from your hand)?(?: or discarded by [^:]{1,120})?.*?"
    r"look at the top card of your deck; if it's a (red|blue|green|yellow|black)\b.*?you may add it to your hand.*?otherwise,?\s*place it at the bottom of your deck"
)
_OWNER_BLACK_BATTLE_PLAYED_FROM_WARP_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when a black battle card is played from your warp.*?this card gains \[wormhole\] for the turn"
)
_OWNER_OTHER_BATTLE_PLAYED_BY_DARK_OVER_REALM_DRAW_RE = re.compile(
    r"(?:if [^:]{1,180}:\s*)?when your battle card other than this card is played by a \[dark over realm\] skill,\s*draw (\d+) card"
)
_OWNER_OPP_BATTLE_ATTACKS_PLAY_SELF_FROM_DROP_OR_WARP_NEGATE_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when your opponent attacks with a battle card.*?play this card from your drop or warp in rest mode and negate the attack"
)
_HAND_TO_DROP_OR_WARP_PLACE_UP_TO_N_FROM_DECK_TO_SAME_DEST_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card in your hand is placed into its owner'?s drop or sent to its owner'?s warp,\s*"
    r"place up to (\d+) (.+?) card with (\d+) power or less from your deck into its owner'?s drop or send it to its owner'?s warp"
)
_HAND_TO_DROP_BY_CAUSE_PLAY_SELF_RE = re.compile(
    r"(?:if [^:]{1,180}:\s*)?when this card is placed in your drop area from your hand by an opponent'?s skill or by your \[revive\] skill,\s*you may play this card"
)
_HAND_DISCARDED_BY_UNION_FUSION_ADD_UP_TO_N_FROM_LIFE_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card is discarded from your hand by a \[union-fusion\] skill,\s*add up to (\d+) cards? from your life to your hand",
    re.IGNORECASE,
)
_PLAY_ADD_TOP_DECK_TO_ENERGY_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card is played.*?add the top card of your deck to your energy in rest mode"
)
_PLAY_ADD_TOP_DECK_TO_ENERGY_AND_BOTTOM_DECK_OPP_BATTLE_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played,\s*you may (?:add|place) the top card of your deck (?:to|in) your energy in rest mode,\s*and choose up to (\d+) of your opponent'?s battle cards? and place (?:it|them) at the bottom of (?:its|their) owner'?s deck",
    re.IGNORECASE,
)
_TURN_END_SWITCH_UP_TO_N_ENERGY_ACTIVE_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?at the end of (?:your turn|the turn), switch up to (\d+) of your(?: (.+?))? energy to active mode"
)
_FIELD_EXTRA_PLACED_SWITCH_UP_TO_N_ENERGY_ACTIVE_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when a player places a \[field\] extra card in a battle area.*?switch up to (\d+) of your(?: (.+?))? energy to active mode"
)
_FIELD_EXTRA_PLACED_BUFF_OWNER_LEADER_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card is placed in a battle area,\s*your (.+?) leader gets \+(\d+) power for the turn",
    re.IGNORECASE,
)
_OPP_SKILL_PLAYS_OVERCOST_BATTLE_REDUCE_RE = re.compile(
    r"switch this card to rest mode:\s*when your opponent uses a skill to play a battle card with an energy cost greater than their current energy, you may choose that battle card and have it get -\s*(\d+) power for the turn"
)
_OPP_SKILL_PLAYS_OVERCOST_BATTLE_SWITCH_REST_RE = re.compile(
    r"switch this card to rest mode:\s*when your opponent uses a skill to play a battle card with an energy cost greater than their current energy, you may choose (?:that battle card|it) and switch (?:that battle card|it) to rest mode"
)
_SELF_KO_UNISON_POWER_REDUCE_RE = re.compile(
    r"when this card is ko['â€™]?d.*?choose up to (\d+) of your opponent'?s unison card.*?gets? -\s*(\d+) power"
)
_SELF_REMOVED_OR_KO_ADD_LIFE_RE = re.compile(
    r"when this card is removed from your battle area by a skill or ko['â€™]?d.*?add (\d+) card from your life to your hand"
)
_SELF_REMOVED_OR_KO_PLAY_UP_TO_N_NAMED_FROM_DROP_RE = re.compile(
    r"when this card is removed from a battle area by an opponent'?s skill or ko['â€™]?d,\s*play up to (\d+) \{([^}]+)\} from your drop"
)
_PLAY_FROM_HAND_PLAY_FROM_DECK_RE = re.compile(
    r"when this card is played from your hand, choose up to (\d+) (.+?) from your deck, play it"
)
_PLAY_FROM_DECK_WITH_MARKERS_RE = re.compile(
    r"(?:if [^:]{1,180}:\s*)?when this card is played,\s*play up to (\d+) (.+?) from your deck with (?:a|(\d+)) markers? on it(?: in rest mode)?"
)
_COMBO_FROM_HAND_PLAY_FROM_HAND_RE = re.compile(
    r"when this card is used in a combo from your hand, choose up to (\d+) (.+?) in your hand and play it(?: in rest mode)?"
)
_PLAY_GAIN_CONTROL_OPP_UNISON_RE = re.compile(
    r"when this card is played from your hand, choose (?:up to )?(\d+) of your opponent'?s unison cards? and gain control of it"
)
_PLAY_GAIN_CONTROL_OPP_BATTLE_RE = re.compile(
    r"when (?:you play this card|this card is played(?: from your hand)?),?\s*choose up to (\d+) of (?:the )?battle cards? in your opponent'?s battle area with an energy cost of (\d+) or less and gain control of it"
)
_PLAY_FROM_HAND_PLAY_FROM_HAND_WITH_MARKERS_RE = re.compile(
    r"when this card is played from your hand, choose up to (\d+) (.+?) in your hand and play it with (?:a|(\d+)) markers? on it(?: in rest mode)?"
)
_PLAY_FROM_HAND_PLAY_FROM_HAND_OR_DECK_WITH_MARKERS_RE = re.compile(
    r"when this card is played from your hand, choose up to (\d+) (.+?) from your hand or deck, play it with (\d+) markers? on it(?: in rest mode)?"
)
_PLAY_LOOK_TOP_ADD_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when (?:this card is played|you play this card)( from your hand)?[^.]{0,300}?"
    r"look at up to (\d+) cards? from (?:the )?top of your deck[.,]\s*(?:add|choose) up to (\d+) (.+?) among them(?:[^.]{0,240})?(?:\s|[-\u2014\u2015])to your hand"
)
_PLAY_LOOK_TOP_ADD_DIRECT_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when (?:this card is played|you play this card)( from your hand)?[^.]{0,300}?"
    r"look at up to (\d+) cards? from (?:the )?top of your deck[.,]\s*(?:add|choose) up to (\d+) (.+?) to your hand"
)
_ATTACK_OPPONENT_CHOOSES_N_HAND_TO_WARP_RE = re.compile(
    r"when this card attacks,\s*your opponent chooses (\d+) card(?:s)? in their hand and sends it to their warp",
    re.IGNORECASE,
)
_PLAY_ADD_UP_TO_N_FROM_DECK_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card is (?:played(?: from your hand)?|placed in a battle area)[^.]{0,240}?add up to (\d+) (.+?) from your deck to your hand"
)
_PLAY_UP_TO_N_FROM_DROP_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played(?: from your hand)?[^.]{0,260}?play up to (\d+) (.+?) from your drop(?: area)?"
)
_PLAY_UP_TO_N_FROM_Z_ENERGY_COMBO_OR_DROP_RE = re.compile(
    r"(?:if [^:]{1,180}:\s*)?when this card is played(?: from your hand)?[^.]{0,320}?play up to (\d+) (.+?) from your z-energy,\s*combo area,\s*or drop(?: area)?",
    re.IGNORECASE,
)
_PLAY_PLACE_UP_TO_N_FROM_DROP_UNDER_SELF_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played(?: from your hand)?[^.]{0,220}?place up to (\d+) (.+?) from your drop(?: area)? under this card"
)
_PLAY_PLACE_UP_TO_N_NAMED_FIELD_EXTRA_FROM_OWNER_Z_DECK_RE = re.compile(
    r"(?:if [^:]{1,180}:\s*)?when this card is played(?: from your hand)?(?:[^.\[]){0,260}?place up to (\d+) \{([^}]+)\} from your z-deck into your battle area",
    re.IGNORECASE,
)
_PLAY_PLACE_UP_TO_N_FROM_DECK_OR_DROP_UNDER_SELF_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played(?: from your hand)?[^.]{0,240}?place up to (\d+) (.+?) from your deck(?: and/or| or) drop(?: area)? under this card"
)
_PLAY_PLACE_UP_TO_N_OPPONENT_BATTLE_INTO_DROP_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card is played(?: from your hand)?(?:[^.\[]){0,240}?choose up to (\d+) of your opponent'?s battle cards?,\s*ignoring \[barrier\],\s*place (?:it|them) in (?:its|their) owner'?s drops?",
    re.IGNORECASE,
)
_PLAY_RETURN_ALL_OPPONENT_BATTLE_AND_UNISON_TO_HAND_AND_BOTTOM_DECK_OPPONENT_LIFE_IF_MORE_HAND_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card is played(?: from your hand)?(?:[^.\[]){0,320}?choose all of your opponent'?s battle cards? and unisons?,\s*ignoring \[barrier\],?\s*return them to their owners'? hands?,\s*and if your opponent has more cards in hand than you,\s*place (\d+) card(?:s)? from your opponent'?s life at the bottom of their deck",
    re.IGNORECASE,
)
_PLAY_PLACE_ALL_OPPONENT_BATTLE_AND_UNISON_UNDER_SELF_AND_ADD_TOP_DECK_TO_LIFE_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card is played(?: from your hand)?(?:[^.\[]){0,320}?choose all of your opponent'?s battle cards? and unisons?,\s*ignoring \[barrier\],\s*place them under this card,\s*and for every (\d+) cards? chosen,\s*you may add the top card of your deck to your life(?:\.\s*\(up to (\d+)\.\))?",
    re.IGNORECASE,
)
_PLAY_PLACE_ALL_OPPONENT_BATTLE_AND_UNISON_INTO_DROP_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card is played(?: from your hand)?(?:[^.\[]){0,260}?choose all of your opponent'?s battle cards? and unisons?,\s*then place them in their owner(?:'s|s')? drops?",
    re.IGNORECASE,
)
_OWNER_OPPONENT_BATTLE_PLAYED_PLAY_SELF_FROM_UNDER_OWNER_LEADER_TO_OPPONENT_BATTLE_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when your opponent plays (.+?),\s*play this card from under your leader into your opponent'?s battle area",
    re.IGNORECASE,
)
_OWNER_OPPONENT_BATTLE_PLAYED_DISCARD_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when your opponent plays a battle card,\s*your opponent discards (\d+) cards? from their hand",
    re.IGNORECASE,
)
_NON_LEADER_ATTACK_HAND_Z_TAX_RE = re.compile(
    r"your opponent can't attack with non-leaders for the turn unless they place (\d+) card(?:s)? each from their hand and z-energy in their owners'? drops? each time",
    re.IGNORECASE,
)
_OWNER_UNION_ABSORB_ACTIVATED_PLACE_TOP_DECK_UNDER_SELF_AND_REST_RE = re.compile(
    r"when one of your (.+?) cards activates \[union absorb\],\s*place the top card of your deck under this card,\s*then choose up to (\d+) of your opponent'?s battle cards? and switch (?:it|them) to rest mode"
)
_PLAY_ADD_MARKER_PER_N_MULTICOLOR_ENERGY_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played, add a marker to (?:this card|it) for every (\d+) multicolor card in your energy"
)
_PLAY_FROM_HAND_ADD_FROM_HAND_TO_LIFE_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played from your hand, you may choose (?:up to )?(\d+) (.+?) card in your hand and add it to your life"
)
_PLAY_OPPONENT_DISCARDS_N_FROM_HAND_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when (?:this card is played|you play this card)(?: from your hand)?(?:(?:[^.\[]|\[[^\]]+\])){0,220}?(?:your opponent chooses (\d+) cards? (?:in|from) their hand and places? (?:it|them) in (?:their|his or her) drop area|your opponent chooses (\d+) cards? (?:in|from) their hand and discards (?:it|them)|your opponent discards (\d+) cards? from their hand)",
    re.IGNORECASE,
)
_PLAY_ADD_MARKERS_TO_OWNER_UNISON_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card is played(?: from your hand)?(?:[^.\[]){0,220}?choose up to (\d+) of your (.+?) unison cards?,\s*add (?:a|(\d+)) markers? to (?:it|them)",
    re.IGNORECASE,
)
_PLAY_OPPONENT_CHOOSES_N_HAND_TO_WARP_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when (?:this card is played|you play this card)(?: from your hand)?(?:[^.\[]){0,240}?your opponent chooses (\d+) cards? in their hand and sends (?:it|them) to their warp",
    re.IGNORECASE,
)
_OWNER_OPPONENT_COUNTER_ACTIVATED_DISCARD_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when your opponent activates a \[counter\] skill,\s*they discard (\d+) cards? from their hand",
    re.IGNORECASE,
)
_PLAY_REVEAL_OPPONENT_HAND_SEND_UP_TO_N_BATTLE_TO_WARP_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when (?:this card is played|you play this card)(?: from your hand)?.{0,260}?your opponent reveals their hand(?:,\s*then)?[\s.]*(?:you )?choose up to (\d+) battle cards? with (\d+)(?: power)? or less(?: power)? from (?:their hand|it) and send (?:it|them) to (?:(?:its|their) owner'?s warp|the warp)",
    re.IGNORECASE,
)
_PLAY_RETURN_WARPED_BY_SKILL_AT_OPPONENT_NEXT_TURN_END_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when (?:this card is played|you play this card)(?: from your hand)?.{0,360}?at the end of your opponent'?s next turn,\s*(?:return (?:all cards|the card) sent to the warp (?:with|by) this skill to (?:their hand|its owner'?s hand)|(?:they|your opponent) add (?:all cards|the card) sent to (?:their )?warp (?:with|by) this skill from (?:their )?warp to their hand)",
    re.IGNORECASE,
)
_PLAY_PLAY_WARPED_BY_SKILL_AT_TURN_END_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when (?:this card is played|you play this card).{0,320}?at the end of the turn,\s*play (?:any cards|the card) sent to a? warp (?:by|with) this skill to (?:their owners'? battle areas|its owner'?s battle area)(?: with their skills negated for the turn)?(?: in rest mode)?",
    re.IGNORECASE,
)
_SELF_LEAVES_BATTLE_RETURN_WARPED_BY_SOURCE_SKILL_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card leaves the battle area,\s*your opponent adds all cards sent to the warp with this card'?s skill to their hand",
    re.IGNORECASE,
)
_PLAY_BOTTOM_DECK_OPP_BATTLE_SWITCH_LEADER_AND_ENERGY_ACTIVE_AND_GAIN_KEYWORD_UNTIL_OPP_TURN_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played(?: from your hand)?[^.]{0,320}?choose up to (\d+) of your opponent'?s battle cards?,\s*place (?:it|them) at the bottom of (?:its|their) owner'?s deck,\s*switch up to (\d+) of your leaders? to active mode,\s*switch up to (\d+) of your (.+?) energy to active mode,\s*and this card gains \[([^\]]+)\] until the end of your opponent'?s next turn",
    re.IGNORECASE,
)
_PLAY_BOTTOM_DECK_OPP_BATTLE_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played(?: from your hand)?[^.]{0,220}?choose up to (\d+) of your opponent'?s battle cards?(?: with an energy cost of (\d+) or less)?\s*and place (?:it|them) at the bottom of (?:its|their) owner'?s deck",
    re.IGNORECASE,
)
_PLAY_RETURN_OPP_BATTLE_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:this card is played|you play this card)(?: from your hand)?[^.]{0,220}?choose up to (\d+) of your opponent'?s battle cards?(?: with an energy cost of (\d+) or less)?\s*and return (?:it|them) to (?:its|their) owner'?s hand",
    re.IGNORECASE,
)
_PLAY_PLACE_ANY_NUMBER_OPPONENT_BATTLES_INTO_DROP_RE = re.compile(
    r"when this card is played,\s*choose any number of your opponent'?s battle cards?,\s*ignoring \[barrier\],\s*and place them in their owners'? drops?",
    re.IGNORECASE,
)
_PLAY_DRAW_OPTIONAL_ADD_FROM_HAND_TO_Z_ENERGY_THEN_LOOK_TOP_ADD_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card is played,\s*draw (\d+) card(?:s)?\.\s*additionally,\s*you may add (\d+) (.+?) from your hand to your z-energy\.\s*if you do,\s*look at up to (\d+) cards? from the top of your deck,\s*add up to (\d+) (.+?) to your hand,\s*then shuffle your deck",
    re.IGNORECASE,
)
_PLAY_SEND_UP_TO_N_OPP_BATTLE_TO_WARP_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played(?: from your hand)?[^.]{0,260}?choose up to (\d+) of your opponent'?s battle cards?(?: with an energy cost (?:greater than their current energy|of (\d+) or less))?(?:,\s*ignoring \[barrier\])?,?\s*and send (?:it|them) to (?:its|their) owner'?s warps?",
    re.IGNORECASE,
)
_PLAY_SEND_UP_TO_N_OPP_BATTLE_TO_WARP_AND_GAIN_KEYWORD_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played(?: from your hand)?[^.]{0,260}?choose up to (\d+) of your opponent'?s battle cards?(?: with an energy cost of (\d+) or less)?(?:,\s*ignoring \[barrier\])?,?\s*send (?:it|them) to their owners'? warps?,?\s*and this card gains \[([^\]]+)\] for the turn",
    re.IGNORECASE,
)
_PLAY_SEND_SELF_AND_UP_TO_N_OPP_BATTLE_TO_WARP_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played(?: from your hand)?[^.]{0,260}?choose this card and up to (\d+) of your opponent'?s battle cards?(?: with an energy cost of (\d+) or less)?\s*and send them to their owners'? warps",
    re.IGNORECASE,
)
_PLAY_SEND_UP_TO_N_FROM_OWNER_DECK_TO_WARP_AND_LATER_PLAY_ONE_ADD_REST_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when this card is played(?: from your hand)?[^.]{0,340}?send up to (\d+) (.+?) from your deck to your warp,\s*shuffle your deck,\s*and at the end of your opponent'?s next turn,\s*play up to (\d+) of the cards sent to your warp by this skill in your battle area,\s*and you may add the remaining cards to your hand",
    re.IGNORECASE,
)
_PLAY_SEND_UP_TO_N_FROM_OWNER_DECK_TO_WARP_THEN_ADD_TO_HAND_NEXT_TURN_IF_STILL_IN_PLAY_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when (?:this card is played|you play this card)(?: from your hand)?[^.]{0,320}?choose up to (\d+) (.+?) from your deck and send (?:it|them) to your warp(?: and shuffle your deck|,\s*shuffle your deck)?\.\s*then,\s*at the beginning of your next turn,\s*if this card is in play in your battle area,\s*add (?:the card|up to \d+ of the cards) that (?:was|were) sent to your warp by this skill to your hand",
    re.IGNORECASE,
)
_PLAY_SEND_UP_TO_N_FROM_OWNER_DECK_TO_WARP_THEN_ADD_TO_HAND_NEXT_TURN_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when (?:this card is played|you play this card)(?: from your hand)?[^.]{0,320}?choose up to (\d+) (.+?) from your deck,\s*send (?:it|them)\s*(?:to\s*)?your warp,\s*shuffle your deck,\s*and at the (?:start|beginning) of your next turn,\s*add (?:that card|the card|up to \d+ of the cards) sent to your warp by this skill to your hand(?: from the warp)?",
    re.IGNORECASE,
)
_PLAY_SEND_UP_TO_N_FROM_OWNER_DECK_TO_WARP_THEN_PLAY_NEXT_TURN_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when (?:this card is played|you play this card)(?: from your hand)?[^.]{0,320}?send up to (\d+) (.+?) from your deck to your warp,\s*shuffle your deck,\s*and at the (?:start|beginning) of your next turn,\s*play (?:that card|the card sent to your warp by this skill) from your warp(?: in rest mode)?",
    re.IGNORECASE,
)
_ACTIVATE_MAIN_SEND_UP_TO_N_FROM_OWNER_HAND_TO_WARP_AND_PLAY_NEXT_TURN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,420}?choose up to (\d+) (.+?) from your hand,\s*send (?:it|them) to your warp,\s*and at the (?:start|beginning) of your next turn,\s*play (?:the card|up to \d+ of the cards) sent to your warp by this skill from your warp",
    re.IGNORECASE,
)
_PLAY_ADD_UP_TO_N_FROM_OWNER_LIFE_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when (?:this card is played|you play this card),\s*choose up to (\d+) cards? in your life and add them to your hand",
    re.IGNORECASE,
)
_PLAY_ADD_UP_TO_N_FROM_OWNER_DROP_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when (?:this card is played|you play this card),\s*add up to (\d+) (.+?) from your drop area to your hand",
    re.IGNORECASE,
)
_PLAY_SWITCH_UP_TO_N_OPPONENT_BATTLE_REST_RE = re.compile(
    r"(?:if [^:]{1,220}:\s*)?when (?:this card is played|you play this card),\s*choose up to (\d+) of your opponent'?s battle cards? with an energy cost of (\d+) or less and switch (?:it|them) to rest mode",
    re.IGNORECASE,
)
_COMBO_FROM_HAND_BATTLE_END_PLAY_SELF_THEN_RETURN_UP_TO_N_OPPONENT_BATTLE_TO_HAND_RE = re.compile(
    r"at the end of a battle in which this card was used in a combo from your hand,\s*play this card from your drop area in rest mode,\s*then choose up to (\d+) of your opponent'?s battle cards? with an energy cost of (\d+) or less and return (?:it|them) to (?:its|their) owner'?s hand",
    re.IGNORECASE,
)
_COMBO_FROM_HAND_BATTLE_END_PLAY_SELF_THEN_NEGATE_UP_TO_N_OPPONENT_UNISON_FOR_TURN_RE = re.compile(
    r"at the end of a battle in which this card was used in a combo from your hand,\s*play this card from your drop area in rest mode,\s*then choose up to (\d+) of your opponent'?s unison cards? and negate (?:its|their) skills for the turn",
    re.IGNORECASE,
)
_PLAY_DRAW_AND_SWITCH_SELF_ACTIVE_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when (?:this card is played(?: from your hand)?|you play this card)(?:[^.\[]){0,200}?draw (\d+) card(?:s)? and switch this card to active mode"
)
_ACTIVATE_MAIN_ADD_UP_TO_N_FROM_OWNER_DECK_TO_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,360}?(?:add|choose) up to (\d+) (.+?) from your (deck(?: or life)?|life or deck) "
    r"(?:(?:and )?add (?:it|them) to your hand|to your hand)"
)
_ACTIVATE_MAIN_ADD_SELF_FROM_OWNER_DROP_TO_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?add this card from your drop(?: area)? to your hand",
    re.IGNORECASE,
)


def _normalize_text(raw: str | None) -> str:
    text = str(raw or "")
    text = re.sub(r"<badge[^>]*>\s*([^<]+?)\s*</badge>", lambda m: f"[{m.group(1)}]", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", ". ", text, flags=re.IGNORECASE)
    text = html.unescape(text).lower()
    text = text.replace("[br]", ". ").replace("â€”", " - ")
    text = text.replace("—", " - ").replace("―", " - ")
    return _WS_RE.sub(" ", text.strip())


def _once_per_turn(text: str) -> bool:
    return ("[once per turn]" in text) or ("once per turn" in text)


def _limit_per_turn(text: str) -> int | None:
    match = re.search(r"\[\s*limit\s+(\d+)\s*\]", text)
    if match:
        return int(match.group(1))
    return None


def _extract_unison_marker_delta(text: str) -> int | None:
    match = re.search(r"\[\s*unison\s*([+-]?\d+)\s*\]", text)
    if match:
        return int(match.group(1))
    match = re.search(r"\[\s*([+-]\d+)\s*\]\s*\[activate(?::)?\s*(?:main|battle|main/battle)\]", text)
    if match:
        return int(match.group(1))
    return None


def _split_choose_one_branches(text: str) -> list[str]:
    marker = "choose one"
    if marker not in text:
        return [text]
    idx = text.find(marker)
    if idx < 0:
        return [text]
    prefix = text[:idx]
    tail = text[idx:]
    bullets = ("ãƒ»", "・", "•", "･", "ï½¥")
    if not any(b in tail for b in bullets):
        return [text]
    # Normalize known bullet tokens to a single delimiter before splitting.
    normalized_tail = tail
    for b in bullets:
        normalized_tail = normalized_tail.replace(b, "|")
    normalized_tail = re.sub(r"(?:\?+|[^\w\s\[\]]+)\s*(?=choose\b)", "|", normalized_tail, flags=re.IGNORECASE)
    parts = [p.strip(" .;-") for p in normalized_tail.split("|")[1:] if p.strip(" .;-")]
    if not parts:
        return [text]
    return [f"{prefix} {part}".strip() for part in parts]


def _split_effect_branches(raw: str | None) -> list[str]:
    text = str(raw or "")
    text = re.sub(r"<badge[^>]*>\s*([^<]+?)\s*</badge>", lambda m: f"[{m.group(1)}]", text, flags=re.IGNORECASE)
    text = html.unescape(text)
    if not text.strip():
        return []
    normalized = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE).replace("[br]", "\n").replace("\r\n", "\n").replace("\r", "\n")
    bullets = ("ãƒ»", "・", "•", "･", "ï½¥")
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    merged: list[str] = []
    for line in lines:
        if merged and (
            any(line.startswith(bullet) for bullet in bullets)
            or (
                "choose one" in merged[-1].lower()
                and re.match(r"^(?:\?+|[^\w\s\[\]]+)\s*choose\b", line, re.IGNORECASE)
            )
        ):
            merged[-1] = f"{merged[-1]} {line}"
        else:
            merged.append(line)
    branches: list[str] = []
    for line in merged:
        normalized_line = _normalize_text(line)
        branches.extend(_split_choose_one_branches(normalized_line))
    return [branch for branch in branches if branch]


def _normalize_token_name(raw: str | None) -> str:
    token_name = str(raw or "token").strip().lower()
    if token_name.endswith("tokens"):
        token_name = f"{token_name[:-1]}"
    return token_name


def _normalize_extracted_keywords(raw: str | None) -> str:
    matches = [part.strip().lower() for part in re.findall(r"\[([^\]]+)\]", str(raw or "")) if part.strip()]
    if matches:
        return ",".join(matches)
    return str(raw or "").strip().lower()


def _extract_token_stats(
    branch: str,
    *,
    token_name: str | None = None,
    explicit_power: str | int | None = None,
    explicit_combo_cost: str | int | None = None,
    explicit_combo_power: str | int | None = None,
) -> tuple[int, int, int]:
    fallback_stats = re.search(
        r"\([^)]*?(\d+)\s+power,\s*(\d+)\s+combo cost,\s*(?:and\s*)?(\d+)\s+combo power[^)]*\)",
        branch,
        re.IGNORECASE,
    )
    named_fallback_stats = None
    normalized_token_name = _normalize_token_name(token_name) if token_name else ""
    if normalized_token_name:
        named_fallback_stats = re.search(
            rf"\({re.escape(normalized_token_name)}s?\s+ha(?:s|ve)\s+(\d+)\s+power(?:,\s*(\d+)\s+combo cost,\s*(?:and\s*)?(\d+)\s+combo power)?[^)]*\)",
            branch,
            re.IGNORECASE,
        )
    power = int(
        explicit_power
        or (fallback_stats.group(1) if fallback_stats else 0)
        or (named_fallback_stats.group(1) if named_fallback_stats else 0)
        or 0
    )
    combo_cost = int(
        explicit_combo_cost
        or (fallback_stats.group(2) if fallback_stats else 0)
        or (named_fallback_stats.group(2) if named_fallback_stats and named_fallback_stats.group(2) else 0)
        or 0
    )
    combo_power = int(
        explicit_combo_power
        or (fallback_stats.group(3) if fallback_stats else 0)
        or (named_fallback_stats.group(3) if named_fallback_stats and named_fallback_stats.group(3) else 0)
        or 0
    )
    return power, combo_cost, combo_power


def _extract_common_conditions(text: str) -> dict[str, int | str | bool]:
    params: dict[str, int | str | bool] = {}
    auto_cost_header = _extract_auto_header_cost_header(text)
    if auto_cost_header:
        params["auto_cost_header"] = auto_cost_header
    m_auto_under_to_drop = re.search(
        r"place (\d+) cards? from under this card in (?:their|its) owner'?s drop(?: area)?s?\s*:\s*when ",
        text,
        re.IGNORECASE,
    )
    if m_auto_under_to_drop is not None:
        params["auto_release_under_to_drop_before"] = int(m_auto_under_to_drop.group(1))
    m_auto_under_to_warp = re.search(
        r"send (\d+) cards? from under this card to your warp\s*:\s*when ",
        text,
        re.IGNORECASE,
    )
    if m_auto_under_to_warp is not None:
        params["auto_release_under_to_warp_before"] = int(m_auto_under_to_warp.group(1))
    m_sparking = re.search(r"\[\s*sparking\s+(\d+)\s*\]", text)
    if m_sparking:
        params["min_owner_drop"] = int(m_sparking.group(1))
    m_opponent_drop = re.search(r"if your opponent has (\d+) or more cards in (?:their|their own) drop", text)
    if m_opponent_drop:
        params["min_opponent_drop"] = int(m_opponent_drop.group(1))
    m_leader = re.search(
        r"(if your leader(?: card)? .{0,260}?)(?::\s*(?:choose|play|add|draw|send|switch|look|place|negate|your opponent|this card|at the|when))",
        text,
    )
    if m_leader:
        params["requires_leader"] = m_leader.group(1).strip()
    elif "if your leader" in text:
        m_inline_leader_named = re.search(r"(if your leader(?:'s back side)?(?: card)?[^:]{0,220}?\{[^}]+\}[^:]{0,60})", text)
        if m_inline_leader_named:
            params["requires_leader"] = m_inline_leader_named.group(1).strip()
        else:
            m_inline_leader = re.search(r"(if your leader(?: card)?[^,.]{0,180})", text)
            if m_inline_leader:
                params["requires_leader"] = m_inline_leader.group(1).strip()
    m_leader_back = re.search(r"if your leader'?s back side is a [^<]*<([^>]+)> card", text)
    if m_leader_back:
        params["required_leader_back_name_contains"] = m_leader_back.group(1).strip().upper()
    m_leader_traits = re.search(r"if your leader(?: card)? is a ([^.]+?) card", text)
    if m_leader_traits:
        raw_traits = m_leader_traits.group(1)
        if "<" in raw_traits:
            traits = [part.strip().title() for part in re.findall(r"<([^>]+)>", raw_traits) if part.strip()]
        elif "{" in raw_traits:
            traits = [part.strip().title() for part in re.findall(r"\{([^}]+)\}", raw_traits) if part.strip()]
        elif "≪" in raw_traits and "≫" in raw_traits:
            traits = [part.strip().title() for part in re.findall(r"≪([^≫]+)≫", raw_traits) if part.strip()]
        else:
            traits = [part.strip().title() for part in re.split(r"\bor\b|/|,", raw_traits) if part.strip()]
        if traits:
            params["required_leader_traits"] = ",".join(traits)
    m_energy = re.search(r"\byou have (\d+) or more energy", text)
    if m_energy:
        params["min_owner_energy"] = int(m_energy.group(1))
    m_z_energy = re.search(r"\byou have (\d+) or more z-energy", text)
    if m_z_energy:
        params["min_owner_z_energy"] = int(m_z_energy.group(1))
    m_opponent_energy = re.search(r"your opponent has (\d+) or more energy", text)
    if m_opponent_energy:
        params["min_opponent_energy"] = int(m_opponent_energy.group(1))
    m_any_energy = re.search(r"you or your opponent has (\d+) or more energy", text)
    if m_any_energy:
        params["min_any_player_energy"] = int(m_any_energy.group(1))
    m_total_players_energy = re.search(r"there'?s a total of (\d+) or more energy between you and your opponent", text)
    if m_total_players_energy:
        params["min_total_players_energy"] = int(m_total_players_energy.group(1))
    m_life = re.search(r"your life is at (\d+) or less", text)
    if m_life:
        params["max_owner_life"] = int(m_life.group(1))
    if "if your life is less than or equal to your opponent's" in text or "if your life is less than or equal to your opponent’s" in text:
        params["requires_owner_life_less_or_equal_opponent"] = True
    if "neither you nor your opponent have a battle card in play" in text:
        params["requires_no_owner_battle"] = True
        params["requires_no_opponent_battle"] = True
    if "if you have no battle cards in play" in text:
        params["requires_no_owner_battle"] = True
    if "if your opponent has no battle cards in play" in text:
        params["requires_no_opponent_battle"] = True
    if "played using its [counter: attack] skill" in text.lower():
        params["requires_played_via"] = "counter"
    if "if a [field] extra card isn't in your battle area" in text or "if a field extra card isn't in your battle area" in text:
        params["requires_no_owner_field_extra"] = True
    m_source_markers = re.search(r"if this card has (\d+) or more markers?(?: on it)?", text, re.IGNORECASE)
    if m_source_markers:
        params["min_source_markers"] = int(m_source_markers.group(1))
    m_hidden_mode = re.search(r"if you have (\d+) or more hidden mode cards? in your battle area", text)
    if m_hidden_mode:
        params["min_owner_hidden_mode_battle"] = int(m_hidden_mode.group(1))
    m_only_battle = re.search(r"if you only have (.+?) cards? in play in your battle area", text)
    if m_only_battle:
        descriptor = m_only_battle.group(1).strip().lower()
        params["required_owner_battle_only_matching"] = True
        params.update(
            {
                f"required_owner_battle_{k}": v
                for k, v in _descriptor_filters(descriptor, text).items()
                if k in {"allowed_colors", "required_traits", "required_characters", "required_name_contains"}
            }
        )
    m_mono_energy = re.search(r"if (?:(?:your leader(?: card)? and )?energy are all|all of your energy is) (?:mono-)?(red|blue|green|yellow|black)", text)
    if m_mono_energy:
        params["requires_mono_energy"] = m_mono_energy.group(1).strip()
    m_owner_leader_descriptor = re.search(r"(?:if|and)\s+your leader(?: card)? is a (.+?) card", text, re.IGNORECASE)
    if m_owner_leader_descriptor:
        raw_descriptor = m_owner_leader_descriptor.group(1).strip()
        descriptor = raw_descriptor.lower()
        filters = {
            k: v
            for k, v in _descriptor_filters(descriptor, text).items()
            if k in {"allowed_colors", "required_traits", "required_characters", "required_name_contains"}
        }
        if "<" in raw_descriptor and "required_characters" not in filters and "required_traits" in filters:
            filters["required_characters"] = str(filters.pop("required_traits"))
        params.update({f"leader_{k}": v for k, v in filters.items()})
    m_owner_battle_or_z_energy = re.search(r"if you have a (.+?) card in play or in your z-energy", text)
    if m_owner_battle_or_z_energy:
        raw_descriptor = m_owner_battle_or_z_energy.group(1).strip()
        descriptor = raw_descriptor.lower()
        filters = {
            k: v
            for k, v in _descriptor_filters(descriptor, text).items()
            if k in {"allowed_colors", "required_traits", "required_characters", "required_name_contains"}
        }
        if "<" in raw_descriptor and "required_characters" not in filters and "required_traits" in filters:
            filters["required_characters"] = str(filters.pop("required_traits"))
        params.update({f"required_owner_battle_or_z_energy_{k}": v for k, v in filters.items()})
    m_owner_battle_costed = re.search(
        r"you have a (.+?) card with an energy cost of (\d+) or more in play",
        text,
        re.IGNORECASE,
    )
    if m_owner_battle_costed:
        raw_descriptor = m_owner_battle_costed.group(1).strip()
        descriptor = raw_descriptor.lower()
        filters = {
            k: v
            for k, v in _descriptor_filters(descriptor, text).items()
            if k in {"allowed_colors", "required_traits", "required_characters", "required_name_contains"}
        }
        if "<" in raw_descriptor and "required_characters" not in filters and "required_traits" in filters:
            filters["required_characters"] = str(filters.pop("required_traits"))
        params.update({f"required_owner_battle_{k}": v for k, v in filters.items()})
        params["required_owner_battle_min_cost"] = int(m_owner_battle_costed.group(2))
    m_owner_battle_named = re.search(r"(?:(?:if|and)\s+)?there is a \{([^}]+)\} in your battle area", text, re.IGNORECASE)
    if m_owner_battle_named:
        params["required_owner_battle_required_name_contains"] = m_owner_battle_named.group(1).strip().upper()
    m_owner_have_named_in_battle = re.search(r"if you have \{([^}]+)\} in your battle area", text, re.IGNORECASE)
    if m_owner_have_named_in_battle:
        params["required_owner_battle_required_name_contains"] = m_owner_have_named_in_battle.group(1).strip().upper()
    m_owner_battle_under_named = re.search(
        r"if there are (\d+) or more cards under a \{([^}]+)\} in your battle area",
        text,
        re.IGNORECASE,
    )
    if m_owner_battle_under_named:
        params["required_owner_battle_under_count_at_least"] = int(m_owner_battle_under_named.group(1))
        params["required_owner_battle_under_host_required_name_contains"] = m_owner_battle_under_named.group(2).strip().upper()
    m_owner_leader_under_it = re.search(
        r"if your leader(?: card)?[^:]{0,220}?\band there are (\d+) or more cards under it",
        text,
        re.IGNORECASE,
    )
    if m_owner_leader_under_it:
        params["required_owner_leader_under_count_at_least"] = int(m_owner_leader_under_it.group(1))
    m_owner_combo_each = re.search(
        r"(?:if|and)\s+you have 1 or more (.+?) card and 1 or more (.+?) card in your combo area",
        text,
        re.IGNORECASE,
    )
    if m_owner_combo_each:
        for key in ("allowed_colors", "required_traits", "required_characters", "required_name_contains", "required_card_type"):
            values: list[str] = []
            for raw_descriptor in (m_owner_combo_each.group(1).strip(), m_owner_combo_each.group(2).strip()):
                filters = _descriptor_filters(raw_descriptor.lower(), text)
                if key == "required_traits" and "<" in raw_descriptor and "required_traits" in filters:
                    continue
                if key == "required_characters" and "<" in raw_descriptor and "required_traits" in filters:
                    value = str(filters.get("required_traits", "")).strip()
                    if value:
                        values.append(value)
                    continue
                value = filters.get(key)
                if value is None:
                    continue
                normalized = str(value).strip()
                if normalized:
                    values.append(normalized)
            if values:
                params[f"required_owner_combo_{key}_each"] = "|".join(values)
    m_owner_combo = re.search(
        r"(?:if you have|and you have|and)\s+(?:a |an )?(.+?) card in your combo area",
        text,
        re.IGNORECASE,
    )
    if m_owner_combo is None:
        m_owner_combo = re.search(
            r"(?:if|and)\s+(?:a|an)\s+(.+?)\s+card is in your combo area",
            text,
            re.IGNORECASE,
        )
    if m_owner_combo:
        raw_descriptor = m_owner_combo.group(1).strip()
        descriptor = raw_descriptor.lower()
        filters = {
            k: v
            for k, v in _descriptor_filters(descriptor, text).items()
            if k in {"allowed_colors", "required_traits", "required_characters", "required_name_contains", "required_card_type", "requires_skill_less"}
        }
        if "required_card_type" not in filters:
            compact_descriptor = re.sub(r"\s+", " ", descriptor).strip()
            if compact_descriptor.endswith("z-battle"):
                filters["required_card_type"] = "Z-BATTLE"
            elif compact_descriptor.endswith("z-unison"):
                filters["required_card_type"] = "Z-UNISON"
            elif compact_descriptor.endswith("unison"):
                filters["required_card_type"] = "UNISON"
            elif compact_descriptor.endswith("extra"):
                filters["required_card_type"] = "EXTRA"
            elif compact_descriptor.endswith("battle") or compact_descriptor.endswith("monster"):
                filters["required_card_type"] = "BATTLE"
        if "<" in raw_descriptor and "required_characters" not in filters and "required_traits" in filters:
            filters["required_characters"] = str(filters.pop("required_traits"))
        params.update({f"required_owner_combo_{k}": v for k, v in filters.items()})
    if "there are no cards in your combo area" in text:
        params["requires_owner_combo_empty"] = True
    if (
        "if you don't have a unison in play" in text
        or "if you do not have a unison in play" in text
        or "if you don't have a unison card in play" in text
        or "if you do not have a unison card in play" in text
    ):
        params["requires_no_owner_unison"] = True
    if re.search(r"if a copy of this card isn(?:'|&apos;)?t in play in your battle area", text, re.IGNORECASE):
        params["requires_no_owner_battle_with_source_card_id"] = True
    if "ignoring [barrier]" in text or "ignoring barrier" in text:
        params["ignores_barrier"] = True
    if (
        "rest mode" in text
        and not re.search(r"\b(?:you )?switch this card to rest mode\b", text, re.IGNORECASE)
        and "play this card from your hand in rest mode" not in text
        and "play this card in rest mode" not in text
    ):
        params["rest_mode_only"] = True
    if "if it's your turn" in text or "during your turn" in text:
        params["requires_owner_turn"] = True
    if "if it's your opponent's turn" in text or "during your opponent's turn" in text:
        params["requires_opponent_turn"] = True
    if "if this card is in a battle" in text.lower():
        params["requires_source_in_battle"] = True
    m_owner_named_in_battle = re.search(r"if your \{([^}]+)\} is in a battle", text, re.IGNORECASE)
    if m_owner_named_in_battle:
        params["required_owner_battle_name_in_battle"] = m_owner_named_in_battle.group(1).strip().upper()
    m_source_under_leader = re.search(
        r"if this card is under (?:(?:your )?\{([^}]+)\}|your <([^>]+)> leader|your leader)",
        text,
        re.IGNORECASE,
    )
    if m_source_under_leader:
        params["required_source_zone"] = "leader_under"
        host_name = str(m_source_under_leader.group(1) or "").strip()
        host_character = str(m_source_under_leader.group(2) or "").strip()
        if host_name:
            params["under_host_name_contains"] = host_name.upper()
        if host_character:
            params["under_host_required_characters"] = host_character
    return params


def _descriptor_filters(descriptor: str, text: str) -> dict[str, int | str | bool]:
    descriptor_lc = descriptor.lower()
    params: dict[str, int | str | bool] = {}
    if "[dragon ball]" in descriptor_lc:
        params["required_runtime_labels"] = "dragon ball"
    raw_required_traits = sorted(
        {
            match.strip().title()
            for match in re.findall(r"(?:≪|â‰ª)\s*([^≫]+?)\s*(?:≫|â‰«)", descriptor, re.IGNORECASE)
            if match.strip()
        }
    )
    raw_required_characters = sorted({match.strip().title() for match in re.findall(r"<([^>]+)>", descriptor) if match.strip()})
    m_character_name_requirement = re.search(r"with <([^>]+)> in (?:its|their) character name", descriptor, re.IGNORECASE)
    if m_character_name_requirement:
        raw_required_characters = sorted({*raw_required_characters, m_character_name_requirement.group(1).strip().title()})
    m_cost = re.search(r"energy costs? of (\d+) or less", descriptor_lc)
    if m_cost is None:
        m_cost = re.search(r"energy cost of (\d+) or less", descriptor_lc)
    if m_cost is None:
        m_cost = re.search(r"energy costs? of (\d+)\b", descriptor_lc)
    if m_cost is None:
        m_cost = re.search(r"energy cost of (\d+)\b", descriptor_lc)
    if m_cost is None:
        m_cost = re.search(r"energy costs? of (\d+) or less", text)
    if m_cost is None:
        m_cost = re.search(r"energy cost of (\d+) or less", text)
    if m_cost is None:
        m_cost = re.search(r"energy costs? of (\d+)\b", text)
    if m_cost is None:
        m_cost = re.search(r"energy cost of (\d+)\b", text)
    params["max_cost"] = int(m_cost.group(1)) if m_cost else -1

    color_scan_text = re.sub(r"(?:≪|â‰ª)\s*([^≫]+?)\s*(?:≫|â‰«)", " ", descriptor_lc)
    color_scan_text = re.sub(r"<[^>]+>", " ", color_scan_text)
    colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black|white)\b", color_scan_text)))
    if colors:
        params["allowed_colors"] = ",".join(colors)
    if raw_required_traits:
        params["required_traits"] = ",".join(raw_required_traits)
    if "[ex-evolve]" in descriptor_lc or " ex-evolve" in descriptor_lc:
        params["requires_ex_evolve"] = True
    if "[union]" in descriptor_lc or " union skill" in descriptor_lc:
        params["required_skill_text_contains"] = "[union]"

    required_card_type = ""
    if "z-leader" in descriptor_lc or "z leader" in descriptor_lc:
        required_card_type = "Z-LEADER"
    elif "leader card" in descriptor_lc or descriptor_lc == "leader":
        required_card_type = "LEADER"
    elif "z-battle card" in descriptor_lc or "z battle card" in descriptor_lc:
        required_card_type = "Z-BATTLE"
    elif "z-unison card" in descriptor_lc or "z unison card" in descriptor_lc:
        required_card_type = "Z-UNISON"
    elif "unison card" in descriptor_lc:
        required_card_type = "UNISON"
    elif "extra card" in descriptor_lc:
        required_card_type = "EXTRA"
    elif "battle card" in descriptor_lc or "monster card" in descriptor_lc:
        required_card_type = "BATTLE"
    if required_card_type:
        params["required_card_type"] = required_card_type
    if "skill-less" in descriptor_lc or "skill less" in descriptor_lc:
        params["requires_skill_less"] = True

    m_name_token = re.search(r"\{([^}]+)\}\s+in\s+(?:their|its)?\s*card\s+names?", descriptor_lc)
    if m_name_token:
        params["required_name_contains"] = m_name_token.group(1).strip().upper()
    elif re.fullmatch(r"\{([^}]+)\}", descriptor.strip()):
        params["required_name_contains"] = descriptor.strip()[1:-1].strip().upper()
    else:
        m_embedded_name_token = re.fullmatch(r"(?:an?|one of your)?\s*\{([^}]+)\}", descriptor.strip(), re.IGNORECASE)
        if m_embedded_name_token:
            params["required_name_contains"] = m_embedded_name_token.group(1).strip().upper()

    cleaned = descriptor_lc
    cleaned = re.sub(r"\{[^}]+\}\s+in\s+(?:their|its)?\s*card\s+names?", " ", cleaned)
    cleaned = re.sub(r"\b(red|blue|green|yellow|black|white)\b", " ", cleaned)
    cleaned = re.sub(r"\b(z-battle|z battle|z-unison|z unison|battle|unison|extra|monster)\s+cards?\b", " ", cleaned)
    cleaned = re.sub(r"\bcards?\b", " ", cleaned)
    cleaned = re.sub(r"\bwith\b", " ", cleaned)
    cleaned = re.sub(r"\bamong them\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:with )?an energy costs? of \d+(?: or less)?\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:with )?energy costs? of \d+(?: or less)?\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:with )?an energy cost of \d+(?: or less)?\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:with )?energy cost of \d+(?: or less)?\b", " ", cleaned)
    cleaned = re.sub(r"\band\s+\[?ex-evolve\]?\b", " ", cleaned)
    cleaned = re.sub(r"\[?ex-evolve\]?", " ", cleaned)
    cleaned = re.sub(r"\bfrom your (?:warp|drop(?: area)?|deck|hand)\b", " ", cleaned)
    cleaned = re.sub(r"with\s+in\s+(?:its|their)\s+character\s+name", " ", cleaned)
    cleaned = re.sub(r"in\s+(?:its|their)\s+character\s+name", " ", cleaned)
    cleaned = re.sub(r"(?:≪|â‰ª)\s*([^≫]+?)\s*(?:≫|â‰«)", " ", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = cleaned.replace("<", " ").replace(">", " ").replace("≪", " ").replace("≫", " ")
    cleaned = re.sub(r"[^0-9a-z ,/.-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    if cleaned in {"or", "and"}:
        cleaned = ""

    if raw_required_characters and raw_required_traits:
        params["required_characters"] = ",".join(raw_required_characters + raw_required_traits)
    elif len(raw_required_characters) > 1:
        params["required_characters"] = ",".join(raw_required_characters)
    elif raw_required_characters and "energy cost" in descriptor_lc:
        params["required_characters"] = ",".join(raw_required_characters)
    elif raw_required_characters:
        params.setdefault("required_traits", ",".join(raw_required_characters))

    if cleaned and "required_name_contains" not in params:
        parts = [part.strip().title() for part in re.split(r"\bor\b|/|,", cleaned) if part.strip()]
        tokens = [t for t in cleaned.split() if t]
        if len(parts) > 1:
            params.setdefault("required_characters", ",".join(parts))
        elif len(tokens) == 1 and tokens[0] not in {"red", "blue", "green", "yellow", "black", "white"}:
            if "<" in descriptor and "energy cost" in descriptor_lc:
                params.setdefault("required_characters", cleaned.title())
            else:
                params.setdefault("required_traits", cleaned.title())
        elif len(tokens) > 0:
            params.setdefault("required_characters", cleaned.title())

    if params.get("required_runtime_labels") == "dragon ball":
        params.pop("required_traits", None)
        params.pop("required_characters", None)

    return params


def _extract_under_leader_promotion_requirements(text: str) -> dict[str, int | str | bool]:
    params: dict[str, int | str | bool] = {}
    m = re.search(
        r"if (?:a|an)\s+(?:<([^>]+)>|\{([^}]+)\}) card is under your leader and you place (\d+) card(?:s)? from under (?:a|an|your)\s+(.+?) card in your battle area in (?:its|their) owner'?s drop",
        text,
        re.IGNORECASE,
    )
    if not m:
        return params
    leader_descriptor = str(m.group(1) or m.group(2) or "").strip().lower()
    host_descriptor = str(m.group(4) or "").strip().lower()
    move_amount = int(m.group(3))
    leader_filters = _descriptor_filters(leader_descriptor, text)
    host_filters = _descriptor_filters(host_descriptor, text)
    params["required_owner_leader_under_count_at_least"] = 1
    params["move_under_owner_battle_to_drop_before"] = move_amount
    params["required_owner_battle_under_count_at_least"] = move_amount
    for key, value in leader_filters.items():
        if key == "required_card_type":
            params["required_owner_leader_under_required_card_types"] = value
        elif key in {"allowed_colors", "required_traits", "required_characters", "required_name_contains"}:
            params[f"required_owner_leader_under_{key}"] = value
    for key, value in host_filters.items():
        if key == "required_card_type":
            params["required_owner_battle_under_host_required_card_types"] = value
        elif key in {"allowed_colors", "required_traits", "required_characters", "required_name_contains"}:
            params[f"required_owner_battle_under_host_{key}"] = value
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


def _extract_auto_header_cost_header(text: str) -> str:
    m_auto_cost = re.match(
        r"\s*(?:\[[^\]]+\])?\s*\[auto\]((?:\{[^}]+\}|\([^)]*\)|[①②③④⑤⑥⑦⑧⑨⑩])+)\s*(?:,|:)",
        text,
        re.IGNORECASE,
    )
    if m_auto_cost is None:
        return ""
    return str(m_auto_cost.group(1) or "").strip()


def _extract_main_phase_auto_cost_params(text: str) -> dict[str, int | str | bool]:
    params: dict[str, int | str | bool] = {}
    auto_cost_header = _extract_auto_header_cost_header(text)
    if auto_cost_header:
        params["auto_cost_header"] = auto_cost_header
    m_marker = re.match(r"\s*\[([+-]?\d+)\]\s*\[auto\]", text, re.IGNORECASE)
    if m_marker is None:
        m_marker = re.match(r"\s*\[auto\]\s*\[([+-]?\d+)\]", text, re.IGNORECASE)
    if m_marker is not None:
        try:
            params["auto_marker_delta"] = int(m_marker.group(1))
        except ValueError:
            pass
    m_discard = re.search(r"discard (\d+) cards? from your hand:\s*at the start of your", text)
    if m_discard is not None:
        params["auto_discard_hand_before"] = int(m_discard.group(1))
    m_choose_discard = re.search(r"choose (\d+) cards? in your hand and discard (?:it|them):\s*at the start of your", text)
    if m_choose_discard is not None:
        params["auto_discard_hand_before"] = int(m_choose_discard.group(1))
    m_bottom_deck = re.search(r"place (\d+) cards? from your hand at the bottom of your deck(?: in any order)?:\s*at the start of your", text)
    if m_bottom_deck is not None:
        params["auto_bottom_deck_hand_before"] = int(m_bottom_deck.group(1))
    if "place this card in its owner's drop" in text or "place this card in its owners' drop" in text:
        if ": at the start of your" in text:
            params["auto_place_self_in_drop_before"] = True
    if "remove this card from the game: at the start of your" in text:
        params["auto_remove_self_before"] = True
    m_under_to_drop = re.search(r"place (\d+) cards? from under this card in (?:their|its) owners?' drops?:\s*at the start of your", text)
    if m_under_to_drop is not None:
        params["auto_release_under_to_drop_before"] = int(m_under_to_drop.group(1))
    return params


def extract_effect_rules_from_card(card: CardData) -> list[EffectRule]:
    text = _normalize_text(card.card_skill_unstyled)
    branches = _split_effect_branches(card.card_skill_unstyled)
    if not branches:
        return []

    card_type = str(getattr(card, "card_type", "") or "").upper()
    is_extra = card_type in {"EXTRA", "Z-EXTRA"}
    rules: list[EffectRule] = []
    once = _once_per_turn(text)
    limit = _limit_per_turn(text)

    m_self_left_choose_play_or_draw = _SELF_LEFT_BATTLE_CHOOSE_PLAY_FROM_OWNER_DECK_OR_HAND_OR_DRAW_RE.search(text)
    if m_self_left_choose_play_or_draw:
        descriptor = str(m_self_left_choose_play_or_draw.group(2) or "").strip().lower()
        filters = _descriptor_filters(descriptor, text)
        if "<" in descriptor and "required_characters" not in filters and "required_traits" in filters:
            filters["required_characters"] = str(filters.pop("required_traits"))
        extra = _extract_common_conditions(text)
        rules.append(
            EffectRule(
                trigger="self_left_battle_area",
                handler_id="auto_choose_play_up_to_n_from_owner_deck_or_hand_or_secondary_on_self_left_battle",
                handler_params={
                    "max_targets": int(m_self_left_choose_play_or_draw.group(1)),
                    "min_cost": int(m_self_left_choose_play_or_draw.group(3)),
                    "max_cost": int(m_self_left_choose_play_or_draw.group(3)),
                    "secondary_mode": "draw",
                    "secondary_amount": int(m_self_left_choose_play_or_draw.group(4)),
                    **filters,
                    **extra,
                },
                source_text=text,
                once_per_turn=once,
                limit_per_turn=limit,
            )
        )

    m_self_left_choose_play_or_discard = _SELF_LEFT_BATTLE_CHOOSE_PLAY_FROM_OWNER_DECK_OR_HAND_OR_OPPONENT_DISCARD_RE.search(text)
    if m_self_left_choose_play_or_discard:
        descriptor = str(m_self_left_choose_play_or_discard.group(2) or "").strip().lower()
        filters = _descriptor_filters(descriptor, text)
        if "<" in descriptor and "required_characters" not in filters and "required_traits" in filters:
            filters["required_characters"] = str(filters.pop("required_traits"))
        extra = _extract_common_conditions(text)
        rules.append(
            EffectRule(
                trigger="self_left_battle_area",
                handler_id="auto_choose_play_up_to_n_from_owner_deck_or_hand_or_secondary_on_self_left_battle",
                handler_params={
                    "max_targets": int(m_self_left_choose_play_or_discard.group(1)),
                    "min_cost": int(m_self_left_choose_play_or_discard.group(3)),
                    "max_cost": int(m_self_left_choose_play_or_discard.group(3)),
                    "secondary_mode": "opponent_discard",
                    "secondary_amount": int(m_self_left_choose_play_or_discard.group(4)),
                    **filters,
                    **extra,
                },
                source_text=text,
                once_per_turn=once,
                limit_per_turn=limit,
            )
        )

    for branch in branches:
        branch_start = len(rules)
        branch_lower = branch.lower()
        consumed_attack_draw = False
        if "[blocker]" in branch_lower and "change the target of the attack to this card" in branch_lower:
            rules.append(
                EffectRule(
                    trigger="self_blocker_activated",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if "[over realm" in branch_lower and "dark over realm" not in branch_lower:
            if "you can play this card" in branch_lower and "drop" in branch_lower and "warp" in branch_lower:
                rules.append(
                    EffectRule(
                        trigger="self_played",
                        handler_id="noop_auto",
                        handler_params={},
                        source_text=branch,
                        once_per_turn=once,
                    )
            )
            continue
        if "[field]" in branch_lower and "place and activate this card in your battle area" in branch_lower and "activate another [field]" in branch_lower:
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if "[aegis" in branch_lower and "defense step" in branch_lower and "match all colors specified by [aegis]" in branch_lower:
            rules.append(
                EffectRule(
                    trigger="self_aegis_activated",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if (
            "[counter: attack]" in branch_lower
            and "negate the attack" in branch_lower
            and "play this card" in branch_lower
            and "([counter] is activated from your hand by paying the card's energy cost.)" in branch_lower
        ):
            rules.append(
                EffectRule(
                    trigger="counter_attack",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if "[critical]" in branch_lower and "instead of their hand" in branch_lower and "drop" in branch_lower:
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if "[double strike]" in branch_lower and "inflicts" in branch_lower and "instead of" in branch_lower:
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if "[dual attack]" in branch_lower and "switch this card to active mode after the battle" in branch_lower:
            rules.append(
                EffectRule(
                    trigger="self_attacks_battle_end",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if branch_lower.strip() == "[energy-exhaust]" or (
            "[energy-exhaust]" in branch_lower and "energy area" in branch_lower and "rest mode" in branch_lower
        ):
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if "[barrier]" in branch_lower and "can't be chosen" in branch_lower and "opponent" in branch_lower:
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if re.fullmatch(
            r"\[permanent\]\s*this card can'?t attack and isn'?t affected by your opponent'?s skills\.?",
            branch_lower,
        ):
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if re.fullmatch(
            r"\[permanent\]\s*if this card is in rest mode,\s*your opponent'?s battle cards? can'?t attack leaders\.?",
            branch_lower,
        ):
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if re.fullmatch(
            r"\[permanent\]\s*if this card would leave the battle area,\s*remove it from the game instead\.?",
            branch_lower,
        ):
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if (
            "[permanent]" in branch_lower
            and "would reveal this card from your life to add it to your hand" in branch_lower
            and "place it in your energy in rest mode instead" in branch_lower
        ):
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if (
            "[permanent]" in branch_lower
            and "when this card is placed in a drop area from a battle area or combo area" in branch_lower
            and "bottom of its owner's deck instead" in branch_lower
        ):
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if "[permanent]" in branch_lower and "as many copies" in branch_lower and "deck" in branch_lower:
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if "[activate" in branch_lower and "compliment each other" in branch_lower:
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        if branch_lower.strip() == "[blocker]":
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="noop_auto",
                    handler_params={},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            continue
        consumed_play_draw = False
        consumed_combo_draw = False
        m_play_or_combo_draw = _PLAY_OR_COMBO_DRAW_RE.search(branch)
        if m_play_or_combo_draw:
            amount = int(m_play_or_combo_draw.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_draw_n",
                    handler_params={"amount": amount, **extra},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_draw_n",
                    handler_params={"amount": amount, **extra},
                    source_text=branch,
                    once_per_turn=once,
                )
            )
            consumed_play_draw = True
            consumed_combo_draw = True

        # [Auto] When this card is played... draw X card(s)
        m_play_draw = re.search(
            r"(?:if [^:]{1,120}:\s*)?(?:when (?:this card is played(?: from your hand)?|you play this card)|on play).*?draw (\d+) card",
            branch,
        )
        if m_play_draw and not consumed_play_draw:
            amount = int(m_play_draw.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_draw_n",
                    handler_params={"amount": amount, **extra},
                    once_per_turn=once,
                )
            )
        m_play_draw_switch_active = _PLAY_DRAW_AND_SWITCH_SELF_ACTIVE_RE.search(branch)
        if m_play_draw_switch_active:
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_switch_self_active_on_play",
                    handler_params={},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_played_from_under_by_skill_buff = _PLAY_FROM_UNDER_BY_SKILL_GAIN_POWER_AND_KEYWORD_RE.search(branch)
        if m_played_from_under_by_skill_buff:
            power_delta = int(m_played_from_under_by_skill_buff.group(1))
            grant_keyword = " ".join(part.capitalize() for part in m_played_from_under_by_skill_buff.group(2).replace("-", " ").split())
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_self_gain_power_for_turn_on_play",
                    handler_params={
                        "power_delta": power_delta,
                        "grant_keyword": grant_keyword,
                        "requires_played_from": "under",
                        "requires_played_via": "skill",
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_played_under_named_host_gain_power_and_combo_rest = _PLAYED_UNDER_NAMED_HOST_GAIN_POWER_AND_COMBO_REST_RE.search(branch)
        if m_played_under_named_host_gain_power_and_combo_rest:
            host_name = str(m_played_under_named_host_gain_power_and_combo_rest.group(1) or "").strip().upper()
            power_delta = int(m_played_under_named_host_gain_power_and_combo_rest.group(2))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_self_gain_power_for_turn_on_play",
                    handler_params={
                        "power_delta": power_delta,
                        "requires_played_from": "under",
                        "under_host_name_contains": host_name,
                        "grant_can_combo_from_battle_while_resting": True,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_played_under_named_host_gain_power = _PLAYED_UNDER_NAMED_HOST_GAIN_POWER_RE.search(branch)
        if m_played_under_named_host_gain_power and not m_played_under_named_host_gain_power_and_combo_rest:
            host_name = str(m_played_under_named_host_gain_power.group(1) or "").strip().upper()
            power_delta = int(m_played_under_named_host_gain_power.group(2))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_self_gain_power_for_turn_on_play",
                    handler_params={
                        "power_delta": power_delta,
                        "requires_played_from": "under",
                        "under_host_name_contains": host_name,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_played_rest_named_host_place_named_under_then_ko = _PLAYED_REST_NAMED_HOST_PLACE_UP_TO_N_EITHER_NAMED_FROM_HAND_UNDER_IT_THEN_KO_IF_PLACED_RE.search(branch)
        if m_played_rest_named_host_place_named_under_then_ko:
            host_name = str(m_played_rest_named_host_place_named_under_then_ko.group(1) or "").strip().upper()
            max_targets = int(m_played_rest_named_host_place_named_under_then_ko.group(2))
            first_name = str(m_played_rest_named_host_place_named_under_then_ko.group(3) or "").strip().upper()
            second_name = str(m_played_rest_named_host_place_named_under_then_ko.group(4) or "").strip().upper()
            ko_max_targets = int(m_played_rest_named_host_place_named_under_then_ko.group(5))
            ko_max_cost = int(m_played_rest_named_host_place_named_under_then_ko.group(6))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_rest_named_host_and_place_up_to_n_named_from_owner_hand_under_it_then_ko_on_play_if_placed",
                    handler_params={
                        "host_name_contains": host_name,
                        "max_targets": max_targets,
                        "required_name_contains_any": f"{first_name}|{second_name}",
                        "rest_host": True,
                        "ko_max_targets": ko_max_targets,
                        "ko_max_cost": ko_max_cost,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_main_phase_under_play = _MAIN_PHASE_PLAY_FROM_UNDER_SELF_AND_PLACE_SELF_UNDER_PLAYED_RE.search(branch)
        if m_main_phase_under_play:
            phase_owner = str(m_main_phase_under_play.group(1) or "").strip().lower()
            max_targets = int(m_main_phase_under_play.group(2))
            descriptor = m_main_phase_under_play.group(3).lower()
            m_cost_less = re.search(r"energy costs? of (\d+) or less", descriptor)
            if m_cost_less is None:
                m_cost_less = re.search(r"energy cost of (\d+) or less", descriptor)
            m_cost_exact = re.search(r"energy cost of (\d+)\b", descriptor)
            min_cost = int(m_cost_exact.group(1)) if (m_cost_exact and m_cost_less is None) else -1
            max_cost = int(m_cost_less.group(1)) if m_cost_less else (int(m_cost_exact.group(1)) if m_cost_exact else -1)
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "max_cost": max_cost,
                **_descriptor_filters(descriptor, branch),
                **extra,
                **_extract_main_phase_auto_cost_params(branch),
            }
            if min_cost >= 0:
                params["min_cost"] = min_cost
            if "rest mode" in branch:
                params["resting"] = True
            if "with its skills negated" in branch or "with their skills negated" in branch:
                params["negate_skills"] = True
            rules.append(
                EffectRule(
                    trigger="owner_opponent_main_phase_start" if phase_owner.startswith("opponent") else "owner_main_phase_start",
                    handler_id="auto_play_up_to_n_from_under_self_and_place_self_under_played_card",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_main_phase_hand_play = _MAIN_PHASE_PLAY_FROM_OWNER_HAND_RE.search(branch)
        if m_main_phase_hand_play:
            phase_owner = str(m_main_phase_hand_play.group(1) or "").strip().lower()
            max_targets = int(m_main_phase_hand_play.group(2))
            descriptor = m_main_phase_hand_play.group(3).lower()
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                **_descriptor_filters(descriptor, branch),
                **extra,
                **_extract_main_phase_auto_cost_params(branch),
            }
            if "rest mode" in branch:
                params["rest_mode"] = True
            rules.append(
                EffectRule(
                    trigger="owner_opponent_main_phase_start" if phase_owner.startswith("opponent") else "owner_main_phase_start",
                    handler_id="auto_play_up_to_n_from_owner_hand_on_main_phase_start",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_main_phase_drop_play = _MAIN_PHASE_PLAY_FROM_OWNER_DROP_RE.search(branch)
        if m_main_phase_drop_play:
            phase_owner = str(m_main_phase_drop_play.group(1) or "").strip().lower()
            max_targets = int(m_main_phase_drop_play.group(2))
            descriptor = m_main_phase_drop_play.group(3).lower()
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                **_descriptor_filters(descriptor, branch),
                **extra,
                **_extract_main_phase_auto_cost_params(branch),
            }
            if "rest mode" in branch:
                params["rest_mode"] = True
            rules.append(
                EffectRule(
                    trigger="owner_opponent_main_phase_start" if phase_owner.startswith("opponent") else "owner_main_phase_start",
                    handler_id="auto_play_up_to_n_from_owner_drop_on_main_phase_start",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_main_phase_deck_play = _MAIN_PHASE_PLAY_FROM_OWNER_DECK_RE.search(branch)
        if m_main_phase_deck_play:
            phase_owner = str(m_main_phase_deck_play.group(1) or "").strip().lower()
            max_targets = int(m_main_phase_deck_play.group(2))
            descriptor = m_main_phase_deck_play.group(3).lower()
            markers = int(m_main_phase_deck_play.group(4) or 0)
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                **_descriptor_filters(descriptor, branch),
                **extra,
                **_extract_main_phase_auto_cost_params(branch),
            }
            if markers > 0:
                params["markers"] = markers
            if "rest mode" in branch:
                params["rest_mode"] = True
            rules.append(
                EffectRule(
                    trigger="owner_opponent_main_phase_start" if phase_owner.startswith("opponent") else "owner_main_phase_start",
                    handler_id="auto_play_up_to_n_from_owner_deck_on_main_phase_start",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_main_phase_hand_play_on_top = _MAIN_PHASE_PLAY_FROM_OWNER_HAND_ON_TOP_OF_SELF_RE.search(branch)
        if m_main_phase_hand_play_on_top:
            phase_owner = str(m_main_phase_hand_play_on_top.group(1) or "").strip().lower()
            max_targets = int(m_main_phase_hand_play_on_top.group(2))
            descriptor = m_main_phase_hand_play_on_top.group(3).lower()
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                **_descriptor_filters(descriptor, branch),
                **extra,
                **_extract_main_phase_auto_cost_params(branch),
            }
            rules.append(
                EffectRule(
                    trigger="owner_opponent_main_phase_start" if phase_owner.startswith("opponent") else "owner_main_phase_start",
                    handler_id="auto_play_up_to_n_from_owner_hand_on_top_of_self_on_main_phase_start",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_main_phase_switch_energy = _MAIN_PHASE_SWITCH_UP_TO_N_OWNER_ENERGY_ACTIVE_RE.search(branch)
        if m_main_phase_switch_energy:
            phase_owner = str(m_main_phase_switch_energy.group(1) or "").strip().lower()
            max_targets = int(m_main_phase_switch_energy.group(2))
            descriptor = str(m_main_phase_switch_energy.group(3) or "").lower()
            colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black)\b", descriptor)))
            requires_multicolor = "multicolor" in descriptor
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                **extra,
                **_extract_main_phase_auto_cost_params(branch),
            }
            if colors:
                params["allowed_colors"] = ",".join(colors)
            if requires_multicolor:
                params["requires_multicolor"] = True
            rules.append(
                EffectRule(
                    trigger="owner_opponent_main_phase_start" if phase_owner.startswith("opponent") else "owner_main_phase_start",
                    handler_id="auto_switch_up_to_n_owner_energy_active_on_main_phase_start",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_main_phase_switch_self = _MAIN_PHASE_SWITCH_SELF_ACTIVE_AND_GAIN_KEYWORD_RE.search(branch)
        if m_main_phase_switch_self:
            phase_owner = str(m_main_phase_switch_self.group(1) or "").strip().lower()
            grant_keyword = " ".join(part.capitalize() for part in m_main_phase_switch_self.group(2).replace("-", " ").split())
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_opponent_main_phase_start" if phase_owner.startswith("opponent") else "owner_main_phase_start",
                    handler_id="auto_switch_self_active_and_gain_keyword_for_turn_on_main_phase_start",
                    handler_params={
                        "grant_keyword": grant_keyword,
                        **extra,
                        **_extract_main_phase_auto_cost_params(branch),
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_main_phase_draw_switch = _MAIN_PHASE_DRAW_SWITCH_LEADER_AND_ENERGY_ACTIVE_AND_GRANT_KEYWORD_RE.search(branch)
        if m_main_phase_draw_switch:
            phase_owner = str(m_main_phase_draw_switch.group(1) or "").strip().lower()
            amount = int(m_main_phase_draw_switch.group(2))
            max_leader_targets = int(m_main_phase_draw_switch.group(3))
            max_energy_targets = int(m_main_phase_draw_switch.group(4))
            grant_keyword = " ".join(part.capitalize() for part in m_main_phase_draw_switch.group(5).replace("-", " ").split())
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_opponent_main_phase_start" if phase_owner.startswith("opponent") else "owner_main_phase_start",
                    handler_id="auto_draw_n_switch_up_to_n_owner_leader_and_energy_active_and_grant_owner_leader_keyword_for_turn",
                    handler_params={
                        "amount": amount,
                        "max_leader_targets": max_leader_targets,
                        "max_energy_targets": max_energy_targets,
                        "grant_keyword": grant_keyword,
                        **extra,
                        **_extract_main_phase_auto_cost_params(branch),
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_main_phase_draw = None if m_main_phase_draw_switch else _MAIN_PHASE_DRAW_RE.search(branch)
        if m_main_phase_draw:
            phase_owner = str(m_main_phase_draw.group(1) or "").strip().lower()
            amount = int(m_main_phase_draw.group(2))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_opponent_main_phase_start" if phase_owner.startswith("opponent") else "owner_main_phase_start",
                    handler_id="auto_draw_n",
                    handler_params={
                        "amount": amount,
                        **extra,
                        **_extract_main_phase_auto_cost_params(branch),
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_main_phase_play_token_until_count = _MAIN_PHASE_PLAY_TOKEN_UNTIL_COUNT_RE.search(branch)
        if m_main_phase_play_token_until_count:
            phase_owner = str(m_main_phase_play_token_until_count.group(1) or "").strip().lower()
            token_name = _normalize_token_name(m_main_phase_play_token_until_count.group(2))
            until_battle_count = int(m_main_phase_play_token_until_count.group(3))
            power, combo_cost, combo_power = _extract_token_stats(branch)
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_opponent_main_phase_start" if phase_owner.startswith("opponent") else "owner_main_phase_start",
                    handler_id="auto_play_token_in_battle_on_main_phase_start",
                    handler_params={
                        "amount": until_battle_count,
                        "until_battle_count": until_battle_count,
                        "token_name": token_name,
                        "power": power,
                        "combo_cost": combo_cost,
                        "combo_power": combo_power,
                        "resting": "in rest mode" in branch.lower(),
                        **extra,
                        **_extract_main_phase_auto_cost_params(branch),
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_main_phase_play_token = _MAIN_PHASE_PLAY_TOKEN_RE.search(branch)
        if m_main_phase_play_token and m_main_phase_play_token_until_count is None:
            phase_owner = str(m_main_phase_play_token.group(1) or "").strip().lower()
            token_name = _normalize_token_name(m_main_phase_play_token.group(3))
            power, combo_cost, combo_power = _extract_token_stats(
                branch,
                explicit_power=m_main_phase_play_token.group(4) or m_main_phase_play_token.group(7),
                explicit_combo_cost=m_main_phase_play_token.group(5),
                explicit_combo_power=m_main_phase_play_token.group(6),
            )
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "amount": int(m_main_phase_play_token.group(2)),
                "token_name": token_name,
                "power": power,
                "combo_cost": combo_cost,
                "combo_power": combo_power,
                "resting": "in rest mode" in branch.lower(),
                **extra,
                **_extract_main_phase_auto_cost_params(branch),
            }
            if m_main_phase_play_token.group(8):
                params["controller_player_scope"] = "opponent"
            rules.append(
                EffectRule(
                    trigger="owner_opponent_main_phase_start" if phase_owner.startswith("opponent") else "owner_main_phase_start",
                    handler_id="auto_play_token_in_battle_on_main_phase_start",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_leader_attack_life_then_draw = _LEADER_ATTACK_ADD_LIFE_TO_HAND_THEN_DRAW_RE.search(branch)
        if m_leader_attack_life_then_draw and card_type == "LEADER":
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_leader_attacks",
                    handler_id="auto_add_up_to_n_from_owner_life_to_hand_then_draw_n_on_owner_leader_attack",
                    handler_params={
                        "max_targets": int(m_leader_attack_life_then_draw.group(1)),
                        "draw_count": int(m_leader_attack_life_then_draw.group(2)),
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            consumed_attack_draw = True

        m_leader_attack_hand_to_drop_then_draw = _LEADER_ATTACK_PLACE_UP_TO_N_FROM_OWNER_HAND_INTO_DROP_THEN_DRAW_RE.search(branch)
        if m_leader_attack_hand_to_drop_then_draw and card_type == "LEADER":
            descriptor = m_leader_attack_hand_to_drop_then_draw.group(2).lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_leader_attacks",
                    handler_id="auto_place_up_to_n_matching_from_owner_hand_into_drop_then_draw_n_on_owner_leader_attack",
                    handler_params={
                        "max_targets": int(m_leader_attack_hand_to_drop_then_draw.group(1)),
                        "draw_count": int(m_leader_attack_hand_to_drop_then_draw.group(3)),
                        "target_policy": "first",
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            consumed_attack_draw = True

        m_owner_battle_attack_gain_power_then_add = _OWNER_BATTLE_ATTACKS_GAIN_POWER_THEN_ADD_UP_TO_N_FROM_OWNER_DECK_OR_LIFE_TO_HAND_RE.search(branch)
        if m_owner_battle_attack_gain_power_then_add and card_type == "LEADER":
            descriptor = m_owner_battle_attack_gain_power_then_add.group(3).lower()
            extra = _extract_common_conditions(branch)
            params = {
                "power_delta": int(m_owner_battle_attack_gain_power_then_add.group(1)),
                "max_targets": int(m_owner_battle_attack_gain_power_then_add.group(2)),
                "source_pool": "deck_or_life",
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if "shuffle any areas you looked through" in branch.lower():
                params["shuffle_searched_zones"] = True
            rules.append(
                EffectRule(
                    trigger="owner_battle_attacks",
                    handler_id="auto_owner_battle_gain_power_then_add_up_to_n_matching_from_owner_deck_or_life_to_hand_on_attack",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_self_aegis_mill_if_no_other_match = _SELF_AEGIS_PLACE_TOP_N_FROM_OPPONENT_DECK_IF_NO_OTHER_OWNER_MATCHING_RE.search(branch)
        if m_self_aegis_mill_if_no_other_match:
            descriptor_raw = str(m_self_aegis_mill_if_no_other_match.group(1) or "").strip()
            descriptor = descriptor_raw.lower()
            filters = _descriptor_filters(descriptor, branch)
            if "<" in descriptor_raw and "required_characters" not in filters and "required_traits" in filters:
                filters["required_characters"] = str(filters.pop("required_traits"))
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "amount": int(m_self_aegis_mill_if_no_other_match.group(2)),
                **extra,
            }
            for key, value in filters.items():
                if key == "required_traits":
                    params["required_no_other_owner_traits"] = value
                elif key == "required_characters":
                    params["required_no_other_owner_characters"] = value
                elif key == "required_name_contains":
                    params["required_no_other_owner_name_contains"] = value
                elif key == "required_card_type":
                    params["required_no_other_owner_card_types"] = value
                else:
                    params[key] = value
            rules.append(
                EffectRule(
                    trigger="self_aegis_activated",
                    handler_id="auto_place_top_n_from_opponent_deck_into_drop_on_aegis",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_field_placed_add_from_deck = _FIELD_EXTRA_PLACED_ADD_UP_TO_N_FROM_OWNER_DECK_TO_HAND_RE.search(branch)
        if m_field_placed_add_from_deck:
            max_targets = int(m_field_placed_add_from_deck.group(1))
            descriptor = str(m_field_placed_add_from_deck.group(2) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "shuffle_deck_after": "shuffle your deck" in branch.lower(),
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="self_field_extra_placed",
                    handler_id="auto_add_up_to_n_from_owner_deck_to_hand_on_play",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_field_placed_restrict_skills = _FIELD_EXTRA_PLACED_RESTRICT_UP_TO_N_OPPONENT_BATTLE_SKILLS_WHILE_SELF_IN_BATTLE_RE.search(branch)
        if m_field_placed_restrict_skills:
            extra = _extract_common_conditions(branch)
            if "if your leader is a blue <cooler> card" in text.lower():
                extra = {
                    **extra,
                    "leader_allowed_colors": "blue",
                    "leader_required_characters": "Cooler",
                }
            rules.append(
                EffectRule(
                    trigger="self_field_extra_placed",
                    handler_id="auto_restrict_up_to_n_opponent_battle_skills_while_self_in_battle_on_field_extra_placed",
                    handler_params={
                        "max_targets": int(m_field_placed_restrict_skills.group(1)),
                        "target_policy": "first",
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_field_placed_grant_keyword = _FIELD_EXTRA_PLACED_GRANT_KEYWORD_TO_UP_TO_N_OWNER_BATTLE_WHILE_SELF_IN_BATTLE_RE.search(branch)
        if m_field_placed_grant_keyword:
            descriptor = str(m_field_placed_grant_keyword.group(2) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            filters = _descriptor_filters(descriptor, branch)
            if "cooler's armored squadron" in descriptor and "<cooler>" in descriptor:
                filters = {
                    "allowed_colors": "blue",
                    "required_name_contains": "COOLER",
                }
            if "if your leader is a blue <cooler> card" in text.lower():
                extra = {
                    **extra,
                    "leader_allowed_colors": "blue",
                    "leader_required_characters": "Cooler",
                }
            rules.append(
                EffectRule(
                    trigger="self_field_extra_placed",
                    handler_id="auto_grant_keyword_to_up_to_n_owner_battle_while_self_in_battle_on_field_extra_placed",
                    handler_params={
                        "max_targets": int(m_field_placed_grant_keyword.group(1)),
                        "grant_keyword": str(m_field_placed_grant_keyword.group(3) or "").strip(),
                        "target_policy": "first",
                        **filters,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        # [Auto] When this card attacks... draw X card(s)
        m_attack_draw = _ATTACK_DRAW_RE.search(branch)
        if m_attack_draw and not consumed_attack_draw:
            amount = int(m_attack_draw.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_draw_n",
                    handler_params={"amount": amount, **extra},
                    once_per_turn=once,
                )
            )

        m_attack_add_life = _ATTACK_ADD_UP_TO_N_FROM_OWNER_LIFE_TO_HAND_RE.search(branch)
        if m_attack_add_life:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_add_up_to_n_from_owner_life_to_hand_on_attack",
                    handler_params={"max_targets": int(m_attack_add_life.group(1)), **extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_attack_play_token = _ATTACK_PLAY_TOKEN_RE.search(branch)
        m_attack_play_a_token = _ATTACK_PLAY_A_TOKEN_RE.search(branch) if m_attack_play_token is None else None
        if m_attack_play_token or m_attack_play_a_token:
            token_name = _normalize_token_name(
                m_attack_play_token.group(2) if m_attack_play_token else m_attack_play_a_token.group(1)
            )
            power, combo_cost, combo_power = _extract_token_stats(
                branch,
                token_name=token_name,
                explicit_power=(
                    (m_attack_play_token.group(3) or m_attack_play_token.group(6))
                    if m_attack_play_token
                    else (m_attack_play_a_token.group(2) or m_attack_play_a_token.group(5))
                ),
                explicit_combo_cost=(m_attack_play_token.group(4) if m_attack_play_token else m_attack_play_a_token.group(3)),
                explicit_combo_power=(m_attack_play_token.group(5) if m_attack_play_token else m_attack_play_a_token.group(4)),
            )
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_play_token_in_battle_on_attack",
                    handler_params={
                        "amount": int(m_attack_play_token.group(1)) if m_attack_play_token else 1,
                        "token_name": token_name,
                        "power": power,
                        "combo_cost": combo_cost,
                        "combo_power": combo_power,
                        "resting": "in rest mode" in branch.lower(),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_attack_place_under_self = _ATTACK_PLACE_UP_TO_N_OPPONENT_BATTLE_UNDER_SELF_RE.search(branch)
        if m_attack_place_under_self:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_place_up_to_n_opponent_battle_under_self_on_attack",
                    handler_params={
                        "max_targets": int(m_attack_place_under_self.group(1)),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_attack_discard_and_next_turn_play_and_z_energy = _ATTACK_DISCARD_AND_NEXT_TURN_PLAY_AND_Z_ENERGY_FROM_WARP_RE.search(branch)
        if m_attack_discard_and_next_turn_play_and_z_energy:
            release_under = int(m_attack_discard_and_next_turn_play_and_z_energy.group(1))
            discard_amount = int(m_attack_discard_and_next_turn_play_and_z_energy.group(2))
            first_character = str(m_attack_discard_and_next_turn_play_and_z_energy.group(3) or "").strip().strip("<>").strip().title()
            second_character = str(m_attack_discard_and_next_turn_play_and_z_energy.group(4) or "").strip().strip("<>").strip().title()
            exact_cost = int(m_attack_discard_and_next_turn_play_and_z_energy.group(5))
            play_max = int(m_attack_discard_and_next_turn_play_and_z_energy.group(6))
            z_energy_max = int(m_attack_discard_and_next_turn_play_and_z_energy.group(7))
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "amount": discard_amount,
                "auto_release_under_to_warp_before": release_under,
                "trigger_kind": "main_phase_start",
                "trigger_player_scope": "owner",
                "affected_player_scope": "owner",
                "max_targets": play_max,
                "add_to_z_energy_max_targets": z_energy_max,
                "min_cost": exact_cost,
                "max_cost": exact_cost,
                "first_required_characters": first_character,
                "second_required_characters": second_character,
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_opponent_discards_n_and_schedule_play_and_add_marked_warped_cards_on_attack",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_attack_or_blocker_switch_self_active = _ATTACK_OR_BLOCKER_SWITCH_SELF_ACTIVE_RE.search(branch)
        if m_attack_or_blocker_switch_self_active:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_attacks_or_self_blocker_activated",
                    handler_id="auto_switch_self_active_on_attack_or_blocker",
                    handler_params={**extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_attack_discard_hand_switch_owner_battle_active = _ATTACK_MAY_DISCARD_HAND_THEN_SWITCH_UP_TO_N_OWNER_BATTLE_ACTIVE_RE.search(branch)
        if m_attack_discard_hand_switch_owner_battle_active:
            raw_descriptor = str(m_attack_discard_hand_switch_owner_battle_active.group(3) or "").strip()
            descriptor = raw_descriptor.lower()
            filters = _descriptor_filters(descriptor, branch)
            if "<" in raw_descriptor and "required_characters" not in filters and "required_traits" in filters:
                filters["required_characters"] = str(filters.pop("required_traits"))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_discard_n_then_switch_up_to_n_owner_battle_active_on_attack",
                    handler_params={
                        "auto_discard_hand_before": int(m_attack_discard_hand_switch_owner_battle_active.group(1)),
                        "max_targets": int(m_attack_discard_hand_switch_owner_battle_active.group(2)),
                        "target_policy": "first",
                        **filters,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        # [Auto] Add N life to hand: when this card attacks, it gets +X power and optional [Keyword] for the turn.
        m_attack_pay_life = _ATTACK_PAY_LIFE_GAIN_POWER_AND_KEYWORD_RE.search(branch)
        if m_attack_pay_life:
            life_to_hand = int(m_attack_pay_life.group(1))
            power_delta = int(m_attack_pay_life.group(2))
            raw_kw = (m_attack_pay_life.group(3) or "").strip()
            grant_keyword = " ".join(part.capitalize() for part in raw_kw.replace("-", " ").split()) if raw_kw else ""
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "life_to_hand": life_to_hand,
                "power_delta": power_delta,
                **extra,
            }
            if grant_keyword:
                params["grant_keyword"] = grant_keyword
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_pay_life_on_attack_gain_power_and_keyword_for_turn",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        # [Auto] When your leader attacks... choose N in hand and add it to life.
        m_owner_leader_attack_life = _OWNER_LEADER_ATTACK_ADD_FROM_HAND_TO_LIFE_RE.search(branch)
        if m_owner_leader_attack_life:
            amount = int(m_owner_leader_attack_life.group(1))
            descriptor = m_owner_leader_attack_life.group(2).lower()
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "amount": amount,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="owner_leader_attacks",
                    handler_id="auto_add_up_to_n_from_owner_hand_to_life_on_owner_leader_attack",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        # [Auto] When your leader attacks... look at top N; add up to M matching cards to hand.
        m_owner_leader_attack_search = _OWNER_LEADER_ATTACK_LOOK_TOP_ADD_TO_HAND_RE.search(branch)
        if m_owner_leader_attack_search is None:
            m_owner_leader_attack_search = _OWNER_LEADER_ATTACK_LOOK_TOP_ADD_DIRECT_TO_HAND_RE.search(branch)
        if m_owner_leader_attack_search:
            look_count = int(m_owner_leader_attack_search.group(1))
            max_add = int(m_owner_leader_attack_search.group(2))
            descriptor = m_owner_leader_attack_search.group(3).lower()
            extra = _extract_common_conditions(m_owner_leader_attack_search.group(0))
            params = {
                "look_count": look_count,
                "max_add": max_add,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="owner_leader_attacks",
                    handler_id="auto_look_top_add_up_to_one_to_hand_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        # Leader [Auto] When this card attacks... look at top N; add up to M matching cards to hand.
        if (card.card_type or "").upper() == "LEADER":
            m_leader_self_attack_search = _LEADER_SELF_ATTACK_LOOK_TOP_ADD_TO_HAND_RE.search(branch)
            if m_leader_self_attack_search is None:
                m_leader_self_attack_search = _LEADER_SELF_ATTACK_LOOK_TOP_ADD_DIRECT_TO_HAND_RE.search(branch)
            if m_leader_self_attack_search:
                look_count = int(m_leader_self_attack_search.group(1))
                max_add = int(m_leader_self_attack_search.group(2))
                descriptor = m_leader_self_attack_search.group(3).lower()
                extra = _extract_common_conditions(m_leader_self_attack_search.group(0))
                params = {
                    "look_count": look_count,
                    "max_add": max_add,
                    **_descriptor_filters(descriptor, branch),
                    **extra,
                }
                rules.append(
                    EffectRule(
                        trigger="owner_leader_attacks",
                        handler_id="auto_look_top_add_up_to_one_to_hand_on_play",
                        handler_params=params,
                        once_per_turn=once,
                    )
                )

        # [Auto] When this card is used in a combo... draw X card(s)
        m_combo_draw = _COMBO_DRAW_RE.search(branch)
        if m_combo_draw and not consumed_combo_draw:
            amount = int(m_combo_draw.group(1))
            extra = _extract_common_conditions(branch)
            lower_branch = branch.lower()
            if "this card in your battle area is used in a combo" in lower_branch:
                extra["requires_comboed_from"] = "battle"
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_draw_n",
                    handler_params={"amount": amount, **extra},
                    once_per_turn=once,
                )
            )

        m_combo_add_from_deck_to_hand = _COMBO_TRIGGER_ADD_UP_TO_N_FROM_OWNER_DECK_TO_HAND_RE.search(branch)
        if m_combo_add_from_deck_to_hand:
            combo_from = str(m_combo_add_from_deck_to_hand.group(1) or "").strip().lower()
            max_targets = int(m_combo_add_from_deck_to_hand.group(2))
            descriptor = str(m_combo_add_from_deck_to_hand.group(3) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            raw_leader_req = str(extra.get("requires_leader", "") or "")
            if " and you choose " in raw_leader_req.lower() and "remove it from the game" in branch.lower():
                extra["requires_leader"] = raw_leader_req.split(" and you choose ", 1)[0].strip()
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if combo_from == "hand":
                params["requires_comboed_from"] = "hand"
            elif combo_from == "battle area":
                params["requires_comboed_from"] = "battle"
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_add_up_to_n_from_owner_deck_to_hand_on_combo",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_leader_placed_activate_named_field_extra = _LEADER_PLACED_ACTIVATE_UP_TO_N_NAMED_FIELD_EXTRA_FROM_OWNER_DECK_RE.search(branch)
        if m_leader_placed_activate_named_field_extra:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_placed_in_leader_area",
                    handler_id="auto_activate_up_to_n_named_field_extra_from_owner_deck_on_leader_placed",
                    handler_params={
                        "max_targets": int(m_leader_placed_activate_named_field_extra.group(1)),
                        "required_name_contains": str(m_leader_placed_activate_named_field_extra.group(2) or "").strip().upper(),
                        "required_card_type": "EXTRA",
                        "requires_field_keyword": True,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_added_to_z_energy_draw = _ADDED_TO_Z_ENERGY_DRAW_RE.search(branch)
        if m_added_to_z_energy_draw:
            amount = int(m_added_to_z_energy_draw.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_added_to_z_energy",
                    handler_id="auto_draw_n",
                    handler_params={"amount": amount, **extra},
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_added_to_z_energy_owner_battle_power = _ADDED_TO_Z_ENERGY_OWNER_BATTLE_GAIN_POWER_RE.search(branch)
        if m_added_to_z_energy_owner_battle_power:
            max_targets = int(m_added_to_z_energy_owner_battle_power.group(1))
            descriptor = str(m_added_to_z_energy_owner_battle_power.group(2) or "").strip().lower()
            power_delta = int(m_added_to_z_energy_owner_battle_power.group(3))
            filters = _descriptor_filters(descriptor, branch)
            if "<" in descriptor and "required_characters" not in filters and "required_traits" in filters:
                filters["required_characters"] = str(filters.pop("required_traits"))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_added_to_z_energy",
                    handler_id="auto_buff_up_to_n_owner_battle_on_z_energy_added",
                    handler_params={
                        "max_targets": max_targets,
                        "power_delta": power_delta,
                        **filters,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_added_to_z_energy_switch_opp_board = _ADDED_TO_Z_ENERGY_SWITCH_OPPONENT_BOARD_RE.search(branch)
        if m_added_to_z_energy_switch_opp_board:
            max_targets = int(m_added_to_z_energy_switch_opp_board.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_added_to_z_energy",
                    handler_id="auto_switch_up_to_n_opponent_board_rest",
                    handler_params={
                        "max_targets": max_targets,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_placed_under_owner_card_power_reduce = _PLACED_UNDER_OWNER_CARD_POWER_REDUCE_RE.search(branch)
        if m_placed_under_owner_card_power_reduce:
            host_descriptor = str(m_placed_under_owner_card_power_reduce.group(1) or "").strip().lower()
            max_targets = int(m_placed_under_owner_card_power_reduce.group(2))
            power_delta = -int(m_placed_under_owner_card_power_reduce.group(3))
            host_filters = _descriptor_filters(host_descriptor, branch)
            if "<" in host_descriptor and "required_characters" not in host_filters and "required_traits" in host_filters:
                host_filters["required_characters"] = str(host_filters.pop("required_traits"))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_placed_under_owner_card",
                    handler_id="auto_power_reduce_up_to_n_on_placed_under",
                    handler_params={
                        "requires_placed_from_zones": "hand,z_energy,combo",
                        "max_targets": max_targets,
                        "power_delta": power_delta,
                        "host_allowed_colors": str(host_filters.get("allowed_colors", "")),
                        "host_required_traits": str(host_filters.get("required_traits", "")),
                        "host_required_characters": str(host_filters.get("required_characters", "")),
                        "host_required_name_contains": str(host_filters.get("required_name_contains", "")),
                        "host_required_card_type": str(host_filters.get("required_card_type", "")),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_placed_under_owner_leader_add_deck_to_hand_discard = _PLACED_UNDER_OWNER_LEADER_ADD_DECK_TO_HAND_DISCARD_RE.search(branch)
        if m_placed_under_owner_leader_add_deck_to_hand_discard:
            host_descriptor = str(m_placed_under_owner_leader_add_deck_to_hand_discard.group(1) or "").strip().lower()
            max_targets = int(m_placed_under_owner_leader_add_deck_to_hand_discard.group(2))
            search_descriptor = str(m_placed_under_owner_leader_add_deck_to_hand_discard.group(3) or "").strip().lower()
            discard_count = int(m_placed_under_owner_leader_add_deck_to_hand_discard.group(4))
            host_filters = _descriptor_filters(host_descriptor, branch)
            if "<" in host_descriptor and "required_characters" not in host_filters and "required_traits" in host_filters:
                host_filters["required_characters"] = str(host_filters.pop("required_traits"))
            search_filters = _descriptor_filters(search_descriptor, branch)
            if "<" in search_descriptor and "required_characters" not in search_filters and "required_traits" in search_filters:
                search_filters["required_characters"] = str(search_filters.pop("required_traits"))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_placed_under_owner_card",
                    handler_id="auto_add_up_to_n_from_owner_deck_to_hand_then_discard_n_on_placed_under",
                    handler_params={
                        "requires_placed_from_zones": "hand",
                        "required_host_zone": "leader",
                        "max_targets": max_targets,
                        "discard_count": discard_count,
                        "allowed_colors": str(search_filters.get("allowed_colors", "")),
                        "required_traits": str(search_filters.get("required_traits", "")),
                        "required_characters": str(search_filters.get("required_characters", "")),
                        "required_name_contains": str(search_filters.get("required_name_contains", "")),
                        "required_card_type": str(search_filters.get("required_card_type", "")),
                        "max_cost": int(search_filters.get("max_cost", -1) or -1),
                        "host_allowed_colors": str(host_filters.get("allowed_colors", "")),
                        "host_required_traits": str(host_filters.get("required_traits", "")),
                        "host_required_characters": str(host_filters.get("required_characters", "")),
                        "host_required_name_contains": str(host_filters.get("required_name_contains", "")),
                        "host_required_card_type": str(host_filters.get("required_card_type", "")),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_placed_under_owner_leader_draw = _PLACED_UNDER_OWNER_LEADER_DRAW_RE.search(branch)
        if m_placed_under_owner_leader_draw:
            source_scope = str(m_placed_under_owner_leader_draw.group(1) or "").strip().lower()
            host_descriptor = str(m_placed_under_owner_leader_draw.group(2) or "").strip().lower()
            amount = int(m_placed_under_owner_leader_draw.group(3))
            host_filters = _descriptor_filters(host_descriptor, branch)
            if "<" in host_descriptor and "required_characters" not in host_filters and "required_traits" in host_filters:
                host_filters["required_characters"] = str(host_filters.pop("required_traits"))
            requires_placed_from_zones = ""
            if source_scope == "hand":
                requires_placed_from_zones = "hand"
            elif source_scope == "battle area":
                requires_placed_from_zones = "battle"
            elif source_scope == "hand or battle area":
                requires_placed_from_zones = "hand,battle"
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "required_host_zone": "leader",
                "amount": amount,
                "host_allowed_colors": str(host_filters.get("allowed_colors", "")),
                "host_required_traits": str(host_filters.get("required_traits", "")),
                "host_required_characters": str(host_filters.get("required_characters", "")),
                "host_required_name_contains": str(host_filters.get("required_name_contains", "")),
                "host_required_card_type": str(host_filters.get("required_card_type", "")),
                **extra,
            }
            if requires_placed_from_zones:
                params["requires_placed_from_zones"] = requires_placed_from_zones
            rules.append(
                EffectRule(
                    trigger="self_placed_under_owner_card",
                    handler_id="auto_draw_n",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_placed_under_owner_leader_buff = _PLACED_UNDER_OWNER_LEADER_OWNER_LEADER_GAIN_POWER_RE.search(branch)
        if m_placed_under_owner_leader_buff:
            source_scope = str(m_placed_under_owner_leader_buff.group(1) or "").strip().lower()
            host_descriptor = str(m_placed_under_owner_leader_buff.group(2) or "").strip().lower()
            leader_power_delta = int(m_placed_under_owner_leader_buff.group(3))
            host_filters = _descriptor_filters(host_descriptor, branch)
            if "<" in host_descriptor and "required_characters" not in host_filters and "required_traits" in host_filters:
                host_filters["required_characters"] = str(host_filters.pop("required_traits"))
            requires_placed_from_zones = ""
            if source_scope == "hand":
                requires_placed_from_zones = "hand"
            elif source_scope == "battle area":
                requires_placed_from_zones = "battle"
            elif source_scope == "hand or battle area":
                requires_placed_from_zones = "hand,battle"
            extra = _extract_common_conditions(branch)
            params = {
                "required_host_zone": "leader",
                "leader_power_delta": leader_power_delta,
                "host_allowed_colors": str(host_filters.get("allowed_colors", "")),
                "host_required_traits": str(host_filters.get("required_traits", "")),
                "host_required_characters": str(host_filters.get("required_characters", "")),
                "host_required_name_contains": str(host_filters.get("required_name_contains", "")),
                "host_required_card_type": str(host_filters.get("required_card_type", "")),
                **extra,
            }
            if requires_placed_from_zones:
                params["requires_placed_from_zones"] = requires_placed_from_zones
            rules.append(
                EffectRule(
                    trigger="self_placed_under_owner_card",
                    handler_id="auto_buff_owner_leader_for_turn_on_placed_under",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_self_placed_into_drop_use_in_combo_from_drop = _SELF_PLACED_INTO_DROP_USE_IN_COMBO_FROM_DROP_RE.search(branch)
        if m_self_placed_into_drop_use_in_combo_from_drop:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_placed_into_drop",
                    handler_id="auto_combo_self_from_drop_on_placed_into_drop",
                    handler_params={
                        "requires_placed_from_zones": "leader_under",
                        "required_drop_causes": "leader_skill",
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_self_placed_into_drop_draw_and_play_self_from_drop = _SELF_PLACED_INTO_DROP_DRAW_AND_PLAY_SELF_FROM_DROP_RE.search(branch)
        if m_self_placed_into_drop_draw_and_play_self_from_drop:
            amount = int(m_self_placed_into_drop_draw_and_play_self_from_drop.group(1))
            markers = int(m_self_placed_into_drop_draw_and_play_self_from_drop.group(2))
            extra = _extract_common_conditions(branch)
            common_params: dict[str, int | str | bool] = {
                "requires_placed_from_zones": "hand,leader_under",
                "required_drop_causes": "leader_skill",
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="self_placed_into_drop",
                    handler_id="auto_draw_n",
                    handler_params={
                        "amount": amount,
                        **common_params,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_placed_into_drop",
                    handler_id="auto_play_self_from_drop_on_hand_drop",
                    handler_params={
                        "marker_count": markers,
                        **common_params,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_placed_under_owner_card_grant_keywords = _PLACED_UNDER_OWNER_CARD_GRANT_KEYWORDS_RE.search(branch)
        if m_placed_under_owner_card_grant_keywords:
            host_descriptor = str(m_placed_under_owner_card_grant_keywords.group(1) or "").strip().lower()
            raw_keywords = str(m_placed_under_owner_card_grant_keywords.group(2) or "")
            keywords = [
                " ".join(part.capitalize() for part in keyword.replace("-", " ").split())
                for keyword in re.findall(r"\[([^\]]+)\]", raw_keywords)
                if str(keyword).strip()
            ]
            host_filters = _descriptor_filters(host_descriptor, branch)
            if "<" in host_descriptor and "required_characters" not in host_filters and "required_traits" in host_filters:
                host_filters["required_characters"] = str(host_filters.pop("required_traits"))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_placed_under_owner_card",
                    handler_id="auto_host_gain_keywords_until_opponent_turn_on_placed_under",
                    handler_params={
                        "required_host_zone": "battle",
                        "host_allowed_colors": str(host_filters.get("allowed_colors", "")),
                        "host_required_traits": str(host_filters.get("required_traits", "")),
                        "host_required_characters": str(host_filters.get("required_characters", "")),
                        "host_required_name_contains": str(host_filters.get("required_name_contains", "")),
                        "host_required_card_type": str(host_filters.get("required_card_type", "")),
                        "host_requires_all_characters": "with both <" in host_descriptor,
                        "grant_keywords": ",".join(keywords),
                        "keyword_duration": "opponent_turn",
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_placed_under_owner_card_place_named_from_deck = _PLACED_UNDER_OWNER_CARD_PLACE_NAMED_FROM_OWNER_DECK_UNDER_NAMED_HOST_RE.search(branch)
        if m_placed_under_owner_card_place_named_from_deck:
            host_name = str(m_placed_under_owner_card_place_named_from_deck.group(1) or "").strip().upper()
            max_targets = int(m_placed_under_owner_card_place_named_from_deck.group(2))
            required_name = str(m_placed_under_owner_card_place_named_from_deck.group(3) or "").strip().upper()
            target_host_name = str(m_placed_under_owner_card_place_named_from_deck.group(4) or "").strip().upper()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_placed_under_owner_card",
                    handler_id="auto_place_up_to_n_named_from_owner_deck_under_named_host_on_placed_under",
                    handler_params={
                        "requires_placed_from_zones": "hand",
                        "required_host_zone": "battle",
                        "host_name_contains": host_name,
                        "max_targets": max_targets,
                        "required_name_contains": required_name,
                        "target_host_name_contains": target_host_name,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_placed_under_owner_card_place_from_deck_under_target_host = _PLACED_UNDER_OWNER_CARD_PLACE_FROM_OWNER_DECK_UNDER_TARGET_HOST_RE.search(branch)
        if m_placed_under_owner_card_place_from_deck_under_target_host:
            host_name = str(m_placed_under_owner_card_place_from_deck_under_target_host.group(1) or "").strip().upper()
            max_targets = int(m_placed_under_owner_card_place_from_deck_under_target_host.group(2))
            search_descriptor_raw = str(m_placed_under_owner_card_place_from_deck_under_target_host.group(3) or "").strip()
            target_host_descriptor_raw = str(m_placed_under_owner_card_place_from_deck_under_target_host.group(4) or "").strip()
            if "{" not in search_descriptor_raw and "{" not in target_host_descriptor_raw:
                search_filters = {
                    k: v
                    for k, v in _descriptor_filters(search_descriptor_raw.lower(), branch).items()
                    if k in {"allowed_colors", "required_traits", "required_characters", "required_name_contains"}
                }
                if "<" in search_descriptor_raw and "required_characters" not in search_filters and "required_traits" in search_filters:
                    search_filters["required_characters"] = str(search_filters.pop("required_traits"))
                target_host_filters = {
                    k: v
                    for k, v in _descriptor_filters(target_host_descriptor_raw.lower(), branch).items()
                    if k in {"allowed_colors", "required_traits", "required_characters", "required_name_contains"}
                }
                if "<" in target_host_descriptor_raw and "required_characters" not in target_host_filters and "required_traits" in target_host_filters:
                    target_host_filters["required_characters"] = str(target_host_filters.pop("required_traits"))
                if "z-extra" in target_host_descriptor_raw.lower() or " extra" in target_host_descriptor_raw.lower():
                    target_host_filters["required_card_type"] = "EXTRA"
                extra = _extract_common_conditions(branch)
                rules.append(
                    EffectRule(
                        trigger="self_placed_under_owner_card",
                        handler_id="auto_place_up_to_n_named_from_owner_deck_under_named_host_on_placed_under",
                        handler_params={
                            "requires_placed_from_zones": "hand",
                            "required_host_zone": "battle",
                            "host_name_contains": host_name,
                            "max_targets": max_targets,
                            **search_filters,
                            **{f"target_host_{k}": v for k, v in target_host_filters.items()},
                            **extra,
                        },
                        source_text=branch,
                        once_per_turn=once,
                        limit_per_turn=limit,
                    )
                )

        m_owner_card_placed_under_named_host_rest = _OWNER_CARD_PLACED_UNDER_NAMED_HOST_REST_RE.search(branch)
        if m_owner_card_placed_under_named_host_rest:
            host_name = str(m_owner_card_placed_under_named_host_rest.group(1) or "").strip().upper()
            max_targets = int(m_owner_card_placed_under_named_host_rest.group(2))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_card_placed_under_owner_card",
                    handler_id="auto_switch_up_to_n_opponent_board_rest",
                    handler_params={
                        "required_host_zone": "battle",
                        "host_name_contains": host_name,
                        "max_targets": max_targets,
                        "target_card_types": "BATTLE",
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_placed_under_owner_card_reveal = _PLACED_UNDER_OWNER_CARD_SWITCH_OWNER_BOARD_REVEALED_RE.search(branch)
        if m_placed_under_owner_card_reveal:
            raw_host_descriptor = str(m_placed_under_owner_card_reveal.group(1) or "").strip()
            host_descriptor = raw_host_descriptor.lower()
            max_targets = int(m_placed_under_owner_card_reveal.group(2))
            host_filters = {
                k: v
                for k, v in _descriptor_filters(host_descriptor, branch).items()
                if k in {"allowed_colors", "required_traits", "required_characters", "required_name_contains"}
            }
            if "<" in raw_host_descriptor and "required_characters" not in host_filters and "required_traits" in host_filters:
                host_filters["required_characters"] = str(host_filters.pop("required_traits"))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_placed_under_owner_card",
                    handler_id="auto_switch_up_to_n_owner_board_to_revealed_on_placed_under",
                    handler_params={
                        "required_host_zone": "battle",
                        "host_required_card_type": "BATTLE",
                        "host_required_skill_text_contains": "[union",
                        "max_targets": max_targets,
                        **{f"host_{k}": v for k, v in host_filters.items()},
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_self_placed_under_by_union_rest = _SELF_PLACED_UNDER_BY_UNION_REST_RE.search(branch)
        if m_self_placed_under_by_union_rest:
            max_targets = int(m_self_placed_under_by_union_rest.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_placed_under_by_union",
                    handler_id="auto_switch_up_to_n_opponent_board_rest",
                    handler_params={
                        "max_targets": max_targets,
                        "target_card_types": "BATTLE",
                        "ignores_barrier": "ignoring [barrier]" in branch.lower(),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_self_placed_under_by_union_opponent_next_main_restand = _SELF_PLACED_UNDER_BY_UNION_OPPONENT_NEXT_MAIN_ENERGY_RESTAND_RE.search(branch)
        if m_self_placed_under_by_union_opponent_next_main_restand:
            max_targets = int(m_self_placed_under_by_union_opponent_next_main_restand.group(1))
            descriptor = str(m_self_placed_under_by_union_opponent_next_main_restand.group(2) or "").strip().lower()
            colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black|white)\b", descriptor)))
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                **extra,
            }
            if colors:
                params["allowed_colors"] = ",".join(colors)
            if "multicolor" in descriptor or "multi-color" in descriptor:
                params["requires_multicolor"] = True
            rules.append(
                EffectRule(
                    trigger="self_placed_under_by_union",
                    handler_id="auto_schedule_switch_up_to_n_owner_energy_active_on_opponent_next_main_phase_on_placed_under_by_union",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_other_battle_dor_draw = _OWNER_OTHER_BATTLE_PLAYED_BY_DARK_OVER_REALM_DRAW_RE.search(branch)
        if m_owner_other_battle_dor_draw:
            amount = int(m_owner_other_battle_dor_draw.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_other_battle_played_by_dark_over_realm",
                    handler_id="auto_draw_n",
                    handler_params={"amount": amount, **extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_other_battle_played_place_from_combo_under_leader = _OWNER_OTHER_BATTLE_PLAYED_PLACE_FROM_OWNER_COMBO_UNDER_OWNER_LEADER_RE.search(branch)
        if m_owner_other_battle_played_place_from_combo_under_leader:
            event_descriptor = str(m_owner_other_battle_played_place_from_combo_under_leader.group(1) or "").strip().lower()
            max_targets = int(m_owner_other_battle_played_place_from_combo_under_leader.group(2))
            combo_descriptor = str(m_owner_other_battle_played_place_from_combo_under_leader.group(3) or "").strip().lower()
            event_filters = _descriptor_filters(event_descriptor, branch)
            if "<" in event_descriptor and "required_characters" not in event_filters and "required_traits" in event_filters:
                event_filters["required_characters"] = str(event_filters.pop("required_traits"))
            combo_filters = _descriptor_filters(combo_descriptor, branch)
            if "<" in combo_descriptor and "required_characters" not in combo_filters and "required_traits" in combo_filters:
                combo_filters["required_characters"] = str(combo_filters.pop("required_traits"))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_other_battle_played",
                    handler_id="auto_place_up_to_n_from_owner_combo_under_owner_leader_on_owner_matching_battle_played",
                    handler_params={
                        "max_targets": max_targets,
                        "event_allowed_colors": str(event_filters.get("allowed_colors", "")),
                        "event_required_traits": str(event_filters.get("required_traits", "")),
                        "event_required_characters": str(event_filters.get("required_characters", "")),
                        "event_required_name_contains": str(event_filters.get("required_name_contains", "")),
                        "event_required_card_type": str(event_filters.get("required_card_type", "")),
                        "event_requires_all_characters": bool(event_filters.get("requires_all_characters", False)),
                        "allowed_colors": str(combo_filters.get("allowed_colors", "")),
                        "required_traits": str(combo_filters.get("required_traits", "")),
                        "required_characters": str(combo_filters.get("required_characters", "")),
                        "required_name_contains": str(combo_filters.get("required_name_contains", "")),
                        "required_card_type": str(combo_filters.get("required_card_type", "")),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_battle_left_place_from_drop_under_leader = _OWNER_BATTLE_LEFT_PLACE_FROM_OWNER_DROP_UNDER_OWNER_LEADER_RE.search(branch)
        if m_owner_battle_left_place_from_drop_under_leader:
            event_descriptor = str(m_owner_battle_left_place_from_drop_under_leader.group(1) or "").strip().lower()
            max_targets = int(m_owner_battle_left_place_from_drop_under_leader.group(2))
            drop_descriptor = str(m_owner_battle_left_place_from_drop_under_leader.group(3) or "").strip().lower()
            event_filters = _descriptor_filters(event_descriptor, branch)
            if "<" in event_descriptor and "required_characters" not in event_filters and "required_traits" in event_filters:
                event_filters["required_characters"] = str(event_filters.pop("required_traits"))
            drop_filters = _descriptor_filters(drop_descriptor, branch)
            if "<" in drop_descriptor and "required_characters" not in drop_filters and "required_traits" in drop_filters:
                drop_filters["required_characters"] = str(drop_filters.pop("required_traits"))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_card_left_battle_area",
                    handler_id="auto_place_up_to_n_from_owner_drop_under_owner_leader_on_owner_matching_battle_left",
                    handler_params={
                        "max_targets": max_targets,
                        "event_allowed_colors": str(event_filters.get("allowed_colors", "")),
                        "event_required_traits": str(event_filters.get("required_traits", "")),
                        "event_required_characters": str(event_filters.get("required_characters", "")),
                        "event_required_name_contains": str(event_filters.get("required_name_contains", "")),
                        "event_required_card_type": str(event_filters.get("required_card_type", "")),
                        "event_requires_all_characters": bool(event_filters.get("requires_all_characters", False)),
                        "allowed_colors": str(drop_filters.get("allowed_colors", "")),
                        "required_traits": str(drop_filters.get("required_traits", "")),
                        "required_characters": str(drop_filters.get("required_characters", "")),
                        "required_name_contains": str(drop_filters.get("required_name_contains", "")),
                        "required_card_type": str(drop_filters.get("required_card_type", "")),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_battle_left_play_token = _OWNER_BATTLE_LEFT_PLAY_TOKEN_RE.search(branch)
        if m_owner_battle_left_play_token:
            event_descriptor = str(m_owner_battle_left_play_token.group(1) or "").strip().lower()
            token_name = _normalize_token_name(m_owner_battle_left_play_token.group(3))
            power, combo_cost, combo_power = _extract_token_stats(branch)
            event_filters = _descriptor_filters(event_descriptor, branch)
            if "<" in event_descriptor and "required_characters" not in event_filters and "required_traits" in event_filters:
                event_filters["required_characters"] = str(event_filters.pop("required_traits"))
            if "token" in event_descriptor and not str(event_filters.get("required_name_contains", "")).strip():
                event_filters["required_name_contains"] = _normalize_token_name(event_descriptor).upper()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_card_left_battle_area",
                    handler_id="auto_play_token_in_battle_on_owner_matching_battle_left",
                    handler_params={
                        "amount": int(m_owner_battle_left_play_token.group(2)),
                        "token_name": token_name,
                        "power": power,
                        "combo_cost": combo_cost,
                        "combo_power": combo_power,
                        "resting": "in rest mode" in branch.lower(),
                        "event_allowed_colors": str(event_filters.get("allowed_colors", "")),
                        "event_required_traits": str(event_filters.get("required_traits", "")),
                        "event_required_characters": str(event_filters.get("required_characters", "")),
                        "event_required_name_contains": str(event_filters.get("required_name_contains", "")),
                        "event_required_card_type": str(event_filters.get("required_card_type", "")),
                        "event_requires_all_characters": bool(event_filters.get("requires_all_characters", False)),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_battle_left_opponent_discards = _OWNER_BATTLE_LEFT_BY_OPPONENT_SKILL_OPPONENT_DISCARDS_RE.search(branch)
        if m_owner_battle_left_opponent_discards:
            amount = int(m_owner_battle_left_opponent_discards.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_card_left_battle_area",
                    handler_id="auto_opponent_discards_n_from_hand_on_owner_matching_battle_left",
                    handler_params={
                        "amount": amount,
                        "event_removed_by_opponent_skill": True,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _OWNER_OPP_BATTLE_ATTACKS_PLAY_SELF_FROM_DROP_OR_WARP_NEGATE_RE.search(branch):
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "played_from": "drop_or_warp",
                "resting": True,
                "negate_attack": True,
                **extra,
            }
            if "add 1 card from your life to your hand" in branch:
                params["life_to_hand"] = 1
            if "place 1 card from your hand at the bottom of your deck" in branch:
                params["bottom_deck_from_hand"] = 1
            rules.append(
                EffectRule(
                    trigger="owner_opponent_battle_attacks",
                    handler_id="auto_pay_life_bottom_deck_play_self_from_drop_or_warp_negate_attack",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _OWNER_OPPONENT_ATTACKS_REST_SELF_REDIRECT_TO_MATCHING_OWNER_BATTLE_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_opponent_battle_attacks",
                    handler_id="auto_rest_self_redirect_attack_to_matching_owner_battle_on_opponent_attack",
                    handler_params={
                        "target_allowed_colors": "green",
                        "target_requires_shared_leader_traits": True,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_hand_to_dest = _HAND_TO_DROP_OR_WARP_PLACE_UP_TO_N_FROM_DECK_TO_SAME_DEST_RE.search(branch)
        if m_hand_to_dest:
            extra = _extract_common_conditions(branch)
            descriptor = m_hand_to_dest.group(2)
            params: dict[str, int | str | bool] = {
                "max_targets": int(m_hand_to_dest.group(1)),
                "max_power": int(m_hand_to_dest.group(3)),
                "required_card_type": "BATTLE",
                "mirror_destination_zone": True,
                **extra,
                **_descriptor_filters(descriptor, branch),
            }
            rules.append(
                EffectRule(
                    trigger="self_in_hand_sent_to_drop_or_warp",
                    handler_id="auto_place_up_to_n_from_owner_deck_to_destination_zone",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _HAND_TO_DROP_BY_CAUSE_PLAY_SELF_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_in_hand_sent_to_drop_or_warp",
                    handler_id="auto_play_self_from_drop_on_hand_drop",
                    handler_params={
                        "required_destination_zone": "drop",
                        "required_drop_causes": "opponent_skill,revive",
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_hand_discarded_by_union_fusion_add_life = _HAND_DISCARDED_BY_UNION_FUSION_ADD_UP_TO_N_FROM_LIFE_TO_HAND_RE.search(branch)
        if m_hand_discarded_by_union_fusion_add_life:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_in_hand_sent_to_drop_or_warp",
                    handler_id="auto_add_up_to_n_from_owner_life_to_hand_on_hand_drop",
                    handler_params={
                        "max_targets": int(m_hand_discarded_by_union_fusion_add_life.group(1)),
                        "required_destination_zone": "drop",
                        "required_drop_causes": "union_fusion",
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_battle_end_play_self_then_negate_unison = _COMBO_FROM_HAND_BATTLE_END_PLAY_SELF_THEN_NEGATE_UP_TO_N_OPPONENT_UNISON_FOR_TURN_RE.search(branch)
        m_combo_battle_end_play_self_then_return_battle = _COMBO_FROM_HAND_BATTLE_END_PLAY_SELF_THEN_RETURN_UP_TO_N_OPPONENT_BATTLE_TO_HAND_RE.search(branch)
        if m_combo_battle_end_play_self_then_negate_unison:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_comboed_battle_end",
                    handler_id="auto_play_self_from_combo_on_battle_end_then_negate_up_to_n_opponent_unisons_for_turn",
                    handler_params={
                        "resting": True,
                        "requires_comboed_from": "hand",
                        "max_targets": int(m_combo_battle_end_play_self_then_negate_unison.group(1)),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
        elif m_combo_battle_end_play_self_then_return_battle:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_comboed_battle_end",
                    handler_id="auto_play_self_from_combo_on_battle_end_then_return_up_to_n_opponent_battle_to_hand",
                    handler_params={
                        "resting": True,
                        "requires_comboed_from": "hand",
                        "max_targets": int(m_combo_battle_end_play_self_then_return_battle.group(1)),
                        "max_cost": int(m_combo_battle_end_play_self_then_return_battle.group(2)),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
        elif _COMBO_FROM_HAND_BATTLE_END_PLAY_SELF_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rest = "rest mode" in branch.lower()
            rules.append(
                EffectRule(
                    trigger="self_comboed_battle_end",
                    handler_id="auto_play_self_from_combo_on_battle_end",
                    handler_params={
                        "resting": rest,
                        "requires_comboed_from": "hand",
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_with_owner_battle_play_end = _COMBO_FROM_HAND_WITH_OWNER_BATTLE_PLAY_AT_BATTLE_END_RE.search(branch)
        if m_combo_with_owner_battle_play_end:
            extra = _extract_common_conditions(branch)
            descriptor = str(m_combo_with_owner_battle_play_end.group(1) or "").strip().lower()
            filters = {
                k: v
                for k, v in _descriptor_filters(descriptor, branch).items()
                if k in {"allowed_colors", "required_traits", "required_characters", "required_name_contains"}
            }
            if "<" in m_combo_with_owner_battle_play_end.group(1) and "required_characters" not in filters and "required_traits" in filters:
                filters["required_characters"] = str(filters.pop("required_traits"))
            rules.append(
                EffectRule(
                    trigger="self_comboed_battle_end",
                    handler_id="auto_play_self_from_combo_on_battle_end",
                    handler_params={
                        "resting": False,
                        "requires_comboed_from": "hand",
                        **{f"required_owner_battle_{k}": v for k, v in filters.items()},
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _COMBO_FROM_HAND_BATTLE_END_ADD_SELF_TO_Z_ENERGY_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_comboed_battle_end",
                    handler_id="auto_add_self_to_owner_z_energy_on_battle_end",
                    handler_params={
                        "requires_comboed_from": "hand",
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _COMBO_FROM_BATTLE_BATTLE_END_ADD_SELF_TO_Z_ENERGY_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_comboed_battle_end",
                    handler_id="auto_add_self_to_owner_z_energy_on_battle_end",
                    handler_params={
                        "requires_comboed_from": "battle",
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _COMBO_BATTLE_END_PLAY_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rest = "rest mode" in branch
            if "from your hand" in branch.lower():
                extra["requires_comboed_from"] = "hand"
            elif "from your battle area" in branch.lower():
                extra["requires_comboed_from"] = "battle"
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

        m_activate_main_optional_hand_warp_draw = _ACTIVATE_MAIN_OPTIONAL_SEND_HAND_TO_WARP_DRAW_RE.search(branch)
        if m_activate_main_optional_hand_warp_draw:
            amount = int(m_activate_main_optional_hand_warp_draw.group(2))
            extra = _extract_common_conditions(branch)
            marker_delta = _extract_unison_marker_delta(branch)
            params: dict[str, int | str | bool] = {
                "hand_to_warp": int(m_activate_main_optional_hand_warp_draw.group(1)),
                "amount": amount,
                **extra,
            }
            if marker_delta is not None:
                params["marker_delta"] = marker_delta
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_optional_send_owner_hand_to_warp_draw_n",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_activate_main_opponent_discards = _ACTIVATE_MAIN_OPPONENT_DISCARDS_N_FROM_HAND_RE.search(branch)
        if m_activate_main_opponent_discards:
            amount = int(m_activate_main_opponent_discards.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_opponent_discards_n_from_hand",
                    handler_params={"amount": amount, **extra},
                    once_per_turn=once,
                )
            )

        m_activate_main_under_named_host_to_drop_then_opponent_discards = _ACTIVATE_MAIN_PLACE_UP_TO_N_FROM_UNDER_NAMED_OWNER_BATTLE_INTO_DROP_THEN_OPPONENT_DISCARDS_SAME_COUNT_RE.search(branch)
        if m_activate_main_under_named_host_to_drop_then_opponent_discards:
            max_targets = int(m_activate_main_under_named_host_to_drop_then_opponent_discards.group(1))
            host_name = str(m_activate_main_under_named_host_to_drop_then_opponent_discards.group(2) or "").strip().upper()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_up_to_n_from_under_named_owner_battle_into_drop_then_opponent_discards_same_count",
                    handler_params={
                        "max_targets": max_targets,
                        "required_host_name_contains": host_name,
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_main_reveal_opponent_hand_play = _ACTIVATE_MAIN_REVEAL_OPPONENT_HAND_PLAY_UP_TO_N_BATTLE_TO_OPPONENT_BATTLE_RE.search(branch)
        if m_activate_main_reveal_opponent_hand_play:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_up_to_n_from_opponent_hand_to_opponent_battle",
                    handler_params={
                        "max_targets": int(m_activate_main_reveal_opponent_hand_play.group(1)),
                        "max_cost": int(m_activate_main_reveal_opponent_hand_play.group(2)),
                        "required_card_type": "BATTLE",
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_main_look_opponent_hand_play = _ACTIVATE_MAIN_LOOK_OPPONENT_HAND_PLAY_UP_TO_N_BATTLE_TO_OPPONENT_BATTLE_RE.search(branch)
        if m_activate_main_look_opponent_hand_play:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_up_to_n_from_opponent_hand_to_opponent_battle",
                    handler_params={
                        "max_targets": int(m_activate_main_look_opponent_hand_play.group(1)),
                        "required_card_type": "BATTLE",
                        "resting": "in rest mode" in branch.lower(),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_main_win_game = _ACTIVATE_MAIN_WIN_GAME_IF_OPPONENT_OWNED_UNDER_SELF_RE.search(branch)
        if m_activate_main_win_game:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_win_game_if_opponent_owned_cards_under_self_at_least_n",
                    handler_params={
                        "required_source_stacked_opponent_owned_at_least": int(m_activate_main_win_game.group(1)),
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_great_priest_damage = _ACTIVATE_MAIN_DEAL_DAMAGE_PER_GOD_BATTLE_COLORS_AND_OPTIONAL_WIN_RE.search(branch)
        if m_activate_main_great_priest_damage:
            leader_character = str(m_activate_main_great_priest_damage.group(1) or "").strip()
            damage_per = int(m_activate_main_great_priest_damage.group(2))
            colors_per = int(m_activate_main_great_priest_damage.group(3))
            battle_trait = str(m_activate_main_great_priest_damage.group(4) or "").strip().title()
            damage_cap = int(m_activate_main_great_priest_damage.group(5))
            win_count = int(m_activate_main_great_priest_damage.group(6))
            win_trait = str(m_activate_main_great_priest_damage.group(7) or "").strip().title()
            extra = {
                key: value
                for key, value in _extract_common_conditions(branch).items()
                if key not in {"requires_leader", "required_leader_traits"}
            }
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_deal_damage_to_opponent_per_owner_matching_battle_colors_and_optionally_win",
                    handler_params={
                        "leader_required_characters": leader_character,
                        "damage_per": damage_per,
                        "colors_per_damage": colors_per,
                        "required_owner_battle_traits": battle_trait,
                        "max_damage": damage_cap,
                        "win_if_owner_in_play_matching_count_at_least": win_count,
                        "win_required_traits": win_trait,
                        "win_requires_multicolor": True,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_draw_discard_place_drop_under_leader = _ACTIVATE_MAIN_DRAW_DISCARD_AND_PLACE_FROM_DROP_UNDER_LEADER_THEN_SWITCH_SELF_ACTIVE_RE.search(branch)
        if m_activate_main_draw_discard_place_drop_under_leader:
            amount = int(m_activate_main_draw_discard_place_drop_under_leader.group(1))
            discard_count = int(m_activate_main_draw_discard_place_drop_under_leader.group(2))
            leader_descriptor = str(m_activate_main_draw_discard_place_drop_under_leader.group(3) or "").strip().lower()
            descriptor = str(m_activate_main_draw_discard_place_drop_under_leader.group(5) or "").strip()
            extra = {
                key: value
                for key, value in _extract_common_conditions(branch).items()
                if key not in {"requires_leader", "required_leader_traits"}
            }
            marker_delta = _extract_unison_marker_delta(branch)
            leader_filters = _descriptor_filters(leader_descriptor, branch)
            params: dict[str, int | str | bool] = {
                "amount": amount,
                "discard_count": discard_count,
                "max_targets": int(m_activate_main_draw_discard_place_drop_under_leader.group(4) or 1),
                **_descriptor_filters(descriptor.lower(), branch),
                **extra,
            }
            for key, value in leader_filters.items():
                if key in {"allowed_colors", "required_traits", "required_characters", "required_name_contains"}:
                    params[f"bonus_leader_{key}"] = value
            if "mono-blue" in branch.lower() or "mono blue" in branch.lower():
                params["bonus_leader_requires_mono"] = True
                params["bonus_leader_allowed_colors"] = "blue"
            if marker_delta is not None:
                params["marker_delta"] = marker_delta
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_draw_n_discard_n_and_place_up_to_n_from_owner_drop_under_owner_leader_then_switch_self_active_on_turn_end",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_draw_place_deck_or_drop_under_leader = _ACTIVATE_MAIN_DRAW_AND_PLACE_FROM_DECK_OR_DROP_UNDER_LEADER_RE.search(branch)
        if m_activate_main_draw_place_deck_or_drop_under_leader:
            amount = int(m_activate_main_draw_place_deck_or_drop_under_leader.group(1))
            max_targets = int(m_activate_main_draw_place_deck_or_drop_under_leader.group(2))
            descriptor = str(m_activate_main_draw_place_deck_or_drop_under_leader.group(3) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_draw_n_and_place_up_to_n_from_owner_deck_or_drop_under_owner_leader",
                    handler_params={
                        "amount": amount,
                        "max_targets": max_targets,
                        "source_pool": "deck_or_drop",
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_play_z_deck_or_z_energy = _ACTIVATE_MAIN_PLAY_UP_TO_N_FROM_OWNER_Z_DECK_OR_Z_ENERGY_RE.search(branch)
        if m_activate_main_play_z_deck_or_z_energy:
            max_targets = int(m_activate_main_play_z_deck_or_z_energy.group(1))
            descriptor = str(m_activate_main_play_z_deck_or_z_energy.group(2) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "source_pool": "z_deck_or_z_energy",
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if "with its skills negated for the game" in branch or "with their skills negated for the game" in branch:
                params["negate_skills"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_up_to_n_from_owner_z_deck_or_z_energy",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_activate_main_battle_named_field_extra_from_z_deck = _ACTIVATE_MAIN_BATTLE_PLACE_UP_TO_N_NAMED_FIELD_EXTRA_FROM_OWNER_Z_DECK_RE.search(branch)
        if m_activate_main_battle_named_field_extra_from_z_deck:
            trigger_mode = str(m_activate_main_battle_named_field_extra_from_z_deck.group(1) or "").strip().lower()
            first_name = str(m_activate_main_battle_named_field_extra_from_z_deck.group(3) or "").strip().upper()
            second_name = str(m_activate_main_battle_named_field_extra_from_z_deck.group(4) or "").strip().upper()
            extra = _extract_common_conditions(branch)
            triggers = (
                ("self_activate_main", "self_activate_battle")
                if trigger_mode == "main/battle"
                else ("self_activate_main",)
                if trigger_mode == "main"
                else ("self_activate_battle",)
            )
            for trigger in triggers:
                rules.append(
                    EffectRule(
                        trigger=trigger,
                        handler_id="activate_activate_up_to_n_named_field_extra_from_owner_z_deck",
                        handler_params={
                            "max_targets": int(m_activate_main_battle_named_field_extra_from_z_deck.group(2)),
                            "required_name_contains_any": f"{first_name}|{second_name}",
                            "required_card_type": "EXTRA",
                            "requires_field_keyword": True,
                            **extra,
                        },
                        once_per_turn=once,
                        limit_per_turn=limit,
                    )
                )

        m_activate_main_bottom_deck_opponent_battle = _ACTIVATE_MAIN_BOTTOM_DECK_UP_TO_N_OPPONENT_BATTLE_RE.search(branch)
        if m_activate_main_bottom_deck_opponent_battle:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": int(m_activate_main_bottom_deck_opponent_battle.group(1)),
                **extra,
            }
            if m_activate_main_bottom_deck_opponent_battle.group(2):
                params["max_cost"] = int(m_activate_main_bottom_deck_opponent_battle.group(2))
            if "ignoring [barrier]" in branch.lower():
                params["ignores_barrier"] = True
            marker_delta = _extract_unison_marker_delta(branch)
            if marker_delta is not None:
                params["marker_delta"] = marker_delta
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_bottom_deck_up_to_n_opponent_battle",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_self_gain_power_then_return_battle = _ACTIVATE_MAIN_SELF_GAIN_POWER_THEN_RETURN_UP_TO_N_OPPONENT_BATTLE_TO_HAND_RE.search(branch)
        if m_activate_main_self_gain_power_then_return_battle:
            extra = _extract_common_conditions(branch)
            marker_delta = _extract_unison_marker_delta(branch)
            params: dict[str, int | str | bool] = {
                "power_delta": int(m_activate_main_self_gain_power_then_return_battle.group(1)),
                "post_return_max_targets": int(m_activate_main_self_gain_power_then_return_battle.group(2)),
                "post_return_max_cost": int(m_activate_main_self_gain_power_then_return_battle.group(3)),
                "post_return_target_policy": "first",
                **extra,
            }
            if marker_delta is not None:
                params["marker_delta"] = marker_delta
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_gain_power_and_keyword_for_turn",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_opponent_chooses_hand_to_warp = _ACTIVATE_MAIN_OPPONENT_CHOOSES_N_HAND_TO_WARP_RE.search(branch)
        if m_activate_main_opponent_chooses_hand_to_warp:
            extra = _extract_common_conditions(branch)
            marker_delta = _extract_unison_marker_delta(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": int(m_activate_main_opponent_chooses_hand_to_warp.group(1)),
                **extra,
            }
            if marker_delta is not None:
                params["marker_delta"] = marker_delta
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_send_up_to_n_opponent_hand_to_warp",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_rest_active_else_gain_control = _ACTIVATE_MAIN_REST_ACTIVE_OPP_CARD_ELSE_GAIN_CONTROL_RE.search(branch)
        if m_activate_main_rest_active_else_gain_control:
            leader_descriptor = str(m_activate_main_rest_active_else_gain_control.group(1) or "").strip().lower()
            max_targets = int(m_activate_main_rest_active_else_gain_control.group(2))
            extra = _extract_common_conditions(branch)
            marker_delta = _extract_unison_marker_delta(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "target_policy": "first",
                **extra,
            }
            params.pop("requires_leader", None)
            params.pop("rest_mode_only", None)
            if "yellow" in leader_descriptor:
                params["leader_or_allowed_colors"] = "yellow"
            if "turles crusher corps" in leader_descriptor:
                params["leader_or_required_traits"] = "Turles Crusher Corps"
            if marker_delta is not None:
                params["marker_delta"] = marker_delta
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_rest_opponent_active_else_gain_control_opponent_battle",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_ko_at_least_current_energy = _ACTIVATE_MAIN_KO_UP_TO_N_OPPONENT_BATTLE_AT_LEAST_CURRENT_ENERGY_RE.search(branch)
        if m_activate_main_ko_at_least_current_energy:
            extra = _extract_common_conditions(branch)
            marker_delta = _extract_unison_marker_delta(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": int(m_activate_main_ko_at_least_current_energy.group(1)),
                "target_policy": "first",
                "requires_cost_at_least_opponent_current_energy": True,
                **extra,
            }
            if marker_delta is not None:
                params["marker_delta"] = marker_delta
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_ko_up_to_n_opponent_battle",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_place_self_under_owner_leader_if_do_play_from_deck = _ACTIVATE_MAIN_PLACE_SELF_UNDER_OWNER_LEADER_IF_DO_PLAY_UP_TO_N_FROM_DECK_RE.search(branch)
        if m_activate_main_place_self_under_owner_leader_if_do_play_from_deck:
            max_targets = int(m_activate_main_place_self_under_owner_leader_if_do_play_from_deck.group(1))
            descriptor = str(m_activate_main_place_self_under_owner_leader_if_do_play_from_deck.group(2) or "").strip().lower()
            max_power = int(m_activate_main_place_self_under_owner_leader_if_do_play_from_deck.group(3))
            extra = _extract_common_conditions(branch)
            marker_delta = _extract_unison_marker_delta(branch)
            place_params: dict[str, int | str | bool] = {**extra}
            if marker_delta is not None:
                place_params["marker_delta"] = marker_delta
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_self_under_owner_leader",
                    handler_params=place_params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            target_filters = _descriptor_filters(descriptor, branch)
            if "<" in descriptor and "required_characters" not in target_filters and "required_traits" in target_filters:
                target_filters["required_characters"] = str(target_filters.pop("required_traits"))
            followup_params: dict[str, int | str | bool] = {
                "requires_placed_from_zones": "unison",
                "required_host_zone": "leader",
                "max_targets": max_targets,
                "max_power": max_power,
                **extra,
            }
            if "allowed_colors" in target_filters:
                followup_params["allowed_colors"] = target_filters["allowed_colors"]
            if "required_traits" in target_filters:
                followup_params["required_traits"] = target_filters["required_traits"]
            if "required_characters" in target_filters:
                followup_params["required_name_contains"] = str(target_filters["required_characters"]).upper()
            if "required_name_contains" in target_filters:
                followup_params["required_name_contains"] = target_filters["required_name_contains"]
            rules.append(
                EffectRule(
                    trigger="self_placed_under_owner_card",
                    handler_id="auto_play_up_to_n_from_owner_deck_on_placed_under",
                    handler_params=followup_params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_play_from_owner_hand_original_cost = _ACTIVATE_MAIN_PLAY_UP_TO_N_FROM_OWNER_HAND_WITH_ORIGINAL_COST_RE.search(branch)
        if m_activate_main_play_from_owner_hand_original_cost:
            max_targets = int(m_activate_main_play_from_owner_hand_original_cost.group(1))
            descriptor = str(m_activate_main_play_from_owner_hand_original_cost.group(2) or "").strip().lower()
            exact_cost = int(m_activate_main_play_from_owner_hand_original_cost.group(3))
            extra = _extract_common_conditions(branch)
            marker_delta = _extract_unison_marker_delta(branch)
            target_filters = _descriptor_filters(descriptor, branch)
            play_params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "allowed_costs": str(exact_cost),
                "max_cost": exact_cost,
                **target_filters,
                **extra,
            }
            if "battle card" in descriptor or " card " in f" {descriptor} ":
                play_params["required_card_type"] = "BATTLE"
            if "multicolor" in descriptor or "multi-color" in descriptor:
                play_params["requires_multicolor"] = True
            m_named_character = re.search(r"<([^>]+)>", descriptor)
            if m_named_character is not None:
                play_params.pop("required_traits", None)
                play_params.pop("required_characters", None)
                play_params["required_name_contains"] = str(m_named_character.group(1) or "").strip().upper()
            if marker_delta is not None:
                play_params["marker_delta"] = marker_delta
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_up_to_n_from_owner_hand",
                    handler_params=play_params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_draw_then_owner_cards_power = _ACTIVATE_MAIN_DRAW_THEN_CHOOSE_OWNER_CARDS_GAIN_POWER_FOR_TURN_RE.search(branch)
        if m_activate_main_draw_then_owner_cards_power:
            amount = int(m_activate_main_draw_then_owner_cards_power.group(1))
            max_targets = int(m_activate_main_draw_then_owner_cards_power.group(2))
            raw_descriptor = str(m_activate_main_draw_then_owner_cards_power.group(3) or "").strip()
            descriptor = raw_descriptor.lower()
            compact_descriptor = re.sub(r"\s+", " ", descriptor).strip()
            power_delta = int(m_activate_main_draw_then_owner_cards_power.group(4))
            extra = _extract_common_conditions(branch)
            filters = {} if compact_descriptor in {"battle", "battle card", "battle cards"} else _descriptor_filters(descriptor, branch)
            if "<" in raw_descriptor and "required_characters" not in filters and "required_traits" in filters:
                filters["required_characters"] = str(filters.pop("required_traits"))
            params = {
                "amount": amount,
                "target_policy": "first",
                "target_scope": "owner_battle" if compact_descriptor in {"battle", "battle card", "battle cards"} else "owner_cards",
                "max_targets": max_targets,
                "power_delta": power_delta,
                **filters,
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="self_activate_extra_from_hand" if is_extra else "self_activate_main",
                    handler_id="activate_buff_owner_battle_cards",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        # [Activate: Main] ... : Draw N card(s).
        m_activate_main_draw = _ACTIVATE_MAIN_IF_DO_DRAW_RE.search(branch) or _ACTIVATE_MAIN_DRAW_RE.search(branch)
        if (
            m_activate_main_draw
            and m_activate_main_optional_hand_warp_draw is None
            and _ACTIVATE_MAIN_DRAW_LIFE_BOUNCE_AND_OPTIONAL_MAIN_PHASE_ENERGY_SWITCH_RE.search(branch) is None
            and m_activate_main_draw_then_owner_cards_power is None
            and _ACTIVATE_MAIN_DRAW_AND_SWITCH_UP_TO_N_OPPONENT_BATTLE_OR_UNISON_ACTIVE_RE.search(branch) is None
        ):
            amount = int(m_activate_main_draw.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_extra_from_hand" if is_extra else "self_activate_main",
                    handler_id="auto_draw_n",
                    handler_params={"amount": amount, **extra},
                    once_per_turn=once,
                )
            )

        # [Activate: Battle] ... : Draw N card(s).
        m_activate_battle_draw = _ACTIVATE_BATTLE_DRAW_RE.search(branch)
        if m_activate_battle_draw:
            amount = int(m_activate_battle_draw.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="auto_draw_n",
                    handler_params={"amount": amount, **extra},
                    once_per_turn=once,
                )
            )

        m_activate_battle_buff = _ACTIVATE_BATTLE_SELF_GAIN_POWER_AND_KEYWORD_FOR_BATTLE_RE.search(branch)
        if m_activate_battle_buff:
            power_delta = int(m_activate_battle_buff.group(1))
            grant_keyword = " ".join(part.capitalize() for part in m_activate_battle_buff.group(2).replace("-", " ").split())
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_gain_power_and_keyword_for_battle",
                    handler_params={"power_delta": power_delta, "grant_keyword": grant_keyword, **extra},
                    once_per_turn=once,
                )
            )

        m_activate_battle_self_power = _ACTIVATE_BATTLE_SELF_GAIN_POWER_FOR_BATTLE_RE.search(branch)
        if m_activate_battle_self_power and "for each card in your warp" not in branch.lower():
            power_delta = int(m_activate_battle_self_power.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_gain_power_and_keyword_for_battle",
                    handler_params={"power_delta": power_delta, **extra},
                    once_per_turn=once,
                )
            )

        m_activate_battle_leader_buff = _ACTIVATE_BATTLE_OWNER_LEADER_GAIN_POWER_AND_KEYWORD_FOR_BATTLE_RE.search(branch)
        if m_activate_battle_leader_buff:
            power_delta = int(m_activate_battle_leader_buff.group(1))
            grant_keyword = " ".join(part.capitalize() for part in m_activate_battle_leader_buff.group(2).replace("-", " ").split())
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_extra_from_hand" if is_extra else "self_activate_battle",
                    handler_id="activate_gain_power_and_keyword_for_battle",
                    handler_params={
                        "power_delta": power_delta,
                        "grant_keyword": grant_keyword,
                        "target_scope": "owner_leader",
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_battle_leader_power = _ACTIVATE_BATTLE_CHOOSE_OWNER_LEADER_GAIN_POWER_FOR_BATTLE_RE.search(branch)
        if m_activate_battle_leader_power:
            power_delta = int(m_activate_battle_leader_power.group(1))
            extra = _extract_common_conditions(branch)
            m_under_z_leader = re.search(r"from under your <([^>]+)>\s*z-leader", branch, re.IGNORECASE)
            if m_under_z_leader is not None:
                extra.setdefault("required_source_zone", "leader_under")
                extra.setdefault("under_host_required_characters", m_under_z_leader.group(1).strip())
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_gain_power_and_keyword_for_battle",
                    handler_params={
                        "power_delta": power_delta,
                        "target_scope": "owner_leader",
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_battle_leader_keyword = _ACTIVATE_BATTLE_OWNER_LEADER_GAIN_KEYWORD_FOR_BATTLE_RE.search(branch)
        if m_activate_battle_leader_keyword:
            grant_keyword = " ".join(part.capitalize() for part in m_activate_battle_leader_keyword.group(1).replace("-", " ").split())
            extra = _extract_common_conditions(branch)
            m_under_z_leader = re.search(r"from under your <([^>]+)>\s*z-leader", branch, re.IGNORECASE)
            if m_under_z_leader is not None:
                extra.setdefault("required_source_zone", "leader_under")
                extra.setdefault("under_host_required_characters", m_under_z_leader.group(1).strip())
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_gain_power_and_keyword_for_battle",
                    handler_params={
                        "grant_keyword": grant_keyword,
                        "target_scope": "owner_leader",
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_battle_owner_cards_power = _ACTIVATE_BATTLE_CHOOSE_OWNER_CARDS_GAIN_POWER_FOR_BATTLE_RE.search(branch)
        if m_activate_battle_owner_cards_power:
            max_targets = int(m_activate_battle_owner_cards_power.group(1))
            descriptor = str(m_activate_battle_owner_cards_power.group(2) or "").strip().lower()
            power_delta = int(m_activate_battle_owner_cards_power.group(3))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_gain_power_and_keyword_for_battle",
                    handler_params={
                        "power_delta": power_delta,
                        "max_targets": max_targets,
                        "target_scope": "owner_cards",
                        "target_policy": "first",
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_battle_card_power = _ACTIVATE_BATTLE_CHOOSE_CARD_GAIN_POWER_FOR_BATTLE_RE.search(branch)
        if m_activate_battle_card_power:
            max_targets = int(m_activate_battle_card_power.group(1))
            descriptor = str(m_activate_battle_card_power.group(2) or "").strip().lower()
            power_delta = int(m_activate_battle_card_power.group(3))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_gain_power_and_keyword_for_battle",
                    handler_params={
                        "power_delta": power_delta,
                        "max_targets": max_targets,
                        "target_scope": "owner_cards",
                        "target_policy": "first",
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_battle_owner_cards_keyword = _ACTIVATE_BATTLE_CHOOSE_OWNER_CARDS_GAIN_KEYWORD_FOR_BATTLE_RE.search(branch)
        if m_activate_battle_owner_cards_keyword:
            max_targets = int(m_activate_battle_owner_cards_keyword.group(1))
            descriptor = str(m_activate_battle_owner_cards_keyword.group(2) or "").strip().lower()
            grant_keyword = " ".join(part.capitalize() for part in str(m_activate_battle_owner_cards_keyword.group(3) or "").replace("-", " ").split())
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_gain_power_and_keyword_for_battle",
                    handler_params={
                        "grant_keyword": grant_keyword,
                        "max_targets": max_targets,
                        "target_scope": "owner_cards",
                        "target_policy": "first",
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_battle_power_per_warp = _ACTIVATE_BATTLE_SELF_GAIN_POWER_PER_OWNER_WARP_RE.search(branch)
        if m_activate_battle_power_per_warp:
            power_per_card = int(m_activate_battle_power_per_warp.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_gain_power_and_keyword_for_battle",
                    handler_params={"power_delta": f"expr:owner_warp_count*{power_per_card}", **extra},
                    once_per_turn=once,
                )
            )

        m_activate_battle_switch_active_power = _ACTIVATE_BATTLE_SWITCH_SELF_ACTIVE_AND_GAIN_POWER_FOR_TURN_RE.search(branch)
        if m_activate_battle_switch_active_power:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_switch_self_active_and_gain_power_for_turn",
                    handler_params={"power_delta": int(m_activate_battle_switch_active_power.group(1)), **extra},
                    once_per_turn=once,
                )
            )

        m_activate_battle_switch_owner_battle_active = _ACTIVATE_BATTLE_SWITCH_UP_TO_N_OWNER_BATTLE_ACTIVE_RE.search(branch)
        if m_activate_battle_switch_owner_battle_active:
            max_targets = int(m_activate_battle_switch_owner_battle_active.group(1))
            descriptor = m_activate_battle_switch_owner_battle_active.group(2).lower()
            max_cost = int(m_activate_battle_switch_owner_battle_active.group(3))
            max_power = int(m_activate_battle_switch_owner_battle_active.group(4))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_switch_up_to_n_owner_battle_active",
                    handler_params={
                        "max_targets": max_targets,
                        "max_cost": max_cost,
                        "max_power": max_power,
                        "target_policy": "first",
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_main_battle_switch_owner_battle_active_general = _ACTIVATE_MAIN_BATTLE_SWITCH_UP_TO_N_OWNER_BATTLE_ACTIVE_GENERAL_RE.search(branch)
        if m_activate_main_battle_switch_owner_battle_active_general:
            trigger_mode = str(m_activate_main_battle_switch_owner_battle_active_general.group(1) or "").strip().lower()
            max_targets = int(m_activate_main_battle_switch_owner_battle_active_general.group(2))
            raw_descriptor = str(m_activate_main_battle_switch_owner_battle_active_general.group(3) or "").strip()
            descriptor = raw_descriptor.lower()
            extra = _extract_common_conditions(branch)
            filters = _descriptor_filters(descriptor, branch)
            if "<" in raw_descriptor and "required_characters" not in filters and "required_traits" in filters:
                filters["required_characters"] = str(filters.pop("required_traits"))
            triggers = (
                ("self_activate_main", "self_activate_battle")
                if trigger_mode == "main/battle"
                else ("self_activate_main",)
                if trigger_mode == "main"
                else ("self_activate_battle",)
            )
            for trigger in triggers:
                rules.append(
                    EffectRule(
                        trigger=trigger,
                        handler_id="activate_switch_up_to_n_owner_battle_active",
                        handler_params={
                            "max_targets": max_targets,
                            "target_policy": "first",
                            **filters,
                            **extra,
                        },
                        once_per_turn=once,
                        limit_per_turn=limit,
                    )
                )

        m_activate_main_buff_all_owner_battle = _ACTIVATE_MAIN_CHOOSE_ALL_OWNER_BATTLE_GAIN_KEYWORD_UNTIL_OPP_TURN_END_RE.search(branch)
        if m_activate_main_buff_all_owner_battle:
            descriptor = m_activate_main_buff_all_owner_battle.group(1).strip().lower()
            grant_keyword = " ".join(
                part.capitalize() for part in m_activate_main_buff_all_owner_battle.group(2).replace("-", " ").split()
            )
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_extra_from_hand" if is_extra else "self_activate_main",
                    handler_id="activate_buff_owner_battle_cards",
                    handler_params={
                        "target_policy": "all",
                        "target_scope": "owner_battle",
                        "grant_keyword": grant_keyword,
                        "keyword_duration": "opponent_turn",
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_main_grant_next_ex_evolve = _ACTIVATE_MAIN_GRANT_NEXT_EX_EVOLVE_FROM_DROP_RE.search(branch)
        if m_activate_main_grant_next_ex_evolve:
            descriptor = m_activate_main_grant_next_ex_evolve.group(1).strip().lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_extra_from_hand" if is_extra else "self_activate_main",
                    handler_id="activate_grant_next_ex_evolve_from_owner_drop",
                    handler_params={
                        "uses_remaining": 1,
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_battle_reduce_next_extra_skill_cost = _ACTIVATE_MAIN_BATTLE_REDUCE_NEXT_EXTRA_SKILL_COST_RE.search(branch)
        if m_activate_main_battle_reduce_next_extra_skill_cost:
            descriptor = m_activate_main_battle_reduce_next_extra_skill_cost.group(1).strip().lower()
            amount = int(m_activate_main_battle_reduce_next_extra_skill_cost.group(2))
            extra = _extract_common_conditions(branch)
            params = {
                "amount": amount,
                "uses_remaining": 1,
                "required_card_type": "EXTRA",
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_reduce_next_matching_extra_skill_cost_from_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_reduce_next_matching_extra_skill_cost_from_hand",
                    handler_params=dict(params),
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_battle_reduce_next_arrival_skill_cost = _ACTIVATE_MAIN_BATTLE_REDUCE_NEXT_ARRIVAL_SKILL_COST_RE.search(branch)
        if m_activate_main_battle_reduce_next_arrival_skill_cost:
            skill_kind = str(m_activate_main_battle_reduce_next_arrival_skill_cost.group(1) or "").strip().lower()
            arrival_colors = ",".join(
                sorted(
                    {
                        part.strip().lower()
                        for part in str(m_activate_main_battle_reduce_next_arrival_skill_cost.group(2) or "").replace("/", ",").split(",")
                        if part.strip()
                    }
                )
            )
            descriptor = m_activate_main_battle_reduce_next_arrival_skill_cost.group(3).strip()
            max_cost_group = m_activate_main_battle_reduce_next_arrival_skill_cost.group(4)
            reduction_token = next(
                (
                    str(token).strip()
                    for token in m_activate_main_battle_reduce_next_arrival_skill_cost.groups()[4:]
                    if str(token or "").strip()
                ),
                "",
            )
            extra = _extract_common_conditions(branch)
            params = {
                "uses_remaining": 1,
                "required_arrival_colors": arrival_colors,
                "reduction_cost_token": reduction_token,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if max_cost_group is not None:
                params["max_energy_cost"] = int(max_cost_group)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle" if skill_kind == "battle" else "self_activate_main",
                    handler_id="activate_reduce_next_matching_arrival_skill_cost_from_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_battle_reduce_next_z_awaken_cost = _ACTIVATE_MAIN_BATTLE_REDUCE_NEXT_Z_AWAKEN_COST_RE.search(branch)
        if m_activate_main_battle_reduce_next_z_awaken_cost:
            skill_kind = str(m_activate_main_battle_reduce_next_z_awaken_cost.group(1) or "").strip().lower()
            descriptor = m_activate_main_battle_reduce_next_z_awaken_cost.group(2).strip()
            reduction_token = next(
                (
                    str(token).strip()
                    for token in m_activate_main_battle_reduce_next_z_awaken_cost.groups()[2:5]
                    if str(token or "").strip()
                ),
                "",
            )
            z_energy_reduction = m_activate_main_battle_reduce_next_z_awaken_cost.group(6)
            extra = _extract_common_conditions(branch)
            target_filters = _descriptor_filters(descriptor, branch)
            params = {
                "uses_remaining": 1,
                "reduction_cost_token": reduction_token,
                **extra,
            }
            if "allowed_colors" in target_filters:
                params["target_allowed_colors"] = target_filters["allowed_colors"]
            if "required_traits" in target_filters:
                params["target_required_traits"] = target_filters["required_traits"]
            if "required_characters" in target_filters:
                params["target_required_characters"] = target_filters["required_characters"]
            if "required_name_contains" in target_filters:
                params["target_required_name_contains"] = target_filters["required_name_contains"]
            if z_energy_reduction is not None:
                params["z_energy_reduction"] = int(z_energy_reduction)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle" if skill_kind == "battle" else "self_activate_main",
                    handler_id="activate_reduce_next_matching_z_awaken_cost_in_z_deck",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_auto_on_play_reduce_next_z_awaken_cost = _AUTO_ON_PLAY_REDUCE_NEXT_Z_AWAKEN_COST_RE.search(branch)
        if m_auto_on_play_reduce_next_z_awaken_cost:
            descriptor = m_auto_on_play_reduce_next_z_awaken_cost.group(1).strip()
            reduction_token = next(
                (
                    str(token).strip()
                    for token in m_auto_on_play_reduce_next_z_awaken_cost.groups()[1:4]
                    if str(token or "").strip()
                ),
                "",
            )
            z_energy_reduction = m_auto_on_play_reduce_next_z_awaken_cost.group(5)
            extra = _extract_common_conditions(branch)
            target_filters = _descriptor_filters(descriptor, branch)
            params = {
                "uses_remaining": 1,
                "reduction_cost_token": reduction_token,
                **extra,
            }
            if "allowed_colors" in target_filters:
                params["target_allowed_colors"] = target_filters["allowed_colors"]
            if "required_traits" in target_filters:
                params["target_required_traits"] = target_filters["required_traits"]
            if "required_characters" in target_filters:
                params["target_required_characters"] = target_filters["required_characters"]
            if "required_name_contains" in target_filters:
                params["target_required_name_contains"] = target_filters["required_name_contains"]
            if z_energy_reduction is not None:
                params["z_energy_reduction"] = int(z_energy_reduction)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_reduce_next_matching_z_awaken_cost_in_z_deck_on_play",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_auto_on_play_grant_next_matching_union_play_keyword = _AUTO_ON_PLAY_GRANT_NEXT_MATCHING_UNION_PLAY_KEYWORD_RE.search(branch)
        if m_auto_on_play_grant_next_matching_union_play_keyword:
            descriptor = m_auto_on_play_grant_next_matching_union_play_keyword.group(1).strip()
            grant_keyword = " ".join(
                part.capitalize()
                for part in m_auto_on_play_grant_next_matching_union_play_keyword.group(2).replace("-", " ").split()
            )
            target_filters = _descriptor_filters(descriptor, branch)
            params: dict[str, int | str | bool] = {
                "grant_keyword": grant_keyword,
            }
            if "allowed_colors" in target_filters:
                params["allowed_colors"] = target_filters["allowed_colors"]
            required_characters = sorted(
                {
                    match.strip().title()
                    for match in re.findall(r"<([^>]+)>", descriptor)
                    if match.strip()
                }
            )
            if required_characters:
                params["required_characters"] = ",".join(required_characters)
            elif "required_characters" in target_filters:
                params["required_characters"] = target_filters["required_characters"]
            if "required_traits" in target_filters:
                params["required_traits"] = target_filters["required_traits"]
            if "required_name_contains" in target_filters:
                params["required_name_contains"] = target_filters["required_name_contains"]
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_pay_z_energy_on_play_and_grant_next_matching_union_play_keyword",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_battle_ko = _ACTIVATE_BATTLE_KO_UP_TO_N_OPP_BATTLE_RE.search(branch)
        if m_activate_battle_ko:
            max_targets = int(m_activate_battle_ko.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_ko_up_to_n_opponent_battle",
                    handler_params={"max_targets": max_targets, "target_policy": "first", **extra},
                    once_per_turn=once,
                )
            )

        m_activate_battle_send_opponent_combo_to_drop = _ACTIVATE_BATTLE_SEND_UP_TO_N_OPPONENT_COMBO_TO_DROP_RE.search(branch)
        if m_activate_battle_send_opponent_combo_to_drop:
            max_targets = int(m_activate_battle_send_opponent_combo_to_drop.group(1))
            max_combo_cost = int(m_activate_battle_send_opponent_combo_to_drop.group(2))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_send_up_to_n_opponent_combo_to_drop",
                    handler_params={
                        "max_targets": max_targets,
                        "max_combo_cost": max_combo_cost,
                        "target_policy": "first",
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_ko = _ACTIVATE_MAIN_KO_UP_TO_N_OPP_BATTLE_RE.search(branch)
        if m_activate_main_ko:
            max_targets = int(m_activate_main_ko.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_ko_up_to_n_opponent_battle",
                    handler_params={"max_targets": max_targets, "target_policy": "first", **extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        # [Activate: Main/Battle] ... : Draw N card(s).
        m_activate_main_battle_draw = _ACTIVATE_MAIN_BATTLE_DRAW_RE.search(branch)
        if (
            m_activate_main_battle_draw
            and not _ACTIVATE_MAIN_DRAW_LIFE_BOUNCE_AND_OPTIONAL_MAIN_PHASE_ENERGY_SWITCH_RE.search(branch)
            and not _ACTIVATE_MAIN_DRAW_AND_SWITCH_UP_TO_N_OPPONENT_BATTLE_OR_UNISON_ACTIVE_RE.search(branch)
        ):
            amount = int(m_activate_main_battle_draw.group(1))
            extra = _extract_common_conditions(branch)
            if is_extra:
                rules.append(
                    EffectRule(
                        trigger="self_activate_extra_from_hand",
                        handler_id="auto_draw_n",
                        handler_params={"amount": amount, **extra},
                        once_per_turn=once,
                    )
                )
            else:
                rules.append(
                    EffectRule(
                        trigger="self_activate_main",
                        handler_id="auto_draw_n",
                        handler_params={"amount": amount, **extra},
                        once_per_turn=once,
                    )
                )
                rules.append(
                    EffectRule(
                        trigger="self_activate_battle",
                        handler_id="auto_draw_n",
                        handler_params={"amount": amount, **extra},
                        once_per_turn=once,
                    )
                )

        m_activate_main_battle_switch_owner_cards_active_if_self = _ACTIVATE_MAIN_BATTLE_SWITCH_UP_TO_N_OWNER_CARDS_ACTIVE_AND_GAIN_KEYWORD_IF_SELF_SWITCHED_RE.search(branch)
        if m_activate_main_battle_switch_owner_cards_active_if_self:
            trigger_mode = str(m_activate_main_battle_switch_owner_cards_active_if_self.group(1) or "").strip().lower()
            max_targets = int(m_activate_main_battle_switch_owner_cards_active_if_self.group(2))
            grant_keyword = " ".join(
                part.capitalize() for part in str(m_activate_main_battle_switch_owner_cards_active_if_self.group(3) or "").replace("-", " ").split()
            )
            extra = _extract_common_conditions(branch)
            triggers = (
                ("self_activate_main", "self_activate_battle")
                if trigger_mode == "main/battle"
                else ("self_activate_main",)
                if trigger_mode == "main"
                else ("self_activate_battle",)
            )
            for trigger in triggers:
                rules.append(
                    EffectRule(
                        trigger=trigger,
                        handler_id="activate_switch_up_to_n_owner_cards_active_and_gain_keyword_if_self_switched",
                        handler_params={
                            "max_targets": max_targets,
                            "grant_keyword": grant_keyword,
                            "target_policy": "first",
                            **extra,
                        },
                        once_per_turn=once,
                        limit_per_turn=limit,
                    )
                )

        m_activate_main_play_self_then_place_all_opp_rest = _ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_THEN_PLACE_ALL_OPPONENT_REST_BATTLE_AND_UNISON_INTO_DROP_RE.search(branch)
        if m_activate_main_play_self_then_place_all_opp_rest:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_hand",
                    handler_params={
                        "post_play_drop_opponent_rest_battle_unison": True,
                        "post_play_drop_opponent_rest_ignores_barrier": True,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_remove_self_negate_leader = _ACTIVATE_MAIN_REMOVE_SELF_NEGATE_OPPONENT_LEADER_SKILLS_AND_RESTRICT_REST_ACTIVE_RE.search(branch)
        if m_activate_main_remove_self_negate_leader:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_negate_opponent_leader_skills_and_restrict_up_to_n_opponent_rest_cards_switch_active_until_opponent_turn_end",
                    handler_params={
                        "max_targets": int(m_activate_main_remove_self_negate_leader.group(1)),
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_battle_owner_cards_power = _ACTIVATE_MAIN_BATTLE_CHOOSE_OWNER_CARDS_GAIN_POWER_FOR_TURN_RE.search(branch)
        if m_activate_main_battle_owner_cards_power and m_activate_main_draw_then_owner_cards_power is None:
            max_targets = int(m_activate_main_battle_owner_cards_power.group(1))
            raw_descriptor = str(m_activate_main_battle_owner_cards_power.group(2) or "").strip()
            descriptor = raw_descriptor.lower()
            compact_descriptor = re.sub(r"\s+", " ", descriptor).strip()
            power_delta = int(m_activate_main_battle_owner_cards_power.group(3))
            extra = _extract_common_conditions(branch)
            filters = {} if compact_descriptor in {"battle", "battle card", "battle cards"} else _descriptor_filters(descriptor, branch)
            if "<" in raw_descriptor and "required_characters" not in filters and "required_traits" in filters:
                filters["required_characters"] = str(filters.pop("required_traits"))
            params = {
                "target_policy": "first",
                "target_scope": "owner_battle" if compact_descriptor in {"battle", "battle card", "battle cards"} else "owner_cards",
                "max_targets": max_targets,
                "power_delta": power_delta,
                **filters,
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="self_activate_extra_from_hand" if is_extra else "self_activate_main",
                    handler_id="activate_buff_owner_battle_cards",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            if not is_extra:
                rules.append(
                    EffectRule(
                        trigger="self_activate_battle",
                        handler_id="activate_buff_owner_battle_cards",
                        handler_params=dict(params),
                        once_per_turn=once,
                        limit_per_turn=limit,
                    )
                )

        m_activate_battle_owner_cards_power = _ACTIVATE_BATTLE_CHOOSE_OWNER_CARDS_GAIN_POWER_FOR_TURN_RE.search(branch)
        if m_activate_battle_owner_cards_power:
            max_targets = int(m_activate_battle_owner_cards_power.group(1))
            raw_descriptor = str(m_activate_battle_owner_cards_power.group(2) or "").strip()
            descriptor = raw_descriptor.lower()
            compact_descriptor = re.sub(r"\s+", " ", descriptor).strip()
            power_delta = int(m_activate_battle_owner_cards_power.group(3))
            extra = _extract_common_conditions(branch)
            filters = {} if compact_descriptor in {"battle", "battle card", "battle cards"} else _descriptor_filters(descriptor, branch)
            if "<" in raw_descriptor and "required_characters" not in filters and "required_traits" in filters:
                filters["required_characters"] = str(filters.pop("required_traits"))
            params = {
                "target_policy": "first",
                "target_scope": "owner_battle" if compact_descriptor in {"battle", "battle card", "battle cards"} else "owner_cards",
                "max_targets": max_targets,
                "power_delta": power_delta,
                **filters,
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_buff_owner_battle_cards",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_choose_owner_leader_or_battle_gain_power_and_keyword = (
            _ACTIVATE_MAIN_CHOOSE_OWNER_LEADER_OR_BATTLE_GAIN_POWER_AND_KEYWORD_FOR_TURN_RE.search(branch)
        )
        if m_activate_main_choose_owner_leader_or_battle_gain_power_and_keyword:
            extra = _extract_common_conditions(branch)
            grant_keyword = " ".join(
                part.capitalize()
                for part in str(m_activate_main_choose_owner_leader_or_battle_gain_power_and_keyword.group(3) or "")
                .replace("-", " ")
                .split()
            )
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_buff_owner_battle_cards",
                    handler_params={
                        "target_policy": "first",
                        "target_scope": "owner_cards",
                        "max_targets": 1,
                        "power_delta": int(m_activate_main_choose_owner_leader_or_battle_gain_power_and_keyword.group(2)),
                        "grant_keyword": grant_keyword,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if (card.card_type or "").upper() in {"EXTRA", "Z-EXTRA"}:
            m_activate_extra_play_each = _ACTIVATE_EXTRA_MAIN_BATTLE_PLAY_UP_TO_N_EACH_OF_TWO_FROM_OWNER_DECK_OR_DROP_RE.search(branch)
            if m_activate_extra_play_each:
                max_each = int(m_activate_extra_play_each.group(1))
                first_name = m_activate_extra_play_each.group(2).strip().upper()
                second_name = m_activate_extra_play_each.group(3).strip().upper()
                color = m_activate_extra_play_each.group(4).strip().lower()
                max_cost = int(m_activate_extra_play_each.group(5))
                extra = _extract_common_conditions(branch)
                params: dict[str, int | str | bool] = {
                    "max_each": max_each,
                    "required_name_contains_each": f"{first_name}|{second_name}",
                    "allowed_colors": color,
                    "required_card_type": "BATTLE",
                    "max_cost": max_cost,
                    **extra,
                }
                if "rest mode" in branch:
                    params["rest_mode"] = True
                m_discard_before = re.search(r"discard (\d+) card from your hand", branch)
                if m_discard_before:
                    params["discard_from_hand_before"] = int(m_discard_before.group(1))
                rules.append(
                    EffectRule(
                        trigger="self_activate_extra_from_hand",
                        handler_id="activate_play_up_to_n_each_named_from_owner_deck_or_drop",
                        handler_params=params,
                        once_per_turn=once,
                        limit_per_turn=limit,
                    )
                )

            m_activate_extra_add_from_deck = _ACTIVATE_EXTRA_MAIN_BATTLE_ADD_UP_TO_N_FROM_OWNER_DECK_TO_HAND_RE.search(branch)
            if m_activate_extra_add_from_deck:
                max_targets = int(m_activate_extra_add_from_deck.group(1))
                descriptor = m_activate_extra_add_from_deck.group(2).lower()
                extra = _extract_common_conditions(branch)
                rules.append(
                    EffectRule(
                        trigger="self_activate_extra_from_hand",
                        handler_id="activate_add_up_to_n_from_owner_deck_to_hand",
                        handler_params={
                            "max_targets": max_targets,
                            **_descriptor_filters(descriptor, branch),
                            **extra,
                        },
                        once_per_turn=once,
                        limit_per_turn=limit,
                    )
                )

        # [Activate: Main] ... Look at top N; add up to M matching cards to hand.
        m_activate_main_search = _ACTIVATE_MAIN_LOOK_TOP_ADD_TO_HAND_RE.search(branch)
        if m_activate_main_search:
            look_count = int(m_activate_main_search.group(1))
            max_add = int(m_activate_main_search.group(2))
            descriptor = m_activate_main_search.group(3).lower()
            m_discard = re.search(r"if you added a card to your hand, choose (\d+) card in your hand and discard it", branch)
            discard_after_add = int(m_discard.group(1)) if m_discard else 0
            m_bottom_after_add = re.search(
                r"if you added (\d+) cards? to your hand, choose (\d+) card in your hand and place it at the bottom of your deck",
                branch,
            )
            bottom_after_add_count = int(m_bottom_after_add.group(2)) if m_bottom_after_add else 0
            bottom_after_add_exact = int(m_bottom_after_add.group(1)) if m_bottom_after_add else 0
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "look_count": look_count,
                "max_add": max_add,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if discard_after_add > 0:
                params["discard_after_add"] = discard_after_add
            if "place the rest at the bottom of your deck" in branch:
                params["move_unpicked_to_bottom"] = True
            if bottom_after_add_count > 0:
                params["bottom_deck_after_add"] = bottom_after_add_count
            if bottom_after_add_exact > 0:
                params["bottom_deck_after_add_exact_add_count"] = bottom_after_add_exact
            m_self_power = re.search(r"this card gets \+(\d+) power for (?:the duration of )?the turn", branch, re.IGNORECASE)
            if m_self_power:
                params["power_delta"] = int(m_self_power.group(1))
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="auto_look_top_add_up_to_one_to_hand_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_activate_main_draw_switch_opponent_active = _ACTIVATE_MAIN_DRAW_AND_SWITCH_UP_TO_N_OPPONENT_BATTLE_OR_UNISON_ACTIVE_RE.search(branch)
        if m_activate_main_draw_switch_opponent_active:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_draw_n_and_switch_up_to_n_opponent_battle_or_unison_active",
                    handler_params={
                        "amount": int(m_activate_main_draw_switch_opponent_active.group(1)),
                        "max_targets": int(m_activate_main_draw_switch_opponent_active.group(2)),
                        "target_policy": "first",
                        "ignores_barrier": True,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_add_from_deck = _ACTIVATE_MAIN_ADD_UP_TO_N_FROM_OWNER_DECK_TO_HAND_RE.search(branch)
        if m_activate_main_add_from_deck and not is_extra:
            max_targets = int(m_activate_main_add_from_deck.group(1))
            descriptor = m_activate_main_add_from_deck.group(2).lower()
            source_pool_text = str(m_activate_main_add_from_deck.group(3) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            params = {
                "max_targets": max_targets,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if "life" in source_pool_text and "deck" in source_pool_text:
                params["source_pool"] = "deck_or_life"
            elif "life" in source_pool_text:
                params["source_pool"] = "life"
            if "shuffle any areas you looked through" in branch.lower():
                params["shuffle_searched_zones"] = True
            if "negate this skill for the game" in branch:
                params["negate_self_skill_for_game"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_add_up_to_n_from_owner_deck_to_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_battle_add_from_deck = _ACTIVATE_BATTLE_ADD_UP_TO_N_FROM_OWNER_DECK_TO_HAND_RE.search(branch)
        if m_activate_battle_add_from_deck:
            max_targets = int(m_activate_battle_add_from_deck.group(1))
            descriptor = m_activate_battle_add_from_deck.group(2).lower()
            extra = _extract_common_conditions(branch)
            params = {
                "max_targets": max_targets,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if "shuffle your deck" in branch.lower():
                params["shuffle_searched_zones"] = True
            m_allowed_costs = re.search(r"energy cost of (\d+) or (\d+)", descriptor)
            if m_allowed_costs:
                low = int(m_allowed_costs.group(1))
                high = int(m_allowed_costs.group(2))
                params["allowed_costs"] = f"{low},{high}"
                params["min_cost"] = min(low, high)
                params["max_cost"] = max(low, high)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_add_up_to_n_from_owner_deck_to_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_add_self_from_drop = _ACTIVATE_MAIN_ADD_SELF_FROM_OWNER_DROP_TO_HAND_RE.search(branch)
        if m_activate_main_add_self_from_drop:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_add_self_from_owner_drop_to_hand",
                    handler_params={**extra},
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_self_gain_power_and_keyword = _ACTIVATE_MAIN_SELF_GAIN_POWER_AND_KEYWORD_FOR_TURN_RE.search(branch)
        if m_activate_main_self_gain_power_and_keyword:
            power_delta = int(m_activate_main_self_gain_power_and_keyword.group(1))
            grant_keyword = " ".join(
                part.capitalize() for part in str(m_activate_main_self_gain_power_and_keyword.group(2) or "").replace("-", " ").split()
            )
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_gain_power_and_keyword_for_turn",
                    handler_params={
                        "power_delta": power_delta,
                        "grant_keyword": grant_keyword,
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_main_self_gain_keywords = _ACTIVATE_MAIN_SELF_GAIN_KEYWORDS_FOR_TURN_RE.search(branch)
        if m_activate_main_self_gain_keywords:
            keywords = [
                " ".join(part.capitalize() for part in str(raw or "").replace("-", " ").split())
                for raw in m_activate_main_self_gain_keywords.groups()
                if str(raw or "").strip()
            ]
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_gain_power_and_keyword_for_turn",
                    handler_params={
                        "grant_keywords": ",".join(keywords),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_battle_self_gain_power_and_keyword = _ACTIVATE_BATTLE_SELF_GAIN_POWER_AND_KEYWORD_FOR_TURN_RE.search(branch)
        if m_activate_battle_self_gain_power_and_keyword:
            power_delta = int(m_activate_battle_self_gain_power_and_keyword.group(1))
            grant_keyword = " ".join(
                part.capitalize() for part in str(m_activate_battle_self_gain_power_and_keyword.group(2) or "").replace("-", " ").split()
            )
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_gain_power_and_keyword_for_turn",
                    handler_params={
                        "power_delta": power_delta,
                        "grant_keyword": grant_keyword,
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        if _ACTIVATE_MAIN_GAIN_KEYWORD_FROM_UNDER_SELF_UNTIL_OPPONENT_TURN_END_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_gain_keyword_from_under_self_until_opponent_turn_end",
                    handler_params={
                        "min_source_stacked_cards": 1,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_play_self_from_hand_then_reveal_and_place_under_self = _ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_THEN_REVEAL_AND_PLACE_UNDER_SELF_RE.search(branch)
        if m_activate_main_play_self_from_hand_then_reveal_and_place_under_self:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "post_play_revealed_max_targets": int(m_activate_main_play_self_from_hand_then_reveal_and_place_under_self.group(1)),
                "post_play_place_under_self_max_targets": int(m_activate_main_play_self_from_hand_then_reveal_and_place_under_self.group(2)),
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
        m_activate_main_play_self_from_hand_then_play_token = _ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_THEN_PLAY_TOKEN_RE.search(branch)
        if m_activate_main_play_self_from_hand_then_play_token:
            fallback_stats = re.search(
                r"\([^)]*?(\d+)\s+power,\s*(\d+)\s+combo cost,\s*(?:and\s*)?(\d+)\s+combo power[^)]*\)",
                branch,
                re.IGNORECASE,
            )
            combo_cost = int(
                m_activate_main_play_self_from_hand_then_play_token.group(4) or (fallback_stats.group(2) if fallback_stats else 0) or 0
            )
            combo_power = int(
                m_activate_main_play_self_from_hand_then_play_token.group(5) or (fallback_stats.group(3) if fallback_stats else 0) or 0
            )
            explicit_power = (
                m_activate_main_play_self_from_hand_then_play_token.group(3)
                or m_activate_main_play_self_from_hand_then_play_token.group(6)
                or (fallback_stats.group(1) if fallback_stats else 0)
                or 0
            )
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "post_play_token_amount": int(m_activate_main_play_self_from_hand_then_play_token.group(1)),
                "post_play_token_name": str(m_activate_main_play_self_from_hand_then_play_token.group(2) or "Token").strip(),
                "post_play_token_power": int(explicit_power or 0),
                "post_play_token_combo_cost": combo_cost,
                "post_play_token_combo_power": combo_power,
                "post_play_token_resting": "in rest mode" in branch.lower(),
                **extra,
            }
            granted_keyword = str(m_activate_main_play_self_from_hand_then_play_token.group(7) or "").strip()
            if not granted_keyword:
                m_token_gain_keywords = _TOKEN_GAIN_KEYWORDS_RE.search(branch)
                granted_keyword = str(m_token_gain_keywords.group(1) or "").strip() if m_token_gain_keywords else ""
            if granted_keyword:
                params["post_play_token_temporary_keywords"] = _normalize_extracted_keywords(granted_keyword)
                params["post_play_token_keyword_duration"] = (
                    "opponent_turn" if "until the end of your opponent's next turn" in branch.lower() else "turn"
                )
            if "play this card from your hand in rest mode" in branch.lower():
                params["resting"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
        m_activate_main_play_self_from_hand_and_place_matching_owner_battle_under_self = _ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_AND_PLACE_MATCHING_OWNER_BATTLE_UNDER_SELF_RE.search(branch)
        if m_activate_main_play_self_from_hand_and_place_matching_owner_battle_under_self:
            extra = _extract_common_conditions(branch)
            descriptor = str(m_activate_main_play_self_from_hand_and_place_matching_owner_battle_under_self.group(2) or "").strip().lower()
            target_filters = _descriptor_filters(descriptor, branch)
            params = {
                "post_play_place_owner_battle_under_self_max_targets": int(
                    m_activate_main_play_self_from_hand_and_place_matching_owner_battle_under_self.group(1)
                ),
                "post_play_place_owner_battle_under_self_target_policy": "first",
                **extra,
            }
            if "allowed_colors" in target_filters:
                params["post_play_place_owner_battle_under_self_allowed_colors"] = target_filters["allowed_colors"]
            if "required_traits" in target_filters:
                params["post_play_place_owner_battle_under_self_required_traits"] = target_filters["required_traits"]
            if "required_characters" in target_filters:
                params["post_play_place_owner_battle_under_self_required_characters"] = target_filters["required_characters"]
            if "required_name_contains" in target_filters:
                params["post_play_place_owner_battle_under_self_required_name_contains"] = target_filters["required_name_contains"]
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
        m_activate_main_play_self_from_hand_then_switch_opponent_battle_rest = _ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_THEN_SWITCH_UP_TO_N_OPPONENT_BATTLE_REST_RE.search(branch)
        if m_activate_main_play_self_from_hand_then_switch_opponent_battle_rest:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "post_play_rest_max_targets": int(m_activate_main_play_self_from_hand_then_switch_opponent_battle_rest.group(1)),
                **extra,
            }
            if "rest mode" in branch:
                params["resting"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
        if (
            "play this card from your z-energy" in branch.lower()
            and "choose up to 1 of your opponent's battle cards or unisons" in branch.lower()
            and "switch it to rest mode" in branch.lower()
            and "can't switch to active mode until the end of your opponent's turn" in branch.lower()
        ):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_hand",
                    handler_params={
                        "required_source_zone": "z_energy",
                        "post_play_rest_board_max_targets": 1,
                        "post_play_rest_prevent_active_until_opponent_turn": True,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
        if (
            "play this card from your z-energy" in branch.lower()
            and "choose up to 1 of your opponent's rest mode battle cards" in branch.lower()
            and "ko it" in branch.lower()
        ):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_hand",
                    handler_params={
                        "required_source_zone": "z_energy",
                        "post_play_ko_rest_battle_max_targets": 1,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
        m_activate_main_play_self_from_hand_with_markers = _ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_IN_REST_MODE_WITH_MARKERS_RE.search(branch)
        if m_activate_main_play_self_from_hand_with_markers:
            extra = _extract_common_conditions(branch)
            marker_count = int(m_activate_main_play_self_from_hand_with_markers.group(1) or 1)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_hand",
                    handler_params={
                        "resting": True,
                        "markers": marker_count,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
        elif _ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_RE.search(branch):
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {**extra}
            if "rest mode" in branch:
                params["resting"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_hand",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_activate_main_play_self_from_under_leader_then_ko = _ACTIVATE_MAIN_PLAY_SELF_FROM_UNDER_LEADER_THEN_KO_RE.search(branch)
        if m_activate_main_play_self_from_under_leader_then_ko:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "required_source_zone": "leader_under",
                "ko_max_targets": int(m_activate_main_play_self_from_under_leader_then_ko.group(3)),
                **extra,
            }
            host_name = str(m_activate_main_play_self_from_under_leader_then_ko.group(1) or "").strip()
            host_character = str(m_activate_main_play_self_from_under_leader_then_ko.group(2) or "").strip()
            tail = str(m_activate_main_play_self_from_under_leader_then_ko.group(4) or "").lower()
            if host_name:
                params["under_host_name_contains"] = host_name.upper()
            if host_character:
                params["under_host_required_characters"] = host_character
            if "rest mode" in tail:
                params["ko_rest_mode_only"] = True
            if "ignoring [barrier]" in tail:
                params["ko_ignores_barrier"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_under_owner_leader_then_ko_up_to_n_opponent_battle",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_activate_main_play_self_from_under_leader = _ACTIVATE_MAIN_PLAY_SELF_FROM_UNDER_LEADER_RE.search(branch)
        if m_activate_main_play_self_from_under_leader:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "required_source_zone": "leader_under",
                **extra,
            }
            host_name = str(m_activate_main_play_self_from_under_leader.group(1) or "").strip()
            host_character = str(m_activate_main_play_self_from_under_leader.group(2) or "").strip()
            if host_name:
                params["under_host_name_contains"] = host_name.upper()
            if host_character:
                params["under_host_required_characters"] = host_character
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_under_owner_leader",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_activate_main_place_self_from_under_leader_on_top = _ACTIVATE_MAIN_PLACE_SELF_FROM_UNDER_LEADER_ON_TOP_OF_LEADER_RE.search(branch)
        if m_activate_main_place_self_from_under_leader_on_top:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "required_source_zone": "leader_under",
                **_extract_under_leader_promotion_requirements(branch),
                **extra,
            }
            if "switch your leader to active mode" in branch.lower():
                params["switch_owner_leader_active_after"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_self_from_under_owner_leader_on_top_of_owner_leader",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_place_self_under_matching_owner_battle = _ACTIVATE_MAIN_PLACE_SELF_UNDER_MATCHING_OWNER_BATTLE_RE.search(branch)
        if m_activate_main_place_self_under_matching_owner_battle:
            max_targets = int(m_activate_main_place_self_under_matching_owner_battle.group(1))
            descriptor = str(m_activate_main_place_self_under_matching_owner_battle.group(2) or "").strip().lower()
            min_cost = int(m_activate_main_place_self_under_matching_owner_battle.group(3))
            extra = _extract_common_conditions(branch)
            filters = _descriptor_filters(descriptor, branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "required_owner_battle_min_cost": min_cost,
                "required_owner_battle_exclude_source_instance": True,
                "required_owner_battle_without_source_name_under": True,
                **extra,
            }
            if "allowed_colors" in filters:
                params["required_owner_battle_allowed_colors"] = filters["allowed_colors"]
            if "required_traits" in filters:
                if "<" in descriptor and "required_characters" not in filters:
                    params["required_owner_battle_required_characters"] = filters["required_traits"]
                else:
                    params["required_owner_battle_required_traits"] = filters["required_traits"]
            if "required_characters" in filters:
                params["required_owner_battle_required_characters"] = filters["required_characters"]
            if "required_name_contains" in filters:
                params["required_owner_battle_required_name_contains"] = filters["required_name_contains"]
            if "mono-" in descriptor or "mono " in descriptor:
                params["required_owner_battle_require_mono_color"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_self_under_matching_owner_battle",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_place_self_under_owner_battle_draw_and_bounce = _ACTIVATE_MAIN_PLACE_SELF_UNDER_OWNER_BATTLE_DRAW_AND_BOUNCE_RE.search(branch)
        if m_activate_main_place_self_under_owner_battle_draw_and_bounce:
            max_hosts = int(m_activate_main_place_self_under_owner_battle_draw_and_bounce.group(1))
            descriptor = str(m_activate_main_place_self_under_owner_battle_draw_and_bounce.group(2) or "").strip().lower()
            tail = str(m_activate_main_place_self_under_owner_battle_draw_and_bounce.group(3) or "").strip().lower()
            draw_count = int(m_activate_main_place_self_under_owner_battle_draw_and_bounce.group(4))
            max_targets = int(m_activate_main_place_self_under_owner_battle_draw_and_bounce.group(5))
            extra = _extract_common_conditions(branch)
            filters = _descriptor_filters(descriptor, branch)
            params: dict[str, int | str | bool] = {
                "max_host_targets": max_hosts,
                "amount": draw_count,
                "max_targets": max_targets,
                "required_owner_battle_exclude_source_instance": True,
                **extra,
            }
            if "allowed_colors" in filters:
                params["required_owner_battle_allowed_colors"] = filters["allowed_colors"]
            if "required_traits" in filters:
                params["required_owner_battle_required_traits"] = filters["required_traits"]
            if "required_characters" in filters:
                params["required_owner_battle_required_characters"] = filters["required_characters"]
            if "required_name_contains" in filters:
                params["required_owner_battle_required_name_contains"] = filters["required_name_contains"]
            if "[revive" in descriptor or "[revive" in tail:
                params["required_owner_battle_skill_text_contains"] = "[revive"
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_self_under_matching_owner_battle_then_draw_n_and_return_up_to_n_opponent_battle_to_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_place_self_under_matching_owner_battle_then_bottom_deck = _ACTIVATE_MAIN_PLACE_SELF_UNDER_MATCHING_OWNER_BATTLE_THEN_BOTTOM_DECK_RE.search(branch)
        if m_activate_main_place_self_under_matching_owner_battle_then_bottom_deck:
            host_descriptor = str(m_activate_main_place_self_under_matching_owner_battle_then_bottom_deck.group(1) or "").strip().lower()
            max_targets = int(m_activate_main_place_self_under_matching_owner_battle_then_bottom_deck.group(2))
            extra = _extract_common_conditions(branch)
            filters = _descriptor_filters(host_descriptor, branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "required_owner_battle_exclude_source_instance": True,
                **extra,
            }
            if "allowed_colors" in filters:
                params["required_owner_battle_allowed_colors"] = filters["allowed_colors"]
            if "required_traits" in filters:
                if "<" in host_descriptor and "required_characters" not in filters:
                    params["required_owner_battle_required_characters"] = filters["required_traits"]
                else:
                    params["required_owner_battle_required_traits"] = filters["required_traits"]
            if "required_characters" in filters:
                params["required_owner_battle_required_characters"] = filters["required_characters"]
            if "required_name_contains" in filters:
                params["required_owner_battle_required_name_contains"] = filters["required_name_contains"]
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_self_under_matching_owner_battle_then_bottom_deck_up_to_n_opponent_battle",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_place_self_under_named_owner_battle_then_add_from_deck = _ACTIVATE_MAIN_PLACE_SELF_UNDER_NAMED_OWNER_BATTLE_THEN_ADD_FROM_DECK_TO_HAND_RE.search(branch)
        if m_activate_main_place_self_under_named_owner_battle_then_add_from_deck:
            host_name = str(m_activate_main_place_self_under_named_owner_battle_then_add_from_deck.group(1) or "").strip()
            max_targets = int(m_activate_main_place_self_under_named_owner_battle_then_add_from_deck.group(2))
            target_name = str(m_activate_main_place_self_under_named_owner_battle_then_add_from_deck.group(3) or "").strip()
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "required_owner_battle_required_name_contains": host_name.upper(),
                "required_owner_battle_exclude_source_instance": True,
                "required_name_contains": target_name.upper(),
                "shuffle_searched_zones": True,
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_self_under_matching_owner_battle_then_add_up_to_n_from_owner_deck_to_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand_on_top = _ACTIVATE_MAIN_PLACE_SELF_UNDER_OWNER_BATTLE_THEN_PLAY_FROM_OWNER_DECK_OR_HAND_ON_TOP_RE.search(branch)
        if m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand_on_top:
            max_hosts = int(m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand_on_top.group(1))
            host_descriptor = str(m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand_on_top.group(2) or "").strip().lower()
            host_cost_low = int(m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand_on_top.group(3))
            host_cost_high_raw = m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand_on_top.group(4)
            host_cost_high = int(host_cost_high_raw) if host_cost_high_raw else host_cost_low
            max_targets = int(m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand_on_top.group(5))
            target_descriptor = str(m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand_on_top.group(6) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            host_filters = _descriptor_filters(host_descriptor, branch)
            target_filters = _descriptor_filters(target_descriptor, branch)
            params: dict[str, int | str | bool] = {
                "max_host_targets": max_hosts,
                "max_targets": max_targets,
                "required_owner_battle_min_cost": min(host_cost_low, host_cost_high),
                "required_owner_battle_max_cost": max(host_cost_low, host_cost_high),
                "required_owner_battle_exclude_source_instance": True,
                "play_on_top_active_mode": True,
                **extra,
            }
            if host_cost_low == host_cost_high:
                params["required_owner_battle_allowed_costs"] = str(host_cost_low)
            else:
                params["required_owner_battle_allowed_costs"] = f"{host_cost_low},{host_cost_high}"
            if "allowed_colors" in host_filters:
                params["required_owner_battle_allowed_colors"] = host_filters["allowed_colors"]
            if "required_traits" in host_filters:
                if "<" in host_descriptor and "required_characters" not in host_filters:
                    params["required_owner_battle_required_characters"] = host_filters["required_traits"]
                else:
                    params["required_owner_battle_required_traits"] = host_filters["required_traits"]
            if "required_characters" in host_filters:
                params["required_owner_battle_required_characters"] = host_filters["required_characters"]
            if "required_name_contains" in host_filters:
                params["required_owner_battle_required_name_contains"] = host_filters["required_name_contains"]
            if "mono-" in host_descriptor or "mono " in host_descriptor:
                params["required_owner_battle_require_mono_color"] = True
            for key, value in target_filters.items():
                if key == "allowed_colors":
                    params["allowed_colors"] = value
                elif key == "required_traits":
                    if "<" in target_descriptor and "required_characters" not in target_filters:
                        params["required_characters"] = value
                    else:
                        params["required_traits"] = value
                elif key == "required_characters":
                    params["required_characters"] = value
                elif key == "required_name_contains":
                    params["required_name_contains"] = value
                elif key == "required_card_type":
                    params["required_card_type"] = value
                elif key == "requires_skill_less":
                    params["requires_skill_less"] = value
                elif key == "max_cost" and int(value) >= 0:
                    params["max_cost"] = value
            m_target_cost_exact = re.search(r"energy cost of (\d+)\b", target_descriptor)
            m_target_cost_less = re.search(r"energy cost of (\d+) or less", target_descriptor)
            if m_target_cost_exact and not m_target_cost_less:
                params["min_cost"] = int(m_target_cost_exact.group(1))
                params["max_cost"] = int(m_target_cost_exact.group(1))
                params["allowed_costs"] = str(int(m_target_cost_exact.group(1)))
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_self_under_matching_owner_battle_then_play_up_to_n_from_owner_deck_or_hand_on_top_of_host",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand = _ACTIVATE_MAIN_PLACE_SELF_UNDER_OWNER_BATTLE_THEN_PLAY_FROM_OWNER_DECK_OR_HAND_RE.search(branch)
        if m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand:
            max_hosts = int(m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand.group(1))
            host_descriptor = str(m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand.group(2) or "").strip().lower()
            host_cost_low = int(m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand.group(3))
            host_cost_high_raw = m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand.group(4)
            host_cost_high = int(host_cost_high_raw) if host_cost_high_raw else host_cost_low
            max_targets = int(m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand.group(5))
            target_descriptor = str(m_activate_main_place_self_under_owner_battle_then_play_from_owner_deck_or_hand.group(6) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            host_filters = _descriptor_filters(host_descriptor, branch)
            target_filters = _descriptor_filters(target_descriptor, branch)
            params: dict[str, int | str | bool] = {
                "max_host_targets": max_hosts,
                "max_targets": max_targets,
                "required_owner_battle_min_cost": min(host_cost_low, host_cost_high),
                "required_owner_battle_max_cost": max(host_cost_low, host_cost_high),
                "required_owner_battle_exclude_source_instance": True,
                **extra,
            }
            if host_cost_low == host_cost_high:
                params["required_owner_battle_allowed_costs"] = str(host_cost_low)
            else:
                params["required_owner_battle_allowed_costs"] = f"{host_cost_low},{host_cost_high}"
            if "allowed_colors" in host_filters:
                params["required_owner_battle_allowed_colors"] = host_filters["allowed_colors"]
            if "required_traits" in host_filters:
                if "<" in host_descriptor and "required_characters" not in host_filters:
                    params["required_owner_battle_required_characters"] = host_filters["required_traits"]
                else:
                    params["required_owner_battle_required_traits"] = host_filters["required_traits"]
            if "required_characters" in host_filters:
                params["required_owner_battle_required_characters"] = host_filters["required_characters"]
            if "required_name_contains" in host_filters:
                params["required_owner_battle_required_name_contains"] = host_filters["required_name_contains"]
            if "mono-" in host_descriptor or "mono " in host_descriptor:
                params["required_owner_battle_require_mono_color"] = True
            for key, value in target_filters.items():
                if key == "allowed_colors":
                    params["allowed_colors"] = value
                elif key == "required_traits":
                    if "<" in target_descriptor and "required_characters" not in target_filters:
                        params["required_characters"] = value
                    else:
                        params["required_traits"] = value
                elif key == "required_characters":
                    params["required_characters"] = value
                elif key == "required_name_contains":
                    params["required_name_contains"] = value
                elif key == "required_card_type":
                    params["required_card_type"] = value
                elif key == "requires_skill_less":
                    params["requires_skill_less"] = value
                elif key == "max_cost" and int(value) >= 0:
                    params["max_cost"] = value
            m_target_cost_exact = re.search(r"energy cost of (\d+)\b", target_descriptor)
            m_target_cost_less = re.search(r"energy cost of (\d+) or less", target_descriptor)
            if m_target_cost_exact and not m_target_cost_less:
                params["min_cost"] = int(m_target_cost_exact.group(1))
                params["max_cost"] = int(m_target_cost_exact.group(1))
                params["allowed_costs"] = str(int(m_target_cost_exact.group(1)))
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_self_under_matching_owner_battle_then_play_up_to_n_from_owner_deck_or_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_place_self_in_owner_drop_then_play_from_owner_deck_or_hand = _ACTIVATE_MAIN_PLACE_SELF_IN_OWNER_DROP_THEN_PLAY_FROM_OWNER_DECK_OR_HAND_RE.search(branch)
        if m_activate_main_place_self_in_owner_drop_then_play_from_owner_deck_or_hand:
            leader_descriptor = str(m_activate_main_place_self_in_owner_drop_then_play_from_owner_deck_or_hand.group(1) or "").strip().lower()
            max_targets = int(m_activate_main_place_self_in_owner_drop_then_play_from_owner_deck_or_hand.group(2))
            target_descriptor = str(m_activate_main_place_self_in_owner_drop_then_play_from_owner_deck_or_hand.group(3) or "").strip().lower()
            between_low = m_activate_main_place_self_in_owner_drop_then_play_from_owner_deck_or_hand.group(4)
            between_high = m_activate_main_place_self_in_owner_drop_then_play_from_owner_deck_or_hand.group(5)
            exact_or_low = m_activate_main_place_self_in_owner_drop_then_play_from_owner_deck_or_hand.group(6)
            exact_or_high = m_activate_main_place_self_in_owner_drop_then_play_from_owner_deck_or_hand.group(7)
            exact_single = m_activate_main_place_self_in_owner_drop_then_play_from_owner_deck_or_hand.group(8)
            min_cost = -1
            max_cost = -1
            allowed_costs: set[int] = set()
            if between_low and between_high:
                min_cost = int(between_low)
                max_cost = int(between_high)
                allowed_costs = set(range(min_cost, max_cost + 1))
            elif exact_or_low and exact_or_high:
                allowed_costs = {int(exact_or_low), int(exact_or_high)}
                min_cost = min(allowed_costs)
                max_cost = max(allowed_costs)
            elif exact_single:
                allowed_costs = {int(exact_single)}
                min_cost = int(exact_single)
                max_cost = int(exact_single)
            leader_filters = {
                k: v
                for k, v in _descriptor_filters(leader_descriptor, branch).items()
                if k in {"allowed_colors", "required_traits", "required_characters", "required_name_contains"}
            }
            target_filters = _descriptor_filters(target_descriptor, branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "min_cost": min_cost,
                "max_cost": max_cost,
            }
            if allowed_costs:
                params["allowed_costs"] = ",".join(str(v) for v in sorted(allowed_costs))
            for key, value in leader_filters.items():
                params[f"leader_{key}"] = value
            for key in ("allowed_colors", "required_traits", "required_characters", "required_name_contains"):
                if key in target_filters:
                    if key == "required_traits" and "<" in target_descriptor and "required_characters" not in target_filters:
                        params["required_characters"] = target_filters[key]
                    else:
                        params[key] = target_filters[key]
            required_card_type = str(target_filters.get("required_card_type", "") or "").strip().upper()
            if required_card_type:
                params["required_card_type"] = required_card_type
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_up_to_n_from_owner_deck_or_hand_after_self_to_drop",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_place_opponent_battle_under_host_above_source = _ACTIVATE_MAIN_PLACE_UP_TO_N_OPPONENT_BATTLE_UNDER_HOST_ABOVE_SOURCE_RE.search(branch)
        if m_activate_main_place_opponent_battle_under_host_above_source:
            source_host_descriptor = str(m_activate_main_place_opponent_battle_under_host_above_source.group(1) or "").strip().lower()
            max_targets = int(m_activate_main_place_opponent_battle_under_host_above_source.group(2))
            extra = _extract_common_conditions(branch)
            source_host_filters = _descriptor_filters(source_host_descriptor, branch)
            params: dict[str, int | str | bool] = {
                "required_source_zone": "battle_under",
                "max_targets": max_targets,
                **extra,
            }
            if "allowed_colors" in source_host_filters:
                params["under_host_allowed_colors"] = source_host_filters["allowed_colors"]
            if "required_traits" in source_host_filters:
                params["under_host_required_traits"] = source_host_filters["required_traits"]
            if "required_characters" in source_host_filters:
                params["under_host_required_characters"] = source_host_filters["required_characters"]
            if "required_name_contains" in source_host_filters:
                params["under_host_name_contains"] = source_host_filters["required_name_contains"]
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_up_to_n_opponent_battle_under_source_host_and_switch_host_active_on_turn_end",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_battle_under_draw_and_ko_by_host_power = _ACTIVATE_MAIN_BATTLE_UNDER_DRAW_AND_KO_BY_HOST_POWER_RE.search(branch)
        if m_activate_main_battle_under_draw_and_ko_by_host_power:
            host_descriptor = str(m_activate_main_battle_under_draw_and_ko_by_host_power.group(1) or "").strip().lower()
            draw_count = int(m_activate_main_battle_under_draw_and_ko_by_host_power.group(2))
            max_targets = int(m_activate_main_battle_under_draw_and_ko_by_host_power.group(3))
            extra = _extract_common_conditions(branch)
            host_filters = _descriptor_filters(host_descriptor, branch)
            params: dict[str, int | str | bool] = {
                "required_source_zone": "battle_under",
                "amount": draw_count,
                "max_targets": max_targets,
                **extra,
            }
            if "allowed_colors" in host_filters:
                params["under_host_allowed_colors"] = host_filters["allowed_colors"]
            if "required_traits" in host_filters:
                if "<" in host_descriptor and "required_characters" not in host_filters:
                    params["under_host_required_characters"] = host_filters["required_traits"]
                else:
                    params["under_host_required_traits"] = host_filters["required_traits"]
            if "required_characters" in host_filters:
                params["under_host_required_characters"] = host_filters["required_characters"]
            if "required_name_contains" in host_filters:
                params["under_host_name_contains"] = host_filters["required_name_contains"]
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_draw_n_and_ko_up_to_n_opponent_battle_by_source_host_power",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_remove_self_and_place_from_under_leader_on_top = _ACTIVATE_MAIN_REMOVE_SELF_AND_PLACE_FROM_UNDER_LEADER_ON_TOP_OF_LEADER_RE.search(branch)
        if m_activate_main_remove_self_and_place_from_under_leader_on_top:
            min_under_count = int(m_activate_main_remove_self_and_place_from_under_leader_on_top.group(1))
            host_name = str(m_activate_main_remove_self_and_place_from_under_leader_on_top.group(2) or "").strip().upper()
            max_targets = int(m_activate_main_remove_self_and_place_from_under_leader_on_top.group(3))
            descriptor = str(m_activate_main_remove_self_and_place_from_under_leader_on_top.group(4) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "required_owner_battle_under_count_at_least": min_under_count,
                "required_owner_battle_under_host_required_name_contains": host_name,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if "switch your leader to active mode" in branch.lower():
                params["switch_owner_leader_active_after"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_remove_self_and_place_up_to_n_from_under_owner_leader_on_top_of_owner_leader",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_rest_named_host_place_self_and_named_deck_under = _ACTIVATE_MAIN_REST_NAMED_HOST_PLACE_SELF_AND_NAMED_DECK_UNDER_CHOSEN_RE.search(branch)
        if m_activate_main_rest_named_host_place_self_and_named_deck_under:
            host_name = str(m_activate_main_rest_named_host_place_self_and_named_deck_under.group(2) or "").strip().upper()
            max_targets = int(m_activate_main_rest_named_host_place_self_and_named_deck_under.group(3))
            required_name = str(m_activate_main_rest_named_host_place_self_and_named_deck_under.group(4) or "").strip().upper()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_self_from_hand_and_up_to_n_named_from_owner_deck_under_named_host",
                    handler_params={
                        "host_name_contains": host_name,
                        "max_targets": max_targets,
                        "required_name_contains": required_name,
                        "rest_host": True,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_rest_named_host_place_each_named_hand_under = _ACTIVATE_MAIN_REST_NAMED_HOST_PLACE_EACH_NAMED_HAND_UNDER_CHOSEN_RE.search(branch)
        if m_activate_main_rest_named_host_place_each_named_hand_under:
            host_name = str(m_activate_main_rest_named_host_place_each_named_hand_under.group(1) or "").strip().upper()
            first_name = str(m_activate_main_rest_named_host_place_each_named_hand_under.group(2) or "").strip().upper()
            second_name = str(m_activate_main_rest_named_host_place_each_named_hand_under.group(3) or "").strip().upper()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_rest_named_host_and_place_each_named_from_owner_hand_under_it",
                    handler_params={
                        "host_name_contains": host_name,
                        "required_name_contains_each": f"{first_name}|{second_name}",
                        "rest_host": True,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_draw_and_play_named_under_host = _ACTIVATE_MAIN_DRAW_AND_PLAY_NAMED_FROM_OWNER_HAND_UNDER_NAMED_HOST_RE.search(branch)
        if m_activate_main_draw_and_play_named_under_host:
            amount = int(m_activate_main_draw_and_play_named_under_host.group(1))
            max_targets = int(m_activate_main_draw_and_play_named_under_host.group(2))
            required_name = str(m_activate_main_draw_and_play_named_under_host.group(3) or "").strip().upper()
            host_name = str(m_activate_main_draw_and_play_named_under_host.group(4) or "").strip().upper()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_draw_n_and_play_up_to_n_named_from_owner_hand_under_named_host",
                    handler_params={
                        "amount": amount,
                        "max_targets": max_targets,
                        "required_name_contains": required_name,
                        "host_name_contains": host_name,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_place_from_hand_under_named_host_then_draw = _ACTIVATE_MAIN_PLACE_N_FROM_OWNER_HAND_UNDER_NAMED_HOST_THEN_DRAW_RE.search(branch)
        if m_activate_main_place_from_hand_under_named_host_then_draw:
            amount = int(m_activate_main_place_from_hand_under_named_host_then_draw.group(1))
            host_name = str(m_activate_main_place_from_hand_under_named_host_then_draw.group(2) or "").strip().upper()
            draw_count = int(m_activate_main_place_from_hand_under_named_host_then_draw.group(3))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_up_to_n_from_owner_hand_under_named_host_then_draw_n",
                    handler_params={
                        "max_targets": amount,
                        "host_name_contains": host_name,
                        "draw_count": draw_count,
                        "required_owner_hand_count_at_least": amount,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_rest_owner_battles_and_place_top_deck_under_named_host = _ACTIVATE_MAIN_REST_ANY_NUMBER_OWNER_BATTLES_AND_PLACE_TOP_DECK_UNDER_NAMED_HOST_RE.search(branch)
        if m_activate_main_rest_owner_battles_and_place_top_deck_under_named_host:
            host_name = str(m_activate_main_rest_owner_battles_and_place_top_deck_under_named_host.group(1) or "").strip().upper()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_rest_any_number_owner_battles_and_place_top_deck_under_named_host",
                    handler_params={
                        "host_name_contains": host_name,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_play_named_from_drop_and_gain_power = _ACTIVATE_MAIN_PLAY_NAMED_FROM_OWNER_DROP_AND_GAIN_POWER_RE.search(branch)
        if m_activate_main_play_named_from_drop_and_gain_power:
            max_targets = int(m_activate_main_play_named_from_drop_and_gain_power.group(1))
            required_name = str(m_activate_main_play_named_from_drop_and_gain_power.group(2) or "").strip().upper()
            power_delta = int(m_activate_main_play_named_from_drop_and_gain_power.group(3))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_up_to_n_named_from_owner_drop_and_gain_power_for_turn",
                    handler_params={
                        "max_targets": max_targets,
                        "required_name_contains": required_name,
                        "power_delta": power_delta,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_move_under_leader_to_z_energy_then_place_self_from_drop_under_owner_leader = _ACTIVATE_MAIN_MOVE_UNDER_LEADER_TO_Z_ENERGY_THEN_PLACE_SELF_FROM_DROP_UNDER_OWNER_LEADER_RE.search(branch)
        if m_activate_main_move_under_leader_to_z_energy_then_place_self_from_drop_under_owner_leader:
            amount = int(m_activate_main_move_under_leader_to_z_energy_then_place_self_from_drop_under_owner_leader.group(1))
            color = str(m_activate_main_move_under_leader_to_z_energy_then_place_self_from_drop_under_owner_leader.group(2) or "").strip().lower()
            card_type = str(m_activate_main_move_under_leader_to_z_energy_then_place_self_from_drop_under_owner_leader.group(3) or "").strip().upper()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_self_under_owner_leader",
                    handler_params={
                        **extra,
                        "required_source_zone": "drop",
                        "required_owner_leader_under_count_at_least": amount,
                        "required_owner_leader_under_allowed_colors": color,
                        "required_owner_leader_under_required_card_types": card_type,
                        "move_under_leader_to_z_energy_before": amount,
                        "move_under_leader_to_z_energy_allowed_colors": color,
                        "move_under_leader_to_z_energy_required_card_types": card_type,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
        elif _ACTIVATE_MAIN_PLACE_SELF_UNDER_OWNER_LEADER_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_place_self_under_owner_leader",
                    handler_params={**extra},
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_delayed_token = _ACTIVATE_MAIN_DELAYED_TOKEN_RE.search(branch)
        if m_activate_main_delayed_token:
            fallback_stats = re.search(
                r"\([^)]*?(\d+)\s+power,\s*(\d+)\s+combo cost,\s*(?:and\s*)?(\d+)\s+combo power[^)]*\)",
                branch,
                re.IGNORECASE,
            )
            combo_cost = int(m_activate_main_delayed_token.group(4) or (fallback_stats.group(2) if fallback_stats else 0) or 0)
            combo_power = int(m_activate_main_delayed_token.group(5) or (fallback_stats.group(3) if fallback_stats else 0) or 0)
            explicit_power = m_activate_main_delayed_token.group(3) or m_activate_main_delayed_token.group(6) or (fallback_stats.group(1) if fallback_stats else 0) or 0
            add_from_life_match = re.search(
                r"add up to (\d+) card[s]? from your life to your hand",
                branch,
                re.IGNORECASE,
            )
            handler_params: dict[str, object] = {
                "amount": int(m_activate_main_delayed_token.group(1)),
                "token_name": str(m_activate_main_delayed_token.group(2) or "Token").strip(),
                "power": int(explicit_power or 0),
                "combo_cost": combo_cost,
                "combo_power": combo_power,
                "resting": "in rest mode" in branch.lower(),
                "trigger_kind": "turn_end",
                "trigger_player_scope": "current",
                "require_next_turn": False,
                **_extract_common_conditions(branch),
            }
            if add_from_life_match:
                handler_params["add_from_life_to_hand_max_targets"] = int(add_from_life_match.group(1))
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_schedule_play_token_in_battle",
                    handler_params=handler_params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_battle_immediate_token = _ACTIVATE_MAIN_BATTLE_IMMEDIATE_TOKEN_RE.search(branch)
        if (
            m_activate_main_battle_immediate_token
            and "play this card from your hand" not in branch.lower()
            and "at the end of the turn, play" not in branch.lower()
        ):
            fallback_stats = re.search(
                r"\([^)]*?(\d+)\s+power,\s*(\d+)\s+combo cost,\s*(?:and\s*)?(\d+)\s+combo power[^)]*\)",
                branch,
                re.IGNORECASE,
            )
            combo_cost = int(
                m_activate_main_battle_immediate_token.group(5) or (fallback_stats.group(2) if fallback_stats else 0) or 0
            )
            combo_power = int(
                m_activate_main_battle_immediate_token.group(6) or (fallback_stats.group(3) if fallback_stats else 0) or 0
            )
            explicit_power = (
                m_activate_main_battle_immediate_token.group(4)
                or m_activate_main_battle_immediate_token.group(7)
                or (fallback_stats.group(1) if fallback_stats else 0)
                or 0
            )
            params: dict[str, int | str | bool] = {
                "amount": int(m_activate_main_battle_immediate_token.group(2)),
                "token_name": _normalize_token_name(m_activate_main_battle_immediate_token.group(3)),
                "power": int(explicit_power or 0),
                "combo_cost": combo_cost,
                "combo_power": combo_power,
                "resting": "in rest mode" in branch.lower(),
                **_extract_common_conditions(branch),
            }
            m_token_then_buff_all = _TOKEN_THEN_CHOOSE_ALL_OWNER_BATTLE_GAIN_KEYWORD_RE.search(branch)
            granted_keyword = str(m_activate_main_battle_immediate_token.group(8) or "").strip()
            if not granted_keyword and not m_token_then_buff_all:
                m_token_gain_keywords = _TOKEN_GAIN_KEYWORDS_RE.search(branch)
                granted_keyword = str(m_token_gain_keywords.group(1) or "").strip() if m_token_gain_keywords else ""
            if granted_keyword:
                params["temporary_keywords"] = _normalize_extracted_keywords(granted_keyword)
                params["keyword_duration"] = (
                    "opponent_turn" if "until the end of your opponent's next turn" in branch.lower() else "turn"
                )
            if m_token_then_buff_all:
                descriptor = str(m_token_then_buff_all.group(1) or "").strip().lower()
                buff_filters = _descriptor_filters(descriptor, branch)
                if "token" in descriptor and "required_name_contains" not in buff_filters:
                    buff_filters.pop("required_characters", None)
                    buff_filters.pop("required_traits", None)
                    buff_filters["required_name_contains"] = _normalize_token_name(descriptor).upper()
                elif descriptor and not any(
                    key in buff_filters for key in ("allowed_colors", "required_traits", "required_characters", "required_name_contains")
                ):
                    buff_filters["required_name_contains"] = _normalize_token_name(descriptor).upper()
                params.update(
                    {
                        "post_play_buff_owner_battle_target_policy": "all",
                        "post_play_buff_owner_battle_grant_keyword": " ".join(
                            part.capitalize() for part in str(m_token_then_buff_all.group(2) or "").replace("-", " ").split()
                        ),
                        "post_play_buff_owner_battle_keyword_duration": (
                            "opponent_turn" if "until the end of your opponent's" in branch.lower() else "turn"
                        ),
                        **{f"post_play_buff_owner_battle_{key}": value for key, value in buff_filters.items()},
                    }
                )
            m_token_then_combo = _TOKEN_THEN_COMBO_FROM_OWNER_ZONE_RE.search(branch)
            if m_token_then_combo:
                descriptor = str(m_token_then_combo.group(2) or "").strip().lower()
                m_combo_power = re.search(r"with (\d+) combo power", descriptor, re.IGNORECASE)
                combo_power = int(m_combo_power.group(1)) if m_combo_power else -1
                combo_descriptor = re.sub(r"with \d+ combo power", " ", descriptor, flags=re.IGNORECASE)
                params.update(
                    {
                        "combo_max_targets": int(m_token_then_combo.group(1)),
                        "combo_source_zone": str(m_token_then_combo.group(3) or "drop").strip().lower(),
                        **{
                            f"combo_{key}": value
                            for key, value in _descriptor_filters(combo_descriptor, branch).items()
                        },
                    }
                )
                if "mono-" in descriptor or "mono " in descriptor:
                    params["combo_require_mono_color"] = True
                if combo_power >= 0:
                    params["combo_exact_combo_power"] = combo_power
                if "with its skills negated for the turn" in branch.lower():
                    params["combo_negate_skills"] = True
            m_token_then_add_life = _TOKEN_THEN_ADD_FROM_OWNER_LIFE_TO_HAND_RE.search(branch)
            if m_token_then_add_life:
                params["add_from_life_to_hand_max_targets"] = int(m_token_then_add_life.group(1))
            if "switch this card to active mode" in branch.lower():
                params["switch_self_active"] = True
            trigger = "self_activate_battle" if str(m_activate_main_battle_immediate_token.group(1) or "").strip().lower() == "battle" else "self_activate_main"
            rules.append(
                EffectRule(
                    trigger=trigger,
                    handler_id="activate_play_token_in_battle",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _ACTIVATE_MAIN_BATTLE_PLAY_SELF_FROM_HAND_RE.search(branch):
            extra = _extract_common_conditions(branch)
            params = {**extra}
            if "rest mode" in branch:
                params["resting"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_play_self_from_hand",
                    handler_params=dict(params),
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _ACTIVATE_MAIN_BATTLE_PLAY_SELF_FROM_DROP_RE.search(branch):
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "required_source_zone": "drop",
                **extra,
            }
            if "rest mode" in branch:
                params["resting"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_play_self_from_hand",
                    handler_params=dict(params),
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_battle_play_self_from_hand = _ACTIVATE_BATTLE_PLAY_SELF_FROM_HAND_RE.search(branch)
        if m_activate_battle_play_self_from_hand:
            extra = _extract_common_conditions(branch)
            params = {**extra}
            discard_after_play = m_activate_battle_play_self_from_hand.group(1)
            if discard_after_play:
                params["opponent_discards_after_play"] = int(discard_after_play)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_play_self_from_hand",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _ACTIVATE_BATTLE_USE_SELF_FROM_DROP_IN_COMBO_RE.search(branch):
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "required_source_zone": "drop",
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_combo_self_from_owner_drop",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_battle_play_self_from_under_leader_bottom_deck = _ACTIVATE_BATTLE_PLAY_SELF_FROM_UNDER_LEADER_AND_BOTTOM_DECK_RE.search(branch)
        if m_activate_battle_play_self_from_under_leader_bottom_deck:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "required_source_zone": "leader_under",
                "bottom_deck_self_at_turn_end": True,
                **extra,
            }
            host_name = str(m_activate_battle_play_self_from_under_leader_bottom_deck.group(1) or "").strip()
            host_character = str(m_activate_battle_play_self_from_under_leader_bottom_deck.group(2) or "").strip()
            if host_name:
                params["under_host_name_contains"] = host_name.upper()
            if host_character:
                params["under_host_required_characters"] = host_character
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_play_self_from_under_owner_leader",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_play_from_under_self = _ACTIVATE_MAIN_BATTLE_PLAY_UP_TO_N_FROM_UNDER_SELF_AND_PLACE_SELF_UNDER_PLAYED_RE.search(branch)
        if m_activate_play_from_under_self:
            trigger = "self_activate_battle" if m_activate_play_from_under_self.group(1).lower() == "battle" else "self_activate_main"
            max_targets = int(m_activate_play_from_under_self.group(2))
            descriptor = m_activate_play_from_under_self.group(3).lower()
            m_cost_less = re.search(r"energy costs? of (\d+) or less", descriptor)
            if m_cost_less is None:
                m_cost_less = re.search(r"energy cost of (\d+) or less", descriptor)
            m_cost_exact = re.search(r"energy cost of (\d+)\b", descriptor)
            min_cost = int(m_cost_exact.group(1)) if (m_cost_exact and m_cost_less is None) else -1
            max_cost = int(m_cost_less.group(1)) if m_cost_less else (int(m_cost_exact.group(1)) if m_cost_exact else -1)
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "max_cost": max_cost,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if min_cost >= 0:
                params["min_cost"] = min_cost
            if "rest mode" in branch:
                params["resting"] = True
            if "with its skills negated" in branch or "with their skills negated" in branch:
                params["negate_skills"] = True
            rules.append(
                EffectRule(
                    trigger=trigger,
                    handler_id="activate_play_up_to_n_from_under_self_and_place_self_under_played_card",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _ACTIVATE_MAIN_PLAY_SELF_FROM_WARP_RE.search(branch):
            extra = _extract_common_conditions(branch)
            params = {
                "required_source_zone": "warp",
                **extra,
            }
            if "rest mode" in branch:
                params["resting"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_warp",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        if (
            _ACTIVATE_MAIN_SEND_SELF_TO_WARP_PLAY_SELF_NEXT_TURN_RE.search(branch)
            or _ACTIVATE_MAIN_SEND_SELF_TO_WARP_AND_PLAY_SELF_NEXT_TURN_RE.search(branch)
        ):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_schedule_play_cards_warped_by_source_skill",
                    handler_params={
                        "affected_player_scope": "owner",
                        "mark_source_in_owner_warp": True,
                        "trigger_kind": "main_phase_start",
                        "trigger_player_scope": "owner",
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _ACTIVATE_MAIN_SEND_SELF_FROM_HAND_TO_WARP_AND_PLAY_SELF_OPPONENT_NEXT_TURN_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_schedule_play_cards_warped_by_source_skill",
                    handler_params={
                        "affected_player_scope": "owner",
                        "mark_source_in_owner_warp": True,
                        "trigger_kind": "turn_end",
                        "trigger_player_scope": "opponent",
                        "require_next_turn": True,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_send_owner_hand_to_warp_and_play_next_turn = _ACTIVATE_MAIN_SEND_UP_TO_N_FROM_OWNER_HAND_TO_WARP_AND_PLAY_NEXT_TURN_RE.search(branch)
        if m_activate_main_send_owner_hand_to_warp_and_play_next_turn:
            max_targets = int(m_activate_main_send_owner_hand_to_warp_and_play_next_turn.group(1))
            descriptor = str(m_activate_main_send_owner_hand_to_warp_and_play_next_turn.group(2) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            send_params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            m_max_cost = re.search(r"energy cost of (\d+) or less", descriptor)
            if m_max_cost is not None:
                send_params["max_cost"] = int(m_max_cost.group(1))
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_send_up_to_n_from_owner_hand_to_warp",
                    handler_params=send_params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_schedule_play_cards_warped_by_source_skill",
                    handler_params={
                        "affected_player_scope": "owner",
                        "trigger_kind": "main_phase_start",
                        "trigger_player_scope": "owner",
                        "require_next_turn": True,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_send_self_to_warp_play_owner_hand_then_return = _ACTIVATE_MAIN_SEND_SELF_TO_WARP_PLAY_UP_TO_N_FROM_OWNER_HAND_THEN_RETURN_SELF_NEXT_TURN_RE.search(branch)
        if m_activate_main_send_self_to_warp_play_owner_hand_then_return:
            max_targets = int(m_activate_main_send_self_to_warp_play_owner_hand_then_return.group(1))
            descriptor = str(m_activate_main_send_self_to_warp_play_owner_hand_then_return.group(2) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            play_params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if "battle card" in descriptor:
                play_params["required_card_type"] = "BATTLE"
            if "multicolor" in descriptor or "multi-color" in descriptor:
                play_params["requires_multicolor"] = True
            m_exact_cost = re.search(r"energy cost of (\d+)\b", descriptor)
            if m_exact_cost is not None:
                play_params["allowed_costs"] = m_exact_cost.group(1)
                play_params["max_cost"] = int(m_exact_cost.group(1))
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_up_to_n_from_owner_hand",
                    handler_params=play_params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_schedule_return_cards_warped_by_source_skill_to_owner_hand",
                    handler_params={
                        "affected_player_scope": "owner",
                        "mark_source_in_owner_warp": True,
                        "trigger_kind": "main_phase_start",
                        "trigger_player_scope": "owner",
                        "require_next_turn": True,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_activate_named_field_extra = _ACTIVATE_MAIN_ACTIVATE_UP_TO_N_NAMED_FIELD_EXTRA_FROM_OWNER_DECK_RE.search(branch)
        if m_activate_main_activate_named_field_extra:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": int(m_activate_main_activate_named_field_extra.group(1)),
                "required_name_contains": str(m_activate_main_activate_named_field_extra.group(2) or "").strip().upper(),
                "required_card_type": "EXTRA",
                "requires_field_keyword": True,
                **extra,
            }
            if "negate this skill for the game" in branch.lower():
                params["negate_self_skill_for_game"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_activate_up_to_n_named_field_extra_from_owner_deck",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_activate_named_field_extra_from_drop = _ACTIVATE_MAIN_ACTIVATE_UP_TO_N_NAMED_FIELD_EXTRA_FROM_OWNER_DROP_RE.search(branch)
        if m_activate_main_activate_named_field_extra_from_drop:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_activate_up_to_n_named_field_extra_from_owner_drop",
                    handler_params={
                        "max_targets": int(m_activate_main_activate_named_field_extra_from_drop.group(1)),
                        "required_name_contains": str(m_activate_main_activate_named_field_extra_from_drop.group(2) or "").strip().upper(),
                        "required_card_type": "EXTRA",
                        "requires_field_keyword": True,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_play_self_from_warp = _ACTIVATE_MAIN_PLAY_SELF_FROM_WARP_WITH_MARKERS_RE.search(branch)
        if m_activate_main_play_self_from_warp:
            extra = _extract_common_conditions(branch)
            params = {
                "markers": int(m_activate_main_play_self_from_warp.group(1)),
                "required_source_zone": "warp",
                **extra,
            }
            if "rest mode" in branch:
                params["resting"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_play_self_from_warp",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_activate_main_play_self_from_hand_or_warp = _ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_OR_WARP_WITH_MARKERS_RE.search(branch)
        if m_activate_main_play_self_from_hand_or_warp:
            extra = _extract_common_conditions(branch)
            markers = int(m_activate_main_play_self_from_hand_or_warp.group(1))
            for handler_id, required_source_zone in (
                ("activate_play_self_from_hand", "hand"),
                ("activate_play_self_from_warp", "warp"),
            ):
                params = {
                    "markers": markers,
                    "required_source_zone": required_source_zone,
                    **extra,
                }
                if "rest mode" in branch:
                    params["resting"] = True
                rules.append(
                    EffectRule(
                        trigger="self_activate_main",
                        handler_id=handler_id,
                        handler_params=params,
                        once_per_turn=once,
                    )
                )

        m_activate_draw_play_self = _ACTIVATE_DRAW_PLAY_SELF_AND_GAIN_KEYWORD_UNTIL_OPP_TURN_END_RE.search(branch)
        if m_activate_draw_play_self:
            trigger = f"self_activate_{str(m_activate_draw_play_self.group(1) or '').strip().lower()}"
            amount = int(m_activate_draw_play_self.group(2))
            grant_keyword = " ".join(part.capitalize() for part in m_activate_draw_play_self.group(3).replace("-", " ").split())
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger=trigger,
                    handler_id="activate_draw_n_play_self_from_hand_and_gain_keyword_until_opponent_turn_end",
                    handler_params={"amount": amount, "grant_keyword": grant_keyword, **extra},
                    once_per_turn=once,
                )
            )

        m_activate_main_draw_life_bounce_schedule = _ACTIVATE_MAIN_DRAW_LIFE_BOUNCE_AND_OPTIONAL_MAIN_PHASE_ENERGY_SWITCH_RE.search(branch)
        if m_activate_main_draw_life_bounce_schedule:
            amount = int(m_activate_main_draw_life_bounce_schedule.group(1))
            life_to_hand_amount = int(m_activate_main_draw_life_bounce_schedule.group(2) or 0)
            max_targets = int(m_activate_main_draw_life_bounce_schedule.group(3))
            max_cost = int(m_activate_main_draw_life_bounce_schedule.group(4))
            schedule_max_targets = int(m_activate_main_draw_life_bounce_schedule.group(5) or 0)
            schedule_descriptor = str(m_activate_main_draw_life_bounce_schedule.group(6) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "amount": amount,
                "max_targets": max_targets,
                "max_cost": max_cost,
                "target_policy": "first",
                **extra,
            }
            if life_to_hand_amount > 0:
                params["life_to_hand_amount"] = life_to_hand_amount
            if schedule_max_targets > 0:
                params["schedule_main_phase_energy_max_targets"] = schedule_max_targets
                schedule_colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black|white)\b", schedule_descriptor)))
                if schedule_colors:
                    params["schedule_main_phase_energy_allowed_colors"] = ",".join(schedule_colors)
                if "multicolor" in schedule_descriptor:
                    params["schedule_main_phase_energy_requires_multicolor"] = True
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_draw_n_add_up_to_n_from_owner_life_to_hand_then_return_up_to_n_opponent_battle_to_hand_and_schedule_energy_switch",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_battle_draw_switch_self_active_and_power_reduce = _ACTIVATE_BATTLE_DRAW_SWITCH_SELF_ACTIVE_AND_POWER_REDUCE_RE.search(branch)
        if m_activate_battle_draw_switch_self_active_and_power_reduce:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_switch_self_active_and_power_reduce_up_to_n_opponent_battle_for_turn",
                    handler_params={
                        "amount": int(m_activate_battle_draw_switch_self_active_and_power_reduce.group(1)),
                        "max_targets": int(m_activate_battle_draw_switch_self_active_and_power_reduce.group(2)),
                        "power_delta": -int(m_activate_battle_draw_switch_self_active_and_power_reduce.group(3)),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_main_draw_keyword = _ACTIVATE_MAIN_DRAW_GAIN_KEYWORD_RE.search(branch)
        if m_activate_main_draw_keyword:
            amount = int(m_activate_main_draw_keyword.group(1))
            grant_keyword = m_activate_main_draw_keyword.group(2).strip().title()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_draw_n_and_gain_keyword_for_turn",
                    handler_params={"amount": amount, "grant_keyword": grant_keyword, **extra},
                    once_per_turn=once,
                )
            )

        m_activate_main_drop_hidden_draw = _ACTIVATE_MAIN_DROP_OWNER_HIDDEN_MODE_DRAW_RE.search(branch)
        if m_activate_main_drop_hidden_draw:
            amount = int(m_activate_main_drop_hidden_draw.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_drop_owner_hidden_mode_draw_n",
                    handler_params={"amount": amount, **extra},
                    once_per_turn=once,
                )
            )

        m_activate_main_switch_hidden = _ACTIVATE_MAIN_SWITCH_OWNER_BATTLE_TO_HIDDEN_RE.search(branch)
        if m_activate_main_switch_hidden:
            descriptor = m_activate_main_switch_hidden.group(1).strip().lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_switch_owner_battle_to_hidden_mode",
                    handler_params={**_descriptor_filters(descriptor, branch), **extra},
                    once_per_turn=once,
                )
            )

        if _ACTIVATE_MAIN_SWITCH_SELF_TO_HIDDEN_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_switch_self_to_hidden_mode",
                    handler_params={**extra},
                    once_per_turn=once,
                )
            )

        m_activate_main_self_gain_hidden_power = _ACTIVATE_MAIN_SELF_GAIN_HIDDEN_COST_TARGET_FRONT_POWER_RE.search(branch)
        if m_activate_main_self_gain_hidden_power:
            descriptor = m_activate_main_self_gain_hidden_power.group(1).strip().lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_gain_power_by_hidden_cost_target_original_power_for_turn",
                    handler_params={"target_scope": "self", **_descriptor_filters(descriptor, branch), **extra},
                    once_per_turn=once,
                )
            )

        m_activate_main_owner_target_gain_hidden_power = _ACTIVATE_MAIN_OWNER_TARGET_GAIN_HIDDEN_COST_TARGET_FRONT_POWER_RE.search(branch)
        if m_activate_main_owner_target_gain_hidden_power:
            cost_descriptor = m_activate_main_owner_target_gain_hidden_power.group(1).strip().lower()
            target_descriptor = m_activate_main_owner_target_gain_hidden_power.group(2).strip().lower()
            extra = _extract_common_conditions(branch)
            target_params = {
                f"target_{k}": v
                for k, v in _descriptor_filters(target_descriptor, branch).items()
            }
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_gain_power_by_hidden_cost_target_original_power_for_turn",
                    handler_params={
                        "target_scope": "owner_leader_or_matching_battle",
                        **_descriptor_filters(cost_descriptor, branch),
                        **target_params,
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_main_send_warp = _ACTIVATE_MAIN_SEND_UP_TO_N_OPP_BATTLE_TO_WARP_RE.search(branch)
        if m_activate_main_send_warp:
            max_targets = int(m_activate_main_send_warp.group(1))
            extra = _extract_common_conditions(branch)
            activate_params: dict[str, int | str | bool] = {"max_targets": max_targets, "target_policy": "first", **extra}
            if "with an energy cost greater than their current energy" in branch.lower():
                activate_params["requires_cost_greater_than_opponent_current_energy"] = True
            has_next_opponent_turn_replay = _PLAY_CARD_SENT_TO_WARP_BY_SOURCE_SKILL_LATER_RE.search(branch) is not None
            has_turn_end_replay = _PLAY_ALL_WARPED_BY_SOURCE_SKILL_LATER_RE.search(branch) is not None
            if is_extra and (has_next_opponent_turn_replay or has_turn_end_replay):
                composite_params = {
                    **activate_params,
                    "send_max_targets": max_targets,
                    "affected_player_scope": "opponent",
                    "trigger_kind": "turn_end",
                    "trigger_player_scope": "opponent" if has_next_opponent_turn_replay else "current",
                    "resting": "rest mode" in branch.lower(),
                }
                if "skills negated for the turn" in branch.lower():
                    composite_params["negate_skills"] = True
                if has_turn_end_replay:
                    composite_params["max_targets"] = -1
                    composite_params["require_next_turn"] = False
                m_drop_instead = re.search(
                    r"if your opponent has (\d+) or fewer cards in their deck,\s*place them in their owners'? drop areas? instead",
                    branch,
                    re.IGNORECASE,
                )
                if m_drop_instead:
                    composite_params["drop_instead_if_affected_deck_at_most"] = int(m_drop_instead.group(1))
                rules.append(
                    EffectRule(
                        trigger="self_activate_extra_from_hand",
                        handler_id="activate_send_up_to_n_opponent_battle_to_warp_and_schedule_play_warped_cards_later",
                        handler_params=composite_params,
                        once_per_turn=once,
                    )
                )
                continue
            activate_triggers = (
                ("self_activate_extra_from_hand",)
                if is_extra
                else ("self_activate_main", "self_activate_battle")
                if "[activate: main/battle]" in branch.lower() or "[activate main/battle]" in branch.lower()
                else ("self_activate_main",)
            )
            for trigger in activate_triggers:
                rules.append(
                    EffectRule(
                        trigger=trigger,
                        handler_id="activate_send_up_to_n_opponent_battle_to_warp",
                        handler_params=dict(activate_params),
                        once_per_turn=once,
                    )
                )
            if has_next_opponent_turn_replay or has_turn_end_replay:
                schedule_params: dict[str, int | str | bool] = {
                    "affected_player_scope": "opponent",
                    "trigger_kind": "turn_end",
                    "trigger_player_scope": "opponent" if has_next_opponent_turn_replay else "current",
                    "resting": "rest mode" in branch.lower(),
                    **extra,
                }
                if "skills negated for the turn" in branch.lower():
                    schedule_params["negate_skills"] = True
                if has_turn_end_replay:
                    schedule_params["max_targets"] = -1
                    schedule_params["require_next_turn"] = False
                m_drop_instead = re.search(
                    r"if your opponent has (\d+) or fewer cards in their deck,\s*place them in their owners'? drop areas? instead",
                    branch,
                    re.IGNORECASE,
                )
                if m_drop_instead:
                    schedule_params["drop_instead_if_affected_deck_at_most"] = int(m_drop_instead.group(1))
                for trigger in activate_triggers:
                    rules.append(
                        EffectRule(
                            trigger=trigger,
                            handler_id="activate_schedule_play_cards_warped_by_source_skill",
                            handler_params=dict(schedule_params),
                            once_per_turn=once,
                        )
                    )

        m_counter_send_warp = _COUNTER_ATTACK_SEND_UP_TO_N_ATTACKING_BATTLE_TO_WARP_RE.search(branch)
        if m_counter_send_warp:
            max_targets = int(m_counter_send_warp.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="counter_attack",
                    handler_id="counter_send_up_to_n_attacking_battle_to_warp",
                    handler_params={"max_targets": max_targets, **extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            if _COUNTER_PLAY_CARD_SENT_TO_WARP_BY_SOURCE_SKILL_LATER_RE.search(branch):
                rules.append(
                    EffectRule(
                        trigger="counter_attack",
                        handler_id="counter_schedule_play_cards_warped_by_source_skill",
                        handler_params={
                            "affected_player_scope": "opponent",
                            "trigger_kind": "turn_end",
                            "trigger_player_scope": "opponent",
                            "require_next_turn": False,
                            "resting": "rest mode" in branch.lower(),
                            **extra,
                        },
                        once_per_turn=once,
                        limit_per_turn=limit,
                    )
                )

        m_counter_delayed_token = _COUNTER_DELAYED_TOKEN_RE.search(branch)
        if m_counter_delayed_token:
            extra = _extract_common_conditions(branch)
            switch_energy_match = re.search(
                r"switch up to (\d+) of your ([a-z/|,\s-]+?) energy to active mode",
                branch,
                re.IGNORECASE,
            )
            handler_params: dict[str, object] = {
                "amount": int(m_counter_delayed_token.group(1)),
                "token_name": str(m_counter_delayed_token.group(2) or "Token").strip(),
                "power": int(m_counter_delayed_token.group(3) or 0),
                "trigger_kind": "turn_end",
                "trigger_player_scope": "current",
                "require_next_turn": False,
                "controller_player_scope": "opponent" if m_counter_delayed_token.group(4) else "owner",
                **extra,
            }
            if switch_energy_match:
                handler_params["switch_owner_energy_active_max_targets"] = int(switch_energy_match.group(1))
                handler_params["switch_owner_energy_active_allowed_colors"] = switch_energy_match.group(2).strip().lower()
            rules.append(
                EffectRule(
                    trigger="counter_attack",
                    handler_id="counter_schedule_play_token_in_battle",
                    handler_params=handler_params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_counter_immediate_token = _COUNTER_IMMEDIATE_TOKEN_RE.search(branch)
        if m_counter_immediate_token:
            fallback_stats = re.search(
                r"\([^)]*?(\d+)\s+power,\s*(\d+)\s+combo cost,\s*(?:and\s*)?(\d+)\s+combo power[^)]*\)",
                branch,
                re.IGNORECASE,
            )
            combo_cost = int(m_counter_immediate_token.group(4) or (fallback_stats.group(2) if fallback_stats else 0) or 0)
            combo_power = int(m_counter_immediate_token.group(5) or (fallback_stats.group(3) if fallback_stats else 0) or 0)
            explicit_power = m_counter_immediate_token.group(3) or m_counter_immediate_token.group(6) or (fallback_stats.group(1) if fallback_stats else 0) or 0
            params: dict[str, int | str | bool] = {
                "amount": int(m_counter_immediate_token.group(1)),
                "token_name": _normalize_token_name(m_counter_immediate_token.group(2)),
                "power": int(explicit_power or 0),
                "combo_cost": combo_cost,
                "combo_power": combo_power,
                "resting": "in rest mode" in branch.lower(),
                **_extract_common_conditions(branch),
            }
            granted_keyword = str(m_counter_immediate_token.group(7) or "").strip()
            if not granted_keyword:
                m_token_gain_keywords = _TOKEN_GAIN_KEYWORDS_RE.search(branch)
                granted_keyword = str(m_token_gain_keywords.group(1) or "").strip() if m_token_gain_keywords else ""
            if granted_keyword:
                params["temporary_keywords"] = _normalize_extracted_keywords(granted_keyword)
                params["keyword_duration"] = (
                    "opponent_turn" if "until the end of your opponent's next turn" in branch.lower() else "turn"
                )
            if "opponent's battle area" in branch.lower():
                params["controller_player_scope"] = "opponent"
            rules.append(
                EffectRule(
                    trigger="counter_attack",
                    handler_id="counter_play_token_in_battle",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_counter_draw_send_each = _COUNTER_ATTACK_DRAW_AND_SEND_UP_TO_ONE_EACH_FROM_ALL_BATTLES_TO_WARP_RE.search(branch)
        if m_counter_draw_send_each:
            amount = int(m_counter_draw_send_each.group(1))
            first_descriptor = str(m_counter_draw_send_each.group(2) or "").strip().lower()
            second_descriptor = str(m_counter_draw_send_each.group(3) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            first_filters = _descriptor_filters(first_descriptor, branch)
            second_filters = _descriptor_filters(second_descriptor, branch)
            rules.append(
                EffectRule(
                    trigger="counter_attack",
                    handler_id="counter_draw_n_and_send_up_to_one_each_matching_from_all_battles_to_warp",
                    handler_params={
                        "amount": amount,
                        **{f"first_{k}": v for k, v in first_filters.items()},
                        **{f"second_{k}": v for k, v in second_filters.items()},
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            if _COUNTER_PLAY_ALL_WARPED_BY_SOURCE_SKILL_LATER_RE.search(branch):
                rules.append(
                    EffectRule(
                        trigger="counter_attack",
                        handler_id="counter_schedule_play_cards_warped_by_source_skill",
                        handler_params={
                            "affected_player_scope": "both",
                            "trigger_kind": "turn_end",
                            "trigger_player_scope": "opponent",
                            "require_next_turn": False,
                            "negate_skills": True,
                            "max_targets": -1,
                            **extra,
                        },
                        once_per_turn=once,
                        limit_per_turn=limit,
                    )
                )

        m_activate_main_send_drop_warp = _ACTIVATE_MAIN_SEND_UP_TO_N_OPP_DROP_BATTLE_TO_WARP_RE.search(branch)
        if m_activate_main_send_drop_warp:
            max_targets = int(m_activate_main_send_drop_warp.group(1))
            extra = _extract_common_conditions(branch)
            marker_delta = _extract_unison_marker_delta(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "target_policy": "first",
                **extra,
            }
            if marker_delta is not None:
                params["marker_delta"] = marker_delta
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_send_up_to_n_opponent_drop_battle_to_warp",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_activate_main_search_warp = _ACTIVATE_MAIN_LOOK_TOP_SEND_TO_OWNER_WARP_RE.search(branch)
        if m_activate_main_search_warp is None:
            m_activate_main_search_warp = _ACTIVATE_MAIN_LOOK_TOP_SEND_DIRECT_TO_OWNER_WARP_RE.search(branch)
        if m_activate_main_search_warp:
            look_count = int(m_activate_main_search_warp.group(1))
            max_send = int(m_activate_main_search_warp.group(2))
            descriptor = m_activate_main_search_warp.group(3).lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_look_top_send_up_to_n_to_owner_warp",
                    handler_params={
                        "look_count": look_count,
                        "max_send": max_send,
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_main_topdeck_warp = _ACTIVATE_MAIN_SEND_TOP_DECK_TO_OWNER_WARP_RE.search(branch)
        if m_activate_main_topdeck_warp:
            send_count = int(m_activate_main_topdeck_warp.group(1))
            extra = _extract_common_conditions(branch)
            marker_delta = _extract_unison_marker_delta(branch)
            params: dict[str, int | str | bool] = {
                "send_count": send_count,
                "switch_self_active": "switch this card to active mode" in branch,
                **extra,
            }
            if marker_delta is not None:
                params["marker_delta"] = marker_delta
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_send_top_deck_to_owner_warp",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_activate_main_warp_to_hand = _ACTIVATE_MAIN_ADD_UP_TO_N_FROM_OWNER_WARP_TO_HAND_RE.search(branch)
        if m_activate_main_warp_to_hand:
            max_add = int(m_activate_main_warp_to_hand.group(1))
            descriptor = m_activate_main_warp_to_hand.group(2).strip().lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_add_up_to_n_from_owner_warp_to_hand",
                    handler_params={
                        "max_add": max_add,
                        "required_source_zone": "unison",
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_activate_main_send_self_to_warp_opponent_choose_battle_ko_if_not_trait = _ACTIVATE_MAIN_SEND_SELF_TO_WARP_OPPONENT_CHOOSE_BATTLE_KO_IF_NOT_TRAIT_RE.search(branch)
        if m_activate_main_send_self_to_warp_opponent_choose_battle_ko_if_not_trait:
            excluded_trait = str(m_activate_main_send_self_to_warp_opponent_choose_battle_ko_if_not_trait.group(1) or "").strip().title()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_send_self_to_warp_then_opponent_choose_battle_ko_if_not_trait",
                    handler_params={
                        "excluded_trait": excluded_trait,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_activate_main_ko_and_buff_leader = _ACTIVATE_MAIN_KO_OPP_BATTLE_AND_BUFF_OWNER_LEADER_RE.search(branch)
        if m_activate_main_ko_and_buff_leader:
            extra = _extract_common_conditions(branch)
            leader_descriptor = m_activate_main_ko_and_buff_leader.group(2).strip().lower()
            power_delta = int(m_activate_main_ko_and_buff_leader.group(3))
            params = {
                "max_targets": 1,
                "leader_power_delta": power_delta,
                "target_policy": "first",
                **extra,
            }
            if "white" in leader_descriptor:
                params["requires_leader"] = "if your leader is white"
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_ko_up_to_n_opponent_battle_and_buff_owner_leader_for_turn",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_activate_main_buff_owner_leader = _ACTIVATE_MAIN_BUFF_OWNER_LEADER_RE.search(branch)
        m_activate_main_buff_owner_leader_and_restrict_attack = _ACTIVATE_MAIN_BUFF_OWNER_LEADER_AND_RESTRICT_MATCHING_OPP_ATTACK_RE.search(branch)
        if m_activate_main_buff_owner_leader_and_restrict_attack:
            leader_descriptor = m_activate_main_buff_owner_leader_and_restrict_attack.group(1).strip().lower()
            power_delta = int(m_activate_main_buff_owner_leader_and_restrict_attack.group(2))
            restricted_descriptor = m_activate_main_buff_owner_leader_and_restrict_attack.group(3).strip().lower()
            extra = _extract_common_conditions(branch)
            params = {
                "leader_power_delta": power_delta,
                "schedule_attack_restriction_name_contains": str(restricted_descriptor).replace(" tokens", " token").upper(),
                **extra,
            }
            if "mono-blue" in leader_descriptor or ("blue" in leader_descriptor and "mono" in leader_descriptor):
                params["leader_allowed_colors"] = "blue"
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_buff_owner_leader_for_turn",
                    handler_params=params,
                    once_per_turn=once,
                )
            )
        elif m_activate_main_buff_owner_leader:
            extra = _extract_common_conditions(branch)
            power_delta = int(m_activate_main_buff_owner_leader.group(1))
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_buff_owner_leader_for_turn",
                    handler_params={
                        "leader_power_delta": power_delta,
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        if _ACTIVATE_MAIN_SWITCH_OWNER_BOARD_TO_REVEALED_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_switch_owner_board_to_revealed_mode",
                    handler_params={**extra},
                    once_per_turn=once,
                )
            )

        m_activate_main_switch_all_opp_revealed_then_ko = _ACTIVATE_MAIN_SWITCH_ALL_OPP_BATTLE_TO_REVEALED_THEN_KO_RE.search(branch)
        if m_activate_main_switch_all_opp_revealed_then_ko:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_switch_all_opponent_battle_to_revealed_then_ko_up_to_n",
                    handler_params={
                        "max_targets": int(m_activate_main_switch_all_opp_revealed_then_ko.group(1)),
                        "target_policy": "first",
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_attack_hidden_then_reveal = _ATTACK_SWITCH_UP_TO_N_OPP_BATTLE_HIDDEN_THEN_REVEAL_OPP_TURN_END_RE.search(branch)
        if m_attack_hidden_then_reveal:
            max_targets = int(m_attack_hidden_then_reveal.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_switch_up_to_n_opponent_battle_to_hidden_then_reveal_on_opponent_turn_end",
                    handler_params={"max_targets": max_targets, **extra},
                    once_per_turn=once,
                )
            )

        m_play_hidden_then_reveal_turn_end = _PLAY_SWITCH_UP_TO_N_OPP_BATTLE_HIDDEN_THEN_REVEAL_TURN_END_RE.search(branch)
        if m_play_hidden_then_reveal_turn_end:
            max_targets = int(m_play_hidden_then_reveal_turn_end.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_switch_up_to_n_opponent_battle_to_hidden_then_reveal_on_turn_end",
                    handler_params={"max_targets": max_targets, **extra},
                    once_per_turn=once,
                )
            )

        m_play_owner_revealed = _PLAY_SWITCH_UP_TO_N_OWNER_BOARD_TO_REVEALED_RE.search(branch)
        if m_play_owner_revealed:
            max_targets = int(m_play_owner_revealed.group(1))
            descriptor = (m_play_owner_revealed.group(2) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_switch_up_to_n_owner_board_to_revealed_on_play",
                    handler_params={"max_targets": max_targets, **_descriptor_filters(descriptor, branch), **extra},
                    once_per_turn=once,
                )
            )

        m_play_any_player_revealed = _PLAY_SWITCH_UP_TO_N_ANY_PLAYER_BOARD_TO_REVEALED_RE.search(branch)
        if m_play_any_player_revealed:
            max_targets = int(m_play_any_player_revealed.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_switch_up_to_n_any_player_board_to_revealed_on_play",
                    handler_params={"max_targets": max_targets, **extra},
                    once_per_turn=once,
                )
            )

        m_play_owner_hidden = _PLAY_SWITCH_UP_TO_N_OWNER_BATTLE_TO_HIDDEN_RE.search(branch)
        if m_play_owner_hidden:
            max_targets = int(m_play_owner_hidden.group(1))
            descriptor = (m_play_owner_hidden.group(2) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_switch_up_to_n_owner_battle_to_hidden_on_play",
                    handler_params={"max_targets": max_targets, **_descriptor_filters(descriptor, branch), **extra},
                    once_per_turn=once,
                )
            )

        m_play_owner_buff_keyword = _PLAY_BUFF_UP_TO_N_OWNER_BATTLE_WITH_MIN_CHAR_NAMES_GAIN_KEYWORD_UNTIL_OPP_TURN_END_RE.search(branch)
        if m_play_owner_buff_keyword:
            max_targets = int(m_play_owner_buff_keyword.group(1))
            min_character_count = int(m_play_owner_buff_keyword.group(2))
            required_character = str(m_play_owner_buff_keyword.group(3) or "").strip().title()
            grant_keyword = " ".join(part.capitalize() for part in m_play_owner_buff_keyword.group(4).replace("-", " ").split())
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_buff_up_to_n_owner_battles_on_play",
                    handler_params={
                        "max_targets": max_targets,
                        "min_character_count": min_character_count,
                        "required_characters": required_character,
                        "grant_keyword": grant_keyword,
                        "keyword_duration": "opponent_turn",
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_draw_self_hidden = _PLAY_DRAW_AND_SWITCH_SELF_TO_HIDDEN_RE.search(branch)
        if m_play_draw_self_hidden:
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_switch_self_to_hidden_on_play",
                    handler_params={},
                    once_per_turn=once,
                )
            )

        m_hidden_leader_buff = _SWITCHED_TO_HIDDEN_OWNER_LEADER_GAIN_POWER_UNTIL_OPP_TURN_END_RE.search(branch)
        if m_hidden_leader_buff:
            power_delta = int(m_hidden_leader_buff.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_switched_hidden",
                    handler_id="auto_buff_owner_leader_on_switch_until_opponent_turn_end",
                    handler_params={"power_delta": power_delta, "requires_owner_actor": True, **extra},
                    once_per_turn=once,
                )
            )

        m_hidden_owner_keyword = _SWITCHED_TO_HIDDEN_OWNER_CARD_GAIN_KEYWORD_UNTIL_OPP_TURN_END_RE.search(branch)
        if m_hidden_owner_keyword:
            max_targets = int(m_hidden_owner_keyword.group(1))
            descriptor = m_hidden_owner_keyword.group(2).strip().lower()
            grant_keyword = " ".join(part.capitalize() for part in m_hidden_owner_keyword.group(3).replace("-", " ").split())
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_switched_hidden",
                    handler_id="auto_buff_up_to_n_owner_cards_on_switch",
                    handler_params={
                        "max_targets": max_targets,
                        "grant_keyword": grant_keyword,
                        "keyword_duration": "opponent_turn",
                        "requires_owner_actor": True,
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_revealed_self_buff = _SWITCHED_TO_REVEALED_SELF_GAIN_POWER_AND_KEYWORD_RE.search(branch)
        if m_revealed_self_buff:
            power_delta = int(m_revealed_self_buff.group(1))
            grant_keyword = " ".join(part.capitalize() for part in m_revealed_self_buff.group(2).replace("-", " ").split())
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_switched_revealed",
                    handler_id="auto_self_gain_power_and_keyword_for_turn_on_switch",
                    handler_params={"power_delta": power_delta, "grant_keyword": grant_keyword, **extra},
                    once_per_turn=once,
                )
            )

        m_switch_owner_power = _SWITCHED_TO_REVEALED_OR_HIDDEN_OWNER_CARD_GAIN_POWER_RE.search(branch)
        switch_triggers = ("self_switched_revealed", "self_switched_hidden") if m_switch_owner_power else ()
        if not m_switch_owner_power:
            m_switch_owner_power = _SWITCHED_TO_REVEALED_OWNER_CARD_GAIN_POWER_RE.search(branch)
            if m_switch_owner_power:
                switch_triggers = ("self_switched_revealed",)
        if m_switch_owner_power:
            max_targets = int(m_switch_owner_power.group(1))
            descriptor = m_switch_owner_power.group(2).strip().lower()
            power_delta = int(m_switch_owner_power.group(3))
            extra = _extract_common_conditions(branch)
            for trigger in switch_triggers:
                rules.append(
                    EffectRule(
                        trigger=trigger,
                        handler_id="auto_buff_up_to_n_owner_cards_on_switch",
                        handler_params={
                            "max_targets": max_targets,
                            "power_delta": power_delta,
                            **_descriptor_filters(descriptor, branch),
                            **extra,
                        },
                        once_per_turn=once,
                    )
                )

        m_revealed_owner_keyword = _SWITCHED_TO_REVEALED_OWNER_CARD_GAIN_KEYWORD_RE.search(branch)
        if m_revealed_owner_keyword:
            max_targets = int(m_revealed_owner_keyword.group(1))
            descriptor = m_revealed_owner_keyword.group(2).strip().lower()
            grant_keyword = " ".join(part.capitalize() for part in m_revealed_owner_keyword.group(3).replace("-", " ").split())
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_switched_revealed",
                    handler_id="auto_buff_up_to_n_owner_cards_on_switch",
                    handler_params={
                        "max_targets": max_targets,
                        "grant_keyword": grant_keyword,
                        "keyword_duration": "turn",
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_switch_ko = _SWITCHED_TO_REVEALED_OR_HIDDEN_KO_OPP_BATTLE_RE.search(branch)
        if m_switch_ko:
            max_targets = int(m_switch_ko.group(1))
            extra = _extract_common_conditions(branch)
            for trigger in ("self_switched_revealed", "self_switched_hidden"):
                rules.append(
                    EffectRule(
                        trigger=trigger,
                        handler_id="auto_ko_up_to_n_opponent_battle_on_switch",
                        handler_params={"max_targets": max_targets, "target_policy": "first", **extra},
                        once_per_turn=once,
                    )
                )

        m_hidden_drop_owner_power = _HIDDEN_BATTLE_TO_DROP_OWNER_CARD_GAIN_POWER_RE.search(branch)
        if m_hidden_drop_owner_power:
            max_targets = int(m_hidden_drop_owner_power.group(1))
            descriptor = m_hidden_drop_owner_power.group(2).strip().lower()
            power_delta = int(m_hidden_drop_owner_power.group(3))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_hidden_battle_to_drop",
                    handler_id="auto_buff_up_to_n_owner_cards_on_hidden_drop",
                    handler_params={
                        "max_targets": max_targets,
                        "power_delta": power_delta,
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
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

        m_play_add_top_deck_to_energy_and_bottom_deck_opp_battle = _PLAY_ADD_TOP_DECK_TO_ENERGY_AND_BOTTOM_DECK_OPP_BATTLE_RE.search(branch)
        if m_play_add_top_deck_to_energy_and_bottom_deck_opp_battle:
            extra = _extract_common_conditions(branch)
            extra.pop("rest_mode_only", None)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_add_top_deck_to_energy_rest_and_bottom_deck_up_to_n_opponent_battle_on_play",
                    handler_params={
                        "max_targets": int(m_play_add_top_deck_to_energy_and_bottom_deck_opp_battle.group(1)),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is played... add the top card of your deck to your energy in Rest Mode.
        if _PLAY_ADD_TOP_DECK_TO_ENERGY_RE.search(branch) and m_play_add_top_deck_to_energy_and_bottom_deck_opp_battle is None:
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

        m_turn_end_place_under_leader = _TURN_END_PLACE_UP_TO_N_FROM_OWNER_DROP_UNDER_OWNER_LEADER_RE.search(branch)
        if m_turn_end_place_under_leader:
            max_targets = int(m_turn_end_place_under_leader.group(1))
            descriptor = str(m_turn_end_place_under_leader.group(2) or "").lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="turn_end",
                    handler_id="auto_place_up_to_n_from_owner_drop_under_owner_leader_on_turn_end",
                    handler_params={
                        "max_targets": max_targets,
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_turn_end_place_self_from_under_leader_on_top = _TURN_END_PLACE_SELF_FROM_UNDER_OWNER_LEADER_ON_TOP_OF_OWNER_LEADER_RE.search(branch)
        if m_turn_end_place_self_from_under_leader_on_top:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "required_source_zone": "leader_under",
                **_extract_under_leader_promotion_requirements(branch),
                **extra,
            }
            if str(m_turn_end_place_self_from_under_leader_on_top.group(2) or "").strip().lower() == "z-leader":
                params["under_host_required_card_type"] = "Z-LEADER"
            rules.append(
                EffectRule(
                    trigger=(
                        "opponent_turn_end"
                        if str(m_turn_end_place_self_from_under_leader_on_top.group(1) or "").strip().lower()
                        else "turn_end"
                    ),
                    handler_id="auto_place_self_from_under_owner_leader_on_top_of_owner_leader_on_turn_end",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        if _TURN_END_PLACE_SELF_FROM_OWNER_ENERGY_INTO_DROP_AFTER_LIFE_REVEAL_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="turn_end",
                    handler_id="auto_send_self_from_owner_energy_to_drop_on_turn_end_if_replaced_from_life",
                    handler_params={**extra},
                    source_text=branch,
                    once_per_turn=once,
                )
            )

        # [Auto] When a player places a [Field] Extra in battle area... switch up to N of your energy to Active.
        m_field_place_energy = _FIELD_EXTRA_PLACED_SWITCH_UP_TO_N_ENERGY_ACTIVE_RE.search(branch)
        if m_field_place_energy:
            max_targets = int(m_field_place_energy.group(1))
            descriptor = (m_field_place_energy.group(2) or "").lower()
            colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black)\b", descriptor)))
            requires_multicolor = "multicolor" in descriptor
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {"max_targets": max_targets, **extra}
            if colors:
                params["allowed_colors"] = ",".join(colors)
            if requires_multicolor:
                params["requires_multicolor"] = True
            rules.append(
                EffectRule(
                    trigger="owner_field_extra_placed",
                    handler_id="auto_switch_up_to_n_owner_energy_active_on_field_extra_placed",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_field_place_leader_buff = _FIELD_EXTRA_PLACED_BUFF_OWNER_LEADER_RE.search(branch)
        if m_field_place_leader_buff:
            leader_descriptor = str(m_field_place_leader_buff.group(1) or "").strip().lower()
            power_delta = int(m_field_place_leader_buff.group(2))
            leader_filters = _descriptor_filters(leader_descriptor, branch)
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "leader_power_delta": power_delta,
                **extra,
            }
            for key, value in leader_filters.items():
                if key in {"allowed_colors", "required_traits", "required_characters", "required_name_contains"}:
                    params[f"leader_{key}"] = value
            rules.append(
                EffectRule(
                    trigger="self_field_extra_placed",
                    handler_id="auto_buff_owner_leader_for_turn_on_field_extra_placed",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        # [Auto] Switch this card to Rest: when opponent skill-plays over-cost battle, reduce that battle's power.
        m_opp_overcost_reduce = _OPP_SKILL_PLAYS_OVERCOST_BATTLE_REDUCE_RE.search(branch)
        if m_opp_overcost_reduce:
            amount = int(m_opp_overcost_reduce.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_opponent_skill_plays_overcost_battle",
                    handler_id="auto_rest_self_on_owner_opponent_skill_play_overcost_battle_reduce_power",
                    handler_params={"power_delta": -abs(amount), **extra},
                    once_per_turn=once,
                )
            )

        # [Auto] Switch this card to Rest: when opponent skill-plays over-cost battle, switch that battle to Rest.
        if _OPP_SKILL_PLAYS_OVERCOST_BATTLE_SWITCH_REST_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_opponent_skill_plays_overcost_battle",
                    handler_id="auto_rest_self_on_owner_opponent_skill_play_overcost_battle_switch_target_rest",
                    handler_params={**extra},
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

        # [Auto] When this card is removed by skill or KO'd... add N card(s) from life to hand.
        m_add_life = _SELF_REMOVED_OR_KO_ADD_LIFE_RE.search(branch)
        if m_add_life:
            amount = int(m_add_life.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_koed",
                    handler_id="auto_add_n_life_to_hand_on_self_ko",
                    handler_params={"amount": amount, **extra},
                    once_per_turn=once,
                )
            )

        m_play_named_from_drop_on_self_ko = _SELF_REMOVED_OR_KO_PLAY_UP_TO_N_NAMED_FROM_DROP_RE.search(branch)
        if m_play_named_from_drop_on_self_ko:
            max_targets = int(m_play_named_from_drop_on_self_ko.group(1))
            required_name = str(m_play_named_from_drop_on_self_ko.group(2) or "").strip().upper()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_koed",
                    handler_id="auto_play_up_to_n_named_from_owner_drop_on_self_ko",
                    handler_params={
                        "max_targets": max_targets,
                        "required_name_contains": required_name,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        # [Auto] When this card is played... play up to N {...} from your deck with marker(s).
        m_play_from_deck_markers = _PLAY_FROM_DECK_WITH_MARKERS_RE.search(branch)
        if m_play_from_deck_markers:
            max_targets = int(m_play_from_deck_markers.group(1))
            descriptor = m_play_from_deck_markers.group(2).strip()
            descriptor_lc = descriptor.lower()
            raw_markers = m_play_from_deck_markers.group(3)
            markers = int(raw_markers) if raw_markers and raw_markers.isdigit() else 1
            rest_mode = "in rest mode" in branch.lower()
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "markers": markers,
                **extra,
            }
            named_targets = [part.strip() for part in re.findall(r"\{([^}]+)\}", descriptor) if part.strip()]
            if named_targets:
                params["required_name_contains"] = named_targets[0].upper()
            else:
                for key, value in _descriptor_filters(descriptor_lc, branch).items():
                    if key in {
                        "allowed_colors",
                        "required_traits",
                        "required_characters",
                        "required_name_contains",
                        "required_card_type",
                        "max_cost",
                    }:
                        params[key] = value
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

        # [Auto] When this card is played from your hand... choose up to N ... from your deck, play it.
        m_play_from_deck = _PLAY_FROM_HAND_PLAY_FROM_DECK_RE.search(branch)
        if m_play_from_deck and not m_play_from_deck_markers:
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

        m_gain_battle = _PLAY_GAIN_CONTROL_OPP_BATTLE_RE.search(branch)
        if m_gain_battle:
            max_targets = int(m_gain_battle.group(1))
            max_cost = int(m_gain_battle.group(2))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_gain_control_opponent_battle_on_play",
                    handler_params={"max_targets": max_targets, "max_cost": max_cost, "target_policy": "first", **extra},
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is played from hand... choose up to N {...} in your hand and play with marker(s).
        m_play_hand_markers = _PLAY_FROM_HAND_PLAY_FROM_HAND_WITH_MARKERS_RE.search(branch)
        if m_play_hand_markers:
            max_targets = int(m_play_hand_markers.group(1))
            descriptor = m_play_hand_markers.group(2).lower()
            raw_markers = m_play_hand_markers.group(3)
            markers = int(raw_markers) if raw_markers and raw_markers.isdigit() else 1
            m_cost = re.search(r"energy cost of (\d+) or less", descriptor)
            if m_cost is None:
                m_cost = re.search(r"energy cost of (\d+) or less", branch)
            max_cost = int(m_cost.group(1)) if m_cost else -1
            colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black)\b", descriptor)))
            required_card_type = ""
            if "z-battle card" in descriptor or "z battle card" in descriptor:
                required_card_type = "Z-BATTLE"
            elif "z-unison card" in descriptor or "z unison card" in descriptor:
                required_card_type = "Z-UNISON"
            elif "unison card" in descriptor:
                required_card_type = "UNISON"
            elif "battle card" in descriptor:
                required_card_type = "BATTLE"
            rest_mode = "in rest mode" in branch
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "markers": markers,
                "source_pool": "hand",
                "requires_played_from": "hand",
                "max_cost": max_cost,
                **extra,
            }
            if colors:
                params["allowed_colors"] = ",".join(colors)
            if required_card_type:
                params["required_card_type"] = required_card_type
            if rest_mode:
                params["rest_mode"] = True
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is played from hand... choose up to N {...} from your hand or deck, play with M markers.
        m_play_hand_or_deck_markers = _PLAY_FROM_HAND_PLAY_FROM_HAND_OR_DECK_WITH_MARKERS_RE.search(branch)
        if m_play_hand_or_deck_markers:
            max_targets = int(m_play_hand_or_deck_markers.group(1))
            descriptor = m_play_hand_or_deck_markers.group(2).lower()
            markers = int(m_play_hand_or_deck_markers.group(3))
            m_cost = re.search(r"energy cost of (\d+) or less", descriptor)
            if m_cost is None:
                m_cost = re.search(r"energy cost of (\d+) or less", branch)
            max_cost = int(m_cost.group(1)) if m_cost else -1
            colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black)\b", descriptor)))
            required_card_type = ""
            if "z-battle card" in descriptor or "z battle card" in descriptor:
                required_card_type = "Z-BATTLE"
            elif "z-unison card" in descriptor or "z unison card" in descriptor:
                required_card_type = "Z-UNISON"
            elif "unison card" in descriptor:
                required_card_type = "UNISON"
            elif "battle card" in descriptor:
                required_card_type = "BATTLE"
            rest_mode = "in rest mode" in branch
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "markers": markers,
                "source_pool": "hand_or_deck",
                "requires_played_from": "hand",
                "max_cost": max_cost,
                **extra,
            }
            if colors:
                params["allowed_colors"] = ",".join(colors)
            if required_card_type:
                params["required_card_type"] = required_card_type
            if rest_mode:
                params["rest_mode"] = True
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is played... look at top N; add up to 1 matching card to hand.
        m_top_search = _PLAY_LOOK_TOP_ADD_TO_HAND_RE.search(branch)
        if not m_top_search:
            m_top_search = _PLAY_LOOK_TOP_ADD_DIRECT_TO_HAND_RE.search(branch)
        if m_top_search:
            played_from_hand = bool((m_top_search.group(1) or "").strip())
            look_count = int(m_top_search.group(2))
            max_add = int(m_top_search.group(3))
            descriptor = m_top_search.group(4).lower()
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "look_count": look_count,
                "max_add": max_add,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if "shuffle your deck" in branch.lower():
                params["shuffle_deck_after"] = True
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

        m_play_draw_optional_add_to_z_then_search = _PLAY_DRAW_OPTIONAL_ADD_FROM_HAND_TO_Z_ENERGY_THEN_LOOK_TOP_ADD_TO_HAND_RE.search(branch)
        if m_play_draw_optional_add_to_z_then_search:
            draw_amount = int(m_play_draw_optional_add_to_z_then_search.group(1))
            hand_descriptor = m_play_draw_optional_add_to_z_then_search.group(3).lower()
            look_count = int(m_play_draw_optional_add_to_z_then_search.group(4))
            max_add = int(m_play_draw_optional_add_to_z_then_search.group(5))
            search_descriptor = m_play_draw_optional_add_to_z_then_search.group(6).lower()
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "draw_amount": draw_amount,
                "look_count": look_count,
                "max_add": max_add,
                **_descriptor_filters(search_descriptor, branch),
                **extra,
            }
            hand_filters = _descriptor_filters(hand_descriptor, branch)
            for key, value in hand_filters.items():
                params[f"hand_{key}"] = value
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_draw_n_optional_add_matching_from_owner_hand_to_z_energy_then_look_top_add_up_to_one_to_hand_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is played... add up to N matching card(s) from deck to hand.
        m_deck_add = _PLAY_ADD_UP_TO_N_FROM_DECK_TO_HAND_RE.search(branch)
        if m_deck_add:
            max_targets = int(m_deck_add.group(1))
            descriptor = m_deck_add.group(2).lower()
            m_cost = re.search(r"energy costs? of (\d+) or less", descriptor)
            if m_cost is None:
                m_cost = re.search(r"energy cost of (\d+) or less", descriptor)
            if m_cost is None:
                m_cost = re.search(r"energy costs? of (\d+) or less", branch)
            if m_cost is None:
                m_cost = re.search(r"energy cost of (\d+) or less", branch)
            max_cost = int(m_cost.group(1)) if m_cost else -1
            colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black)\b", descriptor)))
            required_card_type = ""
            if "z-battle card" in descriptor or "z battle card" in descriptor:
                required_card_type = "Z-BATTLE"
            elif "z-unison card" in descriptor or "z unison card" in descriptor:
                required_card_type = "Z-UNISON"
            elif "unison card" in descriptor:
                required_card_type = "UNISON"
            elif "extra card" in descriptor:
                required_card_type = "EXTRA"
            elif "battle card" in descriptor:
                required_card_type = "BATTLE"
            elif "monster card" in descriptor:
                required_card_type = "BATTLE"
            requires_skill_less = ("skill-less" in descriptor) or ("skill less" in descriptor)
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {"max_targets": max_targets, "max_cost": max_cost, **extra}
            if colors:
                params["allowed_colors"] = ",".join(colors)
            if required_card_type:
                params["required_card_type"] = required_card_type
            if requires_skill_less:
                params["requires_skill_less"] = True
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_add_up_to_n_from_owner_deck_to_hand_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_play_send_opp_battle_warp_gain_keyword = _PLAY_SEND_UP_TO_N_OPP_BATTLE_TO_WARP_AND_GAIN_KEYWORD_RE.search(branch)

        m_play_send_opp_battle_warp = _PLAY_SEND_UP_TO_N_OPP_BATTLE_TO_WARP_RE.search(branch)
        if m_play_send_opp_battle_warp and m_play_send_opp_battle_warp_gain_keyword is None:
            max_targets = int(m_play_send_opp_battle_warp.group(1))
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "target_policy": "first",
                **extra,
            }
            max_cost = m_play_send_opp_battle_warp.group(2)
            if max_cost is not None:
                params["max_cost"] = int(max_cost)
            if "with an energy cost greater than their current energy" in branch:
                params["requires_cost_greater_than_opponent_current_energy"] = True
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_send_up_to_n_opponent_battle_to_warp_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        if m_play_send_opp_battle_warp_gain_keyword:
            max_targets = int(m_play_send_opp_battle_warp_gain_keyword.group(1))
            extra = _extract_common_conditions(branch)
            warp_params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "target_policy": "first",
                **extra,
            }
            max_cost = m_play_send_opp_battle_warp_gain_keyword.group(2)
            if max_cost is not None:
                warp_params["max_cost"] = int(max_cost)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_send_up_to_n_opponent_battle_to_warp_on_play",
                    handler_params=warp_params,
                    once_per_turn=once,
                )
            )
            grant_keyword = " ".join(
                part.capitalize()
                for part in str(m_play_send_opp_battle_warp_gain_keyword.group(3) or "").replace("-", " ").split()
            )
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_self_gain_power_for_turn_on_play",
                    handler_params={"power_delta": 0, "grant_keyword": grant_keyword, **extra},
                    once_per_turn=once,
                )
            )

        m_play_send_self_and_opp_battle_warp = _PLAY_SEND_SELF_AND_UP_TO_N_OPP_BATTLE_TO_WARP_RE.search(branch)
        if m_play_send_self_and_opp_battle_warp:
            max_targets = int(m_play_send_self_and_opp_battle_warp.group(1))
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "target_policy": "first",
                "send_self_to_warp": True,
                **extra,
            }
            max_cost = m_play_send_self_and_opp_battle_warp.group(2)
            if max_cost is not None:
                params["max_cost"] = int(max_cost)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_send_up_to_n_opponent_battle_to_warp_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_play_send_owner_deck_to_warp_then_play_one_add_rest = _PLAY_SEND_UP_TO_N_FROM_OWNER_DECK_TO_WARP_AND_LATER_PLAY_ONE_ADD_REST_TO_HAND_RE.search(branch)
        if m_play_send_owner_deck_to_warp_then_play_one_add_rest:
            max_targets = int(m_play_send_owner_deck_to_warp_then_play_one_add_rest.group(1))
            descriptor = str(m_play_send_owner_deck_to_warp_then_play_one_add_rest.group(2) or "").strip().lower()
            replay_max_targets = int(m_play_send_owner_deck_to_warp_then_play_one_add_rest.group(3))
            extra = _extract_common_conditions(branch)
            cleaned_descriptor = re.sub(r"\bskill[- ]less\b", " ", descriptor)
            cleaned_descriptor = re.sub(r"\bbattle cards?\b", " ", cleaned_descriptor)
            cleaned_descriptor = re.sub(r"\bwith \d+ power\b", " ", cleaned_descriptor)
            cleaned_descriptor = re.sub(r"\band different character names\b", " ", cleaned_descriptor)
            cleaned_descriptor = re.sub(r"\bdifferent character names\b", " ", cleaned_descriptor)
            cleaned_descriptor = " ".join(cleaned_descriptor.split())
            warp_params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                **_descriptor_filters(cleaned_descriptor, branch),
                **extra,
            }
            if "battle card" in descriptor:
                warp_params["required_card_type"] = "BATTLE"
            if "skill-less" in descriptor or "skill less" in descriptor:
                warp_params["requires_skill_less"] = True
            m_power = re.search(r"(\d+) power", descriptor)
            if m_power is not None:
                warp_params["exact_power"] = int(m_power.group(1))
            if "different character names" in descriptor:
                warp_params["require_different_character_names"] = True
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_send_up_to_n_from_owner_deck_to_warp_on_play",
                    handler_params=warp_params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            schedule_params: dict[str, int | str | bool] = {
                "affected_player_scope": "owner",
                "trigger_kind": "turn_end",
                "trigger_player_scope": "opponent",
                "require_next_turn": True,
                "max_targets": replay_max_targets,
                "return_remaining_to_hand": True,
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_schedule_play_cards_warped_by_source_skill_on_play",
                    handler_params=schedule_params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_send_owner_deck_to_warp_then_play_next_turn = _PLAY_SEND_UP_TO_N_FROM_OWNER_DECK_TO_WARP_THEN_PLAY_NEXT_TURN_RE.search(branch)
        if m_play_send_owner_deck_to_warp_then_play_next_turn:
            max_targets = int(m_play_send_owner_deck_to_warp_then_play_next_turn.group(1))
            raw_descriptor = str(m_play_send_owner_deck_to_warp_then_play_next_turn.group(2) or "").strip()
            descriptor = raw_descriptor.lower()
            extra = _extract_common_conditions(branch)
            warp_params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if "required_name_contains" not in warp_params:
                m_named = re.search(r"\{([^}]+)\}", raw_descriptor)
                if m_named is not None:
                    warp_params["required_name_contains"] = m_named.group(1).strip().upper()
            if "battle card" in descriptor:
                warp_params["required_card_type"] = "BATTLE"
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_send_up_to_n_from_owner_deck_to_warp_on_play",
                    handler_params=warp_params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_schedule_play_cards_warped_by_source_skill_on_play",
                    handler_params={
                        "affected_player_scope": "owner",
                        "trigger_kind": "main_phase_start",
                        "trigger_player_scope": "owner",
                        "require_next_turn": True,
                        "max_targets": max_targets,
                        "resting": "rest mode" in branch.lower(),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_send_owner_deck_to_warp_then_add_to_hand_if_still_in_play = _PLAY_SEND_UP_TO_N_FROM_OWNER_DECK_TO_WARP_THEN_ADD_TO_HAND_NEXT_TURN_IF_STILL_IN_PLAY_RE.search(branch)
        if m_play_send_owner_deck_to_warp_then_add_to_hand_if_still_in_play:
            max_targets = int(m_play_send_owner_deck_to_warp_then_add_to_hand_if_still_in_play.group(1))
            descriptor = str(m_play_send_owner_deck_to_warp_then_add_to_hand_if_still_in_play.group(2) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            warp_params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if "battle card" in descriptor:
                warp_params["required_card_type"] = "BATTLE"
            if "skill-less" in descriptor or "skill less" in descriptor:
                warp_params["requires_skill_less"] = True
            m_max_cost = re.search(r"energy cost of (\d+) or less", descriptor)
            if m_max_cost is not None:
                warp_params["max_cost"] = int(m_max_cost.group(1))
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_send_up_to_n_from_owner_deck_to_warp_on_play",
                    handler_params=warp_params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_schedule_return_cards_warped_by_source_skill_on_play",
                    handler_params={
                        "affected_player_scope": "owner",
                        "trigger_kind": "main_phase_start",
                        "trigger_player_scope": "owner",
                        "require_next_turn": True,
                        "require_source_in_play": True,
                        "required_source_zone": "battle",
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_send_owner_deck_to_warp_then_add_to_hand = _PLAY_SEND_UP_TO_N_FROM_OWNER_DECK_TO_WARP_THEN_ADD_TO_HAND_NEXT_TURN_RE.search(branch)
        if m_play_send_owner_deck_to_warp_then_add_to_hand:
            max_targets = int(m_play_send_owner_deck_to_warp_then_add_to_hand.group(1))
            descriptor = str(m_play_send_owner_deck_to_warp_then_add_to_hand.group(2) or "").strip().lower()
            extra = _extract_common_conditions(branch)
            warp_params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if "battle card" in descriptor:
                warp_params["required_card_type"] = "BATTLE"
            if "skill-less" in descriptor or "skill less" in descriptor:
                warp_params["requires_skill_less"] = True
            m_max_cost = re.search(r"energy cost of (\d+) or less", descriptor)
            if m_max_cost is not None:
                warp_params["max_cost"] = int(m_max_cost.group(1))
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_send_up_to_n_from_owner_deck_to_warp_on_play",
                    handler_params=warp_params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_schedule_return_cards_warped_by_source_skill_on_play",
                    handler_params={
                        "affected_player_scope": "owner",
                        "trigger_kind": "main_phase_start",
                        "trigger_player_scope": "owner",
                        "require_next_turn": True,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_add_from_life_to_hand = _PLAY_ADD_UP_TO_N_FROM_OWNER_LIFE_TO_HAND_RE.search(branch)
        if m_play_add_from_life_to_hand:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_add_up_to_n_from_owner_life_to_hand_on_play",
                    handler_params={
                        "max_targets": int(m_play_add_from_life_to_hand.group(1)),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_add_from_drop_to_hand = _PLAY_ADD_UP_TO_N_FROM_OWNER_DROP_TO_HAND_RE.search(branch)
        if m_play_add_from_drop_to_hand:
            descriptor = str(m_play_add_from_drop_to_hand.group(2) or "").strip().lower()
            filtered_descriptor = re.sub(r"\band no keyword skills\b", "", descriptor, flags=re.IGNORECASE).strip(" ,.-")
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": int(m_play_add_from_drop_to_hand.group(1)),
                **_descriptor_filters(filtered_descriptor, branch),
                **extra,
            }
            if "no keyword skills" in descriptor or "without keyword skills" in descriptor:
                params["requires_no_keywords"] = True
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_add_up_to_n_from_owner_drop_to_hand_on_play",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_switch_opponent_battle_rest = _PLAY_SWITCH_UP_TO_N_OPPONENT_BATTLE_REST_RE.search(branch)
        if m_play_switch_opponent_battle_rest:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_switch_up_to_n_opponent_battle_rest_on_play",
                    handler_params={
                        "max_targets": int(m_play_switch_opponent_battle_rest.group(1)),
                        "max_cost": int(m_play_switch_opponent_battle_rest.group(2)),
                        "target_policy": "first",
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_bottom_deck_opp_battle_switch_leader_energy_keyword = _PLAY_BOTTOM_DECK_OPP_BATTLE_SWITCH_LEADER_AND_ENERGY_ACTIVE_AND_GAIN_KEYWORD_UNTIL_OPP_TURN_RE.search(branch)
        if m_play_bottom_deck_opp_battle_switch_leader_energy_keyword:
            max_targets = int(m_play_bottom_deck_opp_battle_switch_leader_energy_keyword.group(1))
            switch_leader_count = int(m_play_bottom_deck_opp_battle_switch_leader_energy_keyword.group(2))
            switch_energy_count = int(m_play_bottom_deck_opp_battle_switch_leader_energy_keyword.group(3))
            energy_descriptor = str(m_play_bottom_deck_opp_battle_switch_leader_energy_keyword.group(4) or "").strip().lower()
            grant_keyword = " ".join(
                part.capitalize()
                for part in str(m_play_bottom_deck_opp_battle_switch_leader_energy_keyword.group(5) or "").replace("-", " ").split()
            )
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "switch_leader_max_targets": switch_leader_count,
                "switch_energy_max_targets": switch_energy_count,
                "grant_keyword": grant_keyword,
                **extra,
            }
            if "mono-blue" in energy_descriptor or "mono blue" in energy_descriptor:
                params["energy_allowed_colors"] = "blue"
                params["energy_requires_mono"] = True
            else:
                energy_filters = _descriptor_filters(energy_descriptor, branch)
                if "allowed_colors" in energy_filters:
                    params["energy_allowed_colors"] = energy_filters["allowed_colors"]
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_bottom_deck_up_to_n_opponent_battle_then_switch_up_to_n_owner_leader_and_energy_active_and_gain_keyword_until_opponent_turn_on_play",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_bottom_deck_opp_battle = _PLAY_BOTTOM_DECK_OPP_BATTLE_RE.search(branch)
        if m_play_bottom_deck_opp_battle and m_play_add_top_deck_to_energy_and_bottom_deck_opp_battle is None:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": int(m_play_bottom_deck_opp_battle.group(1)),
                **extra,
            }
            max_cost = m_play_bottom_deck_opp_battle.group(2)
            if max_cost is not None:
                params["max_cost"] = int(max_cost)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_bottom_deck_up_to_n_opponent_battle",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _PLAY_PLACE_ANY_NUMBER_OPPONENT_BATTLES_INTO_DROP_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_place_any_number_opponent_battle_into_drop_on_play",
                    handler_params={"ignores_barrier": True, **extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_place_up_to_n_opp_battle_drop = _PLAY_PLACE_UP_TO_N_OPPONENT_BATTLE_INTO_DROP_RE.search(branch)
        if m_play_place_up_to_n_opp_battle_drop:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": int(m_play_place_up_to_n_opp_battle_drop.group(1)),
                "ignores_barrier": True,
                **extra,
            }
            if "from your hand" in branch.lower():
                params["requires_played_from"] = "hand"
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_place_up_to_n_opponent_battle_into_drop_on_play",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_return_all_opp_battle_and_unison = _PLAY_RETURN_ALL_OPPONENT_BATTLE_AND_UNISON_TO_HAND_AND_BOTTOM_DECK_OPPONENT_LIFE_IF_MORE_HAND_RE.search(branch)
        if m_play_return_all_opp_battle_and_unison:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_return_all_opponent_battle_and_unison_to_hand_and_bottom_deck_opponent_life_if_more_hand_on_play",
                    handler_params={
                        "bottom_deck_opponent_life_amount": int(m_play_return_all_opp_battle_and_unison.group(1)),
                        "ignores_barrier": True,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_non_leader_attack_hand_z_tax = _NON_LEADER_ATTACK_HAND_Z_TAX_RE.search(branch)
        if m_non_leader_attack_hand_z_tax:
            extra = _extract_common_conditions(branch)
            count = int(m_non_leader_attack_hand_z_tax.group(1) or 1)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_apply_non_leader_attack_hand_and_z_tax_on_play",
                    handler_params={
                        "hand_count": count,
                        "z_energy_count": count,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_place_all_opp_battle_and_unison_under_self = _PLAY_PLACE_ALL_OPPONENT_BATTLE_AND_UNISON_UNDER_SELF_AND_ADD_TOP_DECK_TO_LIFE_RE.search(branch)
        if m_play_place_all_opp_battle_and_unison_under_self:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_place_all_opponent_battle_and_unison_under_self_and_add_top_deck_to_life_on_play",
                    handler_params={
                        "cards_per_life": int(m_play_place_all_opp_battle_and_unison_under_self.group(1)),
                        "max_life_cards": int(m_play_place_all_opp_battle_and_unison_under_self.group(2) or 0),
                        "ignores_barrier": True,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_return_opp_battle = _PLAY_RETURN_OPP_BATTLE_TO_HAND_RE.search(branch)
        if m_play_return_opp_battle:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": int(m_play_return_opp_battle.group(1)),
                **extra,
            }
            max_cost = m_play_return_opp_battle.group(2)
            if max_cost is not None:
                params["max_cost"] = int(max_cost)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_return_up_to_n_opponent_battle_to_hand_on_play",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        # [Auto] When this card is played... play up to N matching card(s) from drop.
        m_drop_play = _PLAY_UP_TO_N_FROM_DROP_RE.search(branch)
        if m_drop_play:
            max_targets = int(m_drop_play.group(1))
            descriptor = m_drop_play.group(2).lower()
            m_cost = re.search(r"energy costs? of (\d+) or less", descriptor)
            if m_cost is None:
                m_cost = re.search(r"energy cost of (\d+) or less", descriptor)
            if m_cost is None:
                m_cost = re.search(r"energy costs? of (\d+) or less", branch)
            if m_cost is None:
                m_cost = re.search(r"energy cost of (\d+) or less", branch)
            m_exact_cost = re.search(r"energy cost of (\d+)\b", descriptor)
            exact_cost = int(m_exact_cost.group(1)) if (m_exact_cost and m_cost is None) else -1
            max_cost = int(m_cost.group(1)) if m_cost else exact_cost
            rest_mode = "in rest mode" in branch
            negate_skills = ("with its skills negated" in branch) or ("with their skills negated" in branch)
            m_discard = re.search(r"discard (\d+) card from your hand:", branch)
            discard_before = int(m_discard.group(1)) if m_discard else 0
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "max_cost": max_cost,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if rest_mode:
                params["rest_mode"] = True
            if negate_skills:
                params["negate_skills"] = True
            if discard_before > 0:
                params["discard_from_hand_before"] = discard_before
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_play_up_to_n_from_owner_drop_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_z_energy_combo_drop_play = _PLAY_UP_TO_N_FROM_Z_ENERGY_COMBO_OR_DROP_RE.search(branch)
        if m_z_energy_combo_drop_play:
            max_targets = int(m_z_energy_combo_drop_play.group(1))
            descriptor = m_z_energy_combo_drop_play.group(2).lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_play_up_to_n_from_owner_z_energy_combo_or_drop_on_play",
                    handler_params={
                        "max_targets": max_targets,
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_place_deck_or_drop_under_self = _PLAY_PLACE_UP_TO_N_FROM_DECK_OR_DROP_UNDER_SELF_RE.search(branch)
        if m_place_deck_or_drop_under_self:
            max_targets = int(m_place_deck_or_drop_under_self.group(1))
            descriptor = m_place_deck_or_drop_under_self.group(2).lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_place_up_to_n_from_owner_deck_or_drop_under_self_on_play",
                    handler_params={"max_targets": max_targets, **_descriptor_filters(descriptor, branch), **extra},
                    once_per_turn=once,
                )
            )

        m_place_drop_under_self = _PLAY_PLACE_UP_TO_N_FROM_DROP_UNDER_SELF_RE.search(branch)
        if m_place_drop_under_self:
            max_targets = int(m_place_drop_under_self.group(1))
            descriptor = m_place_drop_under_self.group(2).lower()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_place_up_to_n_from_owner_drop_under_self_on_play",
                    handler_params={"max_targets": max_targets, **_descriptor_filters(descriptor, branch), **extra},
                    once_per_turn=once,
                )
            )

        m_place_named_field_extra_from_z_deck = _PLAY_PLACE_UP_TO_N_NAMED_FIELD_EXTRA_FROM_OWNER_Z_DECK_RE.search(branch)
        if m_place_named_field_extra_from_z_deck:
            max_targets = int(m_place_named_field_extra_from_z_deck.group(1))
            target_name = str(m_place_named_field_extra_from_z_deck.group(2) or "").strip().upper()
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_activate_up_to_n_named_field_extra_from_owner_z_deck_on_play",
                    handler_params={
                        "max_targets": max_targets,
                        "required_name_contains": target_name,
                        "required_card_type": "EXTRA",
                        "requires_field_keyword": True,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_union_absorb_top_deck_under_self_and_rest = _OWNER_UNION_ABSORB_ACTIVATED_PLACE_TOP_DECK_UNDER_SELF_AND_REST_RE.search(branch)
        if m_owner_union_absorb_top_deck_under_self_and_rest:
            descriptor = m_owner_union_absorb_top_deck_under_self_and_rest.group(1).lower()
            max_targets = int(m_owner_union_absorb_top_deck_under_self_and_rest.group(2))
            trigger_filters = _descriptor_filters(descriptor, branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
            }
            if "allowed_colors" in trigger_filters:
                params["trigger_allowed_colors"] = trigger_filters["allowed_colors"]
            if "required_traits" in trigger_filters:
                params["trigger_required_traits"] = trigger_filters["required_traits"]
            if "required_characters" in trigger_filters:
                params["trigger_required_characters"] = trigger_filters["required_characters"]
            if "required_name_contains" in trigger_filters:
                params["trigger_required_name_contains"] = trigger_filters["required_name_contains"]
            rules.append(
                EffectRule(
                    trigger="owner_union_absorb_activated",
                    handler_id="auto_place_top_deck_under_self_and_switch_up_to_n_opponent_battle_rest_on_union_absorb",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_auto_owner_activate_extra_from_hand_add_markers = _AUTO_OWNER_ACTIVATE_EXTRA_FROM_HAND_ADD_MARKERS_RE.search(branch)
        if m_auto_owner_activate_extra_from_hand_add_markers:
            descriptor = m_auto_owner_activate_extra_from_hand_add_markers.group(1).strip().lower()
            amount = int(m_auto_owner_activate_extra_from_hand_add_markers.group(2))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_activate_extra_from_hand",
                    handler_id="auto_add_markers_on_owner_activate_extra_from_hand",
                    handler_params={
                        "amount": amount,
                        "required_card_type": "EXTRA",
                        **_descriptor_filters(descriptor, branch),
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        # [Auto] When this card is played... add marker(s) based on multicolor energy count.
        m_marker_per_energy = _PLAY_ADD_MARKER_PER_N_MULTICOLOR_ENERGY_RE.search(branch)
        if m_marker_per_energy:
            per_n_energy = int(m_marker_per_energy.group(1))
            if per_n_energy <= 0:
                per_n_energy = 1
            m_min_markers = re.search(r"if this card has (\d+) marker", branch)
            min_markers = int(m_min_markers.group(1)) if m_min_markers else 0
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {"per_n_energy": per_n_energy, **extra}
            if min_markers > 0:
                params["min_source_markers"] = min_markers
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_add_markers_per_n_multicolor_energy_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        # [Auto] When this card is played from your hand... choose N in hand and add it to life.
        m_play_add_life = _PLAY_FROM_HAND_ADD_FROM_HAND_TO_LIFE_RE.search(branch)
        if m_play_add_life:
            amount = int(m_play_add_life.group(1))
            descriptor = m_play_add_life.group(2).lower()
            colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black)\b", descriptor)))
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {"amount": amount, "requires_played_from": "hand", **extra}
            if colors:
                params["allowed_colors"] = ",".join(colors)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_add_up_to_n_from_owner_hand_to_life_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_play_opponent_discards = _PLAY_OPPONENT_DISCARDS_N_FROM_HAND_RE.search(branch)
        if m_play_opponent_discards:
            amount = int(m_play_opponent_discards.group(1) or m_play_opponent_discards.group(2) or 1)
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {"amount": amount, **extra}
            if "when this card is played from your hand" in branch.lower():
                params["requires_played_from"] = "hand"
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_opponent_discards_n_from_hand_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_play_add_markers_to_owner_unison = _PLAY_ADD_MARKERS_TO_OWNER_UNISON_RE.search(branch)
        if m_play_add_markers_to_owner_unison:
            max_targets = int(m_play_add_markers_to_owner_unison.group(1))
            descriptor = str(m_play_add_markers_to_owner_unison.group(2) or "").strip().lower()
            raw_amount = m_play_add_markers_to_owner_unison.group(3)
            amount = int(raw_amount) if raw_amount and raw_amount.isdigit() else 1
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "amount": amount,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if "from your hand" in branch.lower():
                params["requires_played_from"] = "hand"
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_add_markers_to_matching_owner_unison_on_play",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_opponent_hand_to_warp = _PLAY_OPPONENT_CHOOSES_N_HAND_TO_WARP_RE.search(branch)
        if m_play_opponent_hand_to_warp:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": int(m_play_opponent_hand_to_warp.group(1)),
                **extra,
            }
            if "from your hand" in branch.lower():
                params["requires_played_from"] = "hand"
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_send_up_to_n_opponent_hand_to_warp_on_play",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_opponent_counter_activated_discard = _OWNER_OPPONENT_COUNTER_ACTIVATED_DISCARD_RE.search(branch)
        if m_owner_opponent_counter_activated_discard:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_opponent_counter_activated",
                    handler_id="auto_opponent_discards_n_from_hand_on_opponent_counter_activated",
                    handler_params={
                        "amount": int(m_owner_opponent_counter_activated_discard.group(1)),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_delayed_token = _PLAY_DELAYED_TOKEN_RE.search(branch)
        if m_play_delayed_token:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "amount": int(m_play_delayed_token.group(1)),
                "token_name": _normalize_token_name(str(m_play_delayed_token.group(2) or "Token").strip()),
                "power": int(m_play_delayed_token.group(3) or 0),
                "trigger_kind": "turn_end",
                "trigger_player_scope": "opponent",
                "controller_player_scope": "opponent" if m_play_delayed_token.group(4) else "owner",
                **extra,
            }
            if "from your hand" in branch.lower():
                params["requires_played_from"] = "hand"
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_schedule_play_token_in_battle_on_play",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_immediate_token = _PLAY_IMMEDIATE_TOKEN_RE.search(branch)
        m_play_immediate_token_with_power = (
            _PLAY_IMMEDIATE_TOKEN_POST_CREATED_POWER_RE.search(branch)
            if m_play_immediate_token is None
            else None
        )
        if (m_play_immediate_token or m_play_immediate_token_with_power) and "at the end of your opponent's next turn" not in branch.lower():
            token_name = _normalize_token_name(
                m_play_immediate_token.group(2) if m_play_immediate_token else m_play_immediate_token_with_power.group(2)
            )
            power, combo_cost, combo_power = _extract_token_stats(
                branch,
                token_name=token_name,
                explicit_power=(
                    (m_play_immediate_token.group(3) or m_play_immediate_token.group(6))
                    if m_play_immediate_token
                    else (m_play_immediate_token_with_power.group(3) or m_play_immediate_token_with_power.group(6))
                ),
                explicit_combo_cost=(m_play_immediate_token.group(4) if m_play_immediate_token else m_play_immediate_token_with_power.group(4)),
                explicit_combo_power=(m_play_immediate_token.group(5) if m_play_immediate_token else m_play_immediate_token_with_power.group(5)),
            )
            extra = _extract_common_conditions(branch)
            params = {
                "amount": int(m_play_immediate_token.group(1) if m_play_immediate_token else m_play_immediate_token_with_power.group(1)),
                "token_name": token_name,
                "power": power,
                "combo_cost": combo_cost,
                "combo_power": combo_power,
                "resting": "in rest mode" in branch.lower(),
                **extra,
            }
            granted_keyword = str(m_play_immediate_token.group(7) or "").strip() if m_play_immediate_token else ""
            if not granted_keyword:
                m_token_gain_keywords = _TOKEN_GAIN_KEYWORDS_RE.search(branch)
                granted_keyword = str(m_token_gain_keywords.group(1) or "").strip() if m_token_gain_keywords else ""
            if granted_keyword:
                params["temporary_keywords"] = _normalize_extracted_keywords(granted_keyword)
                params["keyword_duration"] = "opponent_turn" if "until the end of your opponent's next turn" in branch.lower() else "turn"
            m_post_created_token_power = _PLAY_IMMEDIATE_TOKEN_POST_CREATED_POWER_RE.search(branch)
            if m_post_created_token_power:
                params["post_created_tokens_power_delta"] = int(m_post_created_token_power.group(7))
            m_token_then_place_under_self = _PLAY_TOKEN_THEN_PLACE_OPPONENT_BATTLE_UNDER_SELF_RE.search(branch)
            if m_token_then_place_under_self:
                params["post_play_place_under_self_max_targets"] = int(m_token_then_place_under_self.group(1))
            if "opponent's battle area" in branch.lower():
                params["controller_player_scope"] = "opponent"
            if "from your hand" in branch.lower():
                params["requires_played_from"] = "hand"
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_play_token_in_battle_on_play",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_other_battle_played_play_token = _OWNER_OTHER_BATTLE_PLAYED_PLAY_TOKEN_RE.search(branch)
        if m_owner_other_battle_played_play_token:
            event_descriptor = str(m_owner_other_battle_played_play_token.group(1) or "").strip().lower()
            event_filters = _descriptor_filters(event_descriptor, branch)
            if "<" in event_descriptor and "required_characters" not in event_filters and "required_traits" in event_filters:
                event_filters["required_characters"] = str(event_filters.pop("required_traits"))
            power, combo_cost, combo_power = _extract_token_stats(branch)
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "amount": int(m_owner_other_battle_played_play_token.group(2)),
                "token_name": _normalize_token_name(m_owner_other_battle_played_play_token.group(3)),
                "power": power,
                "combo_cost": combo_cost,
                "combo_power": combo_power,
                "resting": "in rest mode" in branch.lower(),
                "event_allowed_colors": str(event_filters.get("allowed_colors", "")),
                "event_required_traits": str(event_filters.get("required_traits", "")),
                "event_required_characters": str(event_filters.get("required_characters", "")),
                "event_required_name_contains": str(event_filters.get("required_name_contains", "")),
                "event_required_card_type": str(event_filters.get("required_card_type", "")),
                "event_requires_all_characters": bool(event_filters.get("requires_all_characters", False)),
                **extra,
            }
            if "opponent's battle area" in branch.lower():
                params["controller_player_scope"] = "opponent"
            rules.append(
                EffectRule(
                    trigger="owner_other_battle_played",
                    handler_id="auto_play_token_in_battle_on_owner_matching_battle_played",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_other_token_played_by_owner_extra = _OWNER_OTHER_TOKEN_PLAYED_BY_OWNER_EXTRA_RE.search(branch)
        if m_owner_other_token_played_by_owner_extra:
            power, combo_cost, combo_power = _extract_token_stats(
                branch,
                explicit_power=m_owner_other_token_played_by_owner_extra.group(4),
            )
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "amount": int(m_owner_other_token_played_by_owner_extra.group(2)),
                "token_name": _normalize_token_name(m_owner_other_token_played_by_owner_extra.group(3)),
                "power": power,
                "combo_cost": combo_cost,
                "combo_power": combo_power,
                "event_required_name_contains": _normalize_token_name(m_owner_other_token_played_by_owner_extra.group(1)).upper(),
                "event_required_played_from": "token",
                "event_required_created_by_source_card_type": "EXTRA",
                **extra,
            }
            if "opponent's battle area" in branch.lower():
                params["controller_player_scope"] = "opponent"
            rules.append(
                EffectRule(
                    trigger="owner_other_battle_played",
                    handler_id="auto_play_token_in_battle_on_owner_matching_battle_played",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_play_send_opponent_hand_battle_to_warp = _PLAY_REVEAL_OPPONENT_HAND_SEND_UP_TO_N_BATTLE_TO_WARP_RE.search(branch)
        if m_play_send_opponent_hand_battle_to_warp:
            max_targets = int(m_play_send_opponent_hand_battle_to_warp.group(1))
            max_power = int(m_play_send_opponent_hand_battle_to_warp.group(2))
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "max_power": max_power,
                **extra,
            }
            if "from your hand" in branch.lower():
                params["requires_played_from"] = "hand"
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_send_up_to_n_opponent_hand_battle_to_warp_on_play",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _PLAY_RETURN_WARPED_BY_SKILL_AT_OPPONENT_NEXT_TURN_END_RE.search(branch):
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {**extra}
            if "from your hand" in branch.lower():
                params["requires_played_from"] = "hand"
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_schedule_return_cards_warped_by_source_skill_to_owner_hand_on_opponent_next_turn_end_on_play",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        branch_lower = branch.lower()
        has_play_warped_at_opponent_next_turn_end = (
            _PLAY_ALL_WARPED_BY_SOURCE_SKILL_AT_OPPONENT_NEXT_TURN_END_RE.search(branch) is not None
            or (
                "at the end of your opponent's next turn" in branch_lower
                and "sent to warps by this skill" in branch_lower
                and "play them in their owners' battle areas" in branch_lower
            )
        )
        if has_play_warped_at_opponent_next_turn_end:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "affected_player_scope": "opponent",
                "trigger_kind": "turn_end",
                "trigger_player_scope": "opponent",
                "require_next_turn": True,
                "negate_skills": (
                    "skills negated for the turn" in branch_lower
                    or "negate the skills of all cards sent to warps by this skill for the turn" in branch_lower
                    or "negate the skills of all cards sent to a warp by this skill for the turn" in branch_lower
                ),
                "max_targets": -1 if ("any cards sent" in branch_lower or "all cards sent" in branch_lower or "play them in" in branch_lower or "play them to" in branch_lower or "play them into" in branch_lower) else 1,
                **extra,
            }
            if "from your hand" in branch_lower:
                params["requires_played_from"] = "hand"
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_schedule_play_cards_warped_by_source_skill_on_play",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        has_play_warped_at_turn_end = (
            _PLAY_PLAY_WARPED_BY_SKILL_AT_TURN_END_RE.search(branch) is not None
            or (
                "at the end of the turn" in branch_lower
                and "sent to warps by this skill" in branch_lower
                and "play them to their owners' battle areas" in branch_lower
            )
        )
        if has_play_warped_at_turn_end:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "affected_player_scope": "both" if "choose this card and" in branch_lower else "opponent",
                "trigger_kind": "turn_end",
                "trigger_player_scope": "current",
                "require_next_turn": False,
                "negate_skills": (
                    "skills negated for the turn" in branch_lower
                    or "negate the skills of all cards sent to warps by this skill for the turn" in branch_lower
                    or "negate the skills of all cards sent to a warp by this skill for the turn" in branch_lower
                ),
                "max_targets": -1 if ("any cards sent" in branch_lower or "all cards sent" in branch_lower or "play them to" in branch_lower or "play them into" in branch_lower) else 1,
                **extra,
            }
            if "from your hand" in branch_lower:
                params["requires_played_from"] = "hand"
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_schedule_play_cards_warped_by_source_skill_on_play",
                    handler_params=params,
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
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

        if _PLAY_TRIGGER_RE.search(branch) and "place this card under your leader at the end of the turn" in branch.lower():
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_schedule_place_self_under_owner_leader_on_turn_end_on_play",
                    handler_params={**extra},
                    once_per_turn=once,
                )
            )

        if _SELF_LEAVES_BATTLE_RETURN_WARPED_BY_SOURCE_SKILL_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_card_left_battle_area",
                    handler_id="auto_return_cards_warped_by_source_skill_to_owner_hand_on_owner_matching_battle_left",
                    handler_params={**extra},
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        # [Auto] When this card attacks... choose up to N opponent Battle Card(s)... gets -X power ...
        if _ATTACK_TRIGGER_RE.search(branch) and ("get -" in branch or "gets -" in branch) and "opponent" in branch and "battle card" in branch:
            max_targets = _extract_max_targets(branch)
            m_cost = re.search(r"energy cost of (\d+) or less", branch)
            max_cost = int(m_cost.group(1)) if m_cost else -1
            m_power = re.search(r"get[s]? -\s*(\d+) power", branch)
            if m_power:
                extra = _extract_common_conditions(branch)
                rules.append(
                    EffectRule(
                        trigger="self_attacks",
                        handler_id="auto_power_reduce_up_to_n_on_attack",
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

        # [Auto] When this card is played, it gets +X power for the turn.
        if _PLAY_TRIGGER_RE.search(branch) and ("this card gets +" in branch or "it gets +" in branch) and "power for the turn" in branch:
            m_self_power = re.search(r"(?:this card|it) gets \+\s*(\d+) power for the turn", branch)
            if m_self_power:
                extra = _extract_common_conditions(branch)
                rules.append(
                    EffectRule(
                        trigger="self_played",
                        handler_id="auto_self_gain_power_for_turn_on_play",
                        handler_params={"power_delta": int(m_self_power.group(1)), **extra},
                        once_per_turn=once,
                        limit_per_turn=limit,
                    )
                )

        # [Auto] When this card is used in a combo... choose up to N opponent Battle Card(s)... gets -X power ...
        if _COMBO_TRIGGER_RE.search(branch) and ("get -" in branch or "gets -" in branch) and "opponent" in branch and "battle card" in branch:
            max_targets = _extract_max_targets(branch)
            m_cost = re.search(r"energy cost of (\d+) or less", branch)
            max_cost = int(m_cost.group(1)) if m_cost else -1
            m_power = re.search(r"get[s]? -\s*(\d+) power", branch)
            if m_power:
                extra = _extract_common_conditions(branch)
                rules.append(
                    EffectRule(
                        trigger="self_comboed",
                        handler_id="auto_power_reduce_up_to_n_on_combo",
                        handler_params={
                            "max_targets": max_targets,
                            "max_cost": max_cost,
                            "target_policy": "first",
                            "power_delta": -int(m_power.group(1)),
                            "requires_comboed_from": "hand" if "from your hand" in branch.lower() else "",
                            **extra,
                        },
                        once_per_turn=once,
                    )
                )

        m_opponent_combo_bottom_deck = _OPPONENT_COMBO_BOTTOM_DECK_HAND_AND_NEGATE_SELF_FOR_BATTLE_RE.search(branch)
        if m_opponent_combo_bottom_deck:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_opponent_card_comboed",
                    handler_id="auto_pay_z_energy_bottom_deck_opponent_hand_on_opponent_combo_and_negate_self_for_battle",
                    handler_params={
                        "amount": int(m_opponent_combo_bottom_deck.group(1)),
                        "negate_self_skill_for_battle": True,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _PLAY_PLACE_ALL_OPPONENT_BATTLE_AND_UNISON_INTO_DROP_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_place_all_opponent_battle_and_unison_into_drop_on_play",
                    handler_params={"ignores_barrier": False, **extra},
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_opponent_battle_played_from_under_leader = _OWNER_OPPONENT_BATTLE_PLAYED_PLAY_SELF_FROM_UNDER_OWNER_LEADER_TO_OPPONENT_BATTLE_RE.search(branch)
        if m_owner_opponent_battle_played_from_under_leader:
            descriptor = str(m_owner_opponent_battle_played_from_under_leader.group(1) or "").strip().lower()
            filters = _descriptor_filters(descriptor, branch)
            extra = _extract_common_conditions(branch)
            handler_params = {
                "required_source_zone": "leader_under",
                **{
                    f"event_{key}": value
                    for key, value in filters.items()
                    if key in {
                        "allowed_colors",
                        "required_traits",
                        "required_characters",
                        "required_name_contains",
                        "required_card_type",
                        "requires_skill_less",
                    }
                },
                **extra,
            }
            if "max_cost" in filters:
                handler_params["event_max_energy_cost"] = filters["max_cost"]
            if "with both <" in descriptor:
                handler_params["event_requires_all_characters"] = True
            rules.append(
                EffectRule(
                    trigger="owner_opponent_battle_played",
                    handler_id="auto_play_self_from_under_owner_leader_to_opponent_battle",
                    handler_params=handler_params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_opponent_battle_played_discard = _OWNER_OPPONENT_BATTLE_PLAYED_DISCARD_RE.search(branch)
        if m_owner_opponent_battle_played_discard:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_opponent_battle_played",
                    handler_id="auto_opponent_discards_n_from_hand_on_owner_opponent_battle_played",
                    handler_params={
                        "amount": int(m_owner_opponent_battle_played_discard.group(1)),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_union_activated_play_token = _OWNER_UNION_ACTIVATED_PLAY_TOKEN_RE.search(branch)
        if m_owner_union_activated_play_token:
            fallback_stats = re.search(
                r"\([^)]*?(\d+)\s+power,\s*(\d+)\s+combo cost,\s*(?:and\s*)?(\d+)\s+combo power[^)]*\)",
                branch,
                re.IGNORECASE,
            )
            combo_cost = int(
                m_owner_union_activated_play_token.group(4) or (fallback_stats.group(2) if fallback_stats else 0) or 0
            )
            combo_power = int(
                m_owner_union_activated_play_token.group(5) or (fallback_stats.group(3) if fallback_stats else 0) or 0
            )
            explicit_power = (
                m_owner_union_activated_play_token.group(3)
                or m_owner_union_activated_play_token.group(6)
                or (fallback_stats.group(1) if fallback_stats else 0)
                or 0
            )
            rules.append(
                EffectRule(
                    trigger="owner_union_activated",
                    handler_id="auto_play_token_in_battle_on_owner_union_activated",
                    handler_params={
                        "amount": int(m_owner_union_activated_play_token.group(1)),
                        "token_name": str(m_owner_union_activated_play_token.group(2) or "Token").strip(),
                        "power": int(explicit_power or 0),
                        "combo_cost": combo_cost,
                        "combo_power": combo_power,
                        "resting": "in rest mode" in branch.lower(),
                        **_extract_common_conditions(branch),
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_bottom_deck_opp_hand = _COMBO_TRIGGER_FROM_HAND_OPPONENT_BOTTOM_DECK_HAND_RE.search(branch)
        if m_combo_bottom_deck_opp_hand:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_opponent_bottom_decks_n_from_hand_on_combo",
                    handler_params={
                        "amount": int(m_combo_bottom_deck_opp_hand.group(1)),
                        "requires_comboed_from": "hand",
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_play_token = _COMBO_PLAY_TOKEN_RE.search(branch)
        if m_combo_play_token:
            power, combo_cost, combo_power = _extract_token_stats(
                branch,
                explicit_power=m_combo_play_token.group(4) or m_combo_play_token.group(7),
                explicit_combo_cost=m_combo_play_token.group(5),
                explicit_combo_power=m_combo_play_token.group(6),
            )
            params: dict[str, int | str | bool] = {
                "amount": int(m_combo_play_token.group(2)),
                "token_name": _normalize_token_name(m_combo_play_token.group(3)),
                "power": power,
                "combo_cost": combo_cost,
                "combo_power": combo_power,
                "resting": "in rest mode" in branch.lower(),
                **_extract_common_conditions(branch),
            }
            combo_from = str(m_combo_play_token.group(1) or "").strip().lower()
            if combo_from == "hand":
                params["requires_comboed_from"] = "hand"
            elif combo_from == "battle area":
                params["requires_comboed_from"] = "battle"
            controller_scope = str(m_combo_play_token.group(8) or "").strip().lower()
            if controller_scope:
                params["controller_player_scope"] = "opponent"
            granted_keyword = str(m_combo_play_token.group(9) or "").strip()
            if granted_keyword:
                params["temporary_keywords"] = _normalize_extracted_keywords(granted_keyword)
                params["keyword_duration"] = "opponent_turn" if "until the end of your opponent's next turn" in branch.lower() else "turn"
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_play_token_in_battle_on_combo",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_return_opponent_combo_to_hand = _COMBO_TRIGGER_RETURN_OPPONENT_COMBO_TO_HAND_RE.search(branch)
        if m_combo_return_opponent_combo_to_hand:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_return_up_to_n_opponent_combo_to_hand_on_combo",
                    handler_params={
                        "amount": int(m_combo_return_opponent_combo_to_hand.group(1)),
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_switch_opp_leader_or_battle_rest = _COMBO_TRIGGER_FROM_HAND_SWITCH_OPPONENT_LEADER_OR_BATTLE_REST_RE.search(branch)
        if m_combo_switch_opp_leader_or_battle_rest:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_switch_up_to_n_opponent_leader_or_battle_rest_on_combo",
                    handler_params={
                        "max_targets": int(m_combo_switch_opp_leader_or_battle_rest.group(1)),
                        "requires_comboed_from": "hand",
                        "target_policy": "first",
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_switch_owner_energy_active = _COMBO_TRIGGER_FROM_HAND_SWITCH_OWNER_ENERGY_ACTIVE_RE.search(branch)
        if m_combo_switch_owner_energy_active:
            max_targets = int(m_combo_switch_owner_energy_active.group(1))
            descriptor = str(m_combo_switch_owner_energy_active.group(2) or "").lower()
            colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black)\b", descriptor)))
            requires_multicolor = "multicolor" in descriptor
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "requires_comboed_from": "hand",
                **extra,
            }
            if colors:
                params["allowed_colors"] = ",".join(colors)
            if requires_multicolor:
                params["requires_multicolor"] = True
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_switch_up_to_n_owner_energy_active_on_combo",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_place_deck_card_in_drop = _COMBO_TRIGGER_FROM_HAND_PLACE_DECK_CARD_IN_DROP_RE.search(branch)
        if m_combo_place_deck_card_in_drop:
            max_targets = int(m_combo_place_deck_card_in_drop.group(1))
            descriptor = str(m_combo_place_deck_card_in_drop.group(2) or "").lower()
            colors = sorted(set(re.findall(r"\b(red|blue|green|yellow|black)\b", descriptor)))
            m_cost = re.search(r"energy cost of (\d+) or less", descriptor)
            max_cost = int(m_cost.group(1)) if m_cost else -1
            required_type = "BATTLE" if "battle card" in descriptor else ""
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "requires_comboed_from": "hand",
                **extra,
            }
            if colors:
                params["allowed_colors"] = ",".join(colors)
            if max_cost >= 0:
                params["max_cost"] = max_cost
            if required_type:
                params["required_card_type"] = required_type
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_place_up_to_n_from_owner_deck_into_drop_on_combo",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_gain_combo_power = _COMBO_TRIGGER_FROM_HAND_SELF_GAIN_COMBO_POWER_PER_DROP_AND_WARP_RE.search(branch)
        if m_combo_gain_combo_power:
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "combo_power_per_card": int(m_combo_gain_combo_power.group(1)),
                "requires_comboed_from": "hand",
                **extra,
            }
            if m_combo_gain_combo_power.group(2):
                params["max_count"] = int(m_combo_gain_combo_power.group(2))
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_self_gain_combo_power_on_combo_per_owner_drop_and_warp",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_gain_flat_combo_power = _COMBO_TRIGGER_FROM_HAND_SELF_GAIN_FLAT_COMBO_POWER_RE.search(branch)
        if m_combo_gain_flat_combo_power and "for each card in your drop area and warp" not in branch.lower():
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_self_gain_combo_power_on_combo",
                    handler_params={
                        "combo_power_delta": int(m_combo_gain_flat_combo_power.group(1)),
                        "requires_comboed_from": "hand",
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
        elif "for each card in your drop area and warp" not in branch.lower():
            m_combo_gain_flat_combo_power_any = _COMBO_TRIGGER_SELF_GAIN_FLAT_COMBO_POWER_RE.search(branch)
            if m_combo_gain_flat_combo_power_any:
                extra = _extract_common_conditions(branch)
                params: dict[str, int | str | bool] = {
                    "combo_power_delta": int(m_combo_gain_flat_combo_power_any.group(2)),
                    **extra,
                }
                combo_from = str(m_combo_gain_flat_combo_power_any.group(1) or "").strip().lower()
                if combo_from == "hand":
                    params["requires_comboed_from"] = "hand"
                elif combo_from == "battle area":
                    params["requires_comboed_from"] = "battle"
                rules.append(
                    EffectRule(
                        trigger="self_comboed",
                        handler_id="auto_self_gain_combo_power_on_combo",
                        handler_params=params,
                        once_per_turn=once,
                        limit_per_turn=limit,
                    )
                )

        m_combo_battle_end_warp_self = _COMBO_FROM_HAND_BATTLE_END_WARP_SELF_RE.search(branch)
        if m_combo_battle_end_warp_self:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_comboed_battle_end",
                    handler_id="auto_send_self_to_owner_warp_on_battle_end",
                    handler_params={
                        "requires_comboed_from": "hand",
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_buff_other_combo_card = _COMBO_TRIGGER_FROM_HAND_BUFF_OTHER_COMBO_CARD_RE.search(branch)
        if m_combo_buff_other_combo_card:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_buff_other_owner_combo_card_on_combo",
                    handler_params={
                        "combo_power_delta": int(m_combo_buff_other_combo_card.group(1)),
                        "requires_comboed_from": "hand",
                        "exclude_self": True,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_buff_owner_battle = _COMBO_TRIGGER_BUFF_OWNER_BATTLE_FOR_BATTLE_RE.search(branch)
        if m_combo_buff_owner_battle:
            max_targets = int(m_combo_buff_owner_battle.group(1))
            descriptor = str(m_combo_buff_owner_battle.group(2) or "").lower()
            power_delta = int(m_combo_buff_owner_battle.group(3))
            extra = _extract_common_conditions(branch)
            target_filters = _descriptor_filters(descriptor, branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "power_delta": power_delta,
                **target_filters,
                **extra,
            }
            if "from your hand" in branch.lower():
                params["requires_comboed_from"] = "hand"
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_buff_up_to_n_owner_battles_for_battle_on_combo",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_buff_attacking_owner_battle_keyword = _COMBO_TRIGGER_BUFF_ATTACKING_OWNER_BATTLE_WITH_KEYWORD_RE.search(branch)
        if m_combo_buff_attacking_owner_battle_keyword:
            combo_from = str(m_combo_buff_attacking_owner_battle_keyword.group(1) or "").strip().lower()
            max_targets = int(m_combo_buff_attacking_owner_battle_keyword.group(2))
            descriptor = str(m_combo_buff_attacking_owner_battle_keyword.group(3) or "").lower()
            grant_keyword = " ".join(
                part.capitalize() for part in str(m_combo_buff_attacking_owner_battle_keyword.group(4) or "").replace("-", " ").split()
            )
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "grant_keyword": grant_keyword,
                "require_owner_attacker": True,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            if "<" in str(m_combo_buff_attacking_owner_battle_keyword.group(3) or "") and "required_characters" not in params and "required_traits" in params:
                params["required_characters"] = str(params.pop("required_traits"))
            if combo_from == "hand":
                params["requires_comboed_from"] = "hand"
            elif combo_from == "battle area":
                params["requires_comboed_from"] = "battle"
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_buff_up_to_n_owner_battles_for_battle_on_combo",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_combo_power_bottom_deck_draw = _COMBO_TRIGGER_SELF_GAIN_COMBO_POWER_OPTIONAL_BOTTOM_DECK_DRAW_RE.search(branch)
        if m_combo_power_bottom_deck_draw:
            extra = _extract_common_conditions(branch)
            bottom_count = int(m_combo_power_bottom_deck_draw.group(2) or m_combo_power_bottom_deck_draw.group(3) or 1)
            draw_count = int(m_combo_power_bottom_deck_draw.group(4))
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_self_gain_combo_power_on_combo",
                    handler_params={
                        "combo_power_delta": int(m_combo_power_bottom_deck_draw.group(1)),
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_comboed",
                    handler_id="auto_optional_bottom_deck_n_from_owner_hand_draw_n_on_combo",
                    handler_params={
                        "bottom_deck_from_hand": bottom_count,
                        "amount": draw_count,
                        **extra,
                    },
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_comboed_card_gain_combo_power_and_draw = _OWNER_COMBOED_CARD_GAIN_COMBO_POWER_AND_DRAW_RE.search(branch)
        if m_owner_comboed_card_gain_combo_power_and_draw:
            descriptor = m_owner_comboed_card_gain_combo_power_and_draw.group(1).lower()
            combo_power_delta = int(m_owner_comboed_card_gain_combo_power_and_draw.group(2))
            draw_amount = int(m_owner_comboed_card_gain_combo_power_and_draw.group(3))
            extra = _extract_common_conditions(branch)
            event_filters = _descriptor_filters(descriptor, branch)
            prefixed_filters = {f"event_{key}": value for key, value in event_filters.items()}
            rules.append(
                EffectRule(
                    trigger="owner_card_comboed",
                    handler_id="auto_comboed_card_gain_combo_power_on_owner_combo",
                    handler_params={"combo_power_delta": combo_power_delta, **prefixed_filters, **extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="owner_card_comboed",
                    handler_id="auto_draw_n",
                    handler_params={"amount": draw_amount, **prefixed_filters, **extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_combo_draw = _OWNER_COMBO_DRAW_RE.search(branch)
        if m_owner_combo_draw and "it gets +" not in branch.lower():
            descriptor = m_owner_combo_draw.group(1).lower()
            draw_amount = int(m_owner_combo_draw.group(2))
            extra = _extract_common_conditions(branch)
            event_filters = _descriptor_filters(descriptor, branch)
            if "from your hand" in descriptor or "from your hand" in branch.lower():
                event_filters["requires_comboed_from"] = "hand"
            prefixed_filters = {f"event_{key}": value for key, value in event_filters.items()}
            rules.append(
                EffectRule(
                    trigger="owner_card_comboed",
                    handler_id="auto_draw_n",
                    handler_params={"amount": draw_amount, **prefixed_filters, **extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_combo_switch_self_active = _OWNER_COMBO_SWITCH_SELF_ACTIVE_RE.search(branch)
        if m_owner_combo_switch_self_active:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_card_comboed",
                    handler_id="auto_switch_self_active_on_owner_combo",
                    handler_params={**extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_combo_add_marker_and_self_power = _OWNER_COMBO_ADD_MARKER_AND_SELF_POWER_RE.search(branch)
        if m_owner_combo_add_marker_and_self_power:
            descriptor = m_owner_combo_add_marker_and_self_power.group(1).lower()
            power_delta = int(m_owner_combo_add_marker_and_self_power.group(2))
            extra = _extract_common_conditions(branch)
            event_filters = _descriptor_filters(descriptor, branch)
            prefixed_filters = {f"event_{key}": value for key, value in event_filters.items()}
            rules.append(
                EffectRule(
                    trigger="owner_card_comboed",
                    handler_id="auto_add_markers_and_self_power_for_turn_on_owner_combo",
                    handler_params={"marker_delta": 1, "power_delta": power_delta, **prefixed_filters, **extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_combo_remove_markers_from_opp_unison = _OWNER_COMBO_REMOVE_MARKERS_FROM_OPP_UNISON_RE.search(branch)
        if m_owner_combo_remove_markers_from_opp_unison:
            descriptor = m_owner_combo_remove_markers_from_opp_unison.group(1).lower()
            max_targets = int(m_owner_combo_remove_markers_from_opp_unison.group(2))
            marker_amount = int(m_owner_combo_remove_markers_from_opp_unison.group(3))
            extra = _extract_common_conditions(branch)
            event_filters = _descriptor_filters(descriptor, branch)
            prefixed_filters = {f"event_{key}": value for key, value in event_filters.items()}
            rules.append(
                EffectRule(
                    trigger="owner_card_comboed",
                    handler_id="auto_remove_markers_from_up_to_n_opponent_unisons_on_owner_combo",
                    handler_params={"max_targets": max_targets, "marker_amount": marker_amount, **prefixed_filters, **extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_combo_send_opp_drop_to_warp_else_draw = _OWNER_COMBO_SEND_OPP_DROP_TO_WARP_ELSE_DRAW_RE.search(branch)
        if m_owner_combo_send_opp_drop_to_warp_else_draw:
            descriptor = m_owner_combo_send_opp_drop_to_warp_else_draw.group(1).lower()
            max_targets = int(m_owner_combo_send_opp_drop_to_warp_else_draw.group(2))
            draw_amount = int(m_owner_combo_send_opp_drop_to_warp_else_draw.group(3))
            extra = _extract_common_conditions(branch)
            event_filters = _descriptor_filters(descriptor, branch)
            prefixed_filters = {f"event_{key}": value for key, value in event_filters.items()}
            rules.append(
                EffectRule(
                    trigger="owner_card_comboed",
                    handler_id="auto_send_up_to_n_opponent_drop_to_warp_else_draw_n_on_owner_combo",
                    handler_params={"max_targets": max_targets, "draw_amount": draw_amount, **prefixed_filters, **extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_combo_play_self_from_under_leader_or_hand = _OWNER_COMBO_PLAY_SELF_FROM_UNDER_LEADER_OR_HAND_RE.search(branch)
        if m_owner_combo_play_self_from_under_leader_or_hand:
            descriptor = m_owner_combo_play_self_from_under_leader_or_hand.group(1).lower()
            descriptor_for_filters = re.sub(r"from your hand or battle area|from your battle area or hand|from your hand|from your battle area", " ", descriptor, flags=re.IGNORECASE)
            extra = _extract_common_conditions(branch)
            event_filters = _descriptor_filters(descriptor_for_filters, branch)
            if "<" in descriptor and "required_characters" not in event_filters and "required_traits" in event_filters:
                event_filters["required_characters"] = str(event_filters.pop("required_traits"))
            if "from your hand" in descriptor and "battle area" not in descriptor:
                event_filters["requires_comboed_from"] = "hand"
            elif "battle area" in descriptor and "from your hand" not in descriptor:
                event_filters["requires_comboed_from"] = "battle"
            prefixed_filters = {f"event_{key}": value for key, value in event_filters.items()}
            rules.append(
                EffectRule(
                    trigger="owner_card_comboed",
                    handler_id="auto_play_self_from_under_leader_or_owner_hand_on_owner_combo",
                    handler_params={**prefixed_filters, **extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_owner_combo_use_self_from_battle = _OWNER_COMBO_USE_SELF_FROM_BATTLE_IN_COMBO_RE.search(branch)
        if m_owner_combo_use_self_from_battle:
            descriptor = m_owner_combo_use_self_from_battle.group(1).lower()
            extra = _extract_common_conditions(branch)
            event_filters = _descriptor_filters(descriptor, branch)
            prefixed_filters = {f"event_{key}": value for key, value in event_filters.items()}
            rules.append(
                EffectRule(
                    trigger="owner_card_comboed",
                    handler_id="auto_combo_self_from_battle_on_owner_combo",
                    handler_params={**prefixed_filters, **extra},
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_comboed_battle_end",
                    handler_id="auto_play_self_from_combo_on_battle_end",
                    handler_params={
                        "requires_comboed_from": "battle",
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        m_attack_draw_add_to_z_then_place_under_named_host = _AUTO_ATTACK_DRAW_ADD_FROM_BATTLE_OR_DROP_TO_Z_ENERGY_THEN_PLACE_FROM_BATTLE_OR_DROP_UNDER_NAMED_HOST_RE.search(branch)
        if m_attack_draw_add_to_z_then_place_under_named_host:
            draw_count = int(m_attack_draw_add_to_z_then_place_under_named_host.group(1))
            z_energy_max = int(m_attack_draw_add_to_z_then_place_under_named_host.group(2))
            z_energy_descriptor_raw = str(m_attack_draw_add_to_z_then_place_under_named_host.group(3) or "").strip()
            z_energy_descriptor = z_energy_descriptor_raw.lower()
            under_max = int(m_attack_draw_add_to_z_then_place_under_named_host.group(4))
            under_descriptor_raw = str(m_attack_draw_add_to_z_then_place_under_named_host.group(5) or "").strip()
            under_descriptor = under_descriptor_raw.lower()
            host_name = str(m_attack_draw_add_to_z_then_place_under_named_host.group(6) or "").strip().upper()
            extra = _extract_common_conditions(branch)
            z_energy_filters = _descriptor_filters(z_energy_descriptor, branch)
            if "<" in z_energy_descriptor_raw and "required_characters" not in z_energy_filters and "required_traits" in z_energy_filters:
                z_energy_filters["required_characters"] = str(z_energy_filters.pop("required_traits")).lower()
            under_filters = _descriptor_filters(under_descriptor, branch)
            if "<" in under_descriptor_raw and "required_characters" not in under_filters and "required_traits" in under_filters:
                under_filters["required_characters"] = str(under_filters.pop("required_traits")).lower()
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_draw_n_add_matching_from_owner_battle_or_drop_to_z_energy_then_place_matching_from_owner_battle_or_drop_under_named_host_on_attack",
                    handler_params={
                        "draw_count": draw_count,
                        "z_energy_max_targets": z_energy_max,
                        **{f"z_energy_{k}": v for k, v in z_energy_filters.items()},
                        "under_max_targets": under_max,
                        **{f"under_{k}": v for k, v in under_filters.items()},
                        "host_name_contains": host_name,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_attacks_battle_end",
                    handler_id="auto_send_self_to_owner_drop_on_attack_battle_end",
                    handler_params={**extra},
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if _AUTO_BATTLE_END_OWNER_GREEN_ATTACKER_KO_OPPONENT_BATTLE_PLACE_UNDER_SELF_RE.search(branch):
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="owner_battle_ko_opponent_battle_battle_end",
                    handler_id="auto_place_battle_koed_by_owner_attacker_under_self_on_battle_end",
                    handler_params={
                        "attacker_allowed_colors": "green",
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        # [Auto] When this card attacks, use up to N ... from your Drop/Warp in a combo with its skills negated for the turn.
        m_attack_combo = _ATTACK_COMBO_FROM_OWNER_ZONE_RE.search(branch)
        if m_attack_combo:
            max_targets = int(m_attack_combo.group(1))
            descriptor = m_attack_combo.group(2).strip()
            source_zone = str(m_attack_combo.group(3)).strip().lower()
            m_combo_power = re.search(r"with (\d+) combo power", descriptor, re.IGNORECASE)
            combo_power = int(m_combo_power.group(1)) if m_combo_power else -1
            combo_descriptor = re.sub(r"with \d+ combo power", " ", descriptor, flags=re.IGNORECASE)
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "source_zone": source_zone,
                "target_policy": "first",
                "negate_skills": True,
                **_descriptor_filters(combo_descriptor, branch),
                **extra,
            }
            if combo_power >= 0:
                params["exact_combo_power"] = combo_power
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_combo_up_to_n_from_owner_zone_on_attack",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_attack_combo_under_named_host = _ATTACK_COMBO_NAMED_FROM_UNDER_NAMED_HOST_THEN_DRAW_AND_GAIN_KEYWORD_RE.search(branch)
        if m_attack_combo_under_named_host:
            max_targets = int(m_attack_combo_under_named_host.group(1))
            required_name = str(m_attack_combo_under_named_host.group(2) or "").strip().upper()
            host_name = str(m_attack_combo_under_named_host.group(3) or "").strip().upper()
            amount = int(m_attack_combo_under_named_host.group(4))
            grant_keyword = " ".join(
                part.capitalize() for part in str(m_attack_combo_under_named_host.group(5) or "").replace("-", " ").split()
            )
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_combo_up_to_n_named_from_under_named_host_on_attack_then_draw_n_and_gain_keyword_for_battle",
                    handler_params={
                        "max_targets": max_targets,
                        "required_name_contains": required_name,
                        "host_name_contains": host_name,
                        "amount": amount,
                        "grant_keyword": grant_keyword,
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        # [Auto] When this card attacks, this card gains +X power for each card in your Warp.
        m_attack_self_power_per_warp = _ATTACK_SELF_GAIN_POWER_PER_OWNER_WARP_RE.search(branch)
        if m_attack_self_power_per_warp:
            power_per_card = int(m_attack_self_power_per_warp.group(1))
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_self_gain_power_for_turn_on_attack",
                    handler_params={"power_delta": f"expr:owner_warp_count*{power_per_card}", **extra},
                    once_per_turn=once,
                )
            )

        if _ATTACK_TRIGGER_RE.search(branch) and "opponent" in branch and "battle card" in branch and "ko it" in branch.lower():
            max_targets = _extract_max_targets(branch)
            m_cost = re.search(r"energy cost of (\d+) or less", branch)
            max_cost = int(m_cost.group(1)) if m_cost else -1
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_ko_up_to_n_opponent_battle_on_attack",
                    handler_params={
                        "max_targets": max_targets,
                        "max_cost": max_cost,
                        "target_policy": "first",
                        **extra,
                    },
                    once_per_turn=once,
                )
            )

        m_attack_opponent_hand_to_warp = _ATTACK_OPPONENT_CHOOSES_N_HAND_TO_WARP_RE.search(branch)
        if m_attack_opponent_hand_to_warp:
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_send_up_to_n_opponent_hand_to_warp_on_play",
                    handler_params={
                        "max_targets": int(m_attack_opponent_hand_to_warp.group(1)),
                        **extra,
                    },
                    source_text=branch,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )

        if len(rules) > branch_start:
            rules[branch_start:] = [replace(rule, source_text=(rule.source_text or branch)) for rule in rules[branch_start:]]

    if limit is not None:
        rules = [replace(rule, limit_per_turn=limit, limit_scope="card_number") for rule in rules]

    rules = [
        replace(
            rule,
            family_id=(rule.family_id or f"{rule.trigger}:{rule.handler_id}"),
            provenance=(rule.provenance or "extractor"),
        )
        for rule in rules
    ]

    # De-duplicate exact duplicates.
    uniq: dict[tuple[str, str, tuple[tuple[str, int | str | bool], ...], str, bool, int | None, str, str, str], EffectRule] = {}
    for rule in rules:
        key = (
            rule.trigger,
            rule.handler_id,
            tuple(sorted(rule.handler_params.items())),
            rule.source_text,
            rule.once_per_turn,
            rule.limit_per_turn,
            rule.limit_scope,
            rule.family_id,
            rule.provenance,
        )
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
    if _ATTACK_DRAW_RE.search(text) and not has_attack_draw:
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


def skill_template_signature(raw: str | None) -> str:
    return _skill_template_signature(raw)


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

