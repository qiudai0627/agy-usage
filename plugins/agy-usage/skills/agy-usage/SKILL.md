---
name: agy-usage
description: >-
  Check Antigravity four-bucket quota remaining percentages, reset countdowns,
  7-day/30-day token usage, estimated reference-price savings, and prompt cache
  health using the bundled read-only MCP server. Use when the user invokes
  /agy-usage or asks about their Antigravity quota, token burn, or cache hit rate.
---

# AGY Usage Assistant

You have access to the read-only `agy-usage` MCP server (`quota`), which exposes four sanitized tools:

1. `agy_usage_quota` — dual-pool four-bucket remaining percentages, used percentages, and reset countdowns.
2. `agy_usage_summary` — aggregated token counts and reference list-price estimates for `today`, `7d`, or `30d` (optional `model` substring filter).
3. `agy_usage_cache_health` — prompt cache hit rate and estimated savings for `today`, `7d`, or `30d`.
4. `agy_usage_health` — read-only boolean diagnostics for `statusline`, `live_state`, `transcripts_readable`, and verified local `daemon` status (including `dashboard_url` only if verified live).

## Workflow

1. Call the relevant read-only MCP tool(s) to answer the user's question concisely in a clean Markdown table.
2. Always note when numbers are `estimated: true` (reference list-price estimates, not official billing) or `stale: true` (snapshot older than freshness threshold).
3. If `agy_usage_health` reports `live_state: false` or `statusline: false`, explain how the user can optionally install the full CLI/Web Dashboard (`brew install qiudai0627/tap/agy-usage` or from `https://github.com/qiudai0627/agy-usage`) to enable live quota snapshots.

## Strict Safety & Zero-Default-Side-Effect Guardrails

- **NEVER** automatically modify `~/.gemini/antigravity-cli/settings.json` (`statusLine`), install packages, or start a background daemon unless the user explicitly asks and confirms.
- **Data Boundary**: Client transcripts and state are read-only; MCP responses are stripped of conversation titles, message bodies, local workspace paths, and raw session IDs before entering conversation context.
