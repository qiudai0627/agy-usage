#!/usr/bin/env python3
"""v1.5.0 G02-G05 acceptance tests: pure-query sanitization, self-contained plugin, single-instance lock, MCP stdio."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
PLUGIN_DIR = ROOT_DIR / "plugins" / "agy-usage"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _seed_sensitive_sandbox(root: Path) -> tuple[Path, Path]:
    agy_dir = root / "agy"
    data_dir = root / "cache"
    conv_id = "conv-secret-uuid-9999"
    log_dir = agy_dir / "brain" / conv_id / ".system_generated" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (agy_dir / "cache").mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    (log_dir / "transcript.jsonl").write_text(
        json.dumps(
            {
                "step_index": 1,
                "created_at": "2026-11-28T08:00:00Z",
                "model": "gemini-4-neon-high",
                "input_tokens": 10000,
                "cache_read_tokens": 40000,
                "output_tokens": 800,
            }
        )
        + "\n"
        + "NOT_VALID_JSON_LINE\n",
        encoding="utf-8",
    )
    (agy_dir / "cache" / "conversation_metadata.json").write_text(
        json.dumps(
            {
                "conversations": {
                    conv_id: {
                        "summary": {
                            "Title": "SECRET_PAYROLL_TITLE",
                            "Preview": "SECRET_BODY_SNIPPET",
                            "WorkspaceURIs": ["file:///tmp/top-secret-repo"],
                            "NumSteps": 1,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    # Critical remaining_fraction=0.02 would trigger notification if dispatched!
    (data_dir / "live_state.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-11-28T09:00:00Z",
                "conversation_id": conv_id,
                "conversation_title": "SECRET_PAYROLL_TITLE",
                "quota": {
                    "gemini-5h": {"remaining_fraction": 0.02, "reset_time": "2099-12-01T04:00:00Z", "reset_in_seconds": 3600},
                    "gemini-weekly": {"remaining_fraction": 0.85, "reset_time": "2099-12-07T00:00:00Z", "reset_in_seconds": 400000},
                    "3p-5h": {"remaining_fraction": 0.90, "reset_time": "2099-12-01T04:00:00Z", "reset_in_seconds": 3600},
                    "3p-weekly": {"remaining_fraction": 0.70, "reset_time": "2099-12-06T00:00:00Z", "reset_in_seconds": 480000},
                },
            }
        ),
        encoding="utf-8",
    )
    return agy_dir, data_dir


class TestV15Gates(unittest.TestCase):
    def test_g02_and_g05_mcp_stdio_protocol_and_sanitization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agy_dir, data_dir = _seed_sensitive_sandbox(root)
            # Copy plugin into completely isolated directory (G03: zero ../../src runtime deps)
            iso_plugin = root / "isolated-plugin"
            shutil.copytree(PLUGIN_DIR, iso_plugin)
            mcp_script = iso_plugin / "scripts" / "mcp_server.py"

            env = dict(
                os.environ,
                AGY_DATA_DIR=str(agy_dir),
                AGY_USAGE_DATA_DIR=str(data_dir),
                AGY_USAGE_SUPPRESS_OS_NOTIFY="1",
            )
            proc = subprocess.Popen(
                [sys.executable, str(mcp_script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            assert proc.stdin and proc.stdout and proc.stderr

            frames = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "ping"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "agy_usage_summary", "arguments": {"window": "30d"}}},
                {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "agy_usage_quota", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "agy_usage_cache_health", "arguments": {"window": "30d"}}},
                {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "agy_usage_health", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "agy_usage_summary", "arguments": {"window": "invalid"}}},
                {"jsonrpc": "2.0", "id": 9, "method": "nonexistent/method"},
            ]
            raw_in = "\n".join(json.dumps(f) for f in frames) + "\n{broken json\n" + ("x" * 70000) + "\n"
            out_bytes, err_bytes = proc.communicate(raw_in.encode("utf-8"), timeout=10)
            self.assertEqual(proc.returncode, 0, err_bytes.decode("utf-8", errors="replace"))

            out_text = out_bytes.decode("utf-8")
            self.assertNotIn("Content-Length:", out_text)
            lines = [ln for ln in out_text.splitlines() if ln.strip()]
            # 9 requests with id + 1 parse error + 1 oversized error = 11 responses (notification produces 0!)
            self.assertEqual(len(lines), 11, f"Unexpected response count: {lines}")
            by_id = {}
            for ln in lines:
                obj = json.loads(ln)
                if obj.get("id") is not None:
                    by_id[obj["id"]] = obj

            # Initialize & capabilities check
            init_res = by_id[1]["result"]
            self.assertEqual(init_res["protocolVersion"], "2024-11-05")
            self.assertEqual(init_res["capabilities"], {"tools": {}})

            # Ping
            self.assertEqual(by_id[2]["result"], {})

            # Tools list
            tool_names = [t["name"] for t in by_id[3]["result"]["tools"]]
            self.assertEqual(
                tool_names,
                ["agy_usage_summary", "agy_usage_quota", "agy_usage_cache_health", "agy_usage_health"],
            )

            # G02: Strict sanitization & size caps across all 4 tools
            caps = {4: 2048, 5: 1024, 6: 1024, 7: 512}
            forbidden = ("SECRET_PAYROLL_TITLE", "SECRET_BODY_SNIPPET", "top-secret-repo", "conv-secret-uuid-9999")
            for req_id, cap in caps.items():
                res = by_id[req_id]["result"]
                self.assertFalse(res.get("isError"), res)
                txt = res["content"][0]["text"]
                self.assertLessEqual(len(txt.encode("utf-8")), cap, f"Tool req {req_id} exceeded {cap}B")
                for secret in forbidden:
                    self.assertNotIn(secret, txt)

            # G02: Zero notification side effects
            self.assertFalse((data_dir / "notify_state.json").exists())

            # Validation & protocol errors
            self.assertEqual(by_id[8]["error"]["code"], -32602)
            self.assertEqual(by_id[9]["error"]["code"], -32601)

    def test_g02_readonly_cache_dir_fallback(self) -> None:
        if os.name == "nt":
            return
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agy_dir, data_dir = _seed_sensitive_sandbox(root)
            os.chmod(data_dir, 0o555)
            try:
                env = dict(os.environ, AGY_DATA_DIR=str(agy_dir), AGY_USAGE_DATA_DIR=str(data_dir))
                code = (
                    "import json, sys; sys.path.insert(0, sys.argv[1]); "
                    "import pure_query; print(json.dumps(pure_query.query_usage_summary('30d')))"
                )
                out = subprocess.check_output([sys.executable, "-c", code, str(SRC_DIR)], env=env, timeout=10)
                j = json.loads(out.decode("utf-8"))
                self.assertEqual(j["summary"]["calls"], 1)
            finally:
                os.chmod(data_dir, 0o755)

    def test_g03_plugin_manifest_structure(self) -> None:
        manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "agy-usage")
        self.assertEqual(manifest["version"], "1.5.1")
        mcp_cfg = json.loads((PLUGIN_DIR / "mcp_config.json").read_text(encoding="utf-8"))
        self.assertEqual(list(mcp_cfg["mcpServers"].keys()), ["quota"])
        self.assertFalse((PLUGIN_DIR / "hooks.json").exists())
        self.assertFalse((PLUGIN_DIR / "rules").exists())
        self.assertFalse((PLUGIN_DIR / "sidecars").exists())

    def test_g04_foreign_port_occupant_and_daemon_lifecycle(self) -> None:
        class ForeignHandler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"service":"unrelated-app"}')

        class FastHTTPServer(HTTPServer):
            def server_bind(self) -> None:
                socketserver.TCPServer.server_bind(self)
                self.server_name = str(self.server_address[0])
                self.server_port = int(self.server_address[1])

        foreign_port = _free_port()
        foreign_srv = FastHTTPServer(("127.0.0.1", foreign_port), ForeignHandler)
        t = threading.Thread(target=foreign_srv.serve_forever, daemon=True)
        t.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                agy_dir, data_dir = _seed_sensitive_sandbox(root)
                env = dict(os.environ, AGY_DATA_DIR=str(agy_dir), AGY_USAGE_DATA_DIR=str(data_dir))
                cli = str(SRC_DIR / "cli.py")

                # 1. Foreign service on target port -> must fail safely without killing foreign server
                res = subprocess.run(
                    [sys.executable, cli, "daemon", "start", "--port", str(foreign_port), "--no-open"],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertNotEqual(res.returncode, 0)
                self.assertTrue(t.is_alive())

                # 2. Fake PID-reuse metadata -> verify_live_instance=False & stop refuses to kill self
                meta_file = data_dir / "daemon_instance.json"
                meta_file.write_text(
                    json.dumps(
                        {
                            "service": "agy-usage-dashboard",
                            "protocol_version": 1,
                            "instance_id": "fake-id",
                            "pid": os.getpid(),
                            "pid_start": "9999999999999999",
                            "host": "127.0.0.1",
                            "port": foreign_port,
                            "owner": "daemon",
                        }
                    ),
                    encoding="utf-8",
                )
                stop_fake = subprocess.run(
                    [sys.executable, cli, "daemon", "stop", "--port", str(foreign_port)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(stop_fake.returncode, 0)

                # 3. Clean daemon start -> 0600 metadata -> reuse on second start -> clean stop
                clean_port = _free_port()
                st1 = subprocess.run(
                    [sys.executable, cli, "daemon", "start", "--port", str(clean_port), "--no-open"],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(st1.returncode, 0, st1.stderr)
                try:
                    self.assertTrue(meta_file.is_file())
                    if os.name != "nt":
                        mode = stat.S_IMODE(meta_file.stat().st_mode)
                        self.assertEqual(mode, 0o600)
                    meta1 = json.loads(meta_file.read_text(encoding="utf-8"))
                    st2 = subprocess.run(
                        [sys.executable, cli, "daemon", "start", "--port", str(clean_port), "--no-open"],
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    self.assertEqual(st2.returncode, 0, st2.stderr)
                    meta2 = json.loads(meta_file.read_text(encoding="utf-8"))
                    self.assertEqual(meta1["instance_id"], meta2["instance_id"])
                    self.assertEqual(meta1["pid"], meta2["pid"])
                finally:
                    subprocess.run(
                        [sys.executable, cli, "daemon", "stop", "--port", str(clean_port)],
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                self.assertFalse(meta_file.exists())
        finally:
            foreign_srv.shutdown()
            foreign_srv.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
