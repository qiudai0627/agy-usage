#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_LINK="${HOME}/.local/bin/agy-usage"
APP_BUNDLE="${AGY_APP_DIR:-${HOME}/Applications}/AGY Usage.app"
PLIST="${HOME}/Library/LaunchAgents/local.agy.usage.menubar.plist"

echo "==> 卸载 agy-usage"
pkill -x "AGYUsageMenuBar" 2>/dev/null || true

if [ -x "$BIN_LINK" ]; then
  "$BIN_LINK" daemon stop || true
  "$BIN_LINK" uninstall-statusline || true
elif [ -x "$ROOT_DIR/src/cli.py" ]; then
  "$ROOT_DIR/src/cli.py" daemon stop || true
  "$ROOT_DIR/src/cli.py" uninstall-statusline || true
fi

if [ -L "$BIN_LINK" ]; then
  rm -f "$BIN_LINK"
  echo "✓ 已移除命令软链：$BIN_LINK"
fi

if [ -d "$APP_BUNDLE" ]; then
  rm -rf "$APP_BUNDLE"
  echo "✓ 已移除菜单栏应用：$APP_BUNDLE"
fi

if [ -f "$PLIST" ]; then
  rm -f "$PLIST"
  echo "✓ 已移除开机自启配置：$PLIST"
fi

echo "卸载完成（如需彻底删除历史快照缓存，可手动删除 ~/.cache/agy-usage）。"
