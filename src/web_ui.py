#!/usr/bin/env python3
"""Clean, high-density, zero-CDN real-time Web Dashboard for Antigravity CLI (agy-usage)."""

from __future__ import annotations

from i18n import LANG_OPTIONS_JS, WEB_I18N_JS

_DASHBOARD_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link rel="icon" type="image/png" href="__LOGO_DATA_URI__" />
<title>Antigravity 实时额度与用量监控台 · Quota &amp; Usage Monitor</title>
<script>
(function () {
  var p = localStorage.getItem('agy-usage-theme') || 'system';
  var r = (p === 'light' || p === 'dark' || p === 'tongtou') ? p
    : (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  document.documentElement.setAttribute('data-theme', r);
  document.documentElement.style.colorScheme = (r === 'dark') ? 'dark' : 'light';
})();
</script>
<style>
  :root[data-theme="dark"] {
    color-scheme: dark;
    --bg: #1e293b;
    --bg-grad: radial-gradient(1000px 480px at 12% -10%, rgba(56, 189, 248, 0.12), transparent 60%),
               radial-gradient(800px 420px at 88% -5%, rgba(139, 92, 246, 0.12), transparent 55%);
    --panel: rgba(51, 65, 85, 0.78);
    --panel-solid: #334155;
    --panel-sub: rgba(30, 41, 59, 0.72);
    --panel-hover: rgba(71, 85, 105, 0.55);
    --border: rgba(226, 232, 240, 0.14);
    --border-strong: rgba(56, 189, 248, 0.42);
    --text: #e2e8f0;
    --text-strong: #f8fafc;
    --muted: #94a3b8;
    --chip-bg: rgba(30, 41, 59, 0.72);
    --track: #475569;
    --grid-line: rgba(226, 232, 240, 0.10);
    --heat-0: #334155;
    --heat-1: #155e75;
    --heat-2: #0284c7;
    --heat-3: #38bdf8;
    --heat-4: #a78bfa;
    --shadow: 0 6px 22px rgba(15, 23, 42, 0.28);
    --tip-bg: rgba(51, 65, 85, 0.96);
    --marker: #f8fafc;
  }
  :root[data-theme="light"] {
    color-scheme: light;
    --bg: #fff5f8;
    --bg-grad:
      radial-gradient(920px 540px at 6% -12%, rgba(255, 183, 197, 0.62), transparent 58%),
      radial-gradient(760px 500px at 96% -8%, rgba(196, 181, 253, 0.48), transparent 56%),
      radial-gradient(640px 420px at 48% 108%, rgba(125, 211, 252, 0.30), transparent 52%),
      linear-gradient(165deg, #fff8fb 0%, #fdeef6 42%, #f3e8ff 100%);
    --panel: rgba(255, 255, 255, 0.38);
    --panel-solid: rgba(255, 252, 254, 0.72);
    --panel-sub: rgba(255, 255, 255, 0.28);
    --panel-hover: rgba(255, 255, 255, 0.55);
    --border: rgba(255, 255, 255, 0.66);
    --border-strong: rgba(244, 114, 182, 0.42);
    --text: #4a3540;
    --text-strong: #3a2430;
    --muted: #745664;
    --chip-bg: rgba(255, 255, 255, 0.36);
    --track: rgba(244, 114, 182, 0.16);
    --grid-line: rgba(244, 114, 182, 0.12);
    --heat-0: #fce7f3;
    --heat-1: #fbcfe8;
    --heat-2: #f9a8d4;
    --heat-3: #e879f9;
    --heat-4: #c4b5fd;
    --shadow: 0 10px 34px rgba(244, 114, 182, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.78);
    --tip-bg: rgba(255, 252, 254, 0.62);
    --marker: #be185d;
    --glass-blur: 18px;
  }
  :root[data-theme="tongtou"] {
    color-scheme: light;
    --bg: #F5F0EB;
    --bg-grad:
      radial-gradient(760px 520px at 8% -8%, rgba(123, 167, 167, 0.28), transparent 70%),
      radial-gradient(640px 460px at 94% 4%, rgba(196, 168, 130, 0.24), transparent 68%),
      linear-gradient(180deg, #F5F0EB 0%, #F3EDE6 100%);
    --panel: rgba(255, 253, 251, 0.76);
    --panel-solid: rgba(255, 253, 251, 0.94);
    --panel-sub: rgba(255, 253, 251, 0.58);
    --panel-hover: rgba(255, 253, 251, 0.88);
    --border: rgba(232, 226, 219, 0.92);
    --border-strong: rgba(123, 167, 167, 0.55);
    --text: #4A4A4A;
    --text-strong: #2C3E50;
    --muted: rgba(74, 74, 74, 0.64);
    --chip-bg: rgba(255, 253, 251, 0.86);
    --track: #E8E2DB;
    --grid-line: rgba(232, 226, 219, 0.9);
    --heat-0: #EDE6DE;
    --heat-1: #C9D6D6;
    --heat-2: #7BA7A7;
    --heat-3: #C4A882;
    --heat-4: #2C3E50;
    --shadow: 0 16px 36px rgba(44, 62, 80, 0.08);
    --tip-bg: rgba(255, 253, 251, 0.86);
    --marker: #7BA7A7;
    --glass-blur: 18px;
  }
  :root {
    --cyan: #38bdf8;
    --blue: #3b82f6;
    --purple: #a78bfa;
    --green: #10b981;
    --yellow: #f59e0b;
    --red: #ef4444;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    background-image: var(--bg-grad);
    background-attachment: fixed;
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei UI", sans-serif;
    font-size: 12px;
    line-height: 1.45;
    -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 1380px; margin: 0 auto; padding: 14px 20px 42px; }

  /* Compact Header */
  header {
    display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
    gap: 10px; margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--border);
  }
  .brand { display: flex; align-items: center; gap: 10px; }
  .logo {
    width: 32px; height: 32px; border-radius: 8px; display: block; object-fit: cover;
    box-shadow: 0 3px 10px rgba(15, 23, 42, 0.22); flex-shrink: 0;
  }
  h1 { margin: 0; font-size: 15px; font-weight: 700; color: var(--text-strong); letter-spacing: -0.1px; }
  .sub { font-size: 11px; color: var(--muted); display: flex; align-items: center; gap: 6px; }
  .controls { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .pills {
    display: inline-flex; background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; padding: 2px;
  }
  .pill {
    border: 0; background: transparent; color: var(--muted); padding: 4px 9px;
    border-radius: 6px; font-size: 11.5px; cursor: pointer; font-weight: 550; transition: all .12s;
  }
  .pill.active { background: #2563eb; color: #fff; }
  .pill:hover:not(.active) { color: var(--text-strong); }
  .btn {
    background: var(--panel); border: 1px solid var(--border); color: var(--text);
    padding: 4px 9px; border-radius: 8px; font-size: 11.5px; cursor: pointer; font-weight: 550;
    transition: border-color .12s; display: inline-flex; align-items: center; gap: 5px;
  }
  .btn:hover { border-color: var(--border-strong); }
  .btn.primary { background: #2563eb; border-color: transparent; color: #fff; }
  .btn.live-on { border-color: rgba(16, 185, 129, 0.4); color: var(--green); }

  /* Raycast/Linear Rotating Conic Beam + Duolingo Living Vector Flame CTA */
  @property --beam-angle {
    syntax: '<angle>';
    initial-value: 0deg;
    inherits: false;
  }
  @keyframes spin-beam { to { --beam-angle: 360deg; } }
  @keyframes flame-dance {
    0%   { transform: scale(1, 0.96) rotate(-3deg); filter: drop-shadow(0 0 4px rgba(255,85,0,0.65)); }
    50%  { transform: scale(1.08, 1.12) rotate(2.5deg); filter: drop-shadow(0 0 9px rgba(255,140,0,0.95)); }
    100% { transform: scale(0.98, 1.05) rotate(-1.5deg); filter: drop-shadow(0 0 6px rgba(255,60,40,0.80)); }
  }
  @keyframes ember-rise {
    0%   { transform: translateY(0) scale(1); opacity: 0.95; }
    100% { transform: translateY(-7px) scale(0.3); opacity: 0; }
  }
  @keyframes cta-shimmer {
    0%, 62% { transform: translateX(-140%) skewX(-22deg); }
    100%    { transform: translateX(260%) skewX(-22deg); }
  }
  .fire-cta {
    position: relative; border: 0; padding: 2px; border-radius: 999px; cursor: pointer;
    display: inline-flex; align-items: center; vertical-align: middle;
    background: conic-gradient(from var(--beam-angle), #ff2d55, #ff7a00, #ffd60a, #ff375f, #a855f7, #ff2d55);
    animation: spin-beam 2.8s linear infinite;
    box-shadow: 0 4px 16px rgba(255, 90, 31, 0.34), 0 0 0 1px rgba(255, 122, 0, 0.18);
    transition: transform .16s cubic-bezier(.2,.9,.3,1.2), box-shadow .16s ease;
  }
  .fire-cta:hover {
    transform: translateY(-1.5px) scale(1.03);
    box-shadow: 0 7px 24px rgba(255, 75, 31, 0.52), 0 0 14px rgba(255, 168, 0, 0.38);
  }
  .fire-cta:active { transform: translateY(0.5px) scale(0.99); }
  .fire-cta-in {
    position: relative; overflow: hidden; border-radius: 999px;
    padding: 4.5px 13px 4.5px 10px; display: inline-flex; align-items: center; gap: 6px;
    background: linear-gradient(135deg, #1a1025 0%, #2b1222 52%, #331810 100%);
    color: #fff7ed; font-size: 12px; font-weight: 750; letter-spacing: 0.15px; white-space: nowrap;
  }
  :root[data-theme="tongtou"] .fire-cta-in {
    background: linear-gradient(135deg, #2b211d 0%, #3d241c 55%, #4a2c1d 100%);
  }
  :root[data-theme="light"] .fire-cta-in {
    background: linear-gradient(135deg, #be185d 0%, #e11d48 48%, #ea580c 100%);
  }
  .fire-cta-in::after {
    content: ""; position: absolute; top: 0; bottom: 0; width: 42%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.32), transparent);
    animation: cta-shimmer 3.4s ease-in-out infinite; pointer-events: none;
  }
  .fire-svg {
    width: 16px; height: 16px; flex-shrink: 0; overflow: visible;
    transform-origin: 50% 86%;
    animation: flame-dance 0.95s ease-in-out infinite alternate;
  }
  .fire-cta:hover .fire-svg { animation-duration: 0.55s; transform: scale(1.2); }
  .fire-svg .eb1 { animation: ember-rise 1.2s ease-out infinite; }
  .fire-svg .eb2 { animation: ember-rise 1.2s ease-out 0.55s infinite; }
  .fire-stat-hl {
    color: #fde047; font-weight: 800; font-variant-numeric: tabular-nums;
  }
  :root[data-theme="light"] .fire-stat-hl { color: #fef08a; }
  .spark-dot {
    position: fixed; width: 6px; height: 6px; border-radius: 50%; pointer-events: none; z-index: 99999;
    transition: transform .62s cubic-bezier(.15,.85,.35,1), opacity .62s ease-out;
  }
  @media (prefers-reduced-motion: reduce) {
    .fire-cta, .fire-cta-in::after, .fire-svg, .fire-svg .eb1, .fire-svg .eb2 { animation: none; }
  }
  select.lang-sel {
    appearance: auto; padding-right: 6px; max-width: 132px; outline: none; font-family: inherit;
  }

  .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--muted); }
  .dot.ok { background: var(--green); box-shadow: 0 0 6px rgba(16, 185, 129, 0.65); }
  .dot.warn { background: var(--yellow); }
  .dot.err { background: var(--red); }

  /* Single-line Status Strip */
  .status-strip {
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    padding: 8px 13px; margin-bottom: 10px;
    display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 14px;
    font-size: 11.5px;
  }
  .strip-left { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; }
  .kv { display: inline-flex; align-items: center; gap: 5px; }
  .kv .k { color: var(--muted); font-size: 11px; }
  .kv .v { font-weight: 600; color: var(--text-strong); }
  .code-chip {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px;
    background: var(--chip-bg); border: 1px solid var(--border); border-radius: 6px;
    padding: 2px 8px; color: var(--cyan); cursor: pointer;
  }
  .code-chip:hover { border-color: var(--cyan); }

  /* Compact Insights Chips */
  .insights-bar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
  .ichip {
    display: inline-flex; align-items: center; gap: 6px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 5px 10px; font-size: 11px; color: var(--muted);
  }
  .ichip b { color: var(--text-strong); font-weight: 600; }
  .ichip.warn { border-left: 3px solid var(--yellow); }
  .ichip.crit { border-left: 3px solid var(--red); }
  .ichip.ok { border-left: 3px solid var(--green); }
  .ichip.info { border-left: 3px solid var(--cyan); }

  /* Layout Grids */
  .grid { display: grid; gap: 12px; margin-bottom: 12px; }
  .grid-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .grid-main { grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); }
  @media (max-width: 1024px) {
    .grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .grid-main { grid-template-columns: minmax(0, 1fr); }
  }
  @media (max-width: 780px) {
    .grid-2, .grid-4 { grid-template-columns: minmax(0, 1fr); }
  }

  .card {
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 13px 15px; box-shadow: var(--shadow); min-width: 0; overflow: hidden;
  }
  .card.pool-gemini { border-top: 2px solid rgba(56, 189, 248, 0.65); }
  .card.pool-claude { border-top: 2px solid rgba(167, 139, 250, 0.65); }
  .card-head {
    display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 6px;
    margin-bottom: 10px;
  }
  .card-title { font-size: 12.5px; font-weight: 650; color: var(--text-strong); display: flex; align-items: center; gap: 6px; }
  .card-sub { font-size: 11px; color: var(--muted); font-weight: 400; }

  .badge {
    font-size: 10.5px; font-weight: 600; padding: 1.5px 7px; border-radius: 999px;
    background: rgba(56, 189, 248, 0.13); color: var(--cyan); white-space: nowrap;
  }
  .badge.ok { background: rgba(16, 185, 129, 0.13); color: var(--green); }
  .badge.warn { background: rgba(245, 158, 11, 0.15); color: var(--yellow); }
  .badge.crit { background: rgba(239, 68, 68, 0.15); color: var(--red); }
  .badge.purple { background: rgba(167, 139, 250, 0.15); color: var(--purple); }
  .badge.muted { background: rgba(132, 148, 173, 0.13); color: var(--muted); }

  /* Compact Dual-Row Pool Quota Card */
  .bucket-stack { display: flex; flex-direction: column; gap: 9px; }
  .bucket-item {
    background: var(--panel-sub); border: 1px solid var(--border); border-radius: 9px;
    padding: 9px 11px; display: grid; grid-template-columns: 58px minmax(0, 1fr); gap: 11px; align-items: center;
  }
  .mini-ring { position: relative; width: 58px; height: 58px; flex-shrink: 0; }
  .mini-ring-txt {
    position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center; font-variant-numeric: tabular-nums;
  }
  .mini-ring-pct { font-size: 12.5px; font-weight: 700; line-height: 1.1; }
  .mini-ring-lbl { font-size: 9px; color: var(--muted); }
  .b-top { display: flex; justify-content: space-between; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 11.5px; }
  .b-name { font-weight: 650; color: var(--text-strong); }
  .dual-bar { position: relative; height: 6px; border-radius: 99px; background: var(--track); margin: 5px 0; }
  .dual-fill { height: 100%; border-radius: 99px; transition: width .3s ease; }
  .time-marker {
    position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--marker);
    border-radius: 1px; box-shadow: 0 0 4px rgba(15, 23, 42, 0.35);
  }
  .b-meta {
    display: flex; flex-wrap: wrap; justify-content: space-between; gap: 3px 10px;
    font-size: 10.5px; color: var(--muted); font-variant-numeric: tabular-nums;
  }
  .b-meta strong { color: var(--text); font-weight: 600; }

  /* KPI Strip */
  .kpi-card { padding: 11px 14px; }
  .kpi-val { font-size: 16.5px; font-weight: 650; color: var(--text-strong); font-variant-numeric: tabular-nums; margin: 3px 0 2px; }
  .kpi-sub { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }
  .kpi-foot {
    display: flex; justify-content: space-between; font-size: 10.5px; color: var(--muted);
    margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--border); font-variant-numeric: tabular-nums;
  }

  /* Bars & Charts */
  .bar-track { height: 5px; border-radius: 99px; background: var(--track); overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 99px; }
  .chart-box { width: 100%; overflow-x: auto; }
  .legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 11px; color: var(--muted); margin-top: 6px; }
  .legend-item { display: inline-flex; align-items: center; gap: 5px; }
  .swatch { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }

  /* Heatmap */
  .heatmap-wrap { overflow-x: auto; }
  .heatmap-table { border-collapse: separate; border-spacing: 2.5px; width: 100%; min-width: 460px; }
  .heatmap-table th { font-size: 9.5px; color: var(--muted); font-weight: 500; text-align: center; padding: 1px 0; border: 0; }
  .heatmap-table td.day-lbl { font-size: 10.5px; color: var(--muted); white-space: nowrap; padding-right: 6px; border: 0; }
  .hcell { height: 16px; border-radius: 3px; background: var(--heat-0); cursor: pointer; transition: transform .1s; }
  .hcell:hover { transform: scale(1.2); outline: 1px solid var(--cyan); }

  /* Clean Compact Tables */
  .search-input {
    background: var(--chip-bg); border: 1px solid var(--border); color: var(--text);
    border-radius: 7px; padding: 4px 9px; font-size: 11.5px; width: 190px; outline: none;
  }
  .search-input:focus { border-color: var(--cyan); }
  table { width: 100%; border-collapse: collapse; font-size: 11.5px; font-variant-numeric: tabular-nums; }
  th {
    text-align: left; color: var(--muted); font-weight: 600; font-size: 10.5px;
    padding: 6px 7px; border-bottom: 1px solid var(--border); white-space: nowrap;
  }
  th.sortable { cursor: pointer; user-select: none; }
  th.sortable:hover { color: var(--text-strong); }
  td { padding: 6px 7px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  tr.clickable { cursor: pointer; }
  tr.clickable:hover td { background: var(--panel-hover); }
  .num { text-align: right; white-space: nowrap; }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; }
  .ellipsis { max-width: 210px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tag {
    display: inline-block; padding: 0 5px; border-radius: 4px; font-size: 10px; font-weight: 600;
    background: rgba(167, 139, 250, 0.15); color: var(--purple); margin-left: 4px;
  }
  .tool-pill {
    display: inline-block; padding: 0 5px; border-radius: 4px; font-size: 10px;
    background: rgba(56, 189, 248, 0.11); color: var(--cyan); margin-left: 3px; font-family: ui-monospace, monospace;
  }

  /* Onboarding */
  .onboarding { border: 1px dashed var(--border-strong); }

  /* Floating Glass Tooltip */
  #tip {
    position: fixed; pointer-events: none; z-index: 9999; display: none;
    background: var(--tip-bg); color: var(--text); border: 1px solid var(--border-strong);
    border-radius: 8px; padding: 7px 10px; font-size: 11px; line-height: 1.45;
    box-shadow: var(--shadow); max-width: 260px; backdrop-filter: blur(8px);
  }
  #tip .th { font-weight: 650; color: var(--cyan); margin-bottom: 2px; }

  /* Drawer & Modal */
  .backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5); z-index: 900; display: none; backdrop-filter: blur(3px); }
  .backdrop.open { display: block; }
  .drawer {
    position: fixed; top: 0; right: 0; bottom: 0; width: min(640px, 94vw);
    background: var(--panel-solid); border-left: 1px solid var(--border);
    z-index: 950; transform: translateX(100%); transition: transform .2s ease;
    display: flex; flex-direction: column; box-shadow: -10px 0 32px rgba(0,0,0,0.4);
  }
  .drawer.open { transform: translateX(0); }
  .drawer-head {
    padding: 13px 16px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
  }
  .drawer-body { padding: 14px 16px; overflow-y: auto; flex: 1; }

  .modal {
    position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: min(410px, 92vw); background: var(--panel-solid); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px; z-index: 960; display: none; box-shadow: 0 16px 48px rgba(0,0,0,0.5);
  }
  .modal.modal-wide { width: min(740px, 95vw); border-radius: 16px; padding: 16px 18px; }
  .modal.open { display: block; }
  .sc-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
  .sc-preview-wrap {
    background: var(--chip-bg); border: 1px solid var(--border); border-radius: 12px;
    padding: 10px; display: grid; place-items: center; margin-bottom: 12px;
  }
  #sc-canvas { width: 100%; max-width: 680px; height: auto; border-radius: 12px; display: block; box-shadow: 0 10px 28px rgba(0,0,0,0.18); }
  .sc-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
  .sc-chk { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; color: var(--text); cursor: pointer; user-select: none; }
  .field { margin-bottom: 10px; }
  .field label { display: block; font-size: 11px; color: var(--muted); margin-bottom: 4px; font-weight: 600; }
  .field input, .field select {
    width: 100%; background: var(--chip-bg); border: 1px solid var(--border); color: var(--text);
    border-radius: 7px; padding: 6px 9px; font-size: 12px; outline: none;
  }

  .footnote { font-size: 10.5px; color: var(--muted); margin-top: 12px; text-align: right; }

  :root[data-theme="light"] .card,
  :root[data-theme="light"] .status-strip,
  :root[data-theme="light"] .ichip,
  :root[data-theme="light"] .pills,
  :root[data-theme="light"] .btn,
  :root[data-theme="light"] .bucket-item,
  :root[data-theme="light"] .code-chip,
  :root[data-theme="light"] .modal,
  :root[data-theme="light"] .drawer {
    background: var(--panel);
    backdrop-filter: blur(var(--glass-blur)) saturate(1.45);
    -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(1.45);
    box-shadow: var(--shadow);
  }
  :root[data-theme="light"] .card { border-radius: 16px; }
  :root[data-theme="light"] .status-strip {
    border-radius: 14px;
    background: rgba(255, 252, 254, 0.80);
    border-color: rgba(244, 114, 182, 0.36);
    box-shadow: 0 6px 20px rgba(244, 114, 182, 0.14), inset 0 1px 0 rgba(255, 255, 255, 0.92);
  }
  :root[data-theme="light"] .status-strip .kv .k { color: #664957; font-weight: 550; }
  :root[data-theme="light"] .status-strip .code-chip {
    background: rgba(255, 255, 255, 0.86);
    border-color: rgba(14, 116, 144, 0.34);
    color: #0e7490;
  }
  :root[data-theme="light"] .ichip { border-radius: 14px; }
  :root[data-theme="light"] .pill.active {
    background: linear-gradient(135deg, #fb7185, #e879f9);
    color: #fff;
  }
  :root[data-theme="light"] .btn.primary {
    background: linear-gradient(135deg, #fb7185, #e879f9);
    color: #fff;
  }
  :root[data-theme="light"] .card.pool-gemini { border-top-color: rgba(244, 114, 182, 0.55); }
  :root[data-theme="light"] .card.pool-claude { border-top-color: rgba(196, 181, 253, 0.7); }
  :root[data-theme="light"] header { border-bottom-color: rgba(255, 255, 255, 0.45); }
  :root[data-theme="light"] .backdrop { background: rgba(253, 232, 240, 0.42); }
  @media (prefers-reduced-transparency: reduce) {
    :root[data-theme="light"] .card,
    :root[data-theme="light"] .status-strip,
    :root[data-theme="light"] .ichip,
    :root[data-theme="light"] .pills,
    :root[data-theme="light"] .btn,
    :root[data-theme="light"] .bucket-item,
    :root[data-theme="light"] .code-chip,
    :root[data-theme="light"] .modal,
    :root[data-theme="light"] .drawer {
      backdrop-filter: none;
      -webkit-backdrop-filter: none;
      background: rgba(255, 252, 254, 0.94);
    }
  }
  :root[data-theme="tongtou"] .logo {
    background: linear-gradient(135deg, rgba(123, 167, 167, 0.92) 0%, #7BA7A7 100%);
  }
  :root[data-theme="tongtou"] .card,
  :root[data-theme="tongtou"] .status-strip,
  :root[data-theme="tongtou"] .ichip,
  :root[data-theme="tongtou"] .pills,
  :root[data-theme="tongtou"] .btn,
  :root[data-theme="tongtou"] .bucket-item,
  :root[data-theme="tongtou"] .code-chip,
  :root[data-theme="tongtou"] .modal,
  :root[data-theme="tongtou"] .drawer {
    background: var(--panel);
    backdrop-filter: blur(var(--glass-blur));
    -webkit-backdrop-filter: blur(var(--glass-blur));
    box-shadow: var(--shadow);
  }
  :root[data-theme="tongtou"] .card { border-radius: 16px; }
  :root[data-theme="tongtou"] .status-strip,
  :root[data-theme="tongtou"] .ichip { border-radius: 16px; }
  :root[data-theme="tongtou"] .pills,
  :root[data-theme="tongtou"] .btn { border-radius: 999px; }
  :root[data-theme="tongtou"] .pill.active {
    background: linear-gradient(135deg, rgba(123, 167, 167, 0.92) 0%, #7BA7A7 100%);
    color: #fdfbf8;
  }
  :root[data-theme="tongtou"] .btn.primary {
    background: linear-gradient(135deg, rgba(123, 167, 167, 0.92) 0%, #7BA7A7 100%);
    color: #fdfbf8;
    box-shadow: 0 18px 42px rgba(123, 167, 167, 0.28);
  }
  :root[data-theme="tongtou"] .card.pool-gemini { border-top-color: rgba(123, 167, 167, 0.7); }
  :root[data-theme="tongtou"] .card.pool-claude { border-top-color: rgba(196, 168, 130, 0.7); }
  :root[data-theme="tongtou"] header { border-bottom-color: rgba(232, 226, 219, 0.88); }
  :root[data-theme="tongtou"] .backdrop { background: rgba(245, 240, 235, 0.48); }
  :root[data-theme="tongtou"] h1 { letter-spacing: 0.04em; font-weight: 600; }
</style>
</head>
<body>
<div id="tip"></div>
<div class="backdrop" id="backdrop"></div>

<!-- Session Inspector Drawer -->
<aside class="drawer" id="session-drawer">
  <div class="drawer-head">
    <div style="min-width:0">
      <div style="font-weight:650;font-size:13.5px;color:var(--text-strong)" id="dr-title">会话详情</div>
      <div style="font-size:11px;color:var(--muted)" id="dr-sub">加载中...</div>
    </div>
    <button class="btn" data-action="close" data-i18n="dr_close">关闭 ✕</button>
  </div>
  <div class="drawer-body" id="dr-body"></div>
</aside>

<!-- Manual Quota Calibration Modal -->
<div class="modal" id="quota-modal">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
    <strong style="font-size:13.5px;color:var(--text-strong)" data-i18n="mq_title">手动录入 /usage 限额快照</strong>
    <button class="btn" data-action="close">✕</button>
  </div>
  <p style="font-size:11px;color:var(--muted);margin:0 0 10px;" data-i18n="mq_desc">填入 /usage 页面看到的「已使用 %」，即可立即生成周配速与耗尽预测。</p>
  <div class="field">
    <label data-i18n="mq_pool">限额池</label>
    <select id="mq-bucket">
      <option value="gemini-5h">Gemini · 5h (gemini-5h)</option>
      <option value="gemini-weekly">Gemini · 7d (gemini-weekly)</option>
      <option value="claude-5h">Claude/GPT · 5h (3p-5h)</option>
      <option value="claude-weekly">Claude/GPT · 7d (3p-weekly)</option>
    </select>
  </div>
  <div class="field">
    <label data-i18n="mq_used">已使用百分比 (0 ~ 100)</label>
    <input id="mq-used" type="number" step="0.01" min="0" max="100" data-i18n-ph="mq_used_ph" placeholder="例如 9.1 或 54.9" />
  </div>
  <div class="field">
    <label><span data-i18n="mq_reset">重置时间</span> <span id="modal-tz-lbl">UTC+8</span> <span data-i18n="mq_reset_opt">(可选，如 12-01 18:46)</span></label>
    <input id="mq-reset" type="text" placeholder="12-01 18:46" />
  </div>
  <div id="mq-msg" style="font-size:11px;margin-bottom:8px;color:var(--red)"></div>
  <div style="display:flex;justify-content:flex-end;gap:6px;">
    <button class="btn" data-action="close" data-i18n="mq_cancel">取消</button>
    <button class="btn primary" id="mq-save-btn" data-i18n="mq_save">保存</button>
  </div>
</div>

<!-- Viral Share Card Modal -->
<div class="modal modal-wide" id="share-modal">
  <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px;">
    <div style="font-size:13.5px;font-weight:700;color:var(--text-strong);" data-i18n="sc_title">生成战报晒单卡（自动脱敏 · 不含任何路径与会话名）</div>
    <button class="btn" data-action="close" data-i18n="dr_close">关闭 ✕</button>
  </div>
  <div class="sc-toolbar">
    <div style="display:flex;flex-wrap:wrap;align-items:center;gap:6px;">
      <div class="pills" id="sc-win-pills">
        <button class="pill active" type="button" data-sc-win="7d" data-i18n="w_7d">近7天</button>
        <button class="pill" type="button" data-sc-win="today" data-i18n="w_today">今日</button>
        <button class="pill" type="button" data-sc-win="all" data-i18n="w_all">全部</button>
      </div>
      <div class="pills" id="sc-theme-pills">
        <button class="pill active" type="button" data-sc-theme="tongtou" data-i18n="th_tongtou">通透</button>
        <button class="pill" type="button" data-sc-theme="light" data-i18n="th_light">浅色</button>
        <button class="pill" type="button" data-sc-theme="dark" data-i18n="th_dark">深色</button>
      </div>
    </div>
    <label class="sc-chk"><input type="checkbox" id="sc-usd-chk" checked /> <span data-i18n="sc_show_usd">显示估算节省金额 ($)</span></label>
  </div>
  <div class="sc-preview-wrap">
    <canvas id="sc-canvas" width="1560" height="990"></canvas>
  </div>
  <div class="sc-actions">
    <button class="btn" type="button" id="sc-copy-post-btn" data-i18n="sc_copy_post">📝 复制推荐文案+安装口令</button>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <button class="btn" type="button" id="sc-dl-btn" data-i18n="sc_dl_png">⬇️ 下载高清 PNG</button>
      <button class="btn primary" type="button" id="sc-copy-img-btn" data-i18n="sc_copy_img">📋 复制战报图片</button>
    </div>
  </div>
</div>

<div class="wrap">
  <header>
    <div class="brand">
      <img class="logo" id="brand-logo-img" src="__LOGO_DATA_URI__" alt="AGY Usage" width="32" height="32" />
      <div>
        <h1 data-i18n="h1">Antigravity 实时额度与用量监控台</h1>
        <div class="sub"><span class="dot ok"></span><span id="subtitle" data-i18n="syncing">正在同步本地遥测数据...</span></div>
      </div>
    </div>
    <div class="controls">
      <div class="pills" id="win-pills">
        <button class="pill" data-win="5h" data-i18n="w_5h">5小时</button>
        <button class="pill" data-win="today" data-i18n="w_today">今日</button>
        <button class="pill" data-win="24h" data-i18n="w_24h">24h</button>
        <button class="pill" data-win="week" data-i18n="w_week">本周</button>
        <button class="pill active" data-win="7d" data-i18n="w_7d">近7天</button>
        <button class="pill" data-win="all" data-i18n="w_all">全部</button>
      </div>
      <button class="fire-cta" type="button" id="share-btn" data-open-share="1">
        <span class="fire-cta-in">
          <svg class="fire-svg" viewBox="0 0 24 24" aria-hidden="true">
            <circle class="eb1" cx="9" cy="4" r="1.4" fill="#fde047"/>
            <circle class="eb2" cx="15.5" cy="5" r="1.1" fill="#fb923c"/>
            <path d="M12.4 2.2c.4 3.2-1.9 4.9-2.8 6.8-.9 1.9-.3 3.6 1.1 4.2-.3-1.5.5-2.8 1.9-3.6 1.2 1.8 1.7 3.7.9 5.5 1.8-.6 2.9-2.4 2.8-4.5 2.1 1.7 3.1 4.5 2.1 7.2-1.1 2.9-3.9 4.6-6.8 4.6-3.4 0-6.2-2.3-6.7-5.6-.5-3.4 1.5-6.6 4.4-8.9-.2 1.5.4 2.6 1.4 3.1-.5-3.1 1.7-6.3 1.7-8.8z" fill="#ff4d00"/>
            <path d="M12.1 7.6c.7 1.9-.6 3.3-1.3 4.7-.7 1.4-.3 3.1 1.1 3.9-.2-1 .3-2 1.2-2.5.8 1.2.9 2.7.2 3.9 1.6-.5 2.5-2.2 1.9-4.1-.5-1.7-1.9-3.2-3.1-5.9z" fill="#ffb703"/>
            <path d="M11.8 13.2c.5 1.2-.2 2.2-.5 3.1-.3.9.2 2 1.2 2.3.9.2 1.9-.5 2-1.5.2-1.2-.9-2.3-2.7-3.9z" fill="#fffbeb"/>
          </svg>
          <span id="hdr-share-lbl" data-i18n="sc_btn">生成晒单战报卡</span>
        </span>
      </button>
      <button class="btn live-on" id="live-btn"><span class="dot ok"></span><span id="live-btn-lbl" data-i18n="live_on">实时 3s</span></button>
      <button class="btn" id="notify-btn" data-i18n-title="ntf_tip" title="开启或关闭 80%/95% 额度提醒与回血桌面通知">🔔 提醒: 关</button>
      <button class="btn" id="open-modal-btn" data-i18n="add_quota">＋录入限额</button>
      <button class="btn" id="export-btn" data-i18n="export_csv">导出 CSV</button>
      <div class="pills" id="theme-pills" data-i18n-title="th_title" title="外观主题">
        <button class="pill" type="button" data-theme-pref="light" data-i18n="th_light">浅色</button>
        <button class="pill" type="button" data-theme-pref="tongtou" data-i18n="th_tongtou">通透</button>
        <button class="pill" type="button" data-theme-pref="dark" data-i18n="th_dark">深色</button>
        <button class="pill" type="button" data-theme-pref="system" data-i18n="th_system">系统</button>
      </div>
      <select class="btn lang-sel" id="lang-select" data-i18n-title="lang_title" title="切换界面语言 / Language"></select>
    </div>
  </header>

  <div class="status-strip" id="live-banner"></div>
  <div class="insights-bar" id="insights-strip"></div>

  <!-- Row 1: Side-by-side Dual Pool Quota Cards -->
  <div id="quota-section"></div>

  <!-- Row 2: 4 Compact KPI Strip Cards -->
  <div class="grid grid-4" id="kpi-cards"></div>

  <!-- Row 3: Tabbed Trend Chart (Left) + 7x24 Heatmap & Pool Split (Right) -->
  <div class="grid grid-main">
    <div class="card">
      <div class="card-head">
        <div class="pills" id="chart-tabs">
          <button class="pill active" data-ctab="5h" data-i18n="ct_5h">近5h燃速 (10m)</button>
          <button class="pill" data-ctab="24h" data-i18n="ct_24h">24h每小时</button>
          <button class="pill" data-ctab="7d" data-i18n="ct_7d">7日周趋势</button>
          <button class="pill" data-ctab="quota" data-i18n="ct_quota">限额已用曲线</button>
        </div>
        <div class="pills" id="metric-pills">
          <button class="pill active" data-metric="billable_tokens" data-i18n="m_billable">有效Token</button>
          <button class="pill" data-metric="total_tokens" data-i18n="m_total">含缓存</button>
          <button class="pill" data-metric="calls" data-i18n="m_calls">调用数</button>
          <button class="pill" data-metric="est_cost_usd" data-i18n="m_cost">估算$</button>
        </div>
      </div>
      <div class="chart-box" id="main-chart-box"></div>
      <div class="legend" id="main-chart-legend"></div>
    </div>

    <div class="card">
      <div class="card-head">
        <span class="card-title"><span data-i18n="hm_title">7日 × 24小时作业热力图</span> <span class="card-sub">(<span id="tz-lbl">UTC+8</span>)</span></span>
        <div style="display:inline-flex;align-items:center;gap:4px;font-size:10px;color:var(--muted);">
          <span data-i18n="hm_low">低</span>
          <span class="swatch" style="background:var(--heat-0)"></span>
          <span class="swatch" style="background:var(--heat-1)"></span>
          <span class="swatch" style="background:var(--heat-2)"></span>
          <span class="swatch" style="background:var(--heat-3)"></span>
          <span class="swatch" style="background:var(--heat-4)"></span>
          <span data-i18n="hm_high">高</span>
        </div>
      </div>
      <div class="heatmap-wrap" id="heatmap-box"></div>
      <div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border);">
        <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:6px;">
          <span><span data-i18n="pool_share_lbl">模型限额池占比</span> (<span id="win-badge-pool">近7天</span>)</span>
          <span id="pool-total-lbl"></span>
        </div>
        <div id="pool-compact-bars"></div>
      </div>
    </div>
  </div>

  <!-- Row 4: Tabbed Breakdown Table (Left) + Compact Live Stream (Right) -->
  <div class="grid grid-main">
    <div class="card">
      <div class="card-head">
        <div class="pills" id="detail-tabs">
          <button class="pill active" data-dtab="convs" data-i18n="dt_convs">会话消耗排行</button>
          <button class="pill" data-dtab="models" data-i18n="dt_models">细分模型明细</button>
          <button class="pill" data-dtab="tools" data-i18n="dt_tools">工作区 &amp; 高频工具</button>
        </div>
        <input class="search-input" id="conv-search" type="text" data-i18n-ph="search_ph" placeholder="搜索会话 / 工作区 / 模型..." />
      </div>
      <div id="detail-pane-convs" style="overflow-x:auto;">
        <table>
          <thead>
            <tr>
              <th><span data-i18n="th_conv">会话标题</span> <span style="font-weight:400;color:var(--muted)" data-i18n="th_conv_hint">(点击看逐轮曲线)</span></th>
              <th data-i18n="th_ws">工作区</th>
              <th class="num sortable" data-sort="calls" data-i18n="th_calls_s">调用 ↕</th>
              <th class="num sortable" data-sort="billable_tokens" data-i18n="th_bill_s">有效Token ↕</th>
              <th class="num sortable" data-sort="peak_context" data-i18n="th_peak_s">峰值上下文 ↕</th>
              <th class="num sortable" data-sort="cache_hit_pct" data-i18n="th_hit_s">缓存率 ↕</th>
              <th class="num sortable" data-sort="est_cost_usd" data-i18n="th_cost_s">估算$ ↕</th>
            </tr>
          </thead>
          <tbody id="conv-tbody"></tbody>
        </table>
      </div>
      <div id="detail-pane-models" style="display:none;overflow-x:auto;">
        <table>
          <thead>
            <tr>
              <th data-i18n="th_model">模型名称</th>
              <th data-i18n="th_pool">所属限额池</th>
              <th class="num" data-i18n="th_calls">调用</th>
              <th class="num" data-i18n="th_in">新增输入</th>
              <th class="num" data-i18n="th_cache">缓存命中</th>
              <th class="num" data-i18n="th_out">输出</th>
              <th class="num" data-i18n="th_hit">缓存率</th>
              <th class="num" data-i18n="th_cost">估算$</th>
            </tr>
          </thead>
          <tbody id="model-tbody"></tbody>
        </table>
      </div>
      <div id="detail-pane-tools" style="display:none;">
        <div class="grid grid-2" style="margin-bottom:0">
          <div>
            <div style="font-size:11.5px;font-weight:600;margin-bottom:8px;color:var(--text-strong)" data-i18n="ws_share">工作区消耗占比</div>
            <div id="project-list"></div>
          </div>
          <div>
            <div style="font-size:11.5px;font-weight:600;margin-bottom:8px;color:var(--text-strong)" data-i18n="top_tools">高频 Agent 工具调用</div>
            <div id="tools-list"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <span class="card-title" data-i18n="recent_title">最近调用实时流水</span>
        <span class="badge ok" data-i18n="recent_badge">最新 18 条</span>
      </div>
      <div style="overflow-x:auto;max-height:340px;overflow-y:auto;">
        <table>
          <thead>
            <tr>
              <th data-i18n="th_time">时间</th>
              <th data-i18n="th_model_conv">模型 / 会话</th>
              <th class="num" data-i18n="th_in_short">新增</th>
              <th class="num" data-i18n="th_cache_short">缓存</th>
              <th class="num" data-i18n="th_out">输出</th>
            </tr>
          </thead>
          <tbody id="recent-tbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="footnote" data-i18n="footnote">
    纯本地隐私架构 · 数据仅保存在本机 · 费用与缓存节省按公开单价估算，非官方账单。
  </div>
</div>

<script>
const LANG_OPTIONS = __LANG_OPTIONS_JSON__;
const I18N = __WEB_I18N_JSON__;
const POOL_COLORS = { gemini_pro: '#38bdf8', claude_gpt: '#a78bfa', gemini_flash: '#10b981', other: '#64748b' };

const LANG_KEY = 'agy-usage-lang';
function detectBrowserLang() {
  const list = (navigator.languages && navigator.languages.length) ? navigator.languages : [navigator.language || 'en'];
  for (const raw of list) {
    const lc = String(raw || '').toLowerCase();
    if (!lc) continue;
    if (lc === 'zh-tw' || lc === 'zh-hk' || lc === 'zh-mo' || lc.includes('hant')) return 'zh-TW';
    if (lc.startsWith('zh')) return 'zh-CN';
    if (lc.startsWith('ja')) return 'ja';
    if (lc.startsWith('ko')) return 'ko';
    if (lc.startsWith('es')) return 'es';
    if (lc.startsWith('pt')) return 'pt-BR';
    if (lc.startsWith('de')) return 'de';
    if (lc.startsWith('fr')) return 'fr';
    if (lc.startsWith('ru')) return 'ru';
    if (lc.startsWith('vi')) return 'vi';
    if (lc.startsWith('en')) return 'en';
  }
  return 'en';
}
let currentLang = localStorage.getItem(LANG_KEY) || detectBrowserLang();
if (!I18N[currentLang]) currentLang = 'en';

function tr(key, ...args) {
  const dict = I18N[currentLang] || I18N['en'];
  let tpl = dict[key] !== undefined ? dict[key] : (I18N['en'][key] || key);
  if (typeof tpl !== 'string') return tpl;
  args.forEach((v, idx) => {
    tpl = tpl.split('{' + idx + '}').join(v == null ? '' : String(v));
  });
  return tpl;
}
function winName(w) {
  const map = { '5h': 'w_5h', 'today': 'w_today', '24h': 'w_24h', 'week': 'w_week', '7d': 'w_7d', 'all': 'w_all' };
  return tr(map[w] || 'w_7d');
}
function poolLabel(poolKey) {
  if (poolKey === 'gemini_pro') return tr('leg_gem_pro');
  if (poolKey === 'claude_gpt') return tr('leg_cld');
  if (poolKey === 'gemini_flash') return tr('leg_flash');
  return tr('leg_other');
}
function bucketDisplayLabel(b) {
  const grp = b.pool_key === 'claude_gpt' ? 'Claude/GPT' : (b.pool_key === 'gemini_flash' ? 'Gemini Flash' : 'Gemini');
  const win = b.window_kind === 'five_hour' ? '5h' : (b.window_kind === 'weekly' ? '7d' : '');
  return win ? `${grp} · ${win}` : grp;
}
function fmtDayLabel(dateStr, fallback) {
  if (!dateStr || dateStr.length < 10) return fallback || '';
  const parts = dateStr.split('-');
  if (parts.length !== 3) return fallback || dateStr;
  const dt = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  const wds = tr('weekdays');
  const wd = Array.isArray(wds) ? (wds[dt.getDay()] || '') : '';
  return `${parts[1]}-${parts[2]} ${wd}`.trim();
}
function fmtWs(ws) {
  return (!ws || ws === '(无工作区)') ? tr('no_ws') : ws;
}
function fmtTitle(t) {
  return (!t || t === '(未命名会话)' || t === '(未命名)') ? tr('unnamed') : t;
}

(function initLangSelect() {
  const sel = document.getElementById('lang-select');
  LANG_OPTIONS.forEach(([code, label]) => {
    const opt = document.createElement('option');
    opt.value = code;
    opt.textContent = '🌐 ' + label;
    if (code === currentLang) opt.selected = true;
    sel.appendChild(opt);
  });
})();

function applyStaticI18n() {
  document.documentElement.setAttribute('lang', currentLang);
  document.title = tr('doc_title');
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const k = el.getAttribute('data-i18n');
    if (k === 'syncing' && lastData) return;
    el.textContent = tr(k);
  });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => {
    el.setAttribute('placeholder', tr(el.getAttribute('data-i18n-ph')));
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    el.setAttribute('title', tr(el.getAttribute('data-i18n-title')));
  });
  const liveLbl = document.getElementById('live-btn-lbl');
  if (liveLbl) liveLbl.textContent = liveEnabled ? tr('live_on') : tr('live_off');
}

let currentWin = '7d';
let currentChartTab = '5h';
let currentDetailTab = 'convs';
let currentMetric = 'billable_tokens';
let liveEnabled = true;
let pollTimer = null;
let lastData = null;
let convSortKey = 'billable_tokens';
let convSortDir = -1;

const THEME_KEY = 'agy-usage-theme';
function prefTheme() {
  const v = localStorage.getItem(THEME_KEY);
  return (v === 'light' || v === 'dark' || v === 'system' || v === 'tongtou') ? v : 'system';
}
function resolvedTheme(pref) {
  if (pref === 'light' || pref === 'dark' || pref === 'tongtou') return pref;
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}
function applyTheme() {
  const pref = prefTheme();
  const resolved = resolvedTheme(pref);
  document.documentElement.setAttribute('data-theme', resolved);
  document.documentElement.setAttribute('data-theme-pref', pref);
  document.documentElement.style.colorScheme = (resolved === 'dark') ? 'dark' : 'light';
  document.querySelectorAll('#theme-pills [data-theme-pref]').forEach((btn) => {
    btn.classList.toggle('active', btn.getAttribute('data-theme-pref') === pref);
  });
}
applyTheme();
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function fmtTok(n) {
  n = Number(n || 0);
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k';
  return String(Math.round(n));
}
function fmtUsd(v) {
  v = Number(v || 0);
  return '$' + (v < 0.01 && v > 0 ? v.toFixed(4) : v.toFixed(2));
}
function fmtMetric(v, metric) {
  if (metric === 'est_cost_usd') return fmtUsd(v);
  if (metric === 'calls') return Math.round(v || 0) + '';
  return fmtTok(v);
}
function usedColor(used) {
  if (used == null) return '#64748b';
  if (used >= 80) return '#ef4444';
  if (used >= 55) return '#f59e0b';
  return '#10b981';
}
function fmtCountdown(sec) {
  sec = Math.max(0, Math.floor(sec));
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (d > 0) return tr('cd_dhm', d, h, m);
  if (h > 0) return tr('cd_hms', h, m, s);
  return tr('cd_ms', m, s);
}

// Safe delegated tooltip & click handling (100% textContent DOM nodes, zero innerHTML XSS surface)
const tipEl = document.getElementById('tip');
function renderSafeTip(title, bodyText) {
  tipEl.textContent = '';
  if (title) {
    const hd = document.createElement('div');
    hd.className = 'th';
    hd.textContent = title;
    tipEl.appendChild(hd);
  }
  const lines = String(bodyText || '').split('\n').filter(Boolean);
  lines.forEach(line => {
    const row = document.createElement('div');
    row.textContent = line;
    tipEl.appendChild(row);
  });
}
function positionTip(evt) {
  const pad = 12;
  let x = evt.clientX + pad, y = evt.clientY + pad;
  const r = tipEl.getBoundingClientRect();
  if (x + r.width > window.innerWidth - 8) x = evt.clientX - r.width - pad;
  if (y + r.height > window.innerHeight - 8) y = evt.clientY - r.height - pad;
  tipEl.style.left = Math.max(6, x) + 'px';
  tipEl.style.top = Math.max(6, y) + 'px';
}
document.addEventListener('mouseover', evt => {
  const t = evt.target.closest('[data-tip]');
  if (!t) return;
  renderSafeTip(t.getAttribute('data-tip-title') || '', t.getAttribute('data-tip') || '');
  tipEl.style.display = 'block';
  positionTip(evt);
});
document.addEventListener('mousemove', evt => {
  if (tipEl.style.display === 'block') positionTip(evt);
});
document.addEventListener('mouseout', evt => {
  const t = evt.target.closest('[data-tip]');
  if (t && !t.contains(evt.relatedTarget)) tipEl.style.display = 'none';
});
document.addEventListener('click', evt => {
  const copyEl = evt.target.closest('[data-copy]');
  if (copyEl) {
    const txt = copyEl.getAttribute('data-copy') || '';
    navigator.clipboard && navigator.clipboard.writeText(txt);
    const old = copyEl.textContent;
    copyEl.textContent = tr('copied');
    setTimeout(() => { copyEl.textContent = old; }, 1100);
    return;
  }
  const sessEl = evt.target.closest('[data-session]');
  if (sessEl) {
    openSession(sessEl.getAttribute('data-session'));
    return;
  }
  if (evt.target.closest('[data-open-share]')) {
    burstSparks(evt.clientX, evt.clientY);
    openShareModal();
    return;
  }
  if (evt.target.closest('[data-action="close"]') || evt.target.id === 'backdrop') {
    closeOverlays();
  }
});

// 1-second live countdown ticker
setInterval(() => {
  document.querySelectorAll('[data-reset-ts]').forEach(el => {
    const ts = Number(el.getAttribute('data-reset-ts'));
    if (!ts) return;
    const remSec = (ts - Date.now()) / 1000;
    el.textContent = remSec > 0 ? tr('rem_time', fmtCountdown(remSec)) : tr('expired_wait');
  });
}, 1000);

function flameIconSvg() {
  return `<svg class="fire-svg" viewBox="0 0 24 24" aria-hidden="true"><circle class="eb1" cx="9" cy="4" r="1.4" fill="#fde047"/><circle class="eb2" cx="15.5" cy="5" r="1.1" fill="#fb923c"/><path d="M12.4 2.2c.4 3.2-1.9 4.9-2.8 6.8-.9 1.9-.3 3.6 1.1 4.2-.3-1.5.5-2.8 1.9-3.6 1.2 1.8 1.7 3.7.9 5.5 1.8-.6 2.9-2.4 2.8-4.5 2.1 1.7 3.1 4.5 2.1 7.2-1.1 2.9-3.9 4.6-6.8 4.6-3.4 0-6.2-2.3-6.7-5.6-.5-3.4 1.5-6.6 4.4-8.9-.2 1.5.4 2.6 1.4 3.1-.5-3.1 1.7-6.3 1.7-8.8z" fill="#ff4d00"/><path d="M12.1 7.6c.7 1.9-.6 3.3-1.3 4.7-.7 1.4-.3 3.1 1.1 3.9-.2-1 .3-2 1.2-2.5.8 1.2.9 2.7.2 3.9 1.6-.5 2.5-2.2 1.9-4.1-.5-1.7-1.9-3.2-3.1-5.9z" fill="#ffb703"/><path d="M11.8 13.2c.5 1.2-.2 2.2-.5 3.1-.3.9.2 2 1.2 2.3.9.2 1.9-.5 2-1.5.2-1.2-.9-2.3-2.7-3.9z" fill="#fffbeb"/></svg>`;
}

function burstSparks(cx, cy) {
  if (!cx && !cy) return;
  const cols = ['#ff4d00', '#ffb703', '#fde047', '#ff2d55', '#a855f7', '#38bdf8'];
  for (let i = 0; i < 14; i++) {
    const d = document.createElement('div');
    d.className = 'spark-dot';
    d.style.background = cols[i % cols.length];
    d.style.left = (cx - 3) + 'px';
    d.style.top = (cy - 3) + 'px';
    d.style.boxShadow = '0 0 8px ' + cols[i % cols.length];
    document.body.appendChild(d);
    const ang = (Math.PI * 2 * i) / 14 + (Math.random() - 0.5) * 0.35;
    const dist = 26 + Math.random() * 36;
    requestAnimationFrame(() => {
      d.style.transform = `translate(${Math.cos(ang) * dist}px, ${Math.sin(ang) * dist - 8}px) scale(0.2)`;
      d.style.opacity = '0';
    });
    setTimeout(() => d.remove(), 660);
  }
}

function renderBanner(data) {
  const ls = data.live_session || {};
  const q = data.quota || {};
  const sel = data.selected_summary || {};
  const ctx = ls.context_window;
  let ctxHtml = `<span class="v" style="color:var(--muted)">${esc(tr('st_pending'))}</span>`;
  if (ctx && ctx.used_percentage != null) {
    const u = Number(ctx.used_percentage);
    const col = u >= 80 ? 'var(--red)' : (u >= 55 ? 'var(--yellow)' : 'var(--cyan)');
    ctxHtml = `<span class="v" style="color:${col}">${u.toFixed(1)}%</span> <span style="color:var(--muted)">(${fmtTok((ctx.total_input_tokens||0)+(ctx.total_output_tokens||0))}/${fmtTok(ctx.context_window_size||0)})</span>`;
  }
  const slBadge = ls.connected
    ? `<span class="dot ok"></span>${esc(tr('st_connected'))} <span style="color:var(--muted);font-weight:400">(${esc(ls.captured_at_cst)})</span>`
    : (ls.statusline_configured
        ? `<span class="dot warn"></span>${esc(tr('st_wait_push'))}`
        : `<span class="dot err"></span>${esc(tr('st_not_linked'))}`);
  const slCmd = '/statusline ' + (ls.statusline_path || 'statusline.py');
  const slDisp = '/statusline ' + (ls.statusline_display_path || ls.statusline_path || 'statusline.py');
  const cleanBtnTxt = String(tr('sc_btn')).replace(/^📸\s*/, '');
  const heroHook = (sel.total_tokens || 0) > 0
    ? `<span class="fire-stat-hl">${esc(fmtTok(sel.total_tokens))}${sel.cache_saved_usd >= 1 ? ' · ' + esc(fmtUsd(sel.cache_saved_usd)) : ''}</span> ▸ ${esc(cleanBtnTxt)}`
    : esc(cleanBtnTxt);

  document.getElementById('live-banner').innerHTML = `
    <div class="strip-left">
      <div class="kv"><span class="k">${esc(tr('st_channel'))}</span><span class="v">${slBadge}</span></div>
      <div class="kv"><span class="k">${esc(tr('st_model'))}</span><span class="v" style="color:var(--cyan)">${esc(ls.active_model)}</span></div>
      <div class="kv"><span class="k">Planner</span><span class="v" style="color:var(--purple)">${esc(ls.configured_planner)}</span></div>
      <div class="kv"><span class="k">${esc(tr('st_ctx'))}</span>${ctxHtml}</div>
      ${ls.plan_tier && ls.plan_tier !== '-' ? `<div class="kv"><span class="badge">${esc(ls.plan_tier)}</span></div>` : ''}
      ${q.has_live_quota ? `<div class="kv"><span class="k">${esc(tr('st_samples'))}</span><span class="v">${esc(tr('st_samples_val', q.snapshot_count))}</span></div>` : ''}
    </div>
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
      ${!q.has_live_quota ? `<span class="code-chip" title="${esc(tr('click_copy'))}" data-copy="${esc(slCmd)}">${esc(slDisp)}</span>` : ''}
      <button class="fire-cta" type="button" data-open-share="1"><span class="fire-cta-in">${flameIconSvg()}<span>${heroHook}</span></span></button>
    </div>
  `;
}

function renderInsights(data) {
  const q = data.quota || {};
  const sel = data.selected_summary || {};
  const byPool = data.by_pool || [];
  const b5 = data.burn_5h || {};
  const chips = [];

  (q.buckets || []).forEach(b => {
    const bName = bucketDisplayLabel(b);
    const remTxt = b.reset_in_seconds != null ? fmtCountdown(b.reset_in_seconds) : (b.reset_in_text || '-');
    if (b.status === 'critical' && b.used_pct != null) {
      chips.push({
        level: 'crit',
        title: tr('ins_crit_t', bName, b.used_pct.toFixed(1)),
        detail: tr('ins_crit_d', (b.remaining_pct || 0).toFixed(1), remTxt),
      });
    } else if (b.status === 'warning' && b.used_pct != null) {
      const pBit = b.pacing_ratio ? tr('ins_pace_bit', b.pacing_ratio) : '';
      chips.push({
        level: 'warn',
        title: tr('ins_warn_t', bName, b.used_pct.toFixed(1), pBit),
        detail: tr('ins_warn_d', (b.remaining_pct || 0).toFixed(1), (b.projected_rem_at_reset || 0).toFixed(1)),
      });
    }
  });

  if ((sel.cache_read_tokens || 0) > 0) {
    const hit = sel.cache_hit_pct || 0;
    const lvl = hit >= 85 ? 'ok' : (hit < 65 ? 'warn' : 'info');
    chips.push({
      level: lvl,
      title: tr('ins_cache_t', hit, fmtUsd(sel.cache_saved_usd)),
      detail: tr('ins_cache_d', fmtTok(sel.cache_read_tokens), sel.cache_saved_pct || 0),
    });
  }

  const cldPool = byPool.find(p => p.pool === 'claude_gpt');
  if (cldPool && cldPool.share_billable_pct >= 30) {
    chips.push({
      level: 'info',
      title: tr('ins_3p_t', cldPool.share_billable_pct),
      detail: tr('ins_3p_d', cldPool.calls, fmtUsd(cldPool.est_cost_usd)),
    });
  }

  if ((b5.calls_per_hour || 0) >= 40) {
    chips.push({
      level: 'info',
      title: tr('ins_burst_t', b5.calls_per_hour),
      detail: tr('ins_burst_d', fmtTok(b5.billable_tokens_per_hour)),
    });
  }

  document.getElementById('insights-strip').innerHTML = chips.slice(0, 4).map(i => `
    <div class="ichip ${esc(i.level)}"><b>${esc(i.title)}</b><span>${esc(i.detail)}</span></div>
  `).join('');
}

function renderQuota(data) {
  const q = data.quota || {};
  const ls = data.live_session || {};
  const el = document.getElementById('quota-section');

  if (!q.has_live_quota) {
    const slCmd = '/statusline ' + (ls.statusline_path || 'statusline.py');
    const slDisp = '/statusline ' + (ls.statusline_display_path || ls.statusline_path || 'statusline.py');
    el.innerHTML = `
      <div class="card onboarding" style="margin-bottom:12px;">
        <div class="card-head" style="margin-bottom:6px;">
          <span class="card-title">${esc(tr('onb_title'))}</span>
          <span class="badge warn">${esc(ls.statusline_configured ? tr('onb_wait') : tr('onb_step'))}</span>
        </div>
        <div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px;">
          <span style="color:var(--muted);font-size:11.5px;">${esc(tr('onb_desc'))}</span>
          <div style="display:flex;gap:6px;align-items:center;">
            <span class="code-chip" data-copy="${esc(slCmd)}">${esc(slDisp)}</span>
            <button class="btn primary" data-copy="${esc(slCmd)}">${esc(tr('copy_cmd'))}</button>
          </div>
        </div>
      </div>
    `;
    return;
  }

  function renderBucketRow(b) {
    const rem = b.remaining_pct != null ? b.remaining_pct : 0;
    const used = b.used_pct != null ? b.used_pct : 0;
    const col = b.reset_passed ? '#38bdf8' : usedColor(used);
    const r = 23, circ = 2 * Math.PI * r;
    const dash = Math.max(used > 0 ? 2 : 0, circ * (used / 100));
    const usedDisp = (used > 0 && used < 10) ? used.toFixed(2) : used.toFixed(1);
    const remDisp = (used > 0 && used < 10) ? rem.toFixed(2) : rem.toFixed(1);

    let badge = `<span class="badge ok">${esc(tr('b_ok'))}</span>`;
    if (b.status === 'reset_ready') badge = `<span class="badge">${esc(tr('b_ready'))}</span>`;
    else if (b.status === 'critical') badge = `<span class="badge crit">${esc(tr('b_crit'))}</span>`;
    else if (b.status === 'warning') badge = `<span class="badge warn">${esc(tr('b_warn'))}</span>`;

    const resetEpoch = (!b.reset_passed && b.reset_time) ? new Date(b.reset_time).getTime() : 0;
    const winTitle = b.window_kind === 'five_hour' ? tr('win_5h') : (b.window_kind === 'weekly' ? tr('win_7d') : tr('win_other'));
    const remCountdown = b.reset_in_seconds != null ? fmtCountdown(b.reset_in_seconds) : (b.reset_in_text || '-');

    const budgetBit = b.reset_passed
      ? esc(tr('next_call_refresh'))
      : (b.window_kind === 'weekly' && b.daily_safe_budget_pct != null
          ? tr('daily_avail', b.daily_safe_budget_pct)
          : (b.hourly_safe_budget_pct != null ? tr('hourly_avail', b.hourly_safe_budget_pct) : ''));
    const exhTxt = b.projected_exhaust_hours != null ? fmtCountdown(b.projected_exhaust_hours * 3600) : '-';
    const forecastBit = (!b.reset_passed && b.projected_rem_at_reset != null)
      ? (b.projected_rem_at_reset <= 0.1
          ? `<span style="color:var(--red)">${esc(tr('est_exhaust', exhTxt))}</span>`
          : tr('est_rem_reset', b.projected_rem_at_reset.toFixed(1)))
      : '';
    const ratioBit = (!b.reset_passed && b.pacing_ratio != null) ? tr('pace_val', b.pacing_ratio) : '';
    const tokBit = b.tokens_per_1pct ? `1%≈<strong>${fmtTok(b.tokens_per_1pct)}</strong>` : '';
    const bDisp = bucketDisplayLabel(b);

    return `
      <div class="bucket-item">
        <div class="mini-ring">
          <svg width="58" height="58" viewBox="0 0 58 58">
            <circle cx="29" cy="29" r="${r}" fill="none" stroke="var(--track)" stroke-width="5.5" />
            <circle cx="29" cy="29" r="${r}" fill="none" stroke="${col}" stroke-width="5.5"
              stroke-linecap="round" stroke-dasharray="${dash.toFixed(1)} ${circ.toFixed(1)}"
              transform="rotate(-90 29 29)" />
          </svg>
          <div class="mini-ring-txt">
            <span class="mini-ring-pct" style="color:${col}">${usedDisp}%</span>
            <span class="mini-ring-lbl">${esc(tr('used_lbl'))}</span>
          </div>
        </div>
        <div style="min-width:0">
          <div class="b-top">
            <div><span class="b-name">${esc(winTitle)}</span> <span style="color:var(--muted)">${esc(tr('rem_val', remDisp))}</span> ${badge}</div>
            <span style="color:var(--cyan);font-weight:600;font-size:11px" ${resetEpoch ? `data-reset-ts="${resetEpoch}"` : ''}>${b.reset_passed ? esc(tr('expired_wait')) : (b.reset_in_seconds != null ? esc(tr('rem_time', remCountdown)) : '')}</span>
          </div>
          <div class="dual-bar" data-tip-title="${esc(bDisp)}" data-tip="${esc(tr('dual_tip', usedDisp, (b.time_elapsed_pct||0).toFixed(1), b.reset_time_cst, data.timezone_label || 'UTC+8'))}">
            <div class="dual-fill" style="width:${used}%;background:${col}"></div>
            ${b.time_elapsed_pct != null ? `<div class="time-marker" style="left:${Math.min(99, b.time_elapsed_pct)}%"></div>` : ''}
          </div>
          <div class="b-meta">
            <span>${esc(tr('reset_at', b.reset_time_cst))}</span>
            <span>${[ratioBit, budgetBit, forecastBit, tokBit].filter(Boolean).join(' · ')}</span>
          </div>
        </div>
      </div>
    `;
  }

  const pools = [
    { key: 'gemini', cls: 'pool-gemini', dot: '#38bdf8', title: tr('pool_gem_t'), sub: tr('pool_gem_s'), items: q.buckets.filter(b => (b.pool_key || '').startsWith('gemini')) },
    { key: 'claude', cls: 'pool-claude', dot: '#a78bfa', title: tr('pool_cld_t'), sub: tr('pool_cld_s'), items: q.buckets.filter(b => b.pool_key === 'claude_gpt') },
    { key: 'other', cls: '', dot: '#64748b', title: tr('pool_oth_t'), sub: '', items: q.buckets.filter(b => !(b.pool_key || '').startsWith('gemini') && b.pool_key !== 'claude_gpt') },
  ].filter(g => g.items.length > 0);

  el.innerHTML = `<div class="grid ${pools.length >= 2 ? 'grid-2' : ''}">` + pools.map(g => `
    <div class="card ${g.cls}">
      <div class="card-head">
        <span class="card-title"><span class="swatch" style="background:${g.dot}"></span>${esc(g.title)}</span>
        <span class="card-sub">${esc(g.sub)}</span>
      </div>
      <div class="bucket-stack">${g.items.map(renderBucketRow).join('')}</div>
    </div>
  `).join('') + `</div>`;
}

function renderKPIs(data) {
  const w = data.windows || {};
  const w5 = w['5h'] || {}, wt = w['today'] || {}, w7 = w['7d'] || {};
  const wsel = data.selected_summary || w7;
  const b5 = data.burn_5h || {};
  const wow = data.week_over_week || {};
  let wowBadge = `<span class="badge muted" style="cursor:help" data-tip-title="${esc(tr('wow_title'))}" data-tip="${esc(tr('wow_na_tip'))}">${esc(tr('wow_na'))}</span>`;
  if (wow.comparable && wow.delta_pct != null) {
    const cls = wow.delta_pct <= 0 ? 'ok' : (wow.delta_pct >= 35 ? 'warn' : 'purple');
    const sign = wow.delta_pct > 0 ? '+' : '';
    const prevTok = fmtTok((wow.previous || {}).billable_tokens || 0);
    const curTok = fmtTok((wow.current || {}).billable_tokens || 0);
    const tipTxt = tr('wow_tip', wow.elapsed_hours || 0, curTok, prevTok);
    const bTxt = tr('wow_badge', sign + wow.delta_pct.toFixed(1));
    wowBadge = `<span class="badge ${cls}" style="cursor:help" data-tip-title="${esc(tr('wow_title'))}" data-tip="${esc(tipTxt)}">${esc(bTxt)}</span>`;
  } else if ((wow.elapsed_hours || 0) > 0 && (wow.elapsed_hours || 0) < 2.0) {
    wowBadge = `<span class="badge muted" style="cursor:help" data-tip-title="${esc(tr('wow_title'))}" data-tip="${esc(tr('wow_wait_tip'))}">${esc(tr('wow_wait'))}</span>`;
  }
  document.getElementById('kpi-cards').innerHTML = `
    <div class="card kpi-card">
      <div style="display:flex;justify-content:space-between;align-items:center;"><span class="card-sub">${esc(tr('kpi_5h_t'))}</span><span class="badge">${esc(tr('kpi_burn', fmtTok(b5.billable_tokens_per_hour||0)))}</span></div>
      <div class="kpi-val" style="color:var(--cyan)">${fmtTok(w5.billable_tokens)}</div>
      <div class="kpi-sub">${esc(tr('kpi_io', fmtTok(w5.input_tokens), fmtTok(w5.output_tokens)))}</div>
      <div class="kpi-foot"><span>${esc(tr('kpi_calls_rate', w5.calls || 0, b5.calls_per_hour || 0))}</span><span>${esc(tr('kpi_est', fmtUsd(w5.est_cost_usd)))}</span></div>
    </div>
    <div class="card kpi-card">
      <div style="display:flex;justify-content:space-between;align-items:center;"><span class="card-sub">${esc(tr('kpi_today_t'))}</span><span class="badge ok">${esc(tr('w_today'))}</span></div>
      <div class="kpi-val">${fmtTok(wt.billable_tokens)}</div>
      <div class="kpi-sub">${esc(tr('kpi_io', fmtTok(wt.input_tokens), fmtTok(wt.output_tokens)))}</div>
      <div class="kpi-foot"><span>${esc(tr('kpi_calls_tools', wt.calls || 0, wt.tool_calls || 0))}</span><span>${esc(tr('kpi_est', fmtUsd(wt.est_cost_usd)))}</span></div>
    </div>
    <div class="card kpi-card">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:4px;"><span class="card-sub">${esc(tr('kpi_7d_t'))}</span>${wowBadge}</div>
      <div class="kpi-val" style="color:var(--purple)">${fmtTok(w7.billable_tokens)}</div>
      <div class="kpi-sub">${esc(tr('kpi_total_thru', fmtTok(w7.total_tokens)))}</div>
      <div class="kpi-foot"><span>${esc(tr('kpi_calls_convs', w7.calls || 0, w7.conversations || 0))}</span><span>${esc(tr('kpi_est', fmtUsd(w7.est_cost_usd)))}</span></div>
    </div>
    <div class="card kpi-card">
      <div style="display:flex;justify-content:space-between;align-items:center;"><span class="card-sub">${esc(tr('kpi_cache_t', winName(currentWin)))}</span><span class="badge ok">${esc(tr('kpi_hit', wsel.cache_hit_pct||0))}</span></div>
      <div class="kpi-val" style="color:var(--green)">${fmtUsd(wsel.cache_saved_usd)}</div>
      <div class="kpi-sub">${esc(tr('kpi_hit_sub', fmtTok(wsel.cache_read_tokens), wsel.cache_saved_pct||0))}</div>
      <div class="kpi-foot"><span>${esc(tr('kpi_actual_est', fmtUsd(wsel.est_cost_usd)))}</span><span>${esc(tr('kpi_uncached', fmtUsd((wsel.est_cost_usd||0)+(wsel.cache_saved_usd||0))))}</span></div>
    </div>
  `;
}

function renderMainChart(data) {
  const box = document.getElementById('main-chart-box');
  const legEl = document.getElementById('main-chart-legend');
  const metricWrap = document.getElementById('metric-pills');

  if (currentChartTab === 'quota') {
    metricWrap.style.visibility = 'hidden';
    const q = data.quota || {};
    const withHist = (q.buckets || []).filter(b => (b.history || []).length >= 2);
    if (!withHist.length) {
      box.innerHTML = `<div style="height:210px;display:grid;place-items:center;color:var(--muted);">${esc(tr('quota_empty'))}</div>`;
      legEl.innerHTML = '';
      return;
    }
    const colors = ['#38bdf8', '#a78bfa', '#10b981', '#f59e0b'];
    const W = 680, H = 210, padL = 42, padR = 14, padT = 12, padB = 24;
    const allPts = withHist.flatMap(b => b.history.map(p => new Date(p.ts).getTime()));
    const minT = Math.min(...allPts), maxT = Math.max(...allPts);
    const spanT = Math.max(1, maxT - minT);

    let grid = '';
    for (const pct of [0, 25, 50, 75, 100]) {
      const y = padT + (1 - pct / 100) * (H - padT - padB);
      grid += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--grid-line)" stroke-dasharray="3 3" />`;
      grid += `<text x="${padL - 6}" y="${y + 3.5}" text-anchor="end" fill="var(--muted)" font-size="9.5">${pct}%</text>`;
    }

    let paths = '', leg = '';
    withHist.forEach((b, idx) => {
      const c = colors[idx % colors.length];
      const bDisp = bucketDisplayLabel(b);
      const raw = b.history;
      const slim = raw.filter((pt, i) => i === 0 || i === raw.length - 1 || pt.used_pct !== raw[i - 1].used_pct);
      const coords = slim.map(p => ({
        x: padL + ((new Date(p.ts).getTime() - minT) / spanT) * (W - padL - padR),
        y: padT + (1 - (p.used_pct || 0) / 100) * (H - padT - padB),
        p,
      }));
      paths += `<polyline fill="none" stroke="${c}" stroke-width="2" points="${coords.map(o => `${o.x.toFixed(1)},${o.y.toFixed(1)}`).join(' ')}" />`;
      coords.forEach(o => {
        const tipTitle = `${bDisp} · ${o.p.ts_cst}`;
        const tipTxt = tr('q_tip', o.p.used_pct, o.p.remaining_pct);
        paths += `<circle cx="${o.x.toFixed(1)}" cy="${o.y.toFixed(1)}" r="3" fill="${c}" style="cursor:pointer" data-tip-title="${esc(tipTitle)}" data-tip="${esc(tipTxt)}" />`;
      });
      leg += `<span class="legend-item"><span class="swatch" style="background:${c}"></span>${esc(bDisp)}</span>`;
    });
    box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:210px;display:block">${grid}${paths}</svg>`;
    legEl.innerHTML = leg;
    return;
  }

  metricWrap.style.visibility = 'visible';
  const items = currentChartTab === '5h' ? (data.rolling_5h_10m || [])
              : currentChartTab === '24h' ? (data.hourly_24h || [])
              : (data.daily_7d || []);
  const W = 680, H = 210, padL = 46, padR = 10, padT = 12, padB = 26;
  const vals = items.map(d => Number(d[currentMetric] || 0));
  const maxVal = Math.max(0.0001, ...vals);
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const step = plotW / Math.max(1, items.length);
  const barW = Math.max(5, step * (currentChartTab === '7d' ? 0.45 : 0.64));

  let svg = '';
  for (let i = 0; i <= 3; i++) {
    const v = (maxVal * i) / 3;
    const y = padT + plotH - (plotH * i) / 3;
    svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--grid-line)" stroke-dasharray="3 3" />`;
    svg += `<text x="${padL - 6}" y="${y + 3.5}" text-anchor="end" fill="var(--muted)" font-size="9.5">${esc(fmtMetric(v, currentMetric))}</text>`;
  }

  const stackSeries = [
    { key: 'gemini_pro', color: '#38bdf8' },
    { key: 'claude_gpt', color: '#a78bfa' },
    { key: 'gemini_flash', color: '#10b981' },
    { key: 'other', color: '#64748b' },
  ];

  items.forEach((d, idx) => {
    const x = padL + idx * step + (step - barW) / 2;
    const totalV = Number(d[currentMetric] || 0);
    const dispLbl = currentChartTab === '7d' ? fmtDayLabel(d.date, d.label) : d.label;
    const tipTxt = tr(
      'bar_tip',
      fmtTok(d.billable_tokens),
      fmtTok(d.input_tokens),
      fmtTok(d.output_tokens),
      fmtTok(d.cache_read_tokens),
      tr('n_calls', d.calls),
      fmtUsd(d.est_cost_usd)
    );

    svg += `<g style="cursor:pointer" data-tip-title="${esc(dispLbl)}" data-tip="${esc(tipTxt)}">`;
    svg += `<rect x="${(padL + idx * step).toFixed(1)}" y="${padT}" width="${step.toFixed(1)}" height="${plotH}" fill="transparent" />`;

    if (currentMetric === 'billable_tokens') {
      let curY = padT + plotH;
      for (const s of stackSeries) {
        const val = Number(d[s.key] || 0);
        if (val <= 0) continue;
        const h = Math.max(1.5, (val / maxVal) * plotH);
        curY -= h;
        svg += `<rect x="${x.toFixed(1)}" y="${curY.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="${s.color}" />`;
      }
    } else if (totalV > 0) {
      const h = Math.max(2, (totalV / maxVal) * plotH);
      const col = currentMetric === 'est_cost_usd' ? '#f59e0b' : (currentMetric === 'calls' ? '#3b82f6' : '#38bdf8');
      svg += `<rect x="${x.toFixed(1)}" y="${(padT + plotH - h).toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" rx="2.5" fill="${col}" />`;
    }
    svg += `</g>`;

    const showLbl = currentChartTab === '7d' ? true : (idx % 4 === 0 || idx === items.length - 1);
    if (showLbl) {
      const lx = padL + idx * step + step / 2;
      svg += `<text x="${lx.toFixed(1)}" y="${H - 7}" text-anchor="middle" fill="var(--muted)" font-size="9.5">${esc(dispLbl)}</text>`;
    }
  });

  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:210px;display:block">${svg}</svg>`;
  legEl.innerHTML = currentMetric === 'billable_tokens'
    ? `<span class="legend-item"><span class="swatch" style="background:#38bdf8"></span>${esc(tr('leg_gem_pro'))}</span>
       <span class="legend-item"><span class="swatch" style="background:#a78bfa"></span>${esc(tr('leg_cld'))}</span>
       <span class="legend-item"><span class="swatch" style="background:#10b981"></span>${esc(tr('leg_flash'))}</span>`
    : `<span class="legend-item">${esc(tr('leg_cur', document.querySelector('#metric-pills .pill.active')?.textContent || ''))}</span>`;
}

