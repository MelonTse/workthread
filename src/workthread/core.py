"""SQLite domain operations. All external writes pass through this module."""

from __future__ import annotations
import contextlib
import datetime as dt
import difflib
import hashlib
import json
import sqlite3
from filelock import FileLock
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

VERSION = 2
STATUSES = {"inbox", "open", "in_progress", "waiting", "done", "cancelled"}
PRIORITIES = {"low", "normal", "high", "urgent"}


def uid():
    return str(uuid.uuid4())


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def load(value, default=None):
    return json.loads(value) if value else default


class Conflict(ValueError):
    pass


class DeadlineError(ValueError):
    fields = ("due_date", "no_due_date")


def validate_deadline(due_date, no_due_date):
    """The same final-state rule applies to every To Do writer."""
    if type(no_due_date) not in (bool, int) or no_due_date not in (0, 1):
        raise DeadlineError("no_due_date：无限期必须是明确的布尔选择")
    if due_date is not None:
        try:
            if not isinstance(due_date, str) or dt.date.fromisoformat(due_date).isoformat() != due_date:
                raise ValueError
        except ValueError:
            raise DeadlineError("due_date：截止日期必须是有效的 YYYY-MM-DD 日期或 null") from None
    if due_date is not None and no_due_date:
        raise DeadlineError("due_date / no_due_date：截止日期与无限期不能同时设置")
    if due_date is None and not no_due_date:
        raise DeadlineError("due_date / no_due_date：请填写截止日期或明确选择无限期")


DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS todos(
 todo_id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL, raw_input TEXT NOT NULL,
 input_at TEXT NOT NULL, input_timezone TEXT NOT NULL, source_type TEXT NOT NULL, source_ref TEXT NOT NULL,
 customer_id TEXT, case_id TEXT, owner TEXT NOT NULL, priority TEXT NOT NULL, due_date TEXT, no_due_date INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL, completion_criteria TEXT NOT NULL, completion_policy TEXT NOT NULL,
 status_source TEXT NOT NULL, normalization_status TEXT NOT NULL, needs_review INTEGER NOT NULL DEFAULT 0,
 protected_fields TEXT NOT NULL DEFAULT '[]', revision INTEGER NOT NULL DEFAULT 1,
 merged_into_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS todo_sources(source_id TEXT PRIMARY KEY, todo_id TEXT NOT NULL REFERENCES todos,
 source_type TEXT NOT NULL, source_ref TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS progress_logs(log_id TEXT PRIMARY KEY, todo_id TEXT NOT NULL REFERENCES todos,
 origin_todo_id TEXT NOT NULL, occurred_at TEXT, recorded_at TEXT NOT NULL, content TEXT NOT NULL,
 source_type TEXT NOT NULL, source_ref TEXT, evidence_refs TEXT NOT NULL, operation_id TEXT UNIQUE,
 corrects_log_id TEXT REFERENCES progress_logs);
CREATE TABLE IF NOT EXISTS status_events(event_id TEXT PRIMARY KEY, todo_id TEXT NOT NULL REFERENCES todos,
 old_status TEXT, new_status TEXT NOT NULL, source TEXT NOT NULL, reason TEXT, evidence_refs TEXT,
 recorded_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS customers(customer_id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS contacts(contact_id TEXT PRIMARY KEY, name TEXT, address TEXT, customer_id TEXT REFERENCES customers);
CREATE TABLE IF NOT EXISTS contact_relations(relation_id TEXT PRIMARY KEY, from_id TEXT, to_id TEXT, relation TEXT, confirmed INTEGER);
CREATE TABLE IF NOT EXISTS cases(case_id TEXT PRIMARY KEY, title TEXT NOT NULL, customer_id TEXT REFERENCES customers,
 case_type TEXT NOT NULL, stage TEXT, revision INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS entity_confirmations(confirmation_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL, confirmed INTEGER NOT NULL, UNIQUE(entity_type,entity_id));
CREATE TABLE IF NOT EXISTS categories(category_id TEXT PRIMARY KEY, parent_id TEXT REFERENCES categories, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_items(knowledge_id TEXT PRIMARY KEY, scope TEXT NOT NULL, subject_id TEXT,
 content TEXT NOT NULL, confirmed INTEGER NOT NULL, evidence_refs TEXT NOT NULL, revision INTEGER NOT NULL,
 valid_until TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_versions(version_id TEXT PRIMARY KEY, knowledge_id TEXT NOT NULL REFERENCES knowledge_items,
 revision INTEGER NOT NULL, content TEXT NOT NULL, confirmed INTEGER NOT NULL, recorded_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feedback(feedback_id TEXT PRIMARY KEY, target_id TEXT, content TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS review_items(review_id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
 evidence_refs TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS drafts(draft_id TEXT PRIMARY KEY, message_id TEXT, todo_id TEXT, subject TEXT NOT NULL,
 body TEXT NOT NULL, revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS draft_versions(version_id TEXT PRIMARY KEY, draft_id TEXT, body TEXT, recorded_at TEXT);
CREATE TABLE IF NOT EXISTS mail_accounts(account_id TEXT PRIMARY KEY, label TEXT, host TEXT NOT NULL, port INTEGER NOT NULL,
 username TEXT NOT NULL, credential_ref TEXT NOT NULL, folders TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS mail_folders(folder_id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES mail_accounts,
 name TEXT NOT NULL, direction TEXT NOT NULL, uidvalidity INTEGER NOT NULL, high_uid INTEGER DEFAULT 0,
 UNIQUE(account_id,name));
CREATE TABLE IF NOT EXISTS messages(message_id TEXT PRIMARY KEY, rfc_message_id TEXT, fingerprint TEXT NOT NULL UNIQUE,
 subject TEXT NOT NULL, date TEXT, internal_date TEXT, headers TEXT NOT NULL, sender TEXT NOT NULL,
 recipients TEXT NOT NULL, in_reply_to TEXT, refs TEXT NOT NULL, month TEXT NOT NULL,
 body_text TEXT NOT NULL, body_html TEXT NOT NULL, metadata TEXT NOT NULL, archived_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mail_occurrences(occurrence_id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages,
 account_id TEXT NOT NULL, folder_id TEXT NOT NULL, uidvalidity INTEGER NOT NULL, imap_uid INTEGER NOT NULL,
 flags TEXT NOT NULL, UNIQUE(account_id,folder_id,uidvalidity,imap_uid));
CREATE TABLE IF NOT EXISTS archive_commits(tx_id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_runs(run_id TEXT PRIMARY KEY, account_id TEXT, started_at TEXT, finished_at TEXT, state TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS sync_failures(folder_id TEXT, uidvalidity INTEGER, imap_uid INTEGER, error TEXT,
 PRIMARY KEY(folder_id,uidvalidity,imap_uid));
CREATE TABLE IF NOT EXISTS ai_jobs(job_id TEXT PRIMARY KEY, job_type TEXT NOT NULL, state TEXT NOT NULL,
 input_json TEXT NOT NULL, result_json TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_operations(operation_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES ai_jobs, payload_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analyses(analysis_id TEXT PRIMARY KEY, message_ids TEXT NOT NULL, work_type TEXT,
 stage TEXT, summary TEXT NOT NULL, advice TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events(event_id TEXT PRIMARY KEY, kind TEXT NOT NULL, target_id TEXT,
 payload TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS imports(batch_id TEXT PRIMARY KEY, payload_hash TEXT UNIQUE, created_at TEXT NOT NULL, mapping TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS import_records(batch_id TEXT REFERENCES imports, table_name TEXT, record_id TEXT, PRIMARY KEY(batch_id,table_name,record_id));
CREATE INDEX IF NOT EXISTS todo_status_idx ON todos(status,updated_at);
CREATE INDEX IF NOT EXISTS progress_todo_idx ON progress_logs(todo_id,recorded_at);
"""


class Store:
    def __init__(self, workspace):
        self.root = Path(workspace).expanduser().resolve()
        self.lock = FileLock(
            str(self.root / ".workspace.lock"), timeout=30, is_singleton=True
        )
        self.archive_seen = {}
        self.data = self.root / "data"
        self.data.mkdir(parents=True, exist_ok=True)
        self.path = self.data / "workthread.sqlite3"
        for p in ("meta", "body"):
            (self.data / p).mkdir(exist_ok=True)
        for p in ("inputs", "outputs", "receipts", "quarantine", "intake"):
            (self.root / "agent-workspace" / "exchange" / p).mkdir(
                parents=True, exist_ok=True
            )
        with self.db() as c:
            existing = c.execute(
                "SELECT name FROM sqlite_master WHERE name='schema_migrations'"
            ).fetchone()
            if existing:
                current = c.execute(
                    "SELECT max(version) FROM schema_migrations"
                ).fetchone()[0]
                if current and current > VERSION:
                    raise ValueError("数据库版本高于程序版本；请使用匹配版本或恢复备份")
            c.executescript(DDL)
            if "no_due_date" not in {
                r[1] for r in c.execute("PRAGMA table_info(todos)")
            }:
                c.execute(
                    "ALTER TABLE todos ADD COLUMN no_due_date INTEGER NOT NULL DEFAULT 0"
                )
            c.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(message_id UNINDEXED, subject, body_text, tokenize='trigram')"
            )
            c.execute(
                "INSERT OR IGNORE INTO schema_migrations VALUES (?,?)", (VERSION, now())
            )
            defaults = {
                "workspace_id": uid(),
                "workspace_epoch": uid(),
                "timezone": "Asia/Shanghai",
                "ai_schedule": {
                    "enabled": False,
                    "frequency": "daily",
                    "time": "09:00",
                },
                "imap_interval_minutes": 15,
                "profile": {"owner": "local-user", "email_style": ""},
            }
            for k, v in defaults.items():
                c.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (k, dumps(v)))

    @contextlib.contextmanager
    def db(self):
        with self.lock:
            c = sqlite3.connect(self.path, timeout=20)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=FULL")
            try:
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise
            finally:
                c.close()

    def rows(self, sql, args=()):
        with self.db() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def setting(self, key):
        r = self.rows("SELECT value FROM settings WHERE key=?", (key,))
        return load(r[0]["value"]) if r else None

    def set_setting(self, key, value):
        with self.db() as c:
            c.execute(
                "INSERT OR REPLACE INTO settings VALUES (?,?)", (key, dumps(value))
            )

    def audit(self, c, kind, target, payload):
        c.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?)",
            (uid(), kind, target, dumps(payload), now()),
        )

    def _review(self, c, kind, payload, evidence=()):
        rid = uid()
        c.execute(
            "INSERT INTO review_items VALUES (?,?,?,?,?,?)",
            (rid, kind, dumps(payload), dumps(evidence), "pending", now()),
        )
        return rid

    def relative_date(self, raw, input_at, timezone):
        anchor = dt.datetime.fromisoformat(input_at)
        if anchor.tzinfo is None:
            raise ValueError("input_at must include timezone")
        day = anchor.astimezone(ZoneInfo(timezone)).date()
        import re

        hits = re.findall(
            r"day after tomorrow|tomorrow|today|后天|明天|今天", raw.lower()
        )
        if len(set(hits)) > 1:
            return None, True
        for words, delta in [
            (("后天", "day after tomorrow"), 2),
            (("明天", "tomorrow"), 1),
            (("今天", "today"), 0),
        ]:
            if any(w in raw.lower() for w in words):
                return (day + dt.timedelta(days=delta)).isoformat(), False
        ambiguous = any(
            w in raw.lower()
            for w in (
                "下周",
                "周末",
                "月底",
                "尽快",
                "next week",
                "soon",
                "next monday",
            )
        )
        return None, ambiguous

    def _create_todo(self, c, p, source, key):
        existing = c.execute(
            "SELECT todo_id FROM todo_sources WHERE idempotency_key=?", (key,)
        ).fetchone()
        if existing:
            return existing[0]
        raw = str(p.get("raw_input", p.get("description", p.get("title", "")))).strip()
        if not raw or len(raw) > 100000:
            raise ValueError("请输入 1–100000 字符的工作内容")
        t = now()
        tid = p.get("todo_id") or uid()
        tz = p.get("input_timezone", self.setting("timezone"))
        at = p.get("input_at", t)
        explicit_deadline = bool({"due_date", "no_due_date"}.intersection(p))
        due, ambiguous = self.relative_date(raw, at, tz)
        if source == "html" and explicit_deadline:
            due, ambiguous = None, False
        if due and p.get("due_date") and due != p["due_date"]:
            raise DeadlineError("due_date: relative date disagrees with original input time")
        priority = p.get("priority", "normal")
        status = p.get("status", "inbox")
        if priority not in PRIORITIES or status not in STATUSES:
            raise ValueError("invalid priority or status")
        for field, table, col in [
            ("customer_id", "customers", "customer_id"),
            ("case_id", "cases", "case_id"),
        ]:
            if (
                p.get(field)
                and not c.execute(
                    f"SELECT 1 FROM {table} WHERE {col}=?", (p[field],)
                ).fetchone()
            ):
                raise ValueError("unknown " + field)
        deadline_date = p.get("due_date") if explicit_deadline else due
        indefinite = p.get("no_due_date", False)
        validate_deadline(deadline_date, indefinite)
        values = {
            "todo_id": tid,
            "title": p.get("title") or raw.splitlines()[0][:100],
            "description": p.get("description", raw),
            "raw_input": raw,
            "input_at": at,
            "input_timezone": tz,
            "source_type": source,
            "source_ref": p.get("source_ref", key),
            "customer_id": p.get("customer_id"),
            "case_id": p.get("case_id"),
            "owner": p.get("owner", "local-user"),
            "priority": priority,
            "due_date": deadline_date,
            "no_due_date": int(indefinite),
            "status": status,
            "completion_criteria": p.get("completion_criteria", "由用户确认工作完成"),
            "completion_policy": dumps(p.get("completion_policy", {"type": "manual"})),
            "status_source": "ai" if source == "mail_ai" else "human",
            "normalization_status": "pending",
            "needs_review": int(ambiguous),
            "protected_fields": dumps(["due_date", "no_due_date"])
            if source != "mail_ai" and (p.get("due_date") or p.get("no_due_date"))
            else "[]",
            "revision": 1,
            "merged_into_id": None,
            "created_at": t,
            "updated_at": t,
        }
        c.execute(
            f"INSERT INTO todos ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
            tuple(values.values()),
        )
        c.execute(
            "INSERT INTO todo_sources VALUES (?,?,?,?,?)",
            (uid(), tid, source, values["source_ref"], key),
        )
        c.execute(
            "INSERT INTO status_events VALUES (?,?,?,?,?,?,?,?)",
            (uid(), tid, None, status, values["status_source"], "created", "[]", t),
        )
        self.audit(c, "todo_created", tid, {"source": source})
        if ambiguous:
            self._review(c, "ambiguous_date", {"todo_id": tid, "raw_input": raw})
        return tid

    def create_todo(self, p, source="html", key=None):
        if source not in ("html", "workbuddy", "mail_ai"):
            raise ValueError("invalid source")
        with self.db() as c:
            tid = self._create_todo(c, p, source, key or uid())
        return self.todo(tid)

    def todo(self, tid):
        rows = self.rows("SELECT * FROM todos WHERE todo_id=?", (tid,))
        if not rows:
            raise ValueError("unknown todo")
        t = rows[0]
        t["logs"] = self.rows(
            "SELECT * FROM progress_logs WHERE todo_id=? ORDER BY recorded_at", (tid,)
        )
        t["status_events"] = self.rows(
            "SELECT * FROM status_events WHERE todo_id=? ORDER BY recorded_at", (tid,)
        )
        t["sources"] = self.rows("SELECT * FROM todo_sources WHERE todo_id=?", (tid,))
        return t

    def _edit(self, c, tid, p, revision, human=True, reason="edited", evidence=()):
        row = c.execute("SELECT * FROM todos WHERE todo_id=?", (tid,)).fetchone()
        if not row:
            raise ValueError("unknown todo")
        if row["revision"] != revision:
            raise Conflict("事项已更新，请刷新后重试")
        allowed = {
            "title",
            "description",
            "customer_id",
            "case_id",
            "owner",
            "priority",
            "due_date",
            "no_due_date",
            "completion_criteria",
            "completion_policy",
            "status",
        }
        if not p or set(p) - allowed:
            raise ValueError("invalid editable fields")
        if "status" in p and p["status"] not in STATUSES:
            raise ValueError("invalid status")
        if "priority" in p and p["priority"] not in PRIORITIES:
            raise ValueError("invalid priority")
        for field, table in [("customer_id", "customers"), ("case_id", "cases")]:
            if (
                p.get(field)
                and not c.execute(
                    f"SELECT 1 FROM {table} WHERE {field}=?", (p[field],)
                ).fetchone()
            ):
                raise ValueError("unknown " + field)
        if "title" in p and not p["title"].strip():
            raise ValueError("title cannot be empty")
        protected = set(load(row["protected_fields"], []))
        if not human and protected.intersection(p):
            self._review(c, "protected_change", {"todo_id": tid, "changes": p})
            return False
        deadline_date = p.get("due_date", row["due_date"])
        indefinite = p.get("no_due_date", row["no_due_date"])
        validate_deadline(deadline_date, indefinite)
        if human:
            protected.update(p)
            if {"due_date", "no_due_date"}.intersection(p):
                protected.update({"due_date", "no_due_date"})
        changes = dict(p)
        if "completion_policy" in changes:
            changes["completion_policy"] = dumps(changes["completion_policy"])
        changes.update(
            updated_at=now(),
            revision=revision + 1,
            protected_fields=dumps(sorted(protected)),
        )
        if "status" in p:
            changes["status_source"] = "human" if human else "ai"
            if p["status"] != row["status"]:
                c.execute(
                    "INSERT INTO status_events VALUES (?,?,?,?,?,?,?,?)",
                    (
                        uid(),
                        tid,
                        row["status"],
                        p["status"],
                        changes["status_source"],
                        reason,
                        dumps(evidence),
                        now(),
                    ),
                )
        c.execute(
            "UPDATE todos SET "
            + ",".join(k + "=?" for k in changes)
            + " WHERE todo_id=?",
            (*changes.values(), tid),
        )
        self.audit(c, "todo_edited", tid, {"changes": p, "human": human})
        return True

    def edit_todo(self, tid, p, revision):
        with self.db() as c:
            self._edit(c, tid, p, revision)
        return self.todo(tid)

    def _progress(self, c, tid, p, source="human", op=None):
        if not c.execute("SELECT 1 FROM todos WHERE todo_id=?", (tid,)).fetchone():
            raise ValueError("unknown todo")
        content = p.get("content", "").strip()
        if not content:
            raise ValueError("进展内容不能为空")
        occurred_at = p.get("occurred_at", now() if source == "human" else None)
        if occurred_at:
            event = dt.datetime.fromisoformat(occurred_at)
            if event.tzinfo is None:
                raise ValueError("occurred_at must include timezone")
        if (
            p.get("corrects_log_id")
            and not c.execute(
                "SELECT 1 FROM progress_logs WHERE log_id=? AND todo_id=?",
                (p["corrects_log_id"], tid),
            ).fetchone()
        ):
            raise ValueError("unknown correction target")
        lid = uid()
        c.execute(
            "INSERT INTO progress_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                lid,
                tid,
                tid,
                occurred_at,
                now(),
                content,
                source,
                p.get("source_ref"),
                dumps(p.get("evidence_refs", [])),
                op,
                p.get("corrects_log_id"),
            ),
        )
        if source == "ai":
            for evidence in p.get("evidence_refs", []):
                mid = evidence["message_id"]
                c.execute(
                    "INSERT OR IGNORE INTO todo_sources VALUES (?,?,?,?,?)",
                    (uid(), tid, "mail_evidence", mid, "evidence:" + tid + ":" + mid),
                )
        self.audit(c, "progress_appended", tid, {"log_id": lid})
        return lid

    def progress(self, tid, p):
        with self.db() as c:
            lid = self._progress(c, tid, p)
        return {"log_id": lid}

    def duplicates(self):
        todos = self.rows(
            "SELECT todo_id,title,source_ref FROM todos WHERE merged_into_id IS NULL AND status NOT IN ('done','cancelled')"
        )
        return [
            {"left": a, "right": b, "score": round(score, 2)}
            for i, a in enumerate(todos)
            for b in todos[i + 1 :]
            if (score := difflib.SequenceMatcher(None, a["title"], b["title"]).ratio())
            > 0.7
        ]

    def merge(self, keep, other, versions):
        if keep == other:
            raise ValueError("cannot merge itself")
        with self.db() as c:
            for tid in (keep, other):
                row = c.execute(
                    "SELECT revision,merged_into_id FROM todos WHERE todo_id=?", (tid,)
                ).fetchone()
                if not row or row["revision"] != versions[tid] or row["merged_into_id"]:
                    raise Conflict("merge version conflict")
            c.execute(
                "UPDATE progress_logs SET todo_id=? WHERE todo_id=?", (keep, other)
            )
            c.execute(
                "UPDATE todo_sources SET todo_id=? WHERE todo_id=?", (keep, other)
            )
            c.execute(
                "UPDATE todos SET merged_into_id=?,revision=revision+1,updated_at=? WHERE todo_id=?",
                (keep, now(), other),
            )
            c.execute(
                "UPDATE todos SET revision=revision+1,updated_at=? WHERE todo_id=?",
                (now(), keep),
            )
            self.audit(c, "todo_merged", keep, {"other": other})
        return self.todo(keep)

    def knowledge(self, p, kid=None, revision=None):
        if p["scope"] not in ("personal", "customer", "case"):
            raise ValueError("invalid knowledge scope")
        if p["scope"] != "personal" and not p.get("subject_id"):
            raise ValueError("subject required")
        with self.db() as c:
            if not isinstance(p["content"], str) or not p["content"].strip():
                raise ValueError("知识内容不能为空")
            if p["scope"] != "personal":
                table, key = (
                    ("customers", "customer_id")
                    if p["scope"] == "customer"
                    else ("cases", "case_id")
                )
                if not c.execute(
                    "SELECT 1 FROM " + table + " WHERE " + key + "=?",
                    (p["subject_id"],),
                ).fetchone():
                    raise ValueError("未知知识对象")
            if kid:
                old = c.execute(
                    "SELECT * FROM knowledge_items WHERE knowledge_id=?", (kid,)
                ).fetchone()
                if not old or old["revision"] != revision:
                    raise Conflict("knowledge version conflict")
                rev = revision + 1
                c.execute(
                    "UPDATE knowledge_items SET content=?,confirmed=?,revision=?,updated_at=? WHERE knowledge_id=?",
                    (p["content"], int(p.get("confirmed", True)), rev, now(), kid),
                )
            else:
                kid = uid()
                rev = 1
                c.execute(
                    "INSERT INTO knowledge_items VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        kid,
                        p["scope"],
                        p.get("subject_id"),
                        p["content"],
                        int(p.get("confirmed", True)),
                        dumps(p.get("evidence_refs", [])),
                        rev,
                        p.get("valid_until"),
                        now(),
                        now(),
                    ),
                )
            c.execute(
                "INSERT INTO knowledge_versions VALUES (?,?,?,?,?,?)",
                (uid(), kid, rev, p["content"], int(p.get("confirmed", True)), now()),
            )
            self.audit(c, "knowledge_saved", kid, p)
        return {"knowledge_id": kid, "revision": rev}

    def search(self, q):
        if len(q) < 3:
            return self.rows(
                "SELECT message_id,subject,body_text,date FROM messages WHERE subject LIKE ? ESCAPE '\\' OR body_text LIKE ? ESCAPE '\\' LIMIT 100",
                tuple(
                    "%"
                    + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    + "%"
                    for _ in range(2)
                ),
            )
        return self.rows(
            "SELECT m.message_id,m.subject,m.body_text,m.date FROM message_fts f JOIN messages m ON m.message_id=f.message_id WHERE message_fts MATCH ? LIMIT 100",
            ('"' + q.replace('"', '""') + '"',),
        )

    def thread(self, mid):
        allmail = self.rows("SELECT * FROM messages")
        byid = {m["message_id"]: m for m in allmail}
        if mid not in byid:
            raise ValueError("unknown message")
        picked = {mid}
        changed = True
        while changed:
            anchors = set()
            for k in picked:
                m = byid[k]
                anchors.update(load(m["refs"], []))
                anchors.update(x for x in (m["rfc_message_id"], m["in_reply_to"]) if x)
            found = {
                m["message_id"]
                for m in allmail
                if anchors.intersection(
                    load(m["refs"], []) + [m["rfc_message_id"], m["in_reply_to"]]
                )
            }
            changed = bool(found - picked)
            picked.update(found)
        return sorted([byid[k] for k in picked], key=lambda m: m["date"] or "")

    def health(self):
        with self.db() as c:
            integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
            foreign = list(c.execute("PRAGMA foreign_key_check"))
        import os, shutil, sys

        space_ok = shutil.disk_usage(self.root).free > 100 * 1024 * 1024
        return {
            "version": "1.0.0rc2",
            "python": sys.version.split()[0],
            "schema_version": VERSION,
            "disk_space_ok": space_ok,
            "writable": os.access(self.data, os.W_OK),
            "database": integrity,
            "foreign_keys_ok": not foreign,
            "workspace": str(self.root),
            "ai_schedule": self.setting("ai_schedule"),
            "validation": {
                "windows": "pending",
                "real_imap": "pending",
                "workbuddy_real": "pending",
            },
            "ok": integrity == "ok"
            and not foreign
            and space_ok
            and os.access(self.data, os.W_OK),
        }
