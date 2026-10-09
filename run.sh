#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RDF_FILE="$PROJECT_DIR/data/rdf/movies.ttl"

if [[ ! -f "$RDF_FILE" ]]; then
  echo "RDF graph not found: $RDF_FILE" >&2
  echo "Build it first with: python -m cinegraph.cli ingest" >&2
  exit 1
fi

if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON="$PROJECT_DIR/.venv/bin/python"
  export PYTHONPATH="$PROJECT_DIR/src"
elif [[ -x "$PROJECT_DIR/.venv/Scripts/python.exe" ]] && command -v cygpath >/dev/null 2>&1; then
  # Git Bash on Windows: convert MSYS paths for the native Windows interpreter.
  PYTHON="$(cygpath -u "$PROJECT_DIR/.venv/Scripts/python.exe")"
  export PYTHONPATH="$(cygpath -w "$PROJECT_DIR/src")"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
  export PYTHONPATH="$PROJECT_DIR/src"
elif command -v python >/dev/null 2>&1; then
  PYTHON="$(command -v python)"
  export PYTHONPATH="$PROJECT_DIR/src"
else
  echo "Python was not found. Create a virtual environment and install requirements.txt." >&2
  exit 1
fi

cd "$PROJECT_DIR"
exec "$PYTHON" -m cinegraph.cli serve "$@"
