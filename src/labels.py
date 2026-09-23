"""Map every race-result row to prediction labels.

This file IS the labeling policy. Edit the sets below to change how statuses
are classified; nothing else in the project hard-codes a status string.

Labels are decided from `status` PLUS `position_text` (the official
classification): the classification outranks the status string, because the
source sometimes puts a lap gap (e.g. "+42 Laps") in `status` for a car that
actually stopped mid-race (positionText "R").

Columns produced for each row:

    dnf           True if the car did not make it to the flag, else False.
                  A driver who retired close enough to the end to be officially
                  classified (numeric position_text) still counts as a DNF.
                  Disqualified cars count as FINISHED: the project's question is
                  whether the car survives the race, not how the result was
                  later ruled (see `disqualified` below for sensitivity checks).
    dnf_category  For DNF rows only: "accident", "mechanical", "unknown", or
                  "other". None for finishers.
    started       False for cars that never took the start (a never-started
                  status AND zero laps). NOTE the laps guard: a handful of
                  "Withdrew" rows are really mid/late-race retirements with
                  47-55 laps completed (Button Malaysia 2013, Norris Mexico
                  2019, Magnussen Turkey 2020, Alonso Mexico 2023) - those
                  count as started. Never-started rows stay in the labeled
                  table for the audit trail; the feature build excludes them,
                  because nothing on track caused the outcome.
    disqualified  True for "Disqualified"/"Excluded" rows, so the dnf=False
                  ruling on them can be sensitivity-checked later.
    label_unsure  True for statuses listed in UNSURE (judgment calls).

Categories:
    accident    - the driver crashed, spun, or was involved in contact.
    mechanical  - the car (or its fuelling/equipment) broke.
    unknown     - retired per the classification, but no cause recorded
                  (the status field holds a lap gap instead of a reason).
    other       - remaining non-crash, non-breakdown DNFs: withdrawals,
                  illness/injury, safety, the generic "Retired".

Every status seen in the 2000-2024 data is covered; classify_status() raises
on anything new, and validate_labels() cross-checks every rebuild against the
official classification, so an updated dataset can never be silently
mislabeled.
"""

import re

import pandas as pd

# ---------------------------------------------------------------------------
# Finished: crossed the line, possibly some laps behind the winner.
# "+N Lap(s)" values are matched by pattern so new lap counts never break us.
# ---------------------------------------------------------------------------
FINISHED = {
    "Finished",
    "Lapped",  # older encoding of "finished, laps down"
}
LAPS_DOWN_PATTERN = re.compile(r"^\+\d+ Laps?$")

# ---------------------------------------------------------------------------
# Ruled as finished: the car typically completed the distance and was stripped
# of the result afterwards. Flagged in the `disqualified` column. Caveat kept
# visible on purpose: 8 of the 36 such rows covered <90% distance (one, 0 laps),
# so the ruling slightly stretches "survived the race" for a few black-flag or
# post-race cases - the flag exists so this can be sensitivity-checked.
# ---------------------------------------------------------------------------
DISQUALIFIED = {
    "Disqualified",
    "Excluded",
}

# ---------------------------------------------------------------------------
# Statuses that mean the car never took the start. Combined with a zero-laps
# guard in apply_labels() before setting started=False.
# ---------------------------------------------------------------------------
NEVER_STARTED = {
    "Did not start",
    "Withdrew",
    "Not restarted",
}

# ---------------------------------------------------------------------------
# DNF, category "accident": crash, spin, or contact between cars.
# Ergast convention: "Accident" = solo crash, "Collision" = contact.
# ---------------------------------------------------------------------------
ACCIDENT = {
    "Accident",
    "Collision",
    "Collision damage",  # retired later from damage sustained in contact
    "Spun off",
    "Damage",
    "Broken wing",
    "Debris",
}

# ---------------------------------------------------------------------------
# DNF, category "mechanical": the car or its equipment failed.
# ---------------------------------------------------------------------------
MECHANICAL = {
    # engine / power unit
    "Engine", "Engine fire", "Engine misfire", "Power Unit", "Power loss",
    "Turbo", "ERS", "Battery", "Alternator", "Ignition", "Spark plugs",
    "Crankshaft", "Exhaust", "Fire", "Overheating", "Radiator",
    "Cooling system", "Water leak", "Water pressure", "Water pump",
    "Oil leak", "Oil line", "Oil pressure", "Heat shield fire",
    # transmission / drivetrain
    "Gearbox", "Transmission", "Clutch", "Drivetrain", "Driveshaft",
    "Halfshaft", "Differential", "Launch control", "Stalled",
    # hydraulics / brakes / steering / suspension
    "Hydraulics", "Pneumatics", "Brakes", "Brake duct", "Steering",
    "Suspension", "Track rod", "Throttle", "Electrical", "Electronics",
    "Vibrations", "Handling",
    # wheels / tyres
    "Wheel", "Wheel nut", "Wheel rim", "Tyre", "Puncture", "Tyre puncture",
    # fuel and refuelling
    "Fuel", "Fuel leak", "Fuel pressure", "Fuel pump", "Fuel system",
    "Fuel rig", "Refuelling", "Out of fuel",
    # bodywork and structure
    "Front wing", "Rear wing", "Undertray", "Chassis", "Driver Seat", "Seat",
    # generic mechanical
    "Mechanical", "Technical",
}

# ---------------------------------------------------------------------------
# DNF, category "other": not a mid-race crash or breakdown.
# ---------------------------------------------------------------------------
OTHER = {
    "Retired",         # generic, no cause recorded (166 rows, mostly older seasons)
    "Withdrew",
    "Did not start",
    "Not restarted",
    "Not classified",
    "Injured",
    "Injury",
    "Illness",
    "Safety",
    "Safety concerns",  # e.g. the 2005 US GP Michelin tyre withdrawal
}

