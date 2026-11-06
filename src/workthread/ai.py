"""Versioned file exchange; no model calls and no SQL supplied by an agent."""

import datetime as dt
import json
import os
from pathlib import Path
from jsonschema import Draft202012Validator
from .core import uid, now, dumps, digest, load, Conflict, DeadlineError, validate_deadline

SCHEMA_DIR = Path(__file__).parent / "schemas"


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(dumps(obj))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def validate(obj, name):
    schema = json.loads((SCHEMA_DIR / (name + ".json")).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(obj)


class Bridge:
    def __init__(self, store):
        self.s = store
        self.exchange = store.root / "agent-workspace" / "exchange"

    def queue_draft_rewrite(self, draft_id):
        """Queue one saved draft with its exact feedback; never invoke a model."""
        with self.s.lock:
            drafts = self.s.rows("SELECT * FROM drafts WHERE draft_id=?", (draft_id,))
            if not drafts or not drafts[0]["message_id"]:
                raise ValueError("草稿未关联原邮件，无法加入重写队列")
            draft = drafts[0]
            if not self.s.rows("SELECT message_id FROM messages WHERE message_id=?", (draft["message_id"],)):
                raise ValueError("找不到草稿对应的原邮件")
            feedback = self.s.rows(
                "SELECT * FROM feedback WHERE target_id=? ORDER BY created_at, feedback_id",
                (draft_id,),
            )
            rewrite = {
                "draft_id": draft_id,
                "message_id": draft["message_id"],
                "revision": draft["revision"],
                "subject": draft["subject"],
                "body": draft["body"],
                "feedback": feedback,
                "instruction": "根据这份已保存草稿及其反馈生成新的回复草稿，使用 create_draft；不发送邮件，不修改 To Do。",
            }
            for pending in self.s.rows("SELECT job_id, input_json FROM ai_jobs WHERE state='pending'"):
                if load(pending["input_json"])["context"].get("draft_rewrite") == rewrite:
                    return {"queued": [{"job_id": pending["job_id"]}], "existing": True}
            jobs = self.prepare(rewrite_draft=rewrite)
            return {"queued": [{"job_id": job["job_id"]} for job in jobs], "existing": False}

    def prepare(self, kind="reconcile", historical=False, *, rewrite_draft=None):
        if kind not in ("reconcile", "normalize", "historical"):
            raise ValueError("unknown job type")
        active = self.s.rows(
            "SELECT * FROM todos WHERE merged_into_id IS NULL AND status NOT IN ('done','cancelled') ORDER BY created_at"
        )
        mails = self.s.rows("SELECT * FROM messages ORDER BY internal_date DESC")
        analyzed = set()
        for completed in self.s.rows(
            "SELECT input_json FROM ai_jobs WHERE state='completed'"
        ):
            previous = load(completed["input_json"])
            if previous["scope"]["historical"] == historical and not previous["context"].get("draft_rewrite"):
                analyzed.update(
                    m["message_id"] for m in previous["context"]["messages"]
                )
        mails = [m for m in mails if m["message_id"] not in analyzed]
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)).isoformat()
        mails = (
            [m for m in mails if (m["internal_date"] or "") >= cutoff]
            if not historical
            else [m for m in mails if (m["internal_date"] or "") < cutoff]
        )
        if rewrite_draft is not None:
            # Explicit rewrite requests include already analyzed / older mail too.
            # They are separate from pending general jobs so new feedback is not lost.
            active = []
            mails = self.s.rows(
                "SELECT * FROM messages WHERE message_id=?", (rewrite_draft["message_id"],)
            )
        jobs = []
        # Every open task is covered in bounded pages; each page contains its evidence.
        for offset in range(0, max(len(active), len(mails), 1), 20):
            todo_page = active[offset : offset + 20]
            mail_page = mails[offset : offset + 20]
            linked = {t["source_ref"] for t in todo_page}
            for log in [
                r for t in todo_page for r in self.s.todo(t["todo_id"])["logs"]
            ]:
                linked.update(
                    e["message_id"]
                    for e in load(log["evidence_refs"], [])
                    if "message_id" in e
                )
            related = [
                m
                for m in self.s.rows("SELECT * FROM messages")
                if m["message_id"] in linked
            ]
            known = {m["message_id"]: m for m in mail_page + related}
            for m in list(known.values()):
                for related_mail in self.s.thread(m["message_id"]):
                    known[related_mail["message_id"]] = related_mail
            context = {
                "messages": list(known.values()),
                "todos": todo_page,
                "progress_logs": [
                    r for t in todo_page for r in self.s.todo(t["todo_id"])["logs"]
                ],
                "human_decisions": self.s.rows(
                    "SELECT * FROM audit_events WHERE kind IN ('todo_edited','review_resolved') ORDER BY created_at DESC LIMIT 100"
                ),
                "customers": self.s.rows(
                    "SELECT e.* FROM customers e WHERE NOT EXISTS (SELECT 1 FROM entity_confirmations v WHERE v.entity_type='customers' AND v.entity_id=e.customer_id AND v.confirmed=0)"
                ),
                "contacts": self.s.rows(
                    "SELECT e.* FROM contacts e WHERE NOT EXISTS (SELECT 1 FROM entity_confirmations v WHERE v.entity_type='contacts' AND v.entity_id=e.contact_id AND v.confirmed=0)"
                ),
                "cases": self.s.rows(
                    "SELECT e.* FROM cases e WHERE NOT EXISTS (SELECT 1 FROM entity_confirmations v WHERE v.entity_type='cases' AND v.entity_id=e.case_id AND v.confirmed=0)"
                ),
                "knowledge": self.s.rows(
                    "SELECT * FROM knowledge_items WHERE confirmed=1"
                ),
                "taxonomy": self.s.rows("SELECT * FROM categories"),
                "feedback": [
                    feedback
                    for feedback in self.s.rows(
                        "SELECT f.*, d.message_id, d.subject AS draft_subject, "
                        "d.body AS draft_body FROM feedback f "
                        "LEFT JOIN drafts d ON d.draft_id=f.target_id "
                        "ORDER BY f.created_at DESC LIMIT 100"
                    )
                    if feedback["target_id"] is None or feedback["message_id"] in known
                ],
                "contact_relations": self.s.rows(
                    "SELECT * FROM contact_relations WHERE confirmed=1"
                ),
                "profile": self.s.setting("profile"),
            }
            if rewrite_draft is not None:
                context["draft_rewrite"] = rewrite_draft
            job = {
                "schema_version": "1.0",
                "workspace_id": self.s.setting("workspace_id"),
                "workspace_epoch": self.s.setting("workspace_epoch"),
                "job_id": uid(),
                "job_type": kind,
                "rules_version": "1.0.0rc3",
                "created_at": now(),
                "timezone": self.s.setting("timezone"),
                "scope": {
                    "mail_batch_id": uid(),
                    "todo_ids": [t["todo_id"] for t in todo_page],
                    "historical": historical,
                },
                "context": context,
            }
            job["input_sha256"] = digest(job)
            validate(job, "ai-input")
            with self.s.db() as c:
                c.execute(
                    "INSERT INTO ai_jobs VALUES (?,?,?,?,?,?,?,?)",
                    (
                        job["job_id"],
                        kind,
                        "pending",
                        dumps(job),
                        None,
                        None,
                        now(),
                        now(),
                    ),
                )
            atomic_json(self.exchange / "inputs" / (job["job_id"] + ".json"), job)
            jobs.append(job)
        return jobs

    def check_evidence(self, c, refs, job):
        allowed = {m["message_id"] for m in job["context"]["messages"]}
        for e in refs:
            if e["message_id"] not in allowed:
                raise ValueError("evidence outside job scope")
            m = c.execute(
                "SELECT * FROM messages WHERE message_id=?", (e["message_id"],)
            ).fetchone()
            if not m or e["quote"] not in m["body_text"]:
                raise ValueError("evidence quote not found")

    def import_result(self, result):
        try:
            receipt = self._import_result(result)
        except Conflict as error:
            if isinstance(result, dict) and isinstance(result.get("job_id"), str):
                with self.s.db() as c:
                    c.execute(
                        "UPDATE ai_jobs SET state='superseded',error=?,updated_at=? WHERE job_id=? AND state!='completed'",
                        (str(error), now(), result["job_id"]),
                    )
                atomic_json(
                    self.exchange / "receipts" / (result["job_id"] + ".json"),
                    {
                        "job_id": result["job_id"],
                        "state": "superseded",
                        "error": str(error),
                    },
                )
            raise
        atomic_json(self.exchange / "receipts" / (receipt["job_id"] + ".json"), receipt)
        return receipt

    def _import_result(self, result):
        validate(result, "ai-output")
        with self.s.db() as c:
            row = c.execute(
                "SELECT * FROM ai_jobs WHERE job_id=?", (result["job_id"],)
            ).fetchone()
            if not row:
                raise ValueError("unknown job")
            if row["state"] == "completed":
                if load(row["result_json"]) != result:
                    raise Conflict("completed job has a different result")
                return {
                    "job_id": row["job_id"],
                    "state": "completed",
                    "duplicate": True,
                }
            job = load(row["input_json"])
            for k in ("workspace_id", "workspace_epoch", "input_sha256"):
                expected = self.s.setting(k) if k != "input_sha256" else job[k]
                if result[k] != expected or result[k] != job[k]:
                    raise Conflict("stale or foreign " + k)
            if set(result["reviewed_todo_ids"]) != set(job["scope"]["todo_ids"]):
                raise ValueError("incomplete reconciliation coverage")
            snapshots = {t["todo_id"]: t for t in job["context"]["todos"]}
            for tid, t in snapshots.items():
                current = c.execute(
                    "SELECT revision FROM todos WHERE todo_id=?", (tid,)
                ).fetchone()
                if not current or current[0] != t["revision"]:
                    raise Conflict("stale todo snapshot")
            for op in result["operations"]:
                seen = c.execute(
                    "SELECT payload_hash FROM ai_operations WHERE operation_id=?",
                    (op["operation_id"],),
                ).fetchone()
                if seen:
                    if seen[0] != digest(op):
                        raise Conflict("operation ID collision")
                    continue
                refs = op.get("evidence", [])
                self.check_evidence(c, refs, job)
                typ = op["type"]
                p = op["payload"]
                tid = op.get("todo_id")
                if tid:
                    if (
                        tid not in snapshots
                        or op.get("expected_revision") != snapshots[tid]["revision"]
                    ):
                        raise Conflict("missing or stale operation revision")
                if typ == "create_todo":
                    if not refs:
                        raise ValueError("mail todo needs evidence")
                    mail = c.execute(
                        "SELECT * FROM messages WHERE message_id=?",
                        (refs[0]["message_id"],),
                    ).fetchone()
                    raw = p.get("raw_input", refs[0]["quote"])
                    if raw not in mail["body_text"]:
                        raise ValueError(
                            "mail raw_input must preserve original evidence"
                        )
                    payload = dict(
                        p,
                        raw_input=raw,
                        input_at=mail["internal_date"] or mail["archived_at"],
                        input_timezone=job["timezone"],
                        source_ref=refs[0]["message_id"],
                        status="open",
                    )
                    payload.pop("customer_id", None)
                    payload.pop("case_id", None)
                    if job["scope"]["historical"]:
                        self.s._review(c, "historical_todo", payload, refs)
                    else:
                        key = "mail:" + refs[0]["message_id"] + ":" + p["action_key"]
                        self.s._create_todo(c, payload, "mail_ai", key)
                elif typ == "normalize_todo":
                    orig = snapshots[tid]
                    if {"due_date", "no_due_date"}.intersection(p):
                        validate_deadline(
                            p.get("due_date", orig["due_date"]),
                            p.get("no_due_date", orig["no_due_date"]),
                        )
                    due, ambiguous = self.s.relative_date(
                        orig["raw_input"], orig["input_at"], orig["input_timezone"]
                    )
                    if due and p.get("due_date") and p["due_date"] != due:
                        raise DeadlineError("due_date: relative date must use input timestamp")
                    changes = {
                        k: v
                        for k, v in p.items()
                        if k
                        in (
                            "title",
                            "description",
                            "priority",
                            "due_date",
                            "no_due_date",
                            "completion_criteria",
                        )
                    }
                    if due and not {"due_date", "no_due_date"}.intersection(p):
                        changes["due_date"] = due
                    if ambiguous and {"due_date", "no_due_date"}.intersection(changes):
                        changes.pop("due_date", None)
                        changes.pop("no_due_date", None)
                        self.s._review(
                            c, "ambiguous_date", {"todo_id": tid, "suggestion": p}
                        )
                    current = c.execute(
                        "SELECT revision FROM todos WHERE todo_id=?", (tid,)
                    ).fetchone()[0]
                    if changes:
                        self.s._edit(c, tid, changes, current, human=False)
                    c.execute(
                        "UPDATE todos SET normalization_status='complete' WHERE todo_id=?",
                        (tid,),
                    )
                elif typ == "append_progress":
                    self.s._progress(
                        c, tid, dict(p, evidence_refs=refs), "ai", op["operation_id"]
                    )
                elif typ == "propose_status":
                    original = snapshots[tid]
                    status = p["status"]
                    protected = load(original["protected_fields"], [])
                    safe = (
                        status in ("open", "in_progress", "waiting")
                        and "status" not in protected
                    )
                    if status == "done" and refs and "status" not in protected:
                        policy = load(original["completion_policy"], {})
                        if policy.get("type") == "reply_sent":
                            for e in refs:
                                mail = c.execute(
                                    "SELECT * FROM messages WHERE message_id=?",
                                    (e["message_id"],),
                                ).fetchone()
                                sent = c.execute(
                                    "SELECT 1 FROM mail_occurrences o JOIN mail_folders f ON o.folder_id=f.folder_id JOIN mail_accounts a ON o.account_id=a.account_id WHERE o.message_id=? AND f.direction='sent' AND lower(a.username) IN (SELECT lower(json_extract(value,'$.address')) FROM json_each(?))",
                                    (e["message_id"], mail["sender"]),
                                ).fetchone()
                                safe = bool(
                                    sent
                                    and mail["in_reply_to"]
                                    == policy.get("reply_to_message_id")
                                )
                                if safe:
                                    break
                    if safe and refs:
                        current = c.execute(
                            "SELECT revision FROM todos WHERE todo_id=?", (tid,)
                        ).fetchone()[0]
                        self.s._edit(
                            c,
                            tid,
                            {"status": status},
                            current,
                            human=False,
                            reason=p["reason"],
                            evidence=refs,
                        )
                    else:
                        self.s._review(c, "status", {"todo_id": tid, **p}, refs)
                elif typ in (
                    "suggest_link",
                    "suggest_duplicate",
                    "propose_knowledge",
                    "suggest_relationship",
                    "suggest_case",
                ):
                    self.s._review(
                        c, typ, dict(p, **({"todo_id": tid} if tid else {})), refs
                    )
                elif typ == "create_draft":
                    d = uid()
                    c.execute(
                        "INSERT INTO drafts VALUES (?,?,?,?,?,?,?,?)",
                        (
                            d,
                            p.get("message_id"),
                            tid,
                            p["subject"],
                            p["body"],
                            1,
                            now(),
                            now(),
                        ),
                    )
                elif typ == "mail_analysis":
                    for mid in p["message_ids"]:
                        if mid not in {
                            m["message_id"] for m in job["context"]["messages"]
                        }:
                            raise ValueError("analysis outside scope")
                    c.execute(
                        "INSERT INTO analyses VALUES (?,?,?,?,?,?,?)",
                        (
                            uid(),
                            dumps(p["message_ids"]),
                            p["work_type"],
                            p["stage"],
                            p["summary"],
                            p["advice"],
                            now(),
                        ),
                    )
                c.execute(
                    "INSERT INTO ai_operations VALUES (?,?,?)",
                    (op["operation_id"], job["job_id"], digest(op)),
                )
            c.execute(
                "UPDATE ai_jobs SET state='completed',result_json=?,error=NULL,updated_at=? WHERE job_id=?",
                (dumps(result), now(), job["job_id"]),
            )
            self.s.audit(
                c,
                "ai_imported",
                job["job_id"],
                {"operations": len(result["operations"])},
            )
        receipt = {"job_id": job["job_id"], "state": "completed", "duplicate": False}
        atomic_json(self.exchange / "receipts" / (job["job_id"] + ".json"), receipt)
        return receipt

    def consume(self):
        results = []
        for f in sorted((self.exchange / "outputs").glob("*.json")):
            try:
                if f.stat().st_size > 10_000_000:
                    raise ValueError("result exceeds 10 MB")
                receipt = self.import_result(json.loads(f.read_text(encoding="utf-8")))
                f.unlink()
                results.append(receipt)
            except Exception as e:
                target = self.exchange / "quarantine" / (uid() + ".json")
                os.replace(f, target)
                atomic_json(
                    target.with_suffix(".error.json"),
                    {"error": str(e), "recorded_at": now()},
                )
                results.append({"state": "rejected", "error": str(e)})
        for f in sorted((self.exchange / "intake").glob("*.json")):
            try:
                p = json.loads(f.read_text(encoding="utf-8"))
                validate(p, "intake")
                todo = self.s.create_todo(p, "workbuddy", "intake:" + p["request_id"])
                atomic_json(
                    self.exchange / "receipts" / (p["request_id"] + ".json"),
                    {"todo_id": todo["todo_id"], "state": "saved"},
                )
                f.unlink()
                results.append({"todo_id": todo["todo_id"], "state": "saved"})
            except Exception as e:
                os.replace(f, self.exchange / "quarantine" / (uid() + ".json"))
                results.append({"state": "rejected", "error": str(e)})
        return results

    def recover(self):
        for row in self.s.rows(
            "SELECT * FROM ai_jobs WHERE state IN ('pending','running','failed')"
        ):
            job = load(row["input_json"])
            if job["workspace_epoch"] == self.s.setting("workspace_epoch"):
                atomic_json(self.exchange / "inputs" / (row["job_id"] + ".json"), job)

    def resolve(self, rid, accept):
        with self.s.db() as c:
            r = c.execute(
                "SELECT * FROM review_items WHERE review_id=? AND state='pending'",
                (rid,),
            ).fetchone()
            if not r:
                raise ValueError("unknown pending review")
            p = load(r["payload"])
            kind = r["kind"]
            if accept:
                if kind in ("status", "protected_change"):
                    changes = p.get("changes", {"status": p.get("status")})
                    t = c.execute(
                        "SELECT revision FROM todos WHERE todo_id=?", (p["todo_id"],)
                    ).fetchone()
                    self.s._edit(c, p["todo_id"], changes, t[0], True)
                elif kind == "historical_todo":
                    self.s._create_todo(c, p, "mail_ai", "review:" + rid)
                elif kind == "suggest_link":
                    t = c.execute(
                        "SELECT revision FROM todos WHERE todo_id=?", (p["todo_id"],)
                    ).fetchone()
                    self.s._edit(
                        c,
                        p["todo_id"],
                        {k: p[k] for k in ("customer_id", "case_id") if k in p},
                        t[0],
                        True,
                    )
                elif kind == "suggest_relationship":
                    customer = c.execute(
                        "SELECT customer_id FROM customers WHERE name=?",
                        (p["customer_name"],),
                    ).fetchone()
                    cid = customer[0] if customer else uid()
                    if not customer:
                        c.execute(
                            "INSERT INTO customers VALUES (?,?,1)",
                            (cid, p["customer_name"]),
                        )
                    contact = uid()
                    c.execute(
                        "INSERT INTO contacts VALUES (?,?,?,?)",
                        (contact, p["contact_name"], p["contact_address"], cid),
                    )
                    c.execute(
                        "INSERT INTO contact_relations VALUES (?,?,?,?,1)",
                        (uid(), contact, cid, p["relation"]),
                    )
                elif kind == "suggest_case":
                    c.execute(
                        "INSERT INTO cases VALUES (?,?,?,?,?,1)",
                        (
                            uid(),
                            p["title"],
                            p.get("customer_id"),
                            p["case_type"],
                            p.get("stage"),
                        ),
                    )
                elif kind == "confirm_entity":
                    c.execute(
                        "UPDATE entity_confirmations SET confirmed=1 WHERE entity_type=? AND entity_id=?",
                        (p["entity_type"], p["entity_id"]),
                    )
                elif kind == "propose_knowledge":
                    if p["scope"] != "personal":
                        table, key = (
                            ("customers", "customer_id")
                            if p["scope"] == "customer"
                            else ("cases", "case_id")
                        )
                        if (
                            not p.get("subject_id")
                            or not c.execute(
                                "SELECT 1 FROM " + table + " WHERE " + key + "=?",
                                (p["subject_id"],),
                            ).fetchone()
                        ):
                            raise ValueError("unknown scoped knowledge subject")
                    kid = uid()
                    c.execute(
                        "INSERT INTO knowledge_items VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            kid,
                            p["scope"],
                            p.get("subject_id"),
                            p["content"],
                            1,
                            r["evidence_refs"],
                            1,
                            None,
                            now(),
                            now(),
                        ),
                    )
                    c.execute(
                        "INSERT INTO knowledge_versions VALUES (?,?,?,?,?,?)",
                        (uid(), kid, 1, p["content"], 1, now()),
                    )
                else:
                    raise ValueError("请在事项详情确认日期或使用合并操作")
            c.execute(
                "UPDATE review_items SET state=? WHERE review_id=?",
                ("accepted" if accept else "rejected", rid),
            )
            self.s.audit(c, "review_resolved", rid, {"accept": accept})
        return {"state": "accepted" if accept else "rejected"}
