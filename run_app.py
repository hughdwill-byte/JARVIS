#!/usr/bin/env python3
"""JARVIS as a desktop app: the dashboard in its own native window.

    python run_app.py

Uses pywebview (native WebKit window on macOS, WebView2 on Windows).
If pywebview isn't installed, it falls back to opening your browser —
same app, just in a tab.

Double-clickable launchers: launchers/JARVIS.command (Mac),
launchers/JARVIS.bat (Windows).
"""

from __future__ import annotations

import socket
import threading
import time
import webbrowser

from app.config import load_config
from app.dashboard.server import create_app


def _wait_for_server(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main() -> None:
    cfg = load_config()
    app = create_app(cfg)
    url = f"http://{cfg.dashboard_host}:{cfg.dashboard_port}"

    server = threading.Thread(
        target=lambda: app.run(host=cfg.dashboard_host, port=cfg.dashboard_port,
                               debug=False, use_reloader=False),
        daemon=True,
    )
    server.start()
    if not _wait_for_server(cfg.dashboard_host, cfg.dashboard_port):
        print(f"Server didn't start on {url}. Is the port in use? "
              "Change DASHBOARD_PORT in Settings/.env.")
        return

    try:
        import webview
    except ImportError:
        print("Native window needs: pip install pywebview")
        print(f"Opening in your browser instead: {url}")
        webbrowser.open(url)
        try:
            while True:  # keep the server alive until Ctrl+C
                time.sleep(3600)
        except KeyboardInterrupt:
            return

    webview.create_window(
        "JARVIS — Desk Assistant", url,
        width=1180, height=800, min_size=(760, 520),
    )
    webview.start()  # blocks until the window is closed
    print("Window closed. Goodbye.")


if __name__ == "__main__":
    main()
