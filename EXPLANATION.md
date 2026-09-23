# Step 1 explained: the data foundation

This document walks through everything built in step 1, in plain language. Read it
top to bottom; by the end you should understand exactly what data we have, how it
got here, and what you need to decide before step 2 (feature engineering).

**The headline:** we now have one clean table with **10,858 rows** — one row for
every driver in every Formula 1 race from 2000 through the season in progress
(2026, through round 14) — including how each driver's race ended. It lives at
`data/processed/results.parquet`, and `reports/data_quality.md` describes its
quality in detail. (Step 1 originally covered 2000–2024; the extension to
2025–26 is documented in the "Coverage extension" section near the end.)

---

## 1. The folder layout and why

```
├── src/                  # All reusable Python code, as a package
├── data/
│   ├── raw/              # Exact copies of API responses (NOT in git)
│   └── processed/        # The clean table we actually work with (in git)
├── notebooks/            # For future exploration notebooks (empty)
├── reports/              # Generated reports, e.g. data quality
├── requirements.txt      # The Python libraries the project needs
└── README.md             # How to run everything
```

The key idea is the **raw vs processed split**, a standard data-engineering habit:

- **`data/raw/`** holds the API responses byte-for-byte as the server sent them,
  one JSON file per page. Raw data is our source of truth: if we later discover a
  bug in how we flattened the data, we can rebuild the clean table without
  re-downloading anything. It is *excluded from git* (see `.gitignore`) because
  it is bulky, and anyone can regenerate it by running the loader.
- **`data/processed/`** holds the clean, analysis-ready table. It *is* committed
  to git because it is small (~90 KB) and it is convenient for both of us to have
  the dataset available without re-running the fetch.

`src/` is a Python *package* (a folder of modules you can import), so code is run
as `python -m src.build_dataset` from the repository root. That keeps imports
consistent and avoids the classic "works in the notebook, breaks in the script"
path problems.

---

## 2. How the loader works

Code: `src/config.py` (settings), `src/jolpica.py` (the API client),
`src/build_dataset.py` (builds the table).

### The data source

We use the **Jolpica-F1 API** (`api.jolpi.ca`), the community-run successor to
the retired Ergast API. It serves historical F1 data as JSON over plain HTTPS —
no account or API key needed. An *API* (application programming interface) here
just means: a website designed for programs instead of people; you request a URL
and get structured data back instead of a web page.

### Fetching: one season at a time, in pages

The endpoint `/{season}/results.json` returns every driver-race result for a whole
season. A season has 320–480 result rows, but the API returns at most **100 rows
per request** — so we *paginate*: request rows 0–99, then 100–199, and so on
(`offset` is where to start, `limit` how many to return) until we have the total
the API reports. That is 4–5 requests per season, ~112 requests for all 25 seasons —
far fewer than one request per race (483).

Because a race's rows can be split across a page boundary, the client stitches
pages back together by round number, and then **verifies the row count** against
the API's reported total, so a silently missing page would crash loudly instead
of producing an incomplete dataset.

### Politeness and the rate limit we actually hit

The loader sleeps 0.6 seconds between requests. Even so, the first full run was
**rate-limited**: after ~100 requests the server answered `429 Too Many Requests`
(HTTP-speak for "slow down"). The client now reads the server's `Retry-After`
header (the server saying "try again in N seconds"), waits, and retries up to six
times. The second run completed cleanly. Lesson learned: Jolpica's practical
sustained limit is tighter than its documentation suggests, and the retry logic
is what makes the loader reliable.

### Caching: re-runs never touch the network

Every successful response is saved to `data/raw/` (e.g.
`results_2013_offset0200.json`) *before* being used. On any later run, the loader
sees the file on disk and reads it instead of calling the API. So re-running
`python -m src.build_dataset` is instant, works offline, and can never be
rate-limited. To force a re-download of one season (say, if a result gets
corrected), delete that season's files from `data/raw/`.

### What each field (column) means

One row = one driver's outcome in one race.

