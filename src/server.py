#!/usr/bin/env python3
"""Local loopback HTTP dashboard server (CSRF & DNS-rebinding hardened) and daemon lifecycle manager."""

from __future__ import annotations

import argparse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socketserver
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse
import webbrowser

from analytics import build_analytics, export_sessions_csv, get_conversation_detail
from instance_lock import (
    APP_VERSION,
    PROTOCOL_VERSION,
    SERVICE_NAME,
    daemon_transaction_lock,
    generate_instance_id,
    get_pid_start_id,
    is_port_in_use,
    read_instance_meta,
    remove_instance_meta,
    stop_verified_pid,
    verify_live_instance,
    wait_for_ready_handshake,
    write_instance_meta,
)
from maintenance import append_web_log, rotate_web_log
from notifications import get_preferences, set_preferences
from quota import save_manual_quota
from storage import APP_DIR, DATA_DIR, ensure_data_dir
from tui import BOLD, CYAN, DIM, GREEN, RED, RESET
from web_ui import DASHBOARD_HTML

PID_FILE = DATA_DIR / "web.pid"
LOG_FILE = DATA_DIR / "web.log"


def make_handler(port: int, *, instance_id: str = "", owner: str = "foreground") -> type:
    allowed_hosts = {
        f"127.0.0.1:{port}",
        f"localhost:{port}",
        f"[::1]:{port}",
        "127.0.0.1",
        "localhost",
        "[::1]",
    }
    allowed_origins = {
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        f"http://[::1]:{port}",
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *log_args: Any) -> None:
            return

        def _send(self, code: int, content_type: str, body: bytes, extra_headers: Optional[Dict[str, str]] = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:",
            )
            self.send_header("Content-Length", str(len(body)))
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _check_host_and_origin(self, is_write: bool = False) -> bool:
            host_hdr = (self.headers.get("Host") or "").strip().lower()
            if host_hdr not in allowed_hosts:
                self._send(403, "application/json; charset=utf-8", b'{"ok":false,"error":"forbidden host"}')
                return False
            if is_write:
                ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if ctype != "application/json":
                    self._send(415, "application/json; charset=utf-8", b'{"ok":false,"error":"application/json required"}')
                    return False
                origin = (self.headers.get("Origin") or "").strip().lower()
                if origin and origin not in allowed_origins:
                    self._send(403, "application/json; charset=utf-8", b'{"ok":false,"error":"forbidden origin"}')
                    return False
                fetch_site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
                if fetch_site and fetch_site not in ("same-origin", "none"):
                    self._send(403, "application/json; charset=utf-8", b'{"ok":false,"error":"forbidden fetch-site"}')
                    return False
            return True

        def do_GET(self) -> None:
            if not self._check_host_and_origin(is_write=False):
                return
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", DASHBOARD_HTML.encode("utf-8"))
                return

            if path == "/api/health":
                health = {
                    "ok": True,
                    "service": SERVICE_NAME,
                    "protocol_version": PROTOCOL_VERSION,
                    "version": APP_VERSION,
                    "instance_id": instance_id,
                    "port": port,
                    "owner": owner,
                }
                self._send(200, "application/json; charset=utf-8", json.dumps(health).encode("utf-8"))
                return

            if path == "/api/stats":
                win = (qs.get("window") or ["7d"])[0]
                body = json.dumps(build_analytics(window=win), ensure_ascii=False).encode("utf-8")
                self._send(200, "application/json; charset=utf-8", body)
                return

            if path.startswith("/api/session/"):
                cid = path[len("/api/session/") :]
                detail = get_conversation_detail(cid)
                if detail is None:
                    self._send(404, "application/json; charset=utf-8", b'{"error":"not found"}')
                    return
                body = json.dumps(detail, ensure_ascii=False).encode("utf-8")
                self._send(200, "application/json; charset=utf-8", body)
                return

            if path == "/api/preferences":
                body = json.dumps({"ok": True, "preferences": get_preferences()}, ensure_ascii=False).encode("utf-8")
                self._send(200, "application/json; charset=utf-8", body)
                return

            if path == "/api/export.csv":
                win = (qs.get("window") or ["7d"])[0]
                csv_text = export_sessions_csv(window=win)
                fname = f"agy-usage-{win}-{datetime.now().strftime('%Y%m%d-%H%M')}.csv"
                self._send(
                    200,
                    "text/csv; charset=utf-8",
                    csv_text.encode("utf-8"),
                    {"Content-Disposition": f'attachment; filename="{fname}"'},
                )
                return

            self._send(404, "text/plain; charset=utf-8", b"Not Found")

        def do_POST(self) -> None:
            if not self._check_host_and_origin(is_write=True):
                return
            parsed = urlparse(self.path)
            if parsed.path in ("/api/record-quota", "/api/preferences"):
                try:
                    raw_len = self.headers.get("Content-Length")
                    if raw_len is None:
                        self._send(400, "application/json; charset=utf-8", b'{"ok":false,"error":"missing content-length"}')
                        return
                    length = int(raw_len)
                    if length <= 0 or length > 16384:
                        self._send(413, "application/json; charset=utf-8", b'{"ok":false,"error":"payload size invalid"}')
                        return
                    raw = self.rfile.read(length).decode("utf-8")
                    payload = json.loads(raw)
                    if not isinstance(payload, dict):
                        raise ValueError("JSON object required")
                    if parsed.path == "/api/preferences":
                        en = payload.get("notifications_enabled")
                        prefs = set_preferences(notifications_enabled=bool(en) if en is not None else None)
                        self._send(
                            200,
                            "application/json; charset=utf-8",
                            json.dumps({"ok": True, "preferences": prefs}, ensure_ascii=False).encode("utf-8"),
                        )
                        return
                    res = save_manual_quota(
                        bucket=str(payload.get("bucket") or "gemini-weekly"),
                        remaining_pct=float(payload.get("remaining_pct")),
                        reset_str=payload.get("reset"),
                    )
                    self._send(200, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False).encode("utf-8"))
                except Exception as exc:
                    err = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8")
                    self._send(400, "application/json; charset=utf-8", err)
                return
            self._send(404, "text/plain; charset=utf-8", b"Not Found")

    return Handler


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

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
    except Exception:
        return False


