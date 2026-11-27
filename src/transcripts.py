#!/usr/bin/env python3
"""Conversation metadata discovery and O(1) per-session incremental transcript indexing."""

from __future__ import annotations

from datetime import datetime
import glob
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

from storage import (
    CONV_CACHE_DIR,
    DATA_DIR,
    TRANSCRIPT_INDEX_FILE,
    _discover_agy_dirs,
    atomic_write_text,
    classify_model_pool,
    discover_settings_file,
    estimate_cache_saved_usd,
    estimate_cost_usd,
    file_lock,
    parse_iso_dt,
    shorten_workspace,
)

# Two-tier incremental cache: path -> (mtime_ns, size, parsed_events)
_CACHE_LOCK = threading.RLock()
_MEM_TRANSCRIPT_CACHE: Dict[str, Tuple[int, int, List[Dict[str, Any]]]] = {}
_DISK_INDEX_LOADED: bool = False


def reset_transcript_cache() -> None:
    """Clear in-memory transcript cache so next load rebuilds from disk shards."""
    global _DISK_INDEX_LOADED
    with _CACHE_LOCK:
        _MEM_TRANSCRIPT_CACHE.clear()
        _DISK_INDEX_LOADED = False


def transcript_cache_size() -> int:
    with _CACHE_LOCK:
        return len(_MEM_TRANSCRIPT_CACHE)


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

    if updated_shards or stale_keys:
        with file_lock(DATA_DIR / ".index.lock", timeout=1.5) as locked:
            if locked:
                for path_str, mtime_ns, size, parsed in updated_shards:
                    _save_single_conv_cache(path_str, mtime_ns, size, parsed)
                for k in stale_keys:
                    _remove_single_conv_cache(k)

    events.sort(key=lambda e: e["ts"])
    return events
