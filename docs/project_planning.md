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
- Deck/trace family mapping report:
  - `artifacts/effect_family_mapping_report.json`
- High-confidence assignment candidates:
  - `artifacts/effect_family_assignment_candidates.json`

## Priority Backlog

### P0: Rules / Effect Correctness

- [x] implement batch/pattern-driven effect support audit
- [ ] build and maintain an effect pattern catalog as the source of truth for reusable skill behavior
  - status: first formal-catalog slice complete
  - `effect_catalog.json` is now a versioned envelope with:
    - `catalog_kind`
    - `schema_version`
    - `card_rule_count`
    - `effect_rule_count`
    - `rules`
  - the loader is backward-compatible with the previous plain card-id map format
  - the formal artifact contract is now checked in at `dbdatabase/effect_catalog.schema.json`
  - status: rule provenance slice complete
  - extracted catalog rules now carry:
    - `family_id`
    - `provenance`
  - extractor-generated rules currently default to:
    - `family_id = "<trigger>:<handler_id>"`
    - `provenance = "extractor"`
  - status: manual override layer slice complete
  - effect catalog overrides now support per-card merge modes:
    - `append`
    - `replace`
  - override contract is now checked in at `dbdatabase/effect_catalog_overrides.schema.json`
  - builder and runtime scripts can now apply `effect_catalog_overrides.json` when present
  - first checked-in override entries now cover:
    - `TB1-011 Cabba, Universe Mediator`
    - `BT27-092 Mechikabura`
  - status: family-level report slice complete
  - `scripts/build_effect_family_report.py` now emits `artifacts/effect_family_report.json`
  - family reports group catalog rules by:
    - `family_id`
    - trigger
    - handler
    - provenance
