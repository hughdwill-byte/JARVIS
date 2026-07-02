"""Tasks and reminders."""

from datetime import timedelta

from app.tools.reminders import ReminderManager, parse_delay
from app.tools.tasks import TaskManager


def test_task_add_and_list(db):
    tasks = TaskManager(db)
    reply = tasks.add("finish lab report due friday")
    assert "finish lab report" in reply and "friday" in reply
    listing = tasks.list_text()
    assert "finish lab report" in listing and "[due friday]" in listing


def test_task_complete_and_delete(db):
    tasks = TaskManager(db)
    tasks.add("task one")
    tasks.add("task two")
    task_id = db.list_tasks()[0]["id"]
    assert "done" in tasks.complete(str(task_id)).lower()
    assert "task one" not in tasks.list_text()
    other_id = db.list_tasks()[0]["id"]
    assert "deleted" in tasks.delete(f"#{other_id}").lower()


def test_task_bad_input(db):
    tasks = TaskManager(db)
    assert "What's the task" in tasks.add("")
    assert "task number" in tasks.complete("banana")
    assert "No open task #999" in tasks.complete("999")


def test_parse_delay():
    delta, msg = parse_delay("25m take a break")
    assert delta == timedelta(minutes=25) and msg == "take a break"
    delta, msg = parse_delay("2h submit form")
    assert delta == timedelta(hours=2) and msg == "submit form"
    delta, msg = parse_delay("no delay here")
    assert delta is None


def test_reminder_lifecycle(db):
    reminders = ReminderManager(db)
    assert "Format:" in reminders.add("whenever, do stuff")
    reminders.add("0s stretch your legs")
    due = reminders.pop_due()
    assert due == ["stretch your legs"]
    assert reminders.pop_due() == []  # fired reminders don't repeat
