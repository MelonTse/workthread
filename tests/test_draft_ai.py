"""Single-mail API and WorkBuddy acceptance. The wire transport is synthetic."""

import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest
from test_m4 import client
from test_mail_replies import setup_drafts

from workthread import draft_api
from workthread.ai import Bridge
from workthread.core import dumps, now


class Wire:
    def __init__(self, monkeypatch):
        self.requests = []
        self.reply = {
            "subject": "Re: Sample quotation",
            "body": "Thank you. We will confirm the date.",
        }
        self.choices = None
        self.failure = None
        self.on_request = None
        self.keys = {}
        monkeypatch.setattr(draft_api, "build_opener", lambda *handlers: self)
        monkeypatch.setattr(
            draft_api.keyring,
            "set_password",
            lambda service, ref, secret: self.keys.update({ref: secret}),
        )
        monkeypatch.setattr(
            draft_api.keyring, "get_password", lambda service, ref: self.keys.get(ref)
        )

    def open(self, req, timeout):
        self.requests.append(req)
        if self.on_request:
            self.on_request()
        if self.failure:
            raise self.failure
        choices = (
            self.choices
            if self.choices is not None
            else [{"finish_reason": "stop", "message": {"content": dumps(self.reply)}}]
        )
        return BytesIO(dumps({"choices": choices}).encode())


@pytest.fixture
def env(tmp_path, monkeypatch):
    store, mids = setup_drafts(tmp_path)
    with store.db() as c:
        c.execute("""UPDATE messages SET refs='[]',in_reply_to=NULL""")
        c.execute(
            "UPDATE messages SET subject='Synthetic sample',body_text='Please quote USD 42.',sender=? WHERE message_id=?",
            (dumps([{"address": "contact@example.org"}]), mids[2]["message_id"]),
        )
        c.execute(
            "UPDATE messages SET body_text='UNRELATED CUSTOMER BODY' WHERE message_id=?",
            (mids[0]["message_id"],),
        )
        for scope, subject, content, confirmed in [
            ("customer", "demo-customer", "Confirmed USD preference", 1),
            ("customer", "another-customer", "UNRELATED CUSTOMER KNOWLEDGE", 1),
            ("personal", None, "UNCONFIRMED preference", 0),
        ]:
            c.execute(
                "INSERT INTO knowledge_items VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    content,
                    scope,
                    subject,
                    content,
                    confirmed,
                    "[]",
                    1,
                    None,
                    now(),
                    now(),
                ),
            )
    c, headers = client(store)
    return store, c, headers, mids[2]["message_id"], Wire(monkeypatch)


def configure(c, h, provider):
    config = {"mode": "api", "provider": provider, "model": "synthetic-contract-test"}
    response = c.post(
        "/api/v1/draft-ai/settings",
        json={**config, "key": "synthetic-credential"},
        headers=h,
    )
    assert response.json == config
    return config


