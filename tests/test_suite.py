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
    # Must explicitly include '已用' (never bare percentage) and pool identity colors (CYAN / MAGENTA)
    assert clean.count("已用") == 4, f"Expected 4 '已用' markers at width {w}: {clean!r}"
    assert "\x1b[36mGemini5h\x1b[0m" in out or "\x1b[36mG5h\x1b[0m" in out, f"Missing CYAN Gemini label at w={w}: {out!r}"
    assert "\x1b[35mClaude周\x1b[0m" in out or "\x1b[35mC周\x1b[0m" in out, f"Missing MAGENTA Claude label at w={w}: {out!r}"
    # Respect right margin (>= 16 cols)
    vis_w = statusline.display_width(out)
    assert vis_w <= w - 16, f"Width {vis_w} exceeded budget for w={w}: {clean!r}"

# Ultra-narrow widths (40, 52, 60) must ALWAYS obey >=16 right margin and show clear CYAN web prompt (no DIM)
heavy = dict(
    payload,
    quota={
        "gemini-5h": {"remaining_fraction": 0.2, "reset_time": fut_5h, "reset_in_seconds": 10800},
        "gemini-weekly": {"remaining_fraction": 0.2, "reset_time": fut_w, "reset_in_seconds": 432000},
        "3p-5h": {"remaining_fraction": 0.2, "reset_time": fut_5h, "reset_in_seconds": 10800},
        "3p-weekly": {"remaining_fraction": 0.2, "reset_time": fut_w, "reset_in_seconds": 432000},
    },
)
for w in (40, 52, 60):
    out_u = statusline.render(dict(heavy, terminal_width=w))
    clean_u = re.sub(r"\x1b\[[0-9;]*m", "", out_u)
    vis_u = statusline.display_width(out_u)
    assert vis_u <= w - 16, f"R2 margin violated at w={w}: vis={vis_u} > {w - 16} ({clean_u!r})"
    assert "网页" in clean_u and "agy-usage" in clean_u, f"Missing web hint at w={w}: {clean_u!r}"
    assert "\x1b[36m" in out_u and "\x1b[2m" not in out_u, f"Ultra-narrow hint must use CYAN without DIM at w={w}: {out_u!r}"

