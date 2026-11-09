"""Exercise the real settings UI and two server processes on one loopback port.
Only the release transport, synthetic payload and platform-specific process supervision
are substituted. The test supervisor never invokes mail, the scheduler or WorkBuddy.
"""

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from werkzeug.serving import make_server

from workthread.core import Store
from workthread.server import create_app
from workthread.updating import controller as ctl
from workthread.updating import releases as rel
from workthread.updating import transaction as tx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_updates import NEW, apply, init, package, records


def host(tmp, port):
    root = tmp / "synthetic"
    data = rel.read(tmp / "fixture.json")
    doc, sig = data["doc"].encode(), data["sig"].encode()
    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(data["key"]))
    m = json.loads(doc)

    def fetch(url, limit, out=None):
        if url.startswith("https://api.github.com/"):
            return json.dumps(
                [
                    {
                        "tag_name": "v" + m["version"],
                        "prerelease": True,
                        "draft": False,
                        "body": "升级验收用合成版本",
                        "assets": [
                            {"name": i}
                            for i in ("update.json", "update.sig", m["asset"])
                        ],
                    }
                ]
            ).encode()
        if url.endswith("/update.json"):
            return doc
        if url.endswith("/update.sig"):
            return sig
        if not url.endswith("/" + m["asset"]):
            raise AssertionError("unexpected network input")
        out.write((tmp / m["asset"]).read_bytes())

    def handoff(args):
        assert args[1:3] == ["--maintenance", "finish"]
        (tmp / "handoff").touch()

    def stop():
        threading.Timer(0.1, server.shutdown).start()

    updates = ctl.Updates(root, stop, port)
    server = make_server(
        "127.0.0.1", port, create_app(Store(root / "workspace"), updates), threaded=True
    )
    with (
        patch.object(rel, "fetch", fetch),
        patch.object(rel, "trust", lambda: key),
        patch.object(ctl, "detached", handoff),
        patch.object(tx, "native_quiet", lambda **k: None),
    ):
        server.serve_forever()
    server.server_close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node")
    p.add_argument("--playwright")
    p.add_argument("--browser")
    p.add_argument("--serve", type=Path)
    p.add_argument("--port", type=int)
    a = p.parse_args()
    if a.serve:
        host(a.serve, a.port)
        return
    with tempfile.TemporaryDirectory(prefix="workthread-browser-upgrade-") as temp:
        tmp = Path(temp)
        root = tmp / "synthetic"
        init(root)
        key = Ed25519PrivateKey.generate()
        apply(root, package(tmp, key))
        _, doc, sig, pub = package(tmp, key, "f" * 40, "1.0.0rc5", ["1.0.0rc4@" + NEW])
        rel.save(
            tmp / "fixture.json",
            {
                "doc": doc.decode(),
                "sig": sig.decode(),
                "key": pub.public_bytes_raw().hex(),
            },
        )
        before = records(root)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        args = [sys.executable, __file__, "--serve", str(tmp), "--port", str(port)]
        old = subprocess.Popen(args)
        new = None
        browser = None
        url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(url, timeout=1).close()
                    break
                except OSError:
                    time.sleep(0.1)
            browser = subprocess.Popen(
                [
                    a.node,
                    str(ROOT / "scripts/check_update_browser.cjs"),
                    a.playwright,
                    a.browser,
                    url,
                ]
            )
            if old.wait(45) != 0 or not (tmp / "handoff").exists():
                raise RuntimeError("missing confirmed handoff")
            stage = root / tx.STATE / "downloads" / json.loads(doc)["sha256"]
            result = apply(
                root,
                (
                    stage / "program.zip",
                    (stage / "update.json").read_bytes(),
                    (stage / "update.sig").read_bytes(),
                    pub,
                ),
            )
            rel.save(root / tx.STATE / "result.json", result)
            new = subprocess.Popen(args)
            if browser.wait(40) != 0:
                raise RuntimeError("browser check failed")
            assert before == records(root)
            print(
                "Same-port restart with new server PID; 37 tables per workspace and payloads preserved."
            )
        finally:
            for process in (browser, new, old):
                if process and process.poll() is None:
                    process.terminate()
                    process.wait(10)


if __name__ == "__main__":
    main()
