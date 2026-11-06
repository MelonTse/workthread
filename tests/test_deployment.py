"""Project-only skill deployment; file checks do not assert client discovery."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from workthread.core import Store
from workthread.deployment import install_templates

SKILLS = ("workthread-analysis", "workthread-intake", "workthread-knowledge")
ROOT = Path(__file__).resolve().parents[1]


def test_two_fresh_spaces_deploy_independently_and_remain_empty(tmp_path):
    for space in ("workspace", "acceptance"):
        store = Store(tmp_path / space)
        first = install_templates(store)
        assert first["ready"] and first["template_version"] == "1.0.0rc3"
        assert all(f["status"] == "installed" for f in first["files"])
        dest = store.root / "agent-workspace"
        for name in SKILLS:
            skill = dest / ".codebuddy/skills" / name / "SKILL.md"
            assert skill.is_file() and ("name: " + name) in skill.read_text(
                encoding="utf-8"
            )
        assert not (dest / ".workbuddy/skills").exists()
        for path, expected in first["managed_files"].items():
            assert hashlib.sha256((dest / path).read_bytes()).hexdigest() == expected
        for name in (
            "CODEBUDDY.md",
            ".codebuddy/rules/workthread.md",
            "schemas/intake.json",
            "schemas/ai-input.json",
            "schemas/ai-output.json",
        ):
            assert (dest / name).is_file()
        assert all(
            (dest / "exchange" / n).is_dir()
            for n in ("inputs", "outputs", "intake", "receipts", "quarantine")
        )
        assert not store.rows("SELECT * FROM todos") and not store.rows(
            "SELECT * FROM messages"
        )
        assert not store.rows("SELECT * FROM mail_accounts")
        assert not store.setting("ai_schedule")["enabled"]
        second = install_templates(store)
        assert second["ready"] and all(
            f["status"] == "current" for f in second["files"]
        )
        assert second["managed_files"] == first["managed_files"]
    Store(tmp_path / "acceptance").create_todo(
        {"raw_input": "synthetic only", "no_due_date": True}
    )
    assert not Store(tmp_path / "workspace").rows("SELECT * FROM todos")


def test_custom_rules_skills_and_schemas_never_silently_overwritten(tmp_path):
    store = Store(tmp_path)
    install_templates(store)
    dest = store.root / "agent-workspace"
    paths = [
        "CODEBUDDY.md",
        ".codebuddy/rules/workthread.md",
        "schemas/intake.json",
        ".codebuddy/skills/workthread-analysis/SKILL.md",
    ]
    for name in paths:
        (dest / name).write_text("custom: " + name)
    for _ in range(2):
        report = install_templates(store)
        assert not report["ready"] and {c["path"] for c in report["conflicts"]} == set(
            paths
        )
        for conflict in report["conflicts"]:
            name = conflict["path"]
            assert (dest / name).read_text(encoding="utf-8") == "custom: " + name
            assert Path(conflict["candidate"]).is_file()
    # An explicit user merge to exactly the shipped version becomes current.
    for conflict in report["conflicts"]:
        (dest / conflict["path"]).write_bytes(Path(conflict["candidate"]).read_bytes())
    assert install_templates(store)["ready"]


def test_known_rc1_templates_update_but_custom_legacy_files_stay(tmp_path):
    store = Store(tmp_path)
    dest = store.root / "agent-workspace"
    for name in (
        "CODEBUDDY.md",
        ".codebuddy/rules/workthread.md",
        "schemas/intake.json",
    ):
        original = json.loads(
            (ROOT / "tests/fixtures/rc1-project-files.json").read_text(encoding="utf-8")
        )[name].encode("utf-8")
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original)
    legacy = dest / ".codebuddy/skills/workthread-analysis/SKILL.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("custom rc1 skill; preserve")
    report = install_templates(store)
    assert not report["ready"]
    assert all(
        next(f for f in report["files"] if f["path"] == n)["status"] == "updated"
        for n in (
            "CODEBUDDY.md",
            ".codebuddy/rules/workthread.md",
            "schemas/intake.json",
        )
    )
    assert legacy.read_text(encoding="utf-8") == "custom rc1 skill; preserve"
    assert {c["path"] for c in report["conflicts"]} == {".codebuddy/skills/workthread-analysis/SKILL.md"}


def test_all_three_original_business_bodies_preserved():
    for name in SKILLS:
        origin = json.loads(
            (ROOT / "workbuddy_template/.workthread-template.json").read_text(
                encoding="utf-8"
            )
        )["preserved_skill_prefixes"][name]
        current = (
            ROOT / "workbuddy_template/.codebuddy/skills" / name / "SKILL.md"
        ).read_bytes()
        assert (
            hashlib.sha256(current[: origin["bytes"]]).hexdigest() == origin["sha256"]
        )
    rules = (ROOT / "workbuddy_template/CODEBUDDY.md").read_text(encoding="utf-8")
    assert all(name in rules for name in SKILLS)
    assert "不得把人工读取 SKILL.md" in rules and "不可用" in rules


def test_cli_init_reports_version_and_conflicts(tmp_path):
    args = [
        sys.executable,
        "-m",
        "workthread.cli",
        "--workspace",
        str(tmp_path),
        "init",
    ]
    first = subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", check=True
    )
    assert json.loads(first.stdout)["deployment"]["ready"]
    custom = tmp_path / "agent-workspace/CODEBUDDY.md"
    custom.write_text("custom preserve")
    second = subprocess.run(
        args, check=False, capture_output=True, text=True, encoding="utf-8"
    )
    assert second.returncode == 2
    assert json.loads(second.stdout)["deployment"]["conflicts"]
    assert custom.read_text(encoding="utf-8") == "custom preserve"
