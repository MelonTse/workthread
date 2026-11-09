"""Test both executors through the HTTP/file boundaries. No external accounts."""

import pytest
from test_m4 import client

from workthread import draft_api
from workthread import todo_assist as ta
from workthread.ai import Bridge, atomic_json
from workthread.core import Store, load
from workthread.demo import seed


def action(kind, quote, target="", title="", note="测试记录", status=""):
    return {
        "kind": kind,
        "quote": quote,
        "target": target,
        "title": title,
        "note": note,
        "status": status,
    }


class Flow:
    def __init__(self, tmp, monkeypatch, mode="api", provider="hy"):
        self.s = Store(tmp)
        seed(self.s)
        self.c, self.h = client(self.s)
        self.b = Bridge(self.s)
        self.mode = mode
        self.config = {"mode": mode, "provider": provider, "model": "synthetic-fixture"}
        self.s.set_setting("draft_ai", self.config)
        self.calls = []
        self.reply = None
        monkeypatch.setattr(draft_api, "get_key", lambda *args: "synthetic")

        def request(provider, model, key, material, *, rules, schema, name):
            assert (
                rules == ta.PROMPT and schema == ta.OUTPUT and name == "todo_decisions"
            )
            self.calls.append(material)
            return self.reply

        monkeypatch.setattr(draft_api, "request_json", request)
        self.mail = self.s.rows("SELECT * FROM messages ORDER BY rfc_message_id")

    def post(self, path, p):
        return self.c.post("/api/v1/" + path, json=p, headers=self.h)

    def raw(self, raw):
        r = self.post("todo-ai/inputs", {"raw": raw, "token": "synthetic:" + raw})
        assert r.status_code == 200
        return r.json["input_id"]

    def run(self, src, actions, *, natural=False, historical=False):
        self.reply = {"decisions": [{"source_id": src, "actions": actions}]}
        payload = (
            {"input_id": src}
            if natural
            else {"mail_ids": [src], "historical": historical}
        )
        r = self.post("todo-ai/run", {"selection": self.config, **payload})
        if self.mode == "api" or r.status_code != 200:
            return r.status_code, r.json
        jid = r.json["job_id"]
        j = load(
            (self.b.exchange / "inputs" / (jid + ".json")).read_text(encoding="utf-8")
        )
        assert j["context"]["instructions"] == ta.PROMPT
        out = {**{k: j[k] for k in ta.HEADERS}, **self.reply}
        atomic_json(self.b.exchange / "outputs" / (jid + ".json"), out)
        result = self.b.consume()[0]
        if result["state"] == "completed":
            assert self.b.import_result(out)["duplicate"]
        return (200 if result["state"] == "completed" else 400), result


@pytest.mark.parametrize(
    "mode,provider", [("workbuddy", "hy")] + [("api", p) for p in draft_api.PROVIDERS]
)
def test_intake_merge_mail_status_and_journal(tmp_path, monkeypatch, mode, provider):
    f = Flow(tmp_path, monkeypatch, mode, provider)
    monkeypatch.setattr(ta, "now", lambda: "2025-01-31T23:15:00-08:00")
    f.s.set_setting("timezone", "Asia/Shanghai")
    raw = "明天向供应商确认样品报价"
    rid = f.raw(raw)
    assert f.raw(raw) == rid
    code, result = f.run(rid, [action("new", raw, title="确认样品报价")], natural=True)
    assert code == 200 and result["created"] == 1
    tid = result["todo_ids"][0]
    task = f.s.todo(tid)
    assert task["due_date"] == "2025-02-02" and task["raw_input"] == raw
    f.s.progress(
        tid,
        {"content": "手动整理了报价要求", "occurred_at": "2025-02-01T10:00:00+08:00"},
    )
    first, second, _ = f.mail
    code, result = f.run(
        first["message_id"],
        [action("duplicate", first["body_text"], tid, "回复样品报价")],
    )
    assert code == 200 and result["review"] == 1
    review = f.s.rows("SELECT * FROM review_items WHERE kind='todo_duplicate'")[0]
    assert not f.s.todo(tid)["merged_inputs"]
    choice = {"action": "keep_existing", "revision": task["revision"]}
    r = f.post("todo-ai/reviews/" + review["review_id"], choice)
    assert r.status_code == 200, r.json
    assert f.post("todo-ai/reviews/" + review["review_id"], choice).status_code == 409
    merged = f.s.todo(tid)
    assert {x["source_ref"] for x in merged["sources"]} == {rid, first["message_id"]}
    assert merged["merged_inputs"][0]["raw_input"] == first["body_text"]
    assert merged["logs"][0]["content"] == "手动整理了报价要求"
    with f.s.db() as db:
        db.execute(
            "UPDATE messages SET body_text=? WHERE message_id=?",
            ("样品要求已交给供应商，等待报价。", second["message_id"]),
        )
    a = action(
        "status",
        "已交给供应商，等待报价",
        tid,
        note="样品要求已发出，等待供应商报价",
        status="waiting",
    )
    assert f.run(second["message_id"], [a])[1]["progress"] == 1
    final = f.s.todo(tid)
    assert final["status"] == "waiting" and len(final["logs"]) == 2
    assert final["logs"][-1]["occurred_at"] == second["internal_date"]
    assert load(final["logs"][-1]["evidence_refs"]) == load(
        final["status_events"][-1]["evidence_refs"]
    )
    assert second["message_id"] not in {m["message_id"] for m in ta.mail_scope(f.s)}
    f.config["mode"] = "api" if mode == "workbuddy" else "workbuddy"
    f.s.set_setting("draft_ai", f.config)
    assert f.run(second["message_id"], [a])[0] == 409
    assert len(f.s.todo(tid)["logs"]) == 2