- [x] identify the top repeated text families from `dbs_masters.db`, active decks, and recent traces
- [ ] define reusable effect families for common Auto / Activate / Counter patterns
- [ ] implement the top 20-30 effect families first to maximize real deck coverage
- [ ] map high-frequency deck/trace cards to those effect families
  - status: first mapping-report slice complete
  - `scripts/build_effect_family_mapping_report.py` now emits:
    - `artifacts/effect_family_mapping_report.json`
  - the report joins:
    - active DeckPlanet deck usage
    - recent trace card usage
    - effect catalog family assignments
  - current report snapshot:
    - priority cards: `266`
    - mapped priority cards: `172`
    - unmapped priority cards: `94`
  - current counter-family override batch now maps:
    - `BT14-019 Dyspo, Thwarting the Enemy`
    - `BT13-135 Supreme Kai of Time, Time Labyrinth Unleashed`
    - `BT23-033 Explosive Dance`
    - plus the next `21` high-confidence counter-family assignments from the candidate report
  - current condition-support slice now also maps:
    - `BT5-012 Master Roshi, Martial Expert`
      - via extracted `self_comboed:auto_draw_n`
      - with explicit leader-color + `Sparking 5` / drop-threshold gating
  - current black warp/search family slice now also maps:
    - `BT29-086 Goku Black`
      - via extracted `self_activate_main:activate_look_top_send_up_to_n_to_owner_warp`
    - `BT29-088 SS Rosé Goku Black, Fearsome God`
      - via extracted `self_activate_main:activate_send_top_deck_to_owner_warp`
    - `BT29-091 Goku Black, Surprise Attack`
      - via extracted `self_activate_main:activate_send_top_deck_to_owner_warp`
    - `BT29-093 Zamasu, Dark Plans`
      - via extracted `self_activate_main:activate_send_top_deck_to_owner_warp`
  - current reactive black battle family slice now also maps:
    - `BT19-147 Son Gohan, Hostile Saiyan Encounter`
      - via extracted `owner_opponent_battle_attacks:auto_pay_life_bottom_deck_play_self_from_drop_or_warp_negate_attack`
      - runtime support now covers:
        - public-zone registration from `drop` / `warp`
        - life-to-hand and hand-to-bottom-deck payment
        - playing self from `drop` / `warp` in Rest Mode
        - negating the triggering battle-card attack
  - current opponent-drop-to-warp unison family slice now also maps:
    - `P-244 Piccolo, Savior From the Beyond`
      - via extracted `self_activate_main:activate_send_up_to_n_opponent_drop_battle_to_warp`
      - runtime support now covers:
        - sending up to `N` opponent Battle Cards from Drop to Warp
        - unison marker delta handling from plain `[-N]` activate text
  - current black warp/unison Zamasu family slice now also maps:
    - `BT29-094 Zamasu, Scheme`
      - via extracted `self_activate_main:activate_play_self_from_warp`
      - via extracted `self_activate_main:activate_add_up_to_n_from_owner_warp_to_hand`
      - source-zone-specific skill cost support now covers:
        - `activate_main_warp` -> send `Z-Energy` to Drop
        - `activate_main_unison` -> send `1` hand card to Warp
      - runtime support now covers:
        - warp-origin `Activate: Main` registration
        - opening a second `Counter: Play` timing for `play from Warp`
        - resolving `play_from_warp` with marker override support
        - unison-origin warp-to-hand activation without cross-firing the warp-play family
  - current Mira black warp/unison slice now also maps:
    - `EX15-05 Mira, Dimensional Superpower`
      - via extracted `self_activate_main:activate_optional_send_owner_hand_to_warp_draw_n`
      - via extracted `self_activate_battle:activate_gain_power_and_keyword_for_battle`
      - generic plain marker activate-cost extraction now covers:
        - `[+1][Activate: Main]` -> `activate_main_unison:add_markers`
        - `[-2][Activate: Battle]` -> `activate_battle_unison:remove_markers`
      - runtime support now covers:
        - optional hand-to-warp then draw on `Activate: Main`
        - battle power scaling via `expr:owner_warp_count*5000`
  - current red extra-from-hand multi-branch slice now also maps:
    - `BT29-024 Stowaways`
      - via extracted `self_activate_extra_from_hand:activate_play_up_to_n_each_named_from_owner_deck_or_drop`
      - via extracted `self_activate_extra_from_hand:activate_add_up_to_n_from_owner_deck_to_hand`
      - runtime support now covers:
        - branch-select actions for hand Extras with multiple extracted activation families
        - resolving only the selected Extra activation branch
        - branch-specific pre-resolution discard cost handling
        - searching a matching Extra from Deck to hand
        - playing up to `1` each of named Battle Cards from Deck and/or Drop in Rest Mode
      - catalog candidate scanning now includes:
        - `[Activate: Main/Battle]`
        - `[Activate Main/Battle]`
  - current red `Counter: Play` pressure slice now also maps:
    - `BT10-008 Yamcha, Merciless Barrage`
      - via manual override family:
        - `counter_play:counter_power_reduce_up_to_n_opponent_battle_for_turn_play_self`
      - runtime support now covers:
        - reducing up to `2` opponent Battle Cards by `-15000` for the turn
        - then playing self through the existing `Counter: Play` motion path
        - alternate free counter activation when the owner has a red Unison with `2+` markers in play
  - highest-frequency currently unmapped cards in active deck/trace usage include:
    - `BT29-027 Tiny Golden Warrior`
    - `TB1-023 Strategies of Universe 7`
    - `EX06-36 A Crack in Spacetime`
    - `BT29-150 SS Rosé Goku Black, Justice Enforcer`
    - `BT15-096 Son Goku, Steadfast Assistance`
