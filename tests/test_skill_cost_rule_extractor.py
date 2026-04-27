from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import uuid

from src.game.skill_cost_rule_extractor import extract_skill_cost_rules_from_card
from src.game.skill_costs import load_skill_cost_rules_json, save_skill_cost_rules_json
from src.game import Action, ActionType, CardInstance, RulesEngine, TurnPhase


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _to_main(engine: RulesEngine, state):
    while state.phase != TurnPhase.MAIN:
        state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=state.active_player))
    return state


def test_extract_counter_hidden_mode_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Play][Limit 1] Choose 1 of your white Battle Cards and switch it to Hidden Mode: "
            "Play this card, then switch the card that was switched to Hidden Mode by this skill to Revealed Mode at the end of the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_from_hand": [
            {
                "kind": "switch_owner_battle_to_hidden",
                "amount": 1,
                "allowed_colors": "white",
            }
        ]
    }


def test_extract_activate_hidden_mode_battle_or_energy_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main][Limit 1] Choose 1 white card in your Battle Area or energy and switch it to Hidden Mode: "
            "Choose up to 1 of your opponent's Battle Cards, KO it, and your white Leader gets +20000 power for the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "switch_owner_battle_or_energy_to_hidden",
                "amount": 1,
                "allowed_colors": "white",
            }
        ]
    }


def test_extract_activate_main_without_colon_hidden_mode_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[activate main][once per turn] Choose 1 of your white Battle Cards and switch it to Hidden Mode: "
            "Draw 1 card."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "switch_owner_battle_to_hidden",
                "amount": 1,
                "allowed_colors": "white",
            }
        ]
    }


def test_extract_activate_main_rest_self_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main][Limit 1] If your Leader is a green ≪Machine Mutant≫ card and you switch this card to Rest Mode: "
            "Draw 1 card, place up to 1 <Android 18> or <Cell> card-both green and with an energy cost of 1-from your deck or Drop under your Leader, then shuffle your deck if you looked through it."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "rest_self",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_main_choose_owner_battle_reference_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main] Choose 1 of your red Battle Cards: "
            "Choose one- "
            "The chosen card can attack Battle Cards in Active Mode for the turn. "
            "Choose 1 of your opponent's Battle Cards, and it gets -X power for the turn, where X is the power of the card chosen for this skill's skill cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main_hand": [
            {
                "kind": "choose_owner_battle_reference",
                "amount": 1,
                "allowed_colors": "red",
            }
        ]
    }


def test_extract_activate_main_hand_to_drop_and_send_self_to_warp_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main] Place 1 card from your hand in the Drop Area: "
            "Send this card to the Warp, and play it from the Warp in its owner's Battle Area at the beginning of your next turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_owner_hand_to_drop",
                "amount": 1,
            },
            {
                "kind": "send_self_to_warp",
                "amount": 1,
            },
        ]
    }


def test_extract_activate_main_send_self_from_hand_to_warp_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main] (Green), send this card from your hand to your Warp: "
            "At the end of your opponent's next turn, play the card you sent to your Warp with this skill from your Warp."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main_hand": [
            {
                "kind": "send_self_from_hand_to_warp",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_main_typo_owner_drop_self_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main]②, if your Leader Card is a ≪World Tournament≫ card and you place this card in it's owner's Drop Area: "
            "Choose up to 1 ≪World Tournament≫ card with an energy cost of 3 or less from your hand, send it to your Warp, "
            "and at the start of your next turn, play the card sent to your Warp by this skill from your Warp."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_self_to_drop",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_battle_hidden_mode_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Battle][Once per turn](1), choose 1 white card in your Battle Area and switch it to Hidden Mode: "
            "This card gets +10000 power and [Double Strike] for the battle."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_battle": [
            {
                "kind": "switch_owner_battle_to_hidden",
                "amount": 1,
                "allowed_colors": "white",
            }
        ]
    }


def test_extract_activate_battle_drop_hidden_mode_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Battle][Limit 1] Choose 1 Hidden Mode card in your Battle Area and place it into its owner's Drop: "
            "Choose up to 1 of your opponent's Battle Cards and KO it."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_battle": [
            {
                "kind": "send_owner_hidden_mode_battle_to_drop",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_battle_send_self_from_combo_to_drop_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Battle] Place this card in its owner's Drop Area from your Combo Area: "
            "Choose up to 1 Battle Card with a combo cost of 0 in your opponent's Combo Area and place it in its owner's Drop Area."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_battle_combo": [
            {
                "kind": "send_self_from_combo_to_drop",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_battle_send_self_from_leader_under_to_warp_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Battle][Limit 1] Send this card from under your <Super 17> Z-Leader to its owner's Warp: "
            "Up to 1 of your Leaders gets +5000 power for the battle."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_battle_leader_under": [
            {
                "kind": "send_self_from_leader_under_to_warp",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_battle_discard_hand_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Battle][Limit 1] If your Leader's back side is a red <Super 17> card and you discard 1 card from your hand: "
            "Use this card from your Drop in a combo."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_battle": [
            {
                "kind": "send_owner_hand_to_drop",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_battle_energy_to_drop_skill_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Battle][Once per turn] Place 1 of your energy into its owner's Drop: "
            "Choose up to 1 of your blue â‰ªAndroidâ‰« cards and it gets +10000 power for the battle."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_battle": [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_main_choose_owner_battle_to_drop_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main][Once per turn] Choose 1 of your ?Red Ribbon Army? cards and place it in its owner's Drop Area: "
            "This card gains [Critical] and [Double Strike] for the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules["activate_main"][0]["kind"] == "send_other_battle_to_drop"
    assert rules["activate_main"][0]["amount"] == 1


def test_extract_zamasu_scheme_activate_main_costs_are_source_zone_specific() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Empower Black 2] [Activate: Main][Limit 1] If your Leader is a black <Goku Black> card, "
            "you have 2 or more energy, and you place 1 of your Z-Energy into its owner's Drop : "
            "Play this card with 0 markers on it from your Warp. "
            "[UNISON +1][Activate: Main] Send 1 card from your hand to its owner's Warp : "
            "Add up to 1 black <Zamasu> card with an energy cost of 7 from your Warp to your hand."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main_warp": [
            {
                "kind": "send_owner_z_energy_to_drop",
                "amount": 1,
            }
        ],
        "activate_main_unison": [
            {
                "kind": "send_owner_hand_to_warp",
                "amount": 1,
            }
        ],
    }


def test_extract_activate_main_send_self_to_warp_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main] Send this card to the Warp: "
            "At the beginning of your next turn, if your Leader Card is ≪Universe 6≫, play this card from the Warp in its owner's Battle Area."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules["activate_main"] == [{"kind": "send_self_to_warp", "amount": 1}]


def test_extract_auto_on_play_z_energy_to_drop_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Auto] Place 2 of your Z-Energy into their owner's Drop: When this card is played, activate this skill. "
            "During this turn, the next time you play a blue <Gogeta: Br> card with [Union], it gains [Barrier] for the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "auto_on_play_battle": [
            {
                "kind": "send_owner_z_energy_to_drop",
                "amount": 2,
            }
        ]
    }


