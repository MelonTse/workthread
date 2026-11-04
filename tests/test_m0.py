from workthread.core import Store
from workthread.ai import Bridge


def test_contract_roundtrip(tmp_path):
    s = Store(tmp_path)
    b = Bridge(s)
    j = b.prepare()[0]
    result = {
        k: j[k]
        for k in (
            "schema_version",
            "workspace_id",
            "workspace_epoch",
            "job_id",
            "input_sha256",
        )
    }
    result.update(outcome="completed", reviewed_todo_ids=[], operations=[], warnings=[])
    assert b.import_result(result)["state"] == "completed"
    assert b.import_result(result)["duplicate"]
    assert s.health()["ok"]


def test_bad_contract_is_atomic(tmp_path):
    import pytest

    s = Store(tmp_path)
    b = Bridge(s)
    with pytest.raises(Exception):
        b.import_result({"sql": "DROP TABLE todos"})
    assert s.health()["ok"]
