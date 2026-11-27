#!/usr/bin/env python3
"""Public facade re-exporting agy-usage's modular core engine."""

from __future__ import annotations

from pathlib import Path
import sys

_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from analytics import (  # noqa: E402,F401
    _safe_csv_cell,
    build_analytics,
    build_insights,
    compute_week_over_week,
    export_sessions_csv,
    get_conversation_detail,
    summarize_events,
)
from maintenance import (  # noqa: E402,F401
    append_web_log,
    clean_cache,
    rotate_web_log,
    run_doctor,
)
from notifications import (  # noqa: E402,F401
    evaluate_quota_notifications,
    get_preferences,
    set_preferences,
)
from quota import (  # noqa: E402,F401
    analyze_quota_buckets,
    compact_quota_snapshots,
    extract_remaining_fraction,
    infer_bucket_meta,
    load_live_state,
    load_quota_snapshots,
    record_quota_snapshot,
    save_manual_quota,
)
from storage import (  # noqa: E402,F401
    AGY_DIR,
    APP_DIR,
    BRAIN_DIR,
    CONV_CACHE_DIR,
    CST,
    DAILY_ARCHIVE_FILE,
    DATA_DIR,
    LIVE_STATE_FILE,
    META_CACHE,
    MODEL_PRICING_PER_1M,
    NOTIFY_STATE_FILE,
    POOL_LABELS,
    PREFERENCES_FILE,
    SETTINGS_FILE,
    SNAPSHOTS_FILE,
    SUMMARY_DB,
    TRANSCRIPT_INDEX_FILE,
    WEB_LOG_FILE,
    atomic_replace,
    atomic_write_text,
    classify_model_pool,
    discover_settings_file,
    ensure_data_dir,
    estimate_cache_saved_usd,
    estimate_cost_usd,
    file_lock,
    fmt_cst,
    fmt_duration,
    fmt_tokens,
    get_local_tz,
    get_model_rates,
    get_tz_label,
    parse_iso_dt,
    shorten_workspace,
)
from transcripts import (  # noqa: E402,F401
    extract_tool_names,
    load_agy_settings,
    load_conversation_metadata,
    load_transcript_events,
    reset_transcript_cache,
    transcript_cache_size,
)
