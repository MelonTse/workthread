"""Run browser regression only against a disposable synthetic workspace.

Requires Node and Playwright (supplied by the caller, not runtime dependencies).
"""

import argparse
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from werkzeug.serving import make_server

from workthread.core import Store, now, uid
from workthread.demo import seed
from workthread.server import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="node")
    parser.add_argument("--playwright", default="playwright")
    parser.add_argument("--browser", default="")
    parser.add_argument("--output", type=Path, default=Path("artifacts/ui-v3-check"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="workthread-ui-test-") as directory:
        store = Store(Path(directory))
        seed(store)
        # Include draft alternatives and messages without relying on demo's one draft.
        with store.db() as db:
            for mail in store.rows("SELECT message_id FROM messages"):
                db.execute(
                    "INSERT INTO drafts VALUES (?,?,?,?,?,?,?,?)",
                    (
                        uid(),
                        mail["message_id"],
                        None,
                        "Synthetic alternate reply",
                        "Synthetic draft for browser regression",
                        1,
                        now(),
                        now(),
                    ),
                )
        server = make_server("127.0.0.1", 0, create_app(store), threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = {
                **os.environ,
                "WORKTHREAD_UI_TEST_URL": f"http://127.0.0.1:{server.server_port}",
                "WORKTHREAD_PLAYWRIGHT": args.playwright,
                "WORKTHREAD_BROWSER": args.browser,
                "WORKTHREAD_UI_OUTPUT": str(output),
                "WORKTHREAD_UI_TEST_WORKSPACE": directory,
            }
            result = subprocess.run(
                [args.node, str(Path(__file__).with_suffix(".cjs"))],
                env=env,
                check=False,
            )
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
