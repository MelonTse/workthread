"""Fail closed on tracked runtime/private artifacts; does not scan ignored personal files."""

from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
run = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=False)
if run.returncode:
    raise SystemExit(
        "Initialize Git and stage only reviewed source files before this check"
    )
files = [p for p in run.stdout.decode().split("\0") if p]
forbidden = {".jsonl", ".7z", ".sqlite3", ".sqlite", ".db", ".key", ".pem", ".p12", ".pfx", ".log"}
bad = [
    p
    for p in files
    if Path(p).suffix.lower() in forbidden
    or any(
        x in Path(p).parts
        for x in ("workspace", "data", "backups", ".runtime", ".tools", ".venv", "credentials", "secrets", "artifacts", "dist", "build")
    )
    or Path(p).name.startswith(".env")
]
if bad:
    raise SystemExit("Forbidden tracked files: " + ", ".join(bad))
secret_patterns = (
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    rb"gh[pousr]_[A-Za-z0-9]{30,}",
    rb"github_pat_[A-Za-z0-9_]{50,}",
    rb"AKIA[A-Z0-9]{16}",
    rb"sk-[A-Za-z0-9]{32,}",
)
for path in files:
    # Inspect the actual staged bytes as well as the current working copy.
    staged = subprocess.check_output(["git", "show", ":" + path], cwd=root)
    current = root / path
    contents = [staged] + ([current.read_bytes()] if current.is_file() else [])
    if any(re.search(pattern, content) for pattern in secret_patterns for content in contents):
        raise SystemExit("Possible secret in source (value redacted): " + path)
# Nothing in fixtures may imply real identity: examples are synthetic and use reserved domains.
print(
    f"Source isolation passed: {len(files)} reviewed paths; runtime data excluded. This check does not prove arbitrary prose is non-sensitive."
)