| Column | Meaning |
|---|---|
| `season` | Year of the championship (2000–2024). |
| `round` | Race number within the season (1 = season opener). `season` + `round` uniquely identify a race. |
| `race_name` | Human-readable race name, e.g. "Monaco Grand Prix". |
| `race_date` | Calendar date of the race. |
| `circuit_id` / `circuit_name` | Stable machine ID (e.g. `monza`) and display name of the track. Use the ID for joins/grouping — names can vary. |
| `driver_id` | Stable machine ID for the driver (e.g. `michael_schumacher`). The best key for tracking a driver across years. |
| `driver_code` | Three-letter TV abbreviation (HAM, VER). **Missing for 610 rows** — mostly drivers who left F1 before codes were introduced (~2003). Use `driver_id` instead for logic. |
| `driver_name` | Full name, for readability. |
| `constructor_id` / `constructor_name` | The team (chassis builder), e.g. `ferrari` / "Ferrari". |
| `grid` | Starting position. **0 means started from the pit lane**, not a data error. |
| `position` | Official classification order, 1..N. Note: *retired drivers still get a number* — they are ranked after the finishers by how far they got. So `position` alone cannot tell you who finished. |
| `position_text` | The classification as text: a number for classified finishers, `"R"` retired, `"D"` disqualified, `"W"` withdrew, `"N"` not classified. This is the reliable way to distinguish finish vs non-finish. |
| `laps` | Laps completed. 0 means the driver never completed a racing lap (first-corner crash, formation-lap failure, or withdrawal). |
| `status` | **The column this project revolves around.** Free-text reason for the outcome: `Finished`, `+1 Lap` (finished, one lap behind the winner), `Accident`, `Collision`, `Engine`, `Gearbox`, … There are **104 distinct values** in our data; the full list with counts is in `reports/data_quality.md`. |

I captured `position_text` and `race_date` beyond your requested list because they
cost nothing now and are exactly what step 2 needs (reliable retirement labels and
time ordering). Nothing else was added.

---

## 3. Grouping the status values (preview of the labeling decision)

The 104 raw statuses collapse naturally into a hierarchy. **This grouping is NOT
applied to the data** — the table keeps the raw strings so no information is lost.
This is the map for when *you* decide the target variable in step 2:

- **Finished** (~74% of rows): `Finished`, plus all the `+N Laps` variants
  (crossed the line, N laps behind the winner — still a finish) and `Lapped`.
- **Retired — driver-involved / crash** (~8%): `Accident`, `Collision`,
  `Collision damage`, `Spun off`, `Broken wing`(?), `Damage`, `Debris`(?).
- **Retired — mechanical** (~13%): `Engine`, `Gearbox`, `Hydraulics`, `Brakes`,
  `Suspension`, `Electrical`, `Power Unit`, `Transmission`, `Clutch`, `Puncture`,
  `Wheel`, `Overheating`, … (dozens of small categories — every broken part gets
  its own label).
- **Ambiguous retirements**: `Retired` (166 rows — generic, cause unknown),
  `Mechanical`, `Technical`, `Power loss`, `Out of fuel`, `Stalled`, `Handling`.
- **Not really "retired mid-race"** (worth separating or excluding):
  `Disqualified`/`Excluded` (rule violations, often after finishing!),
  `Withdrew`/`Did not start`/`Not restarted` (never raced — includes the freak
  2005 US Grand Prix where 14 cars pulled out over tyre safety),
  `Injured`/`Injury`/`Illness`, `Safety`/`Safety concerns`.

Two subtleties to keep in mind:

