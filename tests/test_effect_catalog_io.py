from __future__ import annotations

import json
from pathlib import Path
import shutil
import uuid

from src.game import Action, ActionType, CardInstance, RulesEngine, TurnPhase
from src.game.effect_rules import (
    DEFAULT_EFFECT_CATALOG_RELATIVE_PATH,
    DEFAULT_EFFECT_CATALOG_SHARD_RELATIVE_DIR,
    EFFECT_CATALOG_KIND,
    EFFECT_CATALOG_MANIFEST_KIND,
    EFFECT_CATALOG_MANIFEST_SCHEMA_VERSION,
    EFFECT_CATALOG_OVERRIDE_KIND,
    EFFECT_CATALOG_OVERRIDE_SCHEMA_VERSION,
    EFFECT_CATALOG_SCHEMA_VERSION,
    EffectRule,
    default_effect_catalog_path,
    load_effect_rule_overrides_json,
    load_effect_rules_json,
    merge_effect_rule_overrides,
    save_effect_rules_sharded_json,
    save_effect_rule_overrides_json,
    save_effect_rules_json,
)

OVERRIDES_PATH = Path("dbdatabase/effect_catalog_overrides.json")


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _to_main(engine: RulesEngine, state):
    while state.phase != TurnPhase.MAIN:
        state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=state.active_player))
    return state


