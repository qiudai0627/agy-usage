#!/usr/bin/env python3
"""Isolated unit & concurrency regression tests for agy-usage (Blades A & C)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"


def _run_in_sandbox(code: str, extra_env: dict | None = None) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        agy_dir = Path(tmp) / "fake_agy"
        data_dir = Path(tmp) / "fake_cache"
        agy_dir.mkdir(parents=True)
        data_dir.mkdir(parents=True)
        env = dict(os.environ)
        env["AGY_DATA_DIR"] = str(agy_dir)
        env["AGY_USAGE_DATA_DIR"] = str(data_dir)
        env["PYTHONPATH"] = str(SRC_DIR)
        if extra_env:
            env.update(extra_env)
        out = subprocess.check_output([sys.executable, "-c", code], env=env, text=True)
        return out


class TestStatuslineBladeA(unittest.TestCase):
    def test_four_buckets_widths_and_stack_dedup(self) -> None:
        code = r"""
import json, re, statusline
from datetime import datetime, timedelta, timezone

fut_w = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
fut_5h = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
payload = {
    "agent_state": "idle",
    "stack_with_default": True,
    "model": {"id": "Gemini 4 Carbon (High)", "display_name": "Gemini 4 Carbon (High)", "effort": "high"},
    "context_window": {"used_percentage": 37.8, "current_usage": {"input_tokens": 3100, "cache_read_input_tokens": 400000}},
    "quota": {
        "gemini-5h": {"remaining_fraction": 0.821, "reset_time": fut_5h, "reset_in_seconds": 10800},
        "gemini-weekly": {"remaining_fraction": 0.842, "reset_time": fut_w, "reset_in_seconds": 432000},
        "3p-5h": {"remaining_fraction": 0.76, "reset_time": fut_5h, "reset_in_seconds": 10800},
        "3p-weekly": {"remaining_fraction": 0.38, "reset_time": fut_w, "reset_in_seconds": 432000},
    },
}

for w in (80, 105, 120, 160):
    p = dict(payload, terminal_width=w)
    out = statusline.render(p)
    clean = re.sub(r"\x1b\[[0-9;]*m", "", out)
    # Must NOT repeat model name or effort in stack mode
    for forbidden in ("Gemini 4", "Carbon", "Neon", "High"):
        assert forbidden not in clean, f"Forbidden {forbidden!r} in {clean!r}"
    # All 4 buckets must appear in order
    has_full = all(t in clean for t in ("Gemini5h", "Gemini周", "Claude5h", "Claude周"))
    has_short = all(t in clean for t in ("G5h", "G周", "C5h", "C周"))
    assert has_full or has_short, f"Missing bucket at width {w}: {clean!r}"
    # Must explicitly include '已用' (never bare percentage)
    assert clean.count("已用") == 4, f"Expected 4 '已用' markers at width {w}: {clean!r}"
    # Respect right margin (>= 16 cols)
    vis_w = statusline.display_width(out)
    assert vis_w <= w - 16, f"Width {vis_w} exceeded budget for w={w}: {clean!r}"

# Ultra-narrow (< 60 cols) must prompt to view Web UI rather than silently dropping 2 buckets
ultra = re.sub(r"\x1b\[[0-9;]*m", "", statusline.render(dict(payload, terminal_width=52)))
assert "网页" in ultra and "agy-usage" in ultra, f"Ultra-narrow fallback unexpected: {ultra!r}"

# Missing bucket must show placeholder, never fake 0%
partial = dict(payload, terminal_width=120, quota={"gemini-weekly": {"remaining_fraction": 0.85, "reset_time": fut_w}})
clean_p = re.sub(r"\x1b\[[0-9;]*m", "", statusline.render(partial))
assert "Gemini5h —" in clean_p and "Claude5h —" in clean_p and "Claude周 —" in clean_p, clean_p
assert "已用0.0%" not in clean_p and "已用0%" not in clean_p, clean_p
print("STATUSLINE_OK")
"""
        self.assertIn("STATUSLINE_OK", _run_in_sandbox(code))


class TestCoreAlgorithmsAndFaultIsolation(unittest.TestCase):
    def test_f04_tokens_per_1pct_pool_isolation(self) -> None:
        code = r"""
from datetime import datetime, timedelta, timezone
import core

