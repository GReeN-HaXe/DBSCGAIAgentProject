from __future__ import annotations

from types import SimpleNamespace

from src.game import Action, ActionType, AttackContext, BattleStep, CardInstance, EffectRegistration, RulesEngine, TurnPhase
from src.game.engine import CardRuntimeData


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


def test_phase4_activate_main_can_play_self_from_warp_with_marker_override() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 9729:
                return SimpleNamespace(
                    id=9729,
                    card_number="BT29-094",
                    card_name="Zamasu, Scheme",
                    card_type="UNISON",
                    card_color="black",
                    card_energy_cost="X",
                    energy_cost_int=None,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=15000,
                    card_skill_unstyled="[Activate: Main] placeholder",
                    has_activate_main=True,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Zamasu"]',
                )
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="black",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9729: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_warp",
                    "handler_params": {"markers": 0, "required_source_zone": "warp", "min_owner_energy": 2},
                }
            ]
        },
        skill_cost_rules={
            9729: {
                "activate_main_warp": [
                    {
                        "kind": "send_owner_z_energy_to_drop",
                        "amount": 1,
                    }
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p1_z_deck_card_ids=[910001],
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=700001, card_id=111, owner_id=1, card_type="BATTLE", color="black"),
        CardInstance(instance_id=700002, card_id=112, owner_id=1, card_type="BATTLE", color="black"),
    ]
    state.players[1].z_energy = [
        CardInstance(instance_id=700003, card_id=113, owner_id=1, card_type="BATTLE", color="black")
    ]
    warp_card = CardInstance(
        instance_id=700004,
        card_id=9729,
        owner_id=1,
        card_number="BT29-094",
        card_type="UNISON",
        color="black",
        has_activate_main=True,
        characters=("Zamasu",),
    )
    state.players[1].warp = [warp_card]
    engine._register_card_effects(state, player_id=1, source_zone="warp", card=warp_card)

    activate = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "warp"
    )
    state = engine.apply_action(state, activate)
    assert len(state.players[1].z_energy) == 0
    assert len(state.players[1].drop) == 1
    assert state.counter_window is not None
    assert state.counter_window.pending_action.action_type == "activate_main"

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None
    assert state.counter_window.pending_action.action_type == "play_from_warp"

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert not state.players[1].warp
    assert any(card.instance_id == 700004 for card in state.players[1].drop)
    assert any(cp.name == "main_play_unison" for cp in state.checkpoints)
    assert any(cp.name == "rule_unison_zero_markers" for cp in state.checkpoints)


def test_phase4_activate_main_can_play_battle_self_from_warp() -> None:
    engine = RulesEngine(
        effect_rules={
            9732: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_warp",
                    "handler_params": {"required_source_zone": "warp", "requires_leader": "black", "min_owner_energy": 3},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Black"
    state.players[1].energy = [
        CardInstance(instance_id=700101, card_id=211, owner_id=1, card_type="ENERGY", color="Black"),
        CardInstance(instance_id=700102, card_id=212, owner_id=1, card_type="ENERGY", color="Black"),
        CardInstance(instance_id=700103, card_id=213, owner_id=1, card_type="ENERGY", color="Black"),
    ]
    warp_card = CardInstance(
        instance_id=700104,
        card_id=9732,
        owner_id=1,
        card_number="BT29-097",
        card_type="BATTLE",
        color="Black",
        energy_cost=1,
        power=15000,
        has_activate_main=True,
    )
    state.players[1].warp = [warp_card]
    engine._register_card_effects(state, player_id=1, source_zone="warp", card=warp_card)

    activate = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "warp"
    )
    state = engine.apply_action(state, activate)
    assert state.counter_window is not None
    assert state.counter_window.pending_action.action_type == "activate_main"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None
    assert state.counter_window.pending_action.action_type == "play_from_warp"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert not state.players[1].warp
    assert any(card.instance_id == 700104 for card in state.players[1].battle_area)
    assert any(cp.name == "counter_timing_play_from_skill" for cp in state.checkpoints)
    assert any(cp.name == "main_play_battle" for cp in state.checkpoints)


def test_phase4_ex_evolve_can_play_matching_battle_from_hand_on_top_of_owner_battle() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 9637:
                return SimpleNamespace(
                    id=9637,
                    card_number="BT29-006",
                    card_name="SS Son Goten, Demon Resistance",
                    card_type="BATTLE",
                    card_color="red",
                    card_energy_cost="3",
                    energy_cost_int=3,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=20000,
                    card_skill_unstyled=(
                        "[Deflect][Double Strike]\n"
                        "[EX-Evolve][Limit 1]{r} : Red <Son Goten> card with an energy cost of 1.\n"
                        "[Auto] When this card is played, draw 1 card."
                    ),
                    has_activate_main=False,
                    has_auto=True,
                    has_draw=True,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=("Deflect", "Double Strike"),
                    card_traits_json='[]',
                    card_character_json='["Son Goten"]',
                )
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="red",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='["Son Goten"]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9637: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
                {"trigger": "self_played", "handler_id": "auto_switch_self_active_on_play", "handler_params": {}},
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=700120, card_id=301, owner_id=1, card_type="ENERGY", color="Red"),
    ]
    state.players[1].battle_area = [
        CardInstance(
            instance_id=700121,
            card_id=302,
            owner_id=1,
            card_number="BT29-007",
            card_type="BATTLE",
            color="Red",
            energy_cost=1,
            power=5000,
            resting=True,
            characters=("Son Goten",),
        )
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=700122,
            card_id=9637,
            owner_id=1,
            card_number="BT29-006",
            card_type="BATTLE",
            color="Red",
            energy_cost=3,
            power=20000,
            skill_text_raw=(
                "[Deflect][Double Strike]\n"
                "[EX-Evolve][Limit 1]{r} : Red <Son Goten> card with an energy cost of 1.\n"
                "[Auto] When this card is played, draw 1 card."
            ),
            characters=("Son Goten",),
        )
    ]
    deck_before = len(state.players[1].deck)

    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.EX_EVOLVE)
    state = engine.apply_action(state, action)

    evolved = state.players[1].battle_area[0]
    assert evolved.instance_id == 700122
    assert evolved.resting is False
    assert evolved.stacked_card_ids == (302,)
    assert all(card.instance_id != 700122 for card in state.players[1].hand)
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "ex_evolve" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_switch_self_active_on_play" for cp in state.checkpoints)
    assert any(res.resolved for res in state.effect_resolutions if res.reason == "ok")


def test_phase4_tiny_golden_warrior_can_enable_next_matching_ex_evolve_from_drop() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            rows = {
                9660: SimpleNamespace(
                    id=9660,
                    card_number="BT29-027",
                    card_name="Tiny Golden Warrior",
                    card_type="EXTRA",
                    card_color="red",
                    card_energy_cost="0",
                    energy_cost_int=0,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=0,
                    card_skill_unstyled=(
                        "[Permanent] This card gains ≪Earthling≫ in all areas.\n"
                        "[Activate: Main][Limit 1] If your Leader is a red <Krillin> card : "
                        "The next time you activate [EX-Evolve] on your red <Son Goten> or <Trunks : Youth> card during this turn, "
                        "it can also activate from its owner's Drop."
                    ),
                    has_activate_main=True,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=True,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='["Earthling"]',
                    card_character_json='[]',
                ),
                9639: SimpleNamespace(
                    id=9639,
                    card_number="BT29-008",
                    card_name="SS Trunks, Demon Resistance",
                    card_type="BATTLE",
                    card_color="red",
                    card_energy_cost="3",
                    energy_cost_int=3,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=20000,
                    card_skill_unstyled=(
                        "[Deflect][Blocker]\n"
                        "[EX-Evolve][Limit 1]{r} : Red <Trunks : Youth> card with an energy cost of 1.\n"
                        "[Auto] When this card is played, draw 1 card."
                    ),
                    has_activate_main=False,
                    has_auto=True,
                    has_draw=True,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=("Deflect", "Blocker"),
                    card_traits_json='[]',
                    card_character_json='["Trunks : Youth"]',
                ),
            }
            if card_id in rows:
                return rows[card_id]
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="red",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='["Trunks : Youth"]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9660: [
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_grant_next_ex_evolve_from_owner_drop",
                    "handler_params": {
                        "uses_remaining": 1,
                        "allowed_colors": "red",
                        "required_characters": "Son Goten,Trunks : Youth",
                    },
                    "limit_per_turn": 1,
                }
            ],
            9639: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ],
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Red"
    state.players[1].leader_area.characters = ("Krillin",)
    state.players[1].energy = [
        CardInstance(instance_id=700130, card_id=401, owner_id=1, card_type="ENERGY", color="Red"),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=700131,
            card_id=9660,
            owner_id=1,
            card_number="BT29-027",
            card_type="EXTRA",
            color="Red",
            energy_cost=0,
        )
    ]
    play_extra = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play_extra)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert len(state.ex_evolve_permissions) == 1
    state.players[1].battle_area = [
        CardInstance(
            instance_id=700132,
            card_id=402,
            owner_id=1,
            card_number="BT29-009",
            card_type="BATTLE",
            color="Red",
            energy_cost=1,
            power=5000,
            resting=False,
            characters=("Trunks : Youth",),
        )
    ]
    state.players[1].drop = [
        CardInstance(instance_id=700131, card_id=9660, owner_id=1, card_type="EXTRA", color="Red"),
        CardInstance(
            instance_id=700133,
            card_id=9639,
            owner_id=1,
            card_number="BT29-008",
            card_type="BATTLE",
            color="Red",
            energy_cost=3,
            power=20000,
            skill_text_raw=(
                "[Deflect][Blocker]\n"
                "[EX-Evolve][Limit 1]{r} : Red <Trunks : Youth> card with an energy cost of 1.\n"
                "[Auto] When this card is played, draw 1 card."
            ),
            characters=("Trunks : Youth",),
        ),
    ]
    deck_before = len(state.players[1].deck)

    ex_evolve = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.EX_EVOLVE and a.source_zone == "drop"
    )
    state = engine.apply_action(state, ex_evolve)

    assert state.players[1].battle_area[0].instance_id == 700133
    assert state.players[1].battle_area[0].stacked_card_ids == (402,)
    assert len(state.players[1].deck) == deck_before - 1
    assert not state.ex_evolve_permissions
    assert any(cp.name == "effect_activate_grant_next_ex_evolve_from_owner_drop" for cp in state.checkpoints)
    assert any(cp.name == "ex_evolve" for cp in state.checkpoints)


def test_phase4_pursuit_activate_main_can_discard_self_and_add_matching_ex_evolve_from_deck_to_hand() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            rows = {
                1: SimpleNamespace(
                    id=1,
                    card_number="BT29-001",
                    card_name="Krillin",
                    card_type="LEADER",
                    card_color="red",
                    card_energy_cost="-",
                    energy_cost_int=None,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=10000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Krillin"]',
                ),
                9638: SimpleNamespace(
                    id=9638,
                    card_number="BT29-007",
                    card_name="Son Goten, Pursuit",
                    card_type="BATTLE",
                    card_color="red",
                    card_energy_cost="1",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=4000,
                    card_skill_unstyled=(
                        "[Auto] When this card is played, draw 1 card.\n"
                        "[Activate: Main][Limit 1] If your Leader is a red <Krillin> card and you discard this card from your hand : "
                        "Add up to 1 red <Son Goten> card with an energy cost of 3 and [EX-Evolve] from your deck to your hand, then shuffle your deck."
                    ),
                    has_activate_main=True,
                    has_auto=True,
                    has_draw=True,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Son Goten"]',
                ),
                9637: SimpleNamespace(
                    id=9637,
                    card_number="BT29-006",
                    card_name="SS Son Goten, Demon Resistance",
                    card_type="BATTLE",
                    card_color="red",
                    card_energy_cost="3",
                    energy_cost_int=3,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=20000,
                    card_skill_unstyled=(
                        "[Deflect][Double Strike]\n"
                        "[EX-Evolve][Limit 1]{r} : Red <Son Goten> card with an energy cost of 1.\n"
                        "[Auto] When this card is played, draw 1 card and switch this card to Active Mode."
                    ),
                    has_activate_main=False,
                    has_auto=True,
                    has_draw=True,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=("Deflect", "Double Strike"),
                    card_traits_json='[]',
                    card_character_json='["Son Goten"]',
                ),
            }
            if card_id in rows:
                return rows[card_id]
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="red",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9638: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "limit_per_turn": 1},
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_add_up_to_n_from_owner_deck_to_hand",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "red",
                        "required_characters": "Son Goten",
                        "max_cost": 3,
                        "requires_leader": "if your leader is a red <krillin> card and you discard this card from your hand",
                    },
                    "limit_per_turn": 1,
                },
            ],
        },
        skill_cost_rules={
            9638: {
                "activate_main_hand": [
                    {"kind": "send_self_from_hand_to_drop", "amount": 1},
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.color = "Red"
    state.players[1].leader_area.characters = ("Krillin",)
    state.players[1].energy = [
        CardInstance(instance_id=700150, card_id=501, owner_id=1, card_type="ENERGY", color="Red"),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=700151,
            card_id=9638,
            owner_id=1,
            card_number="BT29-007",
            card_type="BATTLE",
            color="Red",
            energy_cost=1,
            power=4000,
            has_activate_main=True,
            skill_text_raw=(
                "[Auto] When this card is played, draw 1 card.\n"
                "[Activate: Main][Limit 1] If your Leader is a red <Krillin> card and you discard this card from your hand : "
                "Add up to 1 red <Son Goten> card with an energy cost of 3 and [EX-Evolve] from your deck to your hand, then shuffle your deck."
            ),
            characters=("Son Goten",),
        )
    ]
    state.players[1].deck = [9637, 1100, 1101]

    activate = next(
        action
        for action in engine.get_legal_actions(state, 1)
        if action.action_type == ActionType.ACTIVATE_MAIN_SKILL and action.source_zone == "hand"
    )
    state = engine.apply_action(state, activate)
    assert any(card.instance_id == 700151 for card in state.players[1].drop)
    assert not state.players[1].hand

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert any(card.card_id == 9637 for card in state.players[1].hand)
    assert any(cp.name == "effect_activate_add_up_to_n_from_owner_deck_to_hand" for cp in state.checkpoints)


def test_phase4_cross_dimensional_fighting_spirit_can_warp_on_play_and_buff_on_activate() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            rows = {
                2140: SimpleNamespace(
                    id=2140,
                    card_number="BT22-116",
                    card_name="SS4 Son Goku, Cross-Dimensional Fighting Spirit",
                    card_type="Z-BATTLE",
                    card_color="black",
                    card_energy_cost="1",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=10000,
                    power_int=15000,
                    card_skill_unstyled=(
                        "[Auto] When this card is played, choose up to 1 of your opponent's Battle Cards and send it to its owner's Warp.\n"
                        "[Activate: Main][Once per turn] If you have 3 or more energy and you remove 10 total cards in your Drop and Warp from the game: "
                        "This card gets +10000 power and [Double Strike] for the turn."
                    ),
                    has_activate_main=True,
                    has_auto=True,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Son Goku"]',
                ),
            }
            if card_id in rows:
                return rows[card_id]
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="black",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            2140: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_send_up_to_n_opponent_battle_to_warp_on_play",
                    "handler_params": {"max_targets": 1, "target_policy": "first"},
                },
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_gain_power_and_keyword_for_turn",
                    "handler_params": {"power_delta": 10000, "grant_keyword": "Double Strike", "min_owner_energy": 3},
                    "once_per_turn": True,
                },
            ]
        },
        skill_cost_rules={
            2140: {
                "activate_main": [
                    {"kind": "send_owner_drop_and_warp_to_removed", "amount": 10},
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=700200, card_id=601, owner_id=1, card_type="ENERGY", color="Black"),
        CardInstance(instance_id=700201, card_id=602, owner_id=1, card_type="ENERGY", color="Black"),
        CardInstance(instance_id=700202, card_id=603, owner_id=1, card_type="ENERGY", color="Black"),
        CardInstance(instance_id=700203, card_id=604, owner_id=1, card_type="ENERGY", color="Black"),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=700204,
            card_id=2140,
            owner_id=1,
            card_number="BT22-116",
            card_type="Z-BATTLE",
            color="Black",
            energy_cost=1,
            power=15000,
            has_activate_main=True,
            skill_text_raw=(
                "[Auto] When this card is played, choose up to 1 of your opponent's Battle Cards and send it to its owner's Warp.\n"
                "[Activate: Main][Once per turn] If you have 3 or more energy and you remove 10 total cards in your Drop and Warp from the game: "
                "This card gets +10000 power and [Double Strike] for the turn."
            ),
            characters=("Son Goku",),
        )
    ]
    state.players[1].drop = [
        CardInstance(instance_id=700210 + i, card_id=700 + i, owner_id=1, card_type="BATTLE", color="Black")
        for i in range(6)
    ]
    state.players[1].warp = [
        CardInstance(instance_id=700220 + i, card_id=800 + i, owner_id=1, card_type="BATTLE", color="Black")
        for i in range(4)
    ]
    state.players[2].battle_area = [
        CardInstance(instance_id=700230, card_id=900, owner_id=2, card_type="BATTLE", color="Red", energy_cost=4, power=20000)
    ]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    assert not state.players[2].battle_area
    assert any(card.instance_id == 700230 for card in state.players[2].warp)
    assert any(cp.name == "effect_auto_send_up_to_n_opponent_battle_to_warp_on_play" for cp in state.checkpoints)

    activate = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    )
    state = engine.apply_action(state, activate)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    source = next(card for card in state.players[1].battle_area if card.instance_id == 700204)
    assert source.power == 25000
    assert "Double Strike" in source.temporary_keywords
    assert len(state.players[1].drop) + len(state.players[1].warp) == 0
    assert len(state.players[1].removed_from_game) == 10
    assert any(cp.name == "effect_activate_gain_power_and_keyword_for_turn" for cp in state.checkpoints)


def test_phase4_activate_main_can_send_hand_to_warp_and_add_matching_zamasu_from_warp() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 9729:
                return SimpleNamespace(
                    id=9729,
                    card_number="BT29-094",
                    card_name="Zamasu, Scheme",
                    card_type="UNISON",
                    card_color="black",
                    card_energy_cost="X",
                    energy_cost_int=None,
                    combo_cost_int=None,
                    combo_power_int=None,
                    power_int=15000,
                    card_skill_unstyled="[UNISON +1][Activate: Main] placeholder",
                    has_activate_main=True,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Zamasu"]',
                )
            if card_id == 972907:
                return SimpleNamespace(
                    id=972907,
                    card_number="BT29-092",
                    card_name="Fused Zamasu, Fearsome God",
                    card_type="BATTLE",
                    card_color="black",
                    card_energy_cost="7",
                    energy_cost_int=7,
                    combo_cost_int=1,
                    combo_power_int=10000,
                    power_int=30000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Zamasu"]',
                )
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="black",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9729: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_add_up_to_n_from_owner_warp_to_hand",
                    "handler_params": {
                        "max_add": 1,
                        "allowed_colors": "black",
                        "required_characters": "Zamasu",
                        "max_cost": 7,
                        "required_source_zone": "unison",
                    },
                }
            ]
        },
        skill_cost_rules={
            9729: {
                "activate_main_unison": [
                    {
                        "kind": "send_owner_hand_to_warp",
                        "amount": 1,
                    }
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=700101,
        card_id=9729,
        owner_id=1,
        card_number="BT29-094",
        card_type="UNISON",
        color="black",
        has_activate_main=True,
        markers=1,
        characters=("Zamasu",),
    )
    state.players[1].unison_area = [source]
    state.players[1].hand = [
        CardInstance(instance_id=700102, card_id=211, owner_id=1, card_type="BATTLE", color="black")
    ]
    state.players[1].warp = [
        CardInstance(instance_id=700103, card_id=972907, owner_id=1, card_type="BATTLE", color="black")
    ]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)

    activate = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, activate)
    assert len(state.players[1].hand) == 0
    assert {card.instance_id for card in state.players[1].warp} == {700102, 700103}

    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].hand) == 1
    assert state.players[1].hand[0].instance_id == 700103
    assert {card.instance_id for card in state.players[1].warp} == {700102}


