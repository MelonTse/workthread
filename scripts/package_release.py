"""Prepare a portable folder from a platform-native PyInstaller build."""

import json
import shutil
import hashlib
import sys
import importlib.metadata
import os
import platform
from pathlib import Path

root = Path(__file__).resolve().parents[1]
output = root / "artifacts" / "WorkThread-1.0.0rc2-windows-x64"
if sys.platform != "win32":
    raise SystemExit(
        "Windows packaging must run on Windows; use native spec build only for Mac smoke tests"
    )
if output.exists():
    shutil.rmtree(output)
output.mkdir(parents=True)
shutil.copytree(root / "dist/WorkThread", output / "app")
(output / "tools").mkdir()
for f in ("install.ps1", "upgrade.ps1"):
    shutil.copy2(root / "scripts" / f, output / "tools" / f)
for src, dest in [
    ("portable-start.cmd", "Start.cmd"),
    ("portable-install.cmd", "Install.cmd"),
    ("portable-health.cmd", "Health.cmd"),
    ("portable-backup.cmd", "Backup.cmd"),
    ("portable-restore.cmd", "Restore.cmd"),
]:
    shutil.copy2(root / "scripts" / src, output / dest)
for name in ("README.md", "WORKBUDDY_SETUP.md"):
    shutil.copy2(root / name, output / name)
shutil.copytree(root / "docs", output / "docs")
shutil.copy2(root / "uv.lock", output / "DEPENDENCIES.lock")
licenses = output / "licenses"
licenses.mkdir()
versions = {}
for distribution in importlib.metadata.distributions():
    name = distribution.metadata["Name"]
    version = distribution.version
    versions[name] = {
        "version": version,
        "license": distribution.metadata.get("License-Expression")
        or distribution.metadata.get("License"),
    }
    for file in distribution.files or []:
        if "license" in str(file).lower() and distribution.locate_file(file).is_file():
            folder = licenses / (name + "-" + version)
            folder.mkdir(exist_ok=True)
            target = folder / Path(str(file)).name
            if not target.exists():
                shutil.copy2(distribution.locate_file(file), target)
(output / "VERSIONS.json").write_text(
    json.dumps({"python": sys.version, "packages": versions}, indent=2)
)
(output / "BUILD_INFO.json").write_text(json.dumps({
    "version": "1.0.0rc2",
    "commit_sha": os.environ.get("GITHUB_SHA"),
    "runner_os": platform.system(),
    "machine": platform.machine(),
}, indent=2))
manifest = {
    str(f.relative_to(output)).replace("\\", "/"): hashlib.sha256(
        f.read_bytes()
    ).hexdigest()
    for f in output.rglob("*")
    if f.is_file()
}
(output / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2))
archive = Path(shutil.make_archive(str(output), "zip", output.parent, output.name))
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
print(archive)
print("SHA-256: " + checksum)
