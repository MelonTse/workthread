import argparse
import json
import threading
import time
import webbrowser
from pathlib import Path
from .core import Store, dumps
from .ai import Bridge
from .deployment import install_templates


def worker(store, stop):
    from .mail import Sync

    last = 0
    while not stop.wait(3):
        try:
            Bridge(store).consume()
            interval = store.setting("imap_interval_minutes") * 60
            if time.monotonic() - last >= interval:
                last = time.monotonic()
                for a in store.rows(
                    "SELECT account_id FROM mail_accounts WHERE enabled=1"
                ):
                    try:
                        Sync(store).run(a["account_id"])
                    except Exception as e:
                        with store.db() as c:
                            store.audit(
                                c,
                                "sync_error",
                                a["account_id"],
                                {"error": type(e).__name__},
                            )
        except Exception as e:
            with store.db() as c:
                store.audit(c, "worker_error", None, {"error": type(e).__name__})


def main(argv=None):
    import sys

    default = (
        Path(sys.executable).resolve().parent.parent / "workspace"
        if getattr(sys, "frozen", False)
        else Path.home() / "WorkThread" / "workspace"
    )
    p = argparse.ArgumentParser(prog="workthread")
    p.add_argument("--workspace", type=Path, default=default)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("init", "doctor", "ai-prepare", "ai-consume", "reindex"):
        sub.add_parser(name)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--demo", action="store_true")
    serve.add_argument("--open", action="store_true")
    demo = sub.add_parser("demo")
    demo.add_argument("--port", type=int, default=8765)
    demo.add_argument("--open", action="store_true")
    imp = sub.add_parser("ai-import")
    imp.add_argument("file", type=Path)
    sim = sub.add_parser("simulate")
    sim.add_argument("--job-id")
    intake = sub.add_parser("intake")
    intake.add_argument("file", type=Path)
    bp = sub.add_parser("backup")
    bp.add_argument("output", type=Path)
    bp.add_argument("--scope", choices=["full", "todos"], default="full")
    rp = sub.add_parser("restore")
    rp.add_argument("file", type=Path)
    rp.add_argument("--apply", action="store_true")
    legacy = sub.add_parser("legacy-import")
    legacy.add_argument("file", type=Path)
    legacy.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    store = Store(a.workspace)
    install_templates(store)
    from .mail import Archive

    Archive(store).recover()
    bridge = Bridge(store)
    bridge.recover()
    if a.command in ("serve", "demo"):
        if a.command == "demo" or a.demo:
            from .demo import seed

            seed(store)
        from .server import create_app
        from waitress import serve

        stop = threading.Event()
        t = threading.Thread(target=worker, args=(store, stop), daemon=True)
        t.start()
        url = f"http://127.0.0.1:{a.port}"
        print("WorkThread " + url, flush=True)
        if a.open:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        try:
            serve(create_app(store), host="127.0.0.1", port=a.port, threads=6)
        finally:
            stop.set()
            t.join(timeout=35)
        return
    if a.command == "doctor":
        result = store.health()
    elif a.command == "init":
        result = {"workspace": str(store.root), "initialized": True}
    elif a.command == "ai-prepare":
        pending = store.rows("SELECT job_id FROM ai_jobs WHERE state='pending'")
        result = pending or [{"job_id": j["job_id"]} for j in bridge.prepare()]
    elif a.command == "reindex":
        with store.db() as c:
            c.execute("DELETE FROM message_fts")
            c.execute(
                "INSERT INTO message_fts SELECT message_id,subject,body_text FROM messages"
            )
        result = {"reindexed": True}
    elif a.command == "ai-consume":
        result = bridge.consume()
    elif a.command == "ai-import":
        result = bridge.import_result(json.loads(a.file.read_text(encoding="utf-8")))
    elif a.command == "intake":
        from .ai import validate

        payload = json.loads(a.file.read_text(encoding="utf-8"))
        validate(payload, "intake")
        result = store.create_todo(
            payload, "workbuddy", "intake:" + payload["request_id"]
        )
    elif a.command == "simulate":
        if not store.setting("demo_seeded"):
            raise ValueError("simulate requires a synthetic demo workspace")
        from .demo import simulated_result

        jobs = [
            json.loads(j["input_json"])
            for j in store.rows("SELECT * FROM ai_jobs WHERE state='pending'")
        ]
        if not jobs:
            jobs = bridge.prepare()
        result = [
            bridge.import_result(simulated_result(j))
            for j in jobs
            if not a.job_id or a.job_id == j["job_id"]
        ]
    elif a.command in ("backup", "restore"):
        import getpass
        from .operations import backup, restore

        password = getpass.getpass("Backup password: ")
        result = (
            backup(store, a.output, password, a.scope)
            if a.command == "backup"
            else restore(store, a.file, password, a.apply)
        )
    elif a.command == "legacy-import":
        from .operations import import_legacy

        result = import_legacy(
            store, json.loads(a.file.read_text(encoding="utf-8")), a.apply
        )
    else:
        result = {"initialized": True}
    print(dumps(result))
    if a.command == "doctor" and not result["ok"]:
        p.exit(2)


if __name__ == "__main__":
    main()
