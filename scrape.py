"""
scrape.py — IIT Commons Compass menu scraper
Hits the dineoncampus.com API and writes menu.json for the frontend.
Run manually: python scrape.py
Run automatically: GitHub Actions calls this every morning at 6am CT.
"""

import json
import requests
from datetime import date

# ── CONFIG ────────────────────────────────────────────────────────────────────
# IIT's location ID on dineoncampus. If the scraper ever breaks, open
# dineoncampus.com/iit in Chrome DevTools → Network → XHR and look for
# a request to api.dineoncampus.com — the location_id is in the URL.
LOCATION_ID = "5b33ae291178e909d807593d"

TODAY = date.today().strftime("%Y-%m-%d")

BASE_URL = "https://api.dineoncampus.com/v1/location/{loc}/periods"
MENU_URL = "https://api.dineoncampus.com/v1/location/{loc}/periods/{period}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CommonsCompass/1.0)",
    "Accept": "application/json",
}

# Known station name mapping — dineoncampus uses internal names, we rename
# them to match what students actually see on the signs at the Commons.
STATION_ALIASES = {
    "Grill":          "Daily Grill",
    "Daily Grill":    "Daily Grill",
    "Pasta":          "Pasta Station",
    "Pasta Station":  "Pasta Station",
    "Homestyle":      "Homestyle",
    "Home Style":     "Homestyle",
    "Deli":           "Deli",
    "Salad Bar":      "Salad Bar",
    "Salad":          "Salad Bar",
    "Global":         "Global Flavors",
    "Global Flavors": "Global Flavors",
    "International":  "Global Flavors",
}


def get_periods():
    """Fetch the list of meal periods (Breakfast, Lunch, Dinner) for today."""
    url = BASE_URL.format(loc=LOCATION_ID)
    resp = requests.get(url, params={"date": TODAY}, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("periods", [])


def get_menu(period_id):
    """Fetch the full menu for a given period."""
    url = MENU_URL.format(loc=LOCATION_ID, period=period_id)
    resp = requests.get(url, params={"date": TODAY}, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_nutrition(item):
    """Extract the nutrition facts we care about from a menu item dict."""
    nutrients = {}
    for n in item.get("nutrients", []):
        name = n.get("name", "").lower()
        val  = n.get("value_numeric") or 0
        if "calorie" in name:
            nutrients["cal"] = int(val)
        elif name.startswith("protein"):
            nutrients["pro"] = round(float(val), 1)
        elif "carbohydrate" in name or name == "total carb":
            nutrients["carb"] = round(float(val), 1)
        elif name.startswith("total fat") or name == "fat":
            nutrients["fat"] = round(float(val), 1)
        elif "sugar" in name:
            nutrients["sugar"] = round(float(val), 1)
    # Fill in zeros for anything missing
    for key in ("cal", "pro", "carb", "fat", "sugar"):
        nutrients.setdefault(key, 0)
    return nutrients


def build_menu_json():
    """Main function — pulls all periods and builds the stations list."""
    print(f"Fetching menu for {TODAY}...")

    periods = get_periods()
    if not periods:
        print("No periods returned — dining hall may be closed today.")
        return None

    # Prefer Lunch, then Dinner, then whatever's first
    def period_priority(p):
        name = p.get("name", "").lower()
        if "lunch" in name: return 0
        if "dinner" in name: return 1
        return 2

    periods.sort(key=period_priority)
    chosen = periods[0]
    print(f"  Using period: {chosen['name']}")

    menu_data = get_menu(chosen["id"])
    categories = menu_data.get("menu", {}).get("periods", {}).get("categories", [])

    if not categories:
        # Some API versions nest differently
        categories = menu_data.get("categories", [])

    stations_map = {}

    for cat in categories:
        raw_name  = cat.get("name", "Unknown")
        # Map to our friendly station name, or keep as-is
        station_name = STATION_ALIASES.get(raw_name, raw_name)

        items_out = []
        for item in cat.get("items", []):
            nutrition = parse_nutrition(item)
            items_out.append({
                "name":  item.get("name", "Unknown Item"),
                **nutrition,
            })

        if items_out:
            # Merge items if multiple API categories map to same station
            if station_name in stations_map:
                stations_map[station_name].extend(items_out)
            else:
                stations_map[station_name] = items_out

    # Convert to list format the frontend expects
    stations = [
        {"name": name, "items": items}
        for name, items in stations_map.items()
    ]

    output = {
        "date":    TODAY,
        "period":  chosen["name"],
        "fetched": True,
        "stations": stations,
    }

    with open("menu.json", "w") as f:
        json.dump(output, f, indent=2)

    total_items = sum(len(s["items"]) for s in stations)
    print(f"  Done — {len(stations)} stations, {total_items} items written to menu.json")
    return output


def write_fallback():
    """
    If the API is down or the dining hall is closed, write a fallback JSON
    so the frontend doesn't break — it'll show a 'closed today' message.
    """
    output = {
        "date":    TODAY,
        "period":  None,
        "fetched": False,
        "stations": [],
    }
    with open("menu.json", "w") as f:
        json.dump(output, f, indent=2)
    print("  Wrote fallback menu.json (no data available).")


if __name__ == "__main__":
    try:
        result = build_menu_json()
        if result is None:
            write_fallback()
    except Exception as e:
        print(f"Scraper error: {e}")
        write_fallback()
