"""Fetch 2000-2024 race results and save one tidy table.

Run with:  python -m src.build_dataset

Outputs:
    data/processed/results.parquet    - full dataset, one row per driver per race
    data/processed/results_sample.csv - first 200 rows, for eyeballing
"""

import logging

import pandas as pd
import requests

from src.config import PROCESSED_DIR, RESULTS_PARQUET, RESULTS_SAMPLE_CSV, SEASONS
from src.jolpica import fetch_season_results

logger = logging.getLogger(__name__)


def race_to_rows(race: dict) -> list[dict]:
    """Flatten one race dict (Ergast schema) into one row per driver."""
    rows = []
    for result in race.get("Results", []):
        driver = result["Driver"]
        constructor = result["Constructor"]
        rows.append(
            {
                "season": int(race["season"]),
                "round": int(race["round"]),
                "race_name": race["raceName"],
                "race_date": race.get("date"),
                "circuit_id": race["Circuit"]["circuitId"],
                "circuit_name": race["Circuit"]["circuitName"],
                "driver_id": driver["driverId"],
                "driver_code": driver.get("code"),
                "driver_name": f"{driver['givenName']} {driver['familyName']}",
                "constructor_id": constructor["constructorId"],
                "constructor_name": constructor["name"],
                "grid": int(result["grid"]),
                "position": int(result["position"]),
                "position_text": result["positionText"],
                "laps": int(result["laps"]),
                "status": result["status"],
            }
        )
    return rows


def build() -> pd.DataFrame:
    session = requests.Session()
    rows = []
    for season in SEASONS:
        races = fetch_season_results(season, session)
        season_rows = [row for race in races for row in race_to_rows(race)]
        rows.extend(season_rows)
        logger.info("Season %d: %d races, %d driver-race rows",
                    season, len(races), len(season_rows))

    df = pd.DataFrame(rows)
    df = df.sort_values(["season", "round", "position"]).reset_index(drop=True)
    df["race_date"] = pd.to_datetime(df["race_date"])
    return df


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    df = build()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(RESULTS_PARQUET, index=False)
    df.head(200).to_csv(RESULTS_SAMPLE_CSV, index=False)

    print(f"Wrote {len(df):,} rows x {len(df.columns)} columns to {RESULTS_PARQUET}")
    print(f"Sample (200 rows) at {RESULTS_SAMPLE_CSV}")


if __name__ == "__main__":
    main()
