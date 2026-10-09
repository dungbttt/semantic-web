"""Offline regression checks for RDF construction and the public web API."""

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from rdflib import Graph, Literal
from rdflib.compare import isomorphic
from rdflib.namespace import OWL, RDF, RDFS, XSD

from cinegraph.config import ROOT
from cinegraph.transform.rdf_builder import build_graph
from cinegraph.transform.validation import validate_graph
from cinegraph.vocabulary import CINE, PROV, SOURCE_URLS
from cinegraph.web.app import create_app

ONTOLOGY = ROOT / "ontology" / "cinegraph.ttl"
SHAPES = ROOT / "ontology" / "cinegraph.shacl.ttl"


def sample_records():
    return [
        {
            "imdb_id": f"tt{index}",
            "title": title,
            "year": 2020 + index,
            "runtime_minutes": 120.0,
            "rating": rating,
            "rating_votes": 60000,
            "genres": ["Drama"],
            "actors": ["Alex Example"],
            "directors": ["Alex Example"],
            "person_ids": [
                {"name": "Alex Example", "role": role, "tmdb_id": "123"}
                for role in ("Actor", "Director")
            ],
            "plot": "An example plot.",
            "sources": {"IMDb": True, "Kaggle": True, "OMDb": True},
            "field_sources": {"title": "IMDb", "plot": "OMDb"},
            "wikidata_uri": f"http://www.wikidata.org/entity/Q{index}",
        }
        for index, title, rating in [(1, "First Film", 8.5), (2, "Second Film", 7.0)]
    ]


class RdfRegressionTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_graph(sample_records(), ONTOLOGY)
        self.movies = list(self.graph.subjects(RDF.type, CINE.Movie))

    def test_decimal_literals_validate_before_and_after_serialization(self):
        for predicate in (CINE.durationMinutes, CINE.imdbRating):
            for literal in self.graph.objects(None, predicate):
                self.assertIsInstance(literal.value, Decimal)
                self.assertEqual(literal.datatype, XSD.decimal)
        reparsed = Graph().parse(data=self.graph.serialize(format="turtle"), format="turtle")
        self.assertTrue(isomorphic(self.graph, reparsed))
        for graph in (self.graph, reparsed):
            summary, _ = validate_graph(graph, SHAPES)
            self.assertTrue(summary["conforms"], summary)
            self.assertEqual(summary["result_count"], 0)

    def test_missing_and_duplicate_imdb_ids_are_rejected(self):
        movie = self.movies[0]
        original = self.graph.value(movie, CINE.imdbID)
        self.graph.remove((movie, CINE.imdbID, None))
        self.assertFalse(validate_graph(self.graph, SHAPES)[0]["conforms"])
        self.graph.add((movie, CINE.imdbID, original))
        self.graph.add((movie, CINE.imdbID, Literal("tt999")))
        self.assertFalse(validate_graph(self.graph, SHAPES)[0]["conforms"])

    def test_text_ranges_match_language_tagged_data(self):
        for predicate in (CINE.title, CINE.description):
            self.assertEqual(self.graph.value(predicate, RDFS.range), RDF.langString)
            for value in self.graph.objects(None, predicate):
                self.assertEqual(value.language, "en")

    def test_shared_person_identity_preserves_both_roles_and_provenance(self):
        people = set(self.graph.subjects(RDF.type, CINE.Person))
        self.assertEqual(len(people), 1)
        person = next(iter(people))
        self.assertIn((person, RDF.type, CINE.Actor), self.graph)
        self.assertIn((person, RDF.type, CINE.Director), self.graph)
        for movie in self.movies:
            self.assertIn((movie, CINE.hasActor, person), self.graph)
            self.assertIn((movie, CINE.directedBy, person), self.graph)
            self.assertEqual(len(list(self.graph.objects(movie, OWL.sameAs))), 1)
            sources = {
                str(self.graph.value(node, CINE.fieldName)): str(
                    self.graph.value(node, PROV.wasDerivedFrom)
                )
                for node in self.graph.objects(movie, CINE.hasFieldProvenance)
            }
            self.assertEqual(sources, {"title": SOURCE_URLS["IMDb"], "plot": SOURCE_URLS["OMDb"]})


class WebRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        folder = Path(cls.temp.name)
        graph_path = folder / "movies.ttl"
        build_graph(sample_records(), ONTOLOGY).serialize(graph_path, format="turtle")
        report_path = folder / "pipeline.json"
        report_path.write_text(json.dumps({"record_count": 2}), encoding="utf-8")
        cls.app = create_app(graph_path, report_path)
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_home_and_filter_search(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        response = self.client.get("/api/movies?genre=Drama&min_rating=8")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["count"], 1)
        self.assertEqual(response.json["movies"][0]["title"], "First Film")

    def test_invalid_filters_remain_rejected(self):
        for query in ("min_rating=nan", "year_from=2025&year_to=2000", "limit=invalid"):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(f"/api/movies?{query}").status_code, 400)

    def test_people_and_derived_recommendations(self):
        people = self.client.get("/api/people?q=Alex&role=actor")
        self.assertEqual(people.status_code, 200)
        self.assertEqual(people.json["count"], 1)
        related = self.client.get("/api/recommend/tt1?type=all")
        self.assertEqual(related.status_code, 200)
        self.assertEqual(related.json["total"], 1)
        self.assertEqual(related.json["recommendations"][0]["movie"]["id"], "tt2")
        self.assertEqual(len(related.json["recommendations"][0]["reasons"]), 3)

    def test_preset_query_preserves_language_tagged_lookup(self):
        response = self.client.post(
            "/api/sparql-explore", json={"template": "movie_people", "value": "First Film"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["count"], 2)
        self.assertIn('"First Film"@en', response.json["sparql"])

    def test_sparql_result_format_and_restricted_operations(self):
        query = f"SELECT ?title WHERE {{ ?movie <{CINE.title}> ?title }}"
        response = self.client.post("/sparql", json={"query": query})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/sparql-results+json")
        bindings = response.json["results"]["bindings"]
        self.assertEqual(len(bindings), 2)
        self.assertEqual(bindings[0]["title"]["xml:lang"], "en")
        for forbidden in (
            "DELETE WHERE { ?s ?p ?o }",
            "SELECT ?s WHERE { SERVICE <https://example.org/> { ?s ?p ?o } }",
        ):
            self.assertEqual(
                self.client.post("/sparql", json={"query": forbidden}).status_code, 400
            )


if __name__ == "__main__":
    unittest.main()