function renderHeatmapAndPools(data) {
  const rows = data.heatmap_7x24 || [];
  let maxVal = 1;
  rows.forEach(r => r.hours.forEach(h => { if (h.billable_tokens > maxVal) maxVal = h.billable_tokens; }));

  let html = '<table class="heatmap-table"><thead><tr><th></th>';
  for (let h = 0; h < 24; h++) html += `<th>${h % 2 === 0 ? String(h).padStart(2, '0') : ''}</th>`;
  html += '</tr></thead><tbody>';

  rows.forEach(r => {
    const dLbl = fmtDayLabel(r.date, r.label);
    html += `<tr><td class="day-lbl">${esc(dLbl)}</td>`;
    r.hours.forEach(c => {
      const ratio = c.billable_tokens / maxVal;
      let bg = 'var(--heat-0)';
      if (c.billable_tokens > 0) {
        if (ratio >= 0.72) bg = 'var(--heat-4)';
        else if (ratio >= 0.42) bg = 'var(--heat-3)';
        else if (ratio >= 0.16) bg = 'var(--heat-2)';
        else bg = 'var(--heat-1)';
      }
      const tipTitle = `${dLbl} ${String(c.hour).padStart(2,'0')}:00`;
      const tipTxt = tr('hm_tip', fmtTok(c.billable_tokens), tr('n_calls', c.calls), fmtUsd(c.est_cost_usd));
      html += `<td><div class="hcell" style="background:${bg}" data-tip-title="${esc(tipTitle)}" data-tip="${esc(tipTxt)}"></div></td>`;
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById('heatmap-box').innerHTML = html;

  document.getElementById('win-badge-pool').textContent = winName(currentWin);
  const pools = data.by_pool || [];
  const totalTok = pools.reduce((s, p) => s + (p.billable_tokens || 0), 0);
  document.getElementById('pool-total-lbl').textContent = tr('pool_total', fmtTok(totalTok));

  const barSegs = pools.map(p => {
    const pName = poolLabel(p.pool);
    return `<div style="width:${p.share_billable_pct}%;background:${POOL_COLORS[p.pool]||'#38bdf8'};height:100%" data-tip-title="${esc(pName)}" data-tip="${esc(tr('pool_tip', fmtTok(p.billable_tokens), p.share_billable_pct, tr('n_calls', p.calls), fmtUsd(p.est_cost_usd)))}"></div>`;
  }).join('');
  const listRows = pools.map(p => `
    <span class="legend-item" style="margin-right:10px;">
      <span class="swatch" style="background:${POOL_COLORS[p.pool]||'#38bdf8'}"></span>
      <span style="color:var(--text)">${esc(poolLabel(p.pool))}</span>
      <strong>${p.share_billable_pct}%</strong>
      <span style="color:var(--muted)">(${fmtTok(p.billable_tokens)})</span>
    </span>
  `).join('');
  document.getElementById('pool-compact-bars').innerHTML = `
    <div style="display:flex;height:7px;border-radius:99px;overflow:hidden;background:var(--track);margin-bottom:7px;">${barSegs}</div>
    <div style="display:flex;flex-wrap:wrap;gap:4px 8px;font-size:11px;">${listRows || `<span style="color:var(--muted)">${esc(tr('no_calls_win'))}</span>`}</div>
  `;
}

function renderDetailPanes(data) {
  renderConvTable();

  document.getElementById('model-tbody').innerHTML = (data.by_model || []).map(m => `
    <tr>
      <td class="mono" style="color:var(--text-strong)">${esc(m.model)}</td>
      <td style="color:var(--muted)">${esc(poolLabel(m.pool))}</td>
      <td class="num">${m.calls}</td>
      <td class="num">${fmtTok(m.input_tokens)}</td>
      <td class="num" style="color:var(--muted)">${fmtTok(m.cache_read_tokens)}</td>
      <td class="num">${fmtTok(m.output_tokens)}</td>
      <td class="num" style="color:var(--green)">${m.cache_hit_pct}%</td>
      <td class="num">${fmtUsd(m.est_cost_usd)}</td>
    </tr>
  `).join('') || `<tr><td colspan="8" style="color:var(--muted);text-align:center">${esc(tr('no_data'))}</td></tr>`;

  document.getElementById('project-list').innerHTML = (data.projects || []).slice(0, 8).map(p => `
    <div style="margin-bottom:8px;">
      <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">
        <span class="mono">${esc(fmtWs(p.workspace))}</span>
        <span><strong style="font-weight:600">${fmtTok(p.billable_tokens)}</strong> <span style="color:var(--muted)">(${p.share_billable_pct}% · ${esc(tr('n_calls', p.calls))})</span></span>
      </div>
      <div class="bar-track"><div class="bar-fill" style="width:${p.share_billable_pct}%;background:#3b82f6"></div></div>
    </div>
  `).join('') || `<div style="color:var(--muted)">${esc(tr('no_data'))}</div>`;

  const tools = data.top_tools || [];
  const maxTool = Math.max(1, ...tools.map(t => t.count));
  document.getElementById('tools-list').innerHTML = tools.slice(0, 8).map(t => `
    <div style="display:grid;grid-template-columns:120px 1fr 68px;gap:8px;align-items:center;margin-bottom:6px;font-size:11px;">
      <span class="mono ellipsis">${esc(t.name)}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${(t.count/maxTool*100).toFixed(1)}%;background:#a78bfa"></div></div>
      <span class="num" style="color:var(--muted)">${t.count} (${t.share_pct}%)</span>
    </div>
  `).join('') || `<div style="color:var(--muted)">${esc(tr('no_tools'))}</div>`;

  document.getElementById('recent-tbody').innerHTML = (data.recent_calls || []).slice(0, 18).map(r => {
    const tns = r.tool_names || [];
    const toolHtml = tns.length ? `<span class="tool-pill">${esc(tns[0])}${tns.length > 1 ? ' +' + (tns.length - 1) : ''}</span>` : '';
    return `
      <tr class="clickable" data-session="${esc(r.conversation_id)}">
        <td class="mono" style="color:var(--muted);white-space:nowrap">${esc(r.ts_cst.slice(6))}</td>
        <td>
          <div class="mono" style="color:${POOL_COLORS[r.pool]||'var(--cyan)'}">${esc(r.model)}${toolHtml}</div>
          <div class="ellipsis" style="font-size:10.5px;color:var(--muted)">${esc(fmtTitle(r.title))}</div>
        </td>
        <td class="num">${fmtTok(r.input_tokens)}</td>
        <td class="num" style="color:var(--muted)">${fmtTok(r.cache_read_tokens)}</td>
        <td class="num">${fmtTok(r.output_tokens)}</td>
      </tr>
    `;
  }).join('') || `<tr><td colspan="5" style="color:var(--muted);text-align:center">${esc(tr('no_calls'))}</td></tr>`;
}

function renderConvTable() {
  if (!lastData) return;
  const q = (document.getElementById('conv-search').value || '').trim().toLowerCase();
  let rows = [...(lastData.conversations || [])];
  if (q) {
    rows = rows.filter(c =>
      (c.title || '').toLowerCase().includes(q) ||
      (c.workspace || '').toLowerCase().includes(q) ||
      (c.models || []).join(' ').toLowerCase().includes(q) ||
      (c.short_id || '').toLowerCase().includes(q)
    );
  }
  rows.sort((a, b) => ((Number(a[convSortKey] || 0) - Number(b[convSortKey] || 0)) * convSortDir));

  document.getElementById('conv-tbody').innerHTML = rows.map(c => `
    <tr class="clickable" data-session="${esc(c.id)}">
      <td>
        <div class="ellipsis" style="font-weight:600;color:var(--text-strong);max-width:250px">${esc(fmtTitle(c.title))}${c.is_subagent ? `<span class="tag">${esc(tr('subagent_tag'))}</span>` : ''}</div>
        <div class="mono" style="color:var(--muted);font-size:10px">${esc(c.short_id)} · ${esc(c.last_ts_cst)}</div>
      </td>
      <td class="mono ellipsis" style="color:var(--muted);max-width:120px">${esc(fmtWs(c.workspace))}</td>
      <td class="num">${c.calls}</td>
      <td class="num" style="font-weight:600;color:var(--text-strong)">${fmtTok(c.billable_tokens)}</td>
      <td class="num" style="color:var(--muted)">${fmtTok(c.peak_context)}</td>
      <td class="num" style="color:var(--green)">${c.cache_hit_pct}%</td>
      <td class="num">${fmtUsd(c.est_cost_usd)}</td>
    </tr>
  `).join('') || `<tr><td colspan="7" style="color:var(--muted);text-align:center">${esc(tr('no_match'))}</td></tr>`;
}

async function openSession(cid) {
  if (!cid) return;
  document.getElementById('backdrop').classList.add('open');
  document.getElementById('session-drawer').classList.add('open');
  document.getElementById('dr-title').textContent = tr('dr_loading');
  document.getElementById('dr-sub').textContent = cid;
  document.getElementById('dr-body').innerHTML = `<div style="color:var(--muted)">${esc(tr('dr_reading'))}</div>`;

  try {
    const res = await fetch('/api/session/' + encodeURIComponent(cid), { cache: 'no-store' });
    const d = await res.json();
    const s = d.summary || {};
    document.getElementById('dr-title').textContent = fmtTitle(d.title) + (d.is_subagent ? ` [${tr('subagent_tag')}]` : '');
    document.getElementById('dr-sub').textContent = tr('dr_sub', d.short_id, fmtWs(d.workspace), s.calls);

    const turns = d.turns || [];
    const W = 580, H = 135, padL = 44, padR = 10, padT = 10, padB = 20;
    const maxCtx = Math.max(1, ...turns.map(t => t.context_size));
    const pts = turns.map((t, i) => {
      const x = padL + (i / Math.max(1, turns.length - 1)) * (W - padL - padR);
      const y = padT + (1 - t.context_size / maxCtx) * (H - padT - padB);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const areaPts = `${padL},${H - padB} ${pts.join(' ')} ${W - padR},${H - padB}`;

    document.getElementById('dr-body').innerHTML = `
      <div class="grid grid-4" style="margin-bottom:12px;">
        <div class="card kpi-card"><div class="card-sub">${esc(tr('dr_bill'))}</div><div style="font-size:14px;font-weight:650;color:var(--cyan);margin-top:2px">${fmtTok(s.billable_tokens)}</div></div>
        <div class="card kpi-card"><div class="card-sub">${esc(tr('dr_peak'))}</div><div style="font-size:14px;font-weight:650;color:var(--purple);margin-top:2px">${fmtTok(d.peak_context)}</div></div>
        <div class="card kpi-card"><div class="card-sub">${esc(tr('dr_hit'))}</div><div style="font-size:14px;font-weight:650;color:var(--green);margin-top:2px">${s.cache_hit_pct}%</div></div>
        <div class="card kpi-card"><div class="card-sub">${esc(tr('dr_cost_save'))}</div><div style="font-size:13px;font-weight:650;margin-top:2px">${fmtUsd(s.est_cost_usd)} / <span style="color:var(--green)">${fmtUsd(s.cache_saved_usd)}</span></div></div>
      </div>

      <div style="font-size:11.5px;font-weight:600;margin-bottom:5px;color:var(--text-strong)">${esc(tr('dr_curve'))}</div>
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:135px;background:var(--chip-bg);border-radius:8px;border:1px solid var(--border);margin-bottom:12px;">
        <polygon points="${areaPts}" fill="rgba(56,189,248,0.14)" />
        <polyline points="${pts.join(' ')}" fill="none" stroke="#38bdf8" stroke-width="2" />
        <text x="6" y="16" fill="var(--muted)" font-size="9.5">${fmtTok(maxCtx)}</text>
        <text x="6" y="${H - 6}" fill="var(--muted)" font-size="9.5">0</text>
        <text x="${W - 8}" y="${H - 6}" text-anchor="end" fill="var(--muted)" font-size="9.5">${esc(tr('dr_turns_cnt', turns.length))}</text>
      </svg>

      ${(d.tools || []).length ? `<div style="margin-bottom:12px;">
        <div style="font-size:11.5px;font-weight:600;margin-bottom:5px;color:var(--text-strong)">${esc(tr('dr_tools'))}</div>
        <div>${d.tools.map(t => `<span class="tool-pill">${esc(t.name)} ×${t.count}</span>`).join(' ')}</div>
      </div>` : ''}

      <div style="font-size:11.5px;font-weight:600;margin-bottom:5px;color:var(--text-strong)">${esc(tr('dr_turns_tbl'))}</div>
      <table>
        <thead><tr><th>#</th><th>${esc(tr('th_time'))}</th><th>${esc(tr('th_model'))}</th><th class="num">${esc(tr('dr_th_ctx'))}</th><th class="num">${esc(tr('th_in_short'))}</th><th class="num">${esc(tr('th_out'))}</th></tr></thead>
        <tbody>
          ${turns.slice().reverse().slice(0, 80).map(t => `
            <tr>
              <td class="mono" style="color:var(--muted)">${t.turn}</td>
              <td class="mono" style="color:var(--muted)">${esc(t.ts_cst.slice(6))}</td>
              <td class="mono">${esc(t.model)} ${(t.tool_names||[]).slice(0,2).map(n => `<span class="tool-pill">${esc(n)}</span>`).join('')}</td>
              <td class="num">${fmtTok(t.context_size)}</td>
              <td class="num">${fmtTok(t.input_tokens)}</td>
              <td class="num">${fmtTok(t.output_tokens)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch (e) {
    document.getElementById('dr-body').innerHTML = `<div style="color:var(--red)">${esc(tr('dr_err', e))}</div>`;
  }
}

function closeOverlays() {
  document.getElementById('backdrop').classList.remove('open');
  document.getElementById('session-drawer').classList.remove('open');
  document.getElementById('quota-modal').classList.remove('open');
  document.getElementById('share-modal').classList.remove('open');
}

function renderAll(data) {
  document.getElementById('subtitle').textContent = tr('synced_sub', data.generated_at_cst, winName(currentWin));
  const tzLbl = data.timezone_label || 'UTC+8';
  const tzEl = document.getElementById('tz-lbl');
  if (tzEl) tzEl.textContent = tzLbl;
  const mTzEl = document.getElementById('modal-tz-lbl');
  if (mTzEl) mTzEl.textContent = tzLbl;
  const nOn = !!(data.notifications && data.notifications.enabled);
  const nBtn = document.getElementById('notify-btn');
  if (nBtn) {
    nBtn.textContent = nOn ? tr('ntf_on') : tr('ntf_off');
    nBtn.classList.toggle('live-on', nOn);
  }
  renderBanner(data);
  renderInsights(data);
  renderQuota(data);
  renderKPIs(data);
  renderMainChart(data);
  renderHeatmapAndPools(data);
  renderDetailPanes(data);
}

async function refresh() {
  try {
    const res = await fetch('/api/stats?window=' + encodeURIComponent(currentWin), { cache: 'no-store' });
    const data = await res.json();
    lastData = data;
    renderAll(data);
  } catch (err) {
    document.getElementById('subtitle').textContent = tr('sync_err', err);
  }
}

applyStaticI18n();

document.getElementById('lang-select').addEventListener('change', (e) => {
  const val = e.target.value;
  if (I18N[val]) {
    currentLang = val;
    localStorage.setItem(LANG_KEY, val);
    applyStaticI18n();
    if (lastData) renderAll(lastData);
  }
});

// Controls binding
document.querySelectorAll('#win-pills .pill').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#win-pills .pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentWin = btn.dataset.win;
    refresh();
  });
});

document.querySelectorAll('#chart-tabs .pill').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#chart-tabs .pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentChartTab = btn.dataset.ctab;
    if (lastData) renderMainChart(lastData);
  });
});

