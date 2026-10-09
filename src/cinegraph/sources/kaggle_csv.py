from __future__ import annotations

import ast
import csv
import io
import json
import logging
import re
import zipfile
from pathlib import Path

from .utils import clean, number, split_names

LOGGER = logging.getLogger(__name__)
DEFAULT_HANDLE = "rounakbanik/the-movies-dataset"


def download_public_dataset(output_dir: Path, handle: str = DEFAULT_HANDLE) -> list[Path]:
    """Download a public Kaggle dataset through Kaggle's maintained KaggleHub client."""
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        import kagglehub
    except ImportError as exc:
        raise RuntimeError("KaggleHub is missing. Install project requirements first.") from exc
    LOGGER.info("Downloading Kaggle dataset %s", handle)
    # Download only the catalog and credits files. Kaggle's archive also has
    # large ratings tables, which are not needed by this graph.
    downloaded: list[Path] = []
    for filename in ("movies_metadata.csv", "credits.csv"):
        target_dir = output_dir / "the-movies-dataset" / Path(filename).stem
        existing = list(target_dir.rglob(filename)) if target_dir.exists() else []
        if existing:
            downloaded.extend(existing)
            continue
        result_path = Path(
            kagglehub.dataset_download(handle, path=filename, output_dir=str(target_dir))
        )
        if result_path.is_file() and result_path.suffix.lower() == ".csv":
            downloaded.append(result_path)
        elif result_path.exists():
            downloaded.extend(result_path.rglob("*.csv"))
    return downloaded


def _read_csv(path: Path) -> list[dict[str, str]]:
    csv.field_size_limit(1_000_000)

    def read(encoding: str) -> list[dict[str, str]]:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                member = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
                with (
                    archive.open(member) as raw,
                    io.TextIOWrapper(raw, encoding=encoding, newline="") as stream,
                ):
                    return [dict(row) for row in csv.DictReader(stream)]
        with path.open("r", encoding=encoding, newline="") as stream:
            return [dict(row) for row in csv.DictReader(stream)]

    try:
        return read("utf-8-sig")
    except UnicodeDecodeError:
        # This historical Kaggle release has non-UTF-8 bytes in some credits.
        try:
            return read("cp1252")
        except UnicodeDecodeError:
            return read("latin-1")


def _index(row: dict[str, str]) -> dict[str, str]:
    return {re.sub(r"[^a-z0-9]", "", key.lower()): value for key, value in row.items() if key}


def _pick(row: dict[str, str], *keys: str) -> str | None:
    indexed = _index(row)
    for key in keys:
        val = clean(indexed.get(re.sub(r"[^a-z0-9]", "", key.lower())))
        if val:
            return val
    return None


def _json_list(value: str | None) -> list[dict]:
    if not value:
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        # Some copies of The Movies Dataset serialize cast/crew with Python
        # single-quoted dicts instead of valid JSON. literal_eval parses that
        # representation without executing arbitrary code.
        try:
            result = ast.literal_eval(value)
            return result if isinstance(result, list) else []
        except (ValueError, SyntaxError, TypeError):
            return []


def _person_names(value: str | None, limit: int = 8) -> list[str]:
    # Kaggle's TMDB files store cast/crew as JSON; generic CSVs often use delimited names.
    parsed = _json_list(value)
    if parsed:
        return [name for item in parsed[:limit] if (name := clean(item.get("name")))]
    return split_names(value)[:limit]


def _person_entries(value: str | None, limit: int = 8) -> list[dict]:
    """Keep TMDB person IDs from credits so later linking never depends on names."""
    entries = []
    for item in _json_list(value)[:limit]:
        name = clean(item.get("name"))
        tmdb_id = clean(item.get("id"))
        if name:
            entries.append(
                {"name": name, "tmdb_id": tmdb_id if tmdb_id and tmdb_id.isdigit() else None}
            )
    return entries


