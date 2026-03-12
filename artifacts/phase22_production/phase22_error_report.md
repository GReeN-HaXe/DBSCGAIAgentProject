# Phase 22 Error Analysis

- dataset_path: `C:\Users\PC\Desktop\dbsAIAgent\artifacts\phase22_benchmark_dataset_v3.json`
- split: `validation`
- example_count: `106`
- top1_accuracy: `0.9339622641509434`
- top_k_accuracy: `{'1': 0.9339622641509434, '3': 1.0, '5': 1.0}`
- error_count: `7`

## Top Confusions

- `attack_leader_with_leader->attack_leader_with_battle`: `5`
- `attack_leader_with_battle->attack_leader_with_leader`: `2`

## Per Source

- `artifacts\phase22_normalized\ai_match_trace_026_review.json`: top1=`1.0` errors=`0` examples=`6`
- `artifacts\phase22_normalized\ai_match_trace_027_review.json`: top1=`1.0` errors=`0` examples=`6`
- `artifacts\phase22_normalized\ai_match_trace_028_review.json`: top1=`1.0` errors=`0` examples=`6`
- `artifacts\phase22_normalized\ai_match_trace_029_review.json`: top1=`1.0` errors=`0` examples=`2`
- `artifacts\phase22_normalized\ai_match_trace_030_review.json`: top1=`0.75` errors=`1` examples=`4`
- `artifacts\phase22_normalized\ai_match_trace_031_review.json`: top1=`0.8333333333333334` errors=`1` examples=`6`
- `artifacts\phase22_normalized\ai_match_trace_032_review.json`: top1=`1.0` errors=`0` examples=`5`
- `artifacts\phase22_normalized\ai_match_trace_033_review.json`: top1=`0.8333333333333334` errors=`1` examples=`6`
- `artifacts\phase22_normalized\ai_match_trace_034_review.json`: top1=`1.0` errors=`0` examples=`5`
- `artifacts\phase22_normalized\ai_match_trace_035_review.json`: top1=`1.0` errors=`0` examples=`4`
- `artifacts\phase22_normalized\ai_match_trace_036_review.json`: top1=`0.8333333333333334` errors=`1` examples=`6`
- `artifacts\phase22_normalized\ai_match_trace_037_review.json`: top1=`1.0` errors=`0` examples=`6`
- `artifacts\phase22_normalized\ai_match_trace_038_review.json`: top1=`1.0` errors=`0` examples=`5`
- `artifacts\phase22_normalized\ai_match_trace_039_review.json`: top1=`0.8` errors=`1` examples=`5`
- `artifacts\phase22_normalized\ai_match_trace_040_review.json`: top1=`1.0` errors=`0` examples=`6`
- `artifacts\phase22_normalized\ai_match_trace_041_review.json`: top1=`0.8` errors=`1` examples=`5`
- `artifacts\phase22_normalized\ai_match_trace_042_review.json`: top1=`1.0` errors=`0` examples=`5`
- `artifacts\phase22_normalized\ai_match_trace_043_review.json`: top1=`1.0` errors=`0` examples=`6`
- `artifacts\phase22_normalized\ai_match_trace_044_review.json`: top1=`1.0` errors=`0` examples=`6`
- `artifacts\phase22_normalized\ai_match_trace_045_review.json`: top1=`0.8333333333333334` errors=`1` examples=`6`

## Per Decision Class

- `attack_leader_with_battle`: top1=`0.9375` errors=`2` examples=`32`
- `attack_leader_with_leader`: top1=`0.2857142857142857` errors=`5` examples=`7`
- `charge_lategame`: top1=`1.0` errors=`0` examples=`16`
- `charge_opening`: top1=`1.0` errors=`0` examples=`20`
- `end_turn_after_development`: top1=`1.0` errors=`0` examples=`11`
- `play_board_extension`: top1=`1.0` errors=`0` examples=`13`
- `play_board_setup`: top1=`1.0` errors=`0` examples=`2`
- `play_pressure`: top1=`1.0` errors=`0` examples=`5`

## Sample Errors

- `artifacts\phase22_normalized\ai_match_trace_030_review.json` idx=`38` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=9629|target_card=card_id=9623|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\ai_match_trace_031_review.json` idx=`48` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=9629|target_card=card_id=9623|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\ai_match_trace_033_review.json` idx=`30` `attack_leader_with_battle` -> `attack_leader_with_leader` action=`declare_attack|attacker_card=card_id=1536|target_card=card_id=9623|attacker_zone=battle|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\ai_match_trace_036_review.json` idx=`48` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=9623|target_card=card_id=9629|attacker_zone=leader|target_zone=leader|target_player=1`
- `artifacts\phase22_normalized\ai_match_trace_039_review.json` idx=`39` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=9623|target_card=card_id=9629|attacker_zone=leader|target_zone=leader|target_player=1`
- `artifacts\phase22_normalized\ai_match_trace_041_review.json` idx=`48` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=9629|target_card=card_id=9623|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\ai_match_trace_045_review.json` idx=`30` `attack_leader_with_battle` -> `attack_leader_with_leader` action=`declare_attack|attacker_card=card_id=7236|target_card=card_id=9623|attacker_zone=battle|target_zone=leader|target_player=2`
