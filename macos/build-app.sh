#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="AGY Usage"
OUT_DIR="${AGY_APP_DIR:-${HOME}/Applications}"
APP_BUNDLE="${OUT_DIR}/${APP_NAME}.app"

if ! command -v swiftc >/dev/null 2>&1; then
  echo "⚠ 未检测到 swiftc（可通过 xcode-select --install 安装），跳过编译菜单栏小工具。"
  exit 0
fi

mkdir -p "${APP_BUNDLE}/Contents/MacOS" "${APP_BUNDLE}/Contents/Resources"

cat > "${APP_BUNDLE}/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>AGYUsageMenuBar</string>
    <key>CFBundleIdentifier</key>
    <string>local.agy.usage.menubar</string>
    <key>CFBundleName</key>
    <string>AGY Usage</string>
    <key>CFBundleDisplayName</key>
    <string>AGY Usage</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.1.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSAppTransportSecurity</key>
    <dict>
        <key>NSAllowsLocalNetworking</key>
        <true/>
    </dict>
</dict>
</plist>
PLIST

echo "==> 编译 macOS 菜单栏与防刘海悬浮胶囊应用: ${APP_BUNDLE}"
LOGO_PNG="${SCRIPT_DIR}/../docs/assets/logo.png"
if [ -f "${LOGO_PNG}" ] && command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
  TMP_ICONSET="$(mktemp -d)/AppIcon.iconset"
  mkdir -p "${TMP_ICONSET}"
  for sz in 16 32 128 256 512; do
    sips -z "${sz}" "${sz}" "${LOGO_PNG}" --out "${TMP_ICONSET}/icon_${sz}x${sz}.png" >/dev/null 2>&1 || true
    sz2=$((sz * 2))
    sips -z "${sz2}" "${sz2}" "${LOGO_PNG}" --out "${TMP_ICONSET}/icon_${sz}x${sz}@2x.png" >/dev/null 2>&1 || true
  done
  iconutil -c icns "${TMP_ICONSET}" -o "${APP_BUNDLE}/Contents/Resources/AppIcon.icns" >/dev/null 2>&1 || true
  rm -rf "$(dirname "${TMP_ICONSET}")"
fi

swiftc -O "${SCRIPT_DIR}/MenuBarApp.swift" \
  -framework Cocoa \
  -o "${APP_BUNDLE}/Contents/MacOS/AGYUsageMenuBar"

xattr -cr "${APP_BUNDLE}" 2>/dev/null || true
codesign --force --deep --sign - "${APP_BUNDLE}" >/dev/null 2>&1 || true

echo "✓ 已生成并签名应用: ${APP_BUNDLE}"
