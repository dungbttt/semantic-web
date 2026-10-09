"""Execute parameterized SPARQL explorer questions against the catalog."""

from __future__ import annotations

from rdflib import Literal, URIRef
from rdflib.namespace import RDFS

from .catalog import CatalogService
from .queries import build_explorer_query
from .vocabulary import CINE

LOOKUP_KINDS = {
    "related_movies": "title",
    "movie_people": "title",
    "coactors_by_actor": "actor",
    "actors_by_director": "director",
    "actor_genre_profile": "actor",
}
NUMBER_TEMPLATES = {
    "genres_by_min_movies",
    "movies_by_min_cast",
}
TEXT_TEMPLATES = set(LOOKUP_KINDS)
RESULT_LIMIT = 100


class SparqlExplorer:
    def __init__(self, catalog: CatalogService):
        self.catalog = catalog

    def run(self, template: str, value: str) -> dict:
        if not value:
            raise ValueError("Enter a value for this query.")
        if len(value) > 160:
            raise ValueError("Search values must be 160 characters or fewer.")
        if template not in TEXT_TEMPLATES | NUMBER_TEMPLATES:
            raise ValueError("Invalid query template.")
        if template == "related_movies":
            return self._related_movies(value)

        number = self._number(template, value) if template in NUMBER_TEMPLATES else 0
        parameter = self._lookup_parameter(template, value)
        query = build_explorer_query(template, parameter, int(number))
        try:
            result = self.catalog.explore_graph.query(query)
            columns = [str(variable) for variable in result.vars]
            rows = [["" if term is None else str(term) for term in row] for row in result]
        except Exception as exc:
            raise ValueError(f"Could not run the RDF query: {exc}") from exc
        return {"columns": columns, "rows": rows, "count": len(rows), "sparql": query}

    @staticmethod
    def _number(template: str, value: str) -> int:
        try:
            number = int(value)
        except ValueError as exc:
            raise ValueError("This query requires a valid number.") from exc
        if number < 1:
            raise ValueError("The value must be at least 1.")
        return number

    def _lookup_parameter(self, template: str, value: str) -> str:
        kind = LOOKUP_KINDS.get(template)
        if kind is None:
            return Literal(value).n3()
        canonical = next(
            (
                name
                for name in self.catalog.suggestion_options[kind]
                if name.casefold() == value.casefold()
            ),
            value,
        )
        predicate = CINE.title if kind == "title" else RDFS.label
        # Preserve the RDF literal's language tag when binding an exact label.
        term = next(
            (
                term
                for term in self.catalog.graph.objects(None, predicate)
                if str(term).casefold() == canonical.casefold()
            ),
            Literal(canonical),
        )
        return term.n3()

    def _related_movies(self, value: str) -> dict:
        seed = next(
            (
                movie
                for movie, title in self.catalog.graph.subject_objects(CINE.title)
                if str(title).casefold() == value.casefold()
            ),
            None,
        )
        bound_seed = seed or URIRef("https://example.org/cinegraph/movie/__not_found__")
        try:
            recommendations = (
                self.catalog.ranked_recommendations(seed)[:RESULT_LIMIT] if seed is not None else []
            )
        except Exception as exc:
            raise ValueError(f"Could not run the RDF query: {exc}") from exc
        rows = [
            [
                self.catalog.literal(item["movie_uri"], CINE.title),
                str(item["score"]),
                "; ".join(f"{reason['type']}: {reason['name']}" for reason in item["reasons"]),
            ]
            for item in recommendations
        ]
        return {
            "columns": ["title", "score", "reasons"],
            "rows": rows,
            "count": len(rows),
            "sparql": self.catalog.recommendation_sparql("all", bound_seed),
        }
