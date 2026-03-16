from __future__ import annotations

from collections import Counter, defaultdict
import re

BOOKKEEPING_ACTION_TYPES = {
    "pass_counter_window",
    "end_offense_step",
    "end_defense_step",
    "resolve_battle",
}

_ACTION_FIELD_RE = re.compile(r"([A-Za-z_]+)=([^ ]+)")


def derive_action_signature(action_type: object, action_text: object) -> str:
    base = str(action_type or "unknown").strip() or "unknown"
    text = str(action_text or "").strip()
    if not text:
        return base
    fields: dict[str, str] = {}
    for key, value in _ACTION_FIELD_RE.findall(text):
        fields[str(key)] = str(value)
    parts = [base]
    for key in (
        "card",
        "source_card",
        "attacker_card",
        "target_card",
        "source_zone",
        "attacker_zone",
        "target_zone",
        "target_player",
    ):
        value = fields.get(key, "").strip()
        if value:
            parts.append(f"{key}={value}")
    if len(parts) == 1:
        for key in ("hand_index", "source_index", "attacker_index", "target_index"):
            value = fields.get(key, "").strip()
            if value:
                parts.append(f"{key}={value}")
    return "|".join(parts)


def filter_decision_trace(
    payload: dict[str, object],
    *,
    include_bookkeeping: bool = False,
) -> list[dict[str, object]]:
    decision_trace = payload.get("decision_trace", [])
    if not isinstance(decision_trace, list):
        return []
    rows: list[dict[str, object]] = []
    for row in decision_trace:
        if not isinstance(row, dict):
            continue
        action_type = str(row.get("chosen_action_type", ""))
        if not include_bookkeeping and action_type in BOOKKEEPING_ACTION_TYPES:
            continue
        rows.append(dict(row))
    return rows


def build_review_trace_payload(
    payload: dict[str, object],
    *,
    include_bookkeeping: bool = False,
) -> dict[str, object]:
    filtered = filter_decision_trace(payload, include_bookkeeping=include_bookkeeping)
    return {
        "schema_version": "ai_match_review_trace.v1",
        "source_schema_version": payload.get("schema_version", "raw"),
        "total_actions": payload.get("total_actions"),
        "winner_id": payload.get("winner_id"),
        "stop_reason": payload.get("stop_reason"),
        "turn_number": payload.get("turn_number"),
        "active_player": payload.get("active_player"),
        "phase": payload.get("phase"),
        "final_state_snapshot": payload.get("final_state_snapshot"),
        "include_bookkeeping": bool(include_bookkeeping),
        "filtered_action_types": sorted(BOOKKEEPING_ACTION_TYPES) if not include_bookkeeping else [],
        "decision_count": len(filtered),
        "decision_trace": filtered,
    }


