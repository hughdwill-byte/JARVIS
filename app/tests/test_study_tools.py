"""Study tools: input validation, integrity checks, offline messaging."""

from app.brain.llm_client import LLMClient
from app.tools.code_helper import CodeHelper
from app.tools.study_tools import StudyTools, integrity_check


def test_integrity_check_flags_dishonest_requests():
    assert integrity_check("write my essay for me") is not None
    assert integrity_check("answer my quiz please") is not None
    assert integrity_check("explain how photosynthesis works") is None
    assert integrity_check("review my draft introduction") is None


def test_empty_inputs_get_usage_hints(cfg):
    study = StudyTools(LLMClient(cfg))
    assert "/plan" in study.assignment_plan("") or "brief" in study.assignment_plan("")
    assert "flashcards" in study.flashcards("").lower()
    assert "explain" in study.explain("").lower()
    assert "timetable" in study.timetable("").lower()
    assert "cite" in study.citation_help("").lower() or "source" in study.citation_help("").lower()


def test_offline_message_without_key(cfg):
    study = StudyTools(LLMClient(cfg))
    assert "ANTHROPIC_API_KEY" in study.explain("eigenvalues")


def test_plan_blocks_integrity_violation(cfg):
    study = StudyTools(LLMClient(cfg))
    assert "won't" in study.assignment_plan("do my assignment for me").lower()


def test_code_runner_executes_python():
    out = CodeHelper.run_python("print(2 + 2)")
    assert "4" in out and "OK" in out


def test_code_runner_reports_errors():
    out = CodeHelper.run_python("raise ValueError('boom')")
    assert "boom" in out and "exit code" in out


def test_code_runner_times_out():
    out = CodeHelper.run_python("while True: pass")
    assert "Timed out" in out
