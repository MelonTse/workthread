"""UI rewrite requests queue saved mail context, never call WorkBuddy or send mail."""

import json

from test_m4 import client
from test_mail_replies import setup_drafts

from workthread.ai import Bridge
from workthread.demo import simulated_result


def test_rewrite_includes_completed_mail_saved_draft_and_exact_feedback(tmp_path):
    store, mails = setup_drafts(tmp_path)
    bridge = Bridge(store)
    for job in bridge.prepare():
        bridge.import_result(simulated_result(job))
    with store.db() as c:
        c.execute("UPDATE messages SET internal_date='2020-01-01T00:00:00+00:00'")
    c, headers = client(store)
    c.post(
        "/api/v1/drafts/draft-a1/feedback",
        json={"content": "Shorten this saved draft"},
        headers=headers,
    )
    c.post(
        "/api/v1/drafts/draft-b/feedback",
        json={"content": "Other draft feedback"},
        headers=headers,
    )
    response = c.post("/api/v1/drafts/draft-a1/queue", json={}, headers=headers)
    assert response.status_code == 200 and not response.json["existing"]
    jid = response.json["queued"][0]["job_id"]
    job = json.loads(
        store.rows("SELECT input_json FROM ai_jobs WHERE job_id=?", (jid,))[0][
            "input_json"
        ]
    )
    target = job["context"]["draft_rewrite"]
    assert target["draft_id"] == "draft-a1"
    assert target["message_id"] == mails[0]["message_id"]
    assert target["body"] == "Body for draft-a1"
    assert [f["content"] for f in target["feedback"]] == ["Shorten this saved draft"]
    assert mails[0]["message_id"] in {
        m["message_id"] for m in job["context"]["messages"]
    }
    assert (
        store.rows("SELECT state FROM ai_jobs WHERE job_id=?", (jid,))[0]["state"]
        == "pending"
    )
    assert json.loads((bridge.exchange / "inputs" / f"{jid}.json").read_text()) == job
    assert not (bridge.exchange / "results" / f"{jid}.json").exists()


def test_rewrite_deduplicates_only_same_saved_revision_and_feedback(tmp_path):
    store, _ = setup_drafts(tmp_path)
    c, headers = client(store)
    generic = c.post("/api/v1/ai/jobs", json={}, headers=headers).json
    first = c.post("/api/v1/drafts/draft-a1/queue", json={}, headers=headers).json
    repeat = c.post("/api/v1/drafts/draft-a1/queue", json={}, headers=headers).json
    assert first["queued"] != generic["queued"]
    assert repeat["existing"] and repeat["queued"] == first["queued"]
    c.post(
        "/api/v1/drafts/draft-a1/feedback",
        json={"content": "New feedback"},
        headers=headers,
    )
    new_feedback = c.post(
        "/api/v1/drafts/draft-a1/queue", json={}, headers=headers
    ).json
    assert not new_feedback["existing"] and new_feedback["queued"] != first["queued"]
    c.patch(
        "/api/v1/drafts/draft-a1",
        json={
            "subject": "Saved subject",
            "body": "Saved revision 2",
            "expected_revision": 1,
        },
        headers=headers,
    )
    new_revision = c.post(
        "/api/v1/drafts/draft-a1/queue", json={}, headers=headers
    ).json
    assert (
        not new_revision["existing"]
        and new_revision["queued"] != new_feedback["queued"]
    )
    assert (
        c.post("/api/v1/drafts/draft-b/queue", json={}, headers=headers).json["queued"]
        != new_revision["queued"]
    )


def test_rewrite_rejects_missing_draft_unlinked_mail_and_csrf(tmp_path):
    store, _ = setup_drafts(tmp_path)
    c, headers = client(store)
    before = store.rows("SELECT * FROM ai_jobs")
    assert c.post("/api/v1/drafts/draft-a1/queue", json={}).status_code == 403
    assert (
        c.post("/api/v1/drafts/missing/queue", json={}, headers=headers).status_code
        == 400
    )
    with store.db() as db:
        db.execute("UPDATE drafts SET message_id=NULL WHERE draft_id='draft-a1'")
    assert (
        c.post("/api/v1/drafts/draft-a1/queue", json={}, headers=headers).status_code
        == 400
    )
    assert store.rows("SELECT * FROM ai_jobs") == before


def test_targeted_rewrite_does_not_block_or_replace_general_analysis(tmp_path):
    store, mails = setup_drafts(tmp_path)
    bridge = Bridge(store)
    c, headers = client(store)
    # This fixture starts with a completed demo job: exclude it to exercise fresh mail.
    with store.db() as db:
        db.execute("UPDATE ai_jobs SET state='failed'")
    rewrite = c.post("/api/v1/drafts/draft-a1/queue", json={}, headers=headers).json
    general = c.post("/api/v1/ai/jobs", json={}, headers=headers).json
    assert not general["existing"] and general["queued"] != rewrite["queued"]
    jid = rewrite["queued"][0]["job_id"]
    job = json.loads(
        store.rows("SELECT input_json FROM ai_jobs WHERE job_id=?", (jid,))[0][
            "input_json"
        ]
    )
    result = {
        key: job[key]
        for key in (
            "schema_version",
            "workspace_id",
            "workspace_epoch",
            "job_id",
            "input_sha256",
        )
    }
    result.update(
        outcome="completed",
        reviewed_todo_ids=[],
        warnings=[],
        operations=[
            {
                "operation_id": "synthetic-rewrite",
                "type": "create_draft",
                "payload": {
                    "message_id": mails[0]["message_id"],
                    "subject": "Rewritten subject",
                    "body": "Synthetic rewritten body",
                },
                "evidence": [
                    {
                        "message_id": mails[0]["message_id"],
                        "quote": job["context"]["messages"][0]["body_text"][:20],
                    }
                ],
            }
        ],
    )
    receipt = bridge.import_result(result)
    assert receipt["state"] == "completed"
    assert (
        store.rows("SELECT body FROM drafts WHERE draft_id='draft-a1'")[0]["body"]
        == "Body for draft-a1"
    )
    assert (
        len(store.rows("SELECT * FROM drafts WHERE body='Synthetic rewritten body'"))
        == 1
    )
    bridge.import_result(result)
    assert (
        len(store.rows("SELECT * FROM drafts WHERE body='Synthetic rewritten body'"))
        == 1
    )
    assert mails[0]["message_id"] in {
        m["message_id"] for j in bridge.prepare() for m in j["context"]["messages"]
    }
