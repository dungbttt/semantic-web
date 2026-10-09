from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, FOAF, OWL, RDF, RDFS, XSD

from ..vocabulary import BASE, CINE, PROV, SCHEMA, SOURCE_URLS, WIKIDATA_URL

NUMERIC_FIELDS = (
    ("runtime_minutes", CINE.durationMinutes, XSD.decimal),
    ("rating", CINE.imdbRating, XSD.decimal),
    ("rating_votes", CINE.ratingVotes, XSD.integer),
    ("tmdb_rating", CINE.tmdbRating, XSD.decimal),
    ("tmdb_vote_count", CINE.tmdbVotes, XSD.integer),
    ("revenue", CINE.revenue, XSD.integer),
    ("budget", CINE.budget, XSD.integer),
)


def _slug(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-") or "unknown"


def _uri(value: str) -> URIRef:
    return URIRef(BASE + value)


def _text(graph: Graph, subject: URIRef, predicate: URIRef, value, lang: str | None = None) -> None:
    if value not in (None, ""):
        graph.add((subject, predicate, Literal(value, lang=lang)))


def _person_source(record: dict, role: str, name: str) -> dict:
    folded = name.casefold()
    return next(
        (
            item
            for item in record.get("person_ids", [])
            if item.get("role") == role and str(item.get("name", "")).casefold() == folded
        ),
        {},
    )


def build_graph(
    records: list[dict], ontology_path: Path, person_profiles: dict[str, dict] | None = None
) -> Graph:
    person_profiles = person_profiles or {}
    graph = Graph()
    graph.bind("cine", CINE)
    graph.bind("schema", SCHEMA)
    graph.bind("prov", PROV)
    graph.bind("dcterms", DCTERMS)
    graph.bind("owl", OWL)
    if ontology_path.exists():
        graph.parse(ontology_path, format="turtle")

    for record in records:
        imdb_id = record.get("imdb_id")
        tmdb_id = record.get("tmdb_id")
        identity = (
            f"movie/{imdb_id}"
            if imdb_id
            else (
                f"movie/tmdb-{tmdb_id}"
                if tmdb_id
                else f"movie/{_slug(record.get('title') or 'movie')}-{record.get('year') or 'na'}"
            )
        )
        movie = _uri(identity)
        graph.add((movie, RDF.type, CINE.Movie))
        graph.add((movie, RDF.type, SCHEMA.Movie))
        title = record.get("title") or "Untitled"
        _text(graph, movie, CINE.title, title, "en")
        _text(graph, movie, RDFS.label, title, "en")
        _text(graph, movie, SCHEMA.name, title, "en")
        year = record.get("year")
        if year:
            graph.add((movie, CINE.releaseYear, Literal(int(year), datatype=XSD.gYear)))
            graph.add(
                (movie, SCHEMA.datePublished, Literal(f"{int(year):04d}", datatype=XSD.gYear))
            )
        for key, prop, datatype in NUMERIC_FIELDS:
            value = record.get(key)
            if value is not None:
                if datatype == XSD.decimal:
                    # Keep construction-time SHACL behavior consistent with reparsed Turtle.
                    value = Decimal(str(value))
                graph.add((movie, prop, Literal(value, datatype=datatype)))
        if imdb_id:
            _text(graph, movie, CINE.imdbID, imdb_id)
            _text(graph, movie, SCHEMA.identifier, imdb_id)
            graph.add((movie, FOAF.page, URIRef(f"https://www.imdb.com/title/{imdb_id}/")))
        if tmdb_id:
            _text(graph, movie, CINE.tmdbID, tmdb_id)
        if record.get("plot"):
            _text(graph, movie, CINE.description, record["plot"], "en")
            _text(graph, movie, SCHEMA.description, record["plot"], "en")
        if record.get("poster_url") and str(record["poster_url"]).startswith("http"):
            graph.add((movie, SCHEMA.image, URIRef(record["poster_url"])))
        for genre_name in record.get("genres", []):
            genre = _uri("genre/" + _slug(genre_name))
            graph.add((genre, RDF.type, CINE.Genre))
            _text(graph, genre, RDFS.label, genre_name, "en")
            _text(graph, genre, SCHEMA.name, genre_name, "en")
            graph.add((movie, CINE.hasGenre, genre))
            graph.add((movie, SCHEMA.genre, Literal(genre_name, lang="en")))
            external_genre = record.get("genre_wikidata", {}).get(genre_name)
            if external_genre and external_genre.startswith("http://www.wikidata.org/entity/Q"):
                graph.add((genre, OWL.sameAs, URIRef(external_genre)))
        for role_key, predicate, role_type in (
            ("directors", CINE.directedBy, CINE.Director),
            ("actors", CINE.hasActor, CINE.Actor),
        ):
            for person_name in record.get(role_key, []):
                role = "Director" if role_key == "directors" else "Actor"
                person_source = _person_source(record, role, person_name)
                person_tmdb_id = person_source.get("tmdb_id")
                person_identity = (
                    f"person/tmdb-{person_tmdb_id}"
                    if person_tmdb_id
                    else "person/" + _slug(person_name)
                )
                person = _uri(person_identity)
                graph.add((person, RDF.type, CINE.Person))
                graph.add((person, RDF.type, role_type))
                graph.add((person, RDF.type, SCHEMA.Person))
                _text(graph, person, RDFS.label, person_name, "en")
                _text(graph, person, SCHEMA.name, person_name, "en")
                if person_tmdb_id:
                    _text(graph, person, CINE.tmdbPersonID, person_tmdb_id)
                    _text(graph, person, SCHEMA.identifier, person_tmdb_id)
                    if str(person_tmdb_id).isdigit():
                        graph.add(
                            (
                                person,
                                FOAF.page,
                                URIRef(f"https://www.themoviedb.org/person/{person_tmdb_id}"),
                            )
                        )
                person_wikidata = person_source.get("wikidata_uri")
                if person_wikidata and person_wikidata.startswith(
                    "http://www.wikidata.org/entity/Q"
                ):
                    graph.add((person, OWL.sameAs, URIRef(person_wikidata)))
                    profile = person_profiles.get(person_wikidata, {})
                    _text(graph, person, SCHEMA.description, profile.get("description"), "en")
                    _text(graph, person, SCHEMA.birthDate, profile.get("birth_date"))
                    _text(graph, person, SCHEMA.deathDate, profile.get("death_date"))
                    image_url = profile.get("image")
                    if image_url and str(image_url).startswith("https://"):
                        graph.add((person, SCHEMA.image, URIRef(image_url)))
                    wikipedia_url = profile.get("wikipedia_url")
                    if wikipedia_url and str(wikipedia_url).startswith("https://"):
                        graph.add((person, FOAF.page, URIRef(wikipedia_url)))
                    if profile:
                        graph.add((person, PROV.wasDerivedFrom, URIRef(WIKIDATA_URL)))
                        graph.add((person, DCTERMS.source, URIRef(WIKIDATA_URL)))
                graph.add((movie, predicate, person))
                graph.add(
                    (movie, SCHEMA.director if role_key == "directors" else SCHEMA.actor, person)
                )
        for rating in record.get("omdb_ratings", []):
            source = rating.get("Source")
            value = rating.get("Value")
            if source and value:
                rating_node = _uri(f"rating/{imdb_id}/{_slug(source)}")
                graph.add((rating_node, RDF.type, CINE.ExternalRating))
                _text(graph, rating_node, RDFS.label, f"{source}: {value}", "en")
                _text(graph, rating_node, CINE.ratingSource, source)
                _text(graph, rating_node, CINE.ratingValue, value)
                graph.add((movie, CINE.hasExternalRating, rating_node))
        if record.get("awards"):
            _text(graph, movie, CINE.awardsSummary, record["awards"], "en")
        for source_name, present in record.get("sources", {}).items():
            if present and source_name in SOURCE_URLS:
                graph.add((movie, PROV.wasDerivedFrom, URIRef(SOURCE_URLS[source_name])))
                graph.add((movie, DCTERMS.source, URIRef(SOURCE_URLS[source_name])))
        if record.get("field_sources"):
            for field, source_name in record["field_sources"].items():
                if source_name in SOURCE_URLS:
                    provenance = _uri(f"provenance/{imdb_id or _slug(title)}/{field}")
                    graph.add((provenance, RDF.type, CINE.FieldProvenance))
                    graph.add((provenance, CINE.fieldName, Literal(field)))
                    graph.add((provenance, PROV.wasDerivedFrom, URIRef(SOURCE_URLS[source_name])))
                    graph.add((movie, CINE.hasFieldProvenance, provenance))
        for external in (record.get("wikidata_uri"), record.get("dbpedia_uri")):
            if external and external.startswith("http"):
                graph.add((movie, OWL.sameAs, URIRef(external)))
    return graph