document.querySelectorAll('#metric-pills .pill').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#metric-pills .pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentMetric = btn.dataset.metric;
    if (lastData) renderMainChart(lastData);
  });
});

document.querySelectorAll('#detail-tabs .pill').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#detail-tabs .pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentDetailTab = btn.dataset.dtab;
    document.getElementById('detail-pane-convs').style.display = currentDetailTab === 'convs' ? 'block' : 'none';
    document.getElementById('detail-pane-models').style.display = currentDetailTab === 'models' ? 'block' : 'none';
    document.getElementById('detail-pane-tools').style.display = currentDetailTab === 'tools' ? 'block' : 'none';
    document.getElementById('conv-search').style.visibility = currentDetailTab === 'convs' ? 'visible' : 'hidden';
  });
});

document.querySelectorAll('th.sortable').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.dataset.sort;
    if (convSortKey === key) convSortDir *= -1;
    else { convSortKey = key; convSortDir = -1; }
    renderConvTable();
  });
});

document.getElementById('conv-search').addEventListener('input', renderConvTable);

document.getElementById('live-btn').addEventListener('click', () => {
  liveEnabled = !liveEnabled;
  const b = document.getElementById('live-btn');
  b.classList.toggle('live-on', liveEnabled);
  b.innerHTML = liveEnabled
    ? `<span class="dot ok"></span><span id="live-btn-lbl">${esc(tr('live_on'))}</span>`
    : `<span class="dot"></span><span id="live-btn-lbl">${esc(tr('live_off'))}</span>`;
  if (pollTimer) clearInterval(pollTimer);
  if (liveEnabled) pollTimer = setInterval(refresh, 3000);
});

