"""Versioned, project-local WorkBuddy deployment with custom-file protection."""

import hashlib
import json
import tempfile
from pathlib import Path


def write_template(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            temporary = Path(f.name)
            f.write(content)
            f.flush()
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install_templates(store):
    source = Path(__file__).parent / "resources" / "workbuddy_template"
    if not source.exists():
        source = Path(__file__).resolve().parents[2] / "workbuddy_template"
    metadata = json.loads(
        (source / ".workthread-template.json").read_text(encoding="utf-8")
    )
    version = metadata["version"]
    dest = store.root / "agent-workspace"
    registry = dest / ".workthread-deployment.json"
    with store.lock:
        previous = (
            json.loads(registry.read_text(encoding="utf-8"))
            if registry.exists()
            else {}
        )
        hashes = previous.get("managed_files", {})
        files = {
            p.relative_to(source).as_posix(): p
            for p in source.rglob("*")
            if p.is_file() and p.name != ".workthread-template.json"
        }
        files.update(
            {
                "schemas/" + p.name: p
                for p in (Path(__file__).parent / "schemas").glob("*.json")
            }
        )
        required_skills = {
            f".codebuddy/skills/{name}/SKILL.md"
            for name in ("workthread-analysis", "workthread-intake", "workthread-knowledge")
        }
        if not required_skills.issubset(files):
            raise ValueError("Missing required .codebuddy/skills templates")
        for name, expected in metadata["file_hashes"].items():
            if name not in files or hashlib.sha256(files[name].read_bytes()).hexdigest() != expected:
                raise ValueError("Template resource hash mismatch: " + name)
        report = {
            "template_version": version,
            "previous_version": previous.get("template_version"),
            "workspace": str(dest),
            "files": [],
            "conflicts": [],
            "managed_files": {},
            "legacy_files": [],
        }
        # Inactive rc2 paths are reported, never removed or promoted to new paths.
        old_reports = {row["path"]: row for row in previous.get("legacy_files", [])}
        for name in sorted(p.replace(".codebuddy/", ".workbuddy/", 1) for p in required_skills):
            legacy = dest / name
            if legacy.is_file():
                prior = old_reports.get(name, {})
                recorded_hash = hashes.get(name) or (
                    prior.get("sha256") if prior.get("status") == "preserved" else None
                )
                actual = hashlib.sha256(legacy.read_bytes()).hexdigest()
                report["legacy_files"].append({
                    "path": name, "sha256": actual,
                    "status": "preserved" if actual == recorded_hash else "custom_preserved",
                })
        for name, origin in sorted(files.items()):
            target = dest / name
            content = origin.read_bytes()
            expected = hashlib.sha256(content).hexdigest()
            actual = (
                hashlib.sha256(target.read_bytes()).hexdigest()
                if target.exists()
                else None
            )
            known = {
                hashes.get(name),
                metadata.get("previous_hashes", {}).get(name),
                metadata.get("rc2_previous_hashes", {}).get(name),
            } - {None}
            if actual is None or actual in known:
                if actual != expected:
                    write_template(target, content)
                status = (
                    "installed"
                    if actual is None
                    else "updated"
                    if actual != expected
                    else "current"
                )
            elif actual == expected:
                status = "current"
            else:
                candidate = dest / ".workthread-updates" / version / name
                write_template(candidate, content)
                report["conflicts"].append(
                    {
                        "path": name,
                        "candidate": str(candidate),
                        "reason": "custom file preserved; merge explicitly",
                    }
                )
                status = "custom_preserved"
            report["files"].append({"path": name, "status": status, "sha256": expected})
            # A custom file must never become an automatically managed file.
            report["managed_files"][name] = (
                expected if status != "custom_preserved" else hashes.get(name)
            )
        for name in ("inputs", "outputs", "receipts", "quarantine", "intake"):
            (dest / "exchange" / name).mkdir(parents=True, exist_ok=True)
        report["missing_skills"] = [
            name for name in sorted(required_skills) if not (dest / name).is_file()
        ]
        report["ready"] = not report["conflicts"] and not report["missing_skills"]
        report["client_discovery"] = (
            "requires WorkBuddy skill-list and real invocation verification"
        )
        write_template(
            registry,
            (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
    return report
