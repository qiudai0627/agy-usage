#!/usr/bin/env python3
"""Antigravity CLI (agy) custom status line & real-time quota telemetry collector.

Configured via:
  /statusline ~/agy-usage/statusline.py
or:
  agy-usage install-statusline [--stack]

Reads the official Antigravity statusLine JSON payload from stdin, persists
live state & quota snapshots for `agy-usage`, and renders a clean, readable
Chinese-labeled ANSI status line.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from core import (  # noqa: E402
    LIVE_STATE_FILE,
    ensure_data_dir,
    extract_remaining_fraction,
    fmt_cst,
    fmt_duration,
    fmt_tokens,
    infer_bucket_meta,
    parse_iso_dt,
    record_quota_snapshot,
)

# ANSI colors
RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"

STATE_MAP = {
    "idle": (f"{GREEN}●{RESET}", "就绪"),
    "working": (f"{CYAN}◉{RESET}", "思考中"),
    "tool_use": (f"{BLUE}⚙{RESET}", "执行工具"),
    "reviewing": (f"{YELLOW}◎{RESET}", "待确认"),
    "authenticating": (f"{YELLOW}🔑{RESET}", "认证中"),
    "initializing": (f"{DIM}◌{RESET}", "初始化"),
    "error": (f"{RED}✖{RESET}", "异常"),
}


def pct_color(rem_pct: float) -> str:
    if rem_pct <= 15:
        return RED
    if rem_pct <= 35:
        return YELLOW
    return GREEN


def used_color(used_pct: float) -> str:
    if used_pct >= 80:
        return RED
    if used_pct >= 55:
        return YELLOW
    return CYAN


def mini_bar(pct: float, width: int = 6) -> str:
    pct = max(0.0, min(100.0, pct))
    filled = int(round((pct / 100.0) * width))
    return "█" * filled + "░" * (width - filled)


def persist_state(payload: Dict[str, Any]) -> None:
    try:
        ensure_data_dir()
        now_iso = datetime.now(timezone.utc).isoformat()
        state = dict(payload)
        state["captured_at"] = now_iso
        state["source"] = "statusline"

        tmp = LIVE_STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, LIVE_STATE_FILE)

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
    except Exception:
        pass


def format_quota_segments(payload: Dict[str, Any], compact: bool) -> List[str]:
    quota = payload.get("quota")
    if not isinstance(quota, dict) or not quota:
        return [f"{DIM}限额 同步中{RESET}"]

    now = datetime.now(timezone.utc)
    active_model = ((payload.get("model") or {}).get("display_name") or "").lower()
    want_claude = "claude" in active_model or "gpt" in active_model

    parsed: List[Tuple[int, str, str, float, Optional[datetime], Optional[float]]] = []
    for bid, raw in quota.items():
        if not isinstance(raw, dict) or raw.get("disabled"):
            continue
        rf = extract_remaining_fraction(raw)
        if rf is None:
            continue
        reset_dt = parse_iso_dt(raw.get("reset_time"))
        reset_sec = raw.get("reset_in_seconds")
        if reset_dt is not None:
            reset_sec = max(0.0, (reset_dt - now).total_seconds())
        elif reset_sec is not None:
            reset_dt = now + (datetime.fromtimestamp(float(reset_sec), tz=timezone.utc) - datetime.fromtimestamp(0, tz=timezone.utc))

        label, kind, _, pool_key, _ = infer_bucket_meta(bid, reset_sec)
        rem_pct = rf * 100.0

        # Prioritize active model group + weekly/5h
        matches_active = (want_claude and pool_key == "claude_gpt") or (
            not want_claude and pool_key != "claude_gpt"
        )
        prio = (0 if matches_active else 10) + (0 if kind == "weekly" else 1 if kind == "five_hour" else 2)
        pool_prefix = "Claude" if pool_key == "claude_gpt" else "Gemini"
        win_tag = "周" if kind == "weekly" else ("5h" if kind == "five_hour" else "")
        short_tag = f"{pool_prefix}{win_tag}" if win_tag else label
        parsed.append((prio, short_tag, kind, rem_pct, reset_dt, reset_sec))

    parsed.sort(key=lambda x: x[0])
    segs: List[str] = []
    max_items = 2 if compact else 3
    for _, tag, kind, rem_pct, reset_dt, reset_sec in parsed[:max_items]:
        used_pct = max(0.0, 100.0 - rem_pct)
        col = pct_color(rem_pct)
        if compact:
            segs.append(f"{tag} {col}剩{rem_pct:.0f}%{RESET}")
        else:
            bar = mini_bar(rem_pct, 5)
            reset_hint = ""
            if kind == "weekly" and reset_dt is not None:
                reset_hint = f" {DIM}重置{fmt_cst(reset_dt, '%m-%d %H:%M')}{RESET}"
            elif reset_sec is not None:
                reset_hint = f" {DIM}({fmt_duration(reset_sec)}){RESET}"
            segs.append(f"{tag} {col}{bar} 剩{rem_pct:.1f}%{RESET}{DIM}(已用{used_pct:.1f}%){RESET}{reset_hint}")
    return segs


def render(payload: Dict[str, Any]) -> str:
    width = int(payload.get("terminal_width") or 120)
    compact = width < 105

    state = str(payload.get("agent_state") or "idle").lower()
    icon, state_zh = STATE_MAP.get(state, (f"{DIM}•{RESET}", state))

    model_obj = payload.get("model") or {}
    model_name = model_obj.get("display_name") or model_obj.get("id") or "未选模型"
    if compact:
        model_name = model_name.replace("Gemini ", "G").replace("Claude ", "C")

    parts: List[str] = [f"{icon} {state_zh}" if not compact else icon, f"{BOLD}{CYAN}{model_name}{RESET}"]

    # Context window
    ctx = payload.get("context_window") or {}
    used_pct = ctx.get("used_percentage")
    if used_pct is not None:
        u = float(used_pct)
        col = used_color(u)
        cur = ctx.get("current_usage") or {}
        cur_in = int(cur.get("input_tokens") or 0) + int(cur.get("cache_read_input_tokens") or 0)
        tok_hint = f" {fmt_tokens(cur_in)}" if cur_in > 0 else ""
        if compact:
            parts.append(f"上下文 {col}{u:.0f}%{RESET}")
        else:
            parts.append(f"上下文 {col}{mini_bar(u, 5)} {u:.1f}%{RESET}{DIM}{tok_hint}{RESET}")

    # Quota buckets
    parts.extend(format_quota_segments(payload, compact))

    # Optional subagents / cost
    subagents = payload.get("subagents") or []
    running_subs = sum(1 for s in subagents if isinstance(s, dict) and s.get("status") == "running")
    if running_subs > 0:
        parts.append(f"{MAGENTA}子代理:{running_subs}{RESET}")

    cost = payload.get("cost") or {}
    if not compact and cost.get("total_usd") is not None:
        parts.append(f"{DIM}≈${float(cost['total_usd']):.2f}{RESET}")

    sep = f" {DIM}│{RESET} "
    return sep.join(parts)


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
    except Exception:
        # Never exit non-zero so agy never disables the statusline
        print(f"{DIM}agy-usage{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
