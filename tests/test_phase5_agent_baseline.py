from __future__ import annotations

import json

from src.agent import (
    BOOKKEEPING_ACTION_TYPES,
    ActionWeights,
    HeuristicPolicy,
    build_review_trace_payload,
    build_training_trace_rows,
    derive_action_signature,
    build_head_to_head_matrix,
    build_history_csv_row,
    build_overview_csv_row,
    compute_seat_bias,
    build_heuristic_policy_from_config,
    decision_trace_to_csv_rows,
    compute_trace_kpis,
    filter_decision_trace,
    compute_match_quality,
    per_phase_kpi_rows,
    per_turn_kpi_rows,
    command_hints_from_summary,
    command_hints_to_csv_row,
    command_hints_to_json_payload,
    evaluate_state,
    format_history_summary,
    history_recent_runs_to_csv_rows,
    history_summary_to_csv_row,
    format_head_to_head,
    format_profile_ranking,
    head_to_head_to_csv_rows,
    merge_matchup_rows,
    matchup_rows_from_dict,
    matchup_rows_to_dict,
    profile_summary_to_csv_rows,
    seat_bias_to_csv_rows,
    rank_profiles,
    recommend_profile,
    run_ai_vs_ai,
    run_profile_matchup_matrix,
    summarize_profile_strength,
    summarize_history_rows,
    simulation_result_to_dict,
    summarize_trace,
)
from src.agent.matchup import MatchupRow
from src.game import ActionType, CardInstance, RulesEngine, TurnPhase


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _to_main(engine: RulesEngine, state):
    while state.phase != TurnPhase.MAIN:
        state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, state.active_player) if a.action_type == ActionType.END_CHARGE))
    return state


def _to_p1_main_where_attacks_are_legal(engine: RulesEngine, state):
    state = _to_main(engine, state)
    state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, state.active_player) if a.action_type == ActionType.END_TURN))
    state = _to_main(engine, state)
    return state


def test_phase5_heuristic_policy_returns_legal_action() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=990001, card_id=300001, owner_id=1, card_type="BATTLE", energy_cost=0),
    ]
    legal = engine.get_legal_actions(state, 1)
    policy = HeuristicPolicy()
    choice = policy.choose_action(state, legal)
    assert choice in legal


def test_phase5_ai_vs_ai_simulation_runs_without_illegal_actions() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    result = run_ai_vs_ai(
        engine=engine,
        state=state,
        p1_policy=HeuristicPolicy(),
        p2_policy=HeuristicPolicy(),
        max_actions=80,
    )
    assert result.total_actions > 0
    assert result.final_state.turn_number >= 1


def test_phase5_state_evaluator_returns_float_advantage() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    score = evaluate_state(state, player_id=1)
    assert isinstance(score, float)


def test_phase5_heuristic_policy_prefers_higher_cost_play_when_legal() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=990101, card_id=310001, owner_id=1, color="Blue", resting=False),
        CardInstance(instance_id=990102, card_id=310002, owner_id=1, color="Blue", resting=False),
        CardInstance(instance_id=990103, card_id=310003, owner_id=1, color="Blue", resting=False),
    ]
    state.players[1].hand = [
        CardInstance(instance_id=990111, card_id=320001, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=1),
        CardInstance(instance_id=990112, card_id=320002, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=3),
    ]
    legal = engine.get_legal_actions(state, 1)
    policy = HeuristicPolicy()
    choice = policy.choose_action(state, legal)
    assert choice.action_type == ActionType.PLAY_CARD_FROM_HAND
    assert choice.hand_index == 1


def test_phase5_profiles_choose_different_actions_in_same_state() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=990201, card_id=330001, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=0, resting=False)
    )
    state.players[1].hand = [
        CardInstance(instance_id=990202, card_id=330002, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=0),
    ]
    legal = engine.get_legal_actions(state, 1)
    aggressive_choice = HeuristicPolicy(profile="aggressive").choose_action(state, legal)
    control_choice = HeuristicPolicy(profile="control").choose_action(state, legal)
    assert aggressive_choice.action_type == ActionType.DECLARE_ATTACK
    assert control_choice.action_type == ActionType.PLAY_CARD_FROM_HAND


def test_phase5_heuristic_policy_prefers_charging_over_skipping_opening_charge() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].hand = [
        CardInstance(instance_id=991001, card_id=350001, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=2, combo_power=5000),
    ]
    legal = engine.get_legal_actions(state, 1)
    choice = HeuristicPolicy(profile="balanced").choose_action(state, legal)
    assert choice.action_type == ActionType.CHARGE_FROM_HAND


def test_phase5_heuristic_policy_avoids_charging_super_combo_when_alternative_exists() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].hand = [
        CardInstance(instance_id=991101, card_id=360001, owner_id=1, card_type="BATTLE", color="Red", energy_cost=2, combo_power=10000),
        CardInstance(instance_id=991102, card_id=360002, owner_id=1, card_type="BATTLE", color="Red", energy_cost=5, combo_power=0),
    ]
    legal = engine.get_legal_actions(state, 1)
    choice = HeuristicPolicy(profile="balanced").choose_action(state, legal)
    assert choice.action_type == ActionType.CHARGE_FROM_HAND
    assert choice.hand_index == 1


def test_phase5_charge_places_energy_active_and_allows_turn_one_one_drop() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].hand = [
        CardInstance(instance_id=991201, card_id=370001, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=1, has_draw=True, auto_draw_on_play=True),
        CardInstance(instance_id=991202, card_id=370002, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=3),
    ]
    state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.CHARGE_FROM_HAND and a.hand_index == 1))
    assert len(state.players[1].energy) == 1
    assert state.players[1].energy[0].resting is False
    legal = engine.get_legal_actions(state, 1)
    assert any(a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0 for a in legal)


