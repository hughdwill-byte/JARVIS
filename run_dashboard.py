#!/usr/bin/env python3
"""Launch the local web dashboard.

    python run_dashboard.py
Then open http://127.0.0.1:8321 in your browser.
"""

from app.config import load_config
from app.dashboard.server import create_app


def main() -> None:
    cfg = load_config()
    app = create_app(cfg)
    print(f"JARVIS dashboard: http://{cfg.dashboard_host}:{cfg.dashboard_port}")
    app.run(host=cfg.dashboard_host, port=cfg.dashboard_port, debug=cfg.debug,
            use_reloader=False)  # reloader would double-init the Assistant


if __name__ == "__main__":
    main()
