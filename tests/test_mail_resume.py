"""Exercise IMAP disconnects with distinct sessions and inspect the real archive."""

import imaplib
import threading

import pytest

from workthread.core import Store, Conflict
from workthread.demo import FakeIMAP
from workthread.mail import Sync
from test_m2 import account
from test_m4 import client


class DropDuringBody(FakeIMAP):
    def __init__(self):
        super().__init__()
        self.closed = False

    def fetch(self, uids, items):
        assert not self.closed
        if self.folder == "INBOX" and uids == [2] and items == ["BODY.PEEK[1]"]:
            raise imaplib.IMAP4.abort("synthetic disconnect")
        return super().fetch(uids, items)

    def shutdown(self):
        self.closed = True


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path)
    account(s)
    return s


def test_automatic_resume_after_body_abort(store):
    broken, fresh = DropDuringBody(), FakeIMAP()
    sessions = iter([broken, fresh])
    sync = Sync(store, lambda _: next(sessions))
    sync.retry_delays = (0,)
    result = sync.run("demo")
    assert broken.closed and result["state"] == "completed"
    assert [n for n, items in fresh.requests if items == ["BODY.PEEK[1]"]] == [2, 3]
    assert result["folders"]["INBOX"] == {"archived": 2, "errors": 0, "total": 2}
    assert not store.rows("SELECT * FROM sync_failures")
    assert len(store.rows("SELECT * FROM mail_occurrences")) == 3
    assert len(store.rows("SELECT * FROM archive_commits")) == 3


def test_exhaust_retries_refresh_and_resume_via_api(store, monkeypatch):
    broken = DropDuringBody()
    sessions = iter([broken, TimeoutError(), ConnectionResetError()])

    def connect(*_):
        session = next(sessions)
        if isinstance(session, Exception):
            raise session
        return session

    monkeypatch.setattr("workthread.demo.FakeIMAP", connect)
    monkeypatch.setattr(Sync, "retry_delays", (0, 0))
    http, headers = client(store)
    outcome = http.post("/api/v1/accounts/demo/sync", headers=headers).get_json()
    assert outcome["attempt"] == 2 and outcome["state"] == "interrupted"
    assert not store.rows("SELECT * FROM sync_failures")

    # Re-open from disk with a new server session, then press the same sync endpoint.
    http, headers = client(Store(store.root))
    progress = http.get("/api/v1/accounts/sync-status").get_json()["demo"]
    assert progress["state"] == "interrupted"
    assert progress["folders"] == {
        "INBOX": {"archived": 1, "errors": 0, "total": 2},
        "Sent": None,
    }
    fresh = FakeIMAP()
    monkeypatch.setattr("workthread.demo.FakeIMAP", lambda *_: fresh)
    assert (
        http.post("/api/v1/accounts/demo/sync", headers=headers).get_json()["state"]
        == "completed"
    )
    assert [n for n, items in fresh.requests if items == ["BODY.PEEK[1]"]] == [2, 3]
    assert len(store.rows("SELECT * FROM messages")) == 3


def test_reconnect_checks_uid_namespace_before_fetch(store):
    broken, changed = DropDuringBody(), FakeIMAP()
    changed.validity += 1
    sessions = iter([broken, changed])
    sync = Sync(store, lambda _: next(sessions))
    sync.retry_delays = (0,)
    result = sync.run("demo")
    assert result["state"] == "blocked" and result["folder"] == "INBOX"
    assert not changed.requests
    assert store.rows("SELECT uidvalidity FROM mail_folders") == [{"uidvalidity": 100}]
    assert len(store.rows("SELECT * FROM mail_occurrences")) == 1


def test_live_status_and_exclusion_during_reconnect(store):
    broken = DropDuringBody()
    waiting, release = threading.Event(), threading.Event()
    responses = []

    def connect(_):
        if not broken.closed:
            return broken
        waiting.set()
        assert release.wait(10)
        return FakeIMAP()

    sync = Sync(store, connect)
    sync.retry_delays = (0,)
    thread = threading.Thread(target=lambda: responses.append(sync.run("demo")))
    thread.start()
    try:
        assert waiting.wait(10)
        other = Sync(Store(store.root))
        assert other.status("demo")["state"] == "reconnecting"
        with pytest.raises(Conflict):
            other.run("demo")
    finally:
        release.set()
        thread.join(10)
    assert responses[0]["state"] == "completed"


def test_hole_below_high_water_and_mime_error(store):
    class BadMime(FakeIMAP):
        def fetch(self, uids, items):
            result = super().fetch(uids, items)
            if uids == [1] and "BODYSTRUCTURE" in items:
                result[1][b"BODYSTRUCTURE"] = ()
            return result

    partial = Sync(store, lambda _: BadMime()).run("demo")
    assert partial["state"] == "partial" and partial["folders"]["INBOX"]["errors"] == 1
    assert store.rows("SELECT error FROM sync_failures") == [{"error": "UnsafeMime"}]
    fresh = FakeIMAP()
    assert Sync(store, lambda _: fresh).run("demo")["state"] == "completed"
    assert [n for n, items in fresh.requests if items == ["BODY.PEEK[1]"]] == [1]
    assert not store.rows("SELECT * FROM sync_failures")


