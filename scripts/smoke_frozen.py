"""Exercise the native executable, bundled web resources and plain ZIP restore via HTTP."""

import http.cookiejar
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from check_bundle import check_bundle

exe = Path(sys.argv[1]).resolve()
check_bundle(exe.parent, Path(__file__).resolve().parents[1])
with tempfile.TemporaryDirectory(prefix="workthread smoke 中文 ") as tmp:
    workspace = Path(tmp) / "workspace"
    process = subprocess.Popen(
        [str(exe), "--workspace", str(workspace), "demo", "--port", "18765"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError(process.communicate())
            try:
                page = opener.open("http://127.0.0.1:18765/").read().decode()
                break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("server did not start")
        assert "WorkThread" in page
        assert opener.open("http://127.0.0.1:18765/static/app.js").status == 200
        token = re.search(r'name="csrf-token" content="([^"]+)"', page)[1]

        def post(path, body, content_type="application/json"):
            return opener.open(
                urllib.request.Request(
                    "http://127.0.0.1:18765/api/v1" + path,
                    data=body,
                    headers={"Content-Type": content_type, "X-CSRF-Token": token},
                ),
                timeout=30,
            )

        todo = json.load(post("/todos", json.dumps({
            "title": "Frozen synthetic task", "raw_input": "Frozen synthetic task",
            "no_due_date": True,
        }).encode()))
        tid = todo["todo_id"]
        request = urllib.request.Request(
            "http://127.0.0.1:18765/api/v1/todos/" + tid,
            data=json.dumps({"changes": {"status": "in_progress"},
                             "expected_revision": todo["revision"]}).encode(),
            headers={"Content-Type": "application/json", "X-CSRF-Token": token},
            method="PATCH",
        )
        assert json.load(opener.open(request))["status"] == "in_progress"
        for content in ("First synthetic progress", "Second synthetic progress"):
            post("/todos/" + tid + "/progress", json.dumps({"content": content}).encode()).close()
        saved = json.load(opener.open("http://127.0.0.1:18765/api/v1/todos/" + tid))
        assert len(saved["logs"]) == 2

        archive = post(
            "/backup",
            json.dumps(
                {"scope": "full"}
            ).encode(),
        ).read()
        assert archive.startswith(b"PK\x03\x04")
        boundary = "WorkThreadSyntheticBoundary"
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="apply"\r\n\r\ntrue\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="backup.zip"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
            + archive
            + f"\r\n--{boundary}--\r\n".encode()
        )
        assert json.load(
            post("/restore", body, "multipart/form-data; boundary=" + boundary)
        )["restored"]
        health = json.load(opener.open("http://127.0.0.1:18765/api/v1/system/status"))
        assert health["ok"]
        restored = json.load(opener.open("http://127.0.0.1:18765/api/v1/todos/" + tid))
        assert restored["status"] == "in_progress" and len(restored["logs"]) == 2
        assert (workspace / "agent-workspace/schemas/ai-output.json").exists()
        for name in ("workthread-analysis", "workthread-intake", "workthread-knowledge"):
            deployed = workspace / "agent-workspace/.codebuddy/skills" / name / "SKILL.md"
            assert deployed.read_bytes() == (exe.parent / "_internal/workthread/resources/workbuddy_template/.codebuddy/skills" / name / "SKILL.md").read_bytes()
        assert not (workspace / "agent-workspace/.workbuddy/skills").exists()
        print(
            "Frozen native startup, HTML/JS, schemas, SQLite, plain ZIP full backup and restore: passed"
        )
    finally:
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
