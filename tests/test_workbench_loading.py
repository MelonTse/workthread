import io
import socket
import ssl
import threading
import urllib.error
from concurrent.futures import ThreadPoolExecutor

import pytest

from workthread.core import Store
from workthread.demo import seed
from workthread.server import create_app
from workthread.updating import releases


def test_workbench_reads_committed_data_during_import(tmp_path, monkeypatch):
    store = Store(tmp_path)
    seed(store)
    mail = store.rows("SELECT message_id,body_text FROM messages LIMIT 1")[0]
    with store.db() as c:
        c.execute("UPDATE messages SET body_text=?", ("A" * 500,))

    http = create_app(store).test_client()

    def reject_probe():
        pytest.fail("a workbench read performed a deep health check")

    monkeypatch.setattr(store, "health", reject_probe)
    with ThreadPoolExecutor(max_workers=1) as pool, store.db() as c:
        c.execute("UPDATE messages SET body_text='uncommitted'")

        def read_pages():
            response = http.get("/api/v1/snapshot?summary=1")
            assert response.status_code == 200
            msgs = response.json["messages"]
            assert msgs and all(
                m["preview"] == "A" * 100 and "body_text" not in m for m in msgs
            )
            assert (
                http.get("/api/v1/mail/" + mail["message_id"]).json["message"][
                    "body_text"
                ]
                == "A" * 500
            )
            assert http.get("/api/v1/accounts/sync-status").status_code == 200

        pool.submit(read_pages).result(timeout=5)


def test_readers_wait_for_workspace_replacement(tmp_path):
    store = Store(tmp_path)
    entered = threading.Event()

    def read():
        entered.set()
        return store.setting("timezone")

    with ThreadPoolExecutor(max_workers=1) as pool:
        with store.read_lock:
            result = pool.submit(read)
            assert entered.wait(2)
            assert not result.done()
        assert result.result(timeout=5) == "Asia/Shanghai"


@pytest.mark.parametrize(
    ("reason", "hint", "attempts"),
    [
        (ssl.SSLCertVerificationError(), "证书验证失败", 1),
        (socket.gaierror(), "域名解析失败", 1),
        (TimeoutError(), "超时", 2),
    ],
)
def test_update_connection_error_identifies_stage(monkeypatch, reason, hint, attempts):
    calls = []

    def fail(req, timeout):
        calls.append(req.full_url)
        raise urllib.error.URLError(reason)

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(ValueError, match="检查 GitHub 版本列表失败.*" + hint):
        releases.fetch("https://api.github.com/repos/MelonTse/workthread/releases", 100)
    assert len(calls) == attempts


def test_download_interrupted_after_first_chunk_is_not_appended_twice(monkeypatch):
    class Broken(io.BytesIO):
        def geturl(self):
            return "https://github.com/download"

        def read(self, size):
            if self.tell():
                raise ConnectionResetError()
            return super().read(size)

    calls = []

    def open_once(req, timeout):
        calls.append(1)
        return Broken(b"zip-prefix")

    monkeypatch.setattr(urllib.request, "urlopen", open_once)
    out = io.BytesIO()
    with pytest.raises(ValueError, match="下载 Windows 安装包失败"):
        releases.fetch("https://github.com/download", 100, out)
    assert calls == [1] and out.getvalue() == b"zip-prefix"
