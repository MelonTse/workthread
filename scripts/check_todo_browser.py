"""Exercise the local webpage using a disposable mailbox and synthetic chat response."""

import argparse
import json
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from threading import Thread
from unittest.mock import patch

from werkzeug.serving import make_server

from workthread import draft_api
from workthread.core import Store, dumps
from workthread.demo import FakeIMAP
from workthread.mail import Sync
from workthread.server import create_app


class SampleMail(FakeIMAP):
    def search(self, criteria):
        return [1, 2] if self.folder == "INBOX" else []

    def fetch(self, uids, items):
        packet = super().fetch(uids, items)
        fields = packet[uids[0]]
        if b"BODY[1]" in fields:
            fields[b"BODY[1]"] = (
                b"Please confirm the sample quotation."
                if uids[0] == 1
                else b"The supplier has received the sample request. We are waiting for their quote."
            )
        if b"BODY[HEADER]" in fields:
            fields[b"BODY[HEADER]"] = fields[b"BODY[HEADER]"].replace(
                b"Project Aurora schedule", b"Sample quotation"
            )
        return packet


class SyntheticEndpoint:
    def open(self, request, timeout):
        material = json.loads(json.loads(request.data)["messages"][1]["content"])
        decisions = []
        for src in material["sources"]:
            item = {
                "kind": "new",
                "target": "",
                "title": "确认样品报价",
                "status": "",
                "quote": src["raw"],
                "note": "跟进供应商的样品报价。",
            }
            if src["kind"] == "mail":
                item["target"] = material["todos"][0]["todo_id"]
                if src["raw"].startswith("Please"):
                    item.update(
                        kind="duplicate",
                        title="跟进样品报价",
                        note="来信与已录入的报价事项可能重复。",
                    )
                else:
                    item.update(
                        kind="status",
                        title="",
                        note="供应商已收到样品要求，正在等待报价。",
                        status="waiting",
                    )
            decisions.append({"source_id": src["id"], "actions": [item]})
        content = dumps({"decisions": decisions})
        return BytesIO(
            dumps(
                {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": content}}
                    ]
                }
            ).encode()
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="node")
    parser.add_argument("--playwright", default="playwright")
    parser.add_argument("--browser", default="")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="workthread-todo-test-") as tmp:
        store = Store(Path(tmp))
        with store.db() as c:
            c.execute(
                "INSERT INTO mail_accounts VALUES (?,?,?,?,?,?,?,?)",
                (
                    "demo",
                    "合成验收",
                    "imap.example.org",
                    993,
                    "user@example.org",
                    "synthetic",
                    "[]",
                    0,
                ),
            )
        Sync(store, lambda account: SampleMail()).run("demo")
        mids = [
            m["message_id"]
            for m in store.rows(
                "SELECT message_id FROM messages ORDER BY rfc_message_id"
            )
        ]
        store.set_setting(
            "draft_ai",
            {"mode": "workbuddy", "provider": "hy", "model": "synthetic-fixture"},
        )
        with (
            patch.object(draft_api, "get_key", return_value="fixture"),
            patch.object(draft_api, "build_opener", return_value=SyntheticEndpoint()),
        ):
            server = make_server("127.0.0.1", 0, create_app(store), threaded=True)
            thread = Thread(target=server.serve_forever)
            thread.start()
            try:
                subprocess.run(
                    [
                        args.node,
                        str(Path(__file__).with_suffix(".cjs")),
                        args.playwright,
                        args.browser,
                        str(args.output.resolve()),
                        f"http://127.0.0.1:{server.server_port}",
                        str(store.root / "agent-workspace" / "exchange"),
                        *mids,
                    ],
                    check=True,
                )
                rows = store.rows(
                    "SELECT todo_id FROM todos WHERE merged_into_id IS NULL"
                )
                assert len(rows) == 1
                todo = store.todo(rows[0]["todo_id"])
                assert (
                    todo["status"] == "waiting"
                    and len(todo["logs"]) == 1
                    and len(todo["sources"]) == 3
                )
            finally:
                server.shutdown()
                thread.join()
                server.server_close()


if __name__ == "__main__":
    main()
