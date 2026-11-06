"""Check actual frozen data bytes, including hidden project Skill directories."""

import hashlib
from pathlib import Path


def check_bundle(bundle, source):
    bundle, source = Path(bundle), Path(source)
    resources = bundle / "_internal/workthread"
    checked = []
    for origin, target in (
        (source / "src/workthread/web", resources / "web"),
        (source / "src/workthread/schemas", resources / "schemas"),
        (source / "workbuddy_template", resources / "resources/workbuddy_template"),
    ):
        expected = {p.relative_to(origin) for p in origin.rglob("*") if p.is_file()}
        actual = {p.relative_to(target) for p in target.rglob("*") if p.is_file()}
        if expected != actual:
            raise ValueError("Frozen resource file set mismatch: " + str(target))
        for name in sorted(expected):
            data = (target / name).read_bytes()
            if data != (origin / name).read_bytes():
                raise ValueError("Frozen resource bytes mismatch: " + str(name))
            checked.append({"path": str((target / name).relative_to(bundle)), "sha256": hashlib.sha256(data).hexdigest()})
    template = resources / "resources/workbuddy_template"
    for name in ("workthread-analysis", "workthread-intake", "workthread-knowledge"):
        if not (template / ".codebuddy/skills" / name / "SKILL.md").is_file():
            raise ValueError("Missing frozen Skill: " + name)
    if (template / ".workbuddy/skills").exists():
        raise ValueError("Obsolete Skills directory in new bundle")
    return checked
