import pytest
from workthread.core import Store, Conflict, uid
from workthread.ai import Bridge, atomic_json


def test_three_intakes_and_progress(tmp_path):
    s = Store(tmp_path)
    a = s.create_todo(
        {
            "raw_input": "明天联系客户",
            "input_at": "2026-01-01T10:00:00+08:00",
            "input_timezone": "Asia/Shanghai",
        },
        key="one",
    )
    assert a["due_date"] == "2026-01-02" and a["logs"] == []
    assert s.create_todo({"raw_input": "重复"}, key="one")["todo_id"] == a["todo_id"]
    s.progress(a["todo_id"], {"content": "已准备资料"})
    s.progress(a["todo_id"], {"content": "等待对方反馈"})
    a = s.todo(a["todo_id"])
    assert len(a["logs"]) == 2 and a["status"] == "inbox"
    b = Bridge(s)
    request = {
        "schema_version": "1.0",
        "request_id": uid(),
        "raw_input": "补充工作",
        "input_at": "2026-01-01T10:00:00+08:00",
        "input_timezone": "Asia/Shanghai",
        "source_ref": "conversation:synthetic",
        "due_date": "2026-12-01",
        "no_due_date": False,
    }
    atomic_json(b.exchange / "intake" / "sample.json", request)
    assert b.consume()[0]["state"] == "saved"
    assert s.rows("SELECT * FROM todos WHERE source_type=?", ("workbuddy",))
    assert Store(tmp_path).todo(a["todo_id"])["raw_input"] == "明天联系客户"


def test_manual_protection_and_stale_result(tmp_path):
    s = Store(tmp_path)
    t = s.create_todo({"raw_input": "测试任务", "no_due_date": True})
    b = Bridge(s)
    j = b.prepare()[0]
    result = {
        k: j[k]
        for k in (
            "schema_version",
            "workspace_id",
            "workspace_epoch",
            "job_id",
            "input_sha256",
        )
    }
    result.update(
        outcome="completed",
        reviewed_todo_ids=[t["todo_id"]],
        warnings=[],
        operations=[],
    )
    s.edit_todo(t["todo_id"], {"status": "done"}, t["revision"])
    with pytest.raises(Conflict):
        b.import_result(result)
    assert s.todo(t["todo_id"])["status"] == "done"


def test_merge_preserves_log_and_source(tmp_path):
    s = Store(tmp_path)
    a = s.create_todo({"raw_input": "客户确认", "no_due_date": True})
    b = s.create_todo({"raw_input": "客户确认进度", "no_due_date": True})
    s.progress(b["todo_id"], {"content": "原始记录"})
    s.merge(a["todo_id"], b["todo_id"], {a["todo_id"]: 1, b["todo_id"]: 1})
    assert len(s.todo(a["todo_id"])["logs"]) == 1
    assert s.todo(b["todo_id"])["merged_into_id"] == a["todo_id"]
