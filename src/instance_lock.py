#!/usr/bin/env python3
"""Cross-platform single-instance lock, process-start identity, and live daemon handshake."""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
from typing import Any, Dict, Optional, Tuple
from urllib.request import Request, urlopen

from storage import DATA_DIR, atomic_write_text, file_lock

SERVICE_NAME = "agy-usage-dashboard"
PROTOCOL_VERSION = 1
APP_VERSION = "1.5.0"

DAEMON_LOCK_FILE = DATA_DIR / "daemon.lock"
INSTANCE_META_FILE = DATA_DIR / "daemon_instance.json"


def generate_instance_id() -> str:
    return secrets.token_hex(12)


def get_pid_start_id(pid: int) -> str:
    """Return a stable process start-time token to defeat PID reuse, or '' if dead/unavailable."""
    if pid <= 0:
        return ""
    if sys.platform == "darwin":
        try:
            libproc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
            buf = ctypes.create_string_buffer(256)
            # PROC_PIDTBSDINFO = 3; pbi_start_tvsec (uint64) @ offset 120, pbi_start_tvusec (uint64) @ offset 128 on arm64/x86_64
            res = libproc.proc_pidinfo(ctypes.c_int(pid), ctypes.c_int(3), ctypes.c_uint64(0), buf, ctypes.c_int(136))
            if res >= 136:
                import struct

                sec, usec = struct.unpack_from("<QQ", buf.raw, 120)
                if sec > 0:
                    return f"{sec * 1_000_000 + usec}"
            return ""
        except Exception:
            return ""
    if sys.platform.startswith("linux"):
        try:
            stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
            rparen = stat_text.rfind(")")
            if rparen != -1:
                fields = stat_text[rparen + 2 :].split()
                if len(fields) > 19:
                    return fields[19]
        except OSError:
            return ""
        return ""
    if os.name == "nt":
        try:
            class FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return ""
            try:
                ct, et, kt, ut = FILETIME(), FILETIME(), FILETIME(), FILETIME()
                ok = ctypes.windll.kernel32.GetProcessTimes(
                    handle, ctypes.byref(ct), ctypes.byref(et), ctypes.byref(kt), ctypes.byref(ut)
                )
                if ok:
                    val = (ct.dwHighDateTime << 32) | ct.dwLowDateTime
                    return str(val) if val > 0 else ""
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return ""
    return ""


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return bool(ok and exit_code.value == 259)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_verified_pid(pid: int, expected_pid_start: str = "") -> bool:
    """Stop pid only if alive and (when known) its start-time token still matches."""
    if not pid_alive(pid):
        return False
    if expected_pid_start:
        current_start = get_pid_start_id(pid)
        if not current_start or current_start != expected_pid_start:
            return False
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return False
    return True


def read_instance_meta(meta_file: Path = INSTANCE_META_FILE) -> Optional[Dict[str, Any]]:
    if not meta_file.is_file():
        return None
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def write_instance_meta(meta: Dict[str, Any], meta_file: Path = INSTANCE_META_FILE) -> None:
    payload = json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_text(meta_file, payload, mode=0o600)


def remove_instance_meta(meta_file: Path = INSTANCE_META_FILE) -> None:
    try:
        meta_file.unlink(missing_ok=True)
    except OSError:
        pass


def fetch_health_identity(host: str, port: int, timeout: float = 0.6) -> Optional[Dict[str, Any]]:
    url = f"http://{host}:{port}/api/health"
    req = Request(url, headers={"Host": f"{host}:{port}", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            raw = resp.read(4096).decode("utf-8", errors="replace")
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
    except Exception:
        return None


def is_port_in_use(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def verify_live_instance(
    meta: Optional[Dict[str, Any]] = None,
    *,
    expected_port: Optional[int] = None,
    meta_file: Path = INSTANCE_META_FILE,
    timeout: float = 0.6,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Verify recorded daemon instance is alive, matches pid_start, and passes /api/health identity handshake."""
    info = meta if meta is not None else read_instance_meta(meta_file)
    if not info:
        return False, None
    try:
        pid = int(info.get("pid") or 0)
        port = int(info.get("port") or 0)
        host = str(info.get("host") or "127.0.0.1")
        inst_id = str(info.get("instance_id") or "")
        pid_start = str(info.get("pid_start") or "")
    except (TypeError, ValueError):
        return False, None

    if pid <= 0 or port <= 0 or not inst_id:
        return False, None
    if expected_port is not None and port != expected_port:
        return False, None
    if not pid_alive(pid):
        return False, None
    if pid_start:
        cur_start = get_pid_start_id(pid)
        if cur_start and cur_start != pid_start:
            return False, None

    health = fetch_health_identity(host, port, timeout=timeout)
    if not health:
        return False, None
    if (
        health.get("ok") is True
        and health.get("service") == SERVICE_NAME
        and health.get("protocol_version") == PROTOCOL_VERSION
        and health.get("instance_id") == inst_id
        and int(health.get("port") or 0) == port
    ):
        return True, info
    return False, None


def wait_for_ready_handshake(
    host: str,
    port: int,
    instance_id: str,
    proc: subprocess.Popen,
    *,
    timeout: float = 4.0,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        health = fetch_health_identity(host, port, timeout=0.35)
        if (
            health
            and health.get("ok") is True
            and health.get("service") == SERVICE_NAME
            and health.get("protocol_version") == PROTOCOL_VERSION
            and health.get("instance_id") == instance_id
        ):
            return True
        time.sleep(0.08)
    return False


def daemon_transaction_lock(timeout: float = 5.0, lock_file: Path = DAEMON_LOCK_FILE):
    return file_lock(lock_file, timeout=timeout)
