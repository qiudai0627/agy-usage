#!/usr/bin/env bash
set -euo pipefail

# 一键生成干净可分享的 zip 发布包（显式文件清单 + 严格隐私与凭证门禁扫描）
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_ZIP="${1:-${HOME}/.cache/agy-usage/agy-usage-release.zip}"

STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT
PKG_DIR="$STAGE_DIR/agy-usage"
mkdir -p "$PKG_DIR/src" "$PKG_DIR/macos" "$PKG_DIR/windows" "$PKG_DIR/scripts" \
         "$PKG_DIR/docs/assets" "$PKG_DIR/tests" "$PKG_DIR/.github/workflows"

# Explicit file manifest (never globs untracked private scripts)
ROOT_FILES=(
  README.md
  README_EN.md
  README_ZH-TW.md
  LICENSE
  .gitignore
  install.sh
  uninstall.sh
  install.ps1
  uninstall.ps1
  verify.sh
  Start-Mac.command
  Start-Windows.bat
)
for f in "${ROOT_FILES[@]}"; do
  cp "$ROOT_DIR/$f" "$PKG_DIR/$f"
done

SRC_FILES=(cli.py core.py i18n.py statusline.py web_ui.py)
for f in "${SRC_FILES[@]}"; do
  cp "$ROOT_DIR/src/$f" "$PKG_DIR/src/$f"
done

ASSET_FILES=(
  logo.png
  overview-4buckets.svg
  overview-4buckets-en.svg
  themes-3way.svg
  themes-3way-en.svg
  macos-pill.svg
  macos-pill-en.svg
  windows-pill.svg
  windows-pill-en.svg
  terminal-bar.svg
  terminal-bar-en.svg
  empty-to-active.svg
  empty-to-active-en.svg
)
for f in "${ASSET_FILES[@]}"; do
  cp "$ROOT_DIR/docs/assets/$f" "$PKG_DIR/docs/assets/$f"
done

cp "$ROOT_DIR/.github/workflows/ci.yml" "$PKG_DIR/.github/workflows/ci.yml"
cp "$ROOT_DIR/macos/MenuBarApp.swift" "$ROOT_DIR/macos/build-app.sh" "$PKG_DIR/macos/"
cp "$ROOT_DIR/windows/tray_widget.pyw" "$PKG_DIR/windows/"
cp "$ROOT_DIR/scripts/package-release.sh" "$PKG_DIR/scripts/"
cp "$ROOT_DIR/tests/test_suite.py" "$PKG_DIR/tests/"

chmod 755 "$PKG_DIR/install.sh" "$PKG_DIR/uninstall.sh" "$PKG_DIR/verify.sh" \
          "$PKG_DIR/Start-Mac.command" "$PKG_DIR/macos/build-app.sh" \
          "$PKG_DIR/scripts/package-release.sh" "$PKG_DIR/src/"*.py "$PKG_DIR/tests/test_suite.py"

echo "==> 执行隐私、个人路径与凭证零泄露门禁扫描..."
PKG_DIR="$PKG_DIR" CURRENT_USER="$(id -un)" python3 - <<'PY'
import os, re, struct, sys
from pathlib import Path

pkg = Path(os.environ["PKG_DIR"])
cur_user = os.environ.get("CURRENT_USER", "").strip()

patterns = [
    ("macOS 个人路径", re.compile(r"/Users/[A-Za-z0-9._-]+")),
    ("Linux 个人路径", re.compile(r"/home/(?!runner\b)[A-Za-z0-9._-]+")),
    ("Windows 个人路径", re.compile(r"C:\\Users\\[A-Za-z0-9._-]+", re.IGNORECASE)),
    ("私人邮箱", re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.com\b|localhost\b|users\.noreply\.github\.com\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("凭证密钥", re.compile(r"(AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{25,}|sk-[A-Za-z0-9]{25,}|ya29\.[0-9A-Za-z_-]+|BEGIN [A-Z ]*PRIVATE KEY)")),
]
if cur_user and cur_user.lower() not in ("runner", "root", "ubuntu", "admin", "user"):
    patterns.append(("本机用户名", re.compile(rf"\b{re.escape(cur_user)}\b", re.IGNORECASE)))


def check_png_chunks(path: Path):
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return [("PNG 文件头损坏", "invalid signature")]
    pos = 8
    issues = []
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8].decode("latin1", errors="replace")
        if ctype in ("tEXt", "iTXt", "zTXt", "eXIf"):
            issues.append(("PNG 隐私元数据块", ctype))
        pos += 12 + length
    return issues


hits = []
for p in sorted(pkg.rglob("*")):
    if p.is_symlink():
        hits.append((str(p), "禁止包含软链接"))
        continue
    if not p.is_file():
        continue
    rel = str(p.relative_to(pkg))
    if p.suffix.lower() == ".png":
        for label, detail in check_png_chunks(p):
            hits.append((rel, f"{label}: {detail}"))
        continue
    text = p.read_text(encoding="utf-8", errors="strict")
    for label, rx in patterns:
        m = rx.search(text)
        if m:
            hits.append((rel, f"{label}: {m.group(0)}"))

if hits:
    for rel, detail in hits:
        sys.stderr.write(f"✖ 门禁阻断 [{rel}] -> {detail}\n")
    sys.exit(1)
print("✓ 隐私与凭证门禁通过（0 个人路径 / 0 用户名 / 0 私人邮箱 / 0 密钥 / 0 图片元数据）")
PY

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