# ---------------------------------------------------------------------------
# Judgment calls. These ARE classified above; this records why they are
# debatable and marks them per-row so their impact can be measured.
# ---------------------------------------------------------------------------
UNSURE = {
    "Retired": "cause unknown - could be mechanical or crash; parked in 'other'",
    "Not classified": "reason unrecorded; parked in 'other'",
    "Broken wing": "wing damage often comes from contact, but wings also fail on their own",
    "Debris": "usually damage from hitting someone else's debris - external cause",
    "Damage": "damage of unrecorded origin - assumed contact/crash",
    "Puncture": "can be a tyre failure or caused by debris/contact",
    "Tyre puncture": "same ambiguity as Puncture",
    "Front wing": "could be a failure or unrecorded contact",
    "Rear wing": "could be a failure or unrecorded contact",
    "Out of fuel": "a team/strategy error, not a part breaking; kept in 'mechanical'",
    "Fuel rig": "refuelling equipment failure - pit issue, not the car itself",
    "Refuelling": "same as Fuel rig",
    "Stalled": "can be a clutch failure or a driver error",
    "Handling": "vague - car undrivable for an unrecorded reason",
    "Fire": "fires usually start mechanically, but the root cause is unrecorded",
    "Technical": "generic catch-all, assumed mechanical",
    "Power loss": "assumed engine-related, cause unrecorded",
}


def classify_status(row) -> tuple[bool, str | None]:
    """Return (dnf, dnf_category) for one result row.

    Takes the whole row (any mapping with "status" and "position_text") so the
    official classification can outrank the status string. Raises KeyError for
    a status not covered by the policy above, so new statuses in future data
    are caught instead of silently mislabeled.
    """
    status = row["status"]
    if status in ACCIDENT:
        return True, "accident"
    if status in MECHANICAL:
        return True, "mechanical"
    if status in OTHER:
        return True, "other"
    if status in DISQUALIFIED or status in FINISHED or LAPS_DOWN_PATTERN.match(status):
        # Guard: positionText "R" means the source classified the car as
        # retired, whatever the status string says. These rows carry a lap gap
        # instead of a cause (e.g. Karthikeyan, Malaysia 2011: 14 of 56 laps,
        # status "+42 Laps"), so the cause is genuinely unknown - not guessed.
        if row["position_text"] == "R":
            return True, "unknown"
        return False, None
    raise KeyError(f"Status {status!r} is not covered by the labeling policy in src/labels.py")


def apply_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of a results table with all label columns added.

    Requires `status`, `position_text`, and `laps` columns. All input columns
    (including the audit columns `status` and `position_text`) are carried
    through. validate_labels() runs on every call, so labels can never be
    rebuilt without the consistency checks.
    """
    out = df.copy()
    labels = [classify_status(row) for row in out[["status", "position_text"]].to_dict("records")]
    out["dnf"] = [dnf for dnf, _ in labels]
    out["dnf_category"] = [cat for _, cat in labels]
    out["label_unsure"] = out["status"].isin(UNSURE)
    # Never-started statuses with the zero-laps guard (see module docstring).
    out["started"] = ~(out["status"].isin(NEVER_STARTED) & out["laps"].eq(0))
    out["disqualified"] = out["status"].isin(DISQUALIFIED)
    validate_labels(out)
    return out


def validate_labels(df: pd.DataFrame) -> None:
    """Cross-check the labels against the official classification.

    Raises AssertionError (fails loudly, never warns) if the labeling policy
    contradicts itself or the source data.
    """
    problems = []

    r_but_finished = df[(df["position_text"] == "R") & ~df["dnf"]]
    if len(r_but_finished):
        problems.append(
            f"{len(r_but_finished)} rows have position_text 'R' (retired) but are "
            f"labeled finished, e.g.:\n{r_but_finished[['season', 'round', 'driver_id', 'status']].head().to_string()}"
        )

    finished_with_cause = df[~df["dnf"] & df["dnf_category"].notna()]
    if len(finished_with_cause):
        problems.append(
            f"{len(finished_with_cause)} finished rows carry a dnf_category"
        )

    dnf_without_cause = df[df["dnf"] & df["dnf_category"].isna()]
    if len(dnf_without_cause):
        problems.append(
            f"{len(dnf_without_cause)} DNF rows have no dnf_category"
        )

    never_started_with_laps = df[~df["started"] & df["laps"].gt(0)]
    if len(never_started_with_laps):
        problems.append(
            f"{len(never_started_with_laps)} rows are marked started=False but completed laps"
        )

    if problems:
        raise AssertionError(
            "Label validation failed:\n- " + "\n- ".join(problems)
        )


def main():
    """Rebuild the labeled table, run the validation, print the breakdown."""
    from src.config import PROCESSED_DIR, RESULTS_LABELED_PARQUET, RESULTS_PARQUET

    df = apply_labels(pd.read_parquet(RESULTS_PARQUET))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(RESULTS_LABELED_PARQUET, index=False)
    print(f"{len(df):,} rows labeled and validated -> {RESULTS_LABELED_PARQUET}\n")
    print("dnf:")
    print(df["dnf"].value_counts().to_string())
    print("\ndnf_category:")
    print(df["dnf_category"].value_counts(dropna=False).to_string())
    print(f"\nstarted=False (never raced, excluded from features): {(~df['started']).sum()}")
    print(f"disqualified (labeled finished, flagged): {df['disqualified'].sum()}")
    print(f"rows with an 'unsure' status: {df['label_unsure'].sum():,} "
          f"({df['label_unsure'].mean() * 100:.1f}%)")


if __name__ == "__main__":
    main()
