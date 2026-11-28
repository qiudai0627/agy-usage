#!/usr/bin/env python3
"""Zero-side-effect, strictly sanitized read-only query layer for MCP and external integrations."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Dict, List, Optional

from analytics import summarize_events
from instance_lock import APP_VERSION, verify_live_instance
from quota import analyze_quota_buckets, load_live_state, load_quota_snapshots
from storage import (
    LIVE_STATE_FILE,
    _discover_agy_dirs,
    classify_model_pool,
    get_local_tz,
    parse_iso_dt,
)
from transcripts import load_agy_settings, load_transcript_events

SCHEMA_VERSION = "1.5.1"
VALID_SUMMARY_WINDOWS = ("today", "7d", "30d")
MAX_SUMMARY_BYTES = 2048
MAX_QUOTA_BYTES = 1024
MAX_CACHE_BYTES = 1024
MAX_HEALTH_BYTES = 512


def _json_size(obj: Dict[str, Any]) -> int:
    return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _window_bounds(window: str, now: datetime) -> tuple[datetime, str]:
    local_tz = get_local_tz()
    now_local = now.astimezone(local_tz)
    if window == "today":
        start = now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        return start, "today"
    if window == "30d":
        return now - timedelta(days=30), "30d"
    return now - timedelta(days=7), "7d"


def _coverage_info(events: List[Dict[str, Any]], start: datetime, now: datetime) -> Dict[str, Any]:
    if not events:
        return {"from": start.isoformat(), "to": now.isoformat(), "event_count": 0}
    return {
        "from": events[0]["ts"].isoformat(),
        "to": events[-1]["ts"].isoformat(),
        "event_count": len(events),
    }


def query_usage_summary(window: str = "7d", model: Optional[str] = None) -> Dict[str, Any]:
    """Pure read-only, strictly sanitized usage summary (<= 2 KiB, zero paths/titles/IDs, zero notifications)."""
    if window not in VALID_SUMMARY_WINDOWS:
        raise ValueError(f"invalid window '{window}', expected one of {VALID_SUMMARY_WINDOWS}")
    if model is not None and (not isinstance(model, str) or len(model) > 128):
        raise ValueError("invalid model filter")

    now = datetime.now(timezone.utc)
    start, norm_win = _window_bounds(window, now)
    all_events = load_transcript_events(read_only=True)
    selected = [e for e in all_events if e["ts"] >= start]
    if model:
        needle = model.strip().lower()
        selected = [e for e in selected if needle in str(e.get("model") or "").lower()]

    agg = summarize_events(selected)
    by_model_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in selected:
        by_model_map[str(e.get("model") or "unknown")].append(e)

    models_list = []
    for m_name, evs in by_model_map.items():
        s = summarize_events(evs)
        models_list.append(
            {
                "model": m_name,
                "pool": classify_model_pool(m_name),
                "calls": s["calls"],
                "billable_tokens": s["billable_tokens"],
                "cache_read_tokens": s["cache_read_tokens"],
                "est_cost_usd": round(s["est_cost_usd"], 4),
            }
        )
    models_list.sort(key=lambda x: -x["billable_tokens"])

    latest_ts = all_events[-1]["ts"] if all_events else None
    stale = bool(latest_ts is None or (now - latest_ts).total_seconds() > 3600)

    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "as_of": now.isoformat(),
        "source": "local_transcripts",
        "stale": stale,
        "coverage": _coverage_info(selected, start, now),
        "estimated": True,
        "window": norm_win,
        "model_filter": model.strip() if model else None,
        "summary": {
            "calls": agg["calls"],
            "input_tokens": agg["input_tokens"],
            "cache_read_tokens": agg["cache_read_tokens"],
            "output_tokens": agg["output_tokens"],
            "billable_tokens": agg["billable_tokens"],
            "total_tokens": agg["total_tokens"],
            "cache_hit_pct": agg["cache_hit_pct"],
            "est_cost_usd": round(agg["est_cost_usd"], 4),
            "cache_saved_usd": round(agg["cache_saved_usd"], 4),
        },
        "top_models": models_list[:8],
        "truncated": len(models_list) > 8,
    }
    while _json_size(payload) > MAX_SUMMARY_BYTES and payload["top_models"]:
        payload["top_models"].pop()
        payload["truncated"] = True
    return payload


def query_quota_status() -> Dict[str, Any]:
    """Pure read-only dual-pool four-bucket quota snapshot (<= 1 KiB, zero notifications)."""
    now = datetime.now(timezone.utc)
    live_state = load_live_state()
    snapshots = load_quota_snapshots()
    events = load_transcript_events(read_only=True)
    quota_info = analyze_quota_buckets(live_state, snapshots, events, now)

    captured_dt = parse_iso_dt((live_state or {}).get("captured_at")) if live_state else None
    stale = bool(captured_dt is None or (now - captured_dt).total_seconds() > 600)

    buckets = []
    for b in quota_info.get("buckets") or []:
        rem_pct = b.get("remaining_pct")
        used_pct = round(max(0.0, 100.0 - float(rem_pct)), 1) if rem_pct is not None else None
        buckets.append(
            {
                "id": b.get("key") or b.get("id") or "unknown",
                "used_pct": used_pct,
                "remaining_pct": round(float(rem_pct), 1) if rem_pct is not None else None,
                "reset_in_s": b.get("reset_in_seconds"),
                "reset_at": b.get("reset_time"),
                "status": b.get("status") or "unknown",
            }
        )

    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "as_of": now.isoformat(),
        "source": "live_state" if live_state else "snapshots",
        "stale": stale,
        "estimated": False,
        "has_live_quota": bool(quota_info.get("has_live_quota")),
        "buckets": buckets[:6],
    }
    while _json_size(payload) > MAX_QUOTA_BYTES and payload["buckets"]:
        payload["buckets"].pop()
    return payload


def query_cache_health(window: str = "7d") -> Dict[str, Any]:
    """Pure read-only cache hit-rate & estimated savings summary (<= 1 KiB)."""
    if window not in VALID_SUMMARY_WINDOWS:
        raise ValueError(f"invalid window '{window}', expected one of {VALID_SUMMARY_WINDOWS}")
    now = datetime.now(timezone.utc)
    start, norm_win = _window_bounds(window, now)
    all_events = load_transcript_events(read_only=True)
    selected = [e for e in all_events if e["ts"] >= start]
    agg = summarize_events(selected)

    latest_ts = all_events[-1]["ts"] if all_events else None
    stale = bool(latest_ts is None or (now - latest_ts).total_seconds() > 3600)

    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": now.isoformat(),
        "source": "local_transcripts",
        "stale": stale,
        "estimated": True,
        "window": norm_win,
        "calls": agg["calls"],
        "cache_hit_pct": agg["cache_hit_pct"],
        "cache_read_tokens": agg["cache_read_tokens"],
        "input_tokens": agg["input_tokens"],
        "cache_saved_usd": round(agg["cache_saved_usd"], 4),
        "suspected_drops": [],
        "drop_detection": "planned_v1.6.0",
    }


def query_health() -> Dict[str, Any]:
    """Pure read-only boolean pipeline & daemon diagnostics (<= 512 B, zero paths/IDs/side-effects)."""
    now = datetime.now(timezone.utc)
    settings = load_agy_settings()
    sl_cfg = settings.get("statusLine") if isinstance(settings.get("statusLine"), dict) else {}
    sl_cmd = str(sl_cfg.get("command") or "")
    sl_ok = ("statusline.py" in sl_cmd) and (sl_cfg.get("enabled", True) is not False)

    live_ok = LIVE_STATE_FILE.is_file()
    transcripts_ok = any((d / "brain").is_dir() for d in _discover_agy_dirs())

    daemon_ok, daemon_meta = verify_live_instance(timeout=0.35)
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "version": APP_VERSION,
        "as_of": now.isoformat(),
        "statusline": sl_ok,
        "live_state": live_ok,
        "transcripts_readable": transcripts_ok,
        "daemon": daemon_ok,
    }
    if daemon_ok and daemon_meta:
        host = str(daemon_meta.get("host") or "127.0.0.1")
        port = int(daemon_meta.get("port") or 18420)
        payload["dashboard_url"] = f"http://{host}:{port}"
    return payload