def test_authentication_and_local_write_errors_do_not_reconnect(store, monkeypatch):
    from imapclient.exceptions import LoginError

    attempts = []

    def denied(_):
        attempts.append(1)
        raise LoginError("synthetic")

    sync = Sync(store, denied)
    with pytest.raises(LoginError):
        sync.run("demo")
    assert attempts == [1] and sync.status("demo")["state"] == "failed"

    def disk_full(*_):
        raise OSError("synthetic local disk failure")

    sync = Sync(store, lambda _: FakeIMAP())
    monkeypatch.setattr(sync.archive, "record", disk_full)
    with pytest.raises(OSError):
        sync.run("demo")
    assert sync.status("demo")["attempt"] == 0
    assert not store.rows("SELECT * FROM sync_failures")


@pytest.mark.parametrize(
    ("listing", "expected"),
    [
        ([((b"\\sEnT",), ".", "外发"), ((), ".", "Sent Items")], "外发"),
        ([((), "/", "已发送")], "已发送"),
        ([((), ".", "INBOX.Sent Items")], "INBOX.Sent Items"),
        ([((), "/", "[Gmail]/已发送邮件")], "[Gmail]/已发送邮件"),
        ([((), "/", "存档/Sent"), ((b"\\NoSelect", b"\\Sent"), "/", "已发送")], None),
        ([((), "/", "Sent"), ((), "/", "已发送")], None),
        ([((b"\\Sent",), "/", "一"), ((b"\\Sent",), "/", "二")], None),
        ([((), "/", "Outbox")], None),
    ],
)
def test_sent_folder_discovery(listing, expected):
    fake = FakeIMAP()
    fake.list_folders = lambda: listing
    assert Sync._sent_options(fake, [])["detected"] == expected


def test_unknown_sent_then_select_on_existing_account(store, monkeypatch):
    from workthread.core import load

    with store.db() as c:
        c.execute("UPDATE mail_accounts SET account_id='test'")
    (before,) = store.rows("SELECT * FROM mail_accounts")
    fresh = FakeIMAP()
    fresh.list_folders = lambda: [
        ((), "/", "INBOX"),
        ((), "/", "往来/对外"),
        ((b"\\Noselect",), "/", "往来"),
    ]
    monkeypatch.setattr(Sync, "_connect", lambda *_: fresh)
    http, headers = client(store)
    route = "/api/v1/accounts/test"

    def post(path, body):
        return http.post(route + path, json=body, headers=headers)

    result = post("/sync", {}).get_json()
    assert result["state"] == "partial" and result["sent_unresolved"]
    assert result["folders"]["INBOX"]["archived"] == 2
    assert http.get("/api/v1/accounts/sync-status").get_json()["test"][
        "sent_unresolved"
    ]
    options = post("/folders", {}).get_json()
    assert options == {
        "names": ["往来/对外"],
        "detected": None,
        "automatic": True,
        "current": None,
    }
    assert post("/folders", {"sent": "往来"}).status_code == 400
    assert post("/folders", {"sent": "INBOX"}).status_code == 400
    assert post("/folders", {"sent": "往来/对外"}).get_json()["saved"]
    (after,) = store.rows("SELECT * FROM mail_accounts")
    assert load(after.pop("folders")) == [
        {"name": "INBOX", "direction": "inbox"},
        {"name": "往来/对外", "direction": "sent"},
    ]
    before.pop("folders")
    assert after == before
    fresh.requests.clear()
    result = post("/sync", {}).get_json()
    assert result["state"] == "completed" and "sent_unresolved" not in result
    assert [n for n, items in fresh.requests if items == ["BODY.PEEK[1]"]] == [3]
    assert len(store.rows("SELECT * FROM mail_occurrences")) == 3
    assert post("/folders", {"sent": None}).get_json()["saved"]
    assert set(post("/sync", {}).get_json()["folders"]) == {"INBOX"}
    assert len(store.rows("SELECT * FROM mail_occurrences")) == 3


