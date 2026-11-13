"""Durable state for one web update, independent of historical offline results."""

import contextlib
import ctypes
import os
import re
import time
import uuid

from filelock import FileLock, Timeout

from ..diagnostics import describe_error
from . import releases as rel
from . import transaction as tx

TERMINAL = {"succeeded", "failed"}


def clock():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_record(path):
    with contextlib.suppress(OSError, ValueError):
        value = rel.read(tx.safe(path))
        if isinstance(value, dict):
            return value
    return None


def describe_failure(exc):
    # Only deliberate application errors contain user-facing details.
    return (
        str(exc)
        if type(exc) is ValueError or getattr(exc, "diagnostic", None)
        else describe_error(exc)
    )


def worker_active(pid):
    if os.name != "nt" or type(pid) is not int or pid <= 0:
        return False
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        return ctypes.get_last_error() != 87
    try:
        return kernel.WaitForSingleObject(wintypes.HANDLE(handle), 0) != 0
    finally:
        kernel.CloseHandle(wintypes.HANDLE(handle))


class Attempt:
    def __init__(self, root):
        self.root = root
        self.state = tx.safe(root / tx.STATE)

    @contextlib.contextmanager
    def lock(self):
        self.state.mkdir(exist_ok=True)
        try:
            with FileLock(str(tx.safe(self.state / "web-update.lock")), timeout=5):
                yield
        except Timeout as exc:
            raise ValueError("软件更新正在运行，请等待完成并重新连接") from exc

    def read(self):
        job = read_record(self.state / "web-update.json")
        if (
            job
            and all(
                isinstance(job.get(k), str)
                for k in (
                    "id",
                    "phase",
                    "sha256",
                    "target_version",
                    "target_commit",
                    "source_version",
                    "source_commit",
                    "started_at",
                    "updated_at",
                )
            )
            and re.fullmatch(r"[0-9a-f]{32}", job["id"])
        ):
            return job
        return None

    def start(self, current, manifest, attempt_id=None):
        return self.write(
            {
                "id": attempt_id or uuid.uuid4().hex,
                "source_version": current["version"],
                "source_commit": current["commit_sha"],
                "target_version": manifest["version"],
                "target_commit": manifest["commit_sha"],
                "sha256": manifest["sha256"],
                "started_at": clock(),
            },
            "waiting-stop",
        )

    def write(self, job, phase, **fields):
        record = {**job, **fields, "phase": phase, "updated_at": clock()}
        rel.save(tx.safe(self.state / "web-update.json"), record)
        return record

    def fail(self, job, stage, exc):
        self.write(
            job,
            "failed",
            failed_stage=stage,
            error=describe_failure(exc),
            error_type=type(exc).__name__,
        )

    def reconcile(self):
        """On explicit launch, the update lock is free and any journal was recovered."""
        job = self.read()
        if not job or job["phase"] in TERMINAL or job["phase"] == "restarting":
            return
        if worker_active(job.get("worker_pid")):
            raise ValueError("软件更新正在运行，请等待完成并重新连接")
        journal = read_record(tx.journal(self.root))
        if (
            journal
            and journal.get("operation_id") == job["id"]
            and journal.get("phase") == "committed"
        ):
            self.write(job, "restarting")
        elif (
            journal
            and journal.get("operation_id") == job["id"]
            and journal.get("phase") == "rolled-back"
        ):
            self.write(
                job,
                "failed",
                failed_stage=job["phase"],
                error="更新已中断，原版本与工作空间已恢复",
            )
        # A duplicate launcher must not mark a handoff as interrupted while the
        # original service is still exiting.
        else:
            from .controller import no_leases

            no_leases(self.state)
            self.write(
                job,
                "failed",
                failed_stage=job["phase"],
                error="更新已中断，未确认完成；请重新检查",
            )
