"""Central place for paths and constants so no other module hard-codes them."""

from pathlib import Path

# Repository root = one level above src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"

# Seasons covered by the project (inclusive).
FIRST_SEASON = 2000
LAST_SEASON = 2024
SEASONS = range(FIRST_SEASON, LAST_SEASON + 1)

# Jolpica-F1 API (Ergast successor). No API key needed.
API_BASE_URL = "https://api.jolpi.ca/ergast/f1"
# Jolpica caps `limit` at 100 rows per response.
PAGE_SIZE = 100
# Polite pause between HTTP requests, in seconds. Jolpica's unauthenticated
# rate limit is 4 requests/second burst and 500 requests/hour sustained;
# ~120 total requests at this pace stays comfortably inside both.
REQUEST_DELAY_SECONDS = 0.6

# Output files
RESULTS_PARQUET = PROCESSED_DIR / "results.parquet"
RESULTS_SAMPLE_CSV = PROCESSED_DIR / "results_sample.csv"
QUALITY_REPORT_MD = REPORTS_DIR / "data_quality.md"
