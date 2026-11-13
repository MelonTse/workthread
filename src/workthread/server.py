"""Loopback-only Flask HTTP interface. External draft generation requires explicit user selection."""

import hmac
import secrets
import sqlite3
from uuid import UUID
import tempfile
from pathlib import Path
from urllib.parse import urlparse
import nh3
from flask import Flask, request, jsonify, render_template, session, send_file, url_for
from jsonschema import ValidationError
from werkzeug.wsgi import ClosingIterator
from .core import Conflict, DeadlineError, now, uid, dumps, load
from . import draft_api, draft_tasks, knowledge_tasks, todo_assist
from .ai import Bridge
from .operations import backup, backup_filename, restore, import_legacy, undo_import


def create_app(store, updates=None, mail_tasks=None, instance_id=None):
    from .mail_tasks import MailTasks

    mail_tasks = mail_tasks or MailTasks(store)
    from .updating.controller import Updates
    updates = updates or Updates(None)
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.secret_key = secrets.token_hex(32)
    app.config.update(
        MAX_CONTENT_LENGTH=512 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
    )
    b = Bridge(store)

    @app.before_request
    def guard():
        if updates.stopping:
            return jsonify(error="工作台正在停机更新"), 503
        host = request.host.split(":")[0]
        if host not in ("127.0.0.1", "localhost", "[::1]"):
            return jsonify(error="local requests only"), 403
        if request.method in ("POST", "PATCH", "DELETE", "PUT"):
            origin = request.headers.get("Origin")
            if origin and urlparse(origin).netloc != request.host:
                return jsonify(error="origin rejected"), 403
            if not hmac.compare_digest(
                request.headers.get("X-CSRF-Token", ""),
                session.get("csrf", secrets.token_hex(32)),
            ):
                return jsonify(error="请刷新页面后重试"), 403

    @app.after_request
    def headers(response):
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        return response

    @app.errorhandler(Conflict)
    def conflict(e):
        return jsonify(error=str(e)), 409

    @app.errorhandler(ValueError)
    @app.errorhandler(KeyError)
    @app.errorhandler(ValidationError)
    def invalid(e):
        result = {"error": str(e)[:500]}
        if isinstance(e, DeadlineError):
            result["fields"] = list(e.fields)
        return jsonify(result), 400

    @app.errorhandler(Exception)
    def unexpected(e):
        from werkzeug.exceptions import HTTPException

        if isinstance(e, HTTPException):
            return e
        from .diagnostics import describe_error

        reference = uid()
        detail = describe_error(e)
        app.logger.error("diagnostic %s: %s %s", reference, type(e).__name__, detail)
        return jsonify(error=f"操作失败：{detail}。诊断编号 {reference}", diagnostic_id=reference), 500

    @app.get("/")
    def home():
        from . import __version__

        session["csrf"] = session.get("csrf") or secrets.token_hex(32)
        return render_template("index.html", csrf=session["csrf"], version=__version__)

    @app.get("/api/v1/instance")
    def service_instance():
        return jsonify(instance_id=instance_id)

    @app.get("/api/v1/software-update")
    def update_status():
        return jsonify(updates.status())

    @app.post("/api/v1/software-update/<action>")
    def update_action(action):
        if action not in {"check", "download", "apply"}:
            return jsonify(error="未知更新操作"), 404
        return jsonify(updates.action(action, (request.get_json(silent=True) or {}).get("confirmed") is True))

    @app.get("/api/v1/snapshot")
    def snapshot():
        tables = [
            "todos",
            "customers",
            "contacts",
            "cases",
            "knowledge_items",
            "review_items",
            "drafts",
            "analyses",
            "sync_runs",
        ]
        compact = request.args.get("summary") == "1"
        with store.read_db() as c:
            def rows(sql):
                return [dict(row) for row in c.execute(sql)]

            result = {}
            for table in tables:
                if compact and table == "analyses":
                    result[table] = rows("SELECT summary,advice FROM analyses ORDER BY rowid DESC LIMIT 1")
                elif compact and table == "drafts":
                    result[table] = rows("SELECT draft_id,message_id,subject FROM drafts")
                elif compact and table == "sync_runs":
                    result[table] = rows("SELECT started_at,state FROM sync_runs ORDER BY rowid DESC LIMIT 5")[::-1]
                else:
                    result[table] = rows("SELECT * FROM " + table)
            body = "substr(body_text,1,100) AS preview" if compact else "body_text"
            result["messages"] = rows(
                f"SELECT message_id,subject,date,sender,recipients,in_reply_to,{body} FROM messages "
                "WHERE rowid IN (SELECT rowid FROM messages ORDER BY internal_date DESC,rowid DESC LIMIT 500) "
                "ORDER BY internal_date DESC,rowid DESC"
            )
            result["jobs"] = rows(
                "SELECT job_id,job_type,state,error,created_at,updated_at FROM ai_jobs ORDER BY created_at DESC LIMIT 100"
            )
            result["accounts"] = rows(
                "SELECT account_id,label,host,port,username,folders,enabled FROM mail_accounts WHERE host<>''"
            )
            for key in ("imap_interval_minutes", "timezone", "profile", "ai_schedule"):
                result[key] = load(c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()[0])
            result["todo_ai_history"] = rows("""SELECT j.job_id,j.state,j.error,j.created_at,a.payload
                FROM ai_jobs j LEFT JOIN audit_events a ON a.target_id=j.job_id AND a.kind='todo_assist_saved'
                WHERE j.job_type='todo_assist' ORDER BY j.created_at DESC LIMIT 6""")
            result["knowledge_jobs"] = rows("""WITH latest AS (
                SELECT *,row_number() OVER (PARTITION BY json_extract(input_json,'$.context.fingerprint')
                  ORDER BY created_at DESC,rowid DESC) AS position FROM ai_jobs WHERE job_type='knowledge_assist'
                  AND json_extract(input_json,'$.workspace_epoch')=(SELECT json_extract(value,'$') FROM settings WHERE key='workspace_epoch')
                ) SELECT job_id,state,error,created_at,
                json_extract(input_json,'$.context.material.scope') AS scope,
                json_extract(input_json,'$.context.subject_id') AS subject_id,
                json_extract(input_json,'$.context.material.raw') AS raw,
                json_array_length(result_json,'$.suggestions') AS proposed
                FROM latest WHERE position=1 AND (state IN ('pending','running','failed')
                OR (state='completed' AND json_array_length(result_json,'$.suggestions')=0))
                ORDER BY created_at DESC""")
            ai_config = c.execute("SELECT value FROM settings WHERE key='draft_ai'").fetchone()
            result["draft_ai"] = load(ai_config[0]) if ai_config else draft_api.DEFAULT.copy()
        schedule = result.pop("ai_schedule")
        result["health"] = (
            {"workspace": str(store.root), "ai_schedule": schedule}
            if compact else store.health()
        )
        result["draft_providers"] = {k: v[0] for k, v in draft_api.PROVIDERS.items()}
        return jsonify(result)

    @app.get("/api/v1/system/status")
    def status():
        return jsonify(store.health())

    @app.get("/api/v1/todos")
    def todos():
        return jsonify(
            store.rows(
                "SELECT * FROM todos WHERE merged_into_id IS NULL ORDER BY created_at DESC"
            )
        )

    @app.post("/api/v1/todos")
    def add_todo():
        return jsonify(
            store.create_todo(
                request.get_json(), key=request.headers.get("Idempotency-Key") or uid()
            )
        ), 201

    @app.get("/api/v1/todos/<tid>")
    def todo(tid):
        return jsonify(store.todo(tid))

    @app.patch("/api/v1/todos/<tid>")
    def edit(tid):
        p = request.get_json()
        return jsonify(store.edit_todo(tid, p["changes"], p["expected_revision"]))

    @app.post("/api/v1/todos/<tid>/status")
    def set_status(tid):
        p = request.get_json()
        return jsonify(
            store.edit_todo(tid, {"status": p["status"]}, p["expected_revision"])
        )

    @app.post("/api/v1/todos/<tid>/progress")
    def progress(tid):
        return jsonify(store.progress(tid, request.get_json())), 201

    @app.get("/api/v1/duplicates")
    def duplicates():
        return jsonify(store.duplicates())

    @app.post("/api/v1/merge")
    def merge():
        p = request.get_json()
        return jsonify(store.merge(p["keep"], p["other"], p["versions"]))

    @app.get("/api/v1/mail/search")
    def search():
        return jsonify(store.search(request.args.get("q", "")))

    @app.get("/api/v1/mail")
    def mail_listing():
        from .mail_listing import mail_page

        return jsonify(mail_page(store, request.args))

    @app.get("/api/v1/mail/<mid>")
    def mail_detail(mid):
        with store.read_db() as c:
            message = c.execute(
                "SELECT * FROM messages WHERE message_id=?", (mid,)
            ).fetchone()
            if not message:
                raise ValueError("未知邮件")
            drafts = c.execute(
                "SELECT * FROM drafts WHERE message_id=? ORDER BY created_at DESC, draft_id",
                (mid,),
            ).fetchall()
            feedback = c.execute(
                "SELECT f.* FROM feedback f JOIN drafts d ON f.target_id=d.draft_id "
                "WHERE d.message_id=? ORDER BY f.created_at, f.feedback_id",
                (mid,),
            ).fetchall()
            analyses = c.execute(
                "SELECT * FROM analyses WHERE EXISTS "
                "(SELECT 1 FROM json_each(analyses.message_ids) WHERE value=?) "
                "ORDER BY created_at DESC",
                (mid,),
            ).fetchall()
            draft_jobs = c.execute(
                """SELECT job_id,state,error FROM ai_jobs WHERE job_type='mail_draft'
                   AND json_extract(input_json,'$.context.target_message_id')=?
                   ORDER BY created_at DESC LIMIT 5""",
                (mid,),
            ).fetchall()
        return jsonify(
            message=dict(message),
            draft_jobs=[dict(j) for j in draft_jobs],
            drafts=[dict(d) for d in drafts],
            feedback=[dict(f) for f in feedback],
            analyses=[dict(a) for a in analyses],
        )

    @app.get("/api/v1/mail/<mid>/thread")
    def thread(mid):
        return jsonify(store.thread(mid))

    @app.get("/api/v1/mail/<mid>/html")
    def mail_html(mid):
        m = store.rows("SELECT body_html FROM messages WHERE message_id=?", (mid,))[0]
        safe = nh3.clean(
            m["body_html"],
            tags={
                "p",
                "br",
                "b",
                "strong",
                "i",
                "em",
                "ul",
                "ol",
                "li",
                "blockquote",
                "table",
                "tr",
                "td",
                "th",
            },
            attributes={},
        )
        response = app.make_response(safe)
        response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response

    @app.post("/api/v1/ai/jobs")
    def prepare():
        pending = [
            {"job_id": row["job_id"]}
            for row in store.rows("SELECT job_id, input_json FROM ai_jobs WHERE state='pending' AND job_type NOT IN ('mail_draft','todo_assist','knowledge_assist')")
            if not load(row["input_json"])["context"].get("draft_rewrite")
        ]
        if pending:
            return jsonify({"queued": pending, "existing": True})
        jobs = b.prepare(
            historical=bool(
                (request.get_json(silent=True) or {}).get("historical", False)
            )
        )
        return jsonify(
            {"queued": [{"job_id": j["job_id"]} for j in jobs], "existing": False}
        )

    @app.post("/api/v1/ai/import")
    def ai_import():
        return jsonify(b.import_result(request.get_json()))

    @app.post("/api/v1/ai/consume")
    def consume():
        return jsonify(b.consume())

    @app.post("/api/v1/demo/analyze")
    def demo_analyze():
        if not store.setting("demo_seeded"):
            raise ValueError("模拟结果仅可用于合成演示工作空间")
        from .demo import simulated_result

        jobs = b.prepare()
        return jsonify([b.import_result(simulated_result(j)) for j in jobs])

    @app.post("/api/v1/reviews/<rid>")
    def review(rid):
        return jsonify(b.resolve(rid, request.get_json()["accept"]))

    @app.post("/api/v1/feedback")
    def feedback():
        p = request.get_json()
        if not p.get("content", "").strip():
            raise ValueError("反馈不能为空")
        with store.db() as c:
            c.execute(
                "INSERT INTO feedback VALUES (?,?,?,?)",
                (uid(), p.get("target_id"), p["content"], now()),
            )
        return jsonify(saved=True)

    @app.post("/api/v1/drafts/<did>/feedback")
    def draft_feedback(did):
        content = request.get_json().get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("反馈不能为空")
        with store.db() as c:
            draft = c.execute(
                "SELECT message_id FROM drafts WHERE draft_id=?", (did,)
            ).fetchone()
            if not draft:
                raise ValueError("未知草稿")
            feedback_id = uid()
            c.execute(
                "INSERT INTO feedback VALUES (?,?,?,?)",
                (feedback_id, did, content.strip(), now()),
            )
        return jsonify(
            saved=True,
            feedback_id=feedback_id,
            draft_id=did,
            message_id=draft["message_id"],
        ), 201

    @app.post("/api/v1/draft-ai/settings")
    def configure_draft_ai():
        p = request.get_json()
        mode = p.get("mode")
        if mode == "workbuddy":
            store.set_setting("draft_ai", {**draft_api.settings(store), "mode": mode})
        elif mode == "api":
            provider, model = p.get("provider"), p.get("model")
            draft_api.validate_selection(provider, model)
            secret = p.get("key", "")
            if secret:
                if not isinstance(secret, str) or not secret.strip() or not secret.isascii() or not secret.isprintable() or len(secret) > 2048:
                    raise ValueError("API Key 格式无效")
                draft_api.keyring.set_password("workthread", draft_api.credential_id(store, provider), secret.strip())
            else:
                draft_api.get_key(store, provider)
            store.set_setting("draft_ai", {"mode": mode, "provider": provider, "model": model})
        else:
            raise ValueError("未知草稿模式")
        return jsonify(draft_api.settings(store))

    def selected_ai_mode():
        config = draft_api.settings(store)
        if request.get_json().get("selection") != config:
            raise Conflict("AI 设置已更改，请刷新页面确认服务商")
        return config if config["mode"] == "api" else {"mode": "workbuddy"}

    @app.post("/api/v1/draft-ai/test")
    def test_draft_ai():
        config = selected_ai_mode()
        if config["mode"] != "api":
            raise ValueError("请先保存 API 配置")
        draft_api.generate(config["provider"], config["model"], draft_api.get_key(store, config["provider"]),
                           {"subject": "Synthetic test", "body_text": "Please confirm receipt of this test."})
        return jsonify(ok=True)

    @app.get("/api/v1/todo-ai/scope")
    def todo_ai_scope():
        rows = todo_assist.mail_scope(store, request.args.get("historical") == "1")
        return jsonify(count=len(rows), mails=rows[: todo_assist.BATCH])

    @app.post("/api/v1/todo-ai/inputs")
    def capture_todo():
        p = request.get_json()
        return jsonify(
            input_id=todo_assist.capture(store, p.get("raw"), p.get("token"))
        )

    @app.post("/api/v1/todo-ai/run")
    def run_todo_ai():
        return jsonify(todo_assist.execute(b, request.get_json(), selected_ai_mode()))

    @app.post("/api/v1/todo-ai/reviews/<rid>")
    def resolve_todo_ai(rid):
        return jsonify(todo_assist.resolve(store, rid, request.get_json()))

    @app.post("/api/v1/todo-ai/withdraw/<jid>")
    def withdraw_todo_ai(jid):
        with store.db() as c:
            changed = c.execute(
                "UPDATE ai_jobs SET state='withdrawn',updated_at=? WHERE job_id=? AND job_type='todo_assist' AND state='pending'",
                (now(), jid),
            )
            if not changed.rowcount:
                raise Conflict("待办任务已结束")
            (b.exchange / "inputs" / (jid + ".json")).unlink(missing_ok=True)
        return jsonify(state="withdrawn")

    @app.post("/api/v1/mail/<mid>/draft")
    def generate_draft(mid):
        return jsonify(draft_tasks.execute(b, mid, request.get_json().get("draft_id"), selected_ai_mode()))

    @app.post("/api/v1/draft-jobs/<jid>/withdraw")
    def withdraw_draft(jid):
        with store.db() as db:
            changed = db.execute("""UPDATE ai_jobs SET state='withdrawn',updated_at=? WHERE job_id=?
                                AND job_type='mail_draft' AND state='pending'""", (now(), jid))
            if not changed.rowcount:
                raise Conflict("该任务已结束，请刷新")
            # Use the stored identifier, already constrained by the exact DB match.
            (b.exchange / "inputs" / (jid + ".json")).unlink(missing_ok=True)
        return jsonify(state="withdrawn")

    @app.post("/api/v1/drafts/<did>/queue")
    def queue_draft(did):
        return jsonify(b.queue_draft_rewrite(did))

    @app.post("/api/v1/knowledge-ai/run")
    def organize_knowledge():
        return jsonify(knowledge_tasks.execute(b, request.get_json(), selected_ai_mode()))

    @app.post("/api/v1/knowledge-ai/withdraw/<jid>")
    def withdraw_knowledge(jid):
        with store.db() as db:
            if not db.execute("UPDATE ai_jobs SET state='withdrawn',updated_at=? WHERE job_id=? AND job_type='knowledge_assist' AND state='pending'", (now(), jid)).rowcount:
                raise Conflict("知识任务已结束")
        (b.exchange / "inputs" / (jid + ".json")).unlink(missing_ok=True)
        return jsonify(state="withdrawn")

    @app.post("/api/v1/knowledge")
    def knowledge():
        return jsonify(store.knowledge(request.get_json()))

    @app.patch("/api/v1/knowledge/<kid>")
    def update_knowledge(kid):
        p = request.get_json()
        return jsonify(store.knowledge(p, kid, p["expected_revision"]))

    @app.patch("/api/v1/drafts/<did>")
    def draft(did):
        p = request.get_json()
        with store.db() as c:
            old = c.execute("SELECT * FROM drafts WHERE draft_id=?", (did,)).fetchone()
            if not old or old["revision"] != p["expected_revision"]:
                raise Conflict("草稿已更新")
            c.execute(
                "INSERT INTO draft_versions VALUES (?,?,?,?)",
                (uid(), did, old["body"], now()),
            )
            c.execute(
                "UPDATE drafts SET body=?,subject=?,revision=revision+1,updated_at=? WHERE draft_id=?",
                (p["body"], p.get("subject", old["subject"]), now(), did),
            )
        return jsonify(saved=True)

    @app.post("/api/v1/settings")
    def settings():
        p = request.get_json()
        for k, v in p.items():
            if k not in ("timezone", "ai_schedule", "imap_interval_minutes", "profile"):
                raise ValueError("unknown setting")
            if k == "timezone":
                __import__("zoneinfo").ZoneInfo(v)
            if k == "ai_schedule":
                if v.get("enabled"):
                    raise ValueError(
                        "正式定时任务请在 Windows 验收后于 WorkBuddy 中启用"
                    )
                __import__("datetime").time.fromisoformat(v["time"])
                v["frequency"] = "daily"
            if k == "imap_interval_minutes" and (
                not isinstance(v, int) or not 1 <= v <= 1440
            ):
                raise ValueError("同步周期须为 1–1440 分钟")
            store.set_setting(k, v)
        return jsonify(saved=True)

    @app.post("/api/v1/accounts")
    def account():
        p = request.get_json()
        aid = p.get("account_id", uid())
        credential = "account:" + aid
        if not p["host"] or not p["username"]:
            raise ValueError("host and username required")
        from .mail import Sync

        with Sync(store).exclusive(aid):
            with store.db() as c:
                if c.execute(
                    "SELECT 1 FROM mail_accounts WHERE account_id=? AND host=''", (aid,)
                ).fetchone():
                    raise ValueError("该邮箱配置已移除")
                c.execute(
                    "INSERT INTO mail_accounts VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET label=excluded.label,host=excluded.host,port=excluded.port,username=excluded.username,folders=excluded.folders,enabled=excluded.enabled",
                    (
                        aid,
                        p.get("label", "邮箱"),
                        p["host"],
                        int(p.get("port", 993)),
                        p["username"],
                        credential,
                        dumps(p.get("folders", [])),
                        int(p.get("enabled", False)),
                    ),
                )
            if p.get("password"):
                import keyring

                keyring.set_password("workthread", credential, p["password"])
        return jsonify(account_id=aid, saved=True)

    @app.delete("/api/v1/accounts/<aid>")
    def remove_account(aid):
        import keyring
        from .mail import Sync

        if aid == "demo":
            raise ValueError("合成邮箱不能移除")
        with Sync(store).exclusive(aid), store.db() as c:
            row = c.execute(
                "SELECT credential_ref,host FROM mail_accounts WHERE account_id=?",
                (aid,),
            ).fetchone()
            if row is None:
                raise ValueError("未知邮箱")
            if row["host"]:
                # Keep the identity and address referenced by archived sent mail.
                # A live configuration always has a nonempty IMAP host.
                c.execute(
                    "UPDATE mail_accounts SET host='', credential_ref='', folders='[]', enabled=0 WHERE account_id=?",
                    (aid,),
                )
                c.execute("DELETE FROM settings WHERE key=?", ("mail-sync:" + aid,))
                if (
                    keyring.get_password("workthread", row["credential_ref"])
                    is not None
                ):
                    keyring.delete_password("workthread", row["credential_ref"])
        return jsonify(removed=True)

    @app.post("/api/v1/accounts/<aid>/enabled")
    def account_enabled(aid):
        if aid == "demo":
            raise ValueError("合成邮箱只支持手动模拟同步")
        enabled = request.get_json()["enabled"]
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        with store.db() as c:
            if not c.execute(
                "SELECT 1 FROM mail_accounts WHERE account_id=? AND host<>''", (aid,)
            ).fetchone():
                raise ValueError("unknown account")
            c.execute(
                "UPDATE mail_accounts SET enabled=? WHERE account_id=?",
                (int(enabled), aid),
            )
        return jsonify(enabled=enabled)

    @app.get("/api/v1/accounts/sync-status")
    def mail_sync_status():
        from .mail import Sync

        sync = Sync(store)
        return jsonify({a["account_id"]: sync.status(a["account_id"])
                        for a in store.rows("SELECT account_id FROM mail_accounts WHERE host<>''")})

    @app.post("/api/v1/accounts/<aid>/folders")
    def account_folders(aid):
        from .mail import Sync

        payload = request.get_json()
        if not isinstance(payload, dict) or set(payload) not in (set(), {"sent"}):
            raise ValueError("无效的文件夹设置")
        if "sent" in payload and payload["sent"] is not None and not isinstance(payload["sent"], str):
            raise ValueError("无效的文件夹名称")
        if aid == "demo":
            raise ValueError("合成邮箱使用固定的示例文件夹")
        return jsonify(Sync(store).folder_settings(aid, payload or None))

    @app.post("/api/v1/accounts/<aid>/sync-tasks")
    def start_mail_task(aid):
        from .mail import ACTIVE_SYNC_STATES

        payload = request.get_json() if request.is_json else {}
        if not isinstance(payload, dict):
            raise ValueError("拉取请求格式不正确")
        request_id = payload.get("request_id")
        if request_id is not None:
            if not isinstance(request_id, str) or len(request_id) != 36:
                raise ValueError("拉取请求编号格式不正确")
            request_id = str(UUID(request_id))
        task = mail_tasks.start(aid, request_id=request_id)
        status = 202 if task["state"] in ACTIVE_SYNC_STATES else 200
        return jsonify(task), status, {"Location": url_for("get_mail_task", aid=aid, task_id=task["task_id"])}

    @app.get("/api/v1/accounts/<aid>/sync-tasks/<task_id>")
    def get_mail_task(aid, task_id):
        task = mail_tasks.get(aid, task_id)
        return jsonify(task) if task else (jsonify(error="未找到拉取任务"), 404)

    @app.post("/api/v1/accounts/<aid>/sync")
    def sync(aid):
        from .mail import Sync, sqlite_sync_error

        factory = None
        if aid == "demo":
            from .demo import FakeIMAP

            factory = lambda _: FakeIMAP()
        try:
            return jsonify(Sync(store, factory, mail_tasks.stop).run(aid))
        except sqlite3.DatabaseError as exc:
            return jsonify(error=sqlite_sync_error(exc)), 500

    @app.post("/api/v1/backup")
    def download_backup():
        p = request.get_json()
        directory = tempfile.TemporaryDirectory(prefix="workthread-download-")
        file = Path(directory.name) / backup_filename(p["scope"])
        try:
            backup(store, file, p["scope"])
            response = send_file(file, as_attachment=True, download_name=file.name, mimetype="application/zip")
        except BaseException:
            directory.cleanup()
            raise
        # send_file uses direct_passthrough: retain cleanup on the WSGI iterator,
        # which closes the open file before removing its directory on Windows.
        response.response = ClosingIterator(response.response, directory.cleanup)
        return response

    @app.post("/api/v1/restore")
    def upload_restore():
        f = request.files["file"]
        with tempfile.TemporaryDirectory(prefix="workthread-upload-") as directory:
            path = Path(directory) / "input.zip"
            f.save(path)
            result = restore(
                store,
                path,
                request.form.get("apply") == "true",
            )
        return jsonify(result)

    @app.post("/api/v1/legacy/import")
    def legacy():
        p = request.get_json()
        return jsonify(import_legacy(store, p["document"], p.get("apply", False)))

    @app.post("/api/v1/legacy/<batch>/undo")
    def legacy_undo(batch):
        return jsonify(undo_import(store, batch))

    return app
