# Blood Bank Directory Scraper

A specialized Python backend automation tool that scrapes, deduplicates, and compiles blood banks, blood storage centres, and hospitals with blood banks across India, syncing the structured directory directly to a Google Sheet.

---

## 🌟 Key Features

1. **Dual-Source Data Extraction**:
   - **Primary Source (eRaktKosh)**: Official National Blood Transfusion Council / MoHFW portal (`eraktkosh.mohfw.gov.in`). Directly calls real-time centralized registry endpoints with automated state-code resolution and Playwright browser fallback.
   - **Secondary Source (OpenStreetMap)**: Nominatim geocoding + Overpass API extracting OSM nodes and ways tagged with `healthcare=blood_bank`, `amenity=blood_donation`, and hospital blood banks.
2. **Intelligent Deduplication & Merging**:
   - Uses `rapidfuzz` token-based fuzzy matching on normalized facility names and cities.
   - Prefers authoritative eRaktKosh data while enriching missing fields (website, phone, coordinates) from OpenStreetMap.
3. **Automated Google Sheets Synchronization**:
   - Authenticates using a free Google Cloud Service Account (`credentials.json`) via `gspread`.
   - Creates a dedicated worksheet tab for each scraped city/place.
   - Clears and refreshes existing tabs upon re-run (preventing row duplicates).
   - Styled header row (frozen, bold white-on-crimson) with auto-fitted column widths.
   - Missing fields are standardized to `"N/A"` (never silently omitted).
4. **Resilient & Polite Crawling**:
   - Rate limiting (1.5s delay) and retry logic with backoff.
   - Transparent local JSON caching in `cache/` to minimize external requests on repeat queries.
   - Comprehensive file logging in `logs/scraper.log`.

---

## 📁 Project Structure

```text
Blood bank webscraper/
├── config/
│   ├── .env               # Active environment configuration
│   └── .env.example       # Example template
├── scrapers/
│   ├── __init__.py
│   ├── eraktkosh.py       # eRaktKosh scraper (API + fallback)
│   └── osm.py             # OpenStreetMap Nominatim/Overpass scraper
├── cache/                 # Cached raw JSON responses
├── logs/                  # Application logs (scraper.log)
├── credentials.json       # Google Cloud Service Account key (user-provided)
├── merge.py               # Fuzzy deduplication and field enrichment
├── sheets.py              # gspread Google Sheets client
├── main.py                # Command-line entrypoint
├── requirements.txt       # Python dependencies
└── README.md              # Documentation
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
- Python 3.9+ (tested on Python 3.13)
- Google account (to create the free Google Cloud Service Account and Google Sheet)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```
*(Optional) If you want Playwright browser fallback enabled:*
```bash
playwright install chromium
```

### 3. Configure `.env`
Edit `config/.env`:
```env
GOOGLE_SPREADSHEET_ID=your_spreadsheet_id_here
GOOGLE_SERVICE_ACCOUNT_FILE=credentials.json
REQUEST_DELAY_SECONDS=1.5
MAX_RETRIES=3
USER_AGENT=BloodBankDirectoryScraper/1.0 (+https://github.com/internship/blood-bank-scraper)
```

---

## 🔑 Google Cloud Service Account & Sheets Setup

To enable Google Sheets syncing:

### Step 1: Create a Google Cloud Project & Enable APIs
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown at the top and select **New Project** (e.g. `Blood-Bank-Scraper`).
3. In the search bar, search for **Google Sheets API** and click **Enable**.
4. Search for **Google Drive API** and click **Enable**.

### Step 2: Create a Service Account & Download Key
1. Go to **APIs & Services > Credentials**.
2. Click **+ CREATE CREDENTIALS** > **Service account**.
3. Enter a Service Account Name (e.g., `sheet-writer`) and click **Create and Continue**, then click **Done**.
4. Under the **Service Accounts** list, click on the newly created service account email.
5. Go to the **Keys** tab > **Add Key** > **Create new key**.
6. Select **JSON** and click **Create**.
7. Rename the downloaded JSON file to `credentials.json` and move it to the root of this project folder (`Blood bank webscraper/credentials.json`).

### Step 3: Create & Share Your Google Sheet
1. Open [Google Sheets](https://sheets.new) and create a new blank spreadsheet.
2. Name the sheet (e.g., `Blood Bank Master Directory`).
3. Click the green **Share** button in the top right.
4. Copy the service account email address from your `credentials.json` (it looks like: `sheet-writer@<your-project>.iam.gserviceaccount.com`).
5. Paste this email into the Share dialog, grant it **Editor** permissions, and click **Send**.
6. Copy the Spreadsheet ID from the URL:
   ```text
   https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                     (This is the ID)
   ```
7. Paste this ID into `config/.env` as `GOOGLE_SPREADSHEET_ID`.

---

## 💻 Usage Examples

### 1. Single City
```bash
python main.py "Delhi"
```

### 2. Multiple Cities in One Run
```bash
python main.py "Delhi,Mumbai,Hyderabad"
```

### 3. Interactive Prompt
Run without arguments and enter the name when prompted:
```bash
python main.py
```

---

## 📊 Extracted Fields Specification

| Column Header | Description | Example |
| :--- | :--- | :--- |
| **Name** | Facility name | *ABVIMS, Dr Ram Manohar Lohia Hospital* |
| **Type** | Blood Bank / Hospital Blood Bank / Storage Centre | *Hospital Blood Bank* |
| **Location** | Full physical street address | *Baba Kharak Singh Marg, Near Gurudwara Bangla Sahib* |
| **City** | City / District | *New Delhi* |
| **State** | State or Union Territory | *Delhi* |
| **Website** | Institutional URL or portal entry | *https://eraktkosh.mohfw.gov.in* |
| **Contact Number** | Cleaned 10-digit mobile or landline numbers | *9811857635, 23404286* |
| **Source** | Origin registry | *eRaktKosh*, *OSM*, or *eRaktKosh / OSM* |
| **Date Scraped** | ISO-8601 scraping date | *2026-11-10* |

