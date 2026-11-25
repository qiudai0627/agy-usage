#!/usr/bin/env bash
set -euo pipefail

# macOS Finder 双击启动器：一键安装/更新 + 启动后台 Web 监控台 + 启动顶部菜单栏小工具 + 打开网页
cd "$(dirname "$0")"
./install.sh

echo ""
echo "全部就绪，3 秒后可关闭此终端窗口..."
sleep 2
