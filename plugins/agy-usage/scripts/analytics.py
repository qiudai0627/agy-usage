#!/usr/bin/env python3
"""Multi-window token aggregation, 7x24 heatmap, week-over-week comparison, session drill-down & CSV export."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone, tzinfo
import io
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from notifications import evaluate_quota_notifications
from quota import analyze_quota_buckets, load_live_state, load_quota_snapshots
from storage import (
    APP_DIR,
    POOL_LABELS,
    _discover_agy_dirs,
    classify_model_pool,
    fmt_cst,
    fmt_tokens,
    get_local_tz,
    get_tz_label,
    parse_iso_dt,
)
from transcripts import (
    _parse_single_transcript,
    load_agy_settings,
    load_conversation_metadata,
    load_transcript_events,
)


def summarize_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    calls = len(events)
    in_tok = sum(e["input_tokens"] for e in events)
    cache_tok = sum(e["cache_read_tokens"] for e in events)
    out_tok = sum(e["output_tokens"] for e in events)
    total_prompt = in_tok + cache_tok
    total_tok = total_prompt + out_tok
    billable = in_tok + out_tok
    cost = sum(e["est_cost_usd"] for e in events)
    saved = sum(e["cache_saved_usd"] for e in events)
    tools = sum(e["tool_count"] for e in events)
    cache_hit_pct = round((cache_tok / total_prompt) * 100.0, 1) if total_prompt > 0 else 0.0
    convs = len({e["conversation_id"] for e in events})
    uncached_cost = cost + saved
    saved_pct = round((saved / uncached_cost) * 100.0, 1) if uncached_cost > 0 else 0.0
    return {
        "calls": calls,
        "conversations": convs,
        "input_tokens": in_tok,
        "cache_read_tokens": cache_tok,
        "output_tokens": out_tok,
        "total_tokens": total_tok,
        "billable_tokens": billable,
        "cache_hit_pct": cache_hit_pct,
        "est_cost_usd": round(cost, 4),
        "cache_saved_usd": round(saved, 4),
        "cache_saved_pct": saved_pct,
        "tool_calls": tools,
    }


def compute_week_over_week(
    events: List[Dict[str, Any]],
    now: datetime,
    tz: tzinfo,
) -> Dict[str, Any]:
    """Same-timezone, same-elapsed-progress natural week comparison (本周 vs 上周同进度)."""
    now_local = now.astimezone(tz)
    this_monday_local = (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    this_monday_utc = this_monday_local.astimezone(timezone.utc)
    elapsed = now - this_monday_utc
    elapsed_hours = round(max(0.0, elapsed.total_seconds() / 3600.0), 2)

    last_monday_local = this_monday_local - timedelta(days=7)
    last_monday_utc = last_monday_local.astimezone(timezone.utc)
    last_same_point_utc = last_monday_utc + elapsed

    cur_evs = [e for e in events if this_monday_utc <= e["ts"] <= now]
    prev_evs = [e for e in events if last_monday_utc <= e["ts"] <= last_same_point_utc]
    cur_sum = summarize_events(cur_evs)
    prev_sum = summarize_events(prev_evs)

    earliest_ts = events[0]["ts"] if events else None
    has_prior_coverage = earliest_ts is not None and earliest_ts <= last_same_point_utc and earliest_ts < this_monday_utc

    if elapsed_hours < 2.0:
        return {
            "comparable": False,
            "reason": "本周刚开始不足 2 小时，暂不计算同进度环比",
            "badge_text": "环比待累积",
            "elapsed_hours": elapsed_hours,
            "current": cur_sum,
            "previous": prev_sum,
            "delta_pct": None,
        }

    if not has_prior_coverage or prev_sum["billable_tokens"] <= 0:
        return {
            "comparable": False,
            "reason": "上周同进度缺少本地历史样本，暂不可比",
            "badge_text": "较上周: 暂不可比",
            "elapsed_hours": elapsed_hours,
            "current": cur_sum,
            "previous": prev_sum,
            "delta_pct": None,
        }

    delta_pct = round(
        ((cur_sum["billable_tokens"] - prev_sum["billable_tokens"]) / float(prev_sum["billable_tokens"])) * 100.0,
        1,
    )
    sign = "+" if delta_pct > 0 else ""
    return {
        "comparable": True,
        "reason": f"自然周同进度对比（周一 00:00 起 {elapsed_hours:.1f}h，非配额重置周期）",
        "badge_text": f"同进度较上周 {sign}{delta_pct:.1f}%",
        "elapsed_hours": elapsed_hours,
        "current": cur_sum,
        "previous": prev_sum,
        "delta_pct": delta_pct,
    }


def build_insights(
    quota_info: Dict[str, Any],
    windows_summary: Dict[str, Any],
    by_pool: List[Dict[str, Any]],
    burn_5h: Dict[str, Any],
    selected_summary: Dict[str, Any],
) -> List[Dict[str, str]]:
    insights: List[Dict[str, str]] = []

    for b in quota_info.get("buckets") or []:
        if b["status"] == "critical":
            insights.append(
                {
                    "level": "crit",
                    "title": f"{b['label']} 已用 {b['used_pct']:.1f}%",
                    "detail": f"仅剩 {b['remaining_pct']:.1f}%，距离重置还剩 {b['reset_in_text']}，请留意重任务节奏。",
                }
            )
        elif b["status"] == "warning":
            ratio_txt = f"（配速 {b['pacing_ratio']}x）" if b.get("pacing_ratio") else ""
            insights.append(
                {
                    "level": "warn",
                    "title": f"{b['label']} 已用 {b['used_pct']:.1f}%{ratio_txt}",
                    "detail": f"剩 {b['remaining_pct']:.1f}%，按当前速率重置前预计剩 {b.get('projected_rem_at_reset', 0):.1f}%。",
                }
            )

    if selected_summary["cache_read_tokens"] > 0:
        hit = selected_summary["cache_hit_pct"]
        lvl = "ok" if hit >= 85 else ("warn" if hit < 65 else "info")
        insights.append(
            {
                "level": lvl,
                "title": f"缓存命中率 {hit}% · 节省约 ${selected_summary['cache_saved_usd']:.2f}",
                "detail": f"累计命中 {fmt_tokens(selected_summary['cache_read_tokens'])} tokens，降低了约 {selected_summary['cache_saved_pct']}% 的输入成本。",
            }
        )

    claude_pool = next((p for p in by_pool if p["pool"] == "claude_gpt"), None)
    if claude_pool and claude_pool["share_billable_pct"] >= 30:
        insights.append(
            {
                "level": "info",
                "title": f"Claude/GPT 池占有效用量 {claude_pool['share_billable_pct']}%",
                "detail": f"共 {claude_pool['calls']} 次调用（估算 ${claude_pool['est_cost_usd']:.2f}），与 Gemini 限额池分离统计。",
            }
        )

    if burn_5h["calls_per_hour"] >= 40:
        insights.append(
            {
                "level": "info",
                "title": f"近 5h 高频作业：{burn_5h['calls_per_hour']} 次/h",
                "detail": f"有效消耗速率 {fmt_tokens(burn_5h['billable_tokens_per_hour'])}/h，建议关注 5h 滚动窗口。",
            }
        )

    return insights[:4]


def build_analytics(window: str = "7d", *, dispatch_notifications: bool = True) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    local_tz = get_local_tz()
    tz_label = get_tz_label()
    now_cst = now.astimezone(local_tz)

    settings = load_agy_settings()
    conv_meta = load_conversation_metadata()
    events = load_transcript_events()
    live_state = load_live_state()
    snapshots = load_quota_snapshots()

    start_5h = now - timedelta(hours=5)
    start_24h = now - timedelta(hours=24)
    start_today_cst = now_cst.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    monday_cst = (now_cst - timedelta(days=now_cst.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).astimezone(timezone.utc)
    start_7d = now - timedelta(days=7)
    start_30d = now - timedelta(days=30)

    win_map = {
        "5h": start_5h,
        "today": start_today_cst,
        "24h": start_24h,
        "week": monday_cst,
        "7d": start_7d,
        "30d": start_30d,
        "all": datetime(1970, 1, 1, tzinfo=timezone.utc),
    }
    selected_start = win_map.get(window, start_7d)
    selected_events = [e for e in events if e["ts"] >= selected_start]
    selected_summary = summarize_events(selected_events)

    windows_summary = {
        "5h": summarize_events([e for e in events if e["ts"] >= start_5h]),
        "today": summarize_events([e for e in events if e["ts"] >= start_today_cst]),
        "24h": summarize_events([e for e in events if e["ts"] >= start_24h]),
        "calendar_week": summarize_events([e for e in events if e["ts"] >= monday_cst]),
        "7d": summarize_events([e for e in events if e["ts"] >= start_7d]),
        "all": summarize_events(events),
    }

    ev_5h = [e for e in events if e["ts"] >= start_5h]
    active_span_5h = 5.0
    if len(ev_5h) >= 2:
        span_h = (ev_5h[-1]["ts"] - ev_5h[0]["ts"]).total_seconds() / 3600.0
        active_span_5h = max(0.25, min(5.0, span_h))
    burn_5h = {
        "calls_per_hour": round(len(ev_5h) / active_span_5h, 1) if ev_5h else 0.0,
        "billable_tokens_per_hour": round(sum(e["billable_tokens"] for e in ev_5h) / active_span_5h, 0)
        if ev_5h
        else 0.0,
        "total_tokens_per_hour": round(sum(e["total_tokens"] for e in ev_5h) / active_span_5h, 0)
        if ev_5h
        else 0.0,
        "est_cost_per_hour": round(sum(e["est_cost_usd"] for e in ev_5h) / active_span_5h, 4)
        if ev_5h
        else 0.0,
        "active_span_hours": round(active_span_5h, 2),
    }

    slot_minute = (now_cst.minute // 10) * 10
    end_slot_cst = now_cst.replace(minute=slot_minute, second=0, microsecond=0)
    start_slot_cst = end_slot_cst - timedelta(minutes=290)
    rolling_5h_map: Dict[str, Dict[str, Any]] = {}
    rolling_5h_keys: List[str] = []
    for i in range(30):
        s_dt = start_slot_cst + timedelta(minutes=10 * i)
        k = s_dt.strftime("%Y-%m-%d %H:%M")
        rolling_5h_keys.append(k)
        rolling_5h_map[k] = {
            "slot": k,
            "label": s_dt.strftime("%H:%M"),
            "calls": 0,
            "input_tokens": 0,
            "cache_read_tokens": 0,
            "output_tokens": 0,
            "billable_tokens": 0,
            "total_tokens": 0,
            "est_cost_usd": 0.0,
            "gemini_pro": 0,
            "gemini_flash": 0,
            "claude_gpt": 0,
            "other": 0,
        }
    for e in ev_5h:
        dt_c = e["ts"].astimezone(local_tz)
        k = dt_c.replace(minute=(dt_c.minute // 10) * 10, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M")
        if k in rolling_5h_map:
            b = rolling_5h_map[k]
            b["calls"] += 1
            b["input_tokens"] += e["input_tokens"]
            b["cache_read_tokens"] += e["cache_read_tokens"]
            b["output_tokens"] += e["output_tokens"]
            b["billable_tokens"] += e["billable_tokens"]
            b["total_tokens"] += e["total_tokens"]
            b["est_cost_usd"] = round(b["est_cost_usd"] + e["est_cost_usd"], 4)
            b[e["pool"]] += e["billable_tokens"]
    rolling_5h_10m = [rolling_5h_map[k] for k in rolling_5h_keys]

    by_model_raw: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_pool_raw: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    tool_counter: Counter = Counter()
    for e in selected_events:
        by_model_raw[e["model"]].append(e)
        by_pool_raw[e["pool"]].append(e)
        for tn in e["tool_names"]:
            tool_counter[tn] += 1

    total_sel_billable = max(1, sum(e["billable_tokens"] for e in selected_events))
    total_sel_total = max(1, sum(e["total_tokens"] for e in selected_events))
    total_sel_cost = max(0.0001, sum(e["est_cost_usd"] for e in selected_events))

    by_model = []
    for m, evs in by_model_raw.items():
        s = summarize_events(evs)
        s["model"] = m
        s["pool"] = classify_model_pool(m)
        s["pool_label"] = POOL_LABELS.get(s["pool"], s["pool"])
        s["share_billable_pct"] = round((s["billable_tokens"] / total_sel_billable) * 100.0, 1)
        s["share_total_pct"] = round((s["total_tokens"] / total_sel_total) * 100.0, 1)
        s["share_cost_pct"] = round((s["est_cost_usd"] / total_sel_cost) * 100.0, 1)
        by_model.append(s)
    by_model.sort(key=lambda x: -x["billable_tokens"])

    by_pool = []
    for pool_key, evs in by_pool_raw.items():
        s = summarize_events(evs)
        s["pool"] = pool_key
        s["label"] = POOL_LABELS.get(pool_key, pool_key)
        s["share_billable_pct"] = round((s["billable_tokens"] / total_sel_billable) * 100.0, 1)
        s["share_total_pct"] = round((s["total_tokens"] / total_sel_total) * 100.0, 1)
        s["share_cost_pct"] = round((s["est_cost_usd"] / total_sel_cost) * 100.0, 1)
        by_pool.append(s)
    by_pool.sort(key=lambda x: -x["billable_tokens"])

    total_tools = sum(tool_counter.values()) or 1
    top_tools = [
        {"name": name, "count": cnt, "share_pct": round((cnt / total_tools) * 100.0, 1)}
        for name, cnt in tool_counter.most_common(10)
    ]

    hourly_buckets: Dict[str, Dict[str, Any]] = {}
    base_hour_cst = now_cst.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    hourly_keys: List[str] = []
    for i in range(24):
        h_dt = base_hour_cst + timedelta(hours=i)
        k = h_dt.strftime("%Y-%m-%d %H:00")
        hourly_keys.append(k)
        hourly_buckets[k] = {
            "hour": k,
            "label": h_dt.strftime("%H:00"),
            "calls": 0,
            "input_tokens": 0,
            "cache_read_tokens": 0,
            "output_tokens": 0,
            "billable_tokens": 0,
            "total_tokens": 0,
            "est_cost_usd": 0.0,
            "gemini_pro": 0,
            "gemini_flash": 0,
            "claude_gpt": 0,
            "other": 0,
        }
    for e in events:
        if e["ts"] < start_24h - timedelta(hours=1):
            continue
        k = e["ts"].astimezone(local_tz).strftime("%Y-%m-%d %H:00")
        if k in hourly_buckets:
            b = hourly_buckets[k]
            b["calls"] += 1
            b["input_tokens"] += e["input_tokens"]
            b["cache_read_tokens"] += e["cache_read_tokens"]
            b["output_tokens"] += e["output_tokens"]
            b["billable_tokens"] += e["billable_tokens"]
            b["total_tokens"] += e["total_tokens"]
            b["est_cost_usd"] = round(b["est_cost_usd"] + e["est_cost_usd"], 4)
            b[e["pool"]] += e["billable_tokens"]
    hourly_24h = [hourly_buckets[k] for k in hourly_keys]

    daily_buckets: Dict[str, Dict[str, Any]] = {}
    base_day_cst = now_cst.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6)
    daily_keys: List[str] = []
    weekdays_zh = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    heatmap_grid: Dict[str, List[Dict[str, Any]]] = {}

    for i in range(7):
        d_dt = base_day_cst + timedelta(days=i)
        k = d_dt.strftime("%Y-%m-%d")
        daily_keys.append(k)
        daily_buckets[k] = {
            "date": k,
            "label": f"{d_dt.strftime('%m-%d')} {weekdays_zh[d_dt.weekday()]}",
            "short_label": d_dt.strftime("%m-%d"),
            "calls": 0,
            "input_tokens": 0,
            "cache_read_tokens": 0,
            "output_tokens": 0,
            "billable_tokens": 0,
            "total_tokens": 0,
            "est_cost_usd": 0.0,
            "gemini_pro": 0,
            "gemini_flash": 0,
            "claude_gpt": 0,
            "other": 0,
        }
        heatmap_grid[k] = [
            {"hour": h, "calls": 0, "billable_tokens": 0, "est_cost_usd": 0.0}
            for h in range(24)
        ]

    for e in events:
        dt_c = e["ts"].astimezone(local_tz)
        k = dt_c.strftime("%Y-%m-%d")
        if k in daily_buckets:
            b = daily_buckets[k]
            b["calls"] += 1
            b["input_tokens"] += e["input_tokens"]
            b["cache_read_tokens"] += e["cache_read_tokens"]
            b["output_tokens"] += e["output_tokens"]
            b["billable_tokens"] += e["billable_tokens"]
            b["total_tokens"] += e["total_tokens"]
            b["est_cost_usd"] = round(b["est_cost_usd"] + e["est_cost_usd"], 4)
            b[e["pool"]] += e["billable_tokens"]

            cell = heatmap_grid[k][dt_c.hour]
            cell["calls"] += 1
            cell["billable_tokens"] += e["billable_tokens"]
            cell["est_cost_usd"] = round(cell["est_cost_usd"] + e["est_cost_usd"], 4)

    daily_7d = [daily_buckets[k] for k in daily_keys]
    heatmap_7x24 = [
        {"date": k, "label": daily_buckets[k]["label"], "hours": heatmap_grid[k]}
        for k in daily_keys
    ]

    by_conv_raw: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_proj_raw: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in selected_events:
        cid = e["conversation_id"]
        by_conv_raw[cid].append(e)
        ws = (conv_meta.get(cid) or {}).get("workspace") or "(无工作区)"
        by_proj_raw[ws].append(e)

    conversations = []
    for cid, evs in by_conv_raw.items():
        s = summarize_events(evs)
        m = conv_meta.get(cid) or {}
        models_used = sorted({e["model"] for e in evs if e["model"] != "unknown"})
        s["id"] = cid
        s["short_id"] = cid[:8]
        s["title"] = m.get("title") or (m.get("preview", "")[:36] or "(未命名会话)")
        s["workspace"] = m.get("workspace") or "(无工作区)"
        s["is_subagent"] = bool(m.get("parent_id"))
        s["parent_id"] = (m.get("parent_id") or "")[:8]
        s["models"] = models_used
        s["peak_context"] = max((e["context_size"] for e in evs), default=0)
        s["last_ts"] = evs[-1]["ts"].isoformat()
        s["last_ts_cst"] = fmt_cst(evs[-1]["ts"], "%m-%d %H:%M")
        conversations.append(s)
    conversations.sort(key=lambda x: -x["billable_tokens"])

    projects = []
    for ws, evs in by_proj_raw.items():
        s = summarize_events(evs)
        s["workspace"] = ws
        s["share_billable_pct"] = round((s["billable_tokens"] / total_sel_billable) * 100.0, 1)
        projects.append(s)
    projects.sort(key=lambda x: -x["billable_tokens"])

    recent_calls = []
    for e in events[-20:][::-1]:
        m = conv_meta.get(e["conversation_id"]) or {}
        recent_calls.append(
            {
                "ts_cst": fmt_cst(e["ts"], "%m-%d %H:%M:%S"),
                "model": e["model"],
                "pool": e["pool"],
                "conversation_id": e["conversation_id"],
                "short_id": e["conversation_id"][:8],
                "title": (m.get("title") or "(未命名)")[:28],
                "input_tokens": e["input_tokens"],
                "cache_read_tokens": e["cache_read_tokens"],
                "output_tokens": e["output_tokens"],
                "tool_names": e["tool_names"][:3],
                "tool_count": e["tool_count"],
                "est_cost_usd": round(e["est_cost_usd"], 4),
            }
        )

    quota_info = analyze_quota_buckets(live_state, snapshots, events, now)
    notifications_info = evaluate_quota_notifications(quota_info, now=now, dispatch=dispatch_notifications)
    week_over_week = compute_week_over_week(events, now=now, tz=local_tz)
    insights = build_insights(quota_info, windows_summary, by_pool, burn_5h, selected_summary)

    sl_cfg = settings.get("statusLine") if isinstance(settings.get("statusLine"), dict) else {}
    sl_cmd = str(sl_cfg.get("command") or "")
    sl_installed = ("statusline.py" in sl_cmd) and (sl_cfg.get("enabled", True) is not False)

    sl_full_path = str(APP_DIR / "statusline.py")
    home_str = str(Path.home())
    sl_disp_path = ("~" + sl_full_path[len(home_str) :]) if sl_full_path.startswith(home_str) else sl_full_path

    live_session: Dict[str, Any] = {
        "connected": live_state is not None,
        "statusline_configured": sl_installed,
        "statusline_path": sl_full_path,
        "statusline_display_path": sl_disp_path,
        "configured_model": settings.get("model") or "-",
        "configured_planner": (settings.get("orchestrator") or {}).get("planner") or "-",
        "agent_state": (live_state or {}).get("agent_state") or "-",
        "plan_tier": (live_state or {}).get("plan_tier") or "-",
        "version": (live_state or {}).get("version") or "-",
        "active_model": ((live_state or {}).get("model") or {}).get("display_name")
        or settings.get("model")
        or "-",
        "conversation_title": (live_state or {}).get("conversation_title") or "-",
        "context_window": (live_state or {}).get("context_window") or None,
        "cost": (live_state or {}).get("cost") or None,
        "subagents": (live_state or {}).get("subagents") or [],
        "captured_at_cst": fmt_cst(parse_iso_dt((live_state or {}).get("captured_at")), "%m-%d %H:%M:%S")
        if live_state
        else "-",
    }

    return {
        "generated_at": now.isoformat(),
        "generated_at_cst": f"{fmt_cst(now, '%Y-%m-%d %H:%M:%S')} {tz_label}",
        "timezone_label": tz_label,
        "window": window,
        "selected_summary": selected_summary,
        "live_session": live_session,
        "quota": quota_info,
        "notifications": notifications_info,
        "week_over_week": week_over_week,
        "insights": insights,
        "windows": windows_summary,
        "burn_5h": burn_5h,
        "rolling_5h_10m": rolling_5h_10m,
        "by_pool": by_pool,
        "by_model": by_model,
        "top_tools": top_tools,
        "hourly_24h": hourly_24h,
        "daily_7d": daily_7d,
        "heatmap_7x24": heatmap_7x24,
        "conversations": conversations[:30],
        "projects": projects[:15],
        "recent_calls": recent_calls,
    }


def get_conversation_detail(conv_id: str) -> Optional[Dict[str, Any]]:
    """Return turn-by-turn breakdown for a single conversation (supports full or 8-char prefix)."""
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", conv_id)
    if not clean_id:
        return None

    target_file: Optional[Path] = None
    matched_id = ""
    for agy_root in _discover_agy_dirs():
        brain_dir = agy_root / "brain"
        if not brain_dir.exists():
            continue
        for d in brain_dir.iterdir():
            if d.is_dir() and (d.name == clean_id or d.name.startswith(clean_id)):
                cand = d / ".system_generated" / "logs" / "transcript.jsonl"
                if cand.exists():
                    target_file = cand
                    matched_id = d.name
                    break
        if target_file is not None:
            break
    if target_file is None:
        return None

    meta = load_conversation_metadata().get(matched_id) or {}
    turns: List[Dict[str, Any]] = []
    tool_counter: Counter = Counter()
    events: List[Dict[str, Any]] = []

    parsed_events = _parse_single_transcript(target_file, matched_id)
    for ev in parsed_events:
        for tn in ev["tool_names"]:
            tool_counter[tn] += 1
        events.append(ev)
        turns.append(
            {
                "turn": len(turns) + 1,
                "step_index": ev["step_index"],
                "ts_cst": fmt_cst(ev["ts"], "%m-%d %H:%M:%S"),
                "model": ev["model"],
                "pool": ev["pool"],
                "input_tokens": ev["input_tokens"],
                "cache_read_tokens": ev["cache_read_tokens"],
                "output_tokens": ev["output_tokens"],
                "context_size": ev["context_size"],
                "billable_tokens": ev["billable_tokens"],
                "est_cost_usd": round(ev["est_cost_usd"], 4),
                "tool_names": ev["tool_names"],
            }
        )

    summary = summarize_events(events)
    return {
        "id": matched_id,
        "short_id": matched_id[:8],
        "title": meta.get("title") or "(未命名会话)",
        "workspace": meta.get("workspace") or "(无工作区)",
        "is_subagent": bool(meta.get("parent_id")),
        "summary": summary,
        "peak_context": max((t["context_size"] for t in turns), default=0),
        "tools": [{"name": k, "count": v} for k, v in tool_counter.most_common(12)],
        "turns": turns,
    }


def _safe_csv_cell(val: Any) -> Any:
    if isinstance(val, str) and val and val[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + val
    return val


def export_sessions_csv(window: str = "7d") -> str:
    data = build_analytics(window=window)
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(
        [
            "会话ID",
            "标题",
            "工作区",
            "是否子代理",
            "使用模型",
            "调用次数",
            "新增输入Tokens",
            "缓存命中Tokens",
            "输出Tokens",
            "有效合计Tokens",
            "峰值上下文",
            "缓存命中率(%)",
            "估算费用(USD)",
            "缓存节省(USD)",
            "最近活跃(CST)",
        ]
    )
    for c in data["conversations"]:
        w.writerow(
            [
                _safe_csv_cell(c["id"]),
                _safe_csv_cell(c["title"]),
                _safe_csv_cell(c["workspace"]),
                "是" if c["is_subagent"] else "否",
                _safe_csv_cell("; ".join(c["models"])),
                c["calls"],
                c["input_tokens"],
                c["cache_read_tokens"],
                c["output_tokens"],
                c["billable_tokens"],
                c["peak_context"],
                c["cache_hit_pct"],
                c["est_cost_usd"],
                c["cache_saved_usd"],
                c["last_ts_cst"],
            ]
        )
    return buf.getvalue()
