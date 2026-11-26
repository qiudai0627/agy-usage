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
from i18n import resolve_cli_lang  # noqa: E402

STATUS_L10N: Dict[str, Dict[str, Any]] = {
    "zh-CN": {
        "slots": [("g5h", "Gemini5h", "G5h"), ("gw", "Gemini周", "G周"), ("c5h", "Claude5h", "C5h"), ("cw", "Claude周", "C周")],
        "used": "已用",
        "ctx": "上下文",
        "ref_long": "待刷新",
        "ref_short": "待刷",
        "sub": "子:",
        "wait": "agy-usage: 等待状态数据...",
        "narrow": [
            "窗口过窄，完整四桶已用请看网页 (agy-usage)",
            "窗口过窄，完整四桶请看网页 agy-usage",
            "窗口过窄，请看网页 agy-usage",
            "看网页:agy-usage",
            "看网页",
            "网页",
        ],
    },
    "zh-TW": {
        "slots": [("g5h", "Gemini5h", "G5h"), ("gw", "Gemini週", "G週"), ("c5h", "Claude5h", "C5h"), ("cw", "Claude週", "C週")],
        "used": "已用",
        "ctx": "上下文",
        "ref_long": "待更新",
        "ref_short": "待更",
        "sub": "子:",
        "wait": "agy-usage: 等待狀態資料...",
        "narrow": [
            "視窗過窄，完整四格已用請看網頁 (agy-usage)",
            "視窗過窄，完整四格請看網頁 agy-usage",
            "視窗過窄，請看網頁 agy-usage",
            "看網頁:agy-usage",
            "看網頁",
            "網頁",
        ],
    },
    "en": {
        "slots": [("g5h", "Gemini5h", "G5h"), ("gw", "GeminiWk", "GWk"), ("c5h", "Claude5h", "C5h"), ("cw", "ClaudeWk", "CWk")],
        "used": "Used ",
        "ctx": "Context",
        "ref_long": "Refresh",
        "ref_short": "Ref",
        "sub": "Sub:",
        "wait": "agy-usage: waiting for telemetry...",
        "narrow": [
            "Window narrow, see all 4 quotas on Web (agy-usage)",
            "Window narrow, see Web UI (agy-usage)",
            "Narrow: check Web agy-usage",
            "Web:agy-usage",
            "Web UI",
            "Web",
        ],
    },
}

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


def _valid_reset_dt(entry: Any) -> Optional[datetime]:
    if not isinstance(entry, dict):
        return None
    dt = parse_iso_dt(entry.get("reset_time"))
    if dt is None or dt.year <= 1971:
        return None
    return dt


def _merge_freshest_quota(
    new_q: Dict[str, Any],
    prev_q: Dict[str, Any],
    now_dt: Optional[datetime] = None,
    same_conv: bool = False,
) -> Dict[str, Any]:
    """Prevent stale in-memory quota from idle background windows rolling back a newer cycle,
    while immediately honoring both natural expiry and server-side early 100% resets."""
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    merged: Dict[str, Any] = dict(prev_q)

    payload_has_stale_cycle = False
    payload_has_active_cycle = False
    for bid, cand in new_q.items():
        if not isinstance(cand, dict):
            continue
        c_dt = _valid_reset_dt(cand)
        if c_dt is not None and c_dt > now_dt:
            payload_has_active_cycle = True
        old = prev_q.get(bid)
        o_dt = _valid_reset_dt(old) if isinstance(old, dict) else None
        if o_dt is not None and o_dt > now_dt and c_dt is not None and c_dt < o_dt - timedelta(seconds=60):
            payload_has_stale_cycle = True

    for bid, cand in new_q.items():
        if not isinstance(cand, dict):
            continue
        old = prev_q.get(bid)
        if not isinstance(old, dict):
            merged[bid] = cand
            continue
        cand_dt = _valid_reset_dt(cand)
        old_dt = _valid_reset_dt(old)
        cand_rem = extract_remaining_fraction(cand)
        old_rem = extract_remaining_fraction(old)

        # 1. Previous cycle already expired in wall-clock time (or had no timer) -> always accept fresh cand
        if old_dt is None or old_dt <= now_dt:
            merged[bid] = cand
            continue

        # 2. Previous cycle is still in the future, but cand has sentinel 1970 reset_time:
        #    Antigravity sends reset_time="1970-01-01T00:00:00Z" + remaining_fraction=1.0 when a pool
        #    is freshly reset to 100% before any new token starts the rolling countdown.
        if cand_dt is None:
            if (
                cand_rem is not None
                and cand_rem >= 0.9999
                and not payload_has_stale_cycle
                and (same_conv or payload_has_active_cycle)
            ):
                merged[bid] = cand
            else:
                merged[bid] = old
            continue

        # 3. Both cand_dt and old_dt are valid future/active timestamps
        if cand_dt < old_dt - timedelta(seconds=60):
            merged[bid] = old
        elif abs((cand_dt - old_dt).total_seconds()) <= 60:
            if (
                not same_conv
                and cand_rem is not None
                and old_rem is not None
                and cand_rem < 0.9999
                and cand_rem > old_rem + 0.002
            ):
                merged[bid] = old
            else:
                merged[bid] = cand
        else:
            merged[bid] = cand
    return merged


