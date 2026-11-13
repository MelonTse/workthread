"""A same-volume, journalled switch. Never merge into or delete a live workspace."""

import contextlib
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import uuid
from pathlib import Path

from filelock import FileLock

from .releases import RC3, atomic, digest, extract, read, save, signed, version

SPACES = ("workspace", "acceptance")
STATE = ".workthread-updates"
EXE = Path("app/WorkThread.exe")


def safe(p):
    if (
        p.is_symlink()
        or p.is_junction()
        or (
            p.exists()
            and getattr(p.lstat(), "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        )
    ):
        raise ValueError(f"拒绝链接或重解析点：{p.name}")
    return p


def catalog(root):
    safe(root)
    result = {}
    for parent, dirs, files in root.walk(on_error=lambda e: (_ for _ in ()).throw(e)):
        for name in dirs + files:
            p = safe(parent / name)
            if p.is_dir():
                result[p.relative_to(root).as_posix()] = None
            elif p.is_file():
                result[p.relative_to(root).as_posix()] = digest(p)
            else:
                raise ValueError("不支持的文件类型：" + name)
    return result


def current(root):
    state = safe(root / STATE)
    ptr = safe(state / "active.json")
    base = safe(state / "base")
    folder = base if base.is_dir() else root
    if ptr.exists():
        sha = read(ptr)["commit_sha"]
        if not re.fullmatch("[0-9a-f]{40}", sha):
            raise ValueError("无效的版本指针")
        folder = safe(safe(state / "versions") / sha)
    identity = read(safe(folder / "BUILD_INFO.json"))
    if ptr.exists() and identity["commit_sha"] != sha:
        raise ValueError("当前程序与版本指针不匹配")
    return folder, identity


def inspect(root):
    try:
        folder, ident = current(root)
    except (OSError, KeyError, ValueError) as e:
        return {
            "current": None,
            "schemas": {},
            "supported": False,
            "reason": "未识别安装：" + str(e),
        }
    known = (
        ident.get("commit_sha") in RC3
        if ident.get("version") == "1.0.0rc3"
        else version(ident["version"]) >= version("1.0.0rc4")
    )
    schemas = {}
    for space in SPACES:
        db = safe(safe(safe(root / space) / "data") / "workthread.sqlite3")
        if db.is_file():
            # immutable avoids creating WAL/SHM when inspecting a legacy installation.
            # A live WAL is rechecked on the quiescent copy before permitting migration.
            with contextlib.closing(
                sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True)
            ) as conn:
                try:
                    schemas[space] = conn.execute(
                        "SELECT max(version) FROM schema_migrations"
                    ).fetchone()[0]
                except sqlite3.DatabaseError:
                    schemas[space] = None
    return {
        "current": ident,
        "schemas": schemas,
        "supported": bool(
            known
            and ident.get("runner_os") == "Windows"
            and (folder / EXE).is_file()
            and set(schemas) == set(SPACES)
            and set(schemas.values()) == {2}
        ),
    }


def copy_workspace(src, dst):
    if os.name == "nt":
        from .copying import Copier, Evidence

        # Both native entry points use this exact implementation; evidence stays
        # in the transaction, never inside the business snapshot being compared.
        evidence = Evidence(dst.parent.parent / ("copy-" + uuid.uuid4().hex))
        Copier(evidence)(src, dst)
    else:
        shutil.copytree(src, dst)


def flush_tree(root):
    # Flush data before persisting a journal which refers to it. Fail closed if the
    # host cannot flush a staged file. Never open the user's original files for writing.
    for directory, dirs, files in root.walk(top_down=False):
        for name in files:
            f = directory / name
            mode = f.stat().st_mode
            try:
                if os.name == "nt" and not mode & stat.S_IWRITE:
                    f.chmod(mode | stat.S_IWRITE)
                with f.open("r+b" if os.name == "nt" else "rb") as handle:
                    os.fsync(handle.fileno())
            finally:
                if os.name == "nt" and not mode & stat.S_IWRITE:
                    f.chmod(mode)
        if os.name != "nt":
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


def available(root, needed):
    if shutil.disk_usage(root).free < needed + 128 * 1024**2:
        raise ValueError("磁盘空间不足，未切换版本")


def estimate(root):
    total = 0
    for space in SPACES:
        for parent, dirs, files in safe(root / space).walk(
            on_error=lambda e: (_ for _ in ()).throw(e)
        ):
            for name in dirs + files:
                p = safe(parent / name)
                if p.is_file():
                    total += p.stat().st_size
    return total


def probe(space, logical):
    """Runs inside the target binary, never the normal CLI startup/recovery/worker."""
    from ..core import Store
    from ..deployment import install_templates
    from ..operations import verify_snapshot

    db = space / "data/workthread.sqlite3"
    with contextlib.closing(
        sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    ) as conn:
        if (
            conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0]
            != 2
        ):
            raise ValueError("未提供此数据库版本的迁移")
    verify_snapshot(space)
    s = Store(space)
    result = install_templates(s)
    if not result["ready"]:
        names = [v["path"] for v in result["conflicts"]]
        raise ValueError(
            "自定义文件保持原样；请合并临时副本中的候选文件：" + ", ".join(names)
        )
    # The operational registry should describe the final, stable project path.
    result["workspace"] = str(logical / "agent-workspace")
    save(space / "agent-workspace/.workthread-deployment.json", result)
    from ..server import create_app

    client = create_app(s).test_client()
    if (
        client.get("/").status_code != 200
        or client.get("/static/app.js").status_code != 200
        or not s.health()["ok"]
    ):
        raise ValueError("新程序工作空间健康检查失败")


