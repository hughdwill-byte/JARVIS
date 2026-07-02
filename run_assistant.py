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

    def terminal_approve(tool_name: str, description: str) -> bool:
        print(f"\n  JARVIS wants to: {description}")
        try:
            return input("  Allow this? [y/N] ").strip().lower() in ("y", "yes")
        except EOFError:
            return False

    assistant.approval_callback = terminal_approve

    if "--check" in sys.argv:
        code = first_run_check(assistant)
        assistant.close()
        return code

    print(BANNER)
    if not assistant.llm.available:
        print("NOTE: no API key found — running in offline mode (notes/tasks/snapshots"
              " work; smart replies don't). Add ANTHROPIC_API_KEY to .env to fix.\n")
    if assistant.voice_loop is not None:
        if assistant.voice_loop.available:
            assistant.voice_loop.ensure_started()
            print("Hands-free mode: say 'jarvis' to talk, 'shutdown' to close the mic,"
                  " type anything to re-arm it.\n")
        else:
            print(f"Hands-free mode unavailable: {assistant.voice_loop.why_unavailable()}\n")
    elif assistant.ptt.available and assistant.transcriber.available:
        print("Voice ready: type /voice to speak, or set WAKE_WORD_ENABLED=true in .env"
              " for hands-free 'jarvis' mode.\n")

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
            # Typing anything (except a sleep command) re-arms hands-free listening.
            if (assistant.voice_loop is not None and assistant.voice_loop.available
                    and not assistant.voice_loop.listening
                    and assistant.router.route(user_text)[0] != "sleep"):
                assistant.voice_loop.wake_up()
                print("  [hands-free re-armed — say 'jarvis' anytime]")
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
