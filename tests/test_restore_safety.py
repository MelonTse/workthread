"""Restore faults must preserve directories not yet protected by rollback."""

import hashlib
from pathlib import Path

import pytest

import workthread.operations as operations
from workthread.core import Store
from workthread.operations import backup, restore


def fingerprints(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for name in ("data", "config", "agent-workspace")
        for p in (root / name).rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize(
    "fault",
    [
        "rename-data",
        "copy-data",
        "rename-config",
        "copy-config",
        "rename-agent-workspace",
        "copy-agent-workspace",
        "initialize",
        "queue",
        "health",
    ],
)
def test_full_restore_fault_preserves_every_original_directory(
    tmp_path, monkeypatch, fault
):
    source = Store(tmp_path / "synthetic-source")
    source.create_todo({"raw_input": "backup synthetic task", "no_due_date": True})
    (source.root / "config").mkdir()
    (source.root / "config/source.txt").write_text("source configuration")
    (source.root / "agent-workspace/source.txt").write_text("source agent file")
    archive = tmp_path / "full.zip"
    backup(source, archive)
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()

    destination = Store(tmp_path / "synthetic-destination")
    todo = destination.create_todo({"raw_input": "keep original", "no_due_date": True})
    (destination.root / "config").mkdir()
    (destination.root / "config/custom.txt").write_text("keep original config")
    (destination.root / "agent-workspace/custom.txt").write_text("keep original agent")
    before = fingerprints(destination.root)
    original_rename, original_copy = Path.rename, operations.shutil.copytree
    triggered = []

    def rename(path, target):
        if path.parent == destination.root and fault == "rename-" + path.name:
            triggered.append(fault)
            raise OSError("injected rename fault")
        return original_rename(path, target)

    def copy(src, dst, *args, **kwargs):
        dst = Path(dst)
        if dst.parent == destination.root and fault == "copy-" + dst.name:
            dst.mkdir(parents=True, exist_ok=True)
            (dst / "partial.txt").write_text("incomplete restored copy")
            triggered.append(fault)
            raise OSError("injected partial copy fault")
        return original_copy(src, dst, *args, **kwargs)

    def fail(*args, **kwargs):
        triggered.append(fault)
        raise OSError("injected " + fault + " fault")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", rename)
        patch.setattr(operations.shutil, "copytree", copy)
        if fault == "initialize":
            patch.setattr(operations, "Store", fail)
        elif fault == "queue":
            patch.setattr(operations.Bridge, "prepare", fail)
        elif fault == "health":
            patch.setattr(Store, "health", fail)
        with pytest.raises(OSError, match="injected"):
            restore(destination, archive, apply=True)
    assert triggered == [fault], "the intended failure point must be reached"
    assert fingerprints(destination.root) == before
    assert Store(destination.root).todo(todo["todo_id"])["raw_input"] == "keep original"
    assert destination.health()["ok"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == archive_hash