@pytest.mark.parametrize("provider", list(draft_api.PROVIDERS))
def test_provider_generation_and_feedback_roundtrip(env, provider):
    store, c, h, mid, wire = env
    cfg = configure(c, h, provider)
    assert c.post("/api/v1/draft-ai/test", json={"selection": cfg}, headers=h).json == {
        "ok": True
    }
    assert "USD 42" not in wire.requests[0].data.decode()
    path = "/api/v1/mail/" + mid + "/draft"

    def run(did=None):
        r = c.post(path, json={"selection": cfg, "draft_id": did}, headers=h)
        assert r.status_code == 200, r.json
        return r.json

    first = run()
    assert first["state"] == "completed"
    draft = c.get("/api/v1/mail/" + mid).json["drafts"][0]
    did = draft["draft_id"]
    req = wire.requests[-1]
    assert req.full_url == draft_api.PROVIDERS[provider][1] + "/chat/completions"
    text = req.data.decode()
    assert "USD 42" in text and "Confirmed USD preference" in text
    assert all(
        word not in text
        for word in ["UNRELATED", "UNCONFIRMED", "synthetic-credential"]
    )
    payload = json.loads(text)
    assert payload["messages"][0]["content"].startswith(draft_api.RULES)
    assert (
        payload.get("response_format", {}).get("type")
        == {
            "openai": "json_schema",
            "xai": "json_schema",
            "glm": "json_object",
            "deepseek": "json_object",
            "mimo": None,
            "hy": None,
        }[provider]
    )
    c.post(
        "/api/v1/drafts/" + did + "/feedback",
        json={"content": "Keep the USD 42 quotation; shorten."},
        headers=h,
    )
    wire.reply = {
        "subject": "Re: Sample quotation",
        "body": "Thank you for your USD 42 quotation.",
    }
    rewritten = run(did)
    assert "shorten." in wire.requests[-1].data.decode()
    assert run(did)["existing"] and len(wire.requests) == 3
    drafts = c.get("/api/v1/mail/" + mid).json["drafts"]
    assert len(drafts) == 2 and {d["body"] for d in drafts} == {
        draft["body"],
        wire.reply["body"],
    }
    exchange = Bridge(store).exchange
    assert (
        json.loads(
            (exchange / "receipts" / (rewritten["job_id"] + ".json")).read_text(
                encoding="utf-8"
            )
        )["state"]
        == "completed"
    )
    Bridge(store).recover()
    assert not (exchange / "inputs" / (first["job_id"] + ".json")).exists()
    assert "synthetic-credential" not in dumps(
        [store.rows("SELECT * FROM ai_jobs"), c.get("/api/v1/snapshot").json]
    )


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("401", "凭据"),
        ("429", "限流"),
        ("timeout", "费用"),
        ("refusal", "拒绝"),
        ("truncated", "截断"),
        ("invalid", "JSON"),
        ("empty", "正文"),
    ],
)
def test_failed_request_keeps_original_and_can_retry(env, failure, expected):
    store, c, h, mid, wire = env
    cfg = configure(c, h, "hy")
    if failure in {"401", "429"}:
        wire.failure = HTTPError("synthetic", int(failure), "synthetic", {}, None)
    elif failure == "timeout":
        wire.failure = URLError("simulated timeout")
    elif failure == "empty":
        wire.reply["body"] = " "
    else:
        wire.choices = [
            {
                "finish_reason": "length" if failure == "truncated" else "stop",
                "message": {"content": "bad", "refusal": failure == "refusal"},
            }
        ]
    url = "/api/v1/mail/" + mid + "/draft"
    r = c.post(url, json={"selection": cfg}, headers=h)
    assert r.status_code == 400 and expected in r.json["error"]
    assert not store.rows("SELECT * FROM drafts WHERE message_id=?", (mid,))
    wire.choices = wire.failure = None
    wire.reply["body"] = "Synthetic reply"
    assert c.post(url, json={"selection": cfg}, headers=h).json["state"] == "completed"


def test_late_api_reply_keeps_human_edit_and_other_executor_out(env):
    store, c, h, _mid, wire = env
    cfg = configure(c, h, "mimo")
    original = store.rows("SELECT * FROM drafts WHERE draft_id='draft-a1'")[0]
    url = "/api/v1/mail/" + original["message_id"] + "/draft"

    def edit():
        c.patch(
            "/api/v1/drafts/draft-a1",
            json={
                "expected_revision": 1,
                "subject": "Human",
                "body": "Latest human edit",
            },
            headers=h,
        )
        bridge = Bridge(store)
        bridge.recover()
        row = store.rows("SELECT job_id FROM ai_jobs WHERE state='running'")[0]
        assert not (bridge.exchange / "inputs" / (row["job_id"] + ".json")).exists()

    wire.on_request = edit
    assert (
        c.post(
            url, json={"selection": cfg, "draft_id": "draft-a1"}, headers=h
        ).status_code
        == 409
    )
    assert (
        store.rows("SELECT body FROM drafts WHERE draft_id='draft-a1'")[0]["body"]
        == "Latest human edit"
    )
    assert len(store.rows("SELECT * FROM drafts")) == 3


