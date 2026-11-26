#!/usr/bin/env python3
"""Windows desktop mini-bar & popup widget for Antigravity CLI (agy-usage).

Pure Python stdlib (`tkinter` + `ctypes` + `urllib` + `subprocess`), zero `pip install` needed.
Includes Per-Monitor DPI awareness, taskbar work-area positioning (`SPI_GETWORKAREA`),
named mutex single-instance guard, dynamic widget sizing, and thread-safe shutdown.
"""

from __future__ import annotations

import json
import locale
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
def _cache_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData/Local"))
        return base / "agy-usage"
    return Path.home() / ".cache" / "agy-usage"


THEME_FILE = _cache_dir() / "ui-theme"
LANG_FILE = _cache_dir() / "ui-lang"
THEMES = {
    "dark": {
        "bg": "#1e293b",
        "fg": "#e2e8f0",
        "muted": "#94a3b8",
        "border": "#38bdf8",
        "btn": "#334155",
        "btn_fg": "#e2e8f0",
        "gem": "#38bdf8",
        "cld": "#a78bfa",
        "sep": "#64748b",
        "ok": "#34d399",
        "warn": "#fbbf24",
        "crit": "#f87171",
        "expired": "#94a3b8",
    },
    "light": {
        "bg": "#fff5f8",
        "fg": "#4a3540",
        "muted": "#745664",
        "border": "#f9a8d4",
        "btn": "#fce7f3",
        "btn_fg": "#9d174d",
        "gem": "#0e7490",
        "cld": "#6d28d9",
        "sep": "#b895a5",
        "ok": "#059669",
        "warn": "#d97706",
        "crit": "#dc2626",
        "expired": "#6b7280",
    },
    "tongtou": {
        "bg": "#F5F0EB",
        "fg": "#2C3E50",
        "muted": "#6B7280",
        "border": "#7BA7A7",
        "btn": "#E8E2DB",
        "btn_fg": "#2C3E50",
        "gem": "#4D7C7C",
        "cld": "#9A7B4F",
        "sep": "#A8A29E",
        "ok": "#059669",
        "warn": "#d97706",
        "crit": "#dc2626",
        "expired": "#78716c",
    },
}


def _windows_system_is_light() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 1
    except Exception:
        return False


def _read_theme_pref() -> str:
    try:
        value = THEME_FILE.read_text(encoding="utf-8").strip()
        if value in ("light", "tongtou", "dark", "system"):
            return value
    except Exception:
        pass
    return "system"


def _write_theme_pref(value: str) -> None:
    try:
        THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
        THEME_FILE.write_text(value, encoding="utf-8")
    except Exception:
        pass


def _resolved_theme(pref: str) -> str:
    if pref in ("light", "tongtou", "dark"):
        return pref
    return "light" if _windows_system_is_light() else "dark"


def _read_lang_pref() -> str:
    try:
        v = LANG_FILE.read_text(encoding="utf-8").strip()
        if v in ("auto", "zh-CN", "zh-TW", "en"):
            return v
    except Exception:
        pass
    return "auto"


def _write_lang_pref(value: str) -> None:
    try:
        LANG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LANG_FILE.write_text(value, encoding="utf-8")
    except Exception:
        pass


def _resolved_lang(pref: str) -> str:
    if pref in ("zh-CN", "zh-TW", "en"):
        return pref
    raw = (os.environ.get("AGY_USAGE_LANG") or "").lower()
    if not raw:
        try:
            loc = locale.getlocale()[0] or ""
            raw = str(loc).lower()
        except Exception:
            raw = ""
    if "tw" in raw or "hk" in raw or "hant" in raw:
        return "zh-TW"
    if raw.startswith("zh") or "chinese" in raw:
        return "zh-CN"
    return "en"


def _wtr(lang: str, cn: str, tw: str, en: str) -> str:
    if lang == "zh-CN":
        return cn
    if lang == "zh-TW":
        return tw
    return en


