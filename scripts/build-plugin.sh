#!/usr/bin/env bash
set -euo pipefail

# Build self-contained AGY native plugin directory from single-source src/ modules (zero ../../src runtime deps).
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="$ROOT_DIR/plugins/agy-usage"

mkdir -p "$PLUGIN_DIR/scripts" "$PLUGIN_DIR/assets"

CORE_MODULES=(
  analytics.py
  instance_lock.py
  mcp_server.py
  notifications.py
  pure_query.py
  quota.py
  storage.py
  transcripts.py
)

for mod in "${CORE_MODULES[@]}"; do
  cp "$ROOT_DIR/src/$mod" "$PLUGIN_DIR/scripts/$mod"
done

cp "$ROOT_DIR/docs/assets/logo.png" "$PLUGIN_DIR/assets/logo.png"
chmod 755 "$PLUGIN_DIR/scripts/mcp_server.py"

echo "✓ Built self-contained plugin bundle at $PLUGIN_DIR (${#CORE_MODULES[@]} core modules synced)"

if command -v agy >/dev/null 2>&1; then
  echo "==> Running agy plugin validate --strict --json ..."
  agy plugin validate --strict --json "$PLUGIN_DIR"
  echo "✓ agy plugin validate --strict passed"
fi
