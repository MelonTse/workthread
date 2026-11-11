"""Exercise duplicate startup through the CLI in independent OS processes."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from workthread.service import ServiceInstance


PROGRAM = """
from pathlib import Path
import os, sys, webbrowser
from workthread import cli
original = cli.worker
def worker(store, stop, tasks):
    with (store.root / 'worker-starts').open('a') as f:
        f.write(str(os.getpid()) + '\\n')
    original(store, stop, tasks)
cli.worker = worker
webbrowser.open = lambda url: print('BROWSER ' + url, flush=True)
cli.main()
"""


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def launch(tmp_path):
    processes = []

    def start(workspace, port, program=PROGRAM):
        log = tmp_path / f"process-{len(processes)}.txt"
        with log.open("wb") as stream:
            proc = subprocess.Popen(
                [sys.executable, "-c", program, "--workspace", str(workspace),
                 "serve", "--port", str(port), "--open"],
                stdout=stream, stderr=subprocess.STDOUT,
                env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src")),
            )
        processes.append((proc, log))
        return proc, log

    yield start
    for proc, _ in processes:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    pytest.fail("service startup did not reach the expected state")


def identity(port):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/v1/instance", timeout=0.5) as r:
            return json.load(r)["instance_id"]
    except (OSError, ValueError):
        return None


def workers(space):
    path = space / "worker-starts"
    return path.read_text().splitlines() if path.exists() else []


def test_simultaneous_launches_open_one_service_and_one_worker(tmp_path, launch):
    space, port = tmp_path / "用户 workspace", free_port()
    p1, log1 = launch(space, port)
    p2, log2 = launch(space, port)
    wait_for(lambda: identity(port))
    wait_for(lambda: p1.poll() is not None or p2.poll() is not None)
    exits = [p1.poll(), p2.poll()]
    assert exits.count(0) == 1 and exits.count(None) == 1
    wait_for(lambda: len(workers(space)) == 1)
    for log in (log1, log2):
        assert f"BROWSER http://127.0.0.1:{port}" in log.read_text(encoding="utf-8")
    # A different requested port still reuses this workspace's original service.
    another_port = free_port()
    duplicate, log = launch(space / ".", another_port)
    assert duplicate.wait(timeout=15) == 0
    assert f"BROWSER http://127.0.0.1:{port}" in log.read_text(encoding="utf-8")
    assert len(workers(space)) == 1
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", another_port))


def test_independent_workspaces_can_run_on_different_ports(tmp_path, launch):
    first_port = free_port()
    first, _ = launch(tmp_path / "workspace", first_port)
    first_id = wait_for(lambda: identity(first_port))
    second_port = free_port()
    second, _ = launch(tmp_path / "acceptance", second_port)
    second_id = wait_for(lambda: identity(second_port))
    assert first_id != second_id
    assert first.poll() is None and second.poll() is None


def test_occupied_port_fails_before_workspace_initialization(tmp_path, launch):
    space = tmp_path / "new-workspace"
    with socket.socket() as occupied:
        # Match an old rc7 listener's use of SO_REUSEADDR on Windows too.
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        proc, log = launch(space, port)
        assert proc.wait(timeout=15) == 2
        assert "无法监听本机端口" in log.read_text(encoding="utf-8")
        assert not (space / "data").exists() and workers(space) == []
        assert not (space / ".workthread-service.json").exists()


def test_crash_releases_lock_and_stale_identity_can_be_replaced(tmp_path, launch):
    space, port = tmp_path / "workspace", free_port()
    proc, _ = launch(space, port)
    old_id = wait_for(lambda: identity(port))
    wait_for(lambda: workers(space))
    proc.kill()
    proc.wait(timeout=10)
    assert json.loads((space / ".workthread-service.json").read_text())["instance_id"] == old_id
    new, _ = launch(space, port)
    new_id = wait_for(lambda: identity(port))
    assert new_id != old_id and new.poll() is None
    wait_for(lambda: len(workers(space)) == 2)


def test_startup_failure_releases_instance_lock(tmp_path, launch):
    space, port = tmp_path / "workspace", free_port()
    failed, log = launch(space, port, PROGRAM.replace(
        "cli.main()", "cli.install_templates = lambda store: (_ for _ in ()).throw(ValueError('fixture startup failure'))\ncli.main()"
    ))
    assert failed.wait(timeout=15) == 2
    assert "fixture startup failure" in log.read_text(encoding="utf-8")
    assert workers(space) == []
    proc, _ = launch(space, port)
    wait_for(lambda: identity(port))
    assert proc.poll() is None


def test_clean_exit_removes_identity_and_keeps_lock_file(tmp_path):
    with ServiceInstance(tmp_path, 0) as service:
        service.ready()
        port = service.port
        assert service.record.exists()
    assert not service.record.exists()
    assert (tmp_path / ".workthread-service.lock").exists()
    with ServiceInstance(tmp_path, port) as restarted:
        assert restarted.socket is not None


def test_failed_metadata_cleanup_does_not_leak_lock(tmp_path):
    # A malformed record must fail safely, with the lock available for later repair.
    record = tmp_path / ".workthread-service.json"
    record.mkdir()
    with pytest.raises(OSError):
        with ServiceInstance(tmp_path, 0):
            pass
    record.rmdir()
    with ServiceInstance(tmp_path, 0) as service:
        assert service.socket is not None


@pytest.mark.parametrize("code", [0, 2])
def test_maintenance_launcher_preserves_child_exit_code(monkeypatch, code):
    from workthread.cli import main
    from workthread.updating import controller

    monkeypatch.setattr(controller, "cli", lambda args: code)
    with pytest.raises(SystemExit) as result:
        main(["--maintenance", "launch", "synthetic-root"])
    assert result.value.code == code


def test_launcher_waits_for_concurrent_startup_admission(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from filelock import FileLock
    from workthread.updating import controller as ctl

    state = tmp_path / ctl.tx.STATE
    state.mkdir()
    entered, launched = threading.Event(), threading.Event()
    monkeypatch.setattr(ctl.tx, "current", lambda root: (tmp_path, {}))

    class Child:
        def __init__(self, args):
            launched.set()

        def wait(self):
            return 0

    monkeypatch.setattr(ctl.subprocess, "Popen", Child)

    def launch():
        entered.set()
        return ctl.launch(tmp_path, ["serve"])

    with ThreadPoolExecutor(max_workers=1) as pool:
        with FileLock(str(state / "install.lock"), timeout=0):
            future = pool.submit(launch)
            assert entered.wait(2)
            assert not launched.wait(0.2)
            assert not future.done()
        assert future.result(timeout=5) == 0
    ctl.no_leases(state)


def test_normal_shutdown_keeps_ownership_until_active_request_finishes(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from filelock import FileLock, Timeout
    from waitress.task import ThreadedTaskDispatcher
    from workthread import cli, server
    from workthread.updating import controller as ctl

    entered, release, draining = threading.Event(), threading.Event(), threading.Event()
    controllers = []
    original_app = server.create_app
    original_shutdown = ThreadedTaskDispatcher.shutdown

    class Controlled(ctl.Updates):
        def __init__(self, *args):
            super().__init__(*args)
            controllers.append(self)

    def app(*args):
        result = original_app(*args)

        @result.get("/hold")
        def hold():
            entered.set()
            assert release.wait(10)
            return "finished"

        return result

    def shutdown(dispatcher, *args, **kwargs):
        original_shutdown(dispatcher, timeout=0)
        draining.set()

    monkeypatch.setattr(ctl, "Updates", Controlled)
    monkeypatch.setattr(server, "create_app", app)
    monkeypatch.setattr(ThreadedTaskDispatcher, "shutdown", shutdown)
    port = free_port()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request():
        with opener.open(f"http://127.0.0.1:{port}/hold", timeout=10) as response:
            return response.read()

    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(cli.main, ["--workspace", str(tmp_path), "serve", "--port", str(port)])
        try:
            wait_for(lambda: identity(port))
            response = pool.submit(request)
            assert entered.wait(5)
            controllers[0].stop()
            assert draining.wait(5)
            assert not running.done()
            with pytest.raises(Timeout):
                with FileLock(str(tmp_path / ".workthread-service.lock"), timeout=0):
                    pass
        finally:
            release.set()
            if controllers:
                controllers[0].stop()
        assert response.result(timeout=5) == b"finished"
        running.result(timeout=5)
    assert not (tmp_path / ".workthread-service.json").exists()
