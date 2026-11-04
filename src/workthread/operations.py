"""Consistent encrypted backups and reversible, confirmed legacy imports."""

import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path, PurePosixPath
import py7zr
from .core import Store, uid, now, dumps, digest, load, VERSION, Conflict
from .ai import Bridge

TODO_TABLES = ["todos", "todo_sources", "progress_logs", "status_events"]


def backup(s, path, password, scope="full"):
    if len(password) < 10:
        raise ValueError("备份密码至少 10 个字符")
    if scope not in ("full", "todos"):
        raise ValueError("invalid backup scope")
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError("备份目标已存在")
    tmp = path.with_suffix(path.suffix + ".partial")
    try:
        with tempfile.TemporaryDirectory(prefix="workthread-backup-") as directory:
            stage = Path(directory)
            with s.lock:
                if scope == "full":
                    from .mail import Archive

                    Archive(s).recover()
                    (stage / "data").mkdir()
                    with s.db() as c:
                        dest = sqlite3.connect(stage / "data/workthread.sqlite3")
                        try:
                            c.backup(dest)
                        finally:
                            dest.close()
                    for kind in ("meta", "body"):
                        (stage / "data" / kind).mkdir()
                        for f in (s.data / kind).glob("*.jsonl"):
                            shutil.copy2(f, stage / "data" / kind / f.name)
                    for sub in (
                        "config",
                        "agent-workspace/.codebuddy",
                        "agent-workspace/schemas",
                    ):
                        source = s.root / sub
                        if source.is_dir():
                            shutil.copytree(source, stage / sub)
                    if (s.root / "agent-workspace/CODEBUDDY.md").exists():
                        target = stage / "agent-workspace/CODEBUDDY.md"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(s.root / "agent-workspace/CODEBUDDY.md", target)
                else:
                    document = {
                        table: s.rows("SELECT * FROM " + table) for table in TODO_TABLES
                    }
                    document["reference_summaries"] = {
                        "customers": s.rows("SELECT * FROM customers"),
                        "cases": s.rows("SELECT * FROM cases"),
                        "entity_confirmations": s.rows(
                            "SELECT * FROM entity_confirmations WHERE entity_type IN ('customers','cases')"
                        ),
                    }
                    (stage / "todos.json").write_text(dumps(document), encoding="utf-8")
            manifest = {
                "format_version": 1,
                "schema_version": VERSION,
                "scope": scope,
                "created_at": now(),
                "files": {
                    str(f.relative_to(stage)).replace("\\", "/"): {
                        "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                        "size": f.stat().st_size,
                    }
                    for f in stage.rglob("*")
                    if f.is_file()
                },
            }
            (stage / "manifest.json").write_text(dumps(manifest), encoding="utf-8")
            with py7zr.SevenZipFile(
                tmp, "w", password=password, header_encryption=True
            ) as z:
                for f in stage.rglob("*"):
                    if f.is_file():
                        z.write(f, str(f.relative_to(stage)).replace("\\", "/"))
            # Verify encrypted archive before exposing the final filename.
            with py7zr.SevenZipFile(tmp, "r", password=password) as z:
                if z.testzip() is not None:
                    raise ValueError("backup archive verification failed")
            tmp.replace(path)
        return {"path": str(path), "scope": scope, "files": len(manifest["files"])}
    finally:
        if tmp.exists():
            tmp.unlink()


def extract_verified(path, password, stage):
    with py7zr.SevenZipFile(
        path, "r", password=password, max_extract_size=20 * 1024**3
    ) as z:
        infos = z.list()
        total = 0
        for info in infos:
            name = info.filename
            p = PurePosixPath(name.replace("\\", "/"))
            if (
                p.is_absolute()
                or ".." in p.parts
                or ":" in name
                or getattr(info, "is_symlink", False)
            ):
                raise ValueError("unsafe archive path")
            total += info.uncompressed or 0
        if total > 20 * 1024**3:
            raise ValueError("archive exceeds restore size limit")
        z.extractall(stage)
    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("scope") not in ("full", "todos"):
        raise ValueError("invalid backup scope")
    if manifest["format_version"] != 1 or manifest["schema_version"] > VERSION:
        raise ValueError("unsupported backup version")
    actual = {
        str(f.relative_to(stage)).replace("\\", "/")
        for f in stage.rglob("*")
        if f.is_file() and f.name != "manifest.json"
    }
    if actual != set(manifest["files"]):
        raise ValueError("backup file manifest mismatch")
    for name, info in manifest["files"].items():
        f = stage / name
        if (
            f.stat().st_size != info["size"]
            or hashlib.sha256(f.read_bytes()).hexdigest() != info["sha256"]
        ):
            raise ValueError("backup hash mismatch")
    return manifest


