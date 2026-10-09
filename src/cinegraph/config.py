from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    """Read simple KEY=value entries without overriding the user's environment."""
    env_file = path or ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    min_imdb_votes: int = 50_000
    omdb_batch_size: int = 700
    imdb_basics_url: str = "https://datasets.imdbws.com/title.basics.tsv.gz"
    imdb_ratings_url: str = "https://datasets.imdbws.com/title.ratings.tsv.gz"
    kaggle_handle: str = "rounakbanik/the-movies-dataset"

    @property
    def raw_imdb(self) -> Path:
        return self.root / "data" / "raw" / "imdb"

    @property
    def raw_kaggle(self) -> Path:
        return self.root / "data" / "raw" / "kaggle"

    @property
    def omdb_cache(self) -> Path:
        return self.root / "data" / "cache" / "omdb"

    @property
    def processed(self) -> Path:
        return self.root / "data" / "processed"

    @property
    def rdf(self) -> Path:
        return self.root / "data" / "rdf"

    @property
    def reports(self) -> Path:
        return self.root / "data" / "reports"

    @property
    def omdb_api_key(self) -> str:
        load_dotenv()
        return os.getenv("OMDB_API_KEY", "").strip()

    @property
    def imdb_vote_threshold(self) -> int:
        load_dotenv()
        return max(0, int(os.getenv("CINEGRAPH_MIN_IMDB_VOTES", self.min_imdb_votes)))

    @property
    def omdb_request_budget(self) -> int:
        load_dotenv()
        return max(0, int(os.getenv("CINEGRAPH_OMDB_BATCH_SIZE", self.omdb_batch_size)))
