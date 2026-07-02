#!/bin/bash
# JARVIS launcher for macOS.
# One-time setup: chmod +x launchers/JARVIS.command
# Then double-click this file in Finder (or drag it to the Dock).
cd "$(dirname "$0")/.." || exit 1
if [ ! -f .venv/bin/python ]; then
  echo "No virtual environment found — run the setup in setup/setup_macos.md first."
  read -r -p "Press Enter to close..."
  exit 1
fi
exec .venv/bin/python run_app.py
