# Phase 22 Error Analysis

- dataset_path: `C:\Users\PC\Desktop\dbsAIAgent\artifacts\phase22_benchmark_batch\gogeta_vs_krillin.json`
- split: `validation`
- example_count: `78`
- top1_accuracy: `0.8717948717948718`
- top_k_accuracy: `{'1': 0.8717948717948718, '3': 1.0, '5': 1.0}`
- error_count: `10`

## Top Confusions

- `attack_leader_with_leader->attack_leader_with_battle`: `7`
- `play_board_extension->play_pressure`: `2`
- `end_turn_after_development->end_turn_reset`: `1`

## Per Source

- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_001_review.json`: top1=`1.0` errors=`0` examples=`2`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_002_review.json`: top1=`1.0` errors=`0` examples=`2`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_003_review.json`: top1=`1.0` errors=`0` examples=`6`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_004_review.json`: top1=`0.5` errors=`1` examples=`2`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_005_review.json`: top1=`1.0` errors=`0` examples=`4`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_006_review.json`: top1=`1.0` errors=`0` examples=`2`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_007_review.json`: top1=`1.0` errors=`0` examples=`4`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_008_review.json`: top1=`1.0` errors=`0` examples=`4`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_009_review.json`: top1=`1.0` errors=`0` examples=`4`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_010_review.json`: top1=`0.75` errors=`1` examples=`4`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_011_review.json`: top1=`1.0` errors=`0` examples=`6`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_012_review.json`: top1=`1.0` errors=`0` examples=`4`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_013_review.json`: top1=`0.6666666666666666` errors=`2` examples=`6`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_014_review.json`: top1=`1.0` errors=`0` examples=`2`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_015_review.json`: top1=`1.0` errors=`0` examples=`8`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_016_review.json`: top1=`0.5` errors=`1` examples=`2`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_017_review.json`: top1=`0.8333333333333334` errors=`1` examples=`6`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_018_review.json`: top1=`0.8` errors=`1` examples=`5`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_019_review.json`: top1=`0.3333333333333333` errors=`2` examples=`3`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_020_review.json`: top1=`0.5` errors=`1` examples=`2`

## Per Decision Class

- `attack_leader_with_battle`: top1=`1.0` errors=`0` examples=`28`
- `attack_leader_with_leader`: top1=`0.125` errors=`7` examples=`8`
- `charge_lategame`: top1=`1.0` errors=`0` examples=`8`
- `charge_opening`: top1=`1.0` errors=`0` examples=`20`
- `end_turn_after_development`: top1=`0.8333333333333334` errors=`1` examples=`6`
- `play_board_extension`: top1=`0.6666666666666666` errors=`2` examples=`6`
- `play_pressure`: top1=`1.0` errors=`0` examples=`2`

## Sample Errors

- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_004_review.json` idx=`30` `end_turn_after_development` -> `end_turn_reset` action=`end_turn`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_010_review.json` idx=`38` `play_board_extension` -> `play_pressure` action=`play_card_from_hand|card=card_id=9638`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_013_review.json` idx=`38` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=7838|target_card=card_id=9623|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_013_review.json` idx=`48` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=9623|target_card=card_id=7838|attacker_zone=leader|target_zone=leader|target_player=1`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_016_review.json` idx=`30` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=7838|target_card=card_id=9623|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_017_review.json` idx=`38` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=7838|target_card=card_id=9623|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_018_review.json` idx=`48` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=7838|target_card=card_id=9623|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_019_review.json` idx=`30` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=7838|target_card=card_id=9623|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_019_review.json` idx=`38` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=9623|target_card=card_id=7838|attacker_zone=leader|target_zone=leader|target_player=1`
- `artifacts\phase22_normalized\gogeta_vs_krillin\ai_match_trace_020_review.json` idx=`30` `play_board_extension` -> `play_pressure` action=`play_card_from_hand|card=card_id=8630`
