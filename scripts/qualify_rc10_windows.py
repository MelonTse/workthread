"""RC9 -> RC10 -> next web update, isolated Windows fixtures and ephemeral signing authority.

The shipping ZIP is built separately without the fixture transport or key. Never publish these ZIPs.
"""

import argparse
import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from workthread.updating import releases as rel
from workthread.updating import transaction as tx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from check_windows_upgrade import seed_old
from qualify_fresh_windows import build
from test_updates import records

RC9 = "49381b86143bbe5ce48b4f47c6d05880927b1b48"
OLD_HASH = "8638fb190766b63422260c9ef4511a70d64839c01fc9ad5bba5d6b3c5a402ae6"
NEXT = "d" * 40


def run(args, **kw):
    return subprocess.run([str(x) for x in args], check=True, **kw)


def prepare(out):
    source = out / "fixture-source"
    archive = out / "source.zip"
    run(["git", "archive", "--format=zip", "-o", archive, "HEAD"], cwd=ROOT)
    with zipfile.ZipFile(archive) as z:
        z.extractall(source)
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    key = Ed25519PrivateKey.generate()
    secret, public = out / "fixture.raw", out / "release-public.hex"
    secret.write_bytes(key.private_bytes_raw())
    public.write_text(key.public_key().public_bytes_raw().hex(), encoding="ascii")
    env = dict(
        os.environ,
        WORKTHREAD_BUILD_PUBLIC_KEY=str(public),
        WORKTHREAD_SIGNING_KEY_FILE=str(secret),
    )
    newer = build(source, out, env, NEXT, "1.0.0rc11")
    feed = out / "feed"
    run(
        [
            sys.executable,
            ROOT / "scripts/sign_update.py",
            newer,
            "--source",
            "1.0.0rc10@" + sha,
            "--output",
            feed,
        ],
        env=env,
    )
    names = ["update.json", "update.sig", newer.name]
    shutil.move(newer, feed / newer.name)
    rel.save(
        feed / "releases.json",
        [
            {
                "tag_name": "v1.0.0rc11",
                "draft": False,
                "prerelease": True,
                "body": "Synthetic next version. NOT A RELEASE.",
                "assets": [{"name": n} for n in names],
            }
        ],
    )
    # Only in this disposable checkout: exact URL -> local signed fixture mapping.
    links = {
        "https://api.github.com/repos/MelonTse/workthread/releases?per_page=30&page=1": "releases.json"
    }
    links.update(
        {
            "https://github.com/MelonTse/workthread/releases/download/v1.0.0rc11/"
            + n: n
            for n in names
        }
    )
    with (source / "src/workthread/updating/releases.py").open(
        "a", encoding="utf-8"
    ) as f:
        f.write("\n\ndef fetch(url, limit, out=None):\n")
        f.write(f"    data = (Path({str(feed)!r}) / {links!r}[url]).read_bytes()\n")
        f.write(
            "    assert len(data) <= limit\n    if out is None: return data\n    out.write(data)\n"
        )
    candidate = build(source, out, env, sha, "1.0.0rc10")
    meta = out / "transition"
    run(
        [
            sys.executable,
            ROOT / "scripts/sign_update.py",
            candidate,
            "--source",
            "1.0.0rc9@" + RC9,
            "--output",
            meta,
        ],
        env=env,
    )
    old = out / "rc9.zip"
    url = "https://github.com/MelonTse/workthread/releases/download/v1.0.0rc9/WorkThread-1.0.0rc9-windows-x64.zip"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as r, old.open("wb") as f:
                shutil.copyfileobj(r, f)
            assert rel.digest(old) == OLD_HASH
            break
        except (OSError, AssertionError):
            if attempt == 2:
                raise
    # Private key unnecessary after signing; never part of uploaded evidence.
    secret.unlink()
    rel.save(
        out / "fixture-info.json",
        {
            "rc10_commit": sha,
            "official_rc9_sha256": OLD_HASH,
            "qualification_only": True,
            "rc10_sha256": rel.digest(candidate),
        },
    )


def stop_fixture(root):
    # Kill only processes from this synthetic test directory; never touches a real installation.
    run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "$ErrorActionPreference='Stop'; Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'WorkThread.exe' -and $_.CommandLine -and $_.CommandLine.Contains($env:WT_QA_MARKER) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }",
        ],
        env=dict(os.environ, WT_QA_MARKER=root.name),
    )
    time.sleep(1)


