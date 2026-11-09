"""Loopback-only Flask HTTP interface. Models are invoked solely by WorkBuddy."""

import hmac
import secrets
import tempfile
from pathlib import Path
from urllib.parse import urlparse
import nh3
from flask import Flask, request, jsonify, render_template, session, send_file
from jsonschema import ValidationError
from werkzeug.wsgi import ClosingIterator
from .core import Conflict, DeadlineError, now, uid, dumps, load
from .ai import Bridge
from .operations import backup, backup_filename, restore, import_legacy, undo_import


def create_app(store, updates=None):
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
        app.logger.error("operation failed: %s", type(e).__name__)
        return jsonify(error="操作失败：" + type(e).__name__ + "；原数据已保留"), 500

    @app.get("/")
    def home():
        from . import __version__

        session["csrf"] = session.get("csrf") or secrets.token_hex(32)
        return render_template("index.html", csrf=session["csrf"], version=__version__)

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
        result = {table: store.rows("SELECT * FROM " + table) for table in tables}
        result["messages"] = store.rows(
            "SELECT message_id,subject,date,sender,recipients,in_reply_to,body_text FROM messages ORDER BY internal_date DESC LIMIT 500"
        )
        result["jobs"] = store.rows(
            "SELECT job_id,job_type,state,error,created_at,updated_at FROM ai_jobs ORDER BY created_at DESC LIMIT 100"
        )
        result["accounts"] = store.rows(
            "SELECT account_id,label,host,port,username,folders,enabled FROM mail_accounts"
        )
        result["health"] = store.health()
        result["imap_interval_minutes"] = store.setting("imap_interval_minutes")
        result["timezone"] = store.setting("timezone")
        result["profile"] = store.setting("profile")
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

    @app.get("/api/v1/mail/<mid>")
    def mail_detail(mid):
        with store.db() as c:
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
        return jsonify(
            message=dict(message),
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
            for row in store.rows("SELECT job_id, input_json FROM ai_jobs WHERE state='pending'")
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

    @app.post("/api/v1/drafts/<did>/queue")
    def queue_draft(did):
        return jsonify(b.queue_draft_rewrite(did))

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
        with store.db() as c:
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

    @app.post("/api/v1/accounts/<aid>/enabled")
    def account_enabled(aid):
        if aid == "demo":
            raise ValueError("合成邮箱只支持手动模拟同步")
        enabled = request.get_json()["enabled"]
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        with store.db() as c:
            if not c.execute(
                "SELECT 1 FROM mail_accounts WHERE account_id=?", (aid,)
            ).fetchone():
                raise ValueError("unknown account")
            c.execute(
                "UPDATE mail_accounts SET enabled=? WHERE account_id=?",
                (int(enabled), aid),
            )
        return jsonify(enabled=enabled)

    @app.post("/api/v1/accounts/<aid>/sync")
    def sync(aid):
        from .mail import Sync

        if aid == "demo":
            from .demo import FakeIMAP

            return jsonify(Sync(store, lambda a: FakeIMAP()).run(aid))
        return jsonify(Sync(store).run(aid))

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
