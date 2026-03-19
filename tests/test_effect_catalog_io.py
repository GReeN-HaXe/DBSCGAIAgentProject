from __future__ import annotations

import json
from pathlib import Path
import shutil
import uuid

from src.game import Action, ActionType, CardInstance, RulesEngine, TurnPhase
from src.game.effect_rules import (
    EFFECT_CATALOG_KIND,
    EFFECT_CATALOG_OVERRIDE_KIND,
    EFFECT_CATALOG_OVERRIDE_SCHEMA_VERSION,
    EFFECT_CATALOG_SCHEMA_VERSION,
    EffectRule,
    load_effect_rule_overrides_json,
    load_effect_rules_json,
    merge_effect_rule_overrides,
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
    assert len(loaded) == 45
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
    assert loaded[2409][0] == "replace"
    assert loaded[4226][0] == "replace"
    assert loaded[5656][0] == "replace"
    assert loaded[5531][0] == "replace"
    assert loaded[7358][0] == "replace"
    assert loaded[7236][0] == "replace"
    assert loaded[7459][0] == "replace"
    assert loaded[8314][0] == "replace"
    assert loaded[4265][0] == "replace"
    assert loaded[5301][0] == "replace"
    assert loaded[8458][0] == "replace"
    assert loaded[6679][0] == "replace"
    assert loaded[8385][0] == "replace"
    assert loaded[8881][0] == "replace"
    assert loaded[8896][0] == "replace"
    assert loaded[9720][0] == "replace"
    king_cold_rule = loaded[20][1][0]
    broly_combo_rule = loaded[27][1][0]
    prismatic_broly_auto = loaded[36][1][0]
    prismatic_broly_activate = loaded[36][1][1]
    dyspo_rule = loaded[6][1][0]
    majin_buu_rule = loaded[1603][1][0]
    prismatic_gohan_rule = loaded[49][1][0]
    gigantic_rule = loaded[83][1][0]
    steadfast_rule = loaded[89][1][0]
    explosive_rule = loaded[2409][1][0]
    released_rule = loaded[4226][1][0]
    cabba_rule = loaded[5656][1][0]
    bardock_rule = loaded[5531][1][0]
    dormant_rule = loaded[7358][1][0]
    supreme_kai_rule = loaded[7236][1][0]
    difference_rule = loaded[7459][1][0]
    mechikabura_rule = loaded[8314][1][0]
    petrification_rule = loaded[4265][1][0]
    yamcha_rule = loaded[5301][1][0]
    final_battle_rule = loaded[8458][1][0]
    toppo_rule = loaded[6679][1][0]
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
    assert bardock_rule.handler_id == "auto_restrict_self_copies_from_hand_next_turn_on_play"
    assert bardock_rule.family_id == "self_played:auto_restrict_self_copies_from_hand_next_turn_on_play"
    assert dormant_rule.handler_id == "counter_negate_attack"
    assert dormant_rule.family_id == "counter_attack:counter_negate_attack"
    assert supreme_kai_rule.handler_id == "counter_negate_attack_play_self"
    assert supreme_kai_rule.trigger == "counter_attack"
    assert difference_rule.handler_id == "counter_spirit_boost_power_reduce_opponent_cards"
    assert difference_rule.family_id == "counter_attack:counter_spirit_boost_power_reduce_opponent_cards"
    assert mechikabura_rule.handler_id == "auto_look_top_add_up_to_one_to_hand_on_play"
    assert mechikabura_rule.trigger == "self_activate_main"
    assert petrification_rule.handler_id == "counter_negate_attack"
    assert petrification_rule.family_id == "counter_attack:counter_negate_attack"
    assert yamcha_rule.handler_id == "counter_power_reduce_up_to_n_opponent_battle_for_turn_play_self"
    assert yamcha_rule.family_id == "counter_play:counter_power_reduce_up_to_n_opponent_battle_for_turn_play_self"
    assert final_battle_rule.handler_id == "counter_negate_attack"
    assert final_battle_rule.family_id == "counter_attack:counter_negate_attack"
    assert toppo_rule.handler_id == "counter_negate_attack_play_self"
    assert toppo_rule.family_id == "counter_attack:counter_negate_attack_play_self"
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