@pytest.mark.parametrize(
    "raw,needs_date",
    [("确认样品", True), ("确认样品，无限期", False), ("下周确认样品", True)],
)
def test_unknown_deadline_preserves_original(tmp_path, monkeypatch, raw, needs_date):
    f = Flow(tmp_path, monkeypatch)
    rid = f.raw(raw)
    _, res = f.run(rid, [action("new", raw, title="整理样品")], natural=True)
    assert bool(res["review"]) == needs_date
    if needs_date:
        row = f.s.rows("SELECT * FROM review_items WHERE kind='todo_candidate'")[0]
        route = "todo-ai/reviews/" + row["review_id"]
        assert f.post(route, {"action": "create"}).status_code == 400
        assert (
            f.post(route, {"action": "create", "due_date": "2027-02-01"}).status_code
            == 200
        )
    t = f.s.rows("SELECT * FROM todos WHERE source_ref=?", (rid,))[0]
    assert t["raw_input"] == raw and bool(t["no_due_date"]) != needs_date


def test_source_proof_transaction_and_stale_results(tmp_path, monkeypatch):
    f = Flow(tmp_path, monkeypatch, "workbuddy")
    m = f.mail[0]
    t = f.s.create_todo({"title": "独立事项", "no_due_date": True})
    mid = m["message_id"]
    path = "todo-ai/run"
    values = {"mail_ids": [mid], "selection": f.config}
    jid = f.post(path, values).json["job_id"]
    assert jid == f.post(path, values).json["job_id"]
    job = load((f.b.exchange / "inputs" / (jid + ".json")).read_text(encoding="utf-8"))
    result = {
        **{k: job[k] for k in ta.HEADERS},
        "decisions": [
            {
                "source_id": mid,
                "actions": [
                    action("new", m["body_text"], title="合法但应回滚"),
                    action("status", "不存在的引文", t["todo_id"], status="waiting"),
                ],
            }
        ],
    }
    assert f.post("ai/import", result).status_code == 400
    assert not f.s.rows("SELECT * FROM review_items WHERE kind='todo_candidate'")
    result["decisions"][0]["actions"] = [
        action("status", m["body_text"], t["todo_id"], status="done")
    ]
    f.s.edit_todo(t["todo_id"], {"title": "人工修订"}, t["revision"])
    assert f.post("ai/import", result).status_code == 409
    assert (
        f.s.todo(t["todo_id"])["status"] == t["status"]
        and not f.s.todo(t["todo_id"])["logs"]
    )
    assert any(i["message_id"] == mid for i in ta.mail_scope(f.s))


