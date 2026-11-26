#!/usr/bin/env python3
"""Core data ingestion, quota telemetry, and deep analytics engine for Antigravity CLI (agy)."""

from __future__ import annotations

import csv
import glob
import io
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone, tzinfo
import hashlib
import math
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

CST = timezone(timedelta(hours=8))


def get_local_tz() -> tzinfo:
    """Return configured or system local timezone (defaults to system timezone, fallback UTC+8)."""
    override = os.environ.get("AGY_USAGE_TZ", "").strip()
    if override:
        up = override.upper()
        if up in ("UTC", "Z"):
            return timezone.utc
        if up in ("CST", "ASIA/SHANGHAI", "UTC+8", "+08:00", "+8"):
            return CST
        m = re.match(r"^([+-])(\d{1,2})(?::?(\d{2}))?$", up)
        if m:
            sign = 1 if m.group(1) == "+" else -1
            hh = int(m.group(2))
            mm = int(m.group(3) or "0")
            return timezone(timedelta(minutes=sign * (hh * 60 + mm)))
    try:
        tz = datetime.now().astimezone().tzinfo
        return tz if tz is not None else CST
    except Exception:
        return CST


def get_tz_label() -> str:
    tz = get_local_tz()
    now_local = datetime.now(tz)
    off = now_local.utcoffset()
    if off is None:
        return "Local"
    total_min = int(round(off.total_seconds() / 60.0))
    if total_min == 0:
        return "UTC"
    if total_min == 480:
        return "UTC+8"
    sign = "+" if total_min >= 0 else "-"
    hh, mm = divmod(abs(total_min), 60)
    return f"UTC{sign}{hh}" if mm == 0 else f"UTC{sign}{hh}:{mm:02d}"

def _default_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData/Local"))
        return base / "agy-usage"
    return Path.home() / ".cache/agy-usage"


def _discover_agy_dirs() -> List[Path]:
    explicit = os.environ.get("AGY_DATA_DIR")
    if explicit:
        return [Path(explicit)]
    candidates = [
        Path.home() / ".gemini/antigravity-cli",
        Path.home() / ".gemini/antigravity",
    ]
    found = [p for p in candidates if p.exists()]
    return found if found else [candidates[0]]


AGY_DIR = Path(os.environ.get("AGY_DATA_DIR", str(Path.home() / ".gemini/antigravity-cli")))
BRAIN_DIR = AGY_DIR / "brain"
SUMMARY_DB = AGY_DIR / "conversation_summaries.db"
META_CACHE = AGY_DIR / "cache/conversation_metadata.json"
SETTINGS_FILE = AGY_DIR / "settings.json"

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("AGY_USAGE_DATA_DIR", str(_default_data_dir())))
LIVE_STATE_FILE = DATA_DIR / "live_state.json"
SNAPSHOTS_FILE = DATA_DIR / "quota_snapshots.jsonl"
TRANSCRIPT_INDEX_FILE = DATA_DIR / "transcript_index.json"
CONV_CACHE_DIR = DATA_DIR / "conv_cache"
DAILY_ARCHIVE_FILE = DATA_DIR / "quota_daily_archive.jsonl"
PREFERENCES_FILE = DATA_DIR / "preferences.json"
NOTIFY_STATE_FILE = DATA_DIR / "notify_state.json"
WEB_LOG_FILE = DATA_DIR / "web.log"


def discover_settings_file() -> Path:
    """Resolve active Antigravity settings.json across CLI and Desktop directories."""
    if os.environ.get("AGY_DATA_DIR"):
        return AGY_DIR / "settings.json"
    for d in _discover_agy_dirs():
        cand = d / "settings.json"
        if cand.exists():
            return cand
    return SETTINGS_FILE

# Two-tier incremental cache: path -> (mtime_ns, size, parsed_events)
_CACHE_LOCK = threading.RLock()
_MEM_TRANSCRIPT_CACHE: Dict[str, Tuple[int, int, List[Dict[str, Any]]]] = {}
_DISK_INDEX_LOADED: bool = False


@contextmanager
def file_lock(lock_path: Path, timeout: float = 2.0) -> Iterator[bool]:
    """Cross-platform inter-process advisory lock (POSIX flock / Windows msvcrt)."""
    ensure_data_dir()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+b")
    locked = False
    deadline = time.monotonic() + max(0.05, timeout)
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.015)
        yield locked
    finally:
        if locked:
            try:
                if os.name == "nt":
                    import msvcrt
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        fh.close()


def atomic_replace(src: Path, dst: Path) -> None:
    """Replace dst with src, retrying brief Windows sharing violations."""
    delays = (0.01, 0.02, 0.04, 0.08, 0.12) if os.name == "nt" else ()
    for d in delays:
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            time.sleep(d)
    os.replace(src, dst)