def test_phase5_heuristic_policy_prefers_turn_one_cantrip_play_after_charge() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].hand = [
        CardInstance(instance_id=991301, card_id=380001, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=1, has_draw=True, auto_draw_on_play=True),
        CardInstance(instance_id=991302, card_id=380002, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=3),
    ]
    state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.CHARGE_FROM_HAND and a.hand_index == 1))
    legal = engine.get_legal_actions(state, 1)
    choice = HeuristicPolicy(profile="balanced").choose_action(state, legal)
    assert choice.action_type == ActionType.PLAY_CARD_FROM_HAND
    assert choice.hand_index == 0


def test_phase5_custom_action_weights_can_override_profile_behavior() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    legal = engine.get_legal_actions(state, 1)
    policy = HeuristicPolicy(
        profile="aggressive",
        action_weights=ActionWeights(end_turn=500.0),
    )
    choice = policy.choose_action(state, legal)
    assert choice.action_type == ActionType.END_TURN


def test_phase5_build_policy_from_json_config(tmp_path) -> None:
    cfg_path = tmp_path / "policy.json"
    cfg_path.write_text(
        json.dumps(
            {
                "profile": "aggressive",
                "prefer_attack": False,
                "weights": {"end_turn": 999.0},
            }
        ),
        encoding="utf-8",
    )
    policy = build_heuristic_policy_from_config(cfg_path)
    assert isinstance(policy, HeuristicPolicy)
    assert policy.prefer_attack is False


def test_phase5_json_config_policy_changes_decision(tmp_path) -> None:
    cfg_path = tmp_path / "policy2.json"
    cfg_path.write_text(
        json.dumps(
            {
                "profile": "balanced",
                "weights": {"end_turn": 500.0},
            }
        ),
        encoding="utf-8",
    )
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    legal = engine.get_legal_actions(state, 1)
    policy = build_heuristic_policy_from_config(cfg_path)
    choice = policy.choose_action(state, legal)
    assert choice.action_type == ActionType.END_TURN


def test_phase5_run_ai_vs_ai_continues_through_battle_step_owner_changes() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.END_CHARGE))
    state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.END_TURN))
    state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.END_CHARGE))
    state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_ATTACK))
    state = engine.apply_action(state, next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PASS_COUNTER_WINDOW))
    result = run_ai_vs_ai(
        engine=engine,
        state=state,
        p1_policy=HeuristicPolicy(profile="balanced"),
        p2_policy=HeuristicPolicy(profile="balanced"),
        max_actions=3,
        capture_trace=True,
        trace_top_k=2,
    )
    assert result.total_actions >= 2
    assert result.decision_trace[0].actor_player_id == 2
    assert result.decision_trace[0].chosen_action_type == "end_offense_step"
    assert result.decision_trace[1].actor_player_id == 1


def test_phase5_rank_actions_returns_sorted_explanations() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=990301, card_id=340001, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=0),
    ]
    legal = engine.get_legal_actions(state, 1)
    policy = HeuristicPolicy(profile="balanced")
    ranked = policy.rank_actions(state, legal)
    assert ranked
    assert ranked[0].action == policy.choose_action(state, legal)
    assert all(isinstance(item.reason, str) and item.reason for item in ranked)
    assert all(ranked[i].score >= ranked[i + 1].score for i in range(len(ranked) - 1))


def test_phase5_ai_vs_ai_trace_capture_returns_ranked_candidates() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    result = run_ai_vs_ai(
        engine=engine,
        state=state,
        p1_policy=HeuristicPolicy(),
        p2_policy=HeuristicPolicy(),
        max_actions=12,
        capture_trace=True,
        trace_top_k=2,
    )
    assert result.total_actions > 0
    assert result.decision_trace
    first = result.decision_trace[0]
    assert first.step_index == 1
    assert first.candidates
    assert len(first.candidates) <= 2
    assert first.candidates[0].reason
    assert first.chosen_action_type == first.candidates[0].action_type


def test_phase5_simulation_result_to_dict_contains_trace_payload() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    result = run_ai_vs_ai(
        engine=engine,
        state=state,
        p1_policy=HeuristicPolicy(),
        p2_policy=HeuristicPolicy(),
        max_actions=6,
        capture_trace=True,
        trace_top_k=2,
    )
    payload = simulation_result_to_dict(result)
    assert isinstance(payload, dict)
    assert payload["total_actions"] == result.total_actions
    assert isinstance(payload["decision_trace"], list)
    if payload["decision_trace"]:
        first = payload["decision_trace"][0]
        assert "chosen_action_type" in first
        assert "candidates" in first


def test_phase5_summarize_trace_builds_player_action_counts() -> None:
    payload = {
        "total_actions": 3,
        "turn_number": 2,
        "winner_id": None,
        "decision_trace": [
            {
                "step_index": 1,
                "actor_player_id": 1,
                "chosen_action_type": "play_card_from_hand",
                "candidates": [{"action_type": "play_card_from_hand", "score": 100.0, "reason": "play_card_from_hand"}],
            },
            {
                "step_index": 2,
                "actor_player_id": 2,
                "chosen_action_type": "declare_attack",
                "candidates": [{"action_type": "declare_attack", "score": 98.0, "reason": "declare_attack"}],
            },
            {
                "step_index": 3,
                "actor_player_id": 1,
                "chosen_action_type": "end_turn",
                "candidates": [{"action_type": "end_turn", "score": 10.0, "reason": "end_turn"}],
            },
        ],
    }
    summary = summarize_trace(payload)
    assert summary["total_decisions"] == 3
    by_player = summary["actions_by_player"]
    assert by_player["1"]["play_card_from_hand"] == 1
    assert by_player["1"]["end_turn"] == 1
    assert by_player["2"]["declare_attack"] == 1


