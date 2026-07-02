@echo off
REM JARVIS launcher for Windows — double-click to start the app.
REM (Right-click > Send to > Desktop to make a desktop shortcut.)
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo No virtual environment found - run the setup in setup\setup_windows.md first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run_app.py
if errorlevel 1 pause
