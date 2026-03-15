from __future__ import annotations

from dataclasses import replace

from src.domain.models import CardData
from src.game.effect_rule_extractor import (
    build_effect_rules_with_diagnostics_and_report,
    build_effect_rules_for_cards,
    build_effect_rules_with_diagnostics,
    diagnose_unresolved_patterns,
    extract_effect_rules_from_card,
)


def _card(skill: str) -> CardData:
    return CardData(
        id=1,
        card_number="TEST-001",
        card_name="Test Card",
        source_table="cards",
        card_type="BATTLE",
        card_skill_unstyled=skill,
        has_auto=True,
        has_draw=True,
    )


def test_extract_draw_rules_on_play_and_attack() -> None:
    card = _card("[Auto][Once per turn] When this card is played, draw 1 card. [Auto] When this card attacks, draw 1 card.")
    rules = extract_effect_rules_from_card(card)
    by_handler = {r.handler_id: r for r in rules}
    assert by_handler["auto_draw_n"].trigger in {"self_played", "self_attacks"}
    assert any(r.trigger == "self_played" and r.handler_id == "auto_draw_n" and r.handler_params["amount"] == 1 for r in rules)
    assert any(r.trigger == "self_attacks" and r.handler_id == "auto_draw_n" and r.handler_params["amount"] == 1 for r in rules)
    assert all(r.once_per_turn for r in rules if r.handler_id == "auto_draw_n")


def test_extract_ko_and_power_reduce_rules_from_play_text() -> None:
    card = _card(
        "[Auto] When this card is played, choose up to 2 of your opponent's Battle Cards with an energy cost of 5 or less and KO them. "
        "Then choose up to 1 of your opponent's Battle Cards and it gets -15000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    assert any(
        r.handler_id == "auto_ko_up_to_n_opponent_battle_on_play"
        and r.handler_params.get("max_targets") == 2
        and r.handler_params.get("max_cost") == 5
        for r in rules
    )
    assert any(
        r.handler_id == "auto_power_reduce_up_to_n_on_play"
        and r.handler_params.get("power_delta") == -15000
        for r in rules
    )


def test_build_effect_rules_for_cards_maps_only_cards_with_matches() -> None:
    class Repo:
        def list_by_ids(self, ids, source_table: str = "cards"):
            c1 = replace(_card("[Auto] When this card attacks, draw 1 card."), id=100)
            c2 = replace(_card("No matching effect text"), id=200, has_auto=False, has_draw=False)
            source = {100: c1, 200: c2}
            return [source[i] for i in ids if i in source]

    mapped = build_effect_rules_for_cards(Repo(), [100, 200])
    assert 100 in mapped
    assert 200 not in mapped
    assert any(r.trigger == "self_attacks" and r.handler_id == "auto_draw_n" for r in mapped[100])


def test_extract_trigger_variants_played_from_hand_and_if_leader_prefix() -> None:
    card = _card(
        "[Auto] If your Leader is a blue card: When this card is played from your hand, draw 2 cards. "
        "[Auto] If your Leader is blue: When this card attacks, draw 1 card."
    )
    rules = extract_effect_rules_from_card(card)
    assert any(r.trigger == "self_played" and r.handler_id == "auto_draw_n" and r.handler_params.get("amount") == 2 for r in rules)
    assert any(r.trigger == "self_attacks" and r.handler_id == "auto_draw_n" and r.handler_params.get("amount") == 1 for r in rules)


def test_extract_play_or_combo_draw_emits_both_triggers_once() -> None:
    card = _card(
        "[Auto] If your leader card is yellow: When this card in your hand is played or used in a combo, draw 1 card."
    )
    rules = extract_effect_rules_from_card(card)
    draws = [r for r in rules if r.handler_id == "auto_draw_n" and r.handler_params.get("amount") == 1]
    assert any(r.trigger == "self_played" for r in draws)
    assert any(r.trigger == "self_comboed" for r in draws)
    assert sum(1 for r in draws if r.trigger in {"self_played", "self_comboed"}) == 2


def test_extract_choose_one_branches_parses_branch_effects() -> None:
    card = _card(
        "[Auto] When this card attacks, choose one— ・Draw 1 card. ・Choose up to 1 of your opponent's Battle Cards and KO it."
    )
    rules = extract_effect_rules_from_card(card)
    assert any(r.trigger == "self_attacks" and r.handler_id == "auto_draw_n" for r in rules)
    assert any(r.trigger == "self_played" and r.handler_id.startswith("auto_ko") for r in rules) is False


