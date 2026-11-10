"""Local asynchronous mail sync. The account lock covers acceptance through completion."""

import sqlite3
import threading

from filelock import Timeout

from .core import Conflict, dumps, uid
from .mail import ACTIVE_SYNC_STATES, Sync, SyncStopped, sqlite_sync_error


class MailTasks:
    def __init__(self, store, stop=None):
        self.store = store
        self.stop = stop or threading.Event()
        self.guard = threading.Lock()
        self.threads = set()

    def start(self, account_id, *, scheduled=False, request_id=None):
        from .demo import FakeIMAP

        sync = Sync(self.store, FakeIMAP if account_id == "demo" else None, self.stop)
        # Coordinate admission across service processes and with full restore.
        with self.guard, self.store.lock:
            if self.stop.is_set():
                raise Conflict("工作台正在停止")
            accounts = self.store.rows(
                "SELECT enabled FROM mail_accounts WHERE account_id=? AND host<>''",
                (account_id,),
            )
            if not accounts:
                raise ValueError("未知邮箱")
            if scheduled and not accounts[0]["enabled"]:
                return None
            key = f"mail-submit:{account_id}:{request_id}" if request_id else None
            if key:
                accepted_id = self.store.setting(key)
                if accepted_id:
                    result = self.get(account_id, accepted_id)
                    if result:
                        return result
            lock = sync._lock(account_id)
            previous = self.store.setting("mail-sync:" + account_id) or {}
            try:
                lock.acquire()
            except Timeout:
                if previous.get("state") in ACTIVE_SYNC_STATES and previous.get(
                    "task_id"
                ):
                    if key:
                        self.store.set_setting(key, previous["task_id"])
                    return previous
                raise Conflict("此邮箱有其他操作正在进行")
            try:
                if previous.get("state") == "blocked":
                    raise Conflict("文件夹标识已变化，请先核对邮箱文件夹设置")
                resume = previous.get("state") in ACTIVE_SYNC_STATES | {
                    "interrupted",
                    "partial",
                    "failed",
                }
                task_id = (previous.get("task_id") if resume else None) or uid()
                task = dict(
                    account_id=account_id,
                    task_id=task_id,
                    state="queued",
                    folders=previous.get("folders", {}) if resume else {},
                )
                with self.store.db() as c:
                    sync._save(c, task)
                    if key:
                        c.execute(
                            "INSERT OR REPLACE INTO settings VALUES (?,?)",
                            (key, dumps(task_id)),
                        )
                thread = threading.Thread(
                    target=self._execute,
                    args=(sync, task, lock),
                    name="mail-sync-" + task_id,
                )
                self.threads.add(thread)
                try:
                    thread.start()
                except BaseException:
                    self.threads.discard(thread)
                    raise
            except BaseException:
                lock.release()
                raise
            return task

    def _execute(self, sync, task, lock):
        try:
            sync.run_locked(task["account_id"], task["task_id"])
        except Exception as exc:
            # Covers failures before the first run row, and shutdown during DB backoff.
            try:
                key = "mail-sync:" + task["account_id"]
                status = self.store.setting(key) or task.copy()
                if status["state"] in ACTIVE_SYNC_STATES:
                    if isinstance(exc, SyncStopped):
                        status["state"] = "interrupted"
                    else:
                        status.update(state="failed", error=type(exc).__name__)
                        if isinstance(exc, sqlite3.DatabaseError):
                            status["error_detail"] = sqlite_sync_error(exc)
                    with self.store.db() as c:
                        sync._save(c, status)
            except (Timeout, sqlite3.Error):
                # An unavailable store cannot record the failure. Releasing the file
                # lock lets status readers identify the abandoned task as interrupted.
                pass
        finally:
            lock.release()
            with self.guard:
                self.threads.discard(threading.current_thread())

    def get(self, account_id, task_id):
        current = Sync(self.store).status(account_id)
        if current.get("task_id") == task_id:
            return current
        result = self.store.setting("mail-task:" + task_id)
        if result and result["account_id"] == account_id:
            return result
        return None

    def close(self):
        with self.guard:
            self.stop.set()
            threads = list(self.threads)
        for thread in threads:
            thread.join()
