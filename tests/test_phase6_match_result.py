from __future__ import annotations

from src.agent.match_result import build_compact_match_summary, evaluate_match_expectations
from src.game import RulesEngine
from src.game.state import SecretAutoOpportunity, TurnPhase


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def test_phase6_build_compact_match_summary_shape() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    summary = build_compact_match_summary(
        state=state,
        total_actions=0,
        human_player_id=1,
        ai_profile="balanced",
        setup_metadata={"seed": 5},
    )
    assert summary["human_player_id"] == 1
    assert summary["ai_profile"] == "balanced"
    assert "checkpoint_tail" in summary
    assert "effect_unresolved_count" in summary
    assert "secret_auto_summary" in summary
    assert summary["secret_auto_summary"]["opportunity_count"] == 0
    assert summary["setup"]["seed"] == 5


def test_phase6_build_compact_match_summary_includes_secret_auto_counts() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.secret_auto_opportunities = [
        SecretAutoOpportunity(
            opportunity_id=1,
            secret_auto_id=11,
            owner_player_id=1,
            source_instance_id=101,
            source_card_id=201,
            source_card_number="BT99-001",
            source_zone="battle",
            trigger="self_played",
            handler_id="auto_draw_n",
            event_id=5,
            event_name="card_played",
            created_turn_number=1,
            created_phase=TurnPhase.MAIN,
            status="blocked_limit_per_turn",
            preblocked=True,
        )
    ]
    summary = build_compact_match_summary(
        state=state,
        total_actions=0,
        human_player_id=1,
        ai_profile="balanced",
    )
    assert summary["secret_auto_summary"]["opportunity_count"] == 1
    assert summary["secret_auto_summary"]["blocked_count"] == 1
    assert summary["secret_auto_summary"]["preblocked_count"] == 1


def test_phase6_evaluate_match_expectations_reports_failures() -> None:
    summary = {
        "winner_id": None,
        "final_turn_number": 2,
        "effect_unresolved_count": 3,
    }
    failures = evaluate_match_expectations(
        summary=summary,
        expect_winner=1,
        expect_final_turn=3,
        expect_completed=True,
        max_unresolved_effects=1,
    )
    assert len(failures) == 4
