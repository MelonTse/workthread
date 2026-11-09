"""Fixed local endpoints and detached bootstrap. The browser cannot supply URLs or paths."""

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from filelock import FileLock, Timeout

from . import releases as rel
from . import transaction as tx


def install_root(space):
    if (
        os.name != "nt"
        or not getattr(sys, "frozen", False)
        or space.name != "workspace"
    ):
        return None
    root = space.parent
    if not (root / "BUILD_INFO.json").is_file():
        return None
    bundle, _ = tx.current(root)
    return (
        root if (bundle / tx.EXE).resolve() == Path(sys.executable).resolve() else None
    )


def detached(args):
    return subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
    )


class Updates:
    def __init__(self, root, stop=None, port=8765):
        self.root, self.stop, self.port = root, stop, port
        self.lock = threading.Lock()
        self.offer = None
        self.ready = False
        self.stopping = False

    def status(self):
        from .. import __version__

        result = {"enabled": bool(self.root), "current": __version__}
        if self.root:
            result["current"] = tx.current(self.root)[1]["version"]
            state = self.root / tx.STATE
            if (state / "result.json").is_file():
                result["last"] = rel.read(state / "result.json")
            if tx.journal(self.root).is_file():
                result["transaction"] = rel.read(tx.journal(self.root))["phase"]
        return {
            **result,
            "offer": {k: self.offer[k] for k in ("version", "notes")}
            if self.offer
            else None,
            "ready": self.ready,
        }

    def action(self, name, confirmed=False):
        if not self.root:
            raise ValueError("此操作需要从 Windows 正式安装目录启动")
        if not self.lock.acquire(blocking=False):
            raise ValueError("更新操作正在执行")
        try:
            if self.stopping:
                raise ValueError("正在退出工作台")
            root = self.root
            current = tx.current(root)[1]
            state = root / tx.STATE
            if name == "check":
                self.ready = False
                self.offer = None
                self.offer = rel.discover(current, rel.trust())
            elif name == "download" and self.offer:
                self.ready = False
                doc = self.offer["doc"].encode()
                sig = self.offer["sig"].encode()
                m = rel.signed(doc, sig, rel.trust(), current)
                if not tx.inspect(root)["supported"]:
                    raise ValueError("当前工作空间无法升级，请查看兼容性报告")
                tx.available(root, tx.estimate(root) * 2 + m["size"] * 3)
                stage = tx.safe(tx.safe(tx.safe(state) / "downloads") / m["sha256"])
                stage.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=stage, delete=False) as f:
                    temp = Path(f.name)
                try:
                    with temp.open("wb") as f:
                        rel.fetch(
                            f"https://github.com/{rel.REPO}/releases/download/v{m['version']}/{m['asset']}",
                            m["size"],
                            f,
                        )
                    # Cross-check unpacked contents now, while the old app is still usable.
                    import zipfile

                    rel.verify_zip(temp, m)
                    with zipfile.ZipFile(temp) as z:
                        unpacked = sum(i.file_size for i in z.infolist())
                    tx.available(
                        root,
                        tx.estimate(root) * 2
                        + unpacked * 2
                        + sum(
                            p.stat().st_size
                            for p in (root / "app").rglob("*")
                            if p.is_file()
                        ),
                    )
                    with tempfile.TemporaryDirectory(dir=stage) as d:
                        rel.extract(temp, Path(d), m)
                    temp.replace(stage / "program.zip")
                    rel.atomic(stage / "update.json", doc)
                    rel.atomic(stage / "update.sig", sig)
                finally:
                    temp.unlink(missing_ok=True)
                self.ready = True
            elif name == "apply" and self.ready and confirmed and self.stop:
                m = rel.signed(
                    self.offer["doc"].encode(),
                    self.offer["sig"].encode(),
                    rel.trust(),
                    current,
                )
                tx.native_quiet(ignore_pid=os.getpid(), root=root)
                helper = Path(sys.executable)
                # A freshly installed server is running out of root/app. Windows will
                # not replace a mapped EXE, even after the web server itself exits.
                if helper.resolve() == (root / tx.EXE).resolve():
                    bootstrap = state / "bootstrap"
                    if not bootstrap.exists():
                        temp = state / ("bootstrap-" + uuid.uuid4().hex)
                        shutil.copytree(helper.parent, temp)
                        if tx.catalog(temp) != tx.catalog(helper.parent):
                            raise ValueError("无法验证独立升级工具")
                        tx.flush_tree(temp)
                        tx.atomic_move(temp, bootstrap)
                    helper = bootstrap / "WorkThread.exe"
                detached(
                    [
                        str(helper),
                        "--maintenance",
                        "finish",
                        str(root),
                        m["sha256"],
                        str(os.getpid()),
                        str(self.port),
                    ]
                )
                self.stopping = True
                self.stop()
            else:
                raise ValueError("请先检查、下载，并确认停写后再更新")
            return self.status()
        finally:
            self.lock.release()


