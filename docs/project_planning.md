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
- pattern-driven effect support audit tooling:
  - `scripts/run_effect_support_audit.py`
- effect-family implementation shortlist tooling:
  - `scripts/build_effect_family_shortlist.py`

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

### Effect Support

- Audit artifact:
  - `artifacts/effect_support_audit.json`
- Ranked implementation shortlist:
  - `artifacts/effect_family_shortlist.json`

## Priority Backlog

### P0: Rules / Effect Correctness

- [x] implement batch/pattern-driven effect support audit
- [ ] build and maintain an effect pattern catalog as the source of truth for reusable skill behavior
- [x] identify the top repeated text families from `dbs_masters.db`, active decks, and recent traces
- [ ] define reusable effect families for common Auto / Activate / Counter patterns
- [ ] implement the top 20-30 effect families first to maximize real deck coverage
- [ ] map high-frequency deck/trace cards to those effect families
- [ ] auto-assign cards to effect families where pattern confidence is high
- [ ] keep manual overrides for edge cases and low-confidence pattern matches
- [ ] implement leader auto families used in current human traces
- [x] implement counter families that negate / play self / apply attack restrictions
- [x] add unsupported counter diagnostics similar to unsupported activate diagnostics
- [x] implement first shortlisted family: generic `Blocker` redirection / target-change
- [x] implement sparking super-combo family (life<=4 or `Sparking N` drop threshold)
- [x] implement owner-leader-attack search/add-to-hand family for Krillin-style leader autos
- [ ] upgrade `[Limit X]` enforcement to match rules text:
  - across the same skill
  - across cards with the same card number
  - including `[Auto]` skills that can go pending multiple times but only resolve up to limit
- [ ] implement full pending/checkpoint handling for `[Auto]` skills:
  - make every trigger instance pending
  - resolve one pending auto at a time at checkpoints
  - allow hidden/secret-area autos to remain undeclared
- [ ] upgrade `[Counter]` handling to match full counter-motion-chain semantics:
  - declaring one pending counter ends the pending status of the others in that hand
  - resolve counter motions in descending order
  - preserve the distinction between counter timing and counter motion resolution
- [ ] implement full Unison rules batch:
  - playing Unison from hand with correct marker entry count
  - replacing an existing Unison / Hidden Mode card in the Unison Area
  - skill-based Unison play with both counter timings
    - status: first slice complete for effect-driven play-from-hand; second `Counter: Play` timing now opens correctly
  - on-play triggers entering pending correctly
    - status: first slice complete where effect-driven Unison play now reuses normal `card_played` resolution
- [x] implement first Unison rules slice:
  - explicit `Unison Growth` action
  - once-per-turn growth lockout
  - per-turn lockout for marker-cost Unison skills after one resolution
- [ ] implement Unison growth:
  - once per turn
  - same card number under existing Unison
  - marker increase after growth
- [ ] implement marker-skill-cost (`[X]`) rules for Unisons:
  - status: first slice complete
  - positive adds markers through the shared skill-cost DSL
  - negative removes markers only if enough markers exist
  - once per turn, per card
  - after one marker-skill resolution, no other marker-cost skills on that card that turn
  - remaining work: broaden beyond generic skill-cost specs into more marker-driven effect families
- [ ] implement Unison battle rules:
  - defense step skipped when a Unison is attacked
  - damage removes markers instead of life
  - `Strike` / `Victory Strike` marker removal behavior
- [ ] implement reusable leader keyword families from rule manual additions:
  - `[Wish]`
  - `[Z-Awaken]`
  - `[Aegis]`
  - `[Arrival]`
  - `[Dark Over Realm]` / `Wormhole`

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

Current next implementation batch from the shortlist:
- completed:
  - blocker redirection / target-change `Blocker` family
  - sparking super-combo family
  - generic counter family: negate attack -> play self in rest -> optional attack restriction
  - unsupported counter diagnostics for unresolved counter skills
  - owner-leader-attack search/add-to-hand family with color / trait / character filtering
  - `SS4's Call`-style activate-main search family with card-name token filtering and bottom-of-deck post-processing
  - `Power Wish` activate-main family:
    - play self from hand with reusable leader/energy/board-state requirements
    - draw-and-gain-keyword-for-turn (`Dual Attack`) family support
- high-priority `Activate: Main/Battle` extra-card families from active decks:
  - `Mighty Blast`
  - `Mechikabura`

### Newly Confirmed Rule Knowledge From `GameRules`

These are rule details confirmed from the new manuals/flowchart set that should shape future engine work.

- `[Limit X]` is broader than per-card runtime tracking:
  - it applies across the same skill
  - across cards with the same card number
  - updated/oracle text still counts as the same skill
