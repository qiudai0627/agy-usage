#!/usr/bin/env python3
"""Zero-dependency multilingual (11-language) loader for agy-usage.

Loads structured locale dictionaries from `src/locales/<lang>.json`:
  zh-CN (简体中文), zh-TW (繁體中文), en (English), ja (日本語), ko (한국어),
  es (Español), pt-BR (Português), de (Deutsch), fr (Français), ru (Русский), vi (Tiếng Việt)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

LOCALES_DIR = Path(__file__).resolve().parent / "locales"

LANG_OPTIONS: List[Tuple[str, str]] = [
    ("zh-CN", "简体中文"),
    ("zh-TW", "繁體中文"),
    ("en", "English"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("es", "Español"),
    ("pt-BR", "Português"),
    ("de", "Deutsch"),
    ("fr", "Français"),
    ("ru", "Русский"),
    ("vi", "Tiếng Việt"),
]


def _load_all_locales() -> Dict[str, Dict[str, Any]]:
    catalog: Dict[str, Dict[str, Any]] = {}
    for code, _ in LANG_OPTIONS:
        path = LOCALES_DIR / f"{code}.json"
        catalog[code] = json.loads(path.read_text(encoding="utf-8"))
    return catalog


WEB_I18N: Dict[str, Dict[str, Any]] = _load_all_locales()


def resolve_cli_lang(override: str | None = None) -> str:
    """Resolve terminal/widget language (`zh-CN`, `zh-TW`, or `en`). Defaults to `zh-CN` when unset."""
    raw = (override or os.environ.get("AGY_USAGE_LANG") or "").strip().lower()
    if not raw:
        return "zh-CN"
    if raw in ("zh-tw", "zh_tw", "zh-hk", "zh_hk", "zh-hant", "tw", "hant"):
        return "zh-TW"
    if raw.startswith("zh"):
        return "zh-CN"
    return "en"


WEB_I18N_JS = json.dumps(WEB_I18N, ensure_ascii=False, separators=(",", ":"))
LANG_OPTIONS_JS = json.dumps(LANG_OPTIONS, ensure_ascii=False, separators=(",", ":"))