def test_phase4_secret_auto_can_place_matching_deck_card_into_drop_after_hand_card_hits_drop() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 9732:
                return SimpleNamespace(
                    id=9732,
                    card_number="BT29-097",
                    card_name="SS2 Trunks, Pursuit",
                    card_type="BATTLE",
                    card_color="black",
                    card_energy_cost="1",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=15000,
                    card_skill_unstyled="",
                    has_activate_main=True,
                    has_auto=True,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=True,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Trunks"]',
                )
            if card_id == 97321:
                return SimpleNamespace(
                    id=97321,
                    card_number="BT29-098",
                    card_name="Black Target",
                    card_type="BATTLE",
                    card_color="black",
                    card_energy_cost="2",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=15000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='[]',
                )
            if card_id == 97322:
                return SimpleNamespace(
                    id=97322,
                    card_number="BT29-099",
                    card_name="Red Miss",
                    card_type="BATTLE",
                    card_color="red",
                    card_energy_cost="2",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=15000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='[]',
                )
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="black",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=5000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9732: [
                {
                    "trigger": "self_in_hand_sent_to_drop_or_warp",
                    "handler_id": "auto_place_up_to_n_from_owner_deck_to_destination_zone",
                    "handler_params": {
                        "max_targets": 1,
                        "max_power": 15000,
                        "required_card_type": "BATTLE",
                        "mirror_destination_zone": True,
                        "allowed_colors": "black,white",
                        "limit_per_turn": 1,
                        "limit_scope": "card_number",
                    },
                    "limit_per_turn": 1,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[97322, 97321] + _deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].deck = [97322, 97321] + _deck(1100)
    source = CardInstance(
        instance_id=700105,
        card_id=9732,
        owner_id=1,
        card_number="BT29-097",
        card_type="BATTLE",
        color="Black",
        power=15000,
        has_auto=True,
    )
    state.players[1].hand = [source]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=source)

    moved = state.players[1].hand.pop(0)
    state.players[1].drop.append(moved)
    engine._emit_card_placed_into_drop(state, owner_player_id=1, card=moved, source_zone="hand")

    legal = engine.get_legal_actions(state, 1)
    assert [row.action_type for row in legal] == [ActionType.DECLARE_SECRET_AUTO, ActionType.IGNORE_SECRET_AUTO]
    state = engine.apply_action(state, legal[0])

    assert any(card.card_id == 97321 for card in state.players[1].drop)
    assert not any(card.card_id == 97322 for card in state.players[1].drop)
    assert any(cp.name == "effect_auto_place_up_to_n_from_owner_deck_to_destination_zone" for cp in state.checkpoints)


def test_phase4_secret_auto_can_place_matching_deck_card_into_warp_after_hand_card_hits_warp() -> None:
    class Repo:
        def get_by_id(self, card_id, source_table: str = "cards"):
            if card_id == 9732:
                return SimpleNamespace(
                    id=9732,
                    card_number="BT29-097",
                    card_name="SS2 Trunks, Pursuit",
                    card_type="BATTLE",
                    card_color="black",
                    card_energy_cost="1",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=15000,
                    card_skill_unstyled="",
                    has_activate_main=True,
                    has_auto=True,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=True,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='["Trunks"]',
                )
            if card_id == 97323:
                return SimpleNamespace(
                    id=97323,
                    card_number="BT29-100",
                    card_name="White Target",
                    card_type="BATTLE",
                    card_color="white",
                    card_energy_cost="2",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    power_int=10000,
                    card_skill_unstyled="",
                    has_activate_main=False,
                    has_auto=False,
                    has_draw=False,
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_permanent=False,
                    has_barrier=False,
                    keywords=(),
                    card_traits_json='[]',
                    card_character_json='[]',
                )
            return SimpleNamespace(
                id=card_id,
                card_number=f"T-{card_id}",
                card_name=f"Card {card_id}",
                card_type="BATTLE",
                card_color="red",
                card_energy_cost="1",
                energy_cost_int=1,
                combo_cost_int=0,
                combo_power_int=5000,
                power_int=20000,
                card_skill_unstyled="",
                has_activate_main=False,
                has_auto=False,
                has_draw=False,
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_permanent=False,
                has_barrier=False,
                keywords=(),
                card_traits_json='[]',
                card_character_json='[]',
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            9732: [
                {
                    "trigger": "self_in_hand_sent_to_drop_or_warp",
                    "handler_id": "auto_place_up_to_n_from_owner_deck_to_destination_zone",
                    "handler_params": {
                        "max_targets": 1,
                        "max_power": 15000,
                        "required_card_type": "BATTLE",
                        "mirror_destination_zone": True,
                        "allowed_colors": "black,white",
                        "limit_per_turn": 1,
                        "limit_scope": "card_number",
                    },
                    "limit_per_turn": 1,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[97323] + _deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].deck = [97323] + _deck(1200)
    source = CardInstance(
        instance_id=700106,
        card_id=9732,
        owner_id=1,
        card_number="BT29-097",
        card_type="BATTLE",
        color="Black",
        power=15000,
        has_auto=True,
    )
    state.players[1].hand = [source]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=source)

    moved = state.players[1].hand.pop(0)
    engine._append_to_owner_warp(state, owner_player_id=1, card=moved, source_zone="hand")

    legal = engine.get_legal_actions(state, 1)
    assert [row.action_type for row in legal] == [ActionType.DECLARE_SECRET_AUTO, ActionType.IGNORE_SECRET_AUTO]
    state = engine.apply_action(state, legal[0])

    assert any(card.card_id == 97323 for card in state.players[1].warp)
    assert any(cp.name == "effect_auto_place_up_to_n_from_owner_deck_to_destination_zone" for cp in state.checkpoints)


def test_phase4_unison_activate_main_can_optionally_send_hand_to_warp_and_draw() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "Black", 0, "LEADER", "[]", "[]", False, False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False),
                6688: ("Mira, Dimensional Superpower", "Black", 0, "UNISON", "[]", "[]", True, True),
                910100: ("Warp Fodder", "Black", 1, "BATTLE", "[]", "[]", False, False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_activate_battle = data.get(
                card_id,
                ("Card", "Black", 0, "BATTLE", "[]", "[]", False, False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=has_activate_battle,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            6688: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_optional_send_owner_hand_to_warp_draw_n",
                    "handler_params": {"hand_to_warp": 1, "amount": 1, "marker_delta": 1},
                }
            ]
        },
        skill_cost_rules={
            6688: {
                "activate_main_unison": [
                    {
                        "kind": "add_markers",
                        "amount": 1,
                    }
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(
        instance_id=710001,
        card_id=6688,
        owner_id=1,
        card_number="EX15-05",
        card_type="UNISON",
        color="Black",
        has_activate_main=True,
        markers=3,
    )
    state.players[1].unison_area = [source]
    state.players[1].hand = [
        CardInstance(instance_id=710002, card_id=910100, owner_id=1, card_type="BATTLE", color="Black")
    ]
    deck_before = len(state.players[1].deck)
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)

    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, action)
    assert state.players[1].unison_area[0].markers == 4
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - 1
    assert {card.instance_id for card in state.players[1].warp} == {710002}
    assert any(cp.name == "effect_activate_optional_send_owner_hand_to_warp_draw_n" for cp in state.checkpoints)


def test_phase4_unison_activate_battle_can_gain_power_per_owner_warp_count() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "Black", 0, "LEADER", "[]", "[]", False, False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False),
                6688: ("Mira, Dimensional Superpower", "Black", 0, "UNISON", "[]", "[]", True, True),
                910101: ("Warp A", "Black", 1, "BATTLE", "[]", "[]", False, False),
                910102: ("Warp B", "Black", 1, "BATTLE", "[]", "[]", False, False),
                910103: ("Warp C", "Black", 1, "BATTLE", "[]", "[]", False, False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_activate_battle = data.get(
                card_id,
                ("Card", "Black", 0, "BATTLE", "[]", "[]", False, False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=has_activate_battle,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            6688: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "activate_gain_power_and_keyword_for_battle",
                    "handler_params": {"power_delta": "expr:owner_warp_count*5000"},
                }
            ]
        },
        skill_cost_rules={
            6688: {
                "activate_battle_unison": [
                    {
                        "kind": "remove_markers",
                        "amount": 2,
                    }
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    source = CardInstance(
        instance_id=710101,
        card_id=6688,
        owner_id=1,
        card_number="EX15-05",
        card_type="UNISON",
        color="Black",
        has_activate_battle=True,
        markers=4,
    )
    state.players[1].unison_area = [source]
    state.players[1].warp = [
        CardInstance(instance_id=710102, card_id=910101, owner_id=1, card_type="BATTLE", color="Black"),
        CardInstance(instance_id=710103, card_id=910102, owner_id=1, card_type="BATTLE", color="Black"),
        CardInstance(instance_id=710104, card_id=910103, owner_id=1, card_type="BATTLE", color="Black"),
    ]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=source)

    state.attack_context = AttackContext(
        attacker_player_id=1,
        attacker_zone="leader",
        attacker_instance_id=state.players[1].leader_area.instance_id,
        target_player_id=2,
        target_zone="leader",
        target_instance_id=state.players[2].leader_area.instance_id,
    )
    state.battle_step = BattleStep.OFFENSE

    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "unison"
    )
    state = engine.apply_action(state, action)
    assert state.players[1].unison_area[0].markers == 2
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].unison_area[0].battle_temporary_power_delta == 15000
    assert any(cp.name == "effect_activate_gain_power_and_keyword_for_battle" for cp in state.checkpoints)


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


def test_phase4_effect_catalog_registers_and_dispatches_handler() -> None:
    def catalog_handler(state, event, reg):
        state.log.append(f"catalog:{reg.effect_id}:{event.name}:{reg.source_card_id}")

    engine = RulesEngine(
        effect_rules={424242: [{"trigger": "self_played", "handler_id": "catalog_draw", "once_per_turn": True}]},
        effect_handlers={"catalog_draw": catalog_handler},
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880025, card_id=424242, owner_id=1, card_type="BATTLE", energy_cost=0, has_auto=False)
    ]

    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))

    reg = next(r for r in state.effect_registry if r.source_card_id == 424242 and r.handler_id == "catalog_draw")
    assert reg.once_per_turn is True
    assert any(entry.startswith("catalog:") for entry in state.log)


