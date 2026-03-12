# Project Planning

## Purpose

This document is the working planning surface for the repo.

This file is the single planning source of truth for the project.

Use it to track:
- current infrastructure status
- canonical artifacts and baselines
- active blockers
- prioritized TODOs
- next benchmark/data/model directions

Update this file whenever:
- a phase is effectively frozen
- a new production artifact becomes canonical
- a blocker is discovered or resolved
- a new TODO is added to planning

Required update events:
- a benchmark is frozen
- a new production artifact becomes canonical
- a new TODO is added
- a blocker is resolved

## Status Summary

### Overall

Status: active development

Current focus:
- keep Phase 22 frozen for the current solved AI-vs-AI benchmark family
- expand benchmark difficulty with human-vs-AI and broader matchup coverage
- improve rules/effect coverage using batch/pattern-driven effect support, not card-by-card ad hoc fixes

### Canonical Runtime / Environment

- Primary Python interpreter:
  - `C:\Users\PC\AppData\Local\Programs\Python\Python313\python.exe`
- Recommended pytest pattern:
  - `& "C:\Users\PC\AppData\Local\Programs\Python\Python313\python.exe" -m pytest -q -p no:cacheprovider --basetemp <fresh-temp-dir>`
- Reason:
  - avoids the Windows Store Python alias
  - reduces flaky temp/cache cleanup failures on this machine

### Rules / Engine

Status: partially complete

Working well:
- turn flow
- charging
- energy payment via resting energy
- basic plays
- attacks / battle steps
- counter timing windows
- awaken action framework
- per-turn activate limit enforcement
- unsupported activate diagnostics

Known gaps:
- many leader autos are still not implemented
- many battle-card Activate / Auto skills are still only partially supported
- card-specific effect resolution coverage is incomplete
- effect correctness still depends on which families are implemented

Important recent fixes:
- `AWAKEN` action support
- activate once-per-turn / `[Limit 1]` enforcement
- unsupported activate diagnostics in trace/checkpoints

### CLI / TUI

Status: strong enough for trace generation and review

Implemented:
- compact TUI-style `play_vs_ai.py`
- side-by-side panels:
  - summary
  - hand
  - actions
  - board
- arrow-key navigation
- action score + hint tags
- action detail / hand detail / board detail views
- per-turn and full-match action history log
- direct DeckPlanet deck import in `play_vs_ai.py`

Current usability level:
- good enough for collecting human-vs-AI traces
- still terminal-first, not GUI-first

### Trace / Dataset Pipeline

Status: strong

Implemented:
- AI-vs-AI raw traces
- human-vs-AI raw traces
- normalized review traces
- normalized training rows
- benchmark dataset builders
- batch dataset builders
- merged benchmark builders
- multi-dataset eval
- LOMO holdout eval

Human trace path:
- raw `play_vs_ai.py` trace
- `scripts/normalize_human_trace.py`
- `scripts/normalize_human_trace_batch.py`
- Phase 22 benchmark dataset builders

### Phase 22 Learned State Encoder

Status: frozen for current AI-vs-AI benchmark scope

Canonical production candidate:
- `artifacts/phase22_generalization_v2/production`

Current benchmark conclusion:
- current AI-vs-AI matchup family is solved
- generalized model reached:
  - batch-eval top-1: `1.0`
  - LOMO top-1: `1.0`

Meaning:
- more Phase 22 tuning on the same four matchup groups is not justified
- next benchmark improvements must come from harder data, not more local optimization

### Vision / Identity

Status: usable but not complete

Implemented:
- Phase 10 detection pipeline
- Phase 15 production identity resolver
- identity enrichment into Phase 10 flow
- identity fields propagated into Phase 9 / Phase 7 datasets

Current limitation:
- gameplay benchmarks still do not fully exploit identity-enriched decision datasets
- current strongest policy/state benchmarks are still mostly non-identity gameplay traces

### Repo / Artifacts

Status: stable

Resolved:
- oversized model artifact git push failures
- generated large model files are no longer the active repo blocker