def test_extract_conditions_capture_leader_barrier_rest_mode() -> None:
    card = _card(
        "[Auto] If your Leader is a green card: When this card is played, choose up to 1 of your opponent's Battle Cards in Rest Mode, ignoring [Barrier], and KO it."
    )
    rules = extract_effect_rules_from_card(card)
    ko = next(r for r in rules if r.handler_id == "auto_ko_opponent_battle_on_play")
    assert ko.handler_params["ignores_barrier"] is True
    assert ko.handler_params["rest_mode_only"] is True
    assert "if your leader is a green card" in str(ko.handler_params["requires_leader"]).lower()


def test_diagnostics_flags_missed_patterns() -> None:
    card = _card("[Auto] When this card attacks, draw 1 card.")
    notes = diagnose_unresolved_patterns(card, [])
    assert "missed_attack_draw" in notes


def test_build_effect_rules_with_diagnostics_returns_both() -> None:
    class Repo:
        def list_by_ids(self, ids, source_table: str = "cards"):
            c1 = replace(_card("[Auto] When this card attacks, draw 1 card."), id=300)
            c2 = replace(_card("[Auto] When this card attacks, draw 2 cards."), id=301)
            return [c1, c2]

    mapped, diagnostics = build_effect_rules_with_diagnostics(Repo(), [300, 301])
    assert 300 in mapped and 301 in mapped
    assert diagnostics == {}


def test_extract_dynamic_x_for_ko_sets_max_targets_expression() -> None:
    card = _card(
        "[Auto] When this card is played, choose up to X of your opponent's Battle Cards and KO them, "
        "where X is equal to the number of your energy."
    )
    rules = extract_effect_rules_from_card(card)
    ko = next(r for r in rules if r.handler_id == "auto_ko_up_to_n_opponent_battle_on_play")
    assert ko.handler_params["max_targets"] == "expr:owner_energy_count"


def test_extract_dynamic_x_for_power_reduce_sets_max_targets_expression() -> None:
    card = _card(
        "[Auto] When this card is played, choose up to X of your opponent's Battle Cards and they get -5000 power for the turn, "
        "where X is equal to the number of your opponent's Battle Cards."
    )
    rules = extract_effect_rules_from_card(card)
    reduce_rule = next(r for r in rules if r.handler_id == "auto_power_reduce_up_to_n_on_play")
    assert reduce_rule.handler_params["max_targets"] == "expr:opponent_battle_count"


def test_extract_combo_draw_rule_with_leader_condition() -> None:
    card = _card("[Auto] If your Leader is green and your life is at 4 or less: When this card is used in a combo, draw 1 card.")
    rules = extract_effect_rules_from_card(card)
    combo_draw = next(r for r in rules if r.trigger == "self_comboed" and r.handler_id == "auto_draw_n")
    assert combo_draw.handler_params["amount"] == 1
    assert "green" in str(combo_draw.handler_params.get("requires_leader", "")).lower()


def test_extract_attack_pay_life_gain_power_and_keyword_rule() -> None:
    card = _card(
        "[Auto] Add 1 card from your life to your hand: When this card attacks, it gets +15000 power and [Double Strike] for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_pay_life_on_attack_gain_power_and_keyword_for_turn")
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["life_to_hand"] == 1
    assert rule.handler_params["power_delta"] == 15000
    assert rule.handler_params["grant_keyword"] == "Double Strike"


