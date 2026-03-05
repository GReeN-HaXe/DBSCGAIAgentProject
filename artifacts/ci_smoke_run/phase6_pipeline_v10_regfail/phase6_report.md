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
| seed | 41 |
| shuffle_decks | False |

## Gates

- play_ok: `True`
- replay_ok: `True`
- replay_trace_hash: `304347837bc38db4f7f80b319009027815f32d55554fe792646cdcb311cab49d`

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

- total_seconds: `0.8819121000015002`
- slowest_stage: `play_vs_ai`
- slowest_seconds: `0.3182507000019541`

| Stage | Duration (s) |
|---|---|
| play_vs_ai | 0.3182507000019541 |
| replay_human_vs_ai | 0.2876883999997517 |
| check_phase6_artifacts | 0.2759729999997944 |

## Timing Regression

| Field | Value |
|---|---|
| has_baseline | True |
| regressed | True |
| current_total_seconds | 0.8819121000015002 |
| baseline_total_seconds | 0.0001 |
| ratio_current_over_baseline | 8819.121000015002 |
| max_total_seconds_regression_ratio | 0.01 |
| reason | timing_regression_detected current_total=0.881912 baseline_total=0.000100 ratio=8819.121000 threshold=1.010000 |
