"""Mail/draft/feedback association must be by stable IDs, including identical subjects."""

from test_m4 import client

from workthread.ai import Bridge
from workthread.core import Store, now
from workthread.demo import seed


def setup_drafts(tmp_path):
    store = Store(tmp_path)
    seed(store)
    mails = store.rows("SELECT message_id FROM messages ORDER BY message_id")
    with store.db() as c:
        c.execute("DELETE FROM drafts")
        for did, mid in [
            ("draft-a1", mails[0]["message_id"]),
            ("draft-a2", mails[0]["message_id"]),
            ("draft-b", mails[1]["message_id"]),
        ]:
            c.execute(
                "INSERT INTO drafts VALUES (?,?,?,?,?,?,?,?)",
                (
                    did,
                    mid,
                    None,
                    "Re: identical subject",
                    "Body for " + did,
                    1,
                    now(),
                    now(),
                ),
            )
    return store, mails


def test_mail_detail_groups_only_exact_linked_drafts_and_feedback(tmp_path):
    store, mails = setup_drafts(tmp_path)
    c, headers = client(store)
    for did in ("draft-a1", "draft-a2", "draft-b"):
        r = c.post(
            "/api/v1/drafts/" + did + "/feedback",
            json={"content": "Feedback for " + did},
            headers=headers,
        )
        assert r.status_code == 201 and r.json["draft_id"] == did
    # Existing unscoped feedback remains unscoped rather than attached by guesswork.
    c.post(
        "/api/v1/feedback", json={"content": "Legacy general feedback"}, headers=headers
    )
    a = c.get("/api/v1/mail/" + mails[0]["message_id"]).json
    assert {d["draft_id"] for d in a["drafts"]} == {"draft-a1", "draft-a2"}
    assert {f["target_id"] for f in a["feedback"]} == {"draft-a1", "draft-a2"}
    b = c.get("/api/v1/mail/" + mails[1]["message_id"]).json
    assert [d["draft_id"] for d in b["drafts"]] == ["draft-b"]
    assert [f["content"] for f in b["feedback"]] == ["Feedback for draft-b"]
    empty = c.get("/api/v1/mail/" + mails[2]["message_id"]).json
    assert empty["drafts"] == [] and empty["feedback"] == []


def test_unknown_or_empty_draft_feedback_does_not_write(tmp_path):
    store, _mails = setup_drafts(tmp_path)
    c, headers = client(store)
    for did, content in [("missing", "Feedback"), ("draft-a1", "   ")]:
        assert (
            c.post(
                "/api/v1/drafts/" + did + "/feedback",
                json={"content": content},
                headers=headers,
            ).status_code
            == 400
        )
    assert not store.rows("SELECT * FROM feedback")
    assert c.get("/api/v1/mail/missing").status_code == 400


def test_draft_feedback_keeps_mail_context_for_ai_and_long_subject(tmp_path):
    store, mails = setup_drafts(tmp_path)
    c, headers = client(store)
    subject = "Re: Project " + ("long subject / 很长的业务主题 " * 20)
    assert (
        c.patch(
            "/api/v1/drafts/draft-a1",
            json={"subject": subject, "body": "Edited body", "expected_revision": 1},
            headers=headers,
        ).status_code
        == 200
    )
    c.post(
        "/api/v1/drafts/draft-a1/feedback",
        json={"content": "Please shorten the first paragraph."},
        headers=headers,
    )
    detail = c.get("/api/v1/mail/" + mails[0]["message_id"]).json
    assert (
        next(d for d in detail["drafts"] if d["draft_id"] == "draft-a1")["subject"]
        == subject
    )
    feedback = Bridge(store).prepare()[0]["context"]["feedback"]
    assert feedback[0]["target_id"] == "draft-a1"
    assert feedback[0]["message_id"] == mails[0]["message_id"]
    assert (
        feedback[0]["draft_subject"] == subject
        and feedback[0]["draft_body"] == "Edited body"
    )