def atomic_write_text(path: Path, content: str, mode: Optional[int] = None) -> None:
    """Write text to a unique sibling temp file, fsync, and atomically replace path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        if mode is not None and os.name != "nt":
            os.chmod(tmp_path, mode)
        atomic_replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

# Reference list-price estimates (USD per 1M tokens) for rough cost & cache-savings estimation only.
# Clearly labeled as "估算" in all UIs; actual billing depends on Antigravity subscription/credits.
MODEL_PRICING_PER_1M: Dict[str, Tuple[float, float, float]] = {
    # (fresh_input, cache_read, output)
    "gemini-4-neon": (2.50, 0.25, 15.00),
    "gemini-4-carbon": (1.50, 0.15, 10.00),
    "gemini-4-argon": (1.25, 0.125, 8.00),
    "gemini-4-hydrogen": (2.00, 0.20, 12.00),
    "gemini-pro-orchestrator": (2.50, 0.25, 15.00),
    "gemini-3.8-flash": (0.30, 0.03, 2.50),
    "claude-opus-5-5": (15.00, 1.50, 75.00),
    "claude-sonnet-5-5": (3.00, 0.30, 15.00),
    "gpt-oss-120b": (1.00, 0.10, 4.00),
}

POOL_LABELS: Dict[str, str] = {
    "gemini_pro": "Gemini Pro / 旗舰系列",
    "gemini_flash": "Gemini Flash 轻量系列",
    "claude_gpt": "Claude / GPT 第三方系列",
    "other": "其他 / 未知模型",
}


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    if not s or s.startswith("0001-01-01"):
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        s = re.sub(r"(\.\d{6})\d+", r"\1", s)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def fmt_cst(dt: Optional[datetime], fmt: str = "%m-%d %H:%M") -> str:
    if dt is None:
        return "-"
    return dt.astimezone(get_local_tz()).strftime(fmt)


def fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    sec = int(max(0, round(seconds)))
    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    if days > 0:
        return f"{days}天{hours}小时"
    if hours > 0:
        return f"{hours}小时{mins}分"
    if mins > 0:
        return f"{mins}分{secs}秒"
    return f"{secs}秒"


def fmt_tokens(n: float) -> str:
    n = float(n or 0)
    if abs(n) >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.1f}k"
    return f"{int(round(n))}"


def classify_model_pool(model: Optional[str]) -> str:
    m = (model or "").lower()
    if not m or m == "unknown":
        return "other"
    if "flash" in m:
        return "gemini_flash"
    if "claude" in m or "gpt" in m or "opus" in m or "sonnet" in m:
        return "claude_gpt"
    if "gemini" in m or "orchestrator" in m:
        return "gemini_pro"
    return "other"


def get_model_rates(model: Optional[str]) -> Tuple[float, float, float]:
    m = (model or "").lower()
    for prefix, r in MODEL_PRICING_PER_1M.items():
        if prefix in m:
            return r
    return (1.50, 0.15, 10.00)


def estimate_cost_usd(
    model: Optional[str],
    input_tokens: int,
    cache_read_tokens: int,
    output_tokens: int,
) -> float:
    in_r, cache_r, out_r = get_model_rates(model)
    return (
        (input_tokens / 1_000_000.0) * in_r
        + (cache_read_tokens / 1_000_000.0) * cache_r
        + (output_tokens / 1_000_000.0) * out_r
    )


def estimate_cache_saved_usd(model: Optional[str], cache_read_tokens: int) -> float:
    in_r, cache_r, _ = get_model_rates(model)
    return (cache_read_tokens / 1_000_000.0) * max(0.0, in_r - cache_r)


def shorten_workspace(uris: List[str]) -> str:
    if not uris:
        return "(无工作区)"
    u = uris[0]
    if u.startswith("file://"):
        u = u[7:]
    home = str(Path.home())
    if u == home:
        return "~"
    if u.startswith(home + "/"):
        rel = u[len(home) + 1 :]
        parts = rel.split("/")
        return parts[-1] if len(parts) > 1 else f"~/{rel}"
    return Path(u).name or u


def extract_tool_names(tool_calls: Any) -> List[str]:
    names: List[str] = []
    if not isinstance(tool_calls, list):
        return names
    for tc in tool_calls:
        if isinstance(tc, dict):
            name = tc.get("name") or (tc.get("function") or {}).get("name") or tc.get("tool_name")
            if name:
                names.append(str(name))
        elif isinstance(tc, str):
            names.append(tc)
    return names


def load_conversation_metadata() -> Dict[str, Dict[str, Any]]:
    meta: Dict[str, Dict[str, Any]] = {}

    for agy_root in _discover_agy_dirs():
        meta_cache = agy_root / "cache/conversation_metadata.json"
        if meta_cache.exists():
            try:
                raw = json.loads(meta_cache.read_text(encoding="utf-8"))
                for cid, entry in (raw.get("conversations") or {}).items():
                    summary = entry.get("summary") or {}
                    uris = summary.get("WorkspaceURIs") or []
                    meta[cid] = {
                        "id": cid,
                        "title": summary.get("Title") or "",
                        "preview": summary.get("Preview") or "",
                        "workspace": shorten_workspace(uris),
                        "workspace_uris": uris,
                        "parent_id": "",
                        "step_count": summary.get("NumSteps") or 0,
                        "updated_at": summary.get("UpdatedAt") or entry.get("last_modified_time") or "",
                    }
            except Exception:
                pass

        summary_db = agy_root / "conversation_summaries.db"
        if summary_db.exists():
            try:
                uri = f"{summary_db.resolve().as_uri()}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=1.5)
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT conversation_id, title, preview, step_count,
                           last_modified_time, workspace_uris, parent_conversation_id, agent_name
                    FROM conversation_summaries
                    """
                )
                for row in cur.fetchall():
                    cid, title, preview, step_count, lmt, uris_json, parent_id, agent_name = row
                    try:
                        uris = json.loads(uris_json) if uris_json else []
                    except Exception:
                        uris = []
                    existing = meta.get(cid, {"id": cid})
                    existing["title"] = title or existing.get("title") or ""
                    existing["preview"] = preview or existing.get("preview") or ""
                    existing["workspace"] = shorten_workspace(uris) if uris else existing.get("workspace", "(无工作区)")
                    existing["workspace_uris"] = uris or existing.get("workspace_uris", [])
                    existing["parent_id"] = parent_id or existing.get("parent_id", "")
                    existing["agent_name"] = agent_name or ""
                    existing["step_count"] = max(int(step_count or 0), int(existing.get("step_count") or 0))
                    if lmt and not str(lmt).startswith("0001-01-01"):
                        existing["updated_at"] = str(lmt)
                    meta[cid] = existing
                conn.close()
            except Exception:
                pass

    return meta


