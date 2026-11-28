#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$ROOT_DIR/src"

echo "==> 1. Python 语法编译与脚本编码门禁检查"
python3 -m py_compile "$SRC_DIR/"*.py "$ROOT_DIR/windows/tray_widget.pyw" "$ROOT_DIR/tests/test_suite.py"

ROOT_DIR="$ROOT_DIR" SRC_DIR="$SRC_DIR" python3 - <<'PY'
import os, re, sys
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
sys.path.insert(0, os.environ["SRC_DIR"])
import web_ui

html = web_ui.DASHBOARD_HTML
assert "showTip(" not in html, "Forbidden inline showTip() found"
assert "onmouseenter=" not in html, "Forbidden inline onmouseenter= found"
assert "onmouseleave=" not in html, "Forbidden inline onmouseleave= found"
assert "tipEl.innerHTML" not in html, "Forbidden tipEl.innerHTML XSS sink found"
assert not re.search(r'onclick="\$\{', html), "Unsafe template interpolation inside onclick"

for ps_name in ("install.ps1", "uninstall.ps1"):
    b = (root / ps_name).read_bytes()
    assert b.startswith(b"\xef\xbb\xbf"), f"{ps_name} must start with UTF-8 BOM for Windows PowerShell 5.1"
    assert not b[3:].startswith(b"\xef\xbb\xbf"), f"{ps_name} must have EXACTLY ONE UTF-8 BOM (found duplicate BOM)"
    body = b[3:].decode("utf-8")
    assert "\ufeff" not in body, f"{ps_name} body must not contain extra U+FEFF"
    assert body.startswith("$ErrorActionPreference"), f"{ps_name} body must start directly with PowerShell code"
bat_b = (root / "Start-Windows.bat").read_bytes()
assert not bat_b.startswith(b"\xef\xbb\xbf"), "Start-Windows.bat must NOT start with UTF-8 BOM"
assert "\ufeff" not in bat_b.decode("utf-8"), "Start-Windows.bat must NOT contain U+FEFF"
print("✓ HTML/SVG 安全与 Windows PowerShell/BAT 编码检查通过")
PY

echo "==> 2. 全隔离合成沙箱端到端冒烟测试（不触碰真实家目录会话）"
TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT
TMPAGY="$TMPROOT/agy"
TMPDATA="$TMPROOT/cache"
mkdir -p "$TMPAGY/brain/synth-conv-001/.system_generated/logs" "$TMPDATA"

cat > "$TMPAGY/brain/synth-conv-001/.system_generated/logs/transcript.jsonl" <<'JSONL'
{"step_index":1,"created_at":"2026-11-25T08:00:00Z","model":"gemini-4-neon-high","input_tokens":12000,"cache_read_tokens":48000,"output_tokens":900}
{"step_index":2,"created_at":"2026-11-25T08:05:00Z","model":"claude-opus-5-5-high","input_tokens":4000,"cache_read_tokens":16000,"output_tokens":600}
JSONL

echo '{"statusLine":{"type":"command","command":"statusline.py","enabled":true,"stack_with_default":true}}' > "$TMPAGY/settings.json"

echo '{"cwd":"/tmp","conversation_id":"synth-conv-001","model":{"id":"gemini-4-neon-high","display_name":"Gemini 4 Neon (High)","effort":"high"},"context_window":{"total_input_tokens":50000,"total_output_tokens":5000,"context_window_size":1048576,"used_percentage":5.2},"quota":{"gemini-5h":{"remaining_fraction":0.82,"reset_time":"2099-12-01T04:00:00Z","reset_in_seconds":10800},"gemini-weekly":{"remaining_fraction":0.9,"reset_time":"2099-12-07T00:00:00Z","reset_in_seconds":400000},"3p-5h":{"remaining_fraction":0.76,"reset_time":"2099-12-01T04:00:00Z","reset_in_seconds":10800},"3p-weekly":{"remaining_fraction":0.5,"reset_time":"2099-12-06T00:00:00Z","reset_in_seconds":480000}},"agent_state":"idle","plan_tier":"Pro","terminal_width":140}' \
  | AGY_DATA_DIR="$TMPAGY" AGY_USAGE_DATA_DIR="$TMPDATA" AGY_USAGE_SUPPRESS_OS_NOTIFY=1 "$SRC_DIR/statusline.py"

TMPAGY="$TMPAGY" TMPDATA="$TMPDATA" SRC_DIR="$SRC_DIR" python3 - <<'PY'
import glob, json, os, subprocess, sys
env = dict(
    os.environ,
    AGY_DATA_DIR=os.environ["TMPAGY"],
    AGY_USAGE_DATA_DIR=os.environ["TMPDATA"],
    AGY_USAGE_SUPPRESS_OS_NOTIFY="1",
)
cli = os.path.join(os.environ["SRC_DIR"], "cli.py")
j = json.loads(subprocess.check_output([sys.executable, cli, "json", "-w", "all"], env=env))
assert j["quota"]["has_live_quota"] is True and len(j["quota"]["buckets"]) == 4
assert j["windows"]["all"]["calls"] == 2, j["windows"]["all"]
assert "week_over_week" in j and "notifications" in j
shards = glob.glob(os.path.join(os.environ["TMPDATA"], "conv_cache", "*.json"))
assert len(shards) == 1, f"Expected 1 conv_cache shard, got {shards}"
assert "synth-conv-001" in open(shards[0], encoding="utf-8").read()
subprocess.check_call([sys.executable, cli, "clean", "--keep-days", "30"], env=env, stdout=subprocess.DEVNULL)
subprocess.check_call([sys.executable, cli, "doctor", "--stale-days", "30"], env=env, stdout=subprocess.DEVNULL)
print("✓ 全隔离合成冒烟通过 (buckets=4, calls=2, shards=1)")
PY

echo "==> 3. 运行全量单元测试套件 (核心回归 + v1.5.0 G02-G05 插件/MCP/单实例锁验收)"
python3 "$ROOT_DIR/tests/test_suite.py"
python3 "$ROOT_DIR/tests/test_v15_plugin.py"

if command -v agy >/dev/null 2>&1; then
  echo "==> 4. 运行官方插件严格校验 (agy plugin validate --strict --json)"
  agy plugin validate --strict --json "$ROOT_DIR/plugins/agy-usage" >/dev/null
  echo "✓ agy plugin validate --strict 通过"
fi
