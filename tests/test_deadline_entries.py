"""Exercise the domain rule through every public deadline-writing route."""

import json

import pytest
from test_m3 import result
from test_m4 import client

from workthread.ai import Bridge, atomic_json
from workthread.cli import main
from workthread.core import Store, now, uid
from workthread.mail import Archive

COMBINATIONS = [
    ("2026-12-01", False, True),
    (None, True, True),
    (None, False, False),
    ("2026-12-01", True, False),
]


@pytest.mark.parametrize("due,indefinite,valid", COMBINATIONS)
@pytest.mark.parametrize(
    "entry",
    [
        "html_post",
        "html_patch",
        "intake_file",
        "intake_cli",
        "ai_create",
        "ai_normalize",
        "historical_accept",
    ],
)
def test_all_entries_share_deadline_rule(tmp_path, due, indefinite, valid, entry):
    s = Store(tmp_path / "synthetic")
    fields = {"due_date": due, "no_due_date": indefinite}
    if entry in ("html_patch", "ai_normalize"):
        t = s.create_todo(
            {"raw_input": "existing synthetic", "due_date": "2026-11-01"},
            source="mail_ai",
        )
        tid = t["todo_id"]
    before = s.rows("SELECT * FROM todos")
    if entry.startswith("html"):
        c, h = client(s)
        if entry == "html_post":
            r = c.post(
                "/api/v1/todos",
                json={"raw_input": "HTML/API capture", **fields},
                headers=h,
            )
        else:
            r = c.patch(
                "/api/v1/todos/" + tid,
                json={"expected_revision": 1, "changes": fields},
                headers=h,
            )
        expected_status = (201 if entry == "html_post" else 200) if valid else 400
        assert r.status_code == expected_status
        if valid:
            tid = r.json["todo_id"]
        else:
            assert set(r.json["fields"]) == {"due_date", "no_due_date"}
            assert "due_date" in r.json["error"]
    elif entry.startswith("intake"):
        request_id = uid()
        payload = {
            "schema_version": "1.0",
            "request_id": request_id,
            "raw_input": "conversation original",
            "input_at": "2026-01-01T23:30:00-08:00",
            "input_timezone": "America/Los_Angeles",
            "source_ref": "synthetic:conversation",
            **fields,
        }
        if entry == "intake_file":
            bridge = Bridge(s)
            atomic_json(bridge.exchange / "intake/request.json", payload)
            receipt = bridge.consume()[0]
            assert receipt["state"] == ("saved" if valid else "rejected")
            if valid:
                tid = receipt["todo_id"]
                assert (
                    json.loads(
                        (
                            bridge.exchange / "receipts" / (request_id + ".json")
                        ).read_text(encoding="utf-8")
                    )["state"]
                    == "saved"
                )
            else:
                assert "due_date" in receipt["error"]
                assert list((bridge.exchange / "quarantine").glob("*.json"))
        else:
            file = tmp_path / "intake.json"
            file.write_text(json.dumps(payload))
            if valid:
                main(["--workspace", str(s.root), "intake", str(file)])
                tid = s.rows("SELECT todo_id FROM todos")[0]["todo_id"]
            else:
                with pytest.raises(ValueError, match="due_date"):
                    main(["--workspace", str(s.root), "intake", str(file)])
    else:
        bridge = Bridge(s)
        if entry in ("ai_create", "historical_accept"):
            s.create_todo({"raw_input": "existing synthetic", "due_date": "2026-11-01"})
            Archive(s).record(
                b"From: synthetic@example.org\r\nSubject: Synthetic action\r\nMessage-ID: <entry@example.org>\r\n\r\n",
                [
                    {
                        "mime_type": "text/plain",
                        "content": "Please prepare the synthetic checklist.",
                    }
                ],
                [],
                {
                    "account_id": "synthetic",
                    "folder_id": "synthetic",
                    "uidvalidity": 1,
                    "imap_uid": 1,
                },
                now(),
            )
            job = bridge.prepare()[0]
            mail = job["context"]["messages"][0]
            payload = {
                "title": "new from mail",
                "description": "synthetic proposal",
                "action_key": uid(),
                **fields,
            }
            refs = [{"message_id": mail["message_id"], "quote": mail["body_text"]}]
            if entry == "historical_accept":
                with s.db() as c:
                    rid = s._review(
                        c,
                        "historical_todo",
                        {"raw_input": mail["body_text"], **payload},
                        refs,
                    )
                before = s.rows("SELECT * FROM todos")
                if valid:
                    bridge.resolve(rid, True)
                    tid = s.rows(
                        "SELECT todo_id FROM todos WHERE title='new from mail'"
                    )[0]["todo_id"]
                else:
                    with pytest.raises(ValueError, match="due_date"):
                        bridge.resolve(rid, True)
                    assert (
                        s.rows(
                            "SELECT state FROM review_items WHERE review_id=?", (rid,)
                        )[0]["state"]
                        == "pending"
                    )
            else:
                before = s.rows("SELECT * FROM todos")
                operation = {
                    "operation_id": uid(),
                    "type": "create_todo",
                    "payload": payload,
                    "evidence": refs,
                }
        else:
            job = bridge.prepare()[0]
            operation = {
                "operation_id": uid(),
                "type": "normalize_todo",
                "todo_id": tid,
                "expected_revision": 1,
                "payload": fields,
                "evidence": [],
            }
        if entry != "historical_accept":
            if valid:
                assert (
                    bridge.import_result(result(job, [operation]))["state"]
                    == "completed"
                )
                if entry == "ai_create":
                    tid = s.rows(
                        "SELECT todo_id FROM todos WHERE title='new from mail'"
                    )[0]["todo_id"]
            else:
                # A prior valid operation in the same result must roll back too.
                log_todo = job["context"]["todos"][0]
                log = {
                    "operation_id": uid(),
                    "type": "append_progress",
                    "todo_id": log_todo["todo_id"],
                    "expected_revision": log_todo["revision"],
                    "payload": {"content": "must rollback"},
                    "evidence": [],
                }
                old_logs = s.rows("SELECT * FROM progress_logs")
                with pytest.raises(ValueError, match="due_date"):
                    bridge.import_result(result(job, [log, operation]))
                assert s.rows("SELECT * FROM progress_logs") == old_logs
    if valid:
        saved = s.todo(tid)
        assert saved["due_date"] == due and bool(saved["no_due_date"]) == indefinite
    else:
        assert s.rows("SELECT * FROM todos") == before