def test_extract_auto_on_play_hand_to_bottom_deck_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Auto][Limit 1] If your Leader is a yellow <Whis> card and you place 1 card from your hand at the bottom of your deck: "
            "When this card is played, send up to 2 skill-less Battle Cards with 15000 power and different character names from your deck to your Warp, "
            "shuffle your deck, and at the end of your opponent's next turn, play up to 1 of the cards sent to your Warp by this skill in your Battle Area, "
            "and you may add the remaining cards to your hand."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "auto_on_play_battle": [
            {
                "kind": "send_owner_hand_to_bottom_deck",
                "amount": 1,
            }
        ]
    }


def test_extract_plain_unison_marker_activate_costs_for_main_and_battle() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[+1][Activate: Main] You may choose 1 card in your hand and send it to your Warp. If you do, draw 1 card. "
            "[-2][Activate: Battle] For each card in your Warp, this card gets +5000 power for the battle."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules["activate_main_unison"] == [{"kind": "add_markers", "amount": 1}]
    assert rules["activate_battle_unison"] == [{"kind": "remove_markers", "amount": 2}]


def test_extract_jaguars_island_challenge_stage_unison_costs() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Auto] When you activate a red ≪Earthling≫ Extra from your hand, add 1 marker to this card. "
            "[UNISON -3][Activate: Main/Battle] If your Leader is a red <Krillin> card and you place 4 red ≪Earthling≫ Extras from your Drop at the bottom of their owner's deck : "
            "The next time you activate an [Activate] skill on a red Extra from your hand during this turn, reduce the skill cost by {1}."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main_unison": [
            {"kind": "remove_markers", "amount": 3},
            {
                "kind": "send_owner_drop_to_bottom_deck",
                "amount": 4,
                "allowed_colors": "red",
                "required_traits": "earthling",
                "required_card_types": "EXTRA",
            },
        ],
        "activate_battle_unison": [
            {"kind": "remove_markers", "amount": 3},
            {
                "kind": "send_owner_drop_to_bottom_deck",
                "amount": 4,
                "allowed_colors": "red",
                "required_traits": "earthling",
                "required_card_types": "EXTRA",
            },
        ],
    }


def test_extract_activate_main_discard_self_from_hand_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main][Limit 1] If your Leader is a red <Krillin> card and you discard this card from your hand : "
            "Add up to 1 red <Son Goten> card with an energy cost of 3 and [EX-Evolve] from your deck to your hand, then shuffle your deck."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main_hand": [
            {
                "kind": "send_self_from_hand_to_drop",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_main_discard_self_from_hand_cost_rule_with_colon_in_leader_name() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main](Green), if your Leader is a green <Son Gohan: Childhood> and you discard this card from your hand: "
            "Choose up to 1 {Hyperbolic Time Chamber} in your Battle Area, switch it to Rest Mode, place 1 {SS Vegeta, Arrogance} "
            "and 1 {SS Trunks, Mysterious Future Warrior} from your hand under the chosen card, then shuffle your deck."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main_hand": [
            {
                "kind": "send_self_from_hand_to_drop",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_main_place_self_in_drop_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main](Green), place this card in your Drop: "
            "Draw 1 card and play up to 1 {SS Son Gohan, Showing the Results of Training} under a {Hyperbolic Time Chamber} in your Battle Area."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_self_to_drop",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_main_place_self_in_owner_drop_area_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main] If your Leader Card is a green <Beerus> or green <Champa> card and you place this card in its owner's Drop Area: "
            "Choose one?\n"
            "・Activate up to 1 {The Nameless Planet} from your deck, then shuffle your deck."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_self_to_drop",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_main_battle_energy_to_drop_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main/Battle][Once per turn] Place 1 of your energy into its owner's Drop: "
            "Choose up to 1 of your blue ≪Red Ribbon Army≫ cards and it gets +5000 power for the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": 1,
            }
        ],
        "activate_battle": [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": 1,
            }
        ],
    }


def test_extract_activate_main_energy_to_drop_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main] Place 2 of your energy into its owner's Drop and remove this card from the game: "
            "Choose all of your opponent's Battle Cards and KO them."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": 2,
            },
            {
                "kind": "send_self_to_removed",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_battle_remove_self_to_removed_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Battle] If your Leader's character name includes <SH>, you have 3 or more energy, and you remove this card from the game: "
            "Choose up to 1 of your blue Battle Cards and it gets +10000 power for the battle."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_battle": [
            {
                "kind": "send_self_to_removed",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_main_battle_remove_self_to_removed_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main/Battle][Limit 1] If your Leader is a <Janemba> card, "
            "you have a blue <Janemba> card with an energy cost of 6 or more in play, and you remove this card from the game: "
            "Place up to 1 {Demonic Blade} or {Dimensional Hole} from your Z-Deck in the Battle Area."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_self_to_removed",
                "amount": 1,
            }
        ],
        "activate_battle": [
            {
                "kind": "send_self_to_removed",
                "amount": 1,
            }
        ],
    }


def test_extract_activate_main_hand_to_bottom_deck_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main][Limit 1](Green), place 1 card from your hand at the bottom of your deck: "
            "Play this card from under {Cell, Return of the Ultimate Lifeform}."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_owner_hand_to_bottom_deck",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_main_remove_self_in_drop_and_discard_hand_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main](Green), if your Leader is a green <Son Gohan: Childhood> Z-Leader, "
            "you remove this card in the Drop from the game, and you discard 1 card from your hand: "
            "Play up to 1 {SS Vegeta, Arrogance} from your Drop and that card gets +10000 power for the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules["activate_main"] == [
        {
            "kind": "send_self_to_removed",
            "amount": 1,
        },
        {
            "kind": "discard_hand",
            "amount": 1,
        },
    ]


def test_extract_activate_main_z_energy_to_drop_and_remove_self_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main] Place 1 of your Z-Energy in your Drop, and remove this card from the game: "
            "If your Leader is a blue <Frieza's Army> card and you have 2 or more blue Z-Extra Cards in your Battle Area, "
            "play 2 Ghost Tokens with 15000 power, then choose all of your Ghost Tokens and they gain [Revenge] until the end of your opponent's next turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_owner_z_energy_to_drop",
                "amount": 1,
            },
            {
                "kind": "send_self_to_removed",
                "amount": 1,
            },
        ]
    }


def test_extract_activate_main_remove_two_opponent_clone_tokens_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main] Choose 2 Clone Tokens in your opponent's Battle Area and remove them from the game: "
            "Play this card from your hand."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_opponent_battle_to_removed",
                "amount": 2,
                "required_name_contains": "CLONE TOKEN",
                "required_card_types": "BATTLE",
            }
        ]
    }