def restore(s, path, password, apply=False):
    with tempfile.TemporaryDirectory(prefix="workthread-restore-") as directory:
        stage = Path(directory)
        manifest = extract_verified(path, password, stage)
        if manifest["scope"] == "full":
            db = sqlite3.connect(stage / "data/workthread.sqlite3")
            try:
                if (
                    db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                    or db.execute("PRAGMA foreign_key_check").fetchall()
                ):
                    raise ValueError("invalid backup database")
            finally:
                db.close()
        if not apply:
            return {
                "preview": True,
                "manifest": manifest,
                "conflict_policy": "full: replace with rollback copy; todos: identical IDs skip, different IDs stop",
            }
        with s.lock:
            if manifest["scope"] == "todos":
                data = json.loads((stage / "todos.json").read_text())
                if manifest["schema_version"] < 2:
                    for todo in data["todos"]:
                        todo.setdefault("no_due_date", 0)
                with s.db() as c:
                    for t in data["todos"]:
                        old = c.execute(
                            "SELECT * FROM todos WHERE todo_id=?", (t["todo_id"],)
                        ).fetchone()
                        if old and dict(old) != t:
                            raise Conflict("To Do ID 冲突；请先选择独立工作空间恢复")
                    for ref, table in [
                        ("customers", "customers"),
                        ("cases", "cases"),
                        ("entity_confirmations", "entity_confirmations"),
                    ]:
                        for item in data.get("reference_summaries", {}).get(ref, []):
                            cols = list(item)
                            if set(cols) != {
                                r[1]
                                for r in c.execute("PRAGMA table_info(" + table + ")")
                            }:
                                raise ValueError("invalid backup columns")
                            ref_key = {
                                "customers": "customer_id",
                                "cases": "case_id",
                                "entity_confirmations": "confirmation_id",
                            }[table]
                            current = c.execute(
                                "SELECT * FROM " + table + " WHERE " + ref_key + "=?",
                                (item[ref_key],),
                            ).fetchone()
                            if current and dict(current) != item:
                                raise Conflict("引用对象存在冲突，请恢复到独立空间")
                            c.execute(
                                "INSERT OR IGNORE INTO "
                                + table
                                + " ("
                                + ",".join(cols)
                                + ") VALUES ("
                                + ",".join("?" for _ in cols)
                                + ")",
                                tuple(item.values()),
                            )
                    for table in TODO_TABLES:
                        for item in data[table]:
                            cols = list(item)
                            if set(cols) != {
                                r[1]
                                for r in c.execute("PRAGMA table_info(" + table + ")")
                            }:
                                raise ValueError("invalid backup columns")
                            primary = {
                                "todos": "todo_id",
                                "todo_sources": "source_id",
                                "progress_logs": "log_id",
                                "status_events": "event_id",
                            }[table]
                            existing = c.execute(
                                "SELECT * FROM " + table + " WHERE " + primary + "=?",
                                (item[primary],),
                            ).fetchone()
                            if existing and dict(existing) != item:
                                raise Conflict("备份记录冲突，已取消整个导入")
                            c.execute(
                                "INSERT OR IGNORE INTO "
                                + table
                                + " ("
                                + ",".join(cols)
                                + ") VALUES ("
                                + ",".join("?" for _ in cols)
                                + ")",
                                tuple(item.values()),
                            )
                    s.audit(c, "todos_restored", None, {"count": len(data["todos"])})
                return {"scope": "todos", "restored": True}
            rollback = s.root / ("restore-rollback-" + uid())
            rollback.mkdir()
            moved = []
            try:
                for name in ("data", "config", "agent-workspace"):
                    target = s.root / name
                    if target.exists():
                        target.rename(rollback / name)
                        moved.append(name)
                    if (stage / name).exists():
                        shutil.copytree(stage / name, target)
                s.archive_seen.clear()
                restored = Store(s.root)
                from .deployment import install_templates

                install_templates(restored)
                restored.set_setting("workspace_epoch", uid())
                restored.set_setting(
                    "ai_schedule",
                    {"enabled": False, "frequency": "daily", "time": "09:00"},
                )
                with restored.db() as c:
                    c.execute("UPDATE mail_accounts SET enabled=0")
                    c.execute(
                        "UPDATE ai_jobs SET state='superseded',error='restored; regenerate job' WHERE state!='completed'"
                    )
                Bridge(restored).prepare()
                if not restored.health()["ok"]:
                    raise ValueError("restore health check failed")
            except BaseException:
                for name in ("data", "config", "agent-workspace"):
                    target = s.root / name
                    if target.exists():
                        shutil.rmtree(target)
                    if name in moved:
                        (rollback / name).rename(target)
                raise
            return {
                "scope": "full",
                "restored": True,
                "rollback_directory": str(rollback),
                "reauthorization_required": True,
            }


