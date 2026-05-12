# AGENTS

Repo-wide guidance for agents working in `C:\Users\PC\Desktop\dbsAIAgent`.

## Scope

- This file applies to the entire repository tree.
- If a deeper `AGENTS.md` exists later, the deeper file wins for its subtree.

## Authoritative Data Sources

- Treat `C:\Users\PC\Desktop\dbsAIAgent\dbdatabase\dbs_masters.db` as the authoritative local card-text database for effect-family work.
- Do not assume `C:\Users\PC\Desktop\dbsAIAgent\dbdatabase\cards.db` is usable. It has been observed as an empty placeholder.
- For effect text matching, trust live DB text over handwritten assumptions. The live text frequently contains:
  - HTML escapes such as `&lt;...&gt;`
  - `<br>` separators
  - Unicode/fullwidth punctuation and reminder-text variants

## Effect-Family Workflow

- For extractor/runtime work, use this order:
  1. implement runtime and extractor changes
  2. add focused extractor tests
  3. add focused phase4 tests
  4. run focused tests first
  5. run broader validation
  6. rebuild generated artifacts
- Prefer exact live-text normalization over narrow handwritten phrase matching.
- If a shortlist head looks already implemented, verify it against:
  - `C:\Users\PC\Desktop\dbsAIAgent\dbdatabase\effect_catalog.json`
  - `C:\Users\PC\Desktop\dbsAIAgent\artifacts\effect_support_audit.json`
  before doing new work.
- If shortlist presentation and catalog/audit disagree, trust the catalog and audit, not the visible shortlist rows.

## Artifact Rebuild Rule

- Rebuild effect artifacts with:
  - `python C:\Users\PC\Desktop\dbsAIAgent\scripts\rebuild_effect_artifacts.py`
- Do not rebuild these in parallel when consistency matters:
  - catalog
  - support audit
  - family mapping report
  - family report
  - family shortlist
- Reason:
  - downstream artifacts can lag if they are regenerated against an older catalog snapshot
  - the sequential rebuild script enforces the correct dependency order

## Validation Rule

- After effect-family changes, run at least:
  - focused extractor tests for the changed slice
  - focused phase4 tests for the changed slice
  - `python -m pytest -q C:\Users\PC\Desktop\dbsAIAgent\tests\test_effect_rule_extractor.py`
  - `python -m pytest -q C:\Users\PC\Desktop\dbsAIAgent\tests\test_effect_catalog_io.py C:\Users\PC\Desktop\dbsAIAgent\tests\test_effect_catalog_drift.py --basetemp=.pytest_tmp_catalog`
- When validating full phase4, use a local base temp to avoid cache/permission noise:
  - `python -m pytest -q C:\Users\PC\Desktop\dbsAIAgent\tests\test_phase4_effect_pipeline.py --basetemp=.pytest_tmp_phase4_full`

## Known Baseline Failure

- There is a known unrelated full-phase4 failure currently treated as baseline until explicitly fixed:
  - `C:\Users\PC\Desktop\dbsAIAgent\tests\test_phase4_effect_pipeline.py:49374`
  - `test_phase4_exact_son_gohan_beyond_the_ultimate_play_activate_and_hand_play_lines`
- Do not conflate that failure with the slice you are implementing unless your changes actually touch that family.

## Shortlist and Report Guidance

- After extractor/runtime changes, rebuild artifacts before trusting:
  - `C:\Users\PC\Desktop\dbsAIAgent\artifacts\effect_family_report.json`
  - `C:\Users\PC\Desktop\dbsAIAgent\artifacts\effect_family_shortlist.json`
- If the shortlist still appears stale after rebuild, cross-check the card directly in:
  - `C:\Users\PC\Desktop\dbsAIAgent\dbdatabase\effect_catalog.json`
  - `C:\Users\PC\Desktop\dbsAIAgent\artifacts\effect_support_audit.json`
- Prefer “next real unresolved head” selection over blindly following a stale displayed rank.

## Practical Implementation Notes

- Many exact handlers are easiest to validate by direct handler tests in `C:\Users\PC\Desktop\dbsAIAgent\tests\test_phase4_effect_pipeline.py` instead of full gameplay flows.
- When adding trigger support, also verify the event is actually emitted in the existing engine path before assuming the extractor family is sufficient.
- When changing union-related behavior, verify discard/drop causes explicitly:
  - `union_fusion`
  - `union_absorb`
  - `union_potara`
- When working on generated artifact mismatches, distinguish:
  - generator logic bugs
  - stale rebuild order
  - presentation lag in downstream reports

## Rebuild Command of Record

- Use this as the canonical repo command after effect-family changes:
  - `python C:\Users\PC\Desktop\dbsAIAgent\scripts\rebuild_effect_artifacts.py`
