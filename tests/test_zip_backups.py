"""Plain ZIP portability, manifest integrity and independent restore safety."""

import hashlib
import io
import json
import stat
import subprocess
import sys
import zipfile

import pytest
from test_m4 import client
from test_restore_safety import fingerprints

from workthread.core import Store
from workthread.demo import seed
from workthread.deployment import install_templates
from workthread.operations import backup, restore


def repack(path, mutate, update_hashes=False):
    with zipfile.ZipFile(path) as z:
        files = {name: z.read(name) for name in z.namelist()}
    mutate(files)
    if update_hashes:
        manifest = json.loads(files["manifest.json"])
        manifest["files"] = {
            name: {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            for name, content in files.items()
            if name != "manifest.json"
        }
        manifest["file_count"] = len(manifest["files"])
        manifest["total_size"] = sum(i["size"] for i in manifest["files"].values())
        files["manifest.json"] = json.dumps(manifest).encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)


@pytest.mark.parametrize("scope", ["todos", "full"])
def test_plain_zip_hashes_preview_independent_restore_and_restart(tmp_path, scope):
    source = Store(tmp_path / "原始 合成")
    install_templates(source)
    seed(source)
    file = tmp_path / ("WorkThread-" + scope + ".zip")
    backup(source, file, scope)
    original_archive = file.read_bytes()
    assert zipfile.is_zipfile(file)
    with zipfile.ZipFile(file) as z:
        assert z.testzip() is None
        assert all(not i.flag_bits & 1 for i in z.infolist())
        manifest = json.loads(z.read("manifest.json"))
        assert manifest["format_version"] == 2 and manifest["container"] == "zip"
        assert manifest["file_count"] == len(manifest["files"])
        assert manifest["total_size"] == sum(
            i["size"] for i in manifest["files"].values()
        )
        for name, info in manifest["files"].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == info["sha256"]
            assert len(z.read(name)) == info["size"]
    destination = Store(tmp_path / ("新目录 " + scope))
    before = fingerprints(destination.root)
    preview = restore(destination, file)
    assert preview["preview"] and preview["files"]
    assert fingerprints(destination.root) == before
    assert restore(destination, file, apply=True)["restored"]
    restarted = Store(destination.root)
    for table in ("todos", "todo_sources", "progress_logs", "status_events"):
        assert restarted.rows("SELECT * FROM " + table + " ORDER BY 1") == source.rows(
            "SELECT * FROM " + table + " ORDER BY 1"
        )
    assert restarted.health()["ok"]
    if scope == "full":
        assert restarted.search("Aurora")
        assert restarted.setting("workspace_epoch") != source.setting("workspace_epoch")
        assert not restarted.setting("ai_schedule")["enabled"]
        assert all(
            not a["enabled"] for a in restarted.rows("SELECT * FROM mail_accounts")
        )
        assert all(
            (
                destination.root
                / "agent-workspace/.workbuddy/skills"
                / skill
                / "SKILL.md"
            ).exists()
            for skill in (
                "workthread-analysis",
                "workthread-intake",
                "workthread-knowledge",
            )
        )
    assert file.read_bytes() == original_archive


@pytest.mark.parametrize(
    "damage",
    [
        "truncated",
        "crc",
        "hash",
        "manifest",
        "version",
        "counts",
        "missing",
        "jsonl",
        "database",
    ],
)
def test_bad_zip_rejected_without_changing_destination(tmp_path, damage):
    source = Store(tmp_path / "source")
    seed(source)
    file = tmp_path / "full.zip"
    backup(source, file)
    if damage == "truncated":
        file.write_bytes(file.read_bytes()[:100])
    elif damage == "crc":
        with zipfile.ZipFile(file) as z:
            entry = z.getinfo("data/workthread.sqlite3")
        raw = bytearray(file.read_bytes())
        start = (
            entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
        )
        raw[start + entry.compress_size // 2] ^= 0xFF
        file.write_bytes(raw)
    else:

        def mutate(files):
            if damage == "hash":
                files["data/workthread.sqlite3"] += b"tamper"
            elif damage == "manifest":
                files["manifest.json"] = b"{}"
            elif damage in ("version", "counts"):
                m = json.loads(files["manifest.json"])
                m["format_version" if damage == "version" else "file_count"] = 999
                files["manifest.json"] = json.dumps(m).encode()
            elif damage == "missing":
                del files["data/workthread.sqlite3"]
            elif damage == "database":
                files["data/workthread.sqlite3"] = b"not sqlite"
            elif damage == "jsonl":
                name = next(
                    n
                    for n in files
                    if n.startswith("data/body/") and n.endswith(".jsonl")
                )
                files[name] = b""

        repack(file, mutate, update_hashes=damage in ("jsonl", "database", "missing"))
    target = Store(tmp_path / "destination")
    target.create_todo({"raw_input": "keep original", "no_due_date": True})
    before = fingerprints(target.root)
    original_archive = file.read_bytes()
    for apply in (False, True):
        with pytest.raises(ValueError):
            restore(target, file, apply=apply)
        assert fingerprints(target.root) == before
        assert file.read_bytes() == original_archive


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/absolute",
        "data/../../escape",
        "C:/escape",
        "..\\escape",
        "data/NUL.txt",
        "data/x.",
        "data/Case",
        "manifest.json/child",
    ],
)
def test_unsafe_zip_paths_rejected_before_restore(tmp_path, name):
    file = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(file, "w") as z:
        z.writestr(name, "unsafe")
        if name == "data/Case":
            z.writestr("data/case", "case collision")
        if name == "manifest.json/child":
            z.writestr("manifest.json", "file/ancestor collision")
    target = Store(tmp_path / "target")
    before = fingerprints(target.root)
    with pytest.raises(ValueError):
        restore(target, file, apply=True)
    assert fingerprints(target.root) == before
    assert not (tmp_path / "escape").exists()


