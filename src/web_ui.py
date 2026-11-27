#!/usr/bin/env python3
"""Zero-CDN Web Dashboard asset assembler (`src/web/*` -> single local HTML response)."""

from __future__ import annotations

from pathlib import Path

from i18n import LANG_OPTIONS_JS, WEB_I18N_JS

WEB_DIR = Path(__file__).resolve().parent / "web"


def _build_dashboard_html() -> tuple[str, str]:
    logo_uri = (WEB_DIR / "logo.b64").read_text(encoding="utf-8").strip()
    styles_css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")
    charts_js = (WEB_DIR / "charts.js").read_text(encoding="utf-8")
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    share_card_js = (WEB_DIR / "share_card.js").read_text(encoding="utf-8")
    template = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    html = (
        template.replace("__STYLES_CSS__", styles_css)
        .replace("__CHARTS_JS__", charts_js)
        .replace("__APP_JS__", app_js)
        .replace("__SHARE_CARD_JS__", share_card_js)
        .replace("__LANG_OPTIONS_JSON__", LANG_OPTIONS_JS)
        .replace("__WEB_I18N_JSON__", WEB_I18N_JS)
        .replace("__LOGO_DATA_URI__", logo_uri)
    )
    return logo_uri, html


LOGO_DATA_URI, DASHBOARD_HTML = _build_dashboard_html()
