"""The RC9 transition and subsequent update use the normal transaction, not standalone.apply."""

import json
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_updates import apply, identity, init, package, records

from workthread.updating import controller as ctl
from workthread.updating import releases as rel
from workthread.updating import transaction as tx

RC9 = "49381b86143bbe5ce48b4f47c6d05880927b1b48"
RC10 = "c" * 40


def setup_rc9(tmp_path):
    root = tmp_path / "中文 RC9"
    init(root)
    rel.save(root / "BUILD_INFO.json", identity("1.0.0rc9", RC9))
    key = Ed25519PrivateKey.generate()
    args = package(tmp_path, key, RC10, "1.0.0rc10", ["1.0.0rc9@" + RC9])
    return root, key, args


def test_rc9_rc10_and_next_preserve_all_records(tmp_path):
    root, key, args = setup_rc9(tmp_path)
    prior = records(root)
    assert apply(root, args)["version"] == "1.0.0rc10"
    assert records(root) == prior
    args2 = package(tmp_path, key, "d" * 40, "1.0.0rc11", ["1.0.0rc10@" + RC10])
    assert apply(root, args2)["version"] == "1.0.0rc11"
    assert records(root) == prior


@pytest.mark.parametrize(
    "step",
    [
        "saved-workspace",
        "placed-workspace",
        "saved-acceptance",
        "placed-acceptance",
        "pointer",
    ],
)
def test_rc9_switch_failure_restores_old_program_and_data(tmp_path, step):
    root, _, args = setup_rc9(tmp_path)
    before = records(root)

    def fail(at):
        if at == step:
            raise OSError("synthetic switch interruption")

    with pytest.raises(OSError):
        apply(root, args, hook=fail)
    assert records(root) == before
    folder, current = tx.current(root)
    assert current["version"] == "1.0.0rc9"
    assert (folder / tx.EXE).read_bytes() == b"old synthetic binary"


def test_fresh_rc10_does_not_reuse_legacy_bootstrap(tmp_path, monkeypatch):
    root, key, args = setup_rc9(tmp_path)
    rel.save(root / "BUILD_INFO.json", identity("1.0.0rc10", RC10))
    exe = root / tx.EXE
    old = root / tx.STATE / "bootstrap" / "WorkThread.exe"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"legacy broken copier")
    args = package(tmp_path, key, "d" * 40, "1.0.0rc11", ["1.0.0rc10@" + RC10])
    _, doc, sig, public = args
    monkeypatch.setattr(rel, "trust", lambda: public)
    monkeypatch.setattr(tx, "native_quiet", lambda **_: None)
    monkeypatch.setattr(sys, "executable", str(exe))
    handoff = []
    monkeypatch.setattr(ctl, "detached", handoff.append)
    updates = ctl.Updates(root, lambda: handoff.append("stop"))
    updates.offer = {
        **json.loads(doc),
        "doc": doc.decode(),
        "sig": sig.decode(),
        "notes": "fixture",
    }
    updates.ready = True
    updates.action("apply", True)
    helper = __import__("pathlib").Path(handoff[0][0])
    assert helper.parent.parent.name == "helpers"
    assert helper.read_bytes() == exe.read_bytes()
    assert old.read_bytes() == b"legacy broken copier"
    assert handoff[-1] == "stop"


def test_transition_records_failure_before_any_business_copy(tmp_path, monkeypatch):
    root, _, args = setup_rc9(tmp_path)
    archive, doc, sig, key = args
    meta = tmp_path / "meta"
    meta.mkdir()
    (meta / "update.json").write_bytes(doc)
    (meta / "update.sig").write_bytes(sig)
    monkeypatch.setattr(rel, "trust", lambda: key)
    monkeypatch.setattr(tx, "native_quiet", lambda **_: None)
    from workthread.updating import copying

    def fail(*_):
        raise ValueError("synthetic ACL mismatch")

    monkeypatch.setattr(copying, "probe_environment", fail)
    before = records(root)
    with pytest.raises(ValueError, match="ACL mismatch"):
        ctl.bootstrap(root, archive, meta)
    result = rel.read(root / tx.STATE / "result.json")
    assert result["status"] == "FAILED" and result["exit_code"] == 1
    assert records(root) == before and not tx.journal(root).exists()


@pytest.mark.parametrize(
    "step",
    [
        "saved-workspace",
        "placed-workspace",
        "saved-acceptance",
        "placed-acceptance",
        "pointer",
    ],
)
def test_rc9_process_death_recovers_in_new_process(tmp_path, step):
    import multiprocessing
    import subprocess

    from test_updates import hard_stop

    root, _, args = setup_rc9(tmp_path)
    before = records(root)
    archive, doc, sig, key = args
    worker = multiprocessing.get_context("spawn").Process(
        target=hard_stop, args=(root, archive, doc, sig, key.public_bytes_raw(), step)
    )
    worker.start()
    worker.join(30)
    assert worker.exitcode == 77
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; import sys; from workthread.updating.transaction import recover; recover(Path(sys.argv[1]))",
            str(root),
        ],
        check=True,
    )
    assert records(root) == before
    assert tx.current(root)[1]["version"] == "1.0.0rc9"
