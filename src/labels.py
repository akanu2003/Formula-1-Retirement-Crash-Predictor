"""Map every race-result status to prediction labels.

This file IS the labeling policy. Edit the sets below to change how statuses
are classified; nothing else in the project hard-codes a status string.

Two labels are produced for each row:

    dnf           True if the driver did not finish the race, else False.
                  Judged from `status` alone: a driver who retired close enough
                  to the end to be officially classified (numeric position_text)
                  still counts as a DNF here, because the car did not make it
                  to the flag.
    dnf_category  For DNF rows only: "accident", "mechanical", or "other".
                  None for finishers.

Categories:
    accident    - the driver crashed, spun, or was involved in contact.
    mechanical  - the car (or its fuelling/equipment) broke.
    other       - everything that is not a mid-race breakdown or crash:
                  disqualification, withdrawal before the start, illness, the
                  generic "Retired" with no recorded cause, etc. These rows are
                  candidates for exclusion when modeling.

Statuses listed in UNSURE are judgment calls; each carries a one-line reason.
They are also flagged per-row (column `label_unsure`) so their impact can be
measured. Every status seen in the 2000-2024 data is covered; apply_labels()
raises on anything new so an updated dataset can never be silently mislabeled.
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
    "Disqualified",
    "Excluded",
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


def classify_status(status: str) -> tuple[bool, str | None]:
    """Return (dnf, dnf_category) for one status string.

    Raises KeyError for a status not covered by the policy above, so new
    statuses in future data are caught instead of silently mislabeled.
    """
    if status in FINISHED or LAPS_DOWN_PATTERN.match(status):
        return False, None
    if status in ACCIDENT:
        return True, "accident"
    if status in MECHANICAL:
        return True, "mechanical"
    if status in OTHER:
        return True, "other"
    raise KeyError(f"Status {status!r} is not covered by the labeling policy in src/labels.py")


def apply_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of a results table with dnf, dnf_category, label_unsure."""
    out = df.copy()
    labels = out["status"].map(lambda s: classify_status(s))
    out["dnf"] = labels.map(lambda t: t[0])
    out["dnf_category"] = labels.map(lambda t: t[1])
    out["label_unsure"] = out["status"].isin(UNSURE)
    return out


def main():
    """Quick self-check: label the full dataset and print the breakdown."""
    from src.config import RESULTS_PARQUET

    df = apply_labels(pd.read_parquet(RESULTS_PARQUET))
    print(f"{len(df):,} rows labeled, no unknown statuses.\n")
    print("dnf:")
    print(df["dnf"].value_counts().to_string())
    print("\ndnf_category:")
    print(df["dnf_category"].value_counts(dropna=False).to_string())
    print(f"\nrows with an 'unsure' status: {df['label_unsure'].sum():,} "
          f"({df['label_unsure'].mean() * 100:.1f}%)")


if __name__ == "__main__":
    main()