@pytest.mark.parametrize(
    "case", ["unlinked", "protected", "manual_done", "historical", "sent_done"]
)
def test_automatic_status_boundary(tmp_path, monkeypatch, case):
    f = Flow(tmp_path, monkeypatch)
    first, second, sent = f.mail
    t = f.s.create_todo(
        {
            "raw_input": "跟踪供应商",
            "no_due_date": True,
            "source_ref": first["message_id"] if case != "unlinked" else "unrelated",
            "completion_policy": {
                "type": "reply_sent",
                "reply_to_message_id": first["rfc_message_id"],
            }
            if case == "sent_done"
            else {"type": "manual"},
        }
    )
    tid = t["todo_id"]
    if case == "protected":
        f.s.edit_todo(tid, {"status": "in_progress"}, 1)
    m = sent if case == "sent_done" else second
    if case == "historical":
        with f.s.db() as c:
            c.execute(
                "UPDATE messages SET internal_date='2010-01-01T10:00:00+00:00' WHERE message_id=?",
                (m["message_id"],),
            )
    status = "done" if case in ("manual_done", "sent_done") else "waiting"
    code, r = f.run(
        m["message_id"],
        [action("status", m["body_text"], tid, note="状态节点", status=status)],
        historical=case == "historical",
    )
    assert code == 200, r
    if case != "sent_done":
        assert r["review"] == 1 and not f.s.todo(tid)["logs"]
        review = f.s.rows(
            "SELECT review_id FROM review_items WHERE kind='todo_change'"
        )[0]["review_id"]
        response = f.post(
            "todo-ai/reviews/" + review,
            {"action": "accept", "revision": f.s.todo(tid)["revision"]},
        )
        assert response.status_code == 200, response.json
    assert f.s.todo(tid)["status"] == status and len(f.s.todo(tid)["logs"]) == 1


def test_interrupted_sync_only_processes_archived_mail_and_resumes(
    tmp_path, monkeypatch
):
    from test_m2 import account
    from test_mail_resume import DropDuringBody

    from workthread.demo import FakeIMAP
    from workthread.mail import Sync

    s = Store(tmp_path)
    account(s)
    sync = Sync(s, lambda _: DropDuringBody())
    sync.retry_delays = ()
    assert sync.run("demo")["state"] == "interrupted"
    before = ta.mail_scope(s)
    assert len(before) == 1
    mid = before[0]["message_id"]
    b = Bridge(s)
    c, h = client(s)
    cfg = draft_api.settings(s)
    url = "/api/v1/todo-ai/run"
    r = c.post(url, json={"mail_ids": [mid], "selection": cfg}, headers=h)
    jid = r.json["job_id"]
    j = load((b.exchange / "inputs" / (jid + ".json")).read_text(encoding="utf-8"))
    out = {
        **{k: j[k] for k in ta.HEADERS},
        "decisions": [{"source_id": mid, "actions": []}],
    }
    b.import_result(out)
    restarted = Store(tmp_path)
    assert not ta.mail_scope(restarted)
    assert Sync(restarted, lambda _: FakeIMAP()).run("demo")["state"] == "completed"
    remaining = ta.mail_scope(restarted)
    assert len(remaining) == 2 and mid not in {r["message_id"] for r in remaining}


def test_failed_second_source_rolls_back_and_retry_succeeds(tmp_path, monkeypatch):
    f = Flow(tmp_path, monkeypatch)
    a, b = f.mail[:2]
    ids = [m["message_id"] for m in [a, b]]
    params = {"mail_ids": ids, "selection": f.config}
    f.reply = {
        "decisions": [
            {
                "source_id": ids[0],
                "actions": [action("new", a["body_text"], title="待确认日期的样品")],
            },
            {
                "source_id": ids[1],
                "actions": [action("new", "伪造的引文", title="无效")],
            },
        ]
    }
    assert f.post("todo-ai/run", params).status_code == 400
    assert not f.s.rows("SELECT * FROM review_items WHERE kind='todo_candidate'")
    assert set(ids) <= {r["message_id"] for r in ta.mail_scope(f.s)}
    f.reply["decisions"][1]["actions"] = []
    r = f.post("todo-ai/run", params)
    assert r.status_code == 200 and r.json["review"] == 1
    assert not set(ids) & {r["message_id"] for r in ta.mail_scope(f.s)}


def test_withdraw_for_executor_switch_and_no_late_result(tmp_path, monkeypatch):
    f = Flow(tmp_path, monkeypatch, "workbuddy")
    mid = f.mail[0]["message_id"]
    path = "todo-ai/run"
    jid = f.post(path, {"selection": f.config, "mail_ids": [mid]}).json["job_id"]
    j = load((f.b.exchange / "inputs" / (jid + ".json")).read_text(encoding="utf-8"))
    out = {
        **{k: j[k] for k in ta.HEADERS},
        "decisions": [{"source_id": mid, "actions": []}],
    }
    f.config["mode"] = f.mode = "api"
    f.s.set_setting("draft_ai", f.config)
    assert f.post(path, {"selection": f.config, "mail_ids": [mid]}).status_code == 409
    assert f.post("todo-ai/withdraw/" + jid, {}).status_code == 200
    assert f.post("ai/import", out).status_code == 400
    assert f.run(mid, [])[1]["state"] == "completed"
    assert len(f.calls) == 1


