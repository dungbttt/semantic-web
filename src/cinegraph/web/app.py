"""Flask application factory."""

from __future__ import annotations

from pathlib import Path

from flask import Flask

from ..config import ROOT
from .catalog import CatalogService
from .routes import register_routes


def create_app(graph_path: Path | None = None, report_path: Path | None = None) -> Flask:
    package_dir = Path(__file__).resolve().parent
    catalog = CatalogService(
        graph_path or ROOT / "data" / "rdf" / "movies.ttl",
        report_path or ROOT / "data" / "reports" / "pipeline.json",
    )
    app = Flask(
        __name__,
        template_folder=str(package_dir / "templates"),
        static_folder=str(package_dir / "static"),
    )
    app.config["CINEGRAPH"] = catalog.graph
    app.extensions["cinegraph_catalog"] = catalog
    register_routes(app, catalog)
    return app