def no_leases(state):
    for lease in state.glob("session-*.lock"):
        try:
            with FileLock(str(lease), timeout=0):
                pass
        except Timeout as e:
            raise ValueError("另一个 WorkThread 会话尚未退出") from e
        lease.unlink(missing_ok=True)


def launch(root, args):
    state = tx.safe(root / tx.STATE)
    state.mkdir(exist_ok=True)
    lease = FileLock(str(state / ("session-" + uuid.uuid4().hex + ".lock")), timeout=0)
    with contextlib.ExitStack() as stack:
        with FileLock(str(state / "install.lock"), timeout=0):
            if (
                tx.journal(root).exists()
                and rel.read(tx.journal(root))["phase"] == "switching"
            ):
                no_leases(state)
                tx.native_quiet(root=root)
                tx.recover(root)
            stack.enter_context(lease)
            exe = tx.current(root)[0] / tx.EXE
            child = subprocess.Popen([str(exe), *args])
        return child.wait()


def wait_for_server(pid):
    # The server drains worker + requests; process exit and session leases prove it stopped.
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if handle:
        try:
            if kernel.WaitForSingleObject(wintypes.HANDLE(handle), 90000) != 0:
                raise ValueError("旧进程未退出，取消升级")
        finally:
            kernel.CloseHandle(wintypes.HANDLE(handle))
    elif ctypes.get_last_error() != 87:  # ERROR_INVALID_PARAMETER: already exited
        raise ValueError("无法确认旧服务已退出")


def finish(root, sha, pid, port):
    import re

    if not re.fullmatch("[a-f0-9]{64}", sha) or not 1 <= port <= 65535:
        raise ValueError("无效的升级请求")
    state = root / tx.STATE
    stage = state / "downloads" / sha
    try:
        wait_for_server(pid)
    except (OSError, ValueError) as e:
        rel.save(state / "result.json", {"error": str(e)})
        raise
    for _ in range(50):
        try:
            with FileLock(str(state / "install.lock"), timeout=0):
                no_leases(state)
            break
        except (Timeout, ValueError):
            time.sleep(0.1)
    try:
        result = tx.apply(
            root,
            stage / "program.zip",
            (stage / "update.json").read_bytes(),
            (stage / "update.sig").read_bytes(),
            rel.trust(),
        )
    except Exception as e:  # noqa: BLE001 - supervisor must persist any failed update
        result = {"error": str(e)}
    rel.save(state / "result.json", result)
    if not tx.journal(root).exists() or rel.read(tx.journal(root))["phase"] in (
        "committed",
        "rolled-back",
    ):
        runner = state / "bootstrap/WorkThread.exe"
        if not runner.exists():
            runner = root / tx.EXE
        detached(
            [
                str(runner),
                "--maintenance",
                "launch",
                str(root),
                "--workspace",
                str(root / "workspace"),
                "serve",
                "--port",
                str(port),
            ]
        )
    if "error" in result:
        raise ValueError(result["error"])


def cli(args):
    mode, *rest = args
    root = tx.safe(Path(rest[0]).absolute()).resolve(strict=True)
    if mode == "inspect":
        return tx.inspect(root)
    if mode == "probe":
        tx.probe(root, Path(rest[1]))
    elif mode == "launch":
        raise SystemExit(launch(root, rest[1:]))
    elif mode == "bootstrap":
        if rest[-1] != "--confirmed" or len(rest) != 4:
            raise ValueError("必须确认关闭 WorkBuddy 和 WorkThread 后继续")
        archive, meta = Path(rest[1]), Path(rest[2])
        return tx.apply(
            root,
            archive,
            (meta / "update.json").read_bytes(),
            (meta / "update.sig").read_bytes().strip(),
            rel.trust(),
        )
    elif mode == "finish":
        finish(root, rest[1], int(rest[2]), int(rest[3]))
    elif mode != "inspect":
        raise ValueError("未知的维护操作")
