# AGY Usage

Read-only local quota, token usage, and prompt cache health monitor for Antigravity.

## What's Included

- **Zero-dependency `stdio` MCP Server (`quota`)** — Python 3.9+ standard library only, launched on demand by the host and exits cleanly on `stdin EOF`. Exposes 4 strictly sanitized read-only tools:
  - `agy_usage_summary` — token usage & estimated reference-price summary (`today` / `7d` / `30d`, optional model filter)
  - `agy_usage_quota` — dual-pool four-bucket quota remaining percentages and reset countdowns
  - `agy_usage_cache_health` — prompt cache hit rate and estimated savings
  - `agy_usage_health` — boolean health check of statusline, live state, transcripts, and verified local dashboard daemon
- **Skill (`/agy-usage`)** — inspect quotas, token burn, and cache health directly inside chat without modifying client files or running background daemons by default.

## Three-Layer Data Boundary

1. **Antigravity Client Data (Read-Only, Zero Injection)**: Reads local Antigravity transcripts and state files only. No CDP injection, no `--remote-debugging-port`, no client file patching, and no credential/OAuth access.
2. **Tool-Owned Local State**: Installing this plugin has zero default side effects — it does not modify `settings.json` (`statusLine`) or auto-start any background daemon. Optional CLI/dashboard features store their own cache and preferences under `~/.cache/agy-usage/` (or `%LOCALAPPDATA%\agy-usage`).
3. **MCP Conversation Context**: Sanitized aggregate metrics returned by the MCP tools enter the host model conversation context. Conversation titles, message bodies, previews, local workspace paths, and raw session IDs are stripped by default.

## Requirements

- Python 3.9+ (`python3` in `PATH`)
- Optional full Web Dashboard, TUI, and macOS/Windows floating pill: see [github.com/qiudai0627/agy-usage](https://github.com/qiudai0627/agy-usage)
