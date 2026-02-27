from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    build_head_to_head_matrix,
    build_history_csv_row,
    build_overview_csv_row,
    compute_match_quality,
    compute_seat_bias,
    head_to_head_to_csv_rows,
    format_head_to_head,
    format_profile_ranking,
    matchup_rows_from_dict,
    profile_summary_to_csv_rows,
    seat_bias_to_csv_rows,
    recommend_profile,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize profile matchup JSON as readable ranking tables.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("artifacts/profile_matchups.json"),
        help="Path to profile matchup JSON.",
    )
    parser.add_argument(
        "--rows-csv",
        type=Path,
        default=None,
        help="Optional path to write matchup rows CSV.",
    )
    parser.add_argument(
        "--summary-csv",
        type=Path,
        default=None,
        help="Optional path to write profile summary CSV.",
    )
    parser.add_argument(
        "--h2h-csv",
        type=Path,
        default=None,
        help="Optional path to write head-to-head CSV.",
    )
    parser.add_argument(
        "--seat-bias-csv",
        type=Path,
        default=None,
        help="Optional path to write seat-bias-by-matchup CSV.",
    )
    parser.add_argument(
        "--overview-csv",
        type=Path,
        default=None,
        help="Optional path to write one-row overview CSV.",
    )
    parser.add_argument(
        "--history-csv",
        type=Path,
        default=None,
        help="Optional path to append one-row run history CSV.",
    )
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    summary = payload.get("profile_summary", {})
    rows = payload.get("rows", [])
    parsed_rows = matchup_rows_from_dict(rows if isinstance(rows, list) else [])
    matrix = build_head_to_head_matrix(parsed_rows)
    if not isinstance(summary, dict):
        summary = {}
    min_games = payload.get("min_games_for_recommendation", 0)
    try:
        min_games_int = int(min_games)
    except (TypeError, ValueError):
        min_games_int = 0
    recommendation = payload.get("recommendation")
    if not isinstance(recommendation, dict):
        recommendation = recommend_profile(summary, min_games_per_profile=max(0, min_games_int))
    seat_bias = payload.get("seat_bias")
    if not isinstance(seat_bias, dict):
        seat_bias = compute_seat_bias(parsed_rows)
    match_quality = payload.get("match_quality")
    if not isinstance(match_quality, dict):
        thr = payload.get("decisive_rate_alert_threshold", 0.30)
        try:
            thr_f = float(thr)
        except (TypeError, ValueError):
            thr_f = 0.30
        match_quality = compute_match_quality(parsed_rows, decisive_rate_alert_threshold=thr_f)
    print(format_profile_ranking(summary))
    print("")
    print(
        "Seat Bias:",
        f"p1_win_rate={float(seat_bias.get('p1_win_rate', 0.0)):.3f}",
        f"p2_win_rate={float(seat_bias.get('p2_win_rate', 0.0)):.3f}",
        f"draw_rate={float(seat_bias.get('draw_rate', 0.0)):.3f}",
        f"delta={float(seat_bias.get('p1_minus_p2', 0.0)):.3f}",
    )
    print("")
    print(
        "Recommendation:",
        recommendation.get("recommended_profile"),
        f"(reason={recommendation.get('reason')}, clear_edge={recommendation.get('clear_edge')})",
    )
    print("")
    print(
        "Match Quality:",
        f"decisive_rate={float(match_quality.get('decisive_rate', 0.0)):.3f}",
        f"draw_rate={float(match_quality.get('draw_rate', 0.0)):.3f}",
        f"low_decisive_rate_alert={bool(match_quality.get('low_decisive_rate_alert', False))}",
    )
    print("")
    print(format_head_to_head(matrix))
    if args.rows_csv is not None:
        args.rows_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.rows_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "p1_profile",
                    "p2_profile",
                    "games",
                    "p1_wins",
                    "p2_wins",
                    "draws",
                    "avg_actions",
                    "avg_turn",
                ],
            )
            writer.writeheader()
            writer.writerows(
                {
                    "p1_profile": row.p1_profile,
                    "p2_profile": row.p2_profile,
                    "games": row.games,
                    "p1_wins": row.p1_wins,
                    "p2_wins": row.p2_wins,
                    "draws": row.draws,
                    "avg_actions": row.avg_actions,
                    "avg_turn": row.avg_turn,
                }
                for row in parsed_rows
            )
        print(f"wrote: {args.rows_csv}")
    if args.summary_csv is not None:
        rows_out = profile_summary_to_csv_rows(summary)
        args.summary_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.summary_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["profile", "points_per_game", "win_rate", "wins", "losses", "draws", "games", "points"],
            )
            writer.writeheader()
            writer.writerows(rows_out)
        print(f"wrote: {args.summary_csv}")
    if args.h2h_csv is not None:
        rows_out = head_to_head_to_csv_rows(matrix)
        args.h2h_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.h2h_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["p1_profile", "p2_profile", "p1_win_rate"],
            )
            writer.writeheader()
            writer.writerows(rows_out)
        print(f"wrote: {args.h2h_csv}")
    if args.seat_bias_csv is not None:
        rows_out = seat_bias_to_csv_rows(seat_bias)
        args.seat_bias_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.seat_bias_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["p1_profile", "p2_profile", "games", "p1_win_rate", "p2_win_rate", "draw_rate"],
            )
            writer.writeheader()
            writer.writerows(rows_out)
        print(f"wrote: {args.seat_bias_csv}")
    if args.overview_csv is not None:
        profiles = payload.get("profiles", [])
        if not isinstance(profiles, list):
            profiles = []
        games_per_matchup = payload.get("games_per_matchup", 0)
        max_actions = payload.get("max_actions", 0)
        shuffle_decks = bool(payload.get("shuffle_decks", False))
        seat_balanced = bool(payload.get("seat_balanced", False))
        seed = payload.get("seed")
        try:
            seed_int = int(seed) if seed is not None else None
        except (TypeError, ValueError):
            seed_int = None
        overview = build_overview_csv_row(
            profiles=[str(p) for p in profiles],
            games_per_matchup=int(games_per_matchup),
            max_actions=int(max_actions),
            shuffle_decks=shuffle_decks,
            seat_balanced=seat_balanced,
            seed=seed_int,
            min_games_for_recommendation=max(0, min_games_int),
            recommendation=recommendation,
            seat_bias=seat_bias,
            match_quality=match_quality,
        )
        args.overview_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.overview_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "profiles",
                    "games_per_matchup",
                    "max_actions",
                    "shuffle_decks",
                    "seat_balanced",
                    "seed",
                    "min_games_for_recommendation",
                    "recommended_profile",
                    "recommendation_reason",
                    "recommendation_reliable",
                    "recommendation_clear_edge",
                    "seat_bias_games",
                    "seat_bias_p1_win_rate",
                    "seat_bias_p2_win_rate",
                    "seat_bias_draw_rate",
                    "seat_bias_p1_minus_p2",
                    "match_quality_draw_rate",
                    "match_quality_decisive_rate",
                    "match_quality_low_decisive_rate_alert",
                ],
            )
            writer.writeheader()
            writer.writerow(overview)
        print(f"wrote: {args.overview_csv}")
    else:
        profiles = payload.get("profiles", [])
        if not isinstance(profiles, list):
            profiles = []
        games_per_matchup = payload.get("games_per_matchup", 0)
        max_actions = payload.get("max_actions", 0)
        shuffle_decks = bool(payload.get("shuffle_decks", False))
        seat_balanced = bool(payload.get("seat_balanced", False))
        seed = payload.get("seed")
        try:
            seed_int = int(seed) if seed is not None else None
        except (TypeError, ValueError):
            seed_int = None
        overview = build_overview_csv_row(
            profiles=[str(p) for p in profiles],
            games_per_matchup=int(games_per_matchup),
            max_actions=int(max_actions),
            shuffle_decks=shuffle_decks,
            seat_balanced=seat_balanced,
            seed=seed_int,
            min_games_for_recommendation=max(0, min_games_int),
            recommendation=recommendation,
            seat_bias=seat_bias,
            match_quality=match_quality,
        )
    if args.history_csv is not None:
        history_row = build_history_csv_row(
            overview,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            source_json=str(args.input),
        )
        args.history_csv.parent.mkdir(parents=True, exist_ok=True)
        file_exists = args.history_csv.exists()
        with args.history_csv.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(history_row.keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(history_row)
        print(f"appended: {args.history_csv}")


if __name__ == "__main__":
    main()
