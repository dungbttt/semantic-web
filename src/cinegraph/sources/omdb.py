from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

from .utils import clean, number, split_names

LOGGER = logging.getLogger(__name__)
OMDB_URL = "https://www.omdbapi.com/"


def _as_movie_record(movie: dict, payload: dict) -> dict:
    rating = number(payload.get("imdbRating"))
    return {
        "imdb_id": movie["imdb_id"],
        "tmdb_id": movie.get("tmdb_id"),
        "title": clean(payload.get("Title")),
        "year": number(str(payload.get("Year", "")).split("–")[0], int),
        "runtime_minutes": number(str(payload.get("Runtime", "")).replace(" min", "")),
        "genres": [
            item.strip() for item in (payload.get("Genre") or "").split(",") if item.strip()
        ],
        "rating": rating,
        "rating_votes": number(str(payload.get("imdbVotes", "")).replace(",", ""), int),
        "tmdb_rating": None,
        "tmdb_vote_count": None,
        "plot": clean(payload.get("Plot")),
        "directors": split_names(payload.get("Director")),
        "actors": split_names(payload.get("Actors"))[:8],
        "poster_url": clean(payload.get("Poster")),
        "omdb_ratings": payload.get("Ratings", []),
        "awards": clean(payload.get("Awards")),
        "sources": {"record": "OMDb"},
    }


def enrich_with_omdb(
    records: list[dict], api_key: str, cache_dir: Path, request_budget: int = 700
) -> tuple[list[dict], int]:
    """Reuse all cached answers and fetch up to `request_budget` uncached IMDb IDs.

    Caching negative "not found" results lets later runs continue with the next
    IDs instead of spending every batch retrying the same unavailable movies.
    """
    if not api_key:
        return [], 0
    cache_dir.mkdir(parents=True, exist_ok=True)
    additions = []
    attempted = 0
    stop_requests = False
    session = requests.Session()
    movies = [record for record in records if record.get("imdb_id")]
    for movie in movies:
        imdb_id = movie["imdb_id"]
        cache_path = cache_dir / f"{imdb_id}.json"
        payload = None
        if cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cache_path.unlink(missing_ok=True)
        if payload is None:
            if stop_requests or attempted >= request_budget:
                continue
            attempted += 1
            try:
                response = session.get(
                    OMDB_URL, params={"apikey": api_key, "i": imdb_id, "plot": "short"}, timeout=20
                )
                response.raise_for_status()
                payload = response.json()
                time.sleep(0.12)
            except requests.HTTPError as exc:
                response = exc.response
                status_code = response.status_code if response is not None else None
                # Request exceptions may contain the full URL, including the API key.
                LOGGER.warning(
                    "OMDb request failed for %s (HTTP %s)", imdb_id, status_code or "unknown"
                )
                if status_code in {401, 403, 429} or (
                    status_code is not None and status_code >= 500
                ):
                    stop_requests = True
                continue
            except (requests.RequestException, ValueError) as exc:
                LOGGER.warning("OMDb request failed for %s (%s)", imdb_id, type(exc).__name__)
                continue

            error = str(payload.get("Error", ""))
            normalized_error = error.lower()
            if payload.get("Response") == "True" or (
                payload.get("Response") == "False"
                and "invalid api key" not in normalized_error
                and "limit reached" not in normalized_error
                and "request limit" not in normalized_error
            ):
                cache_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            elif payload.get("Response") != "True":
                LOGGER.warning(
                    "OMDb returned an error for %s: %s", imdb_id, error or "unknown response"
                )
                if (
                    "invalid api key" in normalized_error
                    or "limit reached" in normalized_error
                    or "request limit" in normalized_error
                ):
                    stop_requests = True
                    continue

        if not payload or payload.get("Response") != "True":
            continue
        additions.append(_as_movie_record(movie, payload))
    return additions, attempted
