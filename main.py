"""
Blood Bank Directory Scraper – Main CLI (v2)
=============================================
Usage:
  python main.py "Delhi"
  python main.py "Delhi,Mumbai,Hyderabad"
  python main.py --all-priority          # Run all 30 priority cities
"""

import sys
import os
import argparse
import logging
import datetime
from dotenv import load_dotenv

from scrapers.eraktkosh import ERaktKoshScraper
from scrapers.osm import OSMScraper
from merge import merge_and_deduplicate
from sheets import GoogleSheetsManager

load_dotenv(os.path.join(os.path.dirname(__file__), "config", ".env"))
load_dotenv(".env")

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join("logs", "scraper.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("BloodBankScraper")

# 30 priority cities from the medical-partner list
PRIORITY_CITIES = [
    "Mumbai", "Delhi", "Chennai", "Bengaluru", "Hyderabad",
    "Kolkata", "Ahmedabad", "Pune", "Chandigarh", "Thiruvananthapuram",
    "Jaipur", "Lucknow", "Varanasi", "Bhubaneswar", "Guwahati",
    "Nagpur", "Cuttack", "Patna", "Coimbatore", "Kochi",
    "Indore", "Bhopal", "Raipur", "Ranchi", "Amritsar",
    "Shimla", "Srinagar", "Jabalpur", "Visakhapatnam", "Dehradun",
]


def process_city(city, erakt, osm, sheets_mgr=None):
    city = city.strip()
    if not city:
        return None

    print(f"\n{'='*70}")
    print(f"  PROCESSING: {city.upper()}")
    print(f"{'='*70}")

    # 1. eRaktKosh
    print(f"  [1/3] eRaktKosh...")
    erakt_records = erakt.fetch(city)

    # 2. OSM
    print(f"  [2/3] OpenStreetMap...")
    osm_records = osm.fetch(city)

    # 3. Merge
    print(f"  [3/3] Merging & deduplicating...")
    merged = merge_and_deduplicate(erakt_records, osm_records)

    if not merged:
        print(f"  [!] Zero results for '{city}'. Skipping.")
        return None

    # Count by type
    bb = sum(1 for r in merged if r["type"] == "Blood Bank")
    hbb = sum(1 for r in merged if r["type"] == "Hospital Blood Bank")
    sc = sum(1 for r in merged if r["type"] == "Storage Centre")

    print(f"  [+] {city}: {len(merged)} facilities "
          f"(BB={bb}, Hospital BB={hbb}, Storage={sc})")
    print(f"      Sources: {len(erakt_records)} eRaktKosh + {len(osm_records)} OSM")

    # Preview top 3
    for i, r in enumerate(merged[:3], 1):
        print(f"      {i}. {r['name']} | {r['type']} | ☎ {r['contact_number']}")

    # 4. Google Sheets
    if sheets_mgr:
        try:
            sheets_mgr.write_city_data(city, merged)
            print(f"  [✓] Sheet tab '{city.title()}' updated!")
        except Exception as e:
            logger.error(f"Sheets error for {city}: {e}", exc_info=True)
            print(f"  [X] Sheets error: {e}")

    return {
        "city": city.title(),
        "state": merged[0].get("state", "N/A") if merged else "N/A",
        "blood_banks": bb,
        "hospital_blood_banks": hbb,
        "storage_centres": sc,
        "total": len(merged),
        "date_scraped": datetime.date.today().isoformat()
    }


def main():
    parser = argparse.ArgumentParser(description="Blood Bank Directory Scraper v2")
    parser.add_argument("places", nargs="?",
                        help="City name or comma-separated list")
    parser.add_argument("--all-priority", action="store_true",
                        help="Run all 30 priority cities")
    args = parser.parse_args()

    if args.all_priority:
        cities = PRIORITY_CITIES
    elif args.places:
        cities = [c.strip() for c in args.places.split(",") if c.strip()]
    else:
        try:
            inp = input("Enter city/cities (comma-separated): ").strip()
            cities = [c.strip() for c in inp.split(",") if c.strip()]
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)

    if not cities:
        print("No cities provided.")
        sys.exit(0)

    delay = float(os.getenv("REQUEST_DELAY_SECONDS", "1.5"))
    ua = os.getenv("USER_AGENT")
    erakt = ERaktKoshScraper(delay=delay, user_agent=ua)
    osm = OSMScraper(delay=delay, user_agent=ua)

    sheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
    creds_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")
    sheets_mgr = None
    if sheet_id and os.path.exists(creds_path):
        try:
            sheets_mgr = GoogleSheetsManager(creds_path, sheet_id)
            print(f"[✓] Connected to Google Sheet")
        except Exception as e:
            print(f"[!] Sheets init failed: {e}. Continuing locally.")

    stats = []
    for city in cities:
        result = process_city(city, erakt, osm, sheets_mgr)
        if result:
            stats.append(result)

    # Write summary dashboard
    if sheets_mgr and stats:
        try:
            sheets_mgr.write_summary_tab(stats)
            print(f"\n[✓] Summary dashboard written with {len(stats)} cities.")
        except Exception as e:
            print(f"[!] Summary write failed: {e}")

    print(f"\n{'='*70}")
    print(f"  COMPLETED: {len(stats)}/{len(cities)} cities processed")
    print(f"  Total facilities across all cities: {sum(s['total'] for s in stats)}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