@pytest.mark.parametrize("provider", list(draft_api.PROVIDERS))
def test_provider_wire_format_for_todos(tmp_path, monkeypatch, provider):
    from test_draft_ai import Wire

    s = Store(tmp_path)
    http, h = client(s)
    wire = Wire(monkeypatch)
    cfg = {"mode": "api", "provider": provider, "model": "synthetic"}
    assert (
        http.post(
            "/api/v1/draft-ai/settings", json={**cfg, "key": "synthetic"}, headers=h
        ).status_code
        == 200
    )
    raw = "请在 2027年2月5日前确认样品。"
    rid = ta.capture(s, raw, "wire")
    wire.reply = {
        "decisions": [
            {"source_id": rid, "actions": [action("new", raw, title="确认样品")]}
        ]
    }
    r = http.post(
        "/api/v1/todo-ai/run", json={"selection": cfg, "input_id": rid}, headers=h
    )
    assert r.status_code == 200, r.json
    assert s.todo(r.json["todo_ids"][0])["due_date"] == "2027-02-05"
    payload = load(wire.requests[0].data)
    assert payload["messages"][0]["content"] == ta.PROMPT
    assert (
        wire.requests[0].full_url
        == draft_api.PROVIDERS[provider][1] + "/chat/completions"
    )
    assert (
        payload.get("response_format", {}).get("type")
        == {"schema": "json_schema", "json": "json_object", "prompt": None}[
            draft_api.PROVIDERS[provider][2]
        ]
    )


def test_same_batch_new_and_followup_in_mail_order(tmp_path, monkeypatch):
    f = Flow(tmp_path, monkeypatch)
    first, second = f.mail[:2]
    for t in f.s.rows("SELECT * FROM todos WHERE merged_into_id IS NULL"):
        f.s.edit_todo(t["todo_id"], {"status": "done"}, t["revision"])
    raw = "请在 2027-03-10 前确认装箱清单"
    with f.s.db() as db:
        db.execute(
            "UPDATE messages SET body_text=? WHERE message_id=?",
            (raw, first["message_id"]),
        )
    followup = action(
        "status",
        second["body_text"],
        "new:" + first["message_id"] + ":1",
        note="等待装箱清单",
        status="waiting",
    )
    f.reply = {
        "decisions": [
            {"source_id": second["message_id"], "actions": [followup]},
            {
                "source_id": first["message_id"],
                "actions": [action("new", raw, title="确认装箱清单")],
            },
        ]
    }
    response = f.post(
        "todo-ai/run",
        {
            "selection": f.config,
            "mail_ids": [second["message_id"], first["message_id"]],
        },
    )
    assert response.status_code == 200, response.json
    assert response.json["created"] == response.json["progress"] == 1
    todo = f.s.todo(response.json["todo_ids"][0])
    assert (
        todo["due_date"] == "2027-03-10"
        and todo["status"] == "waiting"
        and len(todo["logs"]) == 1
    )


def test_keep_incoming_preserves_manual_history_and_stale_merge_guard(
    tmp_path, monkeypatch
):
    f = Flow(tmp_path, monkeypatch)
    old = f.s.create_todo({"raw_input": "人工记录的样品报价", "no_due_date": True})
    tid = old["todo_id"]
    f.s.progress(tid, {"content": "人工进展"})
    m = f.mail[0]
    assert (
        f.run(
            m["message_id"],
            [action("duplicate", m["body_text"], tid, "邮件记录的样品报价")],
        )[1]["review"]
        == 1
    )
    rid = f.s.rows("SELECT review_id FROM review_items WHERE kind='todo_duplicate'")[0][
        "review_id"
    ]
    route = "todo-ai/reviews/" + rid
    f.s.edit_todo(tid, {"title": "人工修订"}, old["revision"])
    assert (
        f.post(
            route, {"action": "keep_incoming", "revision": old["revision"]}
        ).status_code
        == 409
    )
    assert (
        f.post(
            route, {"action": "keep_incoming", "revision": old["revision"] + 1}
        ).status_code
        == 200
    )
    kept = f.s.todo(f.s.todo(tid)["merged_into_id"])
    assert (
        kept["title"] == "邮件记录的样品报价"
        and kept["merged_inputs"][0]["raw_input"] == old["raw_input"]
    )
    assert kept["logs"][0]["origin_todo_id"] == tid and len(kept["sources"]) == 2
