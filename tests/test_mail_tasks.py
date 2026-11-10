"""Verify the async HTTP contract with actual SQLite, account locks and IMAP fixtures."""

import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from workthread.core import Conflict, Store
from workthread.demo import FakeIMAP
from workthread.mail_tasks import MailTasks
from workthread.operations import backup, restore
from test_m2 import account
from test_m4 import client


def finished(http, location):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = http.get(location)
        assert response.status_code == 200
        if response.json["state"] not in {
            "queued",
            "running",
            "database_wait",
            "reconnecting",
        }:
            return response.json
        time.sleep(0.02)
    pytest.fail("background mail task did not finish")


def test_dispatch_reload_dedup_history_and_restore(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    account(store)
    archive = tmp_path / "before.zip"
    backup(store, archive)
    entered, unblock = threading.Event(), threading.Event()
    sessions = []

    class Paused(FakeIMAP):
        def __init__(self, settings=None):
            super().__init__(settings)
            sessions.append(self)

        def fetch(self, uids, items):
            if uids == [2]:
                entered.set()
                assert unblock.wait(10)
            return super().fetch(uids, items)

    monkeypatch.setattr("workthread.demo.FakeIMAP", Paused)
    http, headers = client(store)
    url = "/api/v1/accounts/demo/sync-tasks"
    assert http.post(url).status_code == 403
    assert http.post(url.replace("demo", "unknown"), headers=headers).status_code == 400
    payload = {"request_id": "7573d39e-0a44-4175-bf85-d85c2c59ab3d"}
    result = http.post(url, headers=headers, json=payload)
    location = result.headers["Location"]
    tid = result.json["task_id"]
    assert result.status_code == 202 and result.json["state"] == "queued"
    try:
        assert entered.wait(5)
        # Independent Flask app/session using the same workspace (e.g. a lost reply).
        reopened, fresh_headers = client(Store(store.root))
        for _ in range(2):
            assert reopened.post(url, headers=fresh_headers).json["task_id"] == tid
        assert reopened.get(location).json["folders"]["INBOX"]["archived"] == 1
        assert (
            reopened.get("/api/v1/accounts/sync-status").json["demo"]["task_id"] == tid
        )
        with pytest.raises(Conflict):
            restore(store, archive, apply=True)
    finally:
        unblock.set()
    assert finished(http, location)["state"] == "completed"
    assert len(sessions) == 1 and len(store.rows("SELECT * FROM mail_occurrences")) == 3
    assert http.get(location.replace("/demo/", "/other/")).status_code == 404
    # Once complete, "check new mail" is a new task. The original result survives.
    another = http.post(url, headers=headers)
    assert another.status_code == 202 and another.json["task_id"] != tid
    assert finished(http, another.headers["Location"])["state"] == "completed"
    assert http.get(location).json["state"] == "completed"
    replay = reopened.post(url, headers=fresh_headers, json=payload)
    assert replay.status_code == 200 and replay.json["task_id"] == tid
    assert len(sessions) == 2


def test_shutdown_during_retry_and_scheduler_joins_manual_task(tmp_path, monkeypatch):
    store = Store(tmp_path)
    account(store)
    manager = MailTasks(store)
    assert manager.start("demo", scheduled=True) is None
    with store.db() as c:
        c.execute("UPDATE mail_accounts SET enabled=1 WHERE account_id='demo'")
    failing = threading.Event()

    class Offline(FakeIMAP):
        def fetch(self, uids, items):
            failing.set()
            raise ConnectionResetError()

    monkeypatch.setattr("workthread.demo.FakeIMAP", Offline)
    monkeypatch.setattr("workthread.mail.Sync.retry_delays", (600,))
    task = manager.start("demo", scheduled=True)
    assert failing.wait(5)
    assert manager.start("demo")["task_id"] == task["task_id"]
    manager.close()
    assert manager.get("demo", task["task_id"])["state"] == "interrupted"
    with pytest.raises(Conflict):
        manager.start("demo")
    monkeypatch.setattr("workthread.demo.FakeIMAP", FakeIMAP)
    http, headers = client(store)
    resumed = http.post("/api/v1/accounts/demo/sync-tasks", headers=headers)
    assert resumed.json["task_id"] == task["task_id"]
    assert finished(http, resumed.headers["Location"])["state"] == "completed"


def test_process_crash_after_first_uid_preserves_task_and_resumes(tmp_path):
    workspace = tmp_path / "workspace"
    store = Store(workspace)
    account(store)
    marker = tmp_path / "checkpoint"
    program = """
import sys, time
from pathlib import Path
from workthread import demo
from workthread.core import Store
from workthread.mail_tasks import MailTasks
class Paused(demo.FakeIMAP):
    def fetch(self, uids, items):
        if uids == [2]:
            Path(sys.argv[2]).touch()
            time.sleep(60)
        return super().fetch(uids, items)
demo.FakeIMAP = Paused
MailTasks(Store(sys.argv[1])).start('demo')
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", program, str(workspace), str(marker)],
        env=dict(
            os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src")
        ),
    )
    try:
        deadline = time.monotonic() + 10
        while not marker.exists():
            assert proc.poll() is None and time.monotonic() < deadline
            time.sleep(0.02)
        before = store.setting("mail-sync:demo")
    finally:
        proc.kill()
        proc.wait(timeout=10)
    http, headers = client(Store(workspace))
    stale = http.get("/api/v1/accounts/sync-status").json["demo"]
    assert stale["state"] == "interrupted" and stale["task_id"] == before["task_id"]
    assert stale["folders"]["INBOX"]["archived"] == 1
    resumed = http.post("/api/v1/accounts/demo/sync-tasks", headers=headers)
    assert resumed.json["task_id"] == stale["task_id"]
    assert finished(http, resumed.headers["Location"])["state"] == "completed"
    assert len(store.rows("SELECT * FROM mail_occurrences")) == 3
    assert len(store.rows("SELECT * FROM archive_commits")) == 3


def test_large_folder_resume_fetches_only_missing_uids(tmp_path, monkeypatch):
    store = Store(tmp_path)
    account(store)
    from workthread.mail import Sync

    Sync(store, FakeIMAP).run("demo")
    with store.db() as c:
        folder, message = c.execute(
            "SELECT folder_id,message_id FROM mail_occurrences WHERE imap_uid=1"
        ).fetchone()
        c.executemany(
            "INSERT INTO mail_occurrences VALUES (?,?,?,?,?,?,?)",
            (
                (f"old-{n}", message, "demo", folder, 100, n, "[]")
                for n in range(3, 20000)
            ),
        )

    class LargeMailbox(FakeIMAP):
        def search(self, criteria):
            return (
                range(1, 20001) if self.folder == "INBOX" else super().search(criteria)
            )

        def fetch(self, uids, items):
            assert self.folder == "INBOX" and uids == [20000]
            return {20000: super().fetch([1], items)[1]}

    monkeypatch.setattr("workthread.demo.FakeIMAP", LargeMailbox)
    http, headers = client(store)
    accepted = http.post("/api/v1/accounts/demo/sync-tasks", headers=headers)
    assert accepted.status_code == 202
    result = finished(http, accepted.headers["Location"])
    assert result["state"] == "completed"
    assert result["folders"]["INBOX"] == {
        "total": 20000,
        "archived": 20000,
        "errors": 0,
    }
