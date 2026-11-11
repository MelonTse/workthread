"""Failures use actionable, persistent diagnostics without copying remote payloads."""

import errno
import http.client
import imaplib
import io
import json
import sqlite3
import ssl
import urllib.error
import urllib.request

import pytest
from test_m2 import account
from test_updates import init

from workthread.core import Store
from workthread.demo import FakeIMAP
from workthread.diagnostics import describe_error
from workthread.mail import Sync
from workthread.server import create_app
from workthread.updating import controller as ctl
from workthread.updating import releases as rel

SECRET = "Authorization: secret@example.org token=PRIVATE-SYNTHETIC"


@pytest.mark.parametrize(
    "error,hint",
    [
        (PermissionError(SECRET), "访问被拒绝"),
        (OSError(errno.ENOSPC, SECRET), "磁盘空间不足"),
        (ssl.SSLCertVerificationError(SECRET), "证书验证失败"),
        (ConnectionRefusedError(SECRET), "拒绝连接"),
        (http.client.RemoteDisconnected(SECRET), "连接被关闭"),
        (RuntimeError(SECRET), "尚未确定"),
        (
            urllib.error.HTTPError(
                "https://example.org/?" + SECRET, 407, SECRET, {}, None
            ),
            "代理要求身份验证",
        ),
    ],
)
def test_safe_diagnostic(error, hint):
    assert hint in describe_error(error)
    assert SECRET not in describe_error(error)


@pytest.mark.parametrize(
    "code,hint",
    [
        (sqlite3.SQLITE_BUSY, "正忙"),
        (sqlite3.SQLITE_FULL, "空间已满"),
        (sqlite3.SQLITE_READONLY, "只读"),
        (sqlite3.SQLITE_CORRUPT, "停止写入"),
        (sqlite3.SQLITE_IOERR, "读写失败"),
    ],
)
def test_database_code_not_arbitrary_sql(code, hint):
    error = sqlite3.OperationalError(SECRET)
    error.sqlite_errorcode = code
    assert hint in describe_error(error) and SECRET not in describe_error(error)


class Response(io.BytesIO):
    def geturl(self):
        return "https://release-assets.githubusercontent.com/file?signature=" + SECRET


@pytest.mark.parametrize("failure", ["read-error", "short-body"])
def test_metadata_body_retry_starts_fresh(monkeypatch, failure):
    class Broken(Response):
        @property
        def headers(self):
            return {"Content-Length": "999"}

        def read(self, n):
            if failure == "read-error":
                raise http.client.IncompleteRead(b"secret-partial", 9)
            return b"{"

    calls = []

    def request(req, timeout):
        calls.append(req.full_url)
        return Broken() if len(calls) == 1 else Response(b'{"ok":true}')

    monkeypatch.setattr(urllib.request, "urlopen", request)
    assert rel.fetch("https://github.com/update.json", 100) == b'{"ok":true}'
    assert calls == ["https://github.com/update.json"] * 2


def test_network_error_stage_resource_no_signed_url(monkeypatch):
    class Broken(Response):
        def read(self, n):
            raise ConnectionAbortedError(SECRET)

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Broken())
    with pytest.raises(ValueError) as raised:
        rel.fetch("https://github.com/update.sig", 256)
    text = str(raised.value)
    assert all(
        x in text
        for x in (
            "update.sig",
            "release-assets.githubusercontent.com",
            "读取响应内容",
            "尝试 2 次",
            "ConnectionAbortedError",
        )
    )
    assert SECRET not in text and "signature=" not in text


def test_update_failure_survives_reload_and_clears_on_success(tmp_path, monkeypatch):
    init(tmp_path, seed_spaces=False)
    monkeypatch.setattr(rel, "trust", lambda: None)

    def fail(*args):
        raise ConnectionRefusedError(SECRET)

    monkeypatch.setattr(rel, "discover", fail)
    u = ctl.Updates(tmp_path)
    with pytest.raises(ValueError, match="拒绝连接.*诊断编号"):
        u.action("check")
    recovered = ctl.Updates(tmp_path)
    info = recovered.status()["last_error"]
    assert info == u.status()["last_error"] and info["operation"] == "检查更新"
    assert SECRET not in json.dumps(info)
    monkeypatch.setattr(rel, "discover", lambda *args: None)
    assert "成功读取发布列表" in recovered.action("check")["check_message"]
    assert ctl.Updates(tmp_path).status()["last_error"] is None


def test_unknown_api_error_has_traceable_safe_reference(tmp_path, caplog):
    app = create_app(Store(tmp_path))

    @app.get("/synthetic-failure")
    def fail():
        raise RuntimeError(SECRET)

    response = app.test_client().get("/synthetic-failure")
    assert response.status_code == 500
    reference = response.json["diagnostic_id"]
    assert reference in response.json["error"] and reference in caplog.text
    assert SECRET not in response.text + caplog.text
    assert "原数据已保留" not in response.text


def test_mail_login_error_and_reconnect_cause_persist(tmp_path, monkeypatch):
    s = Store(tmp_path)
    account(s)
    sync = Sync(s)

    def login(account, progress):
        progress["stage"] = "登录邮箱"
        raise imaplib.IMAP4.error(SECRET)

    monkeypatch.setattr(sync, "_connect", login)
    with pytest.raises(imaplib.IMAP4.error):
        sync.run("demo")
    result = Sync(Store(tmp_path)).status("demo")
    assert result["state"] == "failed" and "拒绝登录" in result["error_detail"]
    assert SECRET not in json.dumps(Sync(Store(tmp_path)).status("demo"))

    def connection(*a):
        raise TimeoutError(SECRET)

    retry = Sync(s, connection)
    retry.retry_delays = (0,)
    result = retry.run("demo")
    assert result["state"] == "interrupted" and result["stage"] == "连接邮箱"
    assert (
        "超时" in result["error_detail"] and "自动重连 1 次" in result["error_detail"]
    )
    assert len(s.rows("SELECT * FROM messages")) == 0


def test_single_mail_failure_visible_without_losing_other_mail(tmp_path):
    s = Store(tmp_path)
    account(s)

    class BadMime(FakeIMAP):
        def fetch(self, uids, items):
            result = super().fetch(uids, items)
            if uids == [1] and "BODYSTRUCTURE" in items:
                result[1][b"BODYSTRUCTURE"] = ()
            return result

    result = Sync(s, lambda _: BadMime()).run("demo")
    assert result["state"] == "partial" and len(s.rows("SELECT * FROM messages")) == 2
    issue = result["message_errors"][0]
    assert (
        issue["uid"] == 1
        and issue["folder"] == "INBOX"
        and "未返回邮件正文结构" in issue["detail"]
    )
    assert (
        Sync(Store(tmp_path)).status("demo")["message_errors"]
        == result["message_errors"]
    )
