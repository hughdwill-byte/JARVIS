"""Scene memory: recording, change detection, inventory diffing."""

from app.vision.image_analyzer import split_summary_and_objects
from app.vision.scene_memory import SceneMemory, diff_objects


def test_diff_objects():
    added, removed = diff_objects("laptop, mug, pen", "laptop, pen, notebook")
    assert added == ["notebook"]
    assert removed == ["mug"]


def test_diff_normalizes_case_and_spacing():
    added, removed = diff_objects("Laptop,  MUG ", "laptop, mug")
    assert added == [] and removed == []


def test_change_detection_flow(db):
    scenes = SceneMemory(db)
    assert "only have one" not in scenes.describe_changes()  # zero snapshots message
    scenes.record("A tidy desk.", "laptop, mug, pen")
    assert "only have one" in scenes.describe_changes()
    scenes.record("A desk with a notebook.", "laptop, pen, notebook")
    changes = scenes.describe_changes()
    assert "notebook" in changes and "mug" in changes


def test_no_change_message(db):
    scenes = SceneMemory(db)
    scenes.record("Desk.", "laptop, mug")
    scenes.record("Desk again.", "laptop, mug")
    assert "Nothing meaningful" in scenes.describe_changes()


def test_latest_summary(db):
    scenes = SceneMemory(db)
    assert scenes.latest_summary() is None
    scenes.record("First.", "pen")
    scenes.record("Second.", "pen, mug")
    assert scenes.latest_summary() == "Second."


def test_split_summary_and_objects():
    analysis = (
        "SUMMARY: A laptop sits centre desk with a mug to the left.\n"
        "OBJECTS: laptop, mug, pen, notebook"
    )
    summary, objects = split_summary_and_objects(analysis)
    assert "laptop sits centre desk" in summary
    assert objects == "laptop, mug, pen, notebook"
