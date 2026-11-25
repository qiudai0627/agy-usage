#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$ROOT_DIR/src"

echo "==> 1. Python 语法编译检查"
python3 -m py_compile "$SRC_DIR/core.py" "$SRC_DIR/statusline.py" "$SRC_DIR/web_ui.py" "$SRC_DIR/cli.py" "$ROOT_DIR/windows/tray_widget.pyw" "$ROOT_DIR/tests/test_suite.py"

echo "==> 2. Web UI HTML/SVG 属性安全检查"
SRC_DIR="$SRC_DIR" python3 - <<'PY'
import os, re, sys
sys.path.insert(0, os.environ["SRC_DIR"])
import web_ui
html = web_ui.DASHBOARD_HTML
assert "showTip(" not in html, "Forbidden inline showTip() found"
assert "onmouseenter=" not in html, "Forbidden inline onmouseenter= found"
assert "onmouseleave=" not in html, "Forbidden inline onmouseleave= found"
assert not re.search(r'onclick="\$\{', html), "Unsafe template interpolation inside onclick"
print("✓ HTML/SVG 模板属性安全检查通过")
PY

echo "==> 3. 全隔离合成沙箱端到端冒烟测试（不触碰真实家目录会话）"
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

echo '{"cwd":"/tmp","conversation_id":"synth-conv-001","model":{"id":"gemini-4-neon-high","display_name":"Gemini 4 Neon (High)","effort":"high"},"context_window":{"total_input_tokens":50000,"total_output_tokens":5000,"context_window_size":1048576,"used_percentage":5.2},"quota":{"gemini-5h":{"remaining_fraction":0.82,"reset_time":"2026-12-01T04:00:00Z","reset_in_seconds":10800},"gemini-weekly":{"remaining_fraction":0.9,"reset_time":"2026-12-01T00:00:00Z","reset_in_seconds":400000},"3p-5h":{"remaining_fraction":0.76,"reset_time":"2026-12-01T04:00:00Z","reset_in_seconds":10800},"3p-weekly":{"remaining_fraction":0.5,"reset_time":"2026-12-02T00:00:00Z","reset_in_seconds":480000}},"agent_state":"idle","plan_tier":"Pro","terminal_width":140}' \
  | AGY_DATA_DIR="$TMPAGY" AGY_USAGE_DATA_DIR="$TMPDATA" "$SRC_DIR/statusline.py"

TMPAGY="$TMPAGY" TMPDATA="$TMPDATA" SRC_DIR="$SRC_DIR" python3 - <<'PY'
import json, os, subprocess, sys
env = dict(os.environ, AGY_DATA_DIR=os.environ["TMPAGY"], AGY_USAGE_DATA_DIR=os.environ["TMPDATA"])
cli = os.path.join(os.environ["SRC_DIR"], "cli.py")
j = json.loads(subprocess.check_output([sys.executable, cli, "json", "-w", "all"], env=env))
assert j["quota"]["has_live_quota"] is True and len(j["quota"]["buckets"]) == 4
assert j["windows"]["all"]["calls"] == 2, j["windows"]["all"]
idx_path = os.path.join(os.environ["TMPDATA"], "transcript_index.json")
assert os.path.exists(idx_path), "transcript_index.json not created"
idx_raw = open(idx_path, encoding="utf-8").read()
assert "synth-conv-001" in idx_raw and len(json.loads(idx_raw)["files"]) == 1
subprocess.check_call([sys.executable, cli, "clean", "--keep-days", "30"], env=env, stdout=subprocess.DEVNULL)
subprocess.check_call([sys.executable, cli, "doctor", "--stale-days", "30"], env=env, stdout=subprocess.DEVNULL)
print("✓ 全隔离合成冒烟通过 (buckets=4, calls=2)")
PY

echo "==> 4. 运行单元测试套件 (刀 A & 刀 C 回归验证)"
python3 "$ROOT_DIR/tests/test_suite.py"