def test_remove_mail_account_retains_archive_and_is_retryable(store, monkeypatch):
    import keyring

    with store.db() as c:
        c.execute("UPDATE mail_accounts SET account_id='test',enabled=1")
    Sync(store, lambda _: FakeIMAP()).run("test")
    tables = (
        "messages",
        "mail_occurrences",
        "mail_folders",
        "archive_commits",
        "sync_runs",
    )
    original = {t: store.rows("SELECT * FROM " + t) for t in tables}
    http, headers = client(store)
    secrets = {"synthetic": "fake"}
    monkeypatch.setattr(keyring, "get_password", lambda _, ref: secrets.get(ref))

    def fail(*_):
        raise keyring.errors.KeyringError("synthetic")

    monkeypatch.setattr(keyring, "delete_password", fail)
    route = "/api/v1/accounts/test"
    with Sync(store).exclusive("test"):
        assert http.delete(route, headers=headers).status_code == 409
    assert http.delete(route, headers=headers).status_code == 500
    assert store.rows("SELECT host,enabled FROM mail_accounts") == [
        {"host": "imap.example.org", "enabled": 1}
    ]
    monkeypatch.setattr(keyring, "delete_password", lambda _, ref: secrets.pop(ref))
    assert http.delete(route, headers=headers).get_json()["removed"]
    assert not secrets
    assert http.delete(route, headers=headers).get_json()["removed"]
    assert not http.get("/api/v1/snapshot").get_json()["accounts"]
    assert not http.get("/api/v1/accounts/sync-status").get_json()
    assert (
        http.post(
            route + "/enabled", headers=headers, json={"enabled": True}
        ).status_code
        == 400
    )
    assert http.post(route + "/sync", headers=headers).status_code == 400
    assert {t: store.rows("SELECT * FROM " + t) for t in tables} == original


def test_separated_network_failures_get_fresh_budget_after_a_saved_mail(store):
    first, second, last = DropDuringBody(), FakeIMAP(), FakeIMAP()
    second.fail_uid = 3
    sessions = iter([first, second, last])
    sync = Sync(store, lambda _: next(sessions))
    sync.retry_delays = (0,)
    assert sync.run("demo")["state"] == "completed"
    assert [uid for uid, parts in last.requests if parts == ["BODY.PEEK[1]"]] == [3]
    assert len(store.rows("SELECT * FROM archive_commits")) == 3


def test_sqlite_busy_after_jsonl_append_recovers_without_duplicate(store, monkeypatch):
    import json
    import sqlite3
    from workthread.mail import Archive

    original = Archive._finish
    faults = []

    def finish(archive, conn, tx, payload):
        if not faults and payload["occurrence"]["imap_uid"] == 2:
            with sqlite3.connect(store.path) as blocker:
                blocker.execute("BEGIN IMMEDIATE")
                conn.execute("PRAGMA busy_timeout=0")
                try:
                    return original(archive, conn, tx, payload)
                except sqlite3.OperationalError as exc:
                    faults.append(exc.sqlite_errorcode)
                    raise
        return original(archive, conn, tx, payload)

    monkeypatch.setattr(Archive, "_finish", finish)
    monkeypatch.setattr(Sync, "database_retry_delays", (0,))
    http, headers = client(store)
    response = http.post("/api/v1/accounts/demo/sync", headers=headers)
    assert response.status_code == 200
    assert response.get_json()["state"] == "completed"
    assert faults == [sqlite3.SQLITE_BUSY]
    assert len(store.rows("SELECT * FROM mail_occurrences")) == 3
    assert [r["state"] for r in store.rows("SELECT state FROM sync_runs ORDER BY rowid")] == [
        "database_wait", "completed"
    ]
    commits = store.rows("SELECT tx_id FROM archive_commits WHERE state='committed'")
    assert len(commits) == 3
    for part in ("meta", "body"):
        ids = [json.loads(line)["archive_tx_id"]
               for file in (store.data / part).glob("*.jsonl")
               for line in file.read_text(encoding="utf-8").splitlines()]
        assert sorted(ids) == sorted(r["tx_id"] for r in commits)


def test_readonly_database_reports_sqlite_code_and_uid_without_retry(store, monkeypatch):
    from workthread.mail import Archive

    original = Archive._finish
    def readonly(archive, conn, tx, payload):
        conn.execute("PRAGMA query_only=ON")
        return original(archive, conn, tx, payload)

    monkeypatch.setattr(Archive, "_finish", readonly)
    http, headers = client(store)
    response = http.post("/api/v1/accounts/demo/sync", headers=headers)
    assert response.status_code == 500 and "SQLITE_READONLY" in response.get_json()["error"]
    status = http.get("/api/v1/accounts/sync-status").get_json()["demo"]
    assert status["state"] == "failed" and "只读" in status["error_detail"]
    assert (status["stage"], status["folder"], status["current_uid"]) == ("归档邮件", "INBOX", 1)
    assert len(store.rows("SELECT * FROM sync_runs")) == 1


def test_persistent_sqlite_contention_stops_after_budget(store, monkeypatch):
    import sqlite3
    from workthread.mail import Archive

    original = Archive._finish

    def busy(archive, conn, tx, payload):
        with sqlite3.connect(store.path) as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            conn.execute("PRAGMA busy_timeout=0")
            return original(archive, conn, tx, payload)

    monkeypatch.setattr(Archive, "_finish", busy)
    monkeypatch.setattr(Sync, "database_retry_delays", (0, 0))
    http, headers = client(store)
    response = http.post("/api/v1/accounts/demo/sync", headers=headers)
    assert response.status_code == 500 and "SQLITE_BUSY" in response.get_json()["error"]
    assert http.get("/api/v1/accounts/sync-status").get_json()["demo"]["state"] == "failed"
    assert len(store.rows("SELECT * FROM sync_runs")) == 3
    assert not store.rows("SELECT * FROM mail_occurrences")
