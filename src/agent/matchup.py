from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import statistics
from typing import Callable

from src.agent.heuristic import HeuristicPolicy
from src.agent.simulator import run_ai_vs_ai
from src.game import GameState, RulesEngine


@dataclass(frozen=True)
class MatchupRow:
    p1_profile: str
    p2_profile: str
    games: int
    p1_wins: int
    p2_wins: int
    draws: int
    avg_actions: float
    avg_turn: float


def run_profile_matchup_matrix(
    *,
    engine_factory: Callable[[], RulesEngine],
    state_factory: Callable[[RulesEngine], GameState],
    profiles: list[str],
    games_per_matchup: int = 2,
    max_actions: int = 120,
) -> list[MatchupRow]:
    if not profiles:
        return []
    if games_per_matchup < 1:
        raise ValueError("games_per_matchup must be >= 1")

    rows: list[MatchupRow] = []
    for p1 in profiles:
        for p2 in profiles:
            p1_wins = 0
            p2_wins = 0
            draws = 0
            total_actions = 0
            total_turns = 0
            for _ in range(games_per_matchup):
                engine = engine_factory()
                state = state_factory(engine)
                result = run_ai_vs_ai(
                    engine=engine,
                    state=state,
                    p1_policy=HeuristicPolicy(profile=p1),
                    p2_policy=HeuristicPolicy(profile=p2),
                    max_actions=max(1, max_actions),
                )
                total_actions += result.total_actions
                total_turns += result.final_state.turn_number
                if result.final_state.winner_id == 1:
                    p1_wins += 1
                elif result.final_state.winner_id == 2:
                    p2_wins += 1
                else:
                    draws += 1
            rows.append(
                MatchupRow(
                    p1_profile=p1,
                    p2_profile=p2,
                    games=games_per_matchup,
                    p1_wins=p1_wins,
                    p2_wins=p2_wins,
                    draws=draws,
                    avg_actions=float(total_actions) / float(games_per_matchup),
                    avg_turn=float(total_turns) / float(games_per_matchup),
                )
            )
    return rows


def merge_matchup_rows(rows: list[MatchupRow]) -> list[MatchupRow]:
    grouped: dict[tuple[str, str], dict[str, float | int]] = {}
    for row in rows:
        key = (row.p1_profile, row.p2_profile)
        if key not in grouped:
            grouped[key] = {
                "games": 0,
                "p1_wins": 0,
                "p2_wins": 0,
                "draws": 0,
                "weighted_actions": 0.0,
                "weighted_turns": 0.0,
            }
        acc = grouped[key]
        acc["games"] += row.games
        acc["p1_wins"] += row.p1_wins
        acc["p2_wins"] += row.p2_wins
        acc["draws"] += row.draws
        acc["weighted_actions"] += row.avg_actions * float(row.games)
        acc["weighted_turns"] += row.avg_turn * float(row.games)

    merged: list[MatchupRow] = []
    for (p1, p2), acc in sorted(grouped.items(), key=lambda kv: kv[0]):
        games = int(acc["games"])
        if games <= 0:
            continue
        merged.append(
            MatchupRow(
                p1_profile=p1,
                p2_profile=p2,
                games=games,
                p1_wins=int(acc["p1_wins"]),
                p2_wins=int(acc["p2_wins"]),
                draws=int(acc["draws"]),
                avg_actions=float(acc["weighted_actions"]) / float(games),
                avg_turn=float(acc["weighted_turns"]) / float(games),
            )
        )
    return merged


def matchup_rows_to_dict(rows: list[MatchupRow]) -> list[dict[str, object]]:
    return [
        {
            "p1_profile": row.p1_profile,
            "p2_profile": row.p2_profile,
            "games": row.games,
            "p1_wins": row.p1_wins,
            "p2_wins": row.p2_wins,
            "draws": row.draws,
            "avg_actions": round(row.avg_actions, 4),
            "avg_turn": round(row.avg_turn, 4),
            "p1_win_rate": round((row.p1_wins / row.games) if row.games else 0.0, 6),
        }
        for row in rows
    ]


def matchup_rows_from_dict(rows: list[dict[str, object]]) -> list[MatchupRow]:
    parsed: list[MatchupRow] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed.append(
            MatchupRow(
                p1_profile=str(row.get("p1_profile", "")),
                p2_profile=str(row.get("p2_profile", "")),
                games=int(row.get("games", 0)),
                p1_wins=int(row.get("p1_wins", 0)),
                p2_wins=int(row.get("p2_wins", 0)),
                draws=int(row.get("draws", 0)),
                avg_actions=float(row.get("avg_actions", 0.0)),
                avg_turn=float(row.get("avg_turn", 0.0)),
            )
        )
    return parsed


def summarize_profile_strength(rows: list[MatchupRow]) -> dict[str, dict[str, float | int]]:
    summary: dict[str, dict[str, float | int]] = {}

    def _ensure(profile: str) -> dict[str, float | int]:
        if profile not in summary:
            summary[profile] = {"games": 0, "wins": 0, "losses": 0, "draws": 0, "points": 0.0}
        return summary[profile]

    for row in rows:
        p1 = _ensure(row.p1_profile)
        p2 = _ensure(row.p2_profile)

        p1["games"] += row.games
        p1["wins"] += row.p1_wins
        p1["losses"] += row.p2_wins
        p1["draws"] += row.draws
        p1["points"] += float(row.p1_wins) + (0.5 * float(row.draws))

        p2["games"] += row.games
        p2["wins"] += row.p2_wins
        p2["losses"] += row.p1_wins
        p2["draws"] += row.draws
        p2["points"] += float(row.p2_wins) + (0.5 * float(row.draws))

    for profile, data in summary.items():
        games = int(data["games"])
        data["win_rate"] = (float(data["wins"]) / float(games)) if games else 0.0
        data["points_per_game"] = (float(data["points"]) / float(games)) if games else 0.0
        summary[profile] = data

    return summary


def build_head_to_head_matrix(rows: list[MatchupRow]) -> dict[str, dict[str, float]]:
    wins: dict[str, dict[str, int]] = {}
    games: dict[str, dict[str, int]] = {}
    for row in rows:
        p1 = row.p1_profile
        p2 = row.p2_profile
        if p1 not in wins:
            wins[p1] = {}
            games[p1] = {}
        wins[p1][p2] = wins[p1].get(p2, 0) + row.p1_wins
        games[p1][p2] = games[p1].get(p2, 0) + row.games
    matrix: dict[str, dict[str, float]] = {}
    for p1, vs_map in games.items():
        matrix[p1] = {}
        for p2, g in vs_map.items():
            w = wins[p1].get(p2, 0)
            matrix[p1][p2] = (float(w) / float(g)) if g else 0.0
    return matrix