def import_legacy(s, document, apply=False):
    allowed = {
        "schema_version",
        "categories",
        "customers",
        "contacts",
        "relations",
        "cases",
        "knowledge",
        "profile",
    }
    if set(document) - allowed or document.get("schema_version") != "1.0":
        raise ValueError("unsupported legacy mapping")
    for k in ("categories", "customers", "contacts", "relations", "cases", "knowledge"):
        if not isinstance(document.get(k, []), list):
            raise ValueError("invalid legacy " + k)
    if not apply:
        return {
            "preview": True,
            "counts": {
                k: len(document.get(k, []))
                for k in allowed
                if isinstance(document.get(k), list)
            },
            "unconfirmed_remains_candidate": True,
        }
    h = digest(document)
    with s.db() as c:
        old = c.execute(
            "SELECT batch_id FROM imports WHERE payload_hash=?", (h,)
        ).fetchone()
        if old:
            return {"batch_id": old[0], "duplicate": True}
        batch = uid()
        mapping = {}
        records = []
        c.execute("INSERT INTO imports VALUES (?,?,?,?)", (batch, h, now(), "{}"))

        # IDs are namespaced per import; no source paths are dereferenced.
        def ident(kind, old):
            return mapping.setdefault(
                kind + ":" + old,
                str(
                    __import__("uuid").uuid5(
                        __import__("uuid").NAMESPACE_URL, h + kind + old
                    )
                ),
            )

        for item in document.get("customers", []):
            rid = ident("customer", item["id"])
            c.execute("INSERT INTO customers VALUES (?,?,1)", (rid, item["name"]))
            records.append(("customers", rid))
        pending = list(document.get("categories", []))
        while pending:
            progressed = False
            for item in pending[:]:
                parent = item.get("parent_id")
                if (
                    parent
                    and not c.execute(
                        "SELECT 1 FROM categories WHERE category_id=?",
                        (ident("category", parent),),
                    ).fetchone()
                ):
                    continue
                rid = ident("category", item["id"])
                c.execute(
                    "INSERT INTO categories VALUES (?,?,?)",
                    (rid, ident("category", parent) if parent else None, item["name"]),
                )
                records.append(("categories", rid))
                pending.remove(item)
                progressed = True
            if not progressed:
                raise ValueError("category cycle or unknown parent")
        for item in document.get("contacts", []):
            rid = ident("contact", item["id"])
            customer = (
                ident("customer", item["customer_id"])
                if item.get("customer_id")
                else None
            )
            c.execute(
                "INSERT INTO contacts VALUES (?,?,?,?)",
                (rid, item["name"], item.get("address"), customer),
            )
            records.append(("contacts", rid))
        for item in document.get("relations", []):
            rid = uid()
            c.execute(
                "INSERT INTO contact_relations VALUES (?,?,?,?,?)",
                (
                    rid,
                    ident("contact", item["from_id"]),
                    ident("customer", item["to_id"]),
                    item["relation"],
                    int(item.get("confirmed", False)),
                ),
            )
            records.append(("contact_relations", rid))
        for item in document.get("cases", []):
            rid = ident("case", item["id"])
            c.execute(
                "INSERT INTO cases VALUES (?,?,?,?,?,1)",
                (
                    rid,
                    item["title"],
                    ident("customer", item["customer_id"])
                    if item.get("customer_id")
                    else None,
                    item.get("case_type", "project"),
                    item.get("stage"),
                ),
            )
            records.append(("cases", rid))
        knowledge = list(document.get("knowledge", []))
        if document.get("profile"):
            knowledge.append(
                {
                    "scope": "personal",
                    "content": dumps(document["profile"]),
                    "confirmed": False,
                }
            )
        for item in knowledge:
            if item["scope"] not in ("personal", "customer", "case"):
                raise ValueError("invalid knowledge scope")
            rid = uid()
            scope = item["scope"]
            subject = (
                ident(scope, item["subject_id"]) if item.get("subject_id") else None
            )
            confirmed = int(item.get("confirmed", False))
            content = item["content"]
            c.execute(
                "INSERT INTO knowledge_items VALUES (?,?,?,?,?,?,?,?,?,?)",
                (rid, scope, subject, content, confirmed, "[]", 1, None, now(), now()),
            )
            records.append(("knowledge_items", rid))
            c.execute(
                "INSERT INTO knowledge_versions VALUES (?,?,?,?,?,?)",
                (uid(), rid, 1, content, confirmed, now()),
            )
        # Snapshot record hashes let rollback refuse to erase subsequently edited information.
        for plural, kind in [
            ("customers", "customer"),
            ("contacts", "contact"),
            ("cases", "case"),
        ]:
            for item in document.get(plural, []):
                entity_id = ident(kind, item["id"])
                confirmation_id = uid()
                confirmed = int(item.get("confirmed", False))
                c.execute(
                    "INSERT INTO entity_confirmations VALUES (?,?,?,?)",
                    (confirmation_id, plural, entity_id, confirmed),
                )
                records.append(("entity_confirmations", confirmation_id))
                if not confirmed:
                    s._review(
                        c,
                        "confirm_entity",
                        {
                            "entity_type": plural,
                            "entity_id": entity_id,
                            "name": item.get("name", item.get("title")),
                            "import_batch": batch,
                        },
                    )
        snapshots = {}
        keys = {
            "customers": "customer_id",
            "contacts": "contact_id",
            "contact_relations": "relation_id",
            "cases": "case_id",
            "categories": "category_id",
            "knowledge_items": "knowledge_id",
            "entity_confirmations": "confirmation_id",
        }
        for table, rid in records:
            c.execute("INSERT INTO import_records VALUES (?,?,?)", (batch, table, rid))
            snapshots[table + ":" + rid] = digest(
                dict(
                    c.execute(
                        "SELECT * FROM " + table + " WHERE " + keys[table] + "=?",
                        (rid,),
                    ).fetchone()
                )
            )
        c.execute(
            "UPDATE imports SET mapping=? WHERE batch_id=?",
            (dumps({"ids": mapping, "snapshots": snapshots}), batch),
        )
        s.audit(c, "legacy_imported", batch, {"count": len(records)})
    return {"batch_id": batch, "duplicate": False}


