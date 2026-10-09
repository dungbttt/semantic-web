"""RDF catalog access, indexes, cards, filtering, and recommendations."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, FOAF, OWL, RDF, RDFS, XSD

from .text import normalize_text
from .vocabulary import CINE, REASONS, SCHEMA, SOURCE_NAMES, WEIGHTS


class CatalogService:
    """Own a loaded RDF graph and the indexes used by the web application."""

    def __init__(self, graph_path: Path, report_path: Path):
        self.report_path = Path(report_path)
        self.graph = Graph()
        graph_path = Path(graph_path)
        if not graph_path.is_file():
            raise FileNotFoundError(
                f"RDF dataset not found: {graph_path}. Run `python -m cinegraph.cli ingest` first."
            )
        self.graph.parse(graph_path, format="turtle")

        self._build_suggestions()
        self._index_people()
        self._build_explore_graph()

    def _build_suggestions(self) -> None:
        self.suggestion_options = {
            "title": sorted(
                {str(value) for value in self.graph.objects(None, CINE.title)},
                key=str.casefold,
            ),
            "director": sorted(
                {self.label(person) for person in self.graph.objects(None, CINE.directedBy)},
                key=str.casefold,
            ),
            "actor": sorted(
                {self.label(person) for person in self.graph.objects(None, CINE.hasActor)},
                key=str.casefold,
            ),
            "person": sorted(
                {
                    self.label(person)
                    for person in set(self.graph.objects(None, CINE.hasActor))
                    | set(self.graph.objects(None, CINE.directedBy))
                },
                key=str.casefold,
            ),
            "genre": sorted(
                {self.label(genre) for genre in self.graph.subjects(RDF.type, CINE.Genre)},
                key=str.casefold,
            ),
        }

        self.normalized_suggestions = {
            kind: [(normalize_text(value), value) for value in values]
            for kind, values in self.suggestion_options.items()
        }

    def _index_people(self) -> None:
        self.people_movies = {}
        self.people_roles = {}
        for predicate, role in ((CINE.hasActor, "actor"), (CINE.directedBy, "director")):
            for movie, person in self.graph.subject_objects(predicate):
                self.people_movies.setdefault(person, set()).add(movie)
                self.people_roles.setdefault(person, set()).add(role)

        self.graph.add((CINE.filmographySize, RDF.type, OWL.DatatypeProperty))
        self.graph.add((CINE.filmographySize, RDFS.domain, CINE.Person))
        self.graph.add((CINE.filmographySize, RDFS.range, XSD.integer))
        self.graph.add((CINE.filmographySize, RDFS.label, Literal("filmography size", lang="en")))

        for person, credits in self.people_movies.items():
            self.graph.set(
                (person, CINE.filmographySize, Literal(len(credits), datatype=XSD.integer))
            )

    def _build_explore_graph(self) -> None:
        self.explore_graph = Graph()

        self.explore_predicates = (
            RDF.type,
            RDFS.label,
            CINE.title,
            CINE.releaseYear,
            CINE.imdbRating,
            CINE.ratingVotes,
            CINE.durationMinutes,
            CINE.hasActor,
            CINE.directedBy,
            CINE.hasGenre,
        )

        for predicate in self.explore_predicates:
            for triple in self.graph.triples((None, predicate, None)):
                self.explore_graph.add(triple)

    def report(self) -> dict:
        try:
            return json.loads(self.report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def label(self, node) -> str:
        value = self.graph.value(node, RDFS.label)
        return str(value) if value is not None else str(node).rsplit("/", 1)[-1]

    def labels_for(self, movie, predicate) -> list[str]:
        return sorted(
            {self.label(node) for node in self.graph.objects(movie, predicate)}, key=str.casefold
        )

    def literal(self, movie, predicate, default="") -> str:
        value = self.graph.value(movie, predicate)
        return str(value) if value is not None else default

    def movie_card(self, movie) -> dict:
        imdb_id = self.literal(movie, CINE.imdbID)
        tmdb_id = self.literal(movie, CINE.tmdbID)
        external_links = [str(value) for value in self.graph.objects(movie, OWL.sameAs)]
        source_urls = {str(value) for value in self.graph.objects(movie, DCTERMS.source)}
        sources = [name for url, name in SOURCE_NAMES.items() if url in source_urls]
        entity_links = []
        for kind, predicate in (
            ("Actor", CINE.hasActor),
            ("Director", CINE.directedBy),
            ("Genre", CINE.hasGenre),
        ):
            for entity in self.graph.objects(movie, predicate):
                entity_url = next(
                    (
                        str(value)
                        for value in (
                            *self.graph.objects(entity, OWL.sameAs),
                            *self.graph.objects(entity, FOAF.page),
                        )
                        if str(value).startswith("http")
                    ),
                    "",
                )
                if entity_url:
                    entity_links.append(
                        {"name": self.label(entity), "type": kind, "url": entity_url}
                    )
        return {
            "id": imdb_id or (f"tmdb-{tmdb_id}" if tmdb_id else str(movie).rsplit("/", 1)[-1]),
            "uri": str(movie),
            "title": self.literal(movie, CINE.title, "Untitled"),
            "year": self.literal(movie, CINE.releaseYear),
            "runtime_minutes": self.literal(movie, CINE.durationMinutes),
            "description": self.literal(movie, CINE.description),
            "image": str(self.graph.value(movie, SCHEMA.image) or ""),
            "directors": self.labels_for(movie, CINE.directedBy),
            "actors": self.labels_for(movie, CINE.hasActor),
            "genres": self.labels_for(movie, CINE.hasGenre),
            "imdb_id": imdb_id,
            "rating": self.literal(movie, CINE.imdbRating) or self.literal(movie, CINE.tmdbRating),
            "rating_source": "IMDb"
            if self.graph.value(movie, CINE.imdbRating) is not None
            else ("TMDB" if self.graph.value(movie, CINE.tmdbRating) is not None else ""),
            "rating_votes": self.literal(movie, CINE.ratingVotes),
            "revenue": self.literal(movie, CINE.revenue),
            "wikidata_url": next(
                (link for link in external_links if "wikidata.org/entity/" in link), ""
            ),
            "dbpedia_url": next(
                (link for link in external_links if "dbpedia.org/resource/" in link), ""
            ),
            "entity_links": entity_links,
            "sources": sources,
        }

    def movie_uri(self, identifier: str):
        predicate = CINE.imdbID if identifier.startswith("tt") else CINE.tmdbID
        value = identifier.removeprefix("tmdb-")
        found = next(self.graph.subjects(predicate, Literal(value)), None)
        if found is None and identifier.startswith("https://example.org/cinegraph/movie/"):
            found = URIRef(identifier)
        return found

    def person_card(self, person) -> dict:
        credits = sorted(
            self.people_movies.get(person, set()),
            key=lambda movie: (
                -(
                    int(self.literal(movie, CINE.releaseYear))
                    if self.literal(movie, CINE.releaseYear).isdigit()
                    else 0
                ),
                self.literal(movie, CINE.title).casefold(),
            ),
        )
        same_as = [str(value) for value in self.graph.objects(person, OWL.sameAs)]
        pages = [str(value) for value in self.graph.objects(person, FOAF.page)]
        return {
            "uri": str(person),
            "name": self.label(person),
            "roles": sorted(self.people_roles.get(person, set())),
            "birth_date": self.literal(person, SCHEMA.birthDate),
            "death_date": self.literal(person, SCHEMA.deathDate),
            "description": self.literal(person, SCHEMA.description),
            "image": str(self.graph.value(person, SCHEMA.image) or ""),
            "movie_count": len(credits),
            "movies": [
                {
                    "title": self.literal(movie, CINE.title, "Untitled"),
                    "year": self.literal(movie, CINE.releaseYear),
                    "uri": str(movie),
                }
                for movie in credits[:5]
            ],
            "wikidata_url": next((url for url in same_as if "wikidata.org/entity/" in url), ""),
            "tmdb_url": next((url for url in pages if "themoviedb.org/person/" in url), ""),
            "wikipedia_url": next((url for url in pages if "wikipedia.org/wiki/" in url), ""),
        }

    @lru_cache(maxsize=16)
    def filtered_people(self, search_text, selected_role, minimum, year_from, year_to, ordering):
        filters = []
        if search_text:
            text = Literal(search_text).n3()
            filters.append(
                f"FILTER(CONTAINS(LCASE(STR(?name)), LCASE({text})) || "
                f"(BOUND(?description) && CONTAINS(LCASE(STR(?description)), LCASE({text}))))"
            )
        if selected_role == "actor":
            filters.append("?person a cine:Actor .")
        elif selected_role == "director":
            filters.append("?person a cine:Director .")
        if year_from:
            filters.append(
                f'FILTER(BOUND(?birthDate) && REGEX(STR(?birthDate), "^[0-9]{{4}}") && '
                f"xsd:integer(SUBSTR(STR(?birthDate), 1, 4)) >= {year_from})"
            )
        if year_to:
            filters.append(
                f'FILTER(BOUND(?birthDate) && REGEX(STR(?birthDate), "^[0-9]{{4}}") && '
                f"xsd:integer(SUBSTR(STR(?birthDate), 1, 4)) <= {year_to})"
            )
        order_clause = (
            "LCASE(STR(?name))" if ordering == "name" else "DESC(?movieCount) LCASE(STR(?name))"
        )
        query_text = f"""PREFIX cine: <https://example.org/cinegraph/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <https://schema.org/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT DISTINCT ?person ?name ?movieCount WHERE {{
  ?person a cine:Person ; rdfs:label ?name ; cine:filmographySize ?movieCount .
  FILTER(?movieCount >= {minimum})
  OPTIONAL {{ ?person schema:description ?description }}
  OPTIONAL {{ ?person schema:birthDate ?birthDate }}
  {" ".join(filters)}
}}
ORDER BY {order_clause}"""
        rows = self.graph.query(query_text)
        return tuple((row.person, int(row.movieCount)) for row in rows), query_text

    def recommendation_sparql(self, relation_type="all", bound_seed=None) -> str:
        relation_types = {
            "genre": CINE.hasGenre,
            "actor": CINE.hasActor,
            "director": CINE.directedBy,
        }
        relation_values = " ".join(f"<{relation}>" for relation in WEIGHTS)
        required_pattern = ""
        if relation_type in relation_types:
            required_relation = relation_types[relation_type]
            required_pattern = (
                f"?seed <{required_relation}> ?requiredShared . "
                f"?candidate a cine:Movie ; <{required_relation}> ?requiredShared ."
            )
        seed_pattern = f"VALUES ?seed {{ {bound_seed.n3()} }}" if bound_seed is not None else ""
        return f"""
        PREFIX cine: <https://example.org/cinegraph/ontology#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?candidate ?relation ?shared ?sharedName WHERE {{
          {seed_pattern}
          ?seed ?relation ?shared .
          ?candidate a cine:Movie ; ?relation ?shared .
          VALUES ?relation {{ {relation_values} }}
          {required_pattern}
          FILTER(?candidate != ?seed)
          OPTIONAL {{ ?shared rdfs:label ?sharedName }}
        }}
        """

    @lru_cache(maxsize=32)
    def ranked_recommendations(self, seed, relation_type="all") -> list[dict]:
        query = self.recommendation_sparql(relation_type)
        grouped = {}
        for row in self.graph.query(query, initBindings={"seed": seed}):
            uri = str(row.candidate)
            item = grouped.setdefault(uri, {"movie_uri": URIRef(uri), "score": 0, "reasons": []})
            predicate = URIRef(str(row.relation))
            reason = {
                "type": REASONS[predicate],
                "name": str(row.sharedName or self.label(row.shared)),
            }
            key = (reason["type"], reason["name"])
            if key not in {(v["type"], v["name"]) for v in item["reasons"]}:
                item["reasons"].append(reason)
                item["score"] += WEIGHTS[predicate]
        return sorted(
            grouped.values(),
            key=lambda item: (
                -item["score"],
                self.literal(item["movie_uri"], CINE.title).casefold(),
            ),
        )

    def recommendation_result(self, item) -> dict:
        return {
            "movie": self.movie_card(item["movie_uri"]),
            "score": item["score"],
            "reasons": item["reasons"],
        }

    def matching_movies(self, filters: dict) -> list:
        patterns = ["?movie a cine:Movie ; cine:title ?title ."]
        bindings = {}
        if filters.get("q"):
            patterns.append("FILTER(CONTAINS(LCASE(STR(?title)), LCASE(STR(?needle))))")
            bindings["needle"] = Literal(filters["q"])
        if filters.get("genre"):
            patterns.extend(
                [
                    "?movie cine:hasGenre ?genreNode .",
                    "?genreNode rdfs:label ?genreLabel .",
                    "FILTER(LCASE(STR(?genreLabel)) = LCASE(STR(?genreFilter)))",
                ]
            )
            bindings["genreFilter"] = Literal(filters["genre"])
        if filters.get("year_from") is not None:
            patterns.extend(
                [
                    "?movie cine:releaseYear ?yearFromValue .",
                    "FILTER(xsd:integer(STR(?yearFromValue)) >= ?yearFrom)",
                ]
            )
            bindings["yearFrom"] = Literal(filters["year_from"], datatype=XSD.integer)
        if filters.get("year_to") is not None:
            patterns.extend(
                [
                    "?movie cine:releaseYear ?yearToValue .",
                    "FILTER(xsd:integer(STR(?yearToValue)) <= ?yearTo)",
                ]
            )
            bindings["yearTo"] = Literal(filters["year_to"], datatype=XSD.integer)
        if filters.get("min_rating") is not None:
            patterns.extend(
                [
                    "?movie cine:imdbRating ?ratingFilterValue .",
                    "FILTER(?ratingFilterValue >= ?ratingFloor)",
                ]
            )
            bindings["ratingFloor"] = Literal(str(filters["min_rating"]), datatype=XSD.decimal)
        if filters.get("director"):
            patterns.extend(
                [
                    "?movie cine:directedBy ?directorNode .",
                    "?directorNode rdfs:label ?directorLabel .",
                    "FILTER(CONTAINS(LCASE(STR(?directorLabel)), LCASE(STR(?directorFilter))))",
                ]
            )
            bindings["directorFilter"] = Literal(filters["director"])
        if filters.get("actor"):
            patterns.extend(
                [
                    "?movie cine:hasActor ?actorNode .",
                    "?actorNode rdfs:label ?actorLabel .",
                    "FILTER(CONTAINS(LCASE(STR(?actorLabel)), LCASE(STR(?actorFilter))))",
                ]
            )
            bindings["actorFilter"] = Literal(filters["actor"])
        query = (
            """
        PREFIX cine: <https://example.org/cinegraph/ontology#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        SELECT DISTINCT ?movie WHERE {
        """
            + "\n".join(patterns)
            + "\n}"
        )
        return [row.movie for row in self.graph.query(query, initBindings=bindings)]

    def sort_movie_uris(self, movies: list, sort_by: str) -> None:
        def title(movie) -> str:
            return str(self.graph.value(movie, CINE.title) or "").casefold()

        def number(movie, predicate, cast):
            value = self.graph.value(movie, predicate)
            if value is None:
                return None
            try:
                return cast(str(value))
            except (TypeError, ValueError):
                return None

        sort_fields = {
            "year_desc": (CINE.releaseYear, int),
            "year_asc": (CINE.releaseYear, int),
            "rating_desc": (CINE.imdbRating, float),
            "votes_desc": (CINE.ratingVotes, int),
            "revenue_desc": (CINE.revenue, int),
        }
        if sort_by == "title":
            movies.sort(key=title)
            return
        predicate, cast = sort_fields[sort_by]
        if sort_by == "year_desc":
            movies.sort(
                key=lambda movie: (
                    number(movie, predicate, cast) is None,
                    -(number(movie, predicate, cast) or 0),
                    title(movie),
                )
            )
        elif sort_by == "year_asc":
            movies.sort(
                key=lambda movie: (
                    number(movie, predicate, cast) is None,
                    number(movie, predicate, cast) or 0,
                    title(movie),
                )
            )
        else:
            movies.sort(
                key=lambda movie: (
                    number(movie, predicate, cast) is None,
                    -(number(movie, predicate, cast) or 0),
                    title(movie),
                )
            )

    def graph_stats(self) -> dict:
        summary = self.report()
        return {
            "movies": len(set(self.graph.subjects(RDF.type, CINE.Movie))),
            "actors": len(set(self.graph.objects(None, CINE.hasActor))),
            "directors": len(set(self.graph.objects(None, CINE.directedBy))),
            "genres": len(set(self.graph.subjects(RDF.type, CINE.Genre))),
            "triples": len(self.graph),
            "sources": summary.get("source_status", {}),
            "generated_at": summary.get("generated_at_utc", ""),
            "source_count": summary.get("source_count", 0),
        }
