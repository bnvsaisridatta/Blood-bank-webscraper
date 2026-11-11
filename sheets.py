"""
Google Sheets Manager (v2 – production)
=======================================
Writes blood bank data to per-city tabs with formatting.
Handles rate limiting and adds a Summary dashboard tab.
"""

import os
import time
import logging
from typing import List, Dict, Any
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger("BloodBankScraper")

HEADERS = [
    "Name", "Type", "Location", "City", "State",
    "Website", "Contact Number", "Email", "Source", "Date Scraped"
]


class GoogleSheetsManager:
    def __init__(self, credentials_path: str, spreadsheet_id: str):
        self.credentials_path = credentials_path
        self.spreadsheet_id = spreadsheet_id
        self.client = self._auth()
        self.sheet = self.client.open_by_key(self.spreadsheet_id)
        logger.info(f"[Sheets] Connected to '{self.sheet.title}'")

    def _auth(self) -> gspread.Client:
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(f"Credentials file '{self.credentials_path}' not found!")
        creds = Credentials.from_service_account_file(self.credentials_path, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ])
        return gspread.authorize(creds)

    def write_city_data(self, city_name: str, records: List[Dict[str, Any]]):
        if not records:
            logger.warning(f"[Sheets] Zero records for '{city_name}'. Skipping.")
            return

        title = city_name.strip().title()[:100]

        try:
            ws = self.sheet.worksheet(title)
            logger.info(f"[Sheets] Clearing existing tab '{title}'...")
            ws.clear()
        except gspread.WorksheetNotFound:
            logger.info(f"[Sheets] Creating tab '{title}'...")
            ws = self.sheet.add_worksheet(title=title,
                                          rows=max(len(records) + 10, 50),
                                          cols=len(HEADERS))

        rows = [HEADERS]
        for r in records:
            rows.append([
                r.get("name", "N/A"),
                r.get("type", "N/A"),
                r.get("location", "N/A"),
                r.get("city", "N/A"),
                r.get("state", "N/A"),
                r.get("website", "N/A"),
                r.get("contact_number", "N/A"),
                r.get("email", "N/A"),
                r.get("source", "N/A"),
                r.get("date_scraped", "N/A"),
            ])

        # Batch write
        ws.update(values=rows, range_name="A1")

        # Format header
        try:
            ws.freeze(rows=1)
            ws.format("A1:J1", {
                "textFormat": {"bold": True,
                               "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "backgroundColor": {"red": 0.70, "green": 0.12, "blue": 0.12},
                "horizontalAlignment": "CENTER"
            })
            ws.columns_auto_resize(0, len(HEADERS))
        except Exception as e:
            logger.debug(f"[Sheets] Formatting note: {e}")

        logger.info(f"[Sheets] Wrote {len(records)} rows → tab '{title}'")
        time.sleep(1.2)  # Respect Sheets API rate limits between cities

    def write_summary_tab(self, city_stats: List[Dict[str, Any]]):
        """Create or refresh a Summary / Dashboard tab."""
        title = "📊 Summary"
        try:
            ws = self.sheet.worksheet(title)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = self.sheet.add_worksheet(title=title, rows=50, cols=8)

        headers = ["Rank", "City", "State", "Blood Banks", "Hospital Blood Banks",
                    "Storage Centres", "Total Facilities", "Date Scraped"]
        rows = [headers]
        for i, cs in enumerate(city_stats, 1):
            rows.append([
                i,
                cs["city"],
                cs["state"],
                cs["blood_banks"],
                cs["hospital_blood_banks"],
                cs["storage_centres"],
                cs["total"],
                cs["date_scraped"],
            ])

        ws.update(values=rows, range_name="A1")
        try:
            ws.freeze(rows=1)
            ws.format("A1:H1", {
                "textFormat": {"bold": True,
                               "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "backgroundColor": {"red": 0.15, "green": 0.35, "blue": 0.60},
                "horizontalAlignment": "CENTER"
            })
            ws.columns_auto_resize(0, 8)
        except Exception:
            pass
        logger.info(f"[Sheets] Summary dashboard written with {len(city_stats)} cities.")