def persist_state(payload: Dict[str, Any]) -> None:
    try:
        ensure_data_dir()
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        state = {k: v for k, v in payload.items() if k != "email"}
        state["captured_at"] = now_iso
        state["source"] = "statusline"
        merged_quota: Optional[Dict[str, Any]] = payload.get("quota") if isinstance(payload.get("quota"), dict) else None

        with file_lock(LIVE_STATE_FILE.with_name(".state.lock"), timeout=0.4) as locked:
            if not locked:
                if os.environ.get("AGY_USAGE_DEBUG"):
                    sys.stderr.write("agy-usage persist warning: state lock timeout, skipped live_state write\n")
            else:
                if merged_quota and LIVE_STATE_FILE.exists():
                    try:
                        prev_state = json.loads(LIVE_STATE_FILE.read_text(encoding="utf-8"))
                        prev_q = prev_state.get("quota") if isinstance(prev_state, dict) else None
                        cur_conv = str(payload.get("conversation_id") or "").strip()
                        prev_conv = str(prev_state.get("conversation_id") or "").strip() if isinstance(prev_state, dict) else ""
                        if isinstance(prev_q, dict) and prev_q:
                            merged_quota = _merge_freshest_quota(
                                merged_quota,
                                prev_q,
                                now_dt=now_dt,
                                same_conv=bool(cur_conv and cur_conv == prev_conv),
                            )
                            state["quota"] = merged_quota
                            payload["quota"] = merged_quota
                    except Exception:
                        pass
                atomic_write_text(LIVE_STATE_FILE, json.dumps(state, ensure_ascii=False))

        if isinstance(merged_quota, dict) and merged_quota:
            model_obj = payload.get("model") or {}
            ctx = payload.get("context_window") or {}
            record_quota_snapshot(
                quota_obj=merged_quota,
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


def extract_four_slots(payload: Dict[str, Any], lang: str = "zh-CN") -> List[Dict[str, Any]]:
    """Return fixed 4 slots in locked order: Gemini 5h, Gemini 周, Claude/GPT 5h, Claude/GPT 周."""
    loc = STATUS_L10N.get(lang, STATUS_L10N["zh-CN"])
    s_lbls = loc["slots"]
    slots_meta = [
        (s_lbls[0][0], s_lbls[0][1], s_lbls[0][2], "gemini", "five_hour"),
        (s_lbls[1][0], s_lbls[1][1], s_lbls[1][2], "gemini", "weekly"),
        (s_lbls[2][0], s_lbls[2][1], s_lbls[2][2], "claude_gpt", "five_hour"),
        (s_lbls[3][0], s_lbls[3][1], s_lbls[3][2], "claude_gpt", "weekly"),
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


def _render_slot(s: Dict[str, Any], tier: int, lang: str = "zh-CN") -> str:
    """Render one bucket at tier 0 (richest) .. tier 4 (tightest), never dropping the bucket."""
    loc = STATUS_L10N.get(lang, STATUS_L10N["zh-CN"])
    used_kw = loc["used"]
    used_tight = used_kw.strip() if lang != "en" else "U:"
    lbl = s["full"] if tier <= 2 else s["short"]
    pool_col = CYAN if s["key"].startswith("g") else MAGENTA
    lbl_s = f"{pool_col}{lbl}{RESET}"
    if s["state"] == "missing":
        return f"{lbl_s} {DIM}—{RESET}" if tier <= 3 else f"{lbl_s}:{DIM}—{RESET}"
    if s["state"] == "expired":
        return f"{lbl_s} {DIM}{loc['ref_long']}{RESET}" if tier <= 2 else f"{lbl_s}:{DIM}{loc['ref_short']}{RESET}"

    u = float(s["used_pct"])
    col = used_color(u)
    if tier == 0:
        bar_s = f"{col}{mini_bar(u, 4)}{RESET} "
        rst = ""
        if s["kind"] == "weekly" and s.get("reset_dt"):
            rst = f" {DIM}{fmt_cst(s['reset_dt'], '%m-%d %H:%M')}{RESET}"
        elif s.get("reset_sec") is not None:
            rst = f" {DIM}{short_countdown(s['reset_sec'])}{RESET}"
        return f"{lbl_s} {bar_s}{col}{used_kw}{_fmt_pct(u)}{RESET}{rst}"
    if tier == 1:
        bar_s = f"{col}{mini_bar(u, 4)}{RESET} "
        return f"{lbl_s} {bar_s}{col}{used_kw}{_fmt_pct(u)}{RESET}"
    if tier == 2:
        return f"{lbl_s} {col}{used_kw}{_fmt_pct(u)}{RESET}"
    if tier == 3:
        return f"{lbl_s} {col}{used_kw}{_fmt_pct(u, tight=True)}{RESET}"
    return f"{lbl_s}{col}{used_tight}{_fmt_pct(u, tight=True)}{RESET}"


def _render_candidate(
    icon: str,
    model_seg: Optional[str],
    ctx_pct: Optional[float],
    ctx_tok: int,
    slots: List[Dict[str, Any]],
    running_subs: int,
    tier: int,
    lang: str = "zh-CN",
) -> str:
    loc = STATUS_L10N.get(lang, STATUS_L10N["zh-CN"])
    sep = f" {DIM}│{RESET} " if tier <= 3 else " "
    parts: List[str] = [icon]
    if model_seg and tier <= 2:
        parts.append(f"{BOLD}{CYAN}{model_seg}{RESET}")

    if ctx_pct is not None:
        cc = ctx_color(ctx_pct)
        if tier == 0:
            tok_s = f" {DIM}{fmt_tokens(ctx_tok)}{RESET}" if ctx_tok > 0 else ""
            parts.append(f"{loc['ctx']} {cc}{mini_bar(ctx_pct, 4)} {ctx_pct:.1f}%{RESET}{tok_s}")
        elif tier <= 2:
            parts.append(f"{loc['ctx']} {cc}{ctx_pct:.0f}%{RESET}")
        elif tier == 3:
            parts.append(f"ctx {cc}{ctx_pct:.0f}%{RESET}")

    g_pair = f"{_render_slot(slots[0], tier, lang)} {_render_slot(slots[1], tier, lang)}"
    c_pair = f"{_render_slot(slots[2], tier, lang)} {_render_slot(slots[3], tier, lang)}"
    parts.append(g_pair)
    parts.append(c_pair)

    if running_subs > 0 and tier <= 2:
        parts.append(f"{MAGENTA}{loc['sub']}{running_subs}{RESET}")

    return sep.join(parts)


def render(payload: Dict[str, Any]) -> str:
    lang = resolve_cli_lang(payload.get("lang"))
    loc = STATUS_L10N.get(lang, STATUS_L10N["zh-CN"])
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

    slots = extract_four_slots(payload, lang=lang)
    subagents = payload.get("subagents") or []
    running_subs = sum(1 for s in subagents if isinstance(s, dict) and s.get("status") == "running")

    for tier in range(5):
        line = _render_candidate(icon, model_seg, ctx_pct, ctx_tok, slots, running_subs, tier, lang=lang)
        if display_width(line) <= budget:
            return line

    # Ultra-narrow fallback: always obey >=16 right margin; clear CYAN hint (no whole-line DIM)
    fallback_budget = budget if budget >= 1 else max(0, width - 16)
    hints = [f"{icon} {CYAN}{txt}{RESET}" for txt in loc["narrow"]] + [icon]
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
            loc = STATUS_L10N.get(resolve_cli_lang(), STATUS_L10N["zh-CN"])
            print(f"{DIM}{loc['wait']}{RESET}")
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
