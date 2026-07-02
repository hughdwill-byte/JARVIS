"""JARVIS desk assistant package."""

import sys

# Fail early with instructions instead of a confusing TypeError deep in the code.
if sys.version_info < (3, 10):  # noqa: UP036
    sys.exit(
        "\nJARVIS needs Python 3.10 or newer - this is Python "
        + sys.version.split()[0] + ".\n\n"
        "Your virtual environment was created with an old Python. Fix (from the JARVIS folder):\n\n"
        "  macOS:\n"
        "    brew install python@3.12\n"
        "    deactivate; rm -rf .venv\n"
        "    python3.12 -m venv .venv\n"
        "    source .venv/bin/activate\n"
        "    pip install -r requirements.txt\n\n"
        "  Windows (PowerShell):\n"
        "    install Python 3.12 from python.org (tick 'Add to PATH'), then:\n"
        "    deactivate; Remove-Item -Recurse -Force .venv\n"
        "    py -3.12 -m venv .venv\n"
        "    .venv\\Scripts\\activate\n"
        "    pip install -r requirements.txt\n\n"
        "  Linux/Pi: sudo apt install python3.12-venv (or newest available), then the same\n"
        "  rm/venv/activate/install steps with python3.12.\n\n"
        "Then verify with:  python --version   (must say 3.10+)\n"
    )

__version__ = "0.1.0"
