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
    merge_matchup_rows,
    matchup_rows_to_dict,
    profile_summary_to_csv_rows,
    seat_bias_to_csv_rows,
    recommend_profile,
    run_profile_matchup_matrix,
    summarize_profile_strength,
)
from src.db import SQLiteCardRepository
from src.game import RulesEngine


def _build_deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _make_state_factory(*, shuffle_decks: bool, seed: int | None, first_player: int):
    game_index = 0

    def _state_factory(engine: RulesEngine):
        nonlocal game_index
        game_seed = None if seed is None else (seed + game_index)
        game_index += 1
        return engine.initialize_game(
            p1_leader_card_id=1,
            p1_deck_card_ids=_build_deck(1000),
            p2_leader_card_id=2,
            p2_deck_card_ids=_build_deck(2000),
            first_player=first_player,
            shuffle_decks=shuffle_decks,
            random_seed=game_seed,
        )

    return _state_factory


def _default_csv_path(output_json: Path, suffix: str) -> Path:
    return output_json.with_name(f"{output_json.stem}_{suffix}.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run profile-vs-profile AI matchup matrix.")
    parser.add_argument("--profiles", type=str, default="balanced,aggressive,control", help="Comma-separated profile names.")
    parser.add_argument("--games-per-matchup", type=int, default=2, help="Number of games for each ordered profile pair.")
    parser.add_argument("--max-actions", type=int, default=120, help="Maximum actions before ending a game.")
    parser.add_argument("--effect-catalog", type=Path, default=Path("dbdatabase/effect_catalog.json"), help="Path to effect catalog JSON.")
    parser.add_argument("--db-path", type=Path, default=Path("dbdatabase/dbs_masters.db"), help="Path to SQLite card database.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/profile_matchups.json"), help="Output JSON path.")
    parser.add_argument("--shuffle-decks", action="store_true", help="Shuffle decks at game start.")
    parser.add_argument("--seat-balanced", action="store_true", help="Run each matchup with first_player=1 and first_player=2, then merge.")
    parser.add_argument("--seed", type=int, default=None, help="Optional base RNG seed; if set, each game uses seed+game_index.")
    parser.add_argument(
        "--min-games-for-recommendation",
        type=int,
        default=6,
        help="Minimum games each profile must have before recommendation is considered reliable.",
    )
    parser.add_argument(
        "--decisive-rate-alert-threshold",
        type=float,
        default=0.30,
        help="Alert threshold for decisive-rate quality (below this means draw-heavy/inconclusive simulations).",
    )
    parser.add_argument("--rows-csv", type=Path, default=None, help="Optional rows CSV path. Defaults next to --output.")
    parser.add_argument("--summary-csv", type=Path, default=None, help="Optional profile summary CSV path. Defaults next to --output.")
    parser.add_argument("--h2h-csv", type=Path, default=None, help="Optional head-to-head CSV path. Defaults next to --output.")
    parser.add_argument("--seat-bias-csv", type=Path, default=None, help="Optional seat-bias by-matchup CSV path. Defaults next to --output.")
    parser.add_argument("--overview-csv", type=Path, default=None, help="Optional one-row overview CSV path. Defaults next to --output.")
    parser.add_argument("--history-csv", type=Path, default=None, help="Optional append-only history CSV path.")
    args = parser.parse_args()

    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    repo = SQLiteCardRepository(args.db_path) if args.db_path.exists() else None
    effect_catalog = args.effect_catalog if args.effect_catalog.exists() else None

    def _engine_factory() -> RulesEngine:
        return RulesEngine(card_repository=repo, effect_rules_path=effect_catalog)

    if args.seat_balanced:
        rows_fp1 = run_profile_matchup_matrix(
            engine_factory=_engine_factory,
            state_factory=_make_state_factory(shuffle_decks=bool(args.shuffle_decks), seed=args.seed, first_player=1),
            profiles=profiles,
            games_per_matchup=max(1, args.games_per_matchup),
            max_actions=max(1, args.max_actions),
        )
        seed2 = None if args.seed is None else (int(args.seed) + 1_000_000)
        rows_fp2 = run_profile_matchup_matrix(
            engine_factory=_engine_factory,
            state_factory=_make_state_factory(shuffle_decks=bool(args.shuffle_decks), seed=seed2, first_player=2),
            profiles=profiles,
            games_per_matchup=max(1, args.games_per_matchup),
            max_actions=max(1, args.max_actions),
        )
        rows = merge_matchup_rows([*rows_fp1, *rows_fp2])
    else:
        rows = run_profile_matchup_matrix(
            engine_factory=_engine_factory,
            state_factory=_make_state_factory(shuffle_decks=bool(args.shuffle_decks), seed=args.seed, first_player=1),
            profiles=profiles,
            games_per_matchup=max(1, args.games_per_matchup),
            max_actions=max(1, args.max_actions),
        )
    summary = summarize_profile_strength(rows)
    matrix = build_head_to_head_matrix(rows)
    seat_bias = compute_seat_bias(rows)
    match_quality = compute_match_quality(rows, decisive_rate_alert_threshold=float(args.decisive_rate_alert_threshold))
    recommendation = recommend_profile(summary, min_games_per_profile=max(0, args.min_games_for_recommendation))
    payload = {
        "profiles": profiles,
        "games_per_matchup": max(1, args.games_per_matchup),
        "max_actions": max(1, args.max_actions),
        "shuffle_decks": bool(args.shuffle_decks),
        "seat_balanced": bool(args.seat_balanced),
        "seed": args.seed,
        "min_games_for_recommendation": max(0, args.min_games_for_recommendation),
        "decisive_rate_alert_threshold": float(args.decisive_rate_alert_threshold),
        "rows": matchup_rows_to_dict(rows),
        "profile_summary": summary,
        "seat_bias": seat_bias,
        "match_quality": match_quality,
        "recommendation": recommendation,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote: {args.output}")
    rows_csv = args.rows_csv or _default_csv_path(args.output, "rows")
    summary_csv = args.summary_csv or _default_csv_path(args.output, "summary")
    h2h_csv = args.h2h_csv or _default_csv_path(args.output, "h2h")
    seat_bias_csv = args.seat_bias_csv or _default_csv_path(args.output, "seat_bias")
    overview_csv = args.overview_csv or _default_csv_path(args.output, "overview")

    rows_csv.parent.mkdir(parents=True, exist_ok=True)
    with rows_csv.open("w", encoding="utf-8", newline="") as fh:
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
            for row in rows
        )
    print(f"wrote: {rows_csv}")

    summary_rows = profile_summary_to_csv_rows(summary)
    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    with summary_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["profile", "points_per_game", "win_rate", "wins", "losses", "draws", "games", "points"],
        )
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"wrote: {summary_csv}")

    h2h_rows = head_to_head_to_csv_rows(matrix)
    h2h_csv.parent.mkdir(parents=True, exist_ok=True)
    with h2h_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["p1_profile", "p2_profile", "p1_win_rate"],
        )
        writer.writeheader()
        writer.writerows(h2h_rows)
    print(f"wrote: {h2h_csv}")

    seat_bias_rows = seat_bias_to_csv_rows(seat_bias)
    seat_bias_csv.parent.mkdir(parents=True, exist_ok=True)
    with seat_bias_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["p1_profile", "p2_profile", "games", "p1_win_rate", "p2_win_rate", "draw_rate"],
        )
        writer.writeheader()
        writer.writerows(seat_bias_rows)
    print(f"wrote: {seat_bias_csv}")

    overview_row = build_overview_csv_row(
        profiles=profiles,
        games_per_matchup=max(1, args.games_per_matchup),
        max_actions=max(1, args.max_actions),
        shuffle_decks=bool(args.shuffle_decks),
        seat_balanced=bool(args.seat_balanced),
        seed=args.seed,
        min_games_for_recommendation=max(0, args.min_games_for_recommendation),
        recommendation=recommendation,
        seat_bias=seat_bias,
        match_quality=match_quality,
    )
    overview_csv.parent.mkdir(parents=True, exist_ok=True)
    with overview_csv.open("w", encoding="utf-8", newline="") as fh:
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
        writer.writerow(overview_row)
    print(f"wrote: {overview_csv}")

    if args.history_csv is not None:
        history_row = build_history_csv_row(
            overview_row,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            source_json=str(args.output),
        )
        args.history_csv.parent.mkdir(parents=True, exist_ok=True)
        file_exists = args.history_csv.exists()
        with args.history_csv.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(history_row.keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(history_row)
        print(f"appended: {args.history_csv}")

    print(f"rows: {len(rows)}")
    print(f"seat_bias_p1_minus_p2: {seat_bias.get('p1_minus_p2')}")
    print(f"decisive_rate: {match_quality.get('decisive_rate')}")
    print(f"low_decisive_rate_alert: {match_quality.get('low_decisive_rate_alert')}")
    print(f"recommended_profile: {recommendation.get('recommended_profile')}")
    print(f"recommendation_reason: {recommendation.get('reason')}")


if __name__ == "__main__":
    main()