def load_agy_settings() -> Dict[str, Any]:
    sf = discover_settings_file()
    if not sf.exists():
        return {}
    try:
        d = json.loads(sf.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _conv_cache_file(path_str: str) -> Path:
    digest = hashlib.sha1(path_str.encode("utf-8", errors="replace")).hexdigest()[:20]
    return CONV_CACHE_DIR / f"{digest}.json"


def _hydrate_event_ts(ev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if "ts" in ev and isinstance(ev["ts"], datetime):
        return ev
    dt = parse_iso_dt(ev.get("ts_iso"))
    if dt is None:
        return None
    out = dict(ev)
    out["ts"] = dt
    return out


def _safe_nonneg_int(val: Any) -> Optional[int]:
    if val is None or isinstance(val, bool):
        return 0 if val is None else None
    try:
        f = float(val)
        if not math.isfinite(f) or f < 0:
            return None
        return int(f)
    except (TypeError, ValueError, OverflowError):
        return None


def _save_single_conv_cache(path_str: str, mtime_ns: int, size: int, evs: List[Dict[str, Any]]) -> None:
    try:
        CONV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        serializable = [{k: v for k, v in e.items() if k != "ts"} for e in evs]
        payload = json.dumps(
            {"version": 2, "path": path_str, "mtime_ns": mtime_ns, "size": size, "events": serializable},
            ensure_ascii=False,
        )
        atomic_write_text(_conv_cache_file(path_str), payload)
    except Exception:
        pass


def _remove_single_conv_cache(path_str: str) -> None:
    try:
        _conv_cache_file(path_str).unlink(missing_ok=True)
    except OSError:
        pass


def _load_disk_transcript_index() -> None:
    """Load per-conversation cache shards (and seamlessly migrate legacy monolithic index once)."""
    global _DISK_INDEX_LOADED
    with _CACHE_LOCK:
        if _DISK_INDEX_LOADED:
            return
        CONV_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # One-time migration from legacy v1 monolithic transcript_index.json
        if TRANSCRIPT_INDEX_FILE.exists():
            try:
                raw = json.loads(TRANSCRIPT_INDEX_FILE.read_text(encoding="utf-8"))
                entries = raw.get("files") if isinstance(raw, dict) else None
                if isinstance(entries, dict):
                    for path_str, info in entries.items():
                        if not isinstance(info, dict):
                            continue
                        mtime_ns = _safe_nonneg_int(info.get("mtime_ns")) or 0
                        size = _safe_nonneg_int(info.get("size")) or 0
                        evs = []
                        for item in info.get("events") or []:
                            if isinstance(item, dict):
                                h = _hydrate_event_ts(item)
                                if h is not None:
                                    evs.append(h)
                        _MEM_TRANSCRIPT_CACHE[path_str] = (mtime_ns, size, evs)
                        _save_single_conv_cache(path_str, mtime_ns, size, evs)
                TRANSCRIPT_INDEX_FILE.unlink(missing_ok=True)
            except Exception:
                pass

        # Load v2 per-session cache shards
        for shard in CONV_CACHE_DIR.glob("*.json"):
            try:
                info = json.loads(shard.read_text(encoding="utf-8"))
                if not isinstance(info, dict):
                    continue
                path_str = info.get("path")
                if not isinstance(path_str, str) or not path_str:
                    continue
                mtime_ns = _safe_nonneg_int(info.get("mtime_ns")) or 0
                size = _safe_nonneg_int(info.get("size")) or 0
                evs = []
                for item in info.get("events") or []:
                    if isinstance(item, dict):
                        h = _hydrate_event_ts(item)
                        if h is not None:
                            evs.append(h)
                _MEM_TRANSCRIPT_CACHE[path_str] = (mtime_ns, size, evs)
            except Exception:
                continue

        _DISK_INDEX_LOADED = True


def _parse_single_transcript(p: Path, cid: str) -> List[Dict[str, Any]]:
    file_events: List[Dict[str, Any]] = []
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            if "input_tokens" not in d and "output_tokens" not in d:
                continue
            dt = parse_iso_dt(d.get("created_at"))
            if dt is None:
                continue
            in_tok = _safe_nonneg_int(d.get("input_tokens"))
            cache_tok = _safe_nonneg_int(d.get("cache_read_tokens"))
            out_tok = _safe_nonneg_int(d.get("output_tokens"))
            step_idx = _safe_nonneg_int(d.get("step_index"))
            if in_tok is None or cache_tok is None or out_tok is None or step_idx is None:
                continue
            raw_model = d.get("model")
            model = str(raw_model) if isinstance(raw_model, str) and raw_model.strip() else "unknown"
            tool_names = extract_tool_names(d.get("tool_calls"))
            file_events.append(
                {
                    "conversation_id": cid,
                    "step_index": step_idx,
                    "ts": dt,
                    "ts_iso": dt.isoformat(),
                    "model": model,
                    "pool": classify_model_pool(model),
                    "input_tokens": in_tok,
                    "cache_read_tokens": cache_tok,
                    "output_tokens": out_tok,
                    "total_tokens": in_tok + cache_tok + out_tok,
                    "billable_tokens": in_tok + out_tok,
                    "context_size": in_tok + cache_tok,
                    "est_cost_usd": estimate_cost_usd(model, in_tok, cache_tok, out_tok),
                    "cache_saved_usd": estimate_cache_saved_usd(model, cache_tok),
                    "tool_count": len(tool_names),
                    "tool_names": tool_names,
                    "has_thinking": bool(d.get("thinking")),
                    "has_error": bool(d.get("error")),
                }
            )
    return file_events


def load_transcript_events() -> List[Dict[str, Any]]:
    _load_disk_transcript_index()
    events: List[Dict[str, Any]] = []
    seen_convs = set()
    active_paths = set()
    updated_shards: List[Tuple[str, int, int, List[Dict[str, Any]]]] = []

    for agy_root in _discover_agy_dirs():
        brain_dir = agy_root / "brain"
        if not brain_dir.exists():
            continue
        pattern = str(brain_dir / "*" / ".system_generated" / "logs" / "transcript.jsonl")
        for path_str in glob.glob(pattern):
            p = Path(path_str)
            try:
                cid = p.parts[p.parts.index("brain") + 1]
            except Exception:
                cid = "unknown"
            if cid != "unknown" and cid in seen_convs:
                continue
            seen_convs.add(cid)
            active_paths.add(path_str)
            try:
                st = p.stat()
                with _CACHE_LOCK:
                    cached = _MEM_TRANSCRIPT_CACHE.get(path_str)
                if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
                    events.extend(cached[2])
                else:
                    parsed = _parse_single_transcript(p, cid)
                    with _CACHE_LOCK:
                        _MEM_TRANSCRIPT_CACHE[path_str] = (st.st_mtime_ns, st.st_size, parsed)
                    updated_shards.append((path_str, st.st_mtime_ns, st.st_size, parsed))
                    events.extend(parsed)
            except Exception:
                continue

    with _CACHE_LOCK:
        stale_keys = [k for k in list(_MEM_TRANSCRIPT_CACHE.keys()) if k not in active_paths]
        for k in stale_keys:
            _MEM_TRANSCRIPT_CACHE.pop(k, None)

    # O(1) disk persistence: only write changed session shards & unlink removed ones
    if updated_shards or stale_keys:
        with file_lock(DATA_DIR / ".index.lock", timeout=1.5) as locked:
            if locked:
                for path_str, mtime_ns, size, parsed in updated_shards:
                    _save_single_conv_cache(path_str, mtime_ns, size, parsed)
                for k in stale_keys:
                    _remove_single_conv_cache(k)

    events.sort(key=lambda e: e["ts"])
    return events


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
        pool_desc = "第三方池 · Claude Opus/Sonnet、GPT"
    elif "flash" in bid:
        group = "Gemini Flash"
        pool_key = "gemini_flash"
        pool_desc = "Gemini Flash 轻量系列"
    elif "gemini" in bid or "pro" in bid:
        group = "Gemini"
        pool_key = "gemini_pro"
        pool_desc = "Google 自家池 · Gemini 4 Neon/Flash"
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
        reset_in_sec = raw.get("reset_in_seconds")
        if reset_dt is not None:
            reset_in_sec = max(0.0, (reset_dt - now).total_seconds())
        elif reset_in_sec is not None and captured_at is not None:
            reset_in_sec = max(0.0, float(reset_in_sec) - (now - captured_at).total_seconds())
            reset_dt = now + timedelta(seconds=reset_in_sec)

        label, window_kind, cycle_hours, pool_key, pool_desc = infer_bucket_meta(bid, reset_in_sec)
        rem_pct = round(rem_frac * 100.0, 2) if rem_frac is not None else None
        used_pct = round((1.0 - rem_frac) * 100.0, 2) if rem_frac is not None else None
        reset_passed = (reset_dt is not None and reset_dt <= now) or (reset_in_sec is not None and reset_in_sec <= 0)

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
            if not reset_passed and used_pct is not None and used_pct >= 2.0 and elapsed_h >= min_elapsed_h and time_elapsed_pct > 0.5:
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

        # Segment at any quota reset drop (> 5% used_pct drop) so pre-reset samples never pollute new cycle
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
        if not reset_passed and burn_pct_per_hour is None and used_pct is not None and used_pct > 0.1 and cycle_start_dt is not None:
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

    # Group by pool first (Gemini first, then Claude/GPT), then 5h before weekly
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
            # Safe argument-passed PowerShell BalloonTip fallback on Windows
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
    """Candidate A: Deduplicated 80%/95% alerts & fresh-telemetry-confirmed recovery notifications.

    Rules:
    - Default off (`notifications_enabled == False`); state still tracked quietly so enabling won't misfire old events.
    - Deduplicated per `(bucket_id, cycle_key)` across process restarts.
    - Countdown hitting zero (`reset_passed == True`) NEVER counts as recovery; only fresh official
      `statusline` data (`stale_seconds <= 600` and `not reset_passed`) confirming low `used_pct <= 15%`
      after prior `max_used_pct >= 50%` triggers recovery notification.
    """
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

                # Do NOT advance state or fire recovery merely because countdown expired (`reset_passed`)
                if reset_passed:
                    continue

                # 1. Check fresh-official-confirmed recovery (回血)
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

                # Reset per-cycle tracking if cycle_key changed without triggering recovery
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

                # 2. Check rising-edge 95% and 80% thresholds (deduplicated per cycle)
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


def compute_week_over_week(
    events: List[Dict[str, Any]],
    now: datetime,
    tz: tzinfo,
) -> Dict[str, Any]:
    """Candidate B: Same-timezone, same-elapsed-progress natural week comparison (本周 vs 上周同进度).

    Never fabricates comparison when prior-week samples are missing; explicitly distinguishes natural
    calendar week Token usage from rolling quota buckets.
    """
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

    # 1. Quota alerts (neutral factual pacing notes; Candidate C cross-pool persuasion explicitly omitted)
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

    # 2. Cache savings highlight
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

    # 3. Claude/GPT pool vs Gemini pool balance
    claude_pool = next((p for p in by_pool if p["pool"] == "claude_gpt"), None)
    if claude_pool and claude_pool["share_billable_pct"] >= 30:
        insights.append(
            {
                "level": "info",
                "title": f"Claude/GPT 池占有效用量 {claude_pool['share_billable_pct']}%",
                "detail": f"共 {claude_pool['calls']} 次调用（估算 ${claude_pool['est_cost_usd']:.2f}），与 Gemini 限额池分离统计。",
            }
        )

    # 4. 5h burst pace
    if burn_5h["calls_per_hour"] >= 40:
        insights.append(
            {
                "level": "info",
                "title": f"近 5h 高频作业：{burn_5h['calls_per_hour']} 次/h",
                "detail": f"有效消耗速率 {fmt_tokens(burn_5h['billable_tokens_per_hour'])}/h，建议关注 5h 滚动窗口。",
            }
        )

    return insights[:4]


def build_analytics(window: str = "7d") -> Dict[str, Any]:
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

    win_map = {
        "5h": start_5h,
        "today": start_today_cst,
        "24h": start_24h,
        "week": monday_cst,
        "7d": start_7d,
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

    # Burn rate from transcripts (last 5h)
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

    # 5-hour rolling window in 30 × 10-minute slots (CST)
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

    # Model & Pool breakdown
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

    # Hourly series (last 24 hours, CST)
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

    # Daily series (last 7 days, CST) + 7x24 heatmap
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

    # Top conversations & projects
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

    # Recent calls feed
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
    notifications_info = evaluate_quota_notifications(quota_info, now=now, dispatch=True)
    week_over_week = compute_week_over_week(events, now=now, tz=local_tz)
    insights = build_insights(quota_info, windows_summary, by_pool, burn_5h, selected_summary)

    sl_cfg = settings.get("statusLine") if isinstance(settings.get("statusLine"), dict) else {}
    sl_cmd = str(sl_cfg.get("command") or "")
    sl_installed = ("statusline.py" in sl_cmd) and (sl_cfg.get("enabled", True) is not False)

    sl_full_path = str(APP_DIR / "statusline.py")
    home_str = str(Path.home())
    sl_disp_path = ("~" + sl_full_path[len(home_str):]) if sl_full_path.startswith(home_str) else sl_full_path

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
    buf.write("\ufeff")  # UTF-8 BOM for clean Excel opening on macOS
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


def _snapshots_lock_path() -> Path:
    return SNAPSHOTS_FILE.with_name(".snapshots.lock")


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


def append_web_log(data: bytes | str, timeout: float = 1.5) -> bool:
    """Append log payload to WEB_LOG_FILE under the same .weblog.lock used by rotate_web_log."""
    ensure_data_dir()
    payload = data.encode("utf-8", errors="replace") if isinstance(data, str) else data
    with file_lock(WEB_LOG_FILE.with_name(".weblog.lock"), timeout=timeout) as locked:
        if not locked:
            return False
        with WEB_LOG_FILE.open("ab") as fh:
            fh.write(payload)
            fh.flush()
        return True


def rotate_web_log(
    max_bytes: int = 2 * 1024 * 1024,
    keep_bytes: int = 512 * 1024,
    _after_read_hook: Optional[Any] = None,
) -> int:
    """In-place log rotation under .weblog.lock (shared with append_web_log / LockedLogStream)."""
    if not WEB_LOG_FILE.exists():
        return 0
    try:
        with file_lock(WEB_LOG_FILE.with_name(".weblog.lock"), timeout=1.0) as locked:
            if not locked:
                return 0
            sz = WEB_LOG_FILE.stat().st_size
            if sz <= max_bytes:
                return 0
            with WEB_LOG_FILE.open("r+b") as fh:
                fh.seek(max(0, sz - keep_bytes))
                tail = fh.read()
                nl = tail.find(b"\n")
                if 0 <= nl < len(tail) - 1:
                    tail = tail[nl + 1 :]
                if _after_read_hook is not None:
                    _after_read_hook()
                fh.seek(0)
                fh.write(tail)
                fh.truncate()
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except OSError:
                    pass
            return max(0, sz - len(tail))
    except Exception:
        return 0


def _dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except Exception:
            return 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except Exception:
                pass
    return total


def clean_cache(keep_days: int = 30, reset_index: bool = False, max_backups: int = 3) -> Dict[str, Any]:
    """Prune and compact agy-usage's own cache, logs, stale index entries, and excess settings backups."""
    global _DISK_INDEX_LOADED
    ensure_data_dir()
    before_total = _dir_size(DATA_DIR)

    snap_res = compact_quota_snapshots(keep_days=keep_days)
    rotate_web_log(max_bytes=512 * 1024, keep_bytes=128 * 1024)

    # Remove stale *.tmp files older than 10 minutes inside DATA_DIR
    now_epoch = time.time()
    for tmp_f in DATA_DIR.glob("*.tmp"):
        try:
            if now_epoch - tmp_f.stat().st_mtime > 600:
                tmp_f.unlink()
        except OSError:
            pass

    if reset_index:
        with _CACHE_LOCK:
            _MEM_TRANSCRIPT_CACHE.clear()
            _DISK_INDEX_LOADED = False
        TRANSCRIPT_INDEX_FILE.unlink(missing_ok=True)
        if CONV_CACHE_DIR.exists():
            for shard in CONV_CACHE_DIR.glob("*.json"):
                shard.unlink(missing_ok=True)
    load_transcript_events()

    backups_removed = 0
    backups_freed = 0
    sf = discover_settings_file()
    if sf.parent.exists():
        baks = sorted(
            sf.parent.glob("settings.json.bak-agy-usage-*"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
        for old_bak in baks[max(0, max_backups) :]:
            try:
                backups_freed += old_bak.stat().st_size
                old_bak.unlink()
                backups_removed += 1
            except Exception:
                pass

    after_total = _dir_size(DATA_DIR)
    with _CACHE_LOCK:
        idx_cnt = len(_MEM_TRANSCRIPT_CACHE)
    return {
        "cache_dir": str(DATA_DIR),
        "bytes_before": before_total,
        "bytes_after": after_total,
        "bytes_freed": max(0, before_total - after_total) + backups_freed,
        "snapshots": snap_res,
        "index_entries": idx_cnt,
        "backups_removed": backups_removed,
    }


def _count_corrupt_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    bad = 0
    try:
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not ln.strip():
                continue
            try:
                v = json.loads(ln)
                if not isinstance(v, dict):
                    bad += 1
            except Exception:
                bad += 1
    except Exception:
        pass
    return bad


def run_doctor(stale_days: int = 30, prune_stale: bool = False, fix_issues: bool = False) -> Dict[str, Any]:
    """Inspect Antigravity & agy-usage health first (read-only); optionally repair own pipeline (`--fix`) or prune stale via LS API."""
    import sys as _sys
    import urllib.request

    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=max(1, stale_days))
    orphan_cutoff = now - timedelta(days=1)

    # 1. Inspect own telemetry pipeline & cache health BEFORE modifying anything
    sf = discover_settings_file()
    settings = load_agy_settings()
    sl_cfg = settings.get("statusLine") if isinstance(settings.get("statusLine"), dict) else {}
    sl_cmd = str(sl_cfg.get("command") or "").strip()
    expected_sl = str(APP_DIR / "statusline.py")
    sl_enabled = bool(sl_cfg) and (sl_cfg.get("enabled", True) is not False) and ("statusline.py" in sl_cmd)
    sl_target_exists = Path(expected_sl).exists() and (expected_sl in sl_cmd if sl_cmd else False)
    sl_executable = os.access(expected_sl, os.X_OK) if os.name != "nt" else Path(expected_sl).exists()

    corrupt_snapshots = _count_corrupt_jsonl(SNAPSHOTS_FILE)
    corrupt_archive = _count_corrupt_jsonl(DAILY_ARCHIVE_FILE)
    tmp_set = set()
    if DATA_DIR.exists():
        tmp_set.update(DATA_DIR.glob("*.tmp"))
        tmp_set.update(DATA_DIR.glob(".*.tmp"))
    if CONV_CACHE_DIR.exists():
        tmp_set.update(CONV_CACHE_DIR.glob("*.tmp"))
        tmp_set.update(CONV_CACHE_DIR.glob(".*.tmp"))
    orphan_tmps = sorted(tmp_set)

    ls_state = load_live_state()
    ls_age_sec: Optional[int] = None
    if ls_state and ls_state.get("captured_at"):
        cdt = parse_iso_dt(ls_state.get("captured_at"))
        if cdt is not None:
            ls_age_sec = max(0, int((now - cdt).total_seconds()))

    fixed_actions: List[str] = []
    if fix_issues:
        ensure_data_dir()
        if os.name != "nt":
            for script_p in (APP_DIR / "statusline.py", APP_DIR / "cli.py", APP_DIR / "core.py"):
                if script_p.exists() and not os.access(script_p, os.X_OK):
                    os.chmod(script_p, 0o755)
                    fixed_actions.append(f"恢复脚本可执行权限: {script_p.name}")
            sl_executable = os.access(expected_sl, os.X_OK)

        if not (sl_enabled and sl_target_exists):
            sf.parent.mkdir(parents=True, exist_ok=True)
            cfg_obj = dict(settings) if isinstance(settings, dict) else {}
            cmd_val = f'"{_sys.executable}" "{expected_sl}"' if os.name == "nt" else expected_sl
            cfg_obj["statusLine"] = {
                "type": "command",
                "command": cmd_val,
                "enabled": True,
                "stack_with_default": True,
            }
            atomic_write_text(sf, json.dumps(cfg_obj, ensure_ascii=False, indent=2) + "\n", mode=0o600)
            sl_enabled = True
            sl_target_exists = True
            fixed_actions.append(f"修复并启用 statusLine 配置 ({sf})")

        removed_tmp = 0
        for tf in orphan_tmps:
            try:
                tf.unlink(missing_ok=True)
                removed_tmp += 1
            except OSError:
                pass
        if removed_tmp:
            fixed_actions.append(f"清理遗留临时文件 {removed_tmp} 个")
            orphan_tmps = []

        if corrupt_snapshots > 0 or corrupt_archive > 0:
            compact_quota_snapshots(keep_days=30)
            fixed_actions.append(f"隔离并重写损坏快照/归档行 ({corrupt_snapshots + corrupt_archive} 行)")
            corrupt_snapshots = _count_corrupt_jsonl(SNAPSHOTS_FILE)
            corrupt_archive = _count_corrupt_jsonl(DAILY_ARCHIVE_FILE)

    load_transcript_events()
    meta = load_conversation_metadata()
    agy_dirs = _discover_agy_dirs()

    brain_Ids: Dict[str, Path] = {}
    conv_db_sizes: Dict[str, int] = defaultdict(int)
    total_agy_bytes = 0

    for root in agy_dirs:
        total_agy_bytes += _dir_size(root / "brain") + _dir_size(root / "conversations")
        bdir = root / "brain"
        if bdir.exists():
            for d in bdir.iterdir():
                if d.is_dir() and d.name not in brain_Ids:
                    brain_Ids[d.name] = d
        cdir = root / "conversations"
        if cdir.exists():
            for f in cdir.iterdir():
                if f.is_file():
                    cid_prefix = f.name.split(".db")[0]
                    try:
                        conv_db_sizes[cid_prefix] += f.stat().st_size
                    except Exception:
                        pass

    empty_db_entries: List[Dict[str, Any]] = []
    orphan_brain_dirs: List[Dict[str, Any]] = []
    stale_sessions: List[Dict[str, Any]] = []

    for cid, m in meta.items():
        upd = parse_iso_dt(m.get("updated_at"))
        has_transcript = cid in brain_Ids and (brain_Ids[cid] / ".system_generated/logs/transcript.jsonl").exists()
        steps = int(m.get("step_count") or 0)
        b_size = _dir_size(brain_Ids[cid]) if cid in brain_Ids else 0
        total_sz = b_size + conv_db_sizes.get(cid, 0)

        if steps == 0 and not has_transcript and (upd is None or upd < orphan_cutoff):
            empty_db_entries.append(
                {
                    "id": cid,
                    "short_id": cid[:8],
                    "workspace": m.get("workspace") or "-",
                    "bytes": total_sz,
                }
            )
        elif upd is not None and upd < stale_cutoff:
            stale_sessions.append(
                {
                    "id": cid,
                    "short_id": cid[:8],
                    "title": m.get("title") or "(未命名)",
                    "workspace": m.get("workspace") or "-",
                    "last_cst": fmt_cst(upd, "%Y-%m-%d %H:%M"),
                    "age_days": int((now - upd).total_seconds() // 86400),
                    "bytes": total_sz,
                }
            )

    for cid, bpath in brain_Ids.items():
        tfile = bpath / ".system_generated/logs/transcript.jsonl"
        try:
            mtime_dt = datetime.fromtimestamp(bpath.stat().st_mtime, tz=timezone.utc)
        except Exception:
            mtime_dt = now
        if cid not in meta and not tfile.exists() and mtime_dt < orphan_cutoff:
            orphan_brain_dirs.append(
                {"id": cid, "short_id": cid[:8], "path": str(bpath), "bytes": _dir_size(bpath)}
            )

    stale_sessions.sort(key=lambda x: -x["bytes"])
    empty_db_entries.sort(key=lambda x: -x["bytes"])

    # Optional safe deletion ONLY via official Antigravity ConversationService HTTP API
    ls_addr = os.environ.get("ANTIGRAVITY_LS_ADDRESS", "").strip()
    csrf = os.environ.get("ANTIGRAVITY_CSRF_TOKEN", "").strip()
    deleted_ids: List[str] = []
    delete_errors: List[str] = []

    if prune_stale and (stale_sessions or empty_db_entries):
        if ls_addr and csrf:
            targets = [x["id"] for x in empty_db_entries] + [x["id"] for x in stale_sessions]
            url = f"http://{ls_addr}/product.v1.ConversationService/DeleteConversation"
            for tid in targets:
                try:
                    req = urllib.request.Request(
                        url,
                        data=json.dumps({"conversationId": tid}).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "Connect-Protocol-Version": "1",
                            "x-antigravity-csrf-token": csrf,
                        },
                        method="POST",
                    )
                    urllib.request.urlopen(req, timeout=3.0).read()
                    deleted_ids.append(tid[:8])
                except Exception as exc:
                    delete_errors.append(f"{tid[:8]}: {exc}")

    own_cache_bytes = _dir_size(DATA_DIR)
    with _CACHE_LOCK:
        cached_cnt = len(_MEM_TRANSCRIPT_CACHE)
    return {
        "agy_dirs": [str(p) for p in agy_dirs],
        "settings_file": str(sf),
        "pipeline": {
            "statusline_enabled": sl_enabled,
            "statusline_path_valid": sl_target_exists,
            "statusline_executable": sl_executable,
            "live_state_age_seconds": ls_age_sec,
            "corrupt_snapshot_lines": corrupt_snapshots,
            "corrupt_archive_lines": corrupt_archive,
            "orphan_tmp_count": len(orphan_tmps),
        },
        "fixed_actions": fixed_actions,
        "total_agy_bytes": total_agy_bytes,
        "own_cache_dir": str(DATA_DIR),
        "own_cache_bytes": own_cache_bytes,
        "index_cached_files": cached_cnt,
        "total_conversations": len(meta),
        "empty_db_entries": empty_db_entries,
        "orphan_brain_dirs": orphan_brain_dirs,
        "stale_days": stale_days,
        "stale_sessions": stale_sessions,
        "ls_api_available": bool(ls_addr and csrf),
        "deleted_ids": deleted_ids,
        "delete_errors": delete_errors,
    }


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
