from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from src.agent import HeuristicPolicy
from src.agent.session import (
    HumanVsAiSession,
    decision_owner_for_state,
    describe_action,
    format_full_board_for_cli,
    snapshot_state_for_trace,
    summarize_state_for_cli,
)
from src.game import RulesEngine
from src.game.actions import Action, ActionType
from src.game.state import CardInstance, GameState, PlayerState, TurnPhase
from scripts.play_vs_ai import _history_action_text


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def test_phase6_session_ai_steps_until_human_turn() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    session = HumanVsAiSession(
        engine=engine,
        state=state,
        human_player_id=2,
        ai_policy=HeuristicPolicy(profile="balanced"),
    )
    actions = session.step_ai_until_human_turn(max_ai_actions=20)
    assert actions
    assert bool(session.legal_actions_for_human()) or session.is_over()


def test_phase6_session_apply_human_action_by_index() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    session = HumanVsAiSession(
        engine=engine,
        state=state,
        human_player_id=1,
        ai_policy=HeuristicPolicy(profile="balanced"),
    )
    legal = session.legal_actions_for_human()
    assert legal
    chosen = session.apply_human_action_by_index(0)
    assert chosen == legal[0]
    assert session.total_actions == 1


def test_phase6_cli_helpers_render_non_empty_text() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    legal = engine.get_legal_actions(state, state.active_player)
    text = summarize_state_for_cli(state)
    action_text = describe_action(legal[0])
    assert "turn=" in text
    assert len(action_text) > 0


def test_phase6_cli_helpers_can_render_card_names() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    legal = engine.get_legal_actions(state, state.active_player)
    action_text = describe_action(
        legal[1],
        state=state,
        card_name_resolver=lambda card_id: f"CARD-{card_id}",
    )
    state_text = summarize_state_for_cli(
        state,
        card_name_resolver=lambda card_id: f"CARD-{card_id}",
        reveal_hand_player_id=1,
    )
    assert "card=CARD-" in action_text
    assert "P1 hand:" in state_text
    assert "[0] CARD-" in state_text


def test_phase6_cli_helpers_render_secret_auto_actions_with_card_names() -> None:
    engine = RulesEngine(
        effect_rules={
            990501: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990501, card_id=990501, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=card)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990501, "source_card_id": 990501, "source_zone": "battle", "played_from": "hand"},
    )

    legal = engine.get_legal_actions(state, 1)
    action_text = describe_action(
        legal[0],
        state=state,
        card_name_resolver=lambda card_id: f"CARD-{card_id}",
    )
    assert "opportunity_id=" in action_text
    assert "source_card=CARD-990501" in action_text
    assert "origin_zone=hand" in action_text


def test_phase6_decision_owner_prefers_pending_secret_auto_opportunity_owner() -> None:
    engine = RulesEngine(
        effect_rules={
            990502: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990502, card_id=990502, owner_id=2, card_type="BATTLE", has_auto=True)
    state.players[2].hand = [card]
    engine._register_card_effects(state, player_id=2, source_zone="hand", card=card)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=2,
        payload={"source_instance_id": 990502, "source_card_id": 990502, "source_zone": "battle", "played_from": "hand"},
    )

    assert decision_owner_for_state(state) == 2


