# Human Trace Contribution

Planning source of truth:
- `docs/project_planning.md`

Before collecting or normalizing new traces, check:
- current canonical production artifacts
- current benchmark priorities
- active blockers and TODOs

This document defines the minimum workflow for contributing human-vs-AI traces to the Phase 22 benchmark pipeline.

## Goal

Contributors should generate:

1. raw human-vs-AI trace JSON files
2. normalized review/training artifacts
3. a benchmark dataset group that can be evaluated with the current Phase 22 production model

The current canonical Phase 22 model is:

- `artifacts/phase22_generalization_v2/production`

## Requirements

Use the real Python interpreter, not the Windows Store alias:

```powershell
& "C:\Users\PC\AppData\Local\Programs\Python\Python313\python.exe"
```

## Contribution Rules

Use these rules so traces remain useful:

1. Use fixed deck pairings for a contribution batch.
2. Prefer complete matches or at least longer matches with meaningful action diversity.
3. Do not submit traces that stop after only a few actions unless they expose a real rules bug.
4. Keep filenames stable and descriptive.

Recommended naming:

```text
artifacts/phase22_source/human_vs_ai_trace_<player>_<matchup>_<index>.json
```

Example:

```text
artifacts/phase22_source/human_vs_ai_trace_greenhaxe_krillin_vs_mechikabura_001.json
```

## Step 1: Generate Raw Human-vs-AI Traces

### Option A: DB sample decks

```powershell
& "C:\Users\PC\AppData\Local\Programs\Python\Python313\python.exe" scripts\play_vs_ai.py --human-player 1 --ai-profile balanced --use-db-sample-decks --reveal-ai-hand --trace-output artifacts\phase22_source\human_vs_ai_trace_001.json --summary-output artifacts\phase22_source\human_vs_ai_summary_001.json --save-state-output artifacts\phase22_source\human_vs_ai_state_001.json
```

### Option B: Imported fixed decks

If you already imported DeckPlanet decks into:

- leader ids
- main deck id files

then run:

```powershell
& "C:\Users\PC\AppData\Local\Programs\Python\Python313\python.exe" scripts\play_vs_ai.py --human-player 1 --ai-profile balanced --p1-leader-id <P1_LEADER_ID> --p1-deck-file artifacts\deckplanet\deck_p1_ids.txt --p2-leader-id <P2_LEADER_ID> --p2-deck-file artifacts\deckplanet\deck_p2_ids.txt --reveal-ai-hand --trace-output artifacts\phase22_source\human_vs_ai_trace_001.json --summary-output artifacts\phase22_source\human_vs_ai_summary_001.json --save-state-output artifacts\phase22_source\human_vs_ai_state_001.json
```

Use consistent deck pairings within a batch.

## Step 2: Generate Several Traces

Recommended minimum for one contribution batch:

1. `3-5` traces
2. each with more than `4` meaningful actions
3. with at least `3` unique action types

Keep these files:

- raw trace:
  - `human_vs_ai_trace_*.json`
- optional human-readable summary:
  - `human_vs_ai_summary_*.json`
- optional resumable state:
  - `human_vs_ai_state_*.json`

## Step 3: Normalize the Human Traces

Normalize raw traces into review/training artifacts:

```powershell
& "C:\Users\PC\AppData\Local\Programs\Python\Python313\python.exe" scripts\normalize_human_trace_batch.py --input-glob "artifacts/phase22_source/human_vs_ai_trace_*.json" --output-dir artifacts/phase22_normalized/human_vs_ai --summary-output artifacts/phase22_source/human_trace_normalization_summary.json
```

Outputs:

- `artifacts/phase22_normalized/human_vs_ai/*_review.json`
- `artifacts/phase22_normalized/human_vs_ai/*_training.jsonl`
- `artifacts/phase22_source/human_trace_normalization_summary.json`

## Step 4: Build a Human Benchmark Dataset Group

Build one benchmark dataset from the normalized review traces:

```powershell
& "C:\Users\PC\AppData\Local\Programs\Python\Python313\python.exe" scripts\build_phase22_benchmark_dataset.py --input artifacts/phase22_normalized/human_vs_ai/human_vs_ai_trace_001_review.json artifacts/phase22_normalized/human_vs_ai/human_vs_ai_trace_002_review.json artifacts/phase22_normalized/human_vs_ai/human_vs_ai_trace_003_review.json --output artifacts/phase22_benchmark_batch_v2/human_vs_ai.json --summary-output artifacts/phase22_benchmark_batch_v2/human_vs_ai_summary.json --min-actions 4 --min-unique-action-types 3
```

Outputs:

- `artifacts/phase22_benchmark_batch_v2/human_vs_ai.json`
- `artifacts/phase22_benchmark_batch_v2/human_vs_ai_summary.json`

## Step 5: Evaluate Against Phase 22

Add the human benchmark group to the existing batch evaluation:

```powershell
& "C:\Users\PC\AppData\Local\Programs\Python\Python313\python.exe" scripts\run_phase22_batch_eval.py --dataset artifacts/phase22_benchmark_batch_v2/mechikabura_vs_krillin.json artifacts/phase22_benchmark_batch_v2/gogeta_vs_krillin.json artifacts/phase22_benchmark_batch_v2/red_pan_vs_krillin.json artifacts/phase22_benchmark_batch_v2/mechikabura_vs_gogeta.json artifacts/phase22_benchmark_batch_v2/human_vs_ai.json --production-dir artifacts/phase22_generalization_v2/production --output artifacts/phase22_generalization_v2/phase22_batch_eval_with_human.json
```

Render the report:

```powershell
& "C:\Users\PC\AppData\Local\Programs\Python\Python313\python.exe" scripts\render_phase22_batch_eval_report.py --input artifacts/phase22_generalization_v2/phase22_batch_eval_with_human.json --output artifacts/phase22_generalization_v2/phase22_batch_eval_with_human_report.md
```

## What Contributors Should Submit

Minimum useful submission:

1. raw trace JSON files
2. normalized review JSON files
3. optional notes about obviously bad AI decisions

Preferred package:

```text
artifacts/phase22_source/human_vs_ai_trace_*.json
artifacts/phase22_normalized/human_vs_ai/*_review.json
artifacts/phase22_source/human_trace_normalization_summary.json
```

## Review Checklist

Before accepting a human trace batch:

1. `decision_count` is not tiny
2. action types are not all the same
3. traces are from a consistent deck pairing or are clearly labeled
4. traces are not obviously broken by a rules bug or loop

## Next Benchmark Frontier

Human-vs-AI traces are the next benchmark step after the solved AI-vs-AI matchup family because they introduce:

1. different action preferences
2. less deterministic play patterns
3. a better signal for policy generalization
