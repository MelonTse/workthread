"""Deliberately synthetic portable packages, never real Windows binaries or release keys."""

import base64
import contextlib
import hashlib
import json
import multiprocessing
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from filelock import FileLock

from workthread.ai import Bridge
from workthread.core import Store
from workthread.demo import seed
from workthread.deployment import install_templates
from workthread.server import create_app
from workthread.updating import controller as ctl
from workthread.updating import releases as rel
from workthread.updating import transaction as tx

ROOT = Path(__file__).resolve().parents[1]
OLD = sorted(rel.RC3)
NEW = "e" * 40
CMDS = ("Start", "Health", "Backup", "Restore", "Install")


def identity(v, sha):
    return {"version": v, "commit_sha": sha, "runner_os": "Windows", "machine": "AMD64"}


def init(root, sha=OLD[0], seed_spaces=True):
    (root / "app").mkdir(parents=True)
    (root / tx.EXE).write_bytes(b"old synthetic binary")
    rel.save(root / "BUILD_INFO.json", identity("1.0.0rc3", sha))
    for name in CMDS:
        (root / (name + ".cmd")).write_bytes(b"legacy cmd")
    rel.save(
        root / "SHA256SUMS.json",
        {
            "app/WorkThread.exe": rel.digest(root / tx.EXE),
            **{n + ".cmd": rel.digest(root / (n + ".cmd")) for n in CMDS},
        },
    )
    if not seed_spaces:
        return
    for n in tx.SPACES:
        s = Store(root / n)
        seed(s)
        install_templates(s)
        s.set_setting(
            "ai_schedule", {"enabled": True, "frequency": "daily", "time": "08:30"}
        )
        s.create_todo({"raw_input": n, "title": n, "no_due_date": True}, key=n)
        Bridge(s).prepare()
        with s.db() as c:
            c.execute("UPDATE mail_accounts SET enabled=1 WHERE account_id='demo'")
        for path in (
            "backups/旧备份.zip",
            "agent-workspace/custom.md",
            "agent-workspace/exchange/outputs/unread.json",
            "config/local.txt",
        ):
            dest = s.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("合成/" + n + "/" + path, encoding="utf-8")


def package(tmp, key, sha=NEW, v="1.0.0rc4", sources=None, extra=None):
    name = f"WorkThread-{v}-windows-x64"
    db = {
        "app/WorkThread.exe": b"synthetic-only",
        "BUILD_INFO.json": json.dumps(identity(v, sha)).encode(),
        "Run.cmd": (ROOT / "scripts/portable-run.cmd").read_bytes(),
    }
    db["tools/PortableLauncher.exe"] = b"synthetic fixed launcher"
    for n in CMDS:
        db[n + ".cmd"] = (
            ROOT / ("scripts/portable-" + n.lower() + ".cmd")
        ).read_bytes()
    db.update(extra or {})
    db["SHA256SUMS.json"] = json.dumps(
        {n: hashlib.sha256(b).hexdigest() for n, b in db.items()}
    ).encode()
    archive = tmp / (name + ".zip")
    with zipfile.ZipFile(archive, "w") as z:
        for n, b in db.items():
            z.writestr(name + "/" + n, b)
    m = {
        "format": 1,
        "repository": rel.REPO,
        "platform": "windows-x64",
        "version": v,
        "commit_sha": sha,
        "sources": sources or ["1.0.0rc3@" + old for old in OLD],
        "asset": archive.name,
        "size": archive.stat().st_size,
        "sha256": rel.digest(archive),
    }
    doc = json.dumps(m).encode()
    return archive, doc, base64.b64encode(key.sign(doc)), key.public_key()


def check(bundle, trial, logical):
    tx.probe(trial, logical)


def apply(root, args, **kw):
    return tx.apply(
        root,
        *args,
        quiet=kw.pop("quiet", lambda: None),
        check=kw.pop("check", check),
        **kw,
    )


def records(root):
    out = []
    for n in tx.SPACES:
        path = root / n
        with contextlib.closing(
            sqlite3.connect(
                (path / "data/workthread.sqlite3").as_uri() + "?mode=ro&immutable=1",
                uri=True,
            )
        ) as c:
            tables = [
                r[0]
                for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            ]
            out.append(
                {
                    t: sorted(map(repr, c.execute(f'SELECT * FROM "{t}"')))
                    for t in tables
                }
            )
        out.append(
            {
                k: v
                for k, v in tx.catalog(path).items()
                if not k.startswith("data/workthread.sqlite3")
                and not k.endswith(".workthread-deployment.json")
            }
        )
    return out


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "中文 原安装"
    init(root)
    return root, package(tmp_path, Ed25519PrivateKey.generate())


