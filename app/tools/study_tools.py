"""University study tools — all tutoring-style, none write graded work.

  /plan <assignment brief + due date>  -> milestone plan
  /flashcards <topic or pasted notes>  -> Q/A flashcards
  /explain <concept>                   -> tiered explanation
  /timetable <constraints>             -> weekly study timetable
  /cite <source details> [style]      -> citation formatting help
"""

from __future__ import annotations

from app.brain.llm_client import LLMClient

_NEED_KEY = "This tool needs the LLM — add ANTHROPIC_API_KEY to .env and restart."

# Requests that would cross academic-integrity lines get caught by the system
# prompt too, but a cheap local check saves an API call for blatant cases.
_INTEGRITY_FLAGS = ("write my essay", "write the essay for me", "do my assignment",
                    "answer my quiz", "answer the exam", "take my test",
                    "write my report for me", "so i can submit")


def integrity_check(text: str) -> str | None:
    lowered = text.lower()
    if any(flag in lowered for flag in _INTEGRITY_FLAGS):
        return ("I won't produce work for you to submit as your own — but I'm all in on "
                "the legitimate version: outlining, explaining, reviewing your draft, or "
                "building a study plan. Which would help?")
    return None


class StudyTools:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def _run(self, prompt: str, force_smart: bool = False) -> str:
        if not self.llm.available:
            return _NEED_KEY
        return self.llm.chat(prompt, force_smart=force_smart)

    def assignment_plan(self, brief: str) -> str:
        if not brief.strip():
            return "Paste the assignment brief and due date: /plan 2000-word ethics essay due 20 Oct"
        blocked = integrity_check(brief)
        if blocked:
            return blocked
        return self._run(
            "Create an assignment plan (NOT the assignment itself). Break this into "
            "milestones with suggested dates working back from the deadline, list what to "
            "research first, and flag the riskiest part. Keep it under 15 lines.\n\n"
            f"Assignment: {brief}",
        )

    def flashcards(self, material: str) -> str:
        if not material.strip():
            return "Give me a topic or paste notes: /flashcards TCP three-way handshake"
        return self._run(
            "Generate 8-12 flashcards from this material as 'Q: ...' / 'A: ...' pairs, "
            "one blank line between cards. Test understanding, not trivia; include 2 "
            f"application-style questions.\n\nMaterial: {material}",
        )

    def explain(self, concept: str) -> str:
        if not concept.strip():
            return "What should I explain? e.g. /explain eigenvalues"
        return self._run(
            f"Explain '{concept}' in three tiers: 1) one-sentence intuition, "
            "2) a proper explanation with a concrete example, 3) one common exam "
            "trap or misconception. Keep the whole thing tight.",
        )

    def timetable(self, constraints: str) -> str:
        if not constraints.strip():
            return ("Describe your week: /timetable 4 subjects, lectures Mon-Wed mornings, "
                    "work Thu, exam in 3 weeks")
        return self._run(
            "Build a realistic weekly study timetable as a simple text table. Include "
            "breaks and at least one free evening; note which subject gets priority and "
            f"why.\n\nConstraints: {constraints}",
        )

    def citation_help(self, details: str) -> str:
        if not details.strip():
            return ("Give me the source details and style: /cite Smith 2021 'Deep Learning' "
                    "MIT Press, APA 7")
        return self._run(
            "Format this as a reference and an in-text citation. If the style isn't "
            "stated, show APA 7 and note the style assumption. If details are missing, "
            f"list exactly what's needed.\n\nSource: {details}",
        )
