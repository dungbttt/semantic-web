@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Project Python environment not found. Run run_demo.bat once to set it up.
  exit /b 1
)

".venv\Scripts\python.exe" -c "import flask, rdflib, requests, kagglehub, pyshacl" >nul 2>nul
if errorlevel 1 (
  echo Installing missing project dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Dependency installation failed. Check your internet connection and try again.
    exit /b 1
  )
)

if not exist "data\rdf\movies.ttl" (
  echo RDF graph not found: data\rdf\movies.ttl
  echo Build it first with: .venv\Scripts\python.exe -m cinegraph.cli ingest
  exit /b 1
)

set "PYTHONPATH=%CD%\src"
echo Starting CineGraph from the existing RDF graph...
".venv\Scripts\python.exe" -m cinegraph.cli serve %*
