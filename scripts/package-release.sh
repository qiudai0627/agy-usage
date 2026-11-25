#!/usr/bin/env bash
set -euo pipefail

# 一键生成干净可分享的 zip 发布包（内置严格隐私与个人路径零泄露门禁扫描）
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_ZIP="${1:-${HOME}/.cache/agy-usage/agy-usage-release.zip}"

STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT
PKG_DIR="$STAGE_DIR/agy-usage"
mkdir -p "$PKG_DIR/src" "$PKG_DIR/macos" "$PKG_DIR/windows" "$PKG_DIR/scripts" "$PKG_DIR/.github/workflows"

cp "$ROOT_DIR/README.md" \
   "$ROOT_DIR/LICENSE" \
   "$ROOT_DIR/.gitignore" \
   "$ROOT_DIR/install.sh" \
   "$ROOT_DIR/uninstall.sh" \
   "$ROOT_DIR/install.ps1" \
   "$ROOT_DIR/uninstall.ps1" \
   "$ROOT_DIR/verify.sh" \
   "$ROOT_DIR/Start-Mac.command" \
   "$ROOT_DIR/Start-Windows.bat" \
   "$PKG_DIR/"

cp "$ROOT_DIR/.github/workflows/ci.yml" "$PKG_DIR/.github/workflows/"
cp "$ROOT_DIR/src/"*.py "$PKG_DIR/src/"
cp "$ROOT_DIR/macos/MenuBarApp.swift" "$ROOT_DIR/macos/build-app.sh" "$PKG_DIR/macos/"
cp "$ROOT_DIR/windows/tray_widget.pyw" "$PKG_DIR/windows/"
cp "$ROOT_DIR/scripts/package-release.sh" "$PKG_DIR/scripts/"

chmod 755 "$PKG_DIR/install.sh" "$PKG_DIR/uninstall.sh" "$PKG_DIR/verify.sh" \
          "$PKG_DIR/Start-Mac.command" "$PKG_DIR/macos/build-app.sh" \
          "$PKG_DIR/scripts/package-release.sh" "$PKG_DIR/src/"*.py

echo "==> 执行隐私与个人路径零泄露门禁扫描..."
CURRENT_USER="$(id -un)"
USER_PREFIX="/Users/"
WIN_PREFIX='C:\\Users\\'
PATTERN="(${USER_PREFIX}[A-Za-z0-9._-]+|${WIN_PREFIX}[A-Za-z0-9._-]+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}|${CURRENT_USER})"

if grep -rnE "$PATTERN" "$PKG_DIR"; then
  echo "✖ 阻断打包：检测到疑似个人路径、本机用户名或私人邮箱字符串！" >&2
  exit 1
fi
echo "✓ 隐私门禁通过（0 个人路径 / 0 本机用户名 / 0 邮箱 / 0 历史数据）"

mkdir -p "$(dirname "$OUT_ZIP")"
rm -f "$OUT_ZIP"
STAGE_DIR="$STAGE_DIR" OUT_ZIP="$OUT_ZIP" python3 - <<'PY'
import os, stat, zipfile
stage = os.environ["STAGE_DIR"]
out_zip = os.environ["OUT_ZIP"]
with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(os.path.join(stage, "agy-usage")):
        dirs.sort()
        files.sort()
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, stage)
            st = os.stat(full)
            zi = zipfile.ZipInfo(rel)
            zi.external_attr = (stat.S_IMODE(st.st_mode) | stat.S_IFREG) << 16
            with open(full, "rb") as fh:
                zf.writestr(zi, fh.read(), zipfile.ZIP_DEFLATED)
PY
echo "✓ 已生成跨平台干净分享包: $OUT_ZIP ($(du -h "$OUT_ZIP" | awk '{print $1}'))"
