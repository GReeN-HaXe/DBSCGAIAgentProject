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
| seed | 101 |
| shuffle_decks | False |

## Gates

- play_ok: `True`
- replay_ok: `True`
- replay_trace_hash: `596ea13e15bd46afb5b4d45c4a6541ba91a479a32d80afa9a6081d5a4cb5c914`

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
| determinism_checks_recent | 1 |
| determinism_pass_rate_recent | 1.0 |
| overall_status | healthy |
| is_ready | True |
| recommended_action | continue_phase6_or_move_next_phase |

## Pipeline Timings

- total_seconds: `1.2248760000002221`
- slowest_stage: `play_vs_ai`
- slowest_seconds: `0.3478073000005679`

| Stage | Duration (s) |
|---|---|
| play_vs_ai | 0.3478073000005679 |
| replay_human_vs_ai | 0.2879769999999553 |
| replay_human_vs_ai_second | 0.2989448000007542 |
| check_phase6_artifacts | 0.2901468999989447 |

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
| avg_total_seconds_recent | 1.224876 |
| max_total_seconds_recent | 1.224876 |
| regression_rate_recent | 0.0 |
| latest_total_seconds | 1.224876 |
