from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

LOGGER = logging.getLogger(__name__)
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
DBPEDIA_ENDPOINT = "https://dbpedia.org/sparql"
USER_AGENT = "CineGraphSemanticWeb/2.0 (educational movie knowledge graph)"
WIKIDATA_GENRE_LABELS = {
    "action": "action film",
    "adventure": "adventure film",
    "animation": "animated film",
    "biography": "biographical film",
    "comedy": "comedy film",
    "crime": "crime film",
    "documentary": "documentary film",
    "drama": "drama film",
    "family": "family film",
    "fantasy": "fantasy film",
    "film-noir": "film noir",
    "history": "historical film",
    "horror": "horror film",
    "music": "music film",
    "musical": "musical film",
    "mystery": "mystery film",
    "romance": "romance film",
    "sci-fi": "science fiction film",
    "sport": "sports film",
    "thriller": "thriller film",
    "war": "war film",
    "western": "western film",
}


def _query(endpoint: str, query: str) -> list[dict]:
    response = requests.get(
        endpoint,
        params={"query": query, "format": "json"},
        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
        timeout=25,
    )
    response.raise_for_status()
    return response.json().get("results", {}).get("bindings", [])


def _query_post(endpoint: str, query: str) -> list[dict]:
    response = requests.post(
        endpoint,
        data={"query": query, "format": "json"},
        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
        timeout=40,
    )
    response.raise_for_status()
    return response.json().get("results", {}).get("bindings", [])


def link_by_imdb(records: list[dict], cache_file: Path) -> dict:
    """Resolve IMDb identifiers to exact external records, never title guesses."""
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        links = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    except (OSError, json.JSONDecodeError):
        links = {}
    ids = sorted({r["imdb_id"] for r in records if r.get("imdb_id")})
    missing = [value for value in ids if value not in links]
    for start in range(0, len(missing), 100):
        chunk = missing[start : start + 100]
        values = " ".join(json.dumps(value) for value in chunk)
        if not values:
            continue
        for label, endpoint, prefix, predicate in (
            (
                "wikidata",
                WIKIDATA_ENDPOINT,
                "PREFIX wdt: <http://www.wikidata.org/prop/direct/>",
                "wdt:P345",
            ),
            (
                "dbpedia",
                DBPEDIA_ENDPOINT,
                "PREFIX dbo: <http://dbpedia.org/ontology/>",
                "dbo:imdbId",
            ),
        ):
            query = f"{prefix}\nSELECT ?imdb ?entity WHERE {{ VALUES ?imdb {{ {values} }} ?entity {predicate} ?imdb . }}"
            try:
                for row in _query(endpoint, query):
                    imdb_id = row.get("imdb", {}).get("value")
                    entity = row.get("entity", {}).get("value")
                    if imdb_id and entity and imdb_id in chunk:
                        links.setdefault(imdb_id, {})[label] = entity
            except (requests.RequestException, ValueError, KeyError) as exc:
                LOGGER.warning("Could not resolve %s links: %s", label, exc)
        cache_file.write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")
    for record in records:
        record["wikidata_uri"] = links.get(record.get("imdb_id"), {}).get("wikidata")
        record["dbpedia_uri"] = links.get(record.get("imdb_id"), {}).get("dbpedia")
    return links


