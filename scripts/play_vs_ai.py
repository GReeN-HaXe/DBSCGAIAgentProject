from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

try:
    import msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import (
    HeuristicPolicy,
    HumanVsAiSession,
    build_compact_match_summary,
    compute_trace_hash,
    describe_action,
    evaluate_match_expectations,
    summarize_state_for_cli,
    validate_deck_legality,
)
from src.agent.deck_setup import (
    import_deckplanet_deck_text,
    load_sample_game_setup_from_db,
    read_card_ids_file,
    validate_leader_and_deck,
)
from src.db import SQLiteCardRepository
from src.game import RulesEngine, load_game_state_json, save_game_state_json


def _build_deck(seed: int, size: int = 60) -> list[int]:
    return [seed + i for i in range(size)]


def _init_state(
    engine: RulesEngine,
    *,
    first_player: int,
    p1_leader: int,
    p1_deck: list[int],
    p2_leader: int,
    p2_deck: list[int],
    shuffle_decks: bool,
    random_seed: int | None,
) -> object:
    return engine.initialize_game(
        p1_leader_card_id=p1_leader,
        p1_deck_card_ids=p1_deck,
        p2_leader_card_id=p2_leader,
        p2_deck_card_ids=p2_deck,
        first_player=first_player,
        shuffle_decks=shuffle_decks,
        random_seed=random_seed,
    )


def _card_name_resolver(repo: SQLiteCardRepository | None):
    def _short_skill(card) -> str:
        raw = (card.card_skill_unstyled or "").strip()
        if not raw:
            return ""
        flat = " ".join(raw.split())
        return flat[:72] + ("..." if len(flat) > 72 else "")

    def _resolve(card_id: int) -> str:
        if repo is None:
            return f"card_id={card_id}"
        try:
            card = repo.get_by_id(int(card_id))
            tags: list[str] = []
            if card.card_type:
                tags.append(str(card.card_type))
            if card.card_color:
                tags.append(str(card.card_color))
            if card.has_counter:
                tags.append("Counter")
            if card.has_activate_main:
                tags.append("ActMain")
            if card.has_activate_battle:
                tags.append("ActBattle")
            if card.has_auto:
                tags.append("Auto")
            if card.has_permanent:
                tags.append("Perm")
            if card.has_draw:
                tags.append("Draw")
            if card.has_barrier:
                tags.append("Barrier")
            if getattr(card, "grants_triple_strike", False):
                tags.append("Triple")
            cost = card.energy_cost_int if card.energy_cost_int is not None else card.card_energy_cost or "-"
            power = card.power_int if card.power_int is not None else card.card_power or "-"
            combo = card.combo_power_int if card.combo_power_int is not None else card.card_combo_power or "-"
            tag_suffix = f" tags={','.join(tags)}" if tags else ""
            skill = _short_skill(card)
            skill_suffix = f" skill=\"{skill}\"" if skill else ""
            return f"{card.card_number} {card.card_name} cost={cost} power={power} combo={combo}{tag_suffix}{skill_suffix}"
        except Exception:
            return f"card_id={card_id}"

    return _resolve


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return bool(sys.stdout.isatty())


def _style(text: str, code: str, *, use_color: bool) -> str:
    if not use_color:
        return text
    return f"\033[{code}m{text}\033[0m"


def _clear_screen(*, use_color: bool) -> None:
    if use_color:
        print("\033[2J\033[H", end="")


def _leader_id_from_player(state, player_id: int) -> int:
    return int(state.players[int(player_id)].leader_area.card_id)


def _card_brief_label(repo: SQLiteCardRepository | None, card_id: int) -> str:
    if repo is None:
        return f"card_id={card_id}"
    try:
        card = repo.get_by_id(int(card_id))
        return f"{card.card_number} {card.card_name}"
    except Exception:
        return f"card_id={card_id}"


def _card_detail_text(repo: SQLiteCardRepository | None, card_id: int) -> str:
    if repo is None:
        return f"card_id={card_id}"
    try:
        card = repo.get_by_id(int(card_id))
    except Exception:
        return f"card_id={card_id}"
    tags: list[str] = []
    if card.card_type:
        tags.append(str(card.card_type))
    if card.card_color:
        tags.append(str(card.card_color))
    if card.has_counter:
        tags.append("Counter")
    if card.has_activate_main:
        tags.append("ActMain")
    if card.has_activate_battle:
        tags.append("ActBattle")
    if card.has_auto:
        tags.append("Auto")
    if card.has_permanent:
        tags.append("Perm")
    if card.has_draw:
        tags.append("Draw")
    if card.has_barrier:
        tags.append("Barrier")
    if getattr(card, "grants_triple_strike", False):
        tags.append("Triple")
    skill = " ".join((card.card_skill_unstyled or "").split()).strip()
    lines = [
        f"{card.card_number} {card.card_name}",
        f"Type: {card.card_type or '-'}",
        f"Color: {card.card_color or '-'}",
        f"Cost: {card.energy_cost_int if card.energy_cost_int is not None else card.card_energy_cost or '-'}",
        f"Power: {card.power_int if card.power_int is not None else card.card_power or '-'}",
        f"Combo: {card.combo_power_int if card.combo_power_int is not None else card.card_combo_power or '-'}",
        f"Tags: {', '.join(tags) if tags else '-'}",
    ]
    if skill:
        lines.append(f"Skill: {skill}")
    return "\n".join(lines)


def _card_row(repo: SQLiteCardRepository | None, card_id: int) -> str:
    if repo is None:
        return f"{card_id}"
    try:
        card = repo.get_by_id(int(card_id))
    except Exception:
        return f"{card_id}"
    tags: list[str] = []
    if card.has_counter:
        tags.append("Counter")
    if card.has_activate_main:
        tags.append("ActMain")
    if card.has_activate_battle:
        tags.append("ActBattle")
    if card.has_draw:
        tags.append("Draw")
    if card.has_barrier:
        tags.append("Barrier")
    if getattr(card, "grants_triple_strike", False):
        tags.append("Triple")
    name = str(card.card_name)
    if len(name) > 24:
        name = name[:24] + "..."
    cost = card.energy_cost_int if card.energy_cost_int is not None else card.card_energy_cost or "-"
    power = card.power_int if card.power_int is not None else card.card_power or "-"
    combo = card.combo_power_int if card.combo_power_int is not None else card.card_combo_power or "-"
    tag_suffix = f" {' '.join(tags)}" if tags else ""
    return f"{card.card_number} {name:<27} {cost}c {str(power):>5} {str(combo):>5}combo{tag_suffix}"


def _compact_resolver(repo: SQLiteCardRepository | None):
    def _resolve(card_id: int) -> str:
        return _card_brief_label(repo, card_id)

    return _resolve


