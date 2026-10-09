from __future__ import annotations

import csv
import gzip
import logging
from pathlib import Path

import requests

from ..config import Settings
from .utils import clean, number

LOGGER = logging.getLogger(__name__)


def _download(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 100:
        try:
            with gzip.open(destination, "rb") as stream:
                stream.read(1)
            return destination
        except OSError:
            destination.unlink(missing_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    LOGGER.info("Downloading IMDb dataset file: %s", destination.name)
    with requests.get(
        url,
        stream=True,
        timeout=(20, 120),
        headers={"User-Agent": "CineGraphSemanticWeb/2.0 educational project"},
    ) as response:
        response.raise_for_status()
        with temporary.open("wb") as stream:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    stream.write(chunk)
    temporary.replace(destination)
    return destination


def download_imdb_datasets(settings: Settings) -> tuple[Path, Path]:
    """Download (or reuse cached) IMDb's official basics and ratings files."""
    basics_path = _download(settings.imdb_basics_url, settings.raw_imdb / "title.basics.tsv.gz")
    ratings_path = _download(settings.imdb_ratings_url, settings.raw_imdb / "title.ratings.tsv.gz")
    return basics_path, ratings_path


def load_imdb_movies(settings: Settings, min_votes: int = 50_000) -> list[dict]:
    """Join IMDb's official basics and ratings, retaining titles above the vote threshold."""
    basics_path, ratings_path = download_imdb_datasets(settings)

    ratings: dict[str, tuple[float, int]] = {}
    with gzip.open(ratings_path, "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            tconst = row.get("tconst", "")
            score = number(row.get("averageRating"))
            votes = number(row.get("numVotes"), int)
            if tconst and score is not None and votes is not None and votes > min_votes:
                ratings[tconst] = (score, votes)
    selected = set(ratings)
    if not selected:
        LOGGER.warning("IMDb ratings had no titles with more than %s votes.", min_votes)
        return []

    movies: list[dict] = []
    with gzip.open(basics_path, "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            tconst = row.get("tconst", "")
            if tconst not in selected or row.get("titleType") not in {"movie", "tvMovie"}:
                continue
            score, votes = ratings[tconst]
            raw_genres = clean(row.get("genres")) or ""
            year = number(row.get("startYear"), int)
            movies.append(
                {
                    "imdb_id": tconst,
                    "tmdb_id": None,
                    "title": clean(row.get("primaryTitle")) or clean(row.get("originalTitle")),
                    "year": year,
                    "runtime_minutes": number(row.get("runtimeMinutes")),
                    "genres": [g for g in raw_genres.split(",") if g and g != "\\N"],
                    "rating": score,
                    "rating_votes": votes,
                    "tmdb_rating": None,
                    "tmdb_vote_count": None,
                    "plot": None,
                    "revenue": None,
                    "budget": None,
                    "directors": [],
                    "actors": [],
                    "person_ids": [],
                    "poster_url": None,
                    "wikidata_uri": None,
                    "dbpedia_uri": None,
                    "sources": {"record": "IMDb"},
                }
            )
    movies.sort(key=lambda movie: (movie["rating_votes"] or 0, movie["rating"] or 0), reverse=True)
    return movies
