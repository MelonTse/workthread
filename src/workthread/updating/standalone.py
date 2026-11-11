"""Offline RC7 -> RC9 helper. No mailbox, web server, scheduler or network access."""

import argparse
import contextlib
import ctypes
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from filelock import FileLock

from ..diagnostics import describe_error
from . import releases as rel
from . import transaction as tx
from .controller import no_leases

SOURCE = "a74eec51dcd9e889ac4f299d3871409d8aeb6d6e"
SOURCE_EXE = "91d5e1825b91c0c9bee9bd89a31eda92501245ee2c9d5b5e025fe9e9e2d38cae"
TARGET = "49381b86143bbe5ce48b4f47c6d05880927b1b48"
PACKAGE_SHA = "8638fb190766b63422260c9ef4511a70d64839c01fc9ad5bba5d6b3c5a402ae6"
ASSET = "WorkThread-1.0.0rc9-windows-x64.zip"
TOOL_VERSION = "1.0.0"


class Evidence:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=False)
        self.serial = 0

    def event(self, message):
        line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + message
        print(line, flush=True)
        with (self.directory / "progress.txt").open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

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


def native_copy(src, dst, folder):
    exe = system_robocopy()
    args = [
        str(exe),
        str(src),
        str(dst),
        "/E",
        "/COPY:DATS",
        "/DCOPY:DAT",
        "/XJ",
        "/R:0",
        "/W:0",
        "/NFL",
        "/NDL",
        "/NP",
        "/UNILOG:" + str(folder / "robocopy.txt"),
    ]
    rel.save(
        folder / "command.json",
        {
            "executable": str(exe),
            "args": args,
            "pid": os.getpid(),
            "tool_version": TOOL_VERSION,
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


def validate(root, release):
    bundle, current = tx.current(root)
    if current["version"] == "1.0.0rc9" and current["commit_sha"] == TARGET:
        raise ValueError("已经是官方 RC9，不需要再次升级")
    if (current["version"], current["commit_sha"]) != ("1.0.0rc7", SOURCE):
        raise ValueError("此工具只支持官方 RC7 构建，未修改原安装")
    if rel.digest(bundle / tx.EXE) != SOURCE_EXE:
        raise ValueError("原 RC7 可执行文件与官方指纹不符，停止升级")
    if not tx.inspect(root)["supported"]:
        raise ValueError("工作空间或数据库版本不受支持，停止升级")
    archive = release / ASSET
    doc, sig = (
        (release / "update.json").read_bytes(),
        (release / "update.sig").read_bytes().strip(),
    )
    key = rel.trust()
    manifest = rel.signed(doc, sig, key, current)
    if (
        manifest["version"],
        manifest["commit_sha"],
        manifest["sha256"],
        manifest["asset"],
    ) != ("1.0.0rc9", TARGET, PACKAGE_SHA, ASSET):
        raise ValueError("签名清单不是本工具允许的官方 RC9 安装包")
    rel.verify_zip(archive, manifest)
    return archive, doc, sig, key


def apply_verified(
    root,
    inputs,
    evidence,
    *,
    execute=native_copy,
    quiet=None,
    check=tx.run_probe,
    hook=lambda _: None,
):
    copier = Copier(evidence, execute)
    original = tx.copy_workspace

    def probe(bundle, trial, logical):
        with evidence.progress("预检副本 " + logical.name + "（不收信、不运行 AI）"):
            check(bundle, trial, logical)

    try:
        # Only this single-purpose process uses the patched copy implementation.
        tx.copy_workspace = copier
        evidence.event("开始停写检查、快照及版本切换")
        result = tx.apply(root, *inputs, quiet=quiet, check=probe, hook=hook)
        evidence.event("SUCCESS：版本已切换，两个工作空间健康检查通过")
        evidence.save("result.json", {"success": True, **result})
        return result
    except Exception as exc:
        detail = str(exc) if isinstance(exc, ValueError) else describe_error(exc)
        evidence.save(
            "result.json",
            {"success": False, "error": detail, "error_type": type(exc).__name__},
        )
        evidence.event("FAILED：" + detail)
        raise
    finally:
        tx.copy_workspace = original


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-root", type=Path)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--logs-dir", type=Path)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument(
        "--confirmed", action="store_true", help="For explicit automation approval only"
    )
    args = parser.parse_args(argv)
    if os.name != "nt":
        parser.error("Windows x64 only")
    root = tx.safe(
        args.install_root
        or Path(input("Install root (for example G:\\WorkThread): ").strip().strip('"'))
    ).resolve(strict=True)
    tool = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    if tool.is_relative_to(root):
        parser.error("Extract this helper outside the existing installation")
    logs = (args.logs_dir or tool.parent / "logs").resolve()
    if logs.is_relative_to(root):
        parser.error("Diagnostic logs must be outside the existing installation")
    evidence = Evidence(logs / (time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]))
    evidence.event("独立升级工具 " + TOOL_VERSION + "；安装目录 " + str(root))
    try:
        if args.recover:
            if (
                not args.confirmed
                and input("Close WorkThread and WorkBuddy. Type RECOVER: ") != "RECOVER"
            ):
                return 2
            tx.native_quiet(root=root)
            with FileLock(str(root / tx.STATE / "install.lock"), timeout=0):
                no_leases(root / tx.STATE)
                tx.recover(root)
            evidence.save(
                "result.json",
                {"recovery_checked": True, "current": tx.current(root)[1]},
            )
            evidence.event(
                "恢复检查完成。已提交升级不会回退；发现新写入时会停止并保留双方数据。"
            )
            return 0
        with evidence.progress("校验官方 RC7 身份、RC9 签名和安装包"):
            inputs = validate(root, args.release_dir.resolve(strict=True))
        evidence.event("检查通过：官方 RC7 -> 官方 RC9；不连接网络、不自动启动收信")
        if args.inspect:
            return 0
        if args.probe:
            probe_environment(root, evidence)
            return 0
        if (
            not args.confirmed
            and input("Close WorkThread and WorkBuddy. Type UPDATE: ") != "UPDATE"
        ):
            evidence.event("已取消，未执行升级")
            return 2
        tx.native_quiet(root=root)
        probe_environment(root, evidence)
        apply_verified(root, inputs, evidence)
        evidence.event("请从原安装目录启动 Start.cmd，核对网页版本 1.0.0rc9。")
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary records errors and exits nonzero
        detail = str(exc) if isinstance(exc, ValueError) else describe_error(exc)
        evidence.save("failure.json", {"type": type(exc).__name__, "error": detail})
        evidence.event("停止操作：" + detail + "；请保留日志，不要删除锁文件或失败快照")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
