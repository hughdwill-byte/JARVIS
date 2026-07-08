"""Menu-bar / system-tray status icon — the visible 'JARVIS is working' light.

Runs as its OWN process (launched by app/ui/status_indicator.py). Instead of a
floating window (which sat on the screen and blocked clicks), this puts a small
coloured dot in the macOS menu bar / Windows system tray: green Listening, amber
Thinking, blue Speaking. It lives *in* the menu bar, so it can never cover your
content or steal a click, and it hides itself when JARVIS is idle. It exits on
its own if the app goes away (state file stops updating).

Uses `pystray` (+ Pillow, already a dependency). If pystray isn't installed the
process just prints a hint and exits — the assistant is unaffected.

Run manually to check it renders (cycles the states, ignores the app):
    python -m app.ui.status_overlay --demo
"""

from __future__ import annotations

import argparse
import itertools
import sys
import threading
import time

from app.ui.status_indicator import read_state

# state -> (menu-bar tooltip, dot colour RGB)
_LOOK = {
    "listening": ("JARVIS — Listening", (46, 158, 91)),    # green
    "thinking":  ("JARVIS — Thinking",  (200, 137, 43)),   # amber
    "speaking":  ("JARVIS — Speaking",  (47, 111, 208)),   # blue
    "armed":     ("JARVIS — Ready",     (90, 95, 102)),    # dim grey
}
STALE_AFTER_S = 10.0   # no state update this long => assume the app quit, exit
POLL_S = 0.15
DEMO_STATES = ("listening", "thinking", "speaking", "armed")


def _dot_image(colour: tuple[int, int, int]):
    """A filled circle icon (menu bars scale it down to ~16-22px)."""
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([6, 6, size - 6, size - 6], fill=colour + (255,))
    return img


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", help="JSON file the app writes its state to")
    parser.add_argument("--demo", action="store_true",
                        help="cycle through the states to check rendering, ignore the app")
    args = parser.parse_args(argv)
    if not args.demo and not args.state_file:
        parser.error("give --state-file, or --demo to just test rendering")

    try:
        import pystray
    except Exception as exc:  # not installed / backend unavailable
        print(f"status icon: pystray unavailable ({exc}); no indicator shown.\n"
              "Install it with:  pip install pystray", file=sys.stderr)
        return 1

    icon = pystray.Icon(
        "jarvis",
        _dot_image(_LOOK["armed"][1]),
        "JARVIS",
        menu=pystray.Menu(pystray.MenuItem("Quit indicator", lambda: icon.stop())),
    )

    def apply(state: str) -> None:
        look = _LOOK.get(state)
        if look is None:                 # idle / unknown -> hide the dot
            icon.visible = False
            return
        tooltip, colour = look
        icon.icon = _dot_image(colour)
        icon.title = tooltip
        icon.visible = True

    def poll() -> None:
        demo = itertools.cycle(DEMO_STATES)
        last = object()
        while True:
            if args.demo:
                apply(next(demo))
                time.sleep(1.5)
                continue
            state, ts = read_state(args.state_file)
            if ts and (time.time() - ts) > STALE_AFTER_S:
                icon.stop()              # parent app is gone — clean up
                return
            if state != last:
                last = state
                apply(state)
            time.sleep(POLL_S)

    def setup(icon) -> None:
        icon.visible = False             # start hidden (idle)
        threading.Thread(target=poll, daemon=True, name="jarvis-status-poll").start()

    icon.run(setup=setup)                # blocks on the main thread (required)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
