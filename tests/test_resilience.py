import pytest
from workthread.core import Store, uid, load, Conflict
from workthread.ai import Bridge
from workthread.demo import seed, PLAIN, ATTACHMENT
from workthread.mail import Archive, body_parts
from workthread.operations import backup, restore
from test_m3 import result


def test_archive_power_loss_recovery_and_tail_repair(tmp_path, monkeypatch):
    s = Store(tmp_path)
    seed(s)
    origin = s.rows("SELECT * FROM mail_occurrences")[0]
    origin = {
        k: origin[k] for k in ("account_id", "folder_id", "uidvalidity", "imap_uid")
    }
    origin["imap_uid"] = 99
    import workthread.mail as module

    original = module.append_line
    writes = []

    def fail(path, record):
        writes.append(path)
        if len(writes) == 2:
            raise OSError("synthetic power loss")
        original(path, record)

    monkeypatch.setattr(module, "append_line", fail)
    with pytest.raises(OSError):
        Archive(s).record(
            b"From: a@example.org\r\nSubject: New record\r\nMessage-ID: <new@example.org>\r\n\r\n",
            [{"mime_type": "text/plain", "content": "Crash recovery evidence"}],
            [],
            origin,
            "2026-11-04T10:00:00+00:00",
        )
    assert s.rows("SELECT * FROM archive_commits WHERE state='prepared'")
    monkeypatch.setattr(module, "append_line", original)
    body = s.data / "body/2026-11.jsonl"
    with body.open("ab") as f:
        f.write(b'{"incomplete":')
    Archive(Store(tmp_path)).recover()
    assert s.search("Crash recovery") and not s.rows(
        "SELECT * FROM archive_commits WHERE state='prepared'"
    )
    assert list(body.parent.glob("*.damaged-*"))


def test_operation_rollback_and_quarantine(tmp_path):
    s = Store(tmp_path)
    seed(s)
    b = Bridge(s)
    j = b.prepare()[0]
    t = j["context"]["todos"][0]
    ops = [
        {
            "operation_id": uid(),
            "type": "append_progress",
            "todo_id": t["todo_id"],
            "expected_revision": t["revision"],
            "payload": {"content": "must rollback"},
            "evidence": [],
        },
        {
            "operation_id": uid(),
            "type": "create_todo",
            "payload": {
                "title": "invalid evidence",
                "description": "invalid",
                "action_key": "invalid",
            },
            "evidence": [
                {
                    "message_id": j["context"]["messages"][0]["message_id"],
                    "quote": "invented quote",
                }
            ],
        },
    ]
    before = len(s.todo(t["todo_id"])["logs"])
    with pytest.raises(ValueError):
        b.import_result(result(j, ops))
    assert len(s.todo(t["todo_id"])["logs"]) == before
    (b.exchange / "outputs/bad.json").write_text("{broken")
    assert b.consume()[0]["state"] == "rejected"
    assert list((b.exchange / "quarantine").glob("*.json"))


def test_restart_recreates_pending_input_and_stale_requeues(tmp_path):
    s = Store(tmp_path)
    t = s.create_todo({"raw_input": "A", "no_due_date": True})
    b = Bridge(s)
    j = b.prepare()[0]
    file = b.exchange / "inputs" / (j["job_id"] + ".json")
    file.unlink()
    Bridge(Store(tmp_path)).recover()
    assert file.exists()
    s.edit_todo(t["todo_id"], {"title": "B"}, 1)
    with pytest.raises(Conflict):
        b.import_result(result(j, []))
    assert (
        s.rows("SELECT state FROM ai_jobs WHERE job_id=?", (j["job_id"],))[0]["state"]
        == "superseded"
    )
    assert b.prepare()[0]["job_id"] != j["job_id"]


