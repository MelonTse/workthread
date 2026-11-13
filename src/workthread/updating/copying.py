"""Verified Windows workspace copies shared by web and offline updates."""

import contextlib
import ctypes
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from . import copy_security
from . import releases as rel
from . import transaction as tx


class Evidence:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=False)
        self.serial = 0

    def event(self, message):
        line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + message
        with (self.directory / "progress.txt").open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
        # A detached/redirected or legacy-codepage console is only a display sink.
        # Keep the durable UTF-8 evidence even when that sink cannot render Chinese.
        with contextlib.suppress(UnicodeError, OSError):
            print(line, flush=True)

    @contextlib.contextmanager
    def progress(self, label):
        self.event(label)
        done = threading.Event()

        def heartbeat():
            while not done.wait(10):
                self.event("仍在执行：" + label + "；请保持窗口打开")

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            yield
        finally:
            done.set()
            thread.join()

    def save(self, name, value):
        rel.save(self.directory / name, value)


def differences(expected, actual):
    return {
        "missing": sorted(expected.keys() - actual.keys()),
        "extra": sorted(actual.keys() - expected.keys()),
        "changed": sorted(
            k for k in expected.keys() & actual.keys() if expected[k] != actual[k]
        ),
    }


@contextlib.contextmanager
def system_environment():
    """PyInstaller's DLL search directory must not override system utility DLLs."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetDllDirectoryW.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
    kernel.GetDllDirectoryW.restype = ctypes.c_uint32
    kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
    kernel.SetDllDirectoryW.restype = ctypes.c_int
    buffer = ctypes.create_unicode_buffer(32768)
    size = kernel.GetDllDirectoryW(len(buffer), buffer)
    if size >= len(buffer):
        raise ValueError("无法读取外部工具 DLL 环境，停止复制")
    prior = buffer.value or None
    if not kernel.SetDllDirectoryW(None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("_PYI_") and k != "_MEIPASS2"
        }
        frozen = getattr(sys, "_MEIPASS", None)
        if frozen:
            env["PATH"] = os.pathsep.join(
                p
                for p in env.get("PATH", "").split(os.pathsep)
                if not p.casefold().startswith(str(frozen).casefold())
            )
        yield env
    finally:
        if not kernel.SetDllDirectoryW(prior):
            raise ctypes.WinError(ctypes.get_last_error())


def system_robocopy():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetSystemDirectoryW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    kernel.GetSystemDirectoryW.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(32768)
    size = kernel.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < size < len(buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    return Path(buffer.value) / "robocopy.exe"


def check_copy_log(code, folder):
    log_file = folder / "robocopy.txt"
    if not log_file.is_file():
        rel.save(
            folder / "process-result.json", {"exit_code": code, "log_missing": True}
        )
        raise ValueError("复制程序没有生成完整日志，停止切换")
    log = log_file.read_text(encoding="utf-16", errors="replace")
    reported_error = bool(re.search(r"\(0x(?!00000000)[0-9a-fA-F]{8}\)", log))
    rel.save(
        folder / "process-result.json",
        {
            "exit_code": code,
            "reported_error": reported_error,
        },
    )
    if reported_error:
        raise ValueError(
            f"复制日志报告系统错误（子进程返回 {code}），停止切换；请查看 robocopy.txt"
        )


def native_copy(src, dst, folder):
    security = copy_security.prepare(src, dst, folder)
    exe = system_robocopy()
    args = [
        str(exe),
        str(src),
        str(dst),
        "/E",
        "/COPY:DAT",
        "/DCOPY:DAT",
        "/XJ",
        "/R:0",
        "/W:0",
        "/NFL",
        "/NDL",
        "/NP",
        "/IS",
        "/IT",
        "/UNILOG:" + str(folder / "robocopy.txt"),
    ]
    rel.save(
        folder / "command.json",
        {
            "executable": str(exe),
            "args": args,
            "pid": os.getpid(),
            "tool_version": "shared-v2",
            "frozen": bool(getattr(sys, "frozen", False)),
        },
    )
    # Supply all three standard handles, even when the parent has no console.
    with (
        system_environment() as env,
        (folder / "process-output.bin").open("wb") as output,
    ):
        result = subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=folder,
            timeout=1800,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    check_copy_log(result.returncode, folder)
    if result.returncode in (0, 1):
        copy_security.verify(src, dst, security, folder)
    return result.returncode


class Copier:
    def __init__(self, evidence, execute=native_copy):
        self.evidence, self.execute = evidence, execute

    def __call__(self, src, dst):
        e = self.evidence
        e.serial += 1
        folder = e.directory / f"copy-{e.serial:02d}"
        folder.mkdir()
        e.event(f"复制 {e.serial}：{src} -> {dst}")
        before = tx.catalog(src)
        rel.save(folder / "source-before.json", before)
        code = None
        try:
            with e.progress("复制及校验 " + src.name):
                code = self.execute(src, dst, folder)
                snapshot = tx.catalog(dst) if dst.exists() else {}
                after = tx.catalog(src)
                rel.save(folder / "destination.json", snapshot)
                rel.save(folder / "source-after.json", after)
                diff = differences(before, snapshot)
                source_diff = differences(before, after)
                rel.save(
                    folder / "comparison.json",
                    {
                        "exit_code": code,
                        "destination": diff,
                        "source_during_copy": source_diff,
                        "source_entries": len(before),
                        "destination_entries": len(snapshot),
                    },
                )
                if code not in (0, 1):
                    raise ValueError(
                        f"复制程序返回 {code}，已停止。即使内容已落地也不能忽略权限或其他复制错误；请查看 {folder / 'robocopy.txt'}"
                    )
                if any(diff.values()):
                    category = (
                        "复制结果为空"
                        if before and not snapshot
                        else "复制结果缺失、多出或内容不一致"
                    )
                    raise ValueError(
                        category
                        + f"，未通过校验；差异清单：{folder / 'comparison.json'}"
                    )
                if any(source_diff.values()):
                    raise ValueError(
                        "复制期间原目录发生变化，停止切换；请关闭写入程序，查看差异清单"
                    )
        except BaseException:
            rel.save(folder / "attempt.json", {"exit_code": code, "completed": False})
            raise
        rel.save(folder / "attempt.json", {"exit_code": code, "completed": True})
        e.event(f"复制 {e.serial} 完成：{len(before)} 项，原目录和副本校验一致")


def probe_environment(root, evidence):
    directory = root.parent / ("WorkThread-Upgrade-Probe-" + uuid.uuid4().hex)
    source = directory / "source"
    source.mkdir(parents=True, exist_ok=False)
    (source / "empty-dir").mkdir()
    (source / "plain.txt").write_text(
        "WorkThread synthetic copy probe", encoding="utf-8"
    )
    (source / "中文 空格.txt").write_text("合成文件，不含业务数据", encoding="utf-8")
    hidden = source / "hidden.txt"
    hidden.write_text("synthetic hidden data", encoding="utf-8")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    kernel.SetFileAttributesW.restype = ctypes.c_int
    if not kernel.SetFileAttributesW(str(hidden), 2):
        raise ctypes.WinError(ctypes.get_last_error())
    evidence.event("同盘合成复制自检：" + str(directory))
    Copier(evidence)(source, directory / "destination")
    evidence.event("合成自检通过；未读取或复制业务工作空间。合成目录保留以便排查。")
