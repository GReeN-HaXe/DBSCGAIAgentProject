from __future__ import annotations

from types import SimpleNamespace

from src.game import Action, ActionType, CardInstance, EffectRegistration, RulesEngine, TurnPhase


def _deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _to_main(engine: RulesEngine, state):
    while state.phase != TurnPhase.MAIN:
        state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=state.active_player))
    return state


def _to_p1_main_where_attacks_are_legal(engine: RulesEngine, state):
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=state.active_player))
    state = _to_main(engine, state)
    return state


def test_phase4_auto_effect_registers_on_play_and_resolves() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880001, card_id=1, owner_id=1, card_type="BATTLE", energy_cost=0, has_auto=True)
    ]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    regs = [r for r in state.effect_registry if r.source_instance_id == 880001]
    assert regs
    assert any(r.trigger == "self_played" for r in regs)
    assert any(r.trigger == "self_attacks" for r in regs)
    assert any(res.resolved for res in state.effect_resolutions)


def test_phase4_attack_declared_triggers_self_attack_effect() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880011, card_id=11, owner_id=1, card_type="BATTLE", energy_cost=0, has_auto=True)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
    )
    state = engine.apply_action(state, attack)
    attack_effect_ids = {r.effect_id for r in state.effect_registry if r.source_instance_id == 880011 and r.trigger == "self_attacks"}
    assert attack_effect_ids
    # Auto-trigger should be pending until counter timing closes.
    assert any(pe.effect_id in attack_effect_ids for pe in state.pending_effects)
    assert all(not (res.effect_id in attack_effect_ids and res.resolved) for res in state.effect_resolutions)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(res.effect_id in attack_effect_ids and res.resolved for res in state.effect_resolutions)


def test_phase4_custom_effect_handler_is_used() -> None:
    def custom_handler(state, event, reg):
        state.log.append(f"custom:{reg.effect_id}:{event.name}")

    engine = RulesEngine(effect_handlers={"noop_auto": custom_handler})
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880021, card_id=21, owner_id=1, card_type="BATTLE", energy_cost=0, has_auto=True)
    ]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(entry.startswith("custom:") for entry in state.log)


def test_phase4_permanent_does_not_enter_pending_activation_flow() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880031, card_id=31, owner_id=1, card_type="BATTLE", energy_cost=0, has_permanent=True)
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    regs = [r for r in state.effect_registry if r.source_instance_id == 880031]
    assert regs == []
    assert all(
        not (evt.payload.get("source_instance_id") == 880031 and evt.name == "state_check")
        for evt in state.effect_events
    )


def test_phase4_once_per_turn_pending_batch_resolves_only_once() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    source = state.players[1].leader_area
    state.effect_registry.append(
        EffectRegistration(
            effect_id=state.next_effect_id,
            owner_player_id=1,
            source_instance_id=source.instance_id,
            source_card_id=source.card_id,
            source_zone="leader",
            trigger="turn_start",
            handler_id="noop_auto",
            once_per_turn=True,
            triggers_this_turn=0,
        )
    )
    effect_id = state.next_effect_id
    state.next_effect_id += 1

    # Two same-turn trigger events -> only one should resolve.
    engine._emit_effect_event(state, name="turn_start", actor_player_id=1, payload={})
    engine._emit_effect_event(state, name="turn_start", actor_player_id=1, payload={})
    engine._resolve_pending_effects(state)

    rows = [r for r in state.effect_resolutions if r.effect_id == effect_id]
    assert any(r.resolved for r in rows)
    assert any((not r.resolved) and r.reason == "once_per_turn_used" for r in rows)


def test_phase4_auto_draw_on_play_resolves_after_counter_timing() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    p1 = state.players[1]
    p1.hand = [
        CardInstance(
            instance_id=880041,
            card_id=41,
            owner_id=1,
            card_type="BATTLE",
            energy_cost=0,
            has_auto=True,
            has_draw=True,
            auto_draw_on_play=True,
        )
    ]
    deck_before = len(p1.deck)
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    # Not resolved yet while counter timing is open.
    assert len(state.players[1].deck) == deck_before
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].hand) == 1
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_draw_on_play" for cp in state.checkpoints)


def test_phase4_auto_draw_on_play_empty_deck_causes_loss() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    p1 = state.players[1]
    p1.deck = []
    p1.hand = [
        CardInstance(
            instance_id=880051,
            card_id=51,
            owner_id=1,
            card_type="BATTLE",
            energy_cost=0,
            has_auto=True,
            has_draw=True,
            auto_draw_on_play=True,
        )
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.winner_id == 2


def test_phase4_auto_draw_on_attack_resolves_after_counter_timing() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.append(
        CardInstance(
            instance_id=880061,
            card_id=61,
            owner_id=1,
            card_type="BATTLE",
            energy_cost=0,
            has_auto=True,
            has_draw=True,
            auto_draw_on_attack=True,
        )
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    deck_before = len(state.players[1].deck)

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
    )
    state = engine.apply_action(state, attack)
    # Pending during counter timing.
    assert len(state.players[1].deck) == deck_before
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_draw_on_attack" for cp in state.checkpoints)


def test_phase4_auto_draw_on_attack_empty_deck_causes_loss() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].deck = []
    state.players[1].battle_area.append(
        CardInstance(
            instance_id=880071,
            card_id=71,
            owner_id=1,
            card_type="BATTLE",
            energy_cost=0,
            has_auto=True,
            has_draw=True,
            auto_draw_on_attack=True,
        )
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.winner_id == 2


def test_phase4_once_per_turn_is_detected_from_skill_text() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 990001:
                return SimpleNamespace(
                    power_int=15000,
                    card_type="BATTLE",
                    card_color="Blue",
                    energy_cost_int=0,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=True,
                    has_permanent=False,
                    has_draw=True,
                    max_draw=1,
                    has_barrier=False,
                    z_energy_cost=None,
                    card_energy_cost="0",
                    card_skill_unstyled="[Auto][Once per turn] When this card attacks, draw 1 card.",
                )
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color="Red",
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=0,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
            )

    engine = RulesEngine(card_repository=Repo())
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[990001] + _deck(1000, 59),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    play = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0
    )
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    played_instance_id = next(c.instance_id for c in state.players[1].battle_area if c.card_id == 990001)
    regs = [r for r in state.effect_registry if r.source_instance_id == played_instance_id]
    assert any(r.handler_id == "auto_draw_on_attack" and r.once_per_turn for r in regs)


def test_phase4_once_per_turn_auto_draw_on_attack_triggers_once_same_turn() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    # Keep enough deck to draw and attach a once-per-turn attack draw auto.
    source = CardInstance(
        instance_id=990011,
        card_id=11,
        owner_id=1,
        card_type="BATTLE",
        has_auto=True,
        has_draw=True,
        auto_draw_on_attack=True,
        auto_once_per_turn=True,
    )
    state.players[1].battle_area.append(source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    deck_before = len(state.players[1].deck)

    # Same checkpoint batch with two attack events: should resolve only once.
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": 990011, "attacker_zone": "battle", "target_player_id": 2, "target_zone": "leader"},
    )
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": 990011, "attacker_zone": "battle", "target_player_id": 2, "target_zone": "leader"},
    )
    engine._resolve_pending_effects(state)
    assert len(state.players[1].deck) == deck_before - 1
    rows = [r for r in state.effect_resolutions if r.reason in {"ok", "once_per_turn_used"}]
    assert any(r.resolved and r.reason == "ok" for r in rows)
    assert any((not r.resolved) and r.reason == "once_per_turn_used" for r in rows)
