"""Offline maintainer tool. Sign an already built ZIP; never uploads or creates a release."""

import argparse
import base64
import json
import os
import re
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from workthread.updating.releases import REPO, digest, version


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", action="append", help="version@full_commit_sha")
    mode.add_argument(
        "--fresh-only",
        action="store_true",
        help="Sign a clean-install release without allowing older updaters",
    )
    p.add_argument(
        "--output", type=Path, required=True, help="New local metadata directory"
    )
    a = p.parse_args()
    # A 32-byte raw private key from the maintainer's offline secret store.
    key = Ed25519PrivateKey.from_private_bytes(
        Path(os.environ["WORKTHREAD_SIGNING_KEY_FILE"]).read_bytes()
    )
    with zipfile.ZipFile(a.archive) as z:
        prefix = a.archive.stem + "/"
        info = json.loads(z.read(prefix + "BUILD_INFO.json"))
        embedded = z.read(
            prefix + "app/_internal/workthread/updating/release-public.hex"
        )
    v = version(info["version"])
    if (
        not re.fullmatch("[a-f0-9]{40}", info["commit_sha"])
        or info["runner_os"] != "Windows"
        or info["machine"].lower() not in ("amd64", "x86_64")
        or a.archive.name != f"WorkThread-{v}-windows-x64.zip"
        or bytes.fromhex(embedded.decode().strip())
        != key.public_key().public_bytes_raw()
    ):
        p.error("ZIP identity or embedded public key mismatch")
    sources = a.source or []
    for src in sources:
        old, _, commit = src.partition("@")
        if version(old) >= v or not re.fullmatch("[a-f0-9]{40}", commit):
            p.error("Invalid source build")
    m = {
        "format": 1,
        "repository": REPO,
        "platform": "windows-x64",
        "version": str(v),
        "commit_sha": info["commit_sha"],
        "sources": sorted(set(sources)),
        "asset": a.archive.name,
        "size": a.archive.stat().st_size,
        "sha256": digest(a.archive),
    }
    payload = json.dumps(m, sort_keys=True, separators=(",", ":")).encode()
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / "update.json").write_bytes(payload)
    (a.output / "update.sig").write_bytes(base64.b64encode(key.sign(payload)))


if __name__ == "__main__":
    main()
