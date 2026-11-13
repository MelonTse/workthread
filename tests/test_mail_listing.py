"""Synthetic archive larger than the former 500/100 UI/search limits."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from workthread.core import Store
from workthread.demo import seed
from workthread.mail_listing import mail_page
from workthread.server import create_app


def populate(store, count=623):
    seed(store)
    original = dict(store.rows("SELECT * FROM messages LIMIT 1")[0])
    with store.db() as db:
        # Keep demo messages/relationships; add distinct synthetic records.
        for i in range(count):
            row = {
                **original,
                "message_id": f"page-{i:04}",
                "fingerprint": f"page-{i:04}",
                "subject": f"分页合成样本 {i:04}",
                "internal_date": "2030-01-01T00:00:00+00:00",
                "body_text": "分页合成正文 " + "x" * 500,
                "body_html": "",
            }
            db.execute(
                f"INSERT INTO messages ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
                list(row.values()),
            )
            db.execute(
                "INSERT INTO message_fts(message_id,subject,body_text) VALUES (?,?,?)",
                (row["message_id"], row["subject"], row["body_text"]),
            )
    return count + len(
        store.rows("SELECT message_id FROM messages WHERE message_id NOT LIKE 'page-%'")
    )


def test_all_archive_and_search_pages_are_reachable(tmp_path):
    store = Store(tmp_path)
    total = populate(store)
    http = create_app(store).test_client()
    first = http.get("/api/v1/mail").json
    assert first["total"] == total > 500 and len(first["items"]) == 50
    ids = []
    for page in range(1, first["pages"] + 1):
        data = http.get(f"/api/v1/mail?page={page}&snapshot={first['snapshot']}").json
        assert all(
            len(m["preview"]) <= 100 and "body_text" not in m for m in data["items"]
        )
        ids.extend(m["message_id"] for m in data["items"])
    assert len(ids) == len(set(ids)) == total
    assert ids[:2] == ["page-0622", "page-0621"]  # stable tie-breaker
    results = mail_page(store, {"q": "分页合成样本", "page": 13})
    assert results["total"] == 623 and len(results["items"]) == 23
    assert results["items"][-1]["message_id"] == "page-0000"
    detail = http.get("/api/v1/mail/page-0000").json["message"]
    assert len(detail["body_text"]) > 100


def test_concurrent_arrivals_do_not_shift_existing_pages(tmp_path):
    store = Store(tmp_path)
    populate(store, 101)
    first = mail_page(store, {})
    second_before = mail_page(store, {"page": 2, "snapshot": first["snapshot"]})
    with store.db() as db:
        db.execute(
            "UPDATE messages SET subject='uncommitted' WHERE message_id='page-0000'"
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            data = pool.submit(mail_page, store, {"q": "分页合成样本"}).result(
                timeout=5
            )
        assert data["total"] == 101
    row = dict(store.rows("SELECT * FROM messages WHERE message_id='page-0000'")[0])
    row.update(
        message_id="new-arrival", fingerprint="new-arrival", internal_date="2031-01-01"
    )
    with store.db() as db:
        db.execute(
            f"INSERT INTO messages ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
            list(row.values()),
        )
    second_after = mail_page(store, {"page": 2, "snapshot": first["snapshot"]})
    assert second_after["items"] == second_before["items"]
    assert second_after["new_count"] == 1
    assert mail_page(store, {})["items"][0]["message_id"] == "new-arrival"


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": "abc"},
        {"page_size": 101},
        {"snapshot": -1},
        {"q": "x" * 501},
    ],
)
def test_invalid_parameters_rejected(tmp_path, params):
    with pytest.raises(ValueError):
        mail_page(Store(tmp_path), params)


def test_empty_page_and_literal_search(tmp_path):
    store = Store(tmp_path)
    assert mail_page(store, {"page": 99})["items"] == []
    populate(store, 1)
    assert mail_page(store, {"q": "%_"})["total"] == 0
    assert mail_page(store, {"q": '" OR *'})["total"] == 0
    last = mail_page(store, {"page": 999})
    assert last["page"] == last["pages"] == 1
