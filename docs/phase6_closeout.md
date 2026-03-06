# Phase 6 Closeout

Phase 6 goal was to turn the engine and heuristic agent into a playable, testable human-vs-AI product surface with reproducible validation.

## Stable outcomes

- Human-vs-AI interactive CLI exists through `scripts/play_vs_ai.py`.
- Saved-state resume flow exists through `--load-state-input` and `--save-state-output`.
- Scripted deterministic replay exists through `scripts/replay_human_vs_ai.py`.
- Deck validation supports leader/deck structure checks plus legality checks for copy limits, banned cards, and limited cards.
- Validation pipeline exists through `scripts/validate_phase6_pipeline.py`.
- The pipeline generates manifest, report, integrity, history, timing, and regression artifacts.
- Pipeline determinism checks are normalized to ignore volatile timestamps.

## Phase 6 release command

Use this command to generate the release artifact pack:

```powershell
python scripts/validate_phase6_pipeline.py --artifacts-dir artifacts/phase6_release --pipeline-profile strict --seed 101 --update-timing-baseline-json artifacts/phase6_release/baseline_timing.json
```

## Release artifact set

- `artifacts/phase6_release/phase6_pipeline_manifest.json`
- `artifacts/phase6_release/phase6_report.md`
- `artifacts/phase6_release/phase6_integrity_result.json`
- `artifacts/phase6_release/phase6_pipeline_history.csv`
- `artifacts/phase6_release/phase6_pipeline_history_summary.json`
- `artifacts/phase6_release/phase6_stage_timings.json`
- `artifacts/phase6_release/phase6_timing_regression.json`
- `artifacts/phase6_release/phase6_timing_history.csv`
- `artifacts/phase6_release/phase6_timing_history_summary.json`
- `artifacts/phase6_release/baseline_timing.json`

## Exit criteria

Phase 6 is considered complete when:

- the full pytest suite passes
- the release validation command passes
- the release manifest reports `status = pass`
- the report and artifact integrity outputs are present

## Known boundaries

- AI policy is still heuristic, not learned.
- Deck construction quality is validated structurally, not strategically.
- Card effect coverage is bounded by the current engine/effect-rule implementation, not the entire live card pool.
- The player experience is terminal-first; there is no dedicated GUI yet.
