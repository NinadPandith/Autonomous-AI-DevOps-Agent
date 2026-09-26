@echo off
rem Starts the CodeSentinel API on http://localhost:8010 (docs: http://localhost:8010/docs)
cd /d "%~dp0backend"
".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8010
pause