def test_extract_activate_main_remove_three_opponent_clone_tokens_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main][Limit 1](Blue), if you have 3 or more energy and you choose 3 of your opponent's Clone Tokens and remove them from the game: "
            "Play this card from your hand."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_opponent_battle_to_removed",
                "amount": 3,
                "required_name_contains": "CLONE TOKEN",
                "required_card_types": "BATTLE",
            }
        ]
    }


def test_extract_activate_main_remove_three_opponent_clone_tokens_blocker_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Blocker]<br>[Activate: Main][Limit 1] Choose 3 of your opponent's Clone Tokens and remove them from the game: "
            "Play this card from your hand."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_opponent_battle_to_removed",
                "amount": 3,
                "required_name_contains": "CLONE TOKEN",
                "required_card_types": "BATTLE",
            }
        ]
    }


def test_extract_exact_clone_token_unison_marker_and_removal_cost_rules() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main] If you don't have a Unison Card in play and you choose 1 of your opponent's Clone Tokens and remove it from the game: "
            "Play this card from your hand in Rest Mode with a marker on it.<br>"
            "[+2][Activate: Main] 1 of your mono-blue Leader Cards gets +5000 power for the turn; your opponent's Clone Tokens can't attack during your opponent's next turn.<br>"
            "[-4][Activate: Battle] This card gets +11000 power and [Double Strike] for the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_opponent_battle_to_removed",
                "amount": 1,
                "required_name_contains": "CLONE TOKEN",
                "required_card_types": "BATTLE",
            }
        ],
        "activate_main_unison": [{"kind": "add_markers", "amount": 2}],
        "activate_battle_unison": [{"kind": "remove_markers", "amount": 4}],
    }


def test_extract_exact_clone_token_combo_draw_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Auto] If it's your turn, choose 1 Clone Token in your opponent's Battle Area and remove it from the game: "
            "When you combo with this card, draw 1 card."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "auto_on_combo_battle": [
            {
                "kind": "send_opponent_battle_to_removed",
                "amount": 1,
                "required_name_contains": "CLONE TOKEN",
                "required_card_types": "BATTLE",
            }
        ]
    }


def test_extract_exact_clone_token_combo_power_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Auto] If it's your turn, choose 1 Clone Token in your opponent's Battle Area and remove it from the game: "
            "When you combo with this card, this card gets +5000 combo power for the duration of the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "auto_on_combo_battle": [
            {
                "kind": "send_opponent_battle_to_removed",
                "amount": 1,
                "required_name_contains": "CLONE TOKEN",
                "required_card_types": "BATTLE",
            }
        ]
    }


def test_extract_exact_pincer_attack_android_18_combo_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Auto] If your Leader Card is a blue <Android 18> card and you choose 1 of your opponent's Clone Tokens and remove it from the game: "
            "When this card is used in a combo from your hand, add up to 1 {Supreme Technique Krillin} from your deck to your hand, then shuffle your deck.<br>"
            "[Auto](Blue), if your Leader Card is a blue <Android 18> card: At the end of a battle in which this card is used in a combo from your hand, play this card from your Drop Area."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "auto_on_combo_battle": [
            {
                "kind": "send_opponent_battle_to_removed",
                "amount": 1,
                "required_name_contains": "CLONE TOKEN",
                "required_card_types": "BATTLE",
            }
        ]
    }


def test_extract_exact_supreme_technique_krillin_combo_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Blocker] (When one of your other cards is attacked, you may switch this card to Rest Mode and change the target of the attack to this card.)<br>"
            "[Auto] If it's your turn, choose 1 Clone Token from your opponent's Battle Area and remove it from the game: "
            "When you combo with this card, choose up to 1 attacking <Android 18> card and it gains [Double Strike] for the duration of the battle. <br>"
            "[Auto](Blue), during your turn: When you combo with this card from your hand with an <Android 18> card in battle, play this card at the end of the battle."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "auto_on_combo_battle": [
            {
                "kind": "send_opponent_battle_to_removed",
                "amount": 1,
                "required_name_contains": "CLONE TOKEN",
                "required_card_types": "BATTLE",
            }
        ]
    }


def test_extract_exact_supreme_technique_son_goku_play_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Blocker] <br>[Arrival Blue/Green](Blue) (Play this card from your hand when you have blue and green cards in your Combo Area.)<br>"
            "[Energy-Exhaust] (If this card is placed in an Energy Area from any area, it must be placed there in Rest Mode.)<br>"
            "[Auto] Choose 2 Clone Tokens in your opponent's Battle Area and remove them from the game: "
            "When you play this card, your opponent chooses 1 card from their hand and places it in their Drop Area."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "auto_on_play_battle": [
            {
                "kind": "send_opponent_battle_to_removed",
                "amount": 2,
                "required_name_contains": "CLONE TOKEN",
                "required_card_types": "BATTLE",
            }
        ]
    }


def test_extract_activate_main_discard_hand_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main] Discard 1 card from your hand: This card gets +10000 power for the turn. "
            "Choose up to 1 of your opponent's Battle Cards and it gets -20000 power for the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "discard_hand",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_main_direct_discard_yellow_hand_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main] If your Leader Card is a yellow &lt;Gotenks: Adolescence&gt; card and you choose 1 yellow card in your hand and discard it: "
            "Add this card from your Drop Area to your hand, and you can't activate the [Activate: Main] skill on copies of this card for the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "discard_hand",
                "amount": 1,
                "allowed_colors": "yellow",
            }
        ]
    }


def test_extract_activate_main_spirit_boost_and_drop_to_warp_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main][Limit 1][Spirit Boost 1] Send 3 cards from your Drop to their owner's Warp : "
            "Switch this card to Active Mode."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "remove_owner_unison_markers",
                "amount": 1,
            },
            {
                "kind": "send_owner_drop_to_warp",
                "amount": 3,
            },
        ]
    }


def test_extract_activate_main_remove_total_drop_and_warp_to_removed_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main][Once per turn] If you have 3 or more energy and you remove 10 total cards in your Drop and Warp from the game: "
            "This card gets +10000 power and [Double Strike] for the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_owner_drop_and_warp_to_removed",
                "amount": 10,
            }
        ]
    }


def test_extract_activate_main_remove_opponent_clone_token_to_removed_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main] Remove 1 of your opponent's Clone Tokens from the game: Play this card from your hand or Drop Area."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_opponent_battle_to_removed",
                "amount": 1,
                "required_name_contains": "CLONE TOKEN",
                "required_card_types": "BATTLE",
            }
        ]
    }


def test_extract_exact_bt20_android_21_front_activate_life_to_hand_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Permanent] You can't activate Extras, and during your turn, you can't use skills to play Battle Cards. "
            "[Auto] If you have an <Android 21> Z-Battle Card in play: At the end of your turn, switch up to 1 of your blue energy to Active Mode. "
            "[Activate: Main][Once per turn] Add 1 card from your life to your hand: Look at up to 5 cards from the top of your deck, add up to 1 blue ≪Android≫ card among them to your hand, shuffle your deck, and this card gets +5000 power for the turn. "
            "[Awaken] When your life is at 4 or less: Draw 1 card, and switch up to 1 of your energy to Active Mode."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules["activate_main"] == [{"kind": "add_life_to_hand", "amount": 1}]