def test_phase4_catalog_auto_draw_n_uses_amount_param() -> None:
    engine = RulesEngine(
        effect_rules={
            424243: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 2},
                    "once_per_turn": False,
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    deck_before = len(state.players[1].deck)
    state.players[1].hand = [CardInstance(instance_id=880026, card_id=424243, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - 2
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_catalog_auto_ko_on_play_uses_policy_and_max_cost() -> None:
    engine = RulesEngine(
        effect_rules={
            424244: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_opponent_battle_on_play",
                    "handler_params": {"max_cost": 5, "target_policy": "lowest_power"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880027, card_id=27, owner_id=2, card_type="BATTLE", energy_cost=4, power=15000),
        CardInstance(instance_id=880028, card_id=28, owner_id=2, card_type="BATTLE", energy_cost=6, power=5000),
        CardInstance(instance_id=880029, card_id=29, owner_id=2, card_type="BATTLE", energy_cost=3, power=10000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880030, card_id=424244, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    # Eligible by max_cost are 880027 and 880029; lowest power among them is 880029.
    assert all(c.instance_id != 880029 for c in state.players[2].battle_area)
    assert any(c.instance_id == 880029 for c in state.players[2].drop)
    assert any(cp.name == "effect_auto_ko_on_play" for cp in state.checkpoints)


def test_phase4_catalog_auto_ko_on_play_uses_target_chooser_override() -> None:
    def choose_second(_state, _reg, _candidates, _policy):
        return 1

    engine = RulesEngine(
        effect_rules={
            424245: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_opponent_battle_on_play",
                    "handler_params": {"max_cost": 5, "target_policy": "lowest_power"},
                }
            ]
        },
        effect_target_chooser=choose_second,
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    # Both are eligible (cost<=5); chooser should select second candidate order-wise.
    state.players[2].battle_area = [
        CardInstance(instance_id=880101, card_id=101, owner_id=2, card_type="BATTLE", energy_cost=3, power=5000),
        CardInstance(instance_id=880102, card_id=102, owner_id=2, card_type="BATTLE", energy_cost=4, power=1000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880103, card_id=424245, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert all(c.instance_id != 880102 for c in state.players[2].battle_area)
    assert any(c.instance_id == 880102 for c in state.players[2].drop)


def test_phase4_catalog_auto_ko_on_play_target_chooser_index_is_clamped() -> None:
    def choose_out_of_range(_state, _reg, _candidates, _policy):
        return 999

    engine = RulesEngine(
        effect_rules={
            424246: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_opponent_battle_on_play",
                    "handler_params": {"max_cost": 5},
                }
            ]
        },
        effect_target_chooser=choose_out_of_range,
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880111, card_id=111, owner_id=2, card_type="BATTLE", energy_cost=1, power=5000),
        CardInstance(instance_id=880112, card_id=112, owner_id=2, card_type="BATTLE", energy_cost=2, power=6000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880113, card_id=424246, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    # Clamped to last index.
    assert all(c.instance_id != 880112 for c in state.players[2].battle_area)
    assert any(c.instance_id == 880112 for c in state.players[2].drop)


def test_phase4_catalog_auto_ko_up_to_n_on_play_uses_multi_target_chooser() -> None:
    def choose_targets(_state, _reg, _candidates, _count, _policy):
        return [2, 0]

    engine = RulesEngine(
        effect_rules={
            424247: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_up_to_n_opponent_battle_on_play",
                    "handler_params": {"max_targets": 2, "max_cost": 5, "target_policy": "first"},
                }
            ]
        },
        effect_multi_target_chooser=choose_targets,
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880121, card_id=121, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
        CardInstance(instance_id=880122, card_id=122, owner_id=2, card_type="BATTLE", energy_cost=2, power=9000),
        CardInstance(instance_id=880123, card_id=123, owner_id=2, card_type="BATTLE", energy_cost=3, power=8000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880124, card_id=424247, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    remaining = {c.instance_id for c in state.players[2].battle_area}
    assert 880121 not in remaining
    assert 880123 not in remaining
    assert any(cp.name == "effect_auto_ko_up_to_n_on_play" for cp in state.checkpoints)


def test_phase4_catalog_auto_ko_up_to_n_on_play_default_policy_lowest_power() -> None:
    engine = RulesEngine(
        effect_rules={
            424248: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_up_to_n_opponent_battle_on_play",
                    "handler_params": {"max_targets": 2, "max_cost": 5, "target_policy": "lowest_power"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880131, card_id=131, owner_id=2, card_type="BATTLE", energy_cost=1, power=7000),
        CardInstance(instance_id=880132, card_id=132, owner_id=2, card_type="BATTLE", energy_cost=2, power=3000),
        CardInstance(instance_id=880133, card_id=133, owner_id=2, card_type="BATTLE", energy_cost=3, power=5000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880134, card_id=424248, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    remaining = {c.instance_id for c in state.players[2].battle_area}
    # Lowest power two are 3000 and 5000.
    assert 880132 not in remaining
    assert 880133 not in remaining


def test_phase4_catalog_auto_power_reduce_up_to_n_on_play_uses_shared_selection() -> None:
    engine = RulesEngine(
        effect_rules={
            424249: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_power_reduce_up_to_n_on_play",
                    "handler_params": {
                        "max_targets": 1,
                        "max_cost": 5,
                        "target_policy": "lowest_power",
                        "power_delta": -6000,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880141, card_id=141, owner_id=2, card_type="BATTLE", energy_cost=3, power=5000),
        CardInstance(instance_id=880142, card_id=142, owner_id=2, card_type="BATTLE", energy_cost=2, power=9000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880143, card_id=424249, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    # Lowest-power target is reduced to <=0 and confirmative rule processing sends it to drop.
    assert all(c.instance_id != 880141 for c in state.players[2].battle_area)
    assert any(c.instance_id == 880141 for c in state.players[2].drop)
    assert any(cp.name == "effect_auto_power_reduce_up_to_n_on_play" for cp in state.checkpoints)


def test_phase4_catalog_auto_power_reduce_up_to_n_on_play_respects_multi_chooser() -> None:
    def choose_second(_state, _reg, _candidates, _count, _policy):
        return [1]

    engine = RulesEngine(
        effect_rules={
            424250: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_power_reduce_up_to_n_on_play",
                    "handler_params": {
                        "max_targets": 1,
                        "max_cost": 5,
                        "target_policy": "first",
                        "power_delta": -3000,
                    },
                }
            ]
        },
        effect_multi_target_chooser=choose_second,
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880151, card_id=151, owner_id=2, card_type="BATTLE", energy_cost=2, power=10000),
        CardInstance(instance_id=880152, card_id=152, owner_id=2, card_type="BATTLE", energy_cost=2, power=10000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880153, card_id=424250, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    p2_cards = {c.instance_id: c.power for c in state.players[2].battle_area}
    assert p2_cards[880151] == 10000
    assert p2_cards[880152] == 7000


def test_phase4_catalog_requires_leader_condition_blocks_when_unmet() -> None:
    engine = RulesEngine(
        effect_rules={
            424251: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_opponent_battle_on_play",
                    "handler_params": {"max_cost": 5, "requires_leader": "if your leader is blue card"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    # Owner leader is red; requirement says blue -> should not resolve.
    state.players[1].leader_area.color = "Red"
    state.players[2].battle_area = [
        CardInstance(instance_id=880161, card_id=161, owner_id=2, card_type="BATTLE", energy_cost=2, power=10000)
    ]
    state.players[1].hand = [CardInstance(instance_id=880162, card_id=424251, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(c.instance_id == 880161 for c in state.players[2].battle_area)
    assert all(c.instance_id != 880161 for c in state.players[2].drop)


def test_phase4_catalog_rest_mode_only_filters_targets() -> None:
    engine = RulesEngine(
        effect_rules={
            424252: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_opponent_battle_on_play",
                    "handler_params": {"max_cost": 5, "rest_mode_only": True},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880171, card_id=171, owner_id=2, card_type="BATTLE", energy_cost=2, power=10000, resting=False),
        CardInstance(instance_id=880172, card_id=172, owner_id=2, card_type="BATTLE", energy_cost=2, power=10000, resting=True),
    ]
    state.players[1].hand = [CardInstance(instance_id=880173, card_id=424252, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    remaining = {c.instance_id for c in state.players[2].battle_area}
    assert 880172 not in remaining
    assert 880171 in remaining


def test_phase4_dynamic_expr_max_targets_ko_up_to_n_uses_opponent_battle_count() -> None:
    engine = RulesEngine(
        effect_rules={
            424253: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_ko_up_to_n_opponent_battle_on_play",
                    "handler_params": {"max_targets": "expr:opponent_battle_count", "max_cost": -1, "target_policy": "first"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].battle_area = [
        CardInstance(instance_id=880181, card_id=181, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
        CardInstance(instance_id=880182, card_id=182, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
        CardInstance(instance_id=880183, card_id=183, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880184, card_id=424253, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[2].battle_area) == 0
    assert len([c for c in state.players[2].drop if c.instance_id in {880181, 880182, 880183}]) == 3


def test_phase4_dynamic_expr_max_targets_power_reduce_uses_owner_energy_count() -> None:
    engine = RulesEngine(
        effect_rules={
            424254: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_power_reduce_up_to_n_on_play",
                    "handler_params": {
                        "max_targets": "expr:owner_energy_count",
                        "max_cost": -1,
                        "target_policy": "first",
                        "power_delta": -2000,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880191, card_id=191, owner_id=1, card_type="BATTLE", energy_cost=0),
        CardInstance(instance_id=880192, card_id=192, owner_id=1, card_type="BATTLE", energy_cost=0),
    ]
    state.players[2].battle_area = [
        CardInstance(instance_id=880193, card_id=193, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
        CardInstance(instance_id=880194, card_id=194, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
        CardInstance(instance_id=880195, card_id=195, owner_id=2, card_type="BATTLE", energy_cost=1, power=10000),
    ]
    state.players[1].hand = [CardInstance(instance_id=880196, card_id=424254, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    powers = {c.instance_id: c.power for c in state.players[2].battle_area}
    assert powers[880193] == 8000
    assert powers[880194] == 8000
    assert powers[880195] == 10000


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
    assert any(cp.name == "effect_once_per_turn_blocked" for cp in state.checkpoints)
    assert any("Public effect blocked by once-per-turn" in row and f"effect_id={effect_id}" in row for row in state.log)


def test_phase4_limit_one_pending_batch_resolves_only_once_across_same_card_number() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880038, card_id=38, owner_id=1, card_number="TEST-038", card_type="BATTLE", has_auto=True),
            CardInstance(instance_id=880039, card_id=39, owner_id=1, card_number="TEST-038", card_type="BATTLE", has_auto=True),
        ]
    )
    state.effect_registry.extend(
        [
            EffectRegistration(
                effect_id=state.next_effect_id,
                owner_player_id=1,
                source_instance_id=880038,
                source_card_id=38,
                source_zone="battle",
                trigger="turn_start",
                handler_id="noop_auto",
                source_card_number="TEST-038",
                limit_per_turn=1,
            ),
            EffectRegistration(
                effect_id=state.next_effect_id + 1,
                owner_player_id=1,
                source_instance_id=880039,
                source_card_id=39,
                source_zone="battle",
                trigger="turn_start",
                handler_id="noop_auto",
                source_card_number="TEST-038",
                limit_per_turn=1,
            ),
        ]
    )
    effect_ids = {state.next_effect_id, state.next_effect_id + 1}
    state.next_effect_id += 2

    engine._emit_effect_event(state, name="turn_start", actor_player_id=1, payload={})
    engine._resolve_pending_effects(state)

    rows = [r for r in state.effect_resolutions if r.effect_id in effect_ids]
    assert sum(1 for r in rows if r.resolved and r.reason == "ok") == 1
    assert sum(1 for r in rows if (not r.resolved) and r.reason == "limit_per_turn_used") == 1
    assert any(cp.name == "effect_limit_per_turn_blocked" for cp in state.checkpoints)
    assert any("Public effect blocked by limit" in row and "limit_scope=card_number" in row for row in state.log)


def test_phase4_limit_scope_card_id_allows_distinct_card_ids_with_same_card_number() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=8800381, card_id=381, owner_id=1, card_number="TEST-381", card_type="BATTLE", has_auto=True),
            CardInstance(instance_id=8800382, card_id=382, owner_id=1, card_number="TEST-381", card_type="BATTLE", has_auto=True),
        ]
    )
    state.effect_registry.extend(
        [
            EffectRegistration(
                effect_id=state.next_effect_id,
                owner_player_id=1,
                source_instance_id=8800381,
                source_card_id=381,
                source_zone="battle",
                trigger="turn_start",
                handler_id="noop_auto",
                source_card_number="TEST-381",
                limit_per_turn=1,
                limit_scope="card_id",
            ),
            EffectRegistration(
                effect_id=state.next_effect_id + 1,
                owner_player_id=1,
                source_instance_id=8800382,
                source_card_id=382,
                source_zone="battle",
                trigger="turn_start",
                handler_id="noop_auto",
                source_card_number="TEST-381",
                limit_per_turn=1,
                limit_scope="card_id",
            ),
        ]
    )
    effect_ids = {state.next_effect_id, state.next_effect_id + 1}
    state.next_effect_id += 2

    engine._emit_effect_event(state, name="turn_start", actor_player_id=1, payload={})
    engine._resolve_pending_effects(state)

    rows = [r for r in state.effect_resolutions if r.effect_id in effect_ids]
    assert sum(1 for r in rows if r.resolved and r.reason == "ok") == 2
    assert sum(1 for r in rows if (not r.resolved) and r.reason == "limit_per_turn_used") == 0


def test_phase4_limit_scope_source_instance_allows_distinct_instances_same_card_id() -> None:
    engine = RulesEngine()
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=8800391, card_id=391, owner_id=1, card_number="TEST-391", card_type="BATTLE", has_auto=True),
            CardInstance(instance_id=8800392, card_id=391, owner_id=1, card_number="TEST-391", card_type="BATTLE", has_auto=True),
        ]
    )
    state.effect_registry.extend(
        [
            EffectRegistration(
                effect_id=state.next_effect_id,
                owner_player_id=1,
                source_instance_id=8800391,
                source_card_id=391,
                source_zone="battle",
                trigger="turn_start",
                handler_id="noop_auto",
                source_card_number="TEST-391",
                limit_per_turn=1,
                limit_scope="source_instance",
            ),
            EffectRegistration(
                effect_id=state.next_effect_id + 1,
                owner_player_id=1,
                source_instance_id=8800392,
                source_card_id=391,
                source_zone="battle",
                trigger="turn_start",
                handler_id="noop_auto",
                source_card_number="TEST-391",
                limit_per_turn=1,
                limit_scope="source_instance",
            ),
        ]
    )
    effect_ids = {state.next_effect_id, state.next_effect_id + 1}
    state.next_effect_id += 2

    engine._emit_effect_event(state, name="turn_start", actor_player_id=1, payload={})
    engine._resolve_pending_effects(state)

    rows = [r for r in state.effect_resolutions if r.effect_id in effect_ids]
    assert sum(1 for r in rows if r.resolved and r.reason == "ok") == 2
    assert sum(1 for r in rows if (not r.resolved) and r.reason == "limit_per_turn_used") == 0


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


def test_phase4_nested_pending_auto_from_effect_resolves_in_same_checkpoint() -> None:
    engine = RulesEngine(
        effect_rules={
            990051: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_drop_on_play",
                    "handler_params": {"max_targets": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    source = CardInstance(instance_id=990051, card_id=990051, owner_id=1, card_type="BATTLE", has_auto=True)
    nested = CardInstance(
        instance_id=990052,
        card_id=990052,
        owner_id=1,
        card_type="BATTLE",
        has_auto=True,
        has_draw=True,
        auto_draw_on_play=True,
    )
    state.players[1].battle_area.append(source)
    state.players[1].drop.append(nested)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    deck_before = len(state.players[1].deck)
    hand_before = len(state.players[1].hand)

    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990051, "source_card_id": 990051, "source_zone": "battle", "played_from": "hand"},
    )
    engine._resolve_pending_effects(state)

    assert len(state.pending_effects) == 0
    assert any(card.instance_id == 990052 for card in state.players[1].battle_area)
    assert len(state.players[1].hand) == hand_before + 1
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_drop_on_play" for cp in state.checkpoints)
    assert any(cp.name == "effect_auto_draw_on_play" for cp in state.checkpoints)


def test_phase4_secret_area_registration_skips_auto_rules_but_keeps_activate_rules() -> None:
    engine = RulesEngine(
        effect_rules={
            990061: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
                {"trigger": "self_activate_main", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(
        instance_id=990061,
        card_id=990061,
        owner_id=1,
        card_type="BATTLE",
        has_auto=True,
        has_activate_main=True,
    )
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)

    regs = [r for r in state.effect_registry if r.source_instance_id == 990061]
    assert any(r.trigger == "self_activate_main" for r in regs)
    assert all(r.trigger != "self_played" for r in regs)
    deferred = [row for row in state.deferred_secret_autos if row.source_instance_id == 990061]
    assert len(deferred) == 1
    assert deferred[0].trigger == "self_played"
    assert deferred[0].handler_id == "auto_draw_n"
    assert any(cp.name == "secret_auto_registration_deferred" for cp in state.checkpoints)
    assert any("Deferred secret-area auto registration" in row for row in state.log)


def test_phase4_public_registration_preserves_secret_auto_provenance_for_same_source() -> None:
    engine = RulesEngine(
        effect_rules={
            990062: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(
        instance_id=990062,
        card_id=990062,
        owner_id=1,
        card_type="BATTLE",
        has_auto=False,
    )
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    assert any(row.source_instance_id == 990062 for row in state.deferred_secret_autos)

    engine._register_card_effects(state, player_id=1, source_zone="battle", card=card)
    deferred = [row for row in state.deferred_secret_autos if row.source_instance_id == 990062]
    assert len(deferred) == 1
    assert deferred[0].source_zone == "battle"
    assert deferred[0].origin_zone == "hand"
    assert all(not (r.source_instance_id == 990062 and r.trigger == "self_played") for r in state.effect_registry)


def test_phase4_preserved_secret_auto_provenance_suppresses_public_pending_duplicate() -> None:
    engine = RulesEngine(
        effect_rules={
            9900611: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=9900611, card_id=9900611, owner_id=1, card_type="BATTLE", has_auto=False)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=card)

    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9900611, "source_card_id": 9900611, "source_zone": "battle", "played_from": "hand"},
    )

    assert not any(entry.effect_id > 0 and any(reg.effect_id == entry.effect_id and reg.source_instance_id == 9900611 for reg in state.effect_registry) for entry in state.pending_effects)
    opportunities = [row for row in state.secret_auto_opportunities if row.source_instance_id == 9900611]
    assert len(opportunities) == 1
    assert opportunities[0].origin_zone == "hand"


def test_phase4_stale_deferred_secret_auto_is_pruned_when_source_leaves_hand() -> None:
    engine = RulesEngine(
        effect_rules={
            990063: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990063, card_id=990063, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    assert any(row.source_instance_id == 990063 for row in state.deferred_secret_autos)

    state.players[1].hand.clear()
    engine._run_confirmative_rule_processing(state)

    assert all(row.source_instance_id != 990063 for row in state.deferred_secret_autos)
    assert any(cp.name == "secret_auto_registration_pruned" for cp in state.checkpoints)


def test_phase4_secret_auto_opportunity_is_created_when_matching_event_occurs() -> None:
    engine = RulesEngine(
        effect_rules={
            990064: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990064, card_id=990064, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)

    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990064, "source_card_id": 990064, "source_zone": "battle", "played_from": "hand"},
    )

    opportunities = [row for row in state.secret_auto_opportunities if row.source_instance_id == 990064]
    assert len(opportunities) == 1
    assert opportunities[0].trigger == "self_played"
    assert opportunities[0].handler_id == "auto_draw_n"
    assert opportunities[0].event_name == "card_played"
    assert any(cp.name == "secret_auto_opportunity_created" for cp in state.checkpoints)
    assert any("Secret-area auto opportunity created" in row for row in state.log)


def test_phase4_secret_auto_opportunity_is_not_created_for_unrelated_event() -> None:
    engine = RulesEngine(
        effect_rules={
            990065: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990065, card_id=990065, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)

    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": 123, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"},
    )

    assert all(row.source_instance_id != 990065 for row in state.secret_auto_opportunities)


def test_phase4_secret_auto_opportunity_exposes_declare_ignore_actions_and_declare_resolves() -> None:
    engine = RulesEngine(
        effect_rules={
            990066: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990066, card_id=990066, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990066, "source_card_id": 990066, "source_zone": "battle", "played_from": "hand"},
    )

    deck_before = len(state.players[1].deck)
    legal = engine.get_legal_actions(state, 1)
    assert [row.action_type for row in legal] == [ActionType.DECLARE_SECRET_AUTO, ActionType.IGNORE_SECRET_AUTO]
    assert engine.get_legal_actions(state, 2) == []

    state = engine.apply_action(state, legal[0])

    opportunity = next(row for row in state.secret_auto_opportunities if row.source_instance_id == 990066)
    assert opportunity.status == "declared"
    assert len(state.players[1].deck) == deck_before - 1
    assert any(row.effect_id == -opportunity.secret_auto_id and row.resolved for row in state.effect_resolutions)
    assert any(cp.name == "secret_auto_declared" for cp in state.checkpoints)
    assert any("Secret-area auto declared" in row for row in state.log)


def test_phase4_secret_auto_limit_one_declares_only_once_across_same_card_number() -> None:
    engine = RulesEngine(
        effect_rules={
            9900661: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "limit_per_turn": 1},
            ],
            9900662: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "limit_per_turn": 1},
            ],
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card_a = CardInstance(instance_id=9900661, card_id=9900661, owner_id=1, card_type="BATTLE", card_number="TEST-990066", has_auto=True)
    card_b = CardInstance(instance_id=9900662, card_id=9900662, owner_id=1, card_type="BATTLE", card_number="TEST-990066", has_auto=True)
    state.players[1].hand = [card_a, card_b]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card_a)
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card_b)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9900661, "source_card_id": 9900661, "source_zone": "battle", "played_from": "hand"},
    )
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9900662, "source_card_id": 9900662, "source_zone": "battle", "played_from": "hand"},
    )

    deck_before = len(state.players[1].deck)
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))

    opportunity_ids = {row.secret_auto_id for row in state.secret_auto_opportunities if row.source_instance_id in {9900661, 9900662}}
    rows = [r for r in state.effect_resolutions if r.effect_id in {-secret_auto_id for secret_auto_id in opportunity_ids}]
    assert sum(1 for r in rows if r.resolved and r.reason == "ok") == 1
    assert sum(1 for r in rows if (not r.resolved) and r.reason == "limit_per_turn_used") == 1
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "secret_auto_declared_limit_blocked" for cp in state.checkpoints)
    assert any(row.status == "blocked_limit_per_turn" for row in state.secret_auto_opportunities if row.source_instance_id in {9900661, 9900662})


def test_phase4_declared_secret_auto_counts_against_public_limit_key_same_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            9900663: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "limit_per_turn": 1},
            ],
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    secret_card = CardInstance(instance_id=9900663, card_id=9900663, owner_id=1, card_type="BATTLE", card_number="TEST-990067", has_auto=True)
    public_card = CardInstance(instance_id=9900664, card_id=9900664, owner_id=1, card_type="BATTLE", card_number="TEST-990067", has_auto=True)
    state.players[1].hand = [secret_card]
    state.players[1].battle_area.append(public_card)
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=secret_card)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9900663, "source_card_id": 9900663, "source_zone": "battle", "played_from": "hand"},
    )
    declare = next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO)
    state = engine.apply_action(state, declare)

    public_effect_id = state.next_effect_id
    state.effect_registry.append(
        EffectRegistration(
            effect_id=public_effect_id,
            owner_player_id=1,
            source_instance_id=9900664,
            source_card_id=9900664,
                source_zone="battle",
                trigger="self_played",
                handler_id="auto_draw_n",
                handler_params={"amount": 1, "limit_per_turn": 1, "limit_scope": "card_number"},
                source_card_number="TEST-990067",
                limit_per_turn=1,
                limit_scope="card_number",
        )
    )
    state.next_effect_id += 1
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 9900664, "source_card_id": 9900664, "source_zone": "battle", "played_from": "battle"},
    )

    engine._resolve_pending_effects(state)

    row = next(r for r in state.effect_resolutions if r.effect_id == public_effect_id)
    assert row.resolved is False
    assert row.reason == "limit_per_turn_used"


def test_phase4_secret_auto_opportunity_is_preblocked_after_limit_is_already_used() -> None:
    engine = RulesEngine(
        effect_rules={
            99006631: [
                {"trigger": "owner_leader_attacks", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "limit_per_turn": 1},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=99006631, card_id=99006631, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    event_payload = {"attacker_instance_id": state.players[1].leader_area.instance_id, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"}
    engine._emit_effect_event(state, name="attack_declared", actor_player_id=1, payload=event_payload)
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))

    engine._emit_effect_event(state, name="attack_declared", actor_player_id=1, payload=event_payload)

    latest = state.secret_auto_opportunities[-1]
    assert latest.source_instance_id == 99006631
    assert latest.status == "blocked_limit_per_turn"
    assert all(row.action_type != ActionType.DECLARE_SECRET_AUTO for row in engine.get_legal_actions(state, 1))
    assert any(cp.name == "secret_auto_opportunity_preblocked" for cp in state.checkpoints)
    assert any("Secret-area auto opportunity preblocked" in row and "blocked_limit_per_turn" in row for row in state.log)


def test_phase4_secret_auto_once_per_turn_declares_only_once_for_same_source() -> None:
    engine = RulesEngine(
        effect_rules={
            9900671: [
                {"trigger": "owner_leader_attacks", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "once_per_turn": True},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=9900671, card_id=9900671, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": state.players[1].leader_area.instance_id, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"},
    )
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": state.players[1].leader_area.instance_id, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"},
    )

    deck_before = len(state.players[1].deck)
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))

    secret_auto_id = next(row.secret_auto_id for row in state.secret_auto_opportunities if row.source_instance_id == 9900671)
    rows = [r for r in state.effect_resolutions if r.effect_id == -secret_auto_id]
    assert sum(1 for r in rows if r.resolved and r.reason == "ok") == 1
    assert sum(1 for r in rows if (not r.resolved) and r.reason == "once_per_turn_used") == 1
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "secret_auto_declared_once_per_turn_blocked" for cp in state.checkpoints)
    assert any(row.status == "blocked_once_per_turn" for row in state.secret_auto_opportunities if row.source_instance_id == 9900671)


def test_phase4_secret_auto_opportunity_is_preblocked_after_once_per_turn_is_already_used() -> None:
    engine = RulesEngine(
        effect_rules={
            99006711: [
                {"trigger": "owner_leader_attacks", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "once_per_turn": True},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=99006711, card_id=99006711, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    event_payload = {"attacker_instance_id": state.players[1].leader_area.instance_id, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"}
    engine._emit_effect_event(state, name="attack_declared", actor_player_id=1, payload=event_payload)
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))

    engine._emit_effect_event(state, name="attack_declared", actor_player_id=1, payload=event_payload)

    latest = state.secret_auto_opportunities[-1]
    assert latest.source_instance_id == 99006711
    assert latest.status == "blocked_once_per_turn"
    assert all(row.action_type != ActionType.DECLARE_SECRET_AUTO for row in engine.get_legal_actions(state, 1))
    assert any(cp.name == "secret_auto_opportunity_preblocked" for cp in state.checkpoints)
    assert any("Secret-area auto opportunity preblocked" in row and "blocked_once_per_turn" in row for row in state.log)


def test_phase4_declared_secret_auto_counts_against_public_once_per_turn_same_source() -> None:
    engine = RulesEngine(
        effect_rules={
            9900672: [
                {"trigger": "owner_leader_attacks", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}, "once_per_turn": True},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=9900672, card_id=9900672, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": state.players[1].leader_area.instance_id, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"},
    )
    state = engine.apply_action(state, next(row for row in engine.get_legal_actions(state, 1) if row.action_type == ActionType.DECLARE_SECRET_AUTO))

    public_effect_id = state.next_effect_id
    state.effect_registry.append(
        EffectRegistration(
            effect_id=public_effect_id,
            owner_player_id=1,
            source_instance_id=9900672,
            source_card_id=9900672,
            source_zone="hand",
            trigger="owner_leader_attacks",
            handler_id="auto_draw_n",
            handler_params={"amount": 1},
            source_card_number="",
            once_per_turn=True,
        )
    )
    state.next_effect_id += 1
    engine._emit_effect_event(
        state,
        name="attack_declared",
        actor_player_id=1,
        payload={"attacker_instance_id": state.players[1].leader_area.instance_id, "attacker_zone": "leader", "target_player_id": 2, "target_zone": "leader"},
    )

    engine._resolve_pending_effects(state)

    row = next(r for r in state.effect_resolutions if r.effect_id == public_effect_id)
    assert row.resolved is False
    assert row.reason == "once_per_turn_used"


def test_phase4_secret_auto_ignore_marks_status_without_resolving() -> None:
    engine = RulesEngine(
        effect_rules={
            990067: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990067, card_id=990067, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990067, "source_card_id": 990067, "source_zone": "battle", "played_from": "hand"},
    )

    deck_before = len(state.players[1].deck)
    ignore = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.IGNORE_SECRET_AUTO)
    state = engine.apply_action(state, ignore)

    opportunity = next(row for row in state.secret_auto_opportunities if row.source_instance_id == 990067)
    assert opportunity.status == "ignored"
    assert len(state.players[1].deck) == deck_before
    assert not any(row.effect_id == -opportunity.secret_auto_id for row in state.effect_resolutions)
    assert any(cp.name == "secret_auto_ignored" for cp in state.checkpoints)


def test_phase4_secret_auto_actions_are_ordered_turn_player_first() -> None:
    engine = RulesEngine(
        effect_rules={
            990068: [{"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}}],
            990069: [{"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}}],
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].hand = [CardInstance(instance_id=990068, card_id=990068, owner_id=1, card_type="BATTLE", has_auto=True)]
    state.players[2].hand = [CardInstance(instance_id=990069, card_id=990069, owner_id=2, card_type="BATTLE", has_auto=True)]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=state.players[1].hand[0])
    engine._register_card_effects(state, player_id=2, source_zone="hand", card=state.players[2].hand[0])

    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990068, "source_card_id": 990068, "source_zone": "battle", "played_from": "hand"},
    )
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=2,
        payload={"source_instance_id": 990069, "source_card_id": 990069, "source_zone": "battle", "played_from": "hand"},
    )

    legal_p1 = engine.get_legal_actions(state, 1)
    assert [row.action_type for row in legal_p1] == [ActionType.DECLARE_SECRET_AUTO, ActionType.IGNORE_SECRET_AUTO]
    assert engine.get_legal_actions(state, 2) == []

    state = engine.apply_action(state, next(a for a in legal_p1 if a.action_type == ActionType.IGNORE_SECRET_AUTO))
    legal_p2 = engine.get_legal_actions(state, 2)
    assert [row.action_type for row in legal_p2] == [ActionType.DECLARE_SECRET_AUTO, ActionType.IGNORE_SECRET_AUTO]


def test_phase4_stale_pending_secret_auto_opportunity_is_pruned_when_source_leaves_zone() -> None:
    engine = RulesEngine(
        effect_rules={
            990070: [
                {"trigger": "self_played", "handler_id": "auto_draw_n", "handler_params": {"amount": 1}},
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    card = CardInstance(instance_id=990070, card_id=990070, owner_id=1, card_type="BATTLE", has_auto=True)
    state.players[1].hand = [card]
    engine._register_card_effects(state, player_id=1, source_zone="hand", card=card)
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 990070, "source_card_id": 990070, "source_zone": "battle", "played_from": "hand"},
    )
    assert any(row.source_instance_id == 990070 for row in state.secret_auto_opportunities)

    state.players[1].hand.clear()
    engine._run_confirmative_rule_processing(state)

    assert all(row.source_instance_id != 990070 for row in state.secret_auto_opportunities)
    assert any(cp.name == "secret_auto_opportunity_pruned" for cp in state.checkpoints)


def test_phase4_pending_effects_resolve_turn_player_first_for_simultaneous_public_triggers() -> None:
    def ordered_handler(state, event, reg):
        state.log.append(f"ordered:{reg.owner_player_id}:{event.event_id}")

    engine = RulesEngine(effect_handlers={"noop_auto": ordered_handler})
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].battle_area.append(CardInstance(instance_id=990071, card_id=71, owner_id=1, card_type="BATTLE"))
    state.players[2].battle_area.append(CardInstance(instance_id=990072, card_id=72, owner_id=2, card_type="BATTLE"))
    state.effect_registry.extend(
        [
            EffectRegistration(
                effect_id=state.next_effect_id,
                owner_player_id=1,
                source_instance_id=990071,
                source_card_id=71,
                source_zone="battle",
                trigger="owner_field_extra_placed",
                handler_id="noop_auto",
            ),
            EffectRegistration(
                effect_id=state.next_effect_id + 1,
                owner_player_id=2,
                source_instance_id=990072,
                source_card_id=72,
                source_zone="battle",
                trigger="owner_field_extra_placed",
                handler_id="noop_auto",
            ),
        ]
    )
    state.next_effect_id += 2

    engine._emit_effect_event(state, name="field_extra_placed", actor_player_id=1, payload={})
    engine._resolve_pending_effects(state)

    ordered = [row for row in state.log if row.startswith("ordered:")]
    assert ordered[0].startswith(f"ordered:{state.active_player}:")
    assert ordered[1].startswith(f"ordered:{engine._opponent_of(state.active_player)}:")


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


def test_phase4_combo_declared_triggers_self_comboed_draw_rule() -> None:
    engine = RulesEngine(
        effect_rules={
            424255: [
                {
                    "trigger": "self_comboed",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
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
        CardInstance(instance_id=880201, card_id=201, owner_id=1, card_type="BATTLE", energy_cost=0, power=15000)
    )
    state.players[1].hand = [
        CardInstance(instance_id=880203, card_id=424255, owner_id=1, card_type="BATTLE", combo_cost=0, combo_power=5000)
    ]
    deck_before = len(state.players[1].deck)

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo)

    assert len(state.players[1].deck) == deck_before - 1
    assert any(evt.name == "card_comboed" for evt in state.effect_events)
    assert any(res.resolved and res.reason == "ok" for res in state.effect_resolutions)


def test_phase4_combo_draw_rule_respects_leader_and_sparking_requirements() -> None:
    engine = RulesEngine(
        effect_rules={
            424256: [
                {
                    "trigger": "self_comboed",
                    "handler_id": "auto_draw_n",
                    "handler_params": {
                        "amount": 1,
                        "requires_leader": "if your leader card is red",
                        "min_owner_drop": 5,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].leader_area.color = "Red"
    state.players[1].battle_area.append(
        CardInstance(instance_id=880211, card_id=201, owner_id=1, card_type="BATTLE", energy_cost=0, power=15000)
    )
    state.players[1].hand = [
        CardInstance(instance_id=880212, card_id=424256, owner_id=1, card_type="BATTLE", combo_cost=0, combo_power=5000)
    ]
    deck_before = len(state.players[1].deck)

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo)
    assert len(state.players[1].deck) == deck_before

    state.players[1].drop = [CardInstance(instance_id=880300 + i, card_id=300 + i, owner_id=1, card_type="BATTLE") for i in range(5)]
    state.players[1].hand = [
        CardInstance(instance_id=880213, card_id=424256, owner_id=1, card_type="BATTLE", combo_cost=0, combo_power=5000)
    ]
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo)
    assert len(state.players[1].deck) == deck_before - 1


def test_phase4_combo_battle_end_can_play_self_from_combo_to_battle_resting() -> None:
    engine = RulesEngine(
        effect_rules={
            424256: [
                {
                    "trigger": "self_comboed_battle_end",
                    "handler_id": "auto_play_self_from_combo_on_battle_end",
                    "handler_params": {"resting": True},
                }
            ]
        }
    )
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
        CardInstance(instance_id=880211, card_id=211, owner_id=1, card_type="BATTLE", energy_cost=0, power=15000)
    )
    state.players[1].hand = [
        CardInstance(instance_id=880212, card_id=424256, owner_id=1, card_type="BATTLE", combo_cost=0, combo_power=5000)
    ]

    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND)
    state = engine.apply_action(state, combo)
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))

    played = next((c for c in state.players[1].battle_area if c.instance_id == 880212), None)
    assert played is not None
    assert played.resting is True
    assert all(c.instance_id != 880212 for c in state.players[1].combo_area)
    assert any(cp.name == "effect_auto_play_self_from_combo_on_battle_end" for cp in state.checkpoints)


def test_phase4_turn_end_switch_self_active_handler() -> None:
    engine = RulesEngine(
        effect_rules={
            424257: [
                {
                    "trigger": "turn_end",
                    "handler_id": "auto_switch_self_active_on_turn_end",
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880221, card_id=424257, owner_id=1, card_type="BATTLE", energy_cost=0, resting=False)
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state.players[1].battle_area[0].resting = True

    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state.players[1].battle_area[0].resting is False
    assert any(cp.name == "effect_auto_switch_self_active_on_turn_end" for cp in state.checkpoints)


def test_phase4_play_top_deck_add_if_color_on_play_matches_and_adds_to_hand() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            color_map = {
                1: "Red",
                2: "Blue",
                900001: "Black",
                424258: "Black",
            }
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color_map.get(card_id, "Red"),
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
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

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424258: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_top_deck_add_if_color_on_play",
                    "handler_params": {"required_color": "black", "move_to_bottom_on_fail": True},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900001] + _deck(1000, 59),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].deck = [900001] + state.players[1].deck
    deck_before = len(state.players[1].deck)
    state.players[1].hand = [CardInstance(instance_id=880231, card_id=424258, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - 1
    assert any(c.card_id == 900001 for c in state.players[1].hand)
    assert any(cp.name == "effect_auto_top_deck_add_if_color_on_play" for cp in state.checkpoints)


def test_phase4_play_top_deck_add_if_color_on_play_miss_moves_top_to_bottom() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            color_map = {
                1: "Red",
                2: "Blue",
                900002: "Red",
                900003: "Blue",
                424259: "Black",
            }
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color_map.get(card_id, "Red"),
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
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

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424259: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_top_deck_add_if_color_on_play",
                    "handler_params": {"required_color": "black", "move_to_bottom_on_fail": True},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900002, 900003] + _deck(1000, 58),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].deck = [900002, 900003] + state.players[1].deck
    first_before = state.players[1].deck[0]
    state.players[1].hand = [CardInstance(instance_id=880241, card_id=424259, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].deck[0] == 900003
    assert state.players[1].deck[-1] == first_before
    assert any(cp.name == "effect_auto_top_deck_bottom_on_fail" for cp in state.checkpoints)


def test_phase4_self_activate_main_draw_rule_resolves_on_skill_activation() -> None:
    engine = RulesEngine(
        effect_rules={
            1: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.has_activate_main = True
    deck_before = len(state.players[1].deck)
    act = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "leader")
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - 1
    assert any(evt.name == "skill_activated" for evt in state.effect_events)
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_owner_black_battle_played_from_warp_triggers_wormhole_gain_handler() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            color_map = {1: "Black", 2: "Blue", 900100: "Black"}
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color_map.get(card_id, "Red"),
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
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

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            1: [
                {
                    "trigger": "owner_battle_played_from_warp",
                    "handler_id": "auto_gain_wormhole_on_owner_black_battle_played_from_warp",
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=1,
        payload={"source_instance_id": 999001, "source_card_id": 900100, "source_zone": "battle", "played_from": "warp"},
    )
    engine._resolve_pending_effects(state)
    assert any(cp.name == "effect_auto_gain_wormhole_on_owner_black_battle_played_from_warp" for cp in state.checkpoints)
    assert any("wormhole_gain" in line for line in state.log)


def test_phase4_self_activate_battle_draw_n_resolves_on_skill_activated_event() -> None:
    engine = RulesEngine(
        effect_rules={
            424287: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    src = CardInstance(instance_id=880105, card_id=424287, owner_id=1, card_type="BATTLE", energy_cost=0)
    state.players[1].battle_area.append(src)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=src)
    deck_before = len(state.players[1].deck)
    hand_before = len(state.players[1].hand)
    engine._emit_effect_event(
        state,
        name="skill_activated",
        actor_player_id=1,
        payload={"source_instance_id": 880105, "source_card_id": 424287, "source_zone": "battle", "skill_kind": "activate_battle"},
    )
    engine._resolve_pending_effects(state)
    assert len(state.players[1].deck) == deck_before - 1
    assert len(state.players[1].hand) == hand_before + 1
    assert any(cp.name == "effect_auto_draw_n" for cp in state.checkpoints)


def test_phase4_owner_opponent_skill_plays_overcost_battle_can_rest_self_and_reduce_power() -> None:
    engine = RulesEngine(
        effect_rules={
            424285: [
                {
                    "trigger": "owner_opponent_skill_plays_overcost_battle",
                    "handler_id": "auto_rest_self_on_owner_opponent_skill_play_overcost_battle_reduce_power",
                    "handler_params": {"power_delta": -10000},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].battle_area.append(
        CardInstance(instance_id=880097, card_id=424285, owner_id=1, card_type="BATTLE", energy_cost=0, resting=False)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    state.players[2].energy = [
        CardInstance(instance_id=880098, card_id=920001, owner_id=2, color="Blue", resting=False),
        CardInstance(instance_id=880099, card_id=920002, owner_id=2, color="Blue", resting=False),
    ]
    state.players[2].battle_area.append(
        CardInstance(instance_id=880100, card_id=920003, owner_id=2, card_type="BATTLE", energy_cost=4, power=25000)
    )
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=2,
        payload={"source_instance_id": 880100, "source_card_id": 920003, "source_zone": "battle", "played_from": "deck"},
    )
    engine._resolve_pending_effects(state)
    assert state.players[1].battle_area[0].resting is True
    assert state.players[2].battle_area[0].power == 15000
    assert any(cp.name == "effect_auto_rest_self_on_owner_opponent_skill_play_overcost_battle_reduce_power" for cp in state.checkpoints)


def test_phase4_owner_opponent_skill_plays_overcost_battle_can_rest_self_and_switch_target_rest() -> None:
    engine = RulesEngine(
        effect_rules={
            424286: [
                {
                    "trigger": "owner_opponent_skill_plays_overcost_battle",
                    "handler_id": "auto_rest_self_on_owner_opponent_skill_play_overcost_battle_switch_target_rest",
                    "handler_params": {},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state.players[1].battle_area.append(
        CardInstance(instance_id=880101, card_id=424286, owner_id=1, card_type="BATTLE", energy_cost=0, resting=False)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    state.players[2].energy = [
        CardInstance(instance_id=880102, card_id=920011, owner_id=2, color="Blue", resting=False),
        CardInstance(instance_id=880103, card_id=920012, owner_id=2, color="Blue", resting=False),
    ]
    state.players[2].battle_area.append(
        CardInstance(instance_id=880104, card_id=920013, owner_id=2, card_type="BATTLE", energy_cost=4, power=25000, resting=False)
    )
    engine._emit_effect_event(
        state,
        name="card_played",
        actor_player_id=2,
        payload={"source_instance_id": 880104, "source_card_id": 920013, "source_zone": "battle", "played_from": "deck"},
    )
    engine._resolve_pending_effects(state)
    assert state.players[1].battle_area[0].resting is True
    assert state.players[2].battle_area[0].resting is True
    assert any(cp.name == "effect_auto_rest_self_on_owner_opponent_skill_play_overcost_battle_switch_target_rest" for cp in state.checkpoints)


def test_phase4_played_add_top_deck_to_energy_respects_requires_mono_energy() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            color_map = {1: "Blue", 2: "Blue", 900200: "Red", 424261: "Blue"}
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color_map.get(card_id, "Blue"),
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
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

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424261: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_add_top_deck_to_energy_rest_on_play",
                    "handler_params": {"requires_mono_energy": "blue"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900200] + _deck(1000, 59),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    # Break mono-blue requirement.
    state.players[1].energy = [CardInstance(instance_id=990301, card_id=900200, owner_id=1, card_type="BATTLE", color="Red")]
    energy_before = len(state.players[1].energy)
    state.players[1].hand = [CardInstance(instance_id=880251, card_id=424261, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].energy) == energy_before


def test_phase4_played_look_top_add_up_to_one_to_hand_on_play() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            payload = {
                1: ("Blue", 0),
                2: ("Blue", 0),
                900401: ("Green", 3),
                900402: ("Red", 2),
                900403: ("Yellow", 5),
                424262: ("Yellow", 2),
            }
            color, cost = payload.get(card_id, ("Blue", 0))
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
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

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424262: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_look_top_add_up_to_one_to_hand_on_play",
                    "handler_params": {
                        "look_count": 3,
                        "max_add": 1,
                        "max_cost": 4,
                        "allowed_colors": "green,yellow",
                        "required_card_type": "BATTLE",
                        "requires_played_from": "hand",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900402, 900401, 900403] + _deck(1000, 57),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].deck = [900402, 900401, 900403] + state.players[1].deck
    state.players[1].hand = [CardInstance(instance_id=880261, card_id=424262, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    # Green cost-3 match in top 3 should be added to hand.
    assert any(c.card_id == 900401 for c in state.players[1].hand)
    assert all(c.card_id != 424262 for c in state.players[1].hand)
    assert any(cp.name == "effect_auto_look_top_add_up_to_one_to_hand_on_play" for cp in state.checkpoints)


def test_phase4_played_look_top_add_up_to_two_to_hand_on_play() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            payload = {
                1: ("Blue", 0),
                2: ("Blue", 0),
                900411: ("Green", 3),
                900412: ("Yellow", 4),
                900413: ("Red", 2),
                424263: ("Yellow", 2),
            }
            color, cost = payload.get(card_id, ("Blue", 0))
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
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

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424263: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_look_top_add_up_to_one_to_hand_on_play",
                    "handler_params": {
                        "look_count": 4,
                        "max_add": 2,
                        "max_cost": 6,
                        "allowed_colors": "green,yellow",
                        "required_card_type": "BATTLE",
                        "requires_played_from": "hand",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900413, 900411, 900412] + _deck(1000, 57),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].deck = [900413, 900411, 900412] + state.players[1].deck
    state.players[1].hand = [CardInstance(instance_id=880271, card_id=424263, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    hand_ids = {c.card_id for c in state.players[1].hand}
    assert 900411 in hand_ids
    assert 900412 in hand_ids


def test_phase4_self_ko_trigger_reduces_opponent_unison_power() -> None:
    engine = RulesEngine(
        effect_rules={
            424264: [
                {
                    "trigger": "self_koed",
                    "handler_id": "auto_power_reduce_opponent_unison_on_self_ko",
                    "handler_params": {"max_targets": 1, "power_delta": -10000, "target_policy": "first"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880281, card_id=424264, owner_id=1, card_type="BATTLE", energy_cost=0)
    state.players[1].battle_area.append(source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    state.players[2].unison_area = [
        CardInstance(instance_id=880282, card_id=282, owner_id=2, card_type="UNISON", energy_cost=3, power=12000, markers=2)
    ]

    engine._ko_card(state, player_id=1, zone="battle", instance_id=880281)
    engine._resolve_pending_effects(state)

    assert state.players[2].unison_area[0].power == 2000
    assert any(cp.name == "effect_auto_power_reduce_opponent_unison_on_self_ko" for cp in state.checkpoints)


def test_phase4_turn_end_switch_up_to_n_owner_energy_active() -> None:
    engine = RulesEngine(
        effect_rules={
            424265: [
                {
                    "trigger": "turn_end",
                    "handler_id": "auto_switch_up_to_n_owner_energy_active_on_turn_end",
                    "handler_params": {"max_targets": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=880291, card_id=424265, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state.players[1].energy = [
        CardInstance(instance_id=880292, card_id=292, owner_id=1, card_type="BATTLE", color="Blue", resting=True),
        CardInstance(instance_id=880293, card_id=293, owner_id=1, card_type="BATTLE", color="Blue", resting=True),
    ]
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert sum(1 for e in state.players[1].energy if not e.resting) == 1
    assert any(cp.name == "effect_auto_switch_up_to_n_owner_energy_active_on_turn_end" for cp in state.checkpoints)


def test_phase4_turn_end_switch_up_to_n_owner_energy_active_multicolor_filter() -> None:
    engine = RulesEngine(
        effect_rules={
            424266: [
                {
                    "trigger": "turn_end",
                    "handler_id": "auto_switch_up_to_n_owner_energy_active_on_turn_end",
                    "handler_params": {"max_targets": 2, "allowed_colors": "blue,yellow", "requires_multicolor": True},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=880301, card_id=424266, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state.players[1].energy = [
        CardInstance(instance_id=880302, card_id=302, owner_id=1, card_type="BATTLE", color="Blue/Yellow", resting=True),
        CardInstance(instance_id=880303, card_id=303, owner_id=1, card_type="BATTLE", color="Blue", resting=True),
        CardInstance(instance_id=880304, card_id=304, owner_id=1, card_type="BATTLE", color="Yellow/Blue", resting=True),
    ]
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    by_id = {e.instance_id: e.resting for e in state.players[1].energy}
    assert by_id[880302] is False
    assert by_id[880304] is False
    assert by_id[880303] is True


def test_phase4_self_played_can_play_matching_card_from_owner_deck() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", 15000),
                2: ("Blue", 15000),
                900501: ("Red", 9000),
                900502: ("Blue", 8000),
                900503: ("Red", 15000),
                424267: ("Blue", 15000),
            }
            color, power = data.get(card_id, ("Blue", 15000))
            return SimpleNamespace(
                power_int=power,
                card_type="BATTLE",
                card_color=color,
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
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

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424267: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_deck_on_play",
                    "handler_params": {
                        "max_targets": 1,
                        "max_power": 10000,
                        "allowed_colors": "red",
                        "requires_played_from": "hand",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900502, 900501, 900503] + _deck(1000, 57),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].deck = [900502, 900501, 900503] + state.players[1].deck
    state.players[1].hand = [CardInstance(instance_id=880311, card_id=424267, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(c.card_id == 900501 for c in state.players[1].battle_area)
    assert all(c.card_id != 900503 for c in state.players[1].battle_area)
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_deck_on_play" for cp in state.checkpoints)


def test_phase4_self_comboed_can_play_matching_card_from_owner_hand() -> None:
    engine = RulesEngine(
        effect_rules={
            424268: [
                {
                    "trigger": "self_comboed",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_on_self_combo",
                    "handler_params": {"max_targets": 1, "max_cost": 5, "allowed_colors": "blue", "rest_mode": True},
                }
            ]
        }
    )
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
        CardInstance(instance_id=880321, card_id=321, owner_id=1, card_type="BATTLE", energy_cost=0, power=15000)
    )
    state.players[1].hand = [
        CardInstance(instance_id=880322, card_id=424268, owner_id=1, card_type="BATTLE", combo_cost=0, combo_power=5000),
        CardInstance(instance_id=880323, card_id=323, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=5),
        CardInstance(instance_id=880324, card_id=324, owner_id=1, card_type="BATTLE", color="Red", energy_cost=3),
    ]
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    combo = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.COMBO_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, combo)

    played = next((c for c in state.players[1].battle_area if c.instance_id == 880323), None)
    assert played is not None and played.resting is True
    assert all(c.instance_id != 880324 for c in state.players[1].battle_area)
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_hand_on_self_combo" for cp in state.checkpoints)


def test_phase4_self_played_can_gain_control_of_opponent_unison() -> None:
    engine = RulesEngine(
        effect_rules={
            424269: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_gain_control_opponent_unison_on_play",
                    "handler_params": {"max_targets": 1, "target_policy": "first"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].unison_area = [
        CardInstance(instance_id=880331, card_id=331, owner_id=2, card_type="UNISON", markers=2)
    ]
    state.players[1].hand = [CardInstance(instance_id=880332, card_id=424269, owner_id=1, card_type="BATTLE", energy_cost=0)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[2].unison_area) == 0
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].instance_id == 880331
    assert state.players[1].unison_area[0].owner_id == 1
    assert any(cp.name == "effect_auto_gain_control_opponent_unison_on_play" for cp in state.checkpoints)


def test_phase4_self_activate_main_search_add_then_discard() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", 0),
                2: ("Blue", 0),
                900601: ("Green/Yellow", 3),
                900602: ("Red", 2),
                900603: ("Yellow/Green", 4),
            }
            color, cost = data.get(card_id, ("Blue", 0))
            return SimpleNamespace(
                power_int=15000,
                card_type="BATTLE",
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
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

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            1: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "auto_look_top_add_up_to_one_to_hand_on_play",
                    "handler_params": {
                        "look_count": 3,
                        "max_add": 1,
                        "allowed_colors": "green,yellow",
                        "discard_after_add": 1,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900602, 900601, 900603] + _deck(1000, 57),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.has_activate_main = True
    state.players[1].deck = [900602, 900601, 900603] + state.players[1].deck
    state.players[1].hand = [CardInstance(instance_id=880341, card_id=341, owner_id=1, card_type="BATTLE", energy_cost=0)]
    act = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "leader")
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    hand_ids = {c.card_id for c in state.players[1].hand}
    assert 900601 in hand_ids
    assert 341 not in hand_ids
    assert any(cp.name == "effect_auto_look_top_add_up_to_one_to_hand_on_play" for cp in state.checkpoints)


def test_phase4_self_activate_main_search_by_name_token_and_bottom_rest() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "Black", 0),
                2: ("Other Leader", "Blue", 0),
                900611: ("SS4 Son Goku", "Black", 3),
                900612: ("SS4 Vegeta", "Black", 4),
                900613: ("Regular Bardock", "Black", 2),
                990001: ("Bottom Me", "Red", 1),
            }
            name, color, cost = data.get(card_id, ("Card", "Black", 0))
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type="BATTLE",
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
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
                card_traits_json="[]",
                card_character_json="[]",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            1: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "auto_look_top_add_up_to_one_to_hand_on_play",
                    "handler_params": {
                        "look_count": 3,
                        "max_add": 2,
                        "allowed_colors": "black",
                        "required_name_contains": "SS4",
                        "move_unpicked_to_bottom": True,
                        "bottom_deck_after_add": 1,
                        "bottom_deck_after_add_exact_add_count": 2,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[900611, 900613, 900612] + _deck(1000, 57),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.has_activate_main = True
    state.players[1].hand = [CardInstance(instance_id=880361, card_id=990001, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[1].deck = [900611, 900613, 900612] + state.players[1].deck
    act = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "leader")
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    hand_ids = [c.card_id for c in state.players[1].hand]
    assert 900611 in hand_ids
    assert 900612 in hand_ids
    assert 990001 not in hand_ids
    assert state.players[1].deck[-2:] == [900613, 990001]
    assert any(cp.name == "effect_auto_look_top_add_up_to_one_to_hand_on_play" for cp in state.checkpoints)


def test_phase4_activate_main_play_self_from_hand_with_requirements() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Power Wish Leader", "Blue", 0, '["Power Wish"]', "[]"),
                2: ("Other Leader", "Red", 0, "[]", "[]"),
                900701: ("Power Wish Body", "Blue", 3, '["Power Wish"]', '["Son Goku"]'),
            }
            name, color, cost, traits_json, characters_json = data.get(card_id, ("Card", "Blue", 0, "[]", "[]"))
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type="BATTLE",
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=card_id == 900701,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900701: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_hand",
                    "handler_params": {
                        "required_leader_traits": "Power Wish",
                        "min_owner_energy": 3,
                        "requires_no_owner_battle": True,
                        "requires_no_opponent_battle": True,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880701, card_id=1001, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880702, card_id=1002, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880703, card_id=1003, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
    ]
    state.players[1].hand = [
        CardInstance(instance_id=880704, card_id=900701, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=3, has_activate_main=True)
    ]
    state.players[1].leader_area.has_activate_main = False
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand"
    )
    state = engine.apply_action(state, act)
    assert state.counter_window is not None
    assert state.counter_window.kind == "activate_main"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None
    assert state.counter_window.kind == "play"
    assert any(card.card_id == 900701 for card in state.players[1].hand)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert not state.players[1].hand
    assert any(card.card_id == 900701 for card in state.players[1].battle_area)
    assert any(cp.name == "counter_timing_play_from_skill" for cp in state.checkpoints)


def test_phase4_activate_main_play_self_from_hand_uses_hidden_mode_cost_reduction() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            if card_id == 1:
                return SimpleNamespace(
                    card_name="Universe 7 Leader",
                    power_int=10000,
                    card_type="LEADER",
                    card_color="White",
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
                    card_traits_json='["Universe 7"]',
                    card_character_json="[]",
                )
            if card_id == 900706:
                return SimpleNamespace(
                    card_name="Hidden Cost Reducer",
                    power_int=15000,
                    card_type="BATTLE",
                    card_color="White",
                    energy_cost_int=2,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_counter_attack=False,
                    has_counter_play=False,
                    has_activate_main=True,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=True,
                    has_draw=False,
                    max_draw=None,
                    has_barrier=False,
                    z_energy_cost=None,
                    card_energy_cost="2",
                    card_skill_unstyled=(
                        "[Activate: Main] Play this card from your hand.<br>"
                        "[Permanent] If your Leader is a white ≪Universe 7≫ card and you have a Hidden Mode card in your Battle Area, "
                        "reduce the energy cost of this card in your hand by 2."
                    ),
                    card_traits_json="[]",
                    card_character_json="[]",
                )
            return SimpleNamespace(
                card_name="Card",
                power_int=15000,
                card_type="LEADER" if card_id == 2 else "BATTLE",
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
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost="0",
                card_skill_unstyled="",
                card_traits_json="[]",
                card_character_json="[]",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900706: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_hand",
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = []
    state.players[1].hand = [engine._create_card_instance(next_instance_id=880706, card_id=900706, owner_id=1)]
    state.players[1].battle_area.append(
        CardInstance(instance_id=880707, card_id=113, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True)
    )
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand"
    )
    state = engine.apply_action(state, act)
    assert state.counter_window is not None
    assert state.counter_window.kind == "activate_main"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None
    assert state.counter_window.kind == "play"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert not state.players[1].hand
    assert any(card.card_id == 900706 for card in state.players[1].battle_area)


def test_phase4_activate_main_play_self_from_hand_unison_opens_second_counter_timing() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Power Wish Leader", "Blue", 0, "LEADER", '["Power Wish"]', "[]", False, False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False),
                900702: ("Power Wish Unison", "Blue", 3, "UNISON", "[]", "[]", True, True),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_auto = data.get(
                card_id,
                ("Card", "Blue", 0, "BATTLE", "[]", "[]", False, False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=has_auto,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900702: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_hand",
                    "handler_params": {
                        "required_leader_traits": "Power Wish",
                        "min_owner_energy": 3,
                        "markers": 1,
                    },
                },
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                },
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880711, card_id=1001, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880712, card_id=1002, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880713, card_id=1003, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
    ]
    deck_before = len(state.players[1].deck)
    state.players[1].hand = [
        CardInstance(instance_id=880714, card_id=900702, owner_id=1, card_type="UNISON", color="Blue", energy_cost=3, has_activate_main=True, has_auto=True)
    ]
    state.players[1].leader_area.has_activate_main = False
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand"
    )
    state = engine.apply_action(state, act)
    assert state.counter_window is not None and state.counter_window.kind == "activate_main"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None and state.counter_window.kind == "play"
    assert any(card.card_id == 900702 for card in state.players[1].hand)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert all(card.card_id != 900702 for card in state.players[1].hand)
    assert any(card.card_id == 900702 for card in state.players[1].unison_area)
    assert state.players[1].unison_area[0].markers == 1
    secret_auto = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.DECLARE_SECRET_AUTO)
    state = engine.apply_action(state, secret_auto)
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "counter_timing_play_from_skill" for cp in state.checkpoints)
    assert any(cp.name == "main_play_unison" for cp in state.checkpoints)


def test_phase4_activate_main_play_self_from_hand_unison_replaces_existing_unison() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Power Wish Leader", "Blue", 0, "LEADER", '["Power Wish"]', "[]", False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False),
                900703: ("Power Wish Unison", "Blue", 3, "UNISON", "[]", "[]", True),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main = data.get(
                card_id,
                ("Card", "Blue", 0, "BATTLE", "[]", "[]", False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900703: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_hand",
                    "handler_params": {
                        "required_leader_traits": "Power Wish",
                        "min_owner_energy": 3,
                        "markers": 2,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880721, card_id=1001, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880722, card_id=1002, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880723, card_id=1003, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
    ]
    state.players[1].unison_area.append(CardInstance(instance_id=880724, card_id=901000, owner_id=1, card_type="UNISON", markers=1))
    state.players[1].hand = [
        CardInstance(instance_id=880725, card_id=900703, owner_id=1, card_type="UNISON", color="Blue", energy_cost=3, has_activate_main=True)
    ]
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand"
    )
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None and state.counter_window.kind == "play"
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=state.counter_window.responder_player_id),
    )
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].card_id == 900703
    assert state.players[1].unison_area[0].markers == 2
    assert any(card.instance_id == 880724 for card in state.players[1].drop)
    assert any(cp.name == "unison_replaced" for cp in state.checkpoints)


def test_phase4_activate_main_play_self_from_hand_unison_replaces_hidden_mode_card_in_unison_area() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Power Wish Leader", "Blue", 0, "LEADER", '["Power Wish"]', "[]", False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False),
                900704: ("Power Wish Hidden Replacement Unison", "Blue", 3, "UNISON", "[]", "[]", True),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main = data.get(
                card_id,
                ("Card", "Blue", 0, "BATTLE", "[]", "[]", False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900704: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_hand",
                    "handler_params": {
                        "required_leader_traits": "Power Wish",
                        "min_owner_energy": 3,
                        "markers": 2,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880726, card_id=1001, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880727, card_id=1002, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
        CardInstance(instance_id=880728, card_id=1003, owner_id=1, card_type="ENERGY", color="Blue", energy_cost=0),
    ]
    state.players[1].unison_area.append(CardInstance(instance_id=880729, card_id=901001, owner_id=1, card_type="BATTLE", hidden_mode=True))
    state.players[1].hand = [
        CardInstance(instance_id=880730, card_id=900704, owner_id=1, card_type="UNISON", color="Blue", energy_cost=3, has_activate_main=True)
    ]
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand"
    )
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None and state.counter_window.kind == "play"
    state = engine.apply_action(
        state,
        Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=state.counter_window.responder_player_id),
    )
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].card_id == 900704
    assert state.players[1].unison_area[0].markers == 2
    assert any(card.instance_id == 880729 for card in state.players[1].drop)
    assert any(cp.name == "unison_replaced" for cp in state.checkpoints)


def test_phase4_activate_main_switch_owner_battle_to_hidden_mode() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "White", 0, "LEADER", "[]", "[]", False, False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False),
                900730: ("Hidden Switcher", "White", 2, "BATTLE", "[]", "[]", True, False),
                900731: ("Universe 7 Fighter", "White", 2, "BATTLE", '["Universe 7"]', "[]", False, False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_auto = data.get(
                card_id,
                ("Card", "White", 0, "BATTLE", "[]", "[]", False, False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=has_auto,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900730: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_switch_owner_battle_to_hidden_mode",
                    "handler_params": {
                        "allowed_colors": "white",
                        "required_traits": "Universe 7",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880730, card_id=900730, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True),
            CardInstance(instance_id=880731, card_id=900731, owner_id=1, card_type="BATTLE", color="White"),
        ]
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].battle_area[1].hidden_mode is True
    assert any(cp.name == "effect_activate_switch_owner_battle_to_hidden_mode" for cp in state.checkpoints)


def test_phase4_activate_main_switch_self_to_hidden_mode() -> None:
    engine = RulesEngine(
        effect_rules={
            900760: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_switch_self_to_hidden_mode",
                    "handler_params": {},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880760, card_id=900760, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True)
    state.players[1].battle_area.append(source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    )
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].battle_area[0].hidden_mode is True
    assert any(cp.name == "effect_activate_switch_self_to_hidden_mode" for cp in state.checkpoints)


def test_phase4_activate_main_switch_all_opponent_battle_to_revealed_then_ko() -> None:
    engine = RulesEngine(
        effect_rules={
            900761: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_switch_all_opponent_battle_to_revealed_then_ko_up_to_n",
                    "handler_params": {"max_targets": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880761, card_id=900761, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True)
    state.players[1].battle_area.append(source)
    state.players[2].battle_area.extend(
        [
            CardInstance(instance_id=880762, card_id=900762, owner_id=2, card_type="BATTLE", color="Red", hidden_mode=True, power=10000),
            CardInstance(instance_id=880763, card_id=900763, owner_id=2, card_type="BATTLE", color="Blue", hidden_mode=True, power=5000),
        ]
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    act = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[2].battle_area) == 1
    assert state.players[2].battle_area[0].instance_id == 880763
    assert state.players[2].battle_area[0].hidden_mode is False
    assert any(card.instance_id == 880762 for card in state.players[2].drop)
    assert any(cp.name == "effect_activate_switch_all_opponent_battle_to_revealed_then_ko_up_to_n" for cp in state.checkpoints)


def test_phase4_revealed_switch_can_grant_keyword_to_owner_card_for_turn() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "White", "LEADER", (), (), False),
                2: ("Other Leader", "Red", "LEADER", (), (), False),
                900764: ("Switch Source", "White", "BATTLE", (), (), False),
                900765: ("Baby Target", "White", "BATTLE", ("Baby",), (), False),
            }
            name, color, card_type, traits, characters, has_auto = data.get(
                card_id,
                ("Card", "White", "BATTLE", (), (), False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
                    keywords=(),
                    card_traits_json=traits,
                    card_character_json=characters,
                    has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=False,
                has_activate_battle=False,
                has_auto=has_auto,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900764: [
                {
                    "trigger": "self_switched_revealed",
                    "handler_id": "auto_buff_up_to_n_owner_cards_on_switch",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "white",
                        "required_traits": "Baby",
                        "grant_keyword": "Double Strike",
                        "keyword_duration": "turn",
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880764, card_id=900764, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True)
    target = CardInstance(instance_id=880765, card_id=900765, owner_id=1, card_type="BATTLE", color="White")
    state.players[1].battle_area.extend([source, target])
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    source.hidden_mode = False
    engine._emit_effect_event(
        state,
        name="card_switched_revealed_mode",
        actor_player_id=1,
        payload={"source_instance_id": source.instance_id, "source_card_id": source.card_id, "source_zone": "battle", "owner_player_id": 1},
    )
    engine._resolve_pending_effects(state)
    assert "Double Strike" in state.players[1].battle_area[1].temporary_keywords
    assert any(cp.name == "effect_auto_buff_up_to_n_owner_cards_on_switch" for cp in state.checkpoints)


def test_phase4_activate_main_hidden_mode_cost_can_send_opponent_battle_to_warp() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "White", 0, "LEADER", "[]", "[]", False, False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False),
                900750: ("Hidden Warper", "White", 2, "BATTLE", "[]", "[]", True, False),
                900751: ("White Ally", "White", 2, "BATTLE", "[]", "[]", False, False),
                900752: ("Target", "Red", 3, "BATTLE", "[]", "[]", False, False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_auto = data.get(
                card_id,
                ("Card", "White", 0, "BATTLE", "[]", "[]", False, False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=has_auto,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        skill_cost_rules={
            900750: {
                "activate_main": [
                    {"kind": "switch_owner_battle_to_hidden", "amount": 1, "allowed_colors": "white"}
                ]
            }
        },
        effect_rules={
            900750: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_send_up_to_n_opponent_battle_to_warp",
                    "handler_params": {"max_targets": 1},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880750, card_id=900750, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True),
            CardInstance(instance_id=880751, card_id=900751, owner_id=1, card_type="BATTLE", color="White"),
        ]
    )
    state.players[2].battle_area.append(CardInstance(instance_id=880752, card_id=900752, owner_id=2, card_type="BATTLE", color="Red"))
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert state.players[1].battle_area[1].hidden_mode is True
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert all(card.instance_id != 880752 for card in state.players[2].battle_area)
    assert any(card.instance_id == 880752 for card in state.players[2].warp)
    assert any(cp.name == "effect_activate_send_up_to_n_opponent_battle_to_warp" for cp in state.checkpoints)


def test_phase4_leader_activate_main_can_look_top_and_send_matching_card_to_owner_warp() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "Black", 0, "LEADER", "[]", "[\"Goku Black\"]", True),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False),
                900770: ("Black Battle", "Black", 2, "BATTLE", "[]", "[]", False),
                900771: ("Red Battle", "Red", 2, "BATTLE", "[]", "[]", False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main = data.get(
                card_id,
                ("Card", "Black", 0, "BATTLE", "[]", "[]", False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            1: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_look_top_send_up_to_n_to_owner_warp",
                    "handler_params": {"look_count": 7, "max_send": 1, "allowed_colors": "black"},
                    "once_per_turn": True,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].leader_area.has_activate_main = True
    state.players[1].deck = [
        CardInstance(instance_id=880770, card_id=900771, owner_id=1, card_type="BATTLE", color="Red"),
        CardInstance(instance_id=880771, card_id=900770, owner_id=1, card_type="BATTLE", color="Black"),
        *state.players[1].deck,
    ]
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "leader"
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(card.card_id == 900770 for card in state.players[1].warp)
    assert all(card.card_id != 900771 for card in state.players[1].warp)
    assert any(cp.name == "effect_activate_look_top_send_up_to_n_to_owner_warp" for cp in state.checkpoints)


def test_phase4_unison_activate_main_can_send_top_deck_to_owner_warp_and_switch_self_active() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "Black", 0, "LEADER", "[]", "[]", False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False),
                900772: ("Warping Unison", "Black", 3, "UNISON", "[]", "[]", True),
                900773: ("Deck A", "Black", 1, "BATTLE", "[]", "[]", False),
                900774: ("Deck B", "Black", 1, "BATTLE", "[]", "[]", False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main = data.get(
                card_id,
                ("Card", "Black", 0, "BATTLE", "[]", "[]", False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900772: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_send_top_deck_to_owner_warp",
                    "handler_params": {"send_count": 2, "switch_self_active": True, "marker_delta": 1},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].unison_area.append(
        CardInstance(
            instance_id=880772,
            card_id=900772,
            owner_id=1,
            card_type="UNISON",
            color="Black",
            has_activate_main=True,
            markers=2,
            resting=True,
        )
    )
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=state.players[1].unison_area[0])
    state.players[1].deck = [
        CardInstance(instance_id=880773, card_id=900773, owner_id=1, card_type="BATTLE", color="Black"),
        CardInstance(instance_id=880774, card_id=900774, owner_id=1, card_type="BATTLE", color="Black"),
        *state.players[1].deck,
    ]
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    source = state.players[1].unison_area[0]
    assert source.resting is False
    assert source.markers == 3
    assert [card.card_id for card in state.players[1].warp][-2:] == [900773, 900774]
    assert any(cp.name == "effect_activate_send_top_deck_to_owner_warp" for cp in state.checkpoints)


def test_phase4_owner_opponent_battle_attack_can_pay_life_bottom_deck_and_play_self_from_drop_to_negate() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Black Leader", "Black", 0, "LEADER", "[]", "[]", False, False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False),
                900780: ("Reactive Gohan", "Black", 3, "BATTLE", "[]", "[]", False, True),
                900781: ("Attacker", "Red", 2, "BATTLE", "[]", "[]", False, False),
                900782: ("Hand Card", "Black", 1, "BATTLE", "[]", "[]", False, False),
                900783: ("Life Card", "Black", 1, "BATTLE", "[]", "[]", False, False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_auto = data.get(
                card_id,
                ("Card", "Black", 0, "BATTLE", "[]", "[]", False, False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=has_auto,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900780: [
                {
                    "trigger": "owner_opponent_battle_attacks",
                    "handler_id": "auto_pay_life_bottom_deck_play_self_from_drop_or_warp_negate_attack",
                    "handler_params": {
                        "life_to_hand": 1,
                        "bottom_deck_from_hand": 1,
                        "max_owner_life": 4,
                        "resting": True,
                        "negate_attack": True,
                        "requires_leader": "if your leader is black",
                    },
                    "limit_per_turn": 1,
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=1,
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = _to_main(engine, state)
    reactive = CardInstance(instance_id=880780, card_id=900780, owner_id=1, card_type="BATTLE", color="Black", has_auto=True)
    state.players[1].drop.append(reactive)
    engine._register_card_effects(state, player_id=1, source_zone="drop", card=reactive)
    state.players[1].life = [
        CardInstance(instance_id=880783, card_id=900783, owner_id=1, card_type="BATTLE", color="Black"),
        CardInstance(instance_id=880784, card_id=900783, owner_id=1, card_type="BATTLE", color="Black"),
        CardInstance(instance_id=880785, card_id=900783, owner_id=1, card_type="BATTLE", color="Black"),
        CardInstance(instance_id=880786, card_id=900783, owner_id=1, card_type="BATTLE", color="Black"),
    ]
    state.players[1].hand = [
        CardInstance(instance_id=880782, card_id=900782, owner_id=1, card_type="BATTLE", color="Black")
    ]
    state.players[2].battle_area.append(
        CardInstance(instance_id=880781, card_id=900781, owner_id=2, card_type="BATTLE", color="Red", power=15000)
    )

    attack = next(
        a
        for a in engine.get_legal_actions(state, 2)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=1))

    assert state.attack_context is None
    assert state.counter_window is None
    assert len(state.players[1].life) == 3
    assert len(state.players[1].hand) == 1
    assert state.players[1].deck[-1] == 900782
    played = next(card for card in state.players[1].battle_area if card.instance_id == 880780)
    assert played.resting is True
    assert all(card.instance_id != 880780 for card in state.players[1].drop)
    assert any(cp.name == "effect_auto_pay_life_bottom_deck_play_self_from_drop_or_warp_negate_attack" for cp in state.checkpoints)


def test_phase4_unison_activate_main_can_send_opponent_drop_battle_to_warp() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "Yellow", 0, "LEADER", "[]", "[]", False),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False),
                900790: ("Piccolo Unison", "Yellow", 3, "UNISON", "[]", "[]", True),
                900791: ("Drop Battle A", "Red", 2, "BATTLE", "[]", "[]", False),
                900792: ("Drop Battle B", "Blue", 2, "BATTLE", "[]", "[]", False),
                900793: ("Drop Extra", "Red", 1, "EXTRA", "[]", "[]", False),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main = data.get(
                card_id,
                ("Card", "Yellow", 0, "BATTLE", "[]", "[]", False),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900790: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_send_up_to_n_opponent_drop_battle_to_warp",
                    "handler_params": {"max_targets": 2, "marker_delta": -3},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].unison_area.append(
        CardInstance(
            instance_id=880790,
            card_id=900790,
            owner_id=1,
            card_type="UNISON",
            color="Yellow",
            has_activate_main=True,
            markers=4,
        )
    )
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=state.players[1].unison_area[0])
    state.players[2].drop.extend(
        [
            CardInstance(instance_id=880791, card_id=900791, owner_id=2, card_type="BATTLE", color="Red"),
            CardInstance(instance_id=880792, card_id=900792, owner_id=2, card_type="BATTLE", color="Blue"),
            CardInstance(instance_id=880793, card_id=900793, owner_id=2, card_type="EXTRA", color="Red"),
        ]
    )
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "unison" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    source = state.players[1].unison_area[0]
    assert source.markers == 1
    assert [card.card_id for card in state.players[2].warp][-2:] == [900791, 900792]
    assert any(card.instance_id == 880793 for card in state.players[2].drop)
    assert any(cp.name == "effect_activate_send_up_to_n_opponent_drop_battle_to_warp" for cp in state.checkpoints)


def test_phase4_activate_main_gain_power_by_hidden_cost_target_original_power_for_turn() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "White", 0, "LEADER", "[]", "[]", False, False, 10000),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False, 10000),
                900760: ("Power Copier", "White", 2, "BATTLE", "[]", "[]", True, False, 15000),
                900761: ("White Ally", "White", 2, "BATTLE", "[]", "[]", False, False, 20000),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_auto, power = data.get(
                card_id,
                ("Card", "White", 0, "BATTLE", "[]", "[]", False, False, 15000),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=power,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=has_auto,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        skill_cost_rules={
            900760: {
                "activate_main": [
                    {"kind": "switch_owner_battle_to_hidden", "amount": 1, "allowed_colors": "white"}
                ]
            }
        },
        effect_rules={
            900760: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_gain_power_by_hidden_cost_target_original_power_for_turn",
                    "handler_params": {"target_scope": "self"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880760, card_id=900760, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True, power=15000),
            CardInstance(instance_id=880761, card_id=900761, owner_id=1, card_type="BATTLE", color="White", power=20000),
        ]
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert state.players[1].battle_area[1].hidden_mode is True
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].battle_area[0].power == 35000
    assert state.players[1].battle_area[0].temporary_power_delta == 20000
    assert any(cp.name == "effect_activate_gain_power_by_hidden_cost_target_original_power_for_turn" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state.players[1].battle_area[0].power == 15000
    assert state.players[1].battle_area[0].temporary_power_delta == 0


def test_phase4_activate_battle_hidden_mode_cost_can_gain_power_and_keyword_for_battle() -> None:
    engine = RulesEngine(
        skill_cost_rules={
            900765: {
                "activate_battle": [
                    {"kind": "switch_owner_battle_to_hidden", "amount": 1, "allowed_colors": "white"}
                ]
            }
        },
        effect_rules={
            900765: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "activate_gain_power_and_keyword_for_battle",
                    "handler_params": {"power_delta": 10000, "grant_keyword": "Double Strike"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.extend(
        [
            CardInstance(
                instance_id=880765,
                card_id=900765,
                owner_id=1,
                card_type="BATTLE",
                color="White",
                power=15000,
                has_activate_battle=True,
                activate_limit_once_per_turn=True,
                skill_text_raw=(
                    "[Activate: Battle][Once per turn](1), choose 1 white card in your Battle Area and switch it to Hidden Mode: "
                    "This card gets +10000 power and [Double Strike] for the battle."
                ),
            ),
            CardInstance(instance_id=880766, card_id=900766, owner_id=1, card_type="BATTLE", color="White", power=5000),
        ]
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert state.players[1].battle_area[1].hidden_mode is True
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    attacker = state.players[1].battle_area[0]
    assert attacker.power == 25000
    assert attacker.battle_temporary_power_delta == 10000
    assert "Double Strike" in attacker.battle_temporary_keywords
    assert any(cp.name == "effect_activate_gain_power_and_keyword_for_battle" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    attacker = state.players[1].battle_area[0]
    assert attacker.power == 25000
    assert "Double Strike" in attacker.battle_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    attacker = state.players[1].battle_area[0]
    assert attacker.power == 15000
    assert attacker.battle_temporary_power_delta == 0
    assert "Double Strike" not in attacker.battle_temporary_keywords
    assert any(cp.name == "battle_modifiers_cleared" for cp in state.checkpoints)


def test_phase4_activate_battle_can_buff_owner_leader_for_battle() -> None:
    engine = RulesEngine(
        effect_rules={
            900786: [
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_gain_power_and_keyword_for_battle",
                    "handler_params": {
                        "power_delta": 15000,
                        "grant_keyword": "Double Strike",
                        "target_scope": "owner_leader",
                        "requires_leader": "black",
                        "required_leader_traits": "Saiyan",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].leader_area.color = "Black"
    state.players[1].leader_area.traits = ("Saiyan",)
    engine._card_cache[(1, "front")] = CardRuntimeData(card_name="Leader", card_type="LEADER", color="Black", traits=("Saiyan",))
    state.players[1].hand = [
        CardInstance(
            instance_id=880790,
            card_id=900786,
            owner_id=1,
            card_type="EXTRA",
            color="Black",
            energy_cost=0,
            has_activate_battle=True,
            skill_text_raw=(
                "[Activate: Battle] If your Leader Card is a black ≪Saiyan≫ card, "
                "it gets +15000 power and [Double Strike] for the duration of the battle."
            ),
        )
    ]
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader" and a.target_zone == "leader"
    )
    leader_base_power = state.players[1].leader_area.power
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, action)
    leader = state.players[1].leader_area
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    leader = state.players[1].leader_area
    assert leader.power == leader_base_power + 15000
    assert leader.battle_temporary_power_delta == 15000
    assert "Double Strike" in leader.battle_temporary_keywords
    assert any(cp.name == "effect_activate_gain_power_and_keyword_for_battle" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    leader = state.players[1].leader_area
    assert leader.power == leader_base_power
    assert leader.battle_temporary_power_delta == 0
    assert "Double Strike" not in leader.battle_temporary_keywords


def test_phase4_activate_battle_drop_hidden_mode_cost_can_ko_opponent_battle() -> None:
    engine = RulesEngine(
        skill_cost_rules={
            900767: {
                "activate_battle": [
                    {"kind": "send_owner_hidden_mode_battle_to_drop", "amount": 1}
                ]
            }
        },
        effect_rules={
            900767: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "activate_ko_up_to_n_opponent_battle",
                    "handler_params": {"max_targets": 1, "target_policy": "first"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].battle_area.extend(
        [
            CardInstance(
                instance_id=880767,
                card_id=900767,
                owner_id=1,
                card_type="BATTLE",
                color="White",
                power=15000,
                has_activate_battle=True,
                activate_limit_once_per_turn=True,
                skill_text_raw=(
                    "[Activate: Battle][Limit 1] Choose 1 Hidden Mode card in your Battle Area and place it into its owner's Drop: "
                    "Choose up to 1 of your opponent's Battle Cards and KO it."
                ),
            ),
            CardInstance(instance_id=880768, card_id=900768, owner_id=1, card_type="BATTLE", color="White", power=5000, hidden_mode=True),
        ]
    )
    state.players[2].battle_area.append(
        CardInstance(instance_id=880769, card_id=900769, owner_id=2, card_type="BATTLE", color="Red", power=15000)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert all(card.instance_id != 880768 for card in state.players[1].battle_area)
    assert any(card.instance_id == 880768 for card in state.players[1].drop)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert all(card.instance_id != 880769 for card in state.players[2].battle_area)
    assert any(card.instance_id == 880769 for card in state.players[2].drop)
    assert any(cp.name == "effect_activate_ko_up_to_n_opponent_battle" for cp in state.checkpoints)


def test_phase4_activate_main_can_draw_play_self_and_gain_keyword_until_opponent_turn_end() -> None:
    engine = RulesEngine(
        effect_rules={
            900780: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_draw_n_play_self_from_hand_and_gain_keyword_until_opponent_turn_end",
                    "handler_params": {
                        "amount": 1,
                        "grant_keyword": "Barrier",
                        "min_owner_hidden_mode_battle": 2,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880781, card_id=901001, owner_id=1, card_type="BATTLE", color="White", resting=False),
        CardInstance(instance_id=880782, card_id=901002, owner_id=1, card_type="BATTLE", color="White", resting=False),
    ]
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880783, card_id=901003, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True),
            CardInstance(instance_id=880784, card_id=901004, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True),
        ]
    )
    state.players[1].hand = [
        CardInstance(
            instance_id=880780,
            card_id=900780,
            owner_id=1,
            card_type="BATTLE",
            color="White",
            energy_cost=2,
            power=20000,
            has_activate_main=True,
            skill_text_raw=(
                "[Activate: Main]{w}(2), if you have 2 or more Hidden Mode cards in your Battle Area: "
                "Draw 1 card, play this card from your hand, and this card gains [Barrier] until the end of your opponent's turn."
            ),
        )
    ]
    legal = engine.get_legal_actions(state, 1)
    assert any(a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand" for a in legal)
    state.players[1].battle_area.pop()
    legal = engine.get_legal_actions(state, 1)
    assert all(not (a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand") for a in legal)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880784, card_id=901004, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True)
    )
    action = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand"
    )
    deck_before = len(state.players[1].deck)
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].deck) == deck_before - 1
    assert state.counter_window is not None and state.counter_window.kind == "play"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    played = next(card for card in state.players[1].battle_area if card.instance_id == 880780)
    assert "Barrier" in played.delayed_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))
    still_played = next(card for card in state.players[1].battle_area if card.instance_id == 880780)
    assert "Barrier" in still_played.delayed_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    expired = next(card for card in state.players[1].battle_area if card.instance_id == 880780)
    assert "Barrier" not in expired.delayed_temporary_keywords
    assert any(cp.name == "delayed_keyword_clear_resolved" for cp in state.checkpoints)


def test_phase4_activate_main_can_grant_keyword_to_all_matching_owner_battles_until_opponent_turn_end() -> None:
    engine = RulesEngine(
        effect_rules={
            900785: [
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_buff_owner_battle_cards",
                    "handler_params": {
                        "target_policy": "all",
                        "target_scope": "owner_battle",
                        "grant_keyword": "Barrier",
                        "keyword_duration": "opponent_turn",
                        "allowed_colors": "red",
                        "required_traits": "Saiyan",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880791, card_id=901011, owner_id=1, card_type="ENERGY", color="Red", resting=False),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=880785,
            card_id=900785,
            owner_id=1,
            card_type="EXTRA",
            color="Red",
            energy_cost=1,
            has_activate_main=True,
            skill_text_raw=(
                "[Activate: Main] Choose all red ≪Saiyan≫ cards in your Battle Area. "
                "They gain [Barrier] until the end of your opponent's next turn."
            ),
        )
    ]
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880786, card_id=901012, owner_id=1, card_type="BATTLE", color="Red", traits=("Saiyan",)),
            CardInstance(instance_id=880787, card_id=901013, owner_id=1, card_type="BATTLE", color="Red", traits=("Saiyan",)),
            CardInstance(instance_id=880788, card_id=901014, owner_id=1, card_type="BATTLE", color="Blue", traits=("Saiyan",)),
            CardInstance(instance_id=880789, card_id=901015, owner_id=1, card_type="BATTLE", color="Red", traits=("Earthling",)),
        ]
    )
    engine._card_cache[(901012, "front")] = CardRuntimeData(card_name="Red Saiyan A", card_type="BATTLE", color="Red", traits=("Saiyan",))
    engine._card_cache[(901013, "front")] = CardRuntimeData(card_name="Red Saiyan B", card_type="BATTLE", color="Red", traits=("Saiyan",))
    engine._card_cache[(901014, "front")] = CardRuntimeData(card_name="Blue Saiyan", card_type="BATTLE", color="Blue", traits=("Saiyan",))
    engine._card_cache[(901015, "front")] = CardRuntimeData(card_name="Red Earthling", card_type="BATTLE", color="Red", traits=("Earthling",))
    action = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert "Barrier" in next(card for card in state.players[1].battle_area if card.instance_id == 880786).delayed_temporary_keywords
    assert "Barrier" in next(card for card in state.players[1].battle_area if card.instance_id == 880787).delayed_temporary_keywords
    assert "Barrier" not in next(card for card in state.players[1].battle_area if card.instance_id == 880788).delayed_temporary_keywords
    assert "Barrier" not in next(card for card in state.players[1].battle_area if card.instance_id == 880789).delayed_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))
    assert "Barrier" in next(card for card in state.players[1].battle_area if card.instance_id == 880786).delayed_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    assert "Barrier" not in next(card for card in state.players[1].battle_area if card.instance_id == 880786).delayed_temporary_keywords
    assert any(cp.name == "effect_activate_buff_owner_battle_cards" for cp in state.checkpoints)


def test_phase4_activate_main_can_play_self_with_markers_from_hand_or_warp() -> None:
    engine = RulesEngine(
        effect_rules={
            900787: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_hand",
                    "handler_params": {"markers": 2, "required_source_zone": "hand", "min_opponent_energy": 3},
                },
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_play_self_from_warp",
                    "handler_params": {"markers": 2, "required_source_zone": "warp", "min_opponent_energy": 3},
                },
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[2].energy = [
        CardInstance(instance_id=880810, card_id=901110, owner_id=2, color="Black"),
        CardInstance(instance_id=880811, card_id=901111, owner_id=2, color="Black"),
        CardInstance(instance_id=880812, card_id=901112, owner_id=2, color="Black"),
    ]
    state.players[1].energy = [
        CardInstance(instance_id=880801, card_id=901101, owner_id=1, color="Black"),
        CardInstance(instance_id=880802, card_id=901102, owner_id=1, color="Black"),
        CardInstance(instance_id=880803, card_id=901103, owner_id=1, color="Black"),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=880804,
            card_id=900787,
            owner_id=1,
            card_type="UNISON",
            color="Black",
            energy_cost=2,
            has_activate_main=True,
        )
    ]
    hand_action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "hand" and a.source_index == 0
    )
    state = engine.apply_action(state, hand_action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None and state.counter_window.kind == "play"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].instance_id == 880804
    assert state.players[1].unison_area[0].markers == 2
    assert any(cp.name == "counter_timing_play_from_skill" for cp in state.checkpoints)

    state.players[1].warp = [
        CardInstance(
            instance_id=880805,
            card_id=900787,
            owner_id=1,
            card_type="UNISON",
            color="Black",
            energy_cost=2,
            has_activate_main=True,
        )
    ]
    for energy in state.players[1].energy:
        energy.resting = False
    warp_action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "warp" and a.source_index == 0
    )
    state = engine.apply_action(state, warp_action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.counter_window is not None and state.counter_window.kind == "play"
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(card.instance_id == 880805 and card.markers == 2 for card in state.players[1].unison_area)
    assert any(cp.name == "counter_timing_play_from_skill" for cp in state.checkpoints)


def test_phase4_activate_battle_unison_can_switch_self_active_and_gain_power_for_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            900788: [
                {
                    "trigger": "self_activate_battle",
                    "handler_id": "activate_switch_self_active_and_gain_power_for_turn",
                    "handler_params": {"power_delta": 15000},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    state.players[1].unison_area = [
        CardInstance(
            instance_id=880806,
            card_id=900788,
            owner_id=1,
            card_type="UNISON",
            color="Black",
            power=20000,
            resting=True,
            has_activate_battle=True,
            markers=2,
        )
    ]
    engine._register_card_effects(state, player_id=1, source_zone="unison", card=state.players[1].unison_area[0])
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader" and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_BATTLE_SKILL and a.source_zone == "unison" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    unison = state.players[1].unison_area[0]
    assert unison.resting is False
    assert unison.power == 35000
    assert unison.temporary_power_delta == 15000
    assert any(cp.name == "effect_activate_switch_self_active_and_gain_power_for_turn" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state.players[1].unison_area[0].power == 20000
    assert state.players[1].unison_area[0].temporary_power_delta == 0


def test_phase4_activate_main_hidden_mode_battle_or_energy_cost_can_ko_and_buff_leader_for_turn() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "White", 0, "LEADER", "[]", "[]", False, False, 10000),
                2: ("Other Leader", "Red", 0, "LEADER", "[]", "[]", False, False, 10000),
                900770: ("Leader Buffer", "White", 2, "BATTLE", "[]", "[]", True, False, 15000),
                900771: ("White Ally", "White", 2, "BATTLE", "[]", "[]", False, False, 15000),
                900772: ("Target", "Red", 3, "BATTLE", "[]", "[]", False, False, 15000),
                900773: ("Energy Card", "White", 1, "BATTLE", "[]", "[]", False, False, 5000),
            }
            name, color, cost, card_type, traits_json, characters_json, has_activate_main, has_auto, power = data.get(
                card_id,
                ("Card", "White", 0, "BATTLE", "[]", "[]", False, False, 15000),
            )
            return SimpleNamespace(
                card_name=name,
                power_int=power,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json=traits_json,
                card_character_json=characters_json,
            )

    engine = RulesEngine(
        card_repository=Repo(),
        skill_cost_rules={
            900770: {
                "activate_main": [
                    {"kind": "switch_owner_battle_or_energy_to_hidden", "amount": 1, "allowed_colors": "white"}
                ]
            }
        },
        effect_rules={
            900770: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_ko_up_to_n_opponent_battle_and_buff_owner_leader_for_turn",
                    "handler_params": {"max_targets": 1, "leader_power_delta": 20000, "target_policy": "first"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880770, card_id=900770, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True, power=15000)
    )
    state.players[1].energy.append(CardInstance(instance_id=880773, card_id=900773, owner_id=1, card_type="BATTLE", color="White", resting=False, power=5000))
    state.players[2].battle_area.append(CardInstance(instance_id=880772, card_id=900772, owner_id=2, card_type="BATTLE", color="Red", power=15000))
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    assert state.players[1].energy[0].hidden_mode is True
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert all(card.instance_id != 880772 for card in state.players[2].battle_area)
    assert any(card.instance_id == 880772 for card in state.players[2].drop)
    assert state.players[1].leader_area.power == 30000
    assert state.players[1].leader_area.temporary_power_delta == 20000
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state.players[1].leader_area.power == 10000
    assert state.players[1].leader_area.temporary_power_delta == 0


def test_phase4_activate_main_drop_owner_hidden_mode_draw_n() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Leader", "White", 0, "LEADER", False),
                2: ("Other Leader", "Red", 0, "LEADER", False),
                900740: ("Hidden Recycler", "White", 2, "BATTLE", True),
                900741: ("Hidden Target", "White", 2, "BATTLE", False),
            }
            name, color, cost, card_type, has_activate_main = data.get(card_id, ("Card", "White", 0, "BATTLE", False))
            return SimpleNamespace(
                card_name=name,
                power_int=15000,
                card_type=card_type,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=(),
                has_counter=False,
                has_counter_attack=False,
                has_counter_play=False,
                has_activate_main=has_activate_main,
                has_activate_battle=False,
                has_auto=False,
                has_permanent=False,
                has_draw=False,
                max_draw=None,
                has_barrier=False,
                z_energy_cost=None,
                card_energy_cost=str(cost),
                card_skill_unstyled="",
                card_traits_json="[]",
                card_character_json="[]",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            900740: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_drop_owner_hidden_mode_draw_n",
                    "handler_params": {"amount": 1},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    hand_before = len(state.players[1].hand)
    deck_before = len(state.players[1].deck)
    state.players[1].battle_area.extend(
        [
            CardInstance(instance_id=880740, card_id=900740, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True),
            CardInstance(instance_id=880741, card_id=900741, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True),
        ]
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    action = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle" and a.source_index == 0
    )
    state = engine.apply_action(state, action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert all(card.instance_id != 880741 for card in state.players[1].battle_area)
    assert any(card.instance_id == 880741 for card in state.players[1].drop)
    assert len(state.players[1].hand) == hand_before + 1
    assert len(state.players[1].deck) == deck_before - 1
    assert any(cp.name == "effect_activate_drop_owner_hidden_mode_draw_n" for cp in state.checkpoints)


def test_phase4_play_switch_opponent_battle_to_hidden_then_reveal_on_turn_end() -> None:
    engine = RulesEngine(
        effect_rules={
            900742: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_switch_up_to_n_opponent_battle_to_hidden_then_reveal_on_turn_end",
                    "handler_params": {"max_targets": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880742, card_id=900742, owner_id=1, card_type="BATTLE", energy_cost=0)
    ]
    state.players[2].battle_area = [
        CardInstance(instance_id=880743, card_id=900743, owner_id=2, card_type="BATTLE", energy_cost=2, power=15000)
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[2].battle_area[0].hidden_mode is True
    assert any(cp.name == "effect_auto_switch_opponent_battle_hidden_then_reveal_on_turn_end" for cp in state.checkpoints)
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert state.players[2].battle_area[0].hidden_mode is False
    assert any(cp.name == "delayed_mode_switch_resolved" for cp in state.checkpoints)


def test_phase4_play_switch_owner_board_to_revealed_on_play() -> None:
    engine = RulesEngine(
        effect_rules={
            900745: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_switch_up_to_n_owner_board_to_revealed_on_play",
                    "handler_params": {"max_targets": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [CardInstance(instance_id=880801, card_id=1001, owner_id=1, card_type="ENERGY", color="Red")]
    state.players[1].battle_area.append(
        CardInstance(instance_id=880802, card_id=900746, owner_id=1, card_type="BATTLE", color="Red", hidden_mode=True)
    )
    state.players[1].hand = [CardInstance(instance_id=880803, card_id=900745, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].battle_area[0].hidden_mode is False
    assert any(cp.name == "effect_auto_switch_owner_board_to_revealed_on_play" for cp in state.checkpoints)


def test_phase4_play_switch_any_player_board_to_revealed_on_play() -> None:
    engine = RulesEngine(
        effect_rules={
            900744: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_switch_up_to_n_any_player_board_to_revealed_on_play",
                    "handler_params": {"max_targets": 1},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [CardInstance(instance_id=880809, card_id=1001, owner_id=1, card_type="ENERGY", color="Red")]
    state.players[2].battle_area.append(
        CardInstance(instance_id=880810, card_id=900750, owner_id=2, card_type="BATTLE", color="Blue", hidden_mode=True)
    )
    state.players[1].hand = [CardInstance(instance_id=880811, card_id=900744, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[2].battle_area[0].hidden_mode is False
    assert any(cp.name == "effect_auto_switch_any_player_board_to_revealed_on_play" for cp in state.checkpoints)


def test_phase4_play_switch_owner_battle_to_hidden_on_play() -> None:
    engine = RulesEngine(
        effect_rules={
            900747: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_switch_up_to_n_owner_battle_to_hidden_on_play",
                    "handler_params": {"max_targets": 1, "allowed_colors": "white"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [CardInstance(instance_id=880804, card_id=1001, owner_id=1, card_type="ENERGY", color="White")]
    state.players[1].battle_area.append(
        CardInstance(instance_id=880805, card_id=900748, owner_id=1, card_type="BATTLE", color="White", hidden_mode=False)
    )
    state.players[1].hand = [CardInstance(instance_id=880806, card_id=900747, owner_id=1, card_type="BATTLE", color="White", energy_cost=1)]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].battle_area[0].hidden_mode is True
    assert any(cp.name == "effect_auto_switch_owner_battle_to_hidden_on_play" for cp in state.checkpoints)


def test_phase4_play_draw_and_switch_self_to_hidden_on_play() -> None:
    engine = RulesEngine(
        effect_rules={
            900749: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_draw_n",
                    "handler_params": {"amount": 1},
                },
                {
                    "trigger": "self_played",
                    "handler_id": "auto_switch_self_to_hidden_on_play",
                    "handler_params": {},
                },
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=[3001, 3002] + _deck(1000, 58),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [CardInstance(instance_id=880807, card_id=1001, owner_id=1, card_type="ENERGY", color="White")]
    state.players[1].hand = [CardInstance(instance_id=880808, card_id=900749, owner_id=1, card_type="BATTLE", color="White", energy_cost=1)]
    hand_before = len(state.players[1].hand)
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    played = next(card for card in state.players[1].battle_area if card.card_id == 900749)
    assert played.hidden_mode is True
    assert len(state.players[1].hand) == hand_before
    assert any(cp.name == "effect_auto_switch_self_to_hidden_on_play" for cp in state.checkpoints)


def test_phase4_hidden_switch_can_buff_owner_leader_until_opponent_turn_end() -> None:
    engine = RulesEngine(
        effect_rules={
            900820: [
                {
                    "trigger": "self_switched_hidden",
                    "handler_id": "auto_buff_owner_leader_on_switch_until_opponent_turn_end",
                    "handler_params": {"power_delta": 5000, "requires_owner_actor": True},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880820, card_id=900820, owner_id=1, card_type="BATTLE", color="White")
    state.players[1].battle_area.append(source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    baseline = state.players[1].leader_area.power
    source.hidden_mode = True
    engine._emit_effect_event(
        state,
        name="card_switched_hidden_mode",
        actor_player_id=1,
        payload={"source_instance_id": source.instance_id, "source_card_id": source.card_id, "source_zone": "battle", "owner_player_id": 1},
    )
    engine._resolve_pending_effects(state)
    assert state.players[1].leader_area.power == baseline + 5000
    assert any(cp.name == "effect_auto_buff_owner_leader_on_switch_until_opponent_turn_end" for cp in state.checkpoints)


def test_phase4_hidden_switch_can_grant_owner_card_keyword_until_opponent_turn_end() -> None:
    engine = RulesEngine(
        effect_rules={
            900821: [
                {
                    "trigger": "self_switched_hidden",
                    "handler_id": "auto_buff_up_to_n_owner_cards_on_switch",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "white",
                        "grant_keyword": "Barrier",
                        "keyword_duration": "opponent_turn",
                        "requires_owner_actor": True,
                    },
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880821, card_id=900821, owner_id=1, card_type="BATTLE", color="Blue")
    target = CardInstance(instance_id=880822, card_id=900822, owner_id=1, card_type="BATTLE", color="White")
    state.players[1].battle_area.extend([source, target])
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    source.hidden_mode = True
    engine._emit_effect_event(
        state,
        name="card_switched_hidden_mode",
        actor_player_id=1,
        payload={"source_instance_id": source.instance_id, "source_card_id": source.card_id, "source_zone": "battle", "owner_player_id": 1},
    )
    engine._resolve_pending_effects(state)
    assert "Barrier" in target.delayed_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=1))
    assert "Barrier" in state.players[1].battle_area[1].delayed_temporary_keywords
    state = engine.apply_action(state, Action(action_type=ActionType.END_CHARGE, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_TURN, player_id=2))
    assert "Barrier" not in state.players[1].battle_area[1].delayed_temporary_keywords


def test_phase4_revealed_switch_can_buff_self_for_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            900823: [
                {
                    "trigger": "self_switched_revealed",
                    "handler_id": "auto_self_gain_power_and_keyword_for_turn_on_switch",
                    "handler_params": {"power_delta": 5000, "grant_keyword": "Double Strike"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880823, card_id=900823, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True, power=10000)
    state.players[1].battle_area.append(source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    source.hidden_mode = False
    engine._emit_effect_event(
        state,
        name="card_switched_revealed_mode",
        actor_player_id=1,
        payload={"source_instance_id": source.instance_id, "source_card_id": source.card_id, "source_zone": "battle", "owner_player_id": 1},
    )
    engine._resolve_pending_effects(state)
    assert source.power == 15000
    assert "Double Strike" in source.temporary_keywords


def test_phase4_switch_can_buff_owner_card_for_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            900824: [
                {
                    "trigger": "self_switched_revealed",
                    "handler_id": "auto_buff_up_to_n_owner_cards_on_switch",
                    "handler_params": {"max_targets": 1, "allowed_colors": "white", "power_delta": 10000, "requires_owner_turn": True},
                },
                {
                    "trigger": "self_switched_hidden",
                    "handler_id": "auto_buff_up_to_n_owner_cards_on_switch",
                    "handler_params": {"max_targets": 1, "allowed_colors": "white", "power_delta": 10000, "requires_owner_turn": True},
                },
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880824, card_id=900824, owner_id=1, card_type="BATTLE", color="Blue", hidden_mode=True)
    target = CardInstance(instance_id=880825, card_id=900825, owner_id=1, card_type="BATTLE", color="White", power=10000)
    state.players[1].battle_area.extend([source, target])
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    source.hidden_mode = False
    engine._emit_effect_event(
        state,
        name="card_switched_revealed_mode",
        actor_player_id=1,
        payload={"source_instance_id": source.instance_id, "source_card_id": source.card_id, "source_zone": "battle", "owner_player_id": 1},
    )
    engine._resolve_pending_effects(state)
    assert target.power == 20000


def test_phase4_switch_can_ko_opponent_battle_on_owner_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            900826: [
                {
                    "trigger": "self_switched_revealed",
                    "handler_id": "auto_ko_up_to_n_opponent_battle_on_switch",
                    "handler_params": {"max_targets": 1, "requires_owner_turn": True},
                },
                {
                    "trigger": "self_switched_hidden",
                    "handler_id": "auto_ko_up_to_n_opponent_battle_on_switch",
                    "handler_params": {"max_targets": 1, "requires_owner_turn": True},
                },
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880826, card_id=900826, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True)
    state.players[1].battle_area.append(source)
    state.players[2].battle_area.append(CardInstance(instance_id=880827, card_id=900827, owner_id=2, card_type="BATTLE", color="Red", power=5000))
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    source.hidden_mode = False
    engine._emit_effect_event(
        state,
        name="card_switched_revealed_mode",
        actor_player_id=1,
        payload={"source_instance_id": source.instance_id, "source_card_id": source.card_id, "source_zone": "battle", "owner_player_id": 1},
    )
    engine._resolve_pending_effects(state)
    assert not state.players[2].battle_area


def test_phase4_hidden_drop_can_buff_owner_card_on_ko_path() -> None:
    engine = RulesEngine(
        effect_rules={
            900830: [
                {
                    "trigger": "self_hidden_battle_to_drop",
                    "handler_id": "auto_buff_up_to_n_owner_cards_on_hidden_drop",
                    "handler_params": {"max_targets": 1, "allowed_colors": "white", "power_delta": 5000},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880830, card_id=900830, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True, power=5000)
    target = CardInstance(instance_id=880831, card_id=900831, owner_id=1, card_type="BATTLE", color="White", power=10000)
    state.players[1].battle_area.extend([source, target])
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    engine._ko_card(state, 1, "battle", source.instance_id)
    engine._resolve_pending_effects(state)
    assert target.power == 15000
    assert any(cp.name == "effect_auto_buff_up_to_n_owner_cards_on_hidden_drop" for cp in state.checkpoints)


def test_phase4_hidden_drop_can_buff_owner_card_on_non_ko_drop_path() -> None:
    engine = RulesEngine(
        effect_rules={
            900832: [
                {
                    "trigger": "self_hidden_battle_to_drop",
                    "handler_id": "auto_buff_up_to_n_owner_cards_on_hidden_drop",
                    "handler_params": {"max_targets": 1, "allowed_colors": "white", "power_delta": 5000},
                }
            ],
            900833: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "noop_auto",
                }
            ],
        },
        skill_cost_rules={
            900833: {
                "activate_main": [
                    {"kind": "send_owner_hidden_mode_battle_to_drop", "amount": 1}
                ]
            }
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    source = CardInstance(instance_id=880832, card_id=900832, owner_id=1, card_type="BATTLE", color="White", hidden_mode=True, power=5000)
    target = CardInstance(instance_id=880833, card_id=900834, owner_id=1, card_type="BATTLE", color="White", power=10000)
    activator = CardInstance(instance_id=880834, card_id=900833, owner_id=1, card_type="BATTLE", color="White", has_activate_main=True)
    state.players[1].battle_area.extend([source, target, activator])
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=source)
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=activator)
    act = Action(action_type=ActionType.ACTIVATE_MAIN_SKILL, player_id=1, source_zone="battle", source_index=2)
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    resolved_target = next(card for card in state.players[1].battle_area if card.instance_id == target.instance_id)
    assert resolved_target.power == 15000
    assert any(card.instance_id == source.instance_id for card in state.players[1].drop)
    assert any(cp.name == "effect_auto_buff_up_to_n_owner_cards_on_hidden_drop" for cp in state.checkpoints)


def test_phase4_activate_main_draw_and_gain_dual_attack_for_turn() -> None:
    engine = RulesEngine(
        effect_rules={
            900710: [
                {
                    "trigger": "self_activate_main",
                    "handler_id": "activate_draw_n_and_gain_keyword_for_turn",
                    "handler_params": {"amount": 1, "grant_keyword": "Dual Attack"},
                }
            ]
        }
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        first_player=2,
        shuffle_decks=False,
    )
    state = _to_p1_main_where_attacks_are_legal(engine, state)
    deck_before = len(state.players[1].deck)
    state.players[1].battle_area.append(
        CardInstance(
            instance_id=880710,
            card_id=900710,
            owner_id=1,
            card_type="BATTLE",
            energy_cost=1,
            power=15000,
            has_activate_main=True,
        )
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    act = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.ACTIVATE_MAIN_SKILL and a.source_zone == "battle"
    )
    state = engine.apply_action(state, act)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    attacker = state.players[1].battle_area[0]
    assert len(state.players[1].deck) == deck_before - 1
    assert "Dual Attack" in attacker.temporary_keywords
    first_attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, first_attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.END_OFFENSE_STEP, player_id=1))
    state = engine.apply_action(state, Action(action_type=ActionType.END_DEFENSE_STEP, player_id=2))
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    attacker = state.players[1].battle_area[0]
    assert attacker.resting is False
    state = engine.apply_action(state, Action(action_type=ActionType.RESOLVE_BATTLE, player_id=1))
    assert any(
        a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0
        for a in engine.get_legal_actions(state, 1)
    )


def test_phase4_self_attacks_power_reduce_up_to_n_rule() -> None:
    engine = RulesEngine(
        effect_rules={
            424270: [
                {
                    "trigger": "self_attacks",
                    "handler_id": "auto_power_reduce_up_to_n_on_attack",
                    "handler_params": {
                        "max_targets": 1,
                        "max_cost": -1,
                        "target_policy": "first",
                        "power_delta": -10000,
                    },
                }
            ]
        }
    )
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
        CardInstance(instance_id=880351, card_id=424270, owner_id=1, card_type="BATTLE", energy_cost=0, power=15000)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    state.players[2].battle_area = [
        CardInstance(instance_id=880352, card_id=352, owner_id=2, card_type="BATTLE", energy_cost=1, power=9000)
    ]
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[2].battle_area) == 0
    assert any(c.instance_id == 880352 for c in state.players[2].drop)
    assert any(cp.name == "effect_auto_power_reduce_up_to_n_on_attack" for cp in state.checkpoints)


def test_phase4_self_attacks_can_pay_life_gain_power_and_keyword() -> None:
    engine = RulesEngine(
        effect_rules={
            424282: [
                {
                    "trigger": "self_attacks",
                    "handler_id": "auto_pay_life_on_attack_gain_power_and_keyword_for_turn",
                    "handler_params": {"life_to_hand": 1, "power_delta": 15000, "grant_keyword": "Double Strike"},
                }
            ]
        },
    )
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
        CardInstance(instance_id=880353, card_id=424282, owner_id=1, card_type="BATTLE", energy_cost=0, power=15000, keywords=())
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    life_before = len(state.players[1].life)
    hand_before = len(state.players[1].hand)
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "battle" and a.attacker_index == 0 and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    attacker = state.players[1].battle_area[0]
    assert len(state.players[1].life) == life_before - 1
    assert len(state.players[1].hand) == hand_before + 1
    assert attacker.power == 30000
    assert "Double Strike" in attacker.temporary_keywords
    assert any(cp.name == "effect_auto_pay_life_on_attack_gain_power_and_keyword_for_turn" for cp in state.checkpoints)


def test_phase4_owner_leader_attack_can_add_from_hand_to_life() -> None:
    engine = RulesEngine(
        effect_rules={
            424283: [
                {
                    "trigger": "owner_leader_attacks",
                    "handler_id": "auto_add_up_to_n_from_owner_hand_to_life_on_owner_leader_attack",
                    "handler_params": {"amount": 1, "allowed_colors": "yellow"},
                }
            ]
        },
    )
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
        CardInstance(instance_id=880354, card_id=424283, owner_id=1, card_type="BATTLE", energy_cost=0)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    state.players[1].hand = [
        CardInstance(instance_id=880355, card_id=900951, owner_id=1, card_type="BATTLE", color="Yellow"),
        CardInstance(instance_id=880356, card_id=900952, owner_id=1, card_type="BATTLE", color="Blue"),
    ]
    life_before = len(state.players[1].life)
    hand_before = len(state.players[1].hand)
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader" and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].life) == life_before + 1
    assert len(state.players[1].hand) == hand_before - 1
    assert any(c.instance_id == 880355 for c in state.players[1].life)
    assert any(c.instance_id == 880356 for c in state.players[1].hand)
    assert any(cp.name == "effect_auto_add_up_to_n_from_owner_hand_to_life_on_owner_leader_attack" for cp in state.checkpoints)


def test_phase4_owner_leader_attack_can_search_top_and_add_matching_card_to_hand() -> None:
    class FakeRepo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: SimpleNamespace(
                    card_name="Leader",
                    power_int=10000,
                    card_type="LEADER",
                    card_color="Red",
                    energy_cost_int=0,
                    combo_cost_int=0,
                    combo_power_int=0,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=True,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    card_skill_unstyled="[Auto] When your Leader Card attacks, look at up to 5 cards from the top of your deck, add up to 1 red Earthling card among them to your hand, then shuffle your deck.",
                    card_traits_json='["Earthling"]',
                    card_character_json='["Krillin"]',
                ),
                900961: SimpleNamespace(
                    card_name="Red Earthling",
                    power_int=5000,
                    card_type="BATTLE",
                    card_color="Red",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    card_skill_unstyled="",
                    card_traits_json='["Earthling"]',
                    card_character_json='["Krillin"]',
                ),
                900962: SimpleNamespace(
                    card_name="Blue Earthling",
                    power_int=5000,
                    card_type="BATTLE",
                    card_color="Blue",
                    energy_cost_int=1,
                    combo_cost_int=0,
                    combo_power_int=5000,
                    keywords=(),
                    has_counter=False,
                    has_activate_main=False,
                    has_activate_battle=False,
                    has_auto=False,
                    has_permanent=False,
                    has_barrier=False,
                    has_draw=False,
                    max_draw_count=None,
                    card_skill_unstyled="",
                    card_traits_json='["Earthling"]',
                    card_character_json='["Krillin"]',
                ),
            }
            return data[card_id]

    engine = RulesEngine(
        card_repository=FakeRepo(),
        effect_rules={
            424284: [
                {
                    "trigger": "owner_leader_attacks",
                    "handler_id": "auto_look_top_add_up_to_one_to_hand_on_play",
                    "handler_params": {
                        "look_count": 5,
                        "max_add": 1,
                        "allowed_colors": "red",
                        "required_traits": "Earthling",
                    },
                }
            ]
        },
    )
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
        CardInstance(instance_id=880357, card_id=424284, owner_id=1, card_type="BATTLE", energy_cost=0)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    state.players[1].deck = [
        CardInstance(instance_id=880358, card_id=900962, owner_id=1, card_type="BATTLE", color="Blue"),
        CardInstance(instance_id=880359, card_id=900961, owner_id=1, card_type="BATTLE", color="Red"),
        *state.players[1].deck,
    ]
    hand_before = len(state.players[1].hand)
    attack = next(
        a
        for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.DECLARE_ATTACK and a.attacker_zone == "leader" and a.target_zone == "leader"
    )
    state = engine.apply_action(state, attack)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].hand) == hand_before + 1
    assert any(c.card_id == 900961 for c in state.players[1].hand)
    assert any(c.card_id == 900962 for c in state.players[1].deck)
    assert any(cp.name == "effect_auto_look_top_add_up_to_one_to_hand_on_play" for cp in state.checkpoints)


def test_phase4_self_played_can_add_from_hand_to_life() -> None:
    engine = RulesEngine(
        effect_rules={
            424288: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_add_up_to_n_from_owner_hand_to_life_on_play",
                    "handler_params": {"amount": 1, "allowed_colors": "yellow", "requires_played_from": "hand"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880362, card_id=424288, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=0),
        CardInstance(instance_id=880363, card_id=900971, owner_id=1, card_type="BATTLE", color="Yellow"),
        CardInstance(instance_id=880364, card_id=900972, owner_id=1, card_type="BATTLE", color="Blue"),
    ]
    life_before = len(state.players[1].life)
    hand_before = len(state.players[1].hand)
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].life) == life_before + 1
    assert len(state.players[1].hand) == hand_before - 2
    assert any(c.instance_id == 880363 for c in state.players[1].life)
    assert any(c.instance_id == 880364 for c in state.players[1].hand)
    assert any(cp.name == "effect_auto_add_up_to_n_from_owner_hand_to_life_on_play" for cp in state.checkpoints)


def test_phase4_field_extra_placed_can_switch_owner_energy_active() -> None:
    engine = RulesEngine(
        effect_rules={
            424284: [
                {
                    "trigger": "owner_field_extra_placed",
                    "handler_id": "auto_switch_up_to_n_owner_energy_active_on_field_extra_placed",
                    "handler_params": {"max_targets": 2, "allowed_colors": "yellow"},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].battle_area.append(
        CardInstance(instance_id=880357, card_id=424284, owner_id=1, card_type="BATTLE", energy_cost=0)
    )
    engine._register_card_effects(state, player_id=1, source_zone="battle", card=state.players[1].battle_area[0])
    state.players[1].energy = [
        CardInstance(instance_id=880358, card_id=900961, owner_id=1, color="Yellow", resting=True),
        CardInstance(instance_id=880359, card_id=900962, owner_id=1, color="Yellow", resting=True),
        CardInstance(instance_id=880360, card_id=900963, owner_id=1, color="Blue", resting=True),
    ]
    state.players[1].hand = [
        CardInstance(
            instance_id=880361,
            card_id=900964,
            owner_id=1,
            card_type="EXTRA",
            energy_cost=0,
            keywords=("Field",),
            has_counter=False,
        )
    ]
    play_extra = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play_extra)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert state.players[1].energy[0].resting is False
    assert state.players[1].energy[1].resting is False
    assert state.players[1].energy[2].resting is True
    assert any(evt.name == "field_extra_placed" for evt in state.effect_events)
    assert any(cp.name == "effect_auto_switch_up_to_n_owner_energy_active_on_field_extra_placed" for cp in state.checkpoints)


def test_phase4_self_played_can_play_from_hand_with_markers_and_rest() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE"),
                2: ("Blue", "BATTLE"),
                424271: ("Blue", "BATTLE"),
                900701: ("Blue", "UNISON"),
            }
            color, ctype = data.get(card_id, ("Blue", "BATTLE"))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
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

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424271: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    "handler_params": {
                        "max_targets": 1,
                        "markers": 1,
                        "source_pool": "hand",
                        "requires_played_from": "hand",
                        "rest_mode": True,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880361, card_id=424271, owner_id=1, card_type="BATTLE", energy_cost=0),
        CardInstance(instance_id=880362, card_id=900701, owner_id=1, card_type="UNISON", energy_cost=0),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].card_id == 900701
    assert state.players[1].unison_area[0].markers == 1
    assert state.players[1].unison_area[0].resting is True
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play" for cp in state.checkpoints)


def test_phase4_self_played_can_play_from_deck_with_markers_when_hand_pool_empty() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE"),
                2: ("Blue", "BATTLE"),
                424272: ("Blue", "BATTLE"),
                900702: ("Blue", "UNISON"),
            }
            color, ctype = data.get(card_id, ("Blue", "BATTLE"))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
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

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424272: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    "handler_params": {
                        "max_targets": 1,
                        "markers": 2,
                        "source_pool": "hand_or_deck",
                        "requires_played_from": "hand",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880371, card_id=424272, owner_id=1, card_type="BATTLE", energy_cost=0),
    ]
    state.players[1].deck = [900702]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].card_id == 900702
    assert state.players[1].unison_area[0].markers == 2
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play" for cp in state.checkpoints)


def test_phase4_self_played_can_play_multiple_from_hand_with_markers() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE"),
                2: ("Blue", "BATTLE"),
                424273: ("Blue", "BATTLE"),
                900711: ("Blue", "BATTLE"),
                900712: ("Blue", "BATTLE"),
            }
            color, ctype = data.get(card_id, ("Blue", "BATTLE"))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
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

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424273: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    "handler_params": {
                        "max_targets": 2,
                        "markers": 3,
                        "source_pool": "hand",
                        "requires_played_from": "hand",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880381, card_id=424273, owner_id=1, card_type="BATTLE", energy_cost=0),
        CardInstance(instance_id=880382, card_id=900711, owner_id=1, card_type="BATTLE", energy_cost=0),
        CardInstance(instance_id=880383, card_id=900712, owner_id=1, card_type="BATTLE", energy_cost=0),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].battle_area) == 3
    played = [c for c in state.players[1].battle_area if c.card_id in {900711, 900712}]
    assert len(played) == 2
    assert all(c.markers == 3 for c in played)
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play" for cp in state.checkpoints)


def test_phase4_self_played_can_fill_remaining_from_deck_after_hand() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE"),
                2: ("Blue", "BATTLE"),
                424274: ("Blue", "BATTLE"),
                900721: ("Blue", "BATTLE"),
                900722: ("Blue", "BATTLE"),
            }
            color, ctype = data.get(card_id, ("Blue", "BATTLE"))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=0,
                combo_cost_int=0,
                combo_power_int=5000,
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

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424274: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    "handler_params": {
                        "max_targets": 2,
                        "markers": 2,
                        "source_pool": "hand_or_deck",
                        "requires_played_from": "hand",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880391, card_id=424274, owner_id=1, card_type="BATTLE", energy_cost=0),
        CardInstance(instance_id=880392, card_id=900721, owner_id=1, card_type="BATTLE", energy_cost=0),
    ]
    state.players[1].deck = [900722]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].battle_area) == 3
    played = [c for c in state.players[1].battle_area if c.card_id in {900721, 900722}]
    assert len(played) == 2
    assert all(c.markers == 2 for c in played)
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play" for cp in state.checkpoints)


def test_phase4_self_played_marker_multi_target_respects_cost_color_type_filters_in_hand() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE", 0),
                2: ("Blue", "BATTLE", 0),
                424275: ("Blue", "BATTLE", 0),
                900731: ("Red", "BATTLE", 1),
                900732: ("Blue", "BATTLE", 2),
                900733: ("Blue", "UNISON", 2),
                900734: ("Blue", "BATTLE", 3),
                900735: ("Blue", "BATTLE", 5),
            }
            color, ctype, cost = data.get(card_id, ("Blue", "BATTLE", 0))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
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
                card_energy_cost=str(cost),
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424275: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    "handler_params": {
                        "max_targets": 2,
                        "markers": 4,
                        "source_pool": "hand",
                        "requires_played_from": "hand",
                        "max_cost": 3,
                        "allowed_colors": "blue",
                        "required_card_type": "BATTLE",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880401, card_id=424275, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=0),
        CardInstance(instance_id=880402, card_id=900731, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1),
        CardInstance(instance_id=880403, card_id=900732, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=2),
        CardInstance(instance_id=880404, card_id=900733, owner_id=1, card_type="UNISON", color="Blue", energy_cost=2),
        CardInstance(instance_id=880405, card_id=900735, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=5),
        CardInstance(instance_id=880406, card_id=900734, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=3),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    played = [c for c in state.players[1].battle_area if c.card_id in {900731, 900732, 900733, 900734, 900735}]
    assert [c.card_id for c in played] == [900732, 900734]
    assert all(c.markers == 4 for c in played)


def test_phase4_self_played_marker_multi_target_respects_filters_when_filling_from_deck() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE", 0),
                2: ("Blue", "BATTLE", 0),
                424276: ("Blue", "BATTLE", 0),
                900741: ("Blue", "BATTLE", 2),
                900742: ("Red", "BATTLE", 2),
                900743: ("Blue", "UNISON", 2),
                900744: ("Blue", "BATTLE", 1),
            }
            color, ctype, cost = data.get(card_id, ("Blue", "BATTLE", 0))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
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
                card_energy_cost=str(cost),
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424276: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_hand_or_deck_with_markers_on_play",
                    "handler_params": {
                        "max_targets": 2,
                        "markers": 2,
                        "source_pool": "hand_or_deck",
                        "requires_played_from": "hand",
                        "max_cost": 2,
                        "allowed_colors": "blue",
                        "required_card_type": "BATTLE",
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880411, card_id=424276, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=0),
        CardInstance(instance_id=880412, card_id=900741, owner_id=1, card_type="BATTLE", color="Blue", energy_cost=2),
    ]
    state.players[1].deck = [900742, 900743, 900744]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    played = [c for c in state.players[1].battle_area if c.card_id in {900741, 900742, 900743, 900744}]
    assert [c.card_id for c in played] == [900741, 900744]
    assert all(c.markers == 2 for c in played)


def test_phase4_self_played_can_add_up_to_n_from_deck_to_hand() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE", 0, ()),
                2: ("Blue", "BATTLE", 0, ()),
                424277: ("Blue", "BATTLE", 0, ()),
                900751: ("Yellow", "EXTRA", 1, ()),
            }
            color, ctype, cost, keywords = data.get(card_id, ("Blue", "BATTLE", 0, ()))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=keywords,
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
                card_energy_cost=str(cost),
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424277: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_add_up_to_n_from_owner_deck_to_hand_on_play",
                    "handler_params": {"max_targets": 1},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=880421, card_id=424277, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[1].deck = [900751]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(c.card_id == 900751 for c in state.players[1].hand)
    assert len(state.players[1].deck) == 0
    assert any(cp.name == "effect_auto_add_up_to_n_from_owner_deck_to_hand_on_play" for cp in state.checkpoints)


def test_phase4_self_played_add_from_deck_to_hand_respects_filters() -> None:
    class Repo:
        def get_by_id(self, card_id: int, source_table: str = "cards"):
            data = {
                1: ("Blue", "BATTLE", 0, ()),
                2: ("Blue", "BATTLE", 0, ()),
                424278: ("Blue", "BATTLE", 0, ()),
                900761: ("Green", "BATTLE", 2, ("skill-less",)),
                900762: ("Green", "BATTLE", 4, ("skill-less",)),
                900763: ("Green", "UNISON", 2, ("skill-less",)),
                900764: ("Yellow", "BATTLE", 2, ("skill-less",)),
                900765: ("Green", "BATTLE", 1, ()),
                900766: ("Green", "BATTLE", 1, ("skill-less",)),
            }
            color, ctype, cost, keywords = data.get(card_id, ("Blue", "BATTLE", 0, ()))
            return SimpleNamespace(
                power_int=15000,
                card_type=ctype,
                card_color=color,
                energy_cost_int=cost,
                combo_cost_int=0,
                combo_power_int=5000,
                keywords=keywords,
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
                card_energy_cost=str(cost),
                card_skill_unstyled="",
            )

    engine = RulesEngine(
        card_repository=Repo(),
        effect_rules={
            424278: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_add_up_to_n_from_owner_deck_to_hand_on_play",
                    "handler_params": {
                        "max_targets": 2,
                        "max_cost": 3,
                        "allowed_colors": "green",
                        "required_card_type": "BATTLE",
                        "requires_skill_less": True,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [CardInstance(instance_id=880431, card_id=424278, owner_id=1, card_type="BATTLE", energy_cost=0)]
    state.players[1].deck = [900762, 900763, 900764, 900765, 900761, 900766]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    added = [c.card_id for c in state.players[1].hand if c.card_id in {900761, 900762, 900763, 900764, 900765, 900766}]
    assert added == [900761, 900766]
    assert state.players[1].deck == [900762, 900763, 900764, 900765]


def test_phase4_self_played_adds_markers_per_multicolor_energy() -> None:
    engine = RulesEngine(
        effect_rules={
            424279: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_add_markers_per_n_multicolor_energy_on_play",
                    "handler_params": {"per_n_energy": 1},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880441, card_id=900801, owner_id=1, color="Blue"),
        CardInstance(instance_id=880442, card_id=900802, owner_id=1, color="Yellow"),
        CardInstance(instance_id=880443, card_id=900803, owner_id=1, color="Red/Blue"),
        CardInstance(instance_id=880445, card_id=900804, owner_id=1, color="Blue/Green"),
    ]
    state.players[1].hand = [
        CardInstance(instance_id=880444, card_id=424279, owner_id=1, card_type="UNISON", color="Blue", energy_cost=1, markers=1),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].markers == 3
    assert any(cp.name == "effect_auto_add_markers_per_n_multicolor_energy_on_play" for cp in state.checkpoints)


def test_phase4_self_played_adds_markers_requires_min_source_markers() -> None:
    engine = RulesEngine(
        effect_rules={
            424280: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_add_markers_per_n_multicolor_energy_on_play",
                    "handler_params": {"per_n_energy": 1, "min_source_markers": 2},
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [
        CardInstance(instance_id=880451, card_id=900811, owner_id=1, color="Blue"),
        CardInstance(instance_id=880452, card_id=900812, owner_id=1, color="Red/Yellow"),
    ]
    state.players[1].hand = [
        CardInstance(instance_id=880453, card_id=424280, owner_id=1, card_type="UNISON", color="Blue", energy_cost=1, markers=1),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].unison_area) == 1
    assert state.players[1].unison_area[0].markers == 1
    assert not any(cp.name == "effect_auto_add_markers_per_n_multicolor_energy_on_play" for cp in state.checkpoints)


def test_phase4_self_played_can_play_from_drop_rest_with_skills_negated_and_discard_cost() -> None:
    engine = RulesEngine(
        effect_rules={
            424281: [
                {
                    "trigger": "self_played",
                    "handler_id": "auto_play_up_to_n_from_owner_drop_on_play",
                    "handler_params": {
                        "max_targets": 1,
                        "max_cost": 2,
                        "allowed_colors": "yellow",
                        "required_card_type": "BATTLE",
                        "rest_mode": True,
                        "negate_skills": True,
                        "discard_from_hand_before": 1,
                    },
                }
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].hand = [
        CardInstance(instance_id=880461, card_id=424281, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=0),
        CardInstance(instance_id=880462, card_id=900901, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=0),
    ]
    state.players[1].drop = [
        CardInstance(
            instance_id=880463,
            card_id=900902,
            owner_id=1,
            card_type="BATTLE",
            color="Yellow",
            energy_cost=2,
            keywords=("Double Strike",),
            has_auto=True,
            has_activate_main=True,
            has_permanent=True,
        ),
        CardInstance(instance_id=880464, card_id=900903, owner_id=1, card_type="BATTLE", color="Yellow", energy_cost=4),
    ]
    play = next(a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0)
    state = engine.apply_action(state, play)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert any(c.instance_id == 880461 for c in state.players[1].battle_area)
    played = next(c for c in state.players[1].battle_area if c.instance_id == 880463)
    assert played.resting is True
    assert played.keywords == ()
    assert played.has_auto is False
    assert played.has_activate_main is False
    assert played.has_permanent is False
    assert all(r.source_instance_id != 880463 for r in state.effect_registry)
    assert any(c.instance_id == 880462 for c in state.players[1].drop)
    assert any(c.instance_id == 880464 for c in state.players[1].drop)
    assert any(cp.name == "effect_auto_play_up_to_n_from_owner_drop_on_play" for cp in state.checkpoints)


def test_phase4_activate_extra_from_hand_exposes_effect_choice_actions_and_selected_search_effect_resolves() -> None:
    engine = RulesEngine(
        effect_rules={
            424301: [
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_play_up_to_n_each_named_from_owner_deck_or_drop",
                    "handler_params": {
                        "max_each": 1,
                        "required_name_contains_each": "SON GOTEN|TRUNKS : YOUTH",
                        "allowed_colors": "red",
                        "required_card_type": "BATTLE",
                        "max_cost": 1,
                        "rest_mode": True,
                        "discard_from_hand_before": 1,
                    },
                },
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_add_up_to_n_from_owner_deck_to_hand",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "red",
                        "required_card_type": "EXTRA",
                        "max_cost": 1,
                    },
                    "limit_per_turn": 1,
                },
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [CardInstance(instance_id=880471, card_id=900911, owner_id=1, color="Red")]
    state.players[1].hand = [
        CardInstance(instance_id=880472, card_id=424301, owner_id=1, card_type="EXTRA", color="Red", energy_cost=1),
        CardInstance(instance_id=880473, card_id=900912, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1),
    ]
    state.players[1].deck = [900913, 900914]
    engine._card_cache[(900913, "front")] = CardRuntimeData(card_name="Search Extra", card_type="EXTRA", color="Red", energy_cost=1)
    legal = [a for a in engine.get_legal_actions(state, 1) if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0]
    assert len(legal) == 2
    assert {a.effect_choice for a in legal} == {0, 1}
    search_action = next(a for a in legal if a.effect_choice == 1)
    state = engine.apply_action(state, search_action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert [c.card_id for c in state.players[1].hand] == [900912, 900913]
    assert not state.players[1].battle_area
    assert any(cp.name == "effect_activate_add_up_to_n_from_owner_deck_to_hand" for cp in state.checkpoints)
    assert not any(cp.name == "effect_activate_play_up_to_n_each_named_from_owner_deck_or_drop" for cp in state.checkpoints)


def test_phase4_activate_extra_from_hand_selected_play_effect_discards_and_plays_each_named() -> None:
    engine = RulesEngine(
        effect_rules={
            424302: [
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_play_up_to_n_each_named_from_owner_deck_or_drop",
                    "handler_params": {
                        "max_each": 1,
                        "required_name_contains_each": "SON GOTEN|TRUNKS : YOUTH",
                        "allowed_colors": "red",
                        "required_card_type": "BATTLE",
                        "max_cost": 1,
                        "rest_mode": True,
                        "discard_from_hand_before": 1,
                    },
                },
                {
                    "trigger": "self_activate_extra_from_hand",
                    "handler_id": "activate_add_up_to_n_from_owner_deck_to_hand",
                    "handler_params": {
                        "max_targets": 1,
                        "allowed_colors": "red",
                        "required_card_type": "EXTRA",
                        "max_cost": 1,
                    },
                },
            ]
        },
    )
    state = engine.initialize_game(
        p1_leader_card_id=1,
        p1_deck_card_ids=_deck(1000),
        p2_leader_card_id=2,
        p2_deck_card_ids=_deck(2000),
        shuffle_decks=False,
    )
    state = _to_main(engine, state)
    state.players[1].energy = [CardInstance(instance_id=880481, card_id=900921, owner_id=1, color="Red")]
    state.players[1].hand = [
        CardInstance(instance_id=880482, card_id=424302, owner_id=1, card_type="EXTRA", color="Red", energy_cost=1),
        CardInstance(instance_id=880483, card_id=900922, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1),
    ]
    state.players[1].deck = [900923]
    state.players[1].drop = [
        CardInstance(instance_id=880484, card_id=900924, owner_id=1, card_type="BATTLE", color="Red", energy_cost=1),
    ]
    engine._card_cache[(900923, "front")] = CardRuntimeData(card_name="Son Goten", card_type="BATTLE", color="Red", energy_cost=1)
    engine._card_cache[(900924, "front")] = CardRuntimeData(card_name="Trunks : Youth", card_type="BATTLE", color="Red", energy_cost=1)
    play_action = next(
        a for a in engine.get_legal_actions(state, 1)
        if a.action_type == ActionType.PLAY_CARD_FROM_HAND and a.hand_index == 0 and a.effect_choice == 0
    )
    state = engine.apply_action(state, play_action)
    state = engine.apply_action(state, Action(action_type=ActionType.PASS_COUNTER_WINDOW, player_id=2))
    assert len(state.players[1].battle_area) == 2
    assert all(card.resting for card in state.players[1].battle_area)
    assert {card.card_id for card in state.players[1].battle_area} == {900923, 900924}
    assert any(card.instance_id == 880483 for card in state.players[1].drop)
    assert any(cp.name == "effect_activate_play_up_to_n_each_named_from_owner_deck_or_drop" for cp in state.checkpoints)


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