def test_phase5_decision_trace_to_csv_rows_shape() -> None:
    payload = {
        "decision_trace": [
            {
                "step_index": 1,
                "actor_player_id": 1,
                "turn_number": 1,
                "phase": "main",
                "chosen_action_type": "play_card_from_hand",
                "candidates": [{"action_type": "play_card_from_hand", "score": 101.5, "reason": "play_card_from_hand"}],
            }
        ]
    }
    rows = decision_trace_to_csv_rows(payload)
    assert len(rows) == 1
    row = rows[0]
    assert row["step"] == "1"
    assert row["player"] == "1"
    assert row["turn"] == "1"
    assert row["phase"] == "main"
    assert row["chosen"] == "play_card_from_hand"
    assert row["top1_reason"] == "play_card_from_hand"
    assert row["top1_score"] == "101.5"


def test_phase5_trace_normalizer_filters_bookkeeping_by_default() -> None:
    payload = {
        "winner_id": 2,
        "stop_reason": "winner_decided",
        "turn_number": 3,
        "decision_trace": [
            {"step_index": 1, "actor_player_id": 1, "turn_number": 1, "phase": "main", "chosen_action_type": "play_card_from_hand", "chosen_action_text": "play", "state_snapshot": {}, "post_action_state_snapshot": {}, "candidates": [{"reason": "play_card_from_hand", "score": 99.0}]},
            {"step_index": 2, "actor_player_id": 2, "turn_number": 1, "phase": "main", "chosen_action_type": "pass_counter_window", "chosen_action_text": "pass", "state_snapshot": {}, "post_action_state_snapshot": {}, "candidates": [{"reason": "pass_counter_window", "score": 200.0}]},
            {"step_index": 3, "actor_player_id": 1, "turn_number": 1, "phase": "main", "chosen_action_type": "resolve_battle", "chosen_action_text": "resolve", "state_snapshot": {}, "post_action_state_snapshot": {}, "candidates": [{"reason": "resolve_battle", "score": 170.0}]},
        ],
    }
    filtered = filter_decision_trace(payload)
    assert len(filtered) == 1
    assert filtered[0]["chosen_action_type"] == "play_card_from_hand"
    review = build_review_trace_payload(payload)
    assert review["decision_count"] == 1
    assert sorted(review["filtered_action_types"]) == sorted(BOOKKEEPING_ACTION_TYPES)
    training_rows = build_training_trace_rows(payload)
    assert len(training_rows) == 1
    assert training_rows[0]["chosen_action_type"] == "play_card_from_hand"
    assert training_rows[0]["action_signature"].startswith("play_card_from_hand")


def test_phase5_derive_action_signature_prefers_card_aware_tokens() -> None:
    signature = derive_action_signature(
        "play_card_from_hand",
        "play_card_from_hand hand_index=4 card=BT1-001 source_zone=hand target_zone=leader",
    )
    assert signature == "play_card_from_hand|card=BT1-001|source_zone=hand|target_zone=leader"


def test_phase5_compute_trace_kpis_shape_and_rates() -> None:
    payload = {
        "decision_trace": [
            {
                "step_index": 1,
                "actor_player_id": 1,
                "chosen_action_type": "declare_attack",
                "candidates": [{"action_type": "declare_attack", "score": 120.0, "reason": "declare_attack"}],
            },
            {
                "step_index": 2,
                "actor_player_id": 1,
                "chosen_action_type": "play_card_from_hand",
                "candidates": [{"action_type": "play_card_from_hand", "score": 100.0, "reason": "play_card_from_hand"}],
            },
            {
                "step_index": 3,
                "actor_player_id": 2,
                "chosen_action_type": "end_turn",
                "candidates": [{"action_type": "end_turn", "score": 10.0, "reason": "end_turn"}],
            },
        ]
    }
    kpis = compute_trace_kpis(payload)
    assert kpis["decision_count"] == 3
    assert abs(float(kpis["avg_top1_score"]) - (230.0 / 3.0)) < 1e-9
    assert abs(float(kpis["attack_rate"]) - (1.0 / 3.0)) < 1e-9
    assert abs(float(kpis["play_rate"]) - (1.0 / 3.0)) < 1e-9
    assert abs(float(kpis["end_turn_rate"]) - (1.0 / 3.0)) < 1e-9


def test_phase5_per_turn_kpi_rows_shape_and_values() -> None:
    payload = {
        "decision_trace": [
            {"turn_number": 1, "chosen_action_type": "play_card_from_hand"},
            {"turn_number": 1, "chosen_action_type": "declare_attack"},
            {"turn_number": 2, "chosen_action_type": "end_turn"},
        ]
    }
    rows = per_turn_kpi_rows(payload)
    assert len(rows) == 2
    assert rows[0]["turn"] == "1"
    assert rows[0]["decisions"] == "2"
    assert rows[0]["play_card_from_hand"] == "1"
    assert rows[0]["declare_attack"] == "1"
    assert rows[1]["turn"] == "2"
    assert rows[1]["end_turn"] == "1"


