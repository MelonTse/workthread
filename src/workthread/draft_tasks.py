"""Prepare scoped draft jobs and admit a single matching draft at import time."""

import tempfile
from pathlib import Path

from filelock import FileLock, Timeout

from . import draft_api
from .core import Conflict, digest, dumps, load, now, uid


def saved_feedback(store, did):
    return store.rows(
        "SELECT feedback_id,content FROM feedback WHERE target_id=? ORDER BY created_at,feedback_id",
        (did,),
    )


def material(store, mid, did):
    rows = store.rows("SELECT * FROM messages WHERE message_id=?", (mid,))
    if not rows:
        raise ValueError("找不到原邮件")
    target = rows[0]
    # Follow explicit ancestry only. Same subject, customer or sibling thread is insufficient.
    ancestors = [
        ref for ref in [*load(target["refs"], []), target["in_reply_to"]] if ref
    ]
    messages = [target] + store.rows(
        """SELECT message_id,subject,body_text,date FROM messages WHERE message_id<>?
           AND rfc_message_id IN (SELECT value FROM json_each(?))
           ORDER BY internal_date DESC,message_id LIMIT 4""",
        (mid, dumps(ancestors)),
    )
    senders = [
        a["address"].lower() for a in load(target["sender"], []) if a.get("address")
    ]
    customers = store.rows(
        """SELECT DISTINCT c.customer_id FROM contacts c JOIN customers u USING(customer_id)
           WHERE lower(c.address) IN (SELECT value FROM json_each(?))
           AND NOT EXISTS (SELECT 1 FROM entity_confirmations e WHERE e.confirmed=0 AND
           ((e.entity_type='contacts' AND e.entity_id=c.contact_id) OR
            (e.entity_type='customers' AND e.entity_id=c.customer_id)))""",
        (dumps(senders),),
    )
    customer = customers[0]["customer_id"] if len(customers) == 1 else None
    knowledge = store.rows(
        """SELECT scope,content FROM knowledge_items k WHERE confirmed=1
           AND (valid_until IS NULL OR valid_until='' OR date(valid_until)>=date('now'))
           AND (scope='personal' OR (scope='customer' AND subject_id=?) OR
           (scope='case' AND subject_id IN (SELECT case_id FROM cases WHERE customer_id=?
            AND NOT EXISTS (SELECT 1 FROM entity_confirmations WHERE entity_type='cases' AND entity_id=case_id AND confirmed=0))
            AND EXISTS (SELECT 1 FROM json_each(k.evidence_refs) WHERE json_extract(value,'$.message_id')=?)))
           ORDER BY knowledge_id""",
        (customer, customer, mid),
    )
    context = {
        "messages": [
            {k: m[k] for k in ("message_id", "subject", "body_text", "date")}
            for m in messages
        ],
        "knowledge": knowledge,
        "email_style": (store.setting("profile") or {}).get("email_style", ""),
        "target_message_id": mid,
    }
    if did:
        drafts = store.rows(
            "SELECT draft_id,message_id,subject,body,revision FROM drafts WHERE draft_id=? AND message_id=?",
            (did, mid),
        )
        if not drafts:
            raise ValueError("找不到原邮件对应的草稿")
        context["draft_rewrite"] = {**drafts[0], "feedback": saved_feedback(store, did)}
    return context


def validate_operation(store, job, result):
    ctx = job["context"]
    ops = result["operations"]
    if (
        len(ops) != 1
        or ops[0]["type"] != "create_draft"
        or ops[0].get("todo_id")
        or ops[0]["payload"].get("message_id") != ctx["target_message_id"]
    ):
        raise ValueError("邮件草稿任务只接受一份关联原邮件的草稿")
    draft_api.validate_draft(
        {k: v for k, v in ops[0]["payload"].items() if k != "message_id"}
    )
    did = ctx.get("draft_rewrite", {}).get("draft_id")
    current = material(store, ctx["target_message_id"], did)
    if digest(current) != ctx["material_hash"]:
        raise Conflict("原邮件、草稿、修改意见或知识已更改，请重新生成")
    if not did and store.rows(
        "SELECT 1 FROM drafts WHERE message_id=?", (ctx["target_message_id"],)
    ):
        raise Conflict("该邮件已有新稿，请刷新查看")


def mail_lock(store, mid):
    return FileLock(
        Path(tempfile.gettempdir())
        / ("workthread-mail-" + digest([str(store.root.resolve()), mid]) + ".lock")
    )