- [ ] auto-assign cards to effect families where pattern confidence is high
  - status: first high-confidence candidate-report slice complete
  - `scripts/build_effect_family_assignment_candidates.py` now emits:
    - `artifacts/effect_family_assignment_candidates.json`
  - status: first auto-apply-safe batch complete
  - status: first condition-support holdout slice complete
  - current candidate report snapshot after applying the safe counter-family batch and Roshi condition-support fix:
    - candidates: `0`
    - auto-apply-safe candidates: `0`
  - this means the current candidate heuristic has been exhausted, and the next mapping gains need broader family extraction/runtime support rather than more obvious override assignments
- [x] keep manual overrides for edge cases and low-confidence pattern matches
- [x] implement leader auto families used in current human traces
  - completed for current human-trace leaders:
    - `BT29-001 Krillin` owner-leader-attack search family
    - `EX19-20 Bardock` owner-leader-attack `{SS4}` search family
    - `BT15-001 Son Goten` leader on-attack draw family
  - extractor hardening now prevents leader attack text from false-matching later `[Awaken] Draw ...` text
- [x] implement counter families that negate / play self / apply attack restrictions
- [x] add unsupported counter diagnostics similar to unsupported activate diagnostics
- [x] implement first shortlisted family: generic `Blocker` redirection / target-change
- [x] implement sparking super-combo family (life<=4 or `Sparking N` drop threshold)
- [x] implement owner-leader-attack search/add-to-hand family for Krillin-style leader autos
- [ ] upgrade `[Limit X]` enforcement to match rules text:
  - status: first runtime slice complete
  - extracted effect rules now carry `limit_per_turn`
  - pending auto resolution now enforces that limit across same-card-number registrations for the same skill family
  - status: shared once-per-turn accounting slice complete
  - public pending effects and declared secret autos now share a source-based once-per-turn key
  - repeated secret-auto declarations for the same hidden source now block correctly with `once_per_turn_used`
  - public pending effects now count prior declared secret autos against the same once-per-turn key in the same turn
  - blocked secret auto declarations now retain explicit blocked opportunity status instead of ending up as misleading `declared` records
  - later secret trigger opportunities can now be created as preblocked records when the once-per-turn / limit-per-turn key is already exhausted
  - preblocked opportunity creation now surfaces in:
    - checkpoint `secret_auto_opportunity_preblocked`
    - runtime log entries with blocked status
  - CLI/history rendering now surfaces secret auto status and preblocked opportunities explicitly in:
    - action descriptions
    - state/full-board summaries
    - history text rendering
  - status: trace export / normalization slice complete
  - raw human trace payloads now export:
    - `final_state_snapshot`
    - compact `secret_auto_summary` data at the top level
    - compact `secret_auto_summary` data inside per-action and final state snapshots
  - preblocked opportunity rows now carry explicit `preblocked=true` metadata instead of only relying on logs/checkpoints
  - normalized human review/training artifacts now preserve secret-auto action metadata such as:
    - `secret_auto_trigger`
    - `secret_auto_event_name`
    - `secret_auto_origin_zone`
    - `secret_auto_status_before`
  - status: compact summary / Phase 22 summary slice complete
  - compact match summaries now include count-oriented `secret_auto_summary` data
  - Phase 22 dataset and batch summaries now aggregate:
    - traces with secret-auto opportunities
    - total opportunity / pending / blocked / preblocked counts
    - secret-auto status-count totals across included traces
  - status: merged-benchmark / LO-MO summary slice complete
  - Phase 22 dataset JSON artifacts now carry compact top-level `secret_auto_summary` data
  - merged benchmark outputs now preserve and aggregate compact secret-auto counts from input datasets
  - LO-MO summaries now surface:
    - per-fold holdout secret-auto counts
    - per-fold merged-train secret-auto counts
    - overall holdout secret-auto totals across folds
  - status: generalization / production / batch-eval summary slice complete
  - Phase 22 production summaries now surface compact training-dataset secret-auto counts
  - Phase 22 batch-eval outputs now surface:
    - per-dataset secret-auto counts
    - overall aggregated secret-auto counts across evaluated datasets
  - Phase 22 generalization summaries now surface:
    - train-dataset secret-auto counts
    - production-side training-dataset secret-auto counts
    - batch-eval aggregated secret-auto counts
  - status: reporting layer slice complete
  - Phase 22 batch-eval markdown reports now surface compact secret-auto counts
  - Phase 22 closeout markdown reports now surface:
    - generalized secret-auto counts
    - LO-MO holdout secret-auto counts
  - status: limit-scope runtime slice complete
  - effect limit keys now honor:
    - `card_number`
    - `card_id`
    - `source_instance`
  - regression coverage now proves those scopes resolve differently at runtime instead of only carrying the label
  - status: secret-area declaration counting slice complete
  - declared secret autos now participate in the same per-turn limit accounting as public effect registrations
  - secret auto declaration now blocks with:
    - unresolved `EffectResolution.reason = "limit_per_turn_used"`
    - checkpoint `secret_auto_declared_limit_blocked`
  - public pending effects now also count previously declared secret autos against the same limit key in the same turn
  - status: public limit-diagnostics slice complete
  - public pending effects now surface explicit diagnostics when blocked by:
    - once-per-turn
    - limit-per-turn
  - diagnostics now include:
    - checkpoints `effect_once_per_turn_blocked` / `effect_limit_per_turn_blocked`
    - runtime log summaries with effect id, source instance, trigger, handler, and limit metadata
  - across the same skill
  - across cards with the same card number
  - including `[Auto]` skills that can go pending multiple times but only resolve up to limit