def test_phase5_per_phase_kpi_rows_shape_and_values() -> None:
    payload = {
        "decision_trace": [
            {"phase": "main", "chosen_action_type": "play_card_from_hand"},
            {"phase": "main", "chosen_action_type": "end_turn"},
            {"phase": "battle", "chosen_action_type": "declare_attack"},
            {"phase": "battle", "chosen_action_type": "pass_counter_window"},
        ]
    }
    rows = per_phase_kpi_rows(payload)
    assert len(rows) == 2
    battle = next(r for r in rows if r["phase"] == "battle")
    main = next(r for r in rows if r["phase"] == "main")
    assert battle["decisions"] == "2"
    assert battle["declare_attack"] == "1"
    assert battle["pass_counter_window"] == "1"
    assert main["play_card_from_hand"] == "1"
    assert main["end_turn"] == "1"


def test_phase5_profile_matchup_matrix_returns_consistent_rows() -> None:
    def _engine_factory() -> RulesEngine:
        return RulesEngine()

    def _state_factory(engine: RulesEngine):
        return engine.initialize_game(
            p1_leader_card_id=1,
            p1_deck_card_ids=_deck(1000),
            p2_leader_card_id=2,
            p2_deck_card_ids=_deck(2000),
            shuffle_decks=False,
        )

    rows = run_profile_matchup_matrix(
        engine_factory=_engine_factory,
        state_factory=_state_factory,
        profiles=["balanced", "aggressive"],
        games_per_matchup=1,
        max_actions=8,
    )
    assert len(rows) == 4
    for row in rows:
        assert row.games == 1
        assert row.p1_wins + row.p2_wins + row.draws == 1
    payload = matchup_rows_to_dict(rows)
    assert len(payload) == 4
    assert "p1_win_rate" in payload[0]


def test_phase5_summarize_profile_strength_aggregates_both_sides() -> None:
    rows = [
        MatchupRow(
            p1_profile="balanced",
            p2_profile="aggressive",
            games=2,
            p1_wins=1,
            p2_wins=1,
            draws=0,
            avg_actions=30.0,
            avg_turn=4.0,
        ),
        MatchupRow(
            p1_profile="aggressive",
            p2_profile="balanced",
            games=2,
            p1_wins=0,
            p2_wins=1,
            draws=1,
            avg_actions=32.0,
            avg_turn=5.0,
        ),
    ]
    summary = summarize_profile_strength(rows)
    assert summary["balanced"]["games"] == 4
    assert summary["balanced"]["wins"] == 2
    assert summary["balanced"]["losses"] == 1
    assert summary["balanced"]["draws"] == 1
    assert summary["balanced"]["win_rate"] == 0.5
    assert summary["aggressive"]["games"] == 4


def test_phase5_matchup_rows_from_dict_roundtrip() -> None:
    rows = [
        MatchupRow(
            p1_profile="balanced",
            p2_profile="control",
            games=2,
            p1_wins=1,
            p2_wins=0,
            draws=1,
            avg_actions=12.5,
            avg_turn=3.0,
        )
    ]
    payload = matchup_rows_to_dict(rows)
    parsed = matchup_rows_from_dict(payload)
    assert len(parsed) == 1
    assert parsed[0].p1_profile == "balanced"
    assert parsed[0].p2_profile == "control"
    assert parsed[0].games == 2


def test_phase5_profile_report_formatters_render_tables() -> None:
    rows = [
        MatchupRow(
            p1_profile="balanced",
            p2_profile="aggressive",
            games=2,
            p1_wins=1,
            p2_wins=0,
            draws=1,
            avg_actions=20.0,
            avg_turn=3.0,
        ),
        MatchupRow(
            p1_profile="aggressive",
            p2_profile="balanced",
            games=2,
            p1_wins=0,
            p2_wins=1,
            draws=1,
            avg_actions=21.0,
            avg_turn=3.0,
        ),
    ]
    summary = summarize_profile_strength(rows)
    ranking = format_profile_ranking(summary)
    assert "Profile Ranking" in ranking
    assert "balanced" in ranking
    matrix = build_head_to_head_matrix(rows)
    h2h = format_head_to_head(matrix)
    assert "Head-to-Head" in h2h
    assert "p1\\p2" in h2h


def test_phase5_profile_summary_and_h2h_csv_row_helpers() -> None:
    rows = [
        MatchupRow(
            p1_profile="balanced",
            p2_profile="aggressive",
            games=2,
            p1_wins=1,
            p2_wins=0,
            draws=1,
            avg_actions=20.0,
            avg_turn=3.0,
        )
    ]
    summary = summarize_profile_strength(rows)
    summary_csv = profile_summary_to_csv_rows(summary)
    assert summary_csv
    assert "profile" in summary_csv[0]
    matrix = build_head_to_head_matrix(rows)
    h2h_csv = head_to_head_to_csv_rows(matrix)
    assert h2h_csv
    assert h2h_csv[0]["p1_profile"] == "balanced"
    assert h2h_csv[0]["p2_profile"] == "aggressive"


def test_phase5_rank_and_recommend_profile() -> None:
    summary = {
        "balanced": {"points_per_game": 0.6, "win_rate": 0.4, "wins": 4},
        "aggressive": {"points_per_game": 0.5, "win_rate": 0.3, "wins": 3},
        "control": {"points_per_game": 0.2, "win_rate": 0.1, "wins": 1},
    }
    ranking = rank_profiles(summary)
    assert ranking == ["balanced", "aggressive", "control"]
    rec = recommend_profile(summary)
    assert rec["recommended_profile"] == "balanced"
    assert rec["clear_edge"] is True


def test_phase5_recommend_profile_inconclusive_tie() -> None:
    summary = {
        "balanced": {"points_per_game": 0.5, "win_rate": 0.0, "wins": 0},
        "aggressive": {"points_per_game": 0.5, "win_rate": 0.0, "wins": 0},
    }
    rec = recommend_profile(summary)
    assert rec["recommended_profile"] in {"balanced", "aggressive"}
    assert rec["clear_edge"] is False


