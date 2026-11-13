"""Only maintainer-signed GitHub Release assets can enter the install transaction."""

import base64
import hashlib
import http.client
import json
import ntpath
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from packaging.version import Version

from ..diagnostics import describe_error

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
        raise ValueError(
            "发布签名无效，已停止更新。请重新下载官方 update.json 和 update.sig；仍失败时联系维护者，不要跳过验签"
        ) from e
    try:
        m = json.loads(document)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(
            "发布清单 update.json 不是有效 JSON，请重新检查更新并联系维护者核对发布文件"
        ) from exc
    if (
        not isinstance(m, dict)
        or any(
            not isinstance(m.get(k), str) for k in ("version", "commit_sha", "sha256")
        )
        or not isinstance(m.get("sources"), list)
        or type(m.get("size")) is not int
    ):
        raise ValueError(
            "发布清单 update.json 字段缺失或类型错误，请联系维护者核对签名发布清单"
        )
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


class FetchError(ValueError):
    def __init__(self, message, diagnostic):
        super().__init__(message)
        self.diagnostic = diagnostic


def proxy_source(url):
    scheme, host = (
        urllib.parse.urlsplit(url).scheme,
        urllib.parse.urlsplit(url).hostname,
    )
    try:
        if not host or urllib.request.proxy_bypass(host):
            return "直连"
        if scheme in urllib.request.getproxies_environment():
            return "环境变量代理"
        if scheme in urllib.request.getproxies():
            return "系统代理"
        return "直连"
    except (OSError, ValueError):
        return "未识别"


def http_details(exc):
    if not isinstance(exc, urllib.error.HTTPError):
        return None, None, False
    headers = exc.headers or {}
    retry_at = None
    retry_after = headers.get("Retry-After", "")
    remaining = headers.get("X-RateLimit-Remaining") == "0"
    try:
        if retry_after.isascii() and retry_after.isdecimal():
            timestamp = time.time() + int(retry_after)
        elif retry_after:
            when = parsedate_to_datetime(retry_after)
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            timestamp = when.timestamp()
        elif remaining:
            timestamp = int(headers["X-RateLimit-Reset"])
        else:
            timestamp = 0
        if timestamp > time.time():
            retry_at = datetime.fromtimestamp(timestamp, UTC).isoformat()
    except (ValueError, OverflowError, OSError, KeyError, TypeError):
        pass
    return exc.code, retry_at, exc.code == 429 or (exc.code == 403 and remaining)


def fetch(url, limit, out=None):
    req = urllib.request.Request(
        url, headers={"User-Agent": "WorkThread-local-updater"}
    )
    stage = "下载 Windows 安装包" if out is not None else "读取发布信息"
    if url.startswith("https://api.github.com/"):
        stage = "检查 GitHub 版本列表"

    item = "Windows ZIP" if out is not None else "版本列表"
    for name in ("update.json", "update.sig"):
        if urllib.parse.urlsplit(url).path.endswith("/" + name):
            item = name
    proxy = proxy_source(url)
    # Each metadata retry starts from the original URL and uses a fresh response.
    for attempt in range(2):
        host = urllib.parse.urlsplit(url).hostname
        phase, received = "连接或等待响应头", 0
        try:
            response = urllib.request.urlopen(req, timeout=40)
            with response:
                if not response.geturl().startswith("https://"):
                    raise ValueError("拒绝非 HTTPS 下载")
                host = urllib.parse.urlsplit(response.geturl()).hostname
                proxy = proxy_source(response.geturl())
                phase = "读取响应内容"
                if out is None:
                    data = response.read(limit + 1)
                    received = len(data)
                    if received > limit:
                        raise ValueError("发布元数据过大")
                    length = getattr(response, "headers", {}).get("Content-Length", "")
                    if length.isdigit() and received < int(length):
                        raise http.client.IncompleteRead(b"", int(length) - received)
                    return data
                length = getattr(response, "headers", {}).get("Content-Length", "")
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > limit:
                        raise ValueError("下载超出声明大小")
                    phase = "保存下载文件"
                    out.write(chunk)
                    phase = "读取响应内容"
                if length.isdigit() and received < int(length):
                    raise http.client.IncompleteRead(b"", int(length) - received)
                return
        except (OSError, http.client.HTTPException) as exc:
            reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
            transient = isinstance(
                reason, (TimeoutError, ConnectionError, http.client.IncompleteRead)
            )
            status, retry_at, limited = http_details(exc)
            if isinstance(exc, urllib.error.HTTPError):
                host = urllib.parse.urlsplit(exc.geturl()).hostname
                proxy = proxy_source(exc.geturl())
                transient = exc.code in (502, 503, 504)
                exc.close()
            retry = (
                transient
                and attempt == 0
                and (out is None or phase == "连接或等待响应头")
            )
            if retry:
                time.sleep(0.3)
                continue
            detail = describe_error(exc)
            if status == 403:
                detail = (
                    "HTTP 403：响应显示请求额度已用完"
                    if limited
                    else "HTTP 403：访问被拒绝，具体原因未确定。请检查代理访问策略或稍后重试"
                )
            if retry_at:
                detail += f"；服务端建议重试时间：{retry_at}"
            if out is not None and received:
                detail += "；未完成的安装包不可用，请重新下载"
            raise FetchError(
                f"{stage}失败（{item}，{host}，{phase}，{proxy}，尝试 {attempt + 1} 次，已接收 {received} 字节）："
                f"{detail}。错误类型 {type(reason).__name__}",
                {
                    "resource": item,
                    "host": host,
                    "network_phase": phase,
                    "proxy_source": proxy,
                    "tries": attempt + 1,
                    "bytes_received": received,
                    "http_status": status,
                    "retry_at": retry_at,
                    "error_type": type(reason).__name__,
                },
            ) from exc


def discover(current, key):
    choices = []
    for page in range(1, 11):
        try:
            rows = json.loads(
                fetch(
                    f"https://api.github.com/repos/{REPO}/releases?per_page=30&page={page}",
                    8 * 1024**2,
                )
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(
                "GitHub 版本列表不是有效 JSON，请检查代理是否返回了登录页或拦截页，再重新检查更新"
            ) from exc
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("GitHub 版本列表结构不正确，请稍后重试并检查代理响应")
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
        raise ValueError(
            f"安装包大小或 SHA-256 不匹配（实际 {path.stat().st_size} 字节，声明 {m['size']} 字节），已停止更新。文件可能未完整下载或内容已变化，请重新下载官方安装包，不要强制安装"
        )


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
