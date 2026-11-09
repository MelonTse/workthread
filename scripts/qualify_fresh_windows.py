"""Windows integration test. Uses disposable frozen programs and an offline release feed."""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from workthread.ai import Bridge
from workthread.core import Store
from workthread.demo import seed
from workthread.updating import releases as rel, transaction as tx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_updates import records


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def build(source, tmp, env, sha, version):
    build_env = dict(env, PYTHONPATH=str(source / "src"), GITHUB_SHA=sha)
    (source / "src/workthread/__init__.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8"
    )
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "packaging/workthread.spec",
        ],
        cwd=source,
        env=build_env,
    )
    run([sys.executable, "scripts/package_release.py"], cwd=source, env=build_env)
    name = f"WorkThread-{version}-windows-x64.zip"
    return Path(shutil.copyfile(source / "artifacts" / name, tmp / name))


def main():
    if os.name != "nt":
        raise SystemExit("Native Windows required")
    with tempfile.TemporaryDirectory(prefix="wt-qualification-") as directory:
        tmp = Path(directory).resolve()  # Normalize Windows 8.3 temp paths for process matching.
        source = tmp / "source"
        archive = tmp / "source.zip"
        run(["git", "archive", "--format=zip", "-o", str(archive), "HEAD"], cwd=ROOT)
        with zipfile.ZipFile(archive) as z:
            z.extractall(source)
        next_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        sha = "b8d08dbb73c25dba347e323bfe0db420da20ac06"
        old_source = tmp / "rc4-source"
        run(["git", "archive", "--format=zip", "-o", str(archive), sha], cwd=ROOT)
        with zipfile.ZipFile(archive) as z:
            z.extractall(old_source)
        key = Ed25519PrivateKey.generate()
        secret, public = tmp / "fixture.raw", tmp / "release-public.hex"
        secret.write_bytes(key.private_bytes_raw())
        public.write_text(key.public_key().public_bytes_raw().hex(), encoding="ascii")
        env = dict(
            os.environ,
            WORKTHREAD_BUILD_PUBLIC_KEY=str(public),
            WORKTHREAD_SIGNING_KEY_FILE=str(secret),
        )
        newer = build(source, tmp, env, next_sha, "1.0.0rc5")
        feed = tmp / "feed"
        run(
            [
                sys.executable,
                str(ROOT / "scripts/sign_update.py"),
                str(newer),
                "--source",
                "1.0.0rc4@" + sha,
                "--output",
                str(feed),
            ],
            env=env,
        )
        shutil.move(newer, feed / newer.name)
        names = ["update.json", "update.sig", newer.name]
        rel.save(
            feed / "releases.json",
            [
                {
                    "tag_name": "v1.0.0rc5",
                    "draft": False,
                    "prerelease": True,
                    "body": "Native qualification",
                    "assets": [{"name": n} for n in names],
                }
            ],
        )
        # Restrict just the release transport in the disposable test checkout. No fixture
        # endpoint, runtime override or test signing authority in the shipping source.
        module = old_source / "src/workthread/updating/releases.py"
        with module.open("a", encoding="utf-8") as f:
            f.write("\n\ndef fetch(url, limit, out=None):\n")
            links = {
                "https://api.github.com/repos/MelonTse/workthread/releases?per_page=30&page=1": "releases.json"
            }
            links.update(
                {
                    "https://github.com/MelonTse/workthread/releases/download/v1.0.0rc5/"
                    + n: n
                    for n in names
                }
            )
            f.write(f"    path = Path({str(feed)!r}) / {links!r}[url]\n")
            f.write(
                "    data = path.read_bytes()\n    assert len(data) <= limit\n    if out is None: return data\n    out.write(data)\n"
            )
        old = build(old_source, tmp, env, sha, "1.0.0rc4")
        target = tmp / "用户 安装" / "WorkThread"
        args = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(old_source / "scripts/install-windows.ps1"),
            "-InstallRoot",
            str(target),
            "-PackagePath",
            str(old),
            "-ExpectedSha256",
            rel.digest(old),
        ]
        invalid = subprocess.run([*args[:-1], "0" * 64], capture_output=True, check=False)
        assert b"SHA-256 mismatch" in invalid.stderr, invalid.stderr
        assert invalid.returncode and not target.exists()
        run(args, timeout=180)
        # Same installer must refuse a second invocation without modifying user files.
        assert subprocess.run(args, check=False).returncode
        for n in tx.SPACES:
            store = Store(target / n)
            assert not store.rows("SELECT * FROM todos")
            seed(store)
            store.create_todo({"title": n, "raw_input": n, "no_due_date": True}, key=n)
            Bridge(store).prepare()
            (store.root / "agent-workspace/custom.md").write_text(n, encoding="utf-8")
        assert not any(
            (target / tx.STATE / name).exists()
            for name in ("bootstrap", "base", "active.json")
        )
        before = records(target)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        proc = subprocess.Popen(
            [
                str(target / tx.EXE),
                "--maintenance",
                "launch",
                str(target),
                "--workspace",
                str(target / "workspace"),
                "serve",
                "--port",
                str(port),
            ]
        )
        try:
            for _ in range(200):
                if proc.poll() is not None:
                    raise RuntimeError("Initial server exited")
                try:
                    with urllib.request.urlopen(
                        url + "/api/v1/software-update", timeout=2
                    ) as r:
                        status = json.load(r)
                    assert status["current"] == "1.0.0rc4" and status["enabled"]
                    break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Server did not start")
            run(
                [
                    "node",
                    str(ROOT / "scripts/check_update_browser.cjs"),
                    os.environ["WT_QA_PLAYWRIGHT"],
                    os.environ["WT_QA_CHROME"],
                    url,
                ],
                timeout=240,
            )
            assert tx.current(target)[1]["commit_sha"] == next_sha
            with urllib.request.urlopen(url + "/api/v1/system/status") as r:
                assert json.load(r)["version"] == "1.0.0rc5"
        finally:
            # Select only executables in this newly-created disposable installation.
            run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-Command",
                    "$ErrorActionPreference = 'Stop'; "
                    "$owned = Get-Process -Name WorkThread -ErrorAction SilentlyContinue | "
                    "Where-Object { $_.Path -and $_.Path.StartsWith("
                    "$env:WT_QA_ROOT, [StringComparison]::OrdinalIgnoreCase) }; "
                    "foreach ($p in $owned) { "
                    "if (!$p.HasExited) { $p.Kill() }; "
                    "if (!$p.WaitForExit(30000)) { throw 'Test process still running' } }",
                ],
                env=dict(os.environ, WT_QA_ROOT=str(target) + os.sep),
            )
            proc.wait(timeout=30)
        # Normal process restarts may leave lock files; verify typed records and payloads offline.
        for n in tx.SPACES:
            run([str(target / tx.EXE), "--workspace", str(target / n), "doctor"])
        assert before == records(target)
        print(
            "PASS fresh Windows rc4 -> signed rc5, native handoff, original URL, both workspaces and launcher"
        )


if __name__ == "__main__":
    main()
