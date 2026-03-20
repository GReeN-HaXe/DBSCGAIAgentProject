from __future__ import annotations

from collections import Counter

from src.game.effect_rules import EffectRule


def build_effect_family_report(rules: dict[int, tuple[EffectRule, ...]] | dict[int, list[EffectRule]]) -> dict[str, object]:
    family_rows: list[dict[str, object]] = []
    for family_id in sorted({rule.family_id or f"{rule.trigger}:{rule.handler_id}" for entries in rules.values() for rule in entries}):
        card_ids: list[int] = []
        triggers: Counter[str] = Counter()
        handlers: Counter[str] = Counter()
        provenances: Counter[str] = Counter()
        rule_count = 0
        for card_id, entries in rules.items():
            matched = False
            for rule in entries:
                resolved_family = rule.family_id or f"{rule.trigger}:{rule.handler_id}"
                if resolved_family != family_id:
                    continue
                matched = True
                rule_count += 1
                triggers[rule.trigger] += 1
                handlers[rule.handler_id] += 1
                provenances[rule.provenance or ""] += 1
            if matched:
                card_ids.append(int(card_id))
        family_rows.append(
            {
                "family_id": family_id,
                "card_count": len(card_ids),
                "rule_count": rule_count,
                "card_ids": card_ids,
                "triggers": dict(sorted(triggers.items())),
                "handlers": dict(sorted(handlers.items())),
                "provenances": dict(sorted(provenances.items())),
            }
        )

    provenance_counts: Counter[str] = Counter()
    for entries in rules.values():
        for rule in entries:
            provenance_counts[rule.provenance or ""] += 1

    return {
        "schema_version": "effect_family_report.v1",
        "summary": {
            "family_count": len(family_rows),
            "card_rule_count": len(rules),
            "effect_rule_count": sum(len(entries) for entries in rules.values()),
            "provenance_counts": dict(sorted(provenance_counts.items())),
        },
        "families": family_rows,
    }
