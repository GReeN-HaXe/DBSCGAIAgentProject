from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from src.agent.session import HumanVsAiSession, describe_action


@dataclass(frozen=True)
class ReplayResult:
    consumed_human_actions: int
    ai_actions: int
    completed: bool
    winner_id: int | None
    final_turn_number: int
    final_phase: str


def compute_trace_hash(trace_payload: dict[str, object]) -> str:
    normalized = dict(trace_payload)
    actions = normalized.get("actions")
    if isinstance(actions, list):
        cleaned: list[object] = []
        for item in actions:
            if isinstance(item, dict):
                d = dict(item)
                d.pop("timestamp_utc", None)
                cleaned.append(d)
            else:
                cleaned.append(item)
        normalized["actions"] = cleaned
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_scripted_replay(
    *,
    session: HumanVsAiSession,
    human_action_indices: list[int],
    max_actions: int = 400,
) -> ReplayResult:
    consumed = 0
    ai_steps = 0
    while not session.is_over() and session.total_actions < max(1, int(max_actions)):
        ai_actions = session.step_ai_until_human_turn(max_ai_actions=max_actions)
        ai_steps += len(ai_actions)
        if session.is_over():
            break
        legal = session.legal_actions_for_human()
        if not legal:
            break
        if consumed >= len(human_action_indices):
            break
        idx = int(human_action_indices[consumed])
        if idx < 0 or idx >= len(legal):
            rendered = [describe_action(a) for a in legal[:20]]
            raise ValueError(
                f"Scripted action index out of range at step {consumed}: idx={idx}, legal={len(legal)}, sample={rendered}"
            )
        session.apply_human_action_by_index(idx)
        consumed += 1
    return ReplayResult(
        consumed_human_actions=consumed,
        ai_actions=ai_steps,
        completed=bool(session.is_over()),
        winner_id=session.state.winner_id,
        final_turn_number=int(session.state.turn_number),
        final_phase=session.state.phase.value,
    )
