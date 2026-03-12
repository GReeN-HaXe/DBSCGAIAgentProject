# Phase 7 Handoff

Phase 7 should focus on learning and evaluation infrastructure, not more Phase 6 pipeline polish.

## Stable inputs from Phase 6

- Human-vs-AI session model: `src/agent/session.py`
- Replay runner: `src/agent/replay.py`
- Match summary and expectation evaluation: `src/agent/match_result.py`
- Pipeline validation and reporting: `scripts/validate_phase6_pipeline.py`
- Saved-state serialization: `src/game/state_io.py`

## Known limitations carried forward

- The AI uses heuristic scoring, not trained policy/value models.
- There is no dataset builder yet for supervised or reinforcement learning.
- Deck legality exists, but deck optimization/search is not implemented.
- Validation currently proves reproducibility and artifact health, not gameplay strength.

## Recommended Phase 7 work order

1. Build a dataset capture layer from human-vs-AI and replay traces.
2. Define training/evaluation schemas for policy decisions and game outcomes.
3. Add benchmark suites for deck matchups and fixed replay scenarios.
4. Introduce learned-policy experiments behind a pluggable policy interface.
5. Add comparative evaluation against current heuristic profiles.

## Immediate entry points

- Add trace-to-dataset export in `src/agent/session.py` or a new `src/agent/dataset.py`.
- Add offline evaluator scripts next to `scripts/validate_phase6_pipeline.py`.
- Reuse `artifacts/phase6_release/` as the baseline reference set for regression checks.

## Definition of done for Phase 7 start

- A reproducible training dataset can be produced from saved Phase 6 traces.
- A learned-policy experiment can run without replacing the current heuristic baseline.
- Evaluation reports can compare learned vs heuristic behavior on fixed seeds and replay cases.
