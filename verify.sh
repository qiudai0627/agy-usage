#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$ROOT_DIR/src"

echo "==> 1. Python 语法编译检查"
python3 -m py_compile "$SRC_DIR/core.py" "$SRC_DIR/statusline.py" "$SRC_DIR/web_ui.py" "$SRC_DIR/cli.py" "$ROOT_DIR/windows/tray_widget.pyw"

echo "==> 2. Web UI HTML/SVG 属性安全检查（防止内联引号截断乱码）"
SRC_DIR="$SRC_DIR" python3 - <<'PY'
import os, re, sys
sys.path.insert(0, os.environ["SRC_DIR"])
import web_ui
html = web_ui.DASHBOARD_HTML
assert "showTip(" not in html, "Forbidden inline showTip() found in DASHBOARD_HTML"
assert "onmouseenter=" not in html, "Forbidden inline onmouseenter= found in DASHBOARD_HTML"
assert "onmouseleave=" not in html, "Forbidden inline onmouseleave= found in DASHBOARD_HTML"
assert not re.search(r'onclick="\$\{', html), "Unsafe template interpolation inside onclick"
print("✓ HTML/SVG 模板属性安全检查通过")
PY

echo "==> 3. 隔离环境 statusLine + API 端到端冒烟测试"
TMPDATA="$(mktemp -d)"
trap 'rm -rf "$TMPDATA"' EXIT

echo '{"cwd":"/tmp","conversation_id":"smoke","model":{"id":"gemini-4-neon-high","display_name":"Gemini 4 Neon (High)","effort":"high"},"context_window":{"total_input_tokens":50000,"total_output_tokens":5000,"context_window_size":1048576,"used_percentage":5.2},"quota":{"gemini-weekly":{"remaining_fraction":0.9,"reset_time":"2026-12-01T00:00:00Z","reset_in_seconds":400000},"3p-weekly":{"remaining_fraction":0.5,"reset_time":"2026-12-02T00:00:00Z","reset_in_seconds":480000}},"agent_state":"idle","plan_tier":"Google AI Ultra","terminal_width":140}' \
  | AGY_USAGE_DATA_DIR="$TMPDATA" "$SRC_DIR/statusline.py"

TMPDATA="$TMPDATA" SRC_DIR="$SRC_DIR" python3 - <<'PY'
import json, os, subprocess, sys, time, urllib.request
env = dict(os.environ, AGY_USAGE_DATA_DIR=os.environ["TMPDATA"])
cli = os.path.join(os.environ["SRC_DIR"], "cli.py")
j = json.loads(subprocess.check_output([sys.executable, cli, "json", "-w", "7d"], env=env))
assert j["quota"]["has_live_quota"] is True and len(j["quota"]["buckets"]) == 2
p = subprocess.Popen([sys.executable, cli, "web", "--port", "18769", "--no-open"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
try:
    for _ in range(25):
        try:
            html = urllib.request.urlopen("http://127.0.0.1:18769/", timeout=1).read().decode()
            st = json.loads(urllib.request.urlopen("http://127.0.0.1:18769/api/stats?window=7d", timeout=1).read().decode())
            assert "Antigravity" in html and len(st["quota"]["buckets"]) == 2
            print("✓ verify.sh 全部通过 (buckets=%d, html=%dB)" % (len(st["quota"]["buckets"]), len(html)))
            break
        except Exception:
            time.sleep(0.15)
    else:
        raise RuntimeError("smoke web server timeout")
finally:
    p.terminate()
    p.wait(timeout=3)
PY
