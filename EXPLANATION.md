# Step 1 explained: the data foundation

This document walks through everything built in step 1, in plain language. Read it
top to bottom; by the end you should understand exactly what data we have, how it
got here, and what you need to decide before step 2 (feature engineering).

**The headline:** we now have one clean table with **10,071 rows** — one row for
every driver in every Formula 1 race from 2000 through 2024 (483 races) — including
how each driver's race ended. It lives at `data/processed/results.parquet`, and
`reports/data_quality.md` describes its quality in detail.

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
| `data/processed/features.parquet` | One row per driver-race: features + labels |
| `notebooks/01_exploration.ipynb` | The charts, with commentary (run top to bottom) |
| `reports/figures/*.png` | The same four charts as standalone images |

## 1. How the labels were defined and why

Each row gets two labels (a *label* is the answer we'll ask a model to predict):

- **`dnf`** (did not finish): true/false, decided purely from the `status` string.
  `Finished`, `+N Laps`, and `Lapped` count as finishing; all 86 other statuses
  count as DNF. One deliberate choice: a driver who broke down near the end and
  was still officially *classified* (say 90% distance completed) counts as a DNF
  here, because the car did not make the flag — the project is about whether the
  car survives the race, not about the FIA's classification rules.
- **`dnf_category`**: for DNF rows, one of **accident** (crash, spin, or contact),
  **mechanical** (the car or its equipment broke), or **other** (everything that
  isn't a mid-race breakdown: disqualification, withdrew before the start,
  illness, and the generic `Retired` with no recorded cause).

The whole policy lives in one file, `src/labels.py`, as three plain sets of
status strings you can read and edit. Seventeen statuses were judgment calls;
each is listed in an `UNSURE` dict with a one-line reason (e.g. `Puncture`: tyre
failure or debris damage? `Out of fuel`: the car "broke" or the team blundered?).
Rows with those statuses are flagged in a `label_unsure` column — 234 rows, 2.3% —
so you can later measure whether the debatable calls matter. If a future dataset
contains a status the policy doesn't know, the code raises an error instead of
guessing.

**The result:** 7,750 finished vs 2,321 DNF (23% overall). DNFs split into 1,253
mechanical, 818 accident, 250 other.

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
4. **The "other" DNFs and unsure labels.** Disqualifications, withdrawals,
   pre-2023 generic `Retired` rows (~250 rows, plus 234 unsure-flagged): exclude
   from training, fold into DNF, or leave out of the positive class? These aren't
   the kind of "didn't finish" you're trying to predict, so I'd exclude `other`
   rows from the cause model and count them as DNF in the binary one — but it's
   your call.
5. **Evaluation design.** Time-based split is a given (train on the past, test on
   the future — random splits leak). Decide the boundary (e.g. train ≤2018 /
   validate 2019–21 / test 2022–24) and the metric that matters: with 23% DNFs
   (and ~11% in recent seasons), plain accuracy is misleading — a model saying
   "everyone finishes" scores ~89% in 2024. Look at precision/recall or
   calibration instead (happy to explain these when we get there).

---

*Everything here was generated by the code in `src/` — nothing was hand-edited.
To reproduce from scratch: delete `data/` contents, then run
`python -m src.build_dataset`, `python -m src.quality_report`,
`python -m src.build_features`, and execute `notebooks/01_exploration.ipynb`.*