@pytest.mark.parametrize("old", OLD)
def test_preserve_every_table_and_file_and_real_stable_paths(tmp_path, old):
    root = tmp_path / "中文 空格"
    init(root, old)
    key = Ed25519PrivateKey.generate()
    args = package(tmp_path, key)
    prior = records(root)
    assert apply(root, args)["version"] == "1.0.0rc4"
    assert records(root) == prior
    assert tx.current(root)[1] == identity("1.0.0rc4", NEW)
    assert (root / tx.STATE / "base" / tx.EXE).read_bytes() == b"old synthetic binary"
    assert (root / tx.EXE).read_bytes() == b"synthetic fixed launcher"
    for n in tx.SPACES:
        assert rel.read(root / n / "agent-workspace/.workthread-deployment.json")[
            "workspace"
        ] == str(root / n / "agent-workspace")
    # A committed install never automatically rewinds even if new business writes exist.
    (root / "workspace/after.txt").write_text("new")
    tx.recover(root)
    assert (root / "workspace/after.txt").read_text() == "new"
    args2 = package(tmp_path, key, "f" * 40, "1.0.0rc5", ["1.0.0rc4@" + NEW])
    prior = records(root)
    assert apply(root, args2)["version"] == "1.0.0rc5"
    assert records(root) == prior


def hard_stop(root, arch, doc, sig, pub, at):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    def die(step):
        if step == at:
            os._exit(77)

    apply(root, (arch, doc, sig, Ed25519PublicKey.from_public_bytes(pub)), hook=die)


@pytest.mark.parametrize(
    "at",
    [
        "saved-workspace",
        "placed-workspace",
        "saved-acceptance",
        "placed-acceptance",
        "pointer",
    ],
)
def test_process_death_and_fresh_recovery(setup, at):
    root, (archive, doc, sig, key) = setup
    before = [tx.catalog(root / n) for n in tx.SPACES]
    p = multiprocessing.get_context("spawn").Process(
        target=hard_stop, args=(root, archive, doc, sig, key.public_bytes_raw(), at)
    )
    p.start()
    p.join(30)
    assert p.exitcode == 77
    # Separate process; all Python exception/finally cleanup was bypassed.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from workthread.updating.transaction import recover;from pathlib import Path;import sys;recover(Path(sys.argv[1]))",
            str(root),
        ],
        check=False,
    )
    assert result.returncode == 0
    tx.recover(root)
    assert [tx.catalog(root / n) for n in tx.SPACES] == before
    assert tx.current(root)[1]["commit_sha"] in OLD


@pytest.mark.parametrize(
    "fault",
    [
        "disk",
        "corrupt",
        "signature",
        "writer",
        "copy-migration",
        "custom",
        "unsupported",
        "session",
        "during-copy",
        "io-switch",
        "future-schema",
    ],
)
def test_failures_leave_originals_available(setup, fault, monkeypatch):
    root, args = setup
    kw = {}
    if fault == "disk":
        monkeypatch.setattr(
            tx.shutil, "disk_usage", lambda _: shutil._ntuple_diskusage(1, 1, 0)
        )
    if fault == "corrupt":
        with args[0].open("ab") as f:
            f.write(b"altered")
    if fault == "signature":
        args = (*args[:2], b"AAAA", args[3])
    if fault == "writer":

        def busy():
            raise ValueError("WorkBuddy open")

        kw["quiet"] = busy
    if fault == "copy-migration":

        def migration(bundle, trial, logical):
            (trial / "data/workthread.sqlite3").write_bytes(b"failure on trial only")
            raise ValueError("migration")

        kw["check"] = migration
    if fault == "custom":
        (root / "workspace/agent-workspace/CODEBUDDY.md").write_text(
            "保留手工内容", encoding="utf-8"
        )
    if fault == "unsupported":
        rel.save(root / "BUILD_INFO.json", identity("1.0.0rc3", "0" * 40))
    if fault == "future-schema":
        with Store(root / "acceptance").db() as db:
            db.execute("INSERT INTO schema_migrations VALUES (99,'future')")
    lock = contextlib.nullcontext()
    if fault == "session":
        (root / tx.STATE).mkdir()
        lock = FileLock(str(root / tx.STATE / "session-active.lock"))
    if fault == "during-copy":
        calls = []

        def changes():
            if calls:
                (root / "workspace/external.txt").write_text("new work")
            calls.append(1)

        kw["quiet"] = changes
    if fault == "io-switch":

        def fail(step):
            if step == "placed-workspace":
                raise OSError("synthetic write failure")

        kw["hook"] = fail
    before = [tx.catalog(root / n) for n in tx.SPACES]
    with lock, pytest.raises((ValueError, OSError)):
        apply(root, args, **kw)
    after = [tx.catalog(root / n) for n in tx.SPACES]
    if fault == "during-copy":
        assert after[0].pop("external.txt") == hashlib.sha256(b"new work").hexdigest()
    assert after == before
    assert tx.current(root)[1]["version"] == "1.0.0rc3"


def test_recovery_refuses_to_displace_post_crash_writes(setup):
    root, args = setup

    class PowerLoss(BaseException):
        pass

    def die(s):
        if s == "placed-workspace":
            raise PowerLoss

    with pytest.raises(PowerLoss):
        apply(root, args, hook=die)
    (root / "workspace/external").write_text("must keep")
    with pytest.raises(ValueError, match="新写入"):
        tx.recover(root)
    assert (root / "workspace/external").is_file()
    assert list(
        (root / tx.STATE / "transactions").glob(
            "*/old/workspace/data/workthread.sqlite3"
        )
    )


