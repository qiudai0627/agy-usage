#!/usr/bin/env python3
"""Antigravity CLI (agy) custom status line & real-time quota telemetry collector.

Renders a width-aware, CJK-measured, 4-bucket status line aligned on '已用 %':
- Deduplicates model name/effort when `stack_with_default` is active
- Fixed 4-bucket order: Gemini 5h, Gemini 周, Claude/GPT 5h, Claude/GPT 周
- Reserves right-hand margin (>= 22 cols by default) to avoid TUI toast overlap
- Never silently drops any bucket; missing buckets show `—` placeholder
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from core import (  # noqa: E402
    LIVE_STATE_FILE,
    analyze_quota_buckets,
    atomic_write_text,
    ensure_data_dir,
    evaluate_quota_notifications,
    extract_remaining_fraction,
    file_lock,
    fmt_cst,
    fmt_tokens,
    get_preferences,
    infer_bucket_meta,
    load_agy_settings,
    parse_iso_dt,
    record_quota_snapshot,
)

# ANSI styling
RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

STATE_ICONS = {
    "idle": f"{GREEN}●{RESET}",
    "working": f"{CYAN}◉{RESET}",
    "tool_use": f"{BLUE}⚙{RESET}",
    "reviewing": f"{YELLOW}◎{RESET}",
    "authenticating": f"{YELLOW}●{RESET}",
    "initializing": f"{DIM}◌{RESET}",
    "error": f"{RED}✖{RESET}",
}


def used_color(used_pct: float) -> str:
    if used_pct >= 80.0:
        return RED
    if used_pct >= 55.0:
        return YELLOW
    return GREEN


def ctx_color(used_pct: float) -> str:
    if used_pct >= 80.0:
        return RED
    if used_pct >= 55.0:
        return YELLOW
    return CYAN


def mini_bar(used_pct: float, width: int = 4) -> str:
    clamped = max(0.0, min(100.0, used_pct))
    filled = int(round((clamped / 100.0) * width))
    return "█" * filled + "░" * max(0, width - filled)


def display_width(text: str) -> int:
    """Compute terminal column width after stripping ANSI sequences."""
    clean = ANSI_RE.sub("", text)
    w = 0
    for ch in clean:
        if unicodedata.combining(ch):
            continue
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ("W", "F") else 1
    return w


def short_countdown(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    sec = int(max(0, round(seconds)))
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d > 0:
        return f"{d}d{h}h"
    if h > 0:
        return f"{h}h{m:02d}m"
    return f"{m}m"


def is_stacked_mode(payload: Dict[str, Any]) -> bool:
    if "stack_with_default" in payload:
        return bool(payload["stack_with_default"])
    env_override = os.environ.get("AGY_STATUSLINE_STACK")
    if env_override is not None:
        return env_override.strip().lower() not in ("0", "false", "no")
    settings = load_agy_settings()
    sl = settings.get("statusLine")
    if isinstance(sl, dict) and "stack_with_default" in sl:
        return bool(sl.get("stack_with_default"))
    return True


def compact_model_label(model_obj: Dict[str, Any]) -> str:
    raw = str(model_obj.get("display_name") or model_obj.get("id") or "").strip()
    if not raw:
        return "AGY"
    s = raw.replace("Gemini ", "G").replace("Claude ", "C").replace(" (High)", "-H").replace(" (Medium)", "-M").replace(" (Low)", "-L")
    return s[:18]


def persist_state(payload: Dict[str, Any]) -> None:
    try:
        ensure_data_dir()
        now_iso = datetime.now(timezone.utc).isoformat()
        state = {k: v for k, v in payload.items() if k != "email"}
        state["captured_at"] = now_iso
        state["source"] = "statusline"

        with file_lock(LIVE_STATE_FILE.with_name(".state.lock"), timeout=0.4) as locked:
            if not locked:
                if os.environ.get("AGY_USAGE_DEBUG"):
                    sys.stderr.write("agy-usage persist warning: state lock timeout, skipped live_state write\n")
            else:
                atomic_write_text(LIVE_STATE_FILE, json.dumps(state, ensure_ascii=False))

        quota = payload.get("quota")
        if isinstance(quota, dict) and quota:
            model_obj = payload.get("model") or {}
            ctx = payload.get("context_window") or {}
            record_quota_snapshot(
                quota_obj=quota,
                source="statusline",
                extra={
                    "model": model_obj.get("id") or model_obj.get("display_name") or "",
                    "conversation_id": payload.get("conversation_id") or "",
                    "total_input_tokens": ctx.get("total_input_tokens"),
                    "total_output_tokens": ctx.get("total_output_tokens"),
                },
            )
            if get_preferences().get("notifications_enabled"):
                now_dt = datetime.now(timezone.utc)
                q_info = analyze_quota_buckets(state, [], [], now_dt)
                evaluate_quota_notifications(q_info, now=now_dt, dispatch=True)
    except Exception as exc:
        if os.environ.get("AGY_USAGE_DEBUG"):
            sys.stderr.write(f"agy-usage persist warning: {exc}\n")


def extract_four_slots(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return fixed 4 slots in locked order: Gemini 5h, Gemini 周, Claude/GPT 5h, Claude/GPT 周."""
    slots_meta = [
        ("g5h", "Gemini5h", "G5h", "gemini", "five_hour"),
        ("gw", "Gemini周", "G周", "gemini", "weekly"),
        ("c5h", "Claude5h", "C5h", "claude_gpt", "five_hour"),
        ("cw", "Claude周", "C周", "claude_gpt", "weekly"),
    ]
    quota = payload.get("quota") if isinstance(payload.get("quota"), dict) else {}
    now = datetime.now(timezone.utc)

    matched: Dict[str, Dict[str, Any]] = {}
    for bid, raw in (quota or {}).items():
        if not isinstance(raw, dict) or raw.get("disabled"):
            continue
        rf = extract_remaining_fraction(raw)
        reset_dt = parse_iso_dt(raw.get("reset_time"))
        reset_sec = raw.get("reset_in_seconds")
        if reset_dt is not None:
            reset_sec = (reset_dt - now).total_seconds()
        elif reset_sec is not None:
            reset_sec = float(reset_sec)
            reset_dt = now + timedelta(seconds=max(0.0, reset_sec))

        _, kind, _, pool_key, _ = infer_bucket_meta(bid, reset_sec)
        pool_fam = "claude_gpt" if pool_key == "claude_gpt" else ("gemini" if pool_key.startswith("gemini") else "other")
        slot_key = None
        if pool_fam == "gemini" and kind == "five_hour":
            slot_key = "g5h"
        elif pool_fam == "gemini" and kind == "weekly":
            slot_key = "gw"
        elif pool_fam == "claude_gpt" and kind == "five_hour":
            slot_key = "c5h"
        elif pool_fam == "claude_gpt" and kind == "weekly":
            slot_key = "cw"

        if slot_key and slot_key not in matched:
            expired = (reset_dt is not None and reset_dt <= now) or (reset_sec is not None and reset_sec <= 0)
            used_pct = max(0.0, min(100.0, (1.0 - rf) * 100.0)) if rf is not None else None
            matched[slot_key] = {
                "present": rf is not None,
                "used_pct": used_pct,
                "expired": expired,
                "reset_dt": reset_dt,
                "reset_sec": max(0.0, reset_sec) if reset_sec is not None else None,
            }

    out: List[Dict[str, Any]] = []
    for key, full_lbl, short_lbl, _, kind in slots_meta:
        info = matched.get(key)
        if not info or not info.get("present") or info.get("used_pct") is None:
            out.append({"key": key, "full": full_lbl, "short": short_lbl, "kind": kind, "state": "missing"})
        elif info["expired"]:
            out.append(
                {
                    "key": key,
                    "full": full_lbl,
                    "short": short_lbl,
                    "kind": kind,
                    "state": "expired",
                    "used_pct": info["used_pct"],
                }
            )
        else:
            out.append(
                {
                    "key": key,
                    "full": full_lbl,
                    "short": short_lbl,
                    "kind": kind,
                    "state": "ok",
                    "used_pct": info["used_pct"],
                    "reset_dt": info["reset_dt"],
                    "reset_sec": info["reset_sec"],
                }
            )
    return out


