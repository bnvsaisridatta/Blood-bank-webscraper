"""
Merge & Deduplicate blood bank records from eRaktKosh + OSM (v2)
================================================================
Uses rapidfuzz token-set matching on normalized names.
Prefers eRaktKosh values; enriches missing fields from OSM.
"""

import datetime
import logging
import re
from typing import List, Dict, Any
from rapidfuzz import fuzz

logger = logging.getLogger("BloodBankScraper")


def _normalize(name: str) -> str:
    if not name:
        return ""
    text = name.lower()
    for token in (r'\bblood\s*bank\b', r'\bblood\s*cent(?:re|er)\b',
                  r'\bstorage\s*cent(?:re|er)\b', r'\bdonation\s*cent(?:re|er)\b',
                  r'\bhospital\b', r'\bcharitable\b', r'\btrust\b',
                  r'\bmemorial\b', r'\bgovt\.?\b', r'\bgovernment\b',
                  r'\bshri\b', r'\bdr\.?\b', r'\bsmt\.?\b', r'\bltd\.?\b',
                  r'\bpvt\.?\b', r'\bsociety\b', r'\brotary\b', r'\bred\s*cross\b'):
        text = re.sub(token, '', text, flags=re.I)
    return re.sub(r'[^a-z0-9]', '', text)


def merge_and_deduplicate(
    eraktkosh_data: List[Dict[str, Any]],
    osm_data: List[Dict[str, Any]],
    threshold: float = 78.0
) -> List[Dict[str, Any]]:
    today = datetime.date.today().isoformat()
    merged: List[Dict[str, Any]] = []

    for item in eraktkosh_data:
        r = dict(item)
        r["date_scraped"] = today
        merged.append(r)

    for osm in osm_data:
        norm_osm = _normalize(osm.get("name", ""))
        match = None
        if norm_osm:
            for existing in merged:
                norm_ex = _normalize(existing.get("name", ""))
                if not norm_ex:
                    continue
                if norm_osm == norm_ex or fuzz.token_set_ratio(norm_osm, norm_ex) >= threshold:
                    match = existing
                    break

        if match:
            for field in ("website", "contact_number", "location", "state", "email"):
                if match.get(field) in ("N/A", "", None) and osm.get(field) not in ("N/A", "", None):
                    match[field] = osm[field]
            if "OSM" not in match.get("source", ""):
                match["source"] = f"{match['source']} / OSM"
        else:
            r = dict(osm)
            r["date_scraped"] = today
            merged.append(r)

    # Final cleanup
    for r in merged:
        for k in r:
            if r[k] is None or str(r[k]).strip() in ("", "none", "None"):
                r[k] = "N/A"

    logger.info(f"[Merge] {len(merged)} unique facilities "
                f"({len(eraktkosh_data)} eRaktKosh + {len(osm_data)} OSM)")
    return merged
