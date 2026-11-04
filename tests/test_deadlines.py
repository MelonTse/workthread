import datetime as dt
import sqlite3

import pytest

from workthread.core import DDL, VERSION, Store


def test_capture_can_be_incomplete_but_human_edit_requires_deadline(tmp_path):
    s = Store(tmp_path)
    t = s.create_todo({"raw_input": "立即保存原始工作"})
    assert t["due_date"] is None and not t["no_due_date"]
    with pytest.raises(ValueError, match="截止日期"):
        s.edit_todo(t["todo_id"], {"title": "详情修改"}, 1)
    updated = s.edit_todo(t["todo_id"], {"due_date": "2026-12-01"}, 1)
    assert updated["due_date"] == "2026-12-01" and not updated["no_due_date"]


def test_indefinite_is_explicit_exclusive_and_human_protected(tmp_path):
    s = Store(tmp_path)
    t = s.create_todo({"raw_input": "不设时限的工作"})
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
    old = tmp_path / "data"
    old.mkdir()
    c = sqlite3.connect(old / "workthread.sqlite3")
    c.executescript(DDL.replace(", no_due_date INTEGER NOT NULL DEFAULT 0", ""))
    c.execute("INSERT INTO schema_migrations VALUES (1,?)", ("synthetic",))
    c.commit()
    c.close()
    s = Store(tmp_path)
    assert "no_due_date" in {r["name"] for r in s.rows("PRAGMA table_info(todos)")}
    assert (
        max(r["version"] for r in s.rows("SELECT version FROM schema_migrations"))
        == VERSION
        == 2
    )
    t = s.create_todo({"raw_input": "迁移后仍待填写"})
    assert not t["no_due_date"] and t["due_date"] is None


def test_manual_progress_defaults_to_recording_time_but_unknown_ai_time_stays_unknown(
    tmp_path,
):
    s = Store(tmp_path)
    t = s.create_todo({"raw_input": "工作"})
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


def test_v1_todo_backup_restores_as_pending_deadline(tmp_path):
    import hashlib
    import json

    import py7zr

    from workthread.operations import restore

    s = Store(tmp_path / "source")
    t = s.create_todo({"raw_input": "旧版待填写日期"})
    document = {
        table: s.rows("SELECT * FROM " + table)
        for table in ("todos", "todo_sources", "progress_logs", "status_events")
    }
    document["todos"][0].pop("no_due_date")
    stage = tmp_path / "old-package"
    stage.mkdir()
    payload = stage / "todos.json"
    payload.write_text(json.dumps(document))
    manifest = {
        "format_version": 1,
        "schema_version": 1,
        "scope": "todos",
        "created_at": "synthetic",
        "files": {
            "todos.json": {
                "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
                "size": payload.stat().st_size,
            }
        },
    }
    (stage / "manifest.json").write_text(json.dumps(manifest))
    archive = tmp_path / "old.7z"
    with py7zr.SevenZipFile(
        archive, "w", password="synthetic-test-password", header_encryption=True
    ) as z:
        z.write(payload, "todos.json")
        z.write(stage / "manifest.json", "manifest.json")
    target = Store(tmp_path / "destination")
    restore(target, archive, "synthetic-test-password", True)
    restored = target.todo(t["todo_id"])
    assert restored["due_date"] is None and restored["no_due_date"] == 0
