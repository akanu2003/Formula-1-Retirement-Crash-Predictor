"""Build the first feature table: one row per driver-race, pre-race info only.

Run with:  python -m src.build_features   (after python -m src.build_dataset)

Every feature is knowable BEFORE the race starts, and every historical rate is
computed strictly from races that happened earlier (ordered by season, round).
The current race's outcome never contributes to its own row's features — that
would be data leakage. History only reaches back to 2000, the start of our
window (documented limitation: e.g. Michael Schumacher's 1990s races are
invisible to these counters).

Missing values are left as NaN on purpose (driver's first race, constructor's
first season, circuit's first appearance). How to fill them is a modeling
decision for step 3.

Rows with started=False (car never took the start) are excluded BEFORE any
history is computed: they neither appear as modeling rows nor feed the prior
rates, because nothing on track caused those outcomes. They remain in the
labeled table (data/processed/results_labeled.parquet) for the audit trail.

Output: data/processed/features.parquet (+ a small CSV sample), carrying
`status` and `position_text` through as audit columns so every labeling
decision can be re-checked without going back to the cache.
"""

import pandas as pd

from src.config import PROCESSED_DIR, RESULTS_PARQUET
from src.labels import apply_labels

FEATURES_PARQUET = PROCESSED_DIR / "features.parquet"
FEATURES_SAMPLE_CSV = PROCESSED_DIR / "features_sample.csv"


def add_driver_history(df: pd.DataFrame) -> pd.DataFrame:
    """Prior starts and prior DNF rate per driver, excluding the current race.

    df must be sorted chronologically. cumcount()/cumsum() run in row order,
    and subtracting the current row's own dnf makes the sums strictly-prior.
    """
    grouped = df.groupby("driver_id", sort=False)
    df["driver_prior_starts"] = grouped.cumcount()
    prior_dnfs = grouped["dnf"].cumsum() - df["dnf"].astype(int)
    df["driver_prior_dnf_rate"] = prior_dnfs / df["driver_prior_starts"]
    # 0/0 above yields NaN for debuts, which is what we want.
    return df


def add_circuit_history(df: pd.DataFrame) -> pd.DataFrame:
    """DNF rate over all earlier races held at the same circuit.

    Aggregated per race first, so every driver in a given race gets the same
    value and the shift(1) excludes the current race entirely.
    """
    races = (
        df.groupby(["season", "round", "circuit_id"], as_index=False)
        .agg(entries=("dnf", "size"), dnfs=("dnf", "sum"))
        .sort_values(["season", "round"])
    )
    by_circuit = races.groupby("circuit_id", sort=False)
    races["cum_entries"] = by_circuit["entries"].cumsum()
    races["cum_dnfs"] = by_circuit["dnfs"].cumsum()
    # Group-wise shift moves each circuit's running totals down one race, so a
    # race sees only earlier races at the SAME circuit (NaN at its first one).
    by_circuit2 = races.groupby("circuit_id", sort=False)
    prior_entries = by_circuit2["cum_entries"].shift(1)
    prior_dnfs = by_circuit2["cum_dnfs"].shift(1)
    races["circuit_hist_dnf_rate"] = prior_dnfs / prior_entries
    return df.merge(
        races[["season", "round", "circuit_hist_dnf_rate"]],
        on=["season", "round"],
        how="left",
    )


def add_constructor_history(df: pd.DataFrame) -> pd.DataFrame:
    """Constructor's DNF rate over the WHOLE previous season (NaN if absent)."""
    season_rates = (
        df.groupby(["constructor_id", "season"], as_index=False)
        .agg(constructor_prev_season_dnf_rate=("dnf", "mean"))
    )
    season_rates["season"] += 1  # a season's rate becomes next season's feature
    return df.merge(season_rates, on=["constructor_id", "season"], how="left")


def build() -> pd.DataFrame:
    df = apply_labels(pd.read_parquet(RESULTS_PARQUET))
    # Drop never-started rows before computing anything, so they are neither
    # modeling rows nor part of any prior-rate denominator.
    df = df[df["started"]]
    df = df.sort_values(["season", "round", "position"]).reset_index(drop=True)

    df = add_driver_history(df)
    df = add_circuit_history(df)
    df = add_constructor_history(df)

    columns = [
        # identifiers / context (all known before the race)
        "season", "round", "race_date", "circuit_id",
        "driver_id", "constructor_id", "grid",
        # engineered pre-race features
        "driver_prior_starts", "driver_prior_dnf_rate",
        "constructor_prev_season_dnf_rate", "circuit_hist_dnf_rate",
        # targets (outcomes - never to be used as inputs)
        "dnf", "dnf_category", "label_unsure", "disqualified",
        # audit columns (outcome data - never features): the raw values the
        # labels were decided from, kept so decisions can be re-checked
        "status", "position_text",
    ]
    return df[columns]


def main():
    df = build()

    # Leakage guard: season 2000, round 1 must have no history at all.
    first = df[(df.season == 2000) & (df["round"] == 1)]
    assert (first["driver_prior_starts"] == 0).all()
    assert first["driver_prior_dnf_rate"].isna().all()
    assert first["circuit_hist_dnf_rate"].isna().all()
    assert first["constructor_prev_season_dnf_rate"].isna().all()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(FEATURES_PARQUET, index=False)
    df.head(200).to_csv(FEATURES_SAMPLE_CSV, index=False)
    print(f"Wrote {len(df):,} rows x {len(df.columns)} columns to {FEATURES_PARQUET}")
    print(df.isna().sum().to_string())


if __name__ == "__main__":
    main()
