from __future__ import annotations

from typing import Any


EFFECT_FAMILY_SHORTLIST_SCHEMA_VERSION = "effect_family_shortlist.v1"


def build_effect_family_shortlist(audit: dict[str, Any], *, top_n: int = 20) -> dict[str, Any]:
    priority_rows = audit.get("top_priority_families", [])
    extractor_report = audit.get("extractor_report", {})
    unmatched_rows = extractor_report.get("unmatched_top_templates", [])
    candidates: dict[str, dict[str, Any]] = {}

    def _candidate(template: str) -> dict[str, Any]:
        return candidates.setdefault(
            template,
            {
                "template": template,
                "sources": [],
                "score": 0,
                "card_count": 0,
                "priority_card_count": 0,
                "implemented_card_count": 0,
                "priority_implemented_card_count": 0,
                "example_card_id": None,
                "example_card_number": "",
                "example_card_name": "",
                "recommended_action": "implement_new_family",
                "handler_counts": {},
                "trigger_counts": {},
                "diagnostic_counts": {},
            },
        )

    for row in priority_rows:
        if not isinstance(row, dict):
            continue
        template = str(row.get("template", ""))
        if not template:
            continue
        priority_card_count = int(row.get("priority_card_count", 0))
        priority_implemented = int(row.get("priority_implemented_card_count", 0))
        card_count = int(row.get("card_count", 0))
        implemented = int(row.get("implemented_card_count", 0))
        missing_priority = max(priority_card_count - priority_implemented, 0)
        missing_global = max(card_count - implemented, 0)
        if missing_priority <= 0 and missing_global <= 0:
            continue
        candidate = _candidate(template)
        candidate["sources"] = sorted(set([*candidate["sources"], "priority_family"]))
        candidate["score"] = max(int(candidate["score"]), missing_priority * 1000 + missing_global * 10 + card_count)
        candidate["card_count"] = max(int(candidate["card_count"]), card_count)
        candidate["priority_card_count"] = max(int(candidate["priority_card_count"]), priority_card_count)
        candidate["implemented_card_count"] = max(int(candidate["implemented_card_count"]), implemented)
        candidate["priority_implemented_card_count"] = max(int(candidate["priority_implemented_card_count"]), priority_implemented)
        candidate["example_card_id"] = row.get("example_card_id")
        candidate["example_card_number"] = str(row.get("example_card_number", ""))
        candidate["example_card_name"] = str(row.get("example_card_name", ""))
        candidate["handler_counts"] = dict(row.get("handler_counts", {}))
        candidate["trigger_counts"] = dict(row.get("trigger_counts", {}))
        candidate["diagnostic_counts"] = dict(row.get("diagnostic_counts", {}))
        if implemented > 0:
            candidate["recommended_action"] = "extend_existing_family"

    for row in unmatched_rows:
        if not isinstance(row, dict):
            continue
        template = str(row.get("template", ""))
        if not template:
            continue
        count = int(row.get("count", 0))
        if count <= 0:
            continue
        candidate = _candidate(template)
        candidate["sources"] = sorted(set([*candidate["sources"], "global_unmatched"]))
        candidate["score"] = max(int(candidate["score"]), count * 100)
        candidate["card_count"] = max(int(candidate["card_count"]), count)
        if candidate.get("example_card_id") is None:
            candidate["example_card_id"] = row.get("example_card_id")
        candidate["recommended_action"] = candidate.get("recommended_action") or "implement_new_family"

    ranked = sorted(
        candidates.values(),
        key=lambda row: (-int(row["score"]), -int(row["priority_card_count"]), -int(row["card_count"]), str(row["template"])),
    )[: max(int(top_n), 0)]

    shortlist = []
    for index, row in enumerate(ranked, start=1):
        shortlist.append(
            {
                "rank": index,
                "template": row["template"],
                "sources": row["sources"],
                "score": int(row["score"]),
                "recommended_action": str(row["recommended_action"]),
                "card_count": int(row["card_count"]),
                "priority_card_count": int(row["priority_card_count"]),
                "implemented_card_count": int(row["implemented_card_count"]),
                "priority_implemented_card_count": int(row["priority_implemented_card_count"]),
                "example_card_id": row["example_card_id"],
                "example_card_number": str(row["example_card_number"]),
                "example_card_name": str(row["example_card_name"]),
                "handler_counts": dict(row["handler_counts"]),
                "trigger_counts": dict(row["trigger_counts"]),
                "diagnostic_counts": dict(row["diagnostic_counts"]),
            }
        )

    return {
        "schema_version": EFFECT_FAMILY_SHORTLIST_SCHEMA_VERSION,
        "summary": {
            "candidate_family_count": len(candidates),
            "shortlist_count": len(shortlist),
            "requested_top_n": max(int(top_n), 0),
        },
        "shortlist": shortlist,
    }
