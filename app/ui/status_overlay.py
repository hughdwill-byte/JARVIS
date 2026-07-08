"""Tiny always-on-top status pill — the visible 'JARVIS is working' light.

Runs as its OWN process (launched by app/ui/status_indicator.py), so it can't
interfere with the desktop app's GUI thread. Cross-platform: uses only Python's
built-in Tkinter, which ships with the python.org/Homebrew macOS builds and the
Windows installer. It polls the state file the assistant writes and shows a
coloured pill in the top-right of the screen; it hides itself when JARVIS is
idle, and exits on its own if the app goes away (state file stops updating).

Run manually for a quick look:
    python -m app.ui.status_overlay --state-file data/status.json

Or just prove it renders (cycles through the states, ignores the app):
    python -m app.ui.status_overlay --demo
"""

from __future__ import annotations

import argparse
import itertools
import sys
import time

from app.ui.status_indicator import read_state

# state -> (label, background colour)
_LOOK = {
    "listening": ("🎤  Listening", "#2e9e5b"),   # green
    "thinking":  ("💭  Thinking",  "#c8892b"),   # amber
    "speaking":  ("🔊  Speaking",  "#2f6fd0"),   # blue
    "armed":     ("🎙  Ready",     "#5a5f66"),   # dim grey
}
STALE_AFTER_S = 10.0   # no state update this long => assume the app quit, exit
POLL_MS = 150


def make_click_through(root) -> bool:
    """Let mouse clicks pass straight THROUGH the pill to whatever's beneath, so
    it can never block you. Returns True if it took effect. Best-effort and
    platform-specific; on failure the pill still shows (just not click-through).
    """
    if sys.platform == "darwin":
        try:
            from AppKit import NSApp  # ships with PyObjC (a pywebview dependency)
            root.update_idletasks()
            app = NSApp()
            if app is None:
                return False
            ok = False
            for win in app.windows():
                try:
                    win.setIgnoresMouseEvents_(True)
                    ok = True
                except Exception:
                    pass
            return ok
        except Exception as exc:
            print(f"status overlay: click-through unavailable on macOS ({exc}); the "
                  "pill may block clicks. Fix: pip install pyobjc-framework-Cocoa",
                  file=sys.stderr)
            return False
    if sys.platform.startswith("win"):
        try:
            import ctypes
            GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = \
                -20, 0x80000, 0x20, 0x80
            u = ctypes.windll.user32
            hwnd = u.GetParent(root.winfo_id()) or root.winfo_id()
            style = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            u.SetWindowLongW(hwnd, GWL_EXSTYLE,
                             style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)
            return True
        except Exception as exc:
            print(f"status overlay: click-through unavailable on Windows ({exc})",
                  file=sys.stderr)
            return False
    return False  # Linux/other: not supported; pill still shows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", help="JSON file the app writes its state to")
    parser.add_argument("--demo", action="store_true",
                        help="cycle through the states to check rendering, ignore the app")
    args = parser.parse_args(argv)
    if not args.demo and not args.state_file:
        parser.error("give --state-file, or --demo to just test rendering")

    try:
        import tkinter as tk
    except Exception as exc:  # tkinter missing (e.g. Linux without python3-tk)
        print(f"status overlay: tkinter unavailable ({exc}); no indicator shown.\n"
              "On macOS/Homebrew: brew install python-tk  (match your python version).",
              file=sys.stderr)
        return 1

    root = tk.Tk()
    root.overrideredirect(True)          # borderless
    root.attributes("-topmost", True)    # float above everything
    for attr in (("-alpha", 0.92), ("-type", "splash")):
        try:
            root.attributes(*attr)
        except tk.TclError:
            pass

    label = tk.Label(root, text="", font=("Helvetica", 15, "bold"),
                     fg="white", padx=16, pady=8)
    label.pack()

    applied = {"click_through": False}

    def show(state: str) -> None:
        look = _LOOK.get(state)
        if look is None:                 # idle / unknown -> hide the pill
            root.withdraw()
            return
        text, colour = look
        label.configure(text=text, bg=colour)
        root.configure(bg=colour)
        root.deiconify()
        root.update_idletasks()
        # Apply click-through once the window actually exists (needs a realized
        # native window). Retry each show until it takes.
        if not applied["click_through"]:
            applied["click_through"] = make_click_through(root)
        w = root.winfo_width()
        sw = root.winfo_screenwidth()
        root.geometry(f"+{sw - w - 24}+44")   # top-right, below the menu bar
        root.lift()                      # macOS: make sure it comes to the front
        root.attributes("-topmost", True)

    demo_cycle = itertools.cycle(["listening", "thinking", "speaking", "armed"])

    def tick() -> None:
        if args.demo:
            show(next(demo_cycle))
            root.after(1500, tick)
            return
        state, ts = read_state(args.state_file)
        if ts and (time.time() - ts) > STALE_AFTER_S:
            root.destroy()               # parent app is gone — clean up
            return
        show(state)
        root.after(POLL_MS, tick)

    root.withdraw()
    root.after(POLL_MS, tick)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