def test_workbuddy_rules_scope_withdraw_and_replay(env):
    store, c, h, mid, wire = env
    bridge = Bridge(store)
    path = "/api/v1/mail/" + mid + "/draft"
    cfg = draft_api.settings(store)
    jid = c.post(path, json={"selection": cfg}, headers=h).json["queued"][0]["job_id"]
    job = json.loads(
        (bridge.exchange / "inputs" / (jid + ".json")).read_text(encoding="utf-8")
    )
    assert job["context"]["instructions"] == draft_api.RULES and not wire.requests
    result = {
        k: job[k]
        for k in (
            "schema_version",
            "workspace_id",
            "workspace_epoch",
            "job_id",
            "input_sha256",
        )
    }
    op = {
        "type": "create_draft",
        "operation_id": "one",
        "payload": {"message_id": mid, "subject": "Test", "body": "Synthetic reply"},
        "evidence": [],
    }
    result.update(
        operations=[op], outcome="completed", warnings=[], reviewed_todo_ids=[]
    )
    with pytest.raises(ValueError):
        bridge.import_result(result, channel="api")
    for bad in [
        [],
        [op, op],
        [{**op, "payload": {**op["payload"], "message_id": "foreign-mail"}}],
    ]:
        with pytest.raises(ValueError):
            bridge.import_result({**result, "operations": bad})
    cfg_api = configure(c, h, "deepseek")
    assert (
        c.post(path, json={"selection": cfg_api}, headers=h).status_code == 409
        and not wire.requests
    )
    assert (
        c.post(
            "/api/v1/draft-jobs/" + jid + "/withdraw", json={}, headers=h
        ).status_code
        == 200
    )
    with pytest.raises(ValueError):
        bridge.import_result(result)
    assert c.post(path, json={"selection": cfg}, headers=h).status_code == 409
    c.post("/api/v1/draft-ai/settings", json={"mode": "workbuddy"}, headers=h)
    jid = c.post(path, json={"selection": draft_api.settings(store)}, headers=h).json[
        "queued"
    ][0]["job_id"]
    job = json.loads(
        (bridge.exchange / "inputs" / (jid + ".json")).read_text(encoding="utf-8")
    )
    result.update(job_id=jid, input_sha256=job["input_sha256"])
    (bridge.exchange / "outputs" / (jid + ".json")).write_text(
        dumps(result), encoding="utf-8"
    )
    assert bridge.consume()[0]["state"] == "completed"
    assert bridge.import_result(result)["duplicate"]
    assert len(c.get("/api/v1/mail/" + mid).json["drafts"]) == 1


def test_restart_recovers_interrupted_api_without_network_or_workbuddy_file(env):
    store, c, h, mid, wire = env
    cfg = configure(c, h, "openai")
    wire.failure = URLError("interrupted")
    url = "/api/v1/mail/" + mid + "/draft"
    assert c.post(url, json={"selection": cfg}, headers=h).status_code == 400
    with store.db() as db:
        db.execute("UPDATE ai_jobs SET state='running' WHERE job_type='mail_draft'")
    bridge = Bridge(store)
    bridge.recover()
    job = store.rows(
        "SELECT job_id,state,error FROM ai_jobs WHERE job_type='mail_draft'"
    )[0]
    assert job["state"] == "failed" and "费用" in job["error"]
    assert len(wire.requests) == 1
    assert not (bridge.exchange / "inputs" / (job["job_id"] + ".json")).exists()


def test_invalid_workbuddy_file_is_reported_on_selected_mail(env):
    store, c, h, mid, wire = env
    bridge = Bridge(store)
    url = "/api/v1/mail/" + mid + "/draft"
    job = c.post(url, json={"selection": draft_api.settings(store)}, headers=h).json[
        "queued"
    ][0]
    (bridge.exchange / "outputs" / (job["job_id"] + ".json")).write_text(
        dumps(job), encoding="utf-8"
    )
    assert bridge.consume()[0]["state"] == "rejected"
    item = c.get("/api/v1/mail/" + mid).json["draft_jobs"][0]
    assert item["state"] == "failed" and "校验" in item["error"]
    assert not wire.requests