def _fmt_pct(u: float, tight: bool = False) -> str:
    r = round(u, 1)
    if tight:
        return f"{round(u):.0f}%" if r >= 10.0 or r == 0.0 else f"{r:.1f}%"
    return f"{r:.1f}%"


def _render_slot(s: Dict[str, Any], tier: int) -> str:
    """Render one bucket at tier 0 (richest) .. tier 4 (tightest), never dropping the bucket."""
    lbl = s["full"] if tier <= 2 else s["short"]
    pool_col = CYAN if s["key"].startswith("g") else MAGENTA
    lbl_s = f"{pool_col}{lbl}{RESET}"
    if s["state"] == "missing":
        return f"{lbl_s} {DIM}—{RESET}" if tier <= 3 else f"{lbl_s}:{DIM}—{RESET}"
    if s["state"] == "expired":
        return f"{lbl_s} {DIM}待刷新{RESET}" if tier <= 2 else f"{lbl_s}:{DIM}待刷{RESET}"

    u = float(s["used_pct"])
    col = used_color(u)
    if tier == 0:
        bar_s = f"{col}{mini_bar(u, 4)}{RESET} "
        rst = ""
        if s["kind"] == "weekly" and s.get("reset_dt"):
            rst = f" {DIM}{fmt_cst(s['reset_dt'], '%m-%d %H:%M')}{RESET}"
        elif s.get("reset_sec") is not None:
            rst = f" {DIM}{short_countdown(s['reset_sec'])}{RESET}"
        return f"{lbl_s} {bar_s}{col}已用{_fmt_pct(u)}{RESET}{rst}"
    if tier == 1:
        bar_s = f"{col}{mini_bar(u, 4)}{RESET} "
        return f"{lbl_s} {bar_s}{col}已用{_fmt_pct(u)}{RESET}"
    if tier == 2:
        return f"{lbl_s} {col}已用{_fmt_pct(u)}{RESET}"
    if tier == 3:
        return f"{lbl_s} {col}已用{_fmt_pct(u, tight=True)}{RESET}"
    return f"{lbl_s}{col}已用{_fmt_pct(u, tight=True)}{RESET}"