def test_extract_owner_leader_attack_add_from_hand_to_life_rule() -> None:
    card = _card(
        "[Auto] If your Leader Card is a yellow Turles Crusher Corps card: "
        "When your Leader Card attacks, you may choose 1 yellow Turles Crusher Corps card in your hand and add it to your life."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_add_up_to_n_from_owner_hand_to_life_on_owner_leader_attack")
    assert rule.trigger == "owner_leader_attacks"
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["allowed_colors"] == "yellow"


def test_extract_owner_leader_attack_look_top_add_to_hand_rule() -> None:
    card = _card(
        "[Auto] When your Leader Card attacks, look at up to 5 cards from the top of your deck, "
        "add up to 1 red Earthling card among them to your hand, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "owner_leader_attacks" and r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play")
    assert rule.handler_params["look_count"] == 5
    assert rule.handler_params["max_add"] == 1
    assert rule.handler_params["allowed_colors"] == "red"
    assert rule.handler_params["required_traits"] == "Earthling"


def test_extract_play_from_hand_add_from_hand_to_life_rule() -> None:
    card = _card(
        "[Auto] If your leader card is a yellow Turles Crusher Corps card: "
        "When this card is played from your hand, you may choose 1 yellow Turles Crusher Corps card in your hand and add it to your life."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_add_up_to_n_from_owner_hand_to_life_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["allowed_colors"] == "yellow"
    assert rule.handler_params["requires_played_from"] == "hand"


def test_extract_combo_battle_end_play_self_from_drop_rule() -> None:
    card = _card(
        "[Auto] If your Leader Card is a yellow card: At the end of a battle in which this card was used in a combo from your hand, "
        "play this card from your Drop Area in Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_comboed_battle_end")
    assert rule.handler_id == "auto_play_self_from_combo_on_battle_end"
    assert rule.handler_params["resting"] is True
    assert "if your leader card is a yellow card" in str(rule.handler_params["requires_leader"]).lower()


def test_extract_turn_end_switch_self_active_rule() -> None:
    card = _card("[Auto] At the end of your turn, switch this card to Active Mode.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "turn_end")
    assert rule.handler_id == "auto_switch_self_active_on_turn_end"


def test_extract_field_extra_placed_switch_energy_active_rule() -> None:
    card = _card(
        "[Auto] If you have 5 or more energy: When a player places a [Field] Extra card in a Battle Area, "
        "you may flip this card over. If you do, switch up to 2 of your yellow energy to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_switch_up_to_n_owner_energy_active_on_field_extra_placed")
    assert rule.trigger == "owner_field_extra_placed"
    assert rule.handler_params["max_targets"] == 2
    assert rule.handler_params["allowed_colors"] == "yellow"


def test_extract_owner_opponent_skill_plays_overcost_battle_reduce_rule() -> None:
    card = _card(
        "[Auto] Switch this card to Rest Mode: When your opponent uses a skill to play a Battle Card with an energy cost greater than their current energy, "
        "you may choose that Battle Card and have it get -30000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_rest_self_on_owner_opponent_skill_play_overcost_battle_reduce_power")
    assert rule.trigger == "owner_opponent_skill_plays_overcost_battle"
    assert rule.handler_params["power_delta"] == -30000


def test_extract_owner_opponent_skill_plays_overcost_battle_switch_rest_rule() -> None:
    card = _card(
        "[Auto] Switch this card to Rest Mode: When your opponent uses a skill to play a Battle Card with an energy cost greater than their current energy, "
        "you may choose it and switch it to Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_rest_self_on_owner_opponent_skill_play_overcost_battle_switch_target_rest")
    assert rule.trigger == "owner_opponent_skill_plays_overcost_battle"


def test_extract_play_top_if_color_add_hand_rule() -> None:
    card = _card(
        "[Auto] If your Leader Card is a Shadow Dragon card: When this card is played from your hand or discarded by a skill, "
        "you may look at the top card of your deck; if it's a black card you may add it to your hand, otherwise place it at the bottom of your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_top_deck_add_if_color_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["required_color"] == "black"
    assert rule.handler_params["move_to_bottom_on_fail"] is True


def test_extract_activate_main_draw_rule() -> None:
    card = _card("[Activate: Main] Switch this card to Rest Mode: Draw 1 card.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main")
    assert rule.handler_id == "auto_draw_n"
    assert rule.handler_params["amount"] == 1


def test_extract_activate_battle_draw_rule() -> None:
    card = _card("[Activate: Battle] If your leader is red: Draw 1 card.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_battle" and r.handler_id == "auto_draw_n")
    assert rule.handler_params["amount"] == 1


def test_extract_activate_main_battle_draw_rule_emits_both_triggers() -> None:
    card = _card("[Activate: Main/Battle] Draw 1 card.")
    rules = extract_effect_rules_from_card(card)
    assert any(r.trigger == "self_activate_main" and r.handler_id == "auto_draw_n" and r.handler_params.get("amount") == 1 for r in rules)
    assert any(r.trigger == "self_activate_battle" and r.handler_id == "auto_draw_n" and r.handler_params.get("amount") == 1 for r in rules)


def test_extract_owner_black_battle_played_from_warp_wormhole_rule() -> None:
    card = _card(
        "[Auto] If your Leader Card is a black Trunks card: When a black Battle Card is played from your Warp, "
        "this card gains [Wormhole] for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "owner_battle_played_from_warp")
    assert rule.handler_id == "auto_gain_wormhole_on_owner_black_battle_played_from_warp"


def test_extract_play_add_top_deck_to_energy_rest_on_play_rule() -> None:
    card = _card("[Auto] If all of your energy is mono-blue: When this card is played, add the top card of your deck to your energy in Rest Mode.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_add_top_deck_to_energy_rest_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["requires_mono_energy"] == "blue"


def test_extract_play_look_top_add_to_hand_rule() -> None:
    card = _card(
        "[Auto] When this card is played from your hand, look at up to 5 cards from the top of your deck, "
        "add up to 1 green or yellow Namekian card with an energy cost of 4 or less among them to your hand, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["look_count"] == 5
    assert rule.handler_params["max_add"] == 1
    assert rule.handler_params["max_cost"] == 4
    assert rule.handler_params["allowed_colors"] == "green,yellow"
    assert rule.handler_params["requires_played_from"] == "hand"


def test_extract_play_look_top_add_two_to_hand_rule() -> None:
    card = _card(
        "[Auto] When this card is played from your hand, look at up to 7 cards from the top of your deck, "
        "add up to 2 green or yellow Battle Cards with an energy cost of 6 or less among them to your hand, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play")
    assert rule.handler_params["look_count"] == 7
    assert rule.handler_params["max_add"] == 2
    assert rule.handler_params["max_cost"] == 6


def test_extract_play_look_top_add_to_hand_allows_dash_before_to_your_hand() -> None:
    card = _card(
        "[Auto] When this card is played from your hand, look at up to 7 cards from the top of your deck, "
        "add up to 1 Son Goku card among them―both green and with an energy cost of 6 or less―to your hand, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play")
    assert rule.handler_params["look_count"] == 7
    assert rule.handler_params["max_add"] == 1
    assert rule.handler_params["max_cost"] == 6


def test_extract_self_ko_unison_power_reduce_rule() -> None:
    card = _card("[Auto] When this card is KO'd, choose up to 1 of your opponent's Unison Cards and it gets -10000 power for the turn.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_koed")
    assert rule.handler_id == "auto_power_reduce_opponent_unison_on_self_ko"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["power_delta"] == -10000


def test_extract_self_removed_or_ko_add_life_rule() -> None:
    card = _card(
        "[Auto] When this card is removed from your Battle Area by a skill or KO'd, you may add 1 card from your life to your hand."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_add_n_life_to_hand_on_self_ko")
    assert rule.trigger == "self_koed"
    assert rule.handler_params["amount"] == 1


def test_extract_turn_end_switch_up_to_n_energy_active_rule() -> None:
    card = _card("[Auto] At the end of your turn, switch up to 1 of your energy to Active Mode.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_switch_up_to_n_owner_energy_active_on_turn_end")
    assert rule.trigger == "turn_end"
    assert rule.handler_params["max_targets"] == 1


def test_extract_turn_end_switch_up_to_n_multicolor_energy_active_rule() -> None:
    card = _card("[Auto] At the end of your turn, switch up to 2 of your blue/yellow multicolor energy to Active Mode.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_switch_up_to_n_owner_energy_active_on_turn_end")
    assert rule.handler_params["max_targets"] == 2
    assert rule.handler_params["allowed_colors"] == "blue,yellow"
    assert rule.handler_params["requires_multicolor"] is True


def test_extract_end_of_the_turn_switch_up_to_n_energy_active_rule() -> None:
    card = _card("[Auto] At the end of the turn, switch up to 1 of your energy to Active Mode.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_switch_up_to_n_owner_energy_active_on_turn_end")
    assert rule.trigger == "turn_end"
    assert rule.handler_params["max_targets"] == 1


def test_extract_play_from_hand_play_from_deck_rule() -> None:
    card = _card(
        "[Auto] When this card is played from your hand, choose up to 1 red Battle Card with 10000 power or less from your deck, play it, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_deck_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_power"] == 10000
    assert rule.handler_params["allowed_colors"] == "red"
    assert rule.handler_params["requires_played_from"] == "hand"


def test_extract_combo_from_hand_play_from_hand_rule() -> None:
    card = _card(
        "[Auto] When this card is used in a combo from your hand, choose up to 1 mono-blue Bardock card "
        "with an energy cost of 5 or less in your hand and play it in Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_hand_on_self_combo")
    assert rule.trigger == "self_comboed"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_cost"] == 5
    assert rule.handler_params["allowed_colors"] == "blue"
    assert rule.handler_params["rest_mode"] is True


def test_extract_activate_main_look_top_add_to_hand_with_discard_rule() -> None:
    card = _card(
        "[+1][Activate: Main] Look at up to 5 cards from the top of your deck, "
        "add up to 1 green/yellow multicolor card among them to your hand, then shuffle your deck. "
        "If you added a card to your hand, choose 1 card in your hand and discard it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play")
    assert rule.handler_params["look_count"] == 5
    assert rule.handler_params["max_add"] == 1
    assert rule.handler_params["allowed_colors"] == "green,yellow"
    assert rule.handler_params["discard_after_add"] == 1


def test_extract_activate_main_ss4_call_style_search_rule() -> None:
    card = _card(
        "[Activate: Main][Limit 1] If your Leader Card is a black Bardock: Xeno card or a Saiyan card with {SS4} in its card name: "
        "Look at up to 3 cards from the top of your deck, add up to 2 black cards with {SS4} in their card names among them to your hand, "
        "then place the rest at the bottom of your deck in any order. If you added 2 cards to your hand, choose 1 card in your hand and place it at the bottom of your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play")
    assert rule.handler_params["look_count"] == 3
    assert rule.handler_params["max_add"] == 2
    assert rule.handler_params["allowed_colors"] == "black"
    assert rule.handler_params["required_name_contains"] == "SS4"
    assert rule.handler_params["move_unpicked_to_bottom"] is True
    assert rule.handler_params["bottom_deck_after_add"] == 1
    assert rule.handler_params["bottom_deck_after_add_exact_add_count"] == 2


def test_extract_activate_main_power_wish_play_self_from_hand_rule() -> None:
    card = _card(
        "[Activate: Main] If your Leader Card is a Power Wish card and you have 3 or more energy, and neither you nor your opponent have a Battle Card in play: Play this card from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_play_self_from_hand")
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["required_leader_traits"] == "Power Wish"
    assert rule.handler_params["min_owner_energy"] == 3
    assert rule.handler_params["requires_no_owner_battle"] is True
    assert rule.handler_params["requires_no_opponent_battle"] is True


def test_extract_activate_main_power_wish_draw_and_gain_keyword_rule() -> None:
    card = _card(
        "[Activate: Main][Once per turn]{1}: Draw 1 card, and this card gains [Dual Attack] for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_draw_n_and_gain_keyword_for_turn")
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["grant_keyword"] == "Dual Attack"
    assert rule.once_per_turn is True


def test_extract_activate_battle_gain_power_and_keyword_for_battle_rule() -> None:
    card = _card(
        "[Activate: Battle][Once per turn](1), choose 1 white card in your Battle Area and switch it to Hidden Mode: "
        "This card gets +10000 power and [Double Strike] for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_gain_power_and_keyword_for_battle")
    assert rule.trigger == "self_activate_battle"
    assert rule.handler_params["power_delta"] == 10000
    assert rule.handler_params["grant_keyword"] == "Double Strike"
    assert rule.once_per_turn is True


def test_extract_activate_battle_ko_up_to_n_opponent_battle_rule() -> None:
    card = _card(
        "[Activate: Battle][Limit 1] Choose 1 Hidden Mode card in your Battle Area and place it into its owner's Drop: "
        "Choose up to 1 of your opponent's Battle Cards and KO it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_ko_up_to_n_opponent_battle")
    assert rule.trigger == "self_activate_battle"
    assert rule.handler_params["max_targets"] == 1


def test_extract_activate_main_draw_play_self_and_gain_keyword_until_opponent_turn_end_rule() -> None:
    card = _card(
        "[Activate: Main]{w}(2), if you have 2 or more Hidden Mode cards in your Battle Area: "
        "Draw 1 card, play this card from your hand, and this card gains [Barrier] until the end of your opponent's turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "activate_draw_n_play_self_from_hand_and_gain_keyword_until_opponent_turn_end"
    )
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["grant_keyword"] == "Barrier"
    assert rule.handler_params["min_owner_hidden_mode_battle"] == 2


def test_extract_play_gain_control_opponent_unison_rule() -> None:
    card = _card("[Auto] When this card is played from your hand, choose 1 of your opponent's Unison Cards and gain control of it.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_gain_control_opponent_unison_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1


def test_extract_play_switch_owner_board_to_revealed_rule() -> None:
    card = _card("[Auto] When this card is played, choose up to 1 card in your Battle Area and switch it to Revealed Mode.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_switch_up_to_n_owner_board_to_revealed_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1


def test_extract_play_switch_any_player_board_to_revealed_rule() -> None:
    card = _card("[Auto] When this card is played, choose up to 1 player's card and switch it to Revealed Mode.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_switch_up_to_n_any_player_board_to_revealed_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1


def test_extract_play_switch_owner_battle_to_hidden_rule() -> None:
    card = _card("[Auto] When this card is played, choose up to 1 white card in your Battle Area and switch it to Hidden Mode.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_switch_up_to_n_owner_battle_to_hidden_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "white"


def test_extract_play_switch_owner_battle_to_hidden_rule_without_explicit_area() -> None:
    card = _card("[Auto] When this card is played, choose up to 1 of your white Battle Cards and switch it to Hidden Mode.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_switch_up_to_n_owner_battle_to_hidden_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "white"


def test_extract_play_draw_and_switch_self_to_hidden_rule() -> None:
    card = _card("[Auto] When this card is played, draw 1 card and switch this card to Hidden Mode.")
    rules = extract_effect_rules_from_card(card)
    assert any(r.handler_id == "auto_draw_n" and r.trigger == "self_played" for r in rules)
    assert any(r.handler_id == "auto_switch_self_to_hidden_on_play" and r.trigger == "self_played" for r in rules)


def test_extract_activate_main_switch_self_to_hidden_rule() -> None:
    card = _card("[Activate: Main][Limit 1] If your Leader is a white ≪God≫ card: Switch this card to Hidden Mode.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_switch_self_to_hidden_mode")
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["required_leader_traits"] == "White ≪God≫"


def test_extract_activate_main_without_colon_hidden_cost_draw_rule() -> None:
    card = _card("[activate main][once per turn] Choose 1 of your white Battle Cards and switch it to Hidden Mode: Draw 1 card.")
    rules = extract_effect_rules_from_card(card)
    assert any(r.handler_id == "auto_draw_n" and r.trigger == "self_activate_main" and r.handler_params["amount"] == 1 for r in rules)


def test_extract_hidden_switch_owner_leader_buff_rule() -> None:
    card = _card(
        "[Auto][Limit 1] When this card in a Battle Area is switched to Hidden Mode by one of your skills, "
        "your Leader gets +5000 power until the end of your opponent's turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_buff_owner_leader_on_switch_until_opponent_turn_end")
    assert rule.trigger == "self_switched_hidden"
    assert rule.handler_params["power_delta"] == 5000
    assert rule.handler_params["requires_owner_actor"] is True


def test_extract_hidden_switch_owner_card_keyword_rule() -> None:
    card = _card(
        "[Auto][Limit 1] When this card in a Battle Area is switched to Hidden Mode by one of your skills, "
        "choose up to 1 of your white ≪Universe 7≫ cards and it gains [Barrier] until the end of your opponent's turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_buff_up_to_n_owner_cards_on_switch")
    assert rule.trigger == "self_switched_hidden"
    assert rule.handler_params["grant_keyword"] == "Barrier"
    assert rule.handler_params["keyword_duration"] == "opponent_turn"


def test_extract_revealed_switch_self_gain_power_and_keyword_rule() -> None:
    card = _card("[Auto] When this card is switched to Revealed Mode, it gets +5000 power and [Double Strike] for the turn.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_self_gain_power_and_keyword_for_turn_on_switch")
    assert rule.trigger == "self_switched_revealed"
    assert rule.handler_params["power_delta"] == 5000
    assert rule.handler_params["grant_keyword"] == "Double Strike"


def test_extract_revealed_or_hidden_switch_owner_card_gain_power_rule() -> None:
    card = _card(
        "[Auto] If it's your turn : When this card is switched to Revealed Mode or Hidden Mode, "
        "choose up to 1 of your white <Baby> or ≪Brainwashed≫ cards and it gets +10000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    matching = [r for r in rules if r.handler_id == "auto_buff_up_to_n_owner_cards_on_switch"]
    assert {r.trigger for r in matching} == {"self_switched_hidden", "self_switched_revealed"}
    assert all(r.handler_params["power_delta"] == 10000 for r in matching)
    assert all(r.handler_params["requires_owner_turn"] is True for r in matching)


def test_extract_revealed_or_hidden_switch_ko_opponent_battle_rule() -> None:
    card = _card(
        "[Auto][Limit 1] If it's your turn : When this card is switched to Revealed Mode or Hidden Mode, "
        "choose up to 1 of your opponent's Battle Cards and KO it."
    )
    rules = extract_effect_rules_from_card(card)
    matching = [r for r in rules if r.handler_id == "auto_ko_up_to_n_opponent_battle_on_switch"]
    assert {r.trigger for r in matching} == {"self_switched_hidden", "self_switched_revealed"}
    assert all(r.handler_params["max_targets"] == 1 for r in matching)


def test_extract_hidden_battle_to_drop_owner_card_gain_power_rule() -> None:
    card = _card(
        "[Auto] When this Hidden Mode card in a Battle Area is placed into its owner's Drop, "
        "choose up to 1 of your white ≪Universe 7≫ cards and it gets +5000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_buff_up_to_n_owner_cards_on_hidden_drop")
    assert rule.trigger == "self_hidden_battle_to_drop"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["power_delta"] == 5000
    assert rule.handler_params["allowed_colors"] == "white"


def test_extract_activate_main_switch_all_opponent_battle_to_revealed_then_ko_rule() -> None:
    card = _card(
        "[Activate: Main] Choose all the cards in your opponent's Battle Area and switch them to Revealed Mode, "
        "then choose up to 1 of your opponent's Battle Cards and KO it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_switch_all_opponent_battle_to_revealed_then_ko_up_to_n")
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["max_targets"] == 1


def test_extract_revealed_switch_owner_card_gain_keyword_rule() -> None:
    card = _card(
        "[Auto][Limit 1] If your opponent has 2 or more energy : When this card is switched to Revealed Mode, "
        "choose up to 1 of your white <Baby> cards and it gains [Double Strike] for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_buff_up_to_n_owner_cards_on_switch" and r.trigger == "self_switched_revealed")
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["grant_keyword"] == "Double Strike"
    assert rule.handler_params["allowed_colors"] == "white"
    assert rule.handler_params["required_traits"] == "Baby"


def test_extract_play_search_direct_to_hand_rule() -> None:
    card = _card(
        "[Auto] When this card is played, look at up to 5 cards from the top of your deck, "
        "add up to 1 white <Baby> or â‰ªBrainwashedâ‰« card to your hand, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["look_count"] == 5
    assert rule.handler_params["max_add"] == 1
    assert rule.handler_params["allowed_colors"] == "white"
    assert rule.handler_params["required_characters"] == "Baby,Brainwashed"


def test_extract_attack_power_reduce_rule() -> None:
    card = _card("[Auto] When this card attacks, choose up to 1 of your opponent's Battle Cards and it gets -10000 power for the turn.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_power_reduce_up_to_n_on_attack")
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["power_delta"] == -10000


def test_extract_play_from_hand_play_with_marker_rule() -> None:
    card = _card(
        "[Auto] When this card is played from your hand, choose up to 1 {Meta-Cooler Core, Giant Force} in your hand and play it with a marker on it in Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["markers"] == 1
    assert rule.handler_params["source_pool"] == "hand"
    assert rule.handler_params["rest_mode"] is True


def test_extract_choose_one_with_unicode_bullet_splits_into_branches() -> None:
    card = _card(
        "[Auto] When this card is played, choose one-. "
        "・Draw 1 card. "
        "・At the end of your turn, switch this card to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    assert any(r.trigger == "self_played" and r.handler_id == "auto_draw_n" and r.handler_params.get("amount") == 1 for r in rules)
    assert any(r.trigger == "turn_end" and r.handler_id == "auto_switch_self_active_on_turn_end" for r in rules)


def test_extract_play_from_hand_play_with_markers_from_hand_or_deck_rule() -> None:
    card = _card(
        "[Auto] When this card is played from your hand, choose up to 1 {Meta-Cooler Core, Big Gete Star} "
        "from your hand or deck, play it with 2 markers on it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["markers"] == 2
    assert rule.handler_params["source_pool"] == "hand_or_deck"


def test_extract_play_from_hand_play_with_markers_includes_filters() -> None:
    card = _card(
        "[Auto] When this card is played from your hand, choose up to 2 mono-blue Battle Cards with an energy cost of 3 or less "
        "in your hand and play it with 2 markers on it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play")
    assert rule.handler_params["max_targets"] == 2
    assert rule.handler_params["markers"] == 2
    assert rule.handler_params["source_pool"] == "hand"
    assert rule.handler_params["max_cost"] == 3
    assert rule.handler_params["allowed_colors"] == "blue"
    assert rule.handler_params["required_card_type"] == "BATTLE"


def test_extract_play_from_hand_or_deck_markers_includes_unison_filters() -> None:
    card = _card(
        "[Auto] When this card is played from your hand, choose up to 1 yellow Unison Card with an energy cost of 4 or less "
        "from your hand or deck, play it with 3 markers on it in Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play")
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["markers"] == 3
    assert rule.handler_params["source_pool"] == "hand_or_deck"
    assert rule.handler_params["max_cost"] == 4
    assert rule.handler_params["allowed_colors"] == "yellow"
    assert rule.handler_params["required_card_type"] == "UNISON"


def test_extract_play_add_up_to_n_from_deck_to_hand_rule() -> None:
    card = _card(
        "[Auto] When this card is played, add up to 1 {Natade Village Ritual} from your deck to your hand, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_add_up_to_n_from_owner_deck_to_hand_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_cost"] == -1


def test_extract_play_add_up_to_n_from_deck_to_hand_with_filters_rule() -> None:
    card = _card(
        "[Auto] When this card is played from your hand, add up to 2 skill-less green Battle Cards with energy costs of 3 or less "
        "from your deck to your hand, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_add_up_to_n_from_owner_deck_to_hand_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 2
    assert rule.handler_params["max_cost"] == 3
    assert rule.handler_params["allowed_colors"] == "green"
    assert rule.handler_params["required_card_type"] == "BATTLE"
    assert rule.handler_params["requires_skill_less"] is True


def test_extract_placed_in_battle_area_add_up_to_n_from_deck_to_hand_rule() -> None:
    card = _card(
        "[Auto] When this card is placed in a Battle Area, add up to 1 skill-less Monster card with energy costs of 2 or less from your deck to your hand, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_add_up_to_n_from_owner_deck_to_hand_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_cost"] == 2
    assert rule.handler_params["required_card_type"] == "BATTLE"
    assert rule.handler_params["requires_skill_less"] is True


def test_extract_play_add_markers_per_multicolor_energy_rule() -> None:
    card = _card(
        "[Auto][Limit 1] If this card has 1 marker: When this card is played, add a marker to it for every 1 multicolor card in your energy."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_add_markers_per_n_multicolor_energy_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["per_n_energy"] == 1
    assert rule.handler_params["min_source_markers"] == 1


def test_extract_play_up_to_n_from_drop_with_negate_and_discard_rule() -> None:
    card = _card(
        "[Auto][Limit 1] Discard 1 card from your hand: When this card is played, "
        "play up to 1 yellow Universe 7 card with an energy cost of 2 or less from your drop area in Rest Mode with its skills negated."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_drop_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_cost"] == 2
    assert rule.handler_params["allowed_colors"] == "yellow"
    assert rule.handler_params["rest_mode"] is True
    assert rule.handler_params["negate_skills"] is True
    assert rule.handler_params["discard_from_hand_before"] == 1


def test_build_effect_rules_with_diagnostics_and_report_counts_coverage() -> None:
    class Repo:
        def list_by_ids(self, ids, source_table: str = "cards"):
            c1 = replace(_card("[Auto] When this card attacks, draw 1 card."), id=400)
            c2 = replace(_card("[Auto] When this card is played, draw 2 cards."), id=401)
            c3 = replace(_card("Activate: Main once per turn: choose 1 card in your hand and discard it."), id=402)
            return [c1, c2, c3]

    mapped, diagnostics, report = build_effect_rules_with_diagnostics_and_report(Repo(), [400, 401, 402], top_unmatched=5)
    assert set(mapped) == {400, 401}
    assert diagnostics == {}
    assert report["candidates_scanned"] == 3
    assert report["cards_with_rules"] == 2
    assert report["cards_without_rules"] == 1
    assert report["total_extracted_rules"] == 2
    coverage = report["coverage"]
    assert isinstance(coverage, dict)
    assert coverage["by_trigger"]["self_attacks"] == 1
    assert coverage["by_trigger"]["self_played"] == 1
    assert coverage["by_handler"]["auto_draw_n"] == 2


def test_build_effect_rules_with_diagnostics_and_report_groups_unmatched_templates() -> None:
    class Repo:
        def list_by_ids(self, ids, source_table: str = "cards"):
            c1 = replace(_card("Activate: Main: Draw 1 card, then discard 1 card."), id=500)
            c2 = replace(_card("Activate: Main: Draw 2 cards, then discard 2 cards."), id=501)
            c3 = replace(_card("[Auto] When this card attacks, draw 1 card."), id=502)
            return [c1, c2, c3]

    _, _, report = build_effect_rules_with_diagnostics_and_report(Repo(), [500, 501, 502], top_unmatched=3)
    unmatched = report["unmatched_top_templates"]
    assert isinstance(unmatched, list)
    first = unmatched[0]
    assert first["count"] == 2
    assert "draw <n> card" in first["template"]


def test_diagnostics_does_not_flag_combo_draw_when_draw_is_only_on_play() -> None:
    card = _card(
        "[Auto] When this card is played, draw 1 card. "
        "[Auto] When this card is used in a combo from your Battle Area, it gets +5000 combo power for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    notes = diagnose_unresolved_patterns(card, rules)
    assert "missed_combo_draw" not in notes
