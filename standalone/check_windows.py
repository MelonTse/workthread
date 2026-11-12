"""Actual RC7/RC9 ZIPs and synthetic data only; never uses an existing installation."""

import argparse
import ctypes
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from check_windows_upgrade import seed_old
from test_updates import records

from workthread.updating import copy_security as security
from workthread.updating import releases as rel
from workthread.updating import standalone as helper
from workthread.updating import transaction as tx


def download(url, path):
    for attempt in range(3):
        try:
            with (
                urllib.request.urlopen(url, timeout=90) as response,
                path.open("wb") as stream,
            ):
                shutil.copyfileobj(response, stream)
            return
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2)


def run(tool, root, release, logs, *flags, expected=0, detached=False, input_text=None):
    args = [
        str(tool),
        "--install-root",
        str(root),
        "--release-dir",
        str(release),
        "--logs-dir",
        str(logs),
        *flags,
    ]
    log = logs.parent / (logs.name + ".console.txt")
    with log.open("wb") as stream:
        p = subprocess.Popen(
            args,
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=(
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
            if detached
            else 0,
        )
        if input_text is not None:
            p.communicate(input_text.encode("utf-8"), timeout=300)
        else:
            p.wait(300)
        code = p.returncode
    if code != expected:
        raise AssertionError(
            (code, expected, log.read_text(encoding="utf-8", errors="replace")[-5000:])
        )
    result = rel.read(next(logs.glob("*/result.json")))
    assert result["exit_code"] == expected
    if "--inspect" in flags:
        assert result["status"] == "INSPECT_PASSED" and not result["success"]
    if expected == 1:
        assert result["status"] == "FAILED" and not result["success"]
    return log


def health(root, version):
    # Doctor runs no receiving/AI workers; use the stable launch path, same as original shortcuts.
    for name in tx.SPACES:
        h = json.loads(
            subprocess.check_output(
                [str(root / tx.EXE), "--workspace", str(root / name), "doctor"],
                encoding="utf-8",
            )
        )
        assert h["ok"] and h["version"] == version


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--tool", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--require-standard-user", action="store_true")
    args = a.parse_args()
    if os.name != "nt":
        a.error("Native Windows only")
    administrator = bool(ctypes.windll.shell32.IsUserAnAdmin())
    if args.require_standard_user:
        assert not administrator, "Expected a non-administrator token"
    tool = args.tool.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    assets = out / "release"
    assets.mkdir()
    base = "https://github.com/MelonTse/workthread/releases/download/"
    for name in (helper.ASSET, "update.json", "update.sig"):
        download(base + "v1.0.0rc9/" + name, assets / name)
    assert rel.digest(assets / helper.ASSET) == helper.PACKAGE_SHA
    old = out / "rc7.zip"
    download(base + "v1.0.0rc7/WorkThread-1.0.0rc7-windows-x64.zip", old)
    assert (
        rel.digest(old)
        == "752d7db885a05cf054cad0c313e4a40214c7c0dd6be0099cfa99e08121af211d"
    )
    # Source-side fault injection still uses the official public key, never a test signing key.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    rel.trust = lambda: Ed25519PublicKey.from_public_bytes(
        bytes.fromhex((ROOT / "packaging/release-public.hex").read_text().strip())
    )
    with tempfile.TemporaryDirectory(prefix="WorkThread 合成验收 ") as temp:
        temp = Path(temp)
        with zipfile.ZipFile(old) as z:
            z.extractall(temp / "original")
        seed = temp / "original/WorkThread-1.0.0rc7-windows-x64"
        for n in tx.SPACES:
            seed_old(seed / tx.EXE, seed / n)
            subprocess.run(
                [str(seed / tx.EXE), "--workspace", str(seed / n), "ai-prepare"],
                check=True,
            )
            (seed / n / "agent-workspace/.hidden-synthetic.txt").write_text(
                "synthetic hidden text", encoding="utf-8"
            )
            subprocess.run(
                [
                    "attrib",
                    "+H",
                    str(seed / n / "agent-workspace/.hidden-synthetic.txt"),
                ],
                check=True,
            )
            (seed / n / "agent-workspace/empty-dir").mkdir()
            with (seed / n / "agent-workspace/local.md:synthetic-stream").open(
                "w"
            ) as f:
                f.write("synthetic ADS")
        cases = []

        def fresh(name):
            root = temp / name
            shutil.copytree(seed, root)
            # Restore NTFS attributes/streams that shutil does not guarantee.
            for n in tx.SPACES:
                subprocess.run(
                    [
                        "attrib",
                        "+H",
                        str(root / n / "agent-workspace/.hidden-synthetic.txt"),
                    ],
                    check=True,
                )
                with (root / n / "agent-workspace/local.md:synthetic-stream").open(
                    "w"
                ) as f:
                    f.write("synthetic ADS")
            return root

        for mode in ("console", "detached", "prior-failed-update"):
            root = fresh("用户 " + mode)
            if mode == "prior-failed-update":
                state = root / tx.STATE
                shutil.copytree(root / "app", state / "bootstrap")
                old_snapshot = (
                    state / "transactions" / ("a" * 32) / "snapshot/workspace"
                )
                old_snapshot.mkdir(parents=True)
                rel.save(state / "result.json", {"error": "快照内容已变化"})
                rel.save(
                    state / "request-error.json",
                    {"message": "synthetic old HTTP failure"},
                )
                prior_bootstrap = rel.digest(state / "bootstrap/WorkThread.exe")
            before = records(root)
            permissions = {n: security.inventory(root / n) for n in tx.SPACES}
            run(tool, root, assets, out / (mode + "-inspect"), "--inspect")
            assert records(root) == before
            run(
                tool,
                root,
                assets,
                out / (mode + "-apply"),
                "--confirmed",
                detached=mode == "detached",
            )
            assert tx.current(root)[1]["commit_sha"] == helper.TARGET
            assert records(root) == before
            assert {n: security.inventory(root / n) for n in tx.SPACES} == permissions
            assert rel.read(root / tx.STATE / "result.json")["version"] == "1.0.0rc9"
            if mode == "prior-failed-update":
                assert old_snapshot.is_dir() and not list(old_snapshot.iterdir())
                assert rel.digest(state / "bootstrap/WorkThread.exe") == prior_bootstrap
                assert rel.read(state / "request-error.json") == {}
                previous = next(
                    (out / (mode + "-apply")).glob("*/previous-result.json")
                )
                assert rel.read(previous)["error"] == "快照内容已变化"
            for n in tx.SPACES:
                assert (
                    root / n / "agent-workspace/local.md:synthetic-stream"
                ).read_text() == "synthetic ADS"
                assert (root / n / "agent-workspace/empty-dir").is_dir()
                assert (
                    root / n / "agent-workspace/.hidden-synthetic.txt"
                ).stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN
            health(root, "1.0.0rc9")
            # Start the fixed entry as a second check of program availability, with all mailbox accounts synthetic/disabled.
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            proc = subprocess.Popen(
                [
                    str(root / tx.EXE),
                    "--workspace",
                    str(root / "workspace"),
                    "serve",
                    "--port",
                    str(port),
                ]
            )
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/api/v1/system/status", timeout=1
                        ) as response:
                            h = json.load(response)
                        assert h["version"] == "1.0.0rc9"
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise AssertionError("updated service not available")
            finally:
                subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-Command",
                        r"""$ErrorActionPreference='Stop'
# The fixed launcher can expose an 8.3 profile path. Match only this test's
# unique temporary directory suffix in command lines, not a long-path prefix.
function Owned {
  @(Get-CimInstance Win32_Process -Filter "Name='WorkThread.exe'" | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains($env:WT_QA_ID)
  })
}
$owned = @(Owned)
if ($owned.Count -eq 0) { throw 'Synthetic HTTP service process was not identified' }
$owned | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
for ($i=0; $i -lt 50; $i++) {
  if (@(Owned).Count -eq 0) { exit 0 }
  Start-Sleep -Milliseconds 200
}
throw 'Synthetic processes still running'
""",
                    ],
                    env=dict(os.environ, WT_QA_ID=temp.name.rsplit(" ", 1)[-1]),
                    check=True,
                )
                proc.wait(30)
            cases.append(
                mode
                + ": official RC7 -> RC9; all records, files, ADS, hidden/empty, fixed entry and HTTP verified"
            )
        root = fresh("cancelled")
        before = records(root)
        run(tool, root, assets, out / "cancelled", expected=2, input_text="update\n")
        assert (
            records(root) == before
            and tx.current(root)[1]["commit_sha"] == helper.SOURCE
        )
        assert (
            rel.read(next((out / "cancelled").glob("*/result.json")))["status"]
            == "CANCELLED"
        )
        cases.append(
            "cancelled: lowercase confirmation refused; overall exit code 2 recorded; RC7 intact"
        )
        for kind in ("signature", "archive"):
            root = fresh(kind)
            before = records(root)
            bad = temp / (kind + "-release")
            shutil.copytree(assets, bad)
            if kind == "signature":
                (bad / "update.sig").write_bytes(b"AAAA")
            else:
                with (bad / helper.ASSET).open("ab") as f:
                    f.write(b"corrupt")
            run(tool, root, bad, out / kind, "--confirmed", expected=1)
            assert (
                records(root) == before
                and tx.current(root)[1]["commit_sha"] == helper.SOURCE
            )
            health(root, "1.0.0rc7")
            cases.append(
                kind + ": rejected; original RC7/data intact and doctor passed"
            )
        for kind in ("empty", "acl", "mid-switch", "crash", "post-crash-write"):
            root = fresh(kind)
            before = records(root)
            if kind in ("crash", "post-crash-write"):
                script = temp / "fault.py"
                script.write_text(
                    """import os,sys\nfrom pathlib import Path\nfrom workthread.updating import standalone as h,releases as r\nfrom cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey\nr.trust=lambda:Ed25519PublicKey.from_public_bytes(bytes.fromhex(Path(sys.argv[4]).read_text().strip()))\nroot=Path(sys.argv[1])\ndef crash(step):\n if step=="placed-workspace":os._exit(77)\nh.apply_verified(root,h.validate(root,Path(sys.argv[2])),h.Evidence(Path(sys.argv[3])),hook=crash)\n""",
                    encoding="utf-8",
                )
                p = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        str(root),
                        str(assets),
                        str(out / (kind + "-fault")),
                        str(ROOT / "packaging/release-public.hex"),
                    ],
                    env=dict(
                        os.environ,
                        PYTHONPATH=str(ROOT / "src"),
                        PYTHONIOENCODING="utf-8",
                    ),
                    timeout=300,
                    check=False,
                )
                assert p.returncode == 77
                if kind == "post-crash-write":
                    (root / "workspace/new-business.txt").write_text("must keep")
                    run(
                        tool,
                        root,
                        assets,
                        out / (kind + "-recover"),
                        "--recover",
                        "--confirmed",
                        expected=1,
                    )
                    assert (
                        root / "workspace/new-business.txt"
                    ).read_text() == "must keep"
                    assert list(
                        (root / tx.STATE / "transactions").glob(
                            "*/old/workspace/data/workthread.sqlite3"
                        )
                    )
                    cases.append(kind + ": recovery refused; both data copies retained")
                    continue
                run(
                    tool,
                    root,
                    assets,
                    out / (kind + "-recover"),
                    "--recover",
                    "--confirmed",
                )
            else:

                def execute(src, dst, folder, kind=kind):
                    if kind == "empty":
                        dst.mkdir(parents=True)
                        return 0
                    result = helper.native_copy(src, dst, folder)
                    return 8 if kind == "acl" else result

                def fault(step, kind=kind):
                    if kind == "mid-switch" and step == "placed-workspace":
                        raise OSError("synthetic switch failure")

                try:
                    helper.apply_verified(
                        root,
                        helper.validate(root, assets),
                        helper.Evidence(out / (kind + "-fault")),
                        execute=execute,
                        hook=fault,
                    )
                except (ValueError, OSError):
                    pass
                else:
                    raise AssertionError("fault did not stop upgrade")
            assert (
                tx.current(root)[1]["commit_sha"] == helper.SOURCE
                and records(root) == before
            )
            health(root, "1.0.0rc7")
            cases.append(
                kind + ": original RC7/data restored or untouched; doctor passed"
            )
        acl_source = temp / "custom-acl-source"
        acl_source.mkdir()
        (acl_source / "sensitive.txt").write_text("synthetic content", encoding="utf-8")
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "$a=Get-Acl -LiteralPath $env:WT_ACL_FIXTURE; $a.SetAccessRuleProtection($true,$true); Set-Acl -LiteralPath $env:WT_ACL_FIXTURE -AclObject $a",
            ],
            env=dict(os.environ, WT_ACL_FIXTURE=str(acl_source)),
            check=True,
        )
        acl_before = security.inventory(acl_source)
        acl_target = temp / "custom-acl-target"
        acl_log = out / "custom-acl-refusal"
        acl_log.mkdir()
        try:
            helper.native_copy(acl_source, acl_target, acl_log)
        except ValueError as exc:
            assert "未复制业务内容" in str(exc)
        else:
            raise AssertionError("Different inherited permissions were not refused")
        assert not (acl_target / "sensitive.txt").exists()
        assert security.inventory(acl_source) == acl_before
        cases.append(
            "custom-acl: refused before business content copy; source permissions unchanged"
        )
        report = {
            "passed": cases,
            "source_sha": helper.SOURCE,
            "target_sha": helper.TARGET,
            "environment": "Windows Server 2022 x64; synthetic only; Windows 10 client pending",
            "administrator": administrator,
        }
        (out / "WINDOWS_REPORT.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for row in cases:
            print("PASS " + row)


if __name__ == "__main__":
    main()
