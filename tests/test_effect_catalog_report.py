from __future__ import annotations

from src.game.effect_catalog_report import build_effect_family_report
from src.game.effect_rules import EffectRule


def test_build_effect_family_report_groups_by_family_id_and_provenance() -> None:
    rules = {
        101: (
            EffectRule(
                trigger="self_played",
                handler_id="auto_draw_n",
                handler_params={"amount": 1},
                family_id="self_played:auto_draw_n",
                provenance="extractor",
            ),
        ),
        202: (
            EffectRule(
                trigger="self_played",
                handler_id="auto_draw_n",
                handler_params={"amount": 2},
                family_id="self_played:auto_draw_n",
                provenance="manual_override",
            ),
            EffectRule(
                trigger="self_attacks",
                handler_id="auto_draw_n",
                handler_params={"amount": 1},
                family_id="self_attacks:auto_draw_n",
                provenance="extractor",
            ),
        ),
    }

    report = build_effect_family_report(rules)
    assert report["summary"]["family_count"] == 2
    assert report["summary"]["card_rule_count"] == 2
    assert report["summary"]["effect_rule_count"] == 3
    assert report["summary"]["provenance_counts"] == {
        "extractor": 2,
        "manual_override": 1,
    }

    families = {row["family_id"]: row for row in report["families"]}
    assert families["self_played:auto_draw_n"]["card_count"] == 2
    assert families["self_played:auto_draw_n"]["rule_count"] == 2
    assert families["self_played:auto_draw_n"]["provenances"] == {
        "extractor": 1,
        "manual_override": 1,
    }
    assert families["self_attacks:auto_draw_n"]["card_ids"] == [202]
