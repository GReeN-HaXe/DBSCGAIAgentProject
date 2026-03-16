from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

EFFECT_CATALOG_KIND = "dbs_effect_catalog"
EFFECT_CATALOG_SCHEMA_VERSION = 1
EFFECT_CATALOG_OVERRIDE_KIND = "dbs_effect_catalog_overrides"
EFFECT_CATALOG_OVERRIDE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EffectRule:
    trigger: str
    handler_id: str
    handler_params: dict[str, int | str | bool] = field(default_factory=dict)
    once_per_turn: bool = False
    limit_per_turn: int | None = None
    limit_scope: str = "card_number"
    family_id: str = ""
    provenance: str = ""


def normalize_effect_rules(raw_rules: dict[int, list[dict[str, object]] | list[EffectRule]] | None) -> dict[int, tuple[EffectRule, ...]]:
    if not raw_rules:
        return {}
    normalized: dict[int, tuple[EffectRule, ...]] = {}
    for card_id, rules in raw_rules.items():
        items: list[EffectRule] = []
        for rule in rules:
            if isinstance(rule, EffectRule):
                items.append(rule)
                continue
            if not isinstance(rule, dict):
                raise ValueError("Each effect rule must be a dict or EffectRule.")
            trigger = str(rule.get("trigger", "")).strip()
            handler_id = str(rule.get("handler_id", "")).strip()
            raw_params = rule.get("handler_params", {})
            if raw_params is None:
                raw_params = {}
            if not isinstance(raw_params, dict):
                raise ValueError("handler_params must be a dict when provided.")
            handler_params: dict[str, int | str | bool] = {}
            for key, value in raw_params.items():
                if not isinstance(key, str):
                    raise ValueError("handler_params keys must be strings.")
                if not isinstance(value, (int, str, bool)):
                    raise ValueError("handler_params values must be int/str/bool.")
                handler_params[key] = value
            once_per_turn = bool(rule.get("once_per_turn", False))
            raw_limit = rule.get("limit_per_turn")
            limit_per_turn = int(raw_limit) if isinstance(raw_limit, int) else None
            limit_scope = str(rule.get("limit_scope", "card_number") or "card_number").strip() or "card_number"
            family_id = str(rule.get("family_id", "") or "").strip()
            provenance = str(rule.get("provenance", "") or "").strip()
            if not trigger or not handler_id:
                raise ValueError("Effect rule requires trigger and handler_id.")
            items.append(
                EffectRule(
                    trigger=trigger,
                    handler_id=handler_id,
                    handler_params=handler_params,
                    once_per_turn=once_per_turn,
                    limit_per_turn=limit_per_turn,
                    limit_scope=limit_scope,
                    family_id=family_id,
                    provenance=provenance,
                )
            )
        normalized[int(card_id)] = tuple(items)
    return normalized


def serialize_effect_rules(rules: dict[int, list[EffectRule] | tuple[EffectRule, ...]]) -> dict[str, list[dict[str, object]]]:
    payload: dict[str, list[dict[str, object]]] = {}
    for card_id, entries in rules.items():
        payload[str(int(card_id))] = [
            {
                "trigger": rule.trigger,
                "handler_id": rule.handler_id,
                "handler_params": dict(rule.handler_params),
                "once_per_turn": bool(rule.once_per_turn),
                "limit_per_turn": int(rule.limit_per_turn) if rule.limit_per_turn is not None else None,
                "limit_scope": str(rule.limit_scope or "card_number"),
                "family_id": str(rule.family_id or ""),
                "provenance": str(rule.provenance or ""),
            }
            for rule in entries
        ]
    return payload


def serialize_effect_catalog(rules: dict[int, list[EffectRule] | tuple[EffectRule, ...]]) -> dict[str, object]:
    serialized_rules = serialize_effect_rules(rules)
    return {
        "catalog_kind": EFFECT_CATALOG_KIND,
        "schema_version": EFFECT_CATALOG_SCHEMA_VERSION,
        "card_rule_count": len(serialized_rules),
        "effect_rule_count": sum(len(entries) for entries in serialized_rules.values()),
        "rules": serialized_rules,
    }


