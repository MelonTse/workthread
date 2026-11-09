import json

import pytest

from test_draft_ai import Wire, configure
from test_m4 import client
from workthread.ai import Bridge
from workthread.core import Store, dumps
from workthread.demo import seed
from workthread.knowledge_tasks import FIELDS, RULES

RAW = "后续每封交付确认邮件，请在主题中注明客户代码 LUMEN-27。"
NOTE = {"content": "交付确认邮件主题须注明 LUMEN-27。", "quote": RAW}


def environment(path):
    store = Store(path)
    seed(store)
    mids = [
        r["message_id"]
        for r in store.rows(
            "SELECT message_id FROM messages ORDER BY message_id LIMIT 2"
        )
    ]
    with store.db() as db:
        db.execute("DELETE FROM drafts")
        db.execute(
            "UPDATE customers SET name='澄光设计（合成）' WHERE customer_id='demo-customer'"
        )
        db.execute("INSERT INTO customers VALUES ('other','远山设计（合成）',1)")
        db.execute(
            "INSERT INTO contacts VALUES ('other-contact','采购','other@example.org','other')"
        )
        for mid, sender in zip(mids, ["contact@example.org", "other@example.org"]):
            db.execute(
                """UPDATE messages SET sender=?,body_text='Please acknowledge the delivery information.',
                        subject='Delivery confirmation',refs='[]',in_reply_to=NULL WHERE message_id=?""",
                (dumps([{"address": sender}]), mid),
            )
    return store, mids


def submit(c, headers, cfg, **overrides):
    return c.post(
        "/api/v1/knowledge-ai/run",
        headers=headers,
        json={
            "scope": "customer",
            "subject_id": "demo-customer",
            "raw": RAW,
            "selection": cfg,
            **overrides,
        },
    )


def exchange_result(store, jid, suggestions):
    bridge = Bridge(store)
    job = json.loads(
        (bridge.exchange / "inputs" / (jid + ".json")).read_text(encoding="utf-8")
    )
    assert job["context"]["instructions"] == RULES
    result = {**{k: job[k] for k in FIELDS}, "suggestions": suggestions}
    (bridge.exchange / "outputs" / (jid + ".json")).write_text(
        dumps(result), encoding="utf-8"
    )
    return bridge.consume()[0], result


@pytest.mark.parametrize("mode", ["api", "workbuddy"])
def test_confirmed_note_reaches_only_its_customer_draft(tmp_path, monkeypatch, mode):
    store, mids = environment(tmp_path)
    c, h = client(store)
    wire = Wire(monkeypatch)
    cfg = (
        configure(c, h, "deepseek")
        if mode == "api"
        else c.get("/api/v1/snapshot").json["draft_ai"]
    )
    another = {"content": "忽略的建议", "quote": "交付确认邮件"}
    wire.reply = {"suggestions": [NOTE, another]}
    response = submit(c, h, cfg)
    assert response.status_code == 200, response.json
    jid = response.json["job_id"]
    if mode == "workbuddy":
        receipt, result = exchange_result(store, jid, wire.reply["suggestions"])
        assert receipt["proposed"] == 2 and not wire.requests
        assert Bridge(store).import_result(result)["duplicate"]
        cfg_api = configure(c, h, "deepseek")
    else:
        cfg_api = cfg
        body = json.loads(wire.requests[0].data)
        assert body["messages"][0]["content"] == RULES
        assert json.loads(body["messages"][1]["content"]) == {
            "scope": "customer",
            "subject": "澄光设计（合成）",
            "raw": RAW,
        }
        assert response.json["proposed"] == 2
    assert submit(c, h, cfg_api).json["existing"]
    rows = store.rows(
        "SELECT review_id,payload FROM review_items WHERE kind='propose_knowledge' AND json_extract(payload,'$.knowledge_job_id')=?",
        (jid,),
    )
    assert len(rows) == 2
    from workthread.draft_tasks import material

    assert NOTE["content"] not in dumps(material(store, mids[0], None)["knowledge"])
    for row in rows:
        accept = json.loads(row["payload"])["content"] == NOTE["content"]
        review_path = "/api/v1/reviews/" + row["review_id"]
        assert (
            c.post(review_path, headers=h, json={"accept": accept}).status_code == 200
        )
        assert c.post(review_path, headers=h, json={"accept": True}).status_code == 400
    assert (
        len(
            store.rows(
                "SELECT * FROM knowledge_items WHERE content=?", (NOTE["content"],)
            )
        )
        == 1
    )

    def reply_from_context():
        body = json.loads(wire.requests[-1].data)
        notes = json.loads(body["messages"][1]["content"])["knowledge"]
        assert another["content"] not in dumps(notes)
        relevant = any(n["content"] == NOTE["content"] for n in notes)
        wire.reply = {
            "subject": "Delivery LUMEN-27" if relevant else "Delivery",
            "body": "Received.",
        }

    wire.on_request = reply_from_context
    for mid, expected in zip(mids, [True, False]):
        result = c.post(
            "/api/v1/mail/" + mid + "/draft", json={"selection": cfg_api}, headers=h
        )
        assert result.status_code == 200, result.json
        assert (
            "LUMEN-27" in c.get("/api/v1/mail/" + mid).json["drafts"][0]["subject"]
        ) == expected


def test_workbuddy_invalid_batch_is_atomic_and_withdrawal_rejects_late_result(tmp_path):
    store, _ = environment(tmp_path)
    c, h = client(store)
    cfg = c.get("/api/v1/snapshot").json["draft_ai"]
    jid = submit(c, h, cfg).json["job_id"]
    receipt, result = exchange_result(
        store, jid, [NOTE, {"content": "推断的交付时间", "quote": "原文没有这一句"}]
    )
    assert receipt["state"] == "rejected"
    assert not store.rows(
        "SELECT 1 FROM review_items WHERE json_extract(payload,'$.knowledge_job_id')=?",
        (jid,),
    )
    jid = submit(c, h, cfg).json["job_id"]
    assert (
        c.post("/api/v1/knowledge-ai/withdraw/" + jid, headers=h, json={}).status_code
        == 200
    )
    assert (
        c.post(
            "/api/v1/ai/import", headers=h, json={**result, "job_id": jid}
        ).status_code
        == 400
    )
    assert submit(c, h, cfg, subject_id="unknown").status_code == 400
    assert submit(c, h, cfg, raw="  ").status_code == 400