def _val_color(used_pct: float, expired: bool, pal: Dict[str, str]) -> str:
    if expired:
        return pal["expired"]
    if used_pct >= 80.0:
        return pal["crit"]
    if used_pct >= 55.0:
        return pal["warn"]
    return pal["ok"]

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

    state: Dict[str, Any] = {
        "expanded": False,
        "closing": False,
        "notify_on": False,
        "drag_x": 0,
        "drag_y": 0,
        "theme_pref": _read_theme_pref(),
        "lang_pref": _read_lang_pref(),
        "last_data": None,
    }

    bar_frame = tk.Frame(root, cursor="hand2")
    bar_frame.pack(fill="x", padx=9, pady=5)

    dot_lbl = tk.Label(bar_frame, text="●", fg="#34d399", font=("Segoe UI", 10, "bold"))
    dot_lbl.pack(side="left")

    summary_frame = tk.Frame(bar_frame, cursor="hand2")
    summary_frame.pack(side="left", padx=6)

    g_tag_lbl = tk.Label(summary_frame, text="", font=("Consolas", 9, "bold"), bd=0, padx=0)
    g_val_lbl = tk.Label(summary_frame, text="", font=("Consolas", 9, "bold"), bd=0, padx=0)
    sep_lbl = tk.Label(summary_frame, text="", font=("Consolas", 9), bd=0, padx=0)
    c_tag_lbl = tk.Label(summary_frame, text="", font=("Consolas", 9, "bold"), bd=0, padx=0)
    c_val_lbl = tk.Label(summary_frame, text="", font=("Consolas", 9, "bold"), bd=0, padx=0)
    summary_lbl = tk.Label(summary_frame, text="AGY 连接中...", font=("Consolas", 9, "bold"), bd=0, padx=0)
    summary_lbl.pack(side="left")

    open_btn = tk.Label(bar_frame, text="↗", fg="#38bdf8", font=("Segoe UI", 10, "bold"))
    open_btn.pack(side="right")

    detail_frame = tk.Frame(root)
    detail_text = tk.Text(
        detail_frame,
        width=40,
        height=7,
        relief="flat",
        bd=0,
        highlightthickness=0,
        wrap="none",
        cursor="arrow",
        font=("Consolas", 9),
        state="disabled",
    )
    detail_text.pack(fill="x", padx=10, pady=(2, 6))

    btn_row = tk.Frame(detail_frame)
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

    open_dash_btn = tk.Button(
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
    )
    open_dash_btn.pack(side="left")

    quit_btn = tk.Button(
        btn_row,
        text="退出小工具",
        command=quit_widget,
        relief="flat",
        font=("Microsoft YaHei UI", 8),
        padx=8,
        pady=2,
        cursor="hand2",
    )
    quit_btn.pack(side="right")

    def apply_chrome() -> None:
        pal = THEMES[_resolved_theme(state["theme_pref"])]
        root.configure(bg=pal["bg"], highlightthickness=1, highlightbackground=pal["border"])
        for widget in (bar_frame, summary_frame, detail_frame, btn_row):
            widget.configure(bg=pal["bg"])
        for widget in (dot_lbl, summary_lbl, g_tag_lbl, g_val_lbl, sep_lbl, c_tag_lbl, c_val_lbl, open_btn):
            widget.configure(bg=pal["bg"])
        summary_lbl.configure(fg=pal["fg"])
        open_btn.configure(fg=pal["gem"])
        detail_text.configure(bg=pal["bg"], fg=pal["muted"])
        detail_text.tag_configure("gem", foreground=pal["gem"], font=("Consolas", 9, "bold"))
        detail_text.tag_configure("cld", foreground=pal["cld"], font=("Consolas", 9, "bold"))
        detail_text.tag_configure("ok", foreground=pal["ok"], font=("Consolas", 9, "bold"))
        detail_text.tag_configure("warn", foreground=pal["warn"], font=("Consolas", 9, "bold"))
        detail_text.tag_configure("crit", foreground=pal["crit"], font=("Consolas", 9, "bold"))
        detail_text.tag_configure("expired", foreground=pal["expired"])
        detail_text.tag_configure("muted", foreground=pal["muted"])
        detail_text.tag_configure("fg", foreground=pal["fg"])
        quit_btn.configure(bg=pal["btn"], fg=pal["btn_fg"])
        ctx_menu.configure(bg=pal["bg"], fg=pal["fg"])

    def _set_detail_segments(rows: list) -> None:
        detail_text.configure(state="normal")
        detail_text.delete("1.0", "end")
        max_len = 36
        for idx, segs in enumerate(rows):
            line_len = 0
            for text, tag in segs:
                detail_text.insert("end", text, (tag,) if tag else ())
                line_len += sum(2 if ord(ch) > 127 else 1 for ch in text)
            max_len = max(max_len, line_len)
            if idx < len(rows) - 1:
                detail_text.insert("end", "\n")
        detail_text.configure(width=min(46, max_len + 1), height=max(1, len(rows)), state="disabled")

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

    drag_targets = (bar_frame, summary_frame, dot_lbl, summary_lbl, g_tag_lbl, g_val_lbl, sep_lbl, c_tag_lbl, c_val_lbl)
    for w in drag_targets:
        w.bind("<ButtonPress-1>", start_drag)
        w.bind("<B1-Motion>", on_drag)
        w.bind("<Double-Button-1>", toggle_expand)

    def set_theme_pref(pref: str) -> None:
        state["theme_pref"] = pref
        _write_theme_pref(pref)
        apply_chrome()
        if state.get("last_data") is not None:
            apply_data(state["last_data"])

    def set_lang_pref(pref: str) -> None:
        state["lang_pref"] = pref
        _write_lang_pref(pref)
        lg = _resolved_lang(pref)
        open_dash_btn.configure(text=_wtr(lg, "打开完整监控台", "開啟完整監控台", "Open Web Dashboard"))
        quit_btn.configure(text=_wtr(lg, "退出小工具", "結束小工具", "Quit"))
        apply_data(state.get("last_data"))

    ctx_menu = tk.Menu(root, tearoff=0)
    ctx_menu.add_command(label="Expand / Collapse (双击展开)", command=toggle_expand)
    ctx_menu.add_command(label="Open Web Dashboard (打开监控台)", command=open_web)
    ctx_menu.add_command(label="Toggle 80% Alerts (额度提醒开关)", command=toggle_notifications)
    ctx_menu.add_command(label="Reset Position (重置位置)", command=reset_position)
    ctx_menu.add_separator()
    ctx_menu.add_command(label="Theme · Light / 浅色", command=lambda: set_theme_pref("light"))
    ctx_menu.add_command(label="Theme · Airy / 通透", command=lambda: set_theme_pref("tongtou"))
    ctx_menu.add_command(label="Theme · Dark / 深色", command=lambda: set_theme_pref("dark"))
    ctx_menu.add_command(label="Theme · Auto / 跟随系统", command=lambda: set_theme_pref("system"))
    ctx_menu.add_separator()
    ctx_menu.add_command(label="Language · Auto", command=lambda: set_lang_pref("auto"))
    ctx_menu.add_command(label="Language · 简体中文", command=lambda: set_lang_pref("zh-CN"))
    ctx_menu.add_command(label="Language · 繁體中文", command=lambda: set_lang_pref("zh-TW"))
    ctx_menu.add_command(label="Language · English", command=lambda: set_lang_pref("en"))
    ctx_menu.add_separator()
    ctx_menu.add_command(label="Quit / 退出悬浮小工具", command=quit_widget)

    init_lg = _resolved_lang(state["lang_pref"])
    open_dash_btn.configure(text=_wtr(init_lg, "打开完整监控台", "開啟完整監控台", "Open Web Dashboard"))
    quit_btn.configure(text=_wtr(init_lg, "退出小工具", "結束小工具", "Quit"))
    summary_lbl.configure(text=_wtr(init_lg, "AGY 连接中...", "AGY 連線中...", "AGY Connecting..."))
    apply_chrome()

    def show_menu(evt: Any) -> None:
        ctx_menu.tk_popup(evt.x_root, evt.y_root)

    for w in (root,) + drag_targets:
        w.bind("<Button-3>", show_menu)
    open_btn.bind("<Button-1>", open_web)

    def ascii_bar(pct: float, width: int = 8) -> str:
        pct = max(0.0, min(100.0, pct))
        f = int(round((pct / 100.0) * width))
        return "█" * f + "░" * (width - f)

    def _show_plain_summary(text: str) -> None:
        for w in (g_tag_lbl, g_val_lbl, sep_lbl, c_tag_lbl, c_val_lbl):
            w.pack_forget()
        summary_lbl.configure(text=text)
        summary_lbl.pack(side="left")

    def apply_data(d: Optional[Dict[str, Any]]) -> None:
        if state["closing"]:
            return
        state["last_data"] = d
        pal = THEMES[_resolved_theme(state["theme_pref"])]
        lg = _resolved_lang(state["lang_pref"])
        try:
            if not d:
                dot_lbl.configure(fg=pal["warn"])
                _show_plain_summary(_wtr(lg, "AGY 离线 (双击)", "AGY 離線 (雙擊)", "AGY Offline"))
                _set_detail_segments([[(_wtr(lg, "本地服务未响应，点击下方按钮启动。", "本機服務未回應，點擊下方按鈕啟動。", "Local service offline. Click below to start."), "muted")]])
                clamp_and_place(target_x=root.winfo_x(), target_y=root.winfo_y())
                return

            state["notify_on"] = bool((d.get("notifications") or {}).get("enabled", False))
            q = d.get("quota") or {}
            buckets = q.get("buckets") or []
            rows = []
            if q.get("has_live_quota") and buckets:
                gem_w = next(
                    (b for b in buckets if str(b.get("pool_key", "")).startswith("gemini") and b.get("window_kind") == "weekly"),
                    None,
                )
                cld_w = next(
                    (b for b in buckets if b.get("pool_key") == "claude_gpt" and b.get("window_kind") == "weekly"),
                    None,
                )
                has_g = gem_w is not None and gem_w.get("used_pct") is not None
                has_c = cld_w is not None and cld_w.get("used_pct") is not None

                statuses = [b.get("status") for b in buckets]
                col = pal["crit"] if "critical" in statuses else (pal["warn"] if "warning" in statuses else pal["ok"])
                dot_lbl.configure(fg=col)

                if has_g or has_c:
                    summary_lbl.pack_forget()
                    for w in (g_tag_lbl, g_val_lbl, sep_lbl, c_tag_lbl, c_val_lbl):
                        w.pack_forget()
                    if has_g and gem_w is not None:
                        gu = float(gem_w["used_pct"])
                        g_tag_lbl.configure(text="G ", fg=pal["gem"])
                        g_val_lbl.configure(text=f"{gu:.0f}%", fg=_val_color(gu, bool(gem_w.get("reset_passed")), pal))
                        g_tag_lbl.pack(side="left")
                        g_val_lbl.pack(side="left")
                    if has_g and has_c:
                        sep_lbl.configure(text=" │ ", fg=pal["sep"])
                        sep_lbl.pack(side="left")
                    if has_c and cld_w is not None:
                        cu = float(cld_w["used_pct"])
                        c_tag_lbl.configure(text="C ", fg=pal["cld"])
                        c_val_lbl.configure(text=f"{cu:.0f}%", fg=_val_color(cu, bool(cld_w.get("reset_passed")), pal))
                        c_tag_lbl.pack(side="left")
                        c_val_lbl.pack(side="left")
                else:
                    _show_plain_summary(f"AGY {buckets[0].get('used_pct', 0):.0f}%")

                for b in buckets[:4]:
                    u = float(b.get("used_pct") or 0)
                    exp = bool(b.get("reset_passed"))
                    is_cld = b.get("pool_key") == "claude_gpt"
                    pool = "Claude" if is_cld else "Gemini"
                    win = "5h" if b.get("window_kind") == "five_hour" else _wtr(lg, "周", "週", "Wk")
                    rst = _wtr(lg, "待刷新", "待更新", "Refresh") if exp else (b.get("reset_time_cst") or "-")
                    val_tag = "expired" if exp else ("crit" if u >= 80.0 else ("warn" if u >= 55.0 else "ok"))
                    used_w = _wtr(lg, "已用", "已用", "Used ")
                    rows.append([
                        (f"{pool}{win:<2} ", "cld" if is_cld else "gem"),
                        (f"{ascii_bar(u)} {used_w}{u:5.1f}%", val_tag),
                        (f" ({rst})", "muted"),
                    ])
            else:
                wt = (d.get("windows") or {}).get("today") or {}
                dot_lbl.configure(fg=pal["ok"])
                _show_plain_summary(f"AGY {_wtr(lg, '今日', '今日', 'Today')} {fmt_tok(wt.get('billable_tokens', 0))}")
                rows.append([(_wtr(lg, "等待新开的 Antigravity 会话推送实时额度", "等待新開的 Antigravity 對話推送即時額度", "Waiting for new Antigravity chat to push quota"), "muted")])

            w7 = (d.get("windows") or {}).get("7d") or {}
            ntf_s = _wtr(lg, "开" if state["notify_on"] else "关", "開" if state["notify_on"] else "關", "On" if state["notify_on"] else "Off")
            rows.append([("-" * 38, "muted")])
            rows.append([(f"{_wtr(lg, '近7日有效', '近7日有效', 'Last 7d')}: {fmt_tok(w7.get('billable_tokens', 0))}", "fg")])
            rows.append([(_wtr(lg, f"提醒:{ntf_s} · 双击收起 · 拖动移动 · 右键菜单", f"提醒:{ntf_s} · 雙擊收起 · 拖動移動 · 右鍵選單", f"Alerts:{ntf_s} · Double-click · Drag · Right-click"), "muted")])
            _set_detail_segments(rows)
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