def _print_compact_hand(session: HumanVsAiSession, *, repo: SQLiteCardRepository | None) -> None:
    player = session.state.players[int(session.human_player_id)]
    print("\nYour hand:")
    for index, card in enumerate(player.hand):
        print(f"  [{index}] {_card_row(repo, card.card_id)}")


def _zone_row(repo: SQLiteCardRepository | None, cards: list[object]) -> str:
    if not cards:
        return "-"
    rendered: list[str] = []
    for index, card in enumerate(cards):
        label = _card_brief_label(repo, int(card.card_id))
        short = label if len(label) <= 24 else label[:24] + "..."
        power = getattr(card, "power", "-")
        mode = "R" if getattr(card, "resting", False) else "A"
        rendered.append(f"[{index}] {short} {power} ({mode})")
    return " | ".join(rendered)


def _truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def _panel_box(
    title: str,
    lines: list[str],
    *,
    width: int,
    body_height: int | None = None,
    focused: bool,
    use_color: bool,
) -> list[str]:
    inner = max(8, width - 2)
    title_text = f" {title} "
    border = "=" if focused else "-"
    top_fill = max(0, inner - len(title_text))
    top = "+" + title_text + (border * top_fill) + "+"
    rendered = [top]
    body_height = max(8, len(lines)) if body_height is None else max(8, int(body_height))
    for idx in range(body_height):
        line = lines[idx] if idx < len(lines) else ""
        rendered.append("|" + _truncate(line, inner).ljust(inner) + "|")
    rendered.append("+" + (border * inner) + "+")
    if focused:
        rendered = [_style(line, "1;33", use_color=use_color) for line in rendered]
    return rendered


def _merge_panel_columns(columns: list[list[str]]) -> str:
    heights = [len(col) for col in columns]
    padded: list[list[str]] = []
    for col, height in zip(columns, heights):
        width = max((len(line) for line in col), default=0)
        extra = [" " * width for _ in range(max(heights) - height)]
        padded.append(col + extra)
    lines: list[str] = []
    for row in range(max(heights, default=0)):
        lines.append("  ".join(col[row] for col in padded))
    return "\n".join(lines)


