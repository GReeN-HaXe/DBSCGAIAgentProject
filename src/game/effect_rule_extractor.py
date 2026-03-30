from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace
from typing import Iterable

from src.db.interfaces import CardRepository
from src.domain.models import CardData
from src.game.effect_rules import EffectRule


_WS_RE = re.compile(r"\s+")
_PLAY_TRIGGER_RE = re.compile(r"(?:if [^:]{1,120}:\s*)?when (?:this card is played(?: from your hand)?|you play this card)")
_LEADER_PLACED_TRIGGER_RE = re.compile(r"(?:if [^:]{1,160}:\s*)?when this card is placed in your leader area", re.IGNORECASE)
_ATTACK_TRIGGER_RE = re.compile(r"(?:if [^:]{1,120}:\s*)?when this card attacks")
_COMBO_TRIGGER_RE = re.compile(r"(?:if [^:]{1,120}:\s*)?when (?:this card is used in a combo|you combo with this card)")
_COMBO_TRIGGER_FROM_HAND_OPPONENT_BOTTOM_DECK_HAND_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand,\s*your opponent chooses (\d+) cards? in their hand and places? (?:it|them) at the bottom of their deck",
    re.IGNORECASE,
)
_COMBO_TRIGGER_FROM_HAND_SWITCH_OPPONENT_LEADER_OR_BATTLE_REST_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand,\s*choose up to (\d+) of your opponent's leader cards? or battle cards? and switch (?:it|them) to rest mode",
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
_COMBO_TRIGGER_FROM_HAND_SELF_GAIN_COMBO_POWER_PER_DROP_AND_WARP_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand,\s*this card gets \+(\d+) combo power for the duration of the turn for each card in your drop area and warp(?:.*?up to a maximum of (\d+))?",
    re.IGNORECASE,
)
_COMBO_TRIGGER_FROM_HAND_SELF_GAIN_FLAT_COMBO_POWER_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand(?:[^.\[]){0,220}?this card gets \+(\d+) combo power for (?:the duration of the turn|the battle)(?! for each card)",
    re.IGNORECASE,
)
_COMBO_TRIGGER_FROM_HAND_BUFF_OTHER_COMBO_CARD_RE = re.compile(
    r"(?:if [^:]{1,180}:\s*)?when (?:this card is used in a combo|you combo with this card) from your hand(?:[^.\[]){0,220}?choose 1 card (?:(?:other than this card in your combo area)|(?:in your combo area other than this card)) and it gets \+(\d+) combo power for the battle",
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
_OWNER_COMBO_USE_SELF_FROM_BATTLE_IN_COMBO_RE = re.compile(
    r"(?:if [^:]{1,260}:\s*)?when you use (.+?) in a combo,\s*you may use this card from a battle area in a combo\.\s*if you do,\s*play this card from (?:its|their) owner'?s drop at the end of the battle",
    re.IGNORECASE,
)
_OPPONENT_COMBO_BOTTOM_DECK_HAND_AND_NEGATE_SELF_FOR_BATTLE_RE = re.compile(
    r"when your opponent uses cards? in a combo,\s*(?:you opponent|your opponent) places (\d+) cards? from their hand at the bottom of their deck, then you negate this skill for the battle",
    re.IGNORECASE,
)
_PLAY_OR_COMBO_DRAW_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card(?: in your hand)? is played or used in a combo.*?draw (\d+) card"
)
_ATTACK_DRAW_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card attacks(?:[^.\[]){0,200}?draw (\d+) card"
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
    r"(?:if [^:]{1,120}:\s*)?at the end of a battle in which this card was used in a combo(?: from your (?:hand|life|energy|drop area))?.*?play this card from (?:your )?drop"
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
    r"\[activate(?::)?\s*main/battle\].{0,340}?choose up to (\d+) of your(?: (.+?))? cards? and (?:it gets|they get) \+(\d+) power for the turn"
)
_ACTIVATE_EXTRA_MAIN_BATTLE_PLAY_UP_TO_N_EACH_OF_TWO_FROM_OWNER_DECK_OR_DROP_RE = re.compile(
    r"\[activate(?::)?\s*main/battle\].{0,360}?play up to (\d+) each of <([^>]+)> and <([^>]+)> cards?-both (red|blue|green|yellow|black|white) and with an energy cost of (\d+)-from your deck and/or drop(?: area)?(?: in rest mode)?"
)
_ACTIVATE_EXTRA_MAIN_BATTLE_ADD_UP_TO_N_FROM_OWNER_DECK_TO_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main/battle\].{0,260}?add up to (\d+) (.+?) from your deck to your hand"
)
_ACTIVATE_MAIN_IF_DO_DRAW_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?(?::\s*|if you do,\s*)draw (\d+) card"
)
_ACTIVATE_MAIN_OPTIONAL_SEND_HAND_TO_WARP_DRAW_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?you may choose (\d+) card in your hand and send it to your warp\.\s*if you do, draw (\d+) card"
)
_ACTIVATE_MAIN_OPPONENT_DISCARDS_N_FROM_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,220}?your opponent discards (\d+) card(?:s)? (?:from )?(?:their|his or her) hand"
)
_ACTIVATE_MAIN_PLAY_UP_TO_N_FROM_OWNER_Z_DECK_OR_Z_ENERGY_RE = re.compile(
    r"\[(?:\+|-)?\d+\]\s*\[activate(?::)?\s*main\].{0,360}?play up to (\d+) (.+?) from your z-deck or z-energy(?: with (?:its|their) skills negated for the game)?"
)
_ACTIVATE_BATTLE_SELF_GAIN_POWER_AND_KEYWORD_FOR_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?this card gets \+(\d+) power and \[([^\]]+)\] for (?:the|this) battle"
)
_ACTIVATE_BATTLE_OWNER_LEADER_GAIN_POWER_AND_KEYWORD_FOR_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?if your leader(?: card)? is .{0,140}?, it gets \+(\d+) power and \[([^\]]+)\] for (?:the|this|the duration of the) battle"
)
_ACTIVATE_BATTLE_CHOOSE_OWNER_CARDS_GAIN_POWER_FOR_BATTLE_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?choose up to (\d+) of your(?: (.+?))? cards? and (?:it gets|they get) \+(\d+) power for (?:the|this) battle"
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
_ACTIVATE_MAIN_LOOK_TOP_ADD_TO_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,260}?look at up to (\d+) cards? from (?:the )?top of your deck, add up to (\d+) (.+?) among them(?:[^.]{0,240})?(?:\s|[â€”â€•-])to your hand"
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
_ACTIVATE_MAIN_BATTLE_PLAY_UP_TO_N_FROM_UNDER_SELF_AND_PLACE_SELF_UNDER_PLAYED_RE = re.compile(
    r"\[activate(?::)?\s*(main|battle)\].{0,420}?play up to (\d+) (.+?) from under this card,\s*and place this card under the played card"
)
_ACTIVATE_MAIN_BATTLE_PLAY_SELF_FROM_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main/battle\].{0,320}?play this card from your hand"
)
_AUTO_OWNER_ACTIVATE_EXTRA_FROM_HAND_ADD_MARKERS_RE = re.compile(
    r"\[auto\].{0,220}?when you activate an? (.+?) extra from your hand,\s*add (\d+) marker(?:s)? to this card"
)
_ACTIVATE_BATTLE_PLAY_SELF_FROM_HAND_RE = re.compile(
    r"\[activate(?::)?\s*battle\].{0,320}?play this card from your hand(?:,\s*then your opponent discards (\d+) card from their hand)?"
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_WARP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,240}?play this card from your warp"
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_WARP_WITH_MARKERS_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?play this card with (\d+) markers? on it from your warp"
)
_ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_OR_WARP_WITH_MARKERS_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?play this card with (\d+) markers? on it from your hand or warp"
)
_ACTIVATE_MAIN_DRAW_GAIN_KEYWORD_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,240}?draw (\d+) card(?:s)?[,;]?\s*and this card gains \[([^\]]+)\] for the turn"
)
_ACTIVATE_MAIN_SELF_GAIN_POWER_AND_KEYWORD_FOR_TURN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?this card gets \+(\d+) power and \[([^\]]+)\] for the turn"
)
_ACTIVATE_MAIN_SELF_GAIN_KEYWORDS_FOR_TURN_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,280}?this card gains \[([^\]]+)\](?: and \[([^\]]+)\])(?: and \[([^\]]+)\])? for the turn"
)
_ACTIVATE_MAIN_DRAW_PLAY_SELF_AND_GAIN_KEYWORD_UNTIL_OPP_TURN_END_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,360}?draw (\d+) card(?:s)?[,;]?\s*play this card from your hand[,;]?\s*and this card gains \[([^\]]+)\] until the end of your opponent'?s turn"
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
_ACTIVATE_MAIN_OWNER_TARGET_GAIN_HIDDEN_COST_TARGET_FRONT_POWER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,380}?choose 1 of your (.+?) battle cards? and switch it to hidden mode:\s*choose up to 1 of your leaders? or up to 1 of your (.+?) battle cards? and increase that card'?s power by the original power on the front of the card that was switched to hidden mode by this skill for the turn"
)
_ACTIVATE_MAIN_KO_OPP_BATTLE_AND_BUFF_OWNER_LEADER_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,380}?choose 1 (.+?) card in your battle area or energy and switch it to hidden mode:\s*choose up to 1 of your opponent'?s battle cards?, ko it, and your (.+?) leader gets \+(\d+) power for the turn"
)
_ACTIVATE_MAIN_SEND_UP_TO_N_OPP_BATTLE_TO_WARP_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?choose up to (\d+) of your opponent'?s battle cards? and send (?:it|them) to (?:its|their) owner'?s warp"
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
_PLAY_ADD_TOP_DECK_TO_ENERGY_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card is played.*?add the top card of your deck to your energy in rest mode"
)
_TURN_END_SWITCH_UP_TO_N_ENERGY_ACTIVE_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?at the end of (?:your turn|the turn), switch up to (\d+) of your(?: (.+?))? energy to active mode"
)
_FIELD_EXTRA_PLACED_SWITCH_UP_TO_N_ENERGY_ACTIVE_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when a player places a \[field\] extra card in a battle area.*?switch up to (\d+) of your(?: (.+?))? energy to active mode"
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
    r"(?:if [^:]{1,120}:\s*)?when this card is played( from your hand)?[^.]{0,300}?"
    r"look at up to (\d+) cards? from (?:the )?top of your deck, add up to (\d+) (.+?) among them(?:[^.]{0,240})?(?:\s|[-\u2014\u2015])to your hand"
)
_PLAY_LOOK_TOP_ADD_DIRECT_TO_HAND_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when this card is played( from your hand)?[^.]{0,300}?"
    r"look at up to (\d+) cards? from (?:the )?top of your deck, add up to (\d+) (.+?) to your hand"
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
_PLAY_PLACE_UP_TO_N_FROM_DECK_OR_DROP_UNDER_SELF_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played(?: from your hand)?[^.]{0,240}?place up to (\d+) (.+?) from your deck(?: and/or| or) drop(?: area)? under this card"
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
_PLAY_SEND_UP_TO_N_OPP_BATTLE_TO_WARP_RE = re.compile(
    r"(?:if [^:]{1,160}:\s*)?when this card is played(?: from your hand)?[^.]{0,260}?choose up to (\d+) of your opponent'?s battle cards?(?: with an energy cost greater than their current energy)?(?:,\s*ignoring \[barrier\])?,?\s*and send (?:it|them) to (?:its|their) owner'?s warp"
)
_PLAY_DRAW_AND_SWITCH_SELF_ACTIVE_RE = re.compile(
    r"(?:if [^:]{1,120}:\s*)?when (?:this card is played(?: from your hand)?|you play this card)(?:[^.\[]){0,200}?draw (\d+) card(?:s)? and switch this card to active mode"
)
_ACTIVATE_MAIN_ADD_UP_TO_N_FROM_OWNER_DECK_TO_HAND_RE = re.compile(
    r"\[activate(?::)?\s*main\].{0,320}?add up to (\d+) (.+?) from your deck to your hand"
)


