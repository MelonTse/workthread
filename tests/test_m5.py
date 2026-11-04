from pathlib import Path
import subprocess
import sys
import re


def test_cli_health_and_resources(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "workthread.cli",
            "--workspace",
            str(tmp_path),
            "doctor",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0 and '"ok": true' in result.stdout
    assert (
        tmp_path / "agent-workspace/.codebuddy/skills/workthread-analysis/SKILL.md"
    ).exists()
    assert (tmp_path / "agent-workspace/schemas/ai-output.json").exists()


def test_web_no_model_api():
    js = (
        Path(__file__).resolve().parents[1] / "src/workthread/web/static/app.js"
    ).read_text(encoding="utf-8")
    assert not re.search(r"https?://", js)


def test_runtime_and_credential_paths_are_ignored():
    root = Path(__file__).resolve().parents[1]
    paths = [
        ".runtime/demo/data/workthread.sqlite3",
        "workspace/data/meta/2026-11.jsonl",
        "backups/full.7z",
        ".env",
        "secret.key",
        ".tools/python/bin/python",
        "data/private.json",
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--stdin", "-z"],
        input=("\0".join(paths) + "\0").encode("utf-8"),
        cwd=root,
        capture_output=True,
    )
    assert set(result.stdout.decode("utf-8").rstrip("\0").split("\0")) == set(paths)