def _unwrap_effect_catalog_payload(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise ValueError("Effect catalog JSON must be an object.")
    if "rules" not in data:
        return data
    catalog_kind = str(data.get("catalog_kind", "")).strip()
    if catalog_kind and catalog_kind != EFFECT_CATALOG_KIND:
        raise ValueError(f"Unsupported effect catalog kind: {catalog_kind}")
    schema_version = data.get("schema_version", EFFECT_CATALOG_SCHEMA_VERSION)
    if not isinstance(schema_version, int) or schema_version != EFFECT_CATALOG_SCHEMA_VERSION:
        raise ValueError(f"Unsupported effect catalog schema version: {schema_version!r}")
    rules = data.get("rules")
    if not isinstance(rules, dict):
        raise ValueError("Effect catalog 'rules' payload must be an object keyed by card id.")
    card_rule_count = data.get("card_rule_count")
    if card_rule_count is not None and int(card_rule_count) != len(rules):
        raise ValueError("Effect catalog card_rule_count does not match rules payload.")
    effect_rule_count = data.get("effect_rule_count")
    if effect_rule_count is not None and int(effect_rule_count) != sum(len(entries) for entries in rules.values()):
        raise ValueError("Effect catalog effect_rule_count does not match rules payload.")
    return rules


def save_effect_rules_json(path: str | Path, rules: dict[int, list[EffectRule] | tuple[EffectRule, ...]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = serialize_effect_catalog(rules)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_effect_rules_json(path: str | Path) -> dict[int, tuple[EffectRule, ...]]:
    source = Path(path)
    data = _unwrap_effect_catalog_payload(json.loads(source.read_text(encoding="utf-8")))
    mapped: dict[int, list[dict[str, object]] | list[EffectRule]] = {}
    for key, value in data.items():
        mapped[int(key)] = value  # normalized/validated below
    return normalize_effect_rules(mapped)


def normalize_effect_rule_overrides(
    raw_overrides: dict[int, object] | None,
) -> dict[int, tuple[str, tuple[EffectRule, ...]]]:
    if not raw_overrides:
        return {}
    normalized: dict[int, tuple[str, tuple[EffectRule, ...]]] = {}
    for card_id, spec in raw_overrides.items():
        mode = "append"
        raw_rules: object = spec
        if isinstance(spec, dict) and "rules" in spec:
            mode = str(spec.get("mode", "append") or "append").strip().lower() or "append"
            raw_rules = spec.get("rules", [])
        if mode not in {"append", "replace"}:
            raise ValueError(f"Unsupported effect rule override mode: {mode}")
        if not isinstance(raw_rules, list):
            raise ValueError("Effect rule override payload must provide a list of rules.")
        rules = normalize_effect_rules({int(card_id): raw_rules}).get(int(card_id), ())
        normalized[int(card_id)] = (mode, rules)
    return normalized


def serialize_effect_rule_overrides(
    overrides: dict[int, tuple[str, tuple[EffectRule, ...]]] | dict[int, tuple[str, list[EffectRule]]],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "catalog_kind": EFFECT_CATALOG_OVERRIDE_KIND,
        "schema_version": EFFECT_CATALOG_OVERRIDE_SCHEMA_VERSION,
        "override_count": len(overrides),
        "overrides": {},
    }
    out: dict[str, object] = {}
    for card_id, (mode, rules) in overrides.items():
        out[str(int(card_id))] = {
            "mode": str(mode or "append"),
            "rules": serialize_effect_rules({int(card_id): rules})[str(int(card_id))],
        }
    payload["overrides"] = out
    return payload


def save_effect_rule_overrides_json(
    path: str | Path,
    overrides: dict[int, tuple[str, tuple[EffectRule, ...]]] | dict[int, tuple[str, list[EffectRule]]],
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = serialize_effect_rule_overrides(overrides)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_effect_rule_overrides_json(path: str | Path) -> dict[int, tuple[str, tuple[EffectRule, ...]]]:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Effect catalog overrides JSON must be an object.")
    if "overrides" in data:
        catalog_kind = str(data.get("catalog_kind", "")).strip()
        if catalog_kind and catalog_kind != EFFECT_CATALOG_OVERRIDE_KIND:
            raise ValueError(f"Unsupported effect catalog override kind: {catalog_kind}")
        schema_version = data.get("schema_version", EFFECT_CATALOG_OVERRIDE_SCHEMA_VERSION)
        if not isinstance(schema_version, int) or schema_version != EFFECT_CATALOG_OVERRIDE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported effect catalog override schema version: {schema_version!r}")
        overrides = data.get("overrides")
        if not isinstance(overrides, dict):
            raise ValueError("Effect catalog overrides 'overrides' payload must be an object keyed by card id.")
        return normalize_effect_rule_overrides({int(k): v for k, v in overrides.items()})
    return normalize_effect_rule_overrides({int(k): v for k, v in data.items()})


def merge_effect_rule_overrides(
    base_rules: dict[int, tuple[EffectRule, ...]],
    overrides: dict[int, tuple[str, tuple[EffectRule, ...]]],
) -> dict[int, tuple[EffectRule, ...]]:
    if not overrides:
        return dict(base_rules)
    merged: dict[int, tuple[EffectRule, ...]] = dict(base_rules)
    for card_id, (mode, override_rules) in overrides.items():
        if mode == "replace":
            if override_rules:
                merged[card_id] = tuple(override_rules)
            else:
                merged.pop(card_id, None)
            continue
        items = list(merged.get(card_id, ())) + list(override_rules)
        seen: set[tuple[str, str, tuple[tuple[str, int | str | bool], ...], bool, int | None, str, str, str]] = set()
        uniq: list[EffectRule] = []
        for rule in items:
            sig = (
                rule.trigger,
                rule.handler_id,
                tuple(sorted(rule.handler_params.items())),
                rule.once_per_turn,
                rule.limit_per_turn,
                rule.limit_scope,
                rule.family_id,
                rule.provenance,
            )
            if sig in seen:
                continue
            seen.add(sig)
            uniq.append(rule)
        merged[card_id] = tuple(uniq)
    return merged
