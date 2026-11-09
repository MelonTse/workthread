"""Maintainer helper; schemas are checked in and shipped with the package."""

import json
from pathlib import Path

out = Path(__file__).resolve().parents[1] / "src/workthread/schemas"


def obj(props, required=None):
    return {
        "type": "object",
        "properties": props,
        "required": required if required is not None else list(props),
        "additionalProperties": False,
    }


s = {"type": "string"}
nullable = {"type": ["string", "null"]}
arr = lambda item: {"type": "array", "items": item}
evidence = obj({"message_id": s, "quote": dict(s, minLength=1)})
todo = obj(
    {
        "title": dict(s, minLength=1),
        "description": s,
        "raw_input": s,
        "action_key": dict(s, minLength=1),
        "priority": {"enum": ["low", "normal", "high", "urgent"]},
        "due_date": nullable,
        "no_due_date": {"type": "boolean"},
        "completion_criteria": s,
    },
    ["title", "description", "action_key"],
)
payloads = {
    "create_todo": todo,
    "normalize_todo": obj(
        {
            k: v
            for k, v in todo["properties"].items()
            if k not in ("raw_input", "action_key")
        },
        [],
    ),
    "append_progress": obj(
        {
            "content": dict(s, minLength=1),
            "occurred_at": nullable,
            "corrects_log_id": nullable,
        },
        ["content"],
    ),
    "propose_status": obj(
        {
            "status": {"enum": ["open", "in_progress", "waiting", "done", "cancelled"]},
            "reason": s,
        },
        ["status", "reason"],
    ),
    "suggest_link": obj({"customer_id": nullable, "case_id": nullable}, []),
    "suggest_relationship": obj(
        {"customer_name": s, "contact_name": s, "contact_address": s, "relation": s}
    ),
    "suggest_case": obj(
        {
            "title": s,
            "customer_id": nullable,
            "case_type": {"enum": ["project", "order", "other"]},
            "stage": s,
        },
        ["title", "case_type"],
    ),
    "suggest_duplicate": obj({"other_todo_id": s, "reason": s}),
    "propose_knowledge": obj(
        {
            "scope": {"enum": ["personal", "customer", "case"]},
            "subject_id": nullable,
            "content": s,
        },
        ["scope", "content"],
    ),
    "create_draft": obj(
        {"message_id": nullable, "subject": s, "body": s}, ["subject", "body"]
    ),
    "mail_analysis": obj(
        {"message_ids": arr(s), "work_type": s, "stage": s, "summary": s, "advice": s}
    ),
}
variants = []
for typ, payload in payloads.items():
    props = {
        "operation_id": dict(s, minLength=1),
        "type": {"const": typ},
        "payload": payload,
        "evidence": arr(evidence),
        "todo_id": s,
        "expected_revision": {"type": "integer", "minimum": 1},
    }
    req = ["operation_id", "type", "payload", "evidence"]
    if typ in ("normalize_todo", "append_progress", "propose_status"):
        req += ["todo_id", "expected_revision"]
    variants.append(obj(props, req))
base = {
    "schema_version": {"const": "1.0"},
    "workspace_id": s,
    "workspace_epoch": s,
    "job_id": s,
    "input_sha256": s,
}
output = obj(
    {
        **base,
        "outcome": {"const": "completed"},
        "reviewed_todo_ids": dict(arr(s), uniqueItems=True),
        "operations": arr({"oneOf": variants}),
        "warnings": arr(s),
    }
)
input_schema = obj(
    {
        **base,
        "job_type": {"enum": ["reconcile", "normalize", "historical", "mail_draft","todo_assist","knowledge_assist"]},
        "rules_version": s,
        "created_at": s,
        "timezone": s,
        "scope": obj(
            {"mail_batch_id": s, "todo_ids": arr(s), "historical": {"type": "boolean"}}
        ),
        "context": {
            "type": "object",
            "required": [
                "messages",
                "todos",
                "progress_logs",
                "human_decisions",
                "customers",
                "cases",
                "knowledge",
                "taxonomy",
            ],
        },
    }
)
general_context = input_schema["properties"]["context"]
input_schema["properties"]["context"] = {"type": "object"}
input_schema["allOf"] = [{
    "if": {"properties": {"job_type": {"const": "mail_draft"}}},
    "then": {"properties": {"context": {"type": "object", "required": [
        "target_message_id", "messages", "knowledge", "execution", "instructions", "material_hash"
    ]}}},
    "else": {"if": {"properties":{"job_type":{"const":"todo_assist"}}},
             "then":{"properties":{"context":{"type":"object","required":["sources","todos","instructions","execution"]}}},
             "else":{"properties":{"context":general_context}}},
}]
input_schema["allOf"][0]["else"]["else"] = {
    "if": {"properties": {"job_type": {"const": "knowledge_assist"}}},
    "then": {"properties": {"context": {"required": ["material", "subject_id", "fingerprint", "instructions", "execution"]}}},
    "else": {"properties": {"context": general_context}},
}
intake = obj(
    {
        "schema_version": {"const": "1.0"},
        "request_id": s,
        "raw_input": dict(s, minLength=1, maxLength=100000),
        "input_at": s,
        "input_timezone": s,
        "source_ref": s,
        "due_date": nullable,
        "no_due_date": {"type": "boolean"},
    },
    [
        "schema_version",
        "request_id",
        "raw_input",
        "input_at",
        "input_timezone",
        "source_ref",
    ],
)
for name, doc in [
    ("ai-input", input_schema),
    ("ai-output", output),
    ("intake", intake),
]:
    doc["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    (out / (name + ".json")).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    )
