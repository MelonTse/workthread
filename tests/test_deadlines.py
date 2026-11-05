import datetime as dt

import pytest

from workthread.core import VERSION, Store


def test_new_capture_requires_deadline_and_rejects_atomically(tmp_path):
    s = Store(tmp_path)
    with pytest.raises(ValueError, match="due_date / no_due_date"):
        s.create_todo({"raw_input": "立即保存原始工作"})
    assert not s.rows("SELECT * FROM todos")
    assert not s.rows("SELECT * FROM todo_sources")
    assert not s.rows("SELECT * FROM status_events")


def test_indefinite_is_explicit_exclusive_and_human_protected(tmp_path):
    s = Store(tmp_path)
    t = s.create_todo({"raw_input": "不设时限的工作", "no_due_date": True})
    t = s.edit_todo(t["todo_id"], {"no_due_date": True, "due_date": None}, 1)
    assert t["no_due_date"] and t["due_date"] is None
    with pytest.raises(ValueError):
        s.edit_todo(t["todo_id"], {"due_date": "2026-12-01"}, t["revision"])
    with s.db() as c:
        assert not s._edit(
            c, t["todo_id"], {"due_date": "2026-12-01"}, t["revision"], human=False
        )
    assert s.todo(t["todo_id"])["no_due_date"]
    assert s.rows("SELECT * FROM review_items WHERE kind='protected_change'")


@pytest.mark.parametrize("due,indefinite", [("2026-12-01", False), (None, True)])
def test_form_deadline_overrides_relative_words_and_is_protected(tmp_path, due, indefinite):
    s = Store(tmp_path)
    t = s.create_todo({
        "raw_input": "明天跟进客户\n说明原始安排",
        "title": "明天跟进客户",
        "description": "说明原始安排",
        "due_date": due,
        "no_due_date": indefinite,
        "priority": "high",
        "owner": "local-user",
    })
    assert t["due_date"] == due and bool(t["no_due_date"]) == indefinite
    assert t["raw_input"] == "明天跟进客户\n说明原始安排"
    assert t["description"] == "说明原始安排" and t["priority"] == "high"
    with s.db() as c:
        assert not s._edit(
            c, t["todo_id"], {"due_date": "2027-01-01", "no_due_date": False},
            t["revision"], human=False,
        )


def test_v1_migration_does_not_turn_unknown_deadline_into_indefinite(tmp_path):
    s = Store(tmp_path)
    t = s.create_todo({"raw_input": "历史工作原文", "no_due_date": True})
    with s.db() as c:
        c.execute("ALTER TABLE todos DROP COLUMN no_due_date")
        c.execute("DELETE FROM schema_migrations")
        c.execute("INSERT INTO schema_migrations VALUES (1,?)", ("synthetic",))
    s = Store(tmp_path)
    assert "no_due_date" in {r["name"] for r in s.rows("PRAGMA table_info(todos)")}
    assert max(r["version"] for r in s.rows("SELECT version FROM schema_migrations")) == VERSION == 2
    historical = s.todo(t["todo_id"])
    assert historical["due_date"] is None and historical["no_due_date"] == 0
    assert historical["raw_input"] == "历史工作原文" and historical["revision"] == 1
    with pytest.raises(ValueError, match="due_date"):
        s.edit_todo(t["todo_id"], {"title": "必须补齐日期"}, 1)
    assert s.todo(t["todo_id"]) == historical
    s.edit_todo(t["todo_id"], {"due_date": "2026-12-01", "no_due_date": False}, 1)


def test_manual_progress_defaults_to_recording_time_but_unknown_ai_time_stays_unknown(
    tmp_path,
):
    s = Store(tmp_path)
    t = s.create_todo({"raw_input": "工作", "no_due_date": True})
    s.progress(t["todo_id"], {"content": "当前登记的工作进展"})
    log = s.todo(t["todo_id"])["logs"][0]
    assert (
        abs(
            (
                dt.datetime.fromisoformat(log["occurred_at"])
                - dt.datetime.fromisoformat(log["recorded_at"])
            ).total_seconds()
        )
        < 2
    )
    with s.db() as c:
        s._progress(c, t["todo_id"], {"content": "AI 记录，实际时间未知"}, "ai")
    assert s.todo(t["todo_id"])["logs"][-1]["occurred_at"] is None


def test_invalid_indefinite_values_are_not_coerced_to_true(tmp_path):
    s = Store(tmp_path)
    for value in ("false", "on", None, 2):
        with pytest.raises(ValueError):
            s.create_todo({"raw_input": "无效选择", "no_due_date": value})
    assert not s.rows("SELECT * FROM todos")


def test_old_7z_is_rejected_without_modifying_archive_or_destination(tmp_path):
    from workthread.operations import restore

    archive = tmp_path / "historical.7z"
    original = b"7z\xbc\xaf\x27\x1c" + b"synthetic historical test artifact"
    archive.write_bytes(original)
    target = Store(tmp_path / "destination")
    t = target.create_todo({"raw_input": "keep original", "no_due_date": True})
    before = target.todo(t["todo_id"])
    with pytest.raises(ValueError, match="ZIP"):
        restore(target, archive, apply=True)
    assert archive.read_bytes() == original
    assert target.todo(t["todo_id"]) == before