## Canonical Artifacts

### Phase 22

- Closeout report:
  - `artifacts/phase22_closeout_report.md`
- Generalized production candidate:
  - `artifacts/phase22_generalization_v2/production`
- Generalized batch eval:
  - `artifacts/phase22_generalization_v2/phase22_generalization_batch_eval.json`
- LOMO summary:
  - `artifacts/phase22_lomo_v1/phase22_lomo_summary.json`

### Human Trace Contribution

- Contributor instructions:
  - `docs/human_trace_contribution.md`

## Priority Backlog

### P0: Rules / Effect Correctness

- [ ] implement batch/pattern-driven effect support audit
- [ ] build and maintain an effect pattern catalog as the source of truth for reusable skill behavior
- [ ] identify the top repeated text families from `dbs_masters.db`, active decks, and recent traces
- [ ] define reusable effect families for common Auto / Activate / Counter patterns
- [ ] implement the top 20-30 effect families first to maximize real deck coverage
- [ ] map high-frequency deck/trace cards to those effect families
- [ ] auto-assign cards to effect families where pattern confidence is high
- [ ] keep manual overrides for edge cases and low-confidence pattern matches
- [ ] implement leader auto families used in current human traces
- [ ] implement counter families that negate / play self / apply attack restrictions
- [ ] add unsupported counter diagnostics similar to unsupported activate diagnostics

### P1: Human-vs-AI Benchmark Expansion

- [ ] generate 3-5 usable human-vs-AI traces per selected deck matchup
- [ ] normalize those traces into review/training artifacts
- [ ] build a `human_vs_ai` benchmark dataset group
- [ ] add `human_vs_ai` into Phase 22 batch evaluation
- [ ] compare AI-vs-AI-only vs mixed-source benchmark behavior

### P1: Benchmark Breadth

- [ ] add more DeckPlanet matchup families beyond the current four
- [ ] rebuild benchmark-batch datasets for new matchups
- [ ] rerun generalized Phase 22 training on broader matchup coverage
- [ ] rerun batch eval + LOMO on the expanded family

### P2: Identity-Enriched Gameplay Benchmarks

- [ ] build gameplay decision datasets where identity-resolved features matter
- [ ] measure Phase 22 on identity-enriched gameplay examples
- [ ] compare mixed identity vs non-identity datasets

### P2: UI / Trace Collection

- [ ] keep improving `play_vs_ai.py` only as needed for trace quality
- [ ] consider richer board detail panes if human contributors still struggle
- [ ] defer real GUI until terminal workflow stops being the bottleneck

## Current Known Gaps

### Effect Coverage

Current planning assumption:
- effect coverage is the next real correctness bottleneck
- fixing cards one by one is not scalable
- effect families and coverage tracking are required

### Human Data

Current planning assumption:
- the next useful benchmark frontier is mixed-source:
  - AI-vs-AI
  - human-vs-AI
- current solved benchmarks are too narrow to justify more architecture work

## Decision Log

### Freeze Decision

Decision:
- freeze Phase 22 for the current AI-vs-AI benchmark family

Why:
- generalized batch eval solved the current benchmark family
- LOMO holdout also solved the current benchmark family
- benchmark frontier must move before architecture changes are justified

### Architecture Decision

Decision:
- do not redesign the Phase 22 encoder yet

Why:
- current evidence says data diversity and effect correctness are bigger bottlenecks than model capacity

## Next Recommended Work

In order:

1. build a pattern-driven effect support audit
2. fix high-frequency leader auto / counter families
3. collect and normalize human-vs-AI traces
4. add human benchmark groups to Phase 22 eval
5. expand matchup coverage
6. only then reassess whether a richer state architecture is needed

## TODO Intake

When adding a new TODO:

1. add it to the relevant priority section above
2. if it changes the recommended next work order, update that section too
3. if it replaces a canonical artifact or baseline, update `Canonical Artifacts`
4. if it resolves a blocker, move the old blocker out of `Current Known Gaps`
