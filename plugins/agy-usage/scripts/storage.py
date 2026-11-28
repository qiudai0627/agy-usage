#!/usr/bin/env python3
"""Paths, timezone resolution, cross-platform file locking, atomic I/O, and pricing helpers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone, tzinfo
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Dict, Iterator, List, Optional, Tuple

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


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


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
MODEL_PRICING_PER_1M: Dict[str, Tuple[float, float, float]] = {
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