def test_ui_progress_requires_confirmation_and_local_csrf(setup, monkeypatch):
    root, (archive, doc, sig, key) = setup
    calls = []

    def fetch(url, limit, out=None):
        calls.append(url)
        if "/api.github.com/" in url:
            return json.dumps(
                [
                    {
                        "tag_name": "v1.0.0rc4",
                        "prerelease": True,
                        "draft": False,
                        "body": "合成候选",
                        "assets": [
                            {"name": n}
                            for n in ("update.json", "update.sig", archive.name)
                        ],
                    }
                ]
            ).encode()
        if url.endswith("update.json"):
            return doc
        if url.endswith("update.sig"):
            return sig
        out.write(archive.read_bytes())

    monkeypatch.setattr(rel, "fetch", fetch)
    monkeypatch.setattr(rel, "trust", lambda: key)
    monkeypatch.setattr(tx, "native_quiet", lambda **_: None)
    handoff = []
    monkeypatch.setattr(ctl, "detached", handoff.append)
    u = ctl.Updates(root, lambda: handoff.append("stopped"))
    app = create_app(Store(root / "workspace"), u).test_client()
    token = re.search(r'name="csrf-token" content="([^"]+)"', app.get("/").text)[1]
    url = "/api/v1/software-update"
    assert app.get(url).json["offer"] is None and not calls
    assert app.post(url + "/check", json={}).status_code == 403

    def post(action, **kw):
        return app.post(url + "/" + action, headers={"X-CSRF-Token": token}, json=kw)

    assert post("check").json["offer"]["version"] == "1.0.0rc4"
    assert post("download").json["ready"]
    assert post("apply").status_code == 400 and not handoff
    assert post("apply", confirmed=True).status_code == 200 and handoff[-1] == "stopped"
    assert app.get(url).status_code == 503
    assert len(calls) == 4 and all("example.org" not in url for url in calls)


def test_release_policy_and_signatures(setup):
    root, args = setup
    _, doc, sig, key = args
    source = tx.current(root)[1]
    assert rel.signed(doc, sig, key, source)["version"] == "1.0.0rc4"
    private = Ed25519PrivateKey.generate()
    for changes in (
        {"repository": "other/repo"},
        {"platform": "linux"},
        {"version": "1.0.0rc2"},
        {"sources": ["1.0.0rc3@unknown"]},
        {"asset": "different.zip"},
    ):
        changed = json.dumps({**json.loads(doc), **changes}).encode()
        with pytest.raises(ValueError):
            rel.signed(
                changed,
                base64.b64encode(private.sign(changed)),
                private.public_key(),
                source,
            )
    m = json.loads(doc)
    stable = identity("0.9.0", OLD[0])
    changed = json.dumps({**m, "sources": ["0.9.0@" + OLD[0]]}).encode()
    with pytest.raises(ValueError):
        rel.signed(
            changed,
            base64.b64encode(private.sign(changed)),
            private.public_key(),
            stable,
        )


def test_unknown_old_directory_readonly_report(tmp_path):
    p = tmp_path / "unidentified"
    p.mkdir()
    original = tx.catalog(p)
    assert not tx.inspect(p)["supported"]
    assert tx.catalog(p) == original


def test_block_unsafe_archive_before_program_execution(tmp_path):
    key = Ed25519PrivateKey.generate()
    archive, doc, sig, pub = package(tmp_path, key, extra={"../escape": b"no"})
    m = rel.signed(doc, sig, pub, identity("1.0.0rc3", OLD[0]))
    with pytest.raises(ValueError, match="路径"):
        rel.extract(archive, tmp_path / "stage", m)
    assert not (tmp_path / "escape").exists()


def test_running_waitress_server_returns_confirmation_and_drains(tmp_path, monkeypatch):
    import http.cookiejar
    import socket
    import threading
    import time
    import urllib.request

    from workthread.cli import main

    class TestStop(ctl.Updates):
        def action(self, name, confirmed=False):
            assert name == "apply" and confirmed
            self.stopping = True
            self.stop()
            return {"stopping": True}

    monkeypatch.setattr(ctl, "Updates", TestStop)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    errors = []

    def run():
        try:
            main(
                [
                    "--workspace",
                    str(tmp_path / "synthetic"),
                    "serve",
                    "--port",
                    str(port),
                ]
            )
        except Exception as e:  # noqa: BLE001 - forward server-thread failures to the assertion
            errors.append(e)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    for _ in range(100):
        try:
            with opener.open(url, timeout=2) as response:
                html = response.read().decode()
            break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail(str(errors))
    token = re.search(r'name="csrf-token" content="([^"]+)"', html)[1]
    req = urllib.request.Request(
        url + "/api/v1/software-update/apply",
        data=b'{"confirmed":true}',
        headers={"Content-Type": "application/json", "X-CSRF-Token": token},
    )
    with opener.open(req, timeout=5) as response:
        assert json.load(response) == {"stopping": True}
    thread.join(8)
    assert not errors and not thread.is_alive()
