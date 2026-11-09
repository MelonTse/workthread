"""Run the real draft UI against a temporary workspace and an in-process synthetic provider."""

import argparse
import json
import subprocess
import tempfile
import threading
from contextlib import ExitStack
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from werkzeug.serving import make_server

from workthread import draft_api
from workthread.core import Store, dumps
from workthread.demo import seed
from workthread.server import create_app


class SyntheticEndpoint:
    def open(self, request, timeout):
        material = json.loads(json.loads(request.data)["messages"][1]["content"])
        body = (
            "Dear Lin,\n\nThank you for your note. The quoted sample price is USD 42. "
            "We will confirm the dispatch date once it is available.\n\nBest regards"
        )
        if "draft_rewrite" in material:
            assert "保留 USD 42" in material["draft_rewrite"]["feedback"][-1]["content"]
            body = "Dear Lin,\n\nThe sample price is USD 42. Dispatch date to be confirmed.\n\nBest regards"
        reply = dumps({"subject": "Re: Sample quotation", "body": body})
        return BytesIO(
            dumps(
                {"choices": [{"finish_reason": "stop", "message": {"content": reply}}]}
            ).encode()
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="node")
    parser.add_argument("--playwright", default="playwright")
    parser.add_argument("--browser", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True, parents=True)
    with (
        tempfile.TemporaryDirectory(prefix="workthread-synthetic-draft-") as folder,
        ExitStack() as stack,
    ):
        store = Store(Path(folder))
        seed(store)
        mid = store.rows(
            "SELECT message_id FROM messages ORDER BY internal_date DESC LIMIT 1"
        )[0]["message_id"]
        with store.db() as c:
            c.execute("DELETE FROM drafts WHERE message_id=?", (mid,))
            c.execute(
                "UPDATE messages SET subject=?,body_text=?,sender=?,refs='[]',in_reply_to=NULL WHERE message_id=?",
                (
                    "样品报价与发运时间 · 合成邮件",
                    (
                        "Hello,\n\nThank you for quoting USD 42 for the sample. "
                        "Could you confirm the dispatch date when it is available?\n\nLin"
                    ),
                    dumps([{"name": "Lin", "address": "lin@example.org"}]),
                    mid,
                ),
            )
        keys = {}
        stack.enter_context(
            patch.object(
                draft_api.keyring,
                "get_password",
                side_effect=lambda svc, ref: keys.get(ref),
            )
        )
        stack.enter_context(
            patch.object(
                draft_api.keyring,
                "set_password",
                side_effect=lambda svc, ref, key: keys.update({ref: key}),
            )
        )
        stack.enter_context(
            patch.object(draft_api, "build_opener", return_value=SyntheticEndpoint())
        )
        server = make_server("127.0.0.1", 0, create_app(store), threaded=True)
        thread = threading.Thread(target=server.serve_forever)
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
                    mid,
                ],
                check=True,
            )
            assert (
                len(
                    store.rows("SELECT draft_id FROM drafts WHERE message_id=?", (mid,))
                )
                == 2
            )
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    main()