def _render_candidate(
    icon: str,
    model_seg: Optional[str],
    ctx_pct: Optional[float],
    ctx_tok: int,
    slots: List[Dict[str, Any]],
    running_subs: int,
    tier: int,
) -> str:
    sep = f" {DIM}│{RESET} " if tier <= 3 else " "
    parts: List[str] = [icon]
    if model_seg and tier <= 2:
        parts.append(f"{BOLD}{CYAN}{model_seg}{RESET}")

    if ctx_pct is not None:
        cc = ctx_color(ctx_pct)
        if tier == 0:
            tok_s = f" {DIM}{fmt_tokens(ctx_tok)}{RESET}" if ctx_tok > 0 else ""
            parts.append(f"上下文 {cc}{mini_bar(ctx_pct, 4)} {ctx_pct:.1f}%{RESET}{tok_s}")
        elif tier <= 2:
            parts.append(f"上下文 {cc}{ctx_pct:.0f}%{RESET}")
        elif tier == 3:
            parts.append(f"ctx {cc}{ctx_pct:.0f}%{RESET}")

    g_pair = f"{_render_slot(slots[0], tier)} {_render_slot(slots[1], tier)}"
    c_pair = f"{_render_slot(slots[2], tier)} {_render_slot(slots[3], tier)}"
    parts.append(g_pair)
    parts.append(c_pair)

    if running_subs > 0 and tier <= 2:
        parts.append(f"{MAGENTA}子:{running_subs}{RESET}")

    return sep.join(parts)


def render(payload: Dict[str, Any]) -> str:
    width = int(payload.get("terminal_width") or 120)
    right_margin = max(16, int(os.environ.get("AGY_STATUSLINE_RIGHT_MARGIN", "22")))
    budget = max(0, width - right_margin)

    state = str(payload.get("agent_state") or "idle").lower()
    icon = STATE_ICONS.get(state, f"{DIM}•{RESET}")

    stacked = is_stacked_mode(payload)
    model_seg = None if stacked else compact_model_label(payload.get("model") or {})

    ctx = payload.get("context_window") or {}
    ctx_pct = float(ctx["used_percentage"]) if ctx.get("used_percentage") is not None else None
    cur_u = ctx.get("current_usage") or {}
    ctx_tok = int(cur_u.get("input_tokens") or 0) + int(cur_u.get("cache_read_input_tokens") or 0)

    slots = extract_four_slots(payload)
    subagents = payload.get("subagents") or []
    running_subs = sum(1 for s in subagents if isinstance(s, dict) and s.get("status") == "running")

    for tier in range(5):
        line = _render_candidate(icon, model_seg, ctx_pct, ctx_tok, slots, running_subs, tier)
        if display_width(line) <= budget:
            return line

    # Ultra-narrow fallback: always obey >=16 right margin; clear CYAN hint (no whole-line DIM)
    fallback_budget = budget if budget >= 1 else max(0, width - 16)
    hints = [
        f"{icon} {CYAN}窗口过窄，完整四桶已用请看网页 (agy-usage){RESET}",
        f"{icon} {CYAN}窗口过窄，完整四桶请看网页 agy-usage{RESET}",
        f"{icon} {CYAN}窗口过窄，请看网页 agy-usage{RESET}",
        f"{icon} {CYAN}看网页:agy-usage{RESET}",
        f"{icon} {CYAN}看网页{RESET}",
        f"{icon} {CYAN}网页{RESET}",
        icon,
    ]
    for cand in hints:
        if display_width(cand) <= fallback_budget:
            return cand
    return ""


def main() -> int:
    try:
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        raw = sys.stdin.read()
        if not raw.strip():
            print(f"{DIM}agy-usage: 等待状态数据...{RESET}")
            return 0
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 0
        persist_state(payload)
        print(render(payload))
    except Exception as exc:
        if os.environ.get("AGY_USAGE_DEBUG"):
            sys.stderr.write(f"agy-usage render warning: {exc}\n")
        print(f"{DIM}agy-usage{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