def build_training_trace_rows(
    payload: dict[str, object],
    *,
    include_bookkeeping: bool = False,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    filtered = filter_decision_trace(payload, include_bookkeeping=include_bookkeeping)
    for row in filtered:
        candidates = row.get("candidates", [])
        top = candidates[0] if isinstance(candidates, list) and candidates else {}
        if not isinstance(top, dict):
            top = {}
        rows.append(
            {
                "schema_version": "ai_match_training_row.v1",
                "step_index": row.get("step_index"),
                "actor_player_id": row.get("actor_player_id"),
                "turn_number": row.get("turn_number"),
                "phase": row.get("phase"),
                "chosen_action_type": row.get("chosen_action_type"),
                "chosen_action_text": row.get("chosen_action_text"),
                "action_signature": derive_action_signature(row.get("chosen_action_type"), row.get("chosen_action_text")),
                "top1_reason": top.get("reason"),
                "top1_score": top.get("score"),
                "winner_id": payload.get("winner_id"),
                "stop_reason": payload.get("stop_reason"),
                "final_turn_number": payload.get("turn_number"),
                "state_snapshot": row.get("state_snapshot"),
                "post_action_state_snapshot": row.get("post_action_state_snapshot"),
            }
        )
    return rows


def filter_human_trace_actions(
    payload: dict[str, object],
    *,
    include_bookkeeping: bool = False,
) -> list[dict[str, object]]:
    trace = payload.get("trace", {})
    if not isinstance(trace, dict):
        return []
    actions = trace.get("actions", [])
    if not isinstance(actions, list):
        return []
    rows: list[dict[str, object]] = []
    for row in actions:
        if not isinstance(row, dict):
            continue
        action_type = str(row.get("action_type", ""))
        if not include_bookkeeping and action_type in BOOKKEEPING_ACTION_TYPES:
            continue
        rows.append(dict(row))
    return rows


def build_human_review_trace_payload(
    payload: dict[str, object],
    *,
    include_bookkeeping: bool = False,
) -> dict[str, object]:
    trace = payload.get("trace", {})
    if not isinstance(trace, dict):
        trace = {}
    filtered = filter_human_trace_actions(payload, include_bookkeeping=include_bookkeeping)
    decision_trace: list[dict[str, object]] = []
    for index, row in enumerate(filtered, start=1):
        decision_trace.append(
            {
                "step_index": index,
                "actor_player_id": row.get("player_id"),
                "actor_kind": row.get("actor_kind", "unknown"),
                "turn_number": row.get("turn_number"),
                "phase": row.get("phase", ""),
                "chosen_action_type": row.get("action_type", ""),
                "chosen_action_text": row.get("action", ""),
                "secret_auto_id": row.get("secret_auto_id"),
                "secret_auto_trigger": row.get("secret_auto_trigger"),
                "secret_auto_event_id": row.get("secret_auto_event_id"),
                "secret_auto_event_name": row.get("secret_auto_event_name"),
                "secret_auto_origin_zone": row.get("secret_auto_origin_zone"),
                "secret_auto_status_before": row.get("secret_auto_status_before"),
                "state_snapshot": row.get("state_snapshot", {}),
            }
        )
    return {
        "schema_version": "human_match_review_trace.v1",
        "source_schema_version": trace.get("schema_version", payload.get("schema_version", "human_trace")),
        "total_actions": trace.get("total_actions"),
        "winner_id": trace.get("winner_id"),
        "stop_reason": trace.get("stop_reason", ""),
        "turn_number": trace.get("final_turn_number"),
        "active_player": None,
        "phase": trace.get("final_phase", ""),
        "human_player_id": trace.get("human_player_id"),
        "setup": trace.get("setup", {}),
        "final_state_snapshot": trace.get("final_state_snapshot"),
        "secret_auto_summary": trace.get("secret_auto_summary", {}),
        "include_bookkeeping": bool(include_bookkeeping),
        "filtered_action_types": sorted(BOOKKEEPING_ACTION_TYPES) if not include_bookkeeping else [],
        "decision_count": len(decision_trace),
        "decision_trace": decision_trace,
    }


def build_human_training_trace_rows(
    payload: dict[str, object],
    *,
    include_bookkeeping: bool = False,
) -> list[dict[str, object]]:
    trace = payload.get("trace", {})
    if not isinstance(trace, dict):
        trace = {}
    rows: list[dict[str, object]] = []
    filtered = filter_human_trace_actions(payload, include_bookkeeping=include_bookkeeping)
    for index, row in enumerate(filtered, start=1):
        action_type = row.get("action_type", "")
        action_text = row.get("action", "")
        rows.append(
            {
                "schema_version": "human_match_training_row.v1",
                "step_index": index,
                "actor_player_id": row.get("player_id"),
                "actor_kind": row.get("actor_kind", "unknown"),
                "turn_number": row.get("turn_number"),
                "phase": row.get("phase", ""),
                "chosen_action_type": action_type,
                "chosen_action_text": action_text,
                "action_signature": derive_action_signature(action_type, action_text),
                "secret_auto_id": row.get("secret_auto_id"),
                "secret_auto_trigger": row.get("secret_auto_trigger"),
                "secret_auto_event_id": row.get("secret_auto_event_id"),
                "secret_auto_event_name": row.get("secret_auto_event_name"),
                "secret_auto_origin_zone": row.get("secret_auto_origin_zone"),
                "secret_auto_status_before": row.get("secret_auto_status_before"),
                "winner_id": trace.get("winner_id"),
                "stop_reason": trace.get("stop_reason", ""),
                "final_turn_number": trace.get("final_turn_number"),
                "human_player_id": trace.get("human_player_id"),
                "state_snapshot": row.get("state_snapshot", {}),
                "post_action_state_snapshot": row.get("post_action_state_snapshot"),
            }
        )
    return rows


def summarize_trace(payload: dict[str, object]) -> dict[str, object]:
    decision_trace = payload.get("decision_trace", [])
    if not isinstance(decision_trace, list):
        decision_trace = []

    by_player_actions: dict[int, Counter[str]] = defaultdict(Counter)
    by_player_reasons: dict[int, Counter[str]] = defaultdict(Counter)
    total = 0
    for row in decision_trace:
        if not isinstance(row, dict):
            continue
        try:
            player_id = int(row.get("actor_player_id", 0))
        except (TypeError, ValueError):
            player_id = 0
        action_type = str(row.get("chosen_action_type", "unknown"))
        by_player_actions[player_id][action_type] += 1
        total += 1
        candidates = row.get("candidates", [])
        if isinstance(candidates, list) and candidates:
            top = candidates[0]
            if isinstance(top, dict):
                reason = str(top.get("reason", "unknown"))
                by_player_reasons[player_id][reason] += 1

    return {
        "total_decisions": total,
        "actions_by_player": {str(pid): dict(cnt) for pid, cnt in by_player_actions.items()},
        "top_reasons_by_player": {str(pid): dict(cnt) for pid, cnt in by_player_reasons.items()},
        "winner_id": payload.get("winner_id"),
        "turn_number": payload.get("turn_number"),
        "total_actions": payload.get("total_actions"),
    }


def compute_trace_kpis(payload: dict[str, object]) -> dict[str, object]:
    decision_trace = payload.get("decision_trace", [])
    if not isinstance(decision_trace, list):
        decision_trace = []

    total = 0
    sum_top1_score = 0.0
    top1_score_n = 0
    sum_candidate_count = 0
    action_counts: Counter[str] = Counter()
    by_player: dict[int, dict[str, float | int]] = defaultdict(
        lambda: {"decisions": 0, "sum_top1_score": 0.0, "top1_score_n": 0}
    )
    for row in decision_trace:
        if not isinstance(row, dict):
            continue
        total += 1
        action = str(row.get("chosen_action_type", "unknown"))
        action_counts[action] += 1
        try:
            pid = int(row.get("actor_player_id", 0))
        except (TypeError, ValueError):
            pid = 0
        by_player[pid]["decisions"] = int(by_player[pid]["decisions"]) + 1

        candidates = row.get("candidates", [])
        if isinstance(candidates, list):
            sum_candidate_count += len(candidates)
            if candidates and isinstance(candidates[0], dict):
                score = candidates[0].get("score")
                try:
                    score_f = float(score)
                    sum_top1_score += score_f
                    top1_score_n += 1
                    by_player[pid]["sum_top1_score"] = float(by_player[pid]["sum_top1_score"]) + score_f
                    by_player[pid]["top1_score_n"] = int(by_player[pid]["top1_score_n"]) + 1
                except (TypeError, ValueError):
                    pass

    def _rate(action: str) -> float:
        return (float(action_counts[action]) / float(total)) if total else 0.0

    out_by_player: dict[str, dict[str, float | int]] = {}
    for pid, data in by_player.items():
        n = int(data["decisions"])
        sn = int(data["top1_score_n"])
        out_by_player[str(pid)] = {
            "decisions": n,
            "avg_top1_score": (float(data["sum_top1_score"]) / float(sn)) if sn else 0.0,
        }

    return {
        "decision_count": total,
        "avg_top1_score": (sum_top1_score / float(top1_score_n)) if top1_score_n else 0.0,
        "avg_candidate_count": (float(sum_candidate_count) / float(total)) if total else 0.0,
        "attack_rate": _rate("declare_attack"),
        "play_rate": _rate("play_card_from_hand"),
        "end_turn_rate": _rate("end_turn"),
        "action_counts": dict(action_counts),
        "by_player": out_by_player,
    }


def per_turn_kpi_rows(payload: dict[str, object]) -> list[dict[str, str]]:
    decision_trace = payload.get("decision_trace", [])
    if not isinstance(decision_trace, list):
        return []
    grouped: dict[int, Counter[str]] = defaultdict(Counter)
    for row in decision_trace:
        if not isinstance(row, dict):
            continue
        try:
            turn = int(row.get("turn_number", 0))
        except (TypeError, ValueError):
            turn = 0
        action = str(row.get("chosen_action_type", "unknown"))
        grouped[turn][action] += 1
    out: list[dict[str, str]] = []
    for turn in sorted(grouped.keys()):
        counts = grouped[turn]
        total = sum(counts.values())
        def _rate(key: str) -> float:
            return (float(counts.get(key, 0)) / float(total)) if total else 0.0
        out.append(
            {
                "turn": str(turn),
                "decisions": str(total),
                "declare_attack": str(counts.get("declare_attack", 0)),
                "play_card_from_hand": str(counts.get("play_card_from_hand", 0)),
                "end_turn": str(counts.get("end_turn", 0)),
                "attack_rate": str(_rate("declare_attack")),
                "play_rate": str(_rate("play_card_from_hand")),
                "end_turn_rate": str(_rate("end_turn")),
            }
        )
    return out


def per_phase_kpi_rows(payload: dict[str, object]) -> list[dict[str, str]]:
    decision_trace = payload.get("decision_trace", [])
    if not isinstance(decision_trace, list):
        return []
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for row in decision_trace:
        if not isinstance(row, dict):
            continue
        phase = str(row.get("phase", "unknown"))
        action = str(row.get("chosen_action_type", "unknown"))
        grouped[phase][action] += 1

    out: list[dict[str, str]] = []
    for phase in sorted(grouped.keys()):
        counts = grouped[phase]
        total = sum(counts.values())

        def _rate(key: str) -> float:
            return (float(counts.get(key, 0)) / float(total)) if total else 0.0

        out.append(
            {
                "phase": phase,
                "decisions": str(total),
                "declare_attack": str(counts.get("declare_attack", 0)),
                "play_card_from_hand": str(counts.get("play_card_from_hand", 0)),
                "end_turn": str(counts.get("end_turn", 0)),
                "pass_counter_window": str(counts.get("pass_counter_window", 0)),
                "attack_rate": str(_rate("declare_attack")),
                "play_rate": str(_rate("play_card_from_hand")),
                "end_turn_rate": str(_rate("end_turn")),
                "counter_pass_rate": str(_rate("pass_counter_window")),
            }
        )
    return out


def decision_trace_to_csv_rows(payload: dict[str, object]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    decision_trace = payload.get("decision_trace", [])
    if not isinstance(decision_trace, list):
        return rows
    for row in decision_trace:
        if not isinstance(row, dict):
            continue
        candidates = row.get("candidates", [])
        top = candidates[0] if isinstance(candidates, list) and candidates else {}
        if not isinstance(top, dict):
            top = {}
        rows.append(
            {
                "step": str(row.get("step_index", "")),
                "player": str(row.get("actor_player_id", "")),
                "turn": str(row.get("turn_number", "")),
                "phase": str(row.get("phase", "")),
                "chosen": str(row.get("chosen_action_type", "")),
                "top1_reason": str(top.get("reason", "")),
                "top1_score": str(top.get("score", "")),
            }
        )
    return rows