def undo_import(s, batch):
    keys = {
        "customers": "customer_id",
        "contacts": "contact_id",
        "contact_relations": "relation_id",
        "cases": "case_id",
        "categories": "category_id",
        "knowledge_items": "knowledge_id",
        "entity_confirmations": "confirmation_id",
    }
    with s.db() as c:
        row = c.execute(
            "SELECT mapping FROM imports WHERE batch_id=?", (batch,)
        ).fetchone()
        if not row:
            raise ValueError("unknown import batch")
        snapshot = load(row[0])["snapshots"]
        records = c.execute(
            "SELECT * FROM import_records WHERE batch_id=?", (batch,)
        ).fetchall()
        for r in records:
            record = c.execute(
                "SELECT * FROM "
                + r["table_name"]
                + " WHERE "
                + keys[r["table_name"]]
                + "=?",
                (r["record_id"],),
            ).fetchone()
            if (
                not record
                or digest(dict(record))
                != snapshot[r["table_name"] + ":" + r["record_id"]]
            ):
                raise Conflict("导入内容已修改，不能自动撤销")
        c.execute(
            "DELETE FROM review_items WHERE json_extract(payload, '$.import_batch')=?",
            (batch,),
        )
        for table in (
            "entity_confirmations",
            "knowledge_items",
            "contact_relations",
            "cases",
            "contacts",
            "categories",
            "customers",
        ):
            selected = [r for r in records if r["table_name"] == table]
            if table == "categories":
                selected.reverse()
            for r in selected:
                if table == "knowledge_items":
                    c.execute(
                        "DELETE FROM knowledge_versions WHERE knowledge_id=?",
                        (r["record_id"],),
                    )
                c.execute(
                    "DELETE FROM " + table + " WHERE " + keys[table] + "=?",
                    (r["record_id"],),
                )
        c.execute("DELETE FROM import_records WHERE batch_id=?", (batch,))
        c.execute("DELETE FROM imports WHERE batch_id=?", (batch,))
        s.audit(c, "legacy_import_undone", batch, {})
    return {"undone": True}
