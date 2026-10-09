@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating the project virtual environment...
  where py >nul 2>nul
  if errorlevel 1 (python -m venv .venv) else (py -3 -m venv .venv)
  if errorlevel 1 (
    echo Python 3.10 or later is required. Install Python and run this file again.
    pause
    exit /b 1
  )
)

echo Installing project dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed. Check your Internet connection and try again.
  pause
  exit /b 1
)

set "PYTHONPATH=%CD%\src"
echo Downloading source data, building the RDF graph, and starting CineGraph...
".venv\Scripts\python.exe" -m cinegraph.cli demo
if errorlevel 1 (
  echo CineGraph could not start. See the error above and README.md for setup details.
  pause
  exit /b 1
)
pause
