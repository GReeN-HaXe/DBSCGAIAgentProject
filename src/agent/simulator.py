from __future__ import annotations

from dataclasses import dataclass

from src.agent.policy import AgentPolicy
from src.game import RulesEngine
from src.game.state import GameState, TurnPhase


@dataclass(frozen=True)
class ScoredDecision:
    action_type: str
    score: float
    reason: str


@dataclass(frozen=True)
class DecisionTraceEntry:
    step_index: int
    actor_player_id: int
    turn_number: int
    phase: TurnPhase
    chosen_action_type: str
    candidates: tuple[ScoredDecision, ...]


@dataclass(frozen=True)
class SimulationResult:
    final_state: GameState
    total_actions: int
    decision_trace: tuple[DecisionTraceEntry, ...] = ()


def simulation_result_to_dict(result: SimulationResult) -> dict[str, object]:
    return {
        "total_actions": result.total_actions,
        "winner_id": result.final_state.winner_id,
        "turn_number": result.final_state.turn_number,
        "active_player": result.final_state.active_player,
        "phase": result.final_state.phase.value,
        "decision_trace": [
            {
                "step_index": entry.step_index,
                "actor_player_id": entry.actor_player_id,
                "turn_number": entry.turn_number,
                "phase": entry.phase.value,
                "chosen_action_type": entry.chosen_action_type,
                "candidates": [
                    {
                        "action_type": c.action_type,
                        "score": c.score,
                        "reason": c.reason,
                    }
                    for c in entry.candidates
                ],
            }
            for entry in result.decision_trace
        ],
    }


def run_ai_vs_ai(
    *,
    engine: RulesEngine,
    state: GameState,
    p1_policy: AgentPolicy,
    p2_policy: AgentPolicy,
    max_actions: int = 500,
    capture_trace: bool = False,
    trace_top_k: int = 3,
) -> SimulationResult:
    actions_taken = 0
    trace: list[DecisionTraceEntry] = []
    while state.winner_id is None and actions_taken < max_actions:
        legal = engine.get_legal_actions(state, state.active_player if state.counter_window is None else state.counter_window.responder_player_id)
        if not legal:
            break
        actor_id = legal[0].player_id
        policy = p1_policy if actor_id == 1 else p2_policy
        ranked = None
        rank_fn = getattr(policy, "rank_actions", None)
        if callable(rank_fn):
            try:
                ranked = rank_fn(state, legal)
            except Exception:
                ranked = None
        if ranked:
            choice = ranked[0].action
        else:
            choice = policy.choose_action(state, legal)
        if choice not in legal:
            raise ValueError(f"Policy returned illegal action: {choice}")
        if capture_trace:
            if ranked:
                top = ranked[: max(1, trace_top_k)]
                candidates = tuple(
                    ScoredDecision(
                        action_type=str(item.action.action_type.value),
                        score=float(item.score),
                        reason=str(item.reason),
                    )
                    for item in top
                )
            else:
                candidates = (
                    ScoredDecision(
                        action_type=str(choice.action_type.value),
                        score=0.0,
                        reason="choose_action_only",
                    ),
                )
            trace.append(
                DecisionTraceEntry(
                    step_index=actions_taken + 1,
                    actor_player_id=actor_id,
                    turn_number=state.turn_number,
                    phase=state.phase,
                    chosen_action_type=str(choice.action_type.value),
                    candidates=candidates,
                )
            )
        state = engine.apply_action(state, choice)
        actions_taken += 1
    return SimulationResult(final_state=state, total_actions=actions_taken, decision_trace=tuple(trace))
