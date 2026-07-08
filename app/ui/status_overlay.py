"""Tiny always-on-top status pill — the visible 'JARVIS is working' light.

Runs as its OWN process (launched by app/ui/status_indicator.py), so it can't
interfere with the desktop app's GUI thread. Cross-platform: uses only Python's
built-in Tkinter, which ships with the python.org/Homebrew macOS builds and the
Windows installer. It polls the state file the assistant writes and shows a
coloured pill in the top-right of the screen; it hides itself when JARVIS is
idle, and exits on its own if the app goes away (state file stops updating).

Run manually for a quick look:
    python -m app.ui.status_overlay --state-file data/status.json
"""

from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", required=True)
    args = parser.parse_args(argv)

    try:
        import tkinter as tk
    except Exception as exc:  # tkinter missing (e.g. Linux without python3-tk)
        print(f"status overlay: tkinter unavailable ({exc}); no indicator shown",
              file=sys.stderr)
        return 1

    root = tk.Tk()
    root.overrideredirect(True)          # borderless
    root.attributes("-topmost", True)    # float above everything
    try:
        root.attributes("-alpha", 0.92)
    except tk.TclError:
        pass

    label = tk.Label(root, text="", font=("Helvetica", 15, "bold"),
                     fg="white", padx=16, pady=8)
    label.pack()

    def place_top_right() -> None:
        root.update_idletasks()
        w = root.winfo_width()
        sw = root.winfo_screenwidth()
        root.geometry(f"+{sw - w - 24}+28")

    def tick() -> None:
        state, ts = read_state(args.state_file)
        if ts and (time.time() - ts) > STALE_AFTER_S:
            root.destroy()               # parent app is gone — clean up
            return
        look = _LOOK.get(state)
        if look is None:                 # idle / unknown -> hide the pill
            root.withdraw()
        else:
            text, colour = look
            label.configure(text=text, bg=colour)
            root.configure(bg=colour)
            root.deiconify()
            place_top_right()
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