def _normalize_text(raw: str | None) -> str:
    text = (raw or "").lower()
    text = text.replace("<br>", ". ").replace("[br]", ". ").replace("â€”", " - ")
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
    bullets = ("ãƒ»", "・", "•")
    if not any(b in tail for b in bullets):
        return [text]
    # Normalize known bullet tokens to a single delimiter before splitting.
    normalized_tail = tail
    for b in bullets:
        normalized_tail = normalized_tail.replace(b, "|")
    parts = [p.strip(" .;-") for p in normalized_tail.split("|")[1:] if p.strip(" .;-")]
    if not parts:
        return [text]
    return [f"{prefix} {part}".strip() for part in parts]


def _split_effect_branches(raw: str | None) -> list[str]:
    text = str(raw or "")
    if not text.strip():
        return []
    normalized = text.replace("<br>", "\n").replace("[br]", "\n").replace("\r\n", "\n").replace("\r", "\n")
    bullets = ("ãƒ»", "・", "•")
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    merged: list[str] = []
    for line in lines:
        if merged and any(line.startswith(bullet) for bullet in bullets):
            merged[-1] = f"{merged[-1]} {line}"
        else:
            merged.append(line)
    branches: list[str] = []
    for line in merged:
        normalized_line = _normalize_text(line)
        branches.extend(_split_choose_one_branches(normalized_line))
    return [branch for branch in branches if branch]