def test_extract_activate_main_unison_remove_owner_saibaiman_token_to_removed_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[-1][Activate: Main] Remove 1 of your Saibaiman Tokens from the game: "
            "Choose up to 1 of your opponent's Battle Cards with an energy cost of 2 or less and place it at the bottom of its owner's deck."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main_unison": [
            {
                "kind": "remove_markers",
                "amount": 1,
            },
            {
                "kind": "send_owner_battle_to_removed",
                "amount": 1,
                "required_name_contains": "SAIBAIMAN TOKEN",
                "required_card_types": "BATTLE",
            },
        ]
    }


def test_extract_activate_main_battle_send_owner_battle_to_warp_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main/Battle] Choose 1 of your black Battle Cards with an energy cost of 3 and send it to its owner's Warp: "
            "Play this card from your Drop Area."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_main": [
            {
                "kind": "send_owner_battle_to_warp",
                "amount": 1,
                "allowed_colors": "black",
                "required_card_types": "BATTLE",
                "exact_energy_cost": 3,
            }
        ],
        "activate_battle": [
            {
                "kind": "send_owner_battle_to_warp",
                "amount": 1,
                "allowed_colors": "black",
                "required_card_types": "BATTLE",
                "exact_energy_cost": 3,
            }
        ],
    }


def test_extract_counter_alternate_rest_hidden_battle_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack] Negate the attack. "
            "[Permanent] If your Leader is white, you can activate this card's [Counter] skill from your hand by "
            "switching 1 Hidden Mode card in your Battle Area to Rest Mode instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "rest_owner_hidden_mode_battle",
                "amount": 1,
                "required_leader_colors": "white",
            }
        ]
    }


def test_extract_counter_alternate_life_to_hand_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack] Negate the attack. "
            "[Permanent][Sparking 5] You can activate this card's [Counter] skill from your hand by adding 1 card from your life to your hand "
            "instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "add_life_to_hand",
                "amount": 1,
                "requires_sparking": 5,
            }
        ]
    }


def test_extract_counter_alternate_life_to_hand_with_life_threshold_and_leader_color() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack] Negate the attack. "
            "[Permanent] If your life is at 5 or less, you can activate this card's [Counter] skill from your hand by "
            "adding a card from your life to your hand instead of paying its energy cost. "
            "If your Leader Card is mono-black, do something else."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "add_life_to_hand",
                "amount": 1,
                "requires_life_at_most": 5,
                "required_leader_colors": "black",
            }
        ]
    }


def test_extract_counter_alternate_life_to_hand_with_energy_color_requirement() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack] Negate the attack and play this card. "
            "[Permanent] If there are 4 or more colors in your energy, you can activate this card's [Counter] skill "
            "from your hand by adding 1 card from your life to your hand instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "add_life_to_hand",
                "amount": 1,
                "requires_energy_colors_at_least": 4,
            }
        ]
    }


def test_extract_counter_alternate_life_to_hand_with_multicolor_energy_requirement() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Play] Do something. "
            "[Permanent] If you have a multicolor card in your energy and your life is at 4 or less, "
            "you can activate this card's [Counter] skill from your hand by adding a card from your life to your hand instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "add_life_to_hand",
                "amount": 1,
                "requires_life_at_most": 4,
                "requires_multicolor_in_energy": True,
            }
        ]
    }


def test_extract_counter_alternate_life_to_hand_with_only_black_energy_requirement() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Play] Do something. "
            "[Permanent] If you have only black cards in your energy and your life is at 4 or less, "
            "you can activate this card's [Counter] skill from your hand by adding a card from your life to your hand instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "add_life_to_hand",
                "amount": 1,
                "requires_life_at_most": 4,
                "requires_only_energy_colors": "black",
            }
        ]
    }


def test_extract_counter_alternate_life_to_hand_with_leader_trait_and_all_energy_rested() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack] Negate the attack. "
            "[Permanent] If your Leader is a yellow <<Fierce Foe>> card and all of your energy is in Rest Mode, "
            "you can activate this card's [Counter] skill from your hand by adding 1 card from your life to your hand instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "add_life_to_hand",
                "amount": 1,
                "required_leader_colors": "yellow",
                "required_leader_traits": "fierce foe",
                "requires_all_energy_rested": True,
            }
        ]
    }


def test_extract_counter_alternate_life_to_hand_with_owner_heroic_in_play() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack] Negate the attack. "
            "[Permanent] If you have a yellow ≪Heroic≫ card in play, "
            "you can activate this card's [Counter] skill from your hand by adding 1 card from your life to your hand instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "add_life_to_hand",
                "amount": 1,
                "requires_owner_in_play": True,
                "owner_in_play_allowed_colors": "yellow",
                "owner_in_play_required_traits": "heroic",
            }
        ]
    }


def test_extract_counter_alternate_life_to_hand_with_owner_vegito_cost_requirement() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack][Limit 1] If your Leader is a yellow <Vegito> card: Negate the attack. "
            "[Permanent] If you have a yellow <Vegito> card with an energy cost of 5 or more in play, "
            "you can activate this card's [Counter] skill from your hand by adding 1 card from your life to your hand instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "add_life_to_hand",
                "amount": 1,
                "required_leader_colors": "yellow",
                "required_leader_traits": "vegito",
                "requires_owner_in_play": True,
                "owner_in_play_allowed_colors": "yellow",
                "owner_in_play_required_characters": "vegito",
                "owner_in_play_min_energy_cost": 5,
            }
        ]
    }


def test_extract_counter_alternate_life_to_hand_with_owner_multicolor_extra_in_battle_area() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack][Limit 1] Negate the attack and play this card. "
            "[Permament] If you have a Red/Blue multicolor Extra in your Battle Area, "
            "you can activate this card's [Counter] skill from your hand by adding 1 card from our life o your hand instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "add_life_to_hand",
                "amount": 1,
                "requires_owner_battle_area": True,
                "owner_battle_area_allowed_colors": "blue,red",
                "owner_battle_area_required_card_types": "EXTRA",
                "owner_battle_area_requires_multicolor": True,
            }
        ]
    }


def test_extract_counter_alternate_life_to_hand_with_drop_to_warp_follow_up_cost() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack][Limit 1] Play this card. "
            "[Permanent] If your Leader is red, you can activate this card's [Counter] skill from your hand by "
            "adding 1 card from your life to your hand and sending 2 ≪Saiyan≫ cards from your Drop to their owner's Warp instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "add_life_to_hand",
                "amount": 1,
                "required_leader_colors": "red",
            },
            {
                "kind": "send_owner_drop_to_warp",
                "amount": 2,
                "required_traits": "saiyan",
            },
        ]
    }