def test_phase5_recommend_profile_respects_min_games_gate() -> None:
    summary = {
        "balanced": {"points_per_game": 0.8, "win_rate": 0.6, "wins": 6, "games": 4},
        "aggressive": {"points_per_game": 0.5, "win_rate": 0.4, "wins": 4, "games": 4},
    }
    rec = recommend_profile(summary, min_games_per_profile=6)
    assert rec["recommended_profile"] == "balanced"
    assert rec["reason"] == "insufficient_sample"
    assert rec["reliable"] is False


def test_phase5_merge_matchup_rows_weighted_averages() -> None:
    rows = [
        MatchupRow(
            p1_profile="balanced",
            p2_profile="aggressive",
            games=2,
            p1_wins=1,
            p2_wins=0,
            draws=1,
            avg_actions=10.0,
            avg_turn=2.0,
        ),
        MatchupRow(
            p1_profile="balanced",
            p2_profile="aggressive",
            games=4,
            p1_wins=2,
            p2_wins=1,
            draws=1,
            avg_actions=20.0,
            avg_turn=3.0,
        ),
    ]
    merged = merge_matchup_rows(rows)
    assert len(merged) == 1
    row = merged[0]
    assert row.games == 6
    assert row.p1_wins == 3
    assert row.p2_wins == 1
    assert row.draws == 2
    assert abs(row.avg_actions - (100.0 / 6.0)) < 1e-9
    assert abs(row.avg_turn - (16.0 / 6.0)) < 1e-9


def test_phase5_compute_seat_bias_aggregates_rates() -> None:
    rows = [
        MatchupRow(
            p1_profile="balanced",
            p2_profile="aggressive",
            games=4,
            p1_wins=2,
            p2_wins=1,
            draws=1,
            avg_actions=10.0,
            avg_turn=2.0,
        ),
        MatchupRow(
            p1_profile="aggressive",
            p2_profile="balanced",
            games=2,
            p1_wins=0,
            p2_wins=1,
            draws=1,
            avg_actions=12.0,
            avg_turn=3.0,
        ),
    ]
    bias = compute_seat_bias(rows)
    assert bias["games"] == 6
    assert abs(float(bias["p1_win_rate"]) - (2.0 / 6.0)) < 1e-9
    assert abs(float(bias["p2_win_rate"]) - (2.0 / 6.0)) < 1e-9
    assert abs(float(bias["draw_rate"]) - (2.0 / 6.0)) < 1e-9


def test_phase5_compute_match_quality_alerts_draw_heavy() -> None:
    rows = [
        MatchupRow(
            p1_profile="balanced",
            p2_profile="aggressive",
            games=4,
            p1_wins=0,
            p2_wins=0,
            draws=4,
            avg_actions=10.0,
            avg_turn=2.0,
        )
    ]
    q = compute_match_quality(rows, decisive_rate_alert_threshold=0.25)
    assert q["games"] == 4
    assert q["draws"] == 4
    assert float(q["decisive_rate"]) == 0.0
    assert q["low_decisive_rate_alert"] is True


def test_phase5_seat_bias_to_csv_rows_shape() -> None:
    seat_bias = {
        "by_matchup": {
            "balanced__vs__aggressive": {
                "games": 3,
                "p1_win_rate": 0.333333,
                "p2_win_rate": 0.333333,
                "draw_rate": 0.333333,
            }
        }
    }
    rows = seat_bias_to_csv_rows(seat_bias)
    assert len(rows) == 1
    row = rows[0]
    assert row["p1_profile"] == "balanced"
    assert row["p2_profile"] == "aggressive"
    assert row["games"] == "3"


def test_phase5_build_overview_csv_row_shape() -> None:
    rec = {
        "recommended_profile": "balanced",
        "reason": "dominant_points_per_game",
        "reliable": True,
        "clear_edge": True,
    }
    seat_bias = {
        "games": 12,
        "p1_win_rate": 0.25,
        "p2_win_rate": 0.25,
        "draw_rate": 0.5,
        "p1_minus_p2": 0.0,
    }
    row = build_overview_csv_row(
        profiles=["balanced", "aggressive"],
        games_per_matchup=2,
        max_actions=120,
        shuffle_decks=True,
        seat_balanced=True,
        seed=42,
        min_games_for_recommendation=6,
        recommendation=rec,
        seat_bias=seat_bias,
    )
    assert row["profiles"] == "balanced,aggressive"
    assert row["recommended_profile"] == "balanced"
    assert row["recommendation_reliable"] == "True"
    assert row["seat_bias_games"] == "12"


def test_phase5_build_history_csv_row_shape() -> None:
    overview = {
        "profiles": "balanced,aggressive",
        "recommended_profile": "balanced",
    }
    row = build_history_csv_row(
        overview,
        timestamp_utc="2026-02-26T00:00:00+00:00",
        source_json="artifacts/profile_matchups.json",
    )
    assert row["timestamp_utc"] == "2026-02-26T00:00:00+00:00"
    assert row["source_json"] == "artifacts/profile_matchups.json"
    assert row["recommended_profile"] == "balanced"


