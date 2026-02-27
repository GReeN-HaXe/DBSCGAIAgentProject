from __future__ import annotations

from collections import Counter, defaultdict


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
