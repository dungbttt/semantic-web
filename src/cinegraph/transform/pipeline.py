from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from ..config import Settings
from ..sources.crawl import crawl_sources
from ..sources.imdb import load_imdb_movies
from ..sources.kaggle_csv import load_kaggle_movies, merge_by_identity
from ..sources.linked_data import link_by_imdb, link_people_and_genres
from ..sources.omdb import enrich_with_omdb
from ..sources.people import enrich_person_profiles
from .rdf_builder import build_graph
from .validation import validate_graph

LOGGER = logging.getLogger(__name__)


def run_pipeline(settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    for folder in (settings.omdb_cache, settings.processed, settings.rdf, settings.reports):
        folder.mkdir(parents=True, exist_ok=True)
    status = crawl_sources(settings)

    # IMDb defines the catalog. Kaggle and OMDb are enrichment sources only.
    try:
        records = load_imdb_movies(settings, min_votes=settings.imdb_vote_threshold)
    except Exception as exc:
        LOGGER.exception("IMDb dataset ingestion failed")
        status["IMDb"] = {"status": "unavailable", "detail": str(exc)}
        raise RuntimeError(
            "IMDb is the canonical catalog, but its datasets could not be loaded."
        ) from exc
    if not records:
        raise RuntimeError("IMDb datasets loaded, but no movies were selected for the catalog.")
    imdb_ids = {record["imdb_id"] for record in records if record.get("imdb_id")}
    status["IMDb"] = {
        "status": "loaded",
        "records": len(records),
        "minimum_votes_exclusive": settings.imdb_vote_threshold,
    }

    kaggle_records = (
        load_kaggle_movies(settings.raw_kaggle)
        if status.get("Kaggle", {}).get("status") == "ready"
        else []
    )
    if kaggle_records:
        kaggle_ids = {record["imdb_id"] for record in kaggle_records if record.get("imdb_id")}
        matched_ids = imdb_ids.intersection(kaggle_ids)
        records = merge_by_identity(records, kaggle_records, "Kaggle")
        status["Kaggle"] = {
            "status": "loaded" if matched_ids else "no_matches",
            "handle": settings.kaggle_handle,
            "records": len(kaggle_records),
            "matched_movies": len(matched_ids),
            "unmatched_imdb_ids": len(kaggle_ids - imdb_ids),
        }
    elif status.get("Kaggle", {}).get("status") != "unavailable":
        status["Kaggle"] = {"status": "no_compatible_csv", "records": 0, "matched_movies": 0}

    if settings.omdb_api_key:
        omdb_budget = settings.omdb_request_budget
        # Build the final three-source catalog from the exact IMDb/Kaggle intersection.
        # OMDb is queried only for that subset; cached answers do not consume budget.
        omdb_targets = [record for record in records if record.get("sources", {}).get("Kaggle")]
        omdb_records, requested = enrich_with_omdb(
            omdb_targets, settings.omdb_api_key, settings.omdb_cache, omdb_budget
        )
        records = merge_by_identity(records, omdb_records, "OMDb")
        pending_omdb = sum(
            1
            for record in omdb_targets
            if record.get("imdb_id")
            and not (settings.omdb_cache / f"{record['imdb_id']}.json").exists()
        )
        status["OMDb"] = {
            "status": "loaded" if omdb_records else "no_matches",
            "records": len(omdb_records),
            "target_records": len(omdb_targets),
            "pending_records": pending_omdb,
            "requests": requested,
            "request_budget": omdb_budget,
        }
    else:
        status["OMDb"] = {
            "status": "needs_api_key",
            "records": 0,
            "hint": "Set OMDB_API_KEY in .env to enable enrichment.",
        }

    input_records = len(records)
    records = [
        record
        for record in records
        if all(record.get("sources", {}).get(source) for source in ("IMDb", "Kaggle", "OMDb"))
    ]
    status["Catalog selection"] = {
        "status": "filtered",
        "required_sources": ["IMDb", "Kaggle", "OMDb"],
        "input_records": input_records,
        "records": len(records),
        "excluded_records": input_records - len(records),
    }

    linked = {}
    person_profiles = {}
    if os.getenv("CINEGRAPH_LINKED_DATA", "1").lower() not in {"0", "false", "no"}:
        linked = link_by_imdb(records, settings.root / "data" / "cache" / "linked-data.json")
        current_ids = {record["imdb_id"] for record in records if record.get("imdb_id")}
        status["Linked Data"] = {
            "status": "resolved",
            "wikidata": sum("wikidata" in linked.get(imdb_id, {}) for imdb_id in current_ids),
            "dbpedia": sum("dbpedia" in linked.get(imdb_id, {}) for imdb_id in current_ids),
        }
        linked_entities_status = link_people_and_genres(
            records, settings.root / "data" / "cache" / "linked-entities.json"
        )
        status["Linked Entities"] = {"status": "resolved", **linked_entities_status}
        person_profiles, status["Person Profiles"] = enrich_person_profiles(
            records, settings.root / "data" / "cache" / "person-profiles.json"
        )
    else:
        status["Linked Data"] = {"status": "disabled"}
        status["Linked Entities"] = {"status": "disabled"}
        status["Person Profiles"] = {"status": "disabled"}

    now = datetime.now(timezone.utc).isoformat()
    processed_path = settings.processed / "movies.json"
    processed_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    graph = build_graph(records, settings.root / "ontology" / "cinegraph.ttl", person_profiles)
    try:
        validation, validation_graph = validate_graph(
            graph, settings.root / "ontology" / "cinegraph.shacl.ttl"
        )
        validation_graph.serialize(
            destination=str(settings.reports / "shacl-report.ttl"), format="turtle"
        )
    except Exception as exc:
        LOGGER.exception("SHACL validation could not be completed")
        validation = {"status": "error", "detail": str(exc)}
    else:
        validation["status"] = "conforms" if validation["conforms"] else "violations_found"
        if not validation["conforms"]:
            LOGGER.warning("SHACL found %s validation result(s).", validation["result_count"])
    graph_path = settings.rdf / "movies.ttl"
    graph.serialize(destination=str(graph_path), format="turtle")
    summary = {
        "project": "CineGraph Semantic Movie Catalog",
        "generated_at_utc": now,
        "record_count": len(records),
        "triple_count": len(graph),
        "validation": validation,
        "source_status": status,
        "artifacts": {"catalog": "data/processed/movies.json", "rdf": "data/rdf/movies.ttl"},
        "source_count": sum(
            status.get(name, {}).get("status") == "loaded" for name in ("IMDb", "Kaggle", "OMDb")
        ),
    }
    (settings.reports / "pipeline.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    LOGGER.info("Pipeline ready: %s movies, %s RDF triples", len(records), len(graph))
    return summary
