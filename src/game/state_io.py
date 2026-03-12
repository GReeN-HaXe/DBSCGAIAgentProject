from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
import types
from typing import Any, Union, get_args, get_origin, get_type_hints
import json

from src.game.state import GameState


def _encode_value(value: Any) -> Any:
    if is_dataclass(value):
        out: dict[str, Any] = {}
        for f in fields(value):
            out[f.name] = _encode_value(getattr(value, f.name))
        return out
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_encode_value(v) for v in value]
    if isinstance(value, list):
        return [_encode_value(v) for v in value]
    if isinstance(value, dict):
        return {str(_encode_value(k)): _encode_value(v) for k, v in value.items()}
    return value


def _decode_value(type_hint: Any, value: Any) -> Any:
    if value is None:
        return None
    if type_hint is Any:
        return value
    origin = get_origin(type_hint)
    args = get_args(type_hint)

    if origin in (Union, types.UnionType):
        non_none = [t for t in args if t is not type(None)]
        for t in non_none:
            try:
                return _decode_value(t, value)
            except Exception:
                continue
        return value
    if origin is list:
        inner = args[0] if args else Any
        return [_decode_value(inner, v) for v in value]
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode_value(args[0], v) for v in value)
        if args:
            return tuple(_decode_value(args[min(i, len(args) - 1)], v) for i, v in enumerate(value))
        return tuple(value)
    if origin is dict:
        k_t = args[0] if len(args) >= 1 else Any
        v_t = args[1] if len(args) >= 2 else Any
        out: dict[Any, Any] = {}
        for k, v in value.items():
            out[_decode_value(k_t, k)] = _decode_value(v_t, v)
        return out

    if isinstance(type_hint, type):
        if issubclass(type_hint, Enum):
            return type_hint(value)
        if is_dataclass(type_hint):
            hints = get_type_hints(type_hint)
            kwargs: dict[str, Any] = {}
            for f in fields(type_hint):
                if f.name in value:
                    inner_t = hints.get(f.name, f.type)
                    kwargs[f.name] = _decode_value(inner_t, value[f.name])
            return type_hint(**kwargs)
        if type_hint is int:
            return int(value)
        if type_hint is float:
            return float(value)
        if type_hint is bool:
            return bool(value)
        if type_hint is str:
            return str(value)
    return value


def game_state_to_dict(state: GameState) -> dict[str, Any]:
    return _encode_value(state)


def game_state_from_dict(payload: dict[str, Any]) -> GameState:
    return _decode_value(GameState, payload)


def save_game_state_json(state: GameState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(game_state_to_dict(state), indent=2), encoding="utf-8")


def load_game_state_json(path: Path) -> GameState:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid game state JSON payload.")
    return game_state_from_dict(payload)
