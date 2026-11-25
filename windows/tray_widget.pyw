#!/usr/bin/env python3
"""Windows desktop mini-bar & popup widget for Antigravity CLI (agy-usage).

Pure Python stdlib (`tkinter` + `ctypes` + `urllib` + `subprocess`), zero `pip install` needed.
Includes Per-Monitor DPI awareness, taskbar work-area positioning (`SPI_GETWORKAREA`),
named mutex single-instance guard, dynamic widget sizing, and thread-safe shutdown.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

PORT = int(os.environ.get("AGY_USAGE_PORT", "18420"))
API_URL = f"http://127.0.0.1:{PORT}/api/stats?window=7d"
PREF_URL = f"http://127.0.0.1:{PORT}/api/preferences"
WEB_URL = f"http://127.0.0.1:{PORT}"
CLI_PATH = Path(__file__).resolve().parent.parent / "src" / "cli.py"

_MUTEX_HANDLE: Any = None
_LOCK_FH: Any = None


def _enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            return
        except Exception:
            pass
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _acquire_single_instance() -> bool:
    global _MUTEX_HANDLE, _LOCK_FH
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateMutexW(None, False, f"Local\\AGYUsageTrayWidgetMutex_{PORT}")
            if handle and kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                kernel32.CloseHandle(handle)
                return False
            _MUTEX_HANDLE = handle
            return True
        except Exception:
            return True
    try:
        import fcntl
        lock_dir = Path.home() / ".cache" / "agy-usage"
        lock_dir.mkdir(parents=True, exist_ok=True)
        fh = (lock_dir / ".tray_widget.lock").open("a+b")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_FH = fh
        return True
    except Exception:
        return False


def _get_work_area(root: Any) -> Tuple[int, int, int, int]:
    """Return (left, top, right, bottom) excluding Windows taskbar when available."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
                if rect.right > rect.left and rect.bottom > rect.top:
                    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
        except Exception:
            pass
    sw = int(root.winfo_screenwidth())
    sh = int(root.winfo_screenheight())
    return 0, 0, sw, max(240, sh - 48)


def fmt_tok(n: float) -> str:
    n = float(n or 0)
    if n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if n >= 1e6:
        return f"{n / 1e6:.2f}M"
    if n >= 1e3:
        return f"{n / 1e3:.1f}k"
    return str(int(round(n)))