def test_phase6_ai_declares_pending_secret_auto_opportunity() -> None:
    engine = RulesEngine(
        effect_rules={
            990503: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990503, card_id=990503, owner_id=2, card_type="BATTLE", has_auto=True)
    state.players[2].hand = [card]
    engine._register_card_effects(state, player_id=2, source_zone="hand", card=card)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=2,
        payload={"source_instance_id": 990503, "source_card_id": 990503, "source_zone": "battle", "played_from": "hand"},
    )

    session = HumanVsAiSession(
        engine=engine,
        state=state,
        human_player_id=1,
        ai_policy=HeuristicPolicy(profile="balanced"),
    )
    deck_before = len(session.state.players[2].deck)

    chosen = session.step_ai_once()

    assert chosen.action_type == ActionType.DECLARE_SECRET_AUTO
    assert len(session.state.players[2].deck) == deck_before - 1
    opportunity = next(row for row in session.state.secret_auto_opportunities if row.source_instance_id == 990503)
    assert opportunity.status == "declared"
    trace_row = session.action_trace[-1]
    assert trace_row["opportunity_id"] == chosen.opportunity_id
    assert trace_row["secret_auto_trigger"] == "self_played"
    assert trace_row["secret_auto_event_name"] == "card_played"
    assert trace_row["secret_auto_origin_zone"] == "hand"
    assert trace_row["secret_auto_status_before"] == "pending"


def test_phase6_cli_helpers_can_reveal_multiple_hands() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state_text = summarize_state_for_cli(
        state,
        card_name_resolver=lambda card_id: f"CARD-{card_id}",
        reveal_hand_player_ids=(1, 2),
    )
    assert "P1 hand:" in state_text
    assert "P2 hand:" in state_text


def test_phase6_cli_helpers_render_board_details() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].energy.append(CardInstance(instance_id=9001, card_id=9001, owner_id=1, resting=False))
    state.players[1].battle_area.append(CardInstance(instance_id=9002, card_id=9002, owner_id=1, resting=True))
    state_text = summarize_state_for_cli(
        state,
        card_name_resolver=lambda card_id: f"CARD-{card_id}",
        reveal_hand_player_id=1,
    )
    assert "P1 leader=" in state_text
    assert "P1 zones:" in state_text
    assert "Energy:" in state_text
    assert "Battle:" in state_text


def test_phase6_full_board_formatter_is_sectioned_and_readable() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].energy.append(CardInstance(instance_id=9001, card_id=9001, owner_id=1, resting=False))
    state.players[1].battle_area.append(CardInstance(instance_id=9002, card_id=9002, owner_id=1, resting=True))
    text = format_full_board_for_cli(
        state,
        card_name_resolver=lambda card_id: f"CARD-{card_id}",
        reveal_hand_player_ids=(1,),
    )
    assert "P1" in text
    assert "P2" in text
    assert "  Energy:" in text
    assert "  Battle:" in text
    assert "  Hand:" in text
    assert "    [0] CARD-" in text


def test_phase6_session_trace_payload_collects_actions() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    session = HumanVsAiSession(
        engine=engine,
        state=state,
        human_player_id=1,
        ai_policy=HeuristicPolicy(profile="balanced"),
        setup_metadata={"seed": 123, "deck_source": "synthetic"},
    )
    session.apply_human_action_by_index(0)
    payload = session.to_trace_payload()
    assert payload["total_actions"] == 1
    assert isinstance(payload["actions"], list)
    assert len(payload["actions"]) == 1
    assert isinstance(payload["setup"], dict)
    assert payload["setup"]["seed"] == 123
    row = payload["actions"][0]
    assert isinstance(row["state_snapshot"], dict)
    assert row["state_snapshot"]["active_player"] == 1


def test_phase6_session_current_player_uses_counter_window_responder() -> None:
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
    attack = next(a for a in engine.get_legal_actions(state, 2) if a.action_type == ActionType.DECLARE_ATTACK)
    state = engine.apply_action(state, attack)
    session = HumanVsAiSession(
        engine=engine,
        state=state,
        human_player_id=1,
        ai_policy=HeuristicPolicy(profile="balanced"),
    )
    assert state.counter_window is not None
    assert session.current_player() == 1


def test_phase6_snapshot_state_for_trace_has_compact_zone_counts() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    snapshot = snapshot_state_for_trace(state)
    assert snapshot["phase"] == state.phase.value
    players = snapshot["players"]
    assert isinstance(players, dict)
    assert players["1"]["hand_size"] == 6
    assert players["1"]["life_size"] == 8
    assert players["1"]["deck_size"] == 46


