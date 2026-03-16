from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sqlite3
from typing import Iterable

from src.agent.deck_setup import import_deckplanet_deck_text
from src.game.effect_rules import EffectRule


EFFECT_FAMILY_MAPPING_REPORT_SCHEMA_VERSION = "effect_family_mapping_report.v1"
_CARD_ID_RE = re.compile(r"\bcard_id=(\d+)\b")


def _fetch_card_metadata(db_path: Path, card_ids: Iterable[int]) -> dict[int, dict[str, object]]:
    resolved_ids = sorted({int(card_id) for card_id in card_ids if int(card_id) > 0})
    if not resolved_ids:
        return {}
    metadata: dict[int, dict[str, object]] = {}
    conn = sqlite3.connect(str(db_path))
    try:
        for offset in range(0, len(resolved_ids), 900):
            batch = resolved_ids[offset : offset + 900]
            placeholders = ", ".join("?" for _ in batch)
            rows = conn.execute(
                f"SELECT id, card_number, card_name FROM cards WHERE id IN ({placeholders})",
                [int(card_id) for card_id in batch],
            ).fetchall()
            for row in rows:
                metadata[int(row[0])] = {
                    "card_id": int(row[0]),
                    "card_number": str(row[1] or ""),
                    "card_name": str(row[2] or ""),
                }
    finally:
        conn.close()
    return metadata


def collect_deck_card_counts(*, db_path: Path, deck_paths: Iterable[Path]) -> tuple[Counter[int], list[str]]:
    counts: Counter[int] = Counter()
    included_paths: list[str] = []
    for path in sorted({Path(p) for p in deck_paths if Path(p).exists()}):
        payload = import_deckplanet_deck_text(db_path=db_path, raw=path.read_text(encoding="utf-8"))
        counts[int(payload["leader_id"])] += 1
        counts.update(int(card_id) for card_id in payload["deck_ids"])
        counts.update(int(card_id) for card_id in payload["z_deck_ids"])
        included_paths.append(str(path).replace("/", "\\"))
    return counts, included_paths


def _collect_card_ids_from_trace_action(action: dict[str, object]) -> Counter[int]:
    counts: Counter[int] = Counter()
    for key in ("hand_card_id", "source_card_id", "attacker_card_id", "target_card_id", "card_id"):
        value = action.get(key)
        if isinstance(value, int) and value > 0:
            counts[int(value)] += 1
    for key in ("action", "chosen_action_text"):
        text = action.get(key)
        if not isinstance(text, str):
            continue
        for match in _CARD_ID_RE.finditer(text):
            counts[int(match.group(1))] += 1
    return counts


def collect_trace_card_counts(trace_paths: Iterable[Path]) -> tuple[Counter[int], list[str]]:
    counts: Counter[int] = Counter()
    included_paths: list[str] = []
    for path in sorted({Path(p) for p in trace_paths if Path(p).exists()}):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        root = payload.get("trace") if isinstance(payload, dict) and isinstance(payload.get("trace"), dict) else payload
        if not isinstance(root, dict):
            continue
        local_counts: Counter[int] = Counter()
        setup = root.get("setup")
        if isinstance(setup, dict):
            for key in ("p1_leader_id", "p2_leader_id"):
                value = setup.get(key)
                if isinstance(value, int) and value > 0:
                    local_counts[int(value)] += 1
        actions = root.get("actions")
        if isinstance(actions, list):
            for action in actions:
                if isinstance(action, dict):
                    local_counts.update(_collect_card_ids_from_trace_action(action))
        decision_trace = root.get("decision_trace")
        if isinstance(decision_trace, list):
            for action in decision_trace:
                if isinstance(action, dict):
                    local_counts.update(_collect_card_ids_from_trace_action(action))
        if not local_counts:
            continue
        counts.update(local_counts)
        included_paths.append(str(path).replace("/", "\\"))
    return counts, included_paths