- [ ] implement full pending/checkpoint handling for `[Auto]` skills:
  - status: first queue-driven slice complete
  - pending-effect resolution now consumes a live queue instead of a one-shot snapshot
  - effects triggered by an effect can now continue resolving in the same checkpoint
  - make every trigger instance pending
  - resolve one pending auto at a time at checkpoints
    - simultaneous public pending effects now have explicit turn-player-first regression coverage
  - allow hidden/secret-area autos to remain undeclared
    - status: first guardrail slice complete
    - effect registration from secret zones (`hand`, `life`, `deck`) now skips auto-trigger registrations by default
    - explicit hand-sourced activate-skill registrations are still allowed
    - deferred secret-area autos now have explicit runtime state in `GameState.deferred_secret_autos`
    - deferred secret-area autos are pruned automatically when the source leaves the secret zone
    - trigger-time secret-area auto opportunities now have explicit runtime state in `GameState.secret_auto_opportunities`
    - matching effect events now create opportunity records without interrupting gameplay flow
    - opportunity creation now surfaces in:
      - runtime log entries
      - checkpoint `secret_auto_opportunity_created`
    - deferred secret-area auto registrations now surface in:
      - runtime log entries
      - checkpoint `secret_auto_registration_deferred`
    - phased implementation plan:
      - phase 1: keep deferred secret-auto runtime state as the stable base
      - phase 2: add explicit declaration-opportunity objects backed by `deferred_secret_autos`
        - status: complete
      - phase 3: add engine-level declare / ignore action flow for secret-area auto opportunities
        - status: first slice complete
        - legal actions now expose `declare_secret_auto` / `ignore_secret_auto` for the next pending opportunity
        - opportunities are resolved in deterministic turn-player-first order
        - declared opportunities now resolve through the engine and append `EffectResolution` audit rows
        - ignored opportunities now persist with explicit `ignored` status for replay/audit
        - stale pending opportunities are now pruned automatically when the source leaves all tracked zones
      - phase 4: expose declare / ignore flow in CLI/TUI for human-controlled secret-area autos
      - phase 5: define default AI/self-play policy for secret-area auto declaration
        - status: first slice complete
        - `HeuristicPolicy` now prefers `declare_secret_auto` over `ignore_secret_auto`
        - session turn ownership now yields to the next pending secret-auto opportunity owner before normal active-player flow
        - AI session stepping can now consume pending secret-auto opportunities instead of stalling on them
      - phase 6: add replay / audit support for declared, ignored, and missed secret-area auto opportunities
        - status: first slice complete
        - action traces now persist:
          - `opportunity_id`
          - `secret_auto_id`
          - trigger / event metadata
          - pre-action opportunity status
        - history/action rendering now includes secret-auto trigger and event context when available
    - preserve hidden-origin provenance through public registration
      - status: first slice complete
      - secret-origin `self_played` autos now preserve their hidden origin when the source becomes public
      - deferred secret autos are promoted to the current public zone instead of being discarded
      - linked public auto registration for those `self_played` secret-origin autos is suppressed to avoid duplicate pending/resolution paths
      - provenance now survives into:
        - `SecretAutoOpportunity.origin_zone`
        - action rendering
        - session trace metadata
        - history/review output
      - deferred for later:
        - broaden provenance preservation to live transition-point capture during normal gameplay
        - candidate future families:
          - ordinary `hand -> battle/unison` `self_played` transitions
          - `hand -> combo` `self_comboed` and `self_comboed_battle_end` transitions
        - this broader shift was intentionally deferred because it changes many existing public-auto runtime expectations at once
    - approach decision:
      - preferred path is hybrid
      - keep deferred secret autos as the storage/runtime layer
      - add explicit trigger-time declaration opportunities on top rather than replacing the deferred model outright
    - tradeoff summary:
      - deferred-registration-first is lower risk and preserves current momentum
      - explicit declaration opportunities are the better long-term rules-faithful model
      - the hybrid path gives the best short-term stability and long-term architecture