- `[Auto]` skills are made pending once per trigger occurrence, including simultaneous occurrences
- hidden-area `[Auto]` skills can remain undeclared by their controller
- `[Counter]` skills operate through counter motions and counter-motion chains, not just a single yes/no response window
- when multiple players must make simultaneous choices/resolutions, the turn player acts first
- Unison play has specific replacement and marker-entry rules:
  - existing Unison / Hidden Mode replacement
  - marker entry count based on rested energy or explicit effect text
  - marker count can be modified while the Unison is being played
- skill-based Unison play has two counter timings around the play process
- Unison growth is once per turn with the same card number from hand
- marker skill costs (`[X]`) have their own once-per-turn-per-card lockout semantics
- when a Unison is attacked:
  - defense step is skipped
  - damage removes markers
  - `Strike` / `Victory Strike` change the amount removed
- tournament policy confirms additional useful public-knowledge expectations:
  - names/counts in drop and warp are public
  - cards played this turn are public
  - missed autos / illegal actions should be repairable/reviewable when possible

Practical interpretation:
- the current engine needs a more explicit pending/checkpoint model than the current ad hoc trigger handling
- Unison needs to move from partial support to a dedicated rules track
- future trace/review tooling can lean on the tournament public-knowledge model

### Human Data

Current planning assumption:
- the next useful benchmark frontier is mixed-source:
  - AI-vs-AI
  - human-vs-AI
- current solved benchmarks are too narrow to justify more architecture work

## Improvement Suggestions

These are review-driven improvement ideas that are worth preserving in planning, but are not yet committed backlog items unless promoted into the priority sections above.

### Effect Catalog as a Formal Artifact

Priority:
- high

Assessment:
- strongest suggestion in this set
- directly aligned with the current correctness / scale bottleneck

Suggestion:
- formalize the effect catalog as a first-class project artifact
- consider a DSL or structured schema (`YAML` / `JSON`) for card behavior definitions

Why it matters:
- decouples the engine's "what" from the implementation "how"
- makes new card support easier to add in batches
- improves coverage tracking for supported / unsupported effect families
- enables direct testing of engine behavior against catalog specifications

Recommended approach:
- start with a structured schema, not a custom DSL
- define effect primitives and family mappings first
- add validation/tests against the schema
- only consider a richer DSL later if schema expressiveness becomes a real blocker

### High-Level Roadmap Visualization

Priority:
- medium

Assessment:
- good coordination improvement
- low engineering cost

Suggestion:
- add a concise roadmap section showing:
  - completed phases
  - frozen baselines
  - current focus
  - next benchmark/data/model frontier

Why it matters:
- makes current work easier to place in the broader project trajectory
- helps collaborators understand what is solved vs exploratory

Recommended approach:
- keep it text-based in this planning document
- avoid diagram/tooling overhead unless the team/process complexity grows

### `play_vs_ai.py` Monolith Reduction

Priority:
- medium-high

Assessment:
- real maintainability issue
- should become backlog work once current trace-collection flow is stable

Suggestion:
- break up `scripts/play_vs_ai.py` into smaller modules

Why it matters:
- current script handles:
  - CLI parsing
  - TUI rendering
  - keyboard navigation
  - game loop orchestration
  - output writing
- this reduces maintainability and makes targeted testing harder

### Isolate the TUI

Priority:
- medium-high

Assessment:
- best concrete refactor under the monolith-reduction theme
- high leverage once more CLI/TUI work continues

Suggestion:
- extract the TUI layer into a dedicated module, for example:
  - `src/agent/tui.py`

Candidate responsibilities:
- panel rendering
- color handling
- keyboard input handling
- action selection flow

Target shape:
- main script orchestrates the session
- TUI module exposes a higher-level entrypoint such as:
  - `tui.run(session)`

### Separate Data From Presentation

Priority:
- medium-high

Assessment:
- strong architectural cleanup
- best handled as part of TUI extraction, not as an isolated standalone refactor

Suggestion:
- split data gathering from string/color rendering in the CLI/TUI

Example direction:
- one function returns structured action rows:
  - action text
  - score
  - hints
  - selected-state metadata
- a separate renderer formats that structure into terminal output

Why it matters:
- improves testability
- reduces formatting logic inside gameplay orchestration
- makes future UI migrations easier

### Consider a TUI Framework

Priority:
- low for now

Assessment:
- valid long-term option
- not the current best use of engineering effort

Suggestion:
- evaluate a dedicated TUI framework such as `Textual` if terminal UX remains a long-term priority

Tradeoff:
- higher migration cost now
- potentially much simpler layout/input/state handling later

Use when:
- the terminal interface remains central
- panel complexity keeps growing
- hand-rolled TUI maintenance starts becoming the bottleneck

Current recommendation:
- do not migrate yet
- revisit only if the existing TUI keeps expanding and maintenance becomes the main bottleneck

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