def test_automatic_simple_reply_and_status_evidence(tmp_path):
    s = Store(tmp_path)
    seed(s)
    t = s.create_todo(
        {
            "raw_input": "回复此邮件",
            "completion_policy": {
                "type": "reply_sent",
                "reply_to_message_id": "<synthetic-1@example.org>",
            },
        },
        source="mail_ai",
    )
    b = Bridge(s)
    j = b.prepare()[0]
    # Explicitly include sent evidence in this job's context via todo source.
    sent = s.rows(
        "SELECT * FROM messages WHERE in_reply_to IS NOT NULL AND body_text LIKE 'Thank you.%'"
    )[0]
    # prepare includes related thread for mail-ai todos linked by source.
    with s.db() as c:
        c.execute(
            "UPDATE todos SET source_ref=? WHERE todo_id=?",
            (sent["message_id"], t["todo_id"]),
        )
    j = b.prepare()[0]
    op = {
        "operation_id": uid(),
        "type": "propose_status",
        "todo_id": t["todo_id"],
        "expected_revision": 1,
        "payload": {"status": "done", "reason": "明确已发送回复证据"},
        "evidence": [
            {"message_id": sent["message_id"], "quote": sent["body_text"][:30]}
        ],
    }
    b.import_result(result(j, [op]))
    assert s.todo(t["todo_id"])["status"] == "done"
    assert load(s.todo(t["todo_id"])["status_events"][-1]["evidence_refs"])


def test_attachment_text_and_multipart_attachment_are_never_body():
    leaf = (
        b"TEXT",
        b"PLAIN",
        (b"CHARSET", b"UTF-8", b"NAME", b"secret.txt"),
        None,
        None,
        b"8BIT",
        100,
        4,
        None,
        (b"ATTACHMENT", (b"FILENAME", b"secret.txt")),
    )
    assert not body_parts(leaf)[0]
    assert not body_parts(
        (
            PLAIN,
            ATTACHMENT,
            b"MIXED",
            None,
            (b"ATTACHMENT", (b"FILENAME", b"package.eml")),
        )
    )[0]


def test_backup_tamper_leaves_destination_untouched(tmp_path):
    s = Store(tmp_path / "source")
    seed(s)
    file = tmp_path / "full.7z"
    backup(s, file, "test-password-123")
    raw = file.read_bytes()
    file.write_bytes(raw[: len(raw) // 2])
    dest = Store(tmp_path / "destination")
    t = dest.create_todo({"raw_input": "keep this"})
    with pytest.raises(Exception):
        restore(dest, file, "test-password-123", True)
    assert dest.todo(t["todo_id"])["raw_input"] == "keep this"


def test_ambiguous_dates_remain_review(tmp_path):
    s = Store(tmp_path)
    t = s.create_todo(
        {"raw_input": "今天或者明天联系客户", "input_at": "2026-01-01T10:00:00+08:00"}
    )
    assert t["due_date"] is None and t["needs_review"]


def test_workspace_lock_is_cross_process(tmp_path):
    import subprocess, sys

    s = Store(tmp_path)
    code = "from filelock import FileLock,Timeout; import sys\ntry:\n with FileLock(sys.argv[1],timeout=.1): sys.exit(2)\nexcept Timeout: sys.exit(0)"
    with s.lock:
        p = subprocess.run(
            [sys.executable, "-c", code, str(s.root / ".workspace.lock")], timeout=10
        )
    assert p.returncode == 0


def test_future_schema_refused(tmp_path):
    s = Store(tmp_path)
    with s.db() as c:
        c.execute("INSERT INTO schema_migrations VALUES (999,?)", ("synthetic",))
    with pytest.raises(ValueError):
        Store(tmp_path)


def test_backup_headers_are_encrypted(tmp_path):
    import py7zr

    s = Store(tmp_path / "source")
    file = tmp_path / "encrypted.7z"
    backup(s, file, "synthetic-password", "todos")
    with pytest.raises(Exception):
        with py7zr.SevenZipFile(file, "r") as z:
            z.getnames()