def run_probe(bundle, space, logical):
    r = subprocess.run(
        [str(bundle / EXE), "--maintenance", "probe", str(space), str(logical)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    if r.returncode:
        raise ValueError((r.stderr or r.stdout or "工作空间预检失败")[-1200:])


def native_quiet(ignore_pid=0, root=None):
    if os.name != "nt":
        raise ValueError("正式升级仅支持 Windows")
    # Old rc3 / external WorkBuddy do not participate in our install-level lock.
    script = r"""
$ErrorActionPreference='Stop'
$others = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -match '^(WorkBuddy|CodeBuddy).*\.exe$') -or
    ($_.ProcessId -ne IGNORE_PID -and $_.Name -eq 'WorkThread.exe' -and
     (-not $_.ExecutablePath -or $_.ExecutablePath -ne $env:WT_VERIFIED_LAUNCHER) -and ($_.CommandLine -notmatch '\s--maintenance\s'))
}
if ($others) { exit 4 }
"""
    env = {**os.environ, "WT_VERIFIED_LAUNCHER": ""}
    if (
        root is not None
        and (root / STATE / "launcher.sha256").is_file()
        and digest(root / EXE)
        == (root / STATE / "launcher.sha256").read_text(encoding="ascii")
    ):
        env["WT_VERIFIED_LAUNCHER"] = str(root / EXE)
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script.replace("IGNORE_PID", str(int(ignore_pid))),
        ],
        check=False,
        timeout=30,
        env=env,
    )
    if r.returncode:
        raise ValueError("无法确认已停写：请关闭 WorkBuddy 和其他 WorkThread 窗口再试")


