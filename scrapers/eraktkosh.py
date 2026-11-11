"""
eRaktKosh Blood Bank Directory Scraper (v2 – production-quality)
================================================================
Calls the eRaktKosh (MoHFW) REST API at eraktkosh.mohfw.gov.in.

API endpoints reverse-engineered from the React SPA bundle:
  GET  /eraktkoshPortal/eraktkosh/blood-availability?stateCode=XX&districtCode=-1
  POST /eraktkoshPortal/eraktkosh/eqas/details/getBloodCentreInfo  {hospitalCode: N}

Data quality:
  • Fake / placeholder phones are rejected (sequential, all-same, 1234…, 0000…)
  • Valid Indian mobile (10-digit starting 6-9) & landlines (starting 0 or 2-5, 7-11 digits) are preserved
  • Emails are extracted from the contact blob
  • Facilities are filtered to the requested city/district using fuzzy address match
  • Type is inferred from both the API `type` + `hospitalType` fields
"""

import os
import json
import time
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
import requests

logger = logging.getLogger("BloodBankScraper")

BASE_API = "https://eraktkosh.mohfw.gov.in/eraktkoshPortal"

# ── State-code mapping ────────────────────────────────────────────────
STATE_CODE_MAP: Dict[str, int] = {
    "delhi": 97, "new delhi": 97,
    "maharashtra": 27, "mumbai": 27, "pune": 27, "nagpur": 27,
    "karnataka": 29, "bengaluru": 29, "bangalore": 29,
    "telangana": 36, "hyderabad": 36,
    "tamil nadu": 33, "chennai": 33, "coimbatore": 33,
    "west bengal": 19, "kolkata": 19, "calcutta": 19,
    "uttar pradesh": 99, "lucknow": 99, "noida": 99, "kanpur": 99, "varanasi": 99,
    "gujarat": 24, "ahmedabad": 24, "surat": 24,
    "rajasthan": 98, "jaipur": 98,
    "madhya pradesh": 23, "bhopal": 23, "indore": 23, "jabalpur": 23,
    "punjab": 93, "amritsar": 93,
    "chandigarh": 94, "new chandigarh": 94,
    "haryana": 96, "gurgaon": 96, "gurugram": 96,
    "kerala": 32, "kochi": 32, "thiruvananthapuram": 32, "trivandrum": 32,
    "bihar": 10, "patna": 10,
    "andhra pradesh": 28, "visakhapatnam": 28, "vijayawada": 28, "vizag": 28,
    "odisha": 21, "bhubaneswar": 21, "cuttack": 21,
    "jharkhand": 20, "ranchi": 20,
    "assam": 18, "guwahati": 18,
    "chhattisgarh": 22, "raipur": 22,
    "uttarakhand": 95, "dehradun": 95,
    "jammu and kashmir": 91, "srinagar": 91, "jammu": 91,
    "himachal pradesh": 92, "shimla": 92,
    "goa": 30,
    "tripura": 16,
    "meghalaya": 17,
    "manipur": 14,
    "nagaland": 13,
    "mizoram": 15,
    "arunachal pradesh": 12,
    "sikkim": 11,
    "puducherry": 34, "pondicherry": 34,
    "ladakh": 37,
    "andaman and nicobar islands": 35,
    "dadra and nagar haveli and daman and diu": 25,
    "lakshadweep": 31,
}

STATE_NAMES_BY_CODE: Dict[int, str] = {
    10: "Bihar", 11: "Sikkim", 12: "Arunachal Pradesh", 13: "Nagaland",
    14: "Manipur", 15: "Mizoram", 16: "Tripura", 17: "Meghalaya",
    18: "Assam", 19: "West Bengal", 20: "Jharkhand", 21: "Odisha",
    22: "Chhattisgarh", 23: "Madhya Pradesh", 24: "Gujarat",
    25: "Dadra And Nagar Haveli And Daman And Diu", 27: "Maharashtra",
    28: "Andhra Pradesh", 29: "Karnataka", 30: "Goa", 31: "Lakshadweep",
    32: "Kerala", 33: "Tamil Nadu", 34: "Puducherry",
    35: "Andaman and Nicobar Islands", 36: "Telangana", 37: "Ladakh",
    91: "Jammu and Kashmir", 92: "Himachal Pradesh", 93: "Punjab",
    94: "Chandigarh", 95: "Uttarakhand", 96: "Haryana",
    97: "Delhi", 98: "Rajasthan", 99: "Uttar Pradesh",
}

# City-states / UTs where all entries belong to the city
CITY_STATES = {94, 97, 30, 31, 34, 35, 37, 25}

