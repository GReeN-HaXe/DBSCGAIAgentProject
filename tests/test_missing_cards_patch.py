from __future__ import annotations

from dbdatabase.build_missing_cards_patch import build_missing_cards_patch


def test_build_missing_cards_patch_emits_cards_and_variants() -> None:
    payload = {
        "requested_count": 2,
        "found_count": 1,
        "missing_count": 1,
        "missing_card_numbers": ["BT20-029"],
        "cards": [
            {
                "id": 100,
                "card_number": "BT10-088",
                "card_name": "Card A",
                "card_series": "BT10",
                "card_rarity": "Rare[R]",
                "card_type": "BATTLE",
                "card_color": "Blue",
                "card_energy_cost": "2",
                "card_combo_cost": "0",
                "card_combo_power": "5000",
                "card_power": "15000",
                "card_skill_unstyled": "[auto] test",
                "card_skill": "<b>test</b>",
                "card_traits": ["Trait"],
                "card_character": ["Character"],
                "card_era": ["Era"],
                "keywords": ["Auto"],
                "z_energy_cost": "",
                "is_banned": False,
                "is_limited": False,
                "limited_to": 4,
                "variants": [
                    {
                        "id": 101,
                        "card_number": "BT10-088_PR",
                        "card_name": "Card A Alt",
                        "card_series": "BT10",
                        "card_rarity": "Promo[PR]",
                        "card_type": "BATTLE",
                        "card_color": "Blue",
                        "card_energy_cost": "2",
                        "card_combo_cost": "0",
                        "card_combo_power": "5000",
                        "card_power": "15000",
                        "card_skill_unstyled": "[auto] test",
                        "card_skill": "<b>test</b>",
                        "card_traits": ["Trait"],
                        "card_character": ["Character"],
                        "card_era": ["Era"],
                        "keywords": ["Auto"],
                        "z_energy_cost": "",
                        "is_banned": False,
                        "is_limited": False,
                        "limited_to": 4,
                    }
                ],
            }
        ],
    }

    sql_text, summary = build_missing_cards_patch(payload)
    assert "INSERT OR REPLACE INTO cards" in sql_text
    assert "INSERT OR REPLACE INTO variants" in sql_text
    assert summary["base_cards_in_patch"] == 1
    assert summary["variants_in_patch"] == 1
    assert summary["missing_count"] == 1
