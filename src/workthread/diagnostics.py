"""Actionable error descriptions without exposing server payloads or credentials."""

import errno
import http.client
import socket
import sqlite3
import ssl
import urllib.error

from filelock import Timeout


def describe_error(exc):
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(exc, urllib.error.HTTPError):
        hints = {
            403: "访问被拒绝或请求达到限额，请稍后重试，并检查代理访问策略",
            404: "发布文件不存在或已被移除，请重新检查更新",
            407: "代理要求身份验证，请检查系统代理的登录状态",
            429: "请求频率超限，请稍后重试",
            500: "远端服务内部错误，请稍后重试",
            502: "网关未取得有效响应，请稍后重试",
            503: "远端服务暂时不可用，请稍后重试",
            504: "网关等待上游超时，请稍后重试",
        }
        return f"HTTP {exc.code}：{hints.get(exc.code, '远端服务拒绝了请求，请记录状态码后排查')}"
    if isinstance(reason, sqlite3.DatabaseError):
        code = getattr(reason, "sqlite_errorcode", 0) & 0xFF
        hints = {
            sqlite3.SQLITE_BUSY: "本地数据库正忙，请等待正在写入的任务结束后重试",
            sqlite3.SQLITE_LOCKED: "本地数据库被占用，请关闭多余工作台实例后重试",
            sqlite3.SQLITE_FULL: "数据库空间已满，请检查工作空间所在磁盘的可用空间",
            sqlite3.SQLITE_READONLY: "数据库只读，请检查工作空间及数据库文件的写入权限",
            sqlite3.SQLITE_IOERR: "数据库读写失败，请检查工作空间所在磁盘是否可用",
            sqlite3.SQLITE_CORRUPT: "数据库完整性异常，请停止写入，保留现场并联系维护者检查或从已验证备份恢复",
            sqlite3.SQLITE_NOTADB: "数据库格式异常，请停止写入并核对数据库文件，联系维护者处理",
            sqlite3.SQLITE_CANTOPEN: "无法打开数据库，请检查工作空间路径、访问权限和磁盘状态",
        }
        names = {
            value: name
            for name, value in vars(sqlite3).items()
            if name
            in (
                "SQLITE_BUSY",
                "SQLITE_LOCKED",
                "SQLITE_FULL",
                "SQLITE_READONLY",
                "SQLITE_IOERR",
                "SQLITE_CORRUPT",
                "SQLITE_NOTADB",
                "SQLITE_CANTOPEN",
            )
        }
        return f"{hints.get(code, '本地数据库操作失败，请记录错误编号并联系维护者排查')}（{names.get(code, 'SQLite ' + str(code))}）"
    if isinstance(reason, Timeout):
        return (
            "工作空间正在被其他操作占用，请等待当前任务结束，并确认没有重复运行的工作台"
        )
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "证书验证失败，请检查系统时间、代理证书和目标服务器证书"
    if isinstance(reason, ssl.SSLError):
        return "TLS 安全连接失败，请检查代理与服务器的 TLS 配置"
    if isinstance(reason, socket.gaierror):
        return "域名解析失败，请检查目标地址、DNS 和系统代理"
    if isinstance(reason, TimeoutError):
        return "连接或读取超时，请检查目标服务和代理是否可达，稍后重试"
    if isinstance(reason, ConnectionRefusedError):
        return "目标服务或代理拒绝连接，请检查地址、端口以及代理程序是否正在运行"
    if isinstance(reason, http.client.IncompleteRead):
        return "响应内容未接收完整，连接在读取过程中中断，请稍后重试"
    if isinstance(reason, (ConnectionResetError, ConnectionAbortedError, EOFError)):
        return (
            "连接被关闭或中止，请检查网络与代理的稳定性；浏览器与工作台可能使用不同代理"
        )
    if isinstance(reason, PermissionError):
        return (
            "本地文件访问被拒绝，请检查工作空间写入权限、文件占用和安全软件的拦截记录"
        )
    if isinstance(reason, FileNotFoundError):
        return "所需本地文件或目录不存在，请检查所选路径及安装文件是否完整"
    if isinstance(reason, OSError):
        hints = {
            errno.ENOSPC: "磁盘空间不足，请清理工作空间所在磁盘后重试",
            errno.EROFS: "文件系统只读，请检查磁盘挂载状态和写入权限",
            errno.EIO: "本地文件读写失败，请检查磁盘连接与健康状态",
        }
        if reason.errno in hints:
            return hints[reason.errno]
    return f"尚未确定具体原因（{type(reason).__name__}），请保留诊断编号或任务编号及失败时间，交给维护者排查"
