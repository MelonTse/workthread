"""Offline RC7 -> RC9 helper. No mailbox, web server, scheduler or network access."""

import argparse
import os
import sys
import time
import uuid
from pathlib import Path

from filelock import FileLock

from ..diagnostics import describe_error
from . import releases as rel
from . import transaction as tx
from .controller import no_leases
from .copying import (  # noqa: F401 - legacy helper API
    Copier,
    Evidence,
    check_copy_log,
    differences,
    native_copy,
    probe_environment,
)

SOURCE = "a74eec51dcd9e889ac4f299d3871409d8aeb6d6e"
SOURCE_EXE = "91d5e1825b91c0c9bee9bd89a31eda92501245ee2c9d5b5e025fe9e9e2d38cae"
TARGET = "49381b86143bbe5ce48b4f47c6d05880927b1b48"
PACKAGE_SHA = "8638fb190766b63422260c9ef4511a70d64839c01fc9ad5bba5d6b3c5a402ae6"
ASSET = "WorkThread-1.0.0rc9-windows-x64.zip"
TOOL_VERSION = "1.0.1"




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
        for name in ("result.json", "request-error.json"):
            previous = tx.safe(root / tx.STATE / name)
            if previous.is_file():
                evidence.save("previous-" + name, rel.read(previous))
        # Only this single-purpose process uses the patched copy implementation.
        tx.copy_workspace = copier
        evidence.event("开始停写检查、快照及版本切换")
        result = tx.apply(root, *inputs, quiet=quiet, check=probe, hook=hook)
        # Publish the committed outcome to the existing settings page. Keep old
        # errors in this tool's diagnostics rather than showing them as current.
        try:
            rel.save(root / tx.STATE / "result.json", result)
            previous_request = tx.safe(root / tx.STATE / "request-error.json")
            if previous_request.is_file():
                rel.save(previous_request, {})
        except OSError:
            evidence.event(
                "版本已经提交，但网页结果提示未能更新；以本次日志和实际版本为准"
            )
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

    def finish(status, code, **extra):
        evidence.save(
            "result.json",
            {
                "status": status,
                "exit_code": code,
                "success": status == "SUCCESS",
                **extra,
            },
        )
        evidence.event(
            f"本次结果：{status}；工具退出码 {code}；日志 {evidence.directory}"
        )
        return code

    try:
        if args.recover:
            if (
                not args.confirmed
                and input("Close WorkThread and WorkBuddy. Type RECOVER: ") != "RECOVER"
            ):
                return finish("CANCELLED", 2)
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
            return finish("RECOVERY_CHECKED", 0, current=tx.current(root)[1])
        with evidence.progress("校验官方 RC7 身份、RC9 签名和安装包"):
            inputs = validate(root, args.release_dir.resolve(strict=True))
        evidence.event("检查通过：官方 RC7 -> 官方 RC9；不连接网络、不自动启动收信")
        if args.inspect:
            return finish("INSPECT_PASSED", 0)
        if args.probe:
            probe_environment(root, evidence)
            return finish("PROBE_PASSED", 0)
        if (
            not args.confirmed
            and input("Close WorkThread and WorkBuddy. Type UPDATE: ") != "UPDATE"
        ):
            evidence.event("已取消，未执行升级")
            return finish("CANCELLED", 2)
        tx.native_quiet(root=root)
        probe_environment(root, evidence)
        result = apply_verified(root, inputs, evidence)
        evidence.event("请从原安装目录启动 Start.cmd，核对网页版本 1.0.0rc9。")
        return finish("SUCCESS", 0, **result)
    except Exception as exc:  # noqa: BLE001 - CLI boundary records errors and exits nonzero
        detail = str(exc) if isinstance(exc, ValueError) else describe_error(exc)
        evidence.save("failure.json", {"type": type(exc).__name__, "error": detail})
        evidence.event("停止操作：" + detail + "；请保留日志，不要删除锁文件或失败快照")
        return finish("FAILED", 1, error=detail, error_type=type(exc).__name__)


if __name__ == "__main__":
    raise SystemExit(main())
