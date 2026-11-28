#!/usr/bin/env python3
"""Official quota bucket telemetry analysis, snapshot history compaction, and manual calibration."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from storage import (
    DAILY_ARCHIVE_FILE,
    LIVE_STATE_FILE,
    SNAPSHOTS_FILE,
    atomic_write_text,
    ensure_data_dir,
    file_lock,
    fmt_cst,
    fmt_duration,
    get_local_tz,
    parse_iso_dt,
)


def load_live_state() -> Optional[Dict[str, Any]]:
    if not LIVE_STATE_FILE.exists():
        return None
    try:
        d = json.loads(LIVE_STATE_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def load_quota_snapshots(max_age_days: int = 14) -> List[Dict[str, Any]]:
    if not SNAPSHOTS_FILE.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    snaps: List[Dict[str, Any]] = []
    try:
        with SNAPSHOTS_FILE.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if not isinstance(d, dict):
                    continue
                dt = parse_iso_dt(d.get("captured_at"))
                if dt is None or dt < cutoff:
                    continue
                d["_dt"] = dt
                snaps.append(d)
    except Exception:
        return []
    snaps.sort(key=lambda s: s["_dt"])
    return snaps


def infer_bucket_meta(bucket_id: str, reset_in_seconds: Optional[float]) -> Tuple[str, str, float, str, str]:
    """Return (chinese_label, window_kind, cycle_hours, pool_key, pool_desc)."""
    bid = bucket_id.lower()
    explicit_weekly = "week" in bid or "7d" in bid or "seven" in bid
    explicit_5h = "5h" in bid or "five" in bid or "hour" in bid or "short" in bid

    if explicit_5h and not explicit_weekly:
        is_five_h = True
        is_weekly = False
    elif explicit_weekly:
        is_weekly = True
        is_five_h = False
    elif reset_in_seconds is not None:
        is_weekly = reset_in_seconds > 6 * 3600
        is_five_h = not is_weekly
    else:
        is_weekly = False
        is_five_h = False

    if "3p" in bid or "claude" in bid or "anthropic" in bid or "gpt" in bid or "third" in bid:
        group = "Claude / GPT"
        pool_key = "claude_gpt"
        pool_desc = "Claude · GPT"
    elif "flash" in bid:
        group = "Gemini Flash"
        pool_key = "gemini_flash"
        pool_desc = "Gemini Flash"
    elif "gemini" in bid or "pro" in bid:
        group = "Gemini"
        pool_key = "gemini_pro"
        pool_desc = "Google Gemini"
    else:
        group = bucket_id
        pool_key = "other"
        pool_desc = bucket_id

    if is_weekly:
        return f"{group} · 每周限额", "weekly", 168.0, pool_key, pool_desc
    if is_five_h:
        return f"{group} · 当前用量 (5h)", "five_hour", 5.0, pool_key, pool_desc
    return f"{group} · 用量限额", "other", 168.0, pool_key, pool_desc


def extract_remaining_fraction(entry: Dict[str, Any]) -> Optional[float]:
    if not isinstance(entry, dict):
        return None
    if "remaining_fraction" in entry and entry["remaining_fraction"] is not None:
        try:
            v = float(entry["remaining_fraction"])
            if not math.isfinite(v):
                return None
            return max(0.0, min(1.0, v))
        except Exception:
            return None
    if "remaining_percentage" in entry and entry["remaining_percentage"] is not None:
        try:
            v = float(entry["remaining_percentage"]) / 100.0
            if not math.isfinite(v):
                return None
            return max(0.0, min(1.0, v))
        except Exception:
            return None
    return None


def _event_matches_bucket_pool(event_pool: str, bucket_pool_key: str) -> bool:
    if bucket_pool_key == "claude_gpt":
        return event_pool == "claude_gpt"
    if bucket_pool_key == "gemini_flash":
        return event_pool == "gemini_flash"
    if bucket_pool_key == "gemini_pro":
        return event_pool in ("gemini_pro", "gemini_flash")
    return False


def analyze_quota_buckets(
    live_state: Optional[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    now: datetime,
) -> Dict[str, Any]:
    latest_quota: Dict[str, Any] = {}
    captured_at: Optional[datetime] = None
    source = "none"

    if live_state and isinstance(live_state.get("quota"), dict) and live_state["quota"]:
        latest_quota = live_state["quota"]
        captured_at = parse_iso_dt(live_state.get("captured_at"))
        source = live_state.get("source") or "statusline"
    elif snapshots:
        last = snapshots[-1]
        if isinstance(last.get("quota"), dict):
            latest_quota = last["quota"]
            captured_at = last["_dt"]
            source = last.get("source") or "snapshot"

    stale_seconds = (now - captured_at).total_seconds() if captured_at else None

    buckets: List[Dict[str, Any]] = []
    for bid, raw in sorted(latest_quota.items()):
        if not isinstance(raw, dict):
            continue
        rem_frac = extract_remaining_fraction(raw)
        rem_amt = raw.get("remaining_amount")
        reset_dt = parse_iso_dt(raw.get("reset_time"))
        if reset_dt is not None and reset_dt.year <= 1971:
            reset_dt = None
        reset_in_sec = raw.get("reset_in_seconds")
        is_idle_full = (
            reset_dt is None
            and rem_frac is not None
            and rem_frac >= 0.9999
            and (reset_in_sec is None or float(reset_in_sec) <= 0)
        )
        if is_idle_full:
            reset_in_sec = None
        elif reset_dt is not None:
            reset_in_sec = max(0.0, (reset_dt - now).total_seconds())
        elif reset_in_sec is not None and captured_at is not None:
            reset_in_sec = max(0.0, float(reset_in_sec) - (now - captured_at).total_seconds())
            reset_dt = now + timedelta(seconds=reset_in_sec)

        label, window_kind, cycle_hours, pool_key, pool_desc = infer_bucket_meta(bid, reset_in_sec)
        rem_pct = round(rem_frac * 100.0, 2) if rem_frac is not None else None
        used_pct = round((1.0 - rem_frac) * 100.0, 2) if rem_frac is not None else None
        raw_reset_dt = parse_iso_dt(raw.get("reset_time"))
        if raw_reset_dt is not None and raw_reset_dt.year <= 1971:
            raw_reset_dt = None
        raw_reset_sec = raw.get("reset_in_seconds")
        reset_passed = (not is_idle_full) and (
            (raw_reset_dt is not None and raw_reset_dt <= now)
            or (
                raw_reset_dt is None
                and raw_reset_sec is not None
                and float(raw_reset_sec) - ((now - captured_at).total_seconds() if captured_at else 0.0) <= 0
            )
        )

        time_elapsed_pct: Optional[float] = None
        pacing_ratio: Optional[float] = None
        cycle_start_dt: Optional[datetime] = None
        daily_safe_budget_pct: Optional[float] = None
        hourly_safe_budget_pct: Optional[float] = None

        if reset_dt is not None and cycle_hours > 0:
            cycle_start_dt = reset_dt - timedelta(hours=cycle_hours)
            elapsed_h = max(0.0, (now - cycle_start_dt).total_seconds() / 3600.0)
            time_elapsed_pct = round(min(100.0, (elapsed_h / cycle_hours) * 100.0), 2)
            min_elapsed_h = 0.5 if window_kind == "five_hour" else 6.0
            if (
                not reset_passed
                and used_pct is not None
                and used_pct >= 2.0
                and elapsed_h >= min_elapsed_h
                and time_elapsed_pct > 0.5
            ):
                pacing_ratio = round(used_pct / time_elapsed_pct, 2)
            if not reset_passed and rem_pct is not None and reset_in_sec is not None and reset_in_sec > 60:
                rem_hours = reset_in_sec / 3600.0
                hourly_safe_budget_pct = round(rem_pct / rem_hours, 2)
                if window_kind == "weekly":
                    rem_days = max(0.25, rem_hours / 24.0)
                    daily_safe_budget_pct = round(min(rem_pct, rem_pct / rem_days), 1)

        raw_series: List[Dict[str, Any]] = []
        for s in snapshots:
            q_map = s.get("quota")
            if not isinstance(q_map, dict):
                continue
            q = q_map.get(bid)
            if not isinstance(q, dict):
                continue
            rf = extract_remaining_fraction(q)
            if rf is None:
                continue
            snap_reset_dt = parse_iso_dt(q.get("reset_time"))
            if reset_dt is not None and snap_reset_dt is not None:
                if abs((snap_reset_dt - reset_dt).total_seconds()) > 120:
                    continue
            elif cycle_start_dt is not None and s["_dt"] < cycle_start_dt:
                continue
            raw_series.append(
                {
                    "ts": s["_dt"].isoformat(),
                    "ts_cst": fmt_cst(s["_dt"], "%m-%d %H:%M"),
                    "remaining_pct": round(rf * 100.0, 2),
                    "used_pct": round((1.0 - rf) * 100.0, 2),
                    "_dt": s["_dt"],
                }
            )

        seg_start = 0
        for idx in range(1, len(raw_series)):
            if raw_series[idx]["used_pct"] < raw_series[idx - 1]["used_pct"] - 5.0:
                seg_start = idx
        series = raw_series[seg_start:]

        burn_pct_per_hour: Optional[float] = None
        tokens_per_1pct: Optional[float] = None
        projected_exhaust_hours: Optional[float] = None
        projected_rem_at_reset: Optional[float] = None
        burn_method = "none"

        if not reset_passed and len(series) >= 2:
            lookback_h = 5.0 if window_kind == "five_hour" else 24.0
            cutoff = now - timedelta(hours=lookback_h)
            recent = [pt for pt in series if pt["_dt"] >= cutoff]
            if len(recent) < 2:
                recent = series
            first, last_pt = recent[0], recent[-1]
            dt_hours = (last_pt["_dt"] - first["_dt"]).total_seconds() / 3600.0
            delta_used = last_pt["used_pct"] - first["used_pct"]
            min_obs_h = 0.05 if window_kind == "five_hour" else 0.75
            if dt_hours >= min_obs_h and delta_used >= 0.05:
                burn_pct_per_hour = round(delta_used / dt_hours, 3)
                burn_method = "observed"
                if pool_key != "other" and delta_used >= 0.2:
                    win_tokens = sum(
                        e["billable_tokens"]
                        for e in events
                        if first["_dt"] <= e["ts"] <= last_pt["_dt"]
                        and _event_matches_bucket_pool(e["pool"], pool_key)
                    )
                    if win_tokens > 0:
                        tokens_per_1pct = round(win_tokens / delta_used, 0)

        min_avg_h = 0.25 if window_kind == "five_hour" else 1.5
        if (
            not reset_passed
            and burn_pct_per_hour is None
            and used_pct is not None
            and used_pct > 0.1
            and cycle_start_dt is not None
        ):
            elapsed_h = (now - cycle_start_dt).total_seconds() / 3600.0
            if elapsed_h >= min_avg_h:
                burn_pct_per_hour = round(used_pct / elapsed_h, 3)
                burn_method = "cycle_avg"

        if burn_pct_per_hour is not None and burn_pct_per_hour > 0 and rem_pct is not None and not reset_passed:
            projected_exhaust_hours = round(rem_pct / burn_pct_per_hour, 2)
            if reset_in_sec is not None:
                rem_hours = reset_in_sec / 3600.0
                projected_rem_at_reset = round(max(0.0, rem_pct - burn_pct_per_hour * rem_hours), 2)

        status = "ok"
        if raw.get("disabled"):
            status = "disabled"
        elif reset_passed:
            status = "reset_ready"
        elif used_pct is not None:
            if used_pct >= 80.0:
                status = "critical"
            elif used_pct >= 55.0 or (pacing_ratio is not None and pacing_ratio >= 1.35):
                status = "warning"

        buckets.append(
            {
                "id": bid,
                "label": label,
                "pool_key": pool_key,
                "pool_desc": pool_desc,
                "window_kind": window_kind,
                "cycle_hours": cycle_hours,
                "remaining_pct": rem_pct,
                "used_pct": used_pct,
                "remaining_amount": rem_amt,
                "disabled": bool(raw.get("disabled", False)),
                "reset_passed": reset_passed,
                "reset_time": reset_dt.isoformat() if reset_dt else None,
                "reset_time_cst": fmt_cst(reset_dt, "%m-%d %H:%M") if reset_dt else "-",
                "reset_in_seconds": int(reset_in_sec) if reset_in_sec is not None else None,
                "reset_in_text": "已到期 · 下次调用刷新" if reset_passed else fmt_duration(reset_in_sec),
                "time_elapsed_pct": time_elapsed_pct,
                "pacing_ratio": pacing_ratio,
                "daily_safe_budget_pct": daily_safe_budget_pct,
                "hourly_safe_budget_pct": hourly_safe_budget_pct,
                "burn_pct_per_hour": burn_pct_per_hour,
                "burn_pct_per_day": round(burn_pct_per_hour * 24.0, 2) if burn_pct_per_hour is not None else None,
                "burn_method": burn_method,
                "projected_exhaust_hours": projected_exhaust_hours,
                "projected_exhaust_text": fmt_duration(projected_exhaust_hours * 3600.0)
                if projected_exhaust_hours is not None
                else "-",
                "projected_rem_at_reset": projected_rem_at_reset,
                "tokens_per_1pct": tokens_per_1pct,
                "status": status,
                "history": [{k: v for k, v in pt.items() if k != "_dt"} for pt in series[-120:]],
            }
        )

    pool_order = {"gemini_pro": 0, "gemini_flash": 1, "claude_gpt": 2, "other": 3}
    win_order = {"five_hour": 0, "weekly": 1, "other": 2}
    buckets.sort(key=lambda b: (pool_order.get(b["pool_key"], 9), win_order.get(b["window_kind"], 9), b["id"]))

    return {
        "has_live_quota": len(buckets) > 0,
        "source": source,
        "captured_at": captured_at.isoformat() if captured_at else None,
        "captured_at_cst": fmt_cst(captured_at, "%m-%d %H:%M:%S") if captured_at else "-",
        "stale_seconds": int(stale_seconds) if stale_seconds is not None else None,
        "stale_text": fmt_duration(stale_seconds) if stale_seconds is not None else "未采集",
        "snapshot_count": len(snapshots),
        "buckets": buckets,
    }


def _snapshots_lock_path() -> Path:
    return SNAPSHOTS_FILE.with_name(".snapshots.lock")


def _quota_sig(q: Any) -> str:
    if not isinstance(q, dict):
        return ""
    slim = {}
    for k, v in sorted(q.items()):
        if not isinstance(v, dict):
            continue
        rf = extract_remaining_fraction(v)
        slim[k] = (round(rf, 4) if rf is not None else None, v.get("reset_time"))
    return json.dumps(slim, sort_keys=True)


def record_quota_snapshot(
    quota_obj: Dict[str, Any],
    source: str = "manual",
    extra: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> bool:
    ensure_data_dir()
    if not quota_obj:
        return False
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    with file_lock(_snapshots_lock_path(), timeout=1.5) as locked:
        if not locked:
            return False

        should_append = force
        if not should_append:
            last_snap = None
            if SNAPSHOTS_FILE.exists():
                try:
                    with SNAPSHOTS_FILE.open("rb") as fh:
                        fh.seek(0, os.SEEK_END)
                        size = fh.tell()
                        fh.seek(max(0, size - 4096))
                        lines = fh.read().decode("utf-8", errors="replace").splitlines()
                        for raw_ln in reversed(lines):
                            if not raw_ln.strip():
                                continue
                            try:
                                cand = json.loads(raw_ln)
                                if isinstance(cand, dict):
                                    last_snap = cand
                                    break
                            except Exception:
                                continue
                except Exception:
                    last_snap = None
            if last_snap is None:
                should_append = True
            else:
                last_dt = parse_iso_dt(last_snap.get("captured_at"))
                last_q = last_snap.get("quota") or {}
                if last_dt is None or (now - last_dt).total_seconds() >= 120:
                    should_append = True
                elif _quota_sig(last_q) != _quota_sig(quota_obj):
                    should_append = True

        if should_append:
            rec: Dict[str, Any] = {
                "captured_at": now_iso,
                "source": source,
                "quota": quota_obj,
            }
            if extra:
                rec.update(extra)
            with SNAPSHOTS_FILE.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
            try:
                if SNAPSHOTS_FILE.stat().st_size > 512 * 1024:
                    _compact_quota_snapshots_unlocked(keep_days=30)
            except Exception:
                pass
        return should_append


def _compact_quota_snapshots_unlocked(keep_days: int = 30, keep_archive_days: int = 365) -> Dict[str, int]:
    if not SNAPSHOTS_FILE.exists() and not DAILY_ARCHIVE_FILE.exists():
        return {"before_lines": 0, "after_lines": 0, "archived_days": 0, "bytes_before": 0, "bytes_after": 0}

    bytes_before = SNAPSHOTS_FILE.stat().st_size if SNAPSHOTS_FILE.exists() else 0
    now_utc = datetime.now(timezone.utc)
    local_tz = get_local_tz()
    cutoff = now_utc - timedelta(days=max(1, keep_days))
    archive_cutoff_day = (now_utc - timedelta(days=max(keep_days + 1, keep_archive_days))).astimezone(local_tz).strftime("%Y-%m-%d")

    kept_raw: List[Dict[str, Any]] = []
    old_by_day: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    before_lines = 0

    if SNAPSHOTS_FILE.exists():
        with SNAPSHOTS_FILE.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                before_lines += 1
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if not isinstance(d, dict):
                    continue
                dt = parse_iso_dt(d.get("captured_at"))
                if dt is None:
                    continue
                if dt < cutoff:
                    day_key = dt.astimezone(local_tz).strftime("%Y-%m-%d")
                    q_map = d.get("quota")
                    if not isinstance(q_map, dict):
                        continue
                    for bid, bval in q_map.items():
                        if not isinstance(bval, dict):
                            continue
                        rf = extract_remaining_fraction(bval)
                        if rf is None:
                            continue
                        cur = old_by_day[day_key].get(bid)
                        if cur is None:
                            old_by_day[day_key][bid] = {"min_rem": rf, "last_rem": rf, "samples": 1}
                        else:
                            cur["min_rem"] = min(cur["min_rem"], rf)
                            cur["last_rem"] = rf
                            cur["samples"] += 1
                else:
                    kept_raw.append(d)

    compacted: List[Dict[str, Any]] = []
    sigs = [_quota_sig(x.get("quota")) for x in kept_raw]
    for i, item in enumerate(kept_raw):
        if i == 0 or i == len(kept_raw) - 1 or sigs[i] != sigs[i - 1] or sigs[i] != sigs[i + 1]:
            compacted.append(item)

    archived_days = 0
    if old_by_day or DAILY_ARCHIVE_FILE.exists():
        existing_arch: Dict[str, Any] = {}
        had_corrupt_or_expired = False
        if DAILY_ARCHIVE_FILE.exists():
            for line in DAILY_ARCHIVE_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict) and isinstance(row.get("date"), str):
                        if row["date"] >= archive_cutoff_day:
                            existing_arch[row["date"]] = row
                        else:
                            had_corrupt_or_expired = True
                    else:
                        had_corrupt_or_expired = True
                except Exception:
                    had_corrupt_or_expired = True
        for day_key, buckets_summary in sorted(old_by_day.items()):
            if day_key < archive_cutoff_day:
                continue
            prev = existing_arch.get(day_key)
            prev_buckets = prev.get("buckets") if isinstance(prev, dict) and isinstance(prev.get("buckets"), dict) else {}
            merged_buckets = dict(prev_buckets)
            for bid, b_stat in buckets_summary.items():
                old_b = merged_buckets.get(bid)
                if isinstance(old_b, dict) and old_b.get("min_rem") is not None:
                    merged_buckets[bid] = {
                        "min_rem": min(float(old_b["min_rem"]), b_stat["min_rem"]),
                        "last_rem": b_stat["last_rem"],
                        "samples": int(old_b.get("samples") or 0) + b_stat["samples"],
                    }
                else:
                    merged_buckets[bid] = b_stat
            existing_arch[day_key] = {"date": day_key, "buckets": merged_buckets}
            archived_days += 1
        if archived_days > 0 or had_corrupt_or_expired:
            arch_text = "".join(json.dumps(existing_arch[k], ensure_ascii=False) + "\n" for k in sorted(existing_arch.keys()))
            atomic_write_text(DAILY_ARCHIVE_FILE, arch_text)

    bytes_after = 0
    if SNAPSHOTS_FILE.exists() or compacted:
        snap_text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in compacted)
        atomic_write_text(SNAPSHOTS_FILE, snap_text)
        bytes_after = SNAPSHOTS_FILE.stat().st_size

    return {
        "before_lines": before_lines,
        "after_lines": len(compacted),
        "archived_days": archived_days,
        "bytes_before": bytes_before,
        "bytes_after": bytes_after,
    }


def compact_quota_snapshots(keep_days: int = 30) -> Dict[str, Any]:
    """Thread/process-safe wrapper around snapshot compaction and daily archiving (fail-closed)."""
    ensure_data_dir()
    with file_lock(_snapshots_lock_path(), timeout=3.0) as locked:
        if not locked:
            sz = SNAPSHOTS_FILE.stat().st_size if SNAPSHOTS_FILE.exists() else 0
            return {
                "before_lines": 0,
                "after_lines": 0,
                "archived_days": 0,
                "bytes_before": sz,
                "bytes_after": sz,
                "skipped_locked": True,
            }
        return _compact_quota_snapshots_unlocked(keep_days=keep_days)


def save_manual_quota(bucket: str, remaining_pct: float, reset_str: Optional[str] = None) -> Dict[str, Any]:
    """Shared helper for both CLI and Web UI manual quota recording."""
    ensure_data_dir()
    rem_pct = max(0.0, min(100.0, float(remaining_pct)))
    reset_iso: Optional[str] = None
    reset_in_sec: Optional[int] = None

    if reset_str and reset_str.strip():
        local_tz = get_local_tz()
        now_local = datetime.now(local_tz)
        raw = reset_str.strip()
        dt_local: Optional[datetime] = None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
            try:
                parsed = datetime.strptime(raw, fmt)
                if fmt == "%m-%d %H:%M":
                    parsed = parsed.replace(year=now_local.year)
                dt_local = parsed.replace(tzinfo=local_tz)
                break
            except ValueError:
                continue
        if dt_local is None:
            raise ValueError(f"无法解析重置时间: {raw}（格式如 2026-12-02 08:00 或 12-02 08:00）")
        dt_utc = dt_local.astimezone(timezone.utc)
        reset_iso = dt_utc.isoformat()
        reset_in_sec = max(0, int((dt_utc - datetime.now(timezone.utc)).total_seconds()))

    with file_lock(LIVE_STATE_FILE.with_name(".state.lock"), timeout=1.5) as locked:
        if not locked:
            raise TimeoutError("获取状态文件锁超时，已放弃写入，请稍后重试")

        existing_quota: Dict[str, Any] = {}
        existing_state: Dict[str, Any] = {}
        if LIVE_STATE_FILE.exists():
            try:
                old = json.loads(LIVE_STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(old, dict):
                    existing_state = old
                    if isinstance(old.get("quota"), dict):
                        existing_quota = dict(old["quota"])
            except Exception:
                pass

        entry: Dict[str, Any] = {"remaining_fraction": round(rem_pct / 100.0, 4)}
        if reset_iso:
            entry["reset_time"] = reset_iso
        if reset_in_sec is not None:
            entry["reset_in_seconds"] = reset_in_sec
        existing_quota[bucket.strip()] = entry

        if not record_quota_snapshot(existing_quota, source="manual", force=True):
            raise TimeoutError("获取限额快照锁超时，已放弃写入，请稍后重试")

        state = {k: v for k, v in existing_state.items() if k != "email"}
        state["captured_at"] = datetime.now(timezone.utc).isoformat()
        state["source"] = "manual"
        state["quota"] = existing_quota
        atomic_write_text(LIVE_STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2))
    return {"ok": True, "bucket": bucket.strip(), "remaining_pct": rem_pct, "reset_time": reset_iso}
