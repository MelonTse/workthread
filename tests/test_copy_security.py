import shutil

import pytest

from workthread.updating import copy_security as security
from workthread.updating import releases as rel


def fixture(tmp_path):
    src, dst, log = tmp_path / "source", tmp_path / "target", tmp_path / "log"
    src.mkdir()
    log.mkdir()
    (src / "sub").mkdir()
    (src / "sub/secret.txt").write_text("synthetic business bytes", encoding="utf-8")
    return src, dst, log


def test_permissions_checked_before_any_business_content(tmp_path):
    src, dst, log = fixture(tmp_path)

    def read(p):
        return "different" if p == dst / "sub/secret.txt" else "same"

    with pytest.raises(ValueError, match="未复制业务内容"):
        security.prepare(src, dst, log, read)
    assert (dst / "sub/secret.txt").read_bytes() == b""
    assert (src / "sub/secret.txt").read_text() == "synthetic business bytes"
    assert rel.read(log / "security-refusal.json")["business_content_copied"] is False


def test_matching_inherited_permissions_need_no_acl_mutation(tmp_path):
    src, dst, log = fixture(tmp_path)
    read = lambda p: "same"
    before = security.prepare(src, dst, log, read)
    assert (dst / "sub/secret.txt").read_bytes() == b""
    shutil.copyfile(src / "sub/secret.txt", dst / "sub/secret.txt")
    security.verify(src, dst, before, log, read)
    assert rel.read(log / "security-preflight.json")["matched"]


@pytest.mark.parametrize("which", ["source", "target"])
def test_permissions_change_after_copy_is_rejected(tmp_path, which):
    src, dst, log = fixture(tmp_path)
    before = security.prepare(src, dst, log, lambda p: "same")
    changed = src if which == "source" else dst
    with pytest.raises(ValueError, match="权限或目录结构发生变化"):
        security.verify(
            src, dst, before, log, lambda p: "changed" if p == changed else "same"
        )


def test_existing_destination_never_overwritten(tmp_path):
    src, dst, log = fixture(tmp_path)
    dst.mkdir()
    (dst / "user-file").write_text("keep")
    with pytest.raises(ValueError, match="目标已经存在"):
        security.prepare(src, dst, log, lambda p: "same")
    assert (dst / "user-file").read_text() == "keep"


def test_security_read_failure_stops_before_destination_creation(tmp_path):
    src, dst, log = fixture(tmp_path)

    def denied(p):
        raise PermissionError("synthetic READ_CONTROL denial")

    with pytest.raises(PermissionError):
        security.prepare(src, dst, log, denied)
    assert not dst.exists()


@pytest.mark.parametrize("label", ["ERROR", "\u9519\u8bef", "ERREUR"])
def test_zero_exit_does_not_hide_reported_system_error(tmp_path, label):
    from workthread.updating.standalone import check_copy_log

    (tmp_path / "robocopy.txt").write_text(label + " 5 (0x00000005)", encoding="utf-16")
    with pytest.raises(ValueError):
        check_copy_log(0, tmp_path)
    result = rel.read(tmp_path / "process-result.json")
    assert result == {"exit_code": 0, "reported_error": True}


def test_missing_copy_log_is_not_success(tmp_path):
    from workthread.updating.standalone import check_copy_log

    with pytest.raises(ValueError):
        check_copy_log(0, tmp_path)
    assert rel.read(tmp_path / "process-result.json")["log_missing"]


def test_progress_keeps_utf8_evidence_with_legacy_console(tmp_path, monkeypatch):
    import io
    import sys

    from workthread.updating.copying import Evidence

    console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)
    evidence = Evidence(tmp_path / "legacy-console")
    evidence.event("复制中文 空格目录")
    assert "复制中文 空格目录" in (evidence.directory / "progress.txt").read_text(
        encoding="utf-8"
    )


def test_progress_keeps_evidence_after_console_pipe_closes(tmp_path, monkeypatch):
    import sys

    from workthread.updating.copying import Evidence

    class ClosedPipe:
        def write(self, _):
            raise BrokenPipeError()

        def flush(self):
            pass

    monkeypatch.setattr(sys, "stdout", ClosedPipe())
    evidence = Evidence(tmp_path / "closed-console")
    evidence.event("复制继续")
    assert "复制继续" in (evidence.directory / "progress.txt").read_text(
        encoding="utf-8"
    )
