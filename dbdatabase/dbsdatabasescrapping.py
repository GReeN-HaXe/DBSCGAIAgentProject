import requests
import json
import time

BASE_URL = "https://api.deckplanet.net/cardsearch/dbs_masters_cards"

all_cards = []
page = 1
total_pages = 123  # from your meta data

while page <= total_pages:
    print(f"Pulling page {page}...")
    
    params = {
        "page": page,
        "filter": '{"_and":[{"status":{"_eq":"published"}},{"variant_of":{"id":{"_null":true}}}]}',
        "deep": '{"variants":{"_limit":-1,"_sort":"card_number","_filter":{"status":{"_eq":"published"}}}}'
    }

    response = requests.get(BASE_URL, params=params)
    data = response.json()
    
    all_cards.extend(data["data"])
    
    page += 1
    time.sleep(0.3)  # rate limiting so we don't spam

with open("dbs_masters_full.json", "w", encoding="utf-8") as f:
    json.dump(all_cards, f, indent=2, ensure_ascii=False)

print(f"Export complete. Total cards: {len(all_cards)}")