def test_phase5_summarize_history_rows_and_format() -> None:
    rows = [
        {
            "timestamp_utc": "2026-02-26T00:00:00+00:00",
            "recommended_profile": "balanced",
            "recommendation_reason": "dominant_points_per_game",
            "recommendation_reliable": "True",
            "seat_bias_p1_minus_p2": "0.1",
            "match_quality_decisive_rate": "0.2",
            "source_json": "a.json",
        },
        {
            "timestamp_utc": "2026-02-26T01:00:00+00:00",
            "recommended_profile": "aggressive",
            "recommendation_reason": "tied_or_inconclusive",
            "recommendation_reliable": "False",
            "seat_bias_p1_minus_p2": "0.0",
            "match_quality_decisive_rate": "0.6",
            "source_json": "b.json",
        },
    ]
    summary = summarize_history_rows(
        rows,
        recent_window=1,
        seat_bias_alert_threshold=0.05,
        decisive_rate_alert_threshold=0.30,
    )
    assert summary["total_runs"] == 2
    assert summary["recommendation_counts"]["balanced"] == 1
    assert summary["recommendation_counts"]["aggressive"] == 1
    assert abs(float(summary["top_recommendation_share"]) - 0.5) < 1e-9
    assert abs(float(summary["recent_top_recommendation_share"]) - 1.0) < 1e-9
    assert int(summary["distinct_recommended_profiles"]) == 2
    assert int(summary["recent_distinct_recommended_profiles"]) == 1
    assert abs(float(summary["reliable_rate"]) - 0.5) < 1e-9
    assert abs(float(summary["avg_hours_between_runs"]) - 1.0) < 1e-9
    assert abs(float(summary["median_hours_between_runs"]) - 1.0) < 1e-9
    assert abs(float(summary["latest_hours_since_previous"]) - 1.0) < 1e-9
    assert summary["recommendation_switches"] == 1
    assert summary["recent_window"] == 1
    assert summary["recent_recommendation_counts"]["aggressive"] == 1
    assert summary["recent_recommendation_switches"] == 0
    assert abs(float(summary["recent_switch_rate"]) - 0.0) < 1e-9
    assert abs(float(summary["recent_reliable_rate"]) - 0.0) < 1e-9
    assert abs(float(summary["recent_unreliable_rate"]) - 1.0) < 1e-9
    assert summary["seat_bias_alert_count"] == 1
    assert summary["recent_seat_bias_alert_count"] == 0
    assert summary["low_decisive_rate_alert_count"] == 1
    assert summary["recent_low_decisive_rate_alert_count"] == 0
    assert summary["quality_alert_count"] == 1
    assert summary["recent_quality_alert_count"] == 0
    assert summary["current_recommendation_streak_profile"] == "aggressive"
    assert summary["current_recommendation_streak_len"] == 1
    assert summary["current_reliable_streak_len"] == 0
    assert summary["current_quality_alert_streak_len"] == 0
    assert 0.0 <= float(summary["stability_index"]) <= 1.0
    assert 0.0 <= float(summary["recent_stability_index"]) <= 1.0
    assert summary["stability_label"] in {"stable", "watch", "unstable"}
    assert summary["overall_status"] in {"healthy", "warning", "critical"}
    assert isinstance(summary["status_reasons"], list)
    assert isinstance(summary["status_reason_primary"], str)
    assert summary["recommended_action"] in {"continue", "increase_games", "retune_policy"}
    assert 0.0 <= float(summary["recommended_action_confidence"]) <= 1.0
    assert isinstance(summary["recommended_action_rationale"], str)
    assert summary["recommended_action_rationale"]
    assert summary["runs_needed_for_ready"] == 3
    assert abs(float(summary["ready_progress"]) - 0.4) < 1e-9
    assert abs(float(summary["estimated_hours_to_ready"]) - 3.0) < 1e-9
    assert summary["estimated_ready_timestamp_utc"].startswith("2026-02-26T04:00:00")
    assert summary["is_ready_for_next_phase"] is False
    assert summary["readiness_reason"] == "insufficient_runs"
    assert "--games-per-matchup 3" in summary["next_command_hint"]
    assert "--min-games-for-recommendation 5" in summary["next_command_hint"]
    assert "--decisive-rate-alert-threshold 0.30" in summary["next_command_hint"]
    assert 0.0 <= float(summary["readiness_score"]) <= 1.0
    assert summary["readiness_label"] in {"blocked", "near_ready", "ready"}
    assert int(summary["readiness_blocker_count"]) >= 1
    assert isinstance(summary["readiness_blockers"], list)
    assert isinstance(summary["next_command_hint"], str)
    assert summary["next_command_hint"]
    assert isinstance(summary["followup_command_hint"], str)
    assert summary["followup_command_hint"]
    assert isinstance(summary["next_steps_plan"], list)
    assert summary["next_steps_plan"]
    assert isinstance(summary["prioritized_next_step"], str)
    assert summary["prioritized_next_step"]
    assert isinstance(summary["next_command_sequence"], list)
    assert len(summary["next_command_sequence"]) == 2
    assert isinstance(summary["next_command_sequence_shell"], str)
    assert summary["next_command_sequence_shell"]
    assert isinstance(summary["next_command_sequence_powershell"], str)
    assert isinstance(summary["next_command_sequence_bash"], str)
    assert isinstance(summary["next_command_sequence_multiline"], str)
    delta = summary["latest_delta"]
    assert delta["recommendation_changed"] is True
    assert delta["reliability_changed"] is True
    rendered = format_history_summary(summary)
    assert "Profile Matchup History Summary" in rendered
    assert "total_runs: 2" in rendered
    assert "recommendation_switches: 1" in rendered
    assert "recent_recommendation_switches: 0" in rendered
    assert "top_recommendation_share:" in rendered
    assert "distinct_recommended_profiles: 2" in rendered
    assert "avg_hours_between_runs:" in rendered
    assert "seat_bias_alert_count: 1" in rendered
    assert "low_decisive_rate_alert_count: 1" in rendered
    assert "quality_alert_count: 1" in rendered
    assert "current_recommendation_streak_profile: aggressive" in rendered
    assert "current_reliable_streak_len: 0" in rendered
    assert "stability_index:" in rendered
    assert "recent_stability_index:" in rendered
    assert "stability_label:" in rendered
    assert "overall_status:" in rendered
    assert "status_reason_primary:" in rendered
    assert "recommended_action:" in rendered
    assert "recommended_action_confidence:" in rendered
    assert "recommended_action_rationale:" in rendered
    assert "ready_progress:" in rendered
    assert "estimated_hours_to_ready:" in rendered
    assert "is_ready_for_next_phase:" in rendered
    assert "readiness_score:" in rendered
    assert "readiness_label:" in rendered
    assert "readiness_blockers:" in rendered
    assert "next_command_hint:" in rendered
    assert "followup_command_hint:" in rendered
    assert "next_steps_plan:" in rendered
    assert "prioritized_next_step:" in rendered
    assert "next_command_sequence_shell:" in rendered
    assert "next_command_sequence_bash:" in rendered
    assert "next_command_sequence_multiline:" in rendered
    assert "latest_delta_vs_previous:" in rendered