def _scratch_dir() -> Path:
    path = Path("artifacts/test_tmp_effect_catalog_io") / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_effect_catalog_json_roundtrip() -> None:
    source = {
        101: (
            EffectRule(
                trigger="self_played",
                handler_id="auto_draw_n",
                handler_params={"amount": 2},
                once_per_turn=True,
                family_id="self_played:auto_draw_n",
                provenance="manual",
            ),
        ),
        202: (
            EffectRule(
                trigger="self_attacks",
                handler_id="auto_draw_n",
                handler_params={"amount": 1},
                once_per_turn=False,
                family_id="self_attacks:auto_draw_n",
                provenance="manual",
            ),
        ),
    }
    scratch = _scratch_dir()
    try:
        path = scratch / "catalog.json"
        save_effect_rules_json(path, source)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["catalog_kind"] == EFFECT_CATALOG_KIND
        assert raw["schema_version"] == EFFECT_CATALOG_SCHEMA_VERSION
        assert raw["card_rule_count"] == 2
        assert raw["effect_rule_count"] == 2
        assert set(raw["rules"].keys()) == {"101", "202"}
        assert raw["rules"]["101"][0]["family_id"] == "self_played:auto_draw_n"
        assert raw["rules"]["101"][0]["provenance"] == "manual"
        loaded = load_effect_rules_json(path)
        assert set(loaded.keys()) == {101, 202}
        assert loaded[101][0].handler_params["amount"] == 2
        assert loaded[101][0].once_per_turn is True
        assert loaded[101][0].family_id == "self_played:auto_draw_n"
        assert loaded[101][0].provenance == "manual"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_effect_catalog_loader_accepts_legacy_plain_rule_map() -> None:
    scratch = _scratch_dir()
    try:
        path = scratch / "legacy_catalog.json"
        path.write_text(
            json.dumps(
                {
                    "303": [
                        {
                            "trigger": "self_played",
                            "handler_id": "auto_draw_n",
                            "handler_params": {"amount": 1},
                            "once_per_turn": False,
                            "limit_per_turn": None,
                            "limit_scope": "card_number",
                            "family_id": "self_played:auto_draw_n",
                            "provenance": "legacy-test",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        loaded = load_effect_rules_json(path)
        assert set(loaded.keys()) == {303}
        assert loaded[303][0].handler_id == "auto_draw_n"
        assert loaded[303][0].family_id == "self_played:auto_draw_n"
        assert loaded[303][0].provenance == "legacy-test"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_default_effect_catalog_path_prefers_shards_and_falls_back_to_merged() -> None:
    scratch = _scratch_dir()
    try:
        merged_path = scratch / DEFAULT_EFFECT_CATALOG_RELATIVE_PATH
        shard_dir = scratch / DEFAULT_EFFECT_CATALOG_SHARD_RELATIVE_DIR
        merged_path.parent.mkdir(parents=True, exist_ok=True)
        merged_path.write_text("{}", encoding="utf-8")
        assert default_effect_catalog_path(scratch) == merged_path
        shard_dir.mkdir(parents=True, exist_ok=True)
        assert default_effect_catalog_path(scratch) == shard_dir
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_effect_catalog_sharded_roundtrip_and_directory_load() -> None:
    source = {
        card_id: (
            EffectRule(
                trigger="self_played",
                handler_id="auto_draw_n",
                handler_params={"amount": card_id % 3 + 1},
                family_id="self_played:auto_draw_n",
                provenance="sharded-test",
            ),
        )
        for card_id in range(100, 107)
    }
    scratch = _scratch_dir()
    try:
        shard_dir = scratch / "catalog_shards"
        manifest_path = save_effect_rules_sharded_json(shard_dir, source, shard_size=3)
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert raw_manifest["catalog_kind"] == EFFECT_CATALOG_MANIFEST_KIND
        assert raw_manifest["schema_version"] == EFFECT_CATALOG_MANIFEST_SCHEMA_VERSION
        assert raw_manifest["card_rule_count"] == len(source)
        assert raw_manifest["effect_rule_count"] == len(source)
        assert raw_manifest["shard_count"] == 3
        assert len(list(shard_dir.glob("shard_*.json"))) == 3

        loaded_from_manifest = load_effect_rules_json(manifest_path)
        loaded_from_dir = load_effect_rules_json(shard_dir)
        assert set(loaded_from_manifest.keys()) == set(source.keys())
        assert loaded_from_manifest == loaded_from_dir
        assert loaded_from_dir[100][0].provenance == "sharded-test"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_effect_catalog_override_json_roundtrip_and_merge_modes() -> None:
    overrides = {
        101: (
            "append",
            (
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_draw_n",
                    handler_params={"amount": 1},
                    family_id="self_attacks:auto_draw_n",
                    provenance="override",
                ),
            ),
        ),
        202: (
            "replace",
            (
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_ko_opponent_battle_on_play",
                    handler_params={"max_cost": -1},
                    family_id="self_played:auto_ko_opponent_battle_on_play",
                    provenance="override",
                ),
            ),
        ),
    }
    scratch = _scratch_dir()
    try:
        path = scratch / "catalog_overrides.json"
        save_effect_rule_overrides_json(path, overrides)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["catalog_kind"] == EFFECT_CATALOG_OVERRIDE_KIND
        assert raw["schema_version"] == EFFECT_CATALOG_OVERRIDE_SCHEMA_VERSION
        assert raw["override_count"] == 2
        assert raw["overrides"]["101"]["mode"] == "append"
        loaded = load_effect_rule_overrides_json(path)
        assert loaded[101][0] == "append"
        assert loaded[202][0] == "replace"
        base = {
            101: (
                EffectRule(
                    trigger="self_played",
                    handler_id="auto_draw_n",
                    handler_params={"amount": 2},
                    family_id="self_played:auto_draw_n",
                    provenance="base",
                ),
            ),
            202: (
                EffectRule(
                    trigger="self_attacks",
                    handler_id="auto_draw_n",
                    handler_params={"amount": 1},
                    family_id="self_attacks:auto_draw_n",
                    provenance="base",
                ),
            ),
        }
        merged = merge_effect_rule_overrides(base, loaded)
        assert len(merged[101]) == 2
        assert merged[202][0].handler_id == "auto_ko_opponent_battle_on_play"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_checked_in_effect_catalog_overrides_cover_known_edge_cases() -> None:
    if not OVERRIDES_PATH.exists():
        return
    loaded = load_effect_rule_overrides_json(OVERRIDES_PATH)
    assert len(loaded) == 82
    assert loaded[86][0] == "replace"
    assert loaded[90][0] == "replace"
    assert loaded[8372][0] == "replace"
    assert loaded[20][0] == "replace"
    assert loaded[27][0] == "replace"
    assert loaded[36][0] == "replace"
    assert loaded[6][0] == "replace"
    assert loaded[49][0] == "replace"
    assert loaded[83][0] == "replace"
    assert loaded[1603][0] == "replace"
    assert loaded[1702][0] == "replace"
    assert loaded[2409][0] == "replace"
    assert loaded[4226][0] == "replace"
    assert loaded[5656][0] == "replace"
    assert loaded[6581][0] == "replace"
    assert loaded[5531][0] == "replace"
    assert loaded[6947][0] == "replace"
    assert loaded[7358][0] == "replace"
    assert loaded[7236][0] == "replace"
    assert loaded[7459][0] == "replace"
    assert loaded[7786][0] == "replace"
    assert loaded[7848][0] == "replace"
    assert loaded[7908][0] == "replace"
    assert loaded[7798][0] == "replace"
    assert loaded[8314][0] == "replace"
    assert loaded[8323][0] == "replace"
    assert loaded[4265][0] == "replace"
    assert loaded[5301][0] == "replace"
    assert loaded[8458][0] == "replace"
    assert loaded[6679][0] == "replace"
    assert loaded[6733][0] == "replace"
    assert loaded[7386][0] == "replace"
    assert loaded[23][0] == "replace"
    assert loaded[1002][0] == "replace"
    assert loaded[6299][0] == "replace"
    assert loaded[8385][0] == "replace"
    assert loaded[8881][0] == "replace"
    assert loaded[8896][0] == "replace"
    assert loaded[9720][0] == "replace"
    assert loaded[1063][0] == "replace"
    assert loaded[1632][0] == "replace"
    assert loaded[7839][0] == "replace"
    assert loaded[8233][0] == "replace"
    assert loaded[41][0] == "replace"
    assert loaded[5826][0] == "replace"
    assert loaded[7846][0] == "replace"
    assert loaded[8492][0] == "replace"
    assert loaded[8448][0] == "replace"
    assert loaded[892][0] == "replace"
    assert loaded[40][0] == "replace"
    assert loaded[6820][0] == "replace"
    assert loaded[8444][0] == "replace"
    assert loaded[1480][0] == "replace"
    assert loaded[1509][0] == "replace"
    assert loaded[4949][0] == "replace"
    assert loaded[7906][0] == "replace"
    assert loaded[7940][0] == "replace"
    assert loaded[2461][0] == "replace"
    assert loaded[6997][0] == "replace"
    assert loaded[7910][0] == "replace"
    king_cold_rule = loaded[20][1][0]
    broly_combo_rule = loaded[27][1][0]
    prismatic_broly_auto = loaded[36][1][0]
    prismatic_broly_activate = loaded[36][1][1]
    dyspo_rule = loaded[6][1][0]
    majin_buu_rule = loaded[1603][1][0]
    android_21_auto = loaded[1702][1][0]
    android_21_activate = loaded[1702][1][1]
    prismatic_gohan_rule = loaded[49][1][0]
    gigantic_rule = loaded[83][1][0]
    steadfast_rule = loaded[89][1][0]
    explosive_rule = loaded[2409][1][0]
    released_rule = loaded[4226][1][0]
    cabba_rule = loaded[5656][1][0]
    king_vegeta_rule = loaded[6581][1][0]
    bardock_rule = loaded[5531][1][0]
    nappa_rule = loaded[6947][1][0]
    dormant_rule = loaded[7358][1][0]
    supreme_kai_rule = loaded[7236][1][0]
    difference_rule = loaded[7459][1][0]
    stone_dabura_auto = loaded[7786][1][0]
    stone_dabura_activate = loaded[7786][1][1]
    haze_play_rule = loaded[7848][1][0]
    haze_attack_rule = loaded[7848][1][1]
    haze_combo_rule = loaded[7848][1][2]
    krillin_wish_rule = loaded[7908][1][0]
    wormhole_opened_auto_rule = loaded[7798][1][0]
    wormhole_opened_plus_rule = loaded[7798][1][1]
    wormhole_opened_minus_rule = loaded[7798][1][2]
    mechikabura_rule = loaded[8314][1][0]
    demigra_wormhole_play_rule = loaded[8323][1][0]
    demigra_wormhole_removed_rule = loaded[8323][1][1]
    demigra_wormhole_activate_rule = loaded[8323][1][2]
    petrification_rule = loaded[4265][1][0]
    yamcha_rule = loaded[5301][1][0]
    final_battle_rule = loaded[8458][1][0]
    toppo_rule = loaded[6679][1][0]
    veku_turn_start_rule = loaded[6733][1][0]
    veku_turn_end_rule = loaded[6733][1][1]
    koitsukai_rule = loaded[7386][1][0]
    works_undone_rule = loaded[23][1][0]
    cell_auto_rule = loaded[1002][1][0]
    cell_activate_rule = loaded[1002][1][1]
    piccolo_jr_rule = loaded[6299][1][0]
    no_challenge_rule = loaded[7839][1][0]
    overwhelming_might_rule = loaded[1632][1][0]
    power_release_rule = loaded[8233][1][0]
    prismatic_aegis_auto_rule = loaded[41][1][0]
    prismatic_aegis_activate_rule = loaded[41][1][1]
    temporal_darkness_rule = loaded[5826][1][0]
    gogeta_next_level_rule = loaded[7846][1][0]
    dabura_negation_rule = loaded[8492][1][0]
    dabura_rest_rule = loaded[8492][1][1]
    jiren_climactic_rule = loaded[8448][1][0]
    oolong_rule = loaded[892][1][0]
    prismatic_bardock_counter_rule = loaded[40][1][0]
    scramble_play_rule = loaded[6820][1][0]
    scramble_combo_rule = loaded[6820][1][1]
    bold_arrival_rule = loaded[8444][1][0]
    stronger_together_play_rule = loaded[1480][1][0]
    stronger_together_activate_rule = loaded[1480][1][1]
    pan_glimpse_draw_rule = loaded[1509][1][0]
    pan_glimpse_activate_rule = loaded[1509][1][1]
    special_beam_rule = loaded[2064][1][0]
    paragus_draw_rule = loaded[2461][1][0]
    paragus_play_rule = loaded[2461][1][1]
    paragus_transfer_rule = loaded[2461][1][2]
    crimson_guardian_rule = loaded[2481][1][0]
    almighty_rule = loaded[4949][1][0]
    vegito_barrage_rule = loaded[8315][1][0]
    accidental_wish_rule = loaded[7906][1][0]
    guided_android_rule = loaded[7940][1][0]
    super_kamehameha_rule = loaded[6997][1][0]
    scheme_wish_plus_rule = loaded[7910][1][0]
    scheme_wish_minus_rule = loaded[7910][1][1]
    reclaiming_hope_activate = loaded[86][1][0]
    reclaiming_hope_auto = loaded[86][1][1]
    misadventure_rule = loaded[90][1][0]
    android_attack_rule = loaded[8372][1][0]
    android_plus_rule = loaded[8372][1][1]
    android_zero_rule = loaded[8372][1][2]
    justice_impact_auto = loaded[8385][1][0]
    justice_impact_activate = loaded[8385][1][1]
    frieza_rule = loaded[8881][1][0]
    nail_rule = loaded[8896][1][0]
    fused_zamasu_rule = loaded[9720][1][0]
    pan_rule = loaded[1063][1][0]
    assert king_cold_rule.handler_id == "auto_reduce_next_matching_extra_skill_cost_from_hand_on_combo"
    assert king_cold_rule.family_id == "self_comboed:auto_reduce_next_matching_extra_skill_cost_from_hand_on_combo"
    assert broly_combo_rule.handler_id == "activate_send_up_to_n_opponent_combo_to_drop"
    assert broly_combo_rule.family_id == "self_activate_battle:activate_send_up_to_n_opponent_combo_to_drop"
    assert prismatic_broly_auto.handler_id == "auto_add_markers_per_n_multicolor_energy_on_play"
    assert prismatic_broly_auto.family_id == "self_played:auto_add_markers_per_n_multicolor_energy_on_play"
    assert prismatic_broly_activate.handler_id == "activate_send_up_to_n_opponent_battle_to_warp"
    assert prismatic_broly_activate.family_id == "self_activate_main:activate_send_up_to_n_opponent_battle_to_warp"
    assert dyspo_rule.handler_id == "counter_negate_attack_play_self_attack_restriction"
    assert dyspo_rule.trigger == "counter_attack"
    assert majin_buu_rule.handler_id == "activate_flip_owner_leader_to_back_draw_n_and_send_self_to_removed"
    assert majin_buu_rule.family_id == "self_activate_main:activate_flip_owner_leader_to_back_draw_n_and_send_self_to_removed"
    assert android_21_auto.handler_id == "auto_add_top_deck_to_energy_rest_and_bottom_deck_up_to_n_opponent_battle_on_play"
    assert android_21_auto.family_id == "self_played:auto_add_top_deck_to_energy_rest_and_bottom_deck_up_to_n_opponent_battle_on_play"
    assert android_21_activate.handler_id == "activate_gain_keyword_from_under_self_until_opponent_turn_end"
    assert android_21_activate.family_id == "self_activate_main:activate_gain_keyword_from_under_self_until_opponent_turn_end"
    assert prismatic_gohan_rule.handler_id == "auto_send_up_to_n_opponent_battle_to_warp_on_play"
    assert prismatic_gohan_rule.family_id == "self_played:auto_send_up_to_n_opponent_battle_to_warp_on_play"
    assert gigantic_rule.handler_id == "activate_ko_opponent_battles_up_to_total_power"
    assert gigantic_rule.family_id == "self_activate_extra_from_hand:activate_ko_opponent_battles_up_to_total_power"
    assert steadfast_rule.handler_id == "counter_force_pending_play_rest_play_self_draw_n"
    assert steadfast_rule.family_id == "counter_play:counter_force_pending_play_rest_play_self_draw_n"
    assert explosive_rule.handler_id == "counter_negate_attack"
    assert explosive_rule.trigger == "counter_attack"
    assert released_rule.handler_id == "counter_negate_attacker_skills_and_prevent_switch_active"
    assert released_rule.family_id == "counter_attack:counter_negate_attacker_skills_and_prevent_switch_active"
    assert cabba_rule.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play"
    assert cabba_rule.trigger == "self_played"
    assert king_vegeta_rule.handler_id == "counter_reduce_attacker_and_apply_attack_power_tax"
    assert king_vegeta_rule.family_id == "counter_attack:counter_reduce_attacker_and_apply_attack_power_tax"
    assert bardock_rule.handler_id == "auto_restrict_self_copies_from_hand_next_turn_on_play"
    assert nappa_rule.handler_id == "auto_play_self_from_combo_on_battle_end"
    assert nappa_rule.family_id == "self_comboed_battle_end:auto_play_self_from_combo_on_battle_end"
    assert koitsukai_rule.handler_id == "activate_remove_self_from_drop_bottom_deck_hand_draw_and_punish_low_power_battle_play"
    assert koitsukai_rule.family_id == "self_activate_main:activate_remove_self_from_drop_bottom_deck_hand_draw_and_punish_low_power_battle_play"
    assert works_undone_rule.handler_id == "activate_add_marker_to_matching_owner_unison_and_place_self_under_it"
    assert works_undone_rule.family_id == "self_activate_main:activate_add_marker_to_matching_owner_unison_and_place_self_under_it"
    assert cell_auto_rule.handler_id == "auto_place_all_opponent_battles_up_to_cost_under_self_on_play"
    assert cell_auto_rule.family_id == "self_played:auto_place_all_opponent_battles_up_to_cost_under_self_on_play"
    assert cell_activate_rule.handler_id == "activate_drop_all_under_self_switch_self_active_and_gain_keyword_if_dropped_n"
    assert cell_activate_rule.family_id == "self_activate_main:activate_drop_all_under_self_switch_self_active_and_gain_keyword_if_dropped_n"
    assert piccolo_jr_rule.handler_id == "auto_alliance_rest_matching_owner_battles_gain_power_draw_n_and_deal_damage"
    assert piccolo_jr_rule.family_id == "self_attacks:auto_alliance_rest_matching_owner_battles_gain_power_draw_n_and_deal_damage"
    assert no_challenge_rule.handler_id == "auto_remove_self_prevent_leader_damage_and_battle_ko_for_battle"
    assert no_challenge_rule.family_id == "owner_opponent_card_attacks:auto_remove_self_prevent_leader_damage_and_battle_ko_for_battle"
    assert overwhelming_might_rule.handler_id == "auto_apply_non_leader_attack_rest_tax_warp_self_and_optionally_negate_opponent_strike"
    assert overwhelming_might_rule.family_id == "self_played:auto_apply_non_leader_attack_rest_tax_warp_self_and_optionally_negate_opponent_strike"
    assert power_release_rule.handler_id == "counter_play_self_buff_owner_cards_for_battle"
    assert power_release_rule.family_id == "counter_attack:counter_play_self_buff_owner_cards_for_battle"
    assert bardock_rule.family_id == "self_played:auto_restrict_self_copies_from_hand_next_turn_on_play"
    assert dormant_rule.handler_id == "counter_negate_attack"
    assert dormant_rule.family_id == "counter_attack:counter_negate_attack"
    assert supreme_kai_rule.handler_id == "counter_negate_attack_play_self"
    assert supreme_kai_rule.trigger == "counter_attack"
    assert difference_rule.handler_id == "counter_spirit_boost_power_reduce_opponent_cards"
    assert difference_rule.family_id == "counter_attack:counter_spirit_boost_power_reduce_opponent_cards"
    assert stone_dabura_auto.handler_id == "auto_negate_skills_and_restrict_up_to_n_opponent_battle_on_attack"
    assert stone_dabura_auto.family_id == "owner_opponent_card_attacks:auto_negate_skills_and_restrict_up_to_n_opponent_battle_on_attack"
    assert stone_dabura_activate.handler_id == "activate_bottom_deck_up_to_n_opponent_battle_then_switch_up_to_n_owner_energy_active_at_turn_end"
    assert stone_dabura_activate.family_id == "self_activate_main:activate_bottom_deck_up_to_n_opponent_battle_then_switch_up_to_n_owner_energy_active_at_turn_end"
    assert haze_play_rule.handler_id == "auto_switch_up_to_n_opponent_board_rest"
    assert haze_play_rule.family_id == "self_played:auto_switch_up_to_n_opponent_board_rest"
    assert haze_attack_rule.handler_id == "auto_switch_up_to_n_opponent_board_rest"
    assert haze_attack_rule.family_id == "self_attacks:auto_switch_up_to_n_opponent_board_rest"
    assert haze_combo_rule.handler_id == "auto_place_up_to_n_from_owner_drop_under_named_owner_battle_on_combo"
    assert haze_combo_rule.family_id == "owner_card_comboed:auto_place_up_to_n_from_owner_drop_under_named_owner_battle_on_combo"
    assert krillin_wish_rule.handler_id == "activate_bottom_deck_up_to_n_opponent_battle"
    assert krillin_wish_rule.family_id == "self_activate_main:activate_bottom_deck_up_to_n_opponent_battle"
    assert wormhole_opened_auto_rule.handler_id == "auto_draw_n_discard_n"
    assert wormhole_opened_auto_rule.family_id == "owner_other_battle_played_by_over_realm:auto_draw_n_discard_n"
    assert wormhole_opened_plus_rule.handler_id == "activate_send_up_to_n_from_owner_warp_to_drop_and_gain_keyword_for_turn"
    assert wormhole_opened_minus_rule.handler_id == "activate_buff_owner_battle_cards"
    assert mechikabura_rule.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play"
    assert mechikabura_rule.trigger == "self_activate_main"
    assert demigra_wormhole_play_rule.handler_id == "auto_place_top_n_from_owner_deck_into_drop"
    assert demigra_wormhole_play_rule.family_id == "self_played:auto_place_top_n_from_owner_deck_into_drop"
    assert demigra_wormhole_removed_rule.trigger == "self_removed_from_game"
    assert demigra_wormhole_activate_rule.handler_id == "activate_play_up_to_n_from_owner_warp"
    assert demigra_wormhole_activate_rule.family_id == "self_activate_main:activate_play_up_to_n_from_owner_warp"
    assert petrification_rule.handler_id == "counter_negate_attack"
    assert petrification_rule.family_id == "counter_attack:counter_negate_attack"
    assert yamcha_rule.handler_id == "counter_power_reduce_up_to_n_opponent_battle_for_turn_play_self"
    assert yamcha_rule.family_id == "counter_play:counter_power_reduce_up_to_n_opponent_battle_for_turn_play_self"
    assert final_battle_rule.handler_id == "counter_negate_attack"
    assert final_battle_rule.family_id == "counter_attack:counter_negate_attack"
    assert toppo_rule.handler_id == "counter_negate_attack_play_self"
    assert toppo_rule.family_id == "counter_attack:counter_negate_attack_play_self"
    assert veku_turn_start_rule.handler_id == "auto_transfer_self_control_to_opponent"
    assert veku_turn_start_rule.family_id == "turn_start:auto_transfer_self_control_to_opponent"
    assert veku_turn_end_rule.handler_id == "auto_transfer_self_control_to_opponent"
    assert veku_turn_end_rule.family_id == "turn_end:auto_transfer_self_control_to_opponent"
    assert reclaiming_hope_activate.handler_id == "activate_restrict_up_to_n_opponent_battle_attack_until_opponent_turn_end"
    assert reclaiming_hope_auto.handler_id == "auto_rest_owner_battle_on_self_blocker_activated_switch_self_active"
    assert misadventure_rule.handler_id == "auto_play_self_from_hand_on_owner_field_extra_to_drop_switch_up_to_n_opponent_board_rest"
    assert android_attack_rule.handler_id == "auto_add_up_to_n_matching_from_owner_energy_to_hand_on_attack"
    assert android_plus_rule.handler_id == "activate_bottom_deck_up_to_n_opponent_battle_then_switch_self_active_at_turn_end"
    assert android_zero_rule.handler_id == "activate_opponent_bottom_decks_n_from_hand_and_switch_up_to_n_owner_energy_active_at_turn_end"
    assert justice_impact_auto.handler_id == "auto_switch_up_to_n_owner_leader_active_on_field_extra_placed"
    assert justice_impact_activate.handler_id == "activate_remove_self_and_ko_all_opponent_battles"
    assert frieza_rule.handler_id == "activate_self_gain_power_and_reduce_up_to_n_opponent_battle_for_turn"
    assert nail_rule.handler_id == "counter_play_self_buff_owner_cards_for_battle"
    assert nail_rule.family_id == "counter_attack:counter_play_self_buff_owner_cards_for_battle"
    assert fused_zamasu_rule.handler_id == "activate_switch_self_active_and_gain_power_for_turn"
    assert pan_rule.handler_id == "auto_buff_played_battle_and_draw_if_power_at_least"
    assert pan_rule.family_id == "owner_other_battle_played:auto_buff_played_battle_and_draw_if_power_at_least"
    assert prismatic_aegis_auto_rule.handler_id == "auto_power_reduce_up_to_n_opponent_cards_for_turn_on_play"
    assert prismatic_aegis_auto_rule.family_id == "self_played:auto_power_reduce_up_to_n_opponent_cards_for_turn_on_play"
    assert prismatic_aegis_activate_rule.handler_id == "activate_power_reduce_up_to_n_opponent_battle_for_turn"
    assert prismatic_aegis_activate_rule.family_id == "self_activate_battle:activate_power_reduce_up_to_n_opponent_battle_for_turn"
    assert temporal_darkness_rule.handler_id == "auto_send_up_to_n_opponent_battle_to_warp_and_play_up_to_n_from_owner_warp_on_play"
    assert temporal_darkness_rule.family_id == "self_played:auto_send_up_to_n_opponent_battle_to_warp_and_play_up_to_n_from_owner_warp_on_play"
    assert gogeta_next_level_rule.handler_id == "auto_add_life_to_hand_and_buff_owner_leader_on_owner_matching_battle_played"
    assert gogeta_next_level_rule.family_id == "owner_other_battle_played:auto_add_life_to_hand_and_buff_owner_leader_on_owner_matching_battle_played"
    assert dabura_negation_rule.family_id == "self_permanent:protect_owner_battle_skills_from_opponent_negation"
    assert dabura_rest_rule.family_id == "self_permanent:protect_owner_cards_from_opponent_rest"
    assert jiren_climactic_rule.handler_id == "auto_negate_attack_on_opponent_attack"
    assert oolong_rule.handler_id == "activate_copy_battle_power_to_self_for_turn"
    assert oolong_rule.family_id == "self_activate_main:activate_copy_battle_power_to_self_for_turn"
    assert prismatic_bardock_counter_rule.handler_id == "counter_play_self_and_place_pending_played_battle_to_drop_if_power_at_most"
    assert prismatic_bardock_counter_rule.family_id == "counter_play:counter_play_self_and_place_pending_played_battle_to_drop_if_power_at_most"
    assert scramble_play_rule.handler_id == "auto_place_life_to_drop_and_deal_damage_on_play"
    assert scramble_play_rule.family_id == "self_played:auto_place_life_to_drop_and_deal_damage_on_play"
    assert scramble_combo_rule.handler_id == "auto_send_up_to_n_opponent_combo_to_drop_on_opponent_combo"
    assert scramble_combo_rule.family_id == "owner_opponent_card_comboed:auto_send_up_to_n_opponent_combo_to_drop_on_opponent_combo"
    assert bold_arrival_rule.handler_id == "auto_send_owner_drop_to_warp_and_reduce_up_to_n_opponent_battle_for_turn_on_self_or_opponent_battle_played"
    assert bold_arrival_rule.family_id == "self_or_opponent_battle_played:auto_send_owner_drop_to_warp_and_reduce_up_to_n_opponent_battle_for_turn_on_self_or_opponent_battle_played"
    assert stronger_together_play_rule.handler_id == "auto_opponent_bottom_decks_from_hand_until_n_on_play"
    assert stronger_together_play_rule.family_id == "self_played:auto_opponent_bottom_decks_from_hand_until_n_on_play"
    assert stronger_together_activate_rule.handler_id == "activate_gain_power_and_keyword_for_battle"
    assert stronger_together_activate_rule.family_id == "self_activate_battle:activate_gain_power_and_keyword_for_battle"
    assert pan_glimpse_draw_rule.handler_id == "auto_draw_n"
    assert pan_glimpse_draw_rule.family_id == "self_played:auto_draw_n"
    assert pan_glimpse_activate_rule.handler_id == "activate_transfer_self_control_to_opponent"
    assert pan_glimpse_activate_rule.family_id == "self_activate_main:activate_transfer_self_control_to_opponent"
    assert special_beam_rule.handler_id == "activate_ko_up_to_n_opponent_battle_and_buff_owner_cards_for_battle"
    assert special_beam_rule.family_id == "self_activate_extra_from_hand:activate_ko_up_to_n_opponent_battle_and_buff_owner_cards_for_battle"
    assert paragus_draw_rule.handler_id == "auto_draw_n"
    assert paragus_draw_rule.family_id == "self_played:auto_draw_n"
    assert paragus_play_rule.handler_id == "auto_play_up_to_n_from_owner_deck_on_play"
    assert paragus_play_rule.family_id == "self_played:auto_play_up_to_n_from_owner_deck_on_play"
    assert paragus_transfer_rule.handler_id == "auto_transfer_self_control_to_opponent_on_play"
    assert paragus_transfer_rule.family_id == "self_played:auto_transfer_self_control_to_opponent_on_play"
    assert crimson_guardian_rule.handler_id == "activate_switch_self_active_and_power_reduce_up_to_n_opponent_battle_for_turn"
    assert crimson_guardian_rule.family_id == "self_activate_main:activate_switch_self_active_and_power_reduce_up_to_n_opponent_battle_for_turn"
    assert vegito_barrage_rule.trigger == "self_permanent"
    assert vegito_barrage_rule.family_id == "self_permanent:reduce_own_z_deck_cost_if_owner_battle_with_skill_text_in_play"
    assert almighty_rule.handler_id == "counter_negate_counter_attack"
    assert almighty_rule.family_id == "counter_counter:counter_negate_counter_attack"
    assert accidental_wish_rule.handler_id == "activate_power_reduce_up_to_n_opponent_battle_for_turn"
    assert accidental_wish_rule.family_id == "self_activate_main:activate_power_reduce_up_to_n_opponent_battle_for_turn"
    assert guided_android_rule.handler_id == "auto_switch_up_to_n_opponent_battle_rest_on_play"
    assert guided_android_rule.family_id == "self_played:auto_switch_up_to_n_opponent_battle_rest_on_play"
    assert super_kamehameha_rule.handler_id == "counter_place_pending_played_battle_to_warp_if_cost_at_most"
    assert super_kamehameha_rule.family_id == "counter_play:counter_place_pending_played_battle_to_warp_if_cost_at_most"
    assert scheme_wish_plus_rule.handler_id == "activate_exchange_control_of_battle_cards_for_game"
    assert scheme_wish_plus_rule.family_id == "self_activate_main:activate_exchange_control_of_battle_cards_for_game"
    assert scheme_wish_minus_rule.handler_id == "activate_buff_owner_battle_cards"
    assert scheme_wish_minus_rule.family_id == "self_activate_main:activate_buff_owner_battle_cards"


def test_engine_loads_effect_catalog_from_path() -> None:
    scratch = _scratch_dir()
    try:
        catalog_path = scratch / "catalog.json"
        save_effect_rules_json(
            catalog_path,
            {
                303: (
                    EffectRule(
                        trigger="self_played",
                        handler_id="auto_draw_n",
                        handler_params={"amount": 1},
                        once_per_turn=False,
                        family_id="self_played:auto_draw_n",
                        provenance="manual",
                    ),
                )
            },
        )

        engine = RulesEngine(effect_rules_path=catalog_path)
        state = engine.initialize_game(
            p1_leader_card_id=1,
            p1_deck_card_ids=_deck(1000),
            p2_leader_card_id=2,
            p2_deck_card_ids=_deck(2000),
            shuffle_decks=False,
        )
        state = _to_main(engine, state)
        deck_before = len(state.players[1].deck)
        state.players[1].hand = [CardInstance(instance_id=930001, card_id=303, owner_id=1, card_type="BATTLE", energy_cost=0)]

        play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
        state = engine.apply_action(state, play)
        state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
        assert len(state.players[1].deck) == deck_before - 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_engine_loads_sharded_effect_catalog_from_directory() -> None:
    scratch = _scratch_dir()
    try:
        catalog_dir = scratch / "effect_catalog_shards"
        save_effect_rules_sharded_json(
            catalog_dir,
            {
                101: (
                    EffectRule(
                        trigger="self_played",
                        handler_id="auto_draw_n",
                        handler_params={"amount": 2},
                        family_id="self_played:auto_draw_n",
                        provenance="test",
                    ),
                ),
                202: (
                    EffectRule(
                        trigger="self_attacks",
                        handler_id="auto_draw_n",
                        handler_params={"amount": 1},
                        family_id="self_attacks:auto_draw_n",
                        provenance="test",
                    ),
                ),
            },
            shard_size=1,
        )
        engine = RulesEngine(effect_rules_path=catalog_dir)
        assert 101 in engine._effect_rules
        assert engine._effect_rules[101][0].handler_id == "auto_draw_n"
        assert engine._effect_rules[202][0].family_id == "self_attacks:auto_draw_n"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_engine_applies_effect_catalog_override_replace() -> None:
    scratch = _scratch_dir()
    try:
        catalog_path = scratch / "catalog.json"
        override_path = scratch / "catalog_overrides.json"
        save_effect_rules_json(
            catalog_path,
            {
                404: (
                    EffectRule(
                        trigger="self_played",
                        handler_id="auto_draw_n",
                        handler_params={"amount": 1},
                        family_id="self_played:auto_draw_n",
                        provenance="base",
                    ),
                )
            },
        )
        save_effect_rule_overrides_json(
            override_path,
            {
                404: (
                    "replace",
                    (
                        EffectRule(
                            trigger="self_played",
                            handler_id="auto_draw_n",
                            handler_params={"amount": 2},
                            family_id="self_played:auto_draw_n",
                            provenance="override",
                        ),
                    ),
                )
            },
        )
        engine = RulesEngine(effect_rules_path=catalog_path, effect_rule_overrides_path=override_path)
        state = engine.initialize_game(
            p1_leader_card_id=1,
            p1_deck_card_ids=_deck(1000),
            p2_leader_card_id=2,
            p2_deck_card_ids=_deck(2000),
            shuffle_decks=False,
        )
        state = _to_main(engine, state)
        deck_before = len(state.players[1].deck)
        state.players[1].hand = [CardInstance(instance_id=930002, card_id=404, owner_id=1, card_type="BATTLE", energy_cost=0)]

        play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
        state = engine.apply_action(state, play)
        state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
        assert len(state.players[1].deck) == deck_before - 2
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