def _stop_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass


def _read_pid() -> Optional[int]:
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        return pid if _pid_alive(pid) else None
    except Exception:
        return None


class LockedLogStream:
    """Thread- and process-safe log stream sharing .weblog.lock with rotate_web_log."""

    def __init__(self) -> None:
        self._tlock = threading.Lock()

    def write(self, data: str) -> int:
        if not data:
            return 0
        with self._tlock:
            append_web_log(data)
        return len(data)

    def flush(self) -> None:
        return


class ReusableHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def server_bind(self) -> None:
        # Skip HTTPServer's socket.getfqdn() reverse-DNS lookup (can stall 30s+ on macOS VPN/CI networks)
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


def cmd_web(args: argparse.Namespace) -> int:
    if getattr(args, "daemon_log", False):
        stream = LockedLogStream()
        sys.stdout = stream  # type: ignore[assignment]
        sys.stderr = stream  # type: ignore[assignment]
    host = "127.0.0.1"
    port = int(args.port)
    inst_id = os.environ.get("AGY_USAGE_INSTANCE_ID", "").strip() or generate_instance_id()
    owner = os.environ.get("AGY_USAGE_OWNER", "").strip() or ("daemon" if getattr(args, "daemon_log", False) else "foreground")
    try:
        server = ReusableHTTPServer((host, port), make_handler(port, instance_id=inst_id, owner=owner))
    except Exception as exc:
        print(f"启动 Web 监控台失败 (127.0.0.1:{port}): {exc}", file=sys.stderr, flush=True)
        return 1
    if owner == "foreground":
        try:
            ensure_data_dir()
            write_instance_meta(
                {
                    "service": SERVICE_NAME,
                    "protocol_version": PROTOCOL_VERSION,
                    "version": APP_VERSION,
                    "instance_id": inst_id,
                    "pid": os.getpid(),
                    "pid_start": get_pid_start_id(os.getpid()),
                    "host": host,
                    "port": port,
                    "owner": owner,
                }
            )
        except OSError:
            pass
    url = f"http://{host}:{port}"
    print(f"{GREEN}●{RESET} Antigravity 实时用量监控台已启动: {BOLD}{CYAN}{url}{RESET}", flush=True)
    print(f"  {DIM}仅监听本机 127.0.0.1 · 按 Ctrl+C 停止服务{RESET}", flush=True)
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止 Web 监控台。")
    finally:
        server.server_close()
        if owner == "foreground":
            cur = read_instance_meta()
            if cur and cur.get("instance_id") == inst_id:
                remove_instance_meta()
    return 0


