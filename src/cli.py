#!/usr/bin/env python3
"""Antigravity CLI (agy) real-time usage & weekly quota analytics CLI + Web Dashboard."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from core import (  # noqa: E402
    DATA_DIR,
    append_web_log,
    atomic_write_text,
    build_analytics,
    clean_cache,
    discover_settings_file,
    ensure_data_dir,
    export_sessions_csv,
    fmt_tokens,
    get_conversation_detail,
    get_preferences,
    rotate_web_log,
    run_doctor,
    save_manual_quota,
    set_preferences,
)
from web_ui import DASHBOARD_HTML  # noqa: E402

PID_FILE = DATA_DIR / "web.pid"
LOG_FILE = DATA_DIR / "web.log"

# ANSI styling
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
BLUE = "\033[34m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"

SPARK_CHARS = " ▁▂▃▄▅▆▇█"


def bar(pct: float, width: int = 20, color: str = CYAN) -> str:
    pct = max(0.0, min(100.0, pct))
    filled = int(round((pct / 100.0) * width))
    return f"{color}{'█' * filled}{DIM}{'░' * (width - filled)}{RESET}"


def used_bar_color(used_pct: Optional[float]) -> str:
    if used_pct is None:
        return DIM
    if used_pct >= 80.0:
        return RED
    if used_pct >= 55.0:
        return YELLOW
    return GREEN


def sparkline(values: List[float]) -> str:
    if not values:
        return ""
    mx = max(values)
    if mx <= 0:
        return SPARK_CHARS[0] * len(values)
    out = []
    for v in values:
        idx = int(round((v / mx) * (len(SPARK_CHARS) - 1)))
        out.append(SPARK_CHARS[max(0, min(len(SPARK_CHARS) - 1, idx))])
    return "".join(out)


def fmt_usd(v: float) -> str:
    if 0 < v < 0.01:
        return f"${v:.4f}"
    return f"${v:.2f}"


def pad_display(s: str, width: int) -> str:
    vis = 0
    for ch in s:
        vis += 2 if ord(ch) > 127 else 1
    return s + " " * max(0, width - vis)


def trunc_display(s: str, max_width: int) -> str:
    vis = 0
    out = []
    for ch in s:
        w = 2 if ord(ch) > 127 else 1
        if vis + w > max_width - 1:
            out.append("…")
            break
        out.append(ch)
        vis += w
    return "".join(out)


def render_terminal_report(data: Dict[str, Any], compact: bool = False) -> str:
    lines: List[str] = []
    ls = data["live_session"]
    q = data["quota"]
    wins = data["windows"]
    b5 = data["burn_5h"]
    sel = data["selected_summary"]

    # Header
    lines.append(f"{BOLD}{CYAN}━━━ Antigravity (agy) 实时用量 & 每周限额分析 ━━━{RESET}  {DIM}{data['generated_at_cst']}{RESET}")
    sl_status = (
        f"{GREEN}● 实时 statusLine 已连接{RESET} {DIM}({ls['captured_at_cst']}){RESET}"
        if ls["connected"]
        else (
            f"{YELLOW}◐ statusLine 已配置，待 agy 触发首次推送{RESET}"
            if ls["statusline_configured"]
            else f"{YELLOW}○ 尚未配置实时 statusLine{RESET}"
        )
    )
    lines.append(
        f"主模型: {BOLD}{CYAN}{ls['active_model']}{RESET}  │  "
        f"Planner: {MAGENTA}{ls['configured_planner']}{RESET}  │  {sl_status}"
    )
    if ls.get("context_window") and ls["context_window"].get("used_percentage") is not None:
        cw = ls["context_window"]
        up = float(cw["used_percentage"])
        lines.append(
            f"当前会话上下文: {bar(up, 14, RED if up >= 80 else YELLOW if up >= 55 else CYAN)} "
            f"{BOLD}{up:.1f}%{RESET}  {DIM}({fmt_tokens((cw.get('total_input_tokens') or 0) + (cw.get('total_output_tokens') or 0))} / {fmt_tokens(cw.get('context_window_size') or 0)}){RESET}"
        )

    # Smart insights
    if data.get("insights"):
        lines.append("")
        for ins in data["insights"][:3]:
            c = RED if ins["level"] == "crit" else YELLOW if ins["level"] == "warn" else GREEN if ins["level"] == "ok" else CYAN
            lines.append(f"  {c}▸ {BOLD}{ins['title']}{RESET} {DIM}— {ins['detail']}{RESET}")

    # Section 1: Quota & Weekly Limit
    lines.append("")
    lines.append(f"{BOLD}【1. 每周限额 & 5小时限额实时配速】{RESET}")
    if q["has_live_quota"]:
        for b in q["buckets"]:
            rem = b["remaining_pct"] if b["remaining_pct"] is not None else 0.0
            used = b["used_pct"] if b["used_pct"] is not None else 0.0
            col = CYAN if b["status"] == "reset_ready" else used_bar_color(used)
            status_tag = (
                f"{CYAN}[已到期待刷新]{RESET}"
                if b["status"] == "reset_ready"
                else f"{RED}[告急]{RESET}"
                if b["status"] == "critical"
                else f"{YELLOW}[偏快]{RESET}"
                if b["status"] == "warning"
                else f"{GREEN}[健康]{RESET}"
            )
            lines.append(
                f"  {BOLD}{pad_display(b['label'], 26)}{RESET} {bar(used, 16, col)} "
                f"{col}{BOLD}已用 {used:5.1f}%{RESET} {DIM}(剩 {rem:5.1f}%){RESET} {status_tag}  "
                f"重置: {CYAN}{b['reset_time_cst']}{RESET} {DIM}({b['reset_in_text']}){RESET}"
            )
            extra_bits: List[str] = []
            if b["time_elapsed_pct"] is not None:
                p_str = f" · 配速 {b['pacing_ratio']}x" if b["pacing_ratio"] is not None else ""
                extra_bits.append(f"周期已过 {b['time_elapsed_pct']:.1f}%{p_str}")
            if b["window_kind"] == "weekly" and b.get("daily_safe_budget_pct") is not None:
                extra_bits.append(f"日均安全预算 {b['daily_safe_budget_pct']}%")
            if b["burn_pct_per_hour"] is not None:
                if b["window_kind"] == "five_hour":
                    extra_bits.append(f"速率 {b['burn_pct_per_hour']}%/h")
                else:
                    extra_bits.append(f"速率 {b['burn_pct_per_hour']}%/h ({b['burn_pct_per_day']}%/天)")
            if b["projected_rem_at_reset"] is not None:
                if b["projected_rem_at_reset"] <= 0.1:
                    extra_bits.append(f"{RED}预计 {b['projected_exhaust_text']} 后耗尽{RESET}")
                else:
                    extra_bits.append(f"{GREEN}重置前预计剩 {b['projected_rem_at_reset']:.1f}%{RESET}")
            if b["tokens_per_1pct"] is not None:
                extra_bits.append(f"1%≈{fmt_tokens(b['tokens_per_1pct'])}有效tok")
            if extra_bits:
                lines.append(f"    {DIM}↳ {RESET}" + f" {DIM}│{RESET} ".join(extra_bits))
        lines.append(f"  {DIM}采样源: {q['source']} · 累计 {q['snapshot_count']} 个快照 · 更新于 {q['stale_text']}前{RESET}")
    else:
        sl_path = ls.get("statusline_path") or str(APP_DIR / "statusline.py")
        lines.append(f"  {YELLOW}等待首次实时限额推送{RESET}（当前会话在 agy 内输入 {CYAN}/statusline {sl_path}{RESET} 或新开会话即秒连）。")

    # Section 2: Time windows overview
    lines.append("")
    lines.append(
        f"{BOLD}【2. 多周期 Token 用量总览】{RESET}  "
        f"{DIM}(缓存已为你省约 {GREEN}{fmt_usd(sel['cache_saved_usd'])}{RESET}{DIM} / {sel['cache_saved_pct']}%){RESET}"
    )
    lines.append(
        f"  {DIM}{'窗口':<10} {'调用':>6} {'新增输入':>10} {'缓存命中':>10} {'输出':>9} {'有效合计':>10} {'缓存率':>7} {'估算费用':>9}{RESET}"
    )
    tz_lbl = data.get("timezone_label") or "UTC+8"
    rows = [
        ("近 5 小时", wins["5h"]),
        (f"今日({tz_lbl})", wins["today"]),
        ("近 24 小时", wins["24h"]),
        ("本周(周一起)", wins["calendar_week"]),
        ("近 7 天", wins["7d"]),
        ("全部历史", wins["all"]),
    ]
    for lbl, s in rows:
        lines.append(
            f"  {pad_display(lbl, 12)} {s['calls']:>6} {fmt_tokens(s['input_tokens']):>10} "
            f"{DIM}{fmt_tokens(s['cache_read_tokens']):>10}{RESET} {fmt_tokens(s['output_tokens']):>9} "
            f"{BOLD}{fmt_tokens(s['billable_tokens']):>10}{RESET} {GREEN}{s['cache_hit_pct']:>6.1f}%{RESET} "
            f"{YELLOW}{fmt_usd(s['est_cost_usd']):>9}{RESET}"
        )
    wow = data.get("week_over_week") or {}
    if wow:
        if wow.get("comparable"):
            dp = float(wow.get("delta_pct") or 0.0)
            wc = GREEN if dp <= 0 else YELLOW
            prev_t = fmt_tokens((wow.get("previous") or {}).get("billable_tokens") or 0)
            cur_t = fmt_tokens((wow.get("current") or {}).get("billable_tokens") or 0)
            lines.append(
                f"  {DIM}自然周同进度环比 ({wow.get('elapsed_hours', 0)}h): {RESET}"
                f"{wc}{BOLD}{wow.get('badge_text')}{RESET} {DIM}(本周 {cur_t} vs 上周同期 {prev_t}){RESET}"
            )
        else:
            lines.append(f"  {DIM}自然周同进度环比: {wow.get('badge_text')}（{wow.get('reason', '')}）{RESET}")
    lines.append(
        f"  {DIM}近 5h 实时燃速: {b5['calls_per_hour']} 次/h · {fmt_tokens(b5['billable_tokens_per_hour'])} 有效tok/h · 估算 {fmt_usd(b5['est_cost_per_hour'])}/h{RESET}"
    )

    # Section 3: Model pools & breakdown
    lines.append("")
    lines.append(f"{BOLD}【3. 模型限额池分布 (窗口: {data['window']})】{RESET}")
    pool_colors = {"gemini_pro": CYAN, "claude_gpt": MAGENTA, "gemini_flash": GREEN, "other": DIM}
    if data["by_pool"]:
        for p in data["by_pool"]:
            c = pool_colors.get(p["pool"], CYAN)
            lines.append(
                f"  {pad_display(p['label'], 24)} {bar(p['share_billable_pct'], 16, c)} "
                f"{BOLD}{p['share_billable_pct']:5.1f}%{RESET}  "
                f"{fmt_tokens(p['billable_tokens']):>8} 有效  {DIM}({p['calls']}次 · 缓存{p['cache_hit_pct']}% · 估算{fmt_usd(p['est_cost_usd'])}){RESET}"
            )
    else:
        lines.append(f"  {DIM}(当前窗口无调用){RESET}")

    if data["by_model"] and not compact:
        lines.append(f"  {DIM}细分模型:{RESET}")
        for m in data["by_model"][:8]:
            lines.append(
                f"    • {m['model']:<26} {m['calls']:>4}次  新增{fmt_tokens(m['input_tokens']):>7}  "
                f"缓存{fmt_tokens(m['cache_read_tokens']):>7}({m['cache_hit_pct']:>4.1f}%)  "
                f"输出{fmt_tokens(m['output_tokens']):>7}  {YELLOW}{fmt_usd(m['est_cost_usd']):>7}{RESET}"
            )

    # Section 4: 5h burst, 24h Sparkline & 7-day trend
    lines.append("")
    s5_vals = [x["billable_tokens"] for x in data["rolling_5h_10m"]]
    h_vals = [h["billable_tokens"] for h in data["hourly_24h"]]
    peak_h = max(data["hourly_24h"], key=lambda x: x["billable_tokens"]) if data["hourly_24h"] else None
    peak_txt = f"峰值 {peak_h['label']} ({fmt_tokens(peak_h['billable_tokens'])}, {peak_h['calls']}次)" if peak_h and peak_h["billable_tokens"] > 0 else "无活跃"
    lines.append(f"{BOLD}【4. 5h 燃速 / 24h 曲线 & 7日每日趋势 ({tz_lbl})】{RESET}")
    lines.append(f"  5h 燃速(10m) : {MAGENTA}{sparkline(s5_vals)}{RESET}  {DIM}({data['rolling_5h_10m'][0]['label']} → {data['rolling_5h_10m'][-1]['label']}){RESET}")
    lines.append(f"  24h Token曲线: {CYAN}{sparkline(h_vals)}{RESET}  {DIM}({data['hourly_24h'][0]['label']} → {data['hourly_24h'][-1]['label']} · {peak_txt}){RESET}")

    max_d = max((d["billable_tokens"] for d in data["daily_7d"]), default=1) or 1
    for d in data["daily_7d"]:
        pct = (d["billable_tokens"] / max_d) * 100.0 if d["billable_tokens"] > 0 else 0.0
        lines.append(
            f"  {d['label']}  {bar(pct, 22, BLUE)} {fmt_tokens(d['billable_tokens']):>8}  "
            f"{DIM}{d['calls']:>4}次 · 缓存{fmt_tokens(d['cache_read_tokens']):>7} · 估算{fmt_usd(d['est_cost_usd'])}{RESET}"
        )

    # Section 5: Top conversations & Top tools
    if not compact:
        lines.append("")
        lines.append(f"{BOLD}【5. Top 消耗会话 (窗口: {data['window']})】{RESET}")
        for c in data["conversations"][:8]:
            raw_title = f"[子] {c['title']}" if c["is_subagent"] else c["title"]
            title = trunc_display(raw_title, 30)
            lines.append(
                f"  {DIM}{c['short_id']}{RESET} {pad_display(title, 30)} "
                f"{DIM}{pad_display(trunc_display(c['workspace'], 16), 16)}{RESET} "
                f"{BOLD}{fmt_tokens(c['billable_tokens']):>8}{RESET} "
                f"{DIM}({c['calls']:>3}次 · 缓存{c['cache_hit_pct']:>4.1f}% · {c['last_ts_cst']}){RESET}"
            )
        if data.get("top_tools"):
            top_t = "  ".join(f"{t['name']}({t['count']})" for t in data["top_tools"][:6])
            lines.append(f"\n  {DIM}高频工具: {top_t}{RESET}")

    return "\n".join(lines)


def cmd_report(args: argparse.Namespace) -> int:
    data = build_analytics(window=args.window)
    print(render_terminal_report(data, compact=args.compact))
    return 0


def cmd_json(args: argparse.Namespace) -> int:
    data = build_analytics(window=args.window)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    interval = max(1.0, float(args.interval))
    try:
        while True:
            data = build_analytics(window=args.window)
            out = render_terminal_report(data, compact=args.compact)
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.write(out)
            sys.stdout.write(f"\n\n{DIM}实时监控中（每 {interval:.0f}s 刷新，按 Ctrl+C 退出 · 浏览器看板: agy-usage web）{RESET}\n")
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n已退出实时监控。")
        return 0


def make_handler(port: int) -> type:
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
            return bool(ok and exit_code.value == 259)  # STILL_ACTIVE
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


def cmd_web(args: argparse.Namespace) -> int:
    if getattr(args, "daemon_log", False):
        stream = LockedLogStream()
        sys.stdout = stream  # type: ignore[assignment]
        sys.stderr = stream  # type: ignore[assignment]
    host = "127.0.0.1"
    port = int(args.port)
    try:
        server = ReusableHTTPServer((host, port), make_handler(port))
    except Exception as exc:
        print(f"启动 Web 监控台失败 (127.0.0.1:{port}): {exc}", file=sys.stderr, flush=True)
        return 1
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
    return 0


def cmd_daemon(args: argparse.Namespace) -> int:
    ensure_data_dir()
    port = int(args.port)
    action = args.action
    pid = _read_pid()

    if action == "status":
        if pid:
            print(f"{GREEN}● 运行中{RESET} (PID {pid}) -> http://127.0.0.1:{port}")
        else:
            print(f"{DIM}○ 未运行{RESET}")
        return 0

    if action == "stop":
        if not pid:
            print("后台看板未在运行。")
            PID_FILE.unlink(missing_ok=True)
            return 0
        _stop_pid(pid)
        time.sleep(0.3)
        PID_FILE.unlink(missing_ok=True)
        print(f"{GREEN}✓ 已停止后台看板{RESET} (PID {pid})")
        return 0

    if action in ("start", "restart"):
        if pid:
            if action == "start":
                print(f"{GREEN}● 后台看板已在运行{RESET} (PID {pid}) -> http://127.0.0.1:{port}")
                if not args.no_open:
                    webbrowser.open(f"http://127.0.0.1:{port}")
                return 0
            _stop_pid(pid)
            time.sleep(0.4)
            PID_FILE.unlink(missing_ok=True)

        rotate_web_log()
        py_exe = sys.executable
        popen_kwargs: Dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            pyw = Path(py_exe).with_name("pythonw.exe")
            if pyw.exists():
                py_exe = str(pyw)
            popen_kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(
            [py_exe, str(APP_DIR / "cli.py"), "web", "--port", str(port), "--no-open", "--daemon-log"],
            **popen_kwargs,
        )
        PID_FILE.write_text(str(proc.pid), encoding="utf-8")
        time.sleep(0.5)
        if proc.poll() is not None:
            PID_FILE.unlink(missing_ok=True)
            print(f"{RED}✖ 后台启动失败（端口 {port} 可能被占用），请查看 {LOG_FILE}{RESET}", file=sys.stderr)
            return 1
        url = f"http://127.0.0.1:{port}"
        print(f"{GREEN}✓ 已在后台启动监控台{RESET} (PID {proc.pid}) -> {BOLD}{CYAN}{url}{RESET}")
        if not args.no_open:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        return 0
    return 0


def cmd_install_statusline(args: argparse.Namespace) -> int:
    statusline_path = str(APP_DIR / "statusline.py")
    cmd_str = f'"{sys.executable}" "{statusline_path}"' if os.name == "nt" else statusline_path
    sf = discover_settings_file()
    sf.parent.mkdir(parents=True, exist_ok=True)
    cfg: Dict[str, Any] = {}
    if sf.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = sf.with_name(f"settings.json.bak-agy-usage-{ts}")
        shutil.copy2(sf, backup)
        print(f"已备份原配置: {backup}")
        try:
            loaded = json.loads(sf.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg = loaded
        except Exception:
            cfg = {}

    cfg["statusLine"] = {
        "type": "command",
        "command": cmd_str,
        "enabled": True,
        "stack_with_default": bool(args.stack),
    }
    atomic_write_text(sf, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", mode=0o600)
    print(f"{GREEN}✓ 已在 {sf} 启用 statusLine:{RESET}")
    print(f"  command: {cmd_str}")
    print(f"  stack_with_default: {bool(args.stack)}")
    print(f"提示：新开的 agy 会话会自动生效；当前已打开的 agy 会话可输入 {CYAN}/statusline {cmd_str}{RESET} 立即刷新。")
    return 0


def cmd_uninstall_statusline(_args: argparse.Namespace) -> int:
    sf = discover_settings_file()
    if not sf.exists():
        print("未找到 settings.json")
        return 0
    cfg = json.loads(sf.read_text(encoding="utf-8"))
    if "statusLine" not in cfg:
        print("settings.json 中未配置 statusLine")
        return 0
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = sf.with_name(f"settings.json.bak-agy-usage-{ts}")
    shutil.copy2(sf, backup)
    del cfg["statusLine"]
    atomic_write_text(sf, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", mode=0o600)
    print(f"{GREEN}✓ 已移除 statusLine 配置{RESET}（原配置备份于 {backup}）")
    return 0


def _fmt_bytes(n: int) -> str:
    v = float(max(0, n))
    if v >= 1024 * 1024 * 1024:
        return f"{v / (1024 ** 3):.2f} GB"
    if v >= 1024 * 1024:
        return f"{v / (1024 ** 2):.2f} MB"
    if v >= 1024:
        return f"{v / 1024:.1f} KB"
    return f"{int(v)} B"


def cmd_clean(args: argparse.Namespace) -> int:
    res = clean_cache(
        keep_days=int(args.keep_days),
        reset_index=bool(args.reset_index),
        max_backups=int(args.max_backups),
    )
    sn = res["snapshots"]
    print(f"{BOLD}{CYAN}━━━ agy-usage 缓存瘦身与清理结果 ━━━{RESET}")
    print(f"  缓存目录    : {res['cache_dir']}")
    arch_hint = f" · 归档 {sn['archived_days']} 天" if sn["archived_days"] else ""
    print(
        f"  限额快照压缩: {sn['before_lines']} 行 -> {BOLD}{sn['after_lines']}{RESET} 行 "
        f"({_fmt_bytes(sn['bytes_before'])} -> {_fmt_bytes(sn['bytes_after'])}{arch_hint})"
    )
    print(f"  增量索引缓存: 当前跟踪 {BOLD}{res['index_entries']}{RESET} 个活跃会话日志文件")
    if res["backups_removed"] > 0:
        print(f"  旧配置备份  : 已清理 {res['backups_removed']} 份多余 settings.json.bak 备份")
    print(f"  {GREEN}✓ 共释放空间: {_fmt_bytes(res['bytes_freed'])}{RESET}（当前缓存总占用 {_fmt_bytes(res['bytes_after'])}）")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    # Inspect read-only FIRST before modifying or cleaning anything ("doctor 先展示再清")
    rep = run_doctor(stale_days=int(args.stale_days), prune_stale=False, fix_issues=False)
    pipe = rep.get("pipeline") or {}
    daemon_pid = _read_pid()

    print(f"{BOLD}{CYAN}━━━ Antigravity & agy-usage 数据与链路健康体检 ━━━{RESET}")
    print(f"  监控自有缓存: {_fmt_bytes(rep['own_cache_bytes'])} ({rep['own_cache_dir']})")
    print(f"  分会话索引  : 已缓存 {rep['index_cached_files']} 个会话分片（单会话更新仅重写对应小分片）")
    print(f"  AGY 数据总占: {BOLD}{_fmt_bytes(rep['total_agy_bytes'])}{RESET}（共登记 {rep['total_conversations']} 个会话）")

    sl_ok = pipe.get("statusline_enabled") and pipe.get("statusline_path_valid") and pipe.get("statusline_executable")
    age_s = pipe.get("live_state_age_seconds")
    age_txt = f"{age_s}秒前" if age_s is not None else "尚未生成 live_state.json"
    bad_lines = int(pipe.get("corrupt_snapshot_lines") or 0) + int(pipe.get("corrupt_archive_lines") or 0)
    tmp_cnt = int(pipe.get("orphan_tmp_count") or 0)

    print("")
    print(f"{BOLD}【实时采集链路诊断】{RESET}")
    print(f"  • 状态栏配置 : {f'{GREEN}✓ 正常{RESET}' if sl_ok else f'{YELLOW}⚠ 待修复{RESET}'} ({rep.get('settings_file')})")
    print(f"  • 后台监控台 : {f'{GREEN}● 运行中 (PID {daemon_pid}){RESET}' if daemon_pid else f'{YELLOW}○ 未运行{RESET}'}")
    print(f"  • 最近采集   : {age_txt}")
    print(f"  • 缓存完整性 : 损坏行 {bad_lines} 条 · 遗留临时文件 {tmp_cnt} 个")

    empty_cnt = len(rep["empty_db_entries"])
    orphan_cnt = len(rep["orphan_brain_dirs"])
    stale_cnt = len(rep["stale_sessions"])
    stale_bytes = sum(x["bytes"] for x in rep["stale_sessions"])

    print("")
    print(f"{BOLD}【存储扫描明细（安全只读模式，不直接篡改 AGY SQLite 库）】{RESET}")
    print(f"  • 空壳/零步数记录 : {empty_cnt} 条")
    print(f"  • 孤儿 brain 目录 : {orphan_cnt} 个")
    print(f"  • 超过 {rep['stale_days']} 天陈旧会话: {stale_cnt} 个（共占 {_fmt_bytes(stale_bytes)}）")

    if rep["stale_sessions"]:
        print(f"\n  {DIM}Top 陈旧大体积会话:{RESET}")
        for s in rep["stale_sessions"][:8]:
            print(
                f"    {DIM}{s['short_id']}{RESET}  {_fmt_bytes(s['bytes']):>9}  "
                f"{s['age_days']:>3}天前 ({s['last_cst']})  {trunc_display(s['title'], 32)}"
            )

    if getattr(args, "fix", False):
        print("")
        fix_rep = run_doctor(stale_days=int(args.stale_days), prune_stale=False, fix_issues=True)
        c_res = clean_cache(keep_days=30)
        for act in fix_rep.get("fixed_actions") or []:
            print(f"  {GREEN}✓ 已修复: {act}{RESET}")
        if c_res["bytes_freed"] > 0:
            print(f"  {GREEN}✓ 已压缩自有缓存，释放 {_fmt_bytes(c_res['bytes_freed'])}{RESET}")
        if not daemon_pid:
            ns = argparse.Namespace(action="start", port=18420, no_open=True)
            cmd_daemon(ns)
    elif not sl_ok or bad_lines > 0 or tmp_cnt > 0:
        print(f"\n  {YELLOW}提示：发现可自动修复的本地配置或临时文件问题，可运行: agy-usage doctor --fix{RESET}")

    if args.prune_stale:
        p_rep = run_doctor(stale_days=int(args.stale_days), prune_stale=True, fix_issues=False)
        print("")
        if p_rep["deleted_ids"]:
            print(f"  {GREEN}✓ 已通过官方 ConversationService 安全清理 {len(p_rep['deleted_ids'])} 个失效/陈旧会话{RESET}")
        elif not p_rep["ls_api_available"]:
            print(
                f"  {YELLOW}提示：当前不在 agy 内部会话环境中（未检测到 ANTIGRAVITY_LS_ADDRESS）。{RESET}\n"
                f"  {DIM}为保护 conversation_summaries.db WAL 锁安全，外部终端不直接硬删 SQLite；可在 agy 会话内运行 `agy-usage doctor --prune-stale` 或用 `/delete` 安全清理老会话。{RESET}"
            )
        else:
            print(f"  {GREEN}✓ 无需清理，未发现超期陈旧会话。{RESET}")
    elif stale_cnt > 0 or empty_cnt > 0:
        print(f"\n  {DIM}如需在 agy 内通过官方接口安全清理上述空壳与超期会话，可运行: agy-usage doctor --stale-days {rep['stale_days']} --prune-stale{RESET}")

    return 0


def cmd_notify(args: argparse.Namespace) -> int:
    act = args.action
    if act == "on":
        prefs = set_preferences(notifications_enabled=True)
        print(f"{GREEN}✓ 已开启额度告警 (80%/95%) 与回血桌面通知{RESET}")
        return 0
    if act == "off":
        prefs = set_preferences(notifications_enabled=False)
        print(f"{DIM}○ 已关闭桌面通知提醒{RESET}")
        return 0
    prefs = get_preferences()
    st = f"{GREEN}开启{RESET}" if prefs.get("notifications_enabled") else f"{DIM}关闭（默认）{RESET}"
    print(f"桌面通知状态: {st}（可用 `agy-usage notify on` 或 `off` 切换）")
    return 0


def cmd_record_quota(args: argparse.Namespace) -> int:
    try:
        res = save_manual_quota(args.bucket, args.remaining_pct, args.reset)
    except (ValueError, TimeoutError) as exc:
        print(f"{RED}{exc}{RESET}", file=sys.stderr)
        return 1
    rem = res["remaining_pct"]
    print(f"{GREEN}✓ 已记录限额快照:{RESET} {res['bucket']} 剩余 {rem:.1f}% (已用 {100.0 - rem:.1f}%)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agy-usage",
        description="Antigravity CLI (agy) 实时用量与每周限额分析统计工具",
    )
    p.add_argument(
        "-w",
        "--window",
        choices=["5h", "today", "24h", "week", "7d", "all"],
        default="7d",
        help="明细统计窗口（默认 7d）",
    )
    p.add_argument("--compact", action="store_true", help="精简输出模式")

    sub = p.add_subparsers(dest="cmd")

    p_watch = sub.add_parser("watch", help="终端实时自动刷新监控面板")
    p_watch.add_argument("-i", "--interval", type=float, default=2.0, help="刷新间隔秒数（默认 2）")
    p_watch.add_argument("-w", "--window", choices=["5h", "today", "24h", "week", "7d", "all"], default="7d")
    p_watch.add_argument("--compact", action="store_true")

    p_web = sub.add_parser("web", help="前台启动本地实时 Web 可视化看板")
    p_web.add_argument("-p", "--port", type=int, default=18420, help="监听端口（默认 18420）")
    p_web.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    p_web.add_argument("--daemon-log", action="store_true", help=argparse.SUPPRESS)

    p_d = sub.add_parser("daemon", help="后台常驻管理本地 Web 监控台 (start/stop/restart/status)")
    p_d.add_argument("action", choices=["start", "stop", "restart", "status"])
    p_d.add_argument("-p", "--port", type=int, default=18420, help="监听端口（默认 18420）")
    p_d.add_argument("--no-open", action="store_true", help="启动时不自动打开浏览器")

    p_json = sub.add_parser("json", help="输出结构化 JSON 分析数据")
    p_json.add_argument("-w", "--window", choices=["5h", "today", "24h", "week", "7d", "all"], default="7d")

    p_inst = sub.add_parser("install-statusline", help="将实时状态栏与限额采集器写入 agy settings.json")
    p_inst.add_argument("--stack", dest="stack", action="store_true", default=True, help="叠加在默认状态栏下方（默认开启）")
    p_inst.add_argument("--standalone", dest="stack", action="store_false", help="替换默认状态栏并显示模型名")

    sub.add_parser("uninstall-statusline", help="从 agy settings.json 移除 statusLine 配置")

    p_rec = sub.add_parser("record-quota", help="手动录入一次 /usage 看到的限额快照")
    p_rec.add_argument("bucket", help="限额桶名，如 gemini-weekly / gemini-5h / claude-weekly")
    p_rec.add_argument("remaining_pct", type=float, help="剩余百分比（0~100）")
    p_rec.add_argument("--reset", help="重置时间（本地时区），如 '2026-12-02 08:00' 或 '12-02 08:00'")

    p_clean = sub.add_parser("clean", help="压缩去重快照、轮转日志并清理孤儿缓存索引")
    p_clean.add_argument("--keep-days", type=int, default=30, help="保留高频快照天数，超期自动按日归档（默认 30）")
    p_clean.add_argument("--reset-index", action="store_true", help="清空并重建 transcript 增量索引缓存")
    p_clean.add_argument("--max-backups", type=int, default=3, help="最多保留几份 settings.json 备份（默认 3）")

    p_doc = sub.add_parser("doctor", help="先只读诊断链路与存储健康，可选 --fix 一键自修复或官方接口清理")
    p_doc.add_argument("--stale-days", type=int, default=30, help="超过多少天未活跃视为陈旧会话（默认 30）")
    p_doc.add_argument("--fix", action="store_true", help="自动修复 statusLine 配置、可执行权限、损坏行与孤儿临时文件")
    p_doc.add_argument("--prune-stale", action="store_true", help="通过官方 ConversationService 接口安全删除空壳与超期会话")

    p_not = sub.add_parser("notify", help="管理 80%/95% 额度告警与回血恢复桌面通知（默认关闭）")
    p_not.add_argument("action", nargs="?", choices=["on", "off", "status"], default="status")

    return p


def main() -> int:
    if os.name == "nt":
        os.system("")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd == "watch":
        return cmd_watch(args)
    if args.cmd == "web":
        return cmd_web(args)
    if args.cmd == "daemon":
        return cmd_daemon(args)
    if args.cmd == "json":
        return cmd_json(args)
    if args.cmd == "install-statusline":
        return cmd_install_statusline(args)
    if args.cmd == "uninstall-statusline":
        return cmd_uninstall_statusline(args)
    if args.cmd == "record-quota":
        return cmd_record_quota(args)
    if args.cmd == "clean":
        return cmd_clean(args)
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "notify":
        return cmd_notify(args)
    return cmd_report(args)


if __name__ == "__main__":
    raise SystemExit(main())
