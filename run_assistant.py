#!/usr/bin/env python3
"""JARVIS terminal front-end.

    python run_assistant.py            # normal start
    python run_assistant.py --no-tts   # text-only replies
    python run_assistant.py --check    # first-run self test, then exit

Type /help inside the assistant for commands. Ctrl+C or /quit exits.
"""

from __future__ import annotations

import sys

from app.assistant import Assistant
from app.config import load_config

BANNER = r"""
     ____  ___    ______ _    __ ____ _____
    / / / / | |  / / __ \ |  / //  _// ___/     desk assistant
 __/ / /_/ /| | / / /_/ / | / / / /  \__ \      type /help for commands
/___/\____/ |_|/_/_/ |_|\_|/_/ /___/______/     /quit to exit
"""


def first_run_check(assistant: Assistant) -> int:
    """Verify each subsystem and print a fix hint for anything missing."""
    print("Running first-run check...\n")
    print(assistant.status_text())
    print("\nMemory test:", assistant.notes.add("first-run check note"))
    rows = assistant.db.list_notes(1)
    ok = bool(rows) and "first-run check" in rows[0]["content"]
    if rows:
        assistant.db.delete_note(rows[0]["id"])
    print("Memory read-back:", "OK" if ok else "FAILED — check DATABASE_PATH permissions")
    if assistant.llm.available:
        print("\nLLM test:", assistant.llm.chat("Reply with exactly: systems online.", max_tokens=20))
    else:
        print("\nLLM test skipped (no API key — assistant runs in offline mode).")
    print("\nCheck complete. Start normally with: python run_assistant.py")
    return 0 if ok else 1


def main() -> int:
    cfg = load_config()
    if "--no-tts" in sys.argv:
        cfg.tts_provider = "none"
    assistant = Assistant(cfg)

    if "--check" in sys.argv:
        code = first_run_check(assistant)
        assistant.close()
        return code

    print(BANNER)
    if not assistant.llm.available:
        print("NOTE: no API key found — running in offline mode (notes/tasks/snapshots"
              " work; smart replies don't). Add ANTHROPIC_API_KEY to .env to fix.\n")
    if assistant.ptt.available and assistant.transcriber.available:
        print("Voice ready: type /voice to speak instead of typing.\n")

    try:
        while True:
            for msg in assistant.due_reminder_messages():
                print(f"\n  REMINDER: {msg}")
                assistant.speaker.speak(f"Reminder: {msg}")
            try:
                user_text = input("you> ").strip()
            except EOFError:
                break
            if user_text.lower() in ("/quit", "/exit", "quit", "exit"):
                break
            if not user_text:
                continue
            reply = assistant.handle(user_text)
            if reply.text:
                print(f"\njarvis> {reply.text}\n")
                if reply.speak:
                    assistant.speaker.speak(reply.text)
    except KeyboardInterrupt:
        print()
    finally:
        assistant.close()
        print("Goodbye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
