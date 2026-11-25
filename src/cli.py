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
    SETTINGS_FILE,
    build_analytics,
    ensure_data_dir,
    export_sessions_csv,
    fmt_tokens,
    get_conversation_detail,
    save_manual_quota,
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


def rem_color(rem_pct: Optional[float]) -> str:
    if rem_pct is None:
        return DIM
    if rem_pct <= 15:
        return RED
    if rem_pct <= 35:
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
            col = rem_color(rem)
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
                f"  {BOLD}{pad_display(b['label'], 26)}{RESET} {bar(rem, 16, col)} "
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
    rows = [
        ("近 5 小时", wins["5h"]),
        ("今日(CST)", wins["today"]),
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
    lines.append(f"{BOLD}【4. 5h 燃速 / 24h 曲线 & 7日每日趋势 (CST)】{RESET}")
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


def make_handler() -> type:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *log_args: Any) -> None:
            return

        def _send(self, code: int, content_type: str, body: bytes, extra_headers: Optional[Dict[str, str]] = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
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
            parsed = urlparse(self.path)
            if parsed.path == "/api/record-quota":
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    raw = self.rfile.read(min(length, 16384)).decode("utf-8")
                    payload = json.loads(raw)
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


class ReusableHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def cmd_web(args: argparse.Namespace) -> int:
    host = "127.0.0.1"
    port = int(args.port)
    server = ReusableHTTPServer((host, port), make_handler())
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

        log_fh = LOG_FILE.open("ab")
        py_exe = sys.executable
        popen_kwargs: Dict[str, Any] = {"stdout": log_fh, "stderr": log_fh}
        if os.name == "nt":
            pyw = Path(py_exe).with_name("pythonw.exe")
            if pyw.exists():
                py_exe = str(pyw)
            popen_kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(
            [py_exe, str(APP_DIR / "cli.py"), "web", "--port", str(port), "--no-open"],
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
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg: Dict[str, Any] = {}
    if SETTINGS_FILE.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = SETTINGS_FILE.with_name(f"settings.json.bak-agy-usage-{ts}")
        shutil.copy2(SETTINGS_FILE, backup)
        print(f"已备份原配置: {backup}")
        cfg = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))

    cfg["statusLine"] = {
        "type": "command",
        "command": cmd_str,
        "enabled": True,
        "stack_with_default": bool(args.stack),
    }
    tmp = SETTINGS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, SETTINGS_FILE)
    print(f"{GREEN}✓ 已在 {SETTINGS_FILE} 启用 statusLine:{RESET}")
    print(f"  command: {cmd_str}")
    print(f"  stack_with_default: {bool(args.stack)}")
    print(f"提示：新开的 agy 会话会自动生效；当前已打开的 agy 会话可输入 {CYAN}/statusline {cmd_str}{RESET} 立即刷新。")
    return 0


def cmd_uninstall_statusline(_args: argparse.Namespace) -> int:
    if not SETTINGS_FILE.exists():
        print("未找到 settings.json")
        return 0
    cfg = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    if "statusLine" not in cfg:
        print("settings.json 中未配置 statusLine")
        return 0
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = SETTINGS_FILE.with_name(f"settings.json.bak-agy-usage-{ts}")
    shutil.copy2(SETTINGS_FILE, backup)
    del cfg["statusLine"]
    tmp = SETTINGS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, SETTINGS_FILE)
    print(f"{GREEN}✓ 已移除 statusLine 配置{RESET}（原配置备份于 {backup}）")
    return 0


def cmd_record_quota(args: argparse.Namespace) -> int:
    try:
        res = save_manual_quota(args.bucket, args.remaining_pct, args.reset)
    except ValueError as exc:
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

    p_d = sub.add_parser("daemon", help="后台常驻管理本地 Web 监控台 (start/stop/restart/status)")
    p_d.add_argument("action", choices=["start", "stop", "restart", "status"])
    p_d.add_argument("-p", "--port", type=int, default=18420, help="监听端口（默认 18420）")
    p_d.add_argument("--no-open", action="store_true", help="启动时不自动打开浏览器")

    p_json = sub.add_parser("json", help="输出结构化 JSON 分析数据")
    p_json.add_argument("-w", "--window", choices=["5h", "today", "24h", "week", "7d", "all"], default="7d")

    p_inst = sub.add_parser("install-statusline", help="将实时状态栏与限额采集器写入 agy settings.json")
    p_inst.add_argument("--stack", action="store_true", help="叠加在默认状态栏下方而非替换")

    sub.add_parser("uninstall-statusline", help="从 agy settings.json 移除 statusLine 配置")

    p_rec = sub.add_parser("record-quota", help="手动录入一次 /usage 看到的限额快照")
    p_rec.add_argument("bucket", help="限额桶名，如 gemini-weekly / gemini-5h / claude-weekly")
    p_rec.add_argument("remaining_pct", type=float, help="剩余百分比（0~100）")
    p_rec.add_argument("--reset", help="重置时间（CST），如 '2026-12-02 08:00' 或 '12-02 08:00'")

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
    return cmd_report(args)


if __name__ == "__main__":
    raise SystemExit(main())