def _windowed_lines(lines: list[str], *, selected: int, body_height: int) -> list[str]:
    if body_height <= 0 or len(lines) <= body_height:
        return lines
    selected = max(0, min(selected, len(lines) - 1))
    start = max(0, selected - body_height // 2)
    end = start + body_height
    if end > len(lines):
        end = len(lines)
        start = max(0, end - body_height)
    return lines[start:end]


def _summary_panel_lines(session: HumanVsAiSession, *, repo: SQLiteCardRepository | None) -> list[str]:
    state = session.state
    p1 = state.players[1]
    p2 = state.players[2]
    p1_active_energy = sum(1 for card in p1.energy if not getattr(card, "resting", False))
    p2_active_energy = sum(1 for card in p2.energy if not getattr(card, "resting", False))
    return [
        f"Turn {state.turn_number} | Phase {state.phase.value} | Active P{state.active_player} | Winner {state.winner_id}",
        f"P1 {_card_brief_label(repo, _leader_id_from_player(state, 1))}",
        f"   life {len(p1.life)} | hand {len(p1.hand)} | energy {len(p1.energy)} | battle {len(p1.battle_area)} | unison {len(p1.unison_area)}",
        f"   energy_row active {p1_active_energy} / rest {len(p1.energy) - p1_active_energy}",
        f"P2 {_card_brief_label(repo, _leader_id_from_player(state, 2))}",
        f"   life {len(p2.life)} | hand {len(p2.hand)} | energy {len(p2.energy)} | battle {len(p2.battle_area)} | unison {len(p2.unison_area)}",
        f"   energy_row active {p2_active_energy} / rest {len(p2.energy) - p2_active_energy}",
    ]


def _hand_panel_lines(session: HumanVsAiSession, *, repo: SQLiteCardRepository | None, selected: int) -> list[str]:
    player = session.state.players[int(session.human_player_id)]
    lines = ["Use Up/Down here, Enter shows card detail"]
    for index, card in enumerate(player.hand):
        prefix = ">" if index == selected else " "
        lines.append(f"{prefix} [{index}] {_card_row(repo, card.card_id)}")
    if len(player.hand) == 0:
        lines.append("(empty hand)")
    return lines


def _compact_reason(reason: str) -> str:
    parts = reason.replace("_", " ").split()
    if not parts:
        return "-"
    return " ".join(parts[:4])


def _action_panel_lines(
    session: HumanVsAiSession,
    *,
    repo: SQLiteCardRepository | None,
    use_color: bool,
    legal: list[object],
    selected: int,
) -> list[str]:
    ranked = session.ai_policy.rank_actions(session.state, legal)
    ranked_map = {id(item.action): item for item in ranked}
    best_action_id = id(ranked[0].action) if ranked else None
    lines = ["Use Up/Down here, Enter chooses selected action"]
    for i, action in enumerate(legal):
        text = _compact_action_text(action, state=session.state, repo=repo)
        hints = _action_hints(session, action, repo=repo)
        ranked_item = ranked_map.get(id(action))
        score_text = f"{ranked_item.score:>6.1f}" if ranked_item is not None else "  n/a "
        prefix = ">" if i == selected else " "
        best_marker = "*" if id(action) == best_action_id else " "
        suffix = ""
        if hints:
            rendered_hints = " ".join(_style_hint(h, use_color=use_color) for h in hints)
            suffix = f" {rendered_hints}"
        reason_text = _compact_reason(ranked_item.reason) if ranked_item is not None else "-"
        lines.append(f"{prefix}{best_marker}[{i:>2}] {_truncate(text, 34):<34} {score_text} {_truncate(reason_text, 18):<18}{suffix}")
    return lines


def _board_entries(session: HumanVsAiSession, *, repo: SQLiteCardRepository | None) -> list[tuple[str, str]]:
    state = session.state
    entries: list[tuple[str, str]] = []
    for player_id in (1, 2):
        player = state.players[player_id]
        if player.battle_area:
            entries.append((f"P{player_id} BATTLE", _zone_row(repo, player.battle_area)))
        if player.unison_area:
            entries.append((f"P{player_id} UNISON", _zone_row(repo, player.unison_area)))
        if player.energy:
            entries.append((f"P{player_id} ENERGY", _zone_row(repo, player.energy)))
    if not entries:
        entries.append(("Board", "No zone cards in play"))
    return entries


def _board_panel_lines(entries: list[tuple[str, str]], *, selected: int) -> list[str]:
    lines = ["Use Up/Down here, Enter opens full zone view", ""]
    for index, (label, detail) in enumerate(entries):
        prefix = ">" if index == selected else " "
        lines.append(f"{prefix} [{index}] {label:<12} {_truncate(detail, 44)}")
    lines.append("")
    if entries:
        label, detail = entries[selected]
        lines.append(f"Selected: {label}")
        lines.append(_truncate(detail, 58))
    return lines


def _focus_status_line(
    *,
    focus: str,
    hand_selected: int,
    hand_count: int,
    action_selected: int,
    action_count: int,
    board_selected: int,
    board_entries: list[tuple[str, str]],
    use_color: bool,
) -> str:
    focused_label = {"hand": "Hand", "actions": "Actions", "board": "Board"}[focus]
    board_label = board_entries[board_selected][0] if board_entries else "-"
    text = (
        f"Focus {focused_label} | "
        f"Hand {hand_selected + 1}/{max(1, hand_count)} | "
        f"Action {action_selected + 1}/{max(1, action_count)} | "
        f"Board {board_selected + 1}/{max(1, len(board_entries))}: {board_label}"
    )
    return _style(text, "1;37", use_color=use_color)


def _selected_action_footer_lines(
    session: HumanVsAiSession,
    *,
    repo: SQLiteCardRepository | None,
    legal: list[object],
    action_selected: int,
    use_color: bool,
) -> list[str]:
    if not legal:
        return []
    action = legal[action_selected]
    score, reason = session.ai_policy.score_action_with_reason(session.state, action)
    compact = _compact_action_text(action, state=session.state, repo=repo)
    hints = _action_hints(session, action, repo=repo)
    hint_text = " ".join(hints) if hints else "-"
    lines = [
        _style(f"Selected: {_truncate(compact, 110)}", "1;36", use_color=use_color),
        f"Recommendation: score={score:.2f} | reason={reason} | hints={hint_text}",
    ]
    player = session.state.players.get(int(action.player_id))
    if (
        player is not None
        and action.hand_index is not None
        and 0 <= int(action.hand_index) < len(player.hand)
    ):
        card = player.hand[int(action.hand_index)]
        lines.append(f"Card: {_card_row(repo, card.card_id)}")
        skill = _card_detail_text(repo, card.card_id).splitlines()
        if skill:
            for line in skill:
                if line.startswith("Skill: "):
                    lines.append(_truncate(line, 120))
                    break
    return lines


def _linked_hand_index(session: HumanVsAiSession, legal: list[object], action_selected: int, fallback: int) -> int:
    if 0 <= action_selected < len(legal):
        action = legal[action_selected]
        player = session.state.players.get(int(action.player_id))
        if (
            player is not None
            and int(action.player_id) == int(session.human_player_id)
            and action.hand_index is not None
            and 0 <= int(action.hand_index) < len(player.hand)
        ):
            return int(action.hand_index)
    return fallback


def _show_board_entry_detail(
    session: HumanVsAiSession,
    *,
    repo: SQLiteCardRepository | None,
    board_entries: list[tuple[str, str]],
    entry_index: int,
) -> None:
    if entry_index < 0 or entry_index >= len(board_entries):
        print(f"Board entry out of range: 0..{len(board_entries)-1}")
        return
    label, detail = board_entries[entry_index]
    print(f"\n{label}:")
    print(detail)
    print(
        "\n"
        + summarize_state_for_cli(
            session.state,
            card_name_resolver=_card_name_resolver(repo),
            reveal_hand_player_ids=(),
            show_zone_details=True,
        )
    )


def _render_tui_layout(
    session: HumanVsAiSession,
    *,
    repo: SQLiteCardRepository | None,
    legal: list[object],
    use_color: bool,
    focus: str,
    hand_selected: int,
    action_selected: int,
    board_selected: int,
) -> tuple[list[tuple[str, str]], str]:
    terminal_size = shutil.get_terminal_size((180, 40))
    terminal_width = terminal_size.columns
    terminal_height = terminal_size.lines
    total_width = max(120, terminal_width - 2)
    panel_body_height = max(10, min(16, terminal_height - 18))
    summary_box = _panel_box(
        "Summary",
        _summary_panel_lines(session, repo=repo),
        width=total_width,
        body_height=5,
        focused=False,
        use_color=use_color,
    )
    hand_width = max(42, total_width // 3)
    board_width = max(44, total_width // 3)
    action_width = max(54, total_width - hand_width - board_width - 4)
    board_entries = _board_entries(session, repo=repo)
    effective_hand_selected = _linked_hand_index(session, legal, action_selected, hand_selected)
    hand_lines = _hand_panel_lines(session, repo=repo, selected=effective_hand_selected)
    hand_lines = [hand_lines[0], *(_windowed_lines(hand_lines[1:], selected=effective_hand_selected, body_height=panel_body_height - 1))]
    action_lines = _action_panel_lines(session, repo=repo, use_color=use_color, legal=legal, selected=action_selected)
    action_lines = [action_lines[0], *(_windowed_lines(action_lines[1:], selected=action_selected, body_height=panel_body_height - 1))]
    board_lines = _board_panel_lines(board_entries, selected=board_selected)
    static_prefix = board_lines[:2]
    dynamic_rows = board_lines[2 : 2 + len(board_entries)]
    board_detail = board_lines[2 + len(board_entries) :]
    dynamic_rows = _windowed_lines(dynamic_rows, selected=board_selected, body_height=max(3, panel_body_height - len(static_prefix) - len(board_detail)))
    board_lines = static_prefix + dynamic_rows + board_detail
    columns = [
        _panel_box("Hand", hand_lines, width=hand_width, body_height=panel_body_height, focused=focus == "hand", use_color=use_color),
        _panel_box(
            "Actions",
            action_lines,
            width=action_width,
            body_height=panel_body_height,
            focused=focus == "actions",
            use_color=use_color,
        ),
        _panel_box("Board", board_lines, width=board_width, body_height=panel_body_height, focused=focus == "board", use_color=use_color),
    ]
    footer = [
        _focus_status_line(
            focus=focus,
            hand_selected=effective_hand_selected,
            hand_count=len(session.state.players[int(session.human_player_id)].hand),
            action_selected=action_selected,
            action_count=len(legal),
            board_selected=board_selected,
            board_entries=board_entries,
            use_color=use_color,
        ),
        *_selected_action_footer_lines(
            session,
            repo=repo,
            legal=legal,
            action_selected=action_selected,
            use_color=use_color,
        ),
        _style("Focus: Left/Right switch panels | Up/Down navigate | Enter action/detail", "1;37", use_color=use_color),
        "a: action detail | d: hand card detail | l: full history | t: turn history | b: full board | h: help | q: quit",
    ]
    rendered = "\n".join(summary_box) + "\n\n" + _merge_panel_columns(columns) + "\n\n" + "\n".join(footer)
    return board_entries, rendered


def _action_hints(session: HumanVsAiSession, action, *, repo: SQLiteCardRepository | None) -> list[str]:
    hints: list[str] = []
    state = session.state
    player = state.players[action.player_id]
    score, reason = session.ai_policy.score_action_with_reason(state, action)
    available_energy = sum(1 for energy in player.energy if not energy.resting) + int(player.energy_markers)

    if action.action_type.value == "charge_from_hand" and action.hand_index is not None and 0 <= action.hand_index < len(player.hand):
        card = player.hand[action.hand_index]
        if card.has_counter:
            hints.append("keep_counter")
        elif not card.has_counter and not card.has_activate_main and not card.has_activate_battle and int(card.energy_cost or 0) >= 2:
            hints.append("good_charge")
    elif action.action_type.value == "play_card_from_hand" and action.hand_index is not None and 0 <= action.hand_index < len(player.hand):
        card = player.hand[action.hand_index]
        if int(card.energy_cost or 0) == available_energy or card.has_draw or card.auto_draw_on_play:
            hints.append("curve_play")
        if int(card.power or 0) >= 15000 or getattr(card, "grants_triple_strike", False):
            hints.append("pressure")
    elif action.action_type.value == "declare_attack" and action.target_zone == "leader":
        hints.append("pressure")
    elif action.action_type.value in {"activate_main_skill", "activate_battle_skill"} and score >= 90:
        hints.append("pressure")

    if reason == "charge_from_hand" and "good_charge" not in hints and "keep_counter" not in hints:
        hints.append("good_charge")
    return list(dict.fromkeys(hints))


def _style_hint(hint: str, *, use_color: bool) -> str:
    palette = {
        "good_charge": "32",
        "keep_counter": "33",
        "curve_play": "36",
        "pressure": "31",
    }
    return _style(f"[{hint}]", palette.get(hint, "37"), use_color=use_color)


def _compact_action_text(action, *, state, repo: SQLiteCardRepository | None) -> str:
    action_type = action.action_type.value
    if action_type == "end_charge":
        return "End charge"
    if action_type == "end_turn":
        return "End turn"
    if action_type == "pass_counter_window":
        return "Pass counter window"
    if action_type == "charge_from_hand":
        if action.hand_index is not None:
            player = state.players.get(action.player_id)
            if player is not None and 0 <= action.hand_index < len(player.hand):
                label = _card_brief_label(repo, player.hand[action.hand_index].card_id)
                return f"Charge [{action.hand_index}] {label}"
            return f"Charge [{action.hand_index}]"
        return "Charge energy"
    if action.hand_index is not None:
        player = state.players.get(action.player_id)
        if player is not None and 0 <= action.hand_index < len(player.hand):
            label = _card_brief_label(repo, player.hand[action.hand_index].card_id)
            verb = action_type.replace("_", " ")
            return f"{verb} [{action.hand_index}] {label}"
    if action.action_type.value in {"activate_main_skill", "activate_battle_skill"}:
        source_card = None
        if action.source_zone == "leader":
            source_card = state.players[action.player_id].leader_area
        elif action.source_zone == "battle" and action.source_index is not None:
            battle = state.players[action.player_id].battle_area
            if 0 <= action.source_index < len(battle):
                source_card = battle[action.source_index]
        elif action.source_zone == "unison" and action.source_index is not None:
            zone = state.players[action.player_id].unison_area
            if 0 <= action.source_index < len(zone):
                source_card = zone[action.source_index]
        source_label = _card_brief_label(repo, source_card.card_id) if source_card is not None else action.source_zone or "unknown"
        return f"Use skill: {source_label}"
    if action.action_type.value == "declare_attack":
        attacker = action.attacker_zone or "attacker"
        target = action.target_zone or "target"
        return f"Attack with {attacker} -> {target}"
    return describe_action(action, state=state, card_name_resolver=_compact_resolver(repo))


def _show_hand_card_detail(session: HumanVsAiSession, *, repo: SQLiteCardRepository | None, hand_index: int) -> None:
    player = session.state.players[int(session.human_player_id)]
    if hand_index < 0 or hand_index >= len(player.hand):
        print(f"Hand index out of range: 0..{len(player.hand)-1}")
        return
    print("\n" + _card_detail_text(repo, player.hand[hand_index].card_id))


def _show_action_detail(session: HumanVsAiSession, *, repo: SQLiteCardRepository | None, legal: list[object], action_index: int) -> None:
    if action_index < 0 or action_index >= len(legal):
        print(f"Action index out of range: 0..{len(legal)-1}")
        return
    action = legal[action_index]
    print("\nAction:")
    print(describe_action(action, state=session.state, card_name_resolver=_card_name_resolver(repo)))
    score, reason = session.ai_policy.score_action_with_reason(session.state, action)
    print(f"\nHeuristic score: {score:.2f}")
    print(f"Heuristic reason: {reason}")
    ranked = session.ai_policy.rank_actions(session.state, legal)
    top_ranked = ranked[:5]
    print("\nTop action ranking:")
    for rank, item in enumerate(top_ranked, start=1):
        marker = " <selected>" if item.action == action else ""
        compact = _compact_action_text(item.action, state=session.state, repo=repo)
        print(f"  {rank}. {compact} | score={item.score:.2f} | reason={item.reason}{marker}")
    if action.hand_index is not None:
        _show_hand_card_detail(session, repo=repo, hand_index=action.hand_index)
        return
    if action.source_zone == "leader":
        print("\n" + _card_detail_text(repo, session.state.players[action.player_id].leader_area.card_id))
        return
    if action.source_zone == "battle" and action.source_index is not None:
        zone = session.state.players[action.player_id].battle_area
        if 0 <= action.source_index < len(zone):
            print("\n" + _card_detail_text(repo, zone[action.source_index].card_id))
            return
    if action.source_zone == "unison" and action.source_index is not None:
        zone = session.state.players[action.player_id].unison_area
        if 0 <= action.source_index < len(zone):
            print("\n" + _card_detail_text(repo, zone[action.source_index].card_id))


def _history_action_text(entry: dict[str, object], *, repo: SQLiteCardRepository | None) -> str:
    text = str(entry.get("action", "unknown"))
    for field, label in (
        ("hand_card_id", "card"),
        ("source_card_id", "source_card"),
        ("attacker_card_id", "attacker_card"),
        ("target_card_id", "target_card"),
    ):
        value = entry.get(field)
        if value is None or f"{label}=" in text:
            continue
        try:
            rendered = _card_brief_label(repo, int(value))
        except Exception:
            rendered = f"card_id={value}"
        text += f" {label}={rendered}"
    return text


def _build_turn_history_summary(session: HumanVsAiSession, *, repo: SQLiteCardRepository | None) -> list[dict[str, object]]:
    grouped: dict[int, list[dict[str, object]]] = {}
    for entry in list(session.action_trace or []):
        grouped.setdefault(int(entry.get("turn_number", -1)), []).append(entry)
    summaries: list[dict[str, object]] = []
    for turn in sorted(grouped):
        entries = grouped[turn]
        counts = {
            "charges": 0,
            "plays": 0,
            "attacks": 0,
            "skills": 0,
            "end_turns": 0,
        }
        rendered_actions: list[str] = []
        for entry in entries:
            action_type = str(entry.get("action_type", ""))
            if action_type == "charge_from_hand":
                counts["charges"] += 1
            elif action_type == "play_card_from_hand":
                counts["plays"] += 1
            elif action_type == "declare_attack":
                counts["attacks"] += 1
            elif action_type in {"activate_main_skill", "activate_battle_skill"}:
                counts["skills"] += 1
            elif action_type == "end_turn":
                counts["end_turns"] += 1
            rendered_actions.append(
                f"{entry.get('action_index', '?')}. P{entry.get('player_id', '?')} {_history_action_text(entry, repo=repo)}"
            )
        summaries.append(
            {
                "turn_number": turn,
                "action_count": len(entries),
                **counts,
                "actions": rendered_actions,
            }
        )
    return summaries


def _show_action_history(
    session: HumanVsAiSession,
    *,
    repo: SQLiteCardRepository | None,
    use_color: bool,
    turn_number: int | None = None,
) -> None:
    trace = list(session.action_trace or [])
    if turn_number is not None:
        trace = [entry for entry in trace if int(entry.get("turn_number", -1)) == int(turn_number)]
    if not trace:
        label = f"turn {turn_number}" if turn_number is not None else "match"
        print(f"\nNo recorded actions for {label}.")
        return
    grouped: dict[int, list[dict[str, object]]] = {}
    for entry in trace:
        grouped.setdefault(int(entry.get("turn_number", -1)), []).append(entry)
    print("")
    for turn in sorted(grouped):
        print(_style(f"Turn {turn}", "1;37", use_color=use_color))
        for index, entry in enumerate(grouped[turn], start=1):
            actor = f"P{entry.get('player_id', '?')}"
            actor_kind = str(entry.get("actor_kind", "unknown"))
            phase = str(entry.get("phase", "unknown"))
            actor_text = _style(actor, "1;34" if actor == "P1" else "1;31", use_color=use_color)
            seq = int(entry.get("action_index", index))
            print(f"  #{seq:>3} {actor_text} {actor_kind:<5} phase={phase:<10} {_history_action_text(entry, repo=repo)}")
        turn_entries = grouped[turn]
        charge_count = sum(1 for entry in turn_entries if str(entry.get("action_type", "")) == "charge_from_hand")
        play_count = sum(1 for entry in turn_entries if str(entry.get("action_type", "")) == "play_card_from_hand")
        attack_count = sum(1 for entry in turn_entries if str(entry.get("action_type", "")) == "declare_attack")
        skill_count = sum(
            1 for entry in turn_entries if str(entry.get("action_type", "")) in {"activate_main_skill", "activate_battle_skill"}
        )
        print(f"     summary: charges={charge_count} plays={play_count} attacks={attack_count} skills={skill_count}")
        print("")


def _print_compact_state(session: HumanVsAiSession, *, repo: SQLiteCardRepository | None, use_color: bool) -> None:
    state = session.state
    p1 = state.players[1]
    p2 = state.players[2]
    print(
        "\n"
        + _style(
            f"Turn {state.turn_number} | {state.phase.value.capitalize()} | Active: P{state.active_player} | Winner: {state.winner_id}",
            "1;37",
            use_color=use_color,
        )
    )
    print(_style(f"P1 {_card_brief_label(repo, _leader_id_from_player(state, 1))}", "1;34", use_color=use_color))
    print(f"   life {len(p1.life):<2} | hand {len(p1.hand):<2} | energy {len(p1.energy):<2} | battle {len(p1.battle_area):<2} | unison {len(p1.unison_area):<2}")
    if p1.battle_area:
        print(f"   battle_row { _zone_row(repo, p1.battle_area) }")
    if p1.unison_area:
        print(f"   unison_row { _zone_row(repo, p1.unison_area) }")
    print(_style(f"P2 {_card_brief_label(repo, _leader_id_from_player(state, 2))}", "1;31", use_color=use_color))
    print(f"   life {len(p2.life):<2} | hand {len(p2.hand):<2} | energy {len(p2.energy):<2} | battle {len(p2.battle_area):<2} | unison {len(p2.unison_area):<2}")
    if p2.battle_area:
        print(f"   battle_row { _zone_row(repo, p2.battle_area) }")
    if p2.unison_area:
        print(f"   unison_row { _zone_row(repo, p2.unison_area) }")


def _print_human_actions(session: HumanVsAiSession, *, repo: SQLiteCardRepository | None, use_color: bool) -> list[object]:
    legal = session.legal_actions_for_human()
    ranked = session.ai_policy.rank_actions(session.state, legal)
    ranked_map = {id(item.action): item for item in ranked}
    best_action_id = id(ranked[0].action) if ranked else None
    print("\nLegal actions:")
    for i, action in enumerate(legal):
        text = _compact_action_text(action, state=session.state, repo=repo)
        hints = _action_hints(session, action, repo=repo)
        ranked_item = ranked_map.get(id(action))
        score_text = f"{ranked_item.score:>7.2f}" if ranked_item is not None else "   n/a "
        prefix = _style(">", "1;32", use_color=use_color) if id(action) == best_action_id else " "
        suffix = ""
        if hints:
            suffix = "  " + " ".join(_style_hint(h, use_color=use_color) for h in hints)
        line = f"{prefix} [{i:>2}] {text:<52} score={score_text}{suffix}"
        if id(action) == best_action_id:
            line = _style(line, "1;32", use_color=use_color)
        print(line)
    return legal


def _interactive_action_picker(
    session: HumanVsAiSession,
    *,
    repo: SQLiteCardRepository | None,
    card_name_resolver,
    legal: list[object],
    use_color: bool,
    revealed_hand_players: tuple[int, ...],
) -> str:
    if msvcrt is None or not sys.stdin.isatty():
        return input("Choose action index (or d/a/b/h/q): ").strip().lower()

    focus = "actions"
    action_selected = 0
    hand_selected = 0
    board_selected = 0
    while True:
        _clear_screen(use_color=use_color)
        board_entries, tui = _render_tui_layout(
            session,
            repo=repo,
            legal=legal,
            use_color=use_color,
            focus=focus,
            hand_selected=hand_selected,
            action_selected=action_selected,
            board_selected=board_selected,
        )
        print(tui)

        key = msvcrt.getwch()
        if key in {"\r", "\n"}:
            if focus == "actions":
                return str(action_selected)
            if focus == "hand":
                _show_hand_card_detail(session, repo=repo, hand_index=hand_selected)
                print("\nPress any key to continue...")
                msvcrt.getwch()
                continue
            if focus == "board":
                _show_board_entry_detail(session, repo=repo, board_entries=board_entries, entry_index=board_selected)
                print("\nPress any key to continue...")
                msvcrt.getwch()
                continue
        if key in {"q", "Q"}:
            return "q"
        if key in {"b", "B"}:
            print(
                "\n"
                + summarize_state_for_cli(
                    session.state,
                    card_name_resolver=card_name_resolver,
                    reveal_hand_player_ids=revealed_hand_players,
                    show_zone_details=True,
                )
            )
            print("\nPress any key to continue...")
            msvcrt.getwch()
            continue
        if key in {"l", "L"}:
            _show_action_history(session, repo=repo, use_color=use_color)
            print("Press any key to continue...")
            msvcrt.getwch()
            continue
        if key in {"t", "T"}:
            _show_action_history(session, repo=repo, use_color=use_color, turn_number=int(session.state.turn_number))
            print("Press any key to continue...")
            msvcrt.getwch()
            continue
        if key in {"h", "H"}:
            print("\nCommands:")
            print("  Arrow Up/Down  move selection")
            print("  Arrow Left/Right switch focus between Hand / Actions / Board")
            print("  Enter          choose selected action")
            print("  a              show full details for selected action")
            print("  d              show card detail for selected action's hand card")
            print("  l              show full match action history")
            print("  t              show current turn action history")
            print("  b              show full board and revealed hands")
            print("  q              quit and write outputs")
            print("\nPress any key to continue...")
            msvcrt.getwch()
            continue
        if key in {"a", "A"}:
            _show_action_detail(session, repo=repo, legal=legal, action_index=action_selected)
            print("\nPress any key to continue...")
            msvcrt.getwch()
            continue
        if key in {"d", "D"}:
            if focus == "hand":
                _show_hand_card_detail(session, repo=repo, hand_index=hand_selected)
            else:
                action = legal[action_selected]
                if getattr(action, "hand_index", None) is not None:
                    _show_hand_card_detail(session, repo=repo, hand_index=int(action.hand_index))
                else:
                    print("\nSelected action does not reference a hand card.")
            print("\nPress any key to continue...")
            msvcrt.getwch()
            continue
        if key == "\xe0":
            key2 = msvcrt.getwch()
            if key2 == "H":
                if focus == "actions":
                    action_selected = (action_selected - 1) % len(legal)
                elif focus == "hand":
                    hand_size = len(session.state.players[int(session.human_player_id)].hand)
                    if hand_size:
                        hand_selected = (hand_selected - 1) % hand_size
                elif focus == "board":
                    board_selected = (board_selected - 1) % len(board_entries)
                continue
            if key2 == "P":
                if focus == "actions":
                    action_selected = (action_selected + 1) % len(legal)
                elif focus == "hand":
                    hand_size = len(session.state.players[int(session.human_player_id)].hand)
                    if hand_size:
                        hand_selected = (hand_selected + 1) % hand_size
                elif focus == "board":
                    board_selected = (board_selected + 1) % len(board_entries)
                continue
            if key2 == "K":
                focus = {"actions": "hand", "board": "actions", "hand": "board"}[focus]
                continue
            if key2 == "M":
                focus = {"hand": "actions", "actions": "board", "board": "hand"}[focus]
                continue
        if key.isdigit():
            return key


def _revealed_hand_players(*, human_player: int, reveal_ai_hand: bool, reveal_all_hands: bool) -> tuple[int, ...]:
    if reveal_all_hands:
        return (1, 2)
    if reveal_ai_hand:
        ai_player = 1 if int(human_player) == 2 else 2
        return (int(human_player), ai_player)
    return (int(human_player),)


def _using_real_deck_source(args: argparse.Namespace) -> bool:
    if args.use_db_sample_decks:
        return True
    if args.p1_deckplanet_file is not None and args.p2_deckplanet_file is not None:
        return True
    return all(x is not None for x in [args.p1_leader_id, args.p2_leader_id, args.p1_deck_file, args.p2_deck_file])


def main() -> None:
    parser = argparse.ArgumentParser(description="Play DBS card game against heuristic AI in terminal.")
    parser.add_argument("--human-player", type=int, choices=[1, 2], default=1, help="Human player id (1 or 2).")
    parser.add_argument("--ai-profile", type=str, default="balanced", help="AI profile (balanced/aggressive/control).")
    parser.add_argument("--first-player", type=int, choices=[1, 2], default=1, help="Starting player id.")
    parser.add_argument("--shuffle-decks", action="store_true", help="Shuffle decks before opening draws.")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed used when shuffling decks.")
    parser.add_argument("--max-actions", type=int, default=300, help="Global action cap for the session.")
    parser.add_argument("--effect-catalog", type=Path, default=Path("dbdatabase/effect_catalog.json"), help="Path to effect catalog JSON.")
    parser.add_argument("--db-path", type=Path, default=Path("dbdatabase/dbs_masters.db"), help="Path to SQLite card database.")
    parser.add_argument("--p1-leader-id", type=int, default=None, help="Optional explicit P1 leader card id.")
    parser.add_argument("--p2-leader-id", type=int, default=None, help="Optional explicit P2 leader card id.")
    parser.add_argument("--p1-deck-file", type=Path, default=None, help="Optional P1 deck id file (comma/newline separated ids).")
    parser.add_argument("--p2-deck-file", type=Path, default=None, help="Optional P2 deck id file (comma/newline separated ids).")
    parser.add_argument("--p1-deckplanet-file", type=Path, default=None, help="Optional DeckPlanet text export for player 1.")
    parser.add_argument("--p2-deckplanet-file", type=Path, default=None, help="Optional DeckPlanet text export for player 2.")
    parser.add_argument(
        "--use-db-sample-decks",
        action="store_true",
        help="Use first two leaders and first available non-leader cards from DB to build two decks.",
    )
    parser.add_argument(
        "--scripted-actions-file",
        type=Path,
        default=None,
        help="Optional file with one human action index per line for non-interactive runs.",
    )
    parser.add_argument(
        "--trace-output",
        type=Path,
        default=Path("artifacts/human_vs_ai_trace.json"),
        help="JSON trace output path.",
    )
    parser.add_argument(
        "--load-state-input",
        type=Path,
        default=None,
        help="Optional path to load a previously saved game-state JSON and resume.",
    )
    parser.add_argument(
        "--save-state-output",
        type=Path,
        default=Path("artifacts/human_vs_ai_state.json"),
        help="Path to save game-state JSON on exit/finish.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("artifacts/human_vs_ai_summary.json"),
        help="Path to write compact match summary JSON.",
    )
    parser.add_argument("--result-output", type=Path, default=None, help="Optional path to write expectation result JSON.")
    parser.add_argument(
        "--ci-mode",
        action="store_true",
        help="Apply CI defaults for result outputs and strict expectation checks.",
    )
    parser.add_argument("--expect-winner", type=int, choices=[1, 2], default=None, help="Optional expected winner.")
    parser.add_argument("--expect-final-turn", type=int, default=None, help="Optional expected final turn number.")
    parser.add_argument(
        "--expect-completed",
        choices=["true", "false"],
        default=None,
        help="Optional expectation whether match should be completed (winner exists).",
    )
    parser.add_argument(
        "--max-unresolved-effects",
        type=int,
        default=None,
        help="Optional upper bound for unresolved effect resolutions.",
    )
    parser.add_argument(
        "--reveal-ai-hand",
        action="store_true",
        help="Debug mode: reveal the AI player's hand in terminal summaries.",
    )
    parser.add_argument(
        "--reveal-all-hands",
        action="store_true",
        help="Debug mode: reveal both players' hands in terminal summaries.",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Use a lightweight full-screen ANSI TUI refresh instead of scrolling output.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colorized output.",
    )
    args = parser.parse_args()

    if args.ci_mode:
        if args.result_output is None:
            args.result_output = Path("artifacts/human_vs_ai_result.json")
        if args.max_unresolved_effects is None:
            args.max_unresolved_effects = 100

    repo = SQLiteCardRepository(args.db_path) if args.db_path.exists() else None
    effect_catalog = args.effect_catalog if args.effect_catalog.exists() else None
    engine = RulesEngine(card_repository=repo, effect_rules_path=effect_catalog)

    if args.load_state_input is not None:
        if not args.load_state_input.exists():
            raise ValueError(f"--load-state-input path does not exist: {args.load_state_input}")
        state = load_game_state_json(args.load_state_input)
        setup_meta = {
            "mode": "resume",
            "load_state_input": str(args.load_state_input),
            "first_player": int(args.first_player),
            "shuffle_decks": bool(args.shuffle_decks),
            "seed": args.seed,
        }
    else:
        if args.use_db_sample_decks:
            if not args.db_path.exists():
                raise ValueError("--use-db-sample-decks requires --db-path to exist.")
            p1_leader, p1_deck, p2_leader, p2_deck = load_sample_game_setup_from_db(args.db_path, deck_size=60)
        elif args.p1_deckplanet_file is not None and args.p2_deckplanet_file is not None:
            if not args.db_path.exists():
                raise ValueError("DeckPlanet import requires --db-path to exist.")
            p1_payload = import_deckplanet_deck_text(
                db_path=args.db_path,
                raw=args.p1_deckplanet_file.read_text(encoding="utf-8"),
            )
            p2_payload = import_deckplanet_deck_text(
                db_path=args.db_path,
                raw=args.p2_deckplanet_file.read_text(encoding="utf-8"),
            )
            if p1_payload["unresolved_card_numbers"] or p2_payload["unresolved_card_numbers"]:
                raise ValueError(
                    "DeckPlanet import has unresolved card numbers: "
                    f"p1={p1_payload['unresolved_card_numbers'][:10]} "
                    f"p2={p2_payload['unresolved_card_numbers'][:10]}"
                )
            p1_leader = int(p1_payload["leader_id"])
            p2_leader = int(p2_payload["leader_id"])
            p1_deck = list(p1_payload["deck_ids"])
            p2_deck = list(p2_payload["deck_ids"])
        elif all(x is not None for x in [args.p1_leader_id, args.p2_leader_id, args.p1_deck_file, args.p2_deck_file]):
            p1_leader = int(args.p1_leader_id)
            p2_leader = int(args.p2_leader_id)
            p1_deck = read_card_ids_file(args.p1_deck_file)
            p2_deck = read_card_ids_file(args.p2_deck_file)
            if not args.db_path.exists():
                raise ValueError("Deck validation requires --db-path to exist.")
            validate_leader_and_deck(db_path=args.db_path, leader_id=p1_leader, deck_ids=p1_deck, expected_deck_size=60)
            validate_leader_and_deck(db_path=args.db_path, leader_id=p2_leader, deck_ids=p2_deck, expected_deck_size=60)
        else:
            p1_leader, p1_deck, p2_leader, p2_deck = 1, _build_deck(1000), 2, _build_deck(2000)
        if repo is not None and _using_real_deck_source(args):
            validate_deck_legality(repo=repo, leader_id=p1_leader, deck_ids=p1_deck, expected_deck_size=60)
            validate_deck_legality(repo=repo, leader_id=p2_leader, deck_ids=p2_deck, expected_deck_size=60)
        setup_meta = {
            "mode": "fresh",
            "first_player": int(args.first_player),
            "shuffle_decks": bool(args.shuffle_decks),
            "seed": args.seed,
            "p1_leader_id": int(p1_leader),
            "p2_leader_id": int(p2_leader),
            "p1_deck_size": len(p1_deck),
            "p2_deck_size": len(p2_deck),
            "deck_source": (
                "db_sample"
                if args.use_db_sample_decks
                else (
                    "deckplanet"
                    if args.p1_deckplanet_file is not None and args.p2_deckplanet_file is not None
                    else ("deck_files" if all(x is not None for x in [args.p1_leader_id, args.p2_leader_id, args.p1_deck_file, args.p2_deck_file]) else "synthetic")
                )
            ),
        }

        state = _init_state(
            engine,
            first_player=int(args.first_player),
            p1_leader=p1_leader,
            p1_deck=p1_deck,
            p2_leader=p2_leader,
            p2_deck=p2_deck,
            shuffle_decks=bool(args.shuffle_decks),
            random_seed=args.seed,
        )
    session = HumanVsAiSession(
        engine=engine,
        state=state,
        human_player_id=int(args.human_player),
        ai_policy=HeuristicPolicy(profile=args.ai_profile),
        setup_metadata=setup_meta,
    )
    card_name_resolver = _card_name_resolver(repo)
    revealed_hand_players = _revealed_hand_players(
        human_player=int(args.human_player),
        reveal_ai_hand=bool(args.reveal_ai_hand),
        reveal_all_hands=bool(args.reveal_all_hands),
    )
    use_color = _supports_color() and not bool(args.no_color)

    scripted_inputs: list[str] = []
    if args.scripted_actions_file is not None and args.scripted_actions_file.exists():
        scripted_inputs = [line.strip() for line in args.scripted_actions_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    scripted_ptr = 0

    print("Human-vs-AI match started.")
    print("Commands: <index>, d <hand_index>, a <action_index>, l (history), t (turn history), b (board), h (help), q (quit)")
    last_summary_payload: dict[str, object] = {}

    def _write_outputs_and_exit_banner() -> None:
        nonlocal last_summary_payload
        trace_payload = session.to_trace_payload()
        trace_hash = compute_trace_hash(trace_payload)
        args.trace_output.parent.mkdir(parents=True, exist_ok=True)
        args.trace_output.write_text(
            json.dumps({"trace": trace_payload, "trace_hash": trace_hash}, indent=2),
            encoding="utf-8",
        )
        print(f"wrote: {args.trace_output}")
        if args.save_state_output is not None:
            save_game_state_json(session.state, args.save_state_output)
            print(f"wrote: {args.save_state_output}")
        if args.summary_output is not None:
            turn_history = _build_turn_history_summary(session, repo=repo)
            summary_payload = build_compact_match_summary(
                state=session.state,
                total_actions=session.total_actions,
                human_player_id=int(args.human_player),
                ai_profile=str(args.ai_profile),
                setup_metadata=dict(session.setup_metadata or {}),
                turn_history=turn_history,
            )
            summary_payload["trace_hash"] = trace_hash
            last_summary_payload = dict(summary_payload)
            args.summary_output.parent.mkdir(parents=True, exist_ok=True)
            args.summary_output.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
            print(f"wrote: {args.summary_output}")

    def _evaluate_expectations_and_exit_if_needed() -> None:
        nonlocal last_summary_payload
        if not last_summary_payload:
            last_summary_payload = build_compact_match_summary(
                state=session.state,
                total_actions=session.total_actions,
                human_player_id=int(args.human_player),
                ai_profile=str(args.ai_profile),
                setup_metadata=dict(session.setup_metadata or {}),
            )
        expectation_failures = evaluate_match_expectations(
            summary=last_summary_payload,
            expect_winner=args.expect_winner,
            expect_final_turn=args.expect_final_turn,
            expect_completed=(
                None if args.expect_completed is None else (str(args.expect_completed).strip().lower() == "true")
            ),
            max_unresolved_effects=args.max_unresolved_effects,
        )
        if args.result_output is not None:
            result_payload = {
                "ok": len(expectation_failures) == 0,
                "failures": expectation_failures,
                "summary": last_summary_payload,
                "trace_hash": last_summary_payload.get("trace_hash"),
            }
            args.result_output.parent.mkdir(parents=True, exist_ok=True)
            args.result_output.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")
            print(f"wrote: {args.result_output}")
        if expectation_failures:
            for failure in expectation_failures:
                print(f"match_expectation_failed:{failure}")
            sys.exit(6)

    while not session.is_over() and session.total_actions < max(1, int(args.max_actions)):
        ai_actions = session.step_ai_until_human_turn_with_context()
        for entry in ai_actions:
            action = entry["action"]
            state_before = entry["state_before"]
            print(
                "AI played: "
                + describe_action(
                    action,
                    state=state_before,
                    card_name_resolver=card_name_resolver,
                )
            )
        if session.is_over():
            break
        if args.tui:
            _clear_screen(use_color=use_color)
        _print_compact_state(session, repo=repo, use_color=use_color)
        _print_compact_hand(session, repo=repo)
        legal = _print_human_actions(session, repo=repo, use_color=use_color)
        if not legal:
            print("No legal actions available for human. Ending session.")
            break
        while True:
            if scripted_ptr < len(scripted_inputs):
                raw = scripted_inputs[scripted_ptr].strip().lower()
                scripted_ptr += 1
                print(f"scripted_input: {raw}")
            else:
                raw = _interactive_action_picker(
                    session,
                    repo=repo,
                    card_name_resolver=card_name_resolver,
                    legal=legal,
                    use_color=use_color,
                    revealed_hand_players=revealed_hand_players,
                ).strip().lower()
            if raw == "q":
                print("Session ended by user.")
                _write_outputs_and_exit_banner()
                _evaluate_expectations_and_exit_if_needed()
                return
            if raw == "h":
                print("Commands:")
                print("  <index>       play legal action by index")
                print("  d <hand>      show full details for a card in your hand")
                print("  a <action>    show full details for a legal action")
                print("  l             show full match action history")
                print("  t             show current turn action history")
                print("  b             show full board and revealed hands")
                print("  h             show this help")
                print("  q             quit and write outputs")
                continue
            if raw == "l":
                _show_action_history(session, repo=repo, use_color=use_color)
                continue
            if raw == "t":
                _show_action_history(session, repo=repo, use_color=use_color, turn_number=int(session.state.turn_number))
                continue
            if raw in {"s", "b"}:
                print(
                    "\n"
                    + summarize_state_for_cli(
                        session.state,
                        card_name_resolver=card_name_resolver,
                        reveal_hand_player_ids=revealed_hand_players,
                        show_zone_details=True,
                    )
                )
                continue
            if raw.startswith("d "):
                try:
                    hand_index = int(raw.split(maxsplit=1)[1])
                except (IndexError, ValueError):
                    print("Usage: d <hand_index>")
                    continue
                _show_hand_card_detail(session, repo=repo, hand_index=hand_index)
                continue
            if raw.startswith("a "):
                try:
                    action_index = int(raw.split(maxsplit=1)[1])
                except (IndexError, ValueError):
                    print("Usage: a <action_index>")
                    continue
                _show_action_detail(session, repo=repo, legal=legal, action_index=action_index)
                continue
            try:
                idx = int(raw)
            except ValueError:
                print("Invalid input. Use <index>, d <hand_index>, a <action_index>, l, t, b, h, or q.")
                continue
            if idx < 0 or idx >= len(legal):
                print(f"Index out of range. Valid range: 0..{len(legal)-1}")
                continue
            chosen = legal[idx]
            chosen_text = describe_action(chosen, state=session.state, card_name_resolver=card_name_resolver)
            session.apply_human_action_by_index(idx)
            print(f"You played: {chosen_text}")
            break

    print("\nMatch finished.")
    print(
        summarize_state_for_cli(
            session.state,
            card_name_resolver=card_name_resolver,
            reveal_hand_player_ids=revealed_hand_players,
        )
    )
    print(f"winner={session.state.winner_id} total_actions={session.total_actions}")
    _write_outputs_and_exit_banner()
    _evaluate_expectations_and_exit_if_needed()


if __name__ == "__main__":
    main()
