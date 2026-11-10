"""Upgrade an official Windows installation with synthetic archives in both spaces."""

import argparse
import contextlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
import zipfile

from check_windows_upgrade import seed_old
from workthread import __version__
from workthread.updating import releases as rel, transaction as tx

ROOT = Path(__file__).resolve().parents[1]
OLD = {
    "1.0.0rc4": (
        "b8d08dbb73c25dba347e323bfe0db420da20ac06",
        "5a058a5aebdf3cab4f7c4d3b0bb84c5b6bc50199d3bb4d4b3361edcd2c6189e6",
    ),
    "1.0.0rc5": (
        "528592c0993ccef92fb3d7689c4a4499ba083883",
        "b5e16ec5c29adac1c06df869d5c73fae479528378a812cd198425afb510db890",
    ),
    "1.0.0rc6": (
        "e788a375072adc63606937f162ab5feae8b00e10",
        "3daed3e822dc93a7012e988e5b6dd952057aa2786030ca6adceff0a69524219d",
    ),
}


def inventory(space):
    with contextlib.closing(
        sqlite3.connect(
            (space / "data/workthread.sqlite3").as_uri() + "?mode=ro", uri=True
        )
    ) as db:
        tables = {}
        for table in (
            "messages",
            "mail_occurrences",
            "mail_folders",
            "mail_accounts",
            "archive_commits",
            "sync_failures",
            "drafts",
            "todos",
            "progress_logs",
            "knowledge_items",
        ):
            tables[table] = db.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            ).fetchall()
        assert (
            tables["messages"] and tables["mail_occurrences"] and tables["mail_folders"]
        )
    files = {
        p.relative_to(space).as_posix(): rel.digest(p)
        for name in ("data/body", "data/meta", "backups")
        for p in (space / name).rglob("*")
        if p.is_file()
    }
    for name in ("data/body/", "data/meta/", "backups/"):
        assert any(k.startswith(name) for k in files), name
    return tables, files


def browser_upgrade(target, expected):
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
        for _ in range(150):
            if proc.poll() is not None:
                raise RuntimeError("Old Windows server exited")
            try:
                with urllib.request.urlopen(
                    url + "/api/v1/software-update", timeout=2
                ) as r:
                    state = json.load(r)
                assert state["current"] == expected and state["enabled"]
                break
            except OSError:
                time.sleep(0.3)
        else:
            raise RuntimeError("Old Windows server did not become ready")
        subprocess.run(
            [
                "node",
                str(ROOT / "scripts/check_update_browser.cjs"),
                os.environ["WT_QA_PLAYWRIGHT"],
                os.environ["WT_QA_CHROME"],
                url,
                __version__,
            ],
            check=True,
            timeout=420,
        )
    finally:
        subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-Command",
                "$ErrorActionPreference='Stop'; Get-Process WorkThread -ErrorAction SilentlyContinue | "
                "Where-Object { $_.Path -and $_.Path.StartsWith($env:WT_QA_ROOT, [StringComparison]::OrdinalIgnoreCase) } | "
                "ForEach-Object { if (!$_.HasExited) { $_.Kill() }; if (!$_.WaitForExit(30000)) {throw 'still running'} }",
            ],
            env=dict(os.environ, WT_QA_ROOT=str(target) + os.sep),
            check=True,
        )
        proc.wait(timeout=40)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--from-version", choices=OLD, required=True)
    p.add_argument("--candidate", type=Path)
    p.add_argument("--metadata", type=Path)
    p.add_argument("--commit", required=True)
    args = p.parse_args()
    if os.name != "nt" or bool(args.candidate) != bool(args.metadata):
        p.error(
            "Use native Windows and specify both or neither of candidate and metadata"
        )
    version = args.from_version
    sha, checksum = OLD[version]
    with tempfile.TemporaryDirectory(prefix="wt-release-") as d:
        tmp = Path(d).resolve()
        old = tmp / f"WorkThread-{version}-windows-x64.zip"
        urllib.request.urlretrieve(
            f"https://github.com/{rel.REPO}/releases/download/v{version}/{old.name}",
            old,
        )
        assert rel.digest(old) == checksum
        with zipfile.ZipFile(old) as z:
            z.extractall(tmp / "original")
        original = tmp / "original" / old.stem
        assert rel.read(original / "BUILD_INFO.json")["commit_sha"] == sha
        target = tmp / "用户 WorkThread"
        # Run the installer belonging to precisely this source version.
        installer = tmp / "install-old.ps1"
        installer.write_bytes(
            subprocess.check_output(
                ["git", "show", f"{sha}:scripts/install-windows.ps1"], cwd=ROOT
            )
        )
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(installer),
                "-InstallRoot",
                str(target),
                "-PackagePath",
                str(old),
                "-ExpectedSha256",
                checksum,
            ],
            check=True,
        )
        for n in tx.SPACES:
            seed_old(target / tx.EXE, target / n)
        before = [inventory(target / n) for n in tx.SPACES]
        if args.candidate:
            subprocess.run(
                [
                    str(original / tx.EXE),
                    "--maintenance",
                    "bootstrap",
                    str(target),
                    str(args.candidate.resolve()),
                    str(args.metadata.resolve()),
                    "--confirmed",
                ],
                check=True,
            )
        else:
            browser_upgrade(target, version)
        identity = tx.current(target)[1]
        assert (identity["version"], identity["commit_sha"]) == (
            __version__,
            args.commit,
        )
        for n, expected in zip(tx.SPACES, before, strict=True):
            health = json.loads(
                subprocess.check_output(
                    [str(target / tx.EXE), "--workspace", str(target / n), "doctor"],
                    encoding="utf-8",
                )
            )
            assert health["ok"] and health["version"] == __version__
            assert inventory(target / n) == expected, f"Imported data changed in {n}"
            print(
                f"PASS {version} -> {__version__}, {n}: {len(expected[0]['messages'])} messages, "
                f"{len(expected[1])} archived/backup files, folders, cursors and business records matched"
            )


if __name__ == "__main__":
    main()