def format_profile_ranking(summary: dict[str, dict[str, float | int]]) -> str:
    header = "Profile Ranking (sorted by points_per_game, then win_rate)"
    cols = f"{'profile':<12} {'ppg':>7} {'win_rate':>9} {'wins':>6} {'losses':>8} {'draws':>7} {'games':>7}"
    rows = []
    ordered = sorted(
        summary.items(),
        key=lambda kv: (
            float(kv[1].get("points_per_game", 0.0)),
            float(kv[1].get("win_rate", 0.0)),
            float(kv[1].get("wins", 0)),
        ),
        reverse=True,
    )
    for profile, data in ordered:
        rows.append(
            f"{profile:<12} "
            f"{float(data.get('points_per_game', 0.0)):>7.3f} "
            f"{float(data.get('win_rate', 0.0)):>9.3f} "
            f"{int(data.get('wins', 0)):>6} "
            f"{int(data.get('losses', 0)):>8} "
            f"{int(data.get('draws', 0)):>7} "
            f"{int(data.get('games', 0)):>7}"
        )
    return "\n".join([header, cols, *rows]) if rows else "\n".join([header, cols])


def format_head_to_head(matrix: dict[str, dict[str, float]]) -> str:
    profiles = sorted(matrix.keys())
    header = "Head-to-Head P1 Win Rate"
    if not profiles:
        return header
    top = ["p1\\p2", *profiles]
    lines = [" | ".join(top)]
    lines.append(" | ".join(["---"] * len(top)))
    for p1 in profiles:
        row = [p1]
        for p2 in profiles:
            wr = matrix.get(p1, {}).get(p2, 0.0)
            row.append(f"{wr:.3f}")
        lines.append(" | ".join(row))
    return "\n".join([header, *lines])


def profile_summary_to_csv_rows(summary: dict[str, dict[str, float | int]]) -> list[dict[str, str]]:
    ordered = sorted(
        summary.items(),
        key=lambda kv: (
            float(kv[1].get("points_per_game", 0.0)),
            float(kv[1].get("win_rate", 0.0)),
            float(kv[1].get("wins", 0)),
        ),
        reverse=True,
    )
    rows: list[dict[str, str]] = []
    for profile, data in ordered:
        rows.append(
            {
                "profile": profile,
                "points_per_game": str(float(data.get("points_per_game", 0.0))),
                "win_rate": str(float(data.get("win_rate", 0.0))),
                "wins": str(int(data.get("wins", 0))),
                "losses": str(int(data.get("losses", 0))),
                "draws": str(int(data.get("draws", 0))),
                "games": str(int(data.get("games", 0))),
                "points": str(float(data.get("points", 0.0))),
            }
        )
    return rows