document.getElementById('notify-btn').addEventListener('click', async () => {
  const cur = !!(lastData && lastData.notifications && lastData.notifications.enabled);
  try {
    const res = await fetch('/api/preferences', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notifications_enabled: !cur }),
    });
    if (res.ok) refresh();
  } catch (e) {}
});

document.getElementById('open-modal-btn').addEventListener('click', () => {
  document.getElementById('mq-msg').textContent = '';
  document.getElementById('backdrop').classList.add('open');
  document.getElementById('quota-modal').classList.add('open');
});

document.getElementById('export-btn').addEventListener('click', () => {
  window.location.href = '/api/export.csv?window=' + encodeURIComponent(currentWin);
});

// ==================== Viral Share Card Renderer (Zero-Dependency 2x Canvas) ====================
let scWin = '7d';
let scTheme = 'tongtou';

function scRoundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function drawShareCard() {
  if (!lastData) return;
  const cv = document.getElementById('sc-canvas');
  if (!cv) return;
  const ctx = cv.getContext('2d');
  const S = 2;
  const W = 780, H = 495;
  cv.width = W * S;
  cv.height = H * S;
  ctx.save();
  ctx.scale(S, S);

  const showUsd = document.getElementById('sc-usd-chk').checked;
  const wins = lastData.windows || {};
  const wObj = wins[scWin] || lastData.selected_summary || {};
  const q = lastData.quota || {};
  const buckets = q.buckets || [];
  const ls = lastData.live_session || {};
  const wow = lastData.week_over_week || {};

  const PALS = {
    tongtou: {
      bg0: '#F7F3EE', bg1: '#EFE8E0', glowA: 'rgba(123,167,167,0.22)', glowB: 'rgba(196,168,130,0.20)',
      border: '#DFD7CE', text: '#2C3E50', muted: '#6E6A64', card: 'rgba(255,253,251,0.88)', cardBd: '#E5DED5',
      badgeBg: 'rgba(77,124,124,0.13)', badgeFg: '#356262', pillBg: 'rgba(5,150,105,0.12)', pillFg: '#047857',
      gem: '#4D7C7C', cld: '#9A7B4F', track: '#E8E2DB', ok: '#059669', warn: '#D97706', crit: '#DC2626',
      footBg: '#FFFDFB', footBd: '#E6DFD6', urlBg: '#F2ECE5', urlFg: '#3D6B6B',
    },
    light: {
      bg0: '#FFF8FB', bg1: '#F3ECFF', glowA: 'rgba(244,114,182,0.24)', glowB: 'rgba(167,139,250,0.24)',
      border: '#FBCFE8', text: '#3A2430', muted: '#745664', card: 'rgba(255,255,255,0.80)', cardBd: '#FBCFE8',
      badgeBg: 'rgba(219,39,119,0.11)', badgeFg: '#BE185D', pillBg: 'rgba(124,58,237,0.11)', pillFg: '#6D28D9',
      gem: '#0E7490', cld: '#6D28D9', track: '#FCE7F3', ok: '#059669', warn: '#D97706', crit: '#DC2626',
      footBg: '#FFFFFF', footBd: '#FBCFE8', urlBg: '#FDF2F8', urlFg: '#9D174D',
    },
    dark: {
      bg0: '#1E293B', bg1: '#0F172A', glowA: 'rgba(56,189,248,0.18)', glowB: 'rgba(167,139,250,0.18)',
      border: '#334155', text: '#F8FAFC', muted: '#94A3B8', card: 'rgba(30,41,59,0.86)', cardBd: '#334155',
      badgeBg: 'rgba(56,189,248,0.15)', badgeFg: '#38BDF8', pillBg: 'rgba(16,185,129,0.16)', pillFg: '#34D399',
      gem: '#38BDF8', cld: '#C084FC', track: '#334155', ok: '#34D399', warn: '#FBBF24', crit: '#F87171',
      footBg: '#0F172A', footBd: '#334155', urlBg: '#1E293B', urlFg: '#38BDF8',
    },
  };
  const P = PALS[scTheme] || PALS.tongtou;
  const ff = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei UI", sans-serif';

  // Background & Soft Aurora Glows
  scRoundRect(ctx, 0, 0, W, H, 24);
  ctx.clip();
  const bgG = ctx.createLinearGradient(0, 0, W, H);
  bgG.addColorStop(0, P.bg0);
  bgG.addColorStop(1, P.bg1);
  ctx.fillStyle = bgG;
  ctx.fillRect(0, 0, W, H);

  const g1 = ctx.createRadialGradient(90, 20, 10, 90, 20, 340);
  g1.addColorStop(0, P.glowA); g1.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g1; ctx.fillRect(0, 0, W, H);

  const g2 = ctx.createRadialGradient(W - 80, 60, 10, W - 80, 60, 320);
  g2.addColorStop(0, P.glowB); g2.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g2; ctx.fillRect(0, 0, W, H);

  // Determine Dynamic Fun Rank Badge
  const gemW = buckets.find(b => String(b.pool_key || '').startsWith('gemini') && b.window_kind === 'weekly') || buckets[0];
  const cldW = buckets.find(b => b.pool_key === 'claude_gpt' && b.window_kind === 'weekly') || buckets[1];
  const totTok = Number(wObj.total_tokens || 0);
  const hitPct = Number(wObj.cache_hit_pct || 0);
  let rankTxt = tr('sc_rank_zen');
  if (buckets.some(b => b.used_pct != null && b.used_pct >= 80 && !b.reset_passed)) rankTxt = tr('sc_rank_edge');
  else if (totTok >= 1e8 && hitPct >= 85) rankTxt = tr('sc_rank_save');
  else if ((gemW && gemW.used_pct != null && gemW.used_pct <= 5) || (cldW && cldW.used_pct != null && cldW.used_pct <= 5)) rankTxt = tr('sc_rank_reset');
  else if (totTok >= 3e7) rankTxt = tr('sc_rank_power');

  // Top Row: Rank Pill + Window/Tier
  ctx.font = '700 13px ' + ff;
  const bw = ctx.measureText(rankTxt).width + 26;
  scRoundRect(ctx, 32, 28, bw, 30, 15);
  ctx.fillStyle = P.badgeBg; ctx.fill();
  ctx.fillStyle = P.badgeFg; ctx.fillText(rankTxt, 45, 48);

  const tierBit = (ls.plan_tier && ls.plan_tier !== '-') ? (' · ' + ls.plan_tier) : '';
  const dateStr = tr('sc_win_lbl', winName(scWin)) + tierBit;
  ctx.font = '600 12.5px ' + ff;
  ctx.fillStyle = P.muted;
  ctx.textAlign = 'right';
  ctx.fillText(dateStr, W - 32, 48);
  ctx.textAlign = 'left';

  // Hero Big Token Number + Savings / Hit Pill
  ctx.font = '600 13px ' + ff;
  ctx.fillStyle = P.muted;
  ctx.fillText(tr('sc_kicker'), 32, 86);

  const tokStr = fmtTok(totTok);
  ctx.font = '800 50px ' + ff;
  ctx.fillStyle = P.text;
  ctx.fillText(tokStr, 32, 138);
  const tokW = ctx.measureText(tokStr).width;

  const pillStr = showUsd
    ? tr('sc_save_pill', hitPct.toFixed(1), fmtUsd(wObj.cache_saved_usd || 0))
    : tr('sc_hit_pill', hitPct.toFixed(1));
  ctx.font = '700 14px ' + ff;
  const pw = ctx.measureText(pillStr).width + 24;
  const px = Math.min(W - pw - 32, 32 + tokW + 16);
  scRoundRect(ctx, px, 108, pw, 32, 9);
  ctx.fillStyle = P.pillBg; ctx.fill();
  ctx.fillStyle = P.pillFg; ctx.fillText(pillStr, px + 12, 129);

  // Dual Pool Cards
  function drawPoolBox(bx, by, boxW, boxH, title, accentCol, bkt) {
    scRoundRect(ctx, bx, by, boxW, boxH, 16);
    ctx.fillStyle = P.card; ctx.fill();
    ctx.strokeStyle = P.cardBd; ctx.lineWidth = 1; ctx.stroke();

    ctx.font = '700 13px ' + ff;
    ctx.fillStyle = accentCol;
    ctx.fillText(title, bx + 18, by + 28);

    const hasU = bkt && bkt.used_pct != null;
    const u = hasU ? Number(bkt.used_pct) : 0;
    const exp = !!(bkt && bkt.reset_passed);
    const vCol = !hasU ? P.muted : (exp ? P.muted : (u >= 80 ? P.crit : (u >= 55 ? P.warn : P.ok)));
    const stWord = !hasU ? tr('st_pending') : (exp ? tr('b_ready') : (u >= 80 ? tr('b_crit') : (u >= 55 ? tr('b_warn') : tr('b_ok'))));

    ctx.textAlign = 'right';
    ctx.font = '700 12px ' + ff;
    ctx.fillStyle = vCol;
    ctx.fillText(stWord, bx + boxW - 18, by + 28);
    ctx.textAlign = 'left';

    const valMain = hasU ? (tr('used_lbl') + ' ' + u.toFixed(1) + '%') : '—';
    ctx.font = '800 24px ' + ff;
    ctx.fillStyle = vCol;
    ctx.fillText(valMain, bx + 18, by + 64);

    const rstSub = !hasU ? '' : (exp ? tr('expired_wait') : (bkt.reset_in_seconds != null ? tr('rem_time', fmtCountdown(bkt.reset_in_seconds)) : (bkt.reset_time_cst || '')));
    ctx.textAlign = 'right';
    ctx.font = '600 11.5px ' + ff;
    ctx.fillStyle = P.muted;
    ctx.fillText(rstSub, bx + boxW - 18, by + 63);
    ctx.textAlign = 'left';

    scRoundRect(ctx, bx + 18, by + 80, boxW - 36, 8, 4);
    ctx.fillStyle = P.track; ctx.fill();
    if (hasU && u > 0) {
      const fw = Math.max(8, Math.min(boxW - 36, ((boxW - 36) * u) / 100));
      scRoundRect(ctx, bx + 18, by + 80, fw, 8, 4);
      ctx.fillStyle = vCol; ctx.fill();
    }
  }

  const boxW = (W - 64 - 16) / 2;
  drawPoolBox(32, 162, boxW, 106, tr('sc_gem_lbl'), P.gem, gemW);
  drawPoolBox(32 + boxW + 16, 162, boxW, 106, tr('sc_cld_lbl'), P.cld, cldW);

  // 3 Mini KPIs Row
  const kpis = [
    { k: tr('th_calls'), v: tr('n_calls', wObj.calls || 0), c: P.text },
    showUsd && wow && wow.comparable && scWin === '7d'
      ? { k: tr('kpi_7d_t'), v: (wow.delta_pct <= 0 ? '↓ ' : '↑ ') + Math.abs(wow.delta_pct).toFixed(1) + '% vs last wk', c: wow.delta_pct <= 0 ? P.ok : P.warn }
      : { k: tr('sc_net_tok'), v: fmtTok(wObj.billable_tokens || 0) + ' tok', c: P.text },
    { k: tr('st_model'), v: String(ls.active_model || '-').replace(' (High)', '').slice(0, 22), c: P.text },
  ];
  const kw = (W - 64) / 3;
  kpis.forEach((it, idx) => {
    const kx = 32 + idx * kw;
    ctx.font = '600 11.5px ' + ff;
    ctx.fillStyle = P.muted;
    ctx.fillText(it.k, kx, 304);
    ctx.font = '750 16.5px ' + ff;
    ctx.fillStyle = it.c;
    ctx.fillText(it.v, kx, 328);
  });

  // Leica-Style Watermark Footer
  const fy = H - 76;
  ctx.fillStyle = P.footBg;
  ctx.fillRect(0, fy, W, 76);
  ctx.strokeStyle = P.footBd;
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(0, fy); ctx.lineTo(W, fy); ctx.stroke();

  const logoImg = document.getElementById('brand-logo-img');
  if (logoImg) {
    if (logoImg.complete && logoImg.naturalWidth > 0) {
      ctx.save();
      scRoundRect(ctx, 32, fy + 19, 38, 38, 9);
      ctx.clip();
      ctx.drawImage(logoImg, 32, fy + 19, 38, 38);
      ctx.restore();
    } else {
      logoImg.addEventListener('load', drawShareCard, { once: true });
    }
  }

  ctx.font = '800 14px ' + ff;
  ctx.fillStyle = P.text;
  ctx.fillText(tr('h1'), 82, fy + 35);
  ctx.font = '500 11px ' + ff;
  ctx.fillStyle = P.muted;
  ctx.fillText(tr('sc_tag_sub'), 82, fy + 53);

  const repoUrl = 'github.com/qiudai0627/agy-usage';
  ctx.font = '700 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  const uw = ctx.measureText(repoUrl).width + 22;
  scRoundRect(ctx, W - 32 - uw, fy + 23, uw, 30, 8);
  ctx.fillStyle = P.urlBg; ctx.fill();
  ctx.fillStyle = P.urlFg;
  ctx.fillText(repoUrl, W - 32 - uw + 11, fy + 42);

  // Outer Card Rim
  scRoundRect(ctx, 0.75, 0.75, W - 1.5, H - 1.5, 24);
  ctx.strokeStyle = P.border;
  ctx.lineWidth = 1.5;
  ctx.stroke();

  ctx.restore();
}