def test_phase5_history_summary_to_csv_row_shape() -> None:
    summary = {
        "total_runs": 2,
        "reliable_rate": 0.5,
        "recommendation_switches": 1,
        "recent_window": 1,
        "recent_recommendation_switches": 0,
        "recent_switch_rate": 0.0,
        "top_recommendation_share": 0.5,
        "recent_top_recommendation_share": 1.0,
        "distinct_recommended_profiles": 2,
        "recommendation_entropy": 1.0,
        "recent_distinct_recommended_profiles": 1,
        "recent_recommendation_entropy": 0.0,
        "recent_reliable_rate": 0.0,
        "recent_unreliable_rate": 1.0,
        "avg_hours_between_runs": 1.0,
        "median_hours_between_runs": 1.0,
        "latest_hours_since_previous": 1.0,
        "recent_avg_abs_seat_bias_delta": 0.1,
        "seat_bias_alert_threshold": 0.05,
        "seat_bias_alert_count": 1,
        "recent_seat_bias_alert_count": 0,
        "decisive_rate_alert_threshold": 0.3,
        "low_decisive_rate_alert_count": 1,
        "recent_low_decisive_rate_alert_count": 0,
        "quality_alert_count": 1,
        "recent_quality_alert_count": 0,
        "current_recommendation_streak_profile": "aggressive",
        "current_recommendation_streak_len": 1,
        "current_reliable_streak_len": 0,
        "current_quality_alert_streak_len": 0,
        "stability_index": 0.25,
        "recent_stability_index": 0.75,
        "stability_label": "unstable",
        "overall_status": "critical",
        "status_reason_primary": "stability_unstable",
        "status_reasons": ["stability_unstable", "recent_quality_alerts_present"],
        "recommended_action": "retune_policy",
        "recommended_action_confidence": 0.9,
        "recommended_action_rationale": "retune_policy because ...",
        "min_runs_for_ready": 5,
        "runs_needed_for_ready": 1,
        "ready_progress": 0.8,
        "estimated_hours_to_ready": 1.0,
        "estimated_ready_timestamp_utc": "2026-02-26T02:00:00+00:00",
        "is_ready_for_next_phase": False,
        "readiness_reason": "status_not_healthy",
        "readiness_score": 0.7,
        "readiness_label": "near_ready",
        "readiness_blocker_count": 1,
        "readiness_blockers": ["status_not_healthy"],
        "next_command_hint": "python scripts/run_profile_matchups.py ...",
        "followup_command_hint": "python scripts/summarize_profile_history.py ...",
        "next_steps_plan": ["step1", "step2"],
        "prioritized_next_step": "step1",
        "next_command_sequence": ["cmd1", "cmd2"],
        "next_command_sequence_shell": "cmd1 ; cmd2",
        "next_command_sequence_powershell": "cmd1 ; cmd2",
        "next_command_sequence_bash": "cmd1 && cmd2",
        "next_command_sequence_multiline": "cmd1\ncmd2",
        "recommendation_counts": {"balanced": 1, "aggressive": 1},
        "recent_recommendation_counts": {"aggressive": 1},
        "latest": {
            "timestamp_utc": "2026-02-26T01:00:00+00:00",
            "recommended_profile": "aggressive",
            "recommendation_reason": "tied_or_inconclusive",
            "seat_bias_p1_minus_p2": "0.0",
            "source_json": "b.json",
        },
        "latest_delta": {
            "recommendation_changed": True,
            "reason_changed": True,
            "reliability_changed": True,
            "seat_bias_delta_change": -0.1,
            "previous_timestamp_utc": "2026-02-26T00:00:00+00:00",
        },
    }
    row = history_summary_to_csv_row(summary)
    assert row["total_runs"] == "2"
    assert row["recent_recommendation_switches"] == "0"
    assert row["top_recommendation_share"] == "0.5"
    assert row["distinct_recommended_profiles"] == "2"
    assert row["avg_hours_between_runs"] == "1.0"
    assert row["seat_bias_alert_count"] == "1"
    assert row["low_decisive_rate_alert_count"] == "1"
    assert row["quality_alert_count"] == "1"
    assert row["current_recommendation_streak_profile"] == "aggressive"
    assert row["current_reliable_streak_len"] == "0"
    assert row["stability_index"] == "0.25"
    assert row["recent_stability_index"] == "0.75"
    assert row["stability_label"] == "unstable"
    assert row["overall_status"] == "critical"
    assert row["status_reason_primary"] == "stability_unstable"
    assert row["recommended_action"] == "retune_policy"
    assert row["recommended_action_confidence"] == "0.9"
    assert row["recommended_action_rationale"] == "retune_policy because ..."
    assert row["runs_needed_for_ready"] == "1"
    assert row["ready_progress"] == "0.8"
    assert row["estimated_hours_to_ready"] == "1.0"
    assert row["is_ready_for_next_phase"] == "False"
    assert row["readiness_reason"] == "status_not_healthy"
    assert row["readiness_score"] == "0.7"
    assert row["readiness_label"] == "near_ready"
    assert row["readiness_blocker_count"] == "1"
    assert row["next_command_hint"] == "python scripts/run_profile_matchups.py ..."
    assert row["followup_command_hint"] == "python scripts/summarize_profile_history.py ..."
    assert row["next_steps_plan_json"] == "[\"step1\", \"step2\"]"
    assert row["prioritized_next_step"] == "step1"
    assert row["next_command_sequence_json"] == "[\"cmd1\", \"cmd2\"]"
    assert row["next_command_sequence_shell"] == "cmd1 ; cmd2"
    assert row["next_command_sequence_powershell"] == "cmd1 ; cmd2"
    assert row["next_command_sequence_bash"] == "cmd1 && cmd2"
    assert row["next_command_sequence_multiline"] == "cmd1\ncmd2"
    assert row["latest_recommended_profile"] == "aggressive"
    assert row["latest_delta_recommendation_changed"] == "True"


