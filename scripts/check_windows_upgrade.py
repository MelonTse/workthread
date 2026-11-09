"""Windows-only release gate. All mutable paths are generated under a new temporary directory."""

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from workthread.updating import releases as rel

HASHES = {
    "66fea8f746963561268382b6ab3735eefdc0704f": "4777fce941e4049e01378ea110f85fcf0f3aeaf84a5cf4c46f7ab3c736b32623",
    "1ce8e085f6a1578f7cb94f649df96c4d42983e36": "41e4c90d6a48cc15bbd6bf0e5bd0e59e056371d65cd7c44acb6f9f36bdcded8d",
}
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_updates import records


def seed_old(exe, space):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # rc3 demo uses its bundled FakeIMAP; no credentials or existing data are imported.
    proc = subprocess.Popen(
        [str(exe), "--workspace", str(space), "demo", "--port", str(port)]
    )
    try:
        for _ in range(160):
            if proc.poll() is not None:
                raise RuntimeError("old EXE failed to start")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/v1/snapshot", timeout=2
                ) as r:
                    snap = json.load(r)
                assert all(
                    snap[k] for k in ("messages", "todos", "drafts", "knowledge_items")
                )
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("old EXE did not serve its synthetic workspace")
    finally:
        proc.terminate()
        proc.wait(30)
    # Close clean SQLite handles and checkpoint transient WAL left by terminating demo.
    subprocess.run([str(exe), "--workspace", str(space), "doctor"], check=True)
    (space / "agent-workspace/exchange/outputs/unread.json").write_text(
        '{"synthetic":true}', encoding="utf-8"
    )
    (space / "agent-workspace/local.md").write_text("我的合成规则", encoding="utf-8")
    subprocess.run([str(exe), "--workspace", str(space), "backup"], check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--rc3",
        type=Path,
        nargs=2,
        required=True,
        help="Both original INNER Windows ZIPs",
    )
    p.add_argument("--candidate", type=Path, required=True)
    args = p.parse_args()
    if sys.platform != "win32":
        p.error("native Windows required")
    seen = set()
    for old in args.rc3:
        with tempfile.TemporaryDirectory(prefix="WorkThread upgrade synthetic ") as d:
            tmp = Path(d)
            digest = rel.digest(old)
            sha = next((sha for sha, h in HASHES.items() if h == digest), None)
            if sha is None or sha in seen:
                raise ValueError("old ZIP identity mismatch")
            seen.add(sha)
            with zipfile.ZipFile(old) as z:
                z.extractall(tmp / "old")
            root = tmp / "old/WorkThread-1.0.0rc3-windows-x64"
            assert rel.read(root / "BUILD_INFO.json")["commit_sha"] == sha
            old_exe = root / "app/WorkThread.exe"
            for name in ("workspace", "acceptance"):
                seed_old(old_exe, root / name)
            before = records(root)
            candidate = args.candidate.resolve()
            with zipfile.ZipFile(candidate) as z:
                z.extractall(tmp / "new")
            helper = tmp / "new" / candidate.stem / "app/WorkThread.exe"
            meta = tmp / "metadata"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/sign_update.py"),
                    str(candidate),
                    "--source",
                    "1.0.0rc3@" + sha,
                    "--output",
                    str(meta),
                ],
                check=True,
            )
            subprocess.run(
                [
                    str(helper),
                    "--maintenance",
                    "bootstrap",
                    str(root),
                    str(candidate),
                    str(meta),
                    "--confirmed",
                ],
                check=True,
            )
            assert before == records(root)
            for name in ("workspace", "acceptance"):
                doctor = json.loads(
                    subprocess.check_output(
                        [str(old_exe), "--workspace", str(root / name), "doctor"],
                        encoding="utf-8",
                    )
                )
                assert (
                    doctor["ok"]
                    and doctor["version"] == rel.read(meta / "update.json")["version"]
                )
            print(
                "PASS native rc3 "
                + sha
                + " -> signed candidate; both spaces, direct shortcut and doctor verified"
            )


if __name__ == "__main__":
    main()
