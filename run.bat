@echo off
rem ======================================================================
rem  CodeSentinel - one-click launcher for Windows
rem  Double-click this file. The first run installs everything (a few
rem  minutes); later runs start in seconds.
rem  Needs: Python 3.12+ and Node.js 20+ (links shown if missing).
rem ======================================================================
setlocal EnableExtensions
title CodeSentinel launcher
cd /d "%~dp0"

set "API_PORT=8010"
set "WEB_PORT=5180"
set "WEB_URL=http://localhost:%WEB_PORT%"

echo.
echo   CodeSentinel - autonomous AI DevOps agent
echo   -----------------------------------------
echo.

rem ---------- already running? just open it ----------
netstat -ano | findstr /r /c:":%WEB_PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    netstat -ano | findstr /r /c:":%API_PORT% .*LISTENING" >nul 2>&1
    if not errorlevel 1 (
        echo   CodeSentinel is already running.
        goto open_browser
    )
)

rem ---------- folder path short enough for Windows' 260-character limit ----------
rem Some Python packages contain very long file names; deep folders push them past the limit.
set "CS_DIR=%~dp0"
for /f %%L in ('powershell -NoProfile -Command "$env:CS_DIR.Length"') do set "CS_DIR_LEN=%%L"
if %CS_DIR_LEN% GTR 90 goto path_too_long

rem ---------- Python 3.12+ ----------
set "PY="
where py >nul 2>&1 && py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY goto need_python
echo   [ok] Python found

rem ---------- Node.js 20+ ----------
where node >nul 2>&1 || goto need_node
node -e "process.exit(+process.versions.node.split('.')[0] >= 20 ? 0 : 1)" >nul 2>&1 || goto need_node
echo   [ok] Node.js found

rem ---------- backend: virtualenv + dependencies ----------
if not exist "backend\.venv\Scripts\python.exe" (
    echo   [..] Creating the Python environment - first run only
    %PY% -m venv "backend\.venv" || goto failed
)
fc /b "backend\requirements.txt" "backend\.venv\requirements.installed" >nul 2>&1
if errorlevel 1 (
    echo   [..] Installing backend packages - this can take a few minutes
    "backend\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r "backend\requirements.txt" || goto failed
    copy /y "backend\requirements.txt" "backend\.venv\requirements.installed" >nul
)
echo   [ok] Backend ready

rem ---------- backend: .env with the Gemini key ----------
if not exist "backend\.env" (
    copy /y "backend\.env.example" "backend\.env" >nul
    echo.
    echo   CodeSentinel uses Google Gemini - free, no credit card.
    echo   Get a key at https://aistudio.google.com  ^(Get API key - Create API key^)
    echo   Press Enter to skip: you can still watch recorded runs, and add the key
    echo   later in backend\.env
    echo.
    set /p "GEMINI_KEY=  Paste your Gemini API key: "
    call :save_key
)

rem ---------- frontend: packages + .env ----------
fc /b "frontend\package-lock.json" "frontend\node_modules\.package-lock.installed" >nul 2>&1
if errorlevel 1 (
    echo   [..] Installing dashboard packages - first run only
    pushd frontend
    call npm install --no-audit --no-fund --loglevel=error || (popd & goto failed)
    popd
    copy /y "frontend\package-lock.json" "frontend\node_modules\.package-lock.installed" >nul
)
if not exist "frontend\.env" copy /y "frontend\.env.example" "frontend\.env" >nul
echo   [ok] Dashboard ready

rem ---------- start both servers in their own windows ----------
echo.
echo   Starting the API on port %API_PORT% and the dashboard on port %WEB_PORT%...
start "CodeSentinel API - close to stop" /d "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --port %API_PORT%"
start "CodeSentinel Dashboard - close to stop" /d "%~dp0frontend" cmd /k "npm run dev"

rem wait up to ~60s for the dashboard to answer
powershell -NoProfile -Command "$u='%WEB_URL%'; for($i=0;$i -lt 60;$i++){ try { if((Invoke-WebRequest -UseBasicParsing $u -TimeoutSec 2).StatusCode -eq 200){ exit 0 } } catch {}; Start-Sleep 1 }; exit 1"
if errorlevel 1 (
    echo   The dashboard is taking longer than usual - check the two new windows for errors.
)

:open_browser
echo.
echo   Open %WEB_URL% in your browser  ^(API docs: http://localhost:%API_PORT%/docs^)
if not defined CODESENTINEL_NO_BROWSER start "" "%WEB_URL%"
echo   To stop CodeSentinel, close the "CodeSentinel API" and "CodeSentinel Dashboard" windows.
echo.
if not defined CODESENTINEL_NO_PAUSE pause
exit /b 0

rem ---------- helpers ----------
:save_key
if "%GEMINI_KEY%"=="" (
    echo   Skipped - add GEMINI_API_KEY to backend\.env whenever you like.
    exit /b 0
)
powershell -NoProfile -Command "$k=$env:GEMINI_KEY.Trim(); (Get-Content 'backend\.env') -replace '^GEMINI_API_KEY=.*', ('GEMINI_API_KEY=' + $k) | Set-Content -Encoding ascii 'backend\.env'"
echo   [ok] Key saved to backend\.env  ^(this file is never uploaded to GitHub^)
exit /b 0

:path_too_long
echo   [!!] This folder's path is too long for Windows - %CS_DIR_LEN% characters, the limit here is 90:
echo        %CS_DIR%
echo        Move the project folder somewhere shorter, for example C:\CodeSentinel,
echo        and double-click run.bat again.
goto stop

:need_python
echo   [!!] Python 3.12 or newer is required.
echo        Download it from https://www.python.org/downloads/
echo        During setup, tick "Add python.exe to PATH". Then double-click run.bat again.
goto stop

:need_node
echo   [!!] Node.js 20 or newer is required.
echo        Download the LTS version from https://nodejs.org/  then double-click run.bat again.
goto stop

:failed
echo.
echo   [!!] Setup failed - see the messages above. Check your internet connection and try again.
echo        If the error mentions "Long Path", move this folder somewhere shorter,
echo        for example C:\CodeSentinel, and double-click run.bat again.
goto stop

:stop
echo.
if not defined CODESENTINEL_NO_PAUSE pause
exit /b 1