function syncSharePills() {
  document.querySelectorAll('#sc-win-pills .pill').forEach(b => b.classList.toggle('active', b.getAttribute('data-sc-win') === scWin));
  document.querySelectorAll('#sc-theme-pills .pill').forEach(b => b.classList.toggle('active', b.getAttribute('data-sc-theme') === scTheme));
}

function openShareModal() {
  scTheme = resolvedTheme(prefTheme());
  scWin = (currentWin === 'today' || currentWin === 'all') ? currentWin : '7d';
  syncSharePills();
  document.getElementById('backdrop').classList.add('open');
  document.getElementById('share-modal').classList.add('open');
  drawShareCard();
}

document.getElementById('sc-win-pills').addEventListener('click', e => {
  const b = e.target.closest('[data-sc-win]');
  if (!b) return;
  scWin = b.getAttribute('data-sc-win');
  syncSharePills();
  drawShareCard();
});

document.getElementById('sc-theme-pills').addEventListener('click', e => {
  const b = e.target.closest('[data-sc-theme]');
  if (!b) return;
  scTheme = b.getAttribute('data-sc-theme');
  syncSharePills();
  drawShareCard();
});

document.getElementById('sc-usd-chk').addEventListener('change', drawShareCard);

document.getElementById('sc-dl-btn').addEventListener('click', () => {
  const cv = document.getElementById('sc-canvas');
  const a = document.createElement('a');
  a.download = 'agy-usage-card-' + scWin + '.png';
  a.href = cv.toDataURL('image/png');
  a.click();
});