def health(root, version):
    for n in tx.SPACES:
        data = json.loads(
            subprocess.check_output(
                [str(root / tx.EXE), "--workspace", str(root / n), "doctor"],
                encoding="utf-8",
            )
        )
        assert data["ok"] and data["version"] == version, data


def verify_web_records(root, before, evidence):
    """Account only for the real worker's verified rejection of our invalid fixture.

    Do not ignore queue/receipt directories or database tables. Service identity files
    are checked separately because a restarted service necessarily has a new identity.
    """
    from copy import deepcopy

    from workthread.updating.copying import differences

    after = records(root)
    rel.save(evidence, [differences(a, b) for a, b in zip(before, after)])
    expected = deepcopy(before)
    actual = deepcopy(after)
    for index, name in enumerate(tx.SPACES):
        old, new = expected[index * 2 + 1], actual[index * 2 + 1]
        for catalog in (old, new):
            catalog.pop(".workthread-service.json", None)
            catalog.pop(".workthread-service.lock", None)
        if name == "workspace":
            identity = rel.read(root / name / ".workthread-service.json")
            assert set(identity) == {"port", "instance_id"}
            assert 0 < identity["port"] < 65536 and len(identity["instance_id"]) == 48
            assert (root / name / ".workthread-service.lock").stat().st_size == 0
            unread = "agent-workspace/exchange/outputs/unread.json"
            if unread not in new:
                extra = set(new) - set(old)
                payloads = [
                    p
                    for p in extra
                    if p.startswith("agent-workspace/exchange/quarantine/")
                    and not p.endswith(".error.json")
                ]
                assert len(payloads) == 1, extra
                payload = payloads[0]
                error = payload[:-5] + ".error.json"
                assert extra == {payload, error}, extra
                assert new[payload] == old[unread], (
                    "Rejected synthetic payload lost or changed"
                )
                assert rel.read(root / name / error)["error"] == "无效的任务编号"
                new[unread] = new.pop(payload)
                new.pop(error)
    assert actual == expected, [differences(a, b) for a, b in zip(expected, actual)]


def web_update(root, out, before):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
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
        for _ in range(200):
            if proc.poll() is not None:
                raise RuntimeError(
                    f"RC10 entry exited before serving: {proc.returncode}"
                )
            try:
                with urllib.request.urlopen(
                    url + "/api/v1/software-update", timeout=2
                ) as r:
                    status = json.load(r)
                assert status["current"] == "1.0.0rc10" and status["enabled"]
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("RC10 server did not start")
        run(
            [
                "node",
                ROOT / "scripts/check_update_browser.cjs",
                os.environ["WT_QA_PLAYWRIGHT"],
                os.environ["WT_QA_CHROME"],
                url,
                "1.0.0rc11",
            ],
            timeout=240,
        )
        assert tx.current(root)[1]["version"] == "1.0.0rc11"
    finally:
        stop_fixture(root)
        proc.wait(timeout=30)
    health(root, "1.0.0rc11")
    verify_web_records(root, before, out / (root.name + "-record-differences.json"))


