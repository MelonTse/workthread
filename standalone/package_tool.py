import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / "artifacts"
name = "WorkThread-RC7-to-RC9-Upgrade-Tool-1.0.1"
stage = out / name
stage.mkdir()
shutil.copytree(root / "dist/WorkThreadUpgrade", stage / "tool")
shutil.copytree(out / "upgrade-qa/release", stage / "release")
for file in ("Upgrade.cmd", "README.md", "WORKBUDDY_PROMPT.md"):
    shutil.copy2(root / "standalone" / file, stage / file)
shutil.copy2(out / "upgrade-qa/WINDOWS_REPORT.json", stage / "WINDOWS_REPORT.json")
shutil.copy2(out / "tool-tests.xml", stage / "tool-tests.xml")
(stage / "BUILD_INFO.json").write_text(
    json.dumps(
        {
            "tool_version": "1.0.1",
            "commit_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip(),
            "platform": "windows-x64",
            "source": "1.0.0rc7",
            "target": "1.0.0rc9",
        },
        indent=2,
    ),
    encoding="utf-8",
)
(stage / "TEST_REPORT.md").write_text(
    "Windows Server 2022 x64, standard local user (not administrator): all automated tests and official RC7 -> RC9 synthetic upgrade/failure checks passed. See tool-tests.xml and WINDOWS_REPORT.json. Windows 10/11 client acceptance is pending. No real mailbox or user data was used.\n",
    encoding="utf-8",
)


def hashfile(p):
    with p.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


files = sorted(p for p in stage.rglob("*") if p.is_file())
(stage / "FILE_MANIFEST.sha256").write_text(
    "".join(hashfile(p) + "  " + p.relative_to(stage).as_posix() + "\n" for p in files),
    encoding="utf-8",
)
archive = out / (name + ".zip")
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(stage.rglob("*")):
        if p.is_file():
            z.write(p, Path(name) / p.relative_to(stage))
(out / (name + ".zip.sha256")).write_text(
    hashfile(archive) + "  " + archive.name + "\n", encoding="ascii"
)
print("DELIVERABLE", archive.name, archive.stat().st_size, hashfile(archive))