document.getElementById('sc-copy-img-btn').addEventListener('click', (evt) => {
  burstSparks(evt.clientX, evt.clientY);
  const cv = document.getElementById('sc-canvas');
  const btn = document.getElementById('sc-copy-img-btn');
  cv.toBlob(async blob => {
    if (!blob) return;
    try {
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
      btn.textContent = tr('sc_copied_img');
      setTimeout(() => { btn.textContent = tr('sc_copy_img'); }, 1800);
    } catch (_) {
      const a = document.createElement('a');
      a.download = 'agy-usage-card-' + scWin + '.png';
      a.href = URL.createObjectURL(blob);
      a.click();
    }
  }, 'image/png');
});

document.getElementById('sc-copy-post-btn').addEventListener('click', async () => {
  if (!lastData) return;
  const wObj = (lastData.windows || {})[scWin] || lastData.selected_summary || {};
  const postTxt = tr('sc_post_tpl', winName(scWin), fmtTok(wObj.total_tokens || 0), Number(wObj.cache_hit_pct || 0).toFixed(1));
  if (navigator.clipboard) await navigator.clipboard.writeText(postTxt);
  const btn = document.getElementById('sc-copy-post-btn');
  btn.textContent = tr('sc_copied_post');
  setTimeout(() => { btn.textContent = tr('sc_copy_post'); }, 1800);
});

