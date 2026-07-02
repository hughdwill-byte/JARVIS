"""Tool registry: maps command names to handler callables.

Handlers take one string argument (the text after the command) and return
the reply text. Keeping this dumb-simple makes new tools one-liners to add.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

Handler = Callable[[str], str]


@dataclass
class Tool:
    name: str
    help_text: str
    handler: Handler
    speak_reply: bool = True  # some outputs (long lists) shouldn't be read aloud


@dataclass
class ToolManager:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, name: str, help_text: str, handler: Handler,
                 speak_reply: bool = True) -> None:
        self.tools[name] = Tool(name, help_text, handler, speak_reply)

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def help_text(self) -> str:
        lines = ["Commands:"]
        for tool in sorted(self.tools.values(), key=lambda t: t.name):
            lines.append(f"  /{tool.name:<12} {tool.help_text}")
        lines.append("Anything else you type (or say) goes straight to the AI brain.")
        return "\n".join(lines)
