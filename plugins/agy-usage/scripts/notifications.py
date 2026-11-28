#!/usr/bin/env python3
"""User preferences and deduplicated local OS quota alerts (80% / 95% / fresh-confirmed recovery)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

from storage import (
    NOTIFY_STATE_FILE,
    PREFERENCES_FILE,
    atomic_write_text,
    ensure_data_dir,
    file_lock,
    fmt_cst,
)


def get_preferences() -> Dict[str, Any]:
    """Load user preferences (desktop notifications default to False / toggleable)."""
    defaults: Dict[str, Any] = {"notifications_enabled": False}
    if not PREFERENCES_FILE.exists():
        return defaults
    try:
        raw = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            defaults["notifications_enabled"] = bool(raw.get("notifications_enabled", False))
    except Exception:
        pass
    return defaults


def set_preferences(notifications_enabled: Optional[bool] = None) -> Dict[str, Any]:
    ensure_data_dir()
    with file_lock(PREFERENCES_FILE.with_name(".prefs.lock"), timeout=1.5) as locked:
        if not locked:
            raise TimeoutError("获取 preferences 锁超时，已放弃写入")
        prefs = get_preferences()
        if notifications_enabled is not None:
            prefs["notifications_enabled"] = bool(notifications_enabled)
        prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_text(PREFERENCES_FILE, json.dumps(prefs, ensure_ascii=False, indent=2))
    return prefs


def _dispatch_os_notification(title: str, message: str) -> None:
    """Safely send a native local desktop notification without shell interpolation."""
    if os.environ.get("AGY_USAGE_SUPPRESS_OS_NOTIFY") == "1":
        return
    try:
        if sys.platform == "darwin":
            script = "on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run"
            subprocess.Popen(
                ["osascript", "-e", script, title, message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif os.name == "nt":
            ps_code = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$n = New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon = [System.Drawing.SystemIcons]::Information;"
                "$n.Visible = $true;"
                "$n.ShowBalloonTip(5000, $args[0], $args[1], [System.Windows.Forms.ToolTipIcon]::Info);"
                "Start-Sleep -Seconds 5; $n.Dispose()"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_code, title, message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x00000008 | 0x00000200,
            )
        else:
            subprocess.Popen(
                ["notify-send", title, message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


def evaluate_quota_notifications(
    quota_info: Dict[str, Any],
    now: Optional[datetime] = None,
    dispatch: bool = True,
) -> Dict[str, Any]:
    """Deduplicated 80%/95% alerts & fresh-telemetry-confirmed recovery notifications."""
    ensure_data_dir()
    now_dt = now or datetime.now(timezone.utc)
    prefs = get_preferences()
    enabled = bool(prefs.get("notifications_enabled", False))

    source = str(quota_info.get("source") or "")
    stale_sec = quota_info.get("stale_seconds")
    is_fresh_official = (
        bool(quota_info.get("has_live_quota"))
        and source == "statusline"
        and stale_sec is not None
        and float(stale_sec) <= 600.0
    )

    triggered: List[Dict[str, Any]] = []
    with file_lock(NOTIFY_STATE_FILE.with_name(".notify.lock"), timeout=1.0) as locked:
        state: Dict[str, Any] = {"buckets": {}, "recent_events": []}
        if NOTIFY_STATE_FILE.exists():
            try:
                loaded = json.loads(NOTIFY_STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    if isinstance(loaded.get("buckets"), dict):
                        state["buckets"] = loaded["buckets"]
                    if isinstance(loaded.get("recent_events"), list):
                        state["recent_events"] = loaded["recent_events"]
            except Exception:
                pass

        if locked and quota_info.get("has_live_quota"):
            dirty = False
            b_states: Dict[str, Any] = state["buckets"]
            for b in quota_info.get("buckets") or []:
                bid = str(b.get("id") or "")
                used = b.get("used_pct")
                if not bid or used is None or b.get("disabled"):
                    continue
                used_f = float(used)
                reset_passed = bool(b.get("reset_passed"))
                cycle_key = str(b.get("reset_time") or "rolling")
                prev = b_states.get(bid) if isinstance(b_states.get(bid), dict) else None

                if reset_passed:
                    continue

                if prev is not None and is_fresh_official:
                    prev_cycle = str(prev.get("cycle_key") or "")
                    prev_max = float(prev.get("max_used_pct") or 0.0)
                    recovered_key = f"{cycle_key}:{round(used_f, 1)}"
                    if (
                        prev_max >= 50.0
                        and used_f <= 15.0
                        and (cycle_key != prev_cycle or (prev_max - used_f) >= 40.0)
                        and prev.get("last_recovery_cycle") != cycle_key
                    ):
                        ev = {
                            "ts": now_dt.isoformat(),
                            "ts_cst": fmt_cst(now_dt, "%m-%d %H:%M"),
                            "kind": "recovery",
                            "bucket": bid,
                            "title": f"{b['label']} 已回血恢复",
                            "message": f"最新官方额度确认已恢复至已用 {used_f:.1f}%（重置 {b.get('reset_time_cst') or '-'}）。",
                        }
                        triggered.append(ev)
                        prev = {
                            "cycle_key": cycle_key,
                            "max_used_pct": used_f,
                            "alerted_80": False,
                            "alerted_95": False,
                            "last_recovery_cycle": cycle_key,
                            "recovered_sig": recovered_key,
                        }
                        b_states[bid] = prev
                        dirty = True

                if prev is None or str(prev.get("cycle_key") or "") != cycle_key:
                    prev = {
                        "cycle_key": cycle_key,
                        "max_used_pct": used_f,
                        "alerted_80": False,
                        "alerted_95": False,
                        "last_recovery_cycle": prev.get("last_recovery_cycle") if isinstance(prev, dict) else "",
                    }
                    b_states[bid] = prev
                    dirty = True
                else:
                    if used_f > float(prev.get("max_used_pct") or 0.0):
                        prev["max_used_pct"] = used_f
                        dirty = True

                if used_f >= 95.0 and not prev.get("alerted_95"):
                    prev["alerted_95"] = True
                    prev["alerted_80"] = True
                    dirty = True
                    if is_fresh_official or source == "manual":
                        triggered.append(
                            {
                                "ts": now_dt.isoformat(),
                                "ts_cst": fmt_cst(now_dt, "%m-%d %H:%M"),
                                "kind": "alert_95",
                                "bucket": bid,
                                "title": f"{b['label']} 已用 {used_f:.1f}%（即将耗尽）",
                                "message": f"仅剩 {b.get('remaining_pct', 0):.1f}%，距离重置 {b.get('reset_in_text') or '-'}。",
                            }
                        )
                elif used_f >= 80.0 and not prev.get("alerted_80"):
                    prev["alerted_80"] = True
                    dirty = True
                    if is_fresh_official or source == "manual":
                        triggered.append(
                            {
                                "ts": now_dt.isoformat(),
                                "ts_cst": fmt_cst(now_dt, "%m-%d %H:%M"),
                                "kind": "alert_80",
                                "bucket": bid,
                                "title": f"{b['label']} 已用达 {used_f:.1f}%",
                                "message": f"剩余 {b.get('remaining_pct', 0):.1f}%，距离重置 {b.get('reset_in_text') or '-'}。",
                            }
                        )

            if triggered:
                state["recent_events"] = (triggered + state["recent_events"])[:12]
                dirty = True

            if dirty:
                atomic_write_text(NOTIFY_STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2))

    if enabled and dispatch and triggered:
        for ev in triggered:
            _dispatch_os_notification(ev["title"], ev["message"])

    return {
        "enabled": enabled,
        "triggered": triggered,
        "recent_events": state.get("recent_events", [])[:8],
    }