def exercise(out):
    assert not ctypes.windll.shell32.IsUserAnAdmin(), (
        "Must run with a standard user token"
    )
    cases = []
    with zipfile.ZipFile(out / "rc9.zip") as z:
        z.extractall(out / "original")
    seed = out / "original/WorkThread-1.0.0rc9-windows-x64"
    for n in tx.SPACES:
        seed_old(seed / tx.EXE, seed / n)
        run([seed / tx.EXE, "--workspace", seed / n, "ai-prepare"])
        (seed / n / "agent-workspace/empty-dir").mkdir()
    before = records(seed)
    candidate = out / "WorkThread-1.0.0rc10-windows-x64.zip"
    with zipfile.ZipFile(candidate) as z:
        z.extractall(out / "new-tool")
    helper = out / "new-tool" / candidate.stem / tx.EXE
    root = out / "用户 升级 RC9"
    shutil.copytree(seed, root)
    # Old failed bootstrap remains present; the transition must not invoke it.
    shutil.copytree(root / "app", root / tx.STATE / "bootstrap")
    old_bootstrap = rel.digest(root / tx.STATE / "bootstrap/WorkThread.exe")
    run(
        [
            helper,
            "--maintenance",
            "bootstrap",
            root,
            candidate,
            out / "transition",
            "--confirmed",
        ],
        timeout=900,
    )
    assert rel.read(root / tx.STATE / "result.json")["status"] == "SUCCESS"
    assert records(root) == before
    assert rel.digest(root / tx.STATE / "bootstrap/WorkThread.exe") == old_bootstrap
    health(root, "1.0.0rc10")
    cases.append(
        "official RC9 -> RC10 via new executable; both workspaces, all tables, queue, drafts, custom files, backup, stable entry"
    )
    web_update(root, out, before)
    cases.append(
        "upgraded RC10 -> signed test rc11 via real browser; cancel, confirm, handoff, reconnect, data preserved"
    )
    fresh = out / "全新 RC10 安装"
    with zipfile.ZipFile(candidate) as z:
        z.extractall(out / "fresh-extracted")
    shutil.move(out / "fresh-extracted" / candidate.stem, fresh)
    run(["cmd.exe", "/d", "/c", "Install.cmd", "/quiet"], cwd=fresh, timeout=120)
    health(fresh, "1.0.0rc10")
    for n in tx.SPACES:
        seed_old(fresh / tx.EXE, fresh / n)
    assert not (fresh / tx.STATE / "base").exists()
    rel.save(fresh / tx.STATE / "result.json", {"version": "1.0.0rc10"})
    before_fresh = records(fresh)
    web_update(fresh, out, before_fresh)
    cases.append(
        "fresh RC10 first web update without pre-created base/bootstrap; stable entry and data preserved"
    )
    # Native transaction fault tests with actual binaries and the same signed fixture.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    key = Ed25519PublicKey.from_public_bytes(
        bytes.fromhex((out / "release-public.hex").read_text())
    )
    doc = (out / "transition/update.json").read_bytes()
    sig = (out / "transition/update.sig").read_bytes()
    for fault in [
        "corrupt",
        "signature",
        "disk",
        "copy",
        "trial",
        "placed-workspace",
        "placed-acceptance",
        "pointer",
        "new-write",
    ]:
        from contextlib import ExitStack
        from unittest.mock import patch

        target = out / ("fault-" + fault)
        shutil.copytree(seed, target)
        args = (candidate, doc, sig, key)

        class PowerLoss(BaseException):
            pass

        def hook(step, fault=fault):
            if step == fault or (fault == "new-write" and step == "placed-workspace"):
                raise PowerLoss()

        def fail(*_, fault=fault):
            raise ValueError("synthetic " + fault)

        with ExitStack() as stack:
            if fault == "corrupt":
                bad = out / "corrupt.zip"
                shutil.copyfile(candidate, bad)
                with bad.open("ab") as f:
                    f.write(b"corrupt")
                args = (bad, doc, sig, key)
            if fault == "signature":
                args = (candidate, doc, b"AAAA", key)
            if fault == "disk":
                stack.enter_context(
                    patch.object(
                        tx.shutil,
                        "disk_usage",
                        return_value=shutil._ntuple_diskusage(1, 1, 0),
                    )
                )
            if fault == "copy":
                stack.enter_context(patch.object(tx, "copy_workspace", fail))
            try:
                tx.apply(
                    target,
                    *args,
                    check=fail if fault == "trial" else tx.run_probe,
                    hook=hook,
                )
            except (ValueError, OSError, PowerLoss):
                pass
            else:
                raise AssertionError("fault not triggered: " + fault)
        if fault == "new-write":
            (target / "workspace/after-interruption.txt").write_text(
                "keep new business data", encoding="utf-8"
            )
            try:
                tx.recover(target)
            except ValueError as e:
                assert "新写入" in str(e)
            else:
                raise AssertionError("new data overwritten")
            assert (target / "workspace/after-interruption.txt").is_file()
            assert list(
                (target / tx.STATE / "transactions").glob(
                    "*/old/workspace/data/workthread.sqlite3"
                )
            )
        else:
            tx.recover(target)
            assert records(target) == before
            health(target, "1.0.0rc9")
        cases.append("native safety: " + fault)
    rel.save(
        out / "WINDOWS_REPORT.json",
        {
            "status": "PASS",
            "administrator": False,
            "cases": cases,
            "fixture_info": rel.read(out / "fixture-info.json"),
            "limits": "Windows Server 2022; test key/local release transport only. Windows 10/11 client not tested.",
        },
    )
    print(json.dumps({"passed": cases}, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--prepare", action="store_true")
    a = p.parse_args()
    if os.name != "nt":
        p.error("Windows only")
    out = a.output.resolve()
    out.mkdir(exist_ok=True, parents=True)
    (prepare if a.prepare else exercise)(out)


if __name__ == "__main__":
    main()
