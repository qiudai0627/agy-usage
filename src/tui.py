#!/usr/bin/env python3
"""ANSI terminal analytics report renderer and live `watch` loop for agy-usage."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, List, Optional

from analytics import build_analytics
from storage import APP_DIR, fmt_tokens

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

    lines.append("")
    s5_vals = [x["billable_tokens"] for x in data["rolling_5h_10m"]]
    h_vals = [h["billable_tokens"] for h in data["hourly_24h"]]
    peak_h = max(data["hourly_24h"], key=lambda x: x["billable_tokens"]) if data["hourly_24h"] else None
    peak_txt = (
        f"峰值 {peak_h['label']} ({fmt_tokens(peak_h['billable_tokens'])}, {peak_h['calls']}次)"
        if peak_h and peak_h["billable_tokens"] > 0
        else "无活跃"
    )
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
