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
        report = {
            "template_version": version,
            "previous_version": previous.get("template_version"),
            "workspace": str(dest),
            "files": [],
            "conflicts": [],
            "managed_files": {},
        }
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
        report["ready"] = not report["conflicts"]
        report["client_discovery"] = (
            "requires WorkBuddy skill-list and real invocation verification"
        )
        write_template(
            registry,
            (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
    return report