def head_to_head_to_csv_rows(matrix: dict[str, dict[str, float]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for p1 in sorted(matrix.keys()):
        vs_map = matrix.get(p1, {})
        for p2 in sorted(vs_map.keys()):
            rows.append(
                {
                    "p1_profile": p1,
                    "p2_profile": p2,
                    "p1_win_rate": str(float(vs_map.get(p2, 0.0))),
                }
            )
    return rows


def compute_seat_bias(rows: list[MatchupRow]) -> dict[str, object]:
    total_games = 0
    total_p1_wins = 0
    total_p2_wins = 0
    total_draws = 0
    by_matchup: dict[str, dict[str, float | int]] = {}

    for row in rows:
        total_games += row.games
        total_p1_wins += row.p1_wins
        total_p2_wins += row.p2_wins
        total_draws += row.draws
        key = f"{row.p1_profile}__vs__{row.p2_profile}"
        by_matchup[key] = {
            "games": row.games,
            "p1_win_rate": (float(row.p1_wins) / float(row.games)) if row.games else 0.0,
            "p2_win_rate": (float(row.p2_wins) / float(row.games)) if row.games else 0.0,
            "draw_rate": (float(row.draws) / float(row.games)) if row.games else 0.0,
        }

    if total_games <= 0:
        return {
            "games": 0,
            "p1_win_rate": 0.0,
            "p2_win_rate": 0.0,
            "draw_rate": 0.0,
            "p1_minus_p2": 0.0,
            "by_matchup": by_matchup,
        }
    p1_rate = float(total_p1_wins) / float(total_games)
    p2_rate = float(total_p2_wins) / float(total_games)
    draw_rate = float(total_draws) / float(total_games)
    return {
        "games": total_games,
        "p1_win_rate": p1_rate,
        "p2_win_rate": p2_rate,
        "draw_rate": draw_rate,
        "p1_minus_p2": p1_rate - p2_rate,
        "by_matchup": by_matchup,
    }


def compute_match_quality(
    rows: list[MatchupRow],
    *,
    decisive_rate_alert_threshold: float = 0.30,
) -> dict[str, object]:
    total_games = 0
    total_draws = 0
    for row in rows:
        total_games += int(row.games)
        total_draws += int(row.draws)
    decisive_games = max(0, total_games - total_draws)
    if total_games <= 0:
        decisive_rate = 0.0
        draw_rate = 0.0
    else:
        decisive_rate = float(decisive_games) / float(total_games)
        draw_rate = float(total_draws) / float(total_games)
    threshold = max(0.0, min(1.0, float(decisive_rate_alert_threshold)))
    return {
        "games": total_games,
        "draws": total_draws,
        "decisive_games": decisive_games,
        "draw_rate": draw_rate,
        "decisive_rate": decisive_rate,
        "decisive_rate_alert_threshold": threshold,
        "low_decisive_rate_alert": decisive_rate < threshold,
    }


def seat_bias_to_csv_rows(seat_bias: dict[str, object]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    by_matchup = seat_bias.get("by_matchup", {})
    if not isinstance(by_matchup, dict):
        return rows
    for key in sorted(by_matchup.keys()):
        value = by_matchup.get(key, {})
        if not isinstance(value, dict):
            continue
        if "__vs__" in key:
            p1_profile, p2_profile = key.split("__vs__", 1)
        else:
            p1_profile, p2_profile = key, ""
        rows.append(
            {
                "p1_profile": p1_profile,
                "p2_profile": p2_profile,
                "games": str(int(value.get("games", 0))),
                "p1_win_rate": str(float(value.get("p1_win_rate", 0.0))),
                "p2_win_rate": str(float(value.get("p2_win_rate", 0.0))),
                "draw_rate": str(float(value.get("draw_rate", 0.0))),
            }
        )
    return rows


def build_overview_csv_row(
    *,
    profiles: list[str],
    games_per_matchup: int,
    max_actions: int,
    shuffle_decks: bool,
    seat_balanced: bool,
    seed: int | None,
    min_games_for_recommendation: int,
    recommendation: dict[str, object],
    seat_bias: dict[str, object],
    match_quality: dict[str, object] | None = None,
) -> dict[str, str]:
    quality = match_quality if isinstance(match_quality, dict) else {}
    return {
        "profiles": ",".join(profiles),
        "games_per_matchup": str(int(games_per_matchup)),
        "max_actions": str(int(max_actions)),
        "shuffle_decks": str(bool(shuffle_decks)),
        "seat_balanced": str(bool(seat_balanced)),
        "seed": "" if seed is None else str(int(seed)),
        "min_games_for_recommendation": str(int(min_games_for_recommendation)),
        "recommended_profile": str(recommendation.get("recommended_profile", "")),
        "recommendation_reason": str(recommendation.get("reason", "")),
        "recommendation_reliable": str(bool(recommendation.get("reliable", False))),
        "recommendation_clear_edge": str(bool(recommendation.get("clear_edge", False))),
        "seat_bias_games": str(int(seat_bias.get("games", 0))),
        "seat_bias_p1_win_rate": str(float(seat_bias.get("p1_win_rate", 0.0))),
        "seat_bias_p2_win_rate": str(float(seat_bias.get("p2_win_rate", 0.0))),
        "seat_bias_draw_rate": str(float(seat_bias.get("draw_rate", 0.0))),
        "seat_bias_p1_minus_p2": str(float(seat_bias.get("p1_minus_p2", 0.0))),
        "match_quality_draw_rate": str(float(quality.get("draw_rate", 0.0))),
        "match_quality_decisive_rate": str(float(quality.get("decisive_rate", 0.0))),
        "match_quality_low_decisive_rate_alert": str(bool(quality.get("low_decisive_rate_alert", False))),
    }


def build_history_csv_row(
    overview_row: dict[str, str],
    *,
    timestamp_utc: str,
    source_json: str,
) -> dict[str, str]:
    row = {
        "timestamp_utc": timestamp_utc,
        "source_json": source_json,
    }
    row.update(overview_row)
    return row


def summarize_history_rows(
    rows: list[dict[str, str]],
    *,
    recent_window: int = 5,
    seat_bias_alert_threshold: float = 0.15,
    decisive_rate_alert_threshold: float = 0.30,
    min_runs_for_ready: int = 5,
) -> dict[str, object]:
    if not rows:
        return {
            "total_runs": 0,
            "recommendation_counts": {},
            "reliable_rate": 0.0,
            "recommendation_switches": 0,
            "recent_window": max(1, int(recent_window)),
            "recent_recommendation_counts": {},
            "recent_recommendation_switches": 0,
            "recent_switch_rate": 0.0,
            "top_recommendation_share": 0.0,
            "recent_top_recommendation_share": 0.0,
            "distinct_recommended_profiles": 0,
            "recommendation_entropy": 0.0,
            "recent_distinct_recommended_profiles": 0,
            "recent_recommendation_entropy": 0.0,
            "recent_reliable_rate": 0.0,
            "recent_unreliable_rate": 0.0,
            "avg_hours_between_runs": 0.0,
            "median_hours_between_runs": 0.0,
            "latest_hours_since_previous": 0.0,
            "recent_avg_abs_seat_bias_delta": 0.0,
            "seat_bias_alert_threshold": float(seat_bias_alert_threshold),
            "seat_bias_alert_count": 0,
            "recent_seat_bias_alert_count": 0,
            "decisive_rate_alert_threshold": float(decisive_rate_alert_threshold),
            "low_decisive_rate_alert_count": 0,
            "recent_low_decisive_rate_alert_count": 0,
            "quality_alert_count": 0,
            "recent_quality_alert_count": 0,
            "current_recommendation_streak_profile": "",
            "current_recommendation_streak_len": 0,
            "current_reliable_streak_len": 0,
            "current_quality_alert_streak_len": 0,
            "stability_index": 0.0,
            "recent_stability_index": 0.0,
            "stability_label": "unstable",
            "overall_status": "critical",
            "status_reasons": ["no_runs"],
            "status_reason_primary": "no_runs",
            "recommended_action": "increase_games",
            "recommended_action_confidence": 0.0,
            "recommended_action_rationale": "No runs available; gather more benchmark data.",
            "min_runs_for_ready": max(1, int(min_runs_for_ready)),
            "runs_needed_for_ready": max(1, int(min_runs_for_ready)),
            "ready_progress": 0.0,
            "estimated_hours_to_ready": 0.0,
            "estimated_ready_timestamp_utc": "",
            "is_ready_for_next_phase": False,
            "readiness_reason": "insufficient_runs",
            "latest": None,
        }

    rec_counts: dict[str, int] = {}
    reliable = 0
    switches = 0
    prev_rec = ""
    for row in rows:
        rec = str(row.get("recommended_profile", "")).strip()
        if rec:
            rec_counts[rec] = rec_counts.get(rec, 0) + 1
            if prev_rec and rec != prev_rec:
                switches += 1
            prev_rec = rec
        is_reliable = str(row.get("recommendation_reliable", "")).strip().lower() == "true"
        if is_reliable:
            reliable += 1

    win = max(1, int(recent_window))
    recent = rows[-win:]
    recent_counts: dict[str, int] = {}
    recent_switches = 0
    recent_prev_rec = ""
    recent_reliable = 0
    recent_abs_delta_sum = 0.0
    recent_abs_delta_n = 0
    seat_bias_alert_count = 0
    recent_seat_bias_alert_count = 0
    low_decisive_rate_alert_count = 0
    recent_low_decisive_rate_alert_count = 0
    quality_alert_count = 0
    recent_quality_alert_count = 0
    for row in recent:
        seat_bias_alert_this_row = False
        rec = str(row.get("recommended_profile", "")).strip()
        if rec:
            recent_counts[rec] = recent_counts.get(rec, 0) + 1
            if recent_prev_rec and rec != recent_prev_rec:
                recent_switches += 1
            recent_prev_rec = rec
        if str(row.get("recommendation_reliable", "")).strip().lower() == "true":
            recent_reliable += 1
        raw_delta = str(row.get("seat_bias_p1_minus_p2", "")).strip()
        try:
            abs_delta = abs(float(raw_delta))
            recent_abs_delta_sum += abs_delta
            recent_abs_delta_n += 1
            if abs_delta > float(seat_bias_alert_threshold):
                recent_seat_bias_alert_count += 1
                seat_bias_alert_this_row = True
        except ValueError:
            pass
        low_decisive_alert_this_row = False
        raw_low_decisive = str(row.get("match_quality_low_decisive_rate_alert", "")).strip().lower()
        if raw_low_decisive == "true":
            recent_low_decisive_rate_alert_count += 1
            low_decisive_alert_this_row = True
        elif raw_low_decisive == "":
            raw_decisive = str(row.get("match_quality_decisive_rate", "")).strip()
            try:
                if float(raw_decisive) < float(decisive_rate_alert_threshold):
                    recent_low_decisive_rate_alert_count += 1
                    low_decisive_alert_this_row = True
            except ValueError:
                pass
        if seat_bias_alert_this_row or low_decisive_alert_this_row:
            recent_quality_alert_count += 1
    for row in rows:
        seat_bias_alert_this_row = False
        raw_delta = str(row.get("seat_bias_p1_minus_p2", "")).strip()
        try:
            abs_delta = abs(float(raw_delta))
            if abs_delta > float(seat_bias_alert_threshold):
                seat_bias_alert_count += 1
                seat_bias_alert_this_row = True
        except ValueError:
            pass
        low_decisive_alert_this_row = False
        raw_low_decisive = str(row.get("match_quality_low_decisive_rate_alert", "")).strip().lower()
        if raw_low_decisive == "true":
            low_decisive_rate_alert_count += 1
            low_decisive_alert_this_row = True
        elif raw_low_decisive == "":
            raw_decisive = str(row.get("match_quality_decisive_rate", "")).strip()
            try:
                if float(raw_decisive) < float(decisive_rate_alert_threshold):
                    low_decisive_rate_alert_count += 1
                    low_decisive_alert_this_row = True
            except ValueError:
                pass
        if seat_bias_alert_this_row or low_decisive_alert_this_row:
            quality_alert_count += 1

    current_recommendation_streak_profile = str(rows[-1].get("recommended_profile", "")).strip()
    current_recommendation_streak_len = 0
    if current_recommendation_streak_profile:
        for row in reversed(rows):
            rec = str(row.get("recommended_profile", "")).strip()
            if rec == current_recommendation_streak_profile:
                current_recommendation_streak_len += 1
            else:
                break

    current_quality_alert_streak_len = 0
    for row in reversed(rows):
        seat_bias_alert_this_row = False
        raw_delta = str(row.get("seat_bias_p1_minus_p2", "")).strip()
        try:
            if abs(float(raw_delta)) > float(seat_bias_alert_threshold):
                seat_bias_alert_this_row = True
        except ValueError:
            pass
        low_decisive_alert_this_row = False
        raw_low_decisive = str(row.get("match_quality_low_decisive_rate_alert", "")).strip().lower()
        if raw_low_decisive == "true":
            low_decisive_alert_this_row = True
        elif raw_low_decisive == "":
            raw_decisive = str(row.get("match_quality_decisive_rate", "")).strip()
            try:
                if float(raw_decisive) < float(decisive_rate_alert_threshold):
                    low_decisive_alert_this_row = True
            except ValueError:
                pass
        if seat_bias_alert_this_row or low_decisive_alert_this_row:
            current_quality_alert_streak_len += 1
        else:
            break

    # 0..1 score where 1 means stable recommendations with no quality alerts.
    churn_rate = (float(switches) / float(max(1, len(rows) - 1)))
    alert_rate = (float(quality_alert_count) / float(len(rows)))
    stability_index = max(0.0, min(1.0, 1.0 - (0.5 * churn_rate + 0.5 * alert_rate)))
    recent_switch_rate = (float(recent_switches) / float(max(1, len(recent) - 1)))
    recent_alert_rate = (float(recent_quality_alert_count) / float(len(recent)))
    recent_stability_index = max(0.0, min(1.0, 1.0 - (0.5 * recent_switch_rate + 0.5 * recent_alert_rate)))
    if stability_index >= 0.8:
        stability_label = "stable"
    elif stability_index >= 0.5:
        stability_label = "watch"
    else:
        stability_label = "unstable"
    status_reasons: list[str] = []
    if stability_label == "unstable":
        status_reasons.append("stability_unstable")
    elif stability_label == "watch":
        status_reasons.append("stability_watch")
    if recent_quality_alert_count >= 2:
        status_reasons.append("recent_quality_alerts_high")
    elif recent_quality_alert_count >= 1:
        status_reasons.append("recent_quality_alerts_present")
    if float(recent_unreliable_rate := (1.0 - (float(recent_reliable) / float(len(recent))))) > 0.25:
        status_reasons.append("recent_unreliable_rate_high")
    if stability_label == "unstable" or recent_quality_alert_count >= 2:
        overall_status = "critical"
    elif stability_label == "watch" or recent_quality_alert_count >= 1:
        overall_status = "warning"
    else:
        overall_status = "healthy"
    if not status_reasons:
        status_reasons = ["healthy_stable"]
    if overall_status == "healthy":
        recommended_action = "continue"
    elif "recent_quality_alerts_high" in status_reasons or "stability_unstable" in status_reasons:
        recommended_action = "retune_policy"
    else:
        recommended_action = "increase_games"
    # Confidence biases toward stronger stability and larger recent windows.
    sample_factor = min(1.0, float(len(recent)) / 10.0)
    if recommended_action == "continue":
        recommended_action_confidence = max(0.0, min(1.0, 0.5 * stability_index + 0.5 * sample_factor))
    elif recommended_action == "retune_policy":
        recommended_action_confidence = max(0.0, min(1.0, 0.5 * (1.0 - stability_index) + 0.5 * (float(recent_quality_alert_count) / float(len(recent)))))
    else:
        recommended_action_confidence = max(0.0, min(1.0, 0.5 * (1.0 - sample_factor) + 0.5 * (1.0 - recent_reliable_rate)))
    recommended_action_rationale = (
        f"{recommended_action} because status={overall_status}, "
        f"primary_reason={status_reasons[0]}, confidence={recommended_action_confidence:.3f}"
    )
    min_runs = max(1, int(min_runs_for_ready))
    runs_needed_for_ready = max(0, min_runs - len(rows))
    ready_progress = min(1.0, float(len(rows)) / float(min_runs))
    if len(rows) < min_runs:
        is_ready_for_next_phase = False
        readiness_reason = "insufficient_runs"
    elif overall_status != "healthy":
        is_ready_for_next_phase = False
        readiness_reason = "status_not_healthy"
    elif recommended_action != "continue":
        is_ready_for_next_phase = False
        readiness_reason = "action_not_continue"
    else:
        is_ready_for_next_phase = True
        readiness_reason = "ready"

    latest = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None
    latest_delta: dict[str, object] | None
    if isinstance(prev, dict):
        latest_reliable = str(latest.get("recommendation_reliable", "")).strip().lower() == "true"
        prev_reliable = str(prev.get("recommendation_reliable", "")).strip().lower() == "true"
        latest_rec = str(latest.get("recommended_profile", "")).strip()
        prev_rec = str(prev.get("recommended_profile", "")).strip()
        latest_reason = str(latest.get("recommendation_reason", "")).strip()
        prev_reason = str(prev.get("recommendation_reason", "")).strip()
        try:
            latest_delta_seat = float(str(latest.get("seat_bias_p1_minus_p2", "")).strip() or "0")
            prev_delta_seat = float(str(prev.get("seat_bias_p1_minus_p2", "")).strip() or "0")
        except ValueError:
            latest_delta_seat = 0.0
            prev_delta_seat = 0.0
        latest_delta = {
            "recommendation_changed": latest_rec != prev_rec,
            "reason_changed": latest_reason != prev_reason,
            "reliability_changed": latest_reliable != prev_reliable,
            "seat_bias_delta_change": latest_delta_seat - prev_delta_seat,
            "previous_timestamp_utc": prev.get("timestamp_utc", ""),
        }
    else:
        latest_delta = None

    top_recommendation_share = (float(max(rec_counts.values())) / float(len(rows))) if rec_counts else 0.0
    recent_top_recommendation_share = (float(max(recent_counts.values())) / float(len(recent))) if recent_counts else 0.0
    distinct_recommended_profiles = len(rec_counts)
    recent_distinct_recommended_profiles = len(recent_counts)
    recommendation_entropy = 0.0
    for count in rec_counts.values():
        p = float(count) / float(len(rows))
        if p > 0.0:
            recommendation_entropy += -p * math.log2(p)
    recent_recommendation_entropy = 0.0
    for count in recent_counts.values():
        p = float(count) / float(len(recent))
        if p > 0.0:
            recent_recommendation_entropy += -p * math.log2(p)

    # Cadence metrics from run timestamps.
    parsed_times: list[datetime | None] = []
    for row in rows:
        raw = str(row.get("timestamp_utc", "")).strip()
        if not raw:
            parsed_times.append(None)
            continue
        try:
            parsed_times.append(datetime.fromisoformat(raw))
        except ValueError:
            parsed_times.append(None)
    gap_hours: list[float] = []
    for i in range(1, len(parsed_times)):
        a = parsed_times[i - 1]
        b = parsed_times[i]
        if a is None or b is None:
            continue
        gap_hours.append((b - a).total_seconds() / 3600.0)
    avg_hours_between_runs = (sum(gap_hours) / float(len(gap_hours))) if gap_hours else 0.0
    median_hours_between_runs = float(statistics.median(gap_hours)) if gap_hours else 0.0
    estimated_hours_to_ready = float(runs_needed_for_ready) * avg_hours_between_runs
    latest_ts_raw = str(rows[-1].get("timestamp_utc", "")).strip()
    estimated_ready_timestamp_utc = ""
    if runs_needed_for_ready == 0:
        estimated_ready_timestamp_utc = latest_ts_raw
    elif latest_ts_raw and estimated_hours_to_ready > 0.0:
        try:
            latest_dt = datetime.fromisoformat(latest_ts_raw)
            estimated_ready_timestamp_utc = (latest_dt + timedelta(hours=estimated_hours_to_ready)).isoformat()
        except ValueError:
            estimated_ready_timestamp_utc = ""

    return {
        "total_runs": len(rows),
        "recommendation_counts": rec_counts,
        "reliable_rate": float(reliable) / float(len(rows)),
        "recommendation_switches": switches,
        "recent_window": len(recent),
        "recent_recommendation_counts": recent_counts,
        "recent_recommendation_switches": recent_switches,
        "recent_switch_rate": recent_switch_rate,
        "top_recommendation_share": top_recommendation_share,
        "recent_top_recommendation_share": recent_top_recommendation_share,
        "distinct_recommended_profiles": distinct_recommended_profiles,
        "recommendation_entropy": recommendation_entropy,
        "recent_distinct_recommended_profiles": recent_distinct_recommended_profiles,
        "recent_recommendation_entropy": recent_recommendation_entropy,
        "recent_reliable_rate": float(recent_reliable) / float(len(recent)),
        "recent_unreliable_rate": recent_unreliable_rate,
        "avg_hours_between_runs": avg_hours_between_runs,
        "median_hours_between_runs": median_hours_between_runs,
        "latest_hours_since_previous": (gap_hours[-1] if gap_hours else 0.0),
        "recent_avg_abs_seat_bias_delta": (
            float(recent_abs_delta_sum) / float(recent_abs_delta_n) if recent_abs_delta_n else 0.0
        ),
        "seat_bias_alert_threshold": float(seat_bias_alert_threshold),
        "seat_bias_alert_count": seat_bias_alert_count,
        "recent_seat_bias_alert_count": recent_seat_bias_alert_count,
        "decisive_rate_alert_threshold": float(decisive_rate_alert_threshold),
        "low_decisive_rate_alert_count": low_decisive_rate_alert_count,
        "recent_low_decisive_rate_alert_count": recent_low_decisive_rate_alert_count,
        "quality_alert_count": quality_alert_count,
        "recent_quality_alert_count": recent_quality_alert_count,
        "current_recommendation_streak_profile": current_recommendation_streak_profile,
        "current_recommendation_streak_len": current_recommendation_streak_len,
        "current_reliable_streak_len": (
            next(
                (
                    i
                    for i in range(len(rows) + 1)
                    if i == len(rows)
                    or str(rows[-(i + 1)].get("recommendation_reliable", "")).strip().lower() != "true"
                ),
                len(rows),
            )
        ),
        "current_quality_alert_streak_len": current_quality_alert_streak_len,
        "stability_index": stability_index,
        "recent_stability_index": recent_stability_index,
        "stability_label": stability_label,
        "overall_status": overall_status,
        "status_reasons": status_reasons,
        "status_reason_primary": status_reasons[0],
        "recommended_action": recommended_action,
        "recommended_action_confidence": recommended_action_confidence,
        "recommended_action_rationale": recommended_action_rationale,
        "min_runs_for_ready": min_runs,
        "runs_needed_for_ready": runs_needed_for_ready,
        "ready_progress": ready_progress,
        "estimated_hours_to_ready": estimated_hours_to_ready,
        "estimated_ready_timestamp_utc": estimated_ready_timestamp_utc,
        "is_ready_for_next_phase": is_ready_for_next_phase,
        "readiness_reason": readiness_reason,
        "latest": {
            "timestamp_utc": latest.get("timestamp_utc", ""),
            "recommended_profile": latest.get("recommended_profile", ""),
            "recommendation_reason": latest.get("recommendation_reason", ""),
            "seat_bias_p1_minus_p2": latest.get("seat_bias_p1_minus_p2", ""),
            "source_json": latest.get("source_json", ""),
        },
        "latest_delta": latest_delta,
    }


def format_history_summary(summary: dict[str, object]) -> str:
    total = int(summary.get("total_runs", 0))
    reliable_rate = float(summary.get("reliable_rate", 0.0))
    switches = int(summary.get("recommendation_switches", 0))
    recent_window = int(summary.get("recent_window", 0))
    recent_recommendation_switches = int(summary.get("recent_recommendation_switches", 0))
    recent_switch_rate = float(summary.get("recent_switch_rate", 0.0))
    top_recommendation_share = float(summary.get("top_recommendation_share", 0.0))
    recent_top_recommendation_share = float(summary.get("recent_top_recommendation_share", 0.0))
    distinct_recommended_profiles = int(summary.get("distinct_recommended_profiles", 0))
    recommendation_entropy = float(summary.get("recommendation_entropy", 0.0))
    recent_distinct_recommended_profiles = int(summary.get("recent_distinct_recommended_profiles", 0))
    recent_recommendation_entropy = float(summary.get("recent_recommendation_entropy", 0.0))
    recent_reliable_rate = float(summary.get("recent_reliable_rate", 0.0))
    recent_unreliable_rate = float(summary.get("recent_unreliable_rate", 0.0))
    avg_hours_between_runs = float(summary.get("avg_hours_between_runs", 0.0))
    median_hours_between_runs = float(summary.get("median_hours_between_runs", 0.0))
    latest_hours_since_previous = float(summary.get("latest_hours_since_previous", 0.0))
    recent_avg_abs_delta = float(summary.get("recent_avg_abs_seat_bias_delta", 0.0))
    seat_bias_alert_threshold = float(summary.get("seat_bias_alert_threshold", 0.0))
    seat_bias_alert_count = int(summary.get("seat_bias_alert_count", 0))
    recent_seat_bias_alert_count = int(summary.get("recent_seat_bias_alert_count", 0))
    decisive_rate_alert_threshold = float(summary.get("decisive_rate_alert_threshold", 0.0))
    low_decisive_rate_alert_count = int(summary.get("low_decisive_rate_alert_count", 0))
    recent_low_decisive_rate_alert_count = int(summary.get("recent_low_decisive_rate_alert_count", 0))
    quality_alert_count = int(summary.get("quality_alert_count", 0))
    recent_quality_alert_count = int(summary.get("recent_quality_alert_count", 0))
    current_recommendation_streak_profile = str(summary.get("current_recommendation_streak_profile", ""))
    current_recommendation_streak_len = int(summary.get("current_recommendation_streak_len", 0))
    current_reliable_streak_len = int(summary.get("current_reliable_streak_len", 0))
    current_quality_alert_streak_len = int(summary.get("current_quality_alert_streak_len", 0))
    stability_index = float(summary.get("stability_index", 0.0))
    recent_stability_index = float(summary.get("recent_stability_index", 0.0))
    stability_label = str(summary.get("stability_label", ""))
    overall_status = str(summary.get("overall_status", ""))
    status_reasons = summary.get("status_reasons", [])
    if not isinstance(status_reasons, list):
        status_reasons = []
    status_reason_primary = str(summary.get("status_reason_primary", ""))
    recommended_action = str(summary.get("recommended_action", ""))
    recommended_action_confidence = float(summary.get("recommended_action_confidence", 0.0))
    recommended_action_rationale = str(summary.get("recommended_action_rationale", ""))
    min_runs_for_ready = int(summary.get("min_runs_for_ready", 0))
    runs_needed_for_ready = int(summary.get("runs_needed_for_ready", 0))
    ready_progress = float(summary.get("ready_progress", 0.0))
    estimated_hours_to_ready = float(summary.get("estimated_hours_to_ready", 0.0))
    estimated_ready_timestamp_utc = str(summary.get("estimated_ready_timestamp_utc", ""))
    is_ready_for_next_phase = bool(summary.get("is_ready_for_next_phase", False))
    readiness_reason = str(summary.get("readiness_reason", ""))
    counts = summary.get("recommendation_counts", {})
    if not isinstance(counts, dict):
        counts = {}
    recent_counts = summary.get("recent_recommendation_counts", {})
    if not isinstance(recent_counts, dict):
        recent_counts = {}
    latest = summary.get("latest")
    if not isinstance(latest, dict):
        latest = {}
    latest_delta = summary.get("latest_delta")
    if not isinstance(latest_delta, dict):
        latest_delta = {}

    lines = [
        "Profile Matchup History Summary",
        "===============================",
        f"total_runs: {total}",
        f"reliable_rate: {reliable_rate:.3f}",
        f"recommendation_counts: {counts}",
        f"recommendation_switches: {switches}",
        f"recent_window: {recent_window}",
        f"recent_recommendation_switches: {recent_recommendation_switches}",
        f"recent_switch_rate: {recent_switch_rate:.6f}",
        f"top_recommendation_share: {top_recommendation_share:.6f}",
        f"recent_top_recommendation_share: {recent_top_recommendation_share:.6f}",
        f"distinct_recommended_profiles: {distinct_recommended_profiles}",
        f"recommendation_entropy: {recommendation_entropy:.6f}",
        f"recent_distinct_recommended_profiles: {recent_distinct_recommended_profiles}",
        f"recent_recommendation_entropy: {recent_recommendation_entropy:.6f}",
        f"recent_reliable_rate: {recent_reliable_rate:.3f}",
        f"recent_unreliable_rate: {recent_unreliable_rate:.3f}",
        f"avg_hours_between_runs: {avg_hours_between_runs:.6f}",
        f"median_hours_between_runs: {median_hours_between_runs:.6f}",
        f"latest_hours_since_previous: {latest_hours_since_previous:.6f}",
        f"recent_recommendation_counts: {recent_counts}",
        f"recent_avg_abs_seat_bias_delta: {recent_avg_abs_delta:.6f}",
        f"seat_bias_alert_threshold: {seat_bias_alert_threshold:.6f}",
        f"seat_bias_alert_count: {seat_bias_alert_count}",
        f"recent_seat_bias_alert_count: {recent_seat_bias_alert_count}",
        f"decisive_rate_alert_threshold: {decisive_rate_alert_threshold:.6f}",
        f"low_decisive_rate_alert_count: {low_decisive_rate_alert_count}",
        f"recent_low_decisive_rate_alert_count: {recent_low_decisive_rate_alert_count}",
        f"quality_alert_count: {quality_alert_count}",
        f"recent_quality_alert_count: {recent_quality_alert_count}",
        f"current_recommendation_streak_profile: {current_recommendation_streak_profile}",
        f"current_recommendation_streak_len: {current_recommendation_streak_len}",
        f"current_reliable_streak_len: {current_reliable_streak_len}",
        f"current_quality_alert_streak_len: {current_quality_alert_streak_len}",
        f"stability_index: {stability_index:.6f}",
        f"recent_stability_index: {recent_stability_index:.6f}",
        f"stability_label: {stability_label}",
        f"overall_status: {overall_status}",
        f"status_reason_primary: {status_reason_primary}",
        f"status_reasons: {status_reasons}",
        f"recommended_action: {recommended_action}",
        f"recommended_action_confidence: {recommended_action_confidence:.6f}",
        f"recommended_action_rationale: {recommended_action_rationale}",
        f"min_runs_for_ready: {min_runs_for_ready}",
        f"runs_needed_for_ready: {runs_needed_for_ready}",
        f"ready_progress: {ready_progress:.6f}",
        f"estimated_hours_to_ready: {estimated_hours_to_ready:.6f}",
        f"estimated_ready_timestamp_utc: {estimated_ready_timestamp_utc}",
        f"is_ready_for_next_phase: {is_ready_for_next_phase}",
        f"readiness_reason: {readiness_reason}",
    ]
    if latest:
        lines.extend(
            [
                "latest:",
                f"  timestamp_utc: {latest.get('timestamp_utc', '')}",
                f"  recommended_profile: {latest.get('recommended_profile', '')}",
                f"  recommendation_reason: {latest.get('recommendation_reason', '')}",
                f"  seat_bias_p1_minus_p2: {latest.get('seat_bias_p1_minus_p2', '')}",
                f"  source_json: {latest.get('source_json', '')}",
            ]
        )
    if latest_delta:
        lines.extend(
            [
                "latest_delta_vs_previous:",
                f"  recommendation_changed: {latest_delta.get('recommendation_changed', False)}",
                f"  reason_changed: {latest_delta.get('reason_changed', False)}",
                f"  reliability_changed: {latest_delta.get('reliability_changed', False)}",
                f"  seat_bias_delta_change: {latest_delta.get('seat_bias_delta_change', 0.0)}",
                f"  previous_timestamp_utc: {latest_delta.get('previous_timestamp_utc', '')}",
            ]
        )
    return "\n".join(lines)


def history_summary_to_csv_row(summary: dict[str, object]) -> dict[str, str]:
    import json

    latest = summary.get("latest")
    if not isinstance(latest, dict):
        latest = {}
    delta = summary.get("latest_delta")
    if not isinstance(delta, dict):
        delta = {}
    status_reasons = summary.get("status_reasons", [])
    if not isinstance(status_reasons, list):
        status_reasons = []
    return {
        "total_runs": str(int(summary.get("total_runs", 0))),
        "reliable_rate": str(float(summary.get("reliable_rate", 0.0))),
        "recommendation_switches": str(int(summary.get("recommendation_switches", 0))),
        "recent_window": str(int(summary.get("recent_window", 0))),
        "recent_recommendation_switches": str(int(summary.get("recent_recommendation_switches", 0))),
        "recent_switch_rate": str(float(summary.get("recent_switch_rate", 0.0))),
        "top_recommendation_share": str(float(summary.get("top_recommendation_share", 0.0))),
        "recent_top_recommendation_share": str(float(summary.get("recent_top_recommendation_share", 0.0))),
        "distinct_recommended_profiles": str(int(summary.get("distinct_recommended_profiles", 0))),
        "recommendation_entropy": str(float(summary.get("recommendation_entropy", 0.0))),
        "recent_distinct_recommended_profiles": str(int(summary.get("recent_distinct_recommended_profiles", 0))),
        "recent_recommendation_entropy": str(float(summary.get("recent_recommendation_entropy", 0.0))),
        "recent_reliable_rate": str(float(summary.get("recent_reliable_rate", 0.0))),
        "recent_unreliable_rate": str(float(summary.get("recent_unreliable_rate", 0.0))),
        "avg_hours_between_runs": str(float(summary.get("avg_hours_between_runs", 0.0))),
        "median_hours_between_runs": str(float(summary.get("median_hours_between_runs", 0.0))),
        "latest_hours_since_previous": str(float(summary.get("latest_hours_since_previous", 0.0))),
        "recent_avg_abs_seat_bias_delta": str(float(summary.get("recent_avg_abs_seat_bias_delta", 0.0))),
        "seat_bias_alert_threshold": str(float(summary.get("seat_bias_alert_threshold", 0.0))),
        "seat_bias_alert_count": str(int(summary.get("seat_bias_alert_count", 0))),
        "recent_seat_bias_alert_count": str(int(summary.get("recent_seat_bias_alert_count", 0))),
        "decisive_rate_alert_threshold": str(float(summary.get("decisive_rate_alert_threshold", 0.0))),
        "low_decisive_rate_alert_count": str(int(summary.get("low_decisive_rate_alert_count", 0))),
        "recent_low_decisive_rate_alert_count": str(int(summary.get("recent_low_decisive_rate_alert_count", 0))),
        "quality_alert_count": str(int(summary.get("quality_alert_count", 0))),
        "recent_quality_alert_count": str(int(summary.get("recent_quality_alert_count", 0))),
        "current_recommendation_streak_profile": str(summary.get("current_recommendation_streak_profile", "")),
        "current_recommendation_streak_len": str(int(summary.get("current_recommendation_streak_len", 0))),
        "current_reliable_streak_len": str(int(summary.get("current_reliable_streak_len", 0))),
        "current_quality_alert_streak_len": str(int(summary.get("current_quality_alert_streak_len", 0))),
        "stability_index": str(float(summary.get("stability_index", 0.0))),
        "recent_stability_index": str(float(summary.get("recent_stability_index", 0.0))),
        "stability_label": str(summary.get("stability_label", "")),
        "overall_status": str(summary.get("overall_status", "")),
        "status_reason_primary": str(summary.get("status_reason_primary", "")),
        "status_reasons_json": json.dumps(status_reasons, sort_keys=True),
        "recommended_action": str(summary.get("recommended_action", "")),
        "recommended_action_confidence": str(float(summary.get("recommended_action_confidence", 0.0))),
        "recommended_action_rationale": str(summary.get("recommended_action_rationale", "")),
        "min_runs_for_ready": str(int(summary.get("min_runs_for_ready", 0))),
        "runs_needed_for_ready": str(int(summary.get("runs_needed_for_ready", 0))),
        "ready_progress": str(float(summary.get("ready_progress", 0.0))),
        "estimated_hours_to_ready": str(float(summary.get("estimated_hours_to_ready", 0.0))),
        "estimated_ready_timestamp_utc": str(summary.get("estimated_ready_timestamp_utc", "")),
        "is_ready_for_next_phase": str(bool(summary.get("is_ready_for_next_phase", False))),
        "readiness_reason": str(summary.get("readiness_reason", "")),
        "recommendation_counts_json": json.dumps(summary.get("recommendation_counts", {}), sort_keys=True),
        "recent_recommendation_counts_json": json.dumps(summary.get("recent_recommendation_counts", {}), sort_keys=True),
        "latest_timestamp_utc": str(latest.get("timestamp_utc", "")),
        "latest_recommended_profile": str(latest.get("recommended_profile", "")),
        "latest_recommendation_reason": str(latest.get("recommendation_reason", "")),
        "latest_seat_bias_p1_minus_p2": str(latest.get("seat_bias_p1_minus_p2", "")),
        "latest_source_json": str(latest.get("source_json", "")),
        "latest_delta_recommendation_changed": str(bool(delta.get("recommendation_changed", False))),
        "latest_delta_reason_changed": str(bool(delta.get("reason_changed", False))),
        "latest_delta_reliability_changed": str(bool(delta.get("reliability_changed", False))),
        "latest_delta_seat_bias_delta_change": str(float(delta.get("seat_bias_delta_change", 0.0))),
        "latest_delta_previous_timestamp_utc": str(delta.get("previous_timestamp_utc", "")),
    }


def history_recent_runs_to_csv_rows(rows: list[dict[str, str]], *, recent_window: int = 10) -> list[dict[str, str]]:
    window = max(1, int(recent_window))
    recent = rows[-window:]
    out: list[dict[str, str]] = []
    for row in recent:
        out.append(
            {
                "timestamp_utc": str(row.get("timestamp_utc", "")),
                "recommended_profile": str(row.get("recommended_profile", "")),
                "recommendation_reason": str(row.get("recommendation_reason", "")),
                "recommendation_reliable": str(row.get("recommendation_reliable", "")),
                "seat_bias_p1_minus_p2": str(row.get("seat_bias_p1_minus_p2", "")),
                "match_quality_decisive_rate": str(row.get("match_quality_decisive_rate", "")),
                "match_quality_draw_rate": str(row.get("match_quality_draw_rate", "")),
                "match_quality_low_decisive_rate_alert": str(row.get("match_quality_low_decisive_rate_alert", "")),
                "profiles": str(row.get("profiles", "")),
                "games_per_matchup": str(row.get("games_per_matchup", "")),
                "max_actions": str(row.get("max_actions", "")),
                "shuffle_decks": str(row.get("shuffle_decks", "")),
                "seat_balanced": str(row.get("seat_balanced", "")),
                "seed": str(row.get("seed", "")),
                "source_json": str(row.get("source_json", "")),
            }
        )
    return out


def rank_profiles(summary: dict[str, dict[str, float | int]]) -> list[str]:
    ordered = sorted(
        summary.items(),
        key=lambda kv: (
            float(kv[1].get("points_per_game", 0.0)),
            float(kv[1].get("win_rate", 0.0)),
            float(kv[1].get("wins", 0)),
        ),
        reverse=True,
    )
    return [profile for profile, _ in ordered]


def recommend_profile(
    summary: dict[str, dict[str, float | int]],
    *,
    min_games_per_profile: int = 0,
) -> dict[str, object]:
    ranking = rank_profiles(summary)
    if not ranking:
        return {
            "recommended_profile": None,
            "reason": "no_profiles",
            "clear_edge": False,
            "reliable": False,
        }

    if min_games_per_profile > 0:
        lowest_games = min(int(summary.get(p, {}).get("games", 0)) for p in ranking)
        if lowest_games < min_games_per_profile:
            return {
                "recommended_profile": ranking[0],
                "reason": "insufficient_sample",
                "clear_edge": False,
                "reliable": False,
                "min_games_per_profile_required": min_games_per_profile,
                "min_games_observed": lowest_games,
                "ranking": ranking,
            }

    best = ranking[0]
    if len(ranking) == 1:
        return {
            "recommended_profile": best,
            "reason": "single_profile",
            "clear_edge": True,
            "reliable": True,
            "ranking": ranking,
        }

    top = summary.get(best, {})
    second = summary.get(ranking[1], {})
    top_ppg = float(top.get("points_per_game", 0.0))
    second_ppg = float(second.get("points_per_game", 0.0))
    top_wr = float(top.get("win_rate", 0.0))
    second_wr = float(second.get("win_rate", 0.0))
    clear_edge = (top_ppg > second_ppg) or ((top_ppg == second_ppg) and (top_wr > second_wr))
    reason = "dominant_points_per_game" if top_ppg > second_ppg else ("higher_win_rate_tiebreak" if top_wr > second_wr else "tied_or_inconclusive")
    return {
        "recommended_profile": best,
        "reason": reason,
        "clear_edge": bool(clear_edge),
        "reliable": True,
        "ranking": ranking,
    }
