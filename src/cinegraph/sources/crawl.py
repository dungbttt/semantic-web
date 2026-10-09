from __future__ import annotations

import logging

from ..config import Settings
from .imdb import download_imdb_datasets
from .kaggle_csv import download_public_dataset

LOGGER = logging.getLogger(__name__)


def crawl_sources(settings: Settings | None = None) -> dict[str, dict]:
    """Fetch raw IMDb and Kaggle files only; do not call APIs or build RDF."""
    settings = settings or Settings()
    settings.raw_imdb.mkdir(parents=True, exist_ok=True)
    settings.raw_kaggle.mkdir(parents=True, exist_ok=True)

    basics_path, ratings_path = download_imdb_datasets(settings)
    status = {
        "IMDb": {
            "status": "ready",
            "files": [basics_path.name, ratings_path.name],
        }
    }

    catalog_files = list(settings.raw_kaggle.rglob("movies_metadata.csv"))
    local_csvs = list(settings.raw_kaggle.glob("*.csv"))
    kaggle_files = catalog_files or local_csvs
    if not kaggle_files:
        try:
            kaggle_files = download_public_dataset(settings.raw_kaggle, settings.kaggle_handle)
        except Exception as exc:
            LOGGER.warning("Kaggle dataset download skipped: %s", exc)
            status["Kaggle"] = {"status": "unavailable", "detail": str(exc)}
        else:
            status["Kaggle"] = {
                "status": "ready" if kaggle_files else "no_files",
                "files": [path.name for path in kaggle_files],
            }
    else:
        status["Kaggle"] = {
            "status": "ready",
            "files": [path.name for path in kaggle_files],
        }
    return status
