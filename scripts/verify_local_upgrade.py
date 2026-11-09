"""Offline Mac/Linux evidence: real historical source, real frozen probe, disposable fixtures.
Run from the repository root. No credentials, remote repository, mailbox or installation is used.
"""

import argparse
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from workthread.updating import releases as rel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_updates import apply, init, package, records  # synthetic packaging fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    args = parser.parse_args()
    exe = args.exe.resolve(strict=True)
    for sha in sorted(rel.RC3):
        with tempfile.TemporaryDirectory(prefix="workthread-rc3-history-") as td:
            tmp = Path(td)
            original = tmp / "old-source"
            archive = subprocess.check_output(
                ["git", "archive", sha, "src", "workbuddy_template"], cwd=ROOT
            )
            with tarfile.open(fileobj=io.BytesIO(archive)) as t:
                t.extractall(original, filter="data")
            root = tmp / "合成 WorkThread"
            init(root, sha, seed_spaces=False)
            # Execute seed + template deployment from the precise old commit, not the current package.
            code = """
from pathlib import Path
import workthread
from workthread.core import Store
from workthread.demo import seed
from workthread.deployment import install_templates
from workthread.ai import Bridge
import sys
assert Path(workthread.__file__).resolve().is_relative_to(Path(sys.argv[2]).resolve())
for n in ('workspace','acceptance'):
    s=Store(Path(sys.argv[1])/n)
    seed(s)
    install_templates(s)
    s.create_todo({'raw_input':n,'title':n,'no_due_date':True},key=n)
    Bridge(s).prepare()
    assert s.rows("SELECT job_id FROM ai_jobs WHERE state='pending'")
    (s.root/'agent-workspace/exchange/outputs/待处理.json').write_text('synthetic',encoding='utf-8')
    (s.root/'agent-workspace/custom.md').write_text('custom',encoding='utf-8')
    (s.root/'backups').mkdir(exist_ok=True)
    (s.root/'backups/历史.zip').write_bytes(b'synthetic history')
"""
            subprocess.run(
                [sys.executable, "-c", code, str(root), str(original)],
                cwd=tmp,
                env={**os.environ, "PYTHONPATH": str(original / "src")},
                check=True,
            )
            before = records(root)

            def frozen(bundle, trial, logical):
                subprocess.run(
                    [str(exe), "--maintenance", "probe", str(trial), str(logical)],
                    check=True,
                )

            apply(root, package(tmp, Ed25519PrivateKey.generate()), check=frozen)
            assert before == records(root)
            print(
                json.dumps(
                    {
                        "source_commit": sha,
                        "new_probe": "native frozen executable",
                        "spaces": 2,
                        "all_tables_and_payload_files_preserved": True,
                        "tables_per_space": len(before[0]),
                        "old_format": "historical source, synthetic portable shell",
                    }
                )
            )


if __name__ == "__main__":
    main()
