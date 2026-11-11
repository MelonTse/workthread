import shutil

import pytest
from test_updates import check, records
from test_updates import setup as setup  # noqa: PLC0414 - pytest fixture registration

from workthread.updating import releases as rel
from workthread.updating import standalone as helper
from workthread.updating import transaction as tx


def copy_ok(src, dst, folder):
    shutil.copytree(src, dst)
    return 1


@pytest.mark.parametrize(
    "fault", ["empty", "partial", "acl", "source-write", "copy-error"]
)
def test_copy_fault_preserves_original_install(setup, tmp_path, fault):
    root, inputs = setup
    before = records(root)

    def bad(src, dst, folder):
        if fault == "empty":
            dst.mkdir(parents=True)
            return 0
        if fault == "copy-error":
            raise PermissionError("synthetic denied")
        shutil.copytree(src, dst)
        if fault == "partial":
            (dst / "data/workthread.sqlite3").unlink()
        if fault == "source-write":
            (src / "external.txt").write_text("new user write")
        return 8 if fault == "acl" else 1

    e = helper.Evidence(tmp_path / "evidence")
    with pytest.raises((ValueError, OSError)):
        helper.apply_verified(
            root, inputs, e, execute=bad, quiet=lambda: None, check=check
        )
    assert tx.current(root)[1]["version"] == "1.0.0rc3"
    if fault == "source-write":
        assert (root / "workspace/external.txt").read_text() == "new user write"
        (
            root / "workspace/external.txt"
        ).unlink()  # remove only this test's synthetic addition for comparison
    assert records(root) == before
    assert not tx.journal(root).exists()
    if fault != "copy-error":
        assert (e.directory / "copy-01/comparison.json").exists()


def test_all_records_and_custom_files_preserved(setup, tmp_path):
    root, inputs = setup
    before = records(root)
    e = helper.Evidence(tmp_path / "evidence")
    helper.apply_verified(
        root, inputs, e, execute=copy_ok, quiet=lambda: None, check=check
    )
    assert records(root) == before
    assert len(list(e.directory.glob("copy-*/comparison.json"))) == 4


def test_old_failure_result_archived_and_settings_updated(setup, tmp_path):
    root, inputs = setup
    previous = {"error": "synthetic previous snapshot failure"}
    rel.save(root / tx.STATE / "result.json", previous)
    rel.save(root / tx.STATE / "request-error.json", {"message": "old network failure"})
    empty = root / tx.STATE / "transactions" / ("a" * 32) / "snapshot/workspace"
    empty.mkdir(parents=True)
    e = helper.Evidence(tmp_path / "evidence")
    helper.apply_verified(
        root, inputs, e, execute=copy_ok, quiet=lambda: None, check=check
    )
    assert rel.read(e.directory / "previous-result.json") == previous
    assert rel.read(root / tx.STATE / "result.json")["version"] == "1.0.0rc4"
    assert rel.read(root / tx.STATE / "request-error.json") == {}
    assert empty.is_dir() and not list(empty.iterdir())


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
def test_switch_failures_restore_old_program_and_data(setup, tmp_path, step):
    root, inputs = setup
    before = records(root)

    def fail(name):
        if name == step:
            raise OSError("synthetic switch failure")

    with pytest.raises(OSError):
        helper.apply_verified(
            root,
            inputs,
            helper.Evidence(tmp_path / "evidence"),
            execute=copy_ok,
            quiet=lambda: None,
            check=check,
            hook=fail,
        )
    assert tx.current(root)[1]["version"] == "1.0.0rc3" and records(root) == before
