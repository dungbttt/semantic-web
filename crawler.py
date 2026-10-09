"""Compatibility launcher for downloading raw source datasets only."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from cinegraph.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["crawl"]))
