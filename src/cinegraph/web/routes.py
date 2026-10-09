"""HTTP request validation and responses for the CineGraph web API."""

from __future__ import annotations

import json
import math
import re

from flask import Flask, Response, jsonify, render_template, request
from rdflib import URIRef
from rdflib.namespace import OWL, RDF

from .catalog import CatalogService
from .explorer import SparqlExplorer
from .neighborhood import GraphNeighborhood
from .text import normalize_text
from .vocabulary import CINE


def register_routes(app: Flask, catalog: CatalogService) -> None:
    explorer = SparqlExplorer(catalog)
    neighborhood = GraphNeighborhood(catalog)

    @app.get("/")
    def index():
        return render_template("index.html", stats=catalog.graph_stats())

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "triples": len(catalog.graph)})

    @app.get("/api/stats")
    def stats():
        return jsonify(catalog.graph_stats())

    @app.get("/api/people")
    def search_people():
        query = request.args.get("q", "").strip()
        role = request.args.get("role", "all")
        sort_by = request.args.get("sort", "movies")
        if role not in {"all", "actor", "director"}:
            return jsonify({"error": "Invalid people role."}), 400
        if sort_by not in {"name", "movies"}:
            return jsonify({"error": "Invalid sort option."}), 400
        try:
            min_movies = int(request.args.get("min_movies", "1") or "1")
            birth_from = int(request.args.get("birth_from", "") or "0")
            birth_to = int(request.args.get("birth_to", "") or "0")
        except ValueError:
            return jsonify(
                {"error": "Minimum movie credits and birth years must be integers."}
            ), 400
        if min_movies < 1:
            return jsonify({"error": "Minimum movie credits must be at least 1."}), 400
        if any(year and not 1000 <= year <= 9999 for year in (birth_from, birth_to)):
            return jsonify({"error": "Birth years must be between 1000 and 9999."}), 400
        if birth_from and birth_to and birth_from > birth_to:
            return jsonify(
                {
                    "error": "The starting birth year must be earlier than or equal to the ending year."
                }
            ), 400
        try:
            page = max(1, int(request.args.get("page", "1")))
        except ValueError:
            return jsonify({"error": "Page must be an integer."}), 400

        try:
            matched, sparql = catalog.filtered_people(
                query, role, min_movies, birth_from, birth_to, sort_by
            )
        except Exception as exc:
            return jsonify({"error": f"Could not run the people search query: {exc}"}), 400
        page_size = 6
        count = len(matched)
        pages = math.ceil(count / page_size)
        if pages and page > pages:
            return jsonify({"error": "Result page not found."}), 404
        start = (page - 1) * page_size
        results = []
        for person, movie_count in matched[start : start + page_size]:
            card = catalog.person_card(person)
            card["movie_count"] = movie_count
            results.append(card)
        return jsonify(
            {
                "count": count,
                "people": results,
                "page": page,
                "pages": pages,
                "sparql": sparql,
            }
        )

    @app.get("/api/status")
    def pipeline_status():
        graph_summary = catalog.graph_stats()
        return jsonify({"statistics": graph_summary, "pipeline": catalog.report()})

    @app.get("/api/movies")
    def search_movies():
        year_from_raw = request.args.get("year_from", "").strip()
        year_to_raw = request.args.get("year_to", "").strip()
        min_rating_raw = request.args.get("min_rating", "").strip()
        try:
            year_from = int(year_from_raw) if year_from_raw else None
            year_to = int(year_to_raw) if year_to_raw else None
            min_rating = float(min_rating_raw) if min_rating_raw else None
        except ValueError:
            return jsonify(
                {"error": "Years must be integers and IMDb ratings must be numeric."}
            ), 400
        if any(year is not None and not 0 <= year <= 9999 for year in (year_from, year_to)):
            return jsonify({"error": "Years must be between 0 and 9999."}), 400
        if year_from is not None and year_to is not None and year_from > year_to:
            return jsonify(
                {"error": "The starting year must be earlier than or equal to the ending year."}
            ), 400
        if min_rating is not None and (not math.isfinite(min_rating) or not 0 <= min_rating <= 10):
            return jsonify({"error": "IMDb ratings must be between 0 and 10."}), 400
        sort_by = request.args.get("sort", "rating_desc")
        allowed_sorts = {
            "title",
            "year_desc",
            "year_asc",
            "rating_desc",
            "votes_desc",
            "revenue_desc",
        }
        if sort_by not in allowed_sorts:
            return jsonify({"error": "Invalid sort option."}), 400
        try:
            limit = min(max(int(request.args.get("limit", "200")), 1), 250)
        except ValueError:
            return jsonify({"error": "The result limit must be an integer."}), 400

        filters = {
            "q": request.args.get("q", "").strip(),
            "genre": request.args.get("genre", "").strip(),
            "year_from": year_from,
            "year_to": year_to,
            "min_rating": min_rating,
            "director": request.args.get("director", "").strip(),
            "actor": request.args.get("actor", "").strip(),
        }
        movie_uris = catalog.matching_movies(filters)
        catalog.sort_movie_uris(movie_uris, sort_by)
        count = len(movie_uris)
        movies = [catalog.movie_card(uri) for uri in movie_uris[:limit]]
        return jsonify({"count": count, "shown": len(movies), "movies": movies})

    @app.get("/api/filter-options")
    def filter_options():
        genres = sorted(
            {catalog.label(genre) for genre in catalog.graph.subjects(RDF.type, CINE.Genre)},
            key=str.casefold,
        )
        years = []
        for value in catalog.graph.objects(None, CINE.releaseYear):
            try:
                years.append(int(str(value)))
            except ValueError:
                continue
        return jsonify(
            {
                "genres": genres,
                "year_min": min(years) if years else None,
                "year_max": max(years) if years else None,
            }
        )

    @app.get("/api/suggestions")
    def entity_suggestions():
        kind = request.args.get("type", "")
        query = normalize_text(request.args.get("q", ""))
        if kind not in catalog.normalized_suggestions:
            return jsonify({"error": "Invalid suggestion type."}), 400
        if len(query) < 2:
            return jsonify({"suggestions": []})
        matches = [
            value
            for normalized, value in catalog.normalized_suggestions[kind]
            if query in normalized
        ][:20]
        return jsonify({"suggestions": matches})

    @app.get("/api/recommend/<path:identifier>")
    def recommend(identifier):
        seed = catalog.movie_uri(identifier)
        if seed is None:
            return jsonify({"error": "Movie not found in the graph."}), 404
        relation_type = request.args.get("type", "all")
        if relation_type not in {"all", "genre", "actor", "director"}:
            return jsonify({"error": "Invalid related-movie type."}), 400
        try:
            page_number = int(request.args.get("page", "1"))
        except ValueError:
            return jsonify({"error": "Page must be an integer."}), 400
        if page_number < 1:
            return jsonify({"error": "Page must be at least 1."}), 400
        page_size = 8
        all_recommendations = catalog.ranked_recommendations(seed, relation_type)
        total = len(all_recommendations)
        total_pages = math.ceil(total / page_size)
        if total_pages and page_number > total_pages:
            return jsonify({"error": "Related-movie page not found."}), 404
        start = (page_number - 1) * page_size
        page = all_recommendations[start : start + page_size]
        return jsonify(
            {
                "seed": catalog.movie_card(seed),
                "type": relation_type,
                "recommendations": [catalog.recommendation_result(item) for item in page],
                "total": total,
                "page": page_number,
                "pages": total_pages,
            }
        )

    @app.get("/api/ask")
    def ask_graph():
        question = request.args.get("q", "").strip()
        normalized = normalize_text(question)
        if not normalized:
            return jsonify(
                {
                    "answer": "Ask about a movie, director, actor, or genre.",
                    "results": [],
                    "reasons": [],
                }
            )
        all_movies = list(catalog.graph.subjects(RDF.type, CINE.Movie))
        matched = [
            (len(normalize_text(catalog.literal(movie, CINE.title))), movie)
            for movie in all_movies
            if normalize_text(catalog.literal(movie, CINE.title)) in normalized
        ]
        seed = max(matched, default=(0, None), key=lambda item: item[0])[1]
        if seed is not None and any(
            word in normalized for word in ("giong", "tuong tu", "similar", "like")
        ):
            recs = [
                catalog.recommendation_result(item)
                for item in catalog.ranked_recommendations(seed)[:8]
            ]
            return jsonify(
                {
                    "answer": f"Recommendations based on shared RDF relationships with {catalog.literal(seed, CINE.title)}.",
                    "results": [item["movie"] for item in recs],
                    "reasons": [
                        f"{item['movie']['title']}: "
                        + ", ".join(f"{r['type']} — {r['name']}" for r in item["reasons"])
                        for item in recs
                    ],
                }
            )
        relation_options = [
            (("dao dien", "director", "directed by"), CINE.Person, CINE.directedBy, "director"),
            (("dien vien", "actor", "starring", "cast"), CINE.Person, CINE.hasActor, "actor"),
            (("the loai", "genre"), CINE.Genre, CINE.hasGenre, "genre"),
        ]
        for hints, entity_class, predicate, relation_name in relation_options:
            if any(hint in normalized for hint in hints):
                entities = []
                for entity in catalog.graph.subjects(RDF.type, entity_class):
                    entity_label = normalize_text(catalog.label(entity))
                    if entity_label and entity_label in normalized:
                        entities.append((len(entity_label), entity))
                entity = max(entities, default=(0, None), key=lambda item: item[0])[1]
                if entity is not None:
                    linked = [
                        row.movie
                        for row in catalog.graph.query(
                            "PREFIX cine: <https://example.org/cinegraph/ontology#> SELECT DISTINCT ?movie WHERE { ?movie a cine:Movie ; ?relation ?entity . }",
                            initBindings={"relation": predicate, "entity": entity},
                        )
                    ]
                    results = sorted(
                        [catalog.movie_card(uri) for uri in linked],
                        key=lambda item: item["title"].casefold(),
                    )
                    name = catalog.label(entity)
                    return jsonify(
                        {
                            "answer": f"Found {len(results)} movies connected to {relation_name} {name}.",
                            "results": results,
                            "reasons": [
                                f"{item['title']} — {relation_name}: {name}" for item in results
                            ],
                        }
                    )
        if seed is not None:
            item = catalog.movie_card(seed)
            return jsonify(
                {
                    "answer": f"Knowledge graph details for {item['title']}.",
                    "results": [item],
                    "reasons": [],
                }
            )
        return jsonify(
            {
                "answer": "No matching entity found. Try a movie, director, actor, or genre in the catalog.",
                "results": [],
                "reasons": [],
            }
        )

    @app.get("/api/linked/<path:identifier>")
    def linked_data(identifier):
        movie = catalog.movie_uri(identifier)
        if movie is None:
            return jsonify({"error": "Movie not found."}), 404
        return jsonify(
            {
                "movie": catalog.movie_card(movie),
                "sameAs": sorted(str(v) for v in catalog.graph.objects(movie, OWL.sameAs)),
            }
        )

    @app.post("/api/sparql-explore")
    def sparql_explore():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"error": "Request must be a JSON object."}), 400
        try:
            result = explorer.run(
                str(payload.get("template", "")), str(payload.get("value", "")).strip()
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result)

    @app.get("/api/neighborhood")
    def graph_neighborhood():
        entity_type = request.args.get("type", "")
        value = request.args.get("value", "").strip()
        try:
            result = neighborhood.run(entity_type, value)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result)

    @app.route("/sparql", methods=["GET", "POST"])
    def sparql_endpoint():
        payload = (request.get_json(silent=True) or {}) if request.is_json else {}
        if not isinstance(payload, dict):
            return jsonify({"error": "Request must be a JSON object."}), 400
        query_text = str(
            payload.get("query", "") if request.is_json else request.values.get("query", "")
        ).strip()
        if not query_text:
            return jsonify({"error": "Send a SPARQL SELECT query in the 'query' field."}), 400
        if not re.match(
            r"(?is)^\s*(?:(?:PREFIX\s+\S+\s+<[^>]+>|BASE\s*<[^>]+>)\s*)*SELECT\b", query_text
        ):
            return jsonify({"error": "This demo only allows SPARQL SELECT queries."}), 400
        if re.search(r"(?i)\bSERVICE\b", query_text):
            return jsonify({"error": "SERVICE is disabled in this local demo endpoint."}), 400
        try:
            result = catalog.graph.query(query_text)
            variables = [str(variable) for variable in result.vars]
            bindings = []
            for row in result:
                values = {}
                for key, term in zip(variables, row):
                    if term is None:
                        continue
                    value = (
                        {"type": "uri", "value": str(term)}
                        if isinstance(term, URIRef)
                        else {"type": "literal", "value": str(term)}
                    )
                    if getattr(term, "language", None):
                        value["xml:lang"] = term.language
                    if getattr(term, "datatype", None):
                        value["datatype"] = str(term.datatype)
                    values[key] = value
                bindings.append(values)
            return Response(
                json.dumps(
                    {"head": {"vars": variables}, "results": {"bindings": bindings}},
                    ensure_ascii=False,
                ),
                mimetype="application/sparql-results+json",
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400