def build_effect_family_mapping_report(
    rules: dict[int, tuple[EffectRule, ...]] | dict[int, list[EffectRule]],
    *,
    card_metadata: dict[int, dict[str, object]],
    deck_card_counts: Counter[int] | dict[int, int],
    trace_card_counts: Counter[int] | dict[int, int],
) -> dict[str, object]:
    deck_counts = Counter({int(card_id): int(count) for card_id, count in dict(deck_card_counts).items() if int(count) > 0})
    trace_counts = Counter({int(card_id): int(count) for card_id, count in dict(trace_card_counts).items() if int(count) > 0})
    priority_card_ids = sorted(set(deck_counts) | set(trace_counts))

    family_rows: dict[str, dict[str, object]] = {}
    card_rows: list[dict[str, object]] = []
    mapped_card_count = 0

    for card_id in priority_card_ids:
        entries = list(rules.get(int(card_id), ()))
        metadata = card_metadata.get(int(card_id), {})
        families = sorted({rule.family_id or f"{rule.trigger}:{rule.handler_id}" for rule in entries})
        triggers = Counter(rule.trigger for rule in entries)
        handlers = Counter(rule.handler_id for rule in entries)
        provenances = Counter((rule.provenance or "") for rule in entries)
        deck_count = int(deck_counts.get(int(card_id), 0))
        trace_count = int(trace_counts.get(int(card_id), 0))
        combined_count = deck_count + trace_count
        mapped = bool(families)
        if mapped:
            mapped_card_count += 1
        row = {
            "card_id": int(card_id),
            "card_number": str(metadata.get("card_number", "")),
            "card_name": str(metadata.get("card_name", "")),
            "deck_count": deck_count,
            "trace_count": trace_count,
            "combined_count": combined_count,
            "mapped": mapped,
            "family_ids": families,
            "rule_count": len(entries),
            "triggers": dict(sorted(triggers.items())),
            "handlers": dict(sorted(handlers.items())),
            "provenances": dict(sorted(provenances.items())),
        }
        card_rows.append(row)

        for family_id in families:
            family = family_rows.setdefault(
                family_id,
                {
                    "family_id": family_id,
                    "priority_card_ids": [],
                    "priority_card_count": 0,
                    "deck_count": 0,
                    "trace_count": 0,
                    "combined_count": 0,
                    "triggers": Counter(),
                    "handlers": Counter(),
                    "provenances": Counter(),
                },
            )
            family["priority_card_ids"].append(int(card_id))
            family["priority_card_count"] = int(family["priority_card_count"]) + 1
            family["deck_count"] = int(family["deck_count"]) + deck_count
            family["trace_count"] = int(family["trace_count"]) + trace_count
            family["combined_count"] = int(family["combined_count"]) + combined_count
            for rule in entries:
                resolved_family = rule.family_id or f"{rule.trigger}:{rule.handler_id}"
                if resolved_family != family_id:
                    continue
                family["triggers"][rule.trigger] += 1
                family["handlers"][rule.handler_id] += 1
                family["provenances"][rule.provenance or ""] += 1

    card_rows.sort(
        key=lambda row: (
            -int(row["combined_count"]),
            -int(row["trace_count"]),
            -int(row["deck_count"]),
            str(row["card_name"]),
            int(row["card_id"]),
        )
    )

    serialized_families: list[dict[str, object]] = []
    for family in family_rows.values():
        serialized_families.append(
            {
                "family_id": str(family["family_id"]),
                "priority_card_count": int(family["priority_card_count"]),
                "deck_count": int(family["deck_count"]),
                "trace_count": int(family["trace_count"]),
                "combined_count": int(family["combined_count"]),
                "priority_card_ids": sorted(int(card_id) for card_id in family["priority_card_ids"]),
                "triggers": dict(sorted(family["triggers"].items())),
                "handlers": dict(sorted(family["handlers"].items())),
                "provenances": dict(sorted(family["provenances"].items())),
            }
        )
    serialized_families.sort(
        key=lambda row: (
            -int(row["combined_count"]),
            -int(row["trace_count"]),
            -int(row["deck_count"]),
            str(row["family_id"]),
        )
    )

    unmapped_cards = [row for row in card_rows if not bool(row["mapped"])]
    return {
        "schema_version": EFFECT_FAMILY_MAPPING_REPORT_SCHEMA_VERSION,
        "summary": {
            "priority_card_count": len(priority_card_ids),
            "mapped_priority_card_count": mapped_card_count,
            "unmapped_priority_card_count": len(unmapped_cards),
            "priority_family_count": len(serialized_families),
            "total_deck_mentions": sum(deck_counts.values()),
            "total_trace_mentions": sum(trace_counts.values()),
        },
        "priority_cards": card_rows,
        "top_priority_families": serialized_families,
        "unmapped_priority_cards": unmapped_cards,
    }


def build_effect_family_mapping_report_from_paths(
    *,
    db_path: Path,
    rules: dict[int, tuple[EffectRule, ...]] | dict[int, list[EffectRule]],
    deck_paths: Iterable[Path],
    trace_paths: Iterable[Path],
) -> dict[str, object]:
    deck_counts, included_decks = collect_deck_card_counts(db_path=db_path, deck_paths=deck_paths)
    trace_counts, included_traces = collect_trace_card_counts(trace_paths)
    card_metadata = _fetch_card_metadata(db_path, set(deck_counts) | set(trace_counts) | set(rules.keys()))
    payload = build_effect_family_mapping_report(
        rules,
        card_metadata=card_metadata,
        deck_card_counts=deck_counts,
        trace_card_counts=trace_counts,
    )
    payload["sources"] = {
        "deck_files": included_decks,
        "trace_files": included_traces,
    }
    return payload
