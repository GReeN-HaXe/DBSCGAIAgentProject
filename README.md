# DBS AI Agent

![Status](https://img.shields.io/badge/status-active-success)
![Effect%20Catalog](https://img.shields.io/badge/effect_catalog-sharded-blue)
![Priority%20Mapping](https://img.shields.io/badge/priority_mapping-263%2F266-informational)
![Python](https://img.shields.io/badge/python-3.13-blue)
![Tests](https://img.shields.io/badge/regression_suite-500%2B%20tests-brightgreen)

DBS AI Agent is an experimental Dragon Ball Super Card Game engine, rule-extraction pipeline, and AI evaluation workspace.

The project is built around one core idea: take real DBS card text, turn it into structured effect rules, and use those rules inside a testable gameplay engine that can support both interactive play and AI research.

This repository combines three major tracks:

- a playable DBS Masters rules engine
- a card-text-to-effect-catalog extraction pipeline
- AI, benchmark, and dataset tooling for human-vs-AI and AI-vs-AI experiments

This is not an official simulator or official game client. It is an engineering and research project focused on gameplay correctness, effect modeling, and reproducible iteration.

## Why This Exists

DBS card text is rich, inconsistent, and full of edge cases. This project exists to make that complexity executable.

In practice, that means:

- storing card data locally in a database and normalized exports
- extracting reusable effect families from card text
- filling the hard gaps with maintained overrides where extraction is not enough yet
- running those rules inside a deterministic gameplay engine
- keeping the whole thing grounded with regression tests, reports, and planning artifacts

## Current Status

The project is active and already useful as a serious engineering sandbox.

- the effect catalog supports a broad set of reusable effect families
- the generated catalog has been sharded for maintainability
- the high-frequency priority mapping queue is effectively complete apart from intentional skillless skips
- gameplay coverage is continuing to expand into timing, keyword, control, under-card, and Z-layer seams

Current mapping snapshot from `artifacts/effect_family_mapping_report.json`:

| Metric | Value |
| --- | --- |
| Priority cards | `266` |
| Mapped priority cards | `263` |
| Actionable unmapped priority cards | `0` |
| Intentionally skipped priority cards | `3` |

Primary generated catalog artifact:

- `dbdatabase/effect_catalog_shards/manifest.json`

Compatibility catalog output:

- `dbdatabase/effect_catalog.json`

## What You Can Do Here

- run the gameplay engine against heuristic AI
- rebuild the generated effect catalog from extraction logic and overrides
- inspect mapping coverage and support audits
- test new effect families with focused pipeline regressions
- generate benchmark datasets and analyze model/eval outputs

## First 5 Minutes

If you are opening this repo for the first time, this is the fastest useful path:

### 1. Install the base dependencies

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

### 2. Run the core gameplay/effect slice

```powershell
python -m pytest -q tests/test_phase3_rule_fixes.py tests/test_phase4_effect_pipeline.py tests/test_effect_rule_extractor.py
```

### 3. Rebuild the effect catalog

```powershell
python scripts/build_effect_catalog.py
```

### 4. Open an interactive terminal match

```powershell
python scripts/play_vs_ai.py --use-db-sample-decks --human-player 1
```

## Example Workflow

Here is the typical loop for working on effect support:

1. Pick a bounded seam from `docs/project_planning.md`.
2. Add or extend extractor/runtime support in `src/game`.
3. Add focused regressions in `tests/test_effect_rule_extractor.py` or `tests/test_phase4_effect_pipeline.py`.
4. Rebuild the catalog with `python scripts/build_effect_catalog.py`.
5. Run the targeted regression slice.
6. Rebuild reports if the change affects support/mapping visibility.

A practical example:

```powershell
python -m pytest -q tests/test_effect_rule_extractor.py tests/test_phase4_effect_pipeline.py
python scripts/build_effect_catalog.py
python -m pytest -q tests/test_effect_catalog_io.py tests/test_effect_catalog_drift.py
```

What that usually changes:

- extractor logic in `src/game/effect_rule_extractor.py`
- runtime behavior in `src/game/engine.py`
- generated catalog outputs in `dbdatabase/`
- planning/report artifacts in `docs/` and `artifacts/`

## Repository Layout

Core directories:

- `src/game`
  - rules engine, game state, actions, effect loading, timing, and skill-cost handling
- `src/agent`
  - heuristic/agent utilities, session helpers, deck setup, and dataset tooling
- `src/db`
  - repository interfaces and DB access helpers
- `dbdatabase`
  - SQLite database, source patches, schemas, generated catalogs, maintained overrides
- `scripts`
  - catalog builders, benchmark utilities, match runners, and analysis scripts
- `tests`
  - regression coverage for gameplay, extraction, catalogs, and session flows
- `docs`
  - planning, phase handoffs, contribution workflows, and closeout notes
- `artifacts`
  - generated reports, mapping snapshots, support audits, and debug outputs

## Getting Started

### 1. Create a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements-dev.txt
```

Optional extras:

- `requirements-torch.txt` for model/training work
- `requirements-vision.txt` for vision/image-related phases

### 3. Run the core regression slice

```powershell
python -m pytest -q tests/test_phase3_rule_fixes.py tests/test_phase4_effect_pipeline.py tests/test_effect_rule_extractor.py
```

## Common Commands

### Rebuild the effect catalog

```powershell
python scripts/build_effect_catalog.py
```

This writes:

- `dbdatabase/effect_catalog.json`
- `dbdatabase/effect_catalog_shards/manifest.json`
- `dbdatabase/effect_catalog_strict_report.json`

### Run focused catalog checks

```powershell
python -m pytest -q tests/test_effect_catalog_io.py tests/test_effect_catalog_drift.py
```

### Play against the AI in the terminal

```powershell
python scripts/play_vs_ai.py --use-db-sample-decks --human-player 1
```

Help:

```powershell
python scripts/play_vs_ai.py --help
```

### Build effect-family reports

```powershell
python scripts/build_effect_family_report.py
python scripts/build_effect_family_mapping_report.py
```

## Data and Catalog Notes

This repo keeps a strict distinction between:

- human-maintained sources
  - extractor logic
  - maintained overrides
  - schemas
  - source-text patches
- generated artifacts
  - effect catalogs
  - sharded manifests
  - family reports
  - audit outputs

If you change extraction logic, overrides, or source text patches, rebuild the generated artifacts before committing.

Relevant maintained files:

- `src/game/effect_rule_extractor.py`
- `src/game/skill_cost_rule_extractor.py`
- `dbdatabase/effect_catalog_overrides.json`
- `dbdatabase/source_text_patches.json`

## Testing Philosophy

The test suite is built around regression safety.

Important areas:

- `tests/test_phase4_effect_pipeline.py`
  - end-to-end effect resolution and timing behavior
- `tests/test_effect_rule_extractor.py`
  - extraction-family coverage from card text
- `tests/test_effect_catalog_io.py`
  - loading, manifest support, and catalog compatibility
- `tests/test_effect_catalog_drift.py`
  - ensures generated artifacts stay in sync with code changes
- `tests/test_phase6_human_session.py`
  - interactive/session-facing stability

## Docs Worth Reading First

- `docs/project_planning.md`
  - current status, decision log, ongoing seams, and recommended next work
- `docs/phase6_closeout.md`
  - what the playable human-vs-AI surface currently covers
- `docs/human_trace_contribution.md`
  - how to generate reusable human-vs-AI traces

## Known Realities

This project is ambitious and still incomplete. A few things to know up front:

- effect support is broad, but not exhaustive across the full DBS card pool
- some cards still require maintained overrides rather than pure extractor support
- some source DB rows need local text patching because upstream text is malformed or truncated
- generated artifacts are large by nature; sharding is now the preferred catalog format

## If You Want To Contribute

A good first path is:

1. read `docs/project_planning.md`
2. pick one bounded seam
3. add or extend extractor/runtime support
4. add focused regression coverage
5. rebuild the generated artifacts that your change affects

Small, well-tested slices work best in this codebase.

## Good Entry Points

If you want a fast feel for the codebase, these are good places to start:

- `src/game/engine.py`
  - the runtime core
- `src/game/effect_rule_extractor.py`
  - where card text becomes effect families
- `dbdatabase/effect_catalog_overrides.json`
  - maintained exceptions and manual mappings
- `docs/project_planning.md`
  - the actual roadmap and current engineering decisions
