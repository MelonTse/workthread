"""Install project-local rules and schemas without overwriting user rules."""

import shutil
from pathlib import Path


def install_templates(store):
    source = Path(__file__).parent / "resources" / "workbuddy_template"
    if not source.exists():
        source = Path(__file__).resolve().parents[2] / "workbuddy_template"
    dest = store.root / "agent-workspace"
    if source.exists():
        for p in source.rglob("*"):
            if p.is_file():
                target = dest / p.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copy2(p, target)
    schema_dest = dest / "schemas"
    schema_dest.mkdir(exist_ok=True)
    for schema in (Path(__file__).parent / "schemas").glob("*.json"):
        shutil.copy2(schema, schema_dest / schema.name)
