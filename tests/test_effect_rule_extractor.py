from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

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
    assert all(r.family_id == f"{r.trigger}:{r.handler_id}" for r in rules)
    assert all(r.provenance == "extractor" for r in rules)


def test_extract_source_text_tracks_individual_auto_lines() -> None:
    card = _card(
        "[Auto] When this card is played, draw 1 card."
        "<br>[Auto] When this card attacks, draw 1 card, and you can't activate copies of this card for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    played = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "auto_draw_n")
    attacks = next(r for r in rules if r.trigger == "self_attacks" and r.handler_id == "auto_draw_n")
    assert "when this card is played" in played.source_text.lower()
    assert "when this card attacks" in attacks.source_text.lower()
    assert "copies of this card for the turn" not in played.source_text.lower()
    assert "copies of this card for the turn" in attacks.source_text.lower()


def test_extract_limit_x_tracks_limit_count_on_effect_rules() -> None:
    card = _card("[Auto][Limit 2] When this card attacks, draw 1 card.")
    rules = extract_effect_rules_from_card(card)
    draw = next(r for r in rules if r.trigger == "self_attacks" and r.handler_id == "auto_draw_n")
    assert draw.limit_per_turn == 2
    assert draw.limit_scope == "card_number"


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


def test_extract_self_played_can_schedule_place_self_under_owner_leader_at_turn_end() -> None:
    card = _card(
        "[Auto] When this card is played, choose up to 1 of your opponent's Battle Cards, ignoring [Barrier], it gets -35000 power for the turn, "
        "then place this card under your Leader at the end of the turn."
    )
    rules = extract_effect_rules_from_card(card)
    assert any(r.handler_id == "auto_power_reduce_up_to_n_on_play" for r in rules)
    schedule_rule = next(
        r for r in rules if r.handler_id == "auto_schedule_place_self_under_owner_leader_on_turn_end_on_play"
    )
    assert schedule_rule.trigger == "self_played"


def test_extract_owner_opponent_battle_played_can_play_self_from_under_owner_leader_to_opponent_battle() -> None:
    card = _card(
        "[Auto] If your opponent has 4 or more energy: When your opponent plays a red Battle Card with both <Son Goku> and <Piccolo>, "
        "play this card from under your Leader into your opponent's Battle Area."
    )
    rules = extract_effect_rules_from_card(card)
    trap_rule = next(
        r for r in rules if r.handler_id == "auto_play_self_from_under_owner_leader_to_opponent_battle"
    )
    assert trap_rule.trigger == "owner_opponent_battle_played"
    assert trap_rule.handler_params.get("required_source_zone") == "leader_under"
    assert trap_rule.handler_params.get("event_allowed_colors") == "red"
    assert trap_rule.handler_params.get("event_required_card_type") == "BATTLE"
    assert set(str(trap_rule.handler_params.get("event_required_characters") or "").split(",")) == {"Son Goku", "Piccolo"}
    assert trap_rule.handler_params.get("event_requires_all_characters") is True
    assert trap_rule.handler_params.get("min_opponent_energy") == 4


def test_extract_foreseeing_hit_can_warp_opponent_hand_battles_and_return_them_next_opponent_turn() -> None:
    card = _card(
        "[Double Strike] [Auto] When you play this card from your hand, your opponent reveals their hand. "
        "Choose up to 2 Battle Cards with 35000 or less power from their hand and send them to the Warp. "
        "At the end of your opponent's next turn, return all cards sent to the Warp with this skill to their hand."
    )
    rules = extract_effect_rules_from_card(card)
    warp_rule = next(r for r in rules if r.handler_id == "auto_send_up_to_n_opponent_hand_battle_to_warp_on_play")
    assert warp_rule.trigger == "self_played"
    assert warp_rule.handler_params["max_targets"] == 2
    assert warp_rule.handler_params["max_power"] == 35000
    assert warp_rule.handler_params["requires_played_from"] == "hand"
    delayed_rule = next(
        r
        for r in rules
        if r.handler_id == "auto_schedule_return_cards_warped_by_source_skill_to_owner_hand_on_opponent_next_turn_end_on_play"
    )
    assert delayed_rule.trigger == "self_played"
    assert delayed_rule.handler_params["requires_played_from"] == "hand"


def test_extract_ss_broly_unchained_might_can_warp_opponent_hand_battle_and_return_it_next_opponent_turn() -> None:
    card = _card(
        "[Barrier] [Auto] If you have 2 or more energy and all of your opponent's energy is in Rest Mode: When this card is played, "
        "your opponent reveals their hand. You choose up to 1 Battle Card with 15000 power or less from it and send it to its owner's Warp. "
        "At the end of your opponent's next turn, return the card sent to the Warp by this skill to its owner's hand."
    )
    rules = extract_effect_rules_from_card(card)
    warp_rule = next(r for r in rules if r.handler_id == "auto_send_up_to_n_opponent_hand_battle_to_warp_on_play")
    assert warp_rule.trigger == "self_played"
    assert warp_rule.handler_params["max_targets"] == 1
    assert warp_rule.handler_params["max_power"] == 15000
    assert any(
        r.handler_id == "auto_schedule_return_cards_warped_by_source_skill_to_owner_hand_on_opponent_next_turn_end_on_play"
        for r in rules
    )


def test_extract_broly_br_servant_can_add_marker_and_warp_opponent_hand_then_return_it_next_turn() -> None:
    card = _card(
        "[Swap 5](Red): Mono-red <Broly: Br> with an energy cost of 5. "
        "[Servant] "
        "[Auto] If your Leader Card is red: When this card is played, choose up to 1 of your red Unison Cards, add a marker to it, "
        "then your opponent chooses 1 card in their hand and sends it to their Warp. "
        "At the end of your opponent's next turn, they add the card sent to their Warp by this skill from their Warp to their hand."
    )
    rules = extract_effect_rules_from_card(card)
    marker_rule = next(r for r in rules if r.handler_id == "auto_add_markers_to_matching_owner_unison_on_play")
    assert marker_rule.trigger == "self_played"
    assert marker_rule.handler_params["max_targets"] == 1
    assert marker_rule.handler_params["amount"] == 1
    assert marker_rule.handler_params["allowed_colors"] == "red"
    warp_rule = next(r for r in rules if r.handler_id == "auto_send_up_to_n_opponent_hand_to_warp_on_play")
    assert warp_rule.trigger == "self_played"
    assert warp_rule.handler_params["max_targets"] == 1
    delayed_rule = next(
        r
        for r in rules
        if r.handler_id == "auto_schedule_return_cards_warped_by_source_skill_to_owner_hand_on_opponent_next_turn_end_on_play"
    )
    assert delayed_rule.trigger == "self_played"


def test_extract_kahseral_the_righteous_can_draw_and_send_opponent_hand_to_warp_on_play() -> None:
    card = _card(
        "[Auto] When you play this card, draw 1 card, then your opponent chooses 1 card in their hand and sends it to their Warp. "
        "[Auto][Sparking 5] When this card attacks, choose up to 1 Leader Card and up to 1 Battle Card other than this card, and those cards get +5000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    assert any(r.trigger == "self_played" and r.handler_id == "auto_draw_n" and r.handler_params.get("amount") == 1 for r in rules)
    warp_rule = next(r for r in rules if r.handler_id == "auto_send_up_to_n_opponent_hand_to_warp_on_play")
    assert warp_rule.trigger == "self_played"
    assert warp_rule.handler_params["max_targets"] == 1


def test_extract_vegeta_the_cruel_can_ko_and_send_opponent_hand_to_warp_on_play_during_opponent_turn() -> None:
    card = _card(
        "[Counter: Play] Play this card. "
        "[Auto] When you play this card during your opponent's turn, choose up to 1 of your opponent's Battle Cards with an energy cost of 4 or less, KO it, "
        "then your opponent chooses 1 card in their hand and sends it to their Warp."
    )
    rules = extract_effect_rules_from_card(card)
    ko_rule = next(r for r in rules if r.handler_id in {"auto_ko_up_to_n_opponent_battle_on_play", "auto_ko_opponent_battle_on_play"})
    assert ko_rule.trigger == "self_played"
    assert ko_rule.handler_params["max_cost"] == 4
    assert ko_rule.handler_params["requires_opponent_turn"] is True
    warp_rule = next(r for r in rules if r.handler_id == "auto_send_up_to_n_opponent_hand_to_warp_on_play")
    assert warp_rule.trigger == "self_played"
    assert warp_rule.handler_params["max_targets"] == 1
    assert warp_rule.handler_params["requires_opponent_turn"] is True


def test_extract_android_21_the_ringleader_can_schedule_clone_token_on_opponent_next_turn_end() -> None:
    card = _card(
        "[Auto] If your Leader Card is an ≪Android≫ card: When you play this card, draw 1 card, "
        "then at the end of your opponent's next turn, play 1 Clone Token with 10000 power in your opponent's Battle Area."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_schedule_play_token_in_battle_on_play")
    assert token_rule.trigger == "self_played"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "clone token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["trigger_kind"] == "turn_end"
    assert token_rule.handler_params["trigger_player_scope"] == "opponent"
    assert token_rule.handler_params["controller_player_scope"] == "opponent"


def test_extract_play_can_create_earthling_token_on_play() -> None:
    card = _card(
        "[Auto] If your Leader is a green card with both <Trunks: Future> and <Mai: Future>: "
        "When this card is played, draw 1 card, then play 1 Earthling Token (1000 power, 0 combo cost, and 0 combo power)."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_play")
    assert token_rule.trigger == "self_played"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "earthling token"
    assert token_rule.handler_params["power"] == 1000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 0


def test_extract_owner_union_activated_can_play_ghost_token_in_rest_mode() -> None:
    card = _card(
        "[Auto] When you activate a [Union] skill, play 1 Ghost Token with 15000 power in Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_owner_union_activated")
    assert token_rule.trigger == "owner_union_activated"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "ghost token"
    assert token_rule.handler_params["power"] == 15000
    assert token_rule.handler_params["resting"] is True


def test_extract_activate_main_can_switch_self_active_and_play_two_saibaiman_tokens() -> None:
    card = _card(
        "[Activate: Main][Once per turn](Blue): Switch this card to Active Mode and play 2 Saibaiman Tokens. "
        "(Saibaiman Tokens have 5000 power, 0 combo cost, and 5000 combo power.)"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "activate_play_token_in_battle")
    assert token_rule.trigger == "self_activate_main"
    assert token_rule.handler_params["amount"] == 2
    assert token_rule.handler_params["token_name"] == "saibaiman token"
    assert token_rule.handler_params["power"] == 5000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000
    assert token_rule.handler_params["switch_self_active"] is True


def test_extract_activate_main_can_play_earthling_token_with_barrier_until_opponent_turn_end() -> None:
    card = _card(
        "[Activate: Main][Once per turn] If your Leader is a yellow <Son Goku> Z-Leader and you send 1 yellow Battle Card from your Drop to your Warp: "
        "Play 1 Earthling Token (1000 power, 0 combo cost, 0 combo power), and it gains [Barrier] until the end of your opponent's next turn."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "activate_play_token_in_battle")
    assert token_rule.trigger == "self_activate_main"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "earthling token"
    assert token_rule.handler_params["power"] == 1000
    assert token_rule.handler_params["temporary_keywords"] == "barrier"
    assert token_rule.handler_params["keyword_duration"] == "opponent_turn"


def test_extract_activate_main_can_play_ghost_tokens_then_buff_all_ghost_tokens() -> None:
    card = _card(
        "[Activate: Main] Place 1 of your Z-Energy in your Drop, and remove this card from the game: "
        "If your Leader is a blue <Frieza's Army> card and you have 2 or more blue Z-Extra Cards in your Battle Area, "
        "play 2 Ghost Tokens with 15000 power, then choose all of your Ghost Tokens and they gain [Revenge] until the end of your opponent's next turn."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "activate_play_token_in_battle")
    assert token_rule.trigger == "self_activate_main"
    assert token_rule.handler_params["amount"] == 2
    assert token_rule.handler_params["token_name"] == "ghost token"
    assert token_rule.handler_params["power"] == 15000
    assert "temporary_keywords" not in token_rule.handler_params
    assert token_rule.handler_params["post_play_buff_owner_battle_target_policy"] == "all"
    assert token_rule.handler_params["post_play_buff_owner_battle_grant_keyword"] == "Revenge"
    assert token_rule.handler_params["post_play_buff_owner_battle_keyword_duration"] == "opponent_turn"
    assert token_rule.handler_params["post_play_buff_owner_battle_required_name_contains"] == "GHOST TOKEN"


def test_extract_activate_main_can_schedule_friezas_army_token_for_turn_end() -> None:
    card = _card(
        "[+1][Activate: Main] Add up to 1 card from your life to your hand; at the end of the turn, play 1 Frieza's Army Token with 10000 power."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "activate_schedule_play_token_in_battle")
    assert token_rule.trigger == "self_activate_main"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "frieza's army token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["trigger_kind"] == "turn_end"
    assert token_rule.handler_params["trigger_player_scope"] == "current"
    assert token_rule.handler_params["require_next_turn"] is False
    assert token_rule.handler_params["add_from_life_to_hand_max_targets"] == 1


def test_extract_activate_main_can_play_self_from_hand_then_play_saibaiman_token() -> None:
    card = _card(
        "[Activate: Main][Limit 1](Blue), if your Leader is a blue <Nappa> card and you have 2 or more energy: "
        "Play this card from your hand, then play 1 Saibaiman Token (5000 power, 0 combo cost, and 5000 combo power)."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "activate_play_self_from_hand")
    assert token_rule.trigger == "self_activate_main"
    assert token_rule.handler_params["post_play_token_amount"] == 1
    assert token_rule.handler_params["post_play_token_name"] == "saibaiman token"
    assert token_rule.handler_params["post_play_token_power"] == 5000
    assert token_rule.handler_params["post_play_token_combo_cost"] == 0
    assert token_rule.handler_params["post_play_token_combo_power"] == 5000


def test_extract_activate_battle_can_play_saibaiman_token_then_combo_from_drop() -> None:
    card = _card(
        "[Activate: Battle][Once per turn](Blue), if it's your turn: "
        "Play 1 Saibaiman Token, then use up to 1 mono-blue card with 5000 combo power from your Drop in a combo with its skills negated for the turn. "
        "(Saibaiman Tokens have 5000 power, 0 combo cost, and 5000 combo power.)"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "activate_play_token_in_battle")
    assert token_rule.trigger == "self_activate_battle"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "saibaiman token"
    assert token_rule.handler_params["combo_max_targets"] == 1
    assert token_rule.handler_params["combo_source_zone"] == "drop"
    assert token_rule.handler_params["combo_allowed_colors"] == "blue"
    assert token_rule.handler_params["combo_exact_combo_power"] == 5000
    assert token_rule.handler_params["combo_negate_skills"] is True
    assert token_rule.handler_params["combo_require_mono_color"] is True


def test_extract_self_played_from_hand_can_play_majin_token_then_place_opponent_battle_under_self() -> None:
    card = _card(
        "[Auto] When this card is played from your hand, play 1 Majin Token, then choose up to 1 of your opponent's Battle Cards and place it under this card. "
        "(Majin Tokens have 15000 power, 0 combo cost, and 5000 combo power.)"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_play")
    assert token_rule.trigger == "self_played"
    assert token_rule.handler_params["requires_played_from"] == "hand"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "majin token"
    assert token_rule.handler_params["post_play_place_under_self_max_targets"] == 1


def test_extract_self_played_can_play_saibaiman_token_with_blocker_and_revenge() -> None:
    card = _card(
        "[Auto] When this card is played, play 1 Saibaiman Token (5000 power, 0 combo cost, and 5000 combo power) "
        "and it gains [Blocker] and [Revenge] until the end of the turn."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_play")
    assert token_rule.trigger == "self_played"
    assert token_rule.handler_params["token_name"] == "saibaiman token"
    assert token_rule.handler_params["temporary_keywords"] == "blocker,revenge"
    assert token_rule.handler_params["keyword_duration"] == "turn"


def test_extract_activate_main_can_play_majin_token_then_add_life_to_hand() -> None:
    card = _card(
        "[Activate: Main][Limit 1] [Spirit Boost 1] "
        "Play 1 Majin Token, then add up to 1 card from your life to your hand. "
        "(Majin Tokens have 15000 power, 0 combo cost, and 5000 combo power.)"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "activate_play_token_in_battle")
    assert token_rule.trigger == "self_activate_main"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "majin token"
    assert token_rule.handler_params["add_from_life_to_hand_max_targets"] == 1


def test_extract_self_attacks_can_play_demon_realm_soldier_token() -> None:
    card = _card(
        "[Auto] Add 1 card from your life to your hand: When this card attacks, play up to 1 Demon Realm Soldier Token, "
        "and this card gets +10000 power for the turn. "
        "(Demon Realm Soldier Tokens have 5000 power, 0 combo cost, and 5000 combo power.)"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_attack")
    assert token_rule.trigger == "self_attacks"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "demon realm soldier token"
    assert token_rule.handler_params["power"] == 5000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000


def test_extract_self_attacks_can_play_majin_token_in_rest_mode() -> None:
    card = _card(
        "[Auto] When this card attacks, play 1 Majin Token in Rest Mode. "
        "[em](Majin Tokens have 15000 power, 0 combo cost, and 5000 combo power.)[/em]"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_attack")
    assert token_rule.trigger == "self_attacks"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "majin token"
    assert token_rule.handler_params["power"] == 15000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000
    assert token_rule.handler_params["resting"] is True


def test_extract_owner_main_phase_start_can_play_multiform_tokens_until_three() -> None:
    card = _card(
        "[Auto] If your Leader is a green <Tien Shinhan> card and you discard 1 card from your hand: "
        "At the start of your Main Phase, play Multi-Form Tokens until you have 3 Multi-Form Tokens in your Battle Area. "
        "[em](Multi-Form Tokens have 10000 power, 0 combo cost, and 5000 combo power.)[/em]"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_main_phase_start")
    assert token_rule.trigger == "owner_main_phase_start"
    assert token_rule.handler_params["until_battle_count"] == 3
    assert token_rule.handler_params["token_name"] == "multi-form token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000
    assert token_rule.handler_params["auto_discard_hand_before"] == 1


def test_extract_owner_opponent_main_phase_start_can_play_clone_token_to_opponent_battle() -> None:
    card = _card(
        "[Auto][Limit 1] At the start of your opponent's Main Phase, play 2 Clone Tokens with 10000 power in your opponent's Battle Area."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_main_phase_start")
    assert token_rule.trigger == "owner_opponent_main_phase_start"
    assert token_rule.handler_params["amount"] == 2
    assert token_rule.handler_params["token_name"] == "clone token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["controller_player_scope"] == "opponent"


def test_extract_owner_card_left_battle_area_can_play_multiform_token() -> None:
    card = _card(
        "[Auto][Limit 1] When your Multi-Form Token is removed from a Battle Area, play 1 Multi-Form Token. "
        "[em](Multi-Form Tokens have 10000 power, 0 combo cost, and 5000 combo power.)[/em]"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_owner_matching_battle_left")
    assert token_rule.trigger == "owner_card_left_battle_area"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "multi-form token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000
    assert token_rule.handler_params["event_required_name_contains"] == "MULTI-FORM TOKEN"


def test_extract_owner_other_battle_played_can_play_shadow_token() -> None:
    card = _card(
        "[Auto] When you play a <Goku Black> card in your Battle Area, play 1 Shadow Token. "
        "(Shadow Tokens have 10000 power, 0 combo cost, and 5000 combo power.)"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(
        rule
        for rule in rules
        if rule.trigger == "owner_other_battle_played"
        and rule.handler_id == "auto_play_token_in_battle_on_owner_matching_battle_played"
    )
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "shadow token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000
    assert token_rule.handler_params["event_required_characters"] == "Goku Black"


def test_extract_owner_other_battle_played_can_play_clone_tokens_when_token_is_played_by_owner_extra() -> None:
    card = _card(
        "[Unique]<br>[Permanent] This card can't be used in a combo from the Battle Area and your opponent's Clone Tokens can't attack.<br>"
        "[Auto][Once per turn] When a Clone Token is played by the skill on one of your Extra Cards, play 2 Clone Tokens to your opponent's Battle Area.<br>"
        "[Activate: Main] Remove 1 of your opponent's Clone Tokens from the game: Play this card from your hand or Drop Area."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(
        rule
        for rule in rules
        if rule.trigger == "owner_other_battle_played"
        and rule.handler_id == "auto_play_token_in_battle_on_owner_matching_battle_played"
    )
    assert token_rule.handler_params["amount"] == 2
    assert token_rule.handler_params["token_name"] == "clone token"
    assert token_rule.handler_params["event_required_name_contains"] == "CLONE TOKEN"
    assert token_rule.handler_params["event_required_played_from"] == "token"
    assert token_rule.handler_params["event_required_created_by_source_card_type"] == "EXTRA"
    assert token_rule.handler_params["controller_player_scope"] == "opponent"


def test_extract_activate_main_can_remove_clone_token_to_play_self_from_hand_or_drop() -> None:
    card = _card(
        "[Activate: Main] Remove 1 of your opponent's Clone Tokens from the game: Play this card from your hand or Drop Area."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(rule for rule in rules if rule.trigger == "self_activate_main" and rule.handler_id == "activate_play_self_from_hand")
    assert play_rule.handler_params == {}


def test_extract_activate_main_can_remove_clone_token_to_play_self_from_hand_in_rest_with_marker() -> None:
    card = _card(
        "[Activate: Main] If you don't have a Unison Card in play and you choose 1 of your opponent's Clone Tokens and remove it from the game: "
        "Play this card from your hand in Rest Mode with a marker on it."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(rule for rule in rules if rule.trigger == "self_activate_main" and rule.handler_id == "activate_play_self_from_hand")
    assert play_rule.handler_params["resting"] is True
    assert play_rule.handler_params["markers"] == 1
    assert play_rule.handler_params["requires_no_owner_unison"] is True


def test_extract_activate_main_can_remove_clone_token_to_gain_power_and_critical_for_duration() -> None:
    card = _card(
        "[Activate: Main][Once per turn] Choose 1 Clone Token from your opponent's Battle Area and remove it from the game: "
        "This card gets +10000 power and [Critical] for the duration of the turn."
    )
    rules = extract_effect_rules_from_card(card)
    buff_rule = next(rule for rule in rules if rule.trigger == "self_activate_main" and rule.handler_id == "activate_gain_power_and_keyword_for_turn")
    assert buff_rule.handler_params["power_delta"] == 10000
    assert buff_rule.handler_params["grant_keyword"] == "Critical"


def test_extract_activate_main_can_remove_clone_token_to_gain_power_and_double_strike_for_duration() -> None:
    card = _card(
        "[Activate: Main][Once per turn] Choose 1 Clone Token from your opponent's Battle Area and remove it from the game: "
        "This card gets +10000 power and [Double Strike] for the duration of the turn."
    )
    rules = extract_effect_rules_from_card(card)
    buff_rule = next(rule for rule in rules if rule.trigger == "self_activate_main" and rule.handler_id == "activate_gain_power_and_keyword_for_turn")
    assert buff_rule.handler_params["power_delta"] == 10000
    assert buff_rule.handler_params["grant_keyword"] == "Double Strike"


def test_extract_activate_main_unison_can_remove_saibaiman_token_to_bottom_deck_cost_two_or_less() -> None:
    card = _card(
        "[-1][Activate: Main] Remove 1 of your Saibaiman Tokens from the game: "
        "Choose up to 1 of your opponent's Battle Cards with an energy cost of 2 or less and place it at the bottom of its owner's deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_bottom_deck_up_to_n_opponent_battle")
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_cost"] == 2


def test_extract_exact_android_21_leader_clone_token_activate_line() -> None:
    card = replace(
        _card(
            "[Auto] When you place this card in your Leader Area, choose up to 1 {Android 21's Scheme} from your deck and activate it. "
            "<br>[Activate: Main][Once per turn] Choose 1 Clone Token in your opponent's Battle Area and remove it from the game: "
            "Draw 1 card, then choose up to 1 of your opponent's Battle Cards with an energy cost of 1 and return it to its owner's hand, "
            "then at the start of your opponent's next Main Phase, choose up to 1 Blue/Green multicolor card in your energy and switch it to Active Mode."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_draw_n_add_up_to_n_from_owner_life_to_hand_then_return_up_to_n_opponent_battle_to_hand_and_schedule_energy_switch"
    )
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_cost"] == 1
    assert rule.handler_params["schedule_main_phase_energy_max_targets"] == 1
    assert rule.handler_params["schedule_main_phase_energy_allowed_colors"] == "blue,green"
    assert rule.handler_params["schedule_main_phase_energy_requires_multicolor"] is True


def test_extract_exact_android_18_leader_clone_token_activate_line() -> None:
    card = replace(
        _card(
            "[Auto] When you place this card in your Leader Area, choose up to 1 {Android 21's Scheme} from your deck and activate it. "
            "<br>[Activate: Main][Once per turn] Choose 1 Clone Token in your opponent's Battle Area and remove it from the game: "
            "Draw 1 card, choose 1 card in your life and add it to your hand, then choose up to 1 of your opponent's Battle Cards with an energy cost of 1 and return it to its owner's hand."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_draw_n_add_up_to_n_from_owner_life_to_hand_then_return_up_to_n_opponent_battle_to_hand_and_schedule_energy_switch"
    )
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["life_to_hand_amount"] == 1
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_cost"] == 1
    assert "schedule_main_phase_energy_max_targets" not in rule.handler_params


def test_extract_exact_bt20_android_21_front_activate_searches_and_buffs_self() -> None:
    card = replace(
        _card(
            "[Permanent] You can't activate Extras, and during your turn, you can't use skills to play Battle Cards.<br>"
            "[Auto] If you have an <Android 21> Z-Battle Card in play: At the end of your turn, switch up to 1 of your blue energy to Active Mode.<br>"
            "[Activate: Main][Once per turn] Add 1 card from your life to your hand: Look at up to 5 cards from the top of your deck, add up to 1 blue ≪Android≫ card among them to your hand, shuffle your deck, and this card gets +5000 power for the turn.<br>"
            "[Awaken] When your life is at 4 or less: Draw 1 card, and switch up to 1 of your energy to Active Mode."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main" and r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play"
    )
    assert rule.handler_params["look_count"] == 5
    assert rule.handler_params["max_add"] == 1
    assert rule.handler_params["allowed_colors"] == "blue"
    assert str(rule.handler_params["required_traits"]).lower() == "android"
    assert rule.handler_params["power_delta"] == 5000


def test_extract_exact_bt20_android_21_back_draws_and_switches_opponent_board_active() -> None:
    card = replace(
        _card(
            "[Permanent] During your turn, you can't use skills to play Battle Cards.<br>"
            "[Permanent] When paying energy costs for your <Android 21> cards, you can use your <Android 21> Z-Battle Cards and your opponent's Battle Cards and Unisons as energy.<br>"
            "[Activate: Main][Once per turn] Draw 1 card, and choose up to 3 of your opponent's Battle Cards and/or Unisons, ignoring [Barrier], and switch them to Active Mode."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_draw_n_and_switch_up_to_n_opponent_battle_or_unison_active"
    )
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["max_targets"] == 3
    assert rule.handler_params["ignores_barrier"] is True


def test_extract_exact_the_android_creator_draws_and_buffs_owner_battle() -> None:
    card = replace(
        _card(
            "[Activate: Main] Choose 1 Clone Token in your opponent's Battle Area and remove it from the game: "
            "Draw 1 card, then choose 1 of your Battle Cards and it gets +10000 power for the duration of the turn."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    buff_rule = next(r for r in rules if r.trigger == "self_activate_extra_from_hand" and r.handler_id == "activate_buff_owner_battle_cards")
    assert not any(r.trigger == "self_activate_extra_from_hand" and r.handler_id == "auto_draw_n" for r in rules)
    assert buff_rule.handler_params["amount"] == 1
    assert buff_rule.handler_params["target_scope"] == "owner_battle"
    assert buff_rule.handler_params["max_targets"] == 1
    assert buff_rule.handler_params["power_delta"] == 10000


def test_extract_exact_maleficent_technique_frieza_play_and_bounce_lines() -> None:
    card = _card(
        "[Activate: Main] Choose 2 Clone Tokens in your opponent's Battle Area and remove them from the game: Play this card from your hand. "
        "<br>[Auto] When you play this card, choose up to 1 of your opponent's Battle Cards with an energy cost of 3 or less and return it to its owner's hand."
    )
    rules = extract_effect_rules_from_card(card)
    activate_rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_play_self_from_hand")
    bounce_rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "auto_return_up_to_n_opponent_battle_to_hand_on_play")
    assert activate_rule.handler_params == {}
    assert bounce_rule.handler_params["max_targets"] == 1
    assert bounce_rule.handler_params["max_cost"] == 3


def test_extract_exact_frieza_common_enemy_clone_token_play_line() -> None:
    card = _card(
        "[Unique][Double Strike]<br>[Activate: Main][Limit 1](Blue), if you have 3 or more energy and you choose 3 of your opponent's Clone Tokens and remove them from the game: "
        "Play this card from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    activate_rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_play_self_from_hand")
    assert activate_rule.handler_params["min_owner_energy"] == 3
    assert activate_rule.limit_per_turn == 1


def test_extract_exact_clone_token_blocker_play_line() -> None:
    card = _card(
        "[Blocker]<br>[Activate: Main][Limit 1] Choose 3 of your opponent's Clone Tokens and remove them from the game: Play this card from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    activate_rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_play_self_from_hand")
    assert activate_rule.handler_params == {}
    assert activate_rule.limit_per_turn == 1


def test_extract_exact_clone_token_unison_plus_two_line() -> None:
    card = replace(
        _card(
            "[Activate: Main] If you don't have a Unison Card in play and you choose 1 of your opponent's Clone Tokens and remove it from the game: "
            "Play this card from your hand in Rest Mode with a marker on it.<br>"
            "[+2][Activate: Main] 1 of your mono-blue Leader Cards gets +5000 power for the turn; your opponent's Clone Tokens can't attack during your opponent's next turn.<br>"
            "[-4][Activate: Battle] This card gets +11000 power and [Double Strike] for the turn."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_buff_owner_leader_for_turn")
    assert rule.handler_params["leader_power_delta"] == 5000
    assert rule.handler_params["leader_allowed_colors"] == "blue"
    assert rule.handler_params["schedule_attack_restriction_name_contains"] == "CLONE TOKEN"


def test_extract_exact_clone_token_unison_minus_four_line() -> None:
    card = replace(
        _card(
            "[Activate: Main] If you don't have a Unison Card in play and you choose 1 of your opponent's Clone Tokens and remove it from the game: "
            "Play this card from your hand in Rest Mode with a marker on it.<br>"
            "[+2][Activate: Main] 1 of your mono-blue Leader Cards gets +5000 power for the turn; your opponent's Clone Tokens can't attack during your opponent's next turn.<br>"
            "[-4][Activate: Battle] This card gets +11000 power and [Double Strike] for the turn."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_battle" and r.handler_id == "activate_gain_power_and_keyword_for_turn")
    assert rule.handler_params["power_delta"] == 11000
    assert rule.handler_params["grant_keyword"] == "Double Strike"


def test_extract_exact_clone_token_combo_draw_line() -> None:
    card = _card(
        "[Auto] If it's your turn, choose 1 Clone Token in your opponent's Battle Area and remove it from the game: "
        "When you combo with this card, draw 1 card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_comboed" and r.handler_id == "auto_draw_n")
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["requires_owner_turn"] is True


def test_extract_exact_clone_token_combo_power_line() -> None:
    card = _card(
        "[Auto] If it's your turn, choose 1 Clone Token in your opponent's Battle Area and remove it from the game: "
        "When you combo with this card, this card gets +5000 combo power for the duration of the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_comboed" and r.handler_id == "auto_self_gain_combo_power_on_combo")
    assert rule.handler_params["combo_power_delta"] == 5000
    assert rule.handler_params["requires_owner_turn"] is True
    assert "requires_comboed_from" not in rule.handler_params


def test_extract_exact_son_gohan_universe_7_challenger_combo_buff() -> None:
    card = _card(
        "[Auto] If your Leader Card is a mono-red \u226aUniverse 7\u226b card: "
        "When this card is used in a combo from your hand, you may have your Leader Card get +1000 power for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_buff_owner_leader_for_battle_on_combo")
    assert rule.trigger == "self_comboed"
    assert rule.handler_params["power_delta"] == 1000
    assert rule.handler_params["requires_comboed_from"] == "hand"
    assert rule.handler_params["leader_allowed_colors"] == "red"
    assert rule.handler_params["leader_required_traits"] == "Universe 7"


def test_extract_exact_dodoria_entering_the_fray_rules() -> None:
    card = _card(
        "[Auto] If your Leader Card is a red \u226aFrieza's Army\u226b card, you have 2 or more energy, "
        "and you choose 1 card in your hand and discard it: When this card is played from your hand, "
        "activate up to 1 {Frieza's Spaceship} from your deck, then shuffle your deck.\n"
        "[Auto]((Red)), if you have 3 or more red energy: When this card is KO'd by your Leader Card's skill, "
        "choose up to 1 mono-red <Frieza> card with an energy cost of 5 in your hand and play it."
    )
    rules = extract_effect_rules_from_card(card)
    field_rule = next(
        r
        for r in rules
        if r.handler_id == "auto_discard_n_from_owner_hand_activate_up_to_n_named_field_extra_from_owner_deck_on_play"
    )
    assert field_rule.trigger == "self_played"
    assert field_rule.handler_params["discard_count"] == 1
    assert field_rule.handler_params["required_name_contains"] == "FRIEZA'S SPACESHIP"
    assert field_rule.handler_params["leader_required_traits"] == "Frieza's Army"
    ko_rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_hand_on_self_ko")
    assert ko_rule.trigger == "self_koed"
    assert ko_rule.handler_params["allowed_colors"] == "red"
    assert ko_rule.handler_params["required_characters"] == "Frieza"
    assert ko_rule.handler_params["max_cost"] == 5
    assert ko_rule.handler_params["required_energy_colors"] == "red"


def test_extract_exact_pincer_attack_android_18_combo_line() -> None:
    card = _card(
        "[Auto] If your Leader Card is a blue <Android 18> card and you choose 1 of your opponent's Clone Tokens and remove it from the game: "
        "When this card is used in a combo from your hand, add up to 1 {Supreme Technique Krillin} from your deck to your hand, then shuffle your deck.<br>"
        "[Auto](Blue), if your Leader Card is a blue <Android 18> card: At the end of a battle in which this card is used in a combo from your hand, play this card from your Drop Area."
    )
    rules = extract_effect_rules_from_card(card)
    combo_rule = next(r for r in rules if r.trigger == "self_comboed" and r.handler_id == "auto_add_up_to_n_from_owner_deck_to_hand_on_combo")
    assert combo_rule.handler_params["max_targets"] == 1
    assert combo_rule.handler_params["requires_comboed_from"] == "hand"
    assert combo_rule.handler_params["required_name_contains"] == "SUPREME TECHNIQUE KRILLIN"
    battle_end_rule = next(r for r in rules if r.trigger == "self_comboed_battle_end" and r.handler_id == "auto_play_self_from_combo_on_battle_end")
    assert battle_end_rule.handler_params["requires_comboed_from"] == "hand"


def test_extract_exact_supreme_technique_krillin_combo_line() -> None:
    card = _card(
        "[Blocker] (When one of your other cards is attacked, you may switch this card to Rest Mode and change the target of the attack to this card.)<br>"
        "[Auto] If it's your turn, choose 1 Clone Token from your opponent's Battle Area and remove it from the game: "
        "When you combo with this card, choose up to 1 attacking <Android 18> card and it gains [Double Strike] for the duration of the battle. <br>"
        "[Auto](Blue), during your turn: When you combo with this card from your hand with an <Android 18> card in battle, play this card at the end of the battle."
    )
    rules = extract_effect_rules_from_card(card)
    blocker_rule = next(r for r in rules if r.trigger == "self_blocker_activated" and r.handler_id == "noop_auto")
    combo_rule = next(r for r in rules if r.trigger == "self_comboed" and r.handler_id == "auto_buff_up_to_n_owner_battles_for_battle_on_combo")
    assert blocker_rule.source_text.lower().startswith("[blocker]")
    assert combo_rule.handler_params["max_targets"] == 1
    assert combo_rule.handler_params["grant_keyword"] == "Double Strike"
    assert combo_rule.handler_params["require_owner_attacker"] is True
    assert combo_rule.handler_params["required_characters"] == "Android 18"


def test_extract_exact_supreme_technique_son_goku_play_line() -> None:
    card = _card(
        "[Blocker] <br>[Arrival Blue/Green](Blue) (Play this card from your hand when you have blue and green cards in your Combo Area.)<br>"
        "[Energy-Exhaust] (If this card is placed in an Energy Area from any area, it must be placed there in Rest Mode.)<br>"
        "[Auto] Choose 2 Clone Tokens in your opponent's Battle Area and remove them from the game: "
        "When you play this card, your opponent chooses 1 card from their hand and places it in their Drop Area."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "auto_opponent_discards_n_from_hand_on_play")
    assert rule.handler_params["amount"] == 1


def test_extract_over_realm_reminder_text_noop() -> None:
    card = _card(
        "[Over Realm 4] (If you have at least 4 cards in your Drop Area, you can play this card from your hand by sending all "
        "cards in your Drop Area to your Warp. At the end of the turn, send this card from your Battle Area to your Warp.)"
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "noop_auto")
    assert "[over realm" in rule.source_text.lower()


def test_extract_critical_reminder_text_noop() -> None:
    card = _card(
        "[Critical] (When this card inflicts damage to your opponent's life, they place that many cards in their Drop Area instead of their hand.)"
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_attacks" and r.handler_id == "noop_auto")
    assert "[critical]" in rule.source_text.lower()


def test_extract_on_play_look_top_add_universe_then_shuffle() -> None:
    card = _card(
        "[Auto] When you play this card, look at up to 5 cards from the top of your deck. "
        "Choose up to 1 ≪Universe 7≫ among them and add it to your hand. Then, shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play")
    assert rule.handler_params["look_count"] == 5
    assert rule.handler_params["max_add"] == 1
    assert rule.handler_params["required_traits"] == "Universe 7"
    assert rule.handler_params["shuffle_deck_after"] is True


def test_extract_barrier_reminder_text_noop() -> None:
    card = _card("[Barrier] (This card can't be chosen by the skills of your opponent's cards.)")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "noop_auto")
    assert "[barrier]" in rule.source_text.lower()


def test_extract_unlimited_copies_permanent_noop() -> None:
    card = _card("[Permanent] You can include as many copies of this card in your deck as you like.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "noop_auto")
    assert "as many copies" in rule.source_text.lower()


def test_extract_activate_main_compliment_noop() -> None:
    card = _card("[Activate: Main] You and your opponent compliment each other.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "noop_auto")
    assert "compliment each other" in rule.source_text.lower()


def test_extract_blocker_keyword_only_noop() -> None:
    card = _card("[Blocker]")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "noop_auto")
    assert rule.source_text.strip().lower() == "[blocker]"


def test_extract_field_reminder_text_noop() -> None:
    card = _card(
        "[Field] (Place and activate this card in your Battle Area. It remains in your Battle Area until you activate another [Field]. "
        "When you do, place this card in its owner's Drop Area.)"
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "noop_auto")
    assert "[field]" in rule.source_text.lower()


def test_extract_aegis_reminder_text_noop() -> None:
    card = _card(
        "[Aegis Blue/Yellow][Once per turn] (If it's your opponent's turn, you can activate this during the Defense Step by placing cards in your hand "
        "in your Drop Area that match all colors specified by [Aegis]: Choose up to 2 of your energy and switch them to Active Mode.)"
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_aegis_activated" and r.handler_id == "noop_auto")
    assert "[aegis blue/yellow]" in rule.source_text.lower()


def test_extract_counter_attack_play_this_card_reminder_noop() -> None:
    card = _card("[Counter: Attack] Negate the attack and play this card. ([Counter] is activated from your hand by paying the card's energy cost.)")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "counter_attack" and r.handler_id == "noop_auto")
    assert "negate the attack and play this card" in rule.source_text.lower()


def test_extract_double_strike_reminder_text_noop() -> None:
    card = _card("[Double Strike] (This card inflicts 2 damage instead of 1 when attacking)")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_attacks" and r.handler_id == "noop_auto")
    assert "[double strike]" in rule.source_text.lower()


def test_extract_dual_attack_reminder_text_noop() -> None:
    card = _card("[Dual Attack] (Once per turn, when this card attacks, switch this card to Active Mode after the battle.)")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_attacks_battle_end" and r.handler_id == "noop_auto")
    assert "[dual attack]" in rule.source_text.lower()


def test_extract_energy_exhaust_reminder_text_noop() -> None:
    card = _card("[Energy-Exhaust] (If this card is placed in an Energy Area from any area, it must be placed there in Rest Mode.)")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "noop_auto")
    assert "[energy-exhaust]" in rule.source_text.lower()


def test_extract_field_extra_placed_add_matching_from_owner_deck_to_hand() -> None:
    card = _card(
        "[Field] (Place and activate this card in your Battle Area. It remains in your Battle Area until you activate another [Field]. "
        "When you do, place this card in its owner's Drop Area.)<br>"
        "[Auto] When this card is placed in a Battle Area, choose up to 1 green ≪Great Ape≫ card from your deck, add it to your hand, then shuffle your deck.<br>"
        "[Activate: Main] Switch this card to Rest Mode: Choose up to 1 red or green ≪Saiyan≫ card in your Battle Area, and it gets +5000 power for the duration of the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_field_extra_placed"
        and r.handler_id == "auto_add_up_to_n_from_owner_deck_to_hand_on_play"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "green"
    assert rule.handler_params["required_traits"] == "Great Ape"
    assert rule.handler_params["shuffle_deck_after"] is True


def test_extract_field_extra_placed_restrict_opponent_battle_skills_while_self_in_battle() -> None:
    card = replace(
        _card(
            "[Field] If your Leader is a blue <Cooler> card :\n"
            "[Permanent] The [Field] skill on this card in your hand can also be activated at [Activate: Battle] timings.\n"
            "[Auto] When this card is placed in a Battle Area, choose up to 1 of your opponent's Battle Cards and it can't activate skills while this card is in a Battle Area."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_field_extra_placed"
        and r.handler_id == "auto_restrict_up_to_n_opponent_battle_skills_while_self_in_battle_on_field_extra_placed"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["leader_allowed_colors"] == "blue"
    assert rule.handler_params["leader_required_characters"] == "Cooler"


def test_extract_field_extra_placed_grants_barrier_to_matching_owner_battle_while_self_in_battle() -> None:
    card = replace(
        _card(
            "[Field] If your Leader is a blue <Cooler> card :\n"
            "[Permanent] The [Field] skill on this card in your hand can also be activated at [Activate: Battle] timings.\n"
            "[Auto] When this card is placed in a Battle Area, choose up to 1 of your blue <Cooler> or ≪Cooler's Armored Squadron≫ Battle Cards and it gains [Barrier] while this card is in a Battle Area."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_field_extra_placed"
        and r.handler_id == "auto_grant_keyword_to_up_to_n_owner_battle_while_self_in_battle_on_field_extra_placed"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["grant_keyword"] == "barrier"
    assert rule.handler_params["allowed_colors"] == "blue"
    assert rule.handler_params["required_name_contains"] == "COOLER"
    assert rule.handler_params["leader_allowed_colors"] == "blue"
    assert rule.handler_params["leader_required_characters"] == "Cooler"


def test_extract_activate_main_add_dragon_ball_from_deck_or_life_to_hand() -> None:
    card = _card(
        "[Permanent] This card can't attack.<br>"
        "[Activate: Main] Switch this card to Rest Mode: Choose up to 2 [Dragon Ball] cards from your deck or life and add them to your hand. "
        "Then shuffle any areas you looked through.<br>"
        "[Wish] When there are 7 [Dragon Ball] cards in your Drop Area: Choose up to 1 ≪Desire≫ card in your Drop Area, add it to your hand, and flip this card over."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_add_up_to_n_from_owner_deck_to_hand")
    assert rule.handler_params["max_targets"] == 2
    assert rule.handler_params["source_pool"] == "deck_or_life"
    assert rule.handler_params["required_runtime_labels"] == "dragon ball"
    assert rule.handler_params["shuffle_searched_zones"] is True


def test_extract_activate_main_add_self_from_drop_to_hand_with_gotenks_gate() -> None:
    card = _card(
        "[Activate: Main] If your Leader Card is a yellow &lt;Gotenks: Adolescence&gt; card and you choose 1 yellow card in your hand and discard it: "
        "Add this card from your Drop Area to your hand, and you can't activate the [Activate: Main] skill on copies of this card for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_add_self_from_owner_drop_to_hand")
    assert rule.handler_params["leader_allowed_colors"] == "yellow"
    assert rule.handler_params["leader_required_characters"] == "Gotenks: Adolescence"


def test_extract_self_played_can_play_shadow_token_and_grant_blocker_for_turn() -> None:
    card = _card(
        "[Counter: Attack] Negate the attack and play this card.<br>[Permanent] If it's your opponent's turn and your Leader is a Z-Leader, "
        "reduce the energy cost of this card in your hand by 1.<br>[Auto](Blue), if your Leader is a blue <Goku Black>: "
        "When this card is played, draw 1 card, play 1 Shadow Token (10000 power, 0 combo cost, and 5000 combo power), and that card gains [Blocker] for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_play")
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "shadow token"
    assert token_rule.handler_params["temporary_keywords"] == "blocker"
    assert token_rule.handler_params["keyword_duration"] == "turn"


def test_extract_self_played_from_hand_can_play_shadow_tokens_with_blocker_until_opponent_turn() -> None:
    card = _card(
        "[Energy-Exhaust][Deflect][Double Strike]<br>[Auto] At the end of your turn, switch up to 1 of your Blue/Yellow multicolor energy to Active Mode.<br>"
        "[Auto] When this card is played from your hand, play 4 Shadow Tokens, and they gain [Blocker] until the end of your opponent's next turn. "
        "(Shadow Tokens have 10000 power, 0 combo cost, and 5000 combo power.)"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_play")
    assert token_rule.handler_params["amount"] == 4
    assert token_rule.handler_params["token_name"] == "shadow token"
    assert token_rule.handler_params["requires_played_from"] == "hand"
    assert token_rule.handler_params["temporary_keywords"] == "blocker"
    assert token_rule.handler_params["keyword_duration"] == "opponent_turn"


def test_extract_self_played_can_play_cell_jr_tokens_from_when_you_play_this_card_if_clause() -> None:
    card = _card(
        "[Auto] When you play this card, if your Leader Card is <Cell>, play 2 Cell Jr. tokens. "
        "(Cell Jr. tokens have 10000 power, 0 combo cost, 5000 combo power)"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_play")
    assert token_rule.handler_params["amount"] == 2
    assert token_rule.handler_params["token_name"] == "cell jr. token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000


def test_extract_self_played_can_draw_two_and_play_two_cell_jr_tokens() -> None:
    card = _card(
        "[Auto] When you play this card, if your Leader Card is an ≪Android≫ , draw 2 cards and play 2 Cell Jr. tokens. "
        "(Cell Jr. tokens have 10000 power, 0 combo cost, and 5000 combo power)"
    )
    rules = extract_effect_rules_from_card(card)
    draw_rule = next(rule for rule in rules if rule.handler_id == "auto_draw_n")
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_play")
    assert draw_rule.handler_params["amount"] == 2
    assert token_rule.handler_params["amount"] == 2
    assert token_rule.handler_params["token_name"] == "cell jr. token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000


def test_extract_self_played_can_play_earthling_token_with_leader_condition() -> None:
    card = _card(
        "[Auto] If your Leader is a green card with both <Trunks: Future> and <Mai: Future>: "
        "When this card is played, play 1 Earthling Token (1000 power, 0 combo cost, and 0 combo power)."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_play")
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "earthling token"
    assert token_rule.handler_params["power"] == 1000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 0


def test_extract_activate_main_can_play_self_from_hand_and_play_earthling_token() -> None:
    card = _card(
        "[Activate: Main][Limit 1](Green), if your Leader is green and you have 3 or more energy: "
        "Play this card from your hand, and play 1 Earthling Token. (Earthling Tokens have 1000 power, 0 combo cost, and 0 combo power.)"
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(rule for rule in rules if rule.handler_id == "activate_play_self_from_hand")
    assert play_rule.handler_params["post_play_token_amount"] == 1
    assert play_rule.handler_params["post_play_token_name"] == "earthling token"
    assert play_rule.handler_params["post_play_token_power"] == 1000
    assert play_rule.handler_params["post_play_token_combo_cost"] == 0
    assert play_rule.handler_params["post_play_token_combo_power"] == 0


def test_extract_self_comboed_from_battle_can_play_multiform_token_in_rest_mode() -> None:
    card = _card(
        "[Counter: Attack]Negate the attack and play this card in Rest Mode.<br>"
        "[Auto] When this card is used in a combo from your Battle Area, play 1 Multi-Form Token in Rest Mode. "
        "(Multi-Form Tokens have 10000 power, 0 combo cost, and 5000 combo power.)"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_combo")
    assert token_rule.trigger == "self_comboed"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "multi-form token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000
    assert token_rule.handler_params["resting"] is True
    assert token_rule.handler_params["requires_comboed_from"] == "battle"


def test_extract_self_comboed_from_battle_can_play_four_multiform_tokens_on_opponent_turn() -> None:
    card = _card(
        "[Auto] When this card is played, draw 1 card.<br>"
        "[Auto] \u2461, if it's your opponent's turn: When this card is used in a combo from your Battle Area, "
        "play 4 Multi-Form Tokens. (Multi-Form Tokens have 10000 power, 0 combo cost, and 5000 combo power.)"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_combo")
    assert token_rule.trigger == "self_comboed"
    assert token_rule.handler_params["amount"] == 4
    assert token_rule.handler_params["token_name"] == "multi-form token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000
    assert token_rule.handler_params["requires_opponent_turn"] is True
    assert token_rule.handler_params["requires_comboed_from"] == "battle"


def test_extract_self_comboed_from_hand_can_play_saibaiman_with_unique_and_blocker() -> None:
    card = _card(
        "[Super Combo][Energy-Exhaust]\n"
        "[Auto] If your Leader Card is red or green: When this card is used in a combo from your hand, "
        "play 1 Saibaiman Token, and it gains [Unique] and [Blocker] for the turn. "
        "(Saibaiman Tokens have 5000 power, 0 combo cost, and 5000 combo power.)"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_combo")
    assert token_rule.trigger == "self_comboed"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "saibaiman token"
    assert token_rule.handler_params["power"] == 5000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000
    assert token_rule.handler_params["temporary_keywords"] == "unique,blocker"
    assert token_rule.handler_params["keyword_duration"] == "turn"
    assert token_rule.handler_params["requires_comboed_from"] == "hand"


def test_extract_self_played_can_play_chilleds_army_tokens_with_power_only_text() -> None:
    card = _card(
        "[Deflect]<br>[Auto] When this card is played, play 2 Chilled's Army Tokens with 10000 power.<br>"
        "[Activate: Main](Green)(Green), discard this card from your hand: Choose up to 1 of your opponent's Battle Cards "
        "with an energy cost less than or equal to the number of cards in their hand, ignoring [Barrier], and KO it.<br>"
        "[Activate: Main][Once per turn] Choose up to 2 of your Chilled's Army Tokens and they get +5000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_play")
    assert token_rule.trigger == "self_played"
    assert token_rule.handler_params["amount"] == 2
    assert token_rule.handler_params["token_name"] == "chilled's army token"
    assert token_rule.handler_params["power"] == 10000


def test_extract_self_played_can_play_meda_token_exact_card() -> None:
    card = _card(
        "[Permanent][Bond 3] This card gains [Dual Attack].<br>"
        "[Auto] When this card is played, play 1 Meda Token. (Meda Tokens have 5000 power, 0 combo cost, and 5000 combo power.)<br>"
        "[Activate: Main][Limit 1](Yellow), if a <Medamatcha> card with an energy cost of 3 and combo cost of 1 is in your Z-Energy: Play this card from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_play")
    assert token_rule.trigger == "self_played"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "meda token"
    assert token_rule.handler_params["power"] == 5000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000


def test_extract_self_played_can_ko_then_play_ghost_tokens_then_discard() -> None:
    card = _card(
        "[Deflect][Dual Attack]<br>"
        "[Union-Fusion](Green)(Green)(Green)(Green), if you have 4 or more energy and draw 2 cards: Green <Son Goten> and green <Trunks: Youth>.<br>"
        "[Permanent] If your Leader is a Z-Leader or you have a Z-Battle Card in play, reduce the skill cost of this card's [Union] skill in your hand by (Green).<br>"
        "[Auto] If your Leader is green and has <Gotenks> in its character name: When this card is played, choose up to 1 of your opponent's Battle Cards, "
        "ignoring [Barrier], KO it, play 2 Ghost Tokens with 15000 power, and your opponent discards 1 card from their hand."
    )
    rules = extract_effect_rules_from_card(card)
    ko_rule = next(r for r in rules if r.handler_id in {"auto_ko_up_to_n_opponent_battle_on_play", "auto_ko_opponent_battle_on_play"})
    token_rule = next(r for r in rules if r.handler_id == "auto_play_token_in_battle_on_play")
    discard_rule = next(r for r in rules if r.handler_id == "auto_opponent_discards_n_from_hand_on_play")
    assert ko_rule.trigger == "self_played"
    assert token_rule.trigger == "self_played"
    assert discard_rule.trigger == "self_played"
    assert token_rule.handler_params["amount"] == 2
    assert token_rule.handler_params["token_name"] == "ghost token"
    assert token_rule.handler_params["power"] == 15000
    assert discard_rule.handler_params["amount"] == 1


def test_extract_dark_duo_dabura_can_return_cards_warped_by_its_skill_when_it_leaves_battle() -> None:
    card = _card(
        "[Auto] When you play this card, choose up to 2 cards in your opponent's hand and send them to their Warp. "
        "[Auto] When this card leaves the Battle Area, your opponent adds all cards sent to the Warp with this card's skill to their hand."
    )
    rules = extract_effect_rules_from_card(card)
    leave_rule = next(
        r for r in rules if r.handler_id == "auto_return_cards_warped_by_source_skill_to_owner_hand_on_owner_matching_battle_left"
    )
    assert leave_rule.trigger == "owner_card_left_battle_area"


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


def test_extract_combo_draw_rule_with_sparking_and_leader_condition() -> None:
    card = _card("[Super Combo][Auto][Sparking 5] When you combo with this card, if your Leader Card is red, draw 1 card.")
    rules = extract_effect_rules_from_card(card)
    combo_draw = next(r for r in rules if r.trigger == "self_comboed" and r.handler_id == "auto_draw_n")
    assert combo_draw.handler_params["amount"] == 1
    assert combo_draw.handler_params["min_owner_drop"] == 5
    assert "red" in str(combo_draw.handler_params.get("requires_leader", "")).lower()


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


def test_extract_beerus_belligerent_god_rule() -> None:
    card = _card(
        "[Auto][Once per turn] Add 1 card from your life to your hand: "
        "When this card attacks an opponent's Battle Card, switch this card to Active Mode, and it gets +15000 power for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_pay_life_on_attack_gain_power_and_keyword_for_turn")
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["life_to_hand"] == 1
    assert rule.handler_params["power_delta"] == 15000
    assert rule.handler_params["switch_self_active"] is True
    assert rule.handler_params["power_duration"] == "battle"
    assert rule.handler_params["required_attack_target_zone"] == "battle"


def test_extract_whis_beerus_backup_rules() -> None:
    card = _card(
        "[Auto] When this card is played from your hand, choose up to 1 blue <Beerus> card in your Battle Area, and it can attack Battle Cards without [Barrier] in Active Mode for the turn.\n"
        "[Auto][Limit 1] If this card is in your Combo Area: When a blue <Beerus> card in your Battle Area attacks and KOs an opponent's Battle Card, draw 1 card."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(r for r in rules if r.handler_id == "auto_grant_attack_active_battle_without_barrier_for_turn_on_play")
    assert play_rule.trigger == "self_played"
    assert play_rule.handler_params["max_targets"] == 1
    assert play_rule.handler_params["allowed_colors"] == "blue"
    assert play_rule.handler_params["required_characters"] == "Beerus"
    combo_rule = next(r for r in rules if r.trigger == "owner_battle_ko_opponent_battle_battle_end" and r.handler_id == "auto_draw_n")
    assert combo_rule.handler_params["amount"] == 1
    assert combo_rule.handler_params["attacker_allowed_colors"] == "blue"
    assert combo_rule.handler_params["attacker_required_characters"] == "Beerus"


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


def test_extract_krillin_attack_search_does_not_false_match_awaken_draw() -> None:
    card = replace(_card(
        "[Auto] When this card attacks, look at up to 5 cards from the top of your deck, "
        "add up to 1 red Earthling card among them to your hand, then shuffle your deck. "
        "[Awaken] When your life is at 4 or less: You may draw 1 card, switch up to 1 of your energy to Active Mode, "
        "and flip this card over."
    ), card_type="LEADER")
    rules = extract_effect_rules_from_card(card)
    search = next(
        r for r in rules if r.trigger == "owner_leader_attacks" and r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play"
    )
    assert search.handler_params["look_count"] == 5
    assert search.handler_params["max_add"] == 1
    assert search.handler_params["allowed_colors"] == "red"
    assert search.handler_params["required_traits"] == "Earthling"
    assert not any(r.trigger == "self_attacks" and r.handler_id == "auto_draw_n" for r in rules)


def test_extract_bardock_attack_search_does_not_false_match_awaken_draw() -> None:
    card = replace(_card(
        "[Auto] When this card attacks, look at up to 5 cards from the top of your deck, "
        "add up to 1 black card with {SS4} in its card name among them to your hand, then shuffle your deck. "
        "[Awaken] When your life is at 4 or less: You may draw 2 cards and flip this card over."
    ), card_type="LEADER")
    rules = extract_effect_rules_from_card(card)
    search = next(
        r for r in rules if r.trigger == "owner_leader_attacks" and r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play"
    )
    assert search.handler_params["look_count"] == 5
    assert search.handler_params["max_add"] == 1
    assert search.handler_params["allowed_colors"] == "black"
    assert search.handler_params["required_name_contains"] == "SS4"
    assert not any(r.trigger == "self_attacks" and r.handler_id == "auto_draw_n" for r in rules)


def test_extract_zamasu_scheme_activate_main_warp_and_unison_families() -> None:
    card = replace(_card(
        "[Empower Black 2] [Activate: Main][Limit 1] If your Leader is a black <Goku Black> card, "
        "you have 2 or more energy, and you place 1 of your Z-Energy into its owner's Drop : "
        "Play this card with 0 markers on it from your Warp. "
        "[UNISON +1][Activate: Main] Send 1 card from your hand to its owner's Warp : "
        "Add up to 1 black <Zamasu> card with an energy cost of 7 from your Warp to your hand."
    ), card_type="UNISON")
    rules = extract_effect_rules_from_card(card)
    play_self = next(r for r in rules if r.handler_id == "activate_play_self_from_warp")
    assert play_self.trigger == "self_activate_main"
    assert play_self.handler_params["markers"] == 0
    assert play_self.handler_params["required_source_zone"] == "warp"
    assert play_self.handler_params["min_owner_energy"] == 2
    assert "black" in str(play_self.handler_params.get("requires_leader", "")).lower()

    add_from_warp = next(r for r in rules if r.handler_id == "activate_add_up_to_n_from_owner_warp_to_hand")
    assert add_from_warp.trigger == "self_activate_main"
    assert add_from_warp.handler_params["required_source_zone"] == "unison"
    assert add_from_warp.handler_params["max_add"] == 1
    assert add_from_warp.handler_params["max_cost"] == 7
    assert add_from_warp.handler_params["allowed_colors"] == "black"
    assert add_from_warp.handler_params["required_characters"] == "Zamasu"


def test_extract_ss2_trunks_pursuit_hand_to_drop_or_warp_and_play_from_warp_rules() -> None:
    card = _card(
        "[Critical] [Permanent] If this card would leave the Battle Area, remove it from the game instead. "
        "[Auto][Limit 1] When this card in your hand is placed into its owner's Drop or sent to its owner's Warp, "
        "place up to 1 black or white card with 15000 power or less from your deck into its owner's Drop or send it to its owner's Warp, then shuffle your deck. "
        "[Activate: Main]{b}, if your Leader is black and you have 3 or more energy : Play this card from your Warp."
    )
    rules = extract_effect_rules_from_card(card)

    trigger_rule = next(
        r for r in rules if r.trigger == "self_in_hand_sent_to_drop_or_warp"
        and r.handler_id == "auto_place_up_to_n_from_owner_deck_to_destination_zone"
    )
    assert trigger_rule.limit_per_turn == 1
    assert trigger_rule.handler_params["max_targets"] == 1
    assert trigger_rule.handler_params["max_power"] == 15000
    assert trigger_rule.handler_params["required_card_type"] == "BATTLE"
    assert trigger_rule.handler_params["mirror_destination_zone"] is True
    assert trigger_rule.handler_params["allowed_colors"] == "black,white"

    play_self = next(r for r in rules if r.handler_id == "activate_play_self_from_warp")
    assert play_self.trigger == "self_activate_main"
    assert play_self.handler_params["required_source_zone"] == "warp"
    assert play_self.handler_params["min_owner_energy"] == 3
    assert "black" in str(play_self.handler_params.get("requires_leader", "")).lower()


def test_extract_tiny_golden_warrior_next_ex_evolve_from_drop_rule() -> None:
    card = replace(
        _card(
            "[Permanent] This card gains ≪Earthling≫ in all areas. "
            "[Activate: Main][Limit 1] If your Leader is a red <Krillin> card : "
            "The next time you activate [EX-Evolve] on your red <Son Goten> or <Trunks : Youth> card during this turn, "
            "it can also activate from its owner's Drop."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_grant_next_ex_evolve_from_owner_drop")
    assert rule.trigger == "self_activate_extra_from_hand"
    assert rule.limit_per_turn == 1
    assert rule.handler_params["uses_remaining"] == 1
    assert rule.handler_params["allowed_colors"] == "red"
    assert "krillin" in str(rule.handler_params.get("requires_leader", "")).lower() or "krillin" in str(rule.handler_params.get("required_leader_traits", "")).lower()
    assert "Son Goten" in str(rule.handler_params.get("required_characters", ""))
    assert "Trunks" in str(rule.handler_params.get("required_characters", ""))


def test_extract_jaguars_island_challenge_stage_rules() -> None:
    card = replace(
        _card(
            "[Barrier] "
            "[Permanent] This card can't attack. "
            "[Auto] When you activate a red ≪Earthling≫ Extra from your hand, add 1 marker to this card. "
            "[UNISON -3][Activate: Main/Battle] If your Leader is a red <Krillin> card and you place 4 red ≪Earthling≫ Extras from your Drop at the bottom of their owner's deck : "
            "The next time you activate an [Activate] skill on a red Extra from your hand during this turn, reduce the skill cost by {1}."
        ),
        card_type="Z-UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    auto_rule = next(r for r in rules if r.handler_id == "auto_add_markers_on_owner_activate_extra_from_hand")
    assert auto_rule.trigger == "owner_activate_extra_from_hand"
    assert auto_rule.handler_params["amount"] == 1
    assert auto_rule.handler_params["allowed_colors"] == "red"
    assert auto_rule.handler_params["required_traits"] == "Earthling"
    assert auto_rule.handler_params["required_card_type"] == "EXTRA"

    reduce_rules = [r for r in rules if r.handler_id == "activate_reduce_next_matching_extra_skill_cost_from_hand"]
    assert {r.trigger for r in reduce_rules} == {"self_activate_main", "self_activate_battle"}
    assert all(r.handler_params["amount"] == 1 for r in reduce_rules)
    assert all(r.handler_params["required_card_type"] == "EXTRA" for r in reduce_rules)
    assert all(r.handler_params["allowed_colors"] == "red" for r in reduce_rules)
    assert any("krillin" in str(r.handler_params.get("required_leader_traits", "")).lower() for r in reduce_rules)


def test_extract_activate_battle_can_reduce_next_matching_arrival_skill_cost() -> None:
    card = _card(
        "[Activate: Battle][Once per turn] If it's your opponent's turn and you have 1 or more red cards and 1 or more green cards in your Combo Area: "
        "During this turn, the next time your activate [Arrival Red/Green] on a <Vegeta> or <Trunks: Future> card with an energy cost of 5 in your hand, reduce the skill cost by {r}."
    )
    rules = extract_effect_rules_from_card(card)
    reduce_rule = next(r for r in rules if r.handler_id == "activate_reduce_next_matching_arrival_skill_cost_from_hand")
    assert reduce_rule.trigger == "self_activate_battle"
    assert reduce_rule.handler_params["required_arrival_colors"] == "green,red"
    assert reduce_rule.handler_params["required_characters"] == "Trunks: Future,Vegeta"
    assert reduce_rule.handler_params["max_energy_cost"] == 5
    assert reduce_rule.handler_params["reduction_cost_token"] == "r"
    assert reduce_rule.handler_params["uses_remaining"] == 1
    assert reduce_rule.once_per_turn is True


def test_extract_activate_main_can_reduce_next_matching_z_awaken_cost_in_z_deck() -> None:
    card = _card(
        "[Activate: Main][Once per turn][Spirit Boost 1] If you have {Power Ball, Mimicking the Moon} in your Battle Area: "
        "Reduce the [Z-Awaken] skill cost on {Son Gohan, Power of a Rampaging Great Ape} in your Z-Deck by (Yellow) for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    reduce_rule = next(r for r in rules if r.handler_id == "activate_reduce_next_matching_z_awaken_cost_in_z_deck")
    assert reduce_rule.trigger == "self_activate_main"
    assert reduce_rule.handler_params["target_required_name_contains"] == "SON GOHAN, POWER OF A RAMPAGING GREAT APE"
    assert reduce_rule.handler_params["reduction_cost_token"] == "yellow"
    assert reduce_rule.handler_params["uses_remaining"] == 1
    assert reduce_rule.once_per_turn is True


def test_extract_self_played_can_reduce_next_matching_z_awaken_cost_and_z_energy_in_z_deck() -> None:
    card = _card(
        "[Auto] When this card is played, add up to 1 card from your life to your hand, "
        "then reduce the [Z-Awaken] skill cost of {Golden Frieza, Shining Emperor} in your Z-Deck by {y} "
        "and reduce its Z-Energy cost by 1 for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    reduce_rule = next(r for r in rules if r.handler_id == "auto_reduce_next_matching_z_awaken_cost_in_z_deck_on_play")
    assert reduce_rule.trigger == "self_played"
    assert reduce_rule.handler_params["target_required_name_contains"] == "GOLDEN FRIEZA, SHINING EMPEROR"
    assert reduce_rule.handler_params["reduction_cost_token"] == "y"
    assert reduce_rule.handler_params["z_energy_reduction"] == 1
    assert reduce_rule.handler_params["uses_remaining"] == 1


def test_extract_self_played_can_grant_keyword_to_next_matching_union_play() -> None:
    card = _card(
        "[Auto] Place 2 of your Z-Energy into their owner's Drop: When this card is played, activate this skill. "
        "During this turn, the next time you play a blue <Gogeta: Br> card with [Union], it gains [Barrier] for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_pay_z_energy_on_play_and_grant_next_matching_union_play_keyword")
    assert rule.trigger == "self_played"
    assert rule.handler_params["grant_keyword"] == "Barrier"
    assert rule.handler_params["allowed_colors"] == "blue"
    assert rule.handler_params["required_characters"] == "Gogeta: Br"


def test_extract_self_played_can_place_from_drop_under_self() -> None:
    card = _card(
        "[Auto] When this card is played, place up to 1 ≪Saiyan≫ card from your Drop under this card, "
        "and this card gains [Barrier] for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_place_up_to_n_from_owner_drop_under_self_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_traits"] == "Saiyan"


def test_extract_self_played_can_play_from_z_energy_combo_or_drop() -> None:
    card = _card(
        "[Auto](Blue): When this card is played, "
        "play up to 1 mono-blue <Krillin> card with an energy cost of 3 from your Z-Energy, Combo Area, or Drop."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "auto_play_up_to_n_from_owner_z_energy_combo_or_drop_on_play"
    )
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "blue"
    assert rule.handler_params["required_characters"] == "Krillin"
    assert rule.handler_params["max_cost"] == 3
    assert rule.handler_params["auto_cost_header"] == "(blue)"


def test_extract_self_played_can_place_from_deck_or_drop_under_self() -> None:
    card = _card(
        "[Auto] When this card is played, place up to 2 red \u226aSaiyan\u226b Battle Cards from your deck and/or Drop under this card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_place_up_to_n_from_owner_deck_or_drop_under_self_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 2
    assert rule.handler_params["allowed_colors"] == "red"
    assert rule.handler_params["required_traits"] == "Saiyan"
    assert rule.handler_params["required_card_type"] == "BATTLE"


def test_extract_owner_union_absorb_activated_can_place_top_deck_under_self_and_rest_opponent_battle() -> None:
    card = _card(
        "[Auto][Once per turn] When one of your ≪Namekian≫ cards activates [Union Absorb], "
        "place the top card of your deck under this card, then choose up to 1 of your opponent's Battle Cards and switch it to Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "auto_place_top_deck_under_self_and_switch_up_to_n_opponent_battle_rest_on_union_absorb"
    )
    assert rule.trigger == "owner_union_absorb_activated"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["trigger_required_traits"] == "Namekian"
    assert rule.once_per_turn is True


def test_extract_activate_main_can_play_from_under_self_and_place_self_under_played() -> None:
    card = _card(
        "[Activate: Main][Limit 1] Play up to 1 red \u226aUniverse 7\u226b <Son Gohan: Adolescence> card with an energy cost of 2 or less from under this card, and place this card under the played card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_play_up_to_n_from_under_self_and_place_self_under_played_card")
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "red"
    assert rule.handler_params["required_traits"] == "Universe 7"
    assert "Son Gohan: Adolescence" in rule.handler_params["required_characters"]
    assert rule.handler_params["max_cost"] == 2


def test_extract_self_played_from_under_by_skill_can_gain_power_and_keyword() -> None:
    card = _card(
        "[Auto] If you have 4 or more energy: When this card is played from under a card by a skill, this card gets +10000 power and [Dual Attack] for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_self_gain_power_for_turn_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["power_delta"] == 10000
    assert rule.handler_params["grant_keyword"] == "Dual Attack"
    assert rule.handler_params["requires_played_from"] == "under"
    assert rule.handler_params["requires_played_via"] == "skill"
    assert rule.handler_params["min_owner_energy"] == 4


def test_extract_self_played_under_named_host_can_gain_power() -> None:
    card = _card(
        "[Auto] When this card is played under a {Hyperbolic Time Chamber} in your Battle Area, this card gets +10000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_self_gain_power_for_turn_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["power_delta"] == 10000
    assert rule.handler_params["requires_played_from"] == "under"
    assert rule.handler_params["under_host_name_contains"] == "HYPERBOLIC TIME CHAMBER"


def test_extract_self_played_under_named_host_can_gain_power_and_combo_from_battle() -> None:
    card = _card(
        "[Auto] When this card is played under a {Hyperbolic Time Chamber} in your Battle Area, this card gets +5000 power and you may use this card in a combo in Rest Mode for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_self_gain_power_for_turn_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["power_delta"] == 5000
    assert rule.handler_params["requires_played_from"] == "under"
    assert rule.handler_params["under_host_name_contains"] == "HYPERBOLIC TIME CHAMBER"
    assert rule.handler_params["grant_can_combo_from_battle_while_resting"] is True


def test_extract_self_attacks_combo_named_from_under_named_host_then_draw_and_gain_keyword() -> None:
    card = _card(
        "[Auto] When this card attacks, use up to 1 {SS Trunks, Mysterious Future Warrior} under a {Hyperbolic Time Chamber} in your Battle Area in a combo. If you do, draw 1 card, and this card gains [Critical] for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "auto_combo_up_to_n_named_from_under_named_host_on_attack_then_draw_n_and_gain_keyword_for_battle"
    )
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_name_contains"] == "SS TRUNKS, MYSTERIOUS FUTURE WARRIOR"
    assert rule.handler_params["host_name_contains"] == "HYPERBOLIC TIME CHAMBER"
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["grant_keyword"] == "Critical"


def test_extract_self_attacks_combo_named_from_under_named_host_then_draw_and_gain_keyword_with_under_cost() -> None:
    card = _card(
        "[Auto][Limit 1] Place 1 card from under this card in its owner's Drop: "
        "When this card attacks, use up to 1 {SS Trunks, Mysterious Future Warrior} under a {Hyperbolic Time Chamber} in your Battle Area in a combo. "
        "If you do, draw 1 card, and this card gains [Critical] for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "auto_combo_up_to_n_named_from_under_named_host_on_attack_then_draw_n_and_gain_keyword_for_battle"
    )
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["auto_release_under_to_drop_before"] == 1
    assert rule.handler_params["required_name_contains"] == "SS TRUNKS, MYSTERIOUS FUTURE WARRIOR"


def test_extract_activate_main_can_rest_named_host_and_place_self_and_named_deck_under_it() -> None:
    card = _card(
        "[Activate: Main](Green), choose 1 {Hyperbolic Time Chamber} in your Battle Area and switch it to Rest Mode: "
        "Place this card from your hand and up to 1 {SS Trunks, Mysterious Future Warrior} from your deck under the chosen card, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "activate_place_self_from_hand_and_up_to_n_named_from_owner_deck_under_named_host"
    )
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["host_name_contains"] == "HYPERBOLIC TIME CHAMBER"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_name_contains"] == "SS TRUNKS, MYSTERIOUS FUTURE WARRIOR"
    assert rule.handler_params["rest_host"] is True


def test_extract_self_placed_in_leader_area_can_activate_named_field_extra_from_deck() -> None:
    card = _card(
        "[Auto] When this card is placed in your Leader Area, activate up to 1 {Hyperbolic Time Chamber} from your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_placed_in_leader_area"
        and r.handler_id == "auto_activate_up_to_n_named_field_extra_from_owner_deck_on_leader_placed"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_name_contains"] == "HYPERBOLIC TIME CHAMBER"
    assert rule.handler_params["required_card_type"] == "EXTRA"
    assert rule.handler_params["requires_field_keyword"] is True


def test_extract_activate_main_can_activate_named_field_extra_from_deck_and_negate_for_game() -> None:
    card = _card(
        "[Activate: Main] Activate up to 1 {Spirit Bomb} from your deck, shuffle your deck, and negate this skill for the game."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_activate_up_to_n_named_field_extra_from_owner_deck"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_name_contains"] == "SPIRIT BOMB"
    assert rule.handler_params["required_card_type"] == "EXTRA"
    assert rule.handler_params["requires_field_keyword"] is True
    assert rule.handler_params["negate_self_skill_for_game"] is True


def test_extract_activate_main_named_field_extra_from_deck_requires_no_owner_field_extra() -> None:
    card = replace(
        _card(
            "[+1][Activate: Main] If a [Field] Extra Card isn't in your Battle Area, activate up to 1 {The Nameless Planet} from your deck, then shuffle your deck."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_activate_up_to_n_named_field_extra_from_owner_deck"
    )
    assert rule.handler_params["required_name_contains"] == "THE NAMELESS PLANET"
    assert rule.handler_params["requires_no_owner_field_extra"] is True


def test_extract_janemba_activate_main_battle_can_place_named_field_extra_from_owner_z_deck() -> None:
    card = _card(
        "[Activate: Main/Battle][Limit 1] If your Leader is a <Janemba> card, "
        "you have a blue <Janemba> card with an energy cost of 6 or more in play, and you remove this card from the game: "
        "Place up to 1 {Demonic Blade} or {Lightning Shower Rain} from your Z-Deck in the Battle Area, "
        "choose up to 1 Keyword Skill on your opponent's Battle Cards, negate that skill for the turn, "
        "choose up to 1 of your blue <Janemba> cards, and it gains that skill until the end of your turn."
    )
    rules = extract_effect_rules_from_card(card)
    z_deck_rules = [r for r in rules if r.handler_id == "activate_activate_up_to_n_named_field_extra_from_owner_z_deck"]
    assert {rule.trigger for rule in z_deck_rules} == {"self_activate_main", "self_activate_battle"}
    rule = z_deck_rules[0]
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_name_contains_any"] == "DEMONIC BLADE|LIGHTNING SHOWER RAIN"
    assert rule.handler_params["required_card_type"] == "EXTRA"
    assert rule.handler_params["requires_field_keyword"] is True
    assert rule.handler_params["required_leader_traits"] == "Janemba"
    assert rule.handler_params["required_owner_battle_allowed_colors"] == "blue"
    assert rule.handler_params["required_owner_battle_required_characters"] == "Janemba"
    assert rule.handler_params["required_owner_battle_min_cost"] == 6


def test_extract_referee_introducing_the_fighters_first_branch_rule() -> None:
    card = replace(
        _card(
            "[Activate: Main] If your Leader Card is a green <Beerus> or green <Champa> card and you place this card in its owner's Drop Area: "
            "Choose one?\n"
            "・Activate up to 1 {The Nameless Planet} from your deck, then shuffle your deck.\n"
            "・If your opponent has no Battle Cards in play, your opponent reveals their hand, and you choose up to 1 Battle Card with an energy cost of 3 or less from it and play it in your opponent's Battle Area."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_activate_up_to_n_named_field_extra_from_owner_deck"
    )
    assert rule.handler_params["required_name_contains"] == "THE NAMELESS PLANET"
    assert rule.handler_params["required_card_type"] == "EXTRA"
    assert rule.handler_params["requires_field_keyword"] is True
    assert "green <beerus> or green <champa>" in str(rule.handler_params["requires_leader"]).lower()


def test_extract_referee_introducing_the_fighters_second_branch_rule() -> None:
    card = replace(
        _card(
            "[Activate: Main] If your Leader Card is a green <Beerus> or green <Champa> card and you place this card in its owner's Drop Area: "
            "Choose one?\n"
            "・Activate up to 1 {The Nameless Planet} from your deck, then shuffle your deck.\n"
            "・If your opponent has no Battle Cards in play, your opponent reveals their hand, and you choose up to 1 Battle Card with an energy cost of 3 or less from it and play it in your opponent's Battle Area."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_play_up_to_n_from_opponent_hand_to_opponent_battle"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_cost"] == 3
    assert rule.handler_params["required_card_type"] == "BATTLE"
    assert rule.handler_params["requires_no_opponent_battle"] is True
    assert "green <beerus> or green <champa>" in str(rule.handler_params["requires_leader"]).lower()


def test_extract_whis_pre_fight_preparations_discard_rule() -> None:
    card = replace(
        _card(
            "[Empower Green 3] (If this card replaces a green Unison Card as it enters play, it carries over up to 3 of its markers.)\n"
            "[Auto][Limit 1] If this card has 3 or more markers: When this card is played, your opponent chooses 1 card in their hand and discards it.\n"
            "[+1][Activate: Main] If a [Field] Extra Card isn't in your Battle Area, activate up to 1 {The Nameless Planet} from your deck, then shuffle your deck."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    discard_rule = next(
        r
        for r in rules
        if r.trigger == "self_played"
        and r.handler_id == "auto_opponent_discards_n_from_hand_on_play"
    )
    activate_rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_activate_up_to_n_named_field_extra_from_owner_deck"
    )
    assert discard_rule.handler_params["amount"] == 1
    assert discard_rule.handler_params["min_source_markers"] == 3
    assert activate_rule.handler_params["required_name_contains"] == "THE NAMELESS PLANET"
    assert activate_rule.handler_params["requires_no_owner_field_extra"] is True


def test_extract_planetary_manipulation_second_branch_rule() -> None:
    card = replace(
        _card(
            "[Counter: Attack] Negate the attack.\n"
            "[Permanent] You can activate this card's [Counter] skill from your hand without paying its energy cost by placing 1 card from under a {The Nameless Planet} in your Battle Area in its owner's Drop Area instead.\n"
            "[Activate: Main](G)(G)(G): Choose one??\n"
            "・Place up to 3 cards from under a {The Nameless Planet} in your Battle Area in their owners' Drop Areas; your opponent discards cards equal to the number of cards you placed in Drop Areas this way.\n"
            "・Look at your opponent's hand and play up to 1 Battle Card from it in your opponent's Battle Area in Rest Mode."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_play_up_to_n_from_opponent_hand_to_opponent_battle"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_card_type"] == "BATTLE"
    assert rule.handler_params["resting"] is True


def test_extract_nameless_planet_battle_end_capture_rule() -> None:
    card = replace(
        _card(
            "[Auto] At the end of a battle where one of your green Battle Cards attacks and KOs an opponent's Battle Card, "
            "place that card under this card from your opponent's Drop Area."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_battle_ko_opponent_battle_battle_end"
        and r.handler_id == "auto_place_battle_koed_by_owner_attacker_under_self_on_battle_end"
    )
    assert rule.handler_params["attacker_allowed_colors"] == "green"


def test_extract_nameless_planet_attack_redirect_rule() -> None:
    card = replace(
        _card(
            "[Auto] If your Leader Card is a green <Beerus> or green <Champa> card and you switch this card to Rest Mode: "
            "When your opponent attacks, choose up to 1 of your green Battle Cards in Rest Mode with the same ≪Universe≫ special trait as your Leader Card "
            "and switch the target of attack to that card."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_opponent_battle_attacks"
        and r.handler_id == "auto_rest_self_redirect_attack_to_matching_owner_battle_on_opponent_attack"
    )
    assert rule.handler_params["target_allowed_colors"] == "green"
    assert rule.handler_params["target_requires_shared_leader_traits"] is True
    assert "green <beerus> or green <champa>" in str(rule.handler_params["requires_leader"]).lower()


def test_extract_nameless_planet_win_game_rule() -> None:
    card = replace(
        _card(
            "[Activate: Main] If there are 5 cards owned by your opponent under this card: You win the game."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_win_game_if_opponent_owned_cards_under_self_at_least_n"
    )
    assert rule.handler_params["required_source_stacked_opponent_owned_at_least"] == 5


def test_extract_vados_pre_fight_preparations_ko_rule() -> None:
    card = replace(
        _card(
            "[Empower Green 3] (If this card replaces a green Unison Card as it enters play, it carries over up to 3 of its markers.)\n"
            "[Auto][Limit 1] If this card has 3 or more markers: When this card is played, choose up to 1 of your opponent's Battle Cards and KO it.\n"
            "[+1][Activate: Main] If a [Field] Extra Card isn't in your Battle Area, activate up to 1 {The Nameless Planet} from your deck, then shuffle your deck."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    ko_rule = next(
        r
        for r in rules
        if r.trigger == "self_played"
        and r.handler_id == "auto_ko_opponent_battle_on_play"
    )
    activate_rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_activate_up_to_n_named_field_extra_from_owner_deck"
    )
    assert ko_rule.handler_params["min_source_markers"] == 3
    assert activate_rule.handler_params["required_name_contains"] == "THE NAMELESS PLANET"
    assert activate_rule.handler_params["requires_no_owner_field_extra"] is True


def test_extract_activate_main_can_place_hand_under_spirit_bomb_then_draw() -> None:
    card = _card(
        "[Activate: Main][Once per turn] Place 1 card from your hand under a {Spirit Bomb} in your Battle Area: Draw 2 cards."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_place_up_to_n_from_owner_hand_under_named_host_then_draw_n"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["host_name_contains"] == "SPIRIT BOMB"
    assert rule.handler_params["draw_count"] == 2
    assert rule.handler_params["required_owner_hand_count_at_least"] == 1


def test_extract_activate_main_can_rest_owner_battles_and_place_top_deck_under_spirit_bomb() -> None:
    card = _card(
        "[Activate: Main] Switch this card to Rest Mode: You may choose any number of your Battle Cards and switch them to Rest Mode. "
        "If you do, for each Battle Card switched to Rest Mode by this skill other than this card, you may place the top card of your deck under a {Spirit Bomb} in your Battle Area."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_rest_any_number_owner_battles_and_place_top_deck_under_named_host"
    )
    assert rule.handler_params["host_name_contains"] == "SPIRIT BOMB"


def test_extract_activate_main_can_play_self_from_hand_then_switch_opponent_battle_rest_if_spirit_bomb_in_play() -> None:
    card = _card(
        "[Activate: Main][Limit 1](Yellow), if you have {Spirit Bomb} in your Battle Area: "
        "Play this card from your hand, then choose up to 1 of your opponent's Battle Cards and switch it to Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_play_self_from_hand"
        and int(r.handler_params.get("post_play_rest_max_targets", 0) or 0) == 1
    )
    assert rule.handler_params["post_play_rest_max_targets"] == 1
    assert rule.handler_params["required_owner_battle_required_name_contains"] == "SPIRIT BOMB"


def test_extract_activate_main_can_play_self_from_z_energy_then_rest_and_lock_opponent_board() -> None:
    card = _card(
        "[Permanent] If this card is in Rest Mode, your opponent's Battle Cards can't attack Leaders.<br>"
        "[Permanent] If this card would leave the Battle Area, remove it from the game instead.<br>"
        "[Activate: Main][Limit 1](Yellow), if your Leader is a yellow ≪Universe 7≫ <Son Goku> card and you have 3 or more Z-Energy: "
        "Play this card from your Z-Energy, then choose up to 1 of your opponent's Battle Cards or Unisons, switch it to Rest Mode, and that card can't switch to Active Mode until the end of your opponent's turn."
    )
    rules = extract_effect_rules_from_card(card)
    noop_rules = [r for r in rules if r.trigger == "self_played" and r.handler_id == "noop_auto"]
    play_rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_play_self_from_hand"
        and r.handler_params.get("required_source_zone") == "z_energy"
    )
    assert len(noop_rules) >= 2
    assert play_rule.handler_params["post_play_rest_board_max_targets"] == 1
    assert play_rule.handler_params["post_play_rest_prevent_active_until_opponent_turn"] is True
    assert play_rule.handler_params["min_owner_z_energy"] == 3


def test_extract_activate_main_can_play_self_from_z_energy_then_ko_rest_battle() -> None:
    card = _card(
        "[Permanent] If this card is in Rest Mode, your opponent's Battle Cards can't attack Leaders.<br>"
        "[Permanent] If this card would leave the Battle Area, remove it from the game instead.<br>"
        "[Activate: Main][Limit 1](Yellow), if your Leader is a yellow ≪Universe 7≫ <Son Goku> card and you have 3 or more Z-Energy: "
        "Play this card from your Z-Energy, then choose up to 1 of your opponent's Rest Mode Battle Cards and KO it."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_play_self_from_hand"
        and r.handler_params.get("required_source_zone") == "z_energy"
    )
    assert play_rule.handler_params["post_play_ko_rest_battle_max_targets"] == 1


def test_extract_attack_can_add_matching_to_z_energy_then_place_matching_under_spirit_bomb() -> None:
    card = _card(
        "[Auto] When this card attacks, draw 1 card, place this card from the Battle Area in its owner's Drop at the end of the battle, "
        "choose up to 1 yellow <Son Goku> card in your Battle Area or Drop, add it to your Z-Energy with its skills negated for the turn, "
        "then choose up to 1 yellow <Vegeta> card in your Battle Area or Drop and place it under {Spirit Bomb} in your Battle Area."
    )
    rules = extract_effect_rules_from_card(card)
    attack_rule = next(
        r
        for r in rules
        if r.trigger == "self_attacks"
        and r.handler_id
        == "auto_draw_n_add_matching_from_owner_battle_or_drop_to_z_energy_then_place_matching_from_owner_battle_or_drop_under_named_host_on_attack"
    )
    assert attack_rule.handler_params["draw_count"] == 1
    assert attack_rule.handler_params["z_energy_max_targets"] == 1
    assert attack_rule.handler_params["z_energy_allowed_colors"] == "yellow"
    assert attack_rule.handler_params["z_energy_required_characters"] == "son goku"
    assert attack_rule.handler_params["under_max_targets"] == 1
    assert attack_rule.handler_params["under_allowed_colors"] == "yellow"
    assert attack_rule.handler_params["under_required_characters"] == "vegeta"
    assert attack_rule.handler_params["host_name_contains"] == "SPIRIT BOMB"
    battle_end_rule = next(
        r
        for r in rules
        if r.trigger == "self_attacks_battle_end"
        and r.handler_id == "auto_send_self_to_owner_drop_on_attack_battle_end"
    )


def test_extract_attack_can_add_matching_to_z_energy_then_place_matching_under_spirit_bomb_with_under_cost() -> None:
    card = _card(
        "[Auto][Limit 1] Place 1 card from under this card in its owner's Drop: "
        "When this card attacks, draw 1 card, place this card from the Battle Area in its owner's Drop at the end of the battle, "
        "choose up to 1 yellow <Son Goku> card in your Battle Area or Drop, add it to your Z-Energy with its skills negated for the turn, "
        "then choose up to 1 yellow <Vegeta> card in your Battle Area or Drop and place it under {Spirit Bomb} in your Battle Area."
    )
    rules = extract_effect_rules_from_card(card)
    attack_rule = next(
        r
        for r in rules
        if r.trigger == "self_attacks"
        and r.handler_id
        == "auto_draw_n_add_matching_from_owner_battle_or_drop_to_z_energy_then_place_matching_from_owner_battle_or_drop_under_named_host_on_attack"
    )
    assert attack_rule.handler_params["draw_count"] == 1
    assert attack_rule.handler_params["host_name_contains"] == "SPIRIT BOMB"
    assert attack_rule.handler_params["auto_release_under_to_drop_before"] == 1


def test_extract_hyperbolic_leader_attack_search_with_awaken_clause() -> None:
    card = replace(_card(
        "[Auto] When this card attacks, look at up to 5 cards from the top of your deck, "
        "add up to 1 green ≪Saiyan≫ to your hand, then shuffle your deck. "
        "[Awaken] When your life is at 4 or less or if you have a {SS Son Goku, Showing the Results of Training} in play: "
        "Draw 1 card, switch up to 1 of your energy to Active Mode, then add cards from your life to your hand until you have 6 life left."
    ), card_type="LEADER")
    rules = extract_effect_rules_from_card(card)
    search = next(
        r for r in rules if r.trigger == "owner_leader_attacks" and r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play"
    )
    assert search.handler_params["look_count"] == 5
    assert search.handler_params["max_add"] == 1
    assert search.handler_params["allowed_colors"] == "green"
    assert search.handler_params["required_traits"] == "Saiyan"

def test_extract_hyperbolic_krillin_play_search_with_cost_cap() -> None:
    card = _card(
        "[Auto] When this card is played, look at up to 5 cards from the top of your deck, "
        "add up to 1 green ≪Saiyan≫ with an energy cost of 4 or less to your hand, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    search = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play")
    assert search.handler_params["look_count"] == 5
    assert search.handler_params["max_add"] == 1
    assert search.handler_params["allowed_colors"] == "green"
    assert search.handler_params["required_traits"] == "Saiyan"
    assert search.handler_params["max_cost"] == 4


def test_extract_hyperbolic_son_gohan_on_play_ko_rule() -> None:
    card = _card(
        "[Auto] When this card is played, choose up to 1 of your opponent's Battle Cards and KO it."
    )
    rules = extract_effect_rules_from_card(card)
    ko = next(r for r in rules if r.handler_id == "auto_ko_opponent_battle_on_play")
    assert ko.trigger == "self_played"
    assert ko.handler_params["max_cost"] == -1


def test_extract_cell_on_play_ko_then_play_drop_rule_pair() -> None:
    card = _card(
        "[Auto] When this card is played, choose up to 1 of your opponent's Battle Cards and KO it, "
        "then play up to 1 green <Cell> card with an energy cost of 1 from your Drop."
    )
    rules = extract_effect_rules_from_card(card)
    ko = next(r for r in rules if r.handler_id == "auto_ko_opponent_battle_on_play")
    play = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_drop_on_play")
    assert ko.trigger == "self_played"
    assert play.trigger == "self_played"
    assert play.handler_params["max_targets"] == 1
    assert play.handler_params["allowed_colors"] == "green"
    assert play.handler_params["required_characters"] == "Cell"
    assert play.handler_params["max_cost"] == 1


def test_extract_activate_main_can_rest_named_host_and_place_self_and_named_vegeta_from_deck_under_it() -> None:
    card = _card(
        "[Activate: Main](Green), choose 1 {Hyperbolic Time Chamber} in your Battle Area and switch it to Rest Mode: "
        "Place this card from your hand and up to 1 {SS Vegeta, Arrogance} from your deck under the chosen card, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "activate_place_self_from_hand_and_up_to_n_named_from_owner_deck_under_named_host"
    )
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["host_name_contains"] == "HYPERBOLIC TIME CHAMBER"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_name_contains"] == "SS VEGETA, ARROGANCE"
    assert rule.handler_params["rest_host"] is True


def test_extract_activate_main_can_rest_named_host_and_place_each_named_hand_under_it() -> None:
    card = _card(
        "[Activate: Main](Green), if your Leader is a green <Son Gohan: Childhood> and you discard this card from your hand: "
        "Choose up to 1 {Hyperbolic Time Chamber} in your Battle Area, switch it to Rest Mode, place 1 {SS Vegeta, Arrogance} and 1 {SS Trunks, Mysterious Future Warrior} from your hand under the chosen card, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "activate_rest_named_host_and_place_each_named_from_owner_hand_under_it"
    )
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["host_name_contains"] == "HYPERBOLIC TIME CHAMBER"
    assert rule.handler_params["required_name_contains_each"] == "SS VEGETA, ARROGANCE|SS TRUNKS, MYSTERIOUS FUTURE WARRIOR"
    assert rule.handler_params["rest_host"] is True
    assert "son gohan: childhood" in rule.handler_params["requires_leader"]


def test_extract_activate_main_can_draw_and_play_named_from_owner_hand_under_named_host() -> None:
    card = _card(
        "[Activate: Main](Green), place this card in your Drop: "
        "Draw 1 card and play up to 1 {SS Son Gohan, Showing the Results of Training} under a {Hyperbolic Time Chamber} in your Battle Area."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "activate_draw_n_and_play_up_to_n_named_from_owner_hand_under_named_host"
    )
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_name_contains"] == "SS SON GOHAN, SHOWING THE RESULTS OF TRAINING"
    assert rule.handler_params["host_name_contains"] == "HYPERBOLIC TIME CHAMBER"


def test_extract_self_played_can_rest_named_host_place_named_from_hand_under_it_then_ko_if_placed() -> None:
    card = _card(
        "[Auto] If you have 2 or more energy, choose 1 {Hyperbolic Time Chamber} from your Battle Area, and switch it to Rest Mode: "
        "When this card is played, place up to 1 {SS Son Goku, Showing the Results of Training} or {SS Son Gohan, Showing the Results of Training} from your hand under the chosen card. "
        "If you placed a card, choose up to 1 of your opponent's Battle Cards with an energy cost of 3 or less and KO it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "auto_rest_named_host_and_place_up_to_n_named_from_owner_hand_under_it_then_ko_on_play_if_placed"
    )
    assert rule.trigger == "self_played"
    assert rule.handler_params["host_name_contains"] == "HYPERBOLIC TIME CHAMBER"
    assert rule.handler_params["max_targets"] == 1
    assert (
        rule.handler_params["required_name_contains_any"]
        == "SS SON GOKU, SHOWING THE RESULTS OF TRAINING|SS SON GOHAN, SHOWING THE RESULTS OF TRAINING"
    )
    assert rule.handler_params["ko_max_targets"] == 1
    assert rule.handler_params["ko_max_cost"] == 3
    assert rule.handler_params["min_owner_energy"] == 2


def test_extract_activate_main_can_play_named_from_owner_drop_and_gain_power_for_turn() -> None:
    card = _card(
        "[Activate: Main](Green), if your Leader is a green <Son Gohan: Childhood> Z-Leader, "
        "you remove this card in the Drop from the game, and you discard 1 card from your hand: "
        "Play up to 1 {SS Vegeta, Arrogance} from your Drop and that card gets +10000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "activate_play_up_to_n_named_from_owner_drop_and_gain_power_for_turn"
    )
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_name_contains"] == "SS VEGETA, ARROGANCE"
    assert rule.handler_params["power_delta"] == 10000
    assert "son gohan: childhood" in rule.handler_params["requires_leader"]


def test_extract_activate_main_can_buff_owner_leader_for_turn() -> None:
    card = _card(
        "[Activate: Main][Limit 1](Green), if your Leader is a green <Son Gohan: Childhood> Z-Leader, "
        "you have 4 or more energy, and you remove this card from the game: "
        "Choose up to 1 of your Leaders, and it gets +10000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_buff_owner_leader_for_turn")
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["leader_power_delta"] == 10000
    assert rule.handler_params["min_owner_energy"] == 4
    assert "son gohan: childhood" in rule.handler_params["requires_leader"]


def test_extract_activate_main_can_play_self_from_under_named_owner_leader() -> None:
    card = _card(
        "[Activate: Main][Limit 1](Green), place 1 card from your hand at the bottom of your deck: "
        "Play this card from under {Cell, Return of the Ultimate Lifeform}."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_play_self_from_under_owner_leader")
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["required_source_zone"] == "leader_under"
    assert rule.handler_params["under_host_name_contains"] == "CELL, RETURN OF THE ULTIMATE LIFEFORM"


def test_extract_activate_main_can_play_self_from_generic_owner_leader() -> None:
    card = _card(
        "[Activate: Main](Yellow), if your Leader is a yellow <Vegeta> card or you have a yellow <Vegeta> card in play: "
        "Play this card from under your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_play_self_from_under_owner_leader")
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["required_source_zone"] == "leader_under"
    assert "yellow <vegeta>" in rule.handler_params["requires_leader"] or "yellow <vegeta> card in play" in rule.handler_params["requires_leader"]


def test_extract_activate_main_can_play_self_from_under_named_owner_leader_then_ko_rest() -> None:
    card = _card(
        "[Activate: Main][Limit 1](Yellow): Play this card from under your <Piccolo: SH> Leader, "
        "then choose up to 1 of your opponent's Battle Cards in Rest Mode and KO it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r for r in rules if r.handler_id == "activate_play_self_from_under_owner_leader_then_ko_up_to_n_opponent_battle"
    )
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["required_source_zone"] == "leader_under"
    assert rule.handler_params["under_host_required_characters"] == "piccolo: sh"
    assert rule.handler_params["ko_max_targets"] == 1
    assert rule.handler_params["ko_rest_mode_only"] is True


def test_extract_activate_main_can_place_self_under_owner_leader() -> None:
    card = _card(
        "[Activate: Main][Limit 1][Burst 1] If your Leader is a blue <Android 18> card: Place this card under your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_place_self_under_owner_leader")
    assert rule.trigger == "self_activate_main"
    assert "blue <android 18>" in str(rule.handler_params["requires_leader"]).lower()


def test_extract_activate_main_can_move_matching_under_leader_card_to_z_energy_then_place_self_from_drop_under_owner_leader() -> None:
    card = _card(
        "[Activate: Main][Limit 1] If your Leader is a green <Broly: Br> card: "
        "You may add 1 green Extra from under your Leader to your Z-Energy. If you do, place this card from your Drop under your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_place_self_under_owner_leader")
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["required_source_zone"] == "drop"
    assert rule.handler_params["required_owner_leader_under_count_at_least"] == 1
    assert rule.handler_params["required_owner_leader_under_allowed_colors"] == "green"
    assert rule.handler_params["required_owner_leader_under_required_card_types"] == "EXTRA"
    assert rule.handler_params["move_under_leader_to_z_energy_before"] == 1
    assert "green <broly: br>" in str(rule.handler_params["requires_leader"]).lower()


def test_extract_activate_battle_can_play_self_from_under_owner_leader_then_bottom_deck_if_still_in_play() -> None:
    card = _card(
        "[Activate: Battle][Limit 1](Blue), if your Leader is a blue <Android 18> card and an <Android 18> card is in your Combo Area: "
        "Play this card from under your Leader, and at the end of the turn, if this card is in play, place it at the bottom of its owner's deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_battle" and r.handler_id == "activate_play_self_from_under_owner_leader")
    assert rule.handler_params["required_source_zone"] == "leader_under"
    assert rule.handler_params["bottom_deck_self_at_turn_end"] is True
    assert "blue <android 18>" in rule.handler_params["requires_leader"]
    assert rule.handler_params["required_owner_combo_required_characters"] == "Android 18"


def test_extract_activate_battle_under_named_owner_leader_can_buff_owner_battle_cards() -> None:
    card = _card(
        "[Activate: Battle][Limit 1](Yellow), if this card is under your <Piccolo: SH> Leader: "
        "Choose up to 1 of your Battle Cards with <Son Gohan> in its character name and it gets +5000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_battle" and r.handler_id == "activate_buff_owner_battle_cards")
    assert rule.handler_params["required_source_zone"] == "leader_under"
    assert rule.handler_params["under_host_required_characters"] == "piccolo: sh"
    assert rule.handler_params["required_characters"] == "Son Gohan"
    assert rule.handler_params["power_delta"] == 5000


def test_extract_activate_main_place_self_under_owner_leader_line_can_draw() -> None:
    card = _card(
        "[Activate: Main] If your Leader Card is a mono-green <Cell> card and you place this card under your Leader Card: Draw 1 card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "auto_draw_n")
    assert rule.handler_params["amount"] == 1
    assert "cell" in str(rule.handler_params["required_leader_traits"]).lower()


def test_extract_self_placed_under_owner_leader_can_buff_owner_leader_for_turn() -> None:
    card = _card(
        "[Auto][Limit 1] When this card in your hand or Battle Area is placed under your green <Mai: Future>-only Leader, your Leader gets +10000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_buff_owner_leader_for_turn_on_placed_under")
    assert rule.trigger == "self_placed_under_owner_card"
    assert rule.handler_params["required_host_zone"] == "leader"
    assert rule.handler_params["requires_placed_from_zones"] == "hand,battle"
    assert rule.handler_params["leader_power_delta"] == 10000
    assert "green" in str(rule.handler_params["host_allowed_colors"]).lower()
    assert "mai: future" in str(rule.handler_params["host_required_characters"]).lower()


def test_extract_turn_end_can_place_matching_drop_under_owner_leader() -> None:
    card = _card(
        "[Auto] At the end of your turn, place up to 1 blue <Android 18> card from your Drop under your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_place_up_to_n_from_owner_drop_under_owner_leader_on_turn_end")
    assert rule.trigger == "turn_end"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "blue"
    assert "android 18" in str(rule.handler_params.get("required_characters") or rule.handler_params.get("required_traits") or "").lower()


def test_extract_turn_end_can_place_self_from_under_z_leader_on_top_of_owner_leader() -> None:
    card = _card(
        "[Auto] At the end of your opponent's turn, place this card from under your Z-Leader on top of your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_place_self_from_under_owner_leader_on_top_of_owner_leader_on_turn_end")
    assert rule.trigger == "opponent_turn_end"
    assert rule.handler_params["required_source_zone"] == "leader_under"
    assert rule.handler_params["under_host_required_card_type"] == "Z-LEADER"


def test_extract_turn_end_can_place_self_from_under_leader_on_top_of_owner_leader() -> None:
    card = _card(
        "[Auto] At the end of your turn, place this card from under your Leader on top of your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_place_self_from_under_owner_leader_on_top_of_owner_leader_on_turn_end")
    assert rule.trigger == "turn_end"
    assert rule.handler_params["required_source_zone"] == "leader_under"
    assert "under_host_required_card_type" not in rule.handler_params


def test_extract_turn_end_can_send_self_from_energy_to_drop_after_life_reveal_replacement() -> None:
    card = _card(
        "[Permanent] During your opponent's turn, if all of your energy is mono-blue and you would reveal this card from your life to add it to your hand, "
        "you may place it in your energy in Rest Mode instead. If you do, draw 1 card.<br>"
        "[Auto] At the end of your next turn after you place this card in your energy with this skill, if this card is in your energy, place it in its owner's Drop Area."
    )
    rules = extract_effect_rules_from_card(card)
    noop_rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "noop_auto")
    rule = next(
        r
        for r in rules
        if r.trigger == "turn_end"
        and r.handler_id == "auto_send_self_from_owner_energy_to_drop_on_turn_end_if_replaced_from_life"
    )
    assert "would reveal this card from your life" in str(noop_rule.source_text or "").lower()
    assert "next turn" in str(rule.source_text or "").lower()


def test_extract_activate_main_can_draw_discard_place_from_drop_under_leader_and_switch_self_active() -> None:
    card = _card(
        "[UNISON +2][Activate: Main] Draw 1 card and discard 1 card from your hand. "
        "Additionally, if your Leader is a <Krillin> or <Android 18> card-both mono-blue-place up to 1 <Krillin> or ≪Android≫ card-both blue-from your Drop under your Leader, "
        "and at the end of the turn, switch this card to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_draw_n_discard_n_and_place_up_to_n_from_owner_drop_under_owner_leader_then_switch_self_active_on_turn_end"
    )
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["discard_count"] == 1
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["marker_delta"] == 2
    assert rule.handler_params["bonus_leader_allowed_colors"] == "blue"
    assert rule.handler_params["bonus_leader_requires_mono"] is True
    assert "krillin" in str(rule.handler_params.get("bonus_leader_required_characters", "")).lower()
    assert "android 18" in str(rule.handler_params.get("bonus_leader_required_characters", "")).lower()
    assert rule.handler_params["allowed_colors"] == "blue"


def test_extract_android_18_gearing_up_for_battle_rules() -> None:
    card = _card(
        "[Auto] When this card is played, look at up to 5 cards from the top of your deck, "
        "add up to 1 <Krillin> or ≪Android≫ card-both blue and with an energy cost of 5 or less-from among them to your hand, and shuffle your deck. "
        "[Activate: Main][Limit 1][Burst 1] If your Leader is a blue <Android 18> card: Place this card under your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    search = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play")
    tuck = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_place_self_under_owner_leader")
    assert search.handler_params["look_count"] == 5
    assert search.handler_params["max_add"] == 1
    assert search.handler_params["allowed_colors"] == "blue"
    assert search.handler_params["required_characters"] == "Krillin,Android"
    assert search.handler_params["max_cost"] == 5
    assert tuck.handler_params["requires_leader"] == "if your leader is a blue <android 18> card"


def test_extract_krillin_gearing_up_for_battle_under_leader_rule() -> None:
    card = _card(
        "[Auto] When this card is played, draw 1 card. "
        "[Activate: Main][Limit 1][Burst 1] If your Leader is a blue <Android 18> card: Place this card under your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    tuck = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_place_self_under_owner_leader")
    assert tuck.handler_params["requires_leader"] == "if your leader is a blue <android 18> card"


def test_extract_krillin_accel_dance_turn_end_under_leader_rule() -> None:
    card = _card(
        "[Auto] At the end of your turn, place up to 1 blue <Android 18> card from your Drop under your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_place_up_to_n_from_owner_drop_under_owner_leader_on_turn_end")
    assert rule.trigger == "turn_end"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "blue"
    assert rule.handler_params["required_traits"] == "Android 18"


def test_extract_super_17_power_distilled_first_activate_rule() -> None:
    card = _card(
        "[Activate: Main][Limit 1] If your Leader is a green ≪Machine Mutant≫ card and you switch this card to Rest Mode: "
        "Draw 1 card, place up to 1 <Android 18> or <Cell> card-both green and with an energy cost of 1-from your deck or Drop under your Leader, then shuffle your deck if you looked through it. "
        "[Activate: Main][Limit 1] If this card is under a green <Super 17> card: "
        "Choose up to 1 of your opponent's Battle Cards and place it under a <Super 17> card on top of this card, then switch a <Super 17> card on top of this card to Active Mode at the end of the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_draw_n_and_place_up_to_n_from_owner_deck_or_drop_under_owner_leader"
    )
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["source_pool"] == "deck_or_drop"
    assert rule.handler_params["allowed_colors"] == "green"
    assert rule.handler_params["required_characters"] == "Android 18,Cell"
    assert rule.handler_params["max_cost"] == 1
    assert "machine mutant" in str(rule.handler_params.get("requires_leader", "")).lower()


def test_extract_super_17_power_distilled_second_activate_rule() -> None:
    card = _card(
        "[Activate: Main][Limit 1] If your Leader is a green â‰ªMachine Mutantâ‰« card and you switch this card to Rest Mode: "
        "Draw 1 card, place up to 1 <Android 18> or <Cell> card-both green and with an energy cost of 1-from your deck or Drop under your Leader, then shuffle your deck if you looked through it. "
        "[Activate: Main][Limit 1] If this card is under a green <Super 17> card: "
        "Choose up to 1 of your opponent's Battle Cards and place it under a <Super 17> card on top of this card, then switch a <Super 17> card on top of this card to Active Mode at the end of the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_place_up_to_n_opponent_battle_under_source_host_and_switch_host_active_on_turn_end"
    )
    assert rule.handler_params["required_source_zone"] == "battle_under"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["under_host_allowed_colors"] == "green"
    assert rule.handler_params["under_host_required_traits"] == "Super 17"


def test_extract_son_goku_battle_under_setup_rule() -> None:
    card = _card(
        "[Permanent] If this card is under a red <Son Goku> Battle Card, the <Son Goku> Battle Card on top of this card gets +5000 power. "
        "[Activate: Main] Choose up to 1 of your mono-red <Son Goku> cards with an energy cost of 3 or more and without cards that have the same name as this card under it, then place this card under it. "
        "[Activate: Main][Limit 1] This card is under a <Son Goku> Battle Card: Draw 1 card, choose up to 1 of your opponent's Battle Cards with power less than or equal to the card on top of this card, then KO it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_place_self_under_matching_owner_battle"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_owner_battle_allowed_colors"] == "red"
    assert rule.handler_params["required_owner_battle_required_characters"] == "Son Goku"
    assert rule.handler_params["required_owner_battle_min_cost"] == 3
    assert rule.handler_params["required_owner_battle_require_mono_color"] is True
    assert rule.handler_params["required_owner_battle_without_source_name_under"] is True


def test_extract_son_goku_battle_under_payoff_rule() -> None:
    card = _card(
        "[Permanent] If this card is under a red <Son Goku> Battle Card, the <Son Goku> Battle Card on top of this card gets +5000 power. "
        "[Activate: Main] Choose up to 1 of your mono-red <Son Goku> cards with an energy cost of 3 or more and without cards that have the same name as this card under it, then place this card under it. "
        "[Activate: Main][Limit 1] This card is under a <Son Goku> Battle Card: Draw 1 card, choose up to 1 of your opponent's Battle Cards with power less than or equal to the card on top of this card, then KO it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_draw_n_and_ko_up_to_n_opponent_battle_by_source_host_power"
    )
    assert rule.handler_params["required_source_zone"] == "battle_under"
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["under_host_required_characters"] == "Son Goku"


def test_extract_piccolo_battle_under_draw_and_bounce_rule() -> None:
    card = _card(
        "[Energy-Exhaust][Revive Blue/Green] "
        "[Permanent] If your Leader's back side is {Piccolo, Brotherhood Bonds}, negate this card's [Energy-Exhaust] skill in all areas. "
        "[Activate: Main][Limit 1] Choose 1 of your ≪Namekian≫ Battle Cards with a [Revive] skill and place this card under it: "
        "Draw 1 card, then choose up to 1 of your opponent's Battle Cards and return it to its owner's hand."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_place_self_under_matching_owner_battle_then_draw_n_and_return_up_to_n_opponent_battle_to_hand"
    )
    assert rule.handler_params["max_host_targets"] == 1
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_owner_battle_required_traits"] == "Namekian"
    assert rule.handler_params["required_owner_battle_skill_text_contains"] == "[revive"


def test_extract_kefla_battle_under_bottom_deck_rule() -> None:
    card = _card(
        "[Permanent] If this card is under {Kefla, Everlasting Light} in a Battle Area, the card on top of this card gains [Double Strike] and [Blocker]. "
        "[Activate: Main]{1}, place this card under a <Kefla> Battle Card: Choose up to 1 of your opponent's Battle Cards and place it at the bottom of its owner's deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_place_self_under_matching_owner_battle_then_bottom_deck_up_to_n_opponent_battle"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_owner_battle_exclude_source_instance"] is True
    assert rule.handler_params["required_owner_battle_required_characters"] == "Kefla"


def test_extract_frieza_battle_under_play_from_deck_or_hand_on_top_rule() -> None:
    card = _card(
        "[Permanent] This card gains ≪Dark Dragon Ball≫ in all areas. "
        "[Activate: Battle] Choose 1 of your cards and it gets +5000 power for the battle. "
        "[Activate: Main] Choose 1 <Frieza> card with an energy cost of 4 in your Battle Area and place this card under it: "
        "Play up to 1 green <Frieza: Xeno> card in your deck or hand on top of the chosen card in Active Mode, then shuffle your deck if you looked through it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_place_self_under_matching_owner_battle_then_play_up_to_n_from_owner_deck_or_hand_on_top_of_host"
    )
    assert rule.handler_params["max_host_targets"] == 1
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_owner_battle_required_characters"] == "Frieza"
    assert rule.handler_params["required_owner_battle_min_cost"] == 4
    assert rule.handler_params["required_owner_battle_max_cost"] == 4
    assert rule.handler_params["allowed_colors"] == "green"
    assert rule.handler_params["required_characters"] == "Frieza: Xeno"
    assert rule.handler_params["play_on_top_active_mode"] is True


def test_extract_majin_buu_battle_under_choose_from_deck_or_hand_on_top_rule() -> None:
    card = _card(
        "[Permanent] This card gains ≪Dark Dragon Ball≫ in all areas. "
        "[Activate: Battle] Choose 1 of your cards and that card gets +5000 power for the battle. "
        "[Activate: Main] Choose 1 mono-green <Majin Buu> card with an energy cost of 3 in your Battle Area and place this card under it: "
        "Choose up to 1 green <Majin Buu: Xeno> card with an energy cost of 5 or less in your deck or hand, "
        "play it on top of the chosen card in Active Mode, then shuffle your deck if you looked through it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_place_self_under_matching_owner_battle_then_play_up_to_n_from_owner_deck_or_hand_on_top_of_host"
    )
    assert rule.handler_params["max_host_targets"] == 1
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_owner_battle_allowed_colors"] == "green"
    assert rule.handler_params["required_owner_battle_require_mono_color"] is True
    assert rule.handler_params["required_owner_battle_required_characters"] == "Majin Buu"
    assert rule.handler_params["required_owner_battle_min_cost"] == 3
    assert rule.handler_params["required_owner_battle_max_cost"] == 3
    assert rule.handler_params["allowed_colors"] == "green"
    assert rule.handler_params["required_characters"] == "Majin Buu: Xeno"
    assert rule.handler_params["max_cost"] == 5


def test_extract_turles_battle_under_discrete_cost_on_top_rule() -> None:
    card = _card(
        "[Permanent] This card gains ≪Dark Dragon Ball≫ in all areas. "
        "[Activate: Battle] Choose 1 of your cards and it gets +5000 power for the battle. "
        "[Activate: Main] If your opponent has 2 or more energy and you choose 1 of your mono-green <Turles> cards with an energy cost of 3 or 4 and place this card under it: "
        "Choose up to 1 green <Turles: Xeno> card with an energy cost of 4 in your deck or hand, play it on top of the chosen card in Active Mode, then shuffle your deck if you looked through it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_place_self_under_matching_owner_battle_then_play_up_to_n_from_owner_deck_or_hand_on_top_of_host"
    )
    assert rule.handler_params["min_opponent_energy"] == 2
    assert rule.handler_params["required_owner_battle_allowed_colors"] == "green"
    assert rule.handler_params["required_owner_battle_require_mono_color"] is True
    assert rule.handler_params["required_owner_battle_required_characters"] == "Turles"
    assert rule.handler_params["required_owner_battle_allowed_costs"] == "3,4"
    assert rule.handler_params["required_owner_battle_min_cost"] == 3
    assert rule.handler_params["required_owner_battle_max_cost"] == 4
    assert rule.handler_params["required_characters"] == "Turles: Xeno"
    assert rule.handler_params["allowed_costs"] == "4"
    assert rule.handler_params["min_cost"] == 4
    assert rule.handler_params["max_cost"] == 4


def test_extract_janemba_battle_under_on_top_rule() -> None:
    card = _card(
        "[Permanent] This card gains ≪Dark Dragon Ball≫ in all areas. "
        "[Activate: Battle] Choose 1 of your cards and it gets +5000 power for the battle. "
        "[Activate: Main] If you have 2 or more energy and you choose 1 of your mono-blue <Janemba> cards with an energy cost of 3 and place this card under it: "
        "Play up to 1 blue <Janemba: Xeno> card with an energy cost of 4 from your deck or hand on top of the chosen card in Active Mode, then shuffle your deck if you looked through it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_place_self_under_matching_owner_battle_then_play_up_to_n_from_owner_deck_or_hand_on_top_of_host"
    )
    assert rule.handler_params["min_owner_energy"] == 2
    assert rule.handler_params["required_owner_battle_allowed_colors"] == "blue"
    assert rule.handler_params["required_owner_battle_require_mono_color"] is True
    assert rule.handler_params["required_owner_battle_required_characters"] == "Janemba"
    assert rule.handler_params["required_owner_battle_allowed_costs"] == "3"
    assert rule.handler_params["required_characters"] == "Janemba: Xeno"
    assert rule.handler_params["allowed_colors"] == "blue"
    assert rule.handler_params["allowed_costs"] == "4"


def test_extract_lord_slug_battle_under_discrete_cost_on_top_rule() -> None:
    card = _card(
        "[Permanent] This card gains ≪Dark Dragon Ball≫ in all areas. "
        "[Activate: Battle] Choose 1 of your cards and it gets +5000 power for the battle. "
        "[Activate: Main] If your opponent has 3 or more energy and you choose 1 of your mono-green <Lord Slug> cards with an energy cost of 3 or 4 and place this card under it: "
        "Choose up to 1 green <Lord Slug: Xeno> card with an energy cost of 4 in your deck or hand, play it on top of the chosen card in Active Mode, then shuffle your deck if you looked through it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_place_self_under_matching_owner_battle_then_play_up_to_n_from_owner_deck_or_hand_on_top_of_host"
    )
    assert rule.handler_params["min_opponent_energy"] == 3
    assert rule.handler_params["required_owner_battle_allowed_colors"] == "green"
    assert rule.handler_params["required_owner_battle_require_mono_color"] is True
    assert rule.handler_params["required_owner_battle_required_characters"] == "Lord Slug"
    assert rule.handler_params["required_owner_battle_allowed_costs"] == "3,4"
    assert rule.handler_params["required_characters"] == "Lord Slug: Xeno"
    assert rule.handler_params["allowed_colors"] == "green"
    assert rule.handler_params["allowed_costs"] == "4"


def test_extract_cell_battle_under_choose_from_deck_or_hand_plain_play_rule() -> None:
    card = _card(
        "[Permanent] This card gains â‰ªDark Dragon Ballâ‰« in all areas. "
        "[Activate: Battle] Choose 1 of your cards and it gets +5000 power for the battle. "
        "[Activate: Main] Choose 1 of your <Cell> cards with an energy cost of 7 or 9 and place this card under it: "
        "Choose up to 1 green <Cell: Xeno> card with an energy cost of 9 in your deck or hand, play it, then shuffle your deck if you looked through it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_place_self_under_matching_owner_battle_then_play_up_to_n_from_owner_deck_or_hand"
    )
    assert rule.handler_params["max_host_targets"] == 1
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_owner_battle_required_characters"] == "Cell"
    assert rule.handler_params["required_owner_battle_allowed_costs"] == "7,9"
    assert rule.handler_params["allowed_colors"] == "green"
    assert rule.handler_params["required_characters"] == "Cell: Xeno"
    assert rule.handler_params["allowed_costs"] == "9"
    assert rule.handler_params["min_cost"] == 9
    assert rule.handler_params["max_cost"] == 9


def test_extract_play_self_from_hand_and_place_matching_owner_battle_under_self_rule() -> None:
    card = _card(
        "[Auto][Limit 1] Place 1 card from under this card in its owner's Drop: When this card attacks, choose up to 1 of your opponent's Battle Cards and it gets -30000 power for the turn. "
        "[Activate: Main](Red), choose 1 red ≪Saiyan≫ card in your Battle Area: Play this card from your hand and place the chosen card under it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_play_self_from_hand"
        and int(r.handler_params.get("post_play_place_owner_battle_under_self_max_targets", 0) or 0) == 1
    )
    assert rule.handler_params["post_play_place_owner_battle_under_self_allowed_colors"] == "red"
    assert rule.handler_params["post_play_place_owner_battle_under_self_required_traits"] == "Saiyan"


def test_extract_family_united_minus_four_bottom_deck_rule() -> None:
    card = _card(
        "[-4][Activate: Main] Choose up to 1 of your opponent's Battle Cards, ignoring [Barrier], and place it at the bottom of its owner's deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_bottom_deck_up_to_n_opponent_battle")
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["ignores_barrier"] is True
    assert rule.handler_params["marker_delta"] == -4


def test_extract_krillin_accel_dance_on_play_composite_rule() -> None:
    card = _card(
        "[Auto][Limit 1] If your Leader is a blue <Android 18> card: When this card is played, choose up to 1 of your opponent's Battle Cards, "
        "place it at the bottom of its owner's deck, switch up to 1 of your Leaders to Active Mode, switch up to 1 of your mono-blue energy to Active Mode, "
        "and this card gains [Barrier] until the end of your opponent's next turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_played"
        and r.handler_id == "auto_bottom_deck_up_to_n_opponent_battle_then_switch_up_to_n_owner_leader_and_energy_active_and_gain_keyword_until_opponent_turn_on_play"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["switch_leader_max_targets"] == 1
    assert rule.handler_params["switch_energy_max_targets"] == 1
    assert rule.handler_params["energy_allowed_colors"] == "blue"
    assert rule.handler_params["energy_requires_mono"] is True
    assert rule.handler_params["grant_keyword"] == "Barrier"


def test_extract_android_18_energy_wave_rules() -> None:
    card = _card(
        "[Double Strike] "
        "[Auto][Limit 1](Blue), if your Leader is blue and you have 3 or more energy: "
        "When you use a blue <Krillin> card from your hand or Battle Area in a combo, play this card from under your Leader or from your hand. "
        "[Auto](Blue): When this card is played, play up to 1 mono-blue <Krillin> card with an energy cost of 3 from your Z-Energy, Combo Area, or Drop."
    )
    rules = extract_effect_rules_from_card(card)
    combo_rule = next(
        r
        for r in rules
        if r.trigger == "owner_card_comboed"
        and r.handler_id == "auto_play_self_from_under_leader_or_owner_hand_on_owner_combo"
    )
    play_rule = next(
        r
        for r in rules
        if r.trigger == "self_played"
        and r.handler_id == "auto_play_up_to_n_from_owner_z_energy_combo_or_drop_on_play"
    )
    assert combo_rule.handler_params["event_allowed_colors"] == "blue"
    assert str(combo_rule.handler_params["event_required_characters"]).lower() == "krillin"
    assert combo_rule.handler_params["min_owner_energy"] == 3
    assert play_rule.handler_params["max_targets"] == 1
    assert play_rule.handler_params["allowed_colors"] == "blue"
    assert play_rule.handler_params["required_characters"] == "Krillin"
    assert play_rule.handler_params["max_cost"] == 3


def test_extract_android_18_krillin_future_spun_by_battle_rules() -> None:
    card = _card(
        "[Deflect][Dual Attack] "
        "[Auto] If you don't have a Unison in play: When this card is played, play up to 1 {Android 18, Krillin, and Marron, Family United} "
        "from your deck with a marker on it in Rest Mode, and shuffle your deck. "
        "[Activate: Main][Limit 1](Blue)(Blue), if your Leader is a blue <Android 18> card and there are 2 or more cards under it: Play this card from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(
        r
        for r in rules
        if r.trigger == "self_played"
        and r.handler_id == "auto_play_up_to_n_from_owner_deck_on_play"
    )
    activate_rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_play_self_from_hand"
    )
    assert play_rule.handler_params["max_targets"] == 1
    assert play_rule.handler_params["required_name_contains"] == "ANDROID 18, KRILLIN, AND MARRON, FAMILY UNITED"
    assert play_rule.handler_params["markers"] == 1
    assert play_rule.handler_params["rest_mode"] is True
    assert play_rule.handler_params["requires_no_owner_unison"] is True
    assert activate_rule.handler_params["required_owner_leader_under_count_at_least"] == 2
    assert activate_rule.handler_params["required_leader_traits"] == "Android 18"


def test_extract_krillin_absolute_guard_rules() -> None:
    card = _card(
        "[Super Combo] [Auto] If your Leader is blue and your life is at 4 or less: "
        "When this card is used in a combo, draw 1 card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_draw_n"
    )
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["max_owner_life"] == 4
    assert "blue" in str(rule.handler_params.get("requires_leader", "")).lower()


def test_extract_bulma_helpful_cheer_rules() -> None:
    card = _card(
        "[Auto] When this card is played, draw 1 card. "
        "[Auto][Limit 1] If your Leader is a blue <Android 18> card and you place 1 non-Leaders from under your Leader in its owner's Drop: "
        "When this card is used in a combo, choose up to 1 of your <Krillin> or <Android 18> cards and it gets +1000 power for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    played_draw = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "auto_draw_n")
    combo_buff = next(
        r
        for r in rules
        if r.trigger == "self_comboed" and r.handler_id == "auto_buff_up_to_n_owner_battles_for_battle_on_combo"
    )
    assert played_draw.handler_params["amount"] == 1
    assert combo_buff.handler_params["max_targets"] == 1
    assert combo_buff.handler_params["power_delta"] == 1000
    assert combo_buff.handler_params["required_characters"] == "Android 18,Krillin"
    assert "android 18" in str(combo_buff.handler_params.get("requires_leader", "")).lower()


def test_extract_krillin_powers_expanded_rules() -> None:
    card = _card(
        "[Permanent] While you have a blue <Android 18> card with an energy cost of 5 or more in play, this card gains [Dual Attack]. "
        "[Auto] When this card is played, choose up to 1 of your opponent's Battle Cards with an energy cost of 4 or less and place it at the bottom of its owner's deck. "
        "[Activate: Main][Limit 1](Blue), if your Leader is blue and you have 3 or more energy: Play this card from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    played_rule = next(
        r
        for r in rules
        if r.trigger == "self_played" and r.handler_id == "auto_bottom_deck_up_to_n_opponent_battle"
    )
    activate_rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main" and r.handler_id == "activate_play_self_from_hand"
    )
    assert played_rule.handler_params["max_targets"] == 1
    assert played_rule.handler_params["max_cost"] == 4
    assert "blue" in str(activate_rule.handler_params.get("requires_leader", "")).lower()
    assert activate_rule.handler_params["min_owner_energy"] == 3


def test_extract_krillin_defensive_battler_rules() -> None:
    card = _card(
        "[Deflect] "
        "[Permanent] While you have a blue <Android 18> card with an energy cost of 5 or more in play, this card gets +5000 power and [Blocker]. "
        "[Auto] At the end of your turn, switch this card to Active Mode. "
        "[Activate: Main][Limit 1](Blue), if your Leader is blue and you have 3 or more energy: Play this card from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    turn_end_rule = next(
        r
        for r in rules
        if r.trigger == "turn_end" and r.handler_id == "auto_switch_self_active_on_turn_end"
    )
    activate_rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main" and r.handler_id == "activate_play_self_from_hand"
    )
    assert "blue" in str(turn_end_rule.handler_params.get("requires_leader", "")).lower()
    assert turn_end_rule.handler_params["min_owner_energy"] == 3
    assert "blue" in str(activate_rule.handler_params.get("requires_leader", "")).lower()
    assert activate_rule.handler_params["min_owner_energy"] == 3


def test_extract_activate_main_can_place_self_from_under_leader_on_top_of_owner_leader() -> None:
    card = _card(
        "[Activate: Main] If a <Cell> card is under your Leader and you place 1 card from under a <Super 17> card in your Battle Area in its owner's Drop: "
        "Place this card from under your Leader on top of your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_place_self_from_under_owner_leader_on_top_of_owner_leader")
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["required_source_zone"] == "leader_under"
    assert rule.handler_params["required_owner_leader_under_count_at_least"] == 1
    assert "cell" in str(
        rule.handler_params.get("required_owner_leader_under_required_characters")
        or rule.handler_params.get("required_owner_leader_under_required_traits")
        or ""
    ).lower()
    assert rule.handler_params["move_under_owner_battle_to_drop_before"] == 1
    assert rule.handler_params["required_owner_battle_under_count_at_least"] == 1
    assert "super 17" in str(
        rule.handler_params.get("required_owner_battle_under_host_required_characters")
        or rule.handler_params.get("required_owner_battle_under_host_required_traits")
        or ""
    ).lower()


def test_extract_activate_main_can_place_self_from_under_leader_on_top_of_owner_leader_and_switch_active() -> None:
    card = _card(
        "[Activate: Main] If a <Cell> card is under your Leader and you place 1 card from under a <Super 17> card in your Battle Area in its owner's Drop: "
        "Place this card from under your Leader on top of your Leader, and if you placed a card, you may switch your Leader to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_place_self_from_under_owner_leader_on_top_of_owner_leader")
    assert rule.handler_params["switch_owner_leader_active_after"] is True


def test_extract_turn_end_can_place_self_from_under_leader_on_top_with_under_battle_payment_clause() -> None:
    card = _card(
        "[Auto] If an <Android 18> card is under your Leader and you place 1 card from under a <Super 17> card in your Battle Area in its owner's Drop: "
        "At the end of your turn, place this card from under your Leader on top of your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_place_self_from_under_owner_leader_on_top_of_owner_leader_on_turn_end")
    assert rule.trigger == "turn_end"
    assert rule.handler_params["required_owner_leader_under_count_at_least"] == 1
    assert "android 18" in str(
        rule.handler_params.get("required_owner_leader_under_required_characters")
        or rule.handler_params.get("required_owner_leader_under_required_traits")
        or ""
    ).lower()
    assert rule.handler_params["move_under_owner_battle_to_drop_before"] == 1


def test_extract_activate_main_can_remove_self_and_place_matching_under_leader_on_top_of_owner_leader() -> None:
    card = _card(
        "[Activate: Main] If there are 7 or more cards under a {Spirit Bomb} in your Battle Area: "
        "Remove this card from the game, place up to 1 <Son Goku> Z-Leader from under your Leader on top of your Leader, "
        "and if you placed a card, you may switch your Leader to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "activate_remove_self_and_place_up_to_n_from_under_owner_leader_on_top_of_owner_leader"
    )
    assert rule.trigger == "self_activate_main"
    assert rule.handler_params["required_owner_battle_under_count_at_least"] == 7
    assert rule.handler_params["required_owner_battle_under_host_required_name_contains"] == "SPIRIT BOMB"
    assert "son goku" in str(
        rule.handler_params.get("required_characters")
        or rule.handler_params.get("required_traits")
        or ""
    ).lower()
    assert rule.handler_params["required_card_type"] == "Z-LEADER"
    assert rule.handler_params["switch_owner_leader_active_after"] is True


def test_extract_self_comboed_from_battle_can_draw_and_add_self_to_z_energy() -> None:
    card = _card(
        "[Auto][Limit 1] There is a {Hyperbolic Time Chamber} in your Battle Area and a skill-less Battle Card in your Combo Area: "
        "When this card in your Battle Area is used in a combo, draw 1 card and add this card to its owner's Z-Energy."
    )
    rules = extract_effect_rules_from_card(card)
    draw_rule = next(r for r in rules if r.trigger == "self_comboed" and r.handler_id == "auto_draw_n")
    assert draw_rule.handler_params["amount"] == 1
    assert draw_rule.handler_params["requires_comboed_from"] == "battle"
    assert draw_rule.handler_params["required_owner_battle_required_name_contains"] == "HYPERBOLIC TIME CHAMBER"
    assert draw_rule.handler_params["required_owner_combo_required_card_type"] == "BATTLE"
    assert draw_rule.handler_params["required_owner_combo_requires_skill_less"] is True

    z_rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed_battle_end" and r.handler_id == "auto_add_self_to_owner_z_energy_on_battle_end"
    )
    assert z_rule.handler_params["requires_comboed_from"] == "battle"
    assert z_rule.handler_params["required_owner_battle_required_name_contains"] == "HYPERBOLIC TIME CHAMBER"
    assert z_rule.handler_params["required_owner_combo_required_card_type"] == "BATTLE"
    assert z_rule.handler_params["required_owner_combo_requires_skill_less"] is True


def test_extract_opponent_main_phase_can_play_from_under_self_and_place_self_under_played() -> None:
    card = _card(
        "[Auto] If your Leader is a red <Warriors of Universe 7> card: At the start of your opponent's Main Phase, play up to 1 red ≪Universe 7≫ card with an energy cost of 2 or less from under this card, and place this card under the played card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_under_self_and_place_self_under_played_card")
    assert rule.trigger == "owner_opponent_main_phase_start"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "red"
    assert rule.handler_params["required_traits"] == "Universe 7"
    assert rule.handler_params["max_cost"] == 2
    assert "warriors of universe 7" in rule.handler_params["requires_leader"]


def test_extract_owner_main_phase_can_play_from_under_self_and_place_self_under_played() -> None:
    card = _card(
        "[Auto] At the start of your Main Phase, play up to 1 red <Piccolo Jr.> or ≪Demon Clan≫ card with an energy cost of 3 from under this card, and place this card under the played card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_under_self_and_place_self_under_played_card")
    assert rule.trigger == "owner_main_phase_start"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "red"
    assert "Piccolo Jr." in rule.handler_params["required_characters"]
    assert "Demon Clan" in rule.handler_params["required_traits"]
    assert rule.handler_params["max_cost"] == 3


def test_extract_costed_opponent_main_phase_can_play_from_under_self_and_place_self_under_played() -> None:
    card = _card(
        "[Auto](Red), if your Leader is a red <Warriors of Universe 7> card and your opponent has 2 or more energy: "
        "At the start of your opponent's Main Phase, play up to 1 red ≪Universe 7≫ card with an energy cost of 3 or less from under this card, and place this card under the played card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_under_self_and_place_self_under_played_card")
    assert rule.trigger == "owner_opponent_main_phase_start"
    assert rule.handler_params["auto_cost_header"] == "(red)"
    assert rule.handler_params["min_opponent_energy"] == 2


def test_extract_owner_main_phase_draw_can_place_self_in_drop_before() -> None:
    card = _card("[Auto] Place this card in its owner's Drop: At the start of your Main Phase, draw 1 card.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_draw_n")
    assert rule.trigger == "owner_main_phase_start"
    assert rule.handler_params["amount"] == 1
    assert bool(rule.handler_params["auto_place_self_in_drop_before"]) is True


def test_extract_costed_opponent_main_phase_draw_switch_and_keyword_auto() -> None:
    card = _card(
        "[+1][Auto] Discard 1 card from your hand: "
        "At the start of your opponent's Main Phase, draw 1 card, switch up to 1 of your Leaders and up to 1 of your energy to Active Mode, and your Leader gains [Blocker] for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "auto_draw_n_switch_up_to_n_owner_leader_and_energy_active_and_grant_owner_leader_keyword_for_turn"
    )
    assert rule.trigger == "owner_opponent_main_phase_start"
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["max_leader_targets"] == 1
    assert rule.handler_params["max_energy_targets"] == 1
    assert rule.handler_params["grant_keyword"] == "Blocker"
    assert rule.handler_params["auto_discard_hand_before"] == 1
    assert rule.handler_params["auto_marker_delta"] == 1


def test_extract_owner_main_phase_draw_can_bottom_deck_hand_before() -> None:
    card = _card(
        "[0][Auto] If your Leader is a <Trunks: Future> card and you place 1 card from your hand at the bottom of your deck: "
        "At the start of your opponent's Main Phase, draw 1 card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_draw_n")
    assert rule.trigger == "owner_opponent_main_phase_start"
    assert rule.handler_params["auto_marker_delta"] == 0
    assert rule.handler_params["auto_bottom_deck_hand_before"] == 1


def test_extract_owner_main_phase_draw_can_remove_self_before() -> None:
    card = _card("[Auto] Remove this card from the game: At the start of your opponent's Main Phase, draw 1 card.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_draw_n")
    assert rule.trigger == "owner_opponent_main_phase_start"
    assert bool(rule.handler_params["auto_remove_self_before"]) is True


def test_extract_owner_main_phase_draw_can_release_under_cards_to_drop_before() -> None:
    card = _card(
        "[Auto] Place 2 cards from under this card in their owners' Drops: At the start of your Main Phase, draw 1 card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_draw_n")
    assert rule.trigger == "owner_main_phase_start"
    assert rule.handler_params["auto_release_under_to_drop_before"] == 2


def test_extract_opponent_main_phase_can_play_from_owner_drop() -> None:
    card = _card(
        "[Auto][Limit 1] Place this card in its owner's Drop: "
        "At the start of your opponent's Main Phase, play up to 1 blue <Gogeta> card with an energy cost of 5 and a [Union] skill from your Drop."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_drop_on_main_phase_start")
    assert rule.trigger == "owner_opponent_main_phase_start"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "blue"
    assert "Gogeta" in rule.handler_params["required_characters"]
    assert rule.handler_params["max_cost"] == 5
    assert rule.handler_params["required_skill_text_contains"] == "[union]"
    assert bool(rule.handler_params["auto_place_self_in_drop_before"]) is True


def test_extract_owner_main_phase_can_play_from_owner_hand() -> None:
    card = _card(
        "[Auto](Blue): At the start of your Main Phase, play up to 1 blue <Frost> Battle Card with an energy cost of 4 or less from your hand in Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_hand_on_main_phase_start")
    assert rule.trigger == "owner_main_phase_start"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "blue"
    assert "Frost" in rule.handler_params["required_characters"]
    assert rule.handler_params["max_cost"] == 4
    assert bool(rule.handler_params["rest_mode"]) is True
    assert rule.handler_params["auto_cost_header"] == "(blue)"


def test_extract_opponent_main_phase_can_switch_owner_energy_active() -> None:
    card = _card(
        "[Auto][+1] Discard 1 card from your hand: At the start of your opponent's Main Phase, choose up to 1 of your multicolor energy and switch it to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_switch_up_to_n_owner_energy_active_on_main_phase_start")
    assert rule.trigger == "owner_opponent_main_phase_start"
    assert rule.handler_params["max_targets"] == 1
    assert bool(rule.handler_params["requires_multicolor"]) is True
    assert rule.handler_params["auto_discard_hand_before"] == 1
    assert rule.handler_params["auto_marker_delta"] == 1


def test_extract_owner_main_phase_can_play_from_owner_deck_with_markers() -> None:
    card = _card(
        "[Auto](Blue), if your Leader Card and energy are all mono-blue and you choose 1 card in your hand and discard it: "
        "At the start of your Main Phase, play up to 1 {Frieza & Cell, a Match Made in Hell} from your deck with 2 markers on it in Rest Mode, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_deck_on_main_phase_start")
    assert rule.trigger == "owner_main_phase_start"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_name_contains"] == "FRIEZA & CELL, A MATCH MADE IN HELL"
    assert rule.handler_params["markers"] == 2
    assert bool(rule.handler_params["rest_mode"]) is True
    assert rule.handler_params["auto_cost_header"] == "(blue)"
    assert rule.handler_params["auto_discard_hand_before"] == 1
    assert rule.handler_params["requires_mono_energy"] == "blue"


def test_extract_opponent_main_phase_can_switch_self_active_and_gain_keyword() -> None:
    card = _card(
        "[Auto] If you have a yellow <Vegeta> card in play or in your Z-Energy: "
        "At the start of your opponent's Main Phase, switch this card to Active Mode, and it gains [Blocker] for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_switch_self_active_and_gain_keyword_for_turn_on_main_phase_start")
    assert rule.trigger == "owner_opponent_main_phase_start"
    assert rule.handler_params["grant_keyword"] == "Blocker"
    assert rule.handler_params["required_owner_battle_or_z_energy_allowed_colors"] == "yellow"
    assert rule.handler_params["required_owner_battle_or_z_energy_required_characters"] == "Vegeta"


def test_extract_owner_main_phase_can_play_from_owner_hand_on_top_of_self() -> None:
    card = _card(
        "[Auto](Blue)(Blue): At the start of your Main Phase, choose up to 1 blue <Frost> card with an energy cost of 4 in your hand and play it on top of this card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_hand_on_top_of_self_on_main_phase_start")
    assert rule.trigger == "owner_main_phase_start"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "blue"
    assert "Frost" in rule.handler_params["required_characters"]
    assert rule.handler_params["max_cost"] == 4
    assert rule.handler_params["auto_cost_header"] == "(blue)(blue)"


def test_extract_ex_evolve_followup_draw_and_switch_self_active_rules() -> None:
    card = _card(
        "[Deflect][Double Strike] "
        "[EX-Evolve][Limit 1]{r} : Red <Son Goten> card with an energy cost of 1. "
        "[Auto] When this card is played, draw 1 card and switch this card to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    assert any(
        rule.trigger == "self_played"
        and rule.handler_id == "auto_draw_n"
        and rule.handler_params.get("amount") == 1
        for rule in rules
    )
    assert any(rule.trigger == "self_played" and rule.handler_id == "auto_switch_self_active_on_play" for rule in rules)


def test_extract_pursuit_activate_main_search_rule() -> None:
    card = _card(
        "[Auto] When this card is played, draw 1 card. "
        "[Activate: Main][Limit 1] If your Leader is a red <Krillin> card and you discard this card from your hand : "
        "Add up to 1 red <Son Goten> card with an energy cost of 3 and [EX-Evolve] from your deck to your hand, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    search_rule = next(
        rule for rule in rules
        if rule.trigger == "self_activate_main" and rule.handler_id == "activate_add_up_to_n_from_owner_deck_to_hand"
    )
    assert search_rule.limit_per_turn == 1
    assert search_rule.handler_params["max_targets"] == 1
    assert search_rule.handler_params["allowed_colors"] == "red"
    assert search_rule.handler_params["required_characters"] == "Son Goten"
    assert search_rule.handler_params["max_cost"] == 3
    assert search_rule.handler_params["requires_ex_evolve"] is True
    assert "krillin" in str(search_rule.handler_params.get("requires_leader", "")).lower()


def test_extract_activate_main_search_rule_can_negate_itself_for_game() -> None:
    card = _card(
        "[Activate: Main] Add up to 1 {Potara} from your deck to your hand, shuffle your deck, and negate this skill for the game."
    )
    rules = extract_effect_rules_from_card(card)
    search_rule = next(
        rule for rule in rules
        if rule.trigger == "self_activate_main" and rule.handler_id == "activate_add_up_to_n_from_owner_deck_to_hand"
    )
    assert search_rule.handler_params["max_targets"] == 1
    assert search_rule.handler_params["required_name_contains"] == "POTARA"
    assert search_rule.handler_params["negate_self_skill_for_game"] is True


def test_extract_cross_dimensional_fighting_spirit_families() -> None:
    card = _card(
        "[Auto] When this card is played, choose up to 1 of your opponent's Battle Cards and send it to its owner's Warp. "
        "[Activate: Main][Once per turn] If you have 3 or more energy and you remove 10 total cards in your Drop and Warp from the game: "
        "This card gets +10000 power and [Double Strike] for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(rule for rule in rules if rule.handler_id == "auto_send_up_to_n_opponent_battle_to_warp_on_play")
    assert play_rule.trigger == "self_played"
    assert play_rule.handler_params["max_targets"] == 1
    activate_rule = next(rule for rule in rules if rule.handler_id == "activate_gain_power_and_keyword_for_turn")
    assert activate_rule.trigger == "self_activate_main"
    assert activate_rule.once_per_turn is True
    assert activate_rule.handler_params["power_delta"] == 10000
    assert activate_rule.handler_params["grant_keyword"] == "Double Strike"
    assert activate_rule.handler_params["min_owner_energy"] == 3


def test_extract_hit_can_send_opponent_battle_to_warp_and_play_it_later() -> None:
    card = _card(
        "[Activate: Main][Once per turn] Choose up to 1 of your opponent's Battle Cards, negate its skills for the duration of the turn, "
        "and send it to its owner's Warp. At the end of your opponent's next turn, play the card sent to the Warp by this skill from the Warp in its owner's Battle Area in Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    send_rule = next(rule for rule in rules if rule.handler_id == "activate_send_up_to_n_opponent_battle_to_warp")
    schedule_rule = next(rule for rule in rules if rule.handler_id == "activate_schedule_play_cards_warped_by_source_skill")
    assert send_rule.trigger == "self_activate_main"
    assert send_rule.handler_params["max_targets"] == 1
    assert send_rule.once_per_turn is True
    assert schedule_rule.trigger == "self_activate_main"
    assert schedule_rule.handler_params["affected_player_scope"] == "opponent"
    assert schedule_rule.handler_params["trigger_kind"] == "turn_end"
    assert schedule_rule.handler_params["trigger_player_scope"] == "opponent"
    assert schedule_rule.handler_params["resting"] is True
    assert schedule_rule.once_per_turn is True


def test_extract_universe_6_card_can_schedule_self_play_from_warp_next_turn() -> None:
    card = _card(
        "[Activate: Main] Send this card to the Warp: At the beginning of your next turn, if your Leader Card is ≪Universe 6≫, play this card from the Warp in its owner's Battle Area."
    )
    rules = extract_effect_rules_from_card(card)
    schedule_rule = next(rule for rule in rules if rule.handler_id == "activate_schedule_play_cards_warped_by_source_skill")
    assert schedule_rule.trigger == "self_activate_main"
    assert schedule_rule.handler_params["affected_player_scope"] == "owner"
    assert schedule_rule.handler_params["mark_source_in_owner_warp"] is True
    assert schedule_rule.handler_params["trigger_kind"] == "main_phase_start"
    assert schedule_rule.handler_params["trigger_player_scope"] == "owner"


def test_extract_ultimate_dragon_quake_can_warp_then_replay_or_drop_at_end_of_current_turn() -> None:
    card = replace(
        _card(
            "[Permanent] This card gains ≪Shadow Dragon≫ in all areas. "
            "[Activate: Main/Battle][Limit 1] If your Leader Card is a ≪Shadow Dragon≫ card: "
            "Choose up to 1 of your opponent's Battle Cards with an energy cost greater than their current energy and send it to its owner's Warp. "
            "At the end of the turn, play any cards sent to a Warp by this skill to their owners' Battle Areas with their skills negated for the turn. "
            "If your opponent has 15 or fewer cards in their deck, place them in their owners' Drop Areas instead."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.handler_id == "activate_send_up_to_n_opponent_battle_to_warp_and_schedule_play_warped_cards_later"
    )
    assert rule.trigger == "self_activate_extra_from_hand"
    assert rule.handler_params["send_max_targets"] == 1
    assert rule.handler_params["max_targets"] == -1
    assert rule.handler_params["requires_cost_greater_than_opponent_current_energy"] is True
    assert rule.handler_params["required_leader_traits"] == "Shadow Dragon"
    assert rule.handler_params["trigger_kind"] == "turn_end"
    assert rule.handler_params["trigger_player_scope"] == "current"
    assert rule.handler_params["require_next_turn"] is False
    assert rule.handler_params["negate_skills"] is True
    assert rule.handler_params["drop_instead_if_affected_deck_at_most"] == 15


def test_extract_counter_attack_can_warp_attacking_battle_and_replay_it_at_turn_end() -> None:
    card = _card(
        "[Counter: Attack] If your Leader Card is ≪Universe 6≫: Negate the attack, choose up to 1 attacking Battle Card and send it to the Warp. "
        "At the end of the turn, your opponent plays the card sent to the Warp with this skill in its owner's Battle Area from the Warp in Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    warp_rule = next(rule for rule in rules if rule.handler_id == "counter_send_up_to_n_attacking_battle_to_warp")
    schedule_rule = next(rule for rule in rules if rule.handler_id == "counter_schedule_play_cards_warped_by_source_skill")
    assert warp_rule.trigger == "counter_attack"
    assert warp_rule.handler_params["max_targets"] == 1
    assert schedule_rule.trigger == "counter_attack"
    assert schedule_rule.handler_params["affected_player_scope"] == "opponent"
    assert schedule_rule.handler_params["trigger_kind"] == "turn_end"
    assert schedule_rule.handler_params["trigger_player_scope"] == "opponent"
    assert schedule_rule.handler_params["require_next_turn"] is False
    assert schedule_rule.handler_params["resting"] is True


def test_extract_counter_attack_can_schedule_clone_token_at_turn_end() -> None:
    card = _card(
        "[Counter: Attack] If your Leader is a blue ≪Android≫ card: Negate the attack and switch up to 1 of your blue energy to Active Mode. "
        "Additionally, at the end of the turn, play 1 Clone Token with 10000 power in your opponent's Battle Area."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "counter_schedule_play_token_in_battle")
    assert token_rule.trigger == "counter_attack"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "clone token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["trigger_kind"] == "turn_end"
    assert token_rule.handler_params["trigger_player_scope"] == "current"
    assert token_rule.handler_params["require_next_turn"] is False
    assert token_rule.handler_params["controller_player_scope"] == "opponent"
    assert token_rule.handler_params["switch_owner_energy_active_max_targets"] == 1
    assert token_rule.handler_params["switch_owner_energy_active_allowed_colors"] == "blue"


def test_extract_counter_attack_can_play_skillless_monster_from_hand_and_redirect_attack() -> None:
    card = _card(
        "[Counter: Attack] Choose up to 1 skill-less ≪Monster≫ card in your hand with an energy cost of 2 or less "
        "and play it in Rest Mode. If you played a card, it becomes the target of attack."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "counter_attack"
        and rule.handler_id == "counter_play_up_to_n_skillless_from_owner_hand_rest_and_redirect_attack"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_traits"] == "Monster"
    assert rule.handler_params["max_cost"] == 2
    assert rule.handler_params["event_requires_skill_less"] is True
    assert rule.handler_params["rest_mode"] is True


def test_extract_absorption_of_doom_counter_attack_limit_rule() -> None:
    card = _card(
        "[Counter: Attack] If your Leader Card is a black <Fin> card: Negate the attack. "
        "Additionally, if your opponent has a skill-less Battle Card or Unison Card in play, they can only attack two more times for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "counter_attack"
        and rule.handler_id == "counter_limit_opponent_attacks_if_opponent_has_skillless_battle_or_unison"
    )
    assert rule.handler_params["remaining_attacks"] == 2


def test_extract_counter_attack_can_play_demon_realm_soldier_token_with_blocker() -> None:
    card = _card(
        "[Counter: Attack] If your Leader Card is mono-black: Negate the attack, then play 1 Demon Realm Soldier Token "
        "and it gains [Blocker] for the turn. (Demon Realm Soldier Tokens have 5000 power, 0 combo cost, and 5000 combo power.)"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "counter_play_token_in_battle")
    assert token_rule.trigger == "counter_attack"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "demon realm soldier token"
    assert token_rule.handler_params["power"] == 5000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000
    assert token_rule.handler_params["temporary_keywords"] == "blocker"


def test_extract_counter_attack_can_play_meda_token_with_blocker_in_next_sentence() -> None:
    card = _card(
        "[Counter: Attack] If your Leader Card is mono-green: Negate the attack, then play 1 Meda Token. "
        "That Token gains [Blocker] for the turn. (Meda Tokens have 5000 power, 0 combo cost, and 5000 combo power.)"
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "counter_play_token_in_battle")
    assert token_rule.trigger == "counter_attack"
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "meda token"
    assert token_rule.handler_params["power"] == 5000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000
    assert token_rule.handler_params["temporary_keywords"] == "blocker"
    assert token_rule.handler_params["keyword_duration"] == "turn"


def test_extract_counter_played_card_can_replay_warped_cards_at_turn_end() -> None:
    card = _card(
        "[Counter: Attack] Negate the attack and play this card. "
        "[Auto] If your Leader Card is black: When this card is played using its [Counter: Attack] skill, choose up to 1 of your opponent's Battle Cards and send it to its owner's Warp. "
        "At the end of the turn, play any cards sent to a Warp by this skill to their owners' Battle Areas with their skills negated for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    warp_rule = next(rule for rule in rules if rule.handler_id == "auto_send_up_to_n_opponent_battle_to_warp_on_play")
    schedule_rule = next(rule for rule in rules if rule.handler_id == "auto_schedule_play_cards_warped_by_source_skill_on_play")
    assert warp_rule.trigger == "self_played"
    assert warp_rule.handler_params["requires_played_via"] == "counter"
    assert schedule_rule.trigger == "self_played"
    assert schedule_rule.handler_params["requires_played_via"] == "counter"
    assert schedule_rule.handler_params["trigger_kind"] == "turn_end"
    assert schedule_rule.handler_params["trigger_player_scope"] == "current"
    assert schedule_rule.handler_params["require_next_turn"] is False
    assert schedule_rule.handler_params["negate_skills"] is True
    assert schedule_rule.handler_params["max_targets"] == -1


def test_extract_played_card_can_warp_itself_and_opponent_battle_then_replay_both() -> None:
    card = _card(
        "[Auto] When this card is played, choose this card and up to 1 of your opponent's Battle Cards with an energy cost of 3 or less "
        "and send them to their owners' Warps; at the end of the turn, negate the skills of all cards sent to Warps by this skill for the turn "
        "and play them to their owners' Battle Areas. "
        "[Activate: Battle] If you have a yellow <Trunks: Future> card with an energy cost of 3 or more in play: Play this card from your hand, "
        "and you can't play copies of this card for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    warp_rule = next(rule for rule in rules if rule.handler_id == "auto_send_up_to_n_opponent_battle_to_warp_on_play")
    schedule_rule = next(rule for rule in rules if rule.handler_id == "auto_schedule_play_cards_warped_by_source_skill_on_play")
    play_rule = next(rule for rule in rules if rule.trigger == "self_activate_battle" and rule.handler_id == "activate_play_self_from_hand")
    assert warp_rule.trigger == "self_played"
    assert warp_rule.handler_params["max_targets"] == 1
    assert warp_rule.handler_params["max_cost"] == 3
    assert warp_rule.handler_params["send_self_to_warp"] is True
    assert schedule_rule.trigger == "self_played"
    assert schedule_rule.handler_params["affected_player_scope"] == "both"
    assert schedule_rule.handler_params["trigger_kind"] == "turn_end"
    assert schedule_rule.handler_params["trigger_player_scope"] == "current"
    assert schedule_rule.handler_params["require_next_turn"] is False
    assert schedule_rule.handler_params["negate_skills"] is True
    assert schedule_rule.handler_params["max_targets"] == -1
    assert play_rule.trigger == "self_activate_battle"


def test_extract_played_card_can_warp_two_opponent_battles_gain_critical_and_replay_next_opponent_turn() -> None:
    card = _card(
        "[Auto][Limit 1] When this card is played, choose up to 2 of your opponent's Battle Cards, send them to their owners' Warps, "
        "and this card gains [Critical] for the turn. At the end of your opponent's next turn, negate the skills of all cards sent to Warps "
        "by this skill for the turn and play them in their owners' Battle Areas."
    )
    rules = extract_effect_rules_from_card(card)
    warp_rule = next(rule for rule in rules if rule.handler_id == "auto_send_up_to_n_opponent_battle_to_warp_on_play")
    buff_rule = next(rule for rule in rules if rule.handler_id == "auto_self_gain_power_for_turn_on_play")
    schedule_rule = next(rule for rule in rules if rule.handler_id == "auto_schedule_play_cards_warped_by_source_skill_on_play")
    assert warp_rule.trigger == "self_played"
    assert warp_rule.handler_params["max_targets"] == 2
    assert buff_rule.trigger == "self_played"
    assert buff_rule.handler_params["power_delta"] == 0
    assert buff_rule.handler_params["grant_keyword"] == "Critical"
    assert schedule_rule.trigger == "self_played"
    assert schedule_rule.handler_params["affected_player_scope"] == "opponent"
    assert schedule_rule.handler_params["trigger_kind"] == "turn_end"
    assert schedule_rule.handler_params["trigger_player_scope"] == "opponent"
    assert schedule_rule.handler_params["require_next_turn"] is True
    assert schedule_rule.handler_params["negate_skills"] is True
    assert schedule_rule.handler_params["max_targets"] == -1


def test_extract_played_card_can_send_matching_deck_cards_to_warp_then_play_one_and_add_rest_to_hand() -> None:
    card = _card(
        "[Auto][Limit 1] If your Leader is a yellow <Whis> card and you place 1 card from your hand at the bottom of your deck: "
        "When this card is played, send up to 2 skill-less Battle Cards with 15000 power and different character names from your deck to your Warp, "
        "shuffle your deck, and at the end of your opponent's next turn, play up to 1 of the cards sent to your Warp by this skill in your Battle Area, "
        "and you may add the remaining cards to your hand."
    )
    rules = extract_effect_rules_from_card(card)
    warp_rule = next(rule for rule in rules if rule.handler_id == "auto_send_up_to_n_from_owner_deck_to_warp_on_play")
    schedule_rule = next(rule for rule in rules if rule.handler_id == "auto_schedule_play_cards_warped_by_source_skill_on_play")
    assert warp_rule.trigger == "self_played"
    assert warp_rule.handler_params["max_targets"] == 2
    assert warp_rule.handler_params["required_card_type"] == "BATTLE"
    assert warp_rule.handler_params["requires_skill_less"] is True
    assert warp_rule.handler_params["exact_power"] == 15000
    assert warp_rule.handler_params["require_different_character_names"] is True
    assert "required_characters" not in warp_rule.handler_params
    assert schedule_rule.trigger == "self_played"
    assert schedule_rule.handler_params["affected_player_scope"] == "owner"
    assert schedule_rule.handler_params["trigger_kind"] == "turn_end"
    assert schedule_rule.handler_params["trigger_player_scope"] == "opponent"
    assert schedule_rule.handler_params["require_next_turn"] is True
    assert schedule_rule.handler_params["max_targets"] == 1
    assert schedule_rule.handler_params["return_remaining_to_hand"] is True


def test_extract_played_card_can_send_matching_deck_card_to_warp_then_add_it_to_hand_next_turn_if_still_in_play() -> None:
    card = _card(
        "[Auto] When you play this card, choose up to 1 black Battle Card with an energy cost of 5 or less from your deck and send it to your Warp and shuffle your deck. "
        "Then, at the beginning of your next turn, if this card is in play in your Battle Area, add the card that was sent to your Warp by this skill to your hand."
    )
    rules = extract_effect_rules_from_card(card)
    warp_rule = next(rule for rule in rules if rule.handler_id == "auto_send_up_to_n_from_owner_deck_to_warp_on_play")
    return_rule = next(rule for rule in rules if rule.handler_id == "auto_schedule_return_cards_warped_by_source_skill_on_play")
    assert warp_rule.trigger == "self_played"
    assert warp_rule.handler_params["max_targets"] == 1
    assert warp_rule.handler_params["allowed_colors"] == "black"
    assert warp_rule.handler_params["required_card_type"] == "BATTLE"
    assert warp_rule.handler_params["max_cost"] == 5
    assert return_rule.trigger == "self_played"
    assert return_rule.handler_params["affected_player_scope"] == "owner"
    assert return_rule.handler_params["trigger_kind"] == "main_phase_start"
    assert return_rule.handler_params["trigger_player_scope"] == "owner"
    assert return_rule.handler_params["require_next_turn"] is True
    assert return_rule.handler_params["require_source_in_play"] is True
    assert return_rule.handler_params["required_source_zone"] == "battle"


def test_extract_played_card_can_send_matching_deck_card_to_warp_then_add_it_to_hand_next_turn() -> None:
    card = _card(
        "[Auto] When you play this card, choose up to 1 ≪World Tournament≫ card with an energy cost of 5 or less from your deck, "
        "send it your Warp, shuffle your deck, and at the start of your next turn, add that card sent to your Warp by this skill to your hand from the Warp."
    )
    rules = extract_effect_rules_from_card(card)
    warp_rule = next(rule for rule in rules if rule.handler_id == "auto_send_up_to_n_from_owner_deck_to_warp_on_play")
    return_rule = next(rule for rule in rules if rule.handler_id == "auto_schedule_return_cards_warped_by_source_skill_on_play")
    assert warp_rule.trigger == "self_played"
    assert warp_rule.handler_params["max_targets"] == 1
    assert warp_rule.handler_params["required_traits"] == "World Tournament"
    assert warp_rule.handler_params["max_cost"] == 5
    assert return_rule.trigger == "self_played"
    assert return_rule.handler_params["affected_player_scope"] == "owner"
    assert return_rule.handler_params["trigger_kind"] == "main_phase_start"
    assert return_rule.handler_params["trigger_player_scope"] == "owner"
    assert return_rule.handler_params["require_next_turn"] is True
    assert "require_source_in_play" not in return_rule.handler_params


def test_extract_activate_main_can_send_matching_hand_card_to_warp_then_play_it_next_turn() -> None:
    card = _card(
        "[Activate: Main]②, if your Leader Card is a ≪World Tournament≫ card and you place this card in it's owner's Drop Area: "
        "Choose up to 1 ≪World Tournament≫ card with an energy cost of 3 or less from your hand, send it to your Warp, "
        "and at the start of your next turn, play the card sent to your Warp by this skill from your Warp."
    )
    rules = extract_effect_rules_from_card(card)
    warp_rule = next(rule for rule in rules if rule.handler_id == "activate_send_up_to_n_from_owner_hand_to_warp")
    schedule_rule = next(rule for rule in rules if rule.handler_id == "activate_schedule_play_cards_warped_by_source_skill")
    assert warp_rule.trigger == "self_activate_main"
    assert warp_rule.handler_params["max_targets"] == 1
    assert warp_rule.handler_params["required_traits"] == "World Tournament"
    assert warp_rule.handler_params["max_cost"] == 3
    assert schedule_rule.trigger == "self_activate_main"
    assert schedule_rule.handler_params["affected_player_scope"] == "owner"
    assert schedule_rule.handler_params["trigger_kind"] == "main_phase_start"
    assert schedule_rule.handler_params["trigger_player_scope"] == "owner"
    assert schedule_rule.handler_params["require_next_turn"] is True


def test_extract_played_card_can_send_named_deck_card_to_warp_then_play_it_next_turn_in_rest_mode() -> None:
    card = _card(
        "[Auto][Limit 1] If your Leader is a yellow non-≪Great Ape≫ <Son Goku: Childhood> card: "
        "When this card is played, send up to 1 yellow {Bora} from your deck to your Warp, shuffle your deck, "
        "and at the start of your next turn, play that card from your Warp in Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    warp_rule = next(rule for rule in rules if rule.handler_id == "auto_send_up_to_n_from_owner_deck_to_warp_on_play")
    schedule_rule = next(rule for rule in rules if rule.handler_id == "auto_schedule_play_cards_warped_by_source_skill_on_play")
    assert warp_rule.trigger == "self_played"
    assert warp_rule.handler_params["max_targets"] == 1
    assert warp_rule.handler_params["allowed_colors"] == "yellow"
    assert warp_rule.handler_params["required_name_contains"] == "BORA"
    assert schedule_rule.trigger == "self_played"
    assert schedule_rule.handler_params["affected_player_scope"] == "owner"
    assert schedule_rule.handler_params["trigger_kind"] == "main_phase_start"
    assert schedule_rule.handler_params["trigger_player_scope"] == "owner"
    assert schedule_rule.handler_params["require_next_turn"] is True
    assert schedule_rule.handler_params["max_targets"] == 1
    assert schedule_rule.handler_params["resting"] is True


def test_extract_activate_main_can_send_self_to_warp_and_play_it_next_turn_without_colon_cost() -> None:
    card = _card(
        "[Activate: Main] Place 1 card from your hand in the Drop Area: "
        "Send this card to the Warp, and play it from the Warp in its owner's Battle Area at the beginning of your next turn."
    )
    rules = extract_effect_rules_from_card(card)
    schedule_rule = next(rule for rule in rules if rule.handler_id == "activate_schedule_play_cards_warped_by_source_skill")
    assert schedule_rule.trigger == "self_activate_main"
    assert schedule_rule.handler_params["affected_player_scope"] == "owner"
    assert schedule_rule.handler_params["mark_source_in_owner_warp"] is True
    assert schedule_rule.handler_params["trigger_kind"] == "main_phase_start"
    assert schedule_rule.handler_params["trigger_player_scope"] == "owner"


def test_extract_activate_main_can_send_self_from_hand_to_warp_then_play_it_on_opponent_next_turn_end() -> None:
    card = _card(
        "[Activate: Main] (Green), send this card from your hand to your Warp: "
        "At the end of your opponent's next turn, play the card you sent to your Warp with this skill from your Warp. "
        "[Auto] When you play this card, choose up to 2 cards in your life and add them to your hand."
    )
    rules = extract_effect_rules_from_card(card)
    schedule_rule = next(rule for rule in rules if rule.handler_id == "activate_schedule_play_cards_warped_by_source_skill")
    life_rule = next(rule for rule in rules if rule.handler_id == "auto_add_up_to_n_from_owner_life_to_hand_on_play")
    assert schedule_rule.trigger == "self_activate_main"
    assert schedule_rule.handler_params["affected_player_scope"] == "owner"
    assert schedule_rule.handler_params["mark_source_in_owner_warp"] is True
    assert schedule_rule.handler_params["trigger_kind"] == "turn_end"
    assert schedule_rule.handler_params["trigger_player_scope"] == "opponent"
    assert schedule_rule.handler_params["require_next_turn"] is True
    assert life_rule.trigger == "self_played"
    assert life_rule.handler_params["max_targets"] == 2


def test_extract_activate_main_can_warp_opponent_battle_then_replay_it_next_opponent_turn() -> None:
    card = _card(
        "[Activate: Main] Choose up to 1 of your opponent's Battle Cards and send it to its owner's Warp; "
        "at the end of your opponent's next turn, play the card sent to their Warp with this skill to their Battle Area with its skills negated for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    warp_rule = next(rule for rule in rules if rule.handler_id == "activate_send_up_to_n_opponent_battle_to_warp")
    schedule_rule = next(rule for rule in rules if rule.handler_id == "activate_schedule_play_cards_warped_by_source_skill")
    assert warp_rule.trigger == "self_activate_main"
    assert warp_rule.handler_params["max_targets"] == 1
    assert schedule_rule.trigger == "self_activate_main"
    assert schedule_rule.handler_params["affected_player_scope"] == "opponent"
    assert schedule_rule.handler_params["trigger_kind"] == "turn_end"
    assert schedule_rule.handler_params["trigger_player_scope"] == "opponent"
    assert schedule_rule.handler_params["negate_skills"] is True


def test_extract_attack_can_send_under_self_to_warp_then_play_one_and_add_one_to_z_energy_next_turn() -> None:
    card = _card(
        "[Blocker][Auto] Send 2 cards from under this card to your Warp: When this card attacks, your opponent discards 1 card from their hand, "
        "and at the start of your next turn, you choose up to 1 each of <Android 17> and <Hell Fighter 17> cards with an energy cost of 1 from your Warp, "
        "then play up to 1 of them and add up to 1 of them to your Z-Energy."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.handler_id == "auto_opponent_discards_n_and_schedule_play_and_add_marked_warped_cards_on_attack"
    )
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["auto_release_under_to_warp_before"] == 2
    assert rule.handler_params["trigger_kind"] == "main_phase_start"
    assert rule.handler_params["trigger_player_scope"] == "owner"
    assert rule.handler_params["affected_player_scope"] == "owner"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["add_to_z_energy_max_targets"] == 1
    assert rule.handler_params["first_required_characters"] == "Android 17"
    assert rule.handler_params["second_required_characters"] == "Hell Fighter 17"
    assert rule.handler_params["min_cost"] == 1
    assert rule.handler_params["max_cost"] == 1


def test_extract_counter_attack_can_warp_one_each_from_both_battle_areas_and_replay_all() -> None:
    card = _card(
        "[Counter: Attack] If your Leader is a green ≪Earthling≫ card: Draw 1 card, then choose up to 1 each of ≪Saiyan≫ and ≪Earthling≫ cards "
        "from among all the cards in you and your opponent's Battle Areas and send them to their owners' Warps. "
        "At the end of the turn, play all the cards sent to their owners' Warps by this skill into their owners' Battle Areas wit their skills negated for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    warp_rule = next(
        rule for rule in rules if rule.handler_id == "counter_draw_n_and_send_up_to_one_each_matching_from_all_battles_to_warp"
    )
    schedule_rule = next(rule for rule in rules if rule.handler_id == "counter_schedule_play_cards_warped_by_source_skill")
    assert warp_rule.trigger == "counter_attack"
    assert warp_rule.handler_params["amount"] == 1
    assert warp_rule.handler_params["first_required_traits"] == "Saiyan"
    assert warp_rule.handler_params["second_required_traits"] == "Earthling"
    assert schedule_rule.trigger == "counter_attack"
    assert schedule_rule.handler_params["affected_player_scope"] == "both"
    assert schedule_rule.handler_params["negate_skills"] is True
    assert schedule_rule.handler_params["max_targets"] == -1
    assert schedule_rule.handler_params["require_next_turn"] is False


def test_extract_kahseral_activate_battle_switch_owner_battle_active_rule() -> None:
    card = _card(
        "[Deflect][Blocker] "
        "[Activate: Battle][Once per turn] If your Leader Card is a red ≪Universe 11≫ card: "
        "Choose up to 2 of your red ≪Universe 11≫ cards with energy costs of 1 and 10000 power or less in your Battle Area and switch them to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(rule for rule in rules if rule.handler_id == "activate_switch_up_to_n_owner_battle_active")
    assert rule.trigger == "self_activate_battle"
    assert rule.once_per_turn is True
    assert rule.handler_params["max_targets"] == 2
    assert rule.handler_params["max_cost"] == 1
    assert rule.handler_params["max_power"] == 10000
    assert rule.handler_params["allowed_colors"] == "red"
    assert rule.handler_params["required_traits"] == "Universe 11"


def test_extract_lightning_shower_rain_activate_main_battle_switch_owner_janemba_active_rule() -> None:
    card = _card(
        "[Activate: Main/Battle][Limit 1] If your Leader is a <Janemba> card, "
        "you have a blue <Janemba> card with an energy cost of 6 or more in play, and you remove this card from the game: "
        "Place up to 1 {Demonic Blade} or {Dimensional Hole} from your Z-Deck in the Battle Area, "
        "then choose up to 1 of your blue <Janemba> Battle Cards and switch it to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    switch_rules = [r for r in rules if r.handler_id == "activate_switch_up_to_n_owner_battle_active"]
    assert {rule.trigger for rule in switch_rules} == {"self_activate_main", "self_activate_battle"}
    rule = switch_rules[0]
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "blue"
    assert rule.handler_params["required_characters"] == "Janemba"
    assert rule.handler_params["required_leader_traits"] == "Janemba"
    assert rule.handler_params["required_owner_battle_min_cost"] == 6


def test_extract_attack_discard_hand_then_switch_owner_android_active_rule() -> None:
    card = _card(
        "[Auto] [Once per turn] When this card attacks, you may place 1 card from your hand in the Drop Area. "
        "If you do so, choose up to 1 &lt;Android 17&gt; in your Battle Area and switch it to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_discard_n_then_switch_up_to_n_owner_battle_active_on_attack")
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["auto_discard_hand_before"] == 1
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_characters"] == "Android 17"


def test_extract_mira_dimensional_superpower_activate_families() -> None:
    card = replace(_card(
        "[Permanent] This card can't attack if it has 2 or fewer markers on it. "
        "[+1][Activate: Main] You may choose 1 card in your hand and send it to your Warp. If you do, draw 1 card. "
        "[-2][Activate: Battle] For each card in your Warp, this card gets +5000 power for the battle."
    ), card_type="UNISON")
    rules = extract_effect_rules_from_card(card)
    activate_main = next(r for r in rules if r.handler_id == "activate_optional_send_owner_hand_to_warp_draw_n")
    assert activate_main.trigger == "self_activate_main"
    assert activate_main.handler_params["hand_to_warp"] == 1
    assert activate_main.handler_params["amount"] == 1
    assert activate_main.handler_params["marker_delta"] == 1

    activate_battle = next(r for r in rules if r.trigger == "self_activate_battle" and r.handler_id == "activate_gain_power_and_keyword_for_battle")
    assert activate_battle.handler_params["power_delta"] == "expr:owner_warp_count*5000"


def test_extract_son_goten_attack_draw_still_matches_attack_draw() -> None:
    card = replace(_card(
        "[Auto] When this card attacks, draw 1 card. "
        "[Awaken] When your life is at 4 or less: Draw 1 card and flip this card over."
    ), card_type="LEADER")
    rules = extract_effect_rules_from_card(card)
    draw = next(r for r in rules if r.trigger == "self_attacks" and r.handler_id == "auto_draw_n")
    assert draw.handler_params["amount"] == 1


def test_extract_activate_main_look_top_send_matching_to_owner_warp_rule() -> None:
    card = replace(
        _card(
            "[Activate: Main][Once per turn] Look at up to 7 cards from the top of your deck, "
            "send up to 1 black card to its owner's Warp, then shuffle your deck."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_look_top_send_up_to_n_to_owner_warp")
    assert rule.handler_params["look_count"] == 7
    assert rule.handler_params["max_send"] == 1
    assert rule.handler_params["allowed_colors"] == "black"
    assert rule.once_per_turn is True


def test_extract_unison_plus_activate_main_send_top_deck_to_owner_warp_and_switch_active() -> None:
    card = replace(
        _card(
            "[UNISON +1][Activate: Main] Send up to 2 cards from the top of your deck to their owner's Warp and switch this card to Active Mode."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_send_top_deck_to_owner_warp")
    assert rule.handler_params["send_count"] == 2
    assert rule.handler_params["switch_self_active"] is True
    assert rule.handler_params["marker_delta"] == 1


def test_extract_owner_opponent_battle_attack_play_self_from_drop_or_warp_negate_rule() -> None:
    card = _card(
        "[Auto][Limit 1] If your Leader is black or a <<Master's Teachings>> card, your life is at 4 or less, "
        "and you add 1 card from your life to your hand and place 1 card from your hand at the bottom of your deck: "
        "When your opponent attacks with a Battle Card, you may play this card from your Drop or Warp in Rest Mode and negate the attack."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_opponent_battle_attacks"
        and r.handler_id == "auto_pay_life_bottom_deck_play_self_from_drop_or_warp_negate_attack"
    )
    assert rule.limit_per_turn == 1
    assert rule.handler_params["life_to_hand"] == 1
    assert rule.handler_params["bottom_deck_from_hand"] == 1
    assert rule.handler_params["max_owner_life"] == 4
    assert rule.handler_params["resting"] is True
    assert rule.handler_params["negate_attack"] is True


def test_extract_unison_minus_activate_main_send_opponent_drop_battle_to_warp_rule() -> None:
    card = replace(
        _card(
            "[-3][Activate: Main] Send up to 2 Battle Cards from your opponent's Drop Area to their Warp."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_send_up_to_n_opponent_drop_battle_to_warp"
    )
    assert rule.handler_params["max_targets"] == 2
    assert rule.handler_params["marker_delta"] == -3


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


def test_extract_activate_main_can_send_self_to_warp_play_black_multicolor_from_hand_and_return_self_next_turn() -> None:
    card = _card(
        "[Energy-Exhaust]<br>[Activate: Main](Black), send this card to its owner's Warp: "
        "Choose up to 1 black multicolor Battle Card with an energy cost of 2 in your hand and play it. "
        "At the start of your next turn, add this card to your hand from your Warp."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(r for r in rules if r.handler_id == "activate_play_up_to_n_from_owner_hand")
    return_rule = next(r for r in rules if r.handler_id == "activate_schedule_return_cards_warped_by_source_skill_to_owner_hand")
    assert play_rule.trigger == "self_activate_main"
    assert play_rule.handler_params["max_targets"] == 1
    assert play_rule.handler_params["allowed_colors"] == "black"
    assert play_rule.handler_params["required_card_type"] == "BATTLE"
    assert play_rule.handler_params["requires_multicolor"] is True
    assert play_rule.handler_params["allowed_costs"] == "2"
    assert return_rule.trigger == "self_activate_main"
    assert return_rule.handler_params["mark_source_in_owner_warp"] is True
    assert return_rule.handler_params["trigger_kind"] == "main_phase_start"
    assert return_rule.handler_params["trigger_player_scope"] == "owner"
    assert return_rule.handler_params["require_next_turn"] is True


def test_extract_combo_battle_end_can_play_self_then_negate_opponent_unison_for_turn_with_total_energy_gate() -> None:
    card = _card(
        "[Energy-Exhaust]<br>[Auto](Black), if your Leader Card is a black ≪Saiyan≫ card and there's a total of 3 or more energy between you and your opponent: "
        "At the end of a battle in which this card was used in a combo from your hand, play this card from your Drop Area in Rest Mode, "
        "then choose up to 1 of your opponent's Unison Cards and negate its skills for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_self_from_combo_on_battle_end_then_negate_up_to_n_opponent_unisons_for_turn")
    assert rule.trigger == "self_comboed_battle_end"
    assert rule.handler_params["resting"] is True
    assert rule.handler_params["requires_comboed_from"] == "hand"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["min_total_players_energy"] == 3


def test_extract_combo_battle_end_can_play_self_then_return_opponent_battle_to_hand_with_total_energy_gate() -> None:
    card = _card(
        "[Energy-Exhaust]<br>[Auto](Black), if your Leader Card is a black ≪Saiyan≫ card and there's a total of 3 or more energy between you and your opponent: "
        "At the end of a battle in which this card was used in a combo from your hand, play this card from your Drop Area in Rest Mode, "
        "then choose up to 1 of your opponent's Battle Cards with an energy cost of 3 or less and return it to its owner's hand."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_self_from_combo_on_battle_end_then_return_up_to_n_opponent_battle_to_hand")
    assert rule.trigger == "self_comboed_battle_end"
    assert rule.handler_params["resting"] is True
    assert rule.handler_params["requires_comboed_from"] == "hand"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_cost"] == 3
    assert rule.handler_params["min_total_players_energy"] == 3


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


def test_extract_activate_main_opponent_discards_n_from_hand_rule() -> None:
    card = replace(_card("[+1][Activate: Main] Your opponent discards 1 card their hand."), card_type="UNISON")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_opponent_discards_n_from_hand")
    assert rule.handler_params["amount"] == 1


def test_extract_activate_main_place_from_under_named_host_into_drop_then_opponent_discards_same_count_rule() -> None:
    card = replace(
        _card(
            "[Activate: Main](G)(G)(G): Choose one?? "
            "Place up to 3 cards from under a {The Nameless Planet} in your Battle Area in their owners' Drop Areas; "
            "your opponent discards cards equal to the number of cards you placed in Drop Areas this way."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_main"
        and r.handler_id == "activate_place_up_to_n_from_under_named_owner_battle_into_drop_then_opponent_discards_same_count"
    )
    assert rule.handler_params["max_targets"] == 3
    assert rule.handler_params["required_host_name_contains"] == "THE NAMELESS PLANET"


def test_extract_activate_battle_draw_rule() -> None:
    card = _card("[Activate: Battle] If your leader is red: Draw 1 card.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_battle" and r.handler_id == "auto_draw_n")
    assert rule.handler_params["amount"] == 1


def test_extract_combo_can_reduce_opponent_battle_power_rule() -> None:
    card = _card(
        "[Super Combo][Auto] If your Leader Card is red or yellow: "
        "When you combo with this card from your hand, choose up to 1 of your opponent's Battle Cards and it gets -10000 power for the duration of the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_comboed" and r.handler_id == "auto_power_reduce_up_to_n_on_combo")
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["power_delta"] == -10000
    assert rule.handler_params["requires_comboed_from"] == "hand"
    assert rule.handler_params["requires_leader"] == "if your leader card is red or yellow"


def test_extract_play_self_gain_power_for_turn_with_opponent_drop_requirement_rule() -> None:
    card = _card("[Auto][Limit 1] If your opponent has 20 or more cards in their Drop: When this card is played, it gets +15000 power for the turn.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "auto_self_gain_power_for_turn_on_play")
    assert rule.handler_params["power_delta"] == 15000
    assert rule.handler_params["min_opponent_drop"] == 20
    assert rule.limit_per_turn == 1


def test_extract_activate_main_can_play_from_owner_z_deck_or_z_energy_rule() -> None:
    card = replace(
        _card(
            "[0] [Activate: Main] If your Leader is {Fused Zamasu, Insanity From Justice}: "
            "Play up to 1 <Zamasu> or <Goku Black> card -- both green and with an energy cost of 1 -- "
            "from your Z-Deck or Z-Energy with its skills negated for the game."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_play_up_to_n_from_owner_z_deck_or_z_energy")
    assert rule.handler_params["source_pool"] == "z_deck_or_z_energy"
    assert rule.handler_params["negate_skills"] is True
    assert rule.handler_params["max_targets"] == 1
    assert "zamasu" in str(rule.handler_params.get("required_characters", "")).lower()
    assert "goku black" in str(rule.handler_params.get("required_characters", "")).lower()


def test_extract_activate_main_self_gain_multiple_keywords_for_turn_rule() -> None:
    card = _card("[Activate: Main][Once per turn] This card gains [Critical] and [Double Strike] for the turn.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_gain_power_and_keyword_for_turn")
    assert rule.handler_params["grant_keywords"] == "Critical,Double Strike"


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


def test_extract_supreme_kai_of_time_opposing_the_empire_rules() -> None:
    card = _card(
        "[Auto][Once per turn] If your Leader Card is a black <Trunks: Xeno> card and it's your turn: "
        "When a Battle Card is played from your Warp, draw 1 card, and add a marker to this card.\n"
        "[+1][Activate: Main] If your Leader Card is a black ≪Saiyan≫ card: Send up to 3 cards from the top of your deck to your Warp."
    )
    card = replace(card, card_type="UNISON")
    rules = extract_effect_rules_from_card(card)
    auto_rule = next(
        r
        for r in rules
        if r.trigger == "owner_battle_played_from_warp"
        and r.handler_id == "auto_draw_n_and_add_markers_on_owner_battle_played_from_warp"
    )
    assert auto_rule.handler_params["amount"] == 1
    assert auto_rule.handler_params["marker_delta"] == 1
    assert "<trunks: xeno>" in str(auto_rule.handler_params["requires_leader"]).lower()
    assert "it's your turn" in str(auto_rule.handler_params["requires_leader"]).lower()
    activate_rule = next(r for r in rules if r.trigger == "self_activate_main" and r.handler_id == "activate_send_top_deck_to_owner_warp")
    assert activate_rule.handler_params["send_count"] == 3
    assert activate_rule.handler_params["marker_delta"] == 1
    assert "saiyan" in str(activate_rule.handler_params["requires_leader"]).lower()


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


def test_extract_owner_other_battle_played_by_dark_over_realm_draw_rule() -> None:
    card = _card(
        "[Auto][Limit 1] When your Battle Card other than this card is played by a [Dark Over Realm] skill, draw 1 card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_draw_n")
    assert rule.trigger == "owner_other_battle_played_by_dark_over_realm"
    assert rule.handler_params["amount"] == 1
    assert rule.limit_per_turn == 1


def test_extract_hand_to_drop_by_opponent_skill_or_revive_can_play_self_rule() -> None:
    card = _card(
        "[Blocker][Energy-Exhaust][Auto] When this card is placed in your Drop Area from your hand by an opponent's skill or by your [Revive] skill, you may play this card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_self_from_drop_on_hand_drop")
    assert rule.trigger == "self_in_hand_sent_to_drop_or_warp"
    assert rule.handler_params["required_destination_zone"] == "drop"
    assert rule.handler_params["required_drop_causes"] == "opponent_skill,revive"


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


def test_extract_activate_battle_owner_leader_gain_power_and_keyword_for_battle_rule() -> None:
    card = replace(
        _card(
            "[Activate: Battle] If your Leader Card is a black ≪Saiyan≫ card, it gets +15000 power and [Double Strike] for the duration of the battle."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_gain_power_and_keyword_for_battle")
    assert rule.trigger == "self_activate_extra_from_hand"
    assert rule.handler_params["power_delta"] == 15000
    assert rule.handler_params["grant_keyword"] == "Double Strike"
    assert rule.handler_params["target_scope"] == "owner_leader"
    assert "black" in str(rule.handler_params["requires_leader"]).lower()
    assert "saiyan" in str(rule.handler_params["required_leader_traits"]).lower()


def test_extract_activate_battle_under_leader_can_buff_owner_leader_for_battle() -> None:
    card = _card(
        "[Activate: Battle][Limit 1] Send this card from under your <Super 17> Z-Leader to its owner's Warp: "
        "Up to 1 of your Leaders gets +5000 power for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_gain_power_and_keyword_for_battle")
    assert rule.trigger == "self_activate_battle"
    assert rule.handler_params["target_scope"] == "owner_leader"
    assert rule.handler_params["power_delta"] == 5000
    assert rule.handler_params["required_source_zone"] == "leader_under"
    assert rule.handler_params["under_host_required_characters"] == "super 17"


def test_extract_activate_battle_under_leader_can_grant_owner_leader_keyword_for_battle() -> None:
    card = _card(
        "[Activate: Battle][Limit 1](Green), send this card from under your <Super 17> Z-Leader to its owner's Warp: "
        "Your Leader gains [Double Strike] for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_gain_power_and_keyword_for_battle")
    assert rule.trigger == "self_activate_battle"
    assert rule.handler_params["target_scope"] == "owner_leader"
    assert rule.handler_params["grant_keyword"] == "Double Strike"
    assert rule.handler_params["required_source_zone"] == "leader_under"
    assert rule.handler_params["under_host_required_characters"] == "super 17"


def test_extract_activate_battle_choose_owner_cards_gain_power_for_battle_rule() -> None:
    card = _card(
        "[Activate: Battle][Once per turn] Place 1 of your energy into its owner's Drop: "
        "Choose up to 1 of your blue â‰ªAndroidâ‰« cards and it gets +10000 power for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_gain_power_and_keyword_for_battle")
    assert rule.trigger == "self_activate_battle"
    assert rule.handler_params["target_scope"] == "owner_cards"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["power_delta"] == 10000
    assert rule.handler_params["allowed_colors"] == "blue"
    assert rule.handler_params["required_traits"] == "Android"


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


def test_extract_activate_battle_draw_play_self_and_gain_keyword_until_opponent_turn_end_rule() -> None:
    card = _card(
        "[Activate: Battle][Limit 1](1), if your opponent has 3 or more energy and you have 1 or more <Android 17> card and 1 or more <Hell Fighter 17> card in your Combo Area: "
        "Draw 1 card, play this card from your hand, and this card gains [Barrier] until the end fo your opponent's turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "activate_draw_n_play_self_from_hand_and_gain_keyword_until_opponent_turn_end"
    )
    assert rule.trigger == "self_activate_battle"
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["grant_keyword"] == "Barrier"
    assert rule.handler_params["min_opponent_energy"] == 3
    assert rule.handler_params["required_owner_combo_required_characters_each"] == "Android 17|Hell Fighter 17"


def test_extract_activate_battle_draw_switch_self_active_and_power_reduce_rule() -> None:
    card = _card(
        "[Activate: Battle][Once per turn] (1), place 1 ≪Android≫ card from your Z-Energy under this card: "
        "Draw 1 card, switch this card to Active Mode, then choose up to 1 of your opponent's Battle Cards and it gets -20000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "activate_switch_self_active_and_power_reduce_up_to_n_opponent_battle_for_turn"
    )
    assert rule.trigger == "self_activate_battle"
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["power_delta"] == -20000


def test_extract_activate_main_choose_all_owner_battle_gain_keyword_until_opponent_turn_end_rule() -> None:
    card = replace(
        _card(
            "[Activate: Main] Choose all red ≪Saiyan≫ cards in your Battle Area. "
            "They gain [Barrier] until the end of your opponent's next turn."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_buff_owner_battle_cards")
    assert rule.trigger == "self_activate_extra_from_hand"
    assert rule.handler_params["target_policy"] == "all"
    assert rule.handler_params["target_scope"] == "owner_battle"
    assert rule.handler_params["grant_keyword"] == "Barrier"
    assert rule.handler_params["keyword_duration"] == "opponent_turn"
    assert rule.handler_params["allowed_colors"] == "red"
    assert rule.handler_params["required_traits"] == "Saiyan"


def test_extract_activate_main_battle_choose_owner_cards_gain_power_for_turn_rule() -> None:
    card = _card(
        "[Activate: Main/Battle][Once per turn] Place 1 of your energy into its owner's Drop: "
        "Choose up to 1 of your blue ≪Red Ribbon Army≫ cards and it gets +5000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    matching = [r for r in rules if r.handler_id == "activate_buff_owner_battle_cards"]
    assert {r.trigger for r in matching} == {"self_activate_main", "self_activate_battle"}
    assert all(r.handler_params["target_scope"] == "owner_cards" for r in matching)
    assert all(r.handler_params["max_targets"] == 1 for r in matching)
    assert all(r.handler_params["power_delta"] == 5000 for r in matching)
    assert all(r.handler_params["allowed_colors"] == "blue" for r in matching)
    assert all(r.handler_params["required_traits"] == "Red Ribbon Army" for r in matching)


def test_extract_activate_main_can_play_self_with_markers_from_hand_or_warp_rule() -> None:
    card = replace(
        _card(
            "[Activate: Main]{b}{b}, if your opponent has 3 or more energy : "
            "Play this card with 2 markers on it from your hand or Warp."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    hand_rule = next(
        r
        for r in rules
        if r.handler_id == "activate_play_self_from_hand" and r.handler_params.get("required_source_zone") == "hand"
    )
    warp_rule = next(
        r
        for r in rules
        if r.handler_id == "activate_play_self_from_warp" and r.handler_params.get("required_source_zone") == "warp"
    )
    assert hand_rule.trigger == "self_activate_main"
    assert warp_rule.trigger == "self_activate_main"
    assert hand_rule.handler_params["markers"] == 2
    assert warp_rule.handler_params["markers"] == 2
    assert hand_rule.handler_params["min_opponent_energy"] == 3


def test_extract_activate_battle_can_play_self_from_hand_then_opponent_discards_rule() -> None:
    card = _card(
        "[Activate: Battle][Limit 1]{u}, if your Leader is {Gamma 1 & Gamma 2, Justice} and your opponent has 2 or more energy: "
        "Play this card from your hand, then your opponent discards 1 card from their hand."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.trigger == "self_activate_battle" and r.handler_id == "activate_play_self_from_hand")
    assert rule.handler_params["opponent_discards_after_play"] == 1
    assert rule.handler_params["min_opponent_energy"] == 2


def test_extract_play_can_buff_owner_battles_with_min_character_count_until_opponent_turn_end_rule() -> None:
    card = _card(
        "[Auto] When this card is played, choose up to 2 of your Battle Cards with 2 or more character names including <SH> and they gain [Barrier] until the end of your opponent's turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_buff_up_to_n_owner_battles_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 2
    assert rule.handler_params["min_character_count"] == 2
    assert rule.handler_params["required_characters"] == "Sh"
    assert rule.handler_params["grant_keyword"] == "Barrier"
    assert rule.handler_params["keyword_duration"] == "opponent_turn"


def test_extract_attack_can_ko_up_to_n_opponent_battle_rule() -> None:
    card = _card(
        "[Auto][Once per turn] When this card attacks, choose up to 1 of your opponent's Battle Cards and KO it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_ko_up_to_n_opponent_battle_on_attack")
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["max_targets"] == 1
    assert rule.once_per_turn is True


def test_extract_attack_can_ko_up_to_n_opponent_battle_rule_with_under_cost() -> None:
    card = _card(
        "[Auto][Limit 1] Place 1 card from under this card in its owner's Drop: "
        "When this card attacks, choose up to 1 of your opponent's Battle Cards and KO it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_ko_up_to_n_opponent_battle_on_attack")
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["auto_release_under_to_drop_before"] == 1


def test_extract_self_ko_can_play_up_to_n_named_from_owner_drop_rule() -> None:
    card = _card(
        "[Auto] When this card is removed from a Battle Area by an opponent's skill or KO'd, play up to 1 {Negative Energy Four-Star Ball} from your Drop."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_named_from_owner_drop_on_self_ko")
    assert rule.trigger == "self_koed"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_name_contains"] == "NEGATIVE ENERGY FOUR-STAR BALL"


def test_extract_self_left_battle_choose_play_hirudegarn_or_draw_rule() -> None:
    card = _card(
        "[Auto] When this card is removed from your Battle Area by an opponent's skill or KO'd, choose one-<br>"
        "・ Choose up to 1 &lt;Hirudegarn&gt; card with an energy cost of 3 from your deck or hand, play it, then shuffle your deck if you looked through it.<br>"
        "・ Draw 1 card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r for r in rules
        if r.trigger == "self_left_battle_area"
        and r.handler_id == "auto_choose_play_up_to_n_from_owner_deck_or_hand_or_secondary_on_self_left_battle"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_characters"] == "Hirudegarn"
    assert rule.handler_params["min_cost"] == 3
    assert rule.handler_params["max_cost"] == 3
    assert rule.handler_params["secondary_mode"] == "draw"
    assert rule.handler_params["secondary_amount"] == 1


def test_extract_self_left_battle_choose_play_hirudegarn_or_opponent_discard_rule() -> None:
    card = _card(
        "[Auto] When this card is removed from your Battle Area by an opponent's skill or KO'd, choose one-<br>"
        "・ Choose up to 1 &lt;Hirudegarn&gt; card with an energy cost of 4 from your deck or hand, play it, then shuffle your deck if you looked through it.<br>"
        "・ Your opponent chooses 1 card in their hand and discards it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r for r in rules
        if r.trigger == "self_left_battle_area"
        and r.handler_id == "auto_choose_play_up_to_n_from_owner_deck_or_hand_or_secondary_on_self_left_battle"
    )
    assert rule.handler_params["required_characters"] == "Hirudegarn"
    assert rule.handler_params["min_cost"] == 4
    assert rule.handler_params["max_cost"] == 4
    assert rule.handler_params["secondary_mode"] == "opponent_discard"
    assert rule.handler_params["secondary_amount"] == 1


def test_extract_on_play_switch_up_to_n_opponent_battle_rest_rule() -> None:
    card = _card(
        "[Auto] When you play this card, choose up to 1 of your opponent's Battle Cards with an energy cost of 4 or less and switch it to Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_switch_up_to_n_opponent_battle_rest_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_cost"] == 4


def test_extract_activate_main_battle_can_play_self_from_hand_rule() -> None:
    card = _card(
        "[Activate: Main/Battle][Limit 1]{1}, if your Leader is a card with <SH> in its character name and you or your opponent has 3 or more energy: Play this card from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    matching = [r for r in rules if r.handler_id == "activate_play_self_from_hand"]
    assert {r.trigger for r in matching} == {"self_activate_main", "self_activate_battle"}
    assert all(r.limit_per_turn == 1 for r in matching)
    assert all(r.handler_params["min_any_player_energy"] == 3 for r in matching)


def test_extract_activate_battle_switch_self_active_and_gain_power_for_turn_rule() -> None:
    card = replace(
        _card("[UNISON +1][Activate: Battle] Switch this card to Active Mode and it gets +15000 power for the turn."),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_switch_self_active_and_gain_power_for_turn")
    assert rule.trigger == "self_activate_battle"
    assert rule.handler_params["power_delta"] == 15000


def test_extract_play_gain_control_opponent_unison_rule() -> None:
    card = _card("[Auto] When this card is played from your hand, choose 1 of your opponent's Unison Cards and gain control of it.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_gain_control_opponent_unison_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1


def test_extract_play_gain_control_opponent_battle_rule() -> None:
    card = _card(
        "[Auto] When you play this card, choose up to 1 of the Battle Cards in your opponent's Battle Area with an energy cost of 3 or less and gain control of it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_gain_control_opponent_battle_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_cost"] == 3


def test_extract_raditz_invitation_to_battle_from_badge_html() -> None:
    card = _card(
        "<Badge variant=\"red\">Barrier</Badge><Badge variant=\"red\">Blocker</Badge><br />"
        "<Badge variant=\"purple\">Permanent</Badge> If your opponent has a ≪Saiyan≫ card in play in their Battle Area, reduce the energy cost of this card in your hand by 1.<br />"
        "<Badge variant=\"blue\">Auto</Badge> When this card is played from your hand, choose up to 1 ≪Saiyan≫ card with 5000 power or less in your opponent's Battle Area and gain control of it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_gain_control_opponent_battle_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_power"] == 5000
    assert rule.handler_params["required_traits"] == "Saiyan"


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
    assert rule.handler_params["required_leader_traits"] == "God"


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


def test_extract_attack_draw_rule_can_release_under_cards_to_drop_before() -> None:
    card = _card("[Auto][Limit 1] Place 1 card from under this card in its owner's Drop: When this card attacks, draw 1 card.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_draw_n")
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["auto_release_under_to_drop_before"] == 1


def test_extract_attack_power_reduce_rule_can_release_under_cards_to_drop_before() -> None:
    card = _card(
        "[Auto][Limit 1] Place 1 card from under this card in its owner's Drop: "
        "When this card attacks, choose up to 1 of your opponent's Battle Cards and it gets -30000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_power_reduce_up_to_n_on_attack")
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["power_delta"] == -30000
    assert rule.handler_params["auto_release_under_to_drop_before"] == 1


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


def test_extract_stowaways_activate_extra_from_hand_rules() -> None:
    card = replace(
        _card(
            "[Permanent] This card gains Earthling in all areas. "
            "[Activate: Main/Battle]{1}, if your Leader is a red <Krillin> card and you discard 1 card from your hand : "
            "Play up to 1 each of <Son Goten> and <Trunks : Youth> cards-both red and with an energy cost of 1-from your deck and/or Drop in Rest Mode, then shuffle your deck. "
            "[Activate: Main/Battle][Limit 1] If your Leader is a red <Krillin> card : "
            "Add up to 1 red Extra with an energy cost of 1 or less from your deck to your hand, then shuffle your deck."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    extra_rules = [rule for rule in rules if rule.trigger == "self_activate_extra_from_hand"]
    assert len(extra_rules) == 2
    play_rule = next(rule for rule in extra_rules if rule.handler_id == "activate_play_up_to_n_each_named_from_owner_deck_or_drop")
    assert play_rule.handler_params["required_name_contains_each"] == "SON GOTEN|TRUNKS : YOUTH"
    assert play_rule.handler_params["allowed_colors"] == "red"
    assert play_rule.handler_params["max_cost"] == 1
    assert play_rule.handler_params["rest_mode"] is True
    assert play_rule.handler_params["discard_from_hand_before"] == 1
    search_rule = next(rule for rule in extra_rules if rule.handler_id == "activate_add_up_to_n_from_owner_deck_to_hand")
    assert search_rule.limit_per_turn == 1
    assert search_rule.handler_params["max_targets"] == 1
    assert search_rule.handler_params["allowed_colors"] == "red"
    assert search_rule.handler_params["required_traits"] == "Extra"
    assert search_rule.handler_params["max_cost"] == 1


def test_extract_attack_combo_from_owner_warp_rule() -> None:
    card = _card(
        "[Dual Attack] "
        "[Dark Over Realm 4]{b}, if your Leader is a <Mechikabura> card : "
        "[Auto] Whe this card attacks, use up to 1 black Battle Card with 5000 combo power from your Warp in a combo with its skill negated for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_combo_up_to_n_from_owner_zone_on_attack")
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["source_zone"] == "warp"
    assert rule.handler_params["allowed_colors"] == "black"
    assert rule.handler_params["required_card_type"] == "BATTLE"
    assert rule.handler_params["exact_combo_power"] == 5000
    assert rule.handler_params["negate_skills"] is True


def test_extract_attack_combo_from_owner_warp_rule_with_under_cost() -> None:
    card = _card(
        "[Auto][Limit 1] Place 1 card from under this card in its owner's Drop: "
        "When this card attacks, use up to 1 black Battle Card with 5000 combo power from your Warp in a combo with its skill negated for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_combo_up_to_n_from_owner_zone_on_attack")
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["source_zone"] == "warp"
    assert rule.handler_params["auto_release_under_to_drop_before"] == 1


def test_extract_attack_self_gain_power_per_owner_warp_rule() -> None:
    card = _card("[Auto] When this card attacks, this card gains +5000 power for each card in your Warp.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_self_gain_power_for_turn_on_attack")
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["power_delta"] == "expr:owner_warp_count*5000"


def test_extract_attack_self_gain_power_per_owner_warp_rule_with_under_cost() -> None:
    card = _card(
        "[Auto][Limit 1] Place 1 card from under this card in its owner's Drop: "
        "When this card attacks, this card gains +5000 power for each card in your Warp."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_self_gain_power_for_turn_on_attack")
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["power_delta"] == "expr:owner_warp_count*5000"
    assert rule.handler_params["auto_release_under_to_drop_before"] == 1


def test_extract_dark_over_realm_on_play_draw_rule() -> None:
    card = _card("[Dark Over Realm 4]{b}, on play, if your Leader is a <Mechikabura> card draw 1 card")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_draw_n")
    assert rule.trigger == "self_played"
    assert rule.handler_params["amount"] == 1
    assert "mechikabura" in str(rule.handler_params.get("requires_leader", "")).lower()
    assert "Mechikabura" in str(rule.handler_params["required_leader_traits"])


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


def test_extract_union_fusion_opponent_combo_support_rule() -> None:
    card = _card(
        "[Auto] Place 2 of your Z-Energy into their owner's Drop: "
        "When your opponent uses cards in a combo, your opponent places 1 card from their hand at the bottom of their deck, "
        "then you negate this skill for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_opponent_card_comboed"
        and r.handler_id == "auto_pay_z_energy_bottom_deck_opponent_hand_on_opponent_combo_and_negate_self_for_battle"
    )
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["negate_self_skill_for_battle"] is True


def test_extract_self_combo_opponent_bottom_deck_hand_rule() -> None:
    card = _card(
        "[Auto] If your Leader Card is blue or green: "
        "When you combo with this card from your hand, your opponent chooses 1 card in their hand and places it at the bottom of their deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_opponent_bottom_decks_n_from_hand_on_combo"
    )
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["requires_comboed_from"] == "hand"


def test_extract_self_combo_switch_opponent_leader_or_battle_rest_rule() -> None:
    card = _card(
        "[Auto] If your Leader Card is blue or yellow: "
        "When you combo with this card from your hand, choose up to 1 of your opponent's Leader Cards or Battle Cards and switch it to Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_switch_up_to_n_opponent_leader_or_battle_rest_on_combo"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["requires_comboed_from"] == "hand"


def test_extract_self_combo_switch_owner_multicolor_energy_active_rule() -> None:
    card = _card(
        "[Auto] If your Leader Card is red or blue and it's your opponent's turn: "
        "When you combo with this card from your hand, choose up to 1 of your Red/Blue multicolor energy and switch it to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_switch_up_to_n_owner_energy_active_on_combo"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["requires_comboed_from"] == "hand"
    assert rule.handler_params["allowed_colors"] == "blue,red"
    assert rule.handler_params["requires_multicolor"] is True


def test_extract_self_combo_place_matching_deck_card_in_drop_rule() -> None:
    card = _card(
        "[Auto] If your Leader Card is green or yellow: "
        "When you combo with this card from your hand, choose up to 1 green or yellow Battle Card with an energy cost of 4 or less from your deck, "
        "place it in your Drop Area, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_place_up_to_n_from_owner_deck_into_drop_on_combo"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["requires_comboed_from"] == "hand"
    assert rule.handler_params["allowed_colors"] == "green,yellow"
    assert rule.handler_params["max_cost"] == 4
    assert rule.handler_params["required_card_type"] == "BATTLE"


def test_extract_self_combo_gain_combo_power_per_owner_drop_and_warp_rule() -> None:
    card = _card(
        "[Super Combo][Auto] If all of your energy is black: "
        "When you combo with this card from your hand, this card gets +1000 combo power for the duration of the turn for each card in your Drop Area and Warp (up to a maximum of 12)."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_self_gain_combo_power_on_combo_per_owner_drop_and_warp"
    )
    assert rule.handler_params["combo_power_per_card"] == 1000
    assert rule.handler_params["requires_comboed_from"] == "hand"
    assert rule.handler_params["max_count"] == 12
    assert rule.handler_params["requires_mono_energy"] == "black"


def test_extract_self_combo_battle_end_play_self_with_owner_battle_requirement_rule() -> None:
    card = _card(
        "[Auto](Blue), during your turn: "
        "When you combo with this card from your hand with an <Android 18> card in battle, play this card at the end of the battle."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed_battle_end"
        and r.handler_id == "auto_play_self_from_combo_on_battle_end"
    )
    assert rule.handler_params["requires_comboed_from"] == "hand"
    assert rule.handler_params["requires_owner_turn"] is True
    assert rule.handler_params["required_owner_battle_required_characters"] == "Android 18"


def test_extract_self_combo_battle_end_play_self_in_rest_mode_rule() -> None:
    card = _card(
        "[Auto] At the end of the battle after you combo with this card from your hand, if your Leader Card is ≪Universe 11≫, play this card in Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed_battle_end"
        and r.handler_id == "auto_play_self_from_combo_on_battle_end"
    )
    assert rule.handler_params["requires_comboed_from"] == "hand"
    assert rule.handler_params["resting"] is True
    assert rule.handler_params["requires_leader"] == "if your leader card is ≪universe 11≫"


def test_extract_self_combo_battle_end_add_self_to_z_energy_rule() -> None:
    card = _card(
        "[Auto][Limit 1] If your Leader's back side is a black <Vegito: Xeno> card, you have 2 or more energy, and you have a <Vegeta: Xeno> card in your Combo Area: "
        "When this card is used in a combo from your hand, add this card from your Drop to your Z-Energy at the end of the battle."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed_battle_end"
        and r.handler_id == "auto_add_self_to_owner_z_energy_on_battle_end"
    )
    assert rule.handler_params["requires_comboed_from"] == "hand"
    assert rule.handler_params["required_leader_back_name_contains"] == "VEGITO: XENO"
    assert rule.handler_params["min_owner_energy"] == 2
    assert rule.handler_params["required_owner_combo_required_characters"] == "Vegeta: Xeno"


def test_extract_self_combo_gain_combo_power_and_warp_self_on_battle_end_rules() -> None:
    card = _card(
        "[Auto] When you combo with this card from your hand, this card gets +5000 combo power for the duration of the turn and is sent to its owner's Warp at the end of the battle."
    )
    rules = extract_effect_rules_from_card(card)
    combo_rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_self_gain_combo_power_on_combo"
    )
    battle_end_rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed_battle_end"
        and r.handler_id == "auto_send_self_to_owner_warp_on_battle_end"
    )
    assert combo_rule.handler_params["combo_power_delta"] == 5000
    assert combo_rule.handler_params["requires_comboed_from"] == "hand"
    assert battle_end_rule.handler_params["requires_comboed_from"] == "hand"


def test_extract_self_combo_draw_and_gain_combo_power_for_battle_rules() -> None:
    card = _card(
        "[Auto] If your Leader Card is green and your life is at 4 or less: "
        "When this card is used in a combo from your hand, draw 1 card and this card gets +10000 combo power for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    draw_rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_draw_n"
    )
    combo_rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_self_gain_combo_power_on_combo"
    )
    assert draw_rule.handler_params["amount"] == 1
    assert "green" in str(draw_rule.handler_params.get("requires_leader", "")).lower()
    assert combo_rule.handler_params["combo_power_delta"] == 10000
    assert combo_rule.handler_params["requires_comboed_from"] == "hand"
    assert "green" in str(combo_rule.handler_params.get("requires_leader", "")).lower()


def test_extract_self_combo_draw_and_buff_other_combo_card_for_battle_rules() -> None:
    card = _card(
        "[Auto] If your Leader Card is yellow and your life is at 4 or less: "
        "When this card is used in a combo from your hand, draw 1 card, then choose 1 card other than this card in your Combo Area and it gets +6000 combo power for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    draw_rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_draw_n"
    )
    buff_rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_buff_other_owner_combo_card_on_combo"
    )
    assert draw_rule.handler_params["amount"] == 1
    assert buff_rule.handler_params["combo_power_delta"] == 6000
    assert buff_rule.handler_params["requires_comboed_from"] == "hand"
    assert buff_rule.handler_params["exclude_self"] is True
    assert "yellow" in str(buff_rule.handler_params.get("requires_leader", "")).lower()


def test_extract_self_combo_gain_combo_power_and_optional_bottom_deck_draw_rules() -> None:
    card = _card(
        "[Auto] If your Leader Card is red, your life is at 4 or less, and all of your energy is red: "
        "When this card is used in a combo, it gets +10000 combo power for the battle, then you may choose 1 card in your hand and place it at the bottom of your deck. If you do, draw 2 cards."
    )
    rules = extract_effect_rules_from_card(card)
    combo_rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_self_gain_combo_power_on_combo"
    )
    draw_rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_optional_bottom_deck_n_from_owner_hand_draw_n_on_combo"
    )
    assert combo_rule.handler_params["combo_power_delta"] == 10000
    assert "red" in str(combo_rule.handler_params.get("requires_leader", "")).lower()
    assert draw_rule.handler_params["bottom_deck_from_hand"] == 1
    assert draw_rule.handler_params["amount"] == 2
    assert "all of your energy is red" in str(draw_rule.handler_params.get("requires_leader", "")).lower()


def test_extract_owner_comboed_card_gain_combo_power_and_draw_rules() -> None:
    card = _card(
        "[Auto][Once per turn] When one of your skill-less Battle Cards is used in a combo, it gets +4000 combo power for the battle, then draw 1 card."
    )
    rules = extract_effect_rules_from_card(card)
    buff_rule = next(
        r
        for r in rules
        if r.trigger == "owner_card_comboed"
        and r.handler_id == "auto_comboed_card_gain_combo_power_on_owner_combo"
    )
    draw_rule = next(
        r
        for r in rules
        if r.trigger == "owner_card_comboed"
        and r.handler_id == "auto_draw_n"
    )
    assert buff_rule.handler_params["combo_power_delta"] == 4000
    assert buff_rule.handler_params["event_requires_skill_less"] is True
    assert buff_rule.handler_params["event_required_card_type"] == "BATTLE"
    assert draw_rule.handler_params["amount"] == 1
    assert draw_rule.handler_params["event_requires_skill_less"] is True


def test_extract_owner_combo_switch_self_active_and_owner_combo_marker_buff_rules() -> None:
    card = _card(
        "[Auto][Once per turn] When you use a card in a combo, switch this card to Active Mode.\n"
        "[Auto][Once per turn] When you use a black Battle Card in a combo, add a marker to this card and it gets +5000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    switch_rule = next(
        r
        for r in rules
        if r.trigger == "owner_card_comboed"
        and r.handler_id == "auto_switch_self_active_on_owner_combo"
    )
    buff_rule = next(
        r
        for r in rules
        if r.trigger == "owner_card_comboed"
        and r.handler_id == "auto_add_markers_and_self_power_for_turn_on_owner_combo"
    )
    assert switch_rule.handler_params == {}
    assert buff_rule.handler_params["marker_delta"] == 1
    assert buff_rule.handler_params["power_delta"] == 5000
    assert buff_rule.handler_params["event_allowed_colors"] == "black"
    assert buff_rule.handler_params["event_required_card_type"] == "BATTLE"


def test_extract_owner_combo_send_opponent_drop_to_warp_else_draw_rule() -> None:
    card = _card(
        "[Auto][Once per turn] If this card is in a battle: When you use a black Battle Card in a combo, your opponent sends 1 Battle Card from their Drop Area to their Warp; if there are no Battle Cards in your opponent's Drop Area, draw 1 card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_card_comboed"
        and r.handler_id == "auto_send_up_to_n_opponent_drop_to_warp_else_draw_n_on_owner_combo"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["draw_amount"] == 1
    assert rule.handler_params["event_allowed_colors"] == "black"
    assert rule.handler_params["event_required_card_type"] == "BATTLE"
    assert rule.handler_params["requires_source_in_battle"] is True


def test_extract_owner_combo_remove_markers_from_opponent_unison_rule() -> None:
    card = _card(
        "[Auto][Once per turn] If this card is in a battle: When you use a {SS Son Goku, Showing the Results of Training} in a combo, choose up to 1 of your opponent's Unisons and remove 2 markers from it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_card_comboed"
        and r.handler_id == "auto_remove_markers_from_up_to_n_opponent_unisons_on_owner_combo"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["marker_amount"] == 2
    assert rule.handler_params["event_required_name_contains"] == "SS SON GOKU, SHOWING THE RESULTS OF TRAINING"
    assert rule.handler_params["requires_source_in_battle"] is True


def test_extract_owner_combo_can_play_self_from_under_leader_or_hand_rule() -> None:
    card = _card(
        "[Auto][Limit 1](Blue), if your Leader is blue and you have 3 or more energy: "
        "When you use a blue <Krillin> card from your hand or Battle Area in a combo, "
        "play this card from under your Leader or from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_card_comboed"
        and r.handler_id == "auto_play_self_from_under_leader_or_owner_hand_on_owner_combo"
    )
    assert rule.handler_params["event_allowed_colors"] == "blue"
    assert str(rule.handler_params["event_required_characters"]).lower() == "krillin"
    assert "blue" in str(rule.handler_params.get("requires_leader", "")).lower()
    assert rule.handler_params["min_owner_energy"] == 3


def test_extract_owner_combo_can_use_self_from_battle_and_replay_at_battle_end_rule() -> None:
    card = _card(
        "[Auto][Limit 1] When you use a card in a combo, you may use this card from a Battle Area in a combo. "
        "If you do, play this card from its owner's Drop at the end of the battle."
    )
    rules = extract_effect_rules_from_card(card)
    combo_rule = next(
        r
        for r in rules
        if r.trigger == "owner_card_comboed"
        and r.handler_id == "auto_combo_self_from_battle_on_owner_combo"
    )
    battle_end_rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed_battle_end"
        and r.handler_id == "auto_play_self_from_combo_on_battle_end"
    )
    assert combo_rule.limit_per_turn == 1
    assert battle_end_rule.limit_per_turn == 1
    assert battle_end_rule.handler_params["requires_comboed_from"] == "battle"


def test_extract_self_added_to_z_energy_draw_rule() -> None:
    card = _card(
        "[Auto][Limit 1] If your Leader is a yellow ≪Universe 7≫ <Son Goku> card and you have a ≪Universe 7≫ card in your Combo Area: "
        "When this card is added to Z-Energy, draw 1 card."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_added_to_z_energy"
        and r.handler_id == "auto_draw_n"
    )
    assert rule.handler_params["amount"] == 1
    assert rule.limit_per_turn == 1
    assert rule.handler_params["required_owner_combo_required_traits"] == "Universe 7"


def test_extract_self_added_to_z_energy_can_buff_owner_battle_rule() -> None:
    card = _card(
        "[Auto][Limit 1] If your Leader is a blue ≪Phantom Demon≫ card: "
        "When this card is added to Z-Energy, choose up to 1 of your <Hirudegarn> Battle Cards and it gets +1000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_added_to_z_energy"
        and r.handler_id == "auto_buff_up_to_n_owner_battle_on_z_energy_added"
    )
    assert rule.handler_params["max_targets"] == 1


def test_extract_hit_assassins_strike_rules() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Barrier][Dual Attack]<br />"
            "[Auto]((Green))((Green)), if your Leader Card is green, your opponent has 2 or more energy, and this card is in your Combo Area: "
            "When one of your green Battle Cards attacks and KOs an opponent's Battle Card, play this card from your Combo Area.<br />"
            "[Auto][Limit 1] If this card is in Rest Mode: When your opponent attacks, they may choose 2 cards in their hand and discard them. "
            "If they don't, negate the attack, and your opponent can't attack for the turn."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)

    combo_rule = next(
        r
        for r in rules
        if r.trigger == "owner_battle_ko_opponent_battle_battle_end"
        and r.handler_id == "auto_play_self_from_combo_on_battle_end"
    )
    assert combo_rule.handler_params["attacker_allowed_colors"] == "green"
    assert "leader card is green" in str(combo_rule.handler_params["requires_leader"]).lower()
    assert combo_rule.handler_params["min_opponent_energy"] == 2

    lock_rule = next(
        r
        for r in rules
        if r.trigger == "owner_opponent_battle_attacks"
        and r.handler_id == "auto_if_self_rest_opponent_discards_n_or_negate_attack_and_end_attacks"
    )
    assert lock_rule.handler_params["discard_amount"] == 2
    assert lock_rule.handler_params["remaining_attacks"] == 0
    assert lock_rule.limit_per_turn == 1


def test_extract_realm_of_the_gods_champa_destroys_rules() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Battle] If your Leader Card and all of your energy is green: Choose 1 of your cards and it gets +10000 power for the battle, then choose one?\n"
            "If it's your turn, choose up to 1 of your opponent's Battle Cards with an energy cost greater than their current energy and KO it.\n"
            "If it's your opponent's turn, your opponent chooses 1 card in their hand and discards it, then you choose 1 of your cards and it gets +5000 power for the battle."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_extra_from_hand"
        and r.handler_id == "activate_buff_owner_cards_for_battle_then_turn_based_ko_or_discard_and_buff"
    )
    assert rule.handler_params["requires_leader"] == "green"
    assert rule.handler_params["requires_mono_energy"] == "green"
    assert rule.handler_params["first_power_delta"] == 10000
    assert rule.handler_params["turn_max_targets"] == 1
    assert rule.handler_params["requires_cost_greater_than_opponent_current_energy"] is True
    assert rule.handler_params["opponent_discard_amount"] == 1
    assert rule.handler_params["opponent_turn_power_delta"] == 5000


def test_extract_ultimate_minus_energy_power_ball_rules() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack] If your Leader Card is mono-black: Choose up to 1 of your opponent's Battle Cards with 15000 power or less, ignoring [Barrier], and send it to its owner's Warp.\n"
            "[Permanent] This card gains ≪Shadow Dragon≫ in all areas.\n"
            "[Permanent] If you have a black Unison Card in play, you can activate this card's [Counter] skill from your hand without paying its energy cost.\n"
            "[Activate: Main/Battle][Limit 1] Choose up to 1 of your black Leader Cards or Battle Cards, and it gets +15000 power until the end of a battle or the end of the turn, whichever comes first."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(r for r in rules if r.handler_id == "counter_send_up_to_n_opponent_battle_to_warp")
    assert counter_rule.trigger == "counter_attack"
    assert counter_rule.handler_params["max_targets"] == 1
    assert counter_rule.handler_params["max_power"] == 15000
    assert counter_rule.handler_params["ignores_barrier"] is True
    assert counter_rule.handler_params["requires_leader"] == "mono-black"
    buff_rule = next(r for r in rules if r.handler_id == "activate_buff_owner_cards_until_battle_or_turn")
    assert buff_rule.trigger == "self_activate_extra_from_hand"
    assert buff_rule.handler_params["target_scope"] == "owner_cards"
    assert buff_rule.handler_params["max_targets"] == 1
    assert buff_rule.handler_params["power_delta"] == 15000
    assert buff_rule.handler_params["allowed_colors"] == "black"
    noop_rules = [r for r in rules if r.handler_id == "noop_auto"]
    assert len(noop_rules) == 2


def test_extract_yajirobe_confronting_invasion_rules() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack] Negate the attack and play this card in Rest Mode. "
            "If the attacking card is a ≪Great Ape≫ or ≪Demon Clan≫ Battle Card, choose it, KO it, and your opponent draws 1 card."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "counter_attack"
        and r.handler_id == "counter_play_self_rest_then_ko_attacking_battle_if_trait_and_opponent_draw_n"
    )
    assert rule.handler_params["required_attacker_traits"] == "Great Ape|Demon Clan"
    assert rule.handler_params["draw_amount"] == 1


def test_extract_dyspo_thwarting_the_enemy_rules() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack][Limit 1] If your Leader Card is red: Negate the attack, then play this card in Rest Mode. "
            "If you negated a Leader Card's attack with this skill, your opponent can't attack with their Leader Card for the turn.<br>"
            "[Permanent] You can activate this card's [Counter] skill from your hand without paying its energy cost by paying the cost for [Spirit Boost 2] instead."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "counter_attack"
        and r.handler_id == "counter_negate_attack_play_self_attack_restriction"
    )
    assert rule.handler_params["requires_leader"] == "red"
    assert rule.limit_per_turn == 1


def test_extract_skill_hunter_towa_rules() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Counter: Attack][Spirit Boost 1] Play this card.<br>"
            "[Permanent] If it's your opponent's turn and they have a skill-less Battle Card or Unison Card in play, reduce the energy cost of this card in your hand by 1.<br>"
            "[Auto] If your Leader Card is a black &lt;Fin&gt; card: When this card is played, choose up to 1 of your opponent's Battle Cards with an energy cost of 4 or less and place it under your Leader Card."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(r for r in rules if r.trigger == "counter_attack" and r.handler_id == "noop_auto")
    assert counter_rule.source_text == "[Counter: Attack][Spirit Boost 1] Play this card."
    permanent_rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "noop_auto")
    assert "reduce the energy cost of this card in your hand by 1" in permanent_rule.source_text.lower()
    auto_rule = next(
        r
        for r in rules
        if r.trigger == "self_played"
        and r.handler_id == "auto_place_up_to_n_opponent_battle_under_owner_leader_on_play"
    )
    assert auto_rule.handler_params["max_targets"] == 1
    assert auto_rule.handler_params["max_cost"] == 4
    assert auto_rule.handler_params["leader_allowed_colors"] == "black"
    assert auto_rule.handler_params["leader_required_characters"] == "Fin"


def test_extract_p348_turles_brutal_persuasion_rules() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Dual Attack]<br>"
            "[Permanent] If an opponent's Battle Card would be KO'd by this card's attack, gain control of it instead; you may switch it to Active Mode.<br>"
            "[Auto][Spirit Boost 1] When this card is played from your hand, choose up to 1 face-up Battle Card in your opponent's life and play it in your opponent's Battle Area in Rest Mode with its skills negated for the game."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    permanent_rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "noop_auto")
    assert "gain control of it instead" in permanent_rule.source_text.lower()
    auto_rule = next(
        r for r in rules if r.trigger == "self_played" and r.handler_id == "auto_play_face_up_opponent_life_battle_rest_negated_on_play"
    )
    assert auto_rule.handler_params["max_targets"] == 1
    assert auto_rule.handler_params["requires_played_from"] == "hand"


def test_extract_self_added_to_z_energy_can_switch_opponent_board_rest_rule() -> None:
    card = _card(
        "[Dual Attack]\n"
        "[Auto][Limit 1] If your Leader is yellow and you have 3 or more Z-Energy: "
        "When this card attacks or when this card is added to Z-Energy, choose up to 1 of your opponent's Battle Cards or Unisons and switch it to Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_added_to_z_energy"
        and r.handler_id == "auto_switch_up_to_n_opponent_board_rest"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["min_owner_z_energy"] == 3
    assert "if your leader is yellow" in str(rule.handler_params["requires_leader"]).lower()
    assert rule.limit_per_turn == 1


def test_extract_self_placed_under_owner_card_can_power_reduce_rule() -> None:
    card = _card(
        "[Auto][Limit 1] If your Leader's back side is a red <Super 17> card: "
        "When this card in your hand, Z-Energy, or Combo Area is placed under your red <Super 17> card, choose up to 1 of your opponent's Battle Cards and it gets -10000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_placed_under_owner_card"
        and r.handler_id == "auto_power_reduce_up_to_n_on_placed_under"
    )
    assert rule.handler_params["requires_placed_from_zones"] == "hand,z_energy,combo"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["power_delta"] == -10000
    assert rule.handler_params["host_allowed_colors"] == "red"
    assert rule.handler_params["host_required_characters"] == "Super 17"
    assert "leader's back side" in str(rule.handler_params["requires_leader"]).lower()
    assert rule.limit_per_turn == 1


def test_extract_self_placed_under_owner_leader_can_search_then_discard_rule() -> None:
    card = _card(
        "[Auto] When this card in your hand is placed under your green <Cell> Leader, "
        "add up to a total of 2 <Android 17>, <Android 18>, and/or <Cell> cards-all green and with an energy cost of 1-from your deck to your hand, "
        "place 1 card from your hand into your Drop, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_placed_under_owner_card"
        and r.handler_id == "auto_add_up_to_n_from_owner_deck_to_hand_then_discard_n_on_placed_under"
    )
    assert rule.handler_params["requires_placed_from_zones"] == "hand"
    assert rule.handler_params["required_host_zone"] == "leader"
    assert rule.handler_params["max_targets"] == 2
    assert rule.handler_params["discard_count"] == 1
    assert rule.handler_params["allowed_colors"] == "green"
    assert rule.handler_params["required_characters"] == "Android 17,Android 18,Cell"
    assert rule.handler_params["max_cost"] == 1
    assert rule.handler_params["host_allowed_colors"] == "green"
    assert rule.handler_params["host_required_characters"] == "Cell"


def test_extract_self_placed_into_drop_from_under_leader_can_combo_from_drop_rule() -> None:
    card = _card(
        "[Auto] If your {SSG Son Goku, Crimson Warrior} is in a battle and there are no cards in your Combo Area: "
        "When your Leader Card's skill places this card in a Drop Area from under your Leader Card, use this card in a combo from your Drop Area."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_placed_into_drop"
        and r.handler_id == "auto_combo_self_from_drop_on_placed_into_drop"
    )
    assert rule.handler_params["requires_placed_from_zones"] == "leader_under"
    assert rule.handler_params["required_drop_causes"] == "leader_skill"
    assert rule.handler_params["requires_owner_combo_empty"] is True
    assert rule.handler_params["required_owner_battle_name_in_battle"] == "SSG SON GOKU, CRIMSON WARRIOR"


def test_extract_self_placed_into_drop_can_draw_and_play_self_from_drop_with_markers_rule() -> None:
    card = _card(
        "[Auto]{1}, if your Leader's back side is {SSG Son Goku, Surge of Divinity}: "
        "When this card is placed into its owner's Drop from your hand or from under your Leader by your Leader's skill, "
        "draw 1 card and play this card from your Drop with 1 marker on it."
    )
    rules = extract_effect_rules_from_card(card)
    draw_rule = next(
        r
        for r in rules
        if r.trigger == "self_placed_into_drop"
        and r.handler_id == "auto_draw_n"
    )
    play_rule = next(
        r
        for r in rules
        if r.trigger == "self_placed_into_drop"
        and r.handler_id == "auto_play_self_from_drop_on_hand_drop"
    )
    assert draw_rule.handler_params["amount"] == 1
    assert draw_rule.handler_params["requires_placed_from_zones"] == "hand,leader_under"
    assert draw_rule.handler_params["required_drop_causes"] == "leader_skill"
    assert "surge of divinity" in str(draw_rule.handler_params["requires_leader"]).lower()
    assert play_rule.handler_params["marker_count"] == 1
    assert play_rule.handler_params["requires_placed_from_zones"] == "hand,leader_under"
    assert play_rule.handler_params["required_drop_causes"] == "leader_skill"


def test_extract_combo_can_return_opponent_combo_to_hand_rule() -> None:
    card = _card(
        "[Auto] When this card is used in a combo, choose up to 1 card in your opponent's Combo Area and return it to its owner's hand."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_comboed"
        and r.handler_id == "auto_return_up_to_n_opponent_combo_to_hand_on_combo"
    )
    assert rule.handler_params["amount"] == 1


def test_extract_self_placed_under_owner_card_can_grant_host_keywords_rule() -> None:
    card = _card(
        "[Auto] If your Leader is {Android 17 & Android 18, Future Evil}: "
        "When this card is placed under a red Battle Card with both <Android 17> and <Android 18>, "
        "the card on top of this card gains [Barrier] and [Critical] until the end of your opponent's turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_placed_under_owner_card"
        and r.handler_id == "auto_host_gain_keywords_until_opponent_turn_on_placed_under"
    )
    assert rule.handler_params["required_host_zone"] == "battle"
    assert rule.handler_params["host_allowed_colors"] == "red"
    assert rule.handler_params["host_required_card_type"] == "BATTLE"
    assert rule.handler_params["host_required_characters"] == "Android 17,Android 18"
    assert rule.handler_params["host_requires_all_characters"] is True
    assert rule.handler_params["grant_keywords"] == "Barrier,Critical"
    assert "future evil" in str(rule.handler_params["requires_leader"]).lower()


def test_extract_self_placed_under_owner_card_can_place_named_from_deck_under_named_host_rule() -> None:
    card = _card(
        "[Auto] When this card in your hand is placed under a {Hyperbolic Time Chamber} in your Battle Area, "
        "place up to 1 {SS Son Gohan, Showing the Results of Training} from your deck under a {Hyperbolic Time Chamber} in your Battle Area, "
        "then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_placed_under_owner_card"
        and r.handler_id == "auto_place_up_to_n_named_from_owner_deck_under_named_host_on_placed_under"
    )
    assert rule.handler_params["requires_placed_from_zones"] == "hand"
    assert rule.handler_params["required_host_zone"] == "battle"
    assert rule.handler_params["host_name_contains"] == "HYPERBOLIC TIME CHAMBER"
    assert rule.handler_params["required_name_contains"] == "SS SON GOHAN, SHOWING THE RESULTS OF TRAINING"
    assert rule.handler_params["target_host_name_contains"] == "HYPERBOLIC TIME CHAMBER"


def test_extract_self_placed_under_owner_card_can_place_hyperbolic_mirror_named_from_deck_under_named_host_rule() -> None:
    card = _card(
        "[Auto] When this card in your hand is placed under a {Hyperbolic Time Chamber} in your Battle Area, "
        "place up to 1 {SS Son Goku, Showing the Results of Training} from your deck under a {Hyperbolic Time Chamber} in your Battle Area, "
        "then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_placed_under_owner_card"
        and r.handler_id == "auto_place_up_to_n_named_from_owner_deck_under_named_host_on_placed_under"
    )
    assert rule.handler_params["requires_placed_from_zones"] == "hand"
    assert rule.handler_params["required_host_zone"] == "battle"
    assert rule.handler_params["host_name_contains"] == "HYPERBOLIC TIME CHAMBER"
    assert rule.handler_params["required_name_contains"] == "SS SON GOKU, SHOWING THE RESULTS OF TRAINING"
    assert rule.handler_params["target_host_name_contains"] == "HYPERBOLIC TIME CHAMBER"


def test_extract_self_placed_under_owner_card_can_place_filtered_from_deck_under_target_host_rule() -> None:
    card = _card(
        "[Auto][Limit 1] When this card in your hand is placed under a {Destroyed West City} in your Battle Area, "
        "place up to 1 red <Android 18> card from your deck under a Z-Extra in your Battle Area, then shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_placed_under_owner_card"
        and r.handler_id == "auto_place_up_to_n_named_from_owner_deck_under_named_host_on_placed_under"
        and r.handler_params.get("host_name_contains") == "DESTROYED WEST CITY"
    )
    assert rule.handler_params["requires_placed_from_zones"] == "hand"
    assert rule.handler_params["required_host_zone"] == "battle"
    assert rule.handler_params["allowed_colors"] == "red"
    assert rule.handler_params["required_characters"] == "Android 18"
    assert rule.handler_params["target_host_required_card_type"] == "EXTRA"


def test_extract_owner_other_battle_played_can_place_combo_under_owner_leader_rule() -> None:
    card = _card(
        "[Auto] When your red <Super 17> card is played, place up to 1 red <Android 17> or <Hell Fighter 17> card from your Combo Area under your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_other_battle_played"
        and r.handler_id == "auto_place_up_to_n_from_owner_combo_under_owner_leader_on_owner_matching_battle_played"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["event_allowed_colors"] == "red"
    assert rule.handler_params["event_required_characters"] == "Super 17"
    assert rule.handler_params["allowed_colors"] == "red"
    assert rule.handler_params["required_characters"] == "Android 17,Hell Fighter 17"


def test_extract_owner_card_left_battle_area_can_place_from_drop_under_owner_leader_rule() -> None:
    card = _card(
        "[Auto] When your {Power-Infused Shocking Death Ball} leaves the Battle Area, "
        "place up to 1 red <Android 17> or <Hell Fighter 17> card from your Drop under your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_card_left_battle_area"
        and r.handler_id == "auto_place_up_to_n_from_owner_drop_under_owner_leader_on_owner_matching_battle_left"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["event_required_name_contains"] == "POWER-INFUSED SHOCKING DEATH BALL"
    assert rule.handler_params["allowed_colors"] == "red"
    assert rule.handler_params["required_characters"] == "Android 17,Hell Fighter 17"


def test_extract_self_played_can_place_named_field_extra_from_owner_z_deck_rule() -> None:
    card = _card(
        "[Auto] When this card is played, draw 1 card, then place up to 1 {Power-Infused Shocking Death Ball} from your Z-Deck into your Battle Area."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_played"
        and r.handler_id == "auto_activate_up_to_n_named_field_extra_from_owner_z_deck_on_play"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_name_contains"] == "POWER-INFUSED SHOCKING DEATH BALL"
    assert rule.handler_params["required_card_type"] == "EXTRA"
    assert rule.handler_params["requires_field_keyword"] is True


def test_extract_self_played_can_place_named_field_extra_from_owner_z_deck_and_reduce_power_rule() -> None:
    card = _card(
        "[Auto] When this card is played, place up to 1 {Power-Infused Shocking Death Ball} from your Z-Deck into your Battle Area, "
        "then choose up to 1 of your opponent's Battle Cards and it gets -20000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    assert any(
        r.trigger == "self_played"
        and r.handler_id == "auto_activate_up_to_n_named_field_extra_from_owner_z_deck_on_play"
        for r in rules
    )
    reduce_rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "auto_power_reduce_up_to_n_on_play")
    assert reduce_rule.handler_params["max_targets"] == 1
    assert reduce_rule.handler_params["power_delta"] == -20000


def test_extract_power_infused_shocking_death_ball_rules() -> None:
    card = _card(
        "[Auto] When this card is placed in a Battle Area, your red <Super 17> Leader gets +5000 power for the turn. "
        "[Activate: Battle][Limit 1] Place 1 of your Z-Energy in its owner's Drop and remove this card from the game: "
        "Choose up to 1 of your <Super 17> cards and it gains [Double Strike] for the battle."
    )
    rules = extract_effect_rules_from_card(card)
    place_rule = next(r for r in rules if r.handler_id == "auto_buff_owner_leader_for_turn_on_field_extra_placed")
    assert place_rule.trigger == "self_field_extra_placed"
    assert place_rule.handler_params["leader_power_delta"] == 5000
    assert place_rule.handler_params["leader_allowed_colors"] == "red"
    assert place_rule.handler_params.get("leader_required_characters", place_rule.handler_params.get("leader_required_traits")) == "Super 17"
    activate_rule = next(r for r in rules if r.handler_id == "activate_gain_power_and_keyword_for_battle")
    assert activate_rule.trigger == "self_activate_battle"
    assert activate_rule.handler_params["target_scope"] == "owner_cards"
    assert activate_rule.handler_params["grant_keyword"] == "Double Strike"
    assert activate_rule.handler_params["max_targets"] == 1
    assert activate_rule.handler_params.get("required_characters", activate_rule.handler_params.get("required_traits")) == "Super 17"


def test_extract_super_17_attack_commenced_activate_battle_play_rule() -> None:
    card = _card(
        "[Auto] When this card is played, draw 1 card, then place up to 1 {Power-Infused Shocking Death Ball} from your Z-Deck into your Battle Area. "
        "[Activate: Battle][Limit 1]{r}, if your Leader's back side is a red <Super 17> card, you have 2 or more energy, "
        "and you have 1 or more <Android 17> card and 1 or more <Hell Fighter 17> card in your Combo Area: Play this card from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(r for r in rules if r.trigger == "self_activate_battle" and r.handler_id == "activate_play_self_from_hand")
    assert play_rule.handler_params["required_leader_back_name_contains"] == "SUPER 17"
    assert play_rule.handler_params["min_owner_energy"] == 2
    assert play_rule.handler_params["required_owner_combo_required_characters_each"] == "Android 17|Hell Fighter 17"


def test_extract_super_17_absorbing_power_activate_battle_play_rule() -> None:
    card = _card(
        "[Auto] When this card is played, place up to 1 {Power-Infused Shocking Death Ball} from your Z-Deck into your Battle Area, "
        "then choose up to 1 of your opponent's Battle Cards and it gets -20000 power for the turn. "
        "[Activate: Battle][Limit 1]{r}, if your Leader's back side is a red <Super 17> card, you have 2 or more energy, "
        "and you have 1 or more <Android 17> card and 1 or more <Hell Fighter 17> card in your Combo Area: Play this card from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(r for r in rules if r.trigger == "self_activate_battle" and r.handler_id == "activate_play_self_from_hand")
    assert play_rule.handler_params["required_leader_back_name_contains"] == "SUPER 17"
    assert play_rule.handler_params["min_owner_energy"] == 2
    assert play_rule.handler_params["required_owner_combo_required_characters_each"] == "Android 17|Hell Fighter 17"


def test_extract_super_17_immense_power_rules() -> None:
    card = _card(
        "[Auto] When this card attacks, choose up to 1 of your opponent's Battle Cards and place it under this card. "
        "[Activate: Main][Limit 1]{2}, if your opponent has 3 or more energy : "
        "Play this card from your hand, choose up to 1 card in your opponent's Battle Area and switch it to Revealed Mode, "
        "then choose up to 1 of your opponent's Battle Cards and place it under this card."
    )
    rules = extract_effect_rules_from_card(card)
    attack_rule = next(r for r in rules if r.handler_id == "auto_place_up_to_n_opponent_battle_under_self_on_attack")
    assert attack_rule.trigger == "self_attacks"
    assert attack_rule.handler_params["max_targets"] == 1
    play_rule = next(r for r in rules if r.handler_id == "activate_play_self_from_hand")
    assert play_rule.trigger == "self_activate_main"
    assert play_rule.handler_params["post_play_revealed_max_targets"] == 1
    assert play_rule.handler_params["post_play_place_under_self_max_targets"] == 1
    assert play_rule.handler_params["min_opponent_energy"] == 3


def test_extract_attack_place_up_to_n_opponent_battle_under_self_rule_with_under_cost() -> None:
    card = _card(
        "[Auto][Limit 1] Place 1 card from under this card in its owner's Drop: "
        "When this card attacks, choose up to 1 of your opponent's Battle Cards and place it under this card."
    )
    rules = extract_effect_rules_from_card(card)
    attack_rule = next(r for r in rules if r.handler_id == "auto_place_up_to_n_opponent_battle_under_self_on_attack")
    assert attack_rule.trigger == "self_attacks"
    assert attack_rule.handler_params["max_targets"] == 1
    assert attack_rule.handler_params["auto_release_under_to_drop_before"] == 1


def test_extract_android_17_brainwashed_fighter_rule() -> None:
    card = _card(
        "[Barrier][Auto] When this card is played from your hand, look at up to 5 cards from the top of your deck, "
        "add up to 1 green ≪Android≫ card with an energy cost of 6 or less among them to your hand, and shuffle your deck."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["look_count"] == 5
    assert rule.handler_params["max_add"] == 1
    assert rule.handler_params["allowed_colors"] == "green"
    assert rule.handler_params["required_traits"] == "Android"
    assert rule.handler_params["max_cost"] == 6
    assert rule.handler_params["requires_played_from"] == "hand"


def test_extract_super_17_sibling_fusion_play_rules() -> None:
    card = _card(
        "[Blocker] [EX-Evolve]{r}, if you have 3 or more energy: Red <Super 17> card with an energy cost of 6. "
        "[Auto] When this card is played, draw 1 card and switch this card to Active Mode. "
        "[Auto] [Once per turn] When this card attacks or activates the [Blocker] skill, switch this card to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    assert any(r.trigger == "self_played" and r.handler_id == "auto_draw_n" and r.handler_params.get("amount") == 1 for r in rules)
    assert any(r.trigger == "self_played" and r.handler_id == "auto_switch_self_active_on_play" for r in rules)
    blocker_rule = next(r for r in rules if r.handler_id == "auto_switch_self_active_on_attack_or_blocker")
    assert blocker_rule.trigger == "self_attacks_or_self_blocker_activated"
    assert blocker_rule.once_per_turn is True


def test_extract_super_17_sibling_fusion_attack_or_blocker_rule_with_under_cost() -> None:
    card = _card(
        "[Auto][Limit 1] Place 1 card from under this card in its owner's Drop: "
        "When this card attacks or activates the [Blocker] skill, switch this card to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    blocker_rule = next(r for r in rules if r.handler_id == "auto_switch_self_active_on_attack_or_blocker")
    assert blocker_rule.trigger == "self_attacks_or_self_blocker_activated"
    assert blocker_rule.handler_params["auto_release_under_to_drop_before"] == 1


def test_extract_super_17_perfect_evolution_rules() -> None:
    card = _card(
        "[Critical] [EX-Evolve]{r}, if you have 3 or more energy: Red <Super 17> card with an energy cost of 6. "
        "[Auto] When this card is played, draw 1 card and switch this card to Active Mode. "
        "[Auto] When this card attacks, choose up to 1 of your opponent's Battle Cards and place it under this card."
    )
    rules = extract_effect_rules_from_card(card)
    assert any(r.trigger == "self_played" and r.handler_id == "auto_draw_n" and r.handler_params.get("amount") == 1 for r in rules)
    assert any(r.trigger == "self_played" and r.handler_id == "auto_switch_self_active_on_play" for r in rules)
    attack_rule = next(r for r in rules if r.handler_id == "auto_place_up_to_n_opponent_battle_under_self_on_attack")
    assert attack_rule.trigger == "self_attacks"
    assert attack_rule.handler_params["max_targets"] == 1


def test_extract_hell_fighter_17_infernal_creation_rules() -> None:
    card = _card(
        "[Auto] When this card is played, draw 1 card. Additionally, you may add 1 red ≪Android≫ card from your hand to your Z-Energy. "
        "If you do, look at up to 5 cards from the top of your deck, add up to 1 red <Android 17> or <Super 17> card to your hand, then shuffle your deck. "
        "[Activate: Battle][Limit 1]{r}. if your Leader's back side is a red <Super 17> card and you have 2 or more energy: Play this card from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(
        r
        for r in rules
        if r.trigger == "self_played"
        and r.handler_id == "auto_draw_n_optional_add_matching_from_owner_hand_to_z_energy_then_look_top_add_up_to_one_to_hand_on_play"
    )
    assert play_rule.handler_params["draw_amount"] == 1
    assert play_rule.handler_params["hand_allowed_colors"] == "red"
    assert play_rule.handler_params["hand_required_traits"] == "Android"
    assert play_rule.handler_params["look_count"] == 5
    assert play_rule.handler_params["max_add"] == 1
    assert play_rule.handler_params["allowed_colors"] == "red"
    assert play_rule.handler_params["required_characters"] == "Android 17,Super 17"
    activate_rule = next(r for r in rules if r.trigger == "self_activate_battle" and r.handler_id == "activate_play_self_from_hand")
    assert activate_rule.handler_params["required_leader_back_name_contains"] == "SUPER 17"
    assert activate_rule.handler_params["min_owner_energy"] == 2


def test_extract_hell_fighter_17_fusion_urged_rules() -> None:
    card = _card(
        "[Auto] When this card is played, look at up to 5 cards from the top of your deck, add up to 1 red ≪Android≫ card with an energy cost of 6 or less to your hand, then shuffle your deck. "
        "[Activate: Battle][Limit 1] If your Leader's back side is a red <Super 17> card and you discard 1 card from your hand: Use this card from your Drop in a combo."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play")
    assert play_rule.handler_params["look_count"] == 5
    assert play_rule.handler_params["max_add"] == 1
    assert play_rule.handler_params["allowed_colors"] == "red"
    assert play_rule.handler_params["required_traits"] == "Android"
    assert play_rule.handler_params["max_cost"] == 6
    activate_rule = next(r for r in rules if r.trigger == "self_activate_battle" and r.handler_id == "activate_combo_self_from_owner_drop")
    assert activate_rule.handler_params["required_source_zone"] == "drop"
    assert activate_rule.handler_params["required_leader_back_name_contains"] == "SUPER 17"


def test_extract_power_absorption_and_release_rules() -> None:
    card = _card(
        "[Barrier][Field]\n"
        "[br]\n"
        "[Auto] When your red <Super 17> card is played, place up to 1 red <Android 17> or <Hell Fighter 17> card from your Combo Area under your Leader.\n"
        "[br]\n"
        "[Auto] When your {Power-Infused Shocking Death Ball} leaves the Battle Area, place up to 1 red <Android 17> or <Hell Fighter 17> card from your Drop under your Leader."
    )
    rules = extract_effect_rules_from_card(card)
    combo_rule = next(
        r
        for r in rules
        if r.trigger == "owner_other_battle_played"
        and r.handler_id == "auto_place_up_to_n_from_owner_combo_under_owner_leader_on_owner_matching_battle_played"
    )
    assert combo_rule.handler_params["event_allowed_colors"] == "red"
    assert combo_rule.handler_params["event_required_characters"] == "Super 17"
    assert combo_rule.handler_params["required_traits"] == ""
    assert combo_rule.handler_params["required_characters"] == "Android 17,Hell Fighter 17"
    leave_rule = next(
        r
        for r in rules
        if r.trigger == "owner_card_left_battle_area"
        and r.handler_id == "auto_place_up_to_n_from_owner_drop_under_owner_leader_on_owner_matching_battle_left"
    )
    assert leave_rule.handler_params["event_required_characters"] == ""
    assert leave_rule.handler_params["event_required_name_contains"] == "POWER-INFUSED SHOCKING DEATH BALL"
    assert leave_rule.handler_params["required_traits"] == ""
    assert leave_rule.handler_params["required_characters"] == "Android 17,Hell Fighter 17"


def test_extract_exact_android_21_in_the_name_of_hunger_rules() -> None:
    card = _card(
        "[Unique][Blocker]<br>[Z-Stack 2] Battle Cards.<br>"
        "[Permanent] You may choose up to 1 of your opponent's Battle Cards when choosing cards for this card's [Z-Stack] conditions.<br>"
        "[Auto] When this card is played, you may place the top card of your deck in your energy in Rest Mode, and choose up to 1 of your opponent's Battle Cards and place it at the bottom of its owner's deck.<br>"
        "[Activate: Main][Once per turn] Choose up to 1 keyword skill on a card placed under this card, and this card gains that skill until the end of your opponent's next turn."
    )
    rules = extract_effect_rules_from_card(card)
    auto_rule = next(r for r in rules if r.handler_id == "auto_add_top_deck_to_energy_rest_and_bottom_deck_up_to_n_opponent_battle_on_play")
    assert auto_rule.trigger == "self_played"
    assert auto_rule.handler_params["max_targets"] == 1
    activate_rule = next(r for r in rules if r.handler_id == "activate_gain_keyword_from_under_self_until_opponent_turn_end")
    assert activate_rule.trigger == "self_activate_main"
    assert activate_rule.handler_params["min_source_stacked_cards"] == 1


def test_extract_exact_android_21_ceaseless_despair_rules() -> None:
    card = _card(
        "[Energy-Exhaust][Deflect][Double Strike][Dual Attack]<br>"
        "[Permanent] While your Leader is a blue <Android 21> card, reduce the combo cost of this card in your hand by 1.<br>"
        "[Auto] When this card is played, choose any number of your opponent's Battle Cards, ignoring [Barrier], and place them in their owners' Drops.<br>"
        "[Auto][Once per turn] When your opponent activates a [Counter] skill, they discard 2 cards from their hand.<br>"
        "[Auto] At the end of your turn, switch up to 5 of your energy to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(r for r in rules if r.handler_id == "auto_place_any_number_opponent_battle_into_drop_on_play")
    assert play_rule.trigger == "self_played"
    assert play_rule.handler_params["ignores_barrier"] is True
    counter_rule = next(r for r in rules if r.handler_id == "auto_opponent_discards_n_from_hand_on_opponent_counter_activated")
    assert counter_rule.trigger == "owner_opponent_counter_activated"
    assert counter_rule.handler_params["amount"] == 2
    turn_end_rule = next(r for r in rules if r.handler_id == "auto_switch_up_to_n_owner_energy_active_on_turn_end")
    assert turn_end_rule.handler_params["max_targets"] == 5


def test_extract_exact_android_21_transcendental_predator_rules() -> None:
    card = _card(
        "[Ultimate][Energy-Exhaust][Deflect][Dual Attack][Blocker]<br>"
        "[Permanent] Increase the energy cost of this card by 4 in any area other than an owner's hand or Battle Area.<br>"
        "[Permanent] When this card would be removed from your Battle Area by an opponent's skill, if 1 or more cards are under this card, you may place all cards from under this card in their owners' Drops instead.<br>"
        "[Auto] If your Leader is blue or green: When this card is played, choose all of your opponent's Battle Cards and Unisons, ignoring [Barrier], place them under this card, and for every 2 cards chosen, you may add the top card of your deck to your life. (Up to 2.)"
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.handler_id == "auto_place_all_opponent_battle_and_unison_under_self_and_add_top_deck_to_life_on_play"
    )
    assert rule.trigger == "self_played"
    assert rule.handler_params["cards_per_life"] == 2
    assert rule.handler_params["max_life_cards"] == 2
    assert rule.handler_params["ignores_barrier"] is True
    assert "blue" in str(rule.handler_params.get("requires_leader", "")).lower()
    assert "green" in str(rule.handler_params.get("requires_leader", "")).lower()


def test_extract_exact_son_gohan_beyond_the_ultimate_rules() -> None:
    card = _card(
        "[Ultimate]<br>"
        "[Auto] When this card is played, choose all of your opponent's Battle Cards and Unisons, ignoring [Barrier], return them to their owners' hands, and if your opponent has more cards in hand than you, place 1 card from your opponent's life at the bottom of their deck.<br>"
        "[Activate: Main/Battle][Once per turn] Choose up to 2 of your cards, switch them to Active Mode, and if you switched this card to Active Mode by this skill, it gains [Critical] for the turn.<br>"
        "[Activate: Main](Blue)(Blue), if your Leader is blue, you have 3 or more energy, and you place 2 cards from your hand at the bottom of your deck: Play this card from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(
        r
        for r in rules
        if r.handler_id == "auto_return_all_opponent_battle_and_unison_to_hand_and_bottom_deck_opponent_life_if_more_hand_on_play"
    )
    assert play_rule.trigger == "self_played"
    assert play_rule.handler_params["bottom_deck_opponent_life_amount"] == 1
    assert play_rule.handler_params["ignores_barrier"] is True
    activate_rules = [
        r
        for r in rules
        if r.handler_id == "activate_switch_up_to_n_owner_cards_active_and_gain_keyword_if_self_switched"
    ]
    assert {r.trigger for r in activate_rules} == {"self_activate_main", "self_activate_battle"}
    assert all(r.handler_params["max_targets"] == 2 for r in activate_rules)
    assert all(r.handler_params["grant_keyword"] == "Critical" for r in activate_rules)
    play_self_rule = next(r for r in rules if r.handler_id == "activate_play_self_from_hand")
    assert play_self_rule.trigger == "self_activate_main"
    assert "blue" in str(play_self_rule.handler_params.get("requires_leader", "")).lower()
    assert play_self_rule.handler_params["min_owner_energy"] == 3


def test_extract_nigrisshi_from_the_shadows_rules() -> None:
    card = _card(
        "[Permanent] When this card is placed in a Drop Area from a Battle Area or Combo Area, it is placed at the bottom of its owner's deck instead.<br>"
        "[Activate: Main/Battle] Choose 1 of your black Battle Cards with an energy cost of 3 and send it to its owner's Warp: "
        "Play this card from your Drop Area."
    )
    rules = extract_effect_rules_from_card(card)
    permanent_rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "noop_auto")
    assert "combo area" in permanent_rule.source_text.lower()
    activate_rules = [r for r in rules if r.handler_id == "activate_play_self_from_hand"]
    assert {r.trigger for r in activate_rules} == {"self_activate_main", "self_activate_battle"}
    assert all(r.handler_params["required_source_zone"] == "drop" for r in activate_rules)


def test_extract_ss_caulifla_spirited_striker_rules() -> None:
    card = replace(
        _card(
            "[+1][Activate: Main] This card gets +5000 power for the turn, then choose up to 1 of your opponent's Battle Cards with an energy cost of 2 or less and return it to its owner's hand.<br>"
            "[-3][Activate: Main] If your Leader Card is a blue &lt;Kale&gt; card and you have 5 or more energy: You may place this card under your Leader Card. "
            "If you do, play up to 1 &lt;Kefla&gt; card with 30000 power or less from your deck, then shuffle your deck."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    plus_rule = next(r for r in rules if r.handler_id == "activate_gain_power_and_keyword_for_turn")
    assert plus_rule.trigger == "self_activate_main"
    assert plus_rule.handler_params["power_delta"] == 5000
    assert plus_rule.handler_params["post_return_max_targets"] == 1
    assert plus_rule.handler_params["post_return_max_cost"] == 2
    assert plus_rule.handler_params["marker_delta"] == 1
    minus_rule = next(r for r in rules if r.handler_id == "activate_place_self_under_owner_leader")
    assert minus_rule.trigger == "self_activate_main"
    assert minus_rule.handler_params["marker_delta"] == -3
    assert "blue" in str(minus_rule.handler_params.get("requires_leader", "")).lower()
    assert "kale" in str(minus_rule.handler_params.get("requires_leader", "")).lower()
    assert minus_rule.handler_params["min_owner_energy"] == 5
    placed_under_rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_from_owner_deck_on_placed_under")
    assert placed_under_rule.trigger == "self_placed_under_owner_card"
    assert placed_under_rule.handler_params["required_host_zone"] == "leader"
    assert placed_under_rule.handler_params["requires_placed_from_zones"] == "unison"
    assert placed_under_rule.handler_params["required_name_contains"] == "KEFLA"
    assert placed_under_rule.handler_params["max_power"] == 30000


def test_extract_ss3_nappa_golden_invader_rules() -> None:
    card = replace(
        _card(
            "[+1][Activate: Main] Your opponent chooses 1 card in their hand and sends it to their Warp.<br>"
            "[-2][Activate: Main] Choose up to 2 of your opponent's Battle Cards with energy costs greater than or equal to their current energy and KO them.<br>"
            "[-3][Activate: Main](Green)(Green)②, if your Leader Card is a &lt;Nappa&gt; card or a green ≪Saiyan≫ card: Choose up to 1 Red/Green multicolor &lt;Raditz&gt; card with an original energy cost of 8 in your hand and play it."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    plus_rule = next(r for r in rules if r.handler_id == "activate_send_up_to_n_opponent_hand_to_warp")
    assert plus_rule.trigger == "self_activate_main"
    assert plus_rule.handler_params["max_targets"] == 1
    assert plus_rule.handler_params["marker_delta"] == 1
    minus_two_rule = next(
        r
        for r in rules
        if r.handler_id == "activate_ko_up_to_n_opponent_battle"
        and r.handler_params.get("requires_cost_at_least_opponent_current_energy") is True
    )
    assert minus_two_rule.trigger == "self_activate_main"
    assert minus_two_rule.handler_params["max_targets"] == 2
    assert minus_two_rule.handler_params["marker_delta"] == -2
    minus_three_rule = next(r for r in rules if r.handler_id == "activate_play_up_to_n_from_owner_hand")
    assert minus_three_rule.trigger == "self_activate_main"
    assert minus_three_rule.handler_params["marker_delta"] == -3
    assert minus_three_rule.handler_params["allowed_costs"] == "8"
    assert minus_three_rule.handler_params["requires_multicolor"] is True
    assert minus_three_rule.handler_params["required_card_type"] == "BATTLE"
    assert minus_three_rule.handler_params["required_name_contains"] == "RADITZ"


def test_extract_broly_omen_of_evolution_rules() -> None:
    card = replace(
        _card(
            "[Activate: Battle] Place this card in its owner's Drop Area from your Combo Area: "
            "Choose up to 1 Battle Card with a combo cost of 0 in your opponent's Combo Area and place it in its owner's Drop Area."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "activate_send_up_to_n_opponent_combo_to_drop")
    assert rule.trigger == "self_activate_battle"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_combo_cost"] == 0
    assert rule.handler_params["target_policy"] == "first"


def test_extract_exact_zamasu_final_tenacity_rules() -> None:
    card = _card(
        "[Indestructible]<br>"
        "[Auto] When this card is played, choose all of your opponent's Battle Cards and Unisons, then place them in their owner's Drop.<br>"
        "[Auto] When your opponent plays a Battle Card, your opponent discards 1 card from their hand.<br>"
        "[Activate: Main](Green)(Green)(Green)(Green)(Green), place 1 of your <Zamasu> cards with an energy cost of 7 in your Drop: Play this card from your hand."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(r for r in rules if r.handler_id == "auto_place_all_opponent_battle_and_unison_into_drop_on_play")
    assert play_rule.trigger == "self_played"
    assert play_rule.handler_params["ignores_barrier"] is False
    owner_played_rule = next(
        r for r in rules if r.handler_id == "auto_opponent_discards_n_from_hand_on_owner_opponent_battle_played"
    )
    assert owner_played_rule.trigger == "owner_opponent_battle_played"
    assert owner_played_rule.handler_params["amount"] == 1


def test_extract_exact_android_21_full_power_counter_rules() -> None:
    card = _card(
        "[Energy-Exhaust][Double Strike]<br>"
        "[Counter: Attack] Play this card.<br>"
        "[Permanent] If your Leader is a blue â‰ªAndroidâ‰« card, negate this card's [Energy-Exhaust] in all areas.<br>"
        "[Auto] When this card is played, choose up to 1 of your opponent's Battle Cards, ignoring [Barrier], place it in its owner's Drop, "
        "and your opponent can't attack with non-Leaders for the turn unless they place 1 card each from their hand and Z-Energy in their owners' Drops each time."
    )
    rules = extract_effect_rules_from_card(card)
    drop_rule = next(r for r in rules if r.handler_id == "auto_place_up_to_n_opponent_battle_into_drop_on_play")
    assert drop_rule.trigger == "self_played"
    assert drop_rule.handler_params["max_targets"] == 1
    assert drop_rule.handler_params["ignores_barrier"] is True
    tax_rule = next(r for r in rules if r.handler_id == "auto_apply_non_leader_attack_hand_and_z_tax_on_play")
    assert tax_rule.trigger == "self_played"
    assert tax_rule.handler_params["hand_count"] == 1
    assert tax_rule.handler_params["z_energy_count"] == 1


def test_extract_exact_prince_of_destruction_vegeta_prideful_psyche_rules() -> None:
    card = _card(
        "[Ultimate][Triple Strike][Servant]\n"
        "[br]\n"
        "[Activate: Main]{y}{y}{y}, if your Leader is yellow and you have 4 or more energy: "
        "Play this card from your hand then choose all of your opponent's Rest Mode Battle Cards and Unisons, ignoring [Barrier], "
        "and place them into their owner's Drop.\n"
        "[br]\n"
        "[Activate: Main] Remove this card from the game: Negate the skills of your opponent's Leader until the end of your opponent's turn, "
        "then choose up to 1 of your opponent's Rest Mode cards and it can't switch to Active Mode until the end of your opponent's turn."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(r for r in rules if r.handler_id == "activate_play_self_from_hand")
    assert play_rule.trigger == "self_activate_main"
    assert play_rule.handler_params["post_play_drop_opponent_rest_battle_unison"] is True
    assert play_rule.handler_params["post_play_drop_opponent_rest_ignores_barrier"] is True
    assert "yellow" in str(play_rule.handler_params.get("requires_leader", "")).lower()
    assert play_rule.handler_params["min_owner_energy"] == 4
    negate_rule = next(
        r
        for r in rules
        if r.handler_id
        == "activate_negate_opponent_leader_skills_and_restrict_up_to_n_opponent_rest_cards_switch_active_until_opponent_turn_end"
    )
    assert negate_rule.trigger == "self_activate_main"
    assert negate_rule.handler_params["max_targets"] == 1


def test_extract_super_17_ultimate_masterpiece_rules() -> None:
    card = _card(
        "[Blocker] "
        "[Activate: Battle][Limit 1](1), if your opponent has 3 or more energy and you have 1 or more <Android 17> card and 1 or more <Hell Fighter 17> card in your Combo Area: "
        "Draw 1 card, play this card from your hand, and this card gains [Barrier] until the end fo your opponent's turn. "
        "[Activate: Battle][Once per turn] (1), place 1 ≪Android≫ card from your Z-Energy under this card: "
        "Draw 1 card, switch this card to Active Mode, then choose up to 1 of your opponent's Battle Cards and it gets -20000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    first_rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_battle"
        and r.handler_id == "activate_draw_n_play_self_from_hand_and_gain_keyword_until_opponent_turn_end"
    )
    assert first_rule.handler_params["amount"] == 1
    assert first_rule.handler_params["grant_keyword"] == "Barrier"
    assert first_rule.handler_params["min_opponent_energy"] == 3
    assert first_rule.handler_params["required_owner_combo_required_characters_each"] == "Android 17|Hell Fighter 17"
    second_rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_battle"
        and r.handler_id == "activate_switch_self_active_and_power_reduce_up_to_n_opponent_battle_for_turn"
    )
    assert second_rule.handler_params["amount"] == 1
    assert second_rule.handler_params["max_targets"] == 1
    assert second_rule.handler_params["power_delta"] == -20000


def test_extract_owner_card_placed_under_named_host_can_rest_opponent_battle_rule() -> None:
    card = _card(
        "[Auto][Once per turn] When a card is placed under a {Spirit Bomb} in your Battle Area, "
        "choose up to 1 of your opponent's Battle Cards and switch it to Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_card_placed_under_owner_card"
        and r.handler_id == "auto_switch_up_to_n_opponent_board_rest"
    )
    assert rule.handler_params["required_host_zone"] == "battle"
    assert rule.handler_params["host_name_contains"] == "SPIRIT BOMB"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["target_card_types"] == "BATTLE"


def test_extract_self_placed_under_owner_card_can_switch_owner_board_to_revealed_rule() -> None:
    card = _card(
        "[Auto][Limit 1] When this card is placed under a <Vegito> card with a [Union] skill, "
        "choose up to 1 of your cards and switch it to Revealed Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_placed_under_owner_card"
        and r.handler_id == "auto_switch_up_to_n_owner_board_to_revealed_on_placed_under"
    )
    assert rule.handler_params["required_host_zone"] == "battle"
    assert rule.handler_params["host_required_card_type"] == "BATTLE"
    assert rule.handler_params["host_required_characters"] == "Vegito"
    assert rule.handler_params["host_required_skill_text_contains"] == "[union"
    assert rule.handler_params["max_targets"] == 1


def test_extract_self_placed_under_by_union_can_rest_opponent_battle_rule() -> None:
    card = _card(
        "[Auto] When this card is placed under another card by [Union], choose up to 1 of your opponent's Battle Cards, ignoring [Barrier], and switch it to Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_placed_under_by_union"
        and r.handler_id == "auto_switch_up_to_n_opponent_board_rest"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["target_card_types"] == "BATTLE"
    assert rule.handler_params["ignores_barrier"] is True


def test_extract_exact_ss2_trunks_future_on_the_line_rules() -> None:
    card = _card(
        "[Barrier][Blocker]<br>"
        "[EX-Evolve]((Yellow)), draw 1 card: Yellow <Trunks: Future> with an energy cost of 1.<br>"
        "[Auto] When this card is played using [EX-Evolve], switch it to Active Mode.<br>"
        "[Auto][Once per turn] If your Leader Card is a yellow <Trunks: Future> card: "
        "When your opponent plays a Battle Card or Unison Card, choose it and switch it to Rest Mode."
    )
    rules = extract_effect_rules_from_card(card)
    switch_rule = next(
        r
        for r in rules
        if r.trigger == "self_played" and r.handler_id == "auto_switch_self_active_on_play"
    )
    assert switch_rule.handler_params["requires_played_via"] == "ex_evolve"
    rest_rule = next(
        r
        for r in rules
        if r.trigger == "owner_opponent_battle_played"
        and r.handler_id == "auto_switch_up_to_n_opponent_board_rest"
    )
    assert rest_rule.handler_params["max_targets"] == 1
    assert rest_rule.handler_params["target_card_types"] == "BATTLE,UNISON"
    assert rest_rule.handler_params["leader_required_traits"] == "Trunks: Future"
    assert rest_rule.handler_params["leader_allowed_colors"] == "yellow"


def test_extract_exact_attack_of_the_dark_empire_rule() -> None:
    card = SimpleNamespace(
        card_skill_unstyled=(
            "[Activate: Main] If your Leader Card is a black \u226aDemon Realm Race\u226b card: "
            "Look at up to 7 cards from the top of your deck, then choose one?"
            "\u30fbAdd up to 1 black \u226aEvil Wizard\u226b, black \u226aDemon Realm Race\u226b, or black \u226aDemon God\u226b card among them to your hand, then shuffle your deck."
            "\u30fbIf you have no Unison Cards in play, play up to 1 black Unison Card with no specified cost and 20000 power among them with a marker on it, then shuffle your deck."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_extra_from_hand"
        and r.handler_id == "activate_look_top_choose_add_to_hand_or_play_unison_with_marker"
    )
    assert rule.handler_params["look_count"] == 7
    assert rule.handler_params["max_add"] == 1
    assert rule.handler_params["marker_count"] == 1
    assert rule.handler_params["leader_allowed_colors"] == "black"
    assert rule.handler_params["leader_required_traits"] == "Demon Realm Race"


def test_extract_self_placed_under_by_union_can_schedule_opponent_next_main_energy_restand_rule() -> None:
    card = _card(
        "[Auto] When this card is placed under another card by [Union], activate this skill. "
        "At the beginning of your opponent's next Main Phase, choose up to 1 of your blue energy and switch it to Active Mode."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_placed_under_by_union"
        and r.handler_id == "auto_schedule_switch_up_to_n_owner_energy_active_on_opponent_next_main_phase_on_placed_under_by_union"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "blue"


def test_extract_exact_chilleds_army_reinforcements_counter_token_rule() -> None:
    card = _card(
        "[Counter: Attack] If your Leader Card is mono-blue: Negate the attack, then play 1 Chilled's Army Token with 10000 power; "
        "it gains [Blocker] for the turn.<br>"
        "[Permanent] If your life is at 5 or less, you can activate this card's [Counter] skill from your hand by adding 1 card from your life to your hand instead of paying its energy cost."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "counter_play_token_in_battle")
    assert token_rule.handler_params["token_name"] == "chilled's army token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["temporary_keywords"] == "blocker"
    assert token_rule.handler_params["requires_leader"] == "if your leader card is mono-blue"


def test_extract_exact_frieza_army_reinforcements_counter_token_rule() -> None:
    card = _card(
        "[Counter: Attack] If your Leader Card is mono-yellow: Negate the attack, then play 1 Frieza's Army Token with 10000 power and it gains [Blocker] for the turn.<br>"
        "[Permanent] If your life is at 5 or less, you can activate this card's [Counter] skill from your hand by adding 1 card from your life to your hand instead of paying its energy cost."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "counter_play_token_in_battle")
    assert token_rule.handler_params["token_name"] == "frieza's army token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["temporary_keywords"] == "blocker"
    assert token_rule.handler_params["requires_leader"] == "if your leader card is mono-yellow"


def test_extract_exact_testing_the_opposition_counter_token_rule() -> None:
    card = _card(
        "[Counter: Attack] If your Leader Card is mono-red: Negate the attack, then play 1 Saibaiman Token. "
        "(Saibaiman Tokens have 5000 power, 0 combo cost, and 5000 combo power.) That Token gains [Blocker] for the turn.<br>"
        "[Permanent] If your life is at 5 or less, you can activate this card's [Counter] skill from your hand by adding 1 card from your life to your hand instead of paying its energy cost."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "counter_play_token_in_battle")
    assert token_rule.handler_params["token_name"] == "saibaiman token"
    assert token_rule.handler_params["power"] == 5000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000
    assert token_rule.handler_params["temporary_keywords"] == "blocker"


def test_extract_exact_invasion_of_chilleds_army_counter_token_rule() -> None:
    card = _card("[Counter: Attack] Negate the attack, then play 1 Chilled's Army Token with 10000 power.")
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "counter_play_token_in_battle")
    assert token_rule.handler_params["token_name"] == "chilled's army token"
    assert token_rule.handler_params["power"] == 10000
    assert "temporary_keywords" not in token_rule.handler_params


def test_extract_exact_bt2_chilled_attack_token_rule() -> None:
    card = _card(
        "[Auto] When this card attacks, play 1 Chilled's Army token. (Chilled's Army token has 10000 power) <br>"
        "[Awaken] When your life is at 6 or less: You may draw 2 cards and flip this card over."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_attack")
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "chilled's army token"
    assert token_rule.handler_params["power"] == 10000


def test_extract_exact_bt13_chilled_attack_life_then_token_rule() -> None:
    card = _card(
        "[Permanent] All of your Chilled's Army Tokens gain the following effect:<br>"
        "・ [Permanent] This card gains ≪Chilled's Army≫.<br>"
        "[Auto] When this card attacks, add up to 1 card from your life to your hand, then play a Chilled's Army Token with 10000 power.<br>"
        "[Awaken] When your life is at 3 or less: You may draw 2 cards, switch up to 1 of your energy to Active Mode, then flip this card over."
    )
    rules = extract_effect_rules_from_card(card)
    life_rule = next(rule for rule in rules if rule.handler_id == "auto_add_up_to_n_from_owner_life_to_hand_on_attack")
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_attack")
    assert life_rule.handler_params["max_targets"] == 1
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "chilled's army token"
    assert token_rule.handler_params["power"] == 10000


def test_extract_leader_attack_life_then_draw_with_awaken_clause() -> None:
    card = replace(
        _card(
            "[Auto] When this card attacks a Leader Card, you may choose 1 card in your life and add it to your hand. If you do so, draw 1 card.<br>"
            "[Awaken] When your life is at 4 or less: Choose up to 1 of your energy, switch it to Active Mode, and flip this card over."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_leader_attacks"
        and r.handler_id == "auto_add_up_to_n_from_owner_life_to_hand_then_draw_n_on_owner_leader_attack"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["draw_count"] == 1
    assert not any(r.trigger == "self_attacks" and r.handler_id == "auto_draw_n" for r in rules)


def test_extract_leader_attack_discard_matching_hand_then_draw_with_awaken_clause() -> None:
    card = replace(
        _card(
            "[Auto] When this card attacks a Leader Card, you may choose 1 ≪Universe 11≫ in your hand and place it in your Drop Area. If you do so, draw 2 cards.<br>"
            "[Awaken] When your life is at 4 or less: You may choose up to 2 of your energy, switch them to Active Mode, and flip this card over."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_leader_attacks"
        and r.handler_id == "auto_place_up_to_n_matching_from_owner_hand_into_drop_then_draw_n_on_owner_leader_attack"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["draw_count"] == 2
    assert rule.handler_params["required_traits"] == "Universe 11"
    assert not any(r.trigger == "self_attacks" and r.handler_id == "auto_draw_n" for r in rules)


def test_extract_leader_attack_discard_matching_hand_then_draw_from_hand_variant() -> None:
    card = replace(
        _card(
            "[Auto] When this card attacks a Leader Card, you may choose 1 Battle Card from your hand and place it in your Drop Area. If you do so, draw 2 cards.<br>"
            "[Awaken] When your life is at 4 or less: You may choose up to 2 of your energy, switch them to Active Mode, and flip this card over."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_leader_attacks"
        and r.handler_id == "auto_place_up_to_n_matching_from_owner_hand_into_drop_then_draw_n_on_owner_leader_attack"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["draw_count"] == 2
    assert rule.handler_params["required_card_type"] == "BATTLE"


def test_extract_owner_battle_attack_gain_power_then_add_dragon_ball_from_deck_or_life() -> None:
    card = replace(
        _card(
            "[Auto][Once per turn] When one of your Battle Cards attacks, it gets +5000 power for the duration of the turn, "
            "then choose up to 1 [Dragon Ball] card from your deck or life and add it to your hand. "
            "Then shuffle any areas you looked through.<br>"
            "[Wish] When there are 7 [Dragon Ball] cards in your Drop Area: Choose up to 1 ≪Desire≫ card in your Drop Area, add it to your hand, and flip this card over."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_battle_attacks"
        and r.handler_id == "auto_owner_battle_gain_power_then_add_up_to_n_matching_from_owner_deck_or_life_to_hand_on_attack"
    )
    assert rule.handler_params["power_delta"] == 5000
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["source_pool"] == "deck_or_life"
    assert rule.handler_params["required_runtime_labels"] == "dragon ball"
    assert rule.handler_params["shuffle_searched_zones"] is True


def test_extract_bt16_zamasu_attack_add_dragon_ball_from_deck_and_or_life() -> None:
    card = replace(
        _card(
            "<Badge variant=\"blue\">Auto</Badge> When this card attacks, add up to 2 <Badge variant=\"red\">Dragon Ball</Badge> cards from your deck and/or life to your hand; shuffle any areas you looked through using this skill.\r\n"
            "<Badge variant=\"yellow\">Wish</Badge> When your life is at 3 or less or there are 7 <Badge variant=\"red\">Dragon Ball</Badge> cards in your Drop Area: Draw 1 card, then place all <Badge variant=\"red\">Dragon Ball</Badge> cards from your Drop Area at the bottom of your deck in any order and flip this card over."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "owner_leader_attacks"
        and r.handler_id == "auto_add_up_to_n_matching_from_owner_deck_or_life_to_hand_on_owner_leader_attack"
    )
    assert rule.handler_params["max_targets"] == 2
    assert rule.handler_params["source_pool"] == "deck_or_life"
    assert rule.handler_params["required_runtime_labels"] == "dragon ball"
    assert rule.handler_params["shuffle_searched_zones"] is True


def test_extract_bt15_universe_6_combination_counter_and_activate_rules() -> None:
    card = replace(
        _card(
            "<Badge variant=\"green\">Counter: Attack</Badge> Negate the attack. If your Leader Card is a ≪Universe 6≫ card, play up to 1 ≪Universe 6≫ card with an energy cost of 1 from your Drop Area with its skills negated for the turn.<br />"
            "<Badge variant=\"orange\">Activate: Main</Badge><img src=\"/assets/img/dbs_masters/card_parts/blue_ball.png\" alt=\"\" class=\"colorCostBall\">, if your Leader Card is a ≪Universe 6≫ card: Choose all of your Battle Cards with both ≪Saiyan≫ and ≪Universe 6≫ and they get +5000 power for the turn."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(r for r in rules if r.trigger == "counter_attack" and r.handler_id == "counter_play_up_to_n_from_owner_drop_negate_skills_for_turn")
    assert counter_rule.handler_params["max_targets"] == 1
    assert counter_rule.handler_params["max_cost"] == 1
    assert counter_rule.handler_params["required_traits"] == "Universe 6"
    assert counter_rule.handler_params["required_leader_traits"] == "Universe 6"
    activate_rule = next(
        r
        for r in rules
        if r.trigger == "self_activate_extra_from_hand"
        and r.handler_id == "activate_buff_owner_battle_cards"
        and r.handler_params.get("required_all_traits") == "Saiyan,Universe 6"
    )
    assert activate_rule.handler_params["target_policy"] == "all"
    assert activate_rule.handler_params["power_delta"] == 5000


def test_extract_self_aegis_mill_if_no_other_matching_owner_battle() -> None:
    card = _card(
        "[Barrier]<br>"
        "[Aegis Blue/Yellow][Once per turn] (If it's your opponent's turn, you can activate this during the Defense Step by placing cards in your hand in your Drop Area that match all colors specified by [Aegis]: Choose up to 2 of your energy and switch them to Active Mode.)<br>"
        "[Energy-Exhaust] (If this card is placed in an Energy Area from any area, it must be placed there in Rest Mode.)<br>"
        "[Auto] When this card activates [Aegis], if there are no ≪Evil Incarnate≫ cards in play in your Battle Area other than this card, place 1 card from the top of your opponent's deck in their Drop Area."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "self_aegis_activated"
        and r.handler_id == "auto_place_top_n_from_opponent_deck_into_drop_on_aegis"
    )
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["required_no_other_owner_traits"] == "Evil Incarnate"


def test_extract_on_play_add_matching_red_extra_without_keywords_from_drop_to_hand() -> None:
    card = _card(
        "[Auto] When this card is played, add up to 1 red Extra Card with an energy cost of 1 and no keyword skills from your Drop Area to your hand.<br>"
        "[Auto] When this card is discarded from your hand by a [Union-Fusion] skill, add up to 1 card from your life to your hand."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_add_up_to_n_from_owner_drop_to_hand_on_play")
    assert rule.trigger == "self_played"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "red"
    assert rule.handler_params["required_card_type"] == "EXTRA"
    assert rule.handler_params["max_cost"] == 1
    assert rule.handler_params["requires_no_keywords"] is True


def test_extract_when_discarded_by_union_fusion_can_add_life_to_hand() -> None:
    card = _card(
        "[Auto] When this card is played, add up to 1 red Extra Card with an energy cost of 1 and no keyword skills from your Drop Area to your hand.<br>"
        "[Auto] When this card is discarded from your hand by a [Union-Fusion] skill, add up to 1 card from your life to your hand."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_add_up_to_n_from_owner_life_to_hand_on_hand_drop")
    assert rule.trigger == "self_in_hand_sent_to_drop_or_warp"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_destination_zone"] == "drop"
    assert rule.handler_params["required_drop_causes"] == "union_fusion"


def test_extract_exact_cell_pursuit_of_despair_plays_up_to_two_cell_jr_tokens_and_buffs_them() -> None:
    card = _card(
        "[Double Strike]<br>"
        "[Auto] When this card is played from your hand, play up to 2 Cell Jr. Tokens (10000 power, 0 combo cost, and 5000 combo power), "
        "and those cards get +5000 power for the turn.<br>"
        "[Activate: Main][Limit 1](Green)(Green), if your Leader is green and your opponent has 3 or more energy: Play this card from your hand.<br>"
        "[Activate: Main] If you or your opponent removes 1 token with combo power from the game: Remove 2 markers from your opponent's Unison."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_play")
    assert token_rule.handler_params["requires_played_from"] == "hand"
    assert token_rule.handler_params["amount"] == 2
    assert token_rule.handler_params["token_name"] == "cell jr. token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["combo_cost"] == 0
    assert token_rule.handler_params["combo_power"] == 5000
    assert token_rule.handler_params["post_created_tokens_power_delta"] == 5000


def test_extract_exact_bulma_sacrifice_draws_then_plays_earthling_token() -> None:
    card = _card(
        "[Auto] If your Leader is a green card with both <Trunks: Future> and <Mai: Future>: "
        "When this card is played, draw 1 card, then play 1 Earthling Token (1000 power, 0 combo cost, and 0 combo power).<br>"
        "[Auto] When one of your opponent's multicolor ≪God≫ cards attacks, place this card in your Drop, then negate the attack."
    )
    rules = extract_effect_rules_from_card(card)
    draw_rule = next(rule for rule in rules if rule.handler_id == "auto_draw_n")
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_play_token_in_battle_on_play")
    assert draw_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "earthling token"
    assert token_rule.handler_params["power"] == 1000


def test_extract_exact_android_21_total_audacity_draws_then_schedules_clone_token() -> None:
    card = _card(
        "[Deflect][Double Strike]<br>"
        "[Auto][Limit 1] When this card is played, draw 2 cards, and at the end of your opponent's next turn, "
        "play 1 Clone Token with 10000 power in your opponent's Battle Area."
    )
    rules = extract_effect_rules_from_card(card)
    draw_rule = next(rule for rule in rules if rule.handler_id == "auto_draw_n")
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_schedule_play_token_in_battle_on_play")
    assert draw_rule.handler_params["amount"] == 2
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "clone token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["controller_player_scope"] == "opponent"
    assert token_rule.handler_params["trigger_player_scope"] == "opponent"


def test_extract_exact_unstoppable_technique_restands_blue_energy_then_schedules_clone_token() -> None:
    card = _card(
        "[Counter: Attack] If your Leader is a blue â‰ªAndroidâ‰« card: Negate the attack and switch up to 1 of your blue energy to Active Mode. "
        "Additionally, at the end of the turn, play 1 Clone Token with 10000 power in your opponent's Battle Area."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "counter_schedule_play_token_in_battle")
    assert token_rule.handler_params["token_name"] == "clone token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["controller_player_scope"] == "opponent"
    assert token_rule.handler_params["switch_owner_energy_active_max_targets"] == 1
    assert token_rule.handler_params["switch_owner_energy_active_allowed_colors"] == "blue"


def test_extract_exact_frieza_invader_from_another_dimension_adds_life_then_schedules_token() -> None:
    card = _card(
        "[+1][Activate: Main] Add up to 1 card from your life to your hand; at the end of the turn, play 1 Frieza's Army Token with 10000 power."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "activate_schedule_play_token_in_battle")
    assert token_rule.handler_params["token_name"] == "frieza's army token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["add_from_life_to_hand_max_targets"] == 1
    assert token_rule.handler_params["trigger_kind"] == "turn_end"


def test_extract_exact_android_21_mandatory_gathering_searches_then_schedules_clone_token() -> None:
    card = _card(
        "[Auto] If your Leader is an â‰ªAndroidâ‰« card: When this card is played, look at up to 5 cards from the top of your deck, "
        "add up to 1 blue â‰ªAndroidâ‰« card with an energy cost of 5 or less among them to your hand, shuffle your deck, and at the end of your opponent's next turn, "
        "play 1 Clone Token with 10000 power in your opponent's Battle Area.<br>"
        "[Auto] If your Leader is a blue â‰ªAndroidâ‰« card: When this card is used in a combo from your hand, play 1 Clone Token in your opponent's Battle Area."
    )
    rules = extract_effect_rules_from_card(card)
    search_rule = next(rule for rule in rules if rule.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play")
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_schedule_play_token_in_battle_on_play")
    assert search_rule.handler_params["look_count"] == 5
    assert search_rule.handler_params["max_add"] == 1
    assert search_rule.handler_params["allowed_colors"] == "blue"
    assert search_rule.handler_params["required_traits"] == "Android"
    assert search_rule.handler_params["max_cost"] == 5
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "clone token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["controller_player_scope"] == "opponent"
    assert token_rule.handler_params["trigger_player_scope"] == "opponent"
    combo_token_rule = next(rule for rule in rules if rule.trigger == "self_comboed" and rule.handler_id == "auto_play_token_in_battle_on_combo")
    assert combo_token_rule.handler_params["amount"] == 1
    assert combo_token_rule.handler_params["token_name"] == "clone token"
    assert combo_token_rule.handler_params["requires_comboed_from"] == "hand"
    assert combo_token_rule.handler_params["controller_player_scope"] == "opponent"


def test_extract_exact_android_21_the_ringleader_draws_then_schedules_clone_token() -> None:
    card = _card(
        "[Auto] If your Leader Card is an â‰ªAndroidâ‰« card: When you play this card, draw 1 card, then at the end of your opponent's next turn, "
        "play 1 Clone Token with 10000 power in your opponent's Battle Area.<br>"
        "[Activate: Main][Once per turn](Blue)(Green), your Leader Card is an â‰ªAndroidâ‰« card: Choose 1 {Android 21's Scheme} in your Drop Area and activate it."
    )
    rules = extract_effect_rules_from_card(card)
    draw_rule = next(rule for rule in rules if rule.handler_id == "auto_draw_n")
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_schedule_play_token_in_battle_on_play")
    assert draw_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "clone token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["controller_player_scope"] == "opponent"
    activate_rule = next(
        rule for rule in rules
        if rule.trigger == "self_activate_main" and rule.handler_id == "activate_activate_up_to_n_named_field_extra_from_owner_drop"
    )
    assert activate_rule.handler_params["max_targets"] == 1
    assert activate_rule.handler_params["required_name_contains"] == "ANDROID 21'S SCHEME"
    assert activate_rule.handler_params["required_card_type"] == "EXTRA"
    assert activate_rule.handler_params["requires_field_keyword"] is True


def test_extract_exact_android_21_a_brilliant_idea_schedules_two_clone_tokens() -> None:
    card = _card(
        "[Auto] When you play this card, activate this skill. At the end of your opponent's next turn, play 2 Clone Tokens with 10000 power in your opponent's Battle Area.<br>"
        "[Activate: Main][Once per turn] Choose 1 Clone Token in your opponent's Battle Area and remove it from the game: Choose one-<br>"
        "ï½¥ Choose 1 of your opponent's Battle Cards and KO it. <br>"
        "ï½¥ Choose your Leader Card or 1 of your Battle Cards, and it gets +10000 power and [Critical] for the duration of the turn."
    )
    rules = extract_effect_rules_from_card(card)
    token_rule = next(rule for rule in rules if rule.handler_id == "auto_schedule_play_token_in_battle_on_play")
    assert token_rule.handler_params["amount"] == 2
    assert token_rule.handler_params["token_name"] == "clone token"
    assert token_rule.handler_params["power"] == 10000
    assert token_rule.handler_params["controller_player_scope"] == "opponent"
    assert token_rule.handler_params["trigger_player_scope"] == "opponent"


def test_extract_exact_android_21_a_brilliant_idea_can_ko_on_choice_branch() -> None:
    card = _card(
        "[Auto] When you play this card, activate this skill. At the end of your opponent's next turn, play 2 Clone Tokens with 10000 power in your opponent's Battle Area.<br>"
        "[Activate: Main][Once per turn] Choose 1 Clone Token in your opponent's Battle Area and remove it from the game: Choose one-<br>"
        "ï½¥ Choose 1 of your opponent's Battle Cards and KO it. <br>"
        "ï½¥ Choose your Leader Card or 1 of your Battle Cards, and it gets +10000 power and [Critical] for the duration of the turn."
    )
    rules = extract_effect_rules_from_card(card)
    ko_rule = next(rule for rule in rules if rule.trigger == "self_activate_main" and rule.handler_id == "activate_ko_up_to_n_opponent_battle")
    assert ko_rule.handler_params["max_targets"] == 1
    assert ko_rule.handler_params["target_policy"] == "first"


def test_extract_exact_android_21_a_brilliant_idea_can_buff_leader_or_battle_on_choice_branch() -> None:
    card = _card(
        "[Auto] When you play this card, activate this skill. At the end of your opponent's next turn, play 2 Clone Tokens with 10000 power in your opponent's Battle Area.<br>"
        "[Activate: Main][Once per turn] Choose 1 Clone Token in your opponent's Battle Area and remove it from the game: Choose one-<br>"
        "ï½¥ Choose 1 of your opponent's Battle Cards and KO it. <br>"
        "ï½¥ Choose your Leader Card or 1 of your Battle Cards, and it gets +10000 power and [Critical] for the duration of the turn."
    )
    rules = extract_effect_rules_from_card(card)
    buff_rule = next(rule for rule in rules if rule.trigger == "self_activate_main" and rule.handler_id == "activate_buff_owner_battle_cards")
    assert buff_rule.handler_params["target_scope"] == "owner_cards"
    assert buff_rule.handler_params["max_targets"] == 1
    assert buff_rule.handler_params["power_delta"] == 10000
    assert buff_rule.handler_params["grant_keyword"] == "Critical"


def test_extract_exact_android_21_scholarly_gambit_requires_no_copy_in_battle() -> None:
    card = _card(
        "[Blocker]<br>[Barrier]<br>[Activate: Main] If a copy of this card isn't in play in your Battle Area, choose 1 Clone Token in your opponent's Battle Area and remove it from the game: Play this card from your hand.<br>"
        "[Auto] If you have 5 or more energy and place this card in its owner's Drop Area: When your opponent plays a Battle Card with an energy cost greater than their current energy, you may choose that Battle Card and place it at the bottom of its owner's deck."
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(rule for rule in rules if rule.trigger == "self_activate_main" and rule.handler_id == "activate_play_self_from_hand")
    assert play_rule.handler_params["requires_no_owner_battle_with_source_card_id"] is True


def test_extract_exact_the_android_creator_draws_and_buffs_owner_battle_only() -> None:
    card = replace(
        _card(
            "[Activate: Main] Choose 1 Clone Token in your opponent's Battle Area and remove it from the game: Draw 1 card, then choose 1 of your Battle Cards and it gets +10000 power for the duration of the turn."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    buff_rule = next(rule for rule in rules if rule.trigger == "self_activate_extra_from_hand" and rule.handler_id == "activate_buff_owner_battle_cards")
    assert not any(rule.trigger == "self_activate_extra_from_hand" and rule.handler_id == "auto_draw_n" for rule in rules)
    assert buff_rule.handler_params["amount"] == 1
    assert buff_rule.handler_params["target_scope"] == "owner_battle"
    assert buff_rule.handler_params["max_targets"] == 1
    assert buff_rule.handler_params["power_delta"] == 10000
    assert "required_traits" not in buff_rule.handler_params


def test_extract_exact_mai_link_of_hope_draws_and_activate_main_plays_earthling_token() -> None:
    card = _card(
        "[Auto] When this card is played, draw 1 card.<br>"
        "[Activate: Main][Limit 1] If your Leader is a green card with both <Trunks: Future> and <Mai: Future> and you switch this card to Rest Mode: "
        "Play 1 Earthling Token (1000 power, 0 combo cost, and 0 combo power)."
    )
    rules = extract_effect_rules_from_card(card)
    draw_rule = next(rule for rule in rules if rule.handler_id == "auto_draw_n")
    token_rule = next(rule for rule in rules if rule.handler_id == "activate_play_token_in_battle")
    assert draw_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["amount"] == 1
    assert token_rule.handler_params["token_name"] == "earthling token"
    assert token_rule.handler_params["power"] == 1000
    assert "rest_mode_only" not in token_rule.handler_params


def test_extract_negative_energy_two_star_ball_can_send_self_to_drop_and_play_named_from_deck_or_hand() -> None:
    card = _card(
        "[Permanent] This card can't attack and isn't affected by your opponent's skills.<br>"
        "[Activate: Main](Yellow), if your Leader Card is a ≪Shadow Dragon≫ card and you place this card in its owner's Drop Area: "
        "Choose up to 1 <Haze Shenron> card with an energy cost of 2 or 3 in your deck or hand, play it, then shuffle your deck if you looked through it."
    )
    rules = extract_effect_rules_from_card(card)
    noop_rule = next(rule for rule in rules if rule.trigger == "self_played" and rule.handler_id == "noop_auto")
    assert "can't attack and isn't affected by your opponent's skills" in noop_rule.source_text.lower()
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "activate_play_up_to_n_from_owner_deck_or_hand_after_self_to_drop"
    )
    assert rule.handler_params["leader_required_traits"] == "Shadow Dragon"
    assert rule.handler_params["required_characters"] == "Haze Shenron"
    assert rule.handler_params["allowed_costs"] == "2,3"
    assert rule.handler_params["min_cost"] == 2
    assert rule.handler_params["max_cost"] == 3


def test_extract_get_that_monster_choose_one_branches() -> None:
    card = replace(
        _card(
            "[Activate: Battle][Limit 1] If your Leader Card is a red â‰ªShenronâ‰« card: Choose one-<br>"
            "ãƒ»Add up to 1 [Dragon Ball] card from your deck to your hand, then shuffle your deck.<br>"
            "ãƒ»Add up to 1 red â‰ªDesireâ‰« card with an energy cost of 1 or 2 from your deck to your hand, then shuffle your deck."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    dragon_ball_rule = next(
        rule for rule in rules
        if rule.trigger == "self_activate_battle"
        and rule.handler_id == "activate_add_up_to_n_from_owner_deck_to_hand"
        and rule.handler_params.get("required_runtime_labels") == "dragon ball"
    )
    assert dragon_ball_rule.handler_params["max_targets"] == 1
    desire_rule = next(
        rule for rule in rules
        if rule.trigger == "self_activate_battle"
        and rule.handler_id == "activate_add_up_to_n_from_owner_deck_to_hand"
        and rule.handler_params.get("required_traits") == "Desire"
    )
    assert desire_rule.handler_params["allowed_colors"] == "red"
    assert desire_rule.handler_params["allowed_costs"] == "1,2"


def test_extract_king_kais_training_places_self_under_host_then_adds_goku() -> None:
    card = replace(
        _card(
            "[Activate: Main] Choose 1 {King Kai's Planet} in your Battle Area: "
            "Place this card under the chosen card, add up to 1 {Son Goku, Confronting Invasion} from your deck to your hand, then shuffle your deck."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "activate_place_self_under_matching_owner_battle_then_add_up_to_n_from_owner_deck_to_hand"
    )
    assert rule.handler_params["required_owner_battle_required_name_contains"] == "KING KAI'S PLANET"
    assert rule.handler_params["required_name_contains"] == "SON GOKU, CONFRONTING INVASION"


def test_extract_scout_rests_active_opponent_else_gains_control() -> None:
    card = _card(
        "[Activate: Main] If your Leader Card is yellow or a â‰ªTurles Crusher Corpsâ‰« card and you choose 1 of your opponent's cards in Active Mode: "
        "Your opponent may switch the chosen card to Rest Mode. If they don't, choose up to 1 of your opponent's Battle Cards and gain control of it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "activate_rest_opponent_active_else_gain_control_opponent_battle"
    )
    assert rule.handler_params["leader_or_allowed_colors"] == "yellow"
    assert rule.handler_params["leader_or_required_traits"] == "Turles Crusher Corps"


def test_extract_chiaotzu_warps_self_then_opponent_chooses_non_saiyan_for_ko() -> None:
    card = _card(
        "[Activate: Main] Send this card to its owner's Warp: Your opponent chooses 1 of their Battle Cards; if it's a non-â‰ªSaiyanâ‰« card, KO it."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "activate_send_self_to_warp_then_opponent_choose_battle_ko_if_not_trait"
    )
    assert rule.handler_params["excluded_trait"] == "Saiyan"


def test_extract_p338_raditz_attack_and_search_rules() -> None:
    card = replace(
        _card(
            "[Auto] When this card attacks, your opponent chooses 1 card in their hand and sends it to their Warp.<br>"
            "[Activate: Main][Once per turn] Look at up to 5 cards from the top of your deck, choose up to 1 red or green &lt;Raditz&gt;, &lt;Vegeta&gt;, or &lt;Nappa&gt; card among them and add it to your hand, shuffle your deck, and if you added a card to your hand, choose 1 card in your hand and discard it."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    attack_rule = next(
        rule for rule in rules
        if rule.trigger == "self_attacks"
        and rule.handler_id == "auto_send_up_to_n_opponent_hand_to_warp_on_play"
    )
    assert attack_rule.handler_params["max_targets"] == 1
    search_rule = next(
        rule for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play"
    )
    assert search_rule.handler_params["look_count"] == 5
    assert set(str(search_rule.handler_params["allowed_colors"]).split(",")) == {"red", "green"}
    assert set(str(search_rule.handler_params["required_characters"]).split(",")) == {"Raditz", "Vegeta", "Nappa"}
    assert search_rule.handler_params["discard_after_add"] == 1


def test_extract_erase_a_universe_damage_and_battle_buff_rules() -> None:
    card = replace(
        _card(
            "[Activate: Main]((Red))((Blue))((Green))((Yellow))(1), if your Leader Card is a &lt;Great Priest&gt; card: "
            "Deal 1 damage to your opponent for every 2 colors on ≪God≫ cards in your Battle Area. (2 damage max.) "
            "Additionally, if you have 12 or more multicolor ≪God≫ cards in play, you win the game.<br>"
            "[Activate: Battle] Choose up to 1 ≪God≫ card and it gets +6000 power for the battle."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    damage_rule = next(
        rule for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "activate_deal_damage_to_opponent_per_owner_matching_battle_colors_and_optionally_win"
    )
    assert damage_rule.handler_params["leader_required_characters"] == "Great Priest"
    assert damage_rule.handler_params["damage_per"] == 1
    assert damage_rule.handler_params["colors_per_damage"] == 2
    assert damage_rule.handler_params["required_owner_battle_traits"] == "God"
    assert damage_rule.handler_params["max_damage"] == 2
    assert damage_rule.handler_params["win_if_owner_in_play_matching_count_at_least"] == 12
    buff_rule = next(
        rule for rule in rules
        if rule.trigger == "self_activate_battle"
        and rule.handler_id == "activate_gain_power_and_keyword_for_battle"
    )
    assert buff_rule.handler_params["power_delta"] == 6000
    assert buff_rule.handler_params["target_scope"] == "owner_cards"
    assert buff_rule.handler_params["required_traits"] == "God"


def test_extract_bt15_vegeta_leader_from_badge_html() -> None:
    card = replace(
        _card(
            '<Badge variant="blue">Auto</Badge><Badge variant="red">Once per turn</Badge> '
            "If it's your opponent's turn: When one of your Battle Cards is removed from your Battle Area by an opponent's skill, "
            "your opponent chooses 1 card in their hand and discards it.<br />"
            '<Badge variant="orange">Activate: Battle</Badge><Badge variant="red">Once per turn</Badge> '
            "If your life is less than or equal to your opponent's, this card gets +5000 power for the battle.<br />"
            '<Badge variant="yellow">Awaken</Badge> '
            "When your life is at 3 or less or your opponent's Leader Card's back is facing up: "
            "You may draw 2 cards, choose up to 1 of your opponent's Unison Cards and remove a marker from it, then flip this card over."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    auto_rule = next(
        rule
        for rule in rules
        if rule.trigger == "owner_card_left_battle_area"
        and rule.handler_id == "auto_opponent_discards_n_from_hand_on_owner_matching_battle_left"
    )
    assert auto_rule.handler_params["amount"] == 1
    assert auto_rule.handler_params["event_removed_by_opponent_skill"] is True
    assert auto_rule.handler_params["requires_opponent_turn"] is True
    buff_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_battle"
        and rule.handler_id == "activate_gain_power_and_keyword_for_battle"
    )
    assert buff_rule.handler_params["power_delta"] == 5000
    assert buff_rule.handler_params["requires_owner_life_less_or_equal_opponent"] is True


def test_extract_bt16_son_gohan_interceptor_from_badge_html() -> None:
    card = replace(
        _card(
            '<Badge variant="red">Barrier</Badge>\r <Badge variant="blue">Auto</Badge><Badge variant="red">Once per turn</Badge> '
            "Switch this card to Rest Mode: When you take damage from an opponent's attack, switch up to 1 of your blue energy to Active Mode, "
            "then choose up to 1 of your opponent's Battle Cards with an energy cost greater than their current energy and return it to its owner's hand."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    barrier_rule = next(rule for rule in rules if rule.trigger == "self_played" and rule.handler_id == "noop_auto")
    assert barrier_rule.source_text.lower() == "[barrier]"
    auto_rule = next(
        rule
        for rule in rules
        if rule.trigger == "owner_takes_damage_from_opponent_attack"
        and rule.handler_id == "auto_rest_self_switch_up_to_n_owner_energy_active_then_return_up_to_n_opponent_battle_to_hand_on_owner_damage"
    )
    assert auto_rule.handler_params["owner_energy_targets"] == 1
    assert auto_rule.handler_params["owner_energy_allowed_colors"] == "blue"
    assert auto_rule.handler_params["max_targets"] == 1
    assert auto_rule.handler_params["requires_cost_greater_than_opponent_current_energy"] is True


def test_extract_bt15_son_gohan_simian_revenge_from_badge_html() -> None:
    card = replace(
        _card(
            "[Blocker][Revenge]<br>"
            "[Auto][Limit 1](Green): When one of your green non-≪Great Ape≫ &lt;Son Gohan: Youth&gt; cards with [Blocker] "
            "is removed from your Battle Area by an opponent's skill, you may play this card from your hand."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(
        rule
        for rule in rules
        if rule.trigger == "owner_card_left_battle_area"
        and rule.handler_id == "auto_play_self_from_hand_on_owner_matching_battle_left"
    )
    assert play_rule.handler_params["event_allowed_colors"] == "green"
    assert play_rule.handler_params["event_required_characters"] == "son gohan: youth"
    assert play_rule.handler_params["event_required_keywords"] == "blocker"
    assert play_rule.handler_params["event_excluded_traits"] == "Great Ape"
    assert play_rule.handler_params["event_removed_by_opponent_skill"] is True


def test_extract_bt15_kale_universe_6_combination_from_badge_html() -> None:
    card = replace(
        _card(
            "[Counter: Attack] Negate the attack and play this card. <br>"
            "[Permanent] If your Leader Card is a \u226aUniverse 6\u226b card and it's your opponent's turn, reduce the energy cost of this card in your hand by 2.<br>"
            "[Auto] If your Leader Card is a blue &lt;Kale&gt; card: When this card is played, you may choose 1 card in your hand and discard it. "
            "If you do, your opponent can't attack with Battle Cards with energy costs greater than their current energy for the turn unless they choose 2 cards in their hand and place them at the bottom of their deck each time."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    permanent_rule = next(rule for rule in rules if rule.trigger == "self_played" and rule.handler_id == "noop_auto")
    assert "reduce the energy cost of this card in your hand by 2" in permanent_rule.source_text.lower()
    auto_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_discard_n_from_owner_hand_then_limit_opponent_high_cost_battle_attacks"
    )
    assert auto_rule.handler_params["discard_count"] == 1
    assert auto_rule.handler_params["opponent_hand_bottom_deck_count"] == 2
    assert auto_rule.handler_params["leader_allowed_colors"] == "blue"
    assert auto_rule.handler_params["leader_required_characters"] == "Kale"


def test_extract_exact_whis_stalwart_assistance_rules() -> None:
    card = replace(
        _card(
            "[Counter: Attack] Negate the attack and play this card.\n"
            "[Auto] During a battle in which one of your Battle Cards attacks an opponent's Battle Card: "
            "When this card is used in a combo, it gets +5000 combo power for the battle."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(rule for rule in rules if rule.trigger == "counter_attack" and rule.handler_id == "noop_auto")
    assert "negate the attack and play this card" in counter_rule.source_text.lower()
    combo_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_comboed" and rule.handler_id == "auto_self_gain_combo_power_on_combo"
    )
    assert combo_rule.handler_params["combo_power_delta"] == 5000
    assert combo_rule.handler_params["requires_owner_battle_attacking_opponent_battle"] is True


def test_extract_exact_dr_uiro_rebooting_for_revenge_rules() -> None:
    card = replace(
        _card(
            "[+1][Activate: Main] If your Leader Card is a green <Dr.Uiro> card, "
            "choose up to 1 <Dr.Kochin> or ≪Frenzied Warrior≫ card with an energy cost of 2 or less in your hand and play it.\n"
            "[-2][Activate: Main] Choose up to 1 <Dr.Uiro> card with an energy cost of 4 or less in your hand and play it. "
            "If you do, choose up to 2 of your opponent's Battle Cards with energy costs of 5 or less and place them under a {Dr.Uiro's Lab} in your Battle Area."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    plus_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "activate_play_up_to_n_name_or_trait_from_owner_hand"
    )
    assert plus_rule.handler_params["marker_delta"] == 1
    assert plus_rule.handler_params["max_cost"] == 2
    assert plus_rule.handler_params["required_name_contains_any"] == "DR.KOCHIN"
    assert plus_rule.handler_params["required_traits_any"] == "Frenzied Warrior"
    assert plus_rule.handler_params["leader_allowed_colors"] == "green"
    assert plus_rule.handler_params["leader_required_characters"] == "Dr.Uiro"
    assert plus_rule.handler_params["requires_effect_choice_match"] is True
    minus_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "activate_play_up_to_n_from_owner_hand_then_place_up_to_n_opponent_battle_under_named_host"
    )
    assert minus_rule.handler_params["marker_delta"] == -2
    assert minus_rule.handler_params["max_cost"] == 4
    assert minus_rule.handler_params["required_name_contains"] == "DR.UIRO"
    assert minus_rule.handler_params["place_max_targets"] == 2
    assert minus_rule.handler_params["place_max_cost"] == 5
    assert minus_rule.handler_params["host_required_name_contains"] == "DR.UIRO'S LAB"
    assert minus_rule.handler_params["requires_effect_choice_match"] is True


def test_extract_exact_son_goku_path_to_revival_rules() -> None:
    card = replace(
        _card(
            "[Auto] If your Leader Card is a ≪Shenron≫ card: When this card is played, "
            "add up to 1 [Dragon Ball] card from your deck or Drop Area to your hand, "
            "then shuffle your deck if you looked through it.\n"
            "[Activate: Main]((Green))((Green)), if your Leader Card is a green ≪Shenron≫ card "
            "and you place 7 [Dragon Ball] cards from your Drop Area under this card: "
            "Choose up to 1 {Twin Onslaught SS4 Son Goku} in your hand and play it on top of this card."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    auto_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_add_up_to_n_dragon_ball_from_owner_deck_or_drop_to_hand_on_play"
    )
    assert auto_rule.handler_params["max_targets"] == 1
    assert auto_rule.handler_params["required_runtime_labels"] == "dragon ball"
    assert auto_rule.handler_params["leader_required_traits"] == "Shenron"
    activate_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "activate_place_n_dragon_ball_from_owner_drop_under_self_then_play_named_from_owner_hand_on_top"
    )
    assert activate_rule.handler_params["drop_under_count"] == 7
    assert activate_rule.handler_params["required_name_contains"] == "TWIN ONSLAUGHT SS4 SON GOKU"
    assert activate_rule.handler_params["leader_allowed_colors"] == "green"
    assert activate_rule.handler_params["leader_required_traits"] == "Shenron"


def test_extract_exact_vegeta_fatherly_encouragement_rules() -> None:
    card = replace(
        _card(
            "[Counter: Attack] Negate the attack and play this card.\n"
            "[Auto] If it's your opponent's turn: When this card is used in a combo, "
            "choose up to 1 <Trunks: Future> card in your Battle Area and switch it to Active Mode."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(rule for rule in rules if rule.trigger == "counter_attack" and rule.handler_id == "noop_auto")
    assert "negate the attack and play this card" in counter_rule.source_text.lower()
    combo_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_comboed" and rule.handler_id == "auto_switch_up_to_n_owner_battle_active_on_combo"
    )
    assert combo_rule.handler_params["max_targets"] == 1
    assert combo_rule.handler_params["required_characters"] == "Trunks: Future"
    assert combo_rule.handler_params["requires_opponent_turn"] is True


def test_extract_exact_bt14_source_of_power_rules() -> None:
    card = replace(
        _card(
            "[Counter: Attack][Spirit Boost X] (Remove X markers from your Unison Card to activate this skill.) "
            "If your Leader Card is a red ≪Universe 11≫ card: Negate the attack, add up to 1 red <Jiren> card "
            "with an [Evolve] skill and an energy cost of 5 or less from your deck to your hand, then shuffle your deck. "
            "If you removed a marker from one of your red Unison Cards using this skill, choose up to 1 red ≪Universe 11≫ "
            "card with an energy cost of 1 in your Drop Area and play it in Rest Mode with its skills negated for the turn."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "counter_attack"
        and r.handler_id == "counter_add_up_to_n_from_owner_deck_to_hand_then_play_from_drop_if_spirit_boost"
    )
    assert rule.handler_params["max_add"] == 1
    assert rule.handler_params["add_required_characters"] == "Jiren"
    assert rule.handler_params["add_required_skill_text_contains"] == "[evolve]"
    assert rule.handler_params["add_max_cost"] == 5
    assert rule.handler_params["requires_spirit_boost_marker_removed"] is True
    assert rule.handler_params["play_required_traits"] == "Universe 11"
    assert rule.handler_params["play_exact_cost"] == 1
    assert rule.handler_params["play_resting"] is True
    assert rule.handler_params["leader_required_traits"] == "Universe 11"


def test_extract_exact_bt16_carefree_playtime_rules() -> None:
    card = replace(
        _card(
            "[Counter: Counter] If one of your blue <Beerus> cards is attacking an opponent's Battle Card: "
            "Negate the [Counter: Attack] and switch up to 1 of your blue energy to Active Mode."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    negate_rule = next(
        r
        for r in rules
        if r.trigger == "counter_attack"
        and r.handler_id == "counter_negate_counter_attack"
    )
    switch_rule = next(
        r
        for r in rules
        if r.trigger == "counter_attack"
        and r.handler_id == "counter_switch_up_to_n_owner_energy_active_if_owner_battle_attacking_opponent_battle"
    )
    assert "negate the [counter: attack]" in negate_rule.source_text.lower()
    assert switch_rule.handler_params["max_targets"] == 1
    assert switch_rule.handler_params["allowed_colors"] == "blue"


def test_extract_exact_bt17_instant_kamehameha_rules() -> None:
    card = replace(
        _card(
            "[Counter: Counter] If your Leader Card has <Son Goku> in its character name and is attacking: "
            "Switch 1 of your Leader Cards to Active Mode, and it gets +5000 power and has its skills negated for the turn.\n"
            "[Permanent] You can activate this card's [Counter] skill from your hand without paying its energy cost by paying the cost for [Spirit Boost 3] instead."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    switch_rule = next(
        r
        for r in rules
        if r.trigger == "counter_activated"
        and r.handler_id == "counter_switch_up_to_n_owner_leader_active"
    )
    buff_rule = next(
        r
        for r in rules
        if r.trigger == "counter_activated"
        and r.handler_id == "counter_buff_and_negate_owner_leader_for_turn_if_attacking"
    )
    permanent_rule = next(r for r in rules if r.trigger == "self_played" and r.handler_id == "noop_auto")
    assert switch_rule.handler_params["leader_required_characters"] == "Son Goku"
    assert buff_rule.handler_params["power_delta"] == 5000
    assert buff_rule.handler_params["negate_skills_for_turn"] is True
    assert "spirit boost 3" in permanent_rule.source_text.lower()


def test_extract_bt15_videl_call_of_justice_from_badge_html() -> None:
    card = replace(
        _card(
            "[Counter: Attack] Negate the attack and play this card. If a &lt;Son Gohan: Adolescence&gt; card is in play in your Battle Area, this card gains [Blocker] for the turn.<br>"
            "[Permanent][Bond 2] \u226aHeroine\u226b: This card gets +9000 power."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    permanent_rule = next(rule for rule in rules if rule.trigger == "self_played" and rule.handler_id == "noop_auto")
    assert "[bond 2]" in permanent_rule.source_text.lower()
    blocker_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_self_gain_power_for_turn_on_play"
    )
    assert blocker_rule.handler_params["grant_keyword"] == "Blocker"
    assert blocker_rule.handler_params["required_owner_battle_required_characters"] == "Son Gohan: Adolescence"


def test_extract_bt16_pan_challenging_a_demon_god_from_badge_html() -> None:
    card = replace(
        _card(
            "[Counter: Attack] Play this card.<br>"
            "[Permanent] During your opponent's turn, reduce the energy cost of this card in your hand by 1.<br>"
            "[Auto] If your Leader Card is a black &lt;Trunks: Xeno&gt;-only card and you choose 1 card in your hand and send it to your Warp: "
            "When this card is played, your opponent can't attack with Battle Cards for the turn unless they choose 2 cards in their hand and discard them each time."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    permanent_rule = next(rule for rule in rules if rule.trigger == "self_played" and rule.handler_id == "noop_auto")
    assert "reduce the energy cost of this card in your hand by 1" in permanent_rule.source_text.lower()
    auto_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_send_n_from_owner_hand_to_warp_then_limit_opponent_battle_attacks"
    )
    assert auto_rule.handler_params["warp_count"] == 1
    assert auto_rule.handler_params["opponent_hand_discard_count"] == 2
    assert auto_rule.handler_params["leader_allowed_colors"] == "black"
    assert auto_rule.handler_params["leader_required_characters"] == "Trunks: Xeno"


def test_extract_bt16_spectate_from_badge_html() -> None:
    card = replace(
        _card(
            "[Counter: Attack] Switch up to 1 red &lt;Great Priest&gt; card in your Leader Area to Active Mode.<br>"
            "[Permanent] If there are 4 or more colors among cards in your energy and Battle Area, you can activate this card's [Counter] skill from your hand without paying its energy cost."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    permanent_rule = next(rule for rule in rules if rule.trigger == "self_played" and rule.handler_id == "noop_auto")
    assert "without paying its energy cost" in permanent_rule.source_text.lower()
    counter_rule = next(
        rule
        for rule in rules
        if rule.trigger == "counter_attack"
        and rule.handler_id == "counter_switch_up_to_n_owner_leader_active"
    )
    assert counter_rule.handler_params["max_targets"] == 1
    assert counter_rule.handler_params["leader_allowed_colors"] == "red"
    assert counter_rule.handler_params["leader_required_characters"] == "Great Priest"


def test_extract_bt16_damage_negation_counter_rule() -> None:
    card = replace(
        _card("[Counter: Attack] Negate the attack, and you don't take damage from your opponent's non-keyword skills for the turn."),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        r
        for r in rules
        if r.trigger == "counter_attack"
        and r.handler_id == "counter_prevent_nonkeyword_skill_damage_for_turn"
    )
    assert "don't take damage" in rule.source_text.lower()


def test_extract_exact_p394_android_17_most_valuable_player_rules() -> None:
    card = replace(
        _card(
            "[Activate: Main][Sparking 5](R), if your Leader Card is a red â‰ªUniverse 7â‰« card and you send this card from your Drop Area to your Warp: "
            "Your Leader Card gains [Invoker] until the end of your next turn."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "activate_grant_owner_leader_keyword_until_owner_next_turn_end"
    )
    assert rule.handler_params["grant_keyword"] == "Invoker"
    assert rule.handler_params["leader_allowed_colors"] == "red"
    assert rule.handler_params["leader_required_traits"] == "Universe 7"
    assert rule.handler_params["min_owner_drop"] == 5


def test_extract_exact_bt15_mentors_rescue_rules() -> None:
    card = replace(
        _card(
            "[Counter: Play] If your Leader Card is a <Cabba> card: If the Battle Card being played has 20000 power or more, "
            "play up to 1 blue ≪Universe 7≫ <Vegeta> card with [Blocker] from your deck, negate its non-keyword skills for the game, then shuffle your deck."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "counter_play"
        and rule.handler_id == "counter_play_from_owner_deck_if_pending_battle_power_at_least_negate_nonkeyword_skills_for_game"
    )
    assert rule.handler_params["min_pending_power"] == 20000
    assert rule.handler_params["leader_required_characters"] == "Cabba"
    assert rule.handler_params["allowed_colors"] == "blue"
    assert rule.handler_params["required_traits"] == "Universe 7"
    assert rule.handler_params["required_characters"] == "Vegeta"
    assert rule.handler_params["required_keyword"] == "blocker"


def test_extract_exact_bt16_ss_vegeta_the_pursuer_rules() -> None:
    card = replace(
        _card(
            "[Critical]\n"
            "[Auto] Choose 1 Red/Blue multicolor card in your energy: "
            "At the end of a turn where this card was played from your hand, draw 1 card and switch the chosen card to Active Mode."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_schedule_turn_end_draw_n_and_switch_chosen_owner_energy_active_if_played_from_hand"
    )
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["allowed_colors"] == "red,blue"
    assert rule.handler_params["requires_multicolor"] is True
    assert rule.handler_params["requires_played_from"] == "hand"


def test_extract_exact_bt16_demon_god_gravy_umbral_might_rules() -> None:
    card = replace(
        _card(
            "[Dark Over Realm 3](２)\n"
            "[Auto] When this card is played from your hand, it gets +5000 power and [Double Strike] for the turn."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_self_gain_power_for_turn_on_play"
        and rule.handler_params.get("grant_keyword") == "Double Strike"
    )
    assert rule.handler_params["power_delta"] == 5000
    assert rule.handler_params["requires_played_from"] == "hand"


def test_extract_exact_ex20_cell_startling_assimilation_union_absorb_rule() -> None:
    card = replace(
        _card(
            "[Unique]\n"
            "[Union Absorb][Limit 1] If your Leader Card is a <Cell> card and you place 1 <Android 17> card from your hand or Drop Area under this card: "
            "Play up to 1 multicolor <Cell> card with an energy cost of 4 from your deck or Drop Area on top of this card, then shuffle your deck if you looked through it.\n"
            "[Auto] If your Leader Card is a <Cell> card: When an opponent's Battle Card is KO'd by your Leader Card's skill, you may play this card from your hand in Rest Mode."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_union_absorb_activated"
        and rule.handler_id == "noop_auto"
        and "[union absorb][limit 1]" in rule.source_text.lower()
    )
    assert rule.limit_per_turn == 1


def test_extract_exact_ex20_wretched_regeneration_rules() -> None:
    card = replace(
        _card(
            "[Counter: Attack] If your Leader Card is a <Cell> card: Negate the attack. Additionally, you may discard 1 card from your hand. If you do, play up to 1 green <Cell> card with an energy cost of 1 from your Drop Area.\n"
            "[Activate: Main](Green)(Green)(2), if your Leader Card is a <Cell> card: Play up to 1 <Cell: Xeno> card from under your Leader Card, or 1 green <Cell> card with an energy cost of 7 or 8 from under your Leader Card."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(
        rule
        for rule in rules
        if rule.trigger == "counter_attack"
        and rule.handler_id == "counter_optional_discard_n_from_owner_hand_then_play_up_to_n_from_owner_drop"
    )
    assert counter_rule.handler_params["discard_count"] == 1
    assert counter_rule.handler_params["allowed_colors"] == "green"
    assert counter_rule.handler_params["required_characters"] == "Cell"
    assert counter_rule.handler_params["max_cost"] == 1
    activate_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_extra_from_hand"
        and rule.handler_id == "activate_play_matching_from_owner_leader_under"
    )
    assert activate_rule.handler_params["leader_required_characters"] == "Cell"
    assert activate_rule.handler_params["first_required_characters"] == "Cell: Xeno"
    assert activate_rule.handler_params["second_allowed_colors"] == "green"
    assert activate_rule.handler_params["second_required_characters"] == "Cell"
    assert activate_rule.handler_params["second_exact_costs"] == "7,8"


def test_extract_exact_bt17_a_hopeless_sight_rules() -> None:
    card = replace(
        _card(
            "[Counter: Attack] Negate the attack. Additionally, you may discard 1 card from your hand. If you do, play up to 1 {Infinite Multiplication Meta-Cooler} from your Drop Area.\n"
            "[Activate: Main](Green)(Yellow)(2), if your Leader Card is a <Meta-Cooler Core> card: Play up to 100 {Infinite Multiplication Meta-Cooler} from your Drop Area."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(
        rule
        for rule in rules
        if rule.trigger == "counter_attack"
        and rule.handler_id == "counter_optional_discard_n_from_owner_hand_then_play_up_to_n_from_owner_drop"
    )
    assert counter_rule.handler_params["discard_count"] == 1
    assert counter_rule.handler_params["max_targets"] == 1
    assert counter_rule.handler_params["required_name_contains"] == "INFINITE MULTIPLICATION META-COOLER"
    activate_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_extra_from_hand"
        and rule.handler_id == "activate_play_up_to_n_named_from_owner_drop_and_gain_power_for_turn"
    )
    assert activate_rule.handler_params["max_targets"] == 100
    assert activate_rule.handler_params["required_name_contains"] == "INFINITE MULTIPLICATION META-COOLER"
    assert activate_rule.handler_params["power_delta"] == 0
    assert activate_rule.handler_params["leader_required_characters"] == "Meta-Cooler Core"


def test_extract_exact_bt17_dore_coolers_armored_squadron_rules() -> None:
    card = replace(
        _card(
            "[Empower Green 2]\n"
            "[Auto] If this card has 3 or more markers on it: When this card is played, add up to 1 <Cooler> card with an energy cost of 1 to your hand from your deck, then shuffle your deck.\n"
            "[+1][Activate: Main] This card gets +10000 power for the turn."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    auto_rule = next(rule for rule in rules if rule.handler_id == "auto_add_up_to_n_from_owner_deck_to_hand_on_play")
    assert auto_rule.handler_params["required_characters"] == "Cooler"
    assert auto_rule.handler_params["max_cost"] == 1
    assert auto_rule.handler_params["min_source_markers"] == 3
    plus_rule = next(rule for rule in rules if rule.handler_id == "activate_gain_power_and_keyword_for_turn")
    assert plus_rule.handler_params["power_delta"] == 10000


def test_extract_exact_bt17_neiz_coolers_armored_squadron_rules() -> None:
    card = replace(
        _card(
            "[Empower Green 2]\n"
            "[Counter: Attack] Negate the attack and play this card with a marker on it.\n"
            "[Auto] If this card has 3 or more markers on it: When this card is played, choose up to 1 of your opponent's Battle Cards and it can't attack until the end of your opponent's next turn.\n"
            "[+2][Activate: Main] This card gets +6000 power for the turn."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(rule for rule in rules if rule.handler_id == "counter_negate_attack_and_play_self_with_markers")
    assert counter_rule.handler_params["markers"] == 1
    auto_rule = next(rule for rule in rules if rule.handler_id == "auto_restrict_up_to_n_opponent_battle_attack_until_opponent_turn_end_on_play")
    assert auto_rule.handler_params["max_targets"] == 1
    assert auto_rule.handler_params["min_source_markers"] == 3
    plus_rule = next(rule for rule in rules if rule.handler_id == "activate_gain_power_and_keyword_for_turn")
    assert plus_rule.handler_params["power_delta"] == 6000


def test_extract_exact_bt15_fin_coercion_incarnate_rule() -> None:
    card = replace(
        _card(
            "[Deflect]\n"
            "[Auto] If your Leader Card is black: When this card is played from your hand, "
            "your opponent chooses 1 of their Battle Cards, then you choose the rest of their Battle Cards "
            "and send them to their owners' Warps."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_opponent_choose_one_then_warp_rest_opponent_battle_on_play"
    )
    assert rule.handler_params["leader_allowed_colors"] == "black"
    assert rule.handler_params["requires_played_from"] == "hand"


def test_extract_exact_bt17_dr_myuu_general_rilldo_rule() -> None:
    card = replace(
        _card(
            "[Auto] When this card attacks, play up to 1 red ≪Machine Mutant≫ card with an energy cost of 1 from your hand.\n"
            "[Awaken] When your life is at 4 or less or you choose 3 cards from under a <Super Sigma> card in your Battle Area and place them under this card: "
            "You may draw 1 card, switch up to 1 of your energy to Active Mode, add cards from your life to your hand until you have 6 life left, then flip this card over."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_attacks"
        and rule.handler_id == "auto_play_up_to_n_from_owner_hand_on_attack"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "red"
    assert rule.handler_params["required_traits"] == "Machine Mutant"
    assert rule.handler_params["exact_costs"] == "1"


def test_extract_exact_bt17_galactic_explorers_rules() -> None:
    card = replace(
        _card(
            "[Deflect]\n"
            "[Activate: Main](Red)(Red)(Red), if you have 4 or more energy: Play this card from under a Unison Card.\n"
            "[Activate: Main][Once per turn][Spirit Boost 3] Choose all of your opponent's Battle Cards and they get -30000 power for the turn, and this card gains [Triple Attack] for the turn.\n"
            "[Activate: Main][Limit 1] Choose 1 of your red Unison Cards with 10000 power or more and place this card under it from your hand or Battle Area: Add a marker to the chosen card."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "activate_play_self_from_under_owner_unison"
    )
    assert play_rule.handler_params["required_source_zone"] == "battle_under"
    assert play_rule.handler_params["owner_energy_at_least"] == 4
    boost_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "activate_reduce_all_opponent_battles_power_and_gain_keyword_for_turn"
    )
    assert boost_rule.handler_params["power_delta"] == -30000
    assert boost_rule.handler_params["grant_keyword"] == "Triple Attack"
    tuck_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "activate_add_marker_to_matching_owner_unison_and_place_self_under_it"
    )
    assert tuck_rule.handler_params["target_allowed_colors"] == "red"
    assert tuck_rule.handler_params["target_min_power"] == 10000


def test_extract_exact_ex19_skillbreaker_rules() -> None:
    card = replace(
        _card(
            "[Deflect][Critical][Blocker]\n"
            "[Auto] If your Leader Card is a yellow ≪Universe 11≫ card: When this card is played from your hand, choose one-\n"
            "・If you don't have a Unison Card in play, choose up to 1 {Vegeta, Unison of Fury} from your hand or deck, play it with 3 markers on it, then shuffle your deck if you looked through it.\n"
            "・This card gets +10000 power and [Double Strike] for the turn.\n"
            "[Auto][Once per turn] If it's your turn: When this card is switched to Rest Mode by one of your yellow card skills, switch this card to Active Mode, then choose all of your opponent's Battle Cards and negate their skills for the turn."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    choose_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_choose_unison_play_or_self_buff_on_play"
    )
    assert choose_rule.handler_params["requires_played_from"] == "hand"
    assert choose_rule.handler_params["leader_allowed_colors"] == "yellow"
    assert choose_rule.handler_params["leader_required_traits"] == "Universe 11"
    assert choose_rule.handler_params["play_card_name_contains"] == "VEGETA, UNISON OF FURY"
    assert choose_rule.handler_params["play_markers"] == 3
    assert choose_rule.handler_params["buff_power_delta"] == 10000
    assert choose_rule.handler_params["buff_keyword"] == "Double Strike"
    rest_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_switched_to_rest"
        and rule.handler_id == "auto_switch_self_active_then_negate_all_opponent_battle_skills_for_turn_on_owner_yellow_skill"
    )
    assert rest_rule.handler_params["requires_owner_turn"] is True
    assert rest_rule.handler_params["required_actor_player_id"] == "owner"
    assert rest_rule.handler_params["required_skill_color"] == "yellow"


def test_extract_exact_bt17_bizu_combination_ready_rule() -> None:
    card = replace(
        _card(
            "[Auto] If your Leader Card is a <Dr. Myuu> card: When this card is played from your hand, add up to 1 <Ribet> card from your deck or Drop Area to your hand, then shuffle your deck if you looked through it."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_add_up_to_n_from_owner_deck_or_drop_to_hand_on_play"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_traits"] == "Ribet"
    assert rule.handler_params["leader_required_traits"] == "Dr. Myuu"
    assert rule.handler_params["shuffle_deck_after"] is True
    assert rule.handler_params["requires_played_from"] == "hand"


def test_extract_exact_bt17_ribet_combination_ready_rule() -> None:
    card = replace(
        _card(
            "[Auto] If your Leader Card is a <Dr. Myuu> card: When this card is played from your hand, add up to 1 <Nezi> card from your deck or Drop Area to your hand, then shuffle your deck if you looked through it."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_add_up_to_n_from_owner_deck_or_drop_to_hand_on_play"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_traits"] == "Nezi"
    assert rule.handler_params["leader_required_traits"] == "Dr. Myuu"
    assert rule.handler_params["shuffle_deck_after"] is True
    assert rule.handler_params["requires_played_from"] == "hand"


def test_extract_exact_bt15_kale_rampaging_demon_rule() -> None:
    card = replace(
        _card(
            "[Deflect][Double Strike]\n"
            "[Auto] When this card is played without using skills, choose one-\n"
            "・Choose all of your opponent's Battle Cards with energy costs of 3 or more, place them at the bottom of their owners' decks, and if your Leader Card is a blue <Kale> card, place up to 1 card from the top of your deck under your Leader Card.\n"
            "・If you have 7 or more energy, choose all of your opponent's Battle Cards, ignoring [Barrier], place them at the bottom of their owners' decks, and this card gains [Barrier] and [Dual Attack] for the turn."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_choose_bottom_deck_opponent_battles_or_gain_keywords_on_play_without_skills"
    )
    assert rule.handler_params["first_branch_min_cost"] == 3
    assert rule.handler_params["bonus_leader_allowed_colors"] == "blue"
    assert rule.handler_params["bonus_leader_required_characters"] == "Kale"
    assert rule.handler_params["second_branch_min_owner_energy"] == 7
    assert rule.handler_params["second_branch_grant_keywords"] == "Barrier,Dual Attack"


def test_extract_exact_bt17_clash_on_planet_m2_rule() -> None:
    card = replace(
        _card(
            "[Activate: Main] Choose 1 of your red Battle Cards: Choose one-\n"
            "- The chosen card can attack Battle Cards in Active Mode for the turn.\n"
            "- Choose 1 of your opponent's Battle Cards, and it gets -X power for the turn, where X is the power of the card chosen for this skill's skill cost."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    attack_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_extra_from_hand"
        and rule.handler_id == "activate_grant_cost_target_attack_active_mode"
    )
    assert attack_rule.handler_params["cost_target_scope"] == "owner_battle"
    reduce_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_extra_from_hand"
        and rule.handler_id == "activate_reduce_opponent_battle_by_cost_target_power"
    )
    assert reduce_rule.handler_params["max_targets"] == 1


def test_extract_exact_bt17_meta_cooler_multiplying_threat_rule() -> None:
    card = _card(
        "[Auto] Add 1 card from your life to your hand: When this card attacks, look at up to 5 cards from the top of your deck, "
        "play up to 1 {Infinite Multiplication Meta-Cooler} among them in Rest Mode, shuffle your deck, and this card gets +10000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_attacks"
        and rule.handler_id == "auto_pay_life_look_top_play_up_to_n_named_rest_and_gain_power_on_attack"
    )
    assert rule.handler_params["life_to_hand"] == 1
    assert rule.handler_params["look_count"] == 5
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_name_contains"] == "INFINITE MULTIPLICATION META-COOLER"
    assert rule.handler_params["rest_mode"] is True
    assert rule.handler_params["power_delta"] == 10000
    assert rule.handler_params["shuffle_deck_after"] is True


def test_extract_exact_bt15_ss_broly_brutality_beyond_measure_rule() -> None:
    card = _card(
        "[Deflect][Double Strike]\n"
        "[Permanent] If your opponent has 3 or more energy and you have 5 or more red Extra Cards in your Drop Area, reduce the energy cost of this card in your hand by 3.\n"
        "[Auto][Once per turn] Choose 1 card in your hand and discard it: When you activate the [Activate: Battle] skill on a red Extra Card with an original energy cost of 3 or more in your hand or Drop Area, switch this card to Active Mode. If the card you discarded with this skill is a copy of this card, draw 2 cards, then choose up to 1 of your opponent's Battle Cards or Unison Cards, ignoring [Barrier], and it gets -35000 power for the turn."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "owner_activate_battle"
        and rule.handler_id == "auto_discard_on_owner_activate_battle_red_extra_switch_self_active_and_optional_copy_bonus_debuff"
    )
    assert rule.handler_params["discard_count"] == 1
    assert rule.handler_params["required_skill_source_zones"] == "hand,drop"
    assert rule.handler_params["required_skill_card_type"] == "EXTRA"
    assert rule.handler_params["required_skill_allowed_colors"] == "red"
    assert rule.handler_params["required_skill_min_cost"] == 3
    assert rule.handler_params["bonus_draw"] == 2
    assert rule.handler_params["bonus_power_delta"] == -35000
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["ignores_barrier"] is True


def test_extract_exact_bt15_champa_right_on_time_rules() -> None:
    card = replace(
        _card(
            "[Double Strike]\n"
            "[Counter: Attack] Negate the attack and play this card.\n"
            "[Permanent] During your opponent's turn, reduce the energy cost of this card in your hand by 1."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(
        rule
        for rule in rules
        if rule.trigger == "counter_attack" and rule.handler_id == "counter_negate_attack_play_self"
    )
    assert "negate the attack and play this card" in counter_rule.source_text.lower()
    permanent_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played" and rule.handler_id == "noop_auto"
    )
    assert "reduce the energy cost of this card in your hand by 1" in permanent_rule.source_text.lower()


def test_extract_exact_bt15_hit_on_guard_rules() -> None:
    card = replace(
        _card(
            "[Double Strike]\n"
            "[EX-Evolve](Blue), if you have 3 or more energy: <Hit> card with an energy cost of 3 or 4.\n"
            "[Counter: Attack] Negate the attack and play this card.\n"
            "[Permanent] During your opponent's turn, reduce the energy cost of this card in your hand by 2."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(
        rule
        for rule in rules
        if rule.trigger == "counter_attack" and rule.handler_id == "counter_negate_attack_play_self"
    )
    assert "negate the attack and play this card" in counter_rule.source_text.lower()
    permanent_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played" and rule.handler_id == "noop_auto"
    )
    assert "reduce the energy cost of this card in your hand by 2" in permanent_rule.source_text.lower()


def test_extract_exact_bt16_miraculous_transformation_rules() -> None:
    card = replace(
        _card(
            "[Deflect][Unique][Triple Strike][Barrier]\n"
            "[Counter: Attack] Negate the attack and play this card in Rest Mode.\n"
            "[Permanent] During your opponent's turn, reduce the energy cost of this card in your hand by 1 for each card in your opponent's energy.\n"
            "[Permanent] If your Leader Card is mono-blue and this card is in Rest Mode, your opponent's Battle Cards can't attack Leader Cards."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(
        rule
        for rule in rules
        if rule.trigger == "counter_attack" and rule.handler_id == "counter_negate_attack_play_self"
    )
    assert "play this card in rest mode" in counter_rule.source_text.lower()
    texts = {rule.source_text.lower() for rule in rules if rule.trigger == "self_played" and rule.handler_id == "noop_auto"}
    assert any("reduce the energy cost of this card in your hand by 1 for each card in your opponent's energy" in text for text in texts)
    assert any("your opponent's battle cards can't attack leader cards" in text for text in texts)


def test_extract_exact_bt16_whis_angel_of_universe_7_rules() -> None:
    card = replace(
        _card(
            "[Energy-Exhaust][Blocker]\n"
            "[Counter: Attack] Negate the attack and play this card.\n"
            "[Permanent] If there are 4 or more colors in your energy, you can activate this card's [Counter] skill from your hand by adding a card from your life to your hand instead of paying its energy cost.\n"
            "[Auto] When this card is used in a combo from your hand, switch up to 1 of your energy to Active Mode."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(
        rule
        for rule in rules
        if rule.trigger == "counter_attack" and rule.handler_id == "counter_negate_attack_play_self"
    )
    assert "negate the attack and play this card" in counter_rule.source_text.lower()
    permanent_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played" and rule.handler_id == "noop_auto"
    )
    assert "adding a card from your life to your hand instead of paying its energy cost" in permanent_rule.source_text.lower()
    combo_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_comboed"
        and rule.handler_id == "auto_switch_up_to_n_owner_energy_active_on_combo"
    )
    assert combo_rule.handler_params["max_targets"] == 1
    assert combo_rule.handler_params["requires_comboed_from"] == "hand"


def test_extract_exact_bt16_ss_vegeta_the_interceptor_rules() -> None:
    card = replace(
        _card(
            "[Dual Attack]\n"
            "[Counter: Counter] If your Leader Card is blue: Play this card.\n"
            "[Auto] When this card is played, choose up to 2 of your opponent's Battle Cards and place them at the bottom of their owners' decks in any order."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(
        rule
        for rule in rules
        if rule.trigger == "counter_attack" and rule.handler_id == "counter_play_self_from_counter_counter"
    )
    assert counter_rule.handler_params["leader_allowed_colors"] == "blue"
    bottom_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played" and rule.handler_id == "auto_bottom_deck_up_to_n_opponent_battle"
    )
    assert bottom_rule.handler_params["max_targets"] == 2


def test_extract_exact_bt15_vados_right_on_time_rules() -> None:
    card = replace(
        _card(
            "[Dual Attack]\n"
            "[Counter: Play] Play this card, and if the Battle Card being played has an energy cost of 3 or less, return it to its owner's hand instead.\n"
            "[Permanent] During your opponent's turn, reduce the energy cost of this card in your hand by 1."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    counter_rule = next(
        rule
        for rule in rules
        if rule.trigger == "counter_play"
        and rule.handler_id == "counter_play_self_then_return_pending_to_owner_hand_if_cost_at_most"
    )
    assert counter_rule.handler_params["max_pending_cost"] == 3
    permanent_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played" and rule.handler_id == "noop_auto"
    )
    assert "reduce the energy cost of this card in your hand by 1" in permanent_rule.source_text.lower()


def test_extract_exact_bt17_further_evolution_rules() -> None:
    card = replace(
        _card(
            "[Activate: Main] Look at up to 7 cards from the top of your deck, then choose one-\n"
            "・Add up to 2 skill-less black Battle Cards among them to your hand, then shuffle your deck.\n"
            "・Add up to 1 black ≪Android≫ card with an energy cost of 7 or less among them to your hand, then shuffle your deck."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_extra_from_hand"
        and rule.handler_id == "activate_look_top_choose_further_evolution_branch"
    )
    assert rule.handler_params["look_count"] == 7
    assert rule.handler_params["first_branch_max_add"] == 2
    assert rule.handler_params["second_branch_max_add"] == 1
    assert rule.handler_params["second_branch_max_cost"] == 7


def test_extract_exact_bt17_son_goku_rules() -> None:
    card = replace(
        _card(
            "[Auto] Add 1 card from your life to your hand: When this card attacks, look at up to 5 cards from the top of your deck, play up to 1 yellow Unison Card with a specified cost of 1 among them with a marker on it in Rest Mode, then shuffle your deck.\n"
            "[Awaken] When your life is at 4 or less: You may draw 1 card, switch up to 1 of your energy to Active Mode, and flip this card over."
        ),
        card_type="LEADER",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_attacks"
        and rule.handler_id == "auto_pay_life_look_top_play_up_to_n_matching_unison_with_marker_on_attack"
    )
    assert rule.handler_params["life_to_hand"] == 1
    assert rule.handler_params["look_count"] == 5
    assert rule.handler_params["allowed_colors"] == "yellow"
    assert rule.handler_params["required_card_type"] == "UNISON"
    assert rule.handler_params["specified_cost_total"] == 1
    assert rule.handler_params["markers"] == 1


def test_extract_exact_bt17_demon_god_dabura_imperial_warrior_rules() -> None:
    card = replace(
        _card(
            "[Dark Over Realm 3](2)\n"
            "[Auto][Limit 1] When this card attacks, play up to 1 ≪Evil Wizard≫ card, ≪Demon Realm Race≫ card, or ≪Demon God≫ card"
            "—all black and with an energy cost of 2 or less—from your hand."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_attacks"
        and rule.handler_id == "auto_play_up_to_n_from_owner_hand_on_attack"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["allowed_colors"] == "black"
    assert rule.handler_params["required_traits"] == "Evil Wizard|Demon Realm Race|Demon God"


def test_extract_exact_p381_natt_on_alert_rules() -> None:
    card = replace(
        _card(
            "[Auto] If your Leader Card is a <Dr. Myuu> card: When this card is played from your hand, add up to 1 red <General Rilldo> card with an energy cost of 5 or less to your hand from your deck, then shuffle your deck."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(rule for rule in rules if rule.handler_id == "auto_add_up_to_n_from_owner_deck_to_hand_on_play")
    assert rule.handler_params["allowed_colors"] == "red"
    assert rule.handler_params["required_characters"] == "General Rilldo"
    assert rule.handler_params["max_cost"] == 5
    assert rule.handler_params["requires_played_from"] == "hand"


def test_extract_exact_p379_king_cold_hail_to_the_king_rules() -> None:
    card = replace(
        _card(
            "[Counter: Attack] Negate the attack and play this card.\n"
            "[Permanent] For each green Unison Card in your Unison Area and Drop Area, reduce the energy cost of this card in your hand by 1.\n"
            "[Auto] When this card is played, your opponent can't attack for the turn unless they discard 1 card from their hand each time."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "counter_attack" and rule.handler_id == "noop_auto" for rule in rules)
    rule = next(rule for rule in rules if rule.handler_id == "auto_limit_opponent_battle_attacks_discard_hand_each_time_on_play")
    assert rule.handler_params["opponent_hand_discard_count"] == 1


def test_extract_exact_p377_son_gohan_the_empowered_rules() -> None:
    card = replace(
        _card(
            "[Empower Yellow 2][Blocker]\n"
            "[Permanent] During your turn, this card gets +2000 power for each marker on it.\n"
            "[Auto][Limit 1] If you have a Unison Card in play: When this card is placed in your Drop Area from your Unison Area, add up to 1 {Trunks, the Empowered} to your hand from your deck,  then shuffle your deck.\n"
            "[+1][Activate: Main] At the end of the turn, switch this card to Active Mode."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    drop_rule = next(rule for rule in rules if rule.trigger == "self_placed_into_drop")
    assert drop_rule.handler_id == "auto_add_up_to_n_from_owner_deck_to_hand_on_play"
    assert drop_rule.handler_params["required_name_contains"] == "TRUNKS, THE EMPOWERED"
    assert drop_rule.handler_params["requires_placed_from_zones"] == "unison"
    assert any(rule.trigger == "turn_end" and rule.handler_id == "auto_switch_self_active_on_turn_end" for rule in rules)


def test_extract_exact_p353_ssb_vegito_blue_omen_rules() -> None:
    card = replace(
        _card(
            "[Energy-Exhaust][Blocker]\n"
            "[Auto][Limit 1](Yellow), if the front of your Leader Card is a blue {Son Goku & Vegeta} and you have 2 or less energy: When this card in your hand is played or placed in your energy, place the top card of your deck in your energy. Your opponent chooses up to 1 card in their hand and places it in their energy.\n"
            "[Activate: Main](Blue)(Yellow)①, if your Leader Card is a <Vegito> card: Choose up to 1 Blue/Yellow multicolor <Vegito> card with an original energy cost of 8 in your hand and play it on top of this card."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "self_played" and rule.handler_id == "auto_add_top_deck_to_owner_energy_then_opponent_places_up_to_n_hand_to_energy" for rule in rules)
    assert any(rule.trigger == "self_added_to_energy" and rule.handler_id == "auto_add_top_deck_to_owner_energy_then_opponent_places_up_to_n_hand_to_energy" for rule in rules)
    top_rule = next(rule for rule in rules if rule.handler_id == "activate_play_up_to_n_matching_from_owner_hand_on_top_of_self")
    assert top_rule.handler_params["required_characters"] == "Vegito"
    assert top_rule.handler_params["max_cost"] == 8


def test_extract_exact_ex19_31_ss_broly_reckless_pursuit_rules() -> None:
    card = replace(
        _card(
            "[Energy-Exhaust][Blocker]\n"
            "[Swap 8](Green)(Yellow), if you have 3 or more energy: Green/Yellow <Broly: Br> with an energy cost of 8.\n"
            "[Arrival Green/Yellow](Green)/(Yellow)\n"
            "[Auto] When this card is played, or when this card is switched to Active Mode by a skill during your turn, choose up to 1 of your opponent's Battle Cards with an energy cost of 4 or less and negate its skills for the turn.\n"
            "[Activate: Main/Battle][Once per turn] Switch this card to Rest Mode: Choose up to 1 of your opponent's skill-less Battle Cards and KO it."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "self_played" and rule.handler_id == "auto_negate_up_to_n_opponent_battle_skills_for_turn_on_play_or_self_switch" for rule in rules)
    assert any(rule.trigger == "self_switched_to_active" and rule.handler_id == "auto_negate_up_to_n_opponent_battle_skills_for_turn_on_play_or_self_switch" for rule in rules)
    assert any(rule.trigger == "self_activate_main" and rule.handler_id == "activate_ko_up_to_n_skillless_opponent_battle" for rule in rules)
    assert any(rule.trigger == "self_activate_battle" and rule.handler_id == "activate_ko_up_to_n_skillless_opponent_battle" for rule in rules)


def test_extract_exact_bt15_yamcha_confronting_invasion_rules() -> None:
    card = replace(
        _card(
            "[Dual Attack]\n"
            "[Permanent] If your opponent has 6 or more Battle Cards in play, reduce the energy cost of this card in your hand by 2.\n"
            "[Auto] At the end of your turn, if your opponent has a Battle Card with an energy cost of 1 in play in their Battle Area, place this card in its owner's Drop Area."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    permanent_rule = next(rule for rule in rules if rule.trigger == "self_played" and rule.handler_id == "noop_auto")
    assert "reduce the energy cost of this card in your hand by 2" in permanent_rule.source_text.lower()
    turn_end_rule = next(
        rule
        for rule in rules
        if rule.trigger == "turn_end"
        and rule.handler_id == "auto_send_self_to_owner_drop_on_turn_end_if_opponent_has_battle_cost"
    )
    assert turn_end_rule.handler_params["required_opponent_battle_cost"] == 1


def test_extract_exact_bt17_cooler_sibling_cruelty_rules() -> None:
    card = replace(
        _card(
            "[Double Strike]\n"
            "[Permanent] For each green Unison Card in your Drop Area, reduce the energy cost of this card in your hand by 1.\n"
            "[Auto] When this card is played, you can't play copies of this card this turn. Additionally, you may place 1 green Unison Card with a specified cost of 3 or less from your Drop Area at the bottom of your deck. If you do, your opponent discards 1 card from their hand."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_restrict_self_copies_and_bottom_deck_green_unison_then_opponent_discard_on_play"
    )
    assert rule.handler_params["max_cost"] == 3


def test_extract_exact_p395_ss2_kefla_supreme_warrior_of_universe_6_rules() -> None:
    card = replace(
        _card(
            "[Deflect][Unique][Barrier]\n"
            "[Auto] If you have 7 or more energy: When this card is played, it gains [Triple Strike] for the turn.\n"
            "[Activate: Main][Once per turn] Add up to 1 <Caulifla> or <Kale> card from your Drop Area to your hand."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    play_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played" and rule.handler_id == "auto_self_gain_power_for_turn_on_play"
    )
    assert play_rule.handler_params["grant_keyword"] == "Triple Strike"
    assert play_rule.handler_params["min_owner_energy"] == 7
    activate_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_main" and rule.handler_id == "activate_add_up_to_n_from_owner_drop_to_hand"
    )
    assert activate_rule.handler_params["max_targets"] == 1
    assert activate_rule.handler_params["required_characters"] == "Caulifla|Kale"


def test_extract_exact_bt15_ss_son_gohan_opposing_the_demon_rules() -> None:
    card = replace(
        _card(
            "[Deflect][Dual Attack][Blocker]\n"
            "[EX-Evolve](Red)(Red), if you have 3 or more energy: Red <Son Gohan: Adolescence> card with an energy cost of 3.\n"
            "[Activate: Main][Once per turn] Choose 1 of your Leader Cards or Unison Cards and switch it to Rest Mode: Choose all of your opponent's Battle Cards, and they get -15000 power for the turn."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_main"
        and rule.handler_id == "activate_reduce_all_opponent_battles_power_and_gain_keyword_for_turn"
    )
    assert rule.handler_params["power_delta"] == -15000
    assert rule.handler_params["rest_owner_leader_or_unison"] is True
    assert "grant_keyword" not in rule.handler_params


def test_extract_exact_bt17_the_z_fighters_at_the_cell_games_rules() -> None:
    card = replace(
        _card(
            "[Activate: Main][Limit 1] If your Leader Card is a yellow <Son Goku> card: Look at up to 7 cards from the top of your deck, then choose one-\n"
            "・Add up to 1 yellow ≪Saiyan≫ card with an energy cost of 4 or less among them to your hand, then shuffle your deck.\n"
            "・Play up to 1 yellow Unison Card with a specified cost of 1 among them with a marker on it, then shuffle your deck."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_extra_from_hand"
        and rule.handler_id == "activate_look_top_choose_add_to_hand_or_play_unison_with_marker"
    )
    assert rule.handler_params["look_count"] == 7
    assert rule.handler_params["leader_allowed_colors"] == "yellow"
    assert rule.handler_params["leader_required_characters"] == "Son Goku"
    assert rule.handler_params["hand_branch_allowed_colors"] == "yellow"
    assert rule.handler_params["hand_branch_required_traits"] == "Saiyan"
    assert rule.handler_params["hand_branch_max_cost"] == 4
    assert rule.handler_params["unison_branch_allowed_colors"] == "yellow"
    assert rule.handler_params["unison_branch_required_specified_cost_total"] == 1


def test_extract_exact_bt17_the_world_champion_strikes_rules() -> None:
    card = replace(
        _card("[Counter: Attack] Your opponent may negate the attack."),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "counter_attack" and rule.handler_id == "noop_auto"
    )
    assert rule.source_text == "[Counter: Attack] Your opponent may negate the attack."


def test_extract_exact_bt17_android_19_energy_absorber_rules() -> None:
    rules = extract_effect_rules_from_card(
        _card(
            "[Counter: Attack] Negate the attack and play this card.\n"
            "[Permanent] If your Leader Card is a blue ≪Red Ribbon Army≫ card, you can activate this card's [Counter] skill from your energy by paying its energy cost and discarding 1 card from your hand."
        )
    )

    assert [(r.trigger, r.handler_id) for r in rules] == [
        ("counter_attack", "noop_auto"),
        ("self_played", "noop_auto"),
    ]
    assert rules[0].source_text == "[Counter: Attack] Negate the attack and play this card."
    assert "from your energy by paying its energy cost and discarding 1 card from your hand" in rules[1].source_text


def test_extract_exact_bt17_coolers_armored_squadron_rules() -> None:
    card = replace(
        _card(
            "[Activate: Main][Limit 1] If your Leader Card is a <Cooler> card: Look at up to 7 cards from the top of your deck, then choose one-\n"
            "・Play up to 1 green Unison Card with a specified cost of 1 and [Empower] among them with a marker on it, then shuffle your deck.\n"
            "・Play up to 1 green <Cooler> card with an energy cost of 2 or less among them, then shuffle your deck."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_extra_from_hand"
        and rule.handler_id == "activate_look_top_choose_add_to_hand_or_play_unison_with_marker"
    )
    assert rule.handler_params["look_count"] == 7
    assert rule.handler_params["leader_required_characters"] == "Cooler"
    assert rule.handler_params["hand_branch_allowed_colors"] == "green"
    assert rule.handler_params["hand_branch_required_characters"] == "Cooler"
    assert rule.handler_params["hand_branch_required_card_type"] == "BATTLE"
    assert rule.handler_params["hand_branch_destination"] == "play"
    assert rule.handler_params["hand_branch_max_cost"] == 2
    assert rule.handler_params["unison_branch_allowed_colors"] == "green"
    assert rule.handler_params["unison_branch_required_specified_cost_total"] == 1
    assert rule.handler_params["unison_branch_required_skill_text_contains"] == "[empower"


def test_extract_exact_bt17_android_18_rebellious_will_rules() -> None:
    card = replace(
        _card(
            "[Critical]\n"
            "[Auto] If your Leader Card is a blue ≪Red Ribbon Army≫ card: When this card is played, look at up to 5 cards from the top of your deck, add up to 1 blue ≪Android≫ card among them to your energy in Rest Mode, place 1 card from your energy at the bottom of its owner's deck, then shuffle your deck.\n"
            "[Activate: Main][Limit 1](Blue), if your Leader Card is a blue ≪Android≫ card: You may play this card from your energy."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    on_play = next(rule for rule in rules if rule.trigger == "self_played" and rule.handler_id == "auto_add_up_to_n_matching_from_top_deck_to_energy_rest_then_bottom_deck_owner_energy_on_play")
    assert on_play.handler_params["look_count"] == 5
    assert on_play.handler_params["allowed_colors"] == "blue"
    assert on_play.handler_params["required_traits"] == "Android"
    activate = next(rule for rule in rules if rule.trigger == "self_activate_main" and rule.handler_id == "activate_play_self_from_energy")
    assert activate.handler_params["leader_required_traits"] == "Android"


def test_extract_exact_bt17_tien_shinhan_z_fighter_rules() -> None:
    card = replace(
        _card(
            "[Empower Yellow 2]\n"
            "[Auto] If this card has 3 or more markers on it: When this card is played, choose up to 1 of your opponent's Unison Cards and switch it to Rest Mode.\n"
            "[+1][Activate: Main] Choose up to 1 of your opponent's Battle Cards in Rest Mode and it can't be switched to Active Mode until the end of their next turn.\n"
            "[-3][Activate: Main] Choose up to 1 of your opponent's Leader Cards in Rest Mode and it can't attack until the end of their next turn."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "self_played" and rule.handler_id == "auto_switch_up_to_n_opponent_unison_rest_on_play" for rule in rules)
    assert any(rule.trigger == "self_activate_main" and rule.handler_id == "activate_restrict_up_to_n_opponent_rest_cards_switch_active_until_end_of_next_turn" for rule in rules)
    assert any(rule.trigger == "self_activate_main" and rule.handler_id == "activate_restrict_opponent_leader_attack_until_end_of_next_turn" for rule in rules)


def test_extract_exact_bt17_krillin_z_fighter_rules() -> None:
    card = replace(
        _card(
            "[Empower Yellow 2]\n"
            "[Auto][Limit 1] If this card has 3 or more markers on it: When this card is played, choose up to 1 of your opponent's Battle Cards with an energy cost of 4 or less in Rest Mode and negate its skills for the turn.\n"
            "[+1][Activate: Main] This card gets +10000 power for the turn.\n"
            "[-3][Activate: Battle] Choose up to 1 of your opponent's Battle Cards with an energy cost of 4 or less in Rest Mode and KO it."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "self_played" and rule.handler_id == "auto_negate_up_to_n_opponent_rest_battle_skills_for_turn_on_play" for rule in rules)
    assert any(rule.trigger == "self_activate_main" and rule.handler_id == "activate_gain_power_and_keyword_for_turn" for rule in rules)
    assert any(rule.trigger == "self_activate_battle" and rule.handler_id == "activate_ko_up_to_n_opponent_battle" for rule in rules)


def test_extract_exact_bt16_marcarita_angel_of_universe_11_rules() -> None:
    card = replace(
        _card(
            "[Energy-Exhaust][Barrier][Blocker]\n"
            "[Auto] If you have 1 or more multicolor energy: When this card in your hand is played or used in a combo, your opponent chooses 1 card in their hand and discards it.\n"
            "[Auto][Limit 1] When your opponent plays a Battle Card using a skill or activates a [Counter] skill, choose up to 1 of your opponent's Battle Cards and switch it to Rest Mode."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "self_played" and rule.handler_id == "auto_opponent_discards_n_from_hand_on_play_or_combo" for rule in rules)
    assert any(rule.trigger == "self_comboed" and rule.handler_id == "auto_opponent_discards_n_from_hand_on_play_or_combo" for rule in rules)
    assert any(rule.trigger == "owner_opponent_counter_activated" and rule.handler_id == "auto_switch_up_to_n_owner_opponent_battle_rest_on_owner_opponent_counter_activated" for rule in rules)


def test_extract_exact_bt17_meta_cooler_core_energy_source_rules() -> None:
    card = replace(
        _card(
            "[Energy-Exhaust][Blocker]\n"
            "[Auto] When this card in your hand is played or used in a combo, play up to 1 {Infinite Multiplication Meta-Cooler} from your deck in Rest Mode, then shuffle your deck."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "self_played" and rule.handler_id == "auto_play_up_to_n_named_from_owner_deck_rest_on_play_or_combo" for rule in rules)
    assert any(rule.trigger == "self_comboed" and rule.handler_id == "auto_play_up_to_n_named_from_owner_deck_rest_on_play_or_combo" for rule in rules)


def test_extract_exact_bt17_piccolo_fusing_with_kami_rules() -> None:
    card = replace(
        _card(
            "[Critical]\n"
            "[Evolve](3): <Piccolo> or <Kami>.\n"
            "[Activate: Battle][Once per turn] Choose up to 1 of your opponent's Battle Cards with an energy cost of 4 or less, ignoring [Barrier], and KO it."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_battle" and rule.handler_id == "activate_ko_up_to_n_opponent_battle"
    )
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_cost"] == 4
    assert rule.handler_params["ignores_barrier"] is True


def test_extract_exact_bt16_beerus_ruthless_pursuer_rules() -> None:
    card = replace(
        _card(
            "[Double Strike]\n"
            "[Auto][Limit 1] When this card attacks and KOs an opponent's Battle Card, switch this card and up to 1 of your blue energy to Active Mode.\n"
            "[Auto][Limit 1] If your Leader Card is blue and this card is in your Combo Area: When one of your blue Battle Cards attacks and KOs an opponent's Battle Card, draw 1 card, then play this card from your Combo Area."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    switch_rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_attacks_battle_end"
        and rule.handler_id == "auto_switch_self_and_up_to_n_owner_energy_active_on_attack_ko"
    )
    assert switch_rule.handler_params["max_targets"] == 1
    assert switch_rule.handler_params["allowed_colors"] == "blue"
    draw_rule = next(
        rule
        for rule in rules
        if rule.trigger == "owner_battle_ko_opponent_battle_battle_end" and rule.handler_id == "auto_draw_n"
    )
    assert draw_rule.handler_params["amount"] == 1
    assert draw_rule.handler_params["attacker_allowed_colors"] == "blue"
    assert draw_rule.handler_params["leader_allowed_colors"] == "blue"
    play_rule = next(
        rule
        for rule in rules
        if rule.trigger == "owner_battle_ko_opponent_battle_battle_end"
        and rule.handler_id == "auto_play_self_from_combo_on_battle_end"
    )
    assert play_rule.handler_params["attacker_allowed_colors"] == "blue"
    assert play_rule.handler_params["leader_allowed_colors"] == "blue"


def test_extract_exact_bt17_meta_rilldo_ascended_general_rules() -> None:
    card = replace(
        _card(
            "[Double Strike][Barrier][Blocker]\n"
            "[EX-Evolve](Red): <General Rilldo> with an energy cost of 5 or more.\n"
            "[Activate: Battle] If it's your opponent's turn and you place 1 card from under this card in its owner's Drop Area: Switch this card to Active Mode, and this card gets -5000 power for the turn."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_battle"
        and rule.handler_id == "activate_move_under_self_to_drop_switch_self_active_and_self_power_for_turn"
    )
    assert rule.handler_params["owner_opponent_turn"] is True
    assert rule.handler_params["power_delta"] == -5000


def test_extract_exact_bt17_weight_on_ones_shoulders_rules() -> None:
    card = replace(
        _card(
            "[Activate: Battle] If it's your opponent's turn: Choose up to 1 ≪Namekian≫ card in your Battle Area, switch it to Active Mode, and it gets +1000 power for the battle.\n"
            "[Activate: Battle](Yellow), if it's your turn: Choose up to 1 of your ≪Namekian≫ cards, and for each ≪Namekian≫ card under it, it gets +5000 power (up to a maximum of +15000) and [Double Strike] for the battle."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_extra_from_hand"
        and rule.handler_id == "activate_turn_split_namekian_battle_buff"
    )
    assert "your opponent's turn" in rule.source_text


def test_extract_exact_bt17_android_14_inorganic_horror_rules() -> None:
    card = replace(
        _card(
            "[Counter: Attack] If your Leader Card is a blue ?Red Ribbon Army? ?Android? card and you discard another card from your hand: Negate the attack and play this card.\n"
            "[Auto] If it's your opponent's turn: When this card is played, your opponent can't attack for the turn unless they place 2 cards from their hand at the bottom of their deck each time."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(
        rule.trigger == "self_played"
        and rule.handler_id == "auto_discard_n_from_owner_hand_then_limit_opponent_battle_attacks_bottom_deck_each_time"
        for rule in rules
    )


def test_extract_exact_bt16_whis_calling_to_order_rules() -> None:
    card = replace(
        _card(
            "[Energy-Exhaust][Blocker]\n"
            "[Auto] When this card is played from your hand or at the end of a battle in which this card was used in a combo from your hand, add up to 1 skill-less Battle Card with an energy cost of 2 from your deck or Drop Area to your hand, then shuffle your deck if you looked through it. Additionally, if it's your opponent's turn, you may play 1 skill-less Battle Card with an energy cost of 2 from your hand in Rest Mode."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(
        rule.trigger == "self_played"
        and rule.handler_id == "auto_add_skillless_cost2_from_owner_deck_or_drop_to_hand_then_optional_play_from_hand_rest"
        for rule in rules
    )
    assert any(
        rule.trigger == "self_comboed_battle_end"
        and rule.handler_id == "auto_add_skillless_cost2_from_owner_deck_or_drop_to_hand_then_optional_play_from_hand_rest"
        for rule in rules
    )


def test_extract_exact_bt17_meta_cooler_enhanced_menace_rules() -> None:
    card = replace(
        _card(
            "[Energy-Exhaust][Blocker]\n"
            "[Permanent] If you have a <Meta-Cooler> card in play, negate this card's [Energy-Exhaust] skill in all areas.\n"
            "[Auto] When this card is played from your hand, look at up to 7 cards from the top of your deck, play up to 3 {Infinite Multiplication Meta-Cooler} among them in Rest Mode, then shuffle your deck."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_play_up_to_n_named_from_owner_deck_rest_on_play_or_combo"
    )
    assert rule.handler_params["max_targets"] == 3
    assert rule.handler_params["max_look"] == 7


def test_extract_exact_bt16_ss_gogeta_holding_nothing_back_rules() -> None:
    card = replace(
        _card(
            "[Energy-Exhaust][Blocker]\n"
            "[Union-Fusion]((Red))((Blue))(?) : <Son Goku: Br> and <Vegeta: Br>.\n"
            "[Permanent] This card can't be KO'd by skills.\n"
            "[Auto] If your Leader Card is a blue <Vegeta: Br> or blue <Gogeta: Br> card: At the end of a turn where this card was played, draw 1 card, then add up to 1 Red/Blue multicolor card from your Drop Area to your energy."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_played"
        and rule.handler_id == "auto_schedule_turn_end_draw_n_and_add_up_to_n_from_owner_drop_to_energy_if_played"
    )
    assert rule.handler_params["amount"] == 1
    assert rule.handler_params["allowed_colors"] == "red|blue"
    assert rule.handler_params["requires_multicolor"] is True


def test_extract_exact_p352_king_vegeta_great_apes_rule_rules() -> None:
    card = replace(
        _card(
            "[Energy-Exhaust][Blocker][Arrival Red/Green](Green)\n"
            "[Auto](Red): When this card is played, your opponent may choose 2 cards in their hand and discard them. If they don't, choose up to 1 card in your opponent's Battle Area and place it in its owner's Drop Area.\n"
            "[Auto] At the end of your turn, choose all ?Great Ape? cards in your Battle Area and switch them to Active Mode."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(
        rule.trigger == "self_played"
        and rule.handler_id == "auto_opponent_discards_n_or_owner_sends_up_to_n_opponent_battle_to_drop_on_play"
        for rule in rules
    )
    assert any(
        rule.trigger == "turn_end"
        and rule.handler_id == "auto_switch_all_owner_battles_active_by_trait_on_turn_end"
        for rule in rules
    )


def test_extract_exact_bt17_red_ribbon_army_assemble_rules() -> None:
    card = replace(
        _card("[Activate: Main] Play up to 1 blue ?Red Ribbon Army? card with an energy cost of 2 or less and 10000 power or less from your deck, then shuffle your deck."),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(rule for rule in rules if rule.trigger == "self_activate_extra_from_hand" and rule.handler_id == "activate_play_up_to_n_from_owner_deck")
    assert rule.handler_params["required_traits"] == "Red Ribbon Army"
    assert rule.handler_params["max_power"] == 10000


def test_extract_exact_bt17_sacrificial_strike_rules() -> None:
    card = replace(
        _card(
            "[Counter: Attack] Negate the attack.\n"
            "[Activate: Battle] Choose 1 of your blue ?Red Ribbon Army? cards and it gets +10000 power for the battle. Additionally, you may choose 1 ?Red Ribbon Army? card in your Battle Area and place it in its owner's Drop Area. If you do, your card that's in a battle gains [Critical] for the battle."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "counter_attack" and rule.handler_id == "noop_auto" for rule in rules)
    assert any(
        rule.trigger == "self_activate_extra_from_hand"
        and rule.handler_id == "activate_buff_owner_battle_for_battle_then_optionally_send_owner_battle_to_drop_and_grant_battling_owner_card_keyword"
        for rule in rules
    )


def test_extract_exact_bt17_android_15_inorganic_horror_rules() -> None:
    card = replace(
        _card(
            "[Deflect]\n"
            "[Counter: Play] Play this card, and if the Battle Card being played has an energy cost of 3 or less, return it to its owner's hand instead.\n"
            "[Permanent] If your Leader Card is a blue ?Red Ribbon Army? card, you can activate this card's [Counter] skill from your energy by paying its energy cost.\n"
            "[Permanent][Bond 3] Blue ?Android?: This card gets +10000 power."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "counter_play" and rule.handler_id == "counter_play_self_then_return_pending_to_owner_hand_if_cost_at_most" for rule in rules)
    assert any(rule.source_text.endswith("paying its energy cost.") for rule in rules)


def test_extract_exact_ex20_cell_unending_torrent_rules() -> None:
    card = replace(
        _card(
            "[Energy-Exhaust][Blocker]\n"
            "[Evolve](3): <Android 18>.\n"
            "[Permanent] If this card would be removed from your Battle Area by an opponent's skill, you may place 2 cards from under this card in their owners' Drop Areas instead.\n"
            "[Activate: Battle][Once per turn] If your Leader Card is a <Cell> card and you place 1 card from under this card in its owner's Drop Area: Switch this card to Active Mode."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(
        rule
        for rule in rules
        if rule.trigger == "self_activate_battle"
        and rule.handler_id == "activate_move_under_self_to_drop_switch_self_active_and_self_power_for_turn"
    )
    assert rule.handler_params["leader_required_characters"] == "Cell"
    assert rule.handler_params["power_delta"] == 0


def test_extract_exact_p354_baby_janemba_malefic_agent_of_destruction_rules() -> None:
    card = replace(
        _card("[Energy-Exhaust][Blocker]\n[Offering][Limit 1]\n[Permanent] If your opponent has 5 or more cards in Rest Mode, negate this card's [Energy-Exhaust] skill in all areas."),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.handler_id == "noop_auto" and "5 or more cards in Rest Mode" in rule.source_text for rule in rules)


def test_extract_exact_p403_mai_future_possibilities_rules() -> None:
    card = replace(
        _card(
            "[Auto] If there are 1 or more <Trunks: Future> cards in your Z-Energy: When this card attacks, it gets +10000 power for the turn.\n"
            "[Activate: Main][Once per turn] If there are 1 or more <Trunks: Future> cards in your Z-Energy: During your opponent's next turn, the first time they attack with a Battle Card with an energy cost of 5 or more, negate the attack at the start of the battle's Offense Step."
        ),
        card_type="Z-BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "self_attacks" and rule.handler_id == "auto_self_gain_power_for_turn_on_attack" for rule in rules)
    assert any(rule.trigger == "self_activate_main" and rule.handler_id == "activate_schedule_next_opponent_battle_attack_negate_by_cost" for rule in rules)


def test_extract_exact_p404_piccolo_masters_teachings_rules() -> None:
    card = replace(
        _card(
            "[Auto][Limit 1] If your Leader is green and has <Gotenks> in its character name, and you discard 2 cards from your hand: When this card is played, play up to 1 {Gotenks, Fusion Confusion} from your deck, then shuffle your deck.\n"
            "[Auto][Once per turn] Switch this card to Rest Mode: When you attack with a <Gotenks> card with an energy cost of 5 or more, choose up to 1 card in your opponent's Battle Area and use it in a combo in your Combo Area."
        ),
        card_type="Z-BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "self_played" and rule.handler_id == "auto_play_up_to_n_from_owner_deck_on_play" for rule in rules)
    assert any(rule.trigger == "owner_battle_attacks" and rule.handler_id == "auto_rest_self_then_move_up_to_n_opponent_battle_to_owner_combo_on_owner_attack" for rule in rules)


def test_extract_exact_p387_chiaotzu_z_fighter_rules() -> None:
    card = replace(
        _card(
            "[Empower Yellow 2]\n"
            "[Auto] When this card is placed in your Drop Area from your Unison Area, choose up to 1 of your opponent's Battle Cards and switch it to Rest Mode.\n"
            "[+1][Activate: Main] Choose any number of your opponent's Battle Cards whose total energy costs add up to 2 or less and switch them to Rest Mode.\n"
            "[-3][Auto] When your opponent attacks, you may choose 1 of their Battle Cards and negate its keyword skills for the turn."
        ),
        card_type="UNISON",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "self_placed_into_drop" and rule.handler_id == "auto_switch_up_to_n_opponent_battle_rest_on_play" for rule in rules)
    assert any(rule.trigger == "self_activate_main" and rule.handler_id == "activate_switch_up_to_total_cost_n_opponent_battles_rest" for rule in rules)
    assert any(rule.trigger == "owner_opponent_card_attacks" and rule.handler_id == "auto_negate_up_to_n_opponent_battle_keyword_skills_for_turn_on_opponent_attack" for rule in rules)


def test_extract_exact_bt15_150_turles_dark_power_unleashed_rules() -> None:
    card = replace(
        _card(
            "[Auto][Once per turn] When this card KOs an opponent's Battle Card, switch this card to Active Mode, then choose 1 card in your opponent's hand and discard it.\n"
            "[Auto] When this card is removed from your Battle Area by an opponent's skill, choose all of your opponent's Battle Cards in Rest Mode, KO them, then choose all of your opponent's Battle Cards and switch them to Rest Mode."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "self_attacks_battle_end" and rule.handler_id == "auto_switch_self_active_then_opponent_discards_n_on_attack_ko" for rule in rules)
    assert any(rule.trigger == "self_left_battle_area" and rule.handler_id == "auto_ko_all_opponent_rest_battles_then_switch_all_opponent_battles_rest_on_self_left_battle_by_opponent_skill" for rule in rules)


def test_extract_exact_bt17_139_piccolo_fusing_with_nail_rules() -> None:
    card = replace(
        _card(
            "[Permanent] Once per turn, if this card would be KO'd in battle, you may place 1 card from under this card in its owner's Drop Area instead.\n"
            "[Activate: Battle][Once per turn] Switch this card to Rest Mode: Choose up to 1 of your opponent's Battle Cards with an energy cost of 5 or less in Rest Mode and KO it. If you KO'd a card, your opponent discards 1 card from their hand."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.handler_id == "noop_auto" and "would be KO'd in battle" in rule.source_text for rule in rules)
    rule = next(rule for rule in rules if rule.trigger == "self_activate_battle" and rule.handler_id == "activate_ko_up_to_n_opponent_battle")
    assert rule.handler_params["requires_rested"] is True
    assert rule.handler_params["opponent_discard_on_ko"] == 1


def test_extract_exact_bt18_042_paikuhan_glimpse_of_might_rules() -> None:
    card = replace(
        _card(
            "[Auto][Limit 1] If your Leader is a blue <Paikuhan> card: When this card is played, add 1 blue Battle Card from your energy to your Z-Energy. If you do, add this card to your energy.\n"
            "[Activate: Main][Limit 1] Choose up to 1 {Super Paikuhan, True Mastery} in your Unison Area and place this card under it from your Drop."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "self_played" and rule.handler_id == "auto_add_up_to_n_owner_energy_to_z_energy_then_place_self_in_owner_energy_on_play" for rule in rules)
    assert any(rule.trigger == "self_activate_main" and rule.handler_id == "activate_place_self_from_owner_drop_under_named_owner_unison" for rule in rules)


def test_extract_exact_bt18_044_sarta_north_galaxy_warrior_rules() -> None:
    card = replace(
        _card(
            "[Counter: Attack] Negate the attack and play this card.\n"
            "[Permanent] If it's your opponent's turn and 2 or more {Angel Halo} are in your Drop, reduce the energy cost of this card in your hand by 2.\n"
            "[Auto] If your Leader is a blue ≪Another World Budokai≫ card and you discard 1 {Angel Halo} from your hand: When this card is played, your opponent can't attack with Battle Cards with energy costs of 5 or less for the turn unless they place 1 card from their hand at the bottom of their deck each time."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "counter_attack" and rule.handler_id == "noop_auto" for rule in rules)
    rule = next(rule for rule in rules if rule.trigger == "self_played" and rule.handler_id == "auto_discard_named_from_owner_hand_then_limit_opponent_battle_attacks_bottom_deck_each_time_on_play")
    assert rule.handler_params["max_cost"] == 5
    assert rule.handler_params["discard_required_name_contains"] == "ANGEL HALO"


def test_extract_exact_bt18_057_thunder_flash_rules() -> None:
    card = replace(
        _card(
            "[Counter: Attack] Negate the attack.\n"
            "[Activate: Main](Blue), if your Leader is a <Paikuhan> card and you send this card from your Drop to your Warp: Choose up to 1 of your blue <Paikuhan> cards and it gets +5000 power and [Double Strike] for the turn."
        ),
        card_type="EXTRA",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "counter_attack" and rule.handler_id == "noop_auto" for rule in rules)
    rule = next(rule for rule in rules if rule.trigger == "self_activate_main" and rule.handler_id == "activate_buff_owner_battle_cards")
    assert rule.handler_params["grant_keyword"] == "Double Strike"
    assert rule.handler_params["power_delta"] == 5000


def test_extract_exact_bt18_034_cell_awakening_of_the_created_rules() -> None:
    card = replace(
        _card(
            "[Deflect][Critical]\n"
            "[Auto] When this card is played, choose all of your opponent's Battle Cards with energy costs of 5 or less and place them under this card.\n"
            "[Activate: Main][Once per turn] If 1 or more cards are under this card and you place all of them in their owners' Drops: Switch this card to Active Mode. Additionally, if you used this card's skill to place 4 or more cards in Drops, this card gains [Triple Strike] for the turn."
        ),
        card_type="Z-BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "self_played" and rule.handler_id == "auto_place_all_opponent_battles_with_max_cost_under_self_on_play" for rule in rules)
    rule = next(rule for rule in rules if rule.trigger == "self_activate_main" and rule.handler_id == "activate_drop_all_under_self_switch_self_active_and_gain_keyword_if_dropped_n")
    assert rule.handler_params["min_released_for_keyword"] == 4
    assert rule.handler_params["grant_keyword"] == "Triple Strike"


def test_extract_exact_bt15_146_son_goku_hit_temporary_truce_rules() -> None:
    card = replace(
        _card(
            "[Energy-Exhaust][Critical]\n"
            "[Aegis Blue/Yellow][Once per turn]\n"
            "[Permanent] If there's a Blue/Yellow multicolor card in your energy, reduce the combo cost of this card in your hand by 1."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.handler_id == "noop_auto" and "reduce the combo cost" in rule.source_text for rule in rules)


def test_extract_exact_bt18_081_cymbal_demonic_subordinate_rules() -> None:
    card = replace(
        _card(
            "[Auto] When this card attacks, choose up to 2 ≪Demon Clan≫ cards in your Battle Area and they get +5000 power for the turn.\n"
            "[Auto](1), if your Leader is a <King Piccolo> card: When this card is used in a combo, choose up to 1 of your Leaders and it gains [Double Strike] for the battle."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(rule for rule in rules if rule.trigger == "self_attacks" and rule.handler_id == "auto_buff_owner_battle_cards")
    assert rule.handler_params["max_targets"] == 2
    assert rule.handler_params["required_traits"] == "Demon Clan"
    assert rule.handler_params["power_delta"] == 5000
    rule = next(rule for rule in rules if rule.trigger == "self_comboed" and rule.handler_id == "auto_grant_owner_leader_keyword_for_battle_on_combo")
    assert rule.handler_params["grant_keyword"] == "Double Strike"
    assert rule.handler_params["leader_required_characters"] == "King Piccolo"


def test_extract_exact_bt18_085_ss_son_goten_ss_trunks_unfurled_potential_rules() -> None:
    card = replace(
        _card(
            "[Auto][Limit 1] If your Leader is green and has <Gotenks> in its character name: When this card is placed in your Drop from your hand by [Union-Fusion], you may choose your Leader and it gets +5000 power for the turn.\n"
            "[Auto] When this card is placed in a Drop from your Z-Energy, remove it from the game.\n"
            "[Activate: Battle][Limit 1] If your Leader is a green card with <Gotenks> in its character name and one of your green cards with <Gotenks> in its character name is in a battle: Use this card in a combo from your Drop. At the end of the battle, send this card from your Drop to your Warp."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(rule for rule in rules if rule.trigger == "self_placed_into_drop" and rule.handler_id == "auto_buff_owner_leader_for_turn")
    assert rule.handler_params["power_delta"] == 5000
    assert rule.handler_params["required_drop_causes"] == "union_fusion"
    assert any(rule.trigger == "self_placed_into_drop" and rule.handler_id == "auto_remove_self_from_owner_drop_if_placed_from_z_energy" for rule in rules)
    assert any(rule.trigger == "self_activate_battle" and rule.handler_id == "activate_combo_self_from_owner_drop" for rule in rules)
    rule = next(rule for rule in rules if rule.trigger == "self_comboed_battle_end" and rule.handler_id == "auto_send_self_to_owner_warp_on_battle_end")
    assert rule.handler_params["requires_comboed_from"] == "drop"


def test_extract_exact_bt18_070_son_goku_skills_improved_rules() -> None:
    card = replace(
        _card(
            "[Auto][Limit 1](Green), if you choose 1 of your green ≪Turtle School≫ <Son Goku: Childhood> cards with an energy cost of 1 and place it in its owner's Drop: When one of your cards attacks and KOs an opponent's Battle Card, draw 1 card, and play this card from your hand.\n"
            "[Auto][Limit 1] When this card attacks and KOs a Battle Card, switch this card to Active Mode, and your opponent discards 1 card from their hand."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    assert any(rule.trigger == "owner_battle_ko_opponent_battle_battle_end" and rule.handler_id == "auto_draw_n" for rule in rules)
    assert any(rule.trigger == "owner_battle_ko_opponent_battle_battle_end" and rule.handler_id == "auto_play_self_from_hand_on_owner_battle_ko" for rule in rules)
    rule = next(rule for rule in rules if rule.trigger == "self_attacks_battle_end" and rule.handler_id == "auto_switch_self_active_then_opponent_discards_n_on_self_attack_ko")
    assert rule.handler_params["discard_count"] == 1


def test_extract_exact_bt18_062_pr2_turtle_school_inheritors_rules() -> None:
    card = replace(
        _card(
            "[Deflect]\n"
            "[Activate: Main] If your opponent has 3 or more energy and you place 1 ≪Turtle School≫ card from your Z-Energy in its owner's Drop: Play up to 1 green ≪Turtle School≫ card with 20000 power that doesn't have <Master Roshi> and which you haven't played this turn from your deck with its keyword skills negated for the turn, then shuffle your deck."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(rule for rule in rules if rule.trigger == "self_activate_main" and rule.handler_id == "activate_play_up_to_n_from_owner_deck")
    assert rule.handler_params["max_power"] == 20000
    assert rule.handler_params["required_name_excludes"] == "MASTER ROSHI"
    assert rule.handler_params["negate_skills"] is True


def test_extract_exact_bt15_147_vegeta_cabba_lessons_learned_rules() -> None:
    card = replace(
        _card(
            "[Energy-Exhaust][Dual Attack]\n"
            "[Arrival Blue/Yellow](Blue)/(Yellow)\n"
            "[Auto] When this card is played, choose up to 1 of your opponent's Battle Cards with an energy cost of 4 or less in Rest Mode and place it at the bottom of its owner's deck."
        ),
        card_type="BATTLE",
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(rule for rule in rules if rule.trigger == "self_played" and rule.handler_id == "auto_bottom_deck_up_to_n_opponent_rest_battle_on_play")
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["max_cost"] == 4