def test_extract_counter_alternate_life_to_hand_with_face_up_z_deck_requirement() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack][Limit 1] Negate the attack and play this card. "
            "[Permanent] If you have 3 or more face-up \u226aBoujack Brigade\u226b cards in your Z-Deck, "
            "you can activate this card's [Counter] skill from your hand by adding 1 card from your life to your hand instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "add_life_to_hand",
                "amount": 1,
                "requires_owner_face_up_z_deck_count_at_least": 3,
                "owner_face_up_z_deck_required_traits": "boujack brigade",
            }
        ]
    }


def test_extract_counter_alternate_drop_to_warp_only_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Play][Limit 1] If your Leader is a \u226aPower Wish\u226b card: Play this card. "
            "[Permanent] If your life is at 4 or less, you can activate this card's [Counter] skill from your hand by "
            "sending 2 \u226aPower Wish\u226b cards from your Drop to its owner's Warp instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "send_owner_drop_to_warp",
                "amount": 2,
                "required_leader_traits": "power wish",
                "requires_life_at_most": 4,
                "required_traits": "power wish",
            }
        ]
    }


def test_extract_counter_direct_discard_yellow_hand_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Counter] If your Leader Card is red and you choose 1 yellow card in your hand and place it in your Drop Area: "
            "Negate the [Counter: Attack] skill."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_from_hand": [
            {
                "kind": "discard_hand",
                "amount": 1,
                "allowed_colors": "yellow",
                "required_leader_colors": "red",
            }
        ]
    }


def test_extract_counter_alternate_send_all_drop_to_warp_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack][Limit 1] If your Leader is black: Negate the attack and play this card. "
            "[Permanent] If your life is at 4 or less and you have 5 or more cards in your Drop, "
            "you can activate this card's [Counter] skill from your hand by sending all the cards in your Drop to their owner's Warp instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "send_all_owner_drop_to_warp",
                "amount": 1,
                "required_leader_colors": "black",
                "requires_life_at_most": 4,
            }
        ]
    }


def test_extract_counter_alternate_return_battle_to_hand_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack][Limit 1] Negate the attack and play this card. "
            "[Permanent] You can activate this card's [Counter] skill from your hand by returning 1 {Gods of Dreams Dragon Ball} from your Battle Area to your hand instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "return_owner_battle_to_hand",
                "amount": 1,
                "required_name_contains": "gods of dreams dragon ball",
            }
        ]
    }


def test_extract_counter_alternate_rest_leader_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Permanent] You can activate this card's [Counter] skill from your hand by switching your \u226aScientist\u226b Leader to Rest Mode instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "rest_owner_leader",
                "amount": 1,
                "required_leader_traits": "scientist",
            }
        ]
    }


def test_extract_counter_alternate_reduced_energy_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Permanent] If your Leader is a <King Piccolo> card and you have 3 or more Z-Energy, "
            "you can activate this card's [Counter] skill from your hand by paying (1) instead of its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "rest_energy",
                "amount": 1,
                "required_leader_traits": "king piccolo",
                "requires_z_energy_at_least": 3,
            }
        ]
    }


def test_extract_counter_alternate_hidden_battle_to_drop_with_opponent_energy_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Permanent] If your Leader is white and your opponent has 3 or more energy, "
            "you can activate this card's [Counter] skill from your hand by choosing 1 Hidden Mode card in your Battle Area and placing it into its owner's Drop instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "send_owner_hidden_mode_battle_to_drop",
                "amount": 1,
                "required_leader_colors": "white",
                "requires_opponent_energy_at_least": 3,
            }
        ]
    }


def test_extract_counter_alternate_reduce_owner_battle_power_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack] Choose up to 1 of your Leader Cards or Battle Cards and it gets +100000 power for the battle. "
            "[Permanent] If your Leader Card is red, you can activate this card's [Counter] skill from your hand by choosing 2 of your non-token Battle Cards and reducing their power by -10000 for the turn instead of paying its energy cost."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "reduce_owner_battle_power_for_turn",
                "amount": 2,
                "required_leader_colors": "red",
                "required_card_types": "BATTLE",
                "power_delta": -10000,
            }
        ]
    }


def _workspace_temp_catalog_path(name: str) -> Path:
    directory = Path("artifacts") / "_tmp" / f"{name}_{uuid.uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "skill_cost_catalog.json"


def test_engine_loads_skill_cost_catalog_from_path() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_catalog")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900302: {
                "counter_from_hand": [
                    {"kind": "switch_owner_battle_to_hidden", "amount": 1, "allowed_colors": "white"}
                ]
            }
        },
    )
    loaded = load_skill_cost_rules_json(catalog_path)
    assert 900302 in loaded
    assert loaded[900302]["counter_from_hand"].steps[0].kind == "switch_owner_battle_to_hidden"

    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790001, card_id=601, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].battle_area.append(CardInstance(instance_id=790002, card_id=602, owner_id=2, card_type="BATTLE", color="White"))
    state.players[2].hand.append(
        CardInstance(
            instance_id=790003,
            card_id=900302,
            owner_id=2,
            card_type="BATTLE",
            color="White",
            energy_cost=0,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw="[Counter: Play] Choose 1 of your white Battle Cards and switch it to Hidden Mode: Play this card.",
        )
    )

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_extract_auto_on_opponent_combo_z_energy_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Auto] Place 2 of your Z-Energy into their owner's Drop: "
            "When your opponent uses cards in a combo, your opponent places 1 card from their hand at the bottom of their deck, "
            "then you negate this skill for the battle."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "auto_on_opponent_combo_battle": [
            {
                "kind": "send_owner_z_energy_to_drop",
                "amount": 2,
            }
        ]
    }


def test_extract_auto_on_self_drop_energy_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Auto]{1}, if your Leader's back side is {SSG Son Goku, Surge of Divinity}: "
            "When this card is placed into its owner's Drop from your hand or from under your Leader by your Leader's skill, "
            "draw 1 card and play this card from your Drop with 1 marker on it."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "auto_on_self_drop": [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": 1,
            }
        ]
    }


def test_extract_auto_on_combo_single_energy_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Auto](Blue), during your turn: "
            "When you combo with this card from your hand with an <Android 18> card in battle, play this card at the end of the battle."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "auto_on_combo_battle": [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": 1,
                "allowed_colors": "blue",
            }
        ]
    }


def test_extract_auto_on_combo_leader_under_to_drop_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Auto][Limit 1] If your Leader is a blue <Android 18> card and you place 1 non-Leaders from under your Leader in its owner's Drop: "
            "When this card is used in a combo, choose up to 1 of your <Krillin> or <Android 18> cards and it gets +1000 power for the battle."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "auto_on_combo_battle": [
            {
                "kind": "send_owner_leader_under_to_drop",
                "amount": 1,
                "forbidden_card_types": "LEADER,Z-LEADER",
            }
        ]
    }


