@echo off
rem Starts the CodeSentinel dashboard on http://localhost:5180
cd /d "%~dp0frontend"
npm run dev
pause
