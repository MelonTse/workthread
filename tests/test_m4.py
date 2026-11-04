import re
import pytest
from workthread.core import Store
from workthread.demo import seed
from workthread.operations import backup, restore
from workthread.server import create_app


def client(s):
    c = create_app(s).test_client()
    page = c.get("/")
    token = re.search(r'name="csrf-token" content="([^"]+)"', page.text)[1]
    return c, {"X-CSRF-Token": token}


def test_http_offline_capture_status_two_logs(tmp_path):
    s = Store(tmp_path)
    c, h = client(s)
    r = c.post(
        "/api/v1/todos",
        json={"raw_input": "明天联系客户", "input_at": "2026-01-01T10:00:00+08:00"},
        headers=h,
    )
    assert r.status_code == 201
    t = r.json
    assert t["due_date"] == "2026-01-02"
    r = c.patch(
        "/api/v1/todos/" + t["todo_id"],
        json={"changes": {"status": "in_progress"}, "expected_revision": 1},
        headers=h,
    )
    assert r.status_code == 200
    for content in ("第一次进展", "第二次进展"):
        assert (
            c.post(
                "/api/v1/todos/" + t["todo_id"] + "/progress",
                json={"content": content},
                headers=h,
            ).status_code
            == 201
        )
    assert len(c.get("/api/v1/todos/" + t["todo_id"]).json["logs"]) == 2
    assert c.post("/api/v1/todos", json={"raw_input": "bad"}).status_code == 403
    assert (
        c.post(
            "/api/v1/todos",
            json={"raw_input": "bad"},
            headers={**h, "Origin": "https://evil.example.org"},
        ).status_code
        == 403
    )


def test_backup_restore_both_different_paths_and_bad_password(tmp_path):
    s = Store(tmp_path / "原工作空间")
    seed(s)
    password = "synthetic-password-2026"
    for scope in ("todos", "full"):
        file = tmp_path / (scope + ".7z")
        backup(s, file, password, scope)
        dest = Store(tmp_path / ("新位置 " + scope))
        before = dest.health()
        with pytest.raises(Exception):
            restore(dest, file, "wrong password", True)
        assert dest.health() == before
        assert restore(dest, file, password)["preview"]
        assert restore(dest, file, password, True)["restored"]
        assert len(dest.rows("SELECT * FROM todos")) == len(
            s.rows("SELECT * FROM todos")
        )
        assert len(dest.rows("SELECT * FROM progress_logs")) == len(
            s.rows("SELECT * FROM progress_logs")
        )
        assert dest.health()["ok"]
        if scope == "full":
            assert (dest.root / "agent-workspace/schemas/ai-output.json").exists()
            assert dest.search("Aurora") and dest.setting(
                "workspace_epoch"
            ) != s.setting("workspace_epoch")
            assert not dest.setting("ai_schedule")["enabled"]


def test_http_ai_result_and_draft(tmp_path):
    s = Store(tmp_path)
    seed(s)
    c, h = client(s)
    assert c.post("/api/v1/demo/analyze", json={}, headers=h).status_code == 200
    snapshot = c.get("/api/v1/snapshot").json
    assert snapshot["analyses"] and snapshot["drafts"]
    d = snapshot["drafts"][0]
    assert (
        c.patch(
            "/api/v1/drafts/" + d["draft_id"],
            json={"expected_revision": d["revision"], "body": d["body"] + "\nEdited"},
            headers=h,
        ).status_code
        == 200
    )
    assert s.rows("SELECT * FROM draft_versions")


def test_todo_backup_reimport_is_idempotent(tmp_path):
    s = Store(tmp_path / "a")
    seed(s)
    file = tmp_path / "todos.7z"
    backup(s, file, "password-for-test", "todos")
    target = Store(tmp_path / "b")
    restore(target, file, "password-for-test", True)
    restore(target, file, "password-for-test", True)
    assert len(target.rows("SELECT * FROM todos")) == len(s.rows("SELECT * FROM todos"))
