#!/usr/bin/env python3
"""Command-line entry point for Antigravity CLI (agy-usage)."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from core import (  # noqa: E402
    atomic_write_text,
    clean_cache,
    discover_settings_file,
    get_preferences,
    run_doctor,
    save_manual_quota,
    set_preferences,
)
from server import (  # noqa: E402,F401
    LockedLogStream,
    _read_pid,
    cmd_daemon,
    cmd_web,
)
from tui import (  # noqa: E402
    BOLD,
    CYAN,
    DIM,
    GREEN,
    RED,
    RESET,
    YELLOW,
    cmd_json,
    cmd_report,
    cmd_watch,
    trunc_display,
)


def cmd_install_statusline(args: argparse.Namespace) -> int:
    statusline_path = str(APP_DIR / "statusline.py")
    cmd_str = f'"{sys.executable}" "{statusline_path}"' if os.name == "nt" else statusline_path
    sf = discover_settings_file()
    sf.parent.mkdir(parents=True, exist_ok=True)
    cfg: Dict[str, Any] = {}
    if sf.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = sf.with_name(f"settings.json.bak-agy-usage-{ts}")
        shutil.copy2(sf, backup)
        print(f"已备份原配置: {backup}")
        try:
            loaded = json.loads(sf.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg = loaded
        except Exception:
            cfg = {}

    cfg["statusLine"] = {
        "type": "command",
        "command": cmd_str,
        "enabled": True,
        "stack_with_default": bool(args.stack),
    }
    atomic_write_text(sf, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", mode=0o600)
    print(f"{GREEN}✓ 已在 {sf} 启用 statusLine:{RESET}")
    print(f"  command: {cmd_str}")
    print(f"  stack_with_default: {bool(args.stack)}")
    print(f"提示：新开的 agy 会话会自动生效；当前已打开的 agy 会话可输入 {CYAN}/statusline {cmd_str}{RESET} 立即刷新。")
    return 0


def cmd_uninstall_statusline(_args: argparse.Namespace) -> int:
    sf = discover_settings_file()
    if not sf.exists():
        print("未找到 settings.json")
        return 0
    cfg = json.loads(sf.read_text(encoding="utf-8"))
    if "statusLine" not in cfg:
        print("settings.json 中未配置 statusLine")
        return 0
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = sf.with_name(f"settings.json.bak-agy-usage-{ts}")
    shutil.copy2(sf, backup)
    del cfg["statusLine"]
    atomic_write_text(sf, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", mode=0o600)
    print(f"{GREEN}✓ 已移除 statusLine 配置{RESET}（原配置备份于 {backup}）")
    return 0


def _fmt_bytes(n: int) -> str:
    v = float(max(0, n))
    if v >= 1024 * 1024 * 1024:
        return f"{v / (1024 ** 3):.2f} GB"
    if v >= 1024 * 1024:
        return f"{v / (1024 ** 2):.2f} MB"
    if v >= 1024:
        return f"{v / 1024:.1f} KB"
    return f"{int(v)} B"


def cmd_clean(args: argparse.Namespace) -> int:
    res = clean_cache(
        keep_days=int(args.keep_days),
        reset_index=bool(args.reset_index),
        max_backups=int(args.max_backups),
    )
    sn = res["snapshots"]
    print(f"{BOLD}{CYAN}━━━ agy-usage 缓存瘦身与清理结果 ━━━{RESET}")
    print(f"  缓存目录    : {res['cache_dir']}")
    arch_hint = f" · 归档 {sn['archived_days']} 天" if sn["archived_days"] else ""
    print(
        f"  限额快照压缩: {sn['before_lines']} 行 -> {BOLD}{sn['after_lines']}{RESET} 行 "
        f"({_fmt_bytes(sn['bytes_before'])} -> {_fmt_bytes(sn['bytes_after'])}{arch_hint})"
    )
    print(f"  增量索引缓存: 当前跟踪 {BOLD}{res['index_entries']}{RESET} 个活跃会话日志文件")
    if res["backups_removed"] > 0:
        print(f"  旧配置备份  : 已清理 {res['backups_removed']} 份多余 settings.json.bak 备份")
    print(f"  {GREEN}✓ 共释放空间: {_fmt_bytes(res['bytes_freed'])}{RESET}（当前缓存总占用 {_fmt_bytes(res['bytes_after'])}）")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    rep = run_doctor(stale_days=int(args.stale_days), prune_stale=False, fix_issues=False)
    pipe = rep.get("pipeline") or {}
    daemon_pid = _read_pid()

    print(f"{BOLD}{CYAN}━━━ Antigravity & agy-usage 数据与链路健康体检 ━━━{RESET}")
    print(f"  监控自有缓存: {_fmt_bytes(rep['own_cache_bytes'])} ({rep['own_cache_dir']})")
    print(f"  分会话索引  : 已缓存 {rep['index_cached_files']} 个会话分片（单会话更新仅重写对应小分片）")
    print(f"  AGY 数据总占: {BOLD}{_fmt_bytes(rep['total_agy_bytes'])}{RESET}（共登记 {rep['total_conversations']} 个会话）")

    sl_ok = pipe.get("statusline_enabled") and pipe.get("statusline_path_valid") and pipe.get("statusline_executable")
    age_s = pipe.get("live_state_age_seconds")
    age_txt = f"{age_s}秒前" if age_s is not None else "尚未生成 live_state.json"
    bad_lines = int(pipe.get("corrupt_snapshot_lines") or 0) + int(pipe.get("corrupt_archive_lines") or 0)
    tmp_cnt = int(pipe.get("orphan_tmp_count") or 0)

    print("")
    print(f"{BOLD}【实时采集链路诊断】{RESET}")
    print(f"  • 状态栏配置 : {f'{GREEN}✓ 正常{RESET}' if sl_ok else f'{YELLOW}⚠ 待修复{RESET}'} ({rep.get('settings_file')})")
    print(f"  • 后台监控台 : {f'{GREEN}● 运行中 (PID {daemon_pid}){RESET}' if daemon_pid else f'{YELLOW}○ 未运行{RESET}'}")
    print(f"  • 最近采集   : {age_txt}")
    print(f"  • 缓存完整性 : 损坏行 {bad_lines} 条 · 遗留临时文件 {tmp_cnt} 个")

    empty_cnt = len(rep["empty_db_entries"])
    orphan_cnt = len(rep["orphan_brain_dirs"])
    stale_cnt = len(rep["stale_sessions"])
    stale_bytes = sum(x["bytes"] for x in rep["stale_sessions"])

    print("")
    print(f"{BOLD}【存储扫描明细（安全只读模式，不直接篡改 AGY SQLite 库）】{RESET}")
    print(f"  • 空壳/零步数记录 : {empty_cnt} 条")
    print(f"  • 孤儿 brain 目录 : {orphan_cnt} 个")
    print(f"  • 超过 {rep['stale_days']} 天陈旧会话: {stale_cnt} 个（共占 {_fmt_bytes(stale_bytes)}）")

    if rep["stale_sessions"]:
        print(f"\n  {DIM}Top 陈旧大体积会话:{RESET}")
        for s in rep["stale_sessions"][:8]:
            print(
                f"    {DIM}{s['short_id']}{RESET}  {_fmt_bytes(s['bytes']):>9}  "
                f"{s['age_days']:>3}天前 ({s['last_cst']})  {trunc_display(s['title'], 32)}"
            )

    if getattr(args, "fix", False):
        print("")
        fix_rep = run_doctor(stale_days=int(args.stale_days), prune_stale=False, fix_issues=True)
        c_res = clean_cache(keep_days=30)
        for act in fix_rep.get("fixed_actions") or []:
            print(f"  {GREEN}✓ 已修复: {act}{RESET}")
        if c_res["bytes_freed"] > 0:
            print(f"  {GREEN}✓ 已压缩自有缓存，释放 {_fmt_bytes(c_res['bytes_freed'])}{RESET}")
        if not daemon_pid:
            ns = argparse.Namespace(action="start", port=18420, no_open=True)
            cmd_daemon(ns)
    elif not sl_ok or bad_lines > 0 or tmp_cnt > 0:
        print(f"\n  {YELLOW}提示：发现可自动修复的本地配置或临时文件问题，可运行: agy-usage doctor --fix{RESET}")

    if args.prune_stale:
        p_rep = run_doctor(stale_days=int(args.stale_days), prune_stale=True, fix_issues=False)
        print("")
        if p_rep["deleted_ids"]:
            print(f"  {GREEN}✓ 已通过官方 ConversationService 安全清理 {len(p_rep['deleted_ids'])} 个失效/陈旧会话{RESET}")
        elif not p_rep["ls_api_available"]:
            print(
                f"  {YELLOW}提示：当前不在 agy 内部会话环境中（未检测到 ANTIGRAVITY_LS_ADDRESS）。{RESET}\n"
                f"  {DIM}为保护 conversation_summaries.db WAL 锁安全，外部终端不直接硬删 SQLite；可在 agy 会话内运行 `agy-usage doctor --prune-stale` 或用 `/delete` 安全清理老会话。{RESET}"
            )
        else:
            print(f"  {GREEN}✓ 无需清理，未发现超期陈旧会话。{RESET}")
    elif stale_cnt > 0 or empty_cnt > 0:
        print(f"\n  {DIM}如需在 agy 内通过官方接口安全清理上述空壳与超期会话，可运行: agy-usage doctor --stale-days {rep['stale_days']} --prune-stale{RESET}")

    return 0


def cmd_notify(args: argparse.Namespace) -> int:
    act = args.action
    if act == "on":
        set_preferences(notifications_enabled=True)
        print(f"{GREEN}✓ 已开启额度告警 (80%/95%) 与回血桌面通知{RESET}")
        return 0
    if act == "off":
        set_preferences(notifications_enabled=False)
        print(f"{DIM}○ 已关闭桌面通知提醒{RESET}")
        return 0
    prefs = get_preferences()
    st = f"{GREEN}开启{RESET}" if prefs.get("notifications_enabled") else f"{DIM}关闭（默认）{RESET}"
    print(f"桌面通知状态: {st}（可用 `agy-usage notify on` 或 `off` 切换）")
    return 0


def cmd_record_quota(args: argparse.Namespace) -> int:
    try:
        res = save_manual_quota(args.bucket, args.remaining_pct, args.reset)
    except (ValueError, TimeoutError) as exc:
        print(f"{RED}{exc}{RESET}", file=sys.stderr)
        return 1
    rem = res["remaining_pct"]
    print(f"{GREEN}✓ 已记录限额快照:{RESET} {res['bucket']} 剩余 {rem:.1f}% (已用 {100.0 - rem:.1f}%)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agy-usage",
        description="Antigravity CLI (agy) 实时用量与每周限额分析统计工具",
    )
    p.add_argument(
        "-w",
        "--window",
        choices=["5h", "today", "24h", "week", "7d", "all"],
        default="7d",
        help="明细统计窗口（默认 7d）",
    )
    p.add_argument("--compact", action="store_true", help="精简输出模式")

    sub = p.add_subparsers(dest="cmd")

    p_watch = sub.add_parser("watch", help="终端实时自动刷新监控面板")
    p_watch.add_argument("-i", "--interval", type=float, default=2.0, help="刷新间隔秒数（默认 2）")
    p_watch.add_argument("-w", "--window", choices=["5h", "today", "24h", "week", "7d", "all"], default="7d")
    p_watch.add_argument("--compact", action="store_true")

    p_web = sub.add_parser("web", help="前台启动本地实时 Web 可视化看板")
    p_web.add_argument("-p", "--port", type=int, default=18420, help="监听端口（默认 18420）")
    p_web.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    p_web.add_argument("--daemon-log", action="store_true", help=argparse.SUPPRESS)

    p_d = sub.add_parser("daemon", help="后台常驻管理本地 Web 监控台 (start/stop/restart/status)")
    p_d.add_argument("action", choices=["start", "stop", "restart", "status"])
    p_d.add_argument("-p", "--port", type=int, default=18420, help="监听端口（默认 18420）")
    p_d.add_argument("--no-open", action="store_true", help="启动时不自动打开浏览器")

    p_json = sub.add_parser("json", help="输出结构化 JSON 分析数据")
    p_json.add_argument("-w", "--window", choices=["5h", "today", "24h", "week", "7d", "all"], default="7d")

    p_inst = sub.add_parser("install-statusline", help="将实时状态栏与限额采集器写入 agy settings.json")
    p_inst.add_argument("--stack", dest="stack", action="store_true", default=True, help="叠加在默认状态栏下方（默认开启）")
    p_inst.add_argument("--standalone", dest="stack", action="store_false", help="替换默认状态栏并显示模型名")

    sub.add_parser("uninstall-statusline", help="从 agy settings.json 移除 statusLine 配置")

    p_rec = sub.add_parser("record-quota", help="手动录入一次 /usage 看到的限额快照")
    p_rec.add_argument("bucket", help="限额桶名，如 gemini-weekly / gemini-5h / claude-weekly")
    p_rec.add_argument("remaining_pct", type=float, help="剩余百分比（0~100）")
    p_rec.add_argument("--reset", help="重置时间（本地时区），如 '2026-12-02 08:00' 或 '12-02 08:00'")

    p_clean = sub.add_parser("clean", help="压缩去重快照、轮转日志并清理孤儿缓存索引")
    p_clean.add_argument("--keep-days", type=int, default=30, help="保留高频快照天数，超期自动按日归档（默认 30）")
    p_clean.add_argument("--reset-index", action="store_true", help="清空并重建 transcript 增量索引缓存")
    p_clean.add_argument("--max-backups", type=int, default=3, help="最多保留几份 settings.json 备份（默认 3）")

    p_doc = sub.add_parser("doctor", help="先只读诊断链路与存储健康，可选 --fix 一键自修复或官方接口清理")
    p_doc.add_argument("--stale-days", type=int, default=30, help="超过多少天未活跃视为陈旧会话（默认 30）")
    p_doc.add_argument("--fix", action="store_true", help="自动修复 statusLine 配置、可执行权限、损坏行与孤儿临时文件")
    p_doc.add_argument("--prune-stale", action="store_true", help="通过官方 ConversationService 接口安全删除空壳与超期会话")

    p_not = sub.add_parser("notify", help="管理 80%/95% 额度告警与回血桌面通知（默认关闭）")
    p_not.add_argument("action", nargs="?", choices=["on", "off", "status"], default="status")

    return p


def main() -> int:
    if os.name == "nt":
        os.system("")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd == "watch":
        return cmd_watch(args)
    if args.cmd == "web":
        return cmd_web(args)
    if args.cmd == "daemon":
        return cmd_daemon(args)
    if args.cmd == "json":
        return cmd_json(args)
    if args.cmd == "install-statusline":
        return cmd_install_statusline(args)
    if args.cmd == "uninstall-statusline":
        return cmd_uninstall_statusline(args)
    if args.cmd == "record-quota":
        return cmd_record_quota(args)
    if args.cmd == "clean":
        return cmd_clean(args)
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "notify":
        return cmd_notify(args)
    return cmd_report(args)


if __name__ == "__main__":
    raise SystemExit(main())