def load_kaggle_movies(directory: Path) -> list[dict]:
    """Read the Kaggle movie catalog or a compatible CSV, joining credits when present."""
    files = [p for p in directory.rglob("*.csv") if p.is_file()]
    if not files:
        return []
    movie_file = next((p for p in files if p.name.lower() == "movies_metadata.csv"), None)
    if movie_file is None:
        movie_file = next(
            (p for p in files if "movie" in p.name.lower() and "credit" not in p.name.lower()), None
        )
    if movie_file is None:
        movie_file = next(
            (p for p in files if "title" in p.name.lower() or "film" in p.name.lower()), files[0]
        )
    credit_file = next((p for p in files if p.name.lower() == "credits.csv"), None)
    if credit_file is None:
        credit_file = next((p for p in files if "credit" in p.name.lower()), None)
    credits: dict[str, dict[str, str]] = {}
    if credit_file:
        for row in _read_csv(credit_file):
            key = _pick(row, "id", "tmdb_id", "movie_id")
            if key:
                credits[key] = row

    output = []
    for row in _read_csv(movie_file):
        title = _pick(row, "title", "primaryTitle", "original_title", "name")
        if not title:
            continue
        tmdb_id = _pick(row, "id", "tmdb_id", "movie_id")
        credit = credits.get(tmdb_id or "", {})
        crew = _json_list(_pick(credit, "crew"))
        director_entries = [
            {"name": clean(person.get("name")), "tmdb_id": clean(person.get("id"))}
            for person in crew
            if person.get("job") == "Director" and clean(person.get("name"))
        ]
        director_entries = [
            {
                **person,
                "tmdb_id": person["tmdb_id"]
                if person["tmdb_id"] and person["tmdb_id"].isdigit()
                else None,
            }
            for person in director_entries
        ]
        cast_entries = _person_entries(_pick(credit, "cast"), 8)
        if not cast_entries:
            cast_entries = [
                {"name": name, "tmdb_id": None}
                for name in _person_names(_pick(row, "cast", "actors", "starring"), 8)
            ]
        if not director_entries:
            director_entries = [
                {"name": name, "tmdb_id": None}
                for name in split_names(_pick(row, "director", "directors"))
            ]
        genres_value = _pick(row, "genres", "genre")
        genres = [clean(item.get("name")) for item in _json_list(genres_value)] or split_names(
            genres_value
        )
        imdb_id = _pick(row, "imdb_id", "imdbid", "tconst")
        if imdb_id and not imdb_id.startswith("tt"):
            imdb_id = f"tt{imdb_id}"
        revenue = number(_pick(row, "revenue"), int)
        budget = number(_pick(row, "budget"), int)
        poster = _pick(row, "poster_url", "poster")
        poster_path = _pick(row, "poster_path")
        if not poster and poster_path and poster_path.startswith("/"):
            poster = "https://image.tmdb.org/t/p/w500" + poster_path
        output.append(
            {
                "imdb_id": imdb_id,
                "tmdb_id": tmdb_id,
                "title": title,
                "year": number(_pick(row, "release_year", "year"), int)
                or number((_pick(row, "release_date") or "")[:4], int),
                "runtime_minutes": number(_pick(row, "runtime", "runtime_minutes")),
                "genres": [g for g in genres if g],
                "rating": number(
                    _pick(row, "imdb_rating", "imdbRating", "averageRating", "rating")
                ),
                "rating_votes": number(
                    _pick(row, "imdb_votes", "numVotes", "imdb_vote_count"), int
                ),
                "tmdb_rating": number(_pick(row, "vote_average", "tmdb_rating")),
                "tmdb_vote_count": number(_pick(row, "vote_count", "tmdb_votes"), int),
                "plot": _pick(row, "overview", "plot", "description", "summary"),
                "revenue": revenue if revenue else None,
                "budget": budget if budget else None,
                "directors": [person["name"] for person in director_entries],
                "actors": [person["name"] for person in cast_entries],
                "person_ids": [
                    {**person, "role": role}
                    for role, entries in (("Director", director_entries), ("Actor", cast_entries))
                    for person in entries
                    if person.get("tmdb_id")
                ],
                "poster_url": poster,
                "wikidata_uri": None,
                "dbpedia_uri": None,
                "sources": {"record": "Kaggle"},
            }
        )
    return output