def _extract_common_conditions(text: str) -> dict[str, int | str | bool]:
    params: dict[str, int | str | bool] = {}
    auto_cost_header = _extract_auto_header_cost_header(text)
    if auto_cost_header:
        params["auto_cost_header"] = auto_cost_header
    m_sparking = re.search(r"\[\s*sparking\s+(\d+)\s*\]", text)
    if m_sparking:
        params["min_owner_drop"] = int(m_sparking.group(1))
    m_opponent_drop = re.search(r"if your opponent has (\d+) or more cards in (?:their|their own) drop", text)
    if m_opponent_drop:
        params["min_opponent_drop"] = int(m_opponent_drop.group(1))
    m_leader = re.search(
        r"(if your leader(?: card)? .{0,260}?)(?::\s*(?:choose|play|add|draw|send|switch|look|place|your opponent|this card|at the|when))",
        text,
    )
    if m_leader:
        params["requires_leader"] = m_leader.group(1).strip()
    elif "if your leader" in text:
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
    m_life = re.search(r"your life is at (\d+) or less", text)
    if m_life:
        params["max_owner_life"] = int(m_life.group(1))
    if "neither you nor your opponent have a battle card in play" in text:
        params["requires_no_owner_battle"] = True
        params["requires_no_opponent_battle"] = True
    if "if you have no battle cards in play" in text:
        params["requires_no_owner_battle"] = True
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
    m_owner_battle_named = re.search(r"(?:(?:if|and)\s+)?there is a \{([^}]+)\} in your battle area", text, re.IGNORECASE)
    if m_owner_battle_named:
        params["required_owner_battle_required_name_contains"] = m_owner_battle_named.group(1).strip().upper()
    m_owner_combo = re.search(
        r"(?:if you have|and you have|and)\s+(?:a |an )?(.+?) card in your combo area",
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
    if "ignoring [barrier]" in text or "ignoring barrier" in text:
        params["ignores_barrier"] = True
    if "rest mode" in text:
        params["rest_mode_only"] = True
    if "if it's your turn" in text or "during your turn" in text:
        params["requires_owner_turn"] = True
    if "if it's your opponent's turn" in text or "during your opponent's turn" in text:
        params["requires_opponent_turn"] = True
    if "if this card is in a battle" in text.lower():
        params["requires_source_in_battle"] = True
    return params


def _descriptor_filters(descriptor: str, text: str) -> dict[str, int | str | bool]:
    descriptor_lc = descriptor.lower()
    params: dict[str, int | str | bool] = {}
    raw_required_traits = sorted(
        {
            match.strip().title()
            for match in re.findall(r"(?:≪|â‰ª)\s*([^≫]+?)\s*(?:≫|â‰«)", descriptor, re.IGNORECASE)
            if match.strip()
        }
    )
    raw_required_characters = sorted({match.strip().title() for match in re.findall(r"<([^>]+)>", descriptor) if match.strip()})
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
    if "z-battle card" in descriptor_lc or "z battle card" in descriptor_lc:
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
    cleaned = re.sub(r"(?:≪|â‰ª)\s*([^≫]+?)\s*(?:≫|â‰«)", " ", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = cleaned.replace("<", " ").replace(">", " ").replace("≪", " ").replace("≫", " ")
    cleaned = re.sub(r"[^0-9a-z ,/.-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")

    if raw_required_characters and raw_required_traits:
        params["required_characters"] = ",".join(raw_required_characters + raw_required_traits)
    elif len(raw_required_characters) > 1:
        params["required_characters"] = ",".join(raw_required_characters)
    elif raw_required_characters and "energy cost" in descriptor_lc:
        params["required_characters"] = ",".join(raw_required_characters)
    elif raw_required_characters:
        params.setdefault("required_traits", ",".join(raw_required_characters))

    if cleaned:
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
    for branch in branches:
        branch_start = len(rules)
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

        # [Auto] When this card attacks... draw X card(s)
        m_attack_draw = _ATTACK_DRAW_RE.search(branch)
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

        # [Auto] At the end of a battle in which this card was used in a combo... play this card from your Drop...
        if _COMBO_FROM_HAND_BATTLE_END_PLAY_SELF_RE.search(branch):
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

        # [Activate: Main] ... : Draw N card(s).
        m_activate_main_draw = _ACTIVATE_MAIN_IF_DO_DRAW_RE.search(branch) or _ACTIVATE_MAIN_DRAW_RE.search(branch)
        if m_activate_main_draw and m_activate_main_optional_hand_warp_draw is None:
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

        # [Activate: Main/Battle] ... : Draw N card(s).
        m_activate_main_battle_draw = _ACTIVATE_MAIN_BATTLE_DRAW_RE.search(branch)
        if m_activate_main_battle_draw:
            amount = int(m_activate_main_battle_draw.group(1))
            extra = _extract_common_conditions(branch)
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

        m_activate_main_battle_owner_cards_power = _ACTIVATE_MAIN_BATTLE_CHOOSE_OWNER_CARDS_GAIN_POWER_FOR_TURN_RE.search(branch)
        if m_activate_main_battle_owner_cards_power:
            max_targets = int(m_activate_main_battle_owner_cards_power.group(1))
            descriptor = str(m_activate_main_battle_owner_cards_power.group(2) or "").strip().lower()
            power_delta = int(m_activate_main_battle_owner_cards_power.group(3))
            extra = _extract_common_conditions(branch)
            params = {
                "target_policy": "first",
                "target_scope": "owner_cards",
                "max_targets": max_targets,
                "power_delta": power_delta,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_buff_owner_battle_cards",
                    handler_params=params,
                    once_per_turn=once,
                    limit_per_turn=limit,
                )
            )
            rules.append(
                EffectRule(
                    trigger="self_activate_battle",
                    handler_id="activate_buff_owner_battle_cards",
                    handler_params=dict(params),
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
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="auto_look_top_add_up_to_one_to_hand_on_play",
                    handler_params=params,
                    once_per_turn=once,
                )
            )

        m_activate_main_add_from_deck = _ACTIVATE_MAIN_ADD_UP_TO_N_FROM_OWNER_DECK_TO_HAND_RE.search(branch)
        if m_activate_main_add_from_deck and not is_extra:
            max_targets = int(m_activate_main_add_from_deck.group(1))
            descriptor = m_activate_main_add_from_deck.group(2).lower()
            extra = _extract_common_conditions(branch)
            params = {
                "max_targets": max_targets,
                **_descriptor_filters(descriptor, branch),
                **extra,
            }
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

        if _ACTIVATE_MAIN_PLAY_SELF_FROM_HAND_RE.search(branch):
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

        m_activate_main_draw_play_self = _ACTIVATE_MAIN_DRAW_PLAY_SELF_AND_GAIN_KEYWORD_UNTIL_OPP_TURN_END_RE.search(branch)
        if m_activate_main_draw_play_self:
            amount = int(m_activate_main_draw_play_self.group(1))
            grant_keyword = " ".join(part.capitalize() for part in m_activate_main_draw_play_self.group(2).replace("-", " ").split())
            extra = _extract_common_conditions(branch)
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_draw_n_play_self_from_hand_and_gain_keyword_until_opponent_turn_end",
                    handler_params={"amount": amount, "grant_keyword": grant_keyword, **extra},
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
            rules.append(
                EffectRule(
                    trigger="self_activate_main",
                    handler_id="activate_send_up_to_n_opponent_battle_to_warp",
                    handler_params={"max_targets": max_targets, "target_policy": "first", **extra},
                    once_per_turn=once,
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

        m_play_send_opp_battle_warp = _PLAY_SEND_UP_TO_N_OPP_BATTLE_TO_WARP_RE.search(branch)
        if m_play_send_opp_battle_warp:
            max_targets = int(m_play_send_opp_battle_warp.group(1))
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {
                "max_targets": max_targets,
                "target_policy": "first",
                **extra,
            }
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
            requires_skill_less = ("skill-less" in descriptor) or ("skill less" in descriptor)
            rest_mode = "in rest mode" in branch
            negate_skills = ("with its skills negated" in branch) or ("with their skills negated" in branch)
            m_discard = re.search(r"discard (\d+) card from your hand:", branch)
            discard_before = int(m_discard.group(1)) if m_discard else 0
            extra = _extract_common_conditions(branch)
            params: dict[str, int | str | bool] = {"max_targets": max_targets, "max_cost": max_cost, **extra}
            if colors:
                params["allowed_colors"] = ",".join(colors)
            if required_card_type:
                params["required_card_type"] = required_card_type
            if requires_skill_less:
                params["requires_skill_less"] = True
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

