"""rc3 resource checks and isolated synthetic packaging, not Windows acceptance."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import runpy
import shutil
import sys
import zipfile

import pytest
import workthread.deployment as deployment
from workthread.core import Store

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("workthread-analysis", "workthread-intake", "workthread-knowledge")


@pytest.mark.parametrize("custom_old,canonical", [(False, "missing"), (True, "missing"), (False, "copied"), (True, "custom")])
def test_rc2_registry_paths_are_preserved_without_overwriting(tmp_path, custom_old, canonical):
    store = Store(tmp_path / "synthetic")
    dest = store.root / "agent-workspace"
    fixture = json.loads((ROOT / "tests/fixtures/rc2-project-files.json").read_text(encoding="utf-8"))
    hashes = {}
    for name, text in fixture.items():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode())
        hashes[name] = hashlib.sha256(text.encode()).hexdigest()
    (dest / ".workthread-deployment.json").write_text(json.dumps({"template_version": "1.0.0rc2", "managed_files": hashes}))
    if custom_old:
        (dest / ".workbuddy/skills/workthread-analysis/SKILL.md").write_bytes(b"old custom: keep")
    if canonical != "missing":
        for name in SKILLS:
            target = dest / ".codebuddy/skills" / name / "SKILL.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"canonical custom: keep" if canonical == "custom" else fixture[f".workbuddy/skills/{name}/SKILL.md"].encode())
    old_bytes = {name: (dest / name).read_bytes() for name in hashes if name.startswith(".workbuddy/")}
    for _ in range(2):
        report = deployment.install_templates(store)
        assert report["ready"] == (canonical != "custom")
        assert len(report["legacy_files"]) == 3
        assert report["legacy_files"][0]["status"] == ("custom_preserved" if custom_old else "preserved")
        assert all(not p.startswith(".workbuddy/") for p in report["managed_files"])
        for name, original in old_bytes.items():
            assert (dest / name).read_bytes() == original
        for name in SKILLS:
            path = f".codebuddy/skills/{name}/SKILL.md"
            actual = (dest / path).read_bytes()
            if canonical == "custom":
                assert actual == b"canonical custom: keep"
                assert path in {c["path"] for c in report["conflicts"]}
                assert report["managed_files"][path] is None
            else:
                assert actual == fixture[f".workbuddy/skills/{name}/SKILL.md"].encode()
                assert report["managed_files"][path] == hashlib.sha256(actual).hexdigest()


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_incomplete_or_corrupt_template_cannot_report_ready(tmp_path, monkeypatch, fault):
    package = tmp_path / "package"
    shutil.copytree(ROOT / "workbuddy_template", package / "resources/workbuddy_template")
    shutil.copytree(ROOT / "src/workthread/schemas", package / "schemas")
    monkeypatch.setattr(deployment, "__file__", str(package / "deployment.py"))
    path = package / "resources/workbuddy_template/.codebuddy/skills/workthread-intake/SKILL.md"
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="Missing required|hash mismatch"):
        deployment.install_templates(Store(tmp_path / "synthetic"))


def test_actual_packaging_script_preserves_hidden_skill_bytes(tmp_path, monkeypatch):
    # A fake executable in an isolated directory exercises the ZIP writer only.
    # It is never labelled or delivered as a native Windows build.
    source = tmp_path / "source"
    for folder in ("scripts", "docs", "workbuddy_template", "src/workthread/web", "src/workthread/schemas"):
        shutil.copytree(ROOT / folder, source / folder)
    for name in ("README.md", "WORKBUDDY_SETUP.md", "uv.lock"):
        shutil.copy2(ROOT / name, source / name)
    bundle = source / "dist/WorkThread"
    bundle.mkdir(parents=True)
    (bundle / "WorkThread.exe").write_bytes(b"SYNTHETIC PACKAGING TEST ONLY")
    for origin, target in (("web", "web"), ("schemas", "schemas")):
        shutil.copytree(source / "src/workthread" / origin, bundle / "_internal/workthread" / target)
    shutil.copytree(source / "workbuddy_template", bundle / "_internal/workthread/resources/workbuddy_template")
    monkeypatch.syspath_prepend(str(source / "scripts"))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(importlib.metadata, "distributions", lambda: [])
    # This cross-platform ZIP layout test cannot run the Windows C# compiler.
    def compile_stub(args, check):
        Path(next(arg[5:] for arg in args if arg.startswith("/out:"))).write_bytes(b"synthetic launcher")
    monkeypatch.setattr("subprocess.run", compile_stub)
    runpy.run_path(str(source / "scripts/package_release.py"), run_name="__main__")
    archive = source / "artifacts/WorkThread-1.0.0rc4-windows-x64.zip"
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        prefix = "WorkThread-1.0.0rc4-windows-x64/"
        manifest = json.loads(z.read(prefix + "SHA256SUMS.json"))
        for path, expected in manifest.items():
            assert hashlib.sha256(z.read(prefix + path)).hexdigest() == expected
        assert not any("/.workbuddy/skills/" in p for p in z.namelist())
        for name in SKILLS:
            path = f"app/_internal/workthread/resources/workbuddy_template/.codebuddy/skills/{name}/SKILL.md"
            assert z.read(prefix + path) == (ROOT / "workbuddy_template/.codebuddy/skills" / name / "SKILL.md").read_bytes()


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_bundle_audit_rejects_lost_hidden_resources(tmp_path, monkeypatch, fault):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    from check_bundle import check_bundle
    for folder in ("web", "schemas"):
        shutil.copytree(ROOT / "src/workthread" / folder, tmp_path / "_internal/workthread" / folder)
    target = tmp_path / "_internal/workthread/resources/workbuddy_template"
    shutil.copytree(ROOT / "workbuddy_template", target)
    assert len(check_bundle(tmp_path, ROOT)) == 12
    skill = target / ".codebuddy/skills/workthread-knowledge/SKILL.md"
    if fault == "missing":
        skill.unlink()
    else:
        skill.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="mismatch"):
        check_bundle(tmp_path, ROOT)
