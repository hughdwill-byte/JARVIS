"""Speakable-text cleanup: markdown stripping + abbreviation expansion."""

from app.audio.speech_text import to_speech_text
from app.brain.llm_client import SentenceStreamer


# --- markdown / symbol stripping ---------------------------------------------

def test_strips_emphasis_and_code_marks():
    assert to_speech_text("This is **really** `important` stuff") == \
        "This is really important stuff"


def test_strips_bullets_and_headings():
    out = to_speech_text("# Plan\n- first item\n- second item")
    assert "#" not in out and "-" not in out
    assert "Plan first item second item" == out


def test_links_become_their_label_and_urls_become_link():
    assert to_speech_text("see [the docs](https://x.com/y)") == "see the docs"
    assert to_speech_text("go to https://example.com/foo now") == "go to link now"


# --- abbreviation expansion --------------------------------------------------

def test_expands_common_abbreviations():
    assert to_speech_text("bring a pen, e.g. a biro") == "bring a pen, for example a biro"
    assert to_speech_text("fruit, etc.") == "fruit, and so on"
    assert to_speech_text("Python vs. Java") == "Python versus Java"
    assert to_speech_text("i.e. the second one") == "that is the second one"
    assert to_speech_text("approx. 5 minutes") == "approximately 5 minutes"


def test_expands_symbols():
    assert to_speech_text("cats & dogs") == "cats and dogs"
    assert to_speech_text("battery at 80%") == "battery at 80 percent"


def test_empty_and_plain_text():
    assert to_speech_text("") == ""
    assert to_speech_text("   ") == ""
    assert to_speech_text("Just a normal sentence.") == "Just a normal sentence."


# --- streamer no longer splits mid-abbreviation ------------------------------

def test_streamer_does_not_break_on_abbreviation():
    got = []
    s = SentenceStreamer(got.append)
    s.feed("Bring supplies, e.g. pens and paper. Then start.")
    s.flush()
    # "e.g." must NOT end a spoken chunk; the first sentence stays whole
    assert got == ["Bring supplies, e.g. pens and paper.", "Then start."]


def test_streamer_still_splits_normal_sentences():
    got = []
    s = SentenceStreamer(got.append)
    s.feed("Your desk has a lap")
    s.feed("top. Also a mug! And fin")
    assert got == ["Your desk has a laptop.", "Also a mug!"]
    s.feed("ally pens")
    s.flush()
    assert got[-1] == "And finally pens"