- [ ] upgrade `[Counter]` handling to match full counter-motion-chain semantics:
  - status: first pending-choice closure slice complete
  - when a player declares a counter from hand, the engine now explicitly records that the other pending counter choices in that same hand are closed
  - closure now surfaces in:
    - runtime log entries
    - checkpoint `counter_pending_choices_closed`
  - declaring one pending counter ends the pending status of the others in that hand
  - resolve counter motions in descending order
    - status: first runtime metadata slice complete
    - `CounterResolution` and resolved `CounterMotionTrace` rows now carry explicit `resolution_order`
    - current chain resolution tests now assert latest-declared motion resolves first (`resolution_order=1`)
    - regression coverage now includes three-motion chains to lock in descending-order behavior beyond the simple two-motion case
  - preserve the distinction between counter timing and counter motion resolution
    - status: first diagnostics slice complete
    - counter-chain timing is now explicitly separated from chain resolution in:
      - checkpoint `counter_chain_timing`
      - checkpoint `counter_chain_resolution_begin`
      - checkpoint `counter_chain_resolution_complete`
      - runtime log summaries of ordered motion resolution
    - status: mixed-family effect diagnostics slice complete
    - `CounterResolution` and resolved `CounterMotionTrace` rows now carry `applied_effects`
    - runtime logs now summarize which reusable counter subfamilies fired per resolved motion
    - regression coverage now checks:
      - simple `play_self`
      - `play_self + attack_restriction`
      - unsupported counter family tagging
      - redirecting play-self counters with delayed battle-end Hidden Mode scheduling
    - status: pending-action-context slice complete
    - `CounterResolution` and `CounterMotionTrace` now carry `pending_action_type`
    - runtime logs now expose whether the counter chain was responding to:
      - `attack`
      - `play_from_hand`
      - `activate_main`
      - `activate_battle`
      - `activate_extra_from_hand`
      - other future pending-action kinds
    - regression coverage now includes:
      - attack-counter chains
      - play-counter chains
      - `activate_main` counter chains
      - `activate_battle` counter chains
      - `activate_extra_from_hand` counter chains
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
        - leader trait / character gates such as `yellow â‰ªFierce Foeâ‰«` or `yellow <Vegito>`
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
        - `If you have N or more face-up â‰ªTraitâ‰« cards in your Z-Deck`
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

