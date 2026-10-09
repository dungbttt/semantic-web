from __future__ import annotations

import argparse
import logging
import threading
import webbrowser

from .config import Settings
from .sources.crawl import crawl_sources
from .transform.pipeline import run_pipeline


def _serve(open_browser: bool = True) -> None:
    from .web.app import create_app

    settings = Settings()
    app = create_app(settings.rdf / "movies.ttl", settings.reports / "pipeline.json")
    url = "http://127.0.0.1:5000"
    print(f"CineGraph is running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open_new_tab(url)).start()
    app.run(host="127.0.0.1", port=5000, debug=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cinegraph", description="CineGraph semantic movie catalog"
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("demo", help="ingest data, create RDF, and open the web demo")
    subparsers.add_parser("crawl", help="download raw IMDb and Kaggle data only")
    subparsers.add_parser("ingest", help="run source adapters and build the RDF graph")
    serve_parser = subparsers.add_parser("serve", help="serve the most recently generated graph")
    serve_parser.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    command = args.command or "demo"
    if command == "crawl":
        status = crawl_sources(Settings())
        for name in ("IMDb", "Kaggle"):
            source = status.get(name, {})
            detail = ", ".join(source.get("files", [])) or source.get("detail", "")
            print(f"{name}: {source.get('status', 'unknown')}" + (f" — {detail}" if detail else ""))
        print("Raw source data is ready under data/raw/. No OMDb calls or RDF build were run.")
        return 0 if status.get("IMDb", {}).get("status") == "ready" else 1
    if command in {"demo", "ingest"}:
        summary = run_pipeline(Settings())
        print(
            f"Built {summary['record_count']} movie records and {summary['triple_count']:,} RDF triples."
        )
        for name in ("IMDb", "Kaggle", "OMDb"):
            source = summary["source_status"].get(name, {})
            detail = source.get("records", source.get("status", "unknown"))
            print(f"{name}: {source.get('status', 'unknown')} ({detail})")
        selection = summary["source_status"].get("Catalog selection", {})
        if selection:
            print(
                "Catalog: "
                f"{selection.get('records', 0)} movies with IMDb + Kaggle + OMDb "
                f"({selection.get('excluded_records', 0)} excluded)"
            )
        linked_entities = summary["source_status"].get("Linked Entities", {})
        if linked_entities.get("status") == "resolved":
            print(
                "Linked entities: "
                f"{linked_entities.get('people_linked_to_wikidata', 0)}/"
                f"{linked_entities.get('people_with_tmdb_ids', 0)} people, "
                f"{linked_entities.get('genres_linked_to_wikidata', 0)}/"
                f"{linked_entities.get('genres_with_supported_labels', 0)} genres to Wikidata."
            )
        person_profiles = summary["source_status"].get("Person Profiles", {})
        if person_profiles.get("status") in {"resolved", "partial"}:
            print(
                "Wikidata person profiles: "
                f"{person_profiles.get('profiles_with_data', 0)}/"
                f"{person_profiles.get('linked_people', 0)} linked people."
            )
        validation = summary.get("validation", {})
        if validation:
            print(
                f"SHACL: {validation.get('status', 'unknown')} "
                f"({validation.get('result_count', 0)} finding(s))."
            )
        if command == "ingest":
            print("RDF graph: data/rdf/movies.ttl")
            print("Pipeline report: data/reports/pipeline.json")
            return 0
    _serve(open_browser=not getattr(args, "no_browser", False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
