"""Read-only Windows security checks. Never grants rights or changes any ACL."""

import ctypes
import hashlib

from . import transaction as tx
from .releases import save


def descriptor(path):
    """Fingerprint owner, primary group and DACL including inheritance flags."""
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.c_void_p
    advapi.GetNamedSecurityInfoW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.c_uint32,
        ctypes.POINTER(pointer),
        ctypes.POINTER(pointer),
        ctypes.POINTER(pointer),
        ctypes.POINTER(pointer),
        ctypes.POINTER(pointer),
    ]
    advapi.GetNamedSecurityInfoW.restype = ctypes.c_uint32
    advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        pointer,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.POINTER(pointer),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer
    sd, text = pointer(), pointer()
    code = advapi.GetNamedSecurityInfoW(
        str(path), 1, 7, None, None, None, None, ctypes.byref(sd)
    )
    if code:
        raise ctypes.WinError(code)
    try:
        if not advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            sd, 1, 7, ctypes.byref(text), None
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return hashlib.sha256(ctypes.wstring_at(text).encode("utf-8")).hexdigest()
    finally:
        if text:
            kernel.LocalFree(text)
        kernel.LocalFree(sd)


def inventory(root, read=descriptor):
    result = {".": {"directory": True, "security": read(tx.safe(root))}}
    for parent, dirs, files in root.walk(on_error=lambda e: (_ for _ in ()).throw(e)):
        for name in dirs + files:
            path = tx.safe(parent / name)
            result[path.relative_to(root).as_posix()] = {
                "directory": path.is_dir(),
                "security": read(path),
            }
    return result


def prepare(src, dst, folder, read=descriptor):
    """No business bytes are written until every empty target has matching rights."""
    before = inventory(src, read)
    save(folder / "security-source-before.json", before)
    if dst.exists():
        raise ValueError("复制目标已经存在，拒绝覆盖")
    for name in sorted(before, key=lambda n: (n.count("/"), n != ".", n)):
        target = dst if name == "." else dst / name
        # Parents of the root are staging directories; the root's inherited
        # descriptor is checked before creating children or writing any data.
        if before[name]["directory"]:
            target.mkdir(parents=name == ".", exist_ok=False)
        else:
            with target.open("xb"):
                pass
        actual = read(target)
        if actual != before[name]["security"]:
            save(
                folder / "security-refusal.json",
                {
                    "path": name,
                    "source": before[name]["security"],
                    "destination": actual,
                    "business_content_copied": False,
                },
            )
            raise ValueError(
                "目标继承权限、所有者或组与原件不同，未复制业务内容；请保留 security-refusal.json，不能放宽权限继续"
            )
    save(folder / "security-preflight.json", {"entries": len(before), "matched": True})
    return before


def verify(src, dst, before, folder, read=descriptor):
    source, target = inventory(src, read), inventory(dst, read)
    save(folder / "security-source-after.json", source)
    save(folder / "security-destination.json", target)
    if source != before or target != before:
        raise ValueError(
            "复制期间权限或目录结构发生变化，停止切换；请查看 security 清单"
        )
