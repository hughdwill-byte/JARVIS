"""Agent planning (task decomposition) and lightweight context compaction.

Pure logic — no API key, no devices. The LLM is a scripted fake, matching the
seam the agent tool loop already uses in test_agent.py.
"""

from types import SimpleNamespace

from app.brain.planning import (
    compact_messages,
    estimate_tokens,
    parse_steps,
    plan_steps,
)


# --- parse_steps -------------------------------------------------------------

def test_parse_steps_json_array():
    assert parse_steps('["open folder", "sort files"]') == ["open folder", "sort files"]


def test_parse_steps_json_wrapped_in_prose():
    text = 'Sure! Here is the plan:\n["look", "act"]\nGood luck.'
    assert parse_steps(text) == ["look", "act"]


def test_parse_steps_numbered_and_bulleted_lines():
    assert parse_steps("1. read the file\n2) summarise it") == ["read the file", "summarise it"]
    assert parse_steps("- first\n* second\n• third") == ["first", "second", "third"]


def test_parse_steps_caps_and_dedupes():
    steps = parse_steps('["a","a","b","c","d","e","f","g"]', max_steps=3)
    assert steps == ["a", "b", "c"]


def test_parse_steps_empty_and_junk():
    assert parse_steps("") == []
    assert parse_steps("   ") == []
    assert parse_steps("[]") == []
    assert parse_steps('["none", "n/a"]') == []


# --- plan_steps --------------------------------------------------------------

def _fake_llm(response=None, raises=False):
    calls = []

    class _Messages:
        def create(self, **kw):
            calls.append(kw)
            if raises:
                raise RuntimeError("api down")
            return response

    class _Client:
        messages = _Messages()

    class _LLM:
        raw = _Client()

    llm = _LLM()
    llm.calls = calls
    return llm


def test_plan_steps_calls_client_and_parses():
    resp = SimpleNamespace(content=[SimpleNamespace(type="text", text='["look", "tidy"]')])
    llm = _fake_llm(resp)
    steps = plan_steps(llm, "tidy my downloads", model="m-smart")
    assert steps == ["look", "tidy"]
    assert llm.calls[0]["model"] == "m-smart"


def test_plan_steps_never_raises_on_api_error():
    llm = _fake_llm(raises=True)
    assert plan_steps(llm, "do a thing", model="m") == []


def test_plan_steps_returns_empty_without_raw_client():
    class _NoRaw:
        raw = None
    assert plan_steps(_NoRaw(), "task", model="m") == []


def test_plan_steps_empty_task():
    llm = _fake_llm(SimpleNamespace(content=[SimpleNamespace(type="text", text='["x"]')]))
    assert plan_steps(llm, "   ", model="m") == []
    assert llm.calls == []  # no wasted API call


# --- estimate_tokens ---------------------------------------------------------

def test_estimate_tokens_handles_str_and_block_content():
    messages = [
        {"role": "user", "content": "a" * 40},                       # ~10 + 4
        {"role": "assistant", "content": [{"type": "text", "text": "b" * 40}]},
        {"role": "user", "content": [{"type": "tool_result", "content": "c" * 80}]},
    ]
    # ~ (10+4) + (10+4) + (20+4) = 52; assert it's in a sane ballpark
    assert 45 <= estimate_tokens(messages) <= 60


# --- compact_messages --------------------------------------------------------

def _obs(tool_id, text):
    return {"role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": text}]}


def _act(tool_id):
    return {"role": "assistant",
            "content": [{"type": "tool_use", "id": tool_id, "name": "read_file", "input": {}}]}


def test_compact_messages_noop_under_cap():
    messages = [{"role": "user", "content": "short task"}, _act("t1"), _obs("t1", "small")]
    assert compact_messages(messages, cap_tokens=10_000) is messages


def test_compact_messages_disabled_with_zero_cap():
    messages = [_act("t1"), _obs("t1", "x" * 5000)]
    assert compact_messages(messages, cap_tokens=0) is messages


def test_compact_messages_elides_old_observations_over_cap():
    big = "y" * 4000
    messages = [
        {"role": "user", "content": "the task"},
        _act("t1"), _obs("t1", big),
        _act("t2"), _obs("t2", big),
        _act("t3"), _obs("t3", big),
    ]
    out = compact_messages(messages, cap_tokens=100, keep_last=1)
    # oldest two observations are stubbed, most recent kept verbatim
    assert "elided" in out[2]["content"][0]["content"]
    assert "elided" in out[4]["content"][0]["content"]
    assert out[6]["content"][0]["content"] == big
    # tool_use_ids survive so no result dangles from its call
    assert out[2]["content"][0]["tool_use_id"] == "t1"
    assert estimate_tokens(out) < estimate_tokens(messages)


def test_compact_messages_does_not_mutate_input():
    big = "z" * 4000
    messages = [_act("t1"), _obs("t1", big), _act("t2"), _obs("t2", big)]
    before = messages[1]["content"][0]["content"]
    compact_messages(messages, cap_tokens=100, keep_last=1)
    assert messages[1]["content"][0]["content"] == before  # original untouched


def test_compact_messages_short_results_left_alone():
    messages = [
        {"role": "user", "content": "t"},
        _act("t1"), _obs("t1", "tiny"),
        _act("t2"), _obs("t2", "y" * 4000),
    ]
    out = compact_messages(messages, cap_tokens=100, keep_last=1, stub_over=200)
    # the short old result stays as-is (below stub threshold)
    assert out[2]["content"][0]["content"] == "tiny"
