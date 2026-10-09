"""Shared RDF identifiers and source URLs used by ingestion and the web app."""

from rdflib import Namespace

BASE = "https://example.org/cinegraph/"
CINE = Namespace(BASE + "ontology#")
SCHEMA = Namespace("https://schema.org/")
PROV = Namespace("http://www.w3.org/ns/prov#")
WIKIDATA_URL = "https://www.wikidata.org/"
SOURCE_URLS = {
    "IMDb": "https://www.imdb.com/interfaces/",
    "Kaggle": "https://www.kaggle.com/datasets/rounakbanik/the-movies-dataset",
    "OMDb": "https://www.omdbapi.com/",
}