def recover_api_request(store, job, lock_id):
    # CLI commands also call recover while the server is live.
    try:
        with (
            mail_lock(store, lock_id).acquire(timeout=0),
            store.db() as db,
        ):
            db.execute(
                """UPDATE ai_jobs SET state='failed',error=?,updated_at=?
                          WHERE job_id=? AND state='running'""",
                ("上一请求中断；再次请求可能产生费用", now(), job["job_id"]),
            )
    except Timeout:
        pass


def execute(bridge, mid, did, selection):
    from .ai import atomic_json, validate

    store = bridge.s
    mode = selection["mode"]
    # One active call per mail, including across local server processes. No DB lock during HTTP.
    lock = mail_lock(store, mid)
    try:
        lock.acquire(timeout=0)
    except Timeout:
        raise Conflict("这封邮件的草稿正在处理，请稍后刷新") from None
    try:
        with store.lock:
            context = material(store, mid, did)
            fingerprint = digest(context)
            if not did and store.rows(
                "SELECT 1 FROM drafts WHERE message_id=?", (mid,)
            ):
                raise Conflict("该邮件已有草稿，请刷新后选择重写")
            epoch = store.setting("workspace_epoch")
            for row in store.rows(
                """SELECT job_id,state,input_json FROM ai_jobs WHERE job_type='mail_draft'
                                   AND json_extract(input_json,'$.context.target_message_id')=? ORDER BY created_at DESC""",
                (mid,),
            ):
                previous = load(row["input_json"])
                if (
                    previous["workspace_epoch"] != epoch
                    or previous["rules_version"] != draft_api.RULES_VERSION
                ):
                    continue
                old = previous["context"]
                if row["state"] == "running":
                    # Acquiring the same OS lock proves the previous process released it.
                    with store.db() as db:
                        db.execute(
                            "UPDATE ai_jobs SET state='failed',error=? WHERE job_id=?",
                            ("上一请求中断，重试可能产生费用", row["job_id"]),
                        )
                    raise Conflict("上一请求中断，未记录成功结果；再次请求可能产生费用")
                if old["material_hash"] != fingerprint:
                    continue
                if row["state"] == "pending":
                    if mode != "workbuddy":
                        raise Conflict(
                            "相同草稿正在等待 WorkBuddy；可在邮件页撤回后改用 API"
                        )
                    return {"queued": [{"job_id": row["job_id"]}], "existing": True}
                if row["state"] == "completed":
                    return {
                        "state": "completed",
                        "draft_id": row["job_id"],
                        "existing": True,
                        "job_id": row["job_id"],
                    }
            key = (
                draft_api.get_key(store, selection["provider"])
                if mode == "api"
                else None
            )
            jid = uid()
            job = {
                "job_id": jid,
                "job_type": "mail_draft",
                "schema_version": "1.0",
                "rules_version": draft_api.RULES_VERSION,
                "workspace_id": store.setting("workspace_id"),
                "workspace_epoch": epoch,
                "created_at": now(),
                "timezone": store.setting("timezone"),
                "scope": {"mail_batch_id": jid, "todo_ids": [], "historical": False},
                "context": {
                    **context,
                    "execution": selection,
                    "instructions": draft_api.RULES,
                    "material_hash": fingerprint,
                },
            }
            job["input_sha256"] = digest(job)
            validate(job, "ai-input")
            with store.db() as db:
                db.execute(
                    "INSERT INTO ai_jobs VALUES (?,?,?,?,?,?,?,?)",
                    (
                        jid,
                        "mail_draft",
                        "pending" if mode == "workbuddy" else "running",
                        dumps(job),
                        None,
                        None,
                        now(),
                        now(),
                    ),
                )
                if mode == "workbuddy":
                    atomic_json(bridge.exchange / "inputs" / (jid + ".json"), job)
            if mode == "workbuddy":
                return {"queued": [{"job_id": jid}], "existing": False}
        try:
            draft = draft_api.generate(
                selection["provider"], selection["model"], key, context
            )
            result = {
                k: job[k]
                for k in (
                    "schema_version",
                    "job_id",
                    "workspace_id",
                    "workspace_epoch",
                    "input_sha256",
                )
            }
            result.update(
                outcome="completed",
                reviewed_todo_ids=[],
                warnings=[],
                operations=[
                    {
                        "operation_id": jid + "-draft",
                        "type": "create_draft",
                        "payload": {"message_id": mid, **draft},
                        "evidence": [],
                    }
                ],
            )
            return bridge.import_result(result, channel="api")
        except Exception as exc:
            with store.db() as db:
                detail = str(exc) if isinstance(exc, ValueError) else "生成未完成"
                db.execute(
                    "UPDATE ai_jobs SET state='failed',error=?,updated_at=? WHERE job_id=? AND state='running'",
                    (detail[:160], now(), jid),
                )
            raise
    finally:
        lock.release()