def test_extract_auto_on_combo_circled_generic_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Auto] When this card is played, draw 1 card.<br>"
            "[Auto] \u2461, if it's your opponent's turn: When this card is used in a combo from your Battle Area, "
            "play 4 Multi-Form Tokens. (Multi-Form Tokens have 10000 power, 0 combo cost, and 5000 combo power.)"
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "auto_on_combo_battle": [
            {
                "kind": "send_owner_energy_to_drop",
                "amount": 2,
            }
        ]
    }


def test_extract_counter_alternate_leader_under_to_drop_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack][Limit 1] If your Leader is a blue <Android 18> card: Negate the attack and play this card. "
            "[Permanent] You can activate this card's [Counter] skill from your hand without paying its energy cost by placing 2 blue non-Leaders from under your Leader in their owners' Drops."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "send_owner_leader_under_to_drop",
                "amount": 2,
                "allowed_colors": "blue",
                "forbidden_card_types": "LEADER,Z-LEADER",
                "required_leader_colors": "blue",
                "required_leader_traits": "android 18",
            }
        ]
    }


def test_extract_counter_alternate_owner_battle_under_to_drop_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack] Negate the attack. "
            "[Permanent] You can activate this card's [Counter] skill from your hand without paying its energy cost by placing 1 card from under a {The Nameless Planet} in your Battle Area in its owner's Drop Area instead."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "send_owner_battle_under_to_drop",
                "amount": 1,
                "required_host_name_contains": "THE NAMELESS PLANET",
            }
        ]
    }


def test_extract_absorption_of_doom_counter_alternate_discard_other_black_hand_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack] If your Leader Card is a black <Fin> card: Negate the attack. "
            "Additionally, if your opponent has a skill-less Battle Card or Unison Card in play, they can only attack two more times for the turn."
            "[Permanent] If your opponent has 2 or more Battle Cards in play, you can activate this card's [Counter] skill from your hand "
            "without paying its energy cost by choosing 1 other black card in your hand and discarding it."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "discard_hand",
                "amount": 1,
                "allowed_colors": "black",
                "exclude_source_card": True,
                "required_leader_colors": "black",
                "required_leader_traits": "fin",
                "requires_opponent_battle_cards_at_least": 2,
            }
        ]
    }


def test_extract_dyspo_thwarting_the_enemy_counter_alternate_spirit_boost_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack][Limit 1] If your Leader Card is red: Negate the attack, then play this card in Rest Mode. "
            "If you negated a Leader Card's attack with this skill, your opponent can't attack with their Leader Card for the turn."
            "[Permanent] You can activate this card's [Counter] skill from your hand without paying its energy cost by paying the cost for [Spirit Boost 2] instead."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_alternate_from_hand": [
            {
                "kind": "remove_owner_unison_markers",
                "amount": 2,
                "required_leader_colors": "red",
            }
        ]
    }


def test_extract_skill_hunter_towa_counter_spirit_boost_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack][Spirit Boost 1] Play this card.<br>"
            "[Permanent] If it's your opponent's turn and they have a skill-less Battle Card or Unison Card in play, reduce the energy cost of this card in your hand by 1.<br>"
            "[Auto] If your Leader Card is a black &lt;Fin&gt; card: When this card is played, choose up to 1 of your opponent's Battle Cards with an energy cost of 4 or less and place it under your Leader Card."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_from_hand": [
            {
                "kind": "remove_owner_unison_markers",
                "amount": 1,
            }
        ]
    }


def test_extract_counter_spirit_boost_x_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack][Spirit Boost X] (Remove X markers from your Unison Card to activate this skill.) "
            "If your Leader Card is a red ≪Universe 11≫ card: Negate the attack."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "counter_from_hand": [
            {
                "kind": "remove_owner_unison_markers",
                "amount": 1,
            }
        ]
    }


def test_extract_activate_battle_z_energy_under_self_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Battle][Once per turn] (1), place 1 ≪Android≫ card from your Z-Energy under this card: "
            "Draw 1 card, switch this card to Active Mode, then choose up to 1 of your opponent's Battle Cards and it gets -20000 power for the turn."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "activate_battle": [
            {
                "kind": "send_owner_z_energy_under_self",
                "amount": 1,
                "required_traits": "android",
            }
        ]
    }


def test_extract_auto_on_owner_combo_spirit_boost_cost_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Auto][Once per turn][Spirit Boost 1] "
            "When one of your skill-less Battle Cards is used in a combo, it gets +4000 combo power for the battle, then draw 1 card."
        )
    )
    rules = extract_skill_cost_rules_from_card(card)
    assert rules == {
        "auto_on_owner_combo_battle": [
            {
                "kind": "remove_owner_unison_markers",
                "amount": 1,
            }
        ]
    }