def _stop_recorded_instance() -> Tuple[bool, Optional[int]]:
    """Stop only the verified instance recorded in daemon_instance.json (never blindly kill foreign PIDs)."""
    meta = read_instance_meta()
    if not meta:
        PID_FILE.unlink(missing_ok=True)
        return False, None
    pid = int(meta.get("pid") or 0)
    pid_start = str(meta.get("pid_start") or "")
    stopped = stop_verified_pid(pid, expected_pid_start=pid_start)
    if stopped:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and _pid_alive(pid):
            time.sleep(0.05)
    remove_instance_meta()
    PID_FILE.unlink(missing_ok=True)
    return stopped, pid if stopped else None


def cmd_daemon(args: argparse.Namespace) -> int:
    ensure_data_dir()
    port = int(args.port)
    action = args.action

    if action == "status":
        ok, meta = verify_live_instance(expected_port=port)
        if ok and meta:
            print(f"{GREEN}● 运行中{RESET} (PID {meta['pid']}, owner={meta.get('owner', 'daemon')}) -> http://127.0.0.1:{port}")
        else:
            print(f"{DIM}○ 未运行{RESET}")
        return 0

    with daemon_transaction_lock(timeout=5.0) as locked:
        if not locked:
            print(f"{RED}✖ 无法获取单实例锁（可能有另一个启动/停止操作正在进行）{RESET}", file=sys.stderr)
            return 1

        if action == "stop":
            stopped, stopped_pid = _stop_recorded_instance()
            if not stopped:
                print("后台看板未在运行。")
                return 0
            print(f"{GREEN}✓ 已停止后台看板{RESET} (PID {stopped_pid})")
            return 0

        if action in ("start", "restart"):
            ok, meta = verify_live_instance(expected_port=port)
            if ok and meta:
                if action == "start":
                    print(f"{GREEN}● 后台看板已在运行{RESET} (PID {meta['pid']}) -> http://127.0.0.1:{port}")
                    if not args.no_open:
                        try:
                            webbrowser.open(f"http://127.0.0.1:{port}")
                        except Exception:
                            pass
                    return 0
                _stop_recorded_instance()
            else:
                # Clear stale metadata without killing any unrelated process
                if read_instance_meta():
                    remove_instance_meta()
                PID_FILE.unlink(missing_ok=True)

            if is_port_in_use("127.0.0.1", port):
                print(
                    f"{RED}✖ 端口 127.0.0.1:{port} 已被其他非本工具服务占用，已安全中止（绝不强杀外部进程）。请用 --port 指定其他端口。{RESET}",
                    file=sys.stderr,
                )
                return 1

            rotate_web_log()
            inst_id = generate_instance_id()
            py_exe = sys.executable
            child_env = dict(os.environ)
            child_env["AGY_USAGE_INSTANCE_ID"] = inst_id
            child_env["AGY_USAGE_OWNER"] = "daemon"

            popen_kwargs: Dict[str, Any] = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "env": child_env,
            }
            if os.name == "nt":
                pyw = Path(py_exe).with_name("pythonw.exe")
                if pyw.exists():
                    py_exe = str(pyw)
                popen_kwargs["creationflags"] = 0x00000008 | 0x00000200
            else:
                popen_kwargs["start_new_session"] = True

            proc = subprocess.Popen(
                [py_exe, str(APP_DIR / "cli.py"), "web", "--port", str(port), "--no-open", "--daemon-log"],
                **popen_kwargs,
            )
            if not wait_for_ready_handshake("127.0.0.1", port, inst_id, proc, timeout=8.0):
                stop_verified_pid(proc.pid)
                remove_instance_meta()
                PID_FILE.unlink(missing_ok=True)
                print(f"{RED}✖ 后台启动握手失败（端口 {port}），请查看 {LOG_FILE}{RESET}", file=sys.stderr)
                return 1

            meta_rec = {
                "service": SERVICE_NAME,
                "protocol_version": PROTOCOL_VERSION,
                "version": APP_VERSION,
                "instance_id": inst_id,
                "pid": proc.pid,
                "pid_start": get_pid_start_id(proc.pid),
                "host": "127.0.0.1",
                "port": port,
                "owner": "daemon",
            }
            write_instance_meta(meta_rec)
            PID_FILE.write_text(str(proc.pid), encoding="utf-8")
            url = f"http://127.0.0.1:{port}"
            print(f"{GREEN}✓ 已在后台启动监控台{RESET} (PID {proc.pid}) -> {BOLD}{CYAN}{url}{RESET}")
            if not args.no_open:
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
            return 0
    return 0
