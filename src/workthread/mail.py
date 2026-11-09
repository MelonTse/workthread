"""IMAP section-only fetch, append-only archive journal, and searchable index."""

import base64
import contextlib
import datetime as dt
import email
from email import policy
from email.errors import MessageError
from email.utils import getaddresses, parsedate_to_datetime
import html
import imaplib
import json
import os
import quopri
import re
import ssl
import time
from filelock import FileLock, Timeout
from .core import Conflict, uid, now, dumps, digest, load


class UnsafeMime(ValueError):
    pass


def text(v):
    return v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v or "")


def params(raw):
    if raw is None:
        return {}
    if not isinstance(raw, (tuple, list)) or len(raw) % 2:
        raise UnsafeMime("invalid MIME parameters")
    return {text(raw[i]).lower(): text(raw[i + 1]) for i in range(0, len(raw), 2)}


def body_parts(struct, path=""):
    """Return permitted text leaves and attachment metadata; never fetch container bodies."""
    if not isinstance(struct, (tuple, list)) or not struct:
        raise UnsafeMime("missing BODYSTRUCTURE")
    # IMAPClient BodyData folds multipart children into a first list.
    if (
        isinstance(struct[0], list)
        and struct[0]
        and isinstance(struct[0][0], (tuple, list))
    ):
        children = struct[0]
        tail = struct[1:]
    elif isinstance(struct[0], (tuple, list)):
        n = 0
        while n < len(struct) and isinstance(struct[n], (tuple, list)):
            n += 1
        children = struct[:n]
        tail = struct[n:]
    else:
        children = None
    if children is not None:
        if not tail or not isinstance(tail[0], (bytes, str)):
            raise UnsafeMime("invalid multipart subtype")
        disposition = tail[2] if len(tail) > 2 else None
        mp = params(tail[1]) if len(tail) > 1 else {}
        dp = params(disposition[1]) if disposition and len(disposition) > 1 else {}
        if any(k.startswith(("name", "filename")) for k in list(mp) + list(dp)) or (
            disposition and text(disposition[0]).lower() == "attachment"
        ):
            return [], [
                {
                    "filename": params(disposition[1]).get("filename"),
                    "mime_type": "multipart/" + text(tail[0]).lower(),
                    "size": None,
                    "size_basis": "server_bodystructure",
                }
            ]
        leaves = []
        attachments = []
        for i, child in enumerate(children, 1):
            a, b = body_parts(child, f"{path}.{i}" if path else str(i))
            leaves += a
            attachments += b
        return leaves, attachments
    if len(struct) < 7:
        raise UnsafeMime("invalid MIME leaf")
    major, minor = text(struct[0]).lower(), text(struct[1]).lower()
    p = params(struct[2])
    if not isinstance(struct[6], int) or struct[6] < 0:
        raise UnsafeMime("invalid part size")
    disp_index = (
        9 if major == "text" else 11 if major == "message" and minor == "rfc822" else 8
    )
    disposition = struct[disp_index] if len(struct) > disp_index else None
    dp = params(disposition[1]) if disposition and len(disposition) > 1 else {}
    filename = dp.get("filename") or p.get("name")
    is_attachment = bool(
        filename
        or any(k.startswith(("name*", "filename*")) for k in list(p) + list(dp))
        or (disposition and text(disposition[0]).lower() == "attachment")
    )
    meta = {
        "filename": filename,
        "mime_type": major + "/" + minor,
        "size": struct[6],
        "size_basis": "server_encoded_octets",
    }
    if major != "text" or minor not in ("plain", "html") or is_attachment:
        return [], [meta]
    encoding = text(struct[5]).upper()
    if encoding not in ("7BIT", "8BIT", "BINARY", "BASE64", "QUOTED-PRINTABLE"):
        raise UnsafeMime("unsupported body transfer encoding")
    return [
        {
            "section": path or "1",
            "mime_type": major + "/" + minor,
            "charset": p.get("charset", "utf-8"),
            "encoding": encoding,
            "size": struct[6],
        }
    ], []