CITY_ALIASES: Dict[str, List[str]] = {
    "bengaluru": ["bengaluru", "bangalore", "bengaluru urban", "bengaluru rural", "blr"],
    "mumbai": ["mumbai", "bombay", "thane", "navi mumbai", "mumbai suburban", "mumbai city"],
    "kolkata": ["kolkata", "calcutta", "howrah"],
    "chennai": ["chennai", "madras"],
    "kochi": ["kochi", "cochin", "ernakulam"],
    "thiruvananthapuram": ["thiruvananthapuram", "trivandrum"],
    "pune": ["pune", "poona"],
    "varanasi": ["varanasi", "benaras", "kashi"],
    "visakhapatnam": ["visakhapatnam", "vizag", "vishakhapatnam"],
    "guwahati": ["guwahati", "gauhati", "kamrup"],
    "bhubaneswar": ["bhubaneswar", "bhubaneshwar", "khurda", "khordha"],
    "cuttack": ["cuttack", "cuttak"],
    "coimbatore": ["coimbatore"],
    "nagpur": ["nagpur"],
    "chandigarh": ["chandigarh", "mohali", "panchkula"],
    "shimla": ["shimla", "simla"],
    "srinagar": ["srinagar"],
    "dehradun": ["dehradun", "dehra dun"],
    "jabalpur": ["jabalpur"],
    "amritsar": ["amritsar"],
    "ahmedabad": ["ahmedabad", "amdavad"],
    "jaipur": ["jaipur"],
    "lucknow": ["lucknow"],
    "patna": ["patna"],
    "indore": ["indore"],
    "bhopal": ["bhopal"],
    "raipur": ["raipur"],
    "ranchi": ["ranchi"],
}


# ── Phone / Contact validation ────────────────────────────────────────