def link_people_and_genres(records: list[dict], cache_file: Path) -> dict:
    """Link cast/crew by TMDB person ID and genres by a unique Wikidata genre label.

    Person names are never used as identifiers. Genre matches are accepted only
    when Wikidata returns exactly one English-labeled film-genre item.
    """
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    except (OSError, json.JSONDecodeError):
        cache = {}
    people_cache = cache.setdefault("people", {})
    genres_cache = cache.setdefault("genres", {})

    person_ids = sorted(
        {
            str(person.get("tmdb_id"))
            for record in records
            for person in record.get("person_ids", [])
            if str(person.get("tmdb_id", "")).isdigit()
        }
    )
    missing_people = [tmdb_id for tmdb_id in person_ids if tmdb_id not in people_cache]
    for start in range(0, len(missing_people), 300):
        chunk = missing_people[start : start + 300]
        values = " ".join(json.dumps(tmdb_id) for tmdb_id in chunk)
        query = f"""
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?id ?person WHERE {{
          VALUES ?id {{ {values} }}
          ?person wdt:P4985 ?id .
        }}
        """
        try:
            rows = _query_post(WIKIDATA_ENDPOINT, query)
        except (requests.RequestException, ValueError, KeyError) as exc:
            LOGGER.warning("Could not resolve TMDB person links: %s", exc)
            continue
        matches: dict[str, set[str]] = {}
        for row in rows:
            tmdb_id = row.get("id", {}).get("value")
            entity = row.get("person", {}).get("value")
            if (
                tmdb_id in chunk
                and entity
                and entity.startswith("http://www.wikidata.org/entity/Q")
            ):
                matches.setdefault(tmdb_id, set()).add(entity)
        for tmdb_id in chunk:
            found = matches.get(tmdb_id, set())
            people_cache[tmdb_id] = {"wikidata": next(iter(found))} if len(found) == 1 else {}
        cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    genre_names = sorted(
        {
            str(name).strip()
            for record in records
            for name in record.get("genres", [])
            if str(name).strip()
        },
        key=str.casefold,
    )
    genre_labels: dict[str, set[str]] = {}
    for name in genre_names:
        target_label = WIKIDATA_GENRE_LABELS.get(name.casefold())
        if target_label:
            genre_labels.setdefault(target_label, set()).add(name.casefold())
    missing_labels = [
        label
        for label in genre_labels
        if not all(name in genres_cache for name in genre_labels[label])
    ]
    for start in range(0, len(missing_labels), 30):
        chunk = missing_labels[start : start + 30]
        values = " ".join(json.dumps(label) + "@en" for label in chunk)
        query = f"""
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?label ?genre WHERE {{
          VALUES ?label {{ {values} }}
          ?genre wdt:P31/wdt:P279* wd:Q201658 ; rdfs:label ?label .
        }}
        """
        try:
            rows = _query_post(WIKIDATA_ENDPOINT, query)
        except (requests.RequestException, ValueError, KeyError) as exc:
            LOGGER.warning("Could not resolve Wikidata genre links: %s", exc)
            continue
        matches: dict[str, set[str]] = {}
        for row in rows:
            label = row.get("label", {}).get("value", "").casefold()
            entity = row.get("genre", {}).get("value")
            if label in chunk and entity and entity.startswith("http://www.wikidata.org/entity/Q"):
                matches.setdefault(label, set()).add(entity)
        for target_label in chunk:
            found = matches.get(target_label, set())
            result = {"wikidata": next(iter(found))} if len(found) == 1 else {}
            for local_name in genre_labels[target_label]:
                genres_cache[local_name] = result
        cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    for record in records:
        for person in record.get("person_ids", []):
            person["wikidata_uri"] = people_cache.get(str(person.get("tmdb_id")), {}).get(
                "wikidata"
            )
        record["genre_wikidata"] = {
            name: genres_cache.get(str(name).strip().casefold(), {}).get("wikidata")
            for name in record.get("genres", [])
            if genres_cache.get(str(name).strip().casefold(), {}).get("wikidata")
        }

    linked_people = sum(
        bool(people_cache.get(tmdb_id, {}).get("wikidata")) for tmdb_id in person_ids
    )
    linked_genres = sum(
        bool(genres_cache.get(name.casefold(), {}).get("wikidata"))
        for name in genre_names
        if name.casefold() in WIKIDATA_GENRE_LABELS
    )
    return {
        "people_with_tmdb_ids": len(person_ids),
        "people_linked_to_wikidata": linked_people,
        "genres_with_supported_labels": sum(
            name.casefold() in WIKIDATA_GENRE_LABELS for name in genre_names
        ),
        "genres_linked_to_wikidata": linked_genres,
    }
