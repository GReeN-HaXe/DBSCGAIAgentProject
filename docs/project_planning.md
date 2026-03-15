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
  - status: first runtime slice complete
  - extracted effect rules now carry `limit_per_turn`
  - pending auto resolution now enforces that limit across same-card-number registrations for the same skill family
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
    - status: Unison replacement is now standardized across normal play and effect-driven play; Hidden Mode-specific replacement remains a separate track
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
    - status: runtime now matches by `card_number` when available and falls back to `card_id` only when card-number metadata is missing
  - marker increase after growth
- [ ] implement marker-skill-cost (`[X]`) rules for Unisons:
  - status: first slice complete
  - positive adds markers through the shared skill-cost DSL
  - negative removes markers only if enough markers exist
  - once per turn, per card
  - after one marker-skill resolution, no other marker-cost skills on that card that turn
  - remaining work: broaden beyond generic skill-cost specs into more marker-driven effect families
- [ ] implement Hidden Mode-specific replacement / interaction track:
  - status: replacement/runtime + delayed reveal slices partially complete
  - supported now:
    - hidden-mode battle cards are inert for attacking and skill sourcing
    - reusable `Activate: Main` family to switch an owner battle card to Hidden Mode
    - reusable `Activate: Main` family to drop an owner Hidden Mode battle card and draw
    - reusable `Activate: Main` family to send up to `N` opponent Battle Cards to Warp
    - existing Unison / Hidden Mode replacement semantics now route through the shared replacement path
    - reusable `Activate: Main` family to switch an owner board card to Revealed Mode
    - exact-card delayed reveal now tracks the specific Hidden Mode card chosen as a skill cost
    - reusable `Counter: Play` Hidden Mode cost/runtime slice now supports:
      - switch owner battle card to Hidden Mode as a counter cost
      - play self from the counter resolution path
      - reveal the same chosen card again at end of turn
    - battle-duration temporary modifier support now exists separately from turn-duration modifiers:
      - battle-only power deltas
      - battle-only temporary keywords
      - cleanup on the final `BattleStep.BATTLE_END` resolution
    - reusable `Activate: Battle` Hidden Mode cost family now supports:
      - switch owner battle card to Hidden Mode as an activate-battle cost
      - self gains `+power` and a keyword for the battle
    - reusable `Activate: Battle` Hidden Mode-drop family now supports:
      - place an owner Hidden Mode battle card into its owner's Drop as an activate-battle cost
      - choose up to `N` opponent Battle Cards and KO them
    - effect requirement matching now supports:
      - `if you have N or more Hidden Mode cards in your Battle Area`
      - activate-skill legality is gated by extracted `requires_*` conditions when a matching effect family exists
    - reusable `Activate: Main` play-self family now supports:
      - draw `N`
      - play this card from hand through the normal second `Counter: Play` timing
      - gain a keyword until the end of the opponent's turn
    - hand-based permanent cost reduction is now supported for Hidden Mode white cards:
      - parse `reduce the energy cost of this card in your hand by N`
      - enforce leader color / trait requirements from text
      - enforce Hidden Mode board requirements from text
      - use the effective reduced cost for:
        - normal play legality and payment
        - counter legality and payment
        - hand-based activate-skill legality and payment
      - regression-covered with Android 17-style play/counter tests in `tests/test_game_engine_phase2.py`
    - skill cost catalog path is now available in `RulesEngine` and gameplay scripts
    - initial extracted skill cost catalog now covers four current white Hidden Mode cost families
    - reusable delayed reveal families for:
      - attack-triggered switch of opponent battle card(s) to Hidden Mode, then Revealed Mode at end of opponent's turn
      - play-triggered switch of opponent battle card(s) to Hidden Mode, then Revealed Mode at end of turn
    - reusable owner-side on-play Hidden / Revealed families now support:
      - switch up to `N` owner board cards to Revealed Mode on play
      - switch up to `N` any-player board cards to Revealed Mode on play
      - switch up to `N` owner battle cards to Hidden Mode on play
      - owner battle-card hide triggers now extract even when the text omits the explicit `in your Battle Area` phrase
      - switch self to Hidden Mode on play
      - extractor coverage now picks up simple BT28/BT29 owner-side Hidden/Revealed play triggers
      - regression-covered in `tests/test_effect_rule_extractor.py` and `tests/test_phase4_effect_pipeline.py`
    - reusable `Activate: Main` self-hide family now supports:
      - `Switch this card to Hidden Mode`
      - regression-covered in `tests/test_effect_rule_extractor.py` and `tests/test_phase4_effect_pipeline.py`
    - activate/cost extractor normalization now supports no-colon keyword text:
      - `[Activate Main]`
      - `[Activate Battle]`
      - `[Activate Main/Battle]`
      - this picked up previously missed BT29/BT30 Hidden Mode lines such as `BT29-106 Baby`
    - generic counter play-self family now also supports:
      - `Play this card, then switch it to Hidden Mode`
      - regression-covered in `tests/test_phase3_rule_fixes.py`
    - generic counter-chain resolution now preserves the distinction between:
      - counters that explicitly negate the pending attack
      - counters that only redirect or modify the battle without negating it
    - reusable counter redirect family now supports:
      - `Play this card, switch the target of attack to it, then choose up to 1 of your white Battle Cards and switch it to Hidden Mode at the end of the battle`
      - regression-covered with `BT28-147 Jiren VS Son Goku`-style gameplay flow in `tests/test_phase3_rule_fixes.py`
    - counter Hidden-then-Revealed runtime family now supports:
      - `Negate the attack, choose any number of your opponent's Battle Cards up to the number of your Hidden Mode cards and switch them to Hidden Mode, then switch all the cards switched by this skill to Revealed Mode at the end of the turn`
      - regression-covered with `Revenge Death Ball Final`-style gameplay flow in `tests/test_phase3_rule_fixes.py`
    - optional counter follow-up runtime families now support:
      - `Negate the attack. Additionally, you may switch 1 of your white energy to Hidden Mode. If you do, draw 1 card`
      - `Negate the attack. Additionally, you may discard 1 card from your hand. If you do, choose up to 1 of your white cards and switch it to Hidden Mode`
      - regression-covered in `tests/test_phase3_rule_fixes.py`
    - counter alternate-cost permanents now support:
      - `If your Leader is white, you can activate this card's [Counter] skill from your hand by switching 1 Hidden Mode card in your Battle Area to Rest Mode instead of paying its energy cost`
      - `[Permanent][Sparking 5] You can activate this card's [Counter] skill from your hand by adding 1 card from your life to your hand instead of paying its energy cost`
      - generic extracted requirements now cover:
        - `If your life is at N or less`
        - `If there are N or more colors in your energy`
        - `If you have a multicolor card in your energy`
        - `If you have only black cards in your energy`
        - leader-color gates such as `mono-black`
        - leader trait / character gates such as `yellow ≪Fierce Foe≫` or `yellow <Vegito>`
        - `all of your energy is in Rest Mode`
        - `you have a ... card in play`
        - `you have a ... card in your Battle Area`
        - multicolor / card-type / minimum energy-cost board-state filters for those in-play checks
      - typo-tolerant extraction now covers common DB wording errors such as:
        - `[Permament]`
        - `from our life o your hand`
      - composite alternate costs now support:
        - `add 1 card from your life to your hand and send N matching cards from your Drop to their owner's Warp instead of paying its energy cost`
        - `send N matching cards from your Drop to their owner's Warp instead of paying its energy cost`
        - `send all the cards in your Drop to their owner's Warp instead of paying its energy cost`
        - `return 1 matching card from your Battle Area to your hand instead of paying its energy cost`
        - `switch your matching Leader to Rest Mode instead of paying its energy cost`
        - `pay (N) instead of its energy cost`
        - `choose N of your Battle Cards and reduce their power by -X for the turn instead of paying its energy cost`
      - explicit Z-Deck card state now exists:
        - `PlayerState.z_deck` is modeled as structured cards, not raw ids
        - face-up / face-down Z-Deck state is now tracked
      - face-up Z-Deck alternate-cost requirements now support:
        - `If you have N or more face-up ≪Trait≫ cards in your Z-Deck`
      - the legal-action path now treats those alternates as valid payment when normal energy payment is unavailable
      - extraction/catalog coverage now exists for these alternates under `counter_alternate_from_hand` in `dbdatabase/skill_cost_catalog.json`
      - current catalog coverage now includes older counter families such as:
        - `Support of the Dark Empire`
        - `Whis, Angel of Universe 7`
        - `Dimension Magic`
        - `Focused Breakthrough`
        - `Absolute Release Ball`
        - `Super Kamehameha`
        - `Mercenary Tao, Confrontation`
        - `Marcarita, Caution`
        - `Stop Laughing!`
        - `Strongest Candy in the World`
        - `SS Vegito, Power Release`
        - `Bujin, Bringer of Chaos`
        - `Bujin, Space Pirate Psychic`
        - `Android 17, Guided by the Dragon Balls`
        - `Dr. Uiro, Reckless Science`
        - `Bardock, Destiny-Changing Willpower`
        - `Flight of the Grand Eagle`
        - `Beerus, Godly Power`
      - regression-covered with `BT28-138 Battles of the Gods of Destruction` / `BT29-138 Key to a God`-style tests in `tests/test_phase3_rule_fixes.py`
      - regression coverage for the newer generic families now lives in `tests/test_skill_cost_rule_extractor.py`
    - Hidden Mode drop-trigger families now support:
      - `When this Hidden Mode card in a Battle Area is placed into its owner's Drop, choose up to N of your cards and it gets +power for the turn`
      - works on KO paths and non-KO drop paths driven by skill costs
      - source-drop autos now resolve even after the source leaves play
    - switch-triggered auto families now support:
      - `When this card in a Battle Area is switched to Hidden Mode by one of your skills, your Leader gets +power until the end of your opponent's turn`
      - `When this card in a Battle Area is switched to Hidden Mode by one of your skills, choose up to N of your cards and it gains [Keyword] until the end of your opponent's turn`
      - `When this card is switched to Revealed Mode, it gets +power and [Keyword] for the turn`
      - `When this card is switched to Revealed Mode, choose up to N of your cards and it gains [Keyword] for the turn`
      - `When this card is switched to Revealed Mode or Hidden Mode, choose up to N of your cards and it gets +power for the turn`
      - `When this card is switched to Revealed Mode or Hidden Mode, choose up to N of your opponent's Battle Cards and KO it`
      - extractor and runtime now recognize `self_switched_hidden` / `self_switched_revealed` trigger families
      - turn-gated switch autos (`If it's your turn`) are now supported through generic effect requirements
    - reusable `Activate: Main` Revealed Mode families now support:
      - `Choose all the cards in your opponent's Battle Area and switch them to Revealed Mode, then choose up to N of your opponent's Battle Cards and KO it`
      - regression-covered with `Breakthrough`-style extraction/runtime tests
    - play-search extraction now supports the direct templating variant:
      - `look at up to N cards from the top of your deck, add up to M matching card to your hand`
      - this picks up additional white Hidden Mode cards such as `Master Roshi, Elderly Achievement` and `Bulma, Erosion of the Mind and Body`
    - effect-filter matching now normalizes trait/character comparisons case-insensitively at runtime
  - remaining work:
    - broader Revealed Mode / switch-back interactions beyond the current exact-card cost-selected slice
    - Hidden Mode-specific auto triggers and delayed state changes beyond the generic delayed-reveal families
    - broader Hidden Mode family extraction from active decks and traces
    - broaden skill cost extraction beyond the first Hidden Mode family

- [x] broaden effect catalog scan so activate/counter text families are included even when DB flags are stale
  - `scripts/build_effect_catalog.py` and `tests/test_effect_catalog_drift.py` now scan on normalized skill text markers in addition to DB flags
- [ ] implement Unison battle rules:
  - status: complete
  - defense step skipped when a Unison is attacked
  - damage removes markers instead of life
  - `Double/Triple/Quadruple Strike` remove the corresponding number of markers
  - `Victory Strike` removes all remaining markers
  - regression-covered in `tests/test_phase3_rule_fixes.py`
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