def ensure_daemon() -> None:
    try:
        py = sys.executable
        flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0
        subprocess.Popen(
            [py, str(CLI_PATH), "daemon", "start", "--port", str(PORT), "--no-open"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception:
        pass


def main() -> int:
    if not _acquire_single_instance():
        return 0

    _enable_dpi_awareness()

    try:
        import tkinter as tk
    except Exception:
        webbrowser.open(WEB_URL)
        return 0

    ensure_daemon()

    root = tk.Tk()
    root.title("AGY Usage")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg="#0f1728", highlightthickness=1, highlightbackground="#263552")

    state: Dict[str, Any] = {
        "expanded": False,
        "closing": False,
        "notify_on": False,
        "drag_x": 0,
        "drag_y": 0,
    }

    bar_frame = tk.Frame(root, bg="#0f1728", cursor="hand2")
    bar_frame.pack(fill="x", padx=9, pady=5)

    dot_lbl = tk.Label(bar_frame, text="●", fg="#10b981", bg="#0f1728", font=("Segoe UI", 10, "bold"))
    dot_lbl.pack(side="left")

    summary_lbl = tk.Label(
        bar_frame,
        text="AGY 连接中...",
        fg="#edf2fb",
        bg="#0f1728",
        font=("Consolas", 9, "bold"),
    )
    summary_lbl.pack(side="left", padx=6)

    open_btn = tk.Label(bar_frame, text="↗", fg="#38bdf8", bg="#0f1728", font=("Segoe UI", 10, "bold"))
    open_btn.pack(side="right")

    detail_frame = tk.Frame(root, bg="#0f1728")
    detail_text = tk.Label(
        detail_frame,
        text="",
        justify="left",
        anchor="w",
        fg="#cbd5e1",
        bg="#0f1728",
        font=("Consolas", 9),
    )
    detail_text.pack(fill="x", padx=10, pady=(2, 6))

    btn_row = tk.Frame(detail_frame, bg="#0f1728")
    btn_row.pack(fill="x", padx=10, pady=(0, 8))

    def clamp_and_place(target_x: Optional[int] = None, target_y: Optional[int] = None, anchor_bottom_right: bool = False) -> None:
        root.update_idletasks()
        req_w = max(188, int(root.winfo_reqwidth()))
        req_h = max(30, int(root.winfo_reqheight()))
        wl, wt, wr, wb = _get_work_area(root)
        if anchor_bottom_right or target_x is None or target_y is None:
            nx = wr - req_w - 14
            ny = wb - req_h - 10
        else:
            nx = min(max(wl + 6, target_x), wr - req_w - 6)
            ny = min(max(wt + 6, target_y), wb - req_h - 6)
        root.geometry(f"{req_w}x{req_h}+{nx}+{ny}")

    def open_web(_evt: Any = None) -> None:
        ensure_daemon()
        webbrowser.open(WEB_URL)

    def reset_position() -> None:
        clamp_and_place(anchor_bottom_right=True)

    def toggle_notifications() -> None:
        def _post() -> None:
            try:
                body = json.dumps({"notifications_enabled": not state["notify_on"]}).encode("utf-8")
                req = urllib.request.Request(
                    PREF_URL,
                    data=body,
                    headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{PORT}"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=2.0).read()
            except Exception:
                pass
            if not state["closing"]:
                try:
                    root.after(50, trigger_immediate_poll)
                except Exception:
                    pass

        threading.Thread(target=_post, daemon=True).start()

    def quit_widget() -> None:
        state["closing"] = True
        try:
            root.destroy()
        except Exception:
            pass

    tk.Button(
        btn_row,
        text="打开完整监控台",
        command=open_web,
        bg="#2563eb",
        fg="#ffffff",
        relief="flat",
        font=("Microsoft YaHei UI", 8, "bold"),
        padx=8,
        pady=2,
        cursor="hand2",
    ).pack(side="left")

    tk.Button(
        btn_row,
        text="退出小工具",
        command=quit_widget,
        bg="#1e293b",
        fg="#94a3b8",
        relief="flat",
        font=("Microsoft YaHei UI", 8),
        padx=8,
        pady=2,
        cursor="hand2",
    ).pack(side="right")

    def toggle_expand(_evt: Any = None) -> None:
        old_x = root.winfo_x()
        old_bottom = root.winfo_y() + root.winfo_height()
        state["expanded"] = not state["expanded"]
        if state["expanded"]:
            detail_frame.pack(fill="both", expand=True)
        else:
            detail_frame.pack_forget()
        root.update_idletasks()
        new_h = max(30, int(root.winfo_reqheight()))
        clamp_and_place(target_x=old_x, target_y=old_bottom - new_h)

    def start_drag(evt: Any) -> None:
        state["drag_x"] = evt.x
        state["drag_y"] = evt.y

    def on_drag(evt: Any) -> None:
        nx = root.winfo_x() + evt.x - state["drag_x"]
        ny = root.winfo_y() + evt.y - state["drag_y"]
        clamp_and_place(target_x=nx, target_y=ny)

    for w in (bar_frame, dot_lbl, summary_lbl):
        w.bind("<ButtonPress-1>", start_drag)
        w.bind("<B1-Motion>", on_drag)
        w.bind("<Double-Button-1>", toggle_expand)

    ctx_menu = tk.Menu(root, tearoff=0, bg="#0f1728", fg="#edf2fb")
    ctx_menu.add_command(label="展开 / 收起详情 (双击)", command=toggle_expand)
    ctx_menu.add_command(label="打开完整 Web 监控台", command=open_web)
    ctx_menu.add_command(label="开启/关闭 80% 额度桌面提醒", command=toggle_notifications)
    ctx_menu.add_command(label="重置胶囊到右下角", command=reset_position)
    ctx_menu.add_separator()
    ctx_menu.add_command(label="退出悬浮小工具", command=quit_widget)

    def show_menu(evt: Any) -> None:
        ctx_menu.tk_popup(evt.x_root, evt.y_root)

    for w in (root, bar_frame, dot_lbl, summary_lbl):
        w.bind("<Button-3>", show_menu)
    open_btn.bind("<Button-1>", open_web)

    def ascii_bar(pct: float, width: int = 8) -> str:
        pct = max(0.0, min(100.0, pct))
        f = int(round((pct / 100.0) * width))
        return "█" * f + "░" * (width - f)

    def apply_data(d: Optional[Dict[str, Any]]) -> None:
        if state["closing"]:
            return
        try:
            if not d:
                dot_lbl.configure(fg="#f59e0b")
                summary_lbl.configure(text="AGY 离线 (双击)")
                detail_text.configure(text="本地服务未响应，点击下方按钮启动。")
                clamp_and_place(target_x=root.winfo_x(), target_y=root.winfo_y())
                return

            state["notify_on"] = bool((d.get("notifications") or {}).get("enabled", False))
            q = d.get("quota") or {}
            buckets = q.get("buckets") or []
            if q.get("has_live_quota") and buckets:
                gem_w = next(
                    (b for b in buckets if str(b.get("pool_key", "")).startswith("gemini") and b.get("window_kind") == "weekly"),
                    None,
                )
                cld_w = next(
                    (b for b in buckets if b.get("pool_key") == "claude_gpt" and b.get("window_kind") == "weekly"),
                    None,
                )
                parts = []
                if gem_w and gem_w.get("used_pct") is not None:
                    parts.append(f"G {gem_w['used_pct']:.0f}%")
                if cld_w and cld_w.get("used_pct") is not None:
                    parts.append(f"C {cld_w['used_pct']:.0f}%")
                if not parts:
                    parts.append(f"AGY {buckets[0].get('used_pct', 0):.0f}%")

                statuses = [b.get("status") for b in buckets]
                col = "#ef4444" if "critical" in statuses else ("#f59e0b" if "warning" in statuses else "#10b981")
                dot_lbl.configure(fg=col)
                summary_lbl.configure(text=" │ ".join(parts))

                lines = []
                for b in buckets[:4]:
                    u = float(b.get("used_pct") or 0)
                    pool = "Claude" if b.get("pool_key") == "claude_gpt" else "Gemini"
                    win = "5h" if b.get("window_kind") == "five_hour" else "周"
                    rst = "待刷新" if b.get("reset_passed") else (b.get("reset_time_cst") or "-")
                    lines.append(f"{pool}{win:<2} {ascii_bar(u)} 已用{u:5.1f}% ({rst})")
            else:
                wt = (d.get("windows") or {}).get("today") or {}
                dot_lbl.configure(fg="#10b981")
                summary_lbl.configure(text=f"AGY 今日 {fmt_tok(wt.get('billable_tokens', 0))}")
                lines = ["等待新开的 Antigravity 会话推送实时额度"]

            w7 = (d.get("windows") or {}).get("7d") or {}
            wow = (d.get("week_over_week") or {}).get("badge_text") or ""
            wow_s = f" · {wow}" if wow else ""
            ntf_s = "开" if state["notify_on"] else "关"
            lines.append("-" * 38)
            lines.append(f"近7日有效: {fmt_tok(w7.get('billable_tokens', 0))}{wow_s}")
            lines.append(f"提醒:{ntf_s} · 双击收起 · 拖动移动 · 右键菜单")
            detail_text.configure(text="\n".join(lines))
            clamp_and_place(target_x=root.winfo_x(), target_y=root.winfo_y())
        except Exception:
            pass

    def trigger_immediate_poll() -> None:
        if state["closing"]:
            return

        def worker() -> None:
            data = None
            try:
                req = urllib.request.Request(API_URL, headers={"Host": f"127.0.0.1:{PORT}"})
                raw = urllib.request.urlopen(req, timeout=2.5).read().decode("utf-8")
                data = json.loads(raw)
            except Exception:
                pass
            if not state["closing"]:
                try:
                    root.after(0, lambda: apply_data(data))
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def poll_loop() -> None:
        if state["closing"]:
            return
        trigger_immediate_poll()
        try:
            root.after(6000, poll_loop)
        except Exception:
            pass

    clamp_and_place(anchor_bottom_right=True)
    poll_loop()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