def is_fake_phone(number: str) -> bool:
    """Return True if the number looks like a placeholder / test value."""
    digits = re.sub(r'\D', '', number)
    if len(digits) < 7:
        return True
    # All same digit: 1111111111, 00000000
    if len(set(digits)) == 1:
        return True
    # Sequential strings like 123456789, 0123456789, 987654321
    if digits in "012345678901234567890" or "12345678" in digits or "98765432" in digits:
        return True
    # Repeating patterns: 12121212, 123123123
    for plen in (2, 3):
        pat = digits[:plen]
        if digits == (pat * (len(digits) // plen + 1))[:len(digits)]:
            return True
    # Specific common junk placeholders
    if digits in ("1234567890", "0987654321", "9999999999", "0000000000",
                   "1111111111", "1234567891", "9876543210", "1234512345",
                   "0123456789", "12345678", "1234567", "0000000", "1111111"):
        return True
    return False


def clean_phone(raw_phone: str) -> str:
    """Extract and validate Indian phone numbers from a raw contact string."""
    if not raw_phone or raw_phone.strip() in ("", "-", "N/A", "0", "NA"):
        return "N/A"

    valid = []
    # 1. 10-digit mobile numbers starting with 6, 7, 8, or 9
    mobiles = re.findall(r'(?:\+?91[\-\s]?)?0?([6-9]\d{9})', raw_phone)
    for m in mobiles:
        clean_m = re.sub(r'\D', '', m)
        if len(clean_m) == 10 and not is_fake_phone(clean_m):
            valid.append(clean_m)

    # 2. Standard Indian landlines with STD code (e.g. 011-23404286, 022-24101234)
    std_landlines = re.findall(r'(?:0\d{2,4}[\-\s]?\d{6,8})', raw_phone)
    for ll in std_landlines:
        clean_ll = re.sub(r'\D', '', ll)
        if 8 <= len(clean_ll) <= 12 and not is_fake_phone(clean_ll):
            valid.append(clean_ll)

    # 3. Direct metro subscriber numbers (e.g. 23404286, 24101234 starting with 2-5)
    direct_landlines = re.findall(r'\b([2-5]\d{6,7})\b', raw_phone)
    for dl in direct_landlines:
        clean_dl = re.sub(r'\D', '', dl)
        if 7 <= len(clean_dl) <= 8 and not is_fake_phone(clean_dl):
            valid.append(clean_dl)

    if valid:
        return ", ".join(dict.fromkeys(valid))
    return "N/A"


def parse_contact_blob(blob: str) -> Tuple[str, str]:
    """Parse eRaktKosh contact string → (phone, email)."""
    phone = "N/A"
    email = "N/A"
    if not blob:
        return phone, email
    # Extract phone part
    phone_match = re.search(r'Phone:\s*([\d\s,\-\+/]+)', blob, re.I)
    if phone_match:
        phone = clean_phone(phone_match.group(1))
    else:
        phone = clean_phone(blob)
    # Extract email
    email_match = re.search(r'Email:\s*([a-zA-Z0-9_.+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', blob, re.I)
    if email_match:
        email = email_match.group(1).strip()
    return phone, email


def validate_url(url: str) -> str:
    if not url or url.strip() in ("", "N/A", "NA"):
        return "N/A"
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    return url if re.match(r'^https?://[a-zA-Z0-9]', url) else "N/A"


# ── Facility type classification ──────────────────────────────────────

def classify_facility(api_type: str, hospital_type: str, name: str) -> str:
    text = f"{api_type} {hospital_type} {name}".lower()
    if any(kw in text for kw in ("storage", "bsc", "storage centre")):
        return "Storage Centre"
    if any(kw in text for kw in (
        "hospital", "govt", "government", "medical college", "institute",
        "aiims", "pgimer", "army", "military", "air force", "navy",
        "esi", "mcd", "cantonment"
    )):
        return "Hospital Blood Bank"
    return "Blood Bank"


# ── Address-based city filter ─────────────────────────────────────────

def facility_matches_city(address: str, city: str, state_code: int) -> bool:
    """Return True if the facility address belongs to the requested city."""
    if state_code in CITY_STATES:
        return True  # All entries in Delhi, Chandigarh, Goa belong to the city-state
    addr_lower = address.lower()
    city_lower = city.lower()
    aliases = CITY_ALIASES.get(city_lower, [city_lower])
    return any(alias in addr_lower for alias in aliases)


# ── Main scraper class ────────────────────────────────────────────────

class ERaktKoshScraper:
    def __init__(self, cache_dir: str = "cache", delay: float = 1.0, user_agent: str = None):
        self.cache_dir = cache_dir
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://eraktkosh.mohfw.gov.in/eraktkoshPortal/"
        })
        os.makedirs(self.cache_dir, exist_ok=True)

    def _cache_path(self, city: str) -> str:
        return os.path.join(self.cache_dir, f"eraktkosh_{re.sub(r'[^a-z0-9]', '_', city.lower())}.json")

    def fetch(self, place_name: str) -> List[Dict[str, Any]]:
        cache_file = self._cache_path(place_name)
        if os.path.exists(cache_file):
            logger.info(f"[eRaktKosh] Cache hit for '{place_name}'")
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data:
                        return data
            except Exception:
                pass

        logger.info(f"[eRaktKosh] Fetching facilities for '{place_name}'...")
        results = self._fetch_from_api(place_name)

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"[eRaktKosh] Retrieved {len(results)} facilities for '{place_name}'")
        return results

    def _fetch_from_api(self, place_name: str) -> List[Dict[str, Any]]:
        state_code = STATE_CODE_MAP.get(place_name.strip().lower())
        if not state_code:
            logger.warning(f"[eRaktKosh] No state code mapping for '{place_name}'")
            return []

        state_name = STATE_NAMES_BY_CODE.get(state_code, "N/A")
        time.sleep(self.delay)

        url = f"{BASE_API}/eraktkosh/blood-availability"
        try:
            res = self.session.get(url, params={"stateCode": state_code, "districtCode": -1}, timeout=15)
            if res.status_code != 200:
                logger.error(f"[eRaktKosh] HTTP {res.status_code} from blood-availability")
                return []
            raw_data = res.json()
        except Exception as e:
            logger.error(f"[eRaktKosh] API error: {e}")
            return []

        results = []
        for item in raw_data:
            name = (item.get("hospitalname") or "").strip()
            address = (item.get("hospitaladd") or "N/A").strip()
            contact_blob = item.get("hospitalcontact") or ""
            hospital_code = item.get("hospitalCode")
            api_type = item.get("type") or ""
            hosp_type = item.get("hospitalType") or ""

            if not name:
                continue

            # City filter: skip facilities outside the requested city
            if not facility_matches_city(address, place_name, state_code):
                continue

            # Parse contact info (clean phone + extract real email)
            phone, email = parse_contact_blob(contact_blob)

            # Classify facility type
            ftype = classify_facility(api_type, hosp_type, name)

            # Derive website from email domain or official portal
            website = "https://eraktkosh.mohfw.gov.in"
            if email != "N/A" and "@" in email:
                domain = email.split("@")[1].lower()
                if domain not in ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                                  "rediffmail.com", "ymail.com", "mail.com"):
                    candidate = f"https://{domain}"
                    website = validate_url(candidate)

            # Infer city from address
            city = place_name.strip().title()
            addr_lower = address.lower()
            aliases = CITY_ALIASES.get(place_name.lower(), [place_name.lower()])
            for alias in aliases:
                if alias in addr_lower:
                    city = alias.title()
                    break

            results.append({
                "name": name,
                "type": ftype,
                "location": address,
                "city": city,
                "state": state_name,
                "website": website,
                "contact_number": phone,
                "email": email,
                "source": "eRaktKosh",
                "hospital_code": str(hospital_code) if hospital_code else ""
            })

        return results