def decode_part(raw, part):
    enc = part["encoding"]
    if enc == "BASE64":
        raw = base64.b64decode(raw, validate=False)
    elif enc == "QUOTED-PRINTABLE":
        raw = quopri.decodestring(raw)
    try:
        return raw.decode(part["charset"])
    except (LookupError, UnicodeDecodeError) as error:
        raise UnsafeMime("body charset needs review") from error


def append_line(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as f:
        f.write((dumps(record) + "\n").encode())
        f.flush()
        os.fsync(f.fileno())


def repair_lines(path):
    if not path.exists():
        return set()
    ids = set()
    good = 0
    with path.open("rb") as f:
        for line in f:
            try:
                if not line.endswith(b"\n"):
                    break
                row = json.loads(line)
                ids.add(row["archive_tx_id"])
                good = f.tell()
            except (ValueError, KeyError):
                break
    if good != path.stat().st_size:
        # Preserve damaged suffix for diagnosis before recovering the committed prefix.
        with path.open("rb") as f:
            f.seek(good)
            suffix = f.read()
        path.with_suffix(".damaged-" + uid()).write_bytes(suffix)
        with path.open("r+b") as f:
            f.truncate(good)
    return ids


class Archive:
    def __init__(self, store):
        self.s = store

    def _finish(self, c, tx, p):
        m = p["message"]
        body = p["body"]
        meta = p["meta"]
        month = m["month"]
        for kind, record in [("meta", meta), ("body", body)]:
            if record is None:
                continue
            file = self.s.data / kind / (month + ".jsonl")
            signature = (
                (file.stat().st_size, file.stat().st_mtime_ns)
                if file.exists()
                else (0, 0)
            )
            cached = self.s.archive_seen.get(file)
            if not cached or cached[0] != signature:
                seen = repair_lines(file)
            else:
                seen = cached[1]
            if tx not in seen:
                append_line(file, record)
                seen.add(tx)
            signature = (file.stat().st_size, file.stat().st_mtime_ns)
            self.s.archive_seen[file] = (signature, seen)
        existing = c.execute(
            "SELECT message_id FROM messages WHERE fingerprint=?", (m["fingerprint"],)
        ).fetchone()
        mid = existing[0] if existing else m["message_id"]
        if not existing:
            columns = [
                "message_id",
                "rfc_message_id",
                "fingerprint",
                "subject",
                "date",
                "internal_date",
                "headers",
                "sender",
                "recipients",
                "in_reply_to",
                "refs",
                "month",
                "body_text",
                "body_html",
                "metadata",
                "archived_at",
            ]
            c.execute(
                "INSERT INTO messages ("
                + ",".join(columns)
                + ") VALUES ("
                + ",".join("?" for _ in columns)
                + ")",
                tuple(m[k] for k in columns),
            )
            c.execute(
                "INSERT INTO message_fts VALUES (?,?,?)",
                (mid, m["subject"], m["body_text"]),
            )
        o = p["occurrence"]
        c.execute(
            "INSERT OR IGNORE INTO mail_occurrences VALUES (?,?,?,?,?,?,?)",
            (
                uid(),
                mid,
                o["account_id"],
                o["folder_id"],
                o["uidvalidity"],
                o["imap_uid"],
                dumps(o.get("flags", [])),
            ),
        )
        c.execute("UPDATE archive_commits SET state='committed' WHERE tx_id=?", (tx,))
        c.execute(
            "DELETE FROM sync_failures WHERE folder_id=? AND uidvalidity=? AND imap_uid=?",
            (o["folder_id"], o["uidvalidity"], o["imap_uid"]),
        )
        return mid

    def recover(self):
        with self.s.db() as c:
            for row in c.execute(
                "SELECT * FROM archive_commits WHERE state='prepared'"
            ).fetchall():
                self._finish(c, row["tx_id"], load(row["payload"]))

    def record(self, raw_header, parts, attachment_meta, origin, internaldate):
        header = email.message_from_bytes(raw_header, policy=policy.default)
        headers = [{"name": k, "value": str(v)} for k, v in header.items()]
        addresses = lambda name: [
            {"name": n, "address": a}
            for n, a in getaddresses([str(v) for v in header.get_all(name, [])])
        ]
        plain = "\n".join(p["content"] for p in parts if p["mime_type"] == "text/plain")
        markup = "\n".join(p["content"] for p in parts if p["mime_type"] == "text/html")
        if not plain:
            plain = html.unescape(re.sub("<[^>]+>", " ", markup))
        internal = (
            internaldate
            if isinstance(internaldate, dt.datetime)
            else dt.datetime.fromisoformat(internaldate)
        )
        if not internal.tzinfo:
            internal = internal.replace(tzinfo=dt.timezone.utc)
        month = internal.astimezone(dt.timezone.utc).strftime("%Y-%m")
        try:
            date = parsedate_to_datetime(str(header.get("Date", ""))).isoformat()
        except (ValueError, TypeError):
            date = None
        fingerprint = digest(
            {"headers": headers, "parts": parts, "attachments": attachment_meta}
        )
        existing = self.s.rows(
            "SELECT message_id FROM messages WHERE fingerprint=?", (fingerprint,)
        )
        mid = existing[0]["message_id"] if existing else uid()
        tx = uid()
        at = now()
        metadata = {
            "raw_headers_base64": base64.b64encode(raw_header).decode("ascii"),
            "attachment_metadata": attachment_meta,
            "origin": origin,
            "parse_status": "complete",
            "raw_headers": raw_header.decode("ascii", "surrogateescape")
            .encode("utf-8", "backslashreplace")
            .decode(),
        }
        m = {
            "message_id": mid,
            "rfc_message_id": str(header.get("Message-ID", "")) or None,
            "fingerprint": fingerprint,
            "subject": str(header.get("Subject", "")),
            "date": date,
            "internal_date": internal.isoformat(),
            "headers": dumps(headers),
            "sender": dumps(addresses("From")),
            "recipients": dumps({k: addresses(k) for k in ("To", "Cc", "Bcc")}),
            "in_reply_to": str(header.get("In-Reply-To", "")) or None,
            "refs": dumps(re.findall(r"<[^>]+>", str(header.get("References", "")))),
            "month": month,
            "body_text": plain,
            "body_html": markup,
            "metadata": dumps(metadata),
            "archived_at": at,
        }
        meta = {
            "schema_version": "1.0",
            "record_type": "mail_archived",
            "archive_tx_id": tx,
            **{
                k: load(v)
                if k in ("headers", "sender", "recipients", "refs", "metadata")
                else v
                for k, v in m.items()
                if k not in ("body_text", "body_html")
            },
            "sync_status": "archived",
            "body_sha256": digest(parts),
        }
        body = {
            "schema_version": "1.0",
            "archive_tx_id": tx,
            "message_id": mid,
            "parts": parts,
            "text": plain,
            "html": markup,
            "sha256": digest(parts),
            "parse_status": "complete",
        }
        if existing:
            meta["record_type"] = "mail_source"
            body = None
        p = {"message": m, "meta": meta, "body": body, "occurrence": origin}
        with self.s.db() as c:
            c.execute(
                "INSERT INTO archive_commits VALUES (?,?,?,?)",
                (tx, dumps(p), "prepared", at),
            )
        with self.s.db() as c:
            return self._finish(c, tx, p)


class SessionLost(Exception):
    """Transient failure of an IMAP operation (never a local archive write)."""


class FolderChanged(ValueError):
    pass


def imap_call(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except ssl.SSLCertVerificationError:
        raise
    except (imaplib.IMAP4.abort, EOFError, OSError) as exc:
        raise SessionLost from exc
    except imaplib.IMAP4.error as exc:
        # IMAPClient wraps a login-time abort in LoginError.
        if isinstance(exc.__context__, imaplib.IMAP4.abort):
            raise SessionLost from exc
        raise


class Sync:
    retry_delays = (1, 3, 8)

    def __init__(self, store, client_factory=None):
        self.s = store
        self.archive = Archive(store)
        self.client_factory = client_factory

    def _lock(self, account_id):
        return FileLock(
            self.s.root / (".mail-sync-" + digest(account_id) + ".lock"), timeout=0
        )

    def status(self, account_id):
        status = self.s.setting("mail-sync:" + account_id)
        if status is None:
            history = self.s.rows(
                "SELECT state FROM sync_runs WHERE account_id=? ORDER BY rowid DESC LIMIT 1",
                (account_id,),
            )
            state = history[0]["state"] if history else "idle"
            return {
                "state": "interrupted" if state == "running" else state,
                "folders": {},
            }
        if status["state"] in ("running", "reconnecting"):
            try:
                with self._lock(account_id):
                    # No owning process remains after an unclean exit.
                    status = self.s.setting("mail-sync:" + account_id) or status
                    if status["state"] in ("running", "reconnecting"):
                        status["state"] = "interrupted"
            except Timeout:
                pass
        return status

    def _connect(self, account):
        if self.client_factory:
            return imap_call(self.client_factory, account)
        import keyring
        from imapclient import IMAPClient

        password = keyring.get_password("workthread", account["credential_ref"])
        if not password:
            raise ValueError("请在本机凭证库重新授权邮箱")
        client = imap_call(
            IMAPClient,
            account["host"],
            port=account["port"],
            ssl=True,
            ssl_context=ssl.create_default_context(),
            timeout=30,
        )
        try:
            imap_call(client.login, account["username"], password)
        except Exception:
            with contextlib.suppress(Exception):
                client.shutdown()
            raise
        return client

    def _folders(self, account, client):
        configured = load(account["folders"], [])
        if configured:
            return configured
        for flags, _, name in imap_call(client.list_folders):
            if b"\\Sent" in flags or "\\Sent" in flags:
                return [
                    {"name": "INBOX", "direction": "inbox"},
                    {"name": name, "direction": "sent"},
                ]
        raise ValueError("无法识别已发送文件夹，请在设置中选择")

    def _read_message(self, client, account_id, fid, validity, mailuid):
        data = imap_call(
            client.fetch,
            [mailuid],
            [
                "BODY.PEEK[HEADER]",
                "BODYSTRUCTURE",
                "INTERNALDATE",
                "FLAGS",
            ],
        )[mailuid]
        leaves, attachments = body_parts(data[b"BODYSTRUCTURE"])
        decoded = []
        if not leaves:
            raise UnsafeMime("no permitted body; inspect MIME structure manually")
        for leaf in leaves:
            request = "BODY.PEEK[" + leaf["section"] + "]"
            response = imap_call(client.fetch, [mailuid], [request])[mailuid]
            raw = response.get(("BODY[" + leaf["section"] + "]").encode())
            if not isinstance(raw, bytes):
                raise UnsafeMime("missing requested body section")
            decoded.append(
                {
                    **leaf,
                    "content": decode_part(raw, leaf),
                    "wire_base64": base64.b64encode(raw).decode("ascii"),
                }
            )
        origin = {
            "account_id": account_id,
            "folder_id": fid,
            "uidvalidity": validity,
            "imap_uid": mailuid,
            "flags": [text(f) for f in data.get(b"FLAGS", [])],
        }
        self.archive.record(
            data[b"BODY[HEADER]"],
            decoded,
            attachments,
            origin,
            data[b"INTERNALDATE"],
        )

    def _save(self, c, progress):
        c.execute(
            "INSERT OR REPLACE INTO settings VALUES (?,?)",
            ("mail-sync:" + progress["account_id"], dumps(progress)),
        )

    def _folder(self, client, spec, progress, failures):
        name = spec["name"]
        account_id = progress["account_id"]
        info = imap_call(client.select_folder, name, readonly=True)
        validity = int(info[b"UIDVALIDITY"])
        with self.s.db() as c:
            folder = c.execute(
                "SELECT folder_id,uidvalidity FROM mail_folders WHERE account_id=? AND name=?",
                (account_id, name),
            ).fetchone()
            if folder and folder["uidvalidity"] != validity:
                raise FolderChanged(name)
            fid = folder["folder_id"] if folder else uid()
            if not folder:
                c.execute(
                    "INSERT INTO mail_folders VALUES (?,?,?,?,?,0)",
                    (fid, account_id, name, spec["direction"], validity),
                )
        uids = set(imap_call(client.search, ["ALL"]))
        archived = {
            r["imap_uid"]
            for r in self.s.rows(
                "SELECT imap_uid FROM mail_occurrences WHERE folder_id=? AND uidvalidity=?",
                (fid, validity),
            )
        }
        counts = {
            "total": len(uids),
            "archived": len(uids & archived),
            "errors": len(uids & failures.keys()),
        }
        progress["folders"][name] = counts
        progress["state"] = "running"
        with self.s.db() as c:
            self._save(c, progress)
        for mailuid in sorted(uids - archived - failures.keys()):
            try:
                self._read_message(client, account_id, fid, validity, mailuid)
            except (ValueError, LookupError, MessageError) as exc:
                error = type(exc).__name__
                failures[mailuid] = error
                counts["errors"] += 1
                with self.s.db() as c:
                    c.execute(
                        "INSERT OR REPLACE INTO sync_failures VALUES (?,?,?,?)",
                        (fid, validity, mailuid, error),
                    )
                    self._save(c, progress)
            else:
                counts["archived"] += 1
                with self.s.db() as c:
                    c.execute(
                        "UPDATE mail_folders SET high_uid=max(high_uid,?) WHERE folder_id=?",
                        (mailuid, fid),
                    )
                    self._save(c, progress)

    def run(self, account_id):
        lock = self._lock(account_id)
        try:
            lock.acquire()
        except Timeout as exc:
            raise Conflict("该邮箱正在拉取，请查看当前进度") from exc
        try:
            return self._run(account_id)
        finally:
            lock.release()

    def _run(self, account_id):
        accounts = self.s.rows(
            "SELECT * FROM mail_accounts WHERE account_id=?", (account_id,)
        )
        if not accounts:
            raise ValueError("未知邮箱")
        account = accounts[0]
        previous = self.s.setting("mail-sync:" + account_id) or {}
        resuming = previous.get("state") in (
            "running",
            "reconnecting",
            "interrupted",
            "blocked",
            "failed",
        )
        progress = {
            "account_id": account_id,
            "run_id": uid(),
            "state": "running",
            "attempt": 0,
            "folder": "",
            "folders": previous.get("folders", {}) if resuming else {},
        }
        with self.s.db() as c:
            c.execute(
                "UPDATE sync_runs SET state='interrupted',finished_at=? WHERE account_id=? AND state='running'",
                (now(), account_id),
            )
            c.execute(
                "INSERT INTO sync_runs VALUES (?,?,?,?,?,?)",
                (progress["run_id"], account_id, now(), None, "running", None),
            )
            self._save(c, progress)
        client = None
        folders = None
        index = 0
        failures = {}
        try:
            self.archive.recover()
            while folders is None or index < len(folders):
                try:
                    if client is None:
                        client = self._connect(account)
                    if folders is None:
                        folders = self._folders(account, client)
                        progress["folders"] = {
                            spec["name"]: progress["folders"].get(spec["name"])
                            for spec in folders
                        }
                    spec = folders[index]
                    progress["folder"] = spec["name"]
                    self._folder(
                        client, spec, progress, failures.setdefault(spec["name"], {})
                    )
                    index += 1
                except SessionLost:
                    if client is not None:
                        with contextlib.suppress(Exception):
                            client.shutdown()
                        client = None
                    attempt = progress["attempt"]
                    if attempt == len(self.retry_delays):
                        progress["state"] = "interrupted"
                        break
                    progress.update(state="reconnecting", attempt=attempt + 1)
                    with self.s.db() as c:
                        self._save(c, progress)
                    time.sleep(self.retry_delays[attempt])
            else:
                progress["state"] = "partial" if any(failures.values()) else "completed"
        except FolderChanged:
            progress["state"] = "blocked"
        except Exception as exc:
            progress.update(state="failed", error=type(exc).__name__)
            raise
        finally:
            errors = [
                {"folder": name, "uid": n, "error": reason}
                for name, items in failures.items()
                for n, reason in items.items()
            ]
            with self.s.db() as c:
                self._save(c, progress)
                c.execute(
                    "UPDATE sync_runs SET finished_at=?,state=?,error=? WHERE run_id=?",
                    (
                        now(),
                        progress["state"],
                        progress.get("error") or dumps(errors),
                        progress["run_id"],
                    ),
                )
            if client is not None:
                with contextlib.suppress(Exception):
                    client.logout()
        return {**progress, "errors": errors}
