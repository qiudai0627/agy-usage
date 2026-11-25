#!/usr/bin/env python3
"""Windows desktop mini-bar & popup widget for Antigravity CLI (agy-usage).

Pure Python stdlib (`tkinter` + `urllib` + `subprocess`), zero `pip install` needed.
Runs windowless via `pythonw.exe`: docks a sleek dark-mode status pill near the
bottom-right taskbar (`● G 9% │ C 55%`); click to expand 4-bucket quota bars or
open the full Web Dashboard.
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
from typing import Any, Dict, Optional

PORT = int(os.environ.get("AGY_USAGE_PORT", "18420"))
API_URL = f"http://127.0.0.1:{PORT}/api/stats?window=7d"
WEB_URL = f"http://127.0.0.1:{PORT}"
CLI_PATH = Path(__file__).resolve().parent.parent / "src" / "cli.py"


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

    # Position bottom-right above Windows taskbar
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    pill_w, pill_h = 196, 32
    x0, y0 = sw - pill_w - 20, sh - pill_h - 58
    root.geometry(f"{pill_w}x{pill_h}+{x0}+{y0}")

    state: Dict[str, Any] = {"expanded": False, "data": None, "drag_x": 0, "drag_y": 0}

    # Pill bar
    bar_frame = tk.Frame(root, bg="#0f1728", cursor="hand2")
    bar_frame.pack(fill="x", padx=8, pady=5)

    dot_lbl = tk.Label(bar_frame, text="●", fg="#10b981", bg="#0f1728", font=("Segoe UI", 10, "bold"))
    dot_lbl.pack(side="left")

    summary_lbl = tk.Label(
        bar_frame,
        text="AGY 连接中...",
        fg="#edf2fb",
        bg="#0f1728",
        font=("Consolas", 9, "bold"),
    )
    summary_lbl.pack(side="left", padx=5)

    open_btn = tk.Label(bar_frame, text="↗", fg="#38bdf8", bg="#0f1728", font=("Segoe UI", 10, "bold"))
    open_btn.pack(side="right")

    # Expandable detail panel
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

    def open_web(_evt: Any = None) -> None:
        ensure_daemon()
        webbrowser.open(WEB_URL)

    def quit_widget() -> None:
        root.destroy()

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
        state["expanded"] = not state["expanded"]
        cur_x = root.winfo_x()
        cur_y = root.winfo_y()
        if state["expanded"]:
            detail_frame.pack(fill="both", expand=True)
            new_w, new_h = 310, 215
            new_x = min(cur_x, sw - new_w - 12)
            new_y = max(20, cur_y - (new_h - pill_h))
            root.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")
        else:
            detail_frame.pack_forget()
            new_y = min(sh - pill_h - 52, cur_y + (215 - pill_h))
            root.geometry(f"{pill_w}x{pill_h}+{cur_x}+{new_y}")

    def start_drag(evt: Any) -> None:
        state["drag_x"] = evt.x
        state["drag_y"] = evt.y

    def on_drag(evt: Any) -> None:
        nx = root.winfo_x() + evt.x - state["drag_x"]
        ny = root.winfo_y() + evt.y - state["drag_y"]
        root.geometry(f"+{nx}+{ny}")

    for w in (bar_frame, dot_lbl, summary_lbl):
        w.bind("<ButtonPress-1>", start_drag)
        w.bind("<B1-Motion>", on_drag)
        w.bind("<Double-Button-1>", toggle_expand)

    # Right-click menu
    ctx_menu = tk.Menu(root, tearoff=0, bg="#0f1728", fg="#edf2fb")
    ctx_menu.add_command(label="展开 / 收起详情 (双击)", command=toggle_expand)
    ctx_menu.add_command(label="打开完整 Web 监控台", command=open_web)
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
        if not d:
            dot_lbl.configure(fg="#f59e0b")
            summary_lbl.configure(text="AGY 离线 (双击)")
            detail_text.configure(text="本地服务未响应，点击下方按钮启动。")
            return

        q = d.get("quota") or {}
        buckets = q.get("buckets") or []
        if q.get("has_live_quota") and buckets:
            gem_w = next((b for b in buckets if str(b.get("pool_key", "")).startswith("gemini") and b.get("window_kind") == "weekly"), None)
            cld_w = next((b for b in buckets if b.get("pool_key") == "claude_gpt" and b.get("window_kind") == "weekly"), None)
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
                rst = b.get("reset_time_cst") or "-"
                lines.append(f"{pool}{win:<2} {ascii_bar(u)} {u:5.1f}% ({rst})")
        else:
            wt = (d.get("windows") or {}).get("today") or {}
            dot_lbl.configure(fg="#10b981")
            summary_lbl.configure(text=f"AGY 今日 {fmt_tok(wt.get('billable_tokens', 0))}")
            lines = ["等待 agy 推送实时周限额 (/statusline)"]

        w7 = (d.get("windows") or {}).get("7d") or {}
        lines.append("-" * 34)
        lines.append(f"近7日有效: {fmt_tok(w7.get('billable_tokens', 0))}  省${w7.get('cache_saved_usd', 0):.0f}")
        lines.append("提示: 双击收起 · 拖动移动 · 右键菜单")
        detail_text.configure(text="\n".join(lines))

    def poll() -> None:
        def worker() -> None:
            data = None
            try:
                raw = urllib.request.urlopen(API_URL, timeout=2.0).read().decode("utf-8")
                data = json.loads(raw)
            except Exception:
                pass
            root.after(0, lambda: apply_data(data))

        threading.Thread(target=worker, daemon=True).start()
        root.after(6000, poll)

    poll()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
