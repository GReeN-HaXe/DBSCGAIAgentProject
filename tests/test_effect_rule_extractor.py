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


def test_extract_self_ko_can_play_up_to_n_named_from_owner_drop_rule() -> None:
    card = _card(
        "[Auto] When this card is removed from a Battle Area by an opponent's skill or KO'd, play up to 1 {Negative Energy Four-Star Ball} from your Drop."
    )
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_play_up_to_n_named_from_owner_drop_on_self_ko")
    assert rule.trigger == "self_koed"
    assert rule.handler_params["max_targets"] == 1
    assert rule.handler_params["required_name_contains"] == "NEGATIVE ENERGY FOUR-STAR BALL"


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


def test_extract_attack_self_gain_power_per_owner_warp_rule() -> None:
    card = _card("[Auto] When this card attacks, this card gains +5000 power for each card in your Warp.")
    rules = extract_effect_rules_from_card(card)
    rule = next(r for r in rules if r.handler_id == "auto_self_gain_power_for_turn_on_attack")
    assert rule.trigger == "self_attacks"
    assert rule.handler_params["power_delta"] == "expr:owner_warp_count*5000"


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