now = datetime.now(timezone.utc)
t1 = now - timedelta(hours=2)
t2 = now - timedelta(hours=1)
fut = (now + timedelta(days=4)).isoformat()

snaps = [
    {"_dt": t1, "quota": {"gemini-weekly": {"remaining_fraction": 0.90, "reset_time": fut}, "3p-weekly": {"remaining_fraction": 0.80, "reset_time": fut}}},
    {"_dt": t2, "quota": {"gemini-weekly": {"remaining_fraction": 0.89, "reset_time": fut}, "3p-weekly": {"remaining_fraction": 0.70, "reset_time": fut}}},
]
events = [
    {"ts": t1 + timedelta(minutes=10), "pool": "gemini_pro", "billable_tokens": 100_000},
    {"ts": t1 + timedelta(minutes=20), "pool": "claude_gpt", "billable_tokens": 900_000},
    {"ts": t1 + timedelta(minutes=30), "pool": "other", "billable_tokens": 500_000},
]
live = {"captured_at": now.isoformat(), "quota": snaps[-1]["quota"]}
res = core.analyze_quota_buckets(live, snaps, events, now)
by_id = {b["id"]: b for b in res["buckets"]}
assert by_id["gemini-weekly"]["tokens_per_1pct"] == 100000.0, by_id["gemini-weekly"]
assert by_id["3p-weekly"]["tokens_per_1pct"] == 90000.0, by_id["3p-weekly"]
print("F04_OK")
"""
        self.assertIn("F04_OK", _run_in_sandbox(code))

    def test_f05_reset_segmentation(self) -> None:
        code = r"""
from datetime import datetime, timedelta, timezone
import core

now = datetime.now(timezone.utc)
fut = (now + timedelta(hours=4)).isoformat()
snaps = [
    {"_dt": now - timedelta(minutes=70), "quota": {"gemini-5h": {"remaining_fraction": 0.08, "reset_time": fut}}},
    {"_dt": now - timedelta(minutes=50), "quota": {"gemini-5h": {"remaining_fraction": 0.98, "reset_time": fut}}},
    {"_dt": now - timedelta(minutes=20), "quota": {"gemini-5h": {"remaining_fraction": 0.94, "reset_time": fut}}},
]
live = {"captured_at": now.isoformat(), "quota": snaps[-1]["quota"]}
res = core.analyze_quota_buckets(live, snaps, [], now)
b = res["buckets"][0]
assert b["burn_method"] == "observed" and abs(b["burn_pct_per_hour"] - 8.0) < 0.05, b
print("F05_OK")
"""
        self.assertIn("F05_OK", _run_in_sandbox(code))

    def test_f16_corrupt_jsonl_lines_isolated(self) -> None:
        code = r"""
import json, os
from pathlib import Path
import core

tdir = Path(os.environ["AGY_DATA_DIR"]) / "brain/conv-1/.system_generated/logs"
tdir.mkdir(parents=True)
tfile = tdir / "transcript.jsonl"
lines = [
    json.dumps({"step_index": 1, "created_at": "2026-11-25T10:00:00Z", "model": "gemini-4-neon-high", "input_tokens": 1000, "cache_read_tokens": 200, "output_tokens": 50}),
    "42",
    "null",
    "{corrupt json",
    json.dumps({"step_index": 2, "created_at": "2026-11-25T10:01:00Z", "model": "gemini-4-neon-high", "input_tokens": "bad", "output_tokens": 50}),
    json.dumps({"step_index": 3, "created_at": "2026-11-25T10:02:00Z", "model": "claude-opus-5-5-high", "input_tokens": 500, "cache_read_tokens": 0, "output_tokens": 100}),
]
tfile.write_text("\n".join(lines) + "\n", encoding="utf-8")

evs = core.load_transcript_events()
assert len(evs) == 2 and evs[0]["step_index"] == 1 and evs[1]["step_index"] == 3, evs

core.SNAPSHOTS_FILE.write_text('42\n{"captured_at":"2026-11-25T10:00:00Z","quota":{"gemini-weekly":{"remaining_fraction":0.8}}}\n{bad\n', encoding="utf-8")
sn = core.load_quota_snapshots(max_age_days=3650)
assert len(sn) == 1, sn
print("F16_OK")
"""
        self.assertIn("F16_OK", _run_in_sandbox(code))


class TestConcurrencyAndHttpSecurity(unittest.TestCase):
    def test_f01_f03_concurrent_locks(self) -> None:
        code = r"""
