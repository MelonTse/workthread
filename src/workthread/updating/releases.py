"""Only maintainer-signed GitHub Release assets can enter the install transaction."""

import base64
import hashlib
import json
import ntpath
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from packaging.version import Version

REPO = "MelonTse/workthread"
RC3 = frozenset(
    {
        "66fea8f746963561268382b6ab3735eefdc0704f",
        "1ce8e085f6a1578f7cb94f649df96c4d42983e36",
    }
)
MAX_ARCHIVE = 1024**3
MAX_EXPANDED = 3 * MAX_ARCHIVE


def version(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+(?:rc[0-9]+)?", value
    ):
        raise ValueError("不支持的发布版本")
    return Version(value)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        try:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            f.close()
            tmp.unlink(missing_ok=True)
            raise
    try:
        if os.name == "nt":
            import ctypes

            if not ctypes.windll.kernel32.MoveFileExW(str(tmp), str(path), 1 | 8):
                raise ctypes.WinError()
        else:
            tmp.replace(path)
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        tmp.unlink(missing_ok=True)


def save(path, value):
    atomic(path, json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def trust():
    p = Path(__file__).with_name("release-public.hex")
    if not p.is_file():
        raise ValueError("此构建未配置发布验证公钥，不能安装更新")
    return Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(p.read_text(encoding="ascii").strip())
    )


def signed(document, sig, key, current):
    try:
        key.verify(base64.b64decode(sig, validate=True), document)
    except (ValueError, InvalidSignature) as e:
        raise ValueError("发布签名无效") from e
    m = json.loads(document)
    v = m["version"]
    if (
        version(v) <= version(current["version"])
        or (not version(current["version"]).is_prerelease and version(v).is_prerelease)
        or m.get("format") != 1
        or m.get("repository") != REPO
        or m.get("platform") != "windows-x64"
        or m.get("asset") != f"WorkThread-{v}-windows-x64.zip"
        or not re.fullmatch("[a-f0-9]{40}", m["commit_sha"])
        or not re.fullmatch("[a-f0-9]{64}", m["sha256"])
        or type(m["size"]) is not int
        or not 0 < m["size"] <= MAX_ARCHIVE
        or current["version"] + "@" + current["commit_sha"] not in m["sources"]
    ):
        raise ValueError("发布版本、安装包或来源构建不兼容")
    return m


def fetch(url, limit, out=None):
    req = urllib.request.Request(
        url, headers={"User-Agent": "WorkThread-local-updater"}
    )
    with urllib.request.urlopen(req, timeout=40) as response:
        if not response.geturl().startswith("https://"):
            raise ValueError("拒绝非 HTTPS 下载")
        if out is None:
            data = response.read(limit + 1)
            if len(data) > limit:
                raise ValueError("发布元数据过大")
            return data
        size = 0
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise ValueError("下载超出声明大小")
            out.write(chunk)


def discover(current, key):
    choices = []
    for page in range(1, 11):
        rows = json.loads(
            fetch(
                f"https://api.github.com/repos/{REPO}/releases?per_page=30&page={page}",
                8 * 1024**2,
            )
        )
        for row in rows:
            tag = row["tag_name"]
            try:
                v = version(tag.removeprefix("v"))
            except ValueError:
                continue
            if (
                tag != f"v{v}"
                or row["draft"]
                or v <= version(current["version"])
                or (
                    (row["prerelease"] or v.is_prerelease)
                    and not version(current["version"]).is_prerelease
                )
            ):
                continue
            names = {a["name"] for a in row["assets"]}
            if {
                "update.json",
                "update.sig",
                f"WorkThread-{v}-windows-x64.zip",
            } <= names:
                choices.append((v, row.get("body") or ""))
        if len(rows) < 30:
            break
    for v, notes in sorted(choices, reverse=True):
        base = f"https://github.com/{REPO}/releases/download/v{v}/"
        doc = fetch(base + "update.json", 65536)
        sig = fetch(base + "update.sig", 256).strip()
        try:
            m = signed(doc, sig, key, current)
        except ValueError as e:
            if str(e) == "发布版本、安装包或来源构建不兼容":
                continue
            raise
        if m["version"] != str(v):
            raise ValueError("发布标签不匹配")
        return {
            "doc": doc.decode(),
            "sig": sig.decode(),
            "notes": notes[:8000],
            "version": str(v),
        }
    return None


def verify_zip(path, m):
    if path.stat().st_size != m["size"] or digest(path) != m["sha256"]:
        raise ValueError("安装包大小或 SHA-256 不匹配")


def extract(path, dest, m):
    verify_zip(path, m)
    prefix = m["asset"][:-4]
    seen = set()
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        if len(infos) > 30000 or sum(i.file_size for i in infos) > MAX_EXPANDED:
            raise ValueError("安装包解压超出限制")
        for i in infos:
            parts = i.filename.rstrip("/").split("/")
            if (
                parts[0] != prefix
                or any(
                    not p
                    or p in {".", ".."}
                    or p.endswith((".", " "))
                    or re.search(r'[<>:"\\|?*\x00-\x1f]', p)
                    or ntpath.isreserved(p)
                    for p in parts
                )
                or ((i.external_attr >> 16) & 0o170000) == 0o120000
            ):
                raise ValueError("安装包路径无效")
            name = "/".join(parts).casefold()
            if name in seen:
                raise ValueError("安装包路径重复")
            seen.add(name)
            target = dest.joinpath(*parts[1:])
            if i.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(i) as src, target.open("xb") as dst:
                    shutil.copyfileobj(src, dst)
    info = read(dest / "BUILD_INFO.json")
    if any(info[k] != m[k] for k in ("version", "commit_sha")) or (
        info.get("runner_os") != "Windows"
        or str(info.get("machine", "")).lower() not in ("amd64", "x86_64")
    ):
        raise ValueError("BUILD_INFO 与签名信息不符")
    if not (dest / "app/WorkThread.exe").is_file():
        raise ValueError("安装包缺少 Windows EXE")
    index = read(dest / "SHA256SUMS.json")
    actual = {
        p.relative_to(dest).as_posix(): digest(p)
        for p in dest.rglob("*")
        if p.is_file() and p != dest / "SHA256SUMS.json"
    }
    if actual != index:
        raise ValueError("安装包文件清单不匹配")