def test_engine_uses_catalog_for_counter_alternate_hidden_battle_cost() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_catalog")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900303: {
                "counter_alternate_from_hand": [
                    {"kind": "rest_owner_hidden_mode_battle", "amount": 1, "required_leader_colors": "white"}
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[2].leader_area.color = "White"
    state.players[1].hand = [CardInstance(instance_id=790021, card_id=621, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].battle_area.append(
        CardInstance(instance_id=790022, card_id=622, owner_id=2, card_type="BATTLE", color="White", hidden_mode=True)
    )
    state.players[2].hand.append(
        CardInstance(
            instance_id=790023,
            card_id=900303,
            owner_id=2,
            card_type="EXTRA",
            color="White",
            energy_cost=1,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Negate the attack.",
        )
    )

    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_owner_battle_under_cost() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_owner_battle_under")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900305: {
                "counter_alternate_from_hand": [
                    {
                        "kind": "send_owner_battle_under_to_drop",
                        "amount": 1,
                        "required_host_name_contains": "THE NAMELESS PLANET",
                    }
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790041, card_id=641, owner_id=1, card_type="BATTLE", energy_cost=0)]
    host = CardInstance(
        instance_id=790042,
        card_id=900306,
        owner_id=2,
        card_type="EXTRA",
        color="Green",
    )
    host.stacked_card_ids = (790043,)
    state.players[2].battle_area.append(host)
    engine._card_cache[(900306, "front")] = engine._build_card_runtime_data(
        SimpleNamespace(
            card_name="The Nameless Planet",
            power_int=0,
            card_type="EXTRA",
            card_color="Green",
            energy_cost_int=1,
            combo_cost_int=0,
            combo_power_int=0,
            keywords=[],
            counter_modes=[],
            skill_text_raw="",
            card_traits=[],
            card_character=[],
        ),
        side="front",
    )
    state.players[2].hand.append(
        CardInstance(
            instance_id=790044,
            card_id=900305,
            owner_id=2,
            card_type="EXTRA",
            color="Green",
            energy_cost=1,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Negate the attack.",
        )
    )

    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_life_threshold_requirement() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_life_threshold")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900304: {
                "counter_alternate_from_hand": [
                    {"kind": "add_life_to_hand", "amount": 1, "requires_life_at_most": 5}
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790031, card_id=631, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand.append(
        CardInstance(
            instance_id=790032,
            card_id=900304,
            owner_id=2,
            card_type="EXTRA",
            color="Black",
            energy_cost=1,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Negate the attack.",
        )
    )

    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)

    while len(state.players[2].life) > 5:
        state.players[2].hand.append(state.players[2].life.pop(0))

    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_multicolor_energy_requirement() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_multicolor")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900305: {
                "counter_alternate_from_hand": [
                    {
                        "kind": "add_life_to_hand",
                        "amount": 1,
                        "requires_life_at_most": 4,
                        "requires_multicolor_in_energy": True,
                    }
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790041, card_id=641, owner_id=1, card_type="BATTLE", energy_cost=0)]
    while len(state.players[2].life) > 4:
        state.players[2].hand.append(state.players[2].life.pop(0))
    state.players[2].hand.append(
        CardInstance(
            instance_id=790042,
            card_id=900305,
            owner_id=2,
            card_type="EXTRA",
            color="Blue",
            energy_cost=1,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw="[Counter: Play] Do something.",
        )
    )

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    legal = engine.get_legal_actions(state, 2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)

    state.players[2].energy.append(CardInstance(instance_id=790043, card_id=643, owner_id=2, card_type="EXTRA", color="Blue/Red"))
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_leader_trait_and_all_energy_rested_requirement() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 2:
                return SimpleNamespace(
                    card_name="Mercenary Leader",
                    power_int=15000,
                    card_type="LEADER",
                    card_color="Yellow",
                    energy_cost_int=0,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_draw=False,
                    max_draw=None,
                    has_barrier=False,
                    z_energy_cost=None,
                    card_energy_cost="0",
                    card_skill_unstyled="",
                    card_traits_json='["Fierce Foe"]',
                    card_character_json="[]",
                )
            return SimpleNamespace(
                card_name="Card",
                power_int=15000,
                card_type="LEADER" if card_id == 1 else "BATTLE",
                card_color="Yellow",
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
                card_traits_json="[]",
                card_character_json="[]",
            )

    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_leader_trait_rested")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900306: {
                "counter_alternate_from_hand": [
                    {
                        "kind": "add_life_to_hand",
                        "amount": 1,
                        "required_leader_colors": "yellow",
                        "required_leader_traits": "fierce foe",
                        "requires_all_energy_rested": True,
                    }
                ]
            }
        },
    )
    engine = RulesEngine(card_repository=Repo(), skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790051, card_id=651, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].energy = [CardInstance(instance_id=790052, card_id=652, owner_id=2, card_type="EXTRA", color="Yellow", resting=False)]
    state.players[2].hand.append(
        CardInstance(
            instance_id=790053,
            card_id=900306,
            owner_id=2,
            card_type="EXTRA",
            color="Yellow",
            energy_cost=2,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Negate the attack.",
        )
    )

    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)

    state.players[2].energy[0].resting = True
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_owner_in_play_trait_requirement() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_owner_in_play_trait")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900307: {
                "counter_alternate_from_hand": [
                    {
                        "kind": "add_life_to_hand",
                        "amount": 1,
                        "requires_owner_in_play": True,
                        "owner_in_play_allowed_colors": "yellow",
                        "owner_in_play_required_traits": "heroic",
                    }
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790061, card_id=661, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand.append(
        CardInstance(
            instance_id=790062,
            card_id=900307,
            owner_id=2,
            card_type="EXTRA",
            color="Yellow",
            energy_cost=2,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Negate the attack.",
        )
    )

    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)

    state.players[2].battle_area.append(
        CardInstance(
            instance_id=790063,
            card_id=663,
            owner_id=2,
            card_type="BATTLE",
            color="Yellow",
            traits=("Heroic",),
        )
    )
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_owner_in_play_character_and_cost_requirement() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_owner_in_play_character_cost")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900308: {
                "counter_alternate_from_hand": [
                    {
                        "kind": "add_life_to_hand",
                        "amount": 1,
                        "requires_owner_in_play": True,
                        "owner_in_play_allowed_colors": "yellow",
                        "owner_in_play_required_characters": "vegito",
                        "owner_in_play_min_energy_cost": 5,
                    }
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790071, card_id=671, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand.append(
        CardInstance(
            instance_id=790072,
            card_id=900308,
            owner_id=2,
            card_type="EXTRA",
            color="Yellow",
            energy_cost=2,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Negate the attack.",
        )
    )

    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    state.players[2].battle_area.append(
        CardInstance(
            instance_id=790073,
            card_id=673,
            owner_id=2,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=4,
            characters=("Vegito",),
        )
    )
    legal = engine.get_legal_actions(state, 2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)

    state.players[2].battle_area[0].energy_cost = 5
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_owner_battle_area_extra_requirement() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_owner_battle_area")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900309: {
                "counter_alternate_from_hand": [
                    {
                        "kind": "add_life_to_hand",
                        "amount": 1,
                        "requires_owner_battle_area": True,
                        "owner_battle_area_allowed_colors": "blue,red",
                        "owner_battle_area_required_card_types": "EXTRA",
                        "owner_battle_area_requires_multicolor": True,
                    }
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790081, card_id=681, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand.append(
        CardInstance(
            instance_id=790082,
            card_id=900309,
            owner_id=2,
            card_type="EXTRA",
            color="Blue",
            energy_cost=2,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Negate the attack.",
        )
    )

    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)

    state.players[2].battle_area.append(
        CardInstance(
            instance_id=790083,
            card_id=683,
            owner_id=2,
            card_type="EXTRA",
            color="Red/Blue",
        )
    )
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_drop_to_warp_follow_up_cost() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_drop_to_warp")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900310: {
                "counter_alternate_from_hand": [
                    {"kind": "add_life_to_hand", "amount": 1, "required_leader_colors": "red"},
                    {"kind": "send_owner_drop_to_warp", "amount": 2, "required_traits": "saiyan"},
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[2].leader_area.color = "Red"
    state.players[1].hand = [CardInstance(instance_id=790091, card_id=691, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand.append(
        CardInstance(
            instance_id=790092,
            card_id=900310,
            owner_id=2,
            card_type="BATTLE",
            color="Red",
            energy_cost=3,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Play this card.",
        )
    )
    state.players[2].drop.append(CardInstance(instance_id=790093, card_id=693, owner_id=2, card_type="BATTLE", traits=("Saiyan",)))

    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)

    state.players[2].drop.append(CardInstance(instance_id=790094, card_id=694, owner_id=2, card_type="BATTLE", traits=("Saiyan",)))
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_face_up_z_deck_requirement() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_face_up_z_deck")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900311: {
                "counter_alternate_from_hand": [
                    {
                        "kind": "add_life_to_hand",
                        "amount": 1,
                        "requires_owner_face_up_z_deck_count_at_least": 3,
                        "owner_face_up_z_deck_required_traits": "boujack brigade",
                    }
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        p2_z_deck_card_ids=[701, 702, 703],
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790101, card_id=791, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand.append(
        CardInstance(
            instance_id=790102,
            card_id=900311,
            owner_id=2,
            card_type="BATTLE",
            color="Blue",
            energy_cost=3,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Negate the attack and play this card.",
        )
    )
    for card in state.players[2].z_deck:
        card.traits = ("Boujack Brigade",)

    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)

    for card in state.players[2].z_deck:
        card.face_up = True
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_drop_to_warp_only_requirement() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_drop_to_warp_only")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900312: {
                "counter_alternate_from_hand": [
                    {
                        "kind": "send_owner_drop_to_warp",
                        "amount": 2,
                        "required_leader_traits": "power wish",
                        "requires_life_at_most": 4,
                        "required_traits": "power wish",
                    }
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state.players[2].leader_area.traits = ("Power Wish",)
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    while len(state.players[2].life) > 4:
        state.players[2].hand.append(state.players[2].life.pop(0))
    state.players[1].hand = [CardInstance(instance_id=790111, card_id=801, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand.append(
        CardInstance(
            instance_id=790112,
            card_id=900312,
            owner_id=2,
            card_type="BATTLE",
            color="Blue",
            energy_cost=2,
            has_counter=True,
            has_counter_play=True,
            counter_modes=("Counter: Play",),
            skill_text_raw="[Counter: Play] Play this card.",
        )
    )
    state.players[2].drop.append(CardInstance(instance_id=790113, card_id=803, owner_id=2, card_type="BATTLE", traits=("Power Wish",)))
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    legal = engine.get_legal_actions(state, 2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)
    state.players[2].drop.append(CardInstance(instance_id=790114, card_id=804, owner_id=2, card_type="BATTLE", traits=("Power Wish",)))
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_send_all_drop_to_warp_requirement() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_all_drop_to_warp")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900313: {
                "counter_alternate_from_hand": [
                    {
                        "kind": "send_all_owner_drop_to_warp",
                        "amount": 1,
                        "required_leader_colors": "black",
                        "requires_life_at_most": 4,
                    }
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state.players[2].leader_area.color = "Black"
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    while len(state.players[2].life) > 4:
        state.players[2].hand.append(state.players[2].life.pop(0))
    state.players[1].hand = [CardInstance(instance_id=790121, card_id=811, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand.append(
        CardInstance(
            instance_id=790122,
            card_id=900313,
            owner_id=2,
            card_type="BATTLE",
            color="Black",
            energy_cost=2,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Negate the attack and play this card.",
        )
    )
    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)
    state.players[2].drop.append(CardInstance(instance_id=790123, card_id=813, owner_id=2, card_type="BATTLE"))
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_rest_leader_requirement() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_rest_leader")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900314: {
                "counter_alternate_from_hand": [
                    {
                        "kind": "rest_owner_leader",
                        "amount": 1,
                        "required_leader_traits": "scientist",
                    }
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state.players[2].leader_area.traits = ("Scientist",)
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790131, card_id=821, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand.append(
        CardInstance(
            instance_id=790132,
            card_id=900314,
            owner_id=2,
            card_type="BATTLE",
            color="Blue",
            energy_cost=3,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Play this card.",
        )
    )
    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)
    action = next(a for a in legal if a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND)
    state = engine.apply_action(state, action)
    assert state.players[2].leader_area.resting is True


def test_engine_uses_catalog_for_counter_alternate_reduced_energy_and_z_energy_requirement() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_reduced_energy")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900315: {
                "counter_alternate_from_hand": [
                    {
                        "kind": "rest_energy",
                        "amount": 1,
                        "required_leader_traits": "king piccolo",
                        "requires_z_energy_at_least": 3,
                    }
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state.players[2].leader_area.characters = ("King Piccolo",)
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[2].energy.append(CardInstance(instance_id=790141, card_id=831, owner_id=2, card_type="BATTLE", resting=False))
    state.players[1].hand = [CardInstance(instance_id=790142, card_id=832, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand.append(
        CardInstance(
            instance_id=790143,
            card_id=900315,
            owner_id=2,
            card_type="EXTRA",
            color="Red",
            energy_cost=5,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Negate the attack.",
        )
    )
    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)
    state.players[2].z_energy.extend(
        [
            CardInstance(instance_id=790144, card_id=834, owner_id=2),
            CardInstance(instance_id=790145, card_id=835, owner_id=2),
            CardInstance(instance_id=790146, card_id=836, owner_id=2),
        ]
    )
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_engine_uses_catalog_for_counter_alternate_reduce_owner_battle_power_requirement() -> None:
    catalog_path = _workspace_temp_catalog_path("skill_cost_alt_reduce_battle_power")
    save_skill_cost_rules_json(
        catalog_path,
        {
            900316: {
                "counter_alternate_from_hand": [
                    {
                        "kind": "reduce_owner_battle_power_for_turn",
                        "amount": 2,
                        "required_leader_colors": "red",
                        "required_card_types": "BATTLE",
                        "power_delta": -10000,
                    }
                ]
            }
        },
    )
    engine = RulesEngine(skill_cost_rules_path=catalog_path)
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state.players[2].leader_area.color = "Red"
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790151, card_id=841, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand.append(
        CardInstance(
            instance_id=790152,
            card_id=900316,
            owner_id=2,
            card_type="EXTRA",
            color="Red",
            energy_cost=2,
            has_counter=True,
            has_counter_attack=True,
            counter_modes=("Counter: Attack",),
            skill_text_raw="[Counter: Attack] Choose up to 1 of your cards and it gets power.",
        )
    )
    state.players[2].battle_area.append(CardInstance(instance_id=790153, card_id=843, owner_id=2, card_type="BATTLE", power=15000))
    attack = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    legal = engine.get_legal_actions(state, 2)
    assert all(a.action_type != ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)
    state.players[2].battle_area.append(CardInstance(instance_id=790154, card_id=844, owner_id=2, card_type="BATTLE", power=16000))
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)


def test_runtime_infers_counter_capability_from_skill_text_when_db_flags_are_stale() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 900401:
                return SimpleNamespace(
                    card_name="Hidden Counter",
                    power_int=15000,
                    card_type="BATTLE",
                    card_color="White",
                    energy_cost_int=0,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_draw=False,
                    max_draw=None,
                    has_barrier=False,
                    z_energy_cost=None,
                    card_energy_cost="0",
                    card_skill_unstyled="[Counter: Play] Play this card.",
                    card_traits_json="[]",
                    card_character_json="[]",
                )
            return SimpleNamespace(
                card_name="Card",
                power_int=15000,
                card_type="LEADER" if card_id in {1, 2} else "BATTLE",
                card_color="White",
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
                card_traits_json="[]",
                card_character_json="[]",
            )

    engine = RulesEngine(card_repository=Repo())
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=790011, card_id=611, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[2].hand = [engine._create_card_instance(next_instance_id=790012, card_id=900401, owner_id=2)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    legal = engine.get_legal_actions(state, 2)
    assert any(a.action_type == ActionType.DECLARE_COUNTER_FROM_HAND for a in legal)
