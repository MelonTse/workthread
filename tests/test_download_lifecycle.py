"""The streamed ZIP must own its temporary directory until its file closes."""

import gc
import io
from pathlib import Path
import zipfile

import pytest

from workthread.core import Store
import workthread.server as server
from test_m4 import client


@pytest.mark.parametrize("scope", ["todos", "full"])
@pytest.mark.parametrize("consume", [False, True])
def test_http_download_keeps_temp_archive_until_stream_close(tmp_path, monkeypatch, scope, consume):
    original = server.tempfile.TemporaryDirectory
    directories = []

    def track(*args, **kwargs):
        directory = original(*args, **kwargs)
        if kwargs.get("prefix") == "workthread-download-":
            directories.append(Path(directory.name))
        return directory

    monkeypatch.setattr(server.tempfile, "TemporaryDirectory", track)
    c, headers = client(Store(tmp_path / "synthetic"))
    response = c.post("/api/v1/backup", json={"scope": scope}, headers=headers, buffered=False)
    try:
        gc.collect()
        assert response.status_code == 200 and len(directories) == 1
        assert directories[0].is_dir(), "ZIP must survive while the response stream is open"
        if consume:
            with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                assert archive.testzip() is None
        assert directories[0].is_dir()
    finally:
        response.close()
    assert not directories[0].exists(), "close the file before removing its temporary directory"
