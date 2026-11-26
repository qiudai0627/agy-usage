#!/usr/bin/env bash
set -euo pipefail

# 支持两种模式：
# 1. 本地目录执行：./install.sh 或双击 Start-Mac.command
# 2. 远程一键安装：curl -fsSL https://raw.githubusercontent.com/<owner>/agy-usage/main/install.sh | bash

PORT="${AGY_USAGE_PORT:-18420}"
BIN_DIR="${HOME}/.local/bin"

SCRIPT_PATH="${BASH_SOURCE[0]:-}"
if [ -n "$SCRIPT_PATH" ] && [ -f "$(dirname "$SCRIPT_PATH")/src/cli.py" ]; then
  SOURCE_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
  if [ -d "$SOURCE_DIR/.git" ]; then
    ROOT_DIR="$SOURCE_DIR"
  else
    # 解压包安装（如在“桌面/下载”双击 Start-Mac.command）：自动同步至 ~/.local/share/agy-usage，
    # 避免触发 macOS 访问桌面/下载目录弹窗，且安装后可随时删除原解压包。
    ROOT_DIR="${HOME}/.local/share/agy-usage"
    if [ "$SOURCE_DIR" != "$ROOT_DIR" ]; then
      mkdir -p "$ROOT_DIR"
      cp -R "$SOURCE_DIR"/. "$ROOT_DIR"/
      xattr -cr "$ROOT_DIR" 2>/dev/null || true
    fi
  fi
else
  REPO_SLUG="${AGY_USAGE_REPO:-qiudai0627/agy-usage}"
  ROOT_DIR="${HOME}/.local/share/agy-usage"
  echo "==> 从 GitHub 拉取 ${REPO_SLUG} 到 ${ROOT_DIR}..."
  mkdir -p "$(dirname "$ROOT_DIR")"
  if command -v git >/dev/null 2>&1; then
    if [ -d "$ROOT_DIR/.git" ]; then
      git -C "$ROOT_DIR" pull --ff-only
    else
      rm -rf "$ROOT_DIR"
      git clone --depth 1 "https://github.com/${REPO_SLUG}.git" "$ROOT_DIR"
    fi
  else
    TMP_TAR="$(mktemp -d)"
    curl -fsSL "https://github.com/${REPO_SLUG}/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP_TAR"
    rm -rf "$ROOT_DIR"
    mv "$TMP_TAR"/agy-usage-* "$ROOT_DIR"
    rm -rf "$TMP_TAR"
  fi
fi

SRC_DIR="$ROOT_DIR/src"

echo "==> 安装 agy-usage（来源：$ROOT_DIR）"
chmod +x "$SRC_DIR/cli.py" "$SRC_DIR/core.py" "$SRC_DIR/statusline.py" \
         "$ROOT_DIR/verify.sh" "$ROOT_DIR/uninstall.sh" \
         "$ROOT_DIR/Start-Mac.command" \
         "$ROOT_DIR/macos/build-app.sh" \
         "$ROOT_DIR/scripts/package-release.sh"

mkdir -p "$BIN_DIR"
ln -sf "$SRC_DIR/cli.py" "$BIN_DIR/agy-usage"
echo "✓ 已链接命令：$BIN_DIR/agy-usage -> $SRC_DIR/cli.py"

"$BIN_DIR/agy-usage" install-statusline --stack
"$BIN_DIR/agy-usage" daemon restart --port "$PORT"

if [ "$(uname -s)" = "Darwin" ] && [ -x "$ROOT_DIR/macos/build-app.sh" ]; then
  "$ROOT_DIR/macos/build-app.sh"
  APP_BUNDLE="${AGY_APP_DIR:-${HOME}/Applications}/AGY Usage.app"
  if [ -d "$APP_BUNDLE" ]; then
    pkill -x "AGYUsageMenuBar" 2>/dev/null || true
    sleep 0.2
    launchctl asuser "$(id -u)" open "$APP_BUNDLE" 2>/dev/null || open "$APP_BUNDLE" || true
    echo "✓ 已启动 macOS 顶部菜单栏 + 右上角防刘海毛玻璃胶囊"
  fi
fi

echo ""
echo "安装完成！"
echo "  • Web 监控台  ：http://127.0.0.1:${PORT}"
echo "  • 终端查看    ：agy-usage  或  agy-usage watch"
echo "  • 桌面小工具  ：右上角悬浮胶囊 + 菜单栏 (~/Applications/AGY Usage.app)"
echo "  • 已开 agy 窗 ：输入 /statusline $SRC_DIR/statusline.py 立即同步"
