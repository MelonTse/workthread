"""Synthetic mail pagination browser check; no external mail connection."""

import argparse
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from werkzeug.serving import make_server

from workthread.core import Store
from workthread.server import create_app

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_mail_listing import populate


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--node", default="node")
    p.add_argument("--playwright", required=True)
    p.add_argument("--browser", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wt-mail-pages-") as d:
        store = Store(Path(d))
        total = populate(store)
        server = make_server("127.0.0.1", 0, create_app(store), threaded=True)
        t = threading.Thread(target=server.serve_forever)
        t.start()
        try:
            subprocess.run(
                [
                    a.node,
                    str(Path(__file__).with_suffix(".cjs")),
                    a.playwright,
                    a.browser,
                    f"http://127.0.0.1:{server.server_port}",
                    str(a.output.resolve()),
                    str(total),
                ],
                check=True,
            )
        finally:
            server.shutdown()
            t.join()
            server.server_close()


if __name__ == "__main__":
    main()