def atomic_move(src, dst):
    if dst.exists():
        raise ValueError("目标目录已存在，停止切换")
    if os.name == "nt":
        import ctypes

        if not ctypes.windll.kernel32.MoveFileExW(str(src), str(dst), 8):
            raise ctypes.WinError()
    else:
        src.rename(dst)
        for p in {src.parent, dst.parent}:
            fd = os.open(p, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


def journal(root):
    return root / STATE / "transaction.json"


def recover(root):
    """Called with install lock and writers paused. Never roll back a committed switch."""
    jp = journal(root)
    if not jp.exists():
        return
    j = read(jp)
    if j["phase"] in ("committed", "rolled-back"):
        return
    if not re.fullmatch("[0-9a-f]{32}", j["id"]):
        raise ValueError("升级记录无效")
    tx = root / STATE / "transactions" / j["id"]
    if j["phase"] != "switching":
        raise ValueError("无法识别升级记录，不改动工作空间")
    for name in SPACES:
        old, live = tx / "old" / name, root / name
        if (
            old.exists()
            and live.exists()
            and catalog(live) != read(tx / (name + ".trial.json"))
        ):
            raise ValueError(f"{name} 在切换后有新写入；保留两个版本，需人工恢复")
    for name in reversed(SPACES):
        old, live = tx / "old" / name, root / name
        if old.exists():
            if live.exists():
                atomic_move(live, tx / ("unused-" + name))
            atomic_move(old, live)
    ptr = root / STATE / "active.json"
    if j["prior"] is None:
        if ptr.exists():
            atomic_move(ptr, tx / "reverted-active.json")
    else:
        save(ptr, j["prior"])
    save(jp, {**j, "phase": "rolled-back"})


def wire(root, bundle):
    """Transition legacy shortcuts before moving data; fallback always uses old app."""
    state = root / STATE
    bootstrap = state / "bootstrap"
    if not bootstrap.exists():
        temp = state / ("bootstrap-" + uuid.uuid4().hex)
        shutil.copytree(bundle / "app", temp)
        flush_tree(temp)
        atomic_move(temp, bootstrap)
    shim = (bundle / "Run.cmd").read_bytes()
    if (root / "Run.cmd").exists() and (root / "Run.cmd").read_bytes() != shim:
        # A fresh newer installation ships its own launcher; never replace a custom one.
        raise ValueError("Run.cmd 存在自定义内容；停止切换")
    atomic(root / "Run.cmd", shim)
    index = read(root / "SHA256SUMS.json")
    prior_folder = current(root)[0]
    managed = (
        read(prior_folder / "SHA256SUMS.json")
        if (prior_folder / "SHA256SUMS.json").exists()
        else index
    )
    changes = []
    for name in ("Start.cmd", "Backup.cmd", "Restore.cmd", "Health.cmd", "Install.cmd"):
        p = root / name
        original = p.read_bytes()
        desired = (bundle / name).read_bytes()
        if original != desired:
            if digest(p) not in {managed.get(name), index.get(name)}:
                raise ValueError("启动脚本已自定义：" + name)
            changes.append((p, desired))
    for p, data in changes:
        atomic(p, data)
    # Existing desktop shortcuts may point straight at app/WorkThread.exe.
    # Preserve the complete original onedir runtime before replacing that one file.
    base = safe(state / "base")
    if not base.exists():
        tmp = state / ("base-" + uuid.uuid4().hex)
        if {k: v for k, v in catalog(root / "app").items() if v is not None} != {
            k[4:]: v for k, v in index.items() if k.startswith("app/")
        }:
            raise ValueError("原程序与安装清单不匹配")
        shutil.copytree(root / "app", tmp / "app")
        shutil.copy2(root / "BUILD_INFO.json", tmp / "BUILD_INFO.json")
        if catalog(tmp / "app") != catalog(root / "app"):
            raise ValueError("原程序快照校验失败")
        flush_tree(tmp)
        atomic_move(tmp, base)
    marker = safe(state / "launcher.sha256")
    if marker.is_file():
        if digest(root / EXE) != marker.read_text(encoding="ascii"):
            raise ValueError("固定启动器已被更改")
    else:
        launcher = (bundle / "tools/PortableLauncher.exe").read_bytes()
        if (root / EXE).read_bytes() != launcher:
            atomic(root / EXE, launcher)
        atomic(marker, digest(root / EXE).encode("ascii"))


def apply(
    root, archive, doc, sig, key, *, quiet=None, check=run_probe, hook=lambda _: None,
    progress=lambda _: None, operation_id=None
):
    root = safe(Path(root)).resolve(strict=True)
    quiet = quiet or (lambda: native_quiet(root=root))
    # Unknown legacy installs stay entirely read-only, including when Apply was requested.
    pending = journal(root)
    if (
        not (pending.is_file() and read(pending).get("phase") == "switching")
        and not inspect(root)["supported"]
    ):
        raise ValueError("未验证的来源构建、工作空间或数据库版本")
    state = safe(root / STATE)
    state.mkdir(exist_ok=True)
    for part in (
        "versions",
        "transactions",
        "downloads",
        "bootstrap",
        "base",
        "active.json",
        "transaction.json",
        "install.lock",
    ):
        safe(state / part)
    with FileLock(str(state / "install.lock"), timeout=0):
        from .controller import no_leases

        no_leases(state)
        quiet()
        recover(root)
        info = inspect(root)
        if not info["supported"]:
            raise ValueError("未验证的来源构建、工作空间或数据库版本")
        m = signed(doc, sig, key, info["current"])
        txid = uuid.uuid4().hex
        tx = state / "transactions" / txid
        tx.mkdir(parents=True)
        new = tx / "package"
        import zipfile

        from .releases import verify_zip

        verify_zip(archive, m)
        with zipfile.ZipFile(archive) as z:
            unpacked = sum(i.file_size for i in z.infolist())
        available(
            root,
            estimate(root) * 2
            + unpacked * 2
            + sum(p.stat().st_size for p in (root / "app").rglob("*") if p.is_file()),
        )
        extract(archive, new, m)
        dest = state / "versions" / m["commit_sha"]
        dest.parent.mkdir(exist_ok=True)
        if dest.exists():
            if catalog(dest) != catalog(new):
                raise ValueError("已有版本目录内容不匹配")
        else:
            flush_tree(new)
            atomic_move(new, dest)
        (tx / "old").mkdir()
        before, trials = {}, {}
        for name in SPACES:
            progress("snapshot-" + name)
            live = root / name
            before[name] = catalog(live)
            snapshot = tx / "snapshot" / name
            copy_workspace(live, snapshot)
            if catalog(snapshot) != before[name]:
                raise ValueError(f"{name} 快照内容已变化：复制结果与复制前清单不一致，已停止切换。可能仍有程序写入或复制异常；请关闭 WorkBuddy 和其他工作台后重试，仍失败时保留现场交给维护者检查")
            progress("trial-" + name)
            trial = tx / "trial" / name
            flush_tree(snapshot)
            copy_workspace(snapshot, trial)
            try:
                check(dest, trial, live)
            except ValueError as e:
                raise ValueError(f"{e}；预检副本：{trial}") from e
            flush_tree(trial)
            trials[name] = catalog(trial)
            save(tx / (name + ".trial.json"), trials[name])
        quiet()
        if any(catalog(root / n) != before[n] for n in SPACES):
            raise ValueError("工作空间在预检期间发生写入，取消切换")
        progress("switching")
        wire(root, dest)
        quiet()
        ptr = state / "active.json"
        j = {
            "id": txid,
            "operation_id": operation_id,
            "phase": "switching",
            "prior": read(ptr) if ptr.exists() else None,
            "from": info["current"]["version"],
            "target": m["version"],
        }
        save(journal(root), j)
        try:
            for name in SPACES:
                live = root / name
                atomic_move(live, tx / "old" / name)
                hook("saved-" + name)
                if catalog(tx / "old" / name) != before[name]:
                    raise ValueError("停写检查失败")
                atomic_move(tx / "trial" / name, live)
                hook("placed-" + name)
                if catalog(live) != trials[name]:
                    raise ValueError("切换后的健康快照不符")
            save(ptr, {"commit_sha": m["commit_sha"]})
            hook("pointer")
            if current(root)[1]["commit_sha"] != m["commit_sha"]:
                raise ValueError("版本切换失败")
            for name in SPACES:
                live = root / name
                # Read-only final-path health check; never start a service or mail/AI worker here.
                with contextlib.closing(
                    sqlite3.connect(
                        (live / "data/workthread.sqlite3").as_uri()
                        + "?mode=ro&immutable=1",
                        uri=True,
                    )
                ) as c:
                    if (
                        c.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                        or c.execute("PRAGMA foreign_key_check").fetchone()
                    ):
                        raise ValueError("切换后数据库健康检查失败：" + name)
            save(journal(root), {**j, "phase": "committed"})
        except Exception:
            recover(root)
            raise
        return {"version": m["version"], "snapshot": str(tx / "snapshot")}
