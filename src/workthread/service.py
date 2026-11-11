"""Own a workspace service until all of its writers have stopped."""

import http.client
import json
import os
import secrets
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

from filelock import FileLock, Timeout

from .updating.releases import save


class ServiceInstance:
    def __init__(self, workspace, port):
        self.root = Path(workspace).expanduser().resolve()
        self.port = port
        self.record = self.root / ".workthread-service.json"
        self.lock = FileLock(str(self.root / ".workthread-service.lock"), timeout=0)
        self.socket = None
        self.instance_id = secrets.token_hex(24)
        self.url = None

    def __enter__(self):
        if not 0 <= self.port <= 65535:
            raise ValueError("端口必须在 0 至 65535 之间")
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            self.lock.acquire()
        except Timeout:
            self.url = self._existing_url()
            return self
        try:
            # A stale record after a crash cannot establish ownership. Only the OS lock can.
            self.record.unlink(missing_ok=True)
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if os.name == "nt":
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self.socket.bind(("127.0.0.1", self.port))
                self.socket.listen(128)
            except OSError as exc:
                raise ValueError(
                    f"无法监听本机端口 {self.port}，请检查已有 WorkThread 或其他程序。"
                ) from exc
            self.port = self.socket.getsockname()[1]
            self.url = f"http://127.0.0.1:{self.port}"
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def ready(self):
        save(self.record, {"port": self.port, "instance_id": self.instance_id})

    def _existing_url(self):
        # Loopback verification must not inherit a proxy from WorkBuddy's shell.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                record = json.loads(self.record.read_text(encoding="utf-8"))
                port = record["port"]
                if type(port) is not int or not 1 <= port <= 65535:
                    raise ValueError("invalid port")
                url = f"http://127.0.0.1:{port}"
                with opener.open(url + "/api/v1/instance", timeout=0.5) as response:
                    status = json.loads(response.read(4096))
                if status.get("instance_id") == record["instance_id"]:
                    return url
            except (OSError, ValueError, KeyError, http.client.HTTPException):
                pass
            time.sleep(0.1)
        raise ValueError("此工作空间已有服务正在启动、退出或暂时无法响应，请稍后再试。")

    def __exit__(self, *args):
        if not self.lock.is_locked:
            return
        try:
            if self.socket is not None:
                self.socket.close()
            self.record.unlink(missing_ok=True)
        finally:
            self.lock.release()
