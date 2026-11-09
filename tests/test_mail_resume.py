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