def test_zip_symlink_rejected(tmp_path):
    file = tmp_path / "symlink.zip"
    with zipfile.ZipFile(file, "w") as z:
        entry = zipfile.ZipInfo("data/link")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(entry, "../../escape")
    with pytest.raises(ValueError, match="unsafe"):
        restore(Store(tmp_path / "target"), file)


@pytest.mark.parametrize("scope", ["todos", "full"])
def test_http_zip_download_preview_restore_has_no_password(tmp_path, scope):
    source = Store(tmp_path / "source")
    seed(source)
    c, h = client(source)
    download = c.post("/api/v1/backup", json={"scope": scope}, headers=h)
    assert download.status_code == 200 and download.mimetype == "application/zip"
    assert (
        "WorkThread-" + ("Todos" if scope == "todos" else "Full") + "-"
    ) in download.headers["Content-Disposition"]
    archive = download.data
    assert zipfile.is_zipfile(io.BytesIO(archive))
    target = Store(tmp_path / "target")
    c, h = client(target)
    for apply in (False, True):
        r = c.post(
            "/api/v1/restore",
            data={
                "file": (io.BytesIO(archive), "backup.zip"),
                "apply": str(apply).lower(),
            },
            headers=h,
        )
        assert r.status_code == 200 and r.json["restored" if apply else "preview"]
    assert target.rows("SELECT count(*) AS n FROM todos") == source.rows(
        "SELECT count(*) AS n FROM todos"
    )


def test_cli_noninteractive_backup_preview_restore(tmp_path):
    source, target = tmp_path / "source 中文", tmp_path / "target 空格"
    file = tmp_path / "WorkThread-Todos-test.zip"
    s = Store(source)
    s.create_todo({"raw_input": "noninteractive", "no_due_date": True})
    for workspace, args in [
        (source, ["backup", str(file), "--scope", "todos"]),
        (target, ["restore", str(file)]),
        (target, ["restore", str(file), "--apply"]),
    ]:
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "workthread.cli",
                "--workspace",
                str(workspace),
                *args,
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
        assert r.returncode == 0, r.stderr
        assert "password" not in r.stdout.lower()
    assert len(Store(target).rows("SELECT * FROM todos")) == 1


def test_existing_backup_is_never_overwritten(tmp_path):
    s = Store(tmp_path / "source")
    archive = tmp_path / "existing.zip"
    archive.write_bytes(b"preserve existing backup")
    with pytest.raises(ValueError, match="已存在"):
        backup(s, archive)
    assert archive.read_bytes() == b"preserve existing backup"


def test_todo_restore_conflict_rolls_back_all_rows(tmp_path):
    source = Store(tmp_path / "source")
    todo = source.create_todo({"raw_input": "keep", "no_due_date": True})
    source.progress(todo["todo_id"], {"content": "original log"})
    file = tmp_path / "todos.zip"
    backup(source, file, "todos")
    target = Store(tmp_path / "target")
    restore(target, file, apply=True)
    before = fingerprints(target.root)

    def mutate(files):
        data = json.loads(files["todos.json"])
        # The conflict occurs after an earlier new source row would be inserted.
        data["todo_sources"].insert(
            0,
            {
                **data["todo_sources"][0],
                "source_id": "new-source",
                "idempotency_key": "new-key",
            },
        )
        data["progress_logs"][0]["content"] = "conflicting log"
        files["todos.json"] = json.dumps(data).encode()

    repack(file, mutate, update_hashes=True)
    with pytest.raises(ValueError, match="冲突"):
        restore(target, file, apply=True)
    assert fingerprints(target.root) == before


@pytest.mark.parametrize("scope", ["todos", "full"])
def test_backup_restore_preserves_historical_unknown_deadline(tmp_path, scope):
    source = Store(tmp_path / "source")
    t = source.create_todo({"raw_input": "historical pending", "no_due_date": True})
    # Represent an already stored rc1 record; new business writes cannot create it.
    with source.db() as c:
        c.execute("UPDATE todos SET no_due_date=0 WHERE todo_id=?", (t["todo_id"],))
    historical = source.todo(t["todo_id"])
    file = tmp_path / "history.zip"
    backup(source, file, scope)
    target = Store(tmp_path / "target")
    restore(target, file, apply=True)
    assert target.todo(t["todo_id"]) == historical
    assert Store(source.root).todo(t["todo_id"]) == historical


def test_cli_redirected_legacy_codepage_emits_utf8_json(tmp_path):
    import os
    from pathlib import Path

    target = tmp_path / "中文路径"
    result = subprocess.run(
        [sys.executable, "-m", "workthread.cli", "--workspace", str(target), "init"],
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert json.loads(result.stdout.decode("utf-8"))["workspace"] == str(
        Path(target).resolve()
    )