def test_phase5_history_recent_runs_to_csv_rows_window() -> None:
    rows = [
        {"timestamp_utc": "t1", "recommended_profile": "balanced", "match_quality_decisive_rate": "0.2"},
        {"timestamp_utc": "t2", "recommended_profile": "aggressive", "match_quality_decisive_rate": "0.3"},
        {"timestamp_utc": "t3", "recommended_profile": "control", "match_quality_decisive_rate": "0.4"},
    ]
    out = history_recent_runs_to_csv_rows(rows, recent_window=2)
    assert len(out) == 2
    assert out[0]["timestamp_utc"] == "t2"
    assert out[1]["timestamp_utc"] == "t3"
    assert out[0]["match_quality_decisive_rate"] == "0.3"


def test_phase5_command_hints_from_summary_shape() -> None:
    summary = {
        "prioritized_next_step": "run more games",
        "next_command_hint": "python scripts/run_profile_matchups.py ...",
        "followup_command_hint": "python scripts/summarize_profile_history.py ...",
        "next_command_sequence_shell": "cmd1 ; cmd2",
        "next_command_sequence_powershell": "cmd1 ; cmd2",
        "next_command_sequence_bash": "cmd1 && cmd2",
        "next_command_sequence_multiline": "cmd1\ncmd2",
    }
    hints = command_hints_from_summary(summary)
    assert hints["prioritized_next_step"] == "run more games"
    assert hints["next_command_hint"] == "python scripts/run_profile_matchups.py ..."
    assert hints["followup_command_hint"] == "python scripts/summarize_profile_history.py ..."
    assert hints["next_command_sequence_shell"] == "cmd1 ; cmd2"
    assert hints["next_command_sequence_powershell"] == "cmd1 ; cmd2"
    assert hints["next_command_sequence_bash"] == "cmd1 && cmd2"
    assert hints["next_command_sequence_multiline"] == "cmd1\ncmd2"


def test_phase5_command_hints_to_csv_row_shape() -> None:
    summary = {
        "prioritized_next_step": "run more games",
        "next_command_hint": "python scripts/run_profile_matchups.py ...",
        "followup_command_hint": "python scripts/summarize_profile_history.py ...",
        "next_command_sequence_shell": "cmd1 ; cmd2",
        "next_command_sequence_powershell": "cmd1 ; cmd2",
        "next_command_sequence_bash": "cmd1 && cmd2",
        "next_command_sequence_multiline": "cmd1\ncmd2",
    }
    row = command_hints_to_csv_row(summary)
    assert row["prioritized_next_step"] == "run more games"
    assert row["next_command_hint"] == "python scripts/run_profile_matchups.py ..."
    assert row["followup_command_hint"] == "python scripts/summarize_profile_history.py ..."
    assert row["next_command_sequence_shell"] == "cmd1 ; cmd2"
    assert row["next_command_sequence_powershell"] == "cmd1 ; cmd2"
    assert row["next_command_sequence_bash"] == "cmd1 && cmd2"
    assert row["next_command_sequence_multiline"] == "cmd1\ncmd2"


def test_phase5_command_hints_to_json_payload_shape() -> None:
    summary = {
        "prioritized_next_step": "run more games",
        "next_command_hint": "python scripts/run_profile_matchups.py ...",
        "followup_command_hint": "python scripts/summarize_profile_history.py ...",
        "next_command_sequence_shell": "cmd1 ; cmd2",
        "next_command_sequence_powershell": "cmd1 ; cmd2",
        "next_command_sequence_bash": "cmd1 && cmd2",
        "next_command_sequence_multiline": "cmd1\ncmd2",
    }
    payload = command_hints_to_json_payload(summary)
    assert payload["prioritized_next_step"] == "run more games"
    assert payload["next_command_hint"] == "python scripts/run_profile_matchups.py ..."
    assert payload["followup_command_hint"] == "python scripts/summarize_profile_history.py ..."
    assert isinstance(payload["next_command_sequence"], dict)
    sequence = payload["next_command_sequence"]
    assert sequence["shell"] == "cmd1 ; cmd2"
    assert sequence["powershell"] == "cmd1 ; cmd2"
    assert sequence["bash"] == "cmd1 && cmd2"
    assert sequence["multiline"] == "cmd1\ncmd2"
