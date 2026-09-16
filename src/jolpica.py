"""Minimal Jolpica-F1 API client with on-disk caching.

Jolpica (https://api.jolpi.ca) is the community successor to the Ergast API and
serves the same JSON schema. One endpoint is used here:

    GET {base}/{season}/results.json?limit=100&offset=N

which returns every driver-race result row for a whole season, paginated.
Fetching per-season (4-5 pages) instead of per-race (~20 requests) keeps the
request count low.

Every successful response is written to data/raw/ before being returned, and
subsequent calls read the cache instead of the network. Delete a season's
cache files to force a refresh (e.g. while a season is still in progress).
"""

import json
import logging
import time

import requests

from src.config import API_BASE_URL, PAGE_SIZE, RAW_DIR, REQUEST_DELAY_SECONDS

logger = logging.getLogger(__name__)

USER_AGENT = "f1-retirement-predictor (educational project)"

# How many times to retry a rate-limited (HTTP 429) request before giving up.
MAX_RETRIES = 6


def _cache_path(season: int, offset: int):
    return RAW_DIR / f"results_{season}_offset{offset:04d}.json"


def _get_with_retry(url: str, offset: int, session: requests.Session) -> requests.Response:
    """GET one page, backing off and retrying when the API says 429."""
    for attempt in range(MAX_RETRIES + 1):
        response = session.get(
            url,
            params={"limit": PAGE_SIZE, "offset": offset},
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        if response.status_code != 429 or attempt == MAX_RETRIES:
            response.raise_for_status()
            return response
        # Honor the server's Retry-After if given, else exponential backoff.
        retry_after = response.headers.get("Retry-After")
        wait = float(retry_after) if retry_after else min(4 * 2**attempt, 120)
        logger.warning("Rate limited (429); waiting %.0fs (attempt %d/%d)",
                       wait, attempt + 1, MAX_RETRIES)
        time.sleep(wait)
    raise AssertionError("unreachable")


def _fetch_page(season: int, offset: int, session: requests.Session) -> dict:
    """Return one page of season results, from cache if present."""
    path = _cache_path(season, offset)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    url = f"{API_BASE_URL}/{season}/results.json"
    logger.info("GET %s offset=%d", url, offset)
    response = _get_with_retry(url, offset, session)
    payload = response.json()

    # Cache only after raise_for_status + json() succeed, so a failed request
    # never poisons the cache. Write atomically-ish via a temp name.
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    tmp.replace(path)

    time.sleep(REQUEST_DELAY_SECONDS)
    return payload


def fetch_season_results(season: int, session: requests.Session | None = None) -> list[dict]:
    """Return the season's Races list (Ergast schema), combining all pages.

    Each element is one race dict with season/round/raceName/Circuit/date and a
    Results list holding one entry per driver. Pages are stitched back together
    here because a race's Results can be split across a page boundary.
    """
    session = session or requests.Session()
    races_by_round: dict[int, dict] = {}
    offset = 0
    while True:
        payload = _fetch_page(season, offset, session)
        mrdata = payload["MRData"]
        total = int(mrdata["total"])
        races = mrdata["RaceTable"].get("Races", [])
        for race in races:
            rnd = int(race["round"])
            if rnd in races_by_round:
                races_by_round[rnd]["Results"].extend(race.get("Results", []))
            else:
                races_by_round[rnd] = race
        offset += PAGE_SIZE
        if offset >= total:
            break

    fetched = sum(len(r.get("Results", [])) for r in races_by_round.values())
    if fetched != total:
        raise ValueError(
            f"Season {season}: API reported {total} result rows but {fetched} were parsed"
        )
    return [races_by_round[rnd] for rnd in sorted(races_by_round)]
