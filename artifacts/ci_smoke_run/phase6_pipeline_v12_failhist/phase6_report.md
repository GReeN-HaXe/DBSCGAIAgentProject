# Phase 6 Run Report

## Match Summary

| Field | Value |
|---|---|
| winner_id | None |
| total_actions | 1 |
| human_player_id | 1 |
| ai_profile | balanced |
| final_turn_number | 1 |
| final_phase | main |
| checkpoint_count | 8 |
| effect_resolution_count | 0 |
| effect_unresolved_count | 0 |

## Setup

| Key | Value |
|---|---|
| deck_source | synthetic |
| first_player | 1 |
| mode | fresh |
| p1_deck_size | 60 |
| p1_leader_id | 1 |
| p2_deck_size | 60 |
| p2_leader_id | 2 |
| seed | 53 |
| shuffle_decks | False |

## Gates

- play_ok: `True`
- replay_ok: `True`
- replay_trace_hash: `99a6ae0ea845706c2aa39e70c1cf7df6efb4a7d2b2ed4f9d553e1f75dcda68cd`

## Checkpoint Tail

- pregame_leaders_placed
- pregame_starting_player_decided
- pregame_setup_complete
- charge_phase_begin
- charge_phase_after_untap
- charge_phase_after_draw_skipped
- charge_phase_charge_window
- charge_phase_end

## History Trend

| Field | Value |
|---|---|
| total_runs | 1 |
| recent_window | 1 |
| pass_rate_total | 1.0 |
| pass_rate_recent | 1.0 |
| determinism_checks_recent | 0 |
| determinism_pass_rate_recent | 0.0 |
| overall_status | healthy |
| is_ready | True |
| recommended_action | continue_phase6_or_move_next_phase |

## Pipeline Timings

- total_seconds: `0.8799684000005072`
- slowest_stage: `play_vs_ai`
- slowest_seconds: `0.3349255999964953`

| Stage | Duration (s) |
|---|---|
| play_vs_ai | 0.3349255999964953 |
| replay_human_vs_ai | 0.28069410000171047 |
| check_phase6_artifacts | 0.2643487000023015 |

## Timing Regression

| Field | Value |
|---|---|
| has_baseline | False |
| regressed | False |
| current_total_seconds |  |
| baseline_total_seconds |  |
| ratio_current_over_baseline |  |
| max_total_seconds_regression_ratio |  |
| reason |  |

## Timing History Trend

| Field | Value |
|---|---|
| total_runs | 1 |
| recent_window | 1 |
| avg_total_seconds_recent | 0.879968 |
| max_total_seconds_recent | 0.879968 |
| regression_rate_recent | 0.0 |
| latest_total_seconds | 0.879968 |
