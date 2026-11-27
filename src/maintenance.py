#!/usr/bin/env python3
"""In-place log rotation, cache compaction, and health diagnostics (`doctor` / `clean`)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from quota import compact_quota_snapshots, load_live_state
from storage import (
    APP_DIR,
    CONV_CACHE_DIR,
    DAILY_ARCHIVE_FILE,
    DATA_DIR,
    SNAPSHOTS_FILE,
    TRANSCRIPT_INDEX_FILE,
    WEB_LOG_FILE,
    _discover_agy_dirs,
    atomic_write_text,
    discover_settings_file,
    ensure_data_dir,
    file_lock,
    fmt_cst,
    parse_iso_dt,
)
from transcripts import (
    load_agy_settings,
    load_conversation_metadata,
    load_transcript_events,
    reset_transcript_cache,
    transcript_cache_size,
)


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
    ensure_data_dir()
    before_total = _dir_size(DATA_DIR)

    snap_res = compact_quota_snapshots(keep_days=keep_days)
    rotate_web_log(max_bytes=512 * 1024, keep_bytes=128 * 1024)

    now_epoch = time.time()
    for tmp_f in DATA_DIR.glob("*.tmp"):
        try:
            if now_epoch - tmp_f.stat().st_mtime > 600:
                tmp_f.unlink()
        except OSError:
            pass

    if reset_index:
        reset_transcript_cache()
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
    return {
        "cache_dir": str(DATA_DIR),
        "bytes_before": before_total,
        "bytes_after": after_total,
        "bytes_freed": max(0, before_total - after_total) + backups_freed,
        "snapshots": snap_res,
        "index_entries": transcript_cache_size(),
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
    """Inspect Antigravity & agy-usage health first (read-only); optionally repair own pipeline (`--fix`)."""
    import sys as _sys
    import urllib.request

    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=max(1, stale_days))
    orphan_cutoff = now - timedelta(days=1)

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

    brain_ids: Dict[str, Path] = {}
    conv_db_sizes: Dict[str, int] = defaultdict(int)
    total_agy_bytes = 0

    for root in agy_dirs:
        total_agy_bytes += _dir_size(root / "brain") + _dir_size(root / "conversations")
        bdir = root / "brain"
        if bdir.exists():
            for d in bdir.iterdir():
                if d.is_dir() and d.name not in brain_ids:
                    brain_ids[d.name] = d
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
        has_transcript = cid in brain_ids and (brain_ids[cid] / ".system_generated/logs/transcript.jsonl").exists()
        steps = int(m.get("step_count") or 0)
        b_size = _dir_size(brain_ids[cid]) if cid in brain_ids else 0
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

    for cid, bpath in brain_ids.items():
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
        "own_cache_bytes": _dir_size(DATA_DIR),
        "index_cached_files": transcript_cache_size(),
        "total_conversations": len(meta),
        "empty_db_entries": empty_db_entries,
        "orphan_brain_dirs": orphan_brain_dirs,
        "stale_days": stale_days,
        "stale_sessions": stale_sessions,
        "ls_api_available": bool(ls_addr and csrf),
        "deleted_ids": deleted_ids,
        "delete_errors": delete_errors,
    }
