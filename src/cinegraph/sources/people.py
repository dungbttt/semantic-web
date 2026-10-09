from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

LOGGER = logging.getLogger(__name__)
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "CineGraphSemanticWeb/2.0 (educational movie knowledge graph)"
QID_PATTERN = re.compile(r"^Q[1-9][0-9]*$")


def _bound(row: dict, name: str) -> str | None:
    value = row.get(name, {}).get("value")
    return value if isinstance(value, str) and value else None


def _date_value(timestamp: str | None, precision: str | None) -> str | None:
    if not timestamp or not precision:
        return None
    date = timestamp.split("T", 1)[0].lstrip("+")
    parts = date.split("-")
    if len(parts) != 3:
        return None
    year, month, day = parts
    try:
        level = int(precision)
    except ValueError:
        return None
    if level >= 11:
        return f"{year}-{month}-{day}"
    if level == 10:
        return f"{year}-{month}"
    if level == 9:
        return year
    return None


def _profile_from_binding(row: dict) -> dict:
    description = _bound(row, "description")
    image_name = _bound(row, "image")
    image = (
        "https://commons.wikimedia.org/wiki/Special:FilePath/" + quote(image_name, safe="")
        if image_name
        else None
    )
    return {
        "description": description,
        "birth_date": _date_value(_bound(row, "birth"), _bound(row, "birthPrecision")),
        "death_date": _date_value(_bound(row, "death"), _bound(row, "deathPrecision")),
        "image": image,
        "wikipedia_url": _bound(row, "wikipedia"),
    }


def _profile_query(qids: list[str]) -> str:
    values = " ".join(f"wd:{qid}" for qid in qids)
    return f"""
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX p: <http://www.wikidata.org/prop/>
    PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX wikibase: <http://wikiba.se/ontology#>
    PREFIX schema: <http://schema.org/>
    SELECT ?person
      (SAMPLE(?descriptionValue) AS ?description)
      (SAMPLE(?birthValue) AS ?birth)
      (SAMPLE(?birthPrecisionValue) AS ?birthPrecision)
      (SAMPLE(?deathValue) AS ?death)
      (SAMPLE(?deathPrecisionValue) AS ?deathPrecision)
      (SAMPLE(?imageValue) AS ?image)
      (SAMPLE(?wikipediaValue) AS ?wikipedia)
    WHERE {{
      VALUES ?person {{ {values} }}
      OPTIONAL {{ ?person schema:description ?descriptionValue . FILTER(LANG(?descriptionValue) = "en") }}
      OPTIONAL {{
        ?person p:P569/psv:P569 ?birthNode .
        ?birthNode wikibase:timeValue ?birthValue ; wikibase:timePrecision ?birthPrecisionValue .
      }}
      OPTIONAL {{
        ?person p:P570/psv:P570 ?deathNode .
        ?deathNode wikibase:timeValue ?deathValue ; wikibase:timePrecision ?deathPrecisionValue .
      }}
      OPTIONAL {{ ?person wdt:P18 ?imageValue }}
      OPTIONAL {{ ?wikipediaValue schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> }}
    }} GROUP BY ?person
    """


def enrich_person_profiles(records: list[dict], cache_file: Path) -> tuple[dict[str, dict], dict]:
    """Fetch small, public Wikidata profiles for already linked cast and crew.

    Movie membership is not changed. Only existing exact TMDB-to-Wikidata
    person links are used, and responses are cached so later ingests are local.
    """
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        cached = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    except (OSError, json.JSONDecodeError):
        cached = {}
    profile_cache = cached.setdefault("profiles", {})

    uri_to_qid = {}
    for record in records:
        for person in record.get("person_ids", []):
            uri = person.get("wikidata_uri")
            qid = str(uri).rsplit("/", 1)[-1] if isinstance(uri, str) else ""
            if uri and QID_PATTERN.fullmatch(qid):
                uri_to_qid[uri] = qid

    missing = sorted({qid for qid in uri_to_qid.values() if qid not in profile_cache})
    requested = 0
    failures = 0
    session = requests.Session()
    batch_size = 300
    for start in range(0, len(missing), batch_size):
        chunk = missing[start : start + batch_size]
        LOGGER.info(
            "Fetching Wikidata person profiles %s–%s of %s",
            start + 1,
            start + len(chunk),
            len(missing),
        )
        bindings = None
        for attempt in range(4):
            try:
                response = session.post(
                    WIKIDATA_ENDPOINT,
                    data={"query": _profile_query(chunk), "format": "json"},
                    headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
                    timeout=60,
                )
                requested += 1
                response.raise_for_status()
                bindings = response.json().get("results", {}).get("bindings", [])
                break
            except (requests.RequestException, ValueError) as exc:
                failures += 1
                delay = min(5 * (2**attempt), 60)
                LOGGER.warning(
                    "Wikidata person profile batch failed (%s); retrying in %ss.",
                    type(exc).__name__,
                    delay,
                )
                if attempt < 3:
                    time.sleep(delay)

        if bindings is None:
            LOGGER.warning("Stopping the Wikidata profile refresh after an unsuccessful batch.")
            break
        for row in bindings:
            uri = _bound(row, "person")
            qid = uri.rsplit("/", 1)[-1] if uri else ""
            if qid in chunk:
                profile_cache[qid] = _profile_from_binding(row)
        for qid in chunk:
            profile_cache.setdefault(qid, {})
        cache_file.write_text(json.dumps(cached, ensure_ascii=False, indent=2), encoding="utf-8")
        # Keep this offline cache refresh gentle on the public query service.
        time.sleep(0.75)

    by_uri = {uri: profile_cache.get(qid, {}) for uri, qid in uri_to_qid.items()}
    populated = sum(any(profile.values()) for profile in by_uri.values())
    pending = sum(qid not in profile_cache for qid in uri_to_qid.values())
    return by_uri, {
        "status": "partial" if pending else "resolved",
        "linked_people": len(uri_to_qid),
        "profiles_with_data": populated,
        "profiles_with_description": sum(
            bool(profile.get("description")) for profile in by_uri.values()
        ),
        "profiles_with_birth_date": sum(
            bool(profile.get("birth_date")) for profile in by_uri.values()
        ),
        "profiles_with_image": sum(bool(profile.get("image")) for profile in by_uri.values()),
        "profiles_fetched": len(missing) - pending,
        "requests": requested,
        "batch_failures": failures,
        "pending": pending,
    }