@pytest.mark.parametrize(
    "due", ["", "2026-02-30", "20261201", "2026-W49-2", 123, False]
)
def test_invalid_date_formats_reject_post_and_patch(tmp_path, due):
    s = Store(tmp_path)
    c, h = client(s)
    t = s.create_todo({"raw_input": "valid", "due_date": "2026-12-01"})
    for method, path, body in [
        (c.post, "/api/v1/todos", {"raw_input": "invalid", "due_date": due}),
        (
            c.patch,
            "/api/v1/todos/" + t["todo_id"],
            {"expected_revision": 1, "changes": {"due_date": due}},
        ),
    ]:
        r = method(path, json=body, headers=h)
        assert r.status_code == 400 and "due_date" in r.json["error"]
    assert s.todo(t["todo_id"]) == t


def test_relative_intake_uses_original_timezone_and_delayed_day(tmp_path):
    s = Store(tmp_path)
    t = s.create_todo(
        {
            "raw_input": "tomorrow follow up",
            "input_at": "2026-01-01T23:30:00-08:00",
            "input_timezone": "America/Los_Angeles",
        },
        source="workbuddy",
    )
    assert t["due_date"] == "2026-01-02"


def test_ambiguous_normalization_rejects_invalid_pair_and_preserves_human_fields(
    tmp_path,
):
    s = Store(tmp_path)
    t = s.create_todo({"raw_input": "今天或者明天联系客户", "due_date": "2026-12-01"})
    b = Bridge(s)
    job = b.prepare()[0]
    invalid = {
        "operation_id": uid(),
        "type": "normalize_todo",
        "todo_id": t["todo_id"],
        "expected_revision": 1,
        "payload": {"due_date": "2026-12-02", "no_due_date": True},
        "evidence": [],
    }
    with pytest.raises(ValueError, match="due_date"):
        b.import_result(result(job, [invalid]))
    assert s.todo(t["todo_id"]) == t


def test_simulation_does_not_invent_deadline_for_undated_mail(tmp_path):
    from workthread.demo import seed

    s = Store(tmp_path)
    seed(s)
    assert len(s.rows("SELECT * FROM todos")) == 1
    assert s.rows("SELECT * FROM drafts") and s.rows("SELECT * FROM analyses")
