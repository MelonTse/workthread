import pytest
from workthread.core import Store, uid
from workthread.demo import seed
from workthread.ai import Bridge
from workthread.operations import import_legacy, undo_import


def result(j, ops):
    r = {
        k: j[k]
        for k in (
            "schema_version",
            "workspace_id",
            "workspace_epoch",
            "job_id",
            "input_sha256",
        )
    }
    return dict(
        r,
        outcome="completed",
        reviewed_todo_ids=j["scope"]["todo_ids"],
        operations=ops,
        warnings=[],
    )


def test_replied_does_not_close_case_and_manual_protection(tmp_path):
    s = Store(tmp_path)
    seed(s)
    b = Bridge(s)
    j = b.prepare()[0]
    t = j["context"]["todos"][0]
    m = j["context"]["messages"][0]
    op = {
        "operation_id": uid(),
        "type": "propose_status",
        "todo_id": t["todo_id"],
        "expected_revision": t["revision"],
        "payload": {"status": "done", "reason": "回复已发送"},
        "evidence": [{"message_id": m["message_id"], "quote": m["body_text"][:30]}],
    }
    b.import_result(result(j, [op]))
    assert s.todo(t["todo_id"])["status"] != "done"
    assert s.rows("SELECT * FROM review_items WHERE kind='status'")
    s.edit_todo(t["todo_id"], {"status": "done"}, s.todo(t["todo_id"])["revision"])
    # Closed manual tasks cannot be silently reopened by an out-of-scope operation.
    j = b.prepare()[0]
    op["operation_id"] = uid()
    with pytest.raises(Exception):
        b.import_result(result(j, [op]))
    assert s.todo(t["todo_id"])["status"] == "done"


def test_delayed_normalization_uses_original_day_and_bad_evidence_atomic(tmp_path):
    s = Store(tmp_path)
    t = s.create_todo(
        {"raw_input": "明天联系客户", "input_at": "2026-01-01T10:00:00+08:00"}
    )
    b = Bridge(s)
    j = b.prepare()[0]
    op = {
        "operation_id": uid(),
        "type": "normalize_todo",
        "todo_id": t["todo_id"],
        "expected_revision": 1,
        "payload": {"title": "联系客户", "due_date": "2026-01-04"},
        "evidence": [],
    }
    with pytest.raises(ValueError):
        b.import_result(result(j, [op]))
    assert s.todo(t["todo_id"])["due_date"] == "2026-01-02"
    op["payload"]["due_date"] = "2026-01-02"
    b.import_result(result(j, [op]))
    assert s.todo(t["todo_id"])["due_date"] == "2026-01-02"


def test_legacy_scopes_and_undo(tmp_path):
    s = Store(tmp_path)
    doc = {
        "schema_version": "1.0",
        "categories": [
            {"id": "a", "name": "合成一级"},
            {"id": "b", "parent_id": "a", "name": "合成二级"},
        ],
        "customers": [{"id": "c", "name": "Synthetic"}],
        "contacts": [{"id": "p", "name": "Demo", "customer_id": "c"}],
        "relations": [
            {"from_id": "p", "to_id": "c", "relation": "contact", "confirmed": False}
        ],
        "cases": [
            {
                "id": "o",
                "title": "Synthetic order",
                "case_type": "order",
                "customer_id": "c",
            }
        ],
        "profile": {"english_style": "short paragraphs"},
        "knowledge": [
            {
                "scope": "customer",
                "subject_id": "c",
                "content": "合成客户规则",
                "confirmed": False,
            }
        ],
    }
    assert import_legacy(s, doc)["preview"]
    r = import_legacy(s, doc, True)
    assert import_legacy(s, doc, True)["duplicate"]
    assert all(not k["confirmed"] for k in s.rows("SELECT * FROM knowledge_items"))
    undo_import(s, r["batch_id"])
    assert not s.rows("SELECT * FROM categories")


def test_relationship_and_case_suggestions_require_confirmation(tmp_path):
    s = Store(tmp_path)
    seed(s)
    b = Bridge(s)
    j = b.prepare()[0]
    ops = [
        {
            "operation_id": uid(),
            "type": "suggest_relationship",
            "payload": {
                "customer_name": "Other synthetic company",
                "contact_name": "Other demo contact",
                "contact_address": "other@example.org",
                "relation": "buyer",
            },
            "evidence": [],
        },
        {
            "operation_id": uid(),
            "type": "suggest_case",
            "payload": {
                "title": "Synthetic order B",
                "case_type": "order",
                "customer_id": "demo-customer",
                "stage": "review",
            },
            "evidence": [],
        },
    ]
    b.import_result(result(j, ops))
    assert len(s.rows("SELECT * FROM customers")) == 1
    for review in s.rows("SELECT * FROM review_items WHERE state='pending'"):
        b.resolve(review["review_id"], True)
    assert len(s.rows("SELECT * FROM customers")) == 2
    assert len(s.rows("SELECT * FROM cases")) == 2


def test_unconfirmed_legacy_entities_are_not_ai_facts(tmp_path):
    s = Store(tmp_path)
    doc = {
        "schema_version": "1.0",
        "customers": [{"id": "x", "name": "Unconfirmed company", "confirmed": False}],
    }
    import_legacy(s, doc, True)
    assert not Bridge(s).prepare()[0]["context"]["customers"]
    r = s.rows("SELECT * FROM review_items WHERE kind='confirm_entity'")[0]
    Bridge(s).resolve(r["review_id"], True)
    assert (
        Bridge(s).prepare()[0]["context"]["customers"][0]["name"]
        == "Unconfirmed company"
    )


def test_multiple_mail_evidence_links_one_todo(tmp_path):
    s = Store(tmp_path)
    seed(s)
    b = Bridge(s)
    j = b.prepare()[0]
    t = j["context"]["todos"][0]
    refs = [
        {"message_id": m["message_id"], "quote": m["body_text"][:20]}
        for m in j["context"]["messages"]
    ]
    op = {
        "operation_id": uid(),
        "type": "append_progress",
        "todo_id": t["todo_id"],
        "expected_revision": t["revision"],
        "payload": {"content": "多封合成邮件共同推进同一事项"},
        "evidence": refs,
    }
    b.import_result(result(j, [op]))
    sources = s.todo(t["todo_id"])["sources"]
    assert set(e["message_id"] for e in refs).issubset(
        {source["source_ref"] for source in sources}
    )