def test_phase6_session_ai_loop_guard_prefers_fallback_action() -> None:
    class LoopPolicy:
        def choose_action(self, state: GameState, legal_actions: list[Action]) -> Action:
            for action in legal_actions:
                if action.action_type == ActionType.ACTIVATE_MAIN_SKILL:
                    return action
            return legal_actions[0]

        def rank_actions(self, state: GameState, legal_actions: list[Action]) -> list[object]:
            return [type("Ranked", (), {"action": action}) for action in legal_actions]

    class LoopEngine:
        def get_legal_actions(self, state: GameState, player_id: int) -> list[Action]:
            if state.winner_id is not None or player_id != state.active_player:
                return []
            return [
                Action(action_type=ActionType.ACTIVATE_MAIN_SKILL, player_id=player_id, source_zone="leader"),
                Action(action_type=ActionType.END_TURN, player_id=player_id),
            ]

        def apply_action(self, state: GameState, action: Action) -> GameState:
            if action.action_type == ActionType.ACTIVATE_MAIN_SKILL:
                return state
            ns = replace(state)
            ns.active_player = 1
            return ns

    leader_1 = CardInstance(instance_id=1, card_id=1, owner_id=1)
    leader_2 = CardInstance(instance_id=2, card_id=2, owner_id=2, has_activate_main=True)
    state = GameState(
        players={
            1: PlayerState(player_id=1, leader_card_id=1, leader_area=leader_1, life=[leader_1], hand=[], deck=[]),
            2: PlayerState(player_id=2, leader_card_id=2, leader_area=leader_2, life=[leader_2], hand=[], deck=[]),
        },
        active_player=2,
        first_player_id=1,
        phase=TurnPhase.MAIN,
    )
    session = HumanVsAiSession(
        engine=LoopEngine(),  # type: ignore[arg-type]
        state=state,
        human_player_id=1,
        ai_policy=LoopPolicy(),  # type: ignore[arg-type]
    )
    first = session.step_ai_once()
    second = session.step_ai_once()
    assert first.action_type == ActionType.ACTIVATE_MAIN_SKILL
    assert second.action_type == ActionType.END_TURN


def test_phase6_session_ai_action_context_uses_pre_action_state() -> None:
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
    session = HumanVsAiSession(
        engine=engine,
        state=state,
        human_player_id=1,
        ai_policy=HeuristicPolicy(profile="balanced"),
    )
    entries = session.step_ai_until_human_turn_with_context(max_ai_actions=1)
    assert len(entries) == 1
    action = entries[0]["action"]
    state_before = entries[0]["state_before"]
    if action.action_type == ActionType.CHARGE_FROM_HAND:
        rendered = describe_action(
            action,
            state=state_before,
            card_name_resolver=lambda card_id: f"CARD-{card_id}",
        )
        assert "card=CARD-" in rendered


def test_phase6_history_action_text_renders_card_labels_from_cards_and_variants() -> None:
    class FakeRepo:
        def get_by_id(self, card_id: int, *, source_table: str = "cards"):
            if source_table == "cards" and card_id == 9629:
                return SimpleNamespace(card_number="BT29-086", card_name="Goku Black")
            if source_table == "variants" and card_id == 6:
                return SimpleNamespace(card_number="BT14-019", card_name="Dyspo, Thwarting the Enemy")
            raise KeyError(card_id)

    text = _history_action_text(
        {
            "action": "declare_attack attacker_zone=battle attacker_index=0 attacker_card=card_id=6 target_player=2 target_zone=leader target_card=card_id=9629"
        },
        repo=FakeRepo(),
    )
    assert "attacker_card=BT14-019 Dyspo, Thwarting the Enemy" in text
    assert "target_card=BT29-086 Goku Black" in text
    assert "card_id=6" not in text
    assert "card_id=9629" not in text
