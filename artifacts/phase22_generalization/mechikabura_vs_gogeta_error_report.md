# Phase 22 Error Analysis

- dataset_path: `C:\Users\PC\Desktop\dbsAIAgent\artifacts\phase22_benchmark_batch\mechikabura_vs_gogeta.json`
- split: `validation`
- example_count: `79`
- top1_accuracy: `0.8227848101265823`
- top_k_accuracy: `{'1': 0.8227848101265823, '3': 1.0, '5': 1.0}`
- error_count: `14`

## Top Confusions

- `attack_leader_with_leader->attack_leader_with_battle`: `10`
- `play_board_extension->play_pressure`: `4`

## Per Source

- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_001_review.json`: top1=`0.5` errors=`2` examples=`4`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_002_review.json`: top1=`0.75` errors=`1` examples=`4`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_003_review.json`: top1=`0.8` errors=`1` examples=`5`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_004_review.json`: top1=`0.6666666666666666` errors=`2` examples=`6`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_005_review.json`: top1=`0.75` errors=`1` examples=`4`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_006_review.json`: top1=`1.0` errors=`0` examples=`4`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_007_review.json`: top1=`1.0` errors=`0` examples=`4`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_008_review.json`: top1=`1.0` errors=`0` examples=`4`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_009_review.json`: top1=`1.0` errors=`0` examples=`2`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_010_review.json`: top1=`1.0` errors=`0` examples=`4`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_011_review.json`: top1=`0.5` errors=`1` examples=`2`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_012_review.json`: top1=`1.0` errors=`0` examples=`4`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_013_review.json`: top1=`1.0` errors=`0` examples=`5`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_014_review.json`: top1=`1.0` errors=`0` examples=`2`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_015_review.json`: top1=`0.4` errors=`3` examples=`5`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_016_review.json`: top1=`1.0` errors=`0` examples=`4`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_017_review.json`: top1=`1.0` errors=`0` examples=`4`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_018_review.json`: top1=`0.75` errors=`1` examples=`4`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_019_review.json`: top1=`1.0` errors=`0` examples=`2`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_020_review.json`: top1=`0.6666666666666666` errors=`2` examples=`6`

## Per Decision Class

- `attack_leader_with_battle`: top1=`1.0` errors=`0` examples=`19`
- `attack_leader_with_leader`: top1=`0.09090909090909091` errors=`10` examples=`11`
- `charge_lategame`: top1=`1.0` errors=`0` examples=`11`
- `charge_opening`: top1=`1.0` errors=`0` examples=`20`
- `end_turn_after_development`: top1=`1.0` errors=`0` examples=`6`
- `play_board_extension`: top1=`0.42857142857142855` errors=`4` examples=`7`
- `play_pressure`: top1=`1.0` errors=`0` examples=`5`

## Sample Errors

- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_001_review.json` idx=`30` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=7838|target_card=card_id=8314|attacker_zone=leader|target_zone=leader|target_player=1`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_001_review.json` idx=`38` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=8314|target_card=card_id=7838|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_002_review.json` idx=`39` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=8314|target_card=card_id=7838|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_003_review.json` idx=`30` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=8314|target_card=card_id=7838|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_004_review.json` idx=`39` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=8314|target_card=card_id=7838|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_004_review.json` idx=`48` `play_board_extension` -> `play_pressure` action=`play_card_from_hand|card=card_id=8324`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_005_review.json` idx=`30` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=7838|target_card=card_id=8314|attacker_zone=leader|target_zone=leader|target_player=1`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_011_review.json` idx=`30` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=8314|target_card=card_id=7838|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_015_review.json` idx=`30` `attack_leader_with_leader` -> `attack_leader_with_battle` action=`declare_attack|attacker_card=card_id=8314|target_card=card_id=7838|attacker_zone=leader|target_zone=leader|target_player=2`
- `artifacts\phase22_normalized\mechikabura_vs_gogeta\ai_match_trace_015_review.json` idx=`38` `play_board_extension` -> `play_pressure` action=`play_card_from_hand|card=card_id=1190`