import json, os, threading
from pathlib import Path
import core

tdir = Path(os.environ["AGY_DATA_DIR"]) / "brain/conv-c/.system_generated/logs"
tdir.mkdir(parents=True)
(tdir / "transcript.jsonl").write_text(
    json.dumps({"step_index": 1, "created_at": "2026-11-25T10:00:00Z", "model": "gemini-4-neon-high", "input_tokens": 100, "output_tokens": 20}) + "\n",
    encoding="utf-8",
)

errors = []
def worker(i: int) -> None:
    try:
        for j in range(6):
            core.record_quota_snapshot({"gemini-weekly": {"remaining_fraction": round(0.9 - (i*10+j)*0.001, 4)}}, force=True)
            if j % 2 == 0:
                core.compact_quota_snapshots(keep_days=30)
            core.load_transcript_events()
    except Exception as exc:
        errors.append(exc)

threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
for t in threads: t.start()
for t in threads: t.join()
assert not errors, errors
tmps = list(Path(os.environ["AGY_USAGE_DATA_DIR"]).glob("*.tmp"))
assert not tmps, f"Leftover tmp files: {tmps}"
print("CONCURRENCY_OK")
"""
        self.assertIn("CONCURRENCY_OK", _run_in_sandbox(code))

    def test_f13_http_host_origin_and_email_strip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            env["AGY_DATA_DIR"] = str(Path(tmp) / "agy")
            env["AGY_USAGE_DATA_DIR"] = str(Path(tmp) / "cache")
            Path(env["AGY_DATA_DIR"]).mkdir()
            Path(env["AGY_USAGE_DATA_DIR"]).mkdir()

            # Feed a payload containing email into statusline.py and verify email is stripped
            sample_in = json.dumps({
                "email": "secret_test@example.com",
                "plan_tier": "Pro",
                "quota": {"gemini-weekly": {"remaining_fraction": 0.85}},
            })
            subprocess.run(
                [sys.executable, str(SRC_DIR / "statusline.py")],
                input=sample_in,
                text=True,
                env=env,
                stdout=subprocess.DEVNULL,
                check=True,
            )

            port = 18773
            proc = subprocess.Popen(
                [sys.executable, str(SRC_DIR / "cli.py"), "web", "--port", str(port), "--no-open"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                for _ in range(25):
                    try:
                        c = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                        c.request("GET", "/api/stats")
                        r = c.getresponse()
                        body = r.read().decode("utf-8")
                        c.close()
                        if r.status == 200:
                            break
                    except Exception:
                        time.sleep(0.12)
                else:
                    self.fail("Server did not start")

                # 1. Email must not appear in /api/stats or live_state.json
                self.assertNotIn("secret_test@example.com", body)
                self.assertNotIn('"email"', body)

                # 2. Evil Host header -> 403 (DNS Rebinding defense)
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                c.request("GET", "/api/stats", headers={"Host": f"evil.attacker.com:{port}"})
                self.assertEqual(c.getresponse().status, 403)
                c.close()

                # 3. Cross-site text/plain simple POST -> 415
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                c.request(
                    "POST",
                    "/api/record-quota",
                    body='{"bucket":"gemini-weekly","remaining_pct":10}',
                    headers={"Host": f"127.0.0.1:{port}", "Content-Type": "text/plain"},
                )
                self.assertEqual(c.getresponse().status, 415)
                c.close()

                # 4. Cross-site Origin with application/json -> 403
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                c.request(
                    "POST",
                    "/api/record-quota",
                    body='{"bucket":"gemini-weekly","remaining_pct":10}',
                    headers={
                        "Host": f"127.0.0.1:{port}",
                        "Content-Type": "application/json",
                        "Origin": "https://evil.example",
                    },
                )
                self.assertEqual(c.getresponse().status, 403)
                c.close()

                # 5. Legitimate same-origin JSON POST -> 200
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                c.request(
                    "POST",
                    "/api/record-quota",
                    body='{"bucket":"gemini-weekly","remaining_pct":75}',
                    headers={
                        "Host": f"127.0.0.1:{port}",
                        "Content-Type": "application/json",
                        "Origin": f"http://127.0.0.1:{port}",
                    },
                )
                self.assertEqual(c.getresponse().status, 200)
                c.close()
            finally:
                proc.terminate()
                proc.wait(timeout=3)
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
