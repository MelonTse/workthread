from workthread.core import Store
from workthread.demo import FakeIMAP, seed
from workthread.mail import Sync, body_parts, UnsafeMime
import pytest


def account(s):
    with s.db() as c:
        c.execute(
            "INSERT INTO mail_accounts VALUES (?,?,?,?,?,?,?,?)",
            (
                "demo",
                "demo",
                "imap.example.org",
                993,
                "local@example.org",
                "synthetic",
                "[]",
                0,
            ),
        )


def test_incremental_no_attachment_and_thread(tmp_path):
    s = Store(tmp_path)
    account(s)
    fake = FakeIMAP()
    sync = Sync(s, lambda a: fake)
    assert not sync.run("demo")["errors"]
    count = len(fake.requests)
    sync.run("demo")
    assert len(fake.requests) == count
    assert len(s.rows("SELECT * FROM messages")) == 3
    mid = s.rows("SELECT message_id FROM messages")[0]["message_id"]
    assert len(s.thread(mid)) == 3 and s.search("Aurora")
    body = "".join(p.read_text() for p in (s.data / "body").glob("*.jsonl"))
    assert "demo.pdf" not in body and "999999" not in body
    meta = "".join(p.read_text() for p in (s.data / "meta").glob("*.jsonl"))
    assert "demo.pdf" in meta and "Demo Team" in meta


def test_failure_uid_retried_and_reset_deduplicated(tmp_path):
    s = Store(tmp_path)
    account(s)
    fake = FakeIMAP()
    fake.fail_uid = 2
    sync = Sync(s, lambda a: fake)
    assert sync.run("demo")["errors"]
    fake.fail_uid = None
    sync.run("demo")
    assert len(s.rows("SELECT * FROM messages")) == 3
    fake.validity = 101
    sync.run("demo")
    assert len(s.rows("SELECT * FROM messages")) == 3
    assert not s.rows("SELECT * FROM sync_failures")


def test_malformed_mime_has_no_full_fallback(tmp_path):
    with pytest.raises(UnsafeMime):
        body_parts((b"TEXT",))


def test_demo_full_bridge(tmp_path):
    s = Store(tmp_path)
    seed(s)
    assert s.rows("SELECT * FROM analyses") and s.rows("SELECT * FROM drafts")
    assert s.health()["ok"]


def test_real_imapclient_bodydata_shape_and_bad_charset():
    from imapclient.response_types import BodyData
    from workthread.demo import PLAIN, ATTACHMENT
    from workthread.mail import decode_part

    structure = BodyData.create((PLAIN, ATTACHMENT, b"MIXED", None, None))
    parts, metadata = body_parts(structure)
    assert [p["section"] for p in parts] == ["1"] and metadata[0][
        "filename"
    ] == "demo.pdf"
    with pytest.raises(UnsafeMime):
        decode_part(b"\xff", {"encoding": "8BIT", "charset": "utf-8"})


def test_monthly_archive_does_not_rescan_per_message(tmp_path, monkeypatch):
    import workthread.mail as module

    scans = []
    original = module.repair_lines

    def counted(path):
        scans.append(path)
        return original(path)

    monkeypatch.setattr(module, "repair_lines", counted)
    s = Store(tmp_path)
    account(s)
    Sync(s, lambda a: FakeIMAP()).run("demo")
    # Three mails in the same month require only the initial meta/body scans.
    assert len(scans) == 2
