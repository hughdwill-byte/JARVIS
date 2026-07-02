"""Memory: notes, preferences, conversation history round-trips."""

from app.memory.notes import Notes
from app.memory.preferences import Preferences


def test_note_roundtrip(db):
    notes = Notes(db)
    reply = notes.add("buy a longer USB cable")
    assert "USB cable" in reply
    assert "buy a longer USB cable" in notes.list_text()
    note_id = db.list_notes(1)[0]["id"]
    assert "Deleted" in notes.delete(note_id)
    assert "No notes saved yet" in notes.list_text()


def test_empty_note_rejected(db):
    assert "need some text" in Notes(db).add("   ")


def test_preferences_roundtrip(db):
    prefs = Preferences(db)
    prefs.remember("units: metric")
    assert db.get_preference("units") == "metric"
    assert "metric" in prefs.list_text()
    assert "Forgotten" in prefs.forget("units")
    assert db.get_preference("units") is None


def test_preference_upsert(db):
    prefs = Preferences(db)
    prefs.remember("editor: vim")
    prefs.remember("editor: vscode")
    assert db.get_preference("editor") == "vscode"
    assert len(db.list_preferences()) == 1


def test_conversation_history_order_and_limit(db):
    for i in range(5):
        db.add_message("user", f"question {i}")
        db.add_message("assistant", f"answer {i}")
    recent = db.recent_messages(4)
    assert len(recent) == 4
    assert recent[-1]["content"] == "answer 4"
    assert recent[0]["content"] == "question 3"  # chronological order preserved
    db.clear_conversation()
    assert db.recent_messages(4) == []