document.getElementById('theme-pills').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-theme-pref]');
  if (!btn) return;
  localStorage.setItem(THEME_KEY, btn.getAttribute('data-theme-pref'));
  applyTheme();
});

document.getElementById('mq-save-btn').addEventListener('click', async () => {
  const bucket = document.getElementById('mq-bucket').value;
  const used = parseFloat(document.getElementById('mq-used').value);
  const reset = document.getElementById('mq-reset').value.trim();
  const msg = document.getElementById('mq-msg');
  if (isNaN(used) || used < 0 || used > 100) {
    msg.textContent = tr('mq_err_range');
    return;
  }
  try {
    const res = await fetch('/api/record-quota', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bucket, remaining_pct: Math.max(0, Math.min(100, 100 - used)), reset }),
    });
    const out = await res.json();
    if (!res.ok || !out.ok) {
      msg.textContent = out.error || tr('mq_err_save');
      return;
    }
    closeOverlays();
    refresh();
  } catch (e) {
    msg.textContent = tr('mq_err_req', e);
  }
});

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeOverlays(); });

refresh();
pollTimer = setInterval(refresh, 3000);
</script>
</body>
</html>
"""

LOGO_DATA_URI = "data:image/png;base64,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"

DASHBOARD_HTML = (
    _DASHBOARD_TEMPLATE.replace("__LANG_OPTIONS_JSON__", LANG_OPTIONS_JS)
    .replace("__WEB_I18N_JSON__", WEB_I18N_JS)
    .replace("__LOGO_DATA_URI__", LOGO_DATA_URI)
)
