"""Release gate for the pinned RC10 candidate and its public clean-install path."""

import argparse
import contextlib
import http.cookiejar
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from workthread.updating import releases as rel

NAME = "WorkThread-1.0.0rc10-windows-x64"
COMMIT = "f488b17d3f27488b1d23976c7c58990b3aa5dbda"
HASH = "af17c8568863ee18ce87c037dc842d89e261fd41663490d4487d0887c1f65bfb"


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


def check_update_endpoint(exe, root):
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )
    workspace = root / "workspace"
    record = workspace / ".workthread-service.json"
    proc = subprocess.Popen(
        [str(exe), "--workspace", str(workspace), "serve", "--port", "0"],
        cwd=root,
    )
    try:
        deadline = time.monotonic() + 30
        while not record.is_file():
            check(
                proc.poll() is None, "The installed RC10 server exited during startup"
            )
            check(
                time.monotonic() < deadline, "The installed RC10 server did not start"
            )
            time.sleep(0.25)
        service = rel.read(record)
        base = f"http://127.0.0.1:{service['port']}"
        with opener.open(base + "/api/v1/instance", timeout=5) as response:
            check(
                json.load(response)["instance_id"] == service["instance_id"],
                "The loopback server does not belong to this clean installation",
            )
        with opener.open(base + "/", timeout=5) as response:
            html = response.read().decode("utf-8")
        token = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
        check(
            token is not None,
            "The installed UI did not provide an update request token",
        )
        request = urllib.request.Request(
            base + "/api/v1/software-update/check",
            method="POST",
            data=b"{}",
            headers={"Content-Type": "application/json", "X-CSRF-Token": token[1]},
        )
        with opener.open(request, timeout=180) as response:
            result = json.load(response)
        check(
            result["enabled"]
            and result["current"] == "1.0.0rc10"
            and result["current_commit"] == COMMIT
            and result["checked_at"]
            and not result["last_error"]
            and (result["offer"] is not None or result["check_message"]),
            "The installed RC10 did not complete a real update check",
        )
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--public-install", action="store_true")
    args = parser.parse_args()
    archive = args.assets / (NAME + ".zip")
    check(rel.digest(archive) == HASH, "Wrong Windows program ZIP")
    check(
        (args.assets / (NAME + ".zip.sha256")).read_text().split()[0] == HASH,
        "Wrong public checksum asset",
    )
    doc = (args.metadata / "update.json").read_bytes()
    sig = (args.metadata / "update.sig").read_bytes().strip()
    from base64 import b64decode

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    raw = bytes.fromhex(Path("packaging/release-public.hex").read_text().strip())
    key = Ed25519PublicKey.from_public_bytes(raw)
    key.verify(b64decode(sig, validate=True), doc)
    manifest = json.loads(doc)
    check(
        manifest
        == {
            "format": 1,
            "repository": rel.REPO,
            "platform": "windows-x64",
            "asset": archive.name,
            "version": "1.0.0rc10",
            "commit_sha": COMMIT,
            "sources": [],
            "size": 20635376,
            "sha256": HASH,
        },
        "Signed metadata allows an unsupported source or does not identify the pinned build",
    )
    with tempfile.TemporaryDirectory(prefix="rc10 clean release ") as tmp:
        root = Path(tmp) / "全新 WorkThread"
        rel.extract(archive, root, manifest)
        embedded = root / "app/_internal/workthread/updating/release-public.hex"
        check(
            bytes.fromhex(embedded.read_text().strip()) == raw,
            "Wrong embedded public key",
        )
        if args.public_install:
            check(os.name == "nt", "Public installation test requires Windows")
            subprocess.run(
                ["cmd.exe", "/d", "/c", "Install.cmd", "/quiet"],
                cwd=root,
                check=True,
                timeout=120,
            )
            exe = root / "app/WorkThread.exe"
            for space in ("workspace", "acceptance"):
                health = json.loads(
                    subprocess.check_output(
                        [str(exe), "--workspace", str(root / space), "doctor"],
                        encoding="utf-8",
                        timeout=30,
                    )
                )
                check(
                    health["ok"] and health["version"] == "1.0.0rc10",
                    space + " is not running a healthy RC10",
                )
                with contextlib.closing(
                    sqlite3.connect(root / space / "data/workthread.sqlite3")
                ) as db:
                    for table in ("messages", "todos", "mail_accounts"):
                        check(
                            db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                            == 0,
                            space + " contains unexpected imported data",
                        )
            check_update_endpoint(exe, root)
    print(
        "PASS: pinned RC10 ZIP, checksum, signed clean-install policy, embedded key"
        + (
            "; public download, two blank healthy workspaces and installed update endpoint"
            if args.public_install
            else ""
        )
    )


if __name__ == "__main__":
    main()