# Extremely narrow (30 cols) still obeys >=16 right margin with clear CYAN short hint
out_30 = statusline.render(dict(heavy, terminal_width=30))
assert statusline.display_width(out_30) <= 30 - 16, out_30
assert "网页" in re.sub(r"\x1b\[[0-9;]*m", "", out_30), out_30
assert "\x1b[36m" in out_30 and "\x1b[2m" not in out_30, out_30

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

    def test_r1_lock_timeout_multiprocess_zero_writes_and_concurrent_buckets(self) -> None:
        """R1: Lock timeout across OS processes must fail closed (zero writes/compaction);
        concurrent two-bucket manual updates must both persist without overwriting each other."""
        code = r"""
import json, os, subprocess, sys, time
from pathlib import Path
import core, statusline

cache_dir = Path(os.environ["AGY_USAGE_DATA_DIR"])
agy_dir = Path(os.environ["AGY_DATA_DIR"])

def hold_lock_proc(lock_path: Path, hold_sec: float):
    ready_file = cache_dir / f".ready_{lock_path.name}"
    if ready_file.exists():
        ready_file.unlink()
    helper = (
        "import time, pathlib, core\n"
        f"with core.file_lock(pathlib.Path({str(lock_path)!r}), timeout=5.0) as ok:\n"
        "    assert ok\n"
        f"    pathlib.Path({str(ready_file)!r}).write_text('1')\n"
        f"    time.sleep({hold_sec})\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", helper], env=dict(os.environ))
    for _ in range(100):
        if ready_file.exists():
            break
        time.sleep(0.02)
    assert ready_file.exists(), f"Lock holder did not acquire {lock_path}"
    return proc

# 1. Hold .snapshots.lock across OS process -> force=True record & compact must both fail closed (zero writes)
seed_snap = (
    json.dumps({"captured_at": "2026-11-25T10:00:00+00:00", "source": "manual", "quota": {"gemini-weekly": {"remaining_fraction": 0.9}}}) + "\n" +
    json.dumps({"captured_at": "2026-11-25T10:01:00+00:00", "source": "manual", "quota": {"gemini-weekly": {"remaining_fraction": 0.9}}}) + "\n" +
    json.dumps({"captured_at": "2026-11-25T10:02:00+00:00", "source": "manual", "quota": {"gemini-weekly": {"remaining_fraction": 0.9}}}) + "\n"
)
core.SNAPSHOTS_FILE.write_text(seed_snap, encoding="utf-8")
snap_before = core.SNAPSHOTS_FILE.read_bytes()

p_snap = hold_lock_proc(core.SNAPSHOTS_FILE.with_name(".snapshots.lock"), 5.2)
try:
    wrote = core.record_quota_snapshot({"gemini-weekly": {"remaining_fraction": 0.1}}, source="manual", force=True)
    assert wrote is False, "force=True must NOT bypass lock timeout!"
    assert core.SNAPSHOTS_FILE.read_bytes() == snap_before, "Snapshots file modified despite lock timeout!"

    comp = core.compact_quota_snapshots(keep_days=30)
    assert comp.get("skipped_locked") is True, comp
    assert core.SNAPSHOTS_FILE.read_bytes() == snap_before, "Compact modified file despite lock timeout!"
finally:
    p_snap.terminate()
    p_snap.wait(timeout=3)

# 2. Hold .state.lock across OS process -> statusline.persist_state & save_manual_quota must do zero writes
seed_state = json.dumps({"source": "seed", "quota": {"gemini-weekly": {"remaining_fraction": 0.8}}})
core.LIVE_STATE_FILE.write_text(seed_state, encoding="utf-8")
state_before = core.LIVE_STATE_FILE.read_bytes()

p_state = hold_lock_proc(core.LIVE_STATE_FILE.with_name(".state.lock"), 3.2)
try:
    statusline.persist_state({"quota": {"gemini-weekly": {"remaining_fraction": 0.1}}})
    assert core.LIVE_STATE_FILE.read_bytes() == state_before, "statusline wrote live_state despite lock timeout!"

    failed_manual = False
    try:
        core.save_manual_quota("claude-weekly", 50.0)
    except TimeoutError:
        failed_manual = True
    assert failed_manual, "save_manual_quota must raise TimeoutError when .state.lock is held!"
    assert core.LIVE_STATE_FILE.read_bytes() == state_before, "save_manual_quota modified live_state despite lock timeout!"
finally:
    p_state.terminate()
    p_state.wait(timeout=3)

# 3. Hold .index.lock across OS process -> load_transcript_events must write ZERO shard files
tdir = agy_dir / "brain/conv-locked/.system_generated/logs"
tdir.mkdir(parents=True)
(tdir / "transcript.jsonl").write_text(
    json.dumps({"step_index": 1, "created_at": "2026-11-25T10:00:00Z", "model": "gemini-4-neon", "input_tokens": 100, "output_tokens": 10}) + "\n",
    encoding="utf-8",
)
p_idx = hold_lock_proc(cache_dir / ".index.lock", 2.5)
try:
    evs = core.load_transcript_events()
    assert len(evs) == 1
    shards = list(core.CONV_CACHE_DIR.glob("*.json")) if core.CONV_CACHE_DIR.exists() else []
    assert len(shards) == 0, f"Index shard written despite .index.lock held: {shards}"
finally:
    p_idx.terminate()
    p_idx.wait(timeout=3)

# 4. Two concurrent OS processes updating two DIFFERENT buckets via save_manual_quota -> both survive!
core.LIVE_STATE_FILE.unlink(missing_ok=True)
env = dict(os.environ)
c1 = "import core; core.save_manual_quota('gemini-weekly', 80.0)"
c2 = "import core; core.save_manual_quota('claude-weekly', 40.0)"
proc1 = subprocess.Popen([sys.executable, "-c", c1], env=env)
proc2 = subprocess.Popen([sys.executable, "-c", c2], env=env)
assert proc1.wait(timeout=10) == 0
assert proc2.wait(timeout=10) == 0
merged = json.loads(core.LIVE_STATE_FILE.read_text(encoding="utf-8"))
assert "gemini-weekly" in merged["quota"] and "claude-weekly" in merged["quota"], merged
assert abs(merged["quota"]["gemini-weekly"]["remaining_fraction"] - 0.8) < 1e-4
assert abs(merged["quota"]["claude-weekly"]["remaining_fraction"] - 0.4) < 1e-4
print("R1_LOCK_MULTIPROC_OK")
"""
        self.assertIn("R1_LOCK_MULTIPROC_OK", _run_in_sandbox(code, {"AGY_USAGE_SUPPRESS_OS_NOTIFY": "1"}))

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

            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]

            proc = subprocess.Popen(
                [sys.executable, str(SRC_DIR / "cli.py"), "web", "--port", str(port), "--no-open"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                for _ in range(80):
                    try:
                        c = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                        c.request("GET", "/api/stats")
                        r = c.getresponse()
                        body = r.read().decode("utf-8")
                        c.close()
                        if r.status == 200:
                            break
                    except Exception:
                        time.sleep(0.15)
                else:
                    self.fail("Server did not start within 12s")

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

                # 6. Preferences toggle via /api/preferences -> 200
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                c.request(
                    "POST",
                    "/api/preferences",
                    body='{"notifications_enabled":true}',
                    headers={
                        "Host": f"127.0.0.1:{port}",
                        "Content-Type": "application/json",
                        "Origin": f"http://127.0.0.1:{port}",
                    },
                )
                pref_resp = c.getresponse()
                pref_body = json.loads(pref_resp.read().decode("utf-8"))
                self.assertEqual(pref_resp.status, 200)
                self.assertTrue(pref_body["preferences"]["notifications_enabled"])
                c.close()
            finally:
                proc.terminate()
                proc.wait(timeout=3)
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()


class TestBladeDAndBladeE(unittest.TestCase):
    def test_f06_1000_sessions_o1_shard_write_and_legacy_migration(self) -> None:
        code = r"""
import json, os, time
from pathlib import Path
import core

agy = Path(os.environ["AGY_DATA_DIR"])
cache = Path(os.environ["AGY_USAGE_DATA_DIR"])

# 1. Verify legacy v1 monolithic transcript_index.json migrates and deletes itself
legacy_p = str(agy / "brain/legacy-conv/.system_generated/logs/transcript.jsonl")
Path(legacy_p).parent.mkdir(parents=True, exist_ok=True)
Path(legacy_p).write_text(
    json.dumps({"step_index": 1, "created_at": "2026-11-20T08:00:00Z", "model": "gemini-4-neon", "input_tokens": 100, "output_tokens": 10}) + "\n",
    encoding="utf-8",
)
st0 = Path(legacy_p).stat()
core.TRANSCRIPT_INDEX_FILE.write_text(
    json.dumps({
        "version": 1,
        "files": {
            legacy_p: {
                "mtime_ns": st0.st_mtime_ns,
                "size": st0.st_size,
                "events": [{
                    "conversation_id": "legacy-conv", "step_index": 1, "ts_iso": "2026-11-20T08:00:00+00:00",
                    "model": "gemini-4-neon", "pool": "gemini_pro", "input_tokens": 100, "cache_read_tokens": 0,
                    "output_tokens": 10, "total_tokens": 110, "billable_tokens": 110, "context_size": 100,
                    "est_cost_usd": 0.001, "cache_saved_usd": 0.0, "tool_count": 0, "tool_names": [],
                    "has_thinking": False, "has_error": False,
                }]
            }
        }
    }),
    encoding="utf-8",
)

# 2. Populate 1,000 synthetic sessions
line_tpl = json.dumps({"step_index": 1, "created_at": "2026-11-25T10:00:00Z", "model": "gemini-4-neon", "input_tokens": 500, "output_tokens": 50}) + "\n"
for idx in range(1000):
    d = agy / "brain" / f"conv-{idx:04d}" / ".system_generated" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    (d / "transcript.jsonl").write_text(line_tpl, encoding="utf-8")

evs = core.load_transcript_events()
assert len(evs) == 1001, len(evs)
assert not core.TRANSCRIPT_INDEX_FILE.exists(), "Legacy monolithic index should be retired"
shards = list(core.CONV_CACHE_DIR.glob("*.json"))
assert len(shards) == 1001, len(shards)

# Snapshot shard mtimes before single-session update
before_mtimes = {p.name: p.stat().st_mtime_ns for p in shards}
time.sleep(0.02)

# Modify ONLY 1 session out of 1,001
target = agy / "brain" / "conv-0500" / ".system_generated" / "logs" / "transcript.jsonl"
with target.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps({"step_index": 2, "created_at": "2026-11-25T10:05:00Z", "model": "claude-opus-5-5", "input_tokens": 800, "output_tokens": 120}) + "\n")

t0 = time.perf_counter()
evs2 = core.load_transcript_events()
elapsed_ms = (time.perf_counter() - t0) * 1000.0
assert len(evs2) == 1002, len(evs2)

changed_shards = [p for p in core.CONV_CACHE_DIR.glob("*.json") if before_mtimes.get(p.name) != p.stat().st_mtime_ns]
written_bytes = sum(p.stat().st_size for p in changed_shards)
assert len(changed_shards) == 1, f"Expected O(1) 1 shard write, got {len(changed_shards)}"
assert written_bytes < 4096, f"Expected < 4KB written, got {written_bytes}"
print(f"F06_OK elapsed_ms={elapsed_ms:.1f} written_bytes={written_bytes}")
"""
        self.assertIn("F06_OK", _run_in_sandbox(code))

    def test_f08_f09_weblog_inode_and_doctor_readonly_then_fix(self) -> None:
        code = r"""
import json, os, subprocess, sys, threading, time
from pathlib import Path
import core, cli

# 1. F08 & R5: Concurrent locked append triggered by barrier right after rotate reads tail (before truncate)
#    must wait for .weblog.lock, preserve the marker after rotation AND across a subsequent rotation.
core.ensure_data_dir()
core.WEB_LOG_FILE.write_bytes((b"X" * 99 + b"\n") * 7000)  # ~700 KB
ino_before = core.WEB_LOG_FILE.stat().st_ino

read_tail_barrier = threading.Barrier(2, timeout=5)
append_done = threading.Event()
append_order = []

def after_read_hook() -> None:
    # Synchronize right after tail is read and BEFORE seek(0)/write/truncate
    read_tail_barrier.wait()
    # Give writer thread a moment to prove it blocks on .weblog.lock rather than slipping before truncate
    time.sleep(0.08)
    assert not append_done.is_set(), "Writer bypassed .weblog.lock during rotate!"
    append_order.append("rotate_truncate")

def concurrent_writer() -> None:
    read_tail_barrier.wait()
    stream = cli.LockedLogStream()
    stream.write("MARKER_AFTER_READ_TAIL_OK\n")
    append_order.append("writer_append")
    append_done.set()

t_writer = threading.Thread(target=concurrent_writer)
t_writer.start()
freed = core.rotate_web_log(
    max_bytes=512 * 1024,
    keep_bytes=128 * 1024,
    _after_read_hook=after_read_hook,
)
t_writer.join(timeout=5)
assert freed > 500 * 1024, freed
assert append_done.is_set(), "Writer did not complete"
assert append_order == ["rotate_truncate", "writer_append"], append_order
assert core.WEB_LOG_FILE.stat().st_ino == ino_before, "Inode changed during log rotation!"
assert core.WEB_LOG_FILE.read_text("utf-8").endswith("MARKER_AFTER_READ_TAIL_OK\n")

# Run another rotation after appending more data -> marker stays visible in rotated tail
assert core.append_web_log(b"SECOND_ROTATE_TAIL_MARKER\n") is True
core.rotate_web_log(max_bytes=64 * 1024, keep_bytes=32 * 1024)
tail_txt = core.WEB_LOG_FILE.read_text("utf-8")
assert "MARKER_AFTER_READ_TAIL_OK\n" in tail_txt and tail_txt.endswith("SECOND_ROTATE_TAIL_MARKER\n"), tail_txt[-120:]
assert core.WEB_LOG_FILE.stat().st_size < 64 * 1024

# Also verify fail-closed: if .weblog.lock is held by another OS process, rotate_web_log returns 0 & does not truncate
big_bytes = (b"Y" * 99 + b"\n") * 7000
core.WEB_LOG_FILE.write_bytes(big_bytes)
lock_path = core.WEB_LOG_FILE.with_name(".weblog.lock")
ready = core.DATA_DIR / ".ready_weblog"
ready.unlink(missing_ok=True)
p_wl = subprocess.Popen(
    [
        sys.executable, "-c",
        (
            "import time, pathlib, core\n"
            f"with core.file_lock(pathlib.Path({str(lock_path)!r}), timeout=5.0) as ok:\n"
            "    assert ok\n"
            f"    pathlib.Path({str(ready)!r}).write_text('1')\n"
            "    time.sleep(2.2)\n"
        ),
    ],
    env=dict(os.environ),
)
try:
    for _ in range(100):
        if ready.exists():
            break
        time.sleep(0.02)
    assert ready.exists()
    assert core.rotate_web_log(max_bytes=512 * 1024, keep_bytes=128 * 1024) == 0
    assert core.WEB_LOG_FILE.stat().st_size == len(big_bytes)
finally:
    p_wl.terminate()
    p_wl.wait(timeout=3)

# 2. F09 & doctor --fix: Read-only first, then repair corrupt lines + orphan tmp + missing statusLine
core.DAILY_ARCHIVE_FILE.write_text(
    '{"date":"2026-10-01","buckets":{"gemini-weekly":{"min_rem":0.5,"last_rem":0.6,"samples":2}}}\n'
    '{corrupt_archive_line\n'
    '{"date":"2026-10-02","buckets":{"gemini-weekly":{"min_rem":0.7,"last_rem":0.7,"samples":1}}}\n',
    encoding="utf-8",
)
orphan = core.DATA_DIR / ".orphan_test.tmp"
orphan.write_text("stale", encoding="utf-8")

rep_ro = core.run_doctor(stale_days=30, fix_issues=False)
pipe_ro = rep_ro["pipeline"]
assert pipe_ro["statusline_enabled"] is False
assert pipe_ro["corrupt_archive_lines"] == 1
assert pipe_ro["orphan_tmp_count"] == 1
assert orphan.exists(), "Read-only doctor must NOT delete files before --fix!"

rep_fix = core.run_doctor(stale_days=30, fix_issues=True)
assert rep_fix["pipeline"]["statusline_enabled"] is True
assert rep_fix["pipeline"]["corrupt_archive_lines"] == 0
assert rep_fix["pipeline"]["orphan_tmp_count"] == 0
assert not orphan.exists()
arch_rows = [json.loads(ln) for ln in core.DAILY_ARCHIVE_FILE.read_text("utf-8").splitlines() if ln.strip()]
assert [r["date"] for r in arch_rows] == ["2026-10-01", "2026-10-02"], arch_rows
cfg = core.load_agy_settings()
assert cfg["statusLine"]["stack_with_default"] is True, cfg
print("F08_F09_DOCTOR_OK")
"""
        self.assertIn("F08_F09_DOCTOR_OK", _run_in_sandbox(code, {"AGY_USAGE_SUPPRESS_OS_NOTIFY": "1"}))

    def test_candidate_a_notifications_dedup_and_confirmed_recovery(self) -> None:
        code = r"""
from datetime import datetime, timedelta, timezone
import core

now = datetime.now(timezone.utc)
c1_reset = (now + timedelta(hours=3)).isoformat()
c2_reset = (now + timedelta(hours=8)).isoformat()

# Default must be off
assert core.get_preferences()["notifications_enabled"] is False
core.set_preferences(notifications_enabled=True)
assert core.get_preferences()["notifications_enabled"] is True

def eval_q(rem_frac: float, reset_iso: str, source: str = "statusline", captured_dt=None):
    cap = (captured_dt or now).isoformat()
    ls = {"captured_at": cap, "source": source, "quota": {"gemini-5h": {"remaining_fraction": rem_frac, "reset_time": reset_iso}}}
    q_info = core.analyze_quota_buckets(ls, [], [], now)
    return core.evaluate_quota_notifications(q_info, now=now, dispatch=False)

# 1. Cross 80% used -> fires alert_80 once
r1 = eval_q(0.18, c1_reset)  # 82% used
assert [x["kind"] for x in r1["triggered"]] == ["alert_80"], r1
# Poll again at 84% -> deduplicated (0 alerts)
r2 = eval_q(0.16, c1_reset)
assert r2["triggered"] == [], r2

# 2. Cross 95% used -> fires alert_95 once
r3 = eval_q(0.04, c1_reset)  # 96% used
assert [x["kind"] for x in r3["triggered"]] == ["alert_95"], r3
r4 = eval_q(0.03, c1_reset)
assert r4["triggered"] == [], r4

# 3. Countdown hits zero (`reset_passed == True`) WITHOUT fresh post-reset telemetry -> MUST NOT fire recovery!
past_reset = (now - timedelta(minutes=2)).isoformat()
r_expired = eval_q(0.03, past_reset)
assert r_expired["triggered"] == [], f"Countdown zero must not fake recovery: {r_expired}"

# 4. Fresh official statusline confirms reset (used_pct drops to 4% on new cycle) -> fires recovery ONCE
r_rec = eval_q(0.96, c2_reset, source="statusline")
assert [x["kind"] for x in r_rec["triggered"]] == ["recovery"], r_rec
r_rec_dup = eval_q(0.95, c2_reset, source="statusline")
assert r_rec_dup["triggered"] == [], r_rec_dup
print("CANDIDATE_A_OK")
"""
        self.assertIn("CANDIDATE_A_OK", _run_in_sandbox(code, {"AGY_USAGE_SUPPRESS_OS_NOTIFY": "1"}))

    def test_candidate_b_week_over_week_and_timezone_override(self) -> None:
        code = r"""
from datetime import datetime, timedelta, timezone
import core

tz = core.get_local_tz()
assert core.get_tz_label() == "UTC+9", core.get_tz_label()

# Wednesday 14:00 UTC+9 -> 62 hours into current natural week
wed_local = datetime(2026, 11, 25, 14, 0, 0, tzinfo=tz)
now_utc = wed_local.astimezone(timezone.utc)
this_mon = datetime(2026, 11, 23, 0, 0, 0, tzinfo=tz).astimezone(timezone.utc)
last_mon = this_mon - timedelta(days=7)

def mk_ev(dt_utc, tok):
    return {
        "conversation_id": "c1",
        "ts": dt_utc,
        "input_tokens": tok,
        "cache_read_tokens": 0,
        "output_tokens": 0,
        "total_tokens": tok,
        "billable_tokens": tok,
        "est_cost_usd": 0.1,
        "cache_saved_usd": 0.0,
        "tool_count": 0,
    }

# Case 1: Only current-week events -> missing prior-week sample -> comparable == False
cur_only = [mk_ev(this_mon + timedelta(hours=10), 80_000)]
w_missing = core.compute_week_over_week(cur_only, now=now_utc, tz=tz)
assert w_missing["comparable"] is False, w_missing

# Case 2: Prior week has 100k within same 62h progress + 900k on Friday (after 62h); current week has 80k
# Same-progress comparison must compare 80k vs 100k (-20.0%), NOT 80k vs 1,000k!
both = sorted(
    [
        mk_ev(last_mon + timedelta(hours=20), 100_000),
        mk_ev(last_mon + timedelta(hours=110), 900_000),
        mk_ev(this_mon + timedelta(hours=20), 80_000),
    ],
    key=lambda x: x["ts"],
)
w_ok = core.compute_week_over_week(both, now=now_utc, tz=tz)
assert w_ok["comparable"] is True, w_ok
assert w_ok["delta_pct"] == -20.0, w_ok
assert "-20.0%" in w_ok["badge_text"], w_ok

# CSV formula injection check
assert core._safe_csv_cell("=CMD|' /C calc'!A0") == "'=CMD|' /C calc'!A0"
assert core._safe_csv_cell("@evil") == "'@evil"
print("CANDIDATE_B_TZ_OK")
"""
        self.assertIn("CANDIDATE_B_TZ_OK", _run_in_sandbox(code, {"AGY_USAGE_TZ": "+09:00"}))

    def test_f12_ps1_bom_and_bat_nobom(self) -> None:
        for ps_name in ("install.ps1", "uninstall.ps1"):
            raw = (ROOT_DIR / ps_name).read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), f"{ps_name} must start with UTF-8 BOM")
            self.assertFalse(raw[3:].startswith(b"\xef\xbb\xbf"), f"{ps_name} must have EXACTLY ONE UTF-8 BOM")
            body = raw[3:].decode("utf-8")
            self.assertNotIn("\ufeff", body, f"{ps_name} body must not contain U+FEFF")
            self.assertTrue(body.startswith("$ErrorActionPreference"), f"{ps_name} must start with PowerShell code")
        bat = (ROOT_DIR / "Start-Windows.bat").read_bytes()
        self.assertFalse(bat.startswith(b"\xef\xbb\xbf"), "Start-Windows.bat must not start with UTF-8 BOM")
        self.assertNotIn("\ufeff", bat.decode("utf-8"))

    def test_r4_terminal_svg_buckets_left_of_reserved_zone(self) -> None:
        import unicodedata
        import xml.etree.ElementTree as ET

        svg_path = ROOT_DIR / "docs" / "assets" / "terminal-bar.svg"
        tree = ET.parse(svg_path)
        root = tree.getroot()
        ns = {"s": "http://www.w3.org/2000/svg"}

        reserved_rect = None
        for rect in root.findall("s:rect", ns):
            if rect.attrib.get("stroke-dasharray"):
                reserved_rect = rect
                break
        self.assertIsNotNone(reserved_rect, "Reserved zone rect not found in terminal-bar.svg")
        reserved_x = float(reserved_rect.attrib["x"])

        bucket_texts = []
        row1_model_count = 0
        row2_model_count = 0
        for txt in root.findall("s:text", ns):
            content = "".join(txt.itertext()).strip()
            y = float(txt.attrib.get("y", "0"))
            x = float(txt.attrib.get("x", "0"))
            fs = float(txt.attrib.get("font-size", "11"))
            if "Gemini 4 Carbon" in content:
                if y < 80:
                    row1_model_count += 1
                else:
                    row2_model_count += 1
            if any(k in content for k in ("Gemini5h", "Gemini周", "Claude5h", "Claude周")):
                # Conservative monospace px estimate: CJK/block = 1.05*fs, ASCII = 0.65*fs
                est_px = 0.0
                for ch in content:
                    if unicodedata.east_asian_width(ch) in ("W", "F") or ch in "█░":
                        est_px += fs * 1.05
                    else:
                        est_px += fs * 0.65
                bucket_texts.append((content, x, x + est_px))

        self.assertEqual(row1_model_count, 1, "Model name must appear once on native Row 1")
        self.assertEqual(row2_model_count, 0, "Model name must NOT repeat on Row 2")
        self.assertEqual(len(bucket_texts), 4, f"Expected 4 bucket text nodes: {bucket_texts}")
        for content, x, right_edge in bucket_texts:
            self.assertLess(
                right_edge,
                reserved_x - 16.0,
                f"Bucket {content!r} (x={x}, est_right={right_edge:.1f}) encroaches reserved zone x={reserved_x}",
            )

    def test_ui_color_themes_semantics(self) -> None:
        import importlib.machinery
        import importlib.util

        # Verify Windows tray widget theme palette & system mapping without opening GUI
        win_path = ROOT_DIR / "windows" / "tray_widget.pyw"
        loader = importlib.machinery.SourceFileLoader("tray_widget_mod", str(win_path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        assert spec is not None
        tw = importlib.util.module_from_spec(spec)
        loader.exec_module(tw)

        self.assertIn("tongtou", tw.THEMES)
        self.assertEqual(tw.THEMES["dark"]["gem"].lower(), "#38bdf8")
        self.assertEqual(tw.THEMES["dark"]["cld"].lower(), "#a78bfa")
        self.assertEqual(tw.THEMES["light"]["gem"].lower(), "#0e7490")
        self.assertEqual(tw.THEMES["light"]["cld"].lower(), "#6d28d9")
        self.assertNotEqual(tw.THEMES["light"]["gem"].lower(), "#db2777")
        self.assertEqual(tw.THEMES["tongtou"]["bg"].upper(), "#F5F0EB")
        self.assertEqual(tw.THEMES["tongtou"]["fg"].upper(), "#2C3E50")
        self.assertEqual(tw.THEMES["tongtou"]["border"].upper(), "#7BA7A7")
        self.assertEqual(tw.THEMES["tongtou"]["gem"].upper(), "#4D7C7C")
        self.assertEqual(tw.THEMES["tongtou"]["cld"].upper(), "#9A7B4F")
        # System preference must ONLY resolve to light or dark, never tongtou
        self.assertIn(tw._resolved_theme("system"), ("light", "dark"))
        self.assertEqual(tw._resolved_theme("tongtou"), "tongtou")
        # Numeric thresholds: <55 ok, >=55 warn, >=80 crit, expired gray (never sand-gold)
        tt = tw.THEMES["tongtou"]
        self.assertEqual(tw._val_color(20.0, False, tt), tt["ok"])
        self.assertEqual(tw._val_color(55.0, False, tt), tt["warn"])
        self.assertEqual(tw._val_color(80.0, False, tt), tt["crit"])
        self.assertEqual(tw._val_color(10.0, True, tt), tt["expired"])
        self.assertNotEqual(tw._val_color(55.0, False, tt).upper(), "#9A7B4F")

    def test_i18n_11_languages_parity_and_readmes(self) -> None:
        sys.path.insert(0, str(SRC_DIR))
        import i18n
        import statusline
        import web_ui

        expected_langs = ["zh-CN", "zh-TW", "en", "ja", "ko", "es", "pt-BR", "de", "fr", "ru", "vi"]
        self.assertEqual([code for code, _ in i18n.LANG_OPTIONS], expected_langs)
        base_keys = set(i18n.WEB_I18N["en"].keys())
        self.assertGreater(len(base_keys), 100)

        ph_re = re.compile(r"\{\d+\}")
        for lang in expected_langs:
            self.assertIn(lang, i18n.WEB_I18N)
            d = i18n.WEB_I18N[lang]
            self.assertEqual(set(d.keys()), base_keys, f"Key mismatch in {lang}")
            self.assertEqual(len(d["weekdays"]), 7, f"Weekdays length != 7 in {lang}")
            for k, val in d.items():
                if k == "weekdays":
                    continue
                self.assertTrue(isinstance(val, str) and len(val.strip()) > 0, f"Empty {lang}.{k}")
                self.assertEqual(
                    set(ph_re.findall(val)),
                    set(ph_re.findall(i18n.WEB_I18N["en"][k])),
                    f"Placeholder mismatch in {lang}.{k}",
                )

        # Every data-i18n* attribute in web_ui.DASHBOARD_HTML must exist in WEB_I18N
        html = web_ui.DASHBOARD_HTML
        for attr in ("data-i18n", "data-i18n-ph", "data-i18n-title"):
            for key in re.findall(rf'{attr}="([^"]+)"', html):
                self.assertIn(key, base_keys, f"HTML {attr}={key!r} missing from WEB_I18N")

        # Statusline zh-TW & en rendering and >=16 margin
        fut_5h = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        fut_w = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        payload = {
            "agent_state": "idle",
            "stack_with_default": True,
            "context_window": {"used_percentage": 25.0},
            "quota": {
                "gemini-5h": {"remaining_fraction": 0.80, "reset_time": fut_5h},
                "gemini-weekly": {"remaining_fraction": 0.85, "reset_time": fut_w},
                "3p-5h": {"remaining_fraction": 0.70, "reset_time": fut_5h},
                "3p-weekly": {"remaining_fraction": 0.50, "reset_time": fut_w},
            },
        }
        for lg, expected_tok in (("en", "Used"), ("zh-TW", "Gemini週")):
            out_wide = statusline.render(dict(payload, lang=lg, terminal_width=140))
            clean_wide = re.sub(r"\x1b\[[0-9;]*m", "", out_wide)
            self.assertIn(expected_tok, clean_wide)
            self.assertLessEqual(statusline.display_width(out_wide), 140 - 16)
            out_narrow = statusline.render(dict(payload, lang=lg, terminal_width=52))
            self.assertLessEqual(statusline.display_width(out_narrow), 52 - 16)

        # Tri-lingual READMEs check
        for rname in ("README.md", "README_ZH-TW.md", "README_EN.md"):
            txt = (ROOT_DIR / rname).read_text(encoding="utf-8")
            main_part = txt.split("<details>")[0]
            self.assertNotIn("transcript.jsonl", main_part, f"Jargon leaked in {rname}")
            self.assertNotIn("statusLine", main_part, f"Jargon leaked in {rname}")
            self.assertIn("qiudai0627/agy-usage", txt, f"Repo link missing in {rname}")

        # Multi-window anti-rollback check: older reset_time from an idle window must NOT overwrite newer reset_time
        old_q = {"gemini-weekly": {"remaining_fraction": 0.78, "reset_time": "2099-12-01T10:00:00Z"}}
        new_q = {"gemini-weekly": {"remaining_fraction": 0.99, "reset_time": "2099-12-03T10:00:00Z"}}
        merged = statusline._merge_freshest_quota(old_q, new_q)
        self.assertEqual(merged["gemini-weekly"]["remaining_fraction"], 0.99)
        self.assertEqual(merged["gemini-weekly"]["reset_time"], "2099-12-03T10:00:00Z")


if __name__ == "__main__":
    unittest.main(verbosity=2)