1. **`Accident` vs `Collision`:** in Ergast convention, `Accident` = a solo crash,
   `Collision` = contact between cars. Both are "crashes", but they may deserve
   separate treatment (a collision involves someone else's mistake).
2. **A crashed driver can still be classified.** A driver who retires after
   completing 90% of the race distance is officially classified: their
   `position_text` becomes a number even though their `status` still says
   `Accident` or `Engine`. So `status`, `position_text`, and `laps` together give
   the full picture; any single one alone can mislead.

---

## 4. Assumptions I made

1. **Jolpica's data equals Ergast's historical record and is trustworthy** for
   2000–2024. Spot checks passed (2000 Australia winner, 2021 Abu Dhabi winner,
   2005 US GP mass withdrawal, 2020's 17-race COVID calendar).
2. **Race results only** — no qualifying, sprint races, pit stops, or weather.
   Sprint results have their own endpoint and are *not* included in these rows;
   only the Sunday Grand Prix outcome is.
3. **One row per driver per race is the right unit** — verified: no duplicates.
   (Shared drives, where two drivers used one car, ended in the 1960s.)
4. **Committing the processed Parquet to git is acceptable** because it's ~90 KB.
   For larger data you'd keep git for code only.
5. **2024 is complete** (24 races, season over). The loader's cache means the
   repo won't silently drift if Jolpica corrects a result — a deliberate freeze.

## 5. What I was unsure about

- **The generic `Retired` status (166 rows).** The API doesn't say whether these
  were mechanical or driver-related. They cluster in older seasons. How to label
  them is a genuine judgment call I left for you (decision 2 below).
- **The exact rate limit.** Documentation suggests 500 requests/hour
  unauthenticated, but we were throttled around ~100 requests in a few minutes.
  The retry logic handles it, but first-time full fetches will be slow-ish.
- **`Lapped` vs `+N Laps` (208 rows).** `Lapped` appears to be an older/alternate
  encoding of "finished but behind". I'd group it with finishers, but haven't
  found authoritative documentation.
- **The 2024 Australian GP has 19 rows instead of 20** — real (a Williams driver
  withdrew after his crashed teammate was given his car), not a fetch error. You
  can see it in the quality report's per-season table: 2024 has 479 rows, not 480.

## 6. Where FastF1 fits later (not used yet, per your instruction)

**FastF1** is a Python library that downloads official F1 timing data: lap-by-lap
times, tyre compounds and stint lengths, weather, telemetry (speed/throttle/brake
traces), and session results — but reliably only from **2018 onward**. It slots
into step 2+ as the source of *rich* features (was it raining? how old were the
tyres? was the driver pushing?) layered on top of this table's *labels and
skeleton*. The likely design: this Jolpica table remains the master list of
driver-races and outcomes for 2000–2024, and FastF1 features join onto it for the
recent seasons where they exist. That creates a coverage trade-off — see decision 5.

## 7. Decisions to make before step 2

1. **What exactly are we predicting?** Binary "retired vs finished"? Or the more
   interesting "crash (Accident/Collision) vs mechanical vs finished" multi-class?
   This drives everything downstream. My suggestion: start binary, keep the
   crash/mechanical split as a stretch goal.
2. **How do we treat the ambiguous and non-race statuses?** Generic `Retired`:
   its own class, merged into mechanical, or dropped? `Disqualified`, `Withdrew`,
   `Did not start`, `Injured`: these aren't mid-race retirements — exclude the
   rows, or keep them as finisher/non-finisher edge cases? (~1% of rows.)
3. **Prediction moment: what information is "known" at prediction time?** If we
   predict *before the race*, we can only use grid position, history, track, team —
   not laps completed. Decide this now, because it determines which features are
   legal and whether FastF1's in-race data is even usable.
4. **How do we split train/test?** Random splits leak the future into training
   (the model would "know" 2019 while predicting 2015). Time-based splits (e.g.
   train ≤2018, test 2019+) are the honest choice for this kind of data. Related:
   is the 2000-era of frequent engine failures even representative of modern F1,
   or should older seasons be down-weighted/dropped?
5. **Scope of FastF1 enrichment.** All 25 seasons with sparse features, or
   2018–2024 with rich features (weather, tyres, safety cars)? Roughly 10,000
   simple rows vs ~3,000 rich ones. This is a real modeling trade-off worth
   deciding deliberately.

---

# Step 2 explained: labels, features, and first look at the data

Step 2 turned the raw results into something a model can learn from: **labels**
(the thing to predict) and **features** (the information to predict it from),
plus an exploration notebook. Still no models — that's step 3.

New pieces:

| File | What it is |
|---|---|
| `src/labels.py` | The labeling policy — the file to review and edit |
| `src/build_features.py` | Builds the pre-race feature table |
| `data/processed/results_labeled.parquet` | All 10,071 rows with labels — the audit trail |
| `data/processed/features.parquet` | Modeling table: features + labels, never-started rows excluded |
| `notebooks/01_exploration.ipynb` | The charts, with commentary (run top to bottom) |
| `reports/figures/*.png` | The same four charts as standalone images |

> **Note:** the labeling policy was revised after review — see
> [Step 2 revision](#step-2-revision-labeling-fixes-after-review) below. The
> section that follows describes the *current* (revised) policy.

## 1. How the labels were defined and why

Each row gets two labels (a *label* is the answer we'll ask a model to predict):

- **`dnf`** (did not finish): true/false, decided from the `status` string plus
  `position_text` (the official classification, which outranks the status — see
  the revision below). `Finished`, `+N Laps`, and `Lapped` count as finishing,
  and so do disqualifications (a ruling explained in the revision); everything
  else counts as DNF. One deliberate choice: a driver who broke down near the
  end and was still officially *classified* (say 90% distance completed) counts
  as a DNF here, because the car did not make the flag — the project is about
  whether the car survives the race, not about the FIA's classification rules.
- **`dnf_category`**: for DNF rows, one of **accident** (crash, spin, or contact),
  **mechanical** (the car or its equipment broke), **unknown** (retired per the
  classification but no cause on record), or **other** (withdrawals, illness,
  safety, and the generic `Retired`).
- **`started`** / **`disqualified`**: audit booleans added in the revision —
  cars that never took the start, and cars stripped of a result they achieved.

The whole policy lives in one file, `src/labels.py`, as three plain sets of
status strings you can read and edit. Seventeen statuses were judgment calls;
each is listed in an `UNSURE` dict with a one-line reason (e.g. `Puncture`: tyre
failure or debris damage? `Out of fuel`: the car "broke" or the team blundered?).
Rows with those statuses are flagged in a `label_unsure` column — 234 rows, 2.3% —
so you can later measure whether the debatable calls matter. If a future dataset
contains a status the policy doesn't know, the code raises an error instead of
guessing.

**The result (after the revision below):** in the full labeled table, 7,771
finished vs 2,300 DNF; in the modeling table (never-started rows removed),
10,039 rows with 2,268 DNFs (22.6%), split into 1,253 mechanical, 818 accident,
15 unknown, 182 other.

**⚠ The biggest discovery of step 2:** from **2023 onward the data source stops
recording DNF causes** — almost every retirement is just `Retired` (53 of 61
non-finishes in 2023, 49 of 54 in 2024), while 2022 and earlier have detailed
causes. I found this when the accident-vs-mechanical chart dropped to zero for
2023–24 and confirmed it in the raw responses; the quality report now checks for
it. Consequences: the binary DNF label is fine for all 25 seasons, but the
accident/mechanical split only exists **through 2022** unless we backfill causes
from another source. This reshapes decision 1 below.

## 2. Data leakage, and how the features avoid it

*Data leakage* means letting the model see information that would not exist at
the moment of prediction — like computing a driver's career DNF rate *including
the race you're predicting*. A leaky model looks brilliant in testing and is
useless in reality, because at prediction time the future isn't available.

Guards used here:

- Races are ordered by (season, round), and every historical rate for a race is
  computed **only from races strictly earlier** in that order. The current race's
  outcome never feeds its own row. This is enforced in code (running totals are
  shifted by one race) and tested: season 2000 round 1 must have *no* history at
  all, and spot-checks recompute several values independently (e.g. Monza 2005's
  circuit rate must equal the pooled 2000–2004 Monza rate — it does).
- The spot-checks caught a real bug in the first version: circuit totals were
  shifted along the *global* race calendar instead of within each circuit, so a
  race inherited numbers from a different track. Worth remembering: leakage bugs
  are quiet, tests are how you catch them.
- Only pre-race information is included as features. Nothing from the race itself
  (laps, finishing position, status) appears anywhere except the label columns.

## 3. The features and why each might matter

One row per driver-race, everything knowable before lights out:

| Feature | What it is | Why it might matter |
|---|---|---|
| `season` | The year | Reliability improved enormously over 25 years; the era defines the baseline risk |
| `round` | Race number in the season | Early-season races may show teething problems; late-season, worn components or title desperation |
| `race_date` | Calendar date | Not a model input per se; needed for honest time-based train/test splits |
| `circuit_id` | The track | Street circuits and chaotic venues genuinely differ in risk |
| `driver_id` | The driver | Some drivers crash more, independent of machinery |
| `constructor_id` | The team | The single biggest factor in mechanical reliability |
| `grid` | Starting slot (0 = pit lane) | Back of the grid = slower, less reliable cars in mid-pack lap-1 traffic |
| `driver_prior_starts` | Driver's earlier races (since 2000) | Experience; also a rookie flag (0 = debut) |
| `driver_prior_dnf_rate` | Share of those races the driver didn't finish | The driver's own risk history |
| `constructor_prev_season_dnf_rate` | Team's DNF rate over the whole previous season | Last year's reliability predicts this year's, imperfectly |
| `circuit_hist_dnf_rate` | DNF rate of all earlier races at this track | The track's inherent attrition level |

Missing values are left as gaps (NaN) rather than filled in: a debutant has no
prior DNF rate (126 rows), a brand-new circuit has no history (810 rows), a
constructor's first season has no previous season (1,495 rows — inflated because
renamed teams get new IDs, see decision 3). How to handle the gaps is a modeling
choice, so it is *not* baked into the data.

Known limitation: history starts at 2000, our window's edge. Michael Schumacher's
1990s races are invisible, so his "prior starts" in 2000 is 0 — early-window
history features under-count established careers.

## 4. What the charts show

(Notebook: `notebooks/01_exploration.ipynb`; images: `reports/figures/`.)

1. **DNF rate by season** — falls from ~40–44% (2000–2002) to ~11% (2024), in an
   almost steady slide. Modern F1 is a different sport reliability-wise; any model
   that ignores the era will be badly calibrated.
2. **DNF rate by circuit** — a wide spread, from ~12% (Valencia) to ~45%
   (Indianapolis — inflated by the farcical 2005 six-car race; 8 races total).
   Melbourne, Monaco, and Montreal sit high; purpose-built modern tracks low. One
   caveat: circuits used only in the high-attrition early 2000s look worse than
   they were — circuit and era are tangled together.
3. **DNF rate by grid position** — rises almost monotonically from ~11% (pole)
   to ~32% (grid 22), with pit-lane starters at 40%. Grid encodes car quality,
   reliability, and lap-1 traffic risk all at once — strong feature, murky causality.
4. **DNF causes over time** — mechanical failures collapse (31% of entries in
   2002 to well under 10% recently) while accidents decline much more gently
   (~15% → ~7%), so *the causes of modern DNFs are mostly accidents, not
   breakdowns*. The chart also displays the 2023+ recording break honestly: the
   detailed lines end and a "cause not recorded" line takes over.

## Step 2 revision: labeling fixes after review

After reviewing how the label treats edge cases, four changes were made to the
policy. The numbers above already reflect them.

### The classification now outranks the status string

A cross-check of the label against `position_text` (the source's official
classification: a number for classified cars, `R` retired, `D` disqualified,
`W` withdrew) found 15 rows the old status-only rule got wrong. The source
sometimes puts a **lap gap in the status field for a car that actually
stopped**: Narain Karthikeyan, Malaysia 2011, completed 14 of 56 laps and is
recorded as `positionText="R", status="+42 Laps"`; Mark Webber, Brazil 2005,
did 45 of 71 laps with `status="+26 Laps"`. The old rule read only `status` and
called these finishes. `classify_status` now takes the whole row, and a guard
says: **`position_text == "R"` is a retirement no matter what the status
says.** (Verified against the raw cached API responses — the quirk is in the
source, not our loader.)

### New cause value: "unknown"

Those 15 rows have no recorded cause — their status field holds a lap gap, not
a reason. They get a new category, **unknown**, rather than a guessed cause and
rather than being folded into "other" (which would blur genuine retirements
together with rows that never raced).

### Cars that never started are excluded from modeling

A new boolean **`started`** is False for rows whose status is `Did not start`,
`Withdrew`, or `Not restarted` **and** whose lap count is zero — 32 rows. They
stay in the labeled table (`results_labeled.parquet`) so the audit trail is
intact, but `build_features` drops them *before computing anything*, so they are
neither modeling rows nor part of any prior-rate denominator. Nothing on track
caused those outcomes.

**The laps guard is a deliberate deviation worth knowing about.** Four
`Withdrew` rows are *not* pre-race withdrawals: Button (Malaysia 2013, 53/56
laps), Norris (Mexico 2019, 48/71), Magnussen (Turkey 2020, 55/58), and Alonso
(Mexico 2023, 47/71) all retired during the race, and the source simply coded
the retirement as `Withdrew`. Marking them "never started" would be wrong (and
the validation test below caught exactly this). They keep `started=True` and
count as ordinary DNFs. A related loose end, left alone on purpose: ~25 rows
have `position_text="W"` with a mechanical status and zero laps (cars that
broke *before* the start, e.g. an engine failure on the way to the grid). The
status rule doesn't catch them, so they currently stay in the modeling data as
mechanical DNFs — flagging them is a decision for you (see decision 4 below).

### Disqualifications are now finishes

`Disqualified` (35 rows) and `Excluded` (1) changed from DNF to **finished**:
these cars typically ran the full distance and lost the result afterwards at a
stewards' table — the car survived the race, which is the question this project
asks. They stay in the modeling data, flagged in a boolean **`disqualified`**
column for later sensitivity checks (a *sensitivity check* = rerun the analysis
with the rows treated the other way and see if conclusions change). One honest
caveat that flag exists to cover: 8 of the 36 were disqualified having covered
less than 90% of the distance (one with 0 laps), so for a few black-flag cases
"finished" is a stretch.

### Automatic validation on every rebuild

`validate_labels()` in `src/labels.py` now runs inside `apply_labels()`, so no
rebuild can skip it. It fails with an error (never a warning) if: any
`position_text == "R"` row is labeled finished; any finished row carries a
cause; any DNF row lacks a cause; or any `started=False` row completed laps.
Audit columns `status` and `position_text` are carried through both the labeled
table and the feature table so every decision can be re-checked without going
back to the raw cache.

## Coverage extension: 2025 and 2026

The dataset now runs through the season in progress. What was checked and found:

### Sources

Ergast retired at the end of 2024; **Jolpica-F1 carries on and serves both 2025
and 2026** with a schema byte-for-byte identical to the 2000–2024 data (verified
key-by-key before loading — race, result, driver, and constructor objects all
match). **FastF1 also covers the current season**: its 2026 schedule, race
results (including grid), and qualifying all load. So: Jolpica remains the
single source for this table across all 27 seasons; FastF1 stays reserved for
later enrichment. One operational caveat: the loader caches by season, so the
in-progress 2026 cache freezes at the moment it was fetched — delete
`data/raw/results_2026_*.json` after new races to pick them up (noted in
`src/config.py`).

Pulled: the full 2025 season (24 rounds, 479 rows) and 2026 rounds 1–14, the
last completed being the **Spanish Grand Prix on 13 September 2026** (22 cars
per round, 308 rows). The 2026 calendar shows its disruption in the source:
23 rounds scheduled, two Spanish-named races (round 7 "Barcelona Grand Prix",
round 14 "Spanish Grand Prix"), and a round 16 titled "Bahrain Grand Prix in
Malaysia" (4 October). Nothing was hardcoded about round counts — the loader
takes what the source reports.

**Qualifying and grid for live prediction:** every completed 2026 round has
qualifying results and grid positions in Jolpica (grid present for all 308
rows), and FastF1 serves the same from the official timing feed. Jolpica is
community-run and documents no update deadline; in practice race-weekend data
appears within hours, but if a live pipeline ever finds Jolpica lagging on a
Saturday night, FastF1 (which reads the official live-timing source) is the
faster path to the grid.

### The labeling policy on the new seasons (verified, not changed)

- **No new status strings and no new position_text values** appear in 2025–26
  that weren't already in 2000–2024. Zero rows are unclassifiable; the
  validator passes on the full 10,858-row dataset.
- The cause-recording break continues: 2025's non-finishes are 51 generic
  `Retired` + 6 `Disqualified` + 3 `Did not start`; 2026's are 57 `Retired` +
  7 `Did not start`. The quality report now flags 2023–2026.
- The position_text guard earned its keep on new data too: **2 rows in 2026**
  carry a lap-gap status but classification "R" and were caught as `unknown`.

### New and renamed constructors (reported, not fixed)

The source uses **`cadillac`** (new team) and **`audi`** — and `audi` is a
**separate identifier from `sauber`**, which ran through 2025. So Audi's
Sauber lineage is invisible to the feature build, exactly like earlier renames.
For both teams, `constructor_prev_season_dnf_rate` in 2026 comes out as a
**missing value (NaN)** — not a zero and not an error. Whether to hand-curate
a lineage map (which would give Audi its Sauber history, but leave Cadillac
genuinely blank) is still decision 3 above.

### The generic `Retired` pile-up (reported, not moved)

Where 2023+ `Retired` rows land today: category **"other"**, flagged
`label_unsure` — 53 (2023), 49 (2024), 51 (2025), 57 (2026 so far) = **210
rows**, against only 64 pre-2023. **Recommendation: move status `Retired` to
the "unknown" category.** "Unknown" was defined as "retired per the
classification, but no cause on record" — which is literally what these rows
are; the 15 lap-gap rows already there are the same thing in different
clothes. That would leave "other" holding only genuine oddities (withdrawals,
injury, safety, not-classified) and make the category names honest. Not
applied — the labeling policy is yours to change.

### New columns (data collection only)

- **`power_unit`** — each constructor's engine supplier, per season,
  hand-curated in `src/reference.py` (season-ranged, since suppliers are
  shared and change over time: e.g. McLaren ran Mercedes → Honda → Renault →
  Mercedes across 2000–2026). Sponsor badges are collapsed to the real maker
  (TAG Heuer→Renault, Petronas→Ferrari, Acer→Ferrari, Playlife→Supertec,
  European→Ford), with each collapse and every lower-confidence entry recorded
  in `PU_NOTES` in that file. "Honda RBPT" (2022–25) and "Red Bull Ford"
  (2026) are kept distinct from works Honda because they are separate shared
  programs. The 2026 lineup (Ferrari: Ferrari/Haas/Cadillac; Mercedes:
  Mercedes/McLaren/Williams/Alpine; Honda: Aston Martin; Audi: Audi; Red Bull
  Ford: both Red Bull teams) was verified against current season coverage.
  Every constructor-season in the data resolves — an assertion in
  `build_features` fails the build if a future one doesn't.
- **`reg_reset`** — True for seasons that opened a major technical regulation
  era: 2014, 2017, 2022, 2026 (as specified) plus two defensible additions,
  2006 (V10→V8) and 2009 (aero overhaul + KERS), flagged in
  `src/reference.py` so they're easy to remove. The 2026 uptick in DNF rate
  (~20% vs ~10% in 2024–25) fits the pattern of first-year resets like 2014
  and 2017 — evidence this column carries signal.

## 5. Decisions to make before step 3 (modeling)

1. **Target, given the recording break.** Binary DNF works for 2000–2024. For
   accident-vs-mechanical you must pick: (a) model it only through 2022, (b)
   backfill 2023–24 causes from another source (FastF1 session data, Wikipedia)
   — extra work, decide if it's worth it, or (c) drop the cause model. My
   suggestion: binary DNF on everything, cause model through 2022 as a second
   experiment.
2. **Era scope/weighting.** 2000-era cars DNF'd 3–4× more than today's, mostly
   mechanically. Options: use all seasons and let the model learn the trend, drop
   pre-2010 seasons, or weight recent seasons more. This interacts with how much
   training data the rarer accident class needs.
3. **Constructor lineage.** The data treats renamed teams (Jordan→Midland→Spyker
   →Force India→Racing Point→Aston Martin…) as unrelated, wiping their history at
   each rename and causing most of the 1,495 missing previous-season rates. Decide:
   hand-curate a lineage map (one afternoon, better features) or accept the gaps.
4. **The remaining "other" DNFs and edge rows.** *(Partly resolved by the step-2
   revision: disqualifications are now finishes, and never-started rows are out
   of the modeling data.)* Still open: the 182 remaining "other" DNFs (mostly
   the pre-2023 generic `Retired`, plus a few injury/safety rows) — exclude from
   the cause model, or keep as their own class? And the ~25 cars that broke
   before the start (`position_text="W"`, mechanical status, zero laps) — leave
   them as mechanical DNFs, or treat them like never-started rows? My lean:
   count all of them as DNF in the binary model, exclude "other"/"unknown" from
   the cause model, and decide the broke-before-start rows with a sensitivity
   check — but it's your call.
5. **Evaluation design.** Time-based split is a given (train on the past, test on
   the future — random splits leak). Decide the boundary (e.g. train ≤2018 /
   validate 2019–21 / test 2022–24) and the metric that matters: with 23% DNFs
   (and ~11% in recent seasons), plain accuracy is misleading — a model saying
   "everyone finishes" scores ~89% in 2024. Look at precision/recall or
   calibration instead (happy to explain these when we get there).

---

*Everything here was generated by the code in `src/` — nothing was hand-edited.
To reproduce from scratch: delete `data/` contents, then run
`python -m src.build_dataset`, `python -m src.quality_report`, `python -m
src.labels`, `python -m src.build_features`, and execute
`notebooks/01_exploration.ipynb`.*