def merge_by_identity(records: list[dict], additions: list[dict], source: str) -> list[dict]:
    """Enrich the existing IMDb catalog using exact IMDb IDs only.

    Additions never create catalog entries. This avoids turning Kaggle or OMDb
    into an accidental second catalog and prevents title/year collisions between
    remakes. `field_sources` records which source supplied each winning value.
    """
    priorities = {
        "IMDb": {
            "title": 3,
            "year": 3,
            "runtime_minutes": 3,
            "genres": 3,
            "rating": 3,
            "rating_votes": 3,
        },
        "Kaggle": {
            "revenue": 3,
            "budget": 3,
            "plot": 2,
            "directors": 2,
            "actors": 2,
            "person_ids": 2,
            "title": 2,
            "year": 2,
            "runtime_minutes": 2,
            "genres": 2,
            "rating": 1,
            "rating_votes": 1,
            "tmdb_rating": 2,
            "tmdb_vote_count": 2,
            "poster_url": 2,
        },
        "OMDb": {
            "plot": 3,
            "directors": 2,
            "actors": 2,
            "poster_url": 3,
            "awards": 3,
            "rating": 2,
            "rating_votes": 1,
            "runtime_minutes": 1,
            "year": 1,
            "title": 1,
            "genres": 1,
        },
    }
    excluded_fields = {
        "Kaggle": {"genres", "plot"},
        "OMDb": set(),
    }

    def source_of(record: dict) -> str:
        value = record.get("sources", {}).get("record", source)
        return value if value in priorities else source

    def prepare(record: dict) -> None:
        origin = source_of(record)
        record.setdefault("field_sources", {})
        record.setdefault("sources", {})
        for key, value in record.items():
            if (
                key not in excluded_fields.get(origin, set())
                and key in priorities.get(origin, {})
                and value not in (None, [], "")
            ):
                record["field_sources"].setdefault(key, origin)
        record["sources"][origin] = True

    for record in records:
        prepare(record)
    by_id = {r["imdb_id"]: r for r in records if r.get("imdb_id")}
    for add in additions:
        prepare(add)
        origin = source_of(add)
        existing = by_id.get(add.get("imdb_id")) if add.get("imdb_id") else None
        if existing is None:
            LOGGER.debug(
                "Skipping %s enrichment without a matching IMDb ID: %s", source, add.get("imdb_id")
            )
            continue
        for key, value in add.items():
            if key in excluded_fields.get(origin, set()):
                continue
            elif key == "sources":
                # Keep the original record marker while accumulating all contributors.
                existing.setdefault(key, {}).update(
                    {name: present for name, present in value.items() if name != "record"}
                )
            elif key == "field_sources":
                # Provenance is updated only when the corresponding field wins below.
                continue
            elif key == "omdb_ratings":
                if value:
                    existing[key] = value
            elif key == "person_ids":
                people = existing.setdefault(key, [])
                for incoming_person in value or []:
                    match = next(
                        (
                            person
                            for person in people
                            if person.get("role") == incoming_person.get("role")
                            and str(person.get("name", "")).casefold()
                            == str(incoming_person.get("name", "")).casefold()
                        ),
                        None,
                    )
                    if match is not None:
                        if not match.get("wikidata_uri") and incoming_person.get("wikidata_uri"):
                            match["wikidata_uri"] = incoming_person["wikidata_uri"]
                    else:
                        people.append(incoming_person)
            elif key in priorities.get(origin, {}) and value not in (None, [], ""):
                previous_source = existing.get("field_sources", {}).get(key)
                current_score = priorities.get(previous_source, {}).get(key, 0)
                incoming_score = priorities[origin].get(key, 0)
                if existing.get(key) in (None, [], "") or incoming_score > current_score:
                    existing[key] = value
                    existing.setdefault("field_sources", {})[key] = origin
            elif value not in (None, [], "") and existing.get(key) in (None, [], ""):
                existing[key] = value
        existing.setdefault("sources", {})[origin] = True
    return records
