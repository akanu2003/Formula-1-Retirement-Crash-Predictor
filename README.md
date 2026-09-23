# Formula 1 Retirement / Crash Predictor

Predicting whether a Formula 1 driver will retire from a race (accident, collision,
mechanical failure, ...) using historical race data from the 2000–2024 seasons.

**Current status: step 2 — labels, pre-race features, and exploration.** No
models yet. See [EXPLANATION.md](EXPLANATION.md) for a plain-language walkthrough
of everything built so far and the decisions to make before step 3 (modeling).

## Project layout

```
├── src/                  # Python package with all reusable code
│   ├── config.py         # Paths and constants (seasons, API settings)
│   ├── jolpica.py        # Jolpica-F1 API client with on-disk caching
│   ├── build_dataset.py  # Fetch + flatten results into one tidy table
│   ├── quality_report.py # Generate the data-quality report
│   ├── labels.py         # THE labeling policy: status -> DNF + category
│   └── build_features.py # Pre-race feature table (leak-free history rates)
├── data/
│   ├── raw/              # Cached API responses (git-ignored, re-fetchable)
│   └── processed/        # Tidy datasets: Parquet + small CSV samples (committed)
├── notebooks/            # 01_exploration.ipynb: DNF charts with commentary
├── reports/              # Data-quality report + chart PNGs in figures/
├── requirements.txt
└── EXPLANATION.md        # Read this first
```

## How to run

```bash
# 1. Install dependencies (Python 3.10+)
pip install -r requirements.txt

# 2. Fetch race results for 2000–2024 and build data/processed/results.parquet
#    First run downloads ~120 pages from the Jolpica-F1 API (a few minutes).
#    Every response is cached under data/raw/, so re-runs are instant and offline.
python -m src.build_dataset

# 3. Regenerate the data-quality report at reports/data_quality.md
python -m src.quality_report

# 4. Rebuild the labeled table (runs the label validation checks) at
#    data/processed/results_labeled.parquet
python -m src.labels

# 5. Build the pre-race feature table at data/processed/features.parquet
#    (excludes cars that never took the start)
python -m src.build_features

# 6. (optional) Re-run the exploration notebook and regenerate the chart PNGs
jupyter nbconvert --to notebook --execute --inplace notebooks/01_exploration.ipynb
```

Every command is idempotent: run them as often as you like.

## Data source

Race results come from the [Jolpica-F1 API](https://api.jolpi.ca/ergast/f1/),
the community-run successor to the retired Ergast API. It is free, requires no
API key, and asks for polite usage — the loader paginates season by season and
sleeps between requests to stay well inside the published rate limits.
