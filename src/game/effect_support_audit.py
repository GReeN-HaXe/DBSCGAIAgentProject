from __future__ import annotations

from collections import Counter
from typing import Iterable

from src.db.interfaces import CardRepository
from src.game.effect_rule_extractor import (
    build_effect_rules_with_diagnostics_and_report,
    skill_template_signature,
)


EFFECT_SUPPORT_AUDIT_SCHEMA_VERSION = "effect_support_audit.v1"
_INTENTIONALLY_SKIPPED_CARD_NUMBERS = {
    "BT25-010",
    "BT15-018",
    "BT15-105",
}


def _is_intentionally_skipped_skillless(card_number: object, skill_text: object) -> bool:
    if str(card_number or "").strip().upper() in _INTENTIONALLY_SKIPPED_CARD_NUMBERS:
        return True
    return str(skill_text or "").strip() == "-"


def build_effect_support_audit(
    repo: CardRepository,
    card_ids: Iterable[int],
    *,
    priority_card_ids: Iterable[int] = (),
    top_families: int = 30,
) -> dict[str, object]:
    ids = [int(card_id) for card_id in dict.fromkeys(int(x) for x in card_ids)]
    priority_set = {int(card_id) for card_id in priority_card_ids}
    cards = repo.list_by_ids(ids, source_table="cards")
    rules_by_card, diagnostics, extractor_report = build_effect_rules_with_diagnostics_and_report(
        repo,
        ids,
        top_unmatched=max(int(top_families), 0) * 2 if int(top_families) > 0 else 20,
    )

    families: dict[str, dict[str, object]] = {}
    priority_skill_cards = 0
    priority_cards_with_rules = 0
    priority_cards_with_diagnostics = 0
    priority_cards_without_rules = 0
    priority_intentionally_skipped_cards = 0

    for card in cards:
        signature = skill_template_signature(card.card_skill_unstyled)
        if not signature:
            continue
        family = families.setdefault(
            signature,
            {
                "template": signature,
                "card_count": 0,
                "implemented_card_count": 0,
                "diagnostic_card_count": 0,
                "priority_card_count": 0,
                "priority_implemented_card_count": 0,
                "priority_diagnostic_card_count": 0,
                "example_card_id": int(card.id),
                "example_card_number": str(card.card_number),
                "example_card_name": str(card.card_name),
                "handler_counts": Counter(),
                "trigger_counts": Counter(),
                "diagnostic_counts": Counter(),
            },
        )
        family["card_count"] = int(family["card_count"]) + 1

        card_rules = rules_by_card.get(int(card.id), [])
        if card_rules:
            family["implemented_card_count"] = int(family["implemented_card_count"]) + 1
            for rule in card_rules:
                family["handler_counts"][rule.handler_id] += 1
                family["trigger_counts"][rule.trigger] += 1

        notes = diagnostics.get(int(card.id), [])
        if notes:
            family["diagnostic_card_count"] = int(family["diagnostic_card_count"]) + 1
            for note in notes:
                family["diagnostic_counts"][note] += 1

        if int(card.id) in priority_set:
            priority_skill_cards += 1
            family["priority_card_count"] = int(family["priority_card_count"]) + 1
            if card_rules:
                priority_cards_with_rules += 1
                family["priority_implemented_card_count"] = int(family["priority_implemented_card_count"]) + 1
            else:
                priority_cards_without_rules += 1
            if notes:
                priority_cards_with_diagnostics += 1
                family["priority_diagnostic_card_count"] = int(family["priority_diagnostic_card_count"]) + 1

    def _serialize_family(payload: dict[str, object]) -> dict[str, object]:
        card_count = int(payload["card_count"])
        implemented_card_count = int(payload["implemented_card_count"])
        priority_card_count = int(payload["priority_card_count"])
        priority_implemented_card_count = int(payload["priority_implemented_card_count"])
        return {
            "template": str(payload["template"]),
            "card_count": card_count,
            "implemented_card_count": implemented_card_count,
            "diagnostic_card_count": int(payload["diagnostic_card_count"]),
            "implemented_rate": (implemented_card_count / card_count) if card_count else 0.0,
            "priority_card_count": priority_card_count,
            "priority_implemented_card_count": priority_implemented_card_count,
            "priority_diagnostic_card_count": int(payload["priority_diagnostic_card_count"]),
            "priority_implemented_rate": (priority_implemented_card_count / priority_card_count) if priority_card_count else 0.0,
            "example_card_id": int(payload["example_card_id"]),
            "example_card_number": str(payload["example_card_number"]),
            "example_card_name": str(payload["example_card_name"]),
            "handler_counts": dict(sorted(payload["handler_counts"].items())),
            "trigger_counts": dict(sorted(payload["trigger_counts"].items())),
            "diagnostic_counts": dict(sorted(payload["diagnostic_counts"].items())),
        }

    serialized_families = [_serialize_family(family) for family in families.values()]
    serialized_families.sort(key=lambda row: (-int(row["card_count"]), str(row["template"])))
    top_priority_families = [
        family
        for family in sorted(
            serialized_families,
            key=lambda row: (-int(row["priority_card_count"]), -int(row["card_count"]), str(row["template"])),
        )
        if int(family["priority_card_count"]) > 0
    ][: max(int(top_families), 0)]

    priority_unimplemented_cards: list[dict[str, object]] = []
    intentionally_skipped_priority_cards: list[dict[str, object]] = []
    priority_diagnostic_cards: list[dict[str, object]] = []
    if priority_set:
        for card in cards:
            if int(card.id) not in priority_set:
                continue
            signature = skill_template_signature(card.card_skill_unstyled)
            notes = diagnostics.get(int(card.id), [])
            intentionally_skipped = _is_intentionally_skipped_skillless(card.card_number, card.card_skill_unstyled)
            if int(card.id) not in rules_by_card and intentionally_skipped:
                priority_intentionally_skipped_cards += 1
                priority_cards_without_rules -= 1
                intentionally_skipped_priority_cards.append(
                    {
                        "card_id": int(card.id),
                        "card_number": str(card.card_number),
                        "card_name": str(card.card_name),
                        "template": signature,
                        "skip_reason": "skillless",
                    }
                )
            elif int(card.id) not in rules_by_card:
                priority_unimplemented_cards.append(
                    {
                        "card_id": int(card.id),
                        "card_number": str(card.card_number),
                        "card_name": str(card.card_name),
                        "template": signature,
                    }
                )
            if notes:
                priority_diagnostic_cards.append(
                    {
                        "card_id": int(card.id),
                        "card_number": str(card.card_number),
                        "card_name": str(card.card_name),
                        "template": signature,
                        "diagnostics": list(notes),
                    }
                )

    return {
        "schema_version": EFFECT_SUPPORT_AUDIT_SCHEMA_VERSION,
        "summary": {
            "skill_card_count": sum(int(row["card_count"]) for row in serialized_families),
            "cards_with_rules": int(extractor_report["cards_with_rules"]),
            "cards_without_rules": int(extractor_report["cards_without_rules"]),
            "cards_with_diagnostics": int(extractor_report["cards_with_diagnostics"]),
            "family_count": len(serialized_families),
            "priority_card_count": len(priority_set),
            "priority_skill_card_count": priority_skill_cards,
            "priority_cards_with_rules": priority_cards_with_rules,
            "priority_cards_without_rules": priority_cards_without_rules,
            "priority_intentionally_skipped_cards": priority_intentionally_skipped_cards,
            "priority_cards_with_diagnostics": priority_cards_with_diagnostics,
        },
        "coverage": {
            "db": {
                "cards_with_rules": int(extractor_report["cards_with_rules"]),
                "cards_without_rules": int(extractor_report["cards_without_rules"]),
                "cards_with_diagnostics": int(extractor_report["cards_with_diagnostics"]),
            },
            "priority": {
                "cards_with_rules": priority_cards_with_rules,
                "cards_without_rules": priority_cards_without_rules,
                "intentionally_skipped_cards": priority_intentionally_skipped_cards,
                "cards_with_diagnostics": priority_cards_with_diagnostics,
            },
        },
        "top_global_families": serialized_families[: max(int(top_families), 0)],
        "top_priority_families": top_priority_families,
        "priority_unimplemented_cards": priority_unimplemented_cards,
        "intentionally_skipped_priority_cards": intentionally_skipped_priority_cards,
        "priority_diagnostic_cards": priority_diagnostic_cards,
        "extractor_report": extractor_report,
    }
