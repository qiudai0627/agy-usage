#!/usr/bin/env python3
"""Clean, high-density, zero-CDN real-time Web Dashboard for Antigravity CLI (agy-usage)."""

from __future__ import annotations

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Antigravity · 实时用量与限额监控台</title>
<style>
  :root[data-theme="dark"] {
    --bg: #080c15;
    --bg-grad: radial-gradient(1000px 480px at 12% -10%, rgba(37, 99, 235, 0.13), transparent 60%),
               radial-gradient(800px 420px at 88% -5%, rgba(124, 58, 237, 0.10), transparent 55%);
    --panel: rgba(14, 20, 34, 0.88);
    --panel-solid: #0e1422;
    --panel-sub: rgba(20, 29, 48, 0.65);
    --panel-hover: rgba(26, 37, 62, 0.85);
    --border: rgba(148, 163, 184, 0.13);
    --border-strong: rgba(56, 189, 248, 0.35);
    --text: #e2e8f0;
    --text-strong: #f8fafc;
    --muted: #8494ad;
    --chip-bg: rgba(11, 16, 28, 0.9);
    --track: #1b2538;
    --grid-line: rgba(148, 163, 184, 0.09);
    --heat-0: #121a2b;
    --heat-1: #154559;
    --heat-2: #0369a1;
    --heat-3: #0ea5e9;
    --heat-4: #8b5cf6;
    --shadow: 0 6px 22px rgba(0, 0, 0, 0.28);
  }
  :root[data-theme="light"] {
    --bg: #f4f7fb;
    --bg-grad: radial-gradient(900px 400px at 10% -10%, rgba(37, 99, 235, 0.08), transparent 60%);
    --panel: rgba(255, 255, 255, 0.94);
    --panel-solid: #ffffff;
    --panel-sub: #f8fafc;
    --panel-hover: #f1f5f9;
    --border: rgba(15, 23, 42, 0.09);
    --border-strong: rgba(37, 99, 235, 0.35);
    --text: #1e293b;
    --text-strong: #0f172a;
    --muted: #64748b;
    --chip-bg: #f1f5f9;
    --track: #e2e8f0;
    --grid-line: rgba(15, 23, 42, 0.07);
    --heat-0: #eaeff7;
    --heat-1: #bae6fd;
    --heat-2: #38bdf8;
    --heat-3: #2563eb;
    --heat-4: #7c3aed;
    --shadow: 0 4px 16px rgba(15, 23, 42, 0.05);
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
    width: 30px; height: 30px; border-radius: 8px;
    background: linear-gradient(135deg, #2563eb, #06b6d4 60%, #8b5cf6);
    display: grid; place-items: center; font-weight: 700; font-size: 11.5px; color: #fff;
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
    position: absolute; top: -2px; bottom: -2px; width: 2px; background: #fff;
    border-radius: 1px; box-shadow: 0 0 4px rgba(0,0,0,0.6);
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
    background: rgba(9, 13, 24, 0.95); color: #e2e8f0; border: 1px solid rgba(56, 189, 248, 0.35);
    border-radius: 8px; padding: 7px 10px; font-size: 11px; line-height: 1.45;
    box-shadow: 0 8px 24px rgba(0,0,0,0.45); max-width: 260px; backdrop-filter: blur(8px);
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
  .modal.open { display: block; }
  .field { margin-bottom: 10px; }
  .field label { display: block; font-size: 11px; color: var(--muted); margin-bottom: 4px; font-weight: 600; }
  .field input, .field select {
    width: 100%; background: var(--chip-bg); border: 1px solid var(--border); color: var(--text);
    border-radius: 7px; padding: 6px 9px; font-size: 12px; outline: none;
  }

  .footnote { font-size: 10.5px; color: var(--muted); margin-top: 12px; text-align: right; }
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
    <button class="btn" data-action="close">关闭 ✕</button>
  </div>
  <div class="drawer-body" id="dr-body"></div>
</aside>

<!-- Manual Quota Calibration Modal -->
<div class="modal" id="quota-modal">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
    <strong style="font-size:13.5px;color:var(--text-strong)">手动录入 /usage 限额快照</strong>
    <button class="btn" data-action="close">✕</button>
  </div>
  <p style="font-size:11px;color:var(--muted);margin:0 0 10px;">将 <code>/usage</code> 页面看到的「已使用 %」填入，即可立即生成周配速与耗尽预测。</p>
  <div class="field">
    <label>限额池</label>
    <select id="mq-bucket">
      <option value="gemini-5h">Gemini · 当前用量 5h (gemini-5h)</option>
      <option value="gemini-weekly">Gemini · 每周限额 7d (gemini-weekly)</option>
      <option value="claude-5h">Claude/GPT · 当前用量 5h (3p-5h)</option>
      <option value="claude-weekly">Claude/GPT · 每周限额 7d (3p-weekly)</option>
    </select>
  </div>
  <div class="field">
    <label>已使用百分比 (0 ~ 100)</label>
    <input id="mq-used" type="number" step="0.01" min="0" max="100" placeholder="例如 9.1 或 54.9" />
  </div>
  <div class="field">
    <label>重置时间 <span id="modal-tz-lbl">本地时区</span> (可选，如 12-01 18:46)</label>
    <input id="mq-reset" type="text" placeholder="12-01 18:46" />
  </div>
  <div id="mq-msg" style="font-size:11px;margin-bottom:8px;color:var(--red)"></div>
  <div style="display:flex;justify-content:flex-end;gap:6px;">
    <button class="btn" data-action="close">取消</button>
    <button class="btn primary" id="mq-save-btn">保存</button>
  </div>
</div>

<div class="wrap">
  <header>
    <div class="brand">
      <div class="logo">AGY</div>
      <div>
        <h1>Antigravity 实时用量与限额监控台</h1>
        <div class="sub"><span class="dot ok"></span><span id="subtitle">正在同步本地遥测数据...</span></div>
      </div>
    </div>
    <div class="controls">
      <div class="pills" id="win-pills">
        <button class="pill" data-win="5h">5小时</button>
        <button class="pill" data-win="today">今日</button>
        <button class="pill" data-win="24h">24h</button>
        <button class="pill" data-win="week">本周</button>
        <button class="pill active" data-win="7d">近7天</button>
        <button class="pill" data-win="all">全部</button>
      </div>
      <button class="btn live-on" id="live-btn"><span class="dot ok"></span>实时 3s</button>
      <button class="btn" id="notify-btn" title="开启或关闭 80%/95% 额度提醒与回血桌面通知">🔔 提醒: 关</button>
      <button class="btn" id="open-modal-btn">＋录入限额</button>
      <button class="btn" id="export-btn">导出 CSV</button>
      <button class="btn" id="theme-btn">☀ 亮色</button>
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
          <button class="pill active" data-ctab="5h">近5h燃速 (10m)</button>
          <button class="pill" data-ctab="24h">24h每小时</button>
          <button class="pill" data-ctab="7d">7日周趋势</button>
          <button class="pill" data-ctab="quota">限额已用曲线</button>
        </div>
        <div class="pills" id="metric-pills">
          <button class="pill active" data-metric="billable_tokens">有效Token</button>
          <button class="pill" data-metric="total_tokens">含缓存</button>
          <button class="pill" data-metric="calls">调用数</button>
          <button class="pill" data-metric="est_cost_usd">估算$</button>
        </div>
      </div>
      <div class="chart-box" id="main-chart-box"></div>
      <div class="legend" id="main-chart-legend"></div>
    </div>

    <div class="card">
      <div class="card-head">
        <span class="card-title">7日 × 24小时作业热力图 <span class="card-sub">(<span id="tz-lbl">UTC+8</span>)</span></span>
        <div style="display:inline-flex;align-items:center;gap:4px;font-size:10px;color:var(--muted);">
          <span>低</span>
          <span class="swatch" style="background:var(--heat-0)"></span>
          <span class="swatch" style="background:var(--heat-1)"></span>
          <span class="swatch" style="background:var(--heat-2)"></span>
          <span class="swatch" style="background:var(--heat-3)"></span>
          <span class="swatch" style="background:var(--heat-4)"></span>
          <span>高</span>
        </div>
      </div>
      <div class="heatmap-wrap" id="heatmap-box"></div>
      <div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border);">
        <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:6px;">
          <span>模型限额池占比 (<span id="win-badge-pool">近7天</span>)</span>
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
          <button class="pill active" data-dtab="convs">会话消耗排行</button>
          <button class="pill" data-dtab="models">细分模型明细</button>
          <button class="pill" data-dtab="tools">工作区 &amp; 高频工具</button>
        </div>
        <input class="search-input" id="conv-search" type="text" placeholder="搜索会话 / 工作区 / 模型..." />
      </div>
      <div id="detail-pane-convs" style="overflow-x:auto;">
        <table>
          <thead>
            <tr>
              <th>会话标题 <span style="font-weight:400;color:var(--muted)">(点击看逐轮曲线)</span></th>
              <th>工作区</th>
              <th class="num sortable" data-sort="calls">调用 ↕</th>
              <th class="num sortable" data-sort="billable_tokens">有效Token ↕</th>
              <th class="num sortable" data-sort="peak_context">峰值上下文 ↕</th>
              <th class="num sortable" data-sort="cache_hit_pct">缓存率 ↕</th>
              <th class="num sortable" data-sort="est_cost_usd">估算$ ↕</th>
            </tr>
          </thead>
          <tbody id="conv-tbody"></tbody>
        </table>
      </div>
      <div id="detail-pane-models" style="display:none;overflow-x:auto;">
        <table>
          <thead>
            <tr>
              <th>模型名称</th>
              <th>所属限额池</th>
              <th class="num">调用</th>
              <th class="num">新增输入</th>
              <th class="num">缓存命中</th>
              <th class="num">输出</th>
              <th class="num">缓存率</th>
              <th class="num">估算$</th>
            </tr>
          </thead>
          <tbody id="model-tbody"></tbody>
        </table>
      </div>
      <div id="detail-pane-tools" style="display:none;">
        <div class="grid grid-2" style="margin-bottom:0">
          <div>
            <div style="font-size:11.5px;font-weight:600;margin-bottom:8px;color:var(--text-strong)">工作区消耗占比</div>
            <div id="project-list"></div>
          </div>
          <div>
            <div style="font-size:11.5px;font-weight:600;margin-bottom:8px;color:var(--text-strong)">高频 Agent 工具调用</div>
            <div id="tools-list"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <span class="card-title">最近调用实时流水</span>
        <span class="badge ok">最新 18 条</span>
      </div>
      <div style="overflow-x:auto;max-height:340px;overflow-y:auto;">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>模型 / 会话</th>
              <th class="num">新增</th>
              <th class="num">缓存</th>
              <th class="num">输出</th>
            </tr>
          </thead>
          <tbody id="recent-tbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="footnote">
    纯本地隐私架构 · 数据源：本地 transcript.jsonl + 官方 statusLine 实时配额 JSON · 费用与缓存节省按公开单价估算，非官方账单。
  </div>
</div>

<script>
const WIN_NAMES = { '5h': '近5小时', 'today': '今日', '24h': '近24小时', 'week': '本周', '7d': '近7天', 'all': '全部' };
const POOL_COLORS = { gemini_pro: '#38bdf8', claude_gpt: '#a78bfa', gemini_flash: '#10b981', other: '#64748b' };

let currentWin = '7d';
let currentChartTab = '5h';
let currentDetailTab = 'convs';
let currentMetric = 'billable_tokens';
let liveEnabled = true;
let pollTimer = null;
let lastData = null;
let convSortKey = 'billable_tokens';
let convSortDir = -1;

// Theme setup
(function initTheme() {
  const saved = localStorage.getItem('agy-usage-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  document.getElementById('theme-btn').textContent = saved === 'dark' ? '☀ 亮色' : '☾ 暗色';
})();

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
  if (d > 0) return `${d}天${h}小时${m}分`;
  if (h > 0) return `${h}小时${m}分${s}秒`;
  return `${m}分${s}秒`;
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
    copyEl.textContent = '已复制 ✓';
    setTimeout(() => { copyEl.textContent = old; }, 1100);
    return;
  }
  const sessEl = evt.target.closest('[data-session]');
  if (sessEl) {
    openSession(sessEl.getAttribute('data-session'));
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
    el.textContent = remSec > 0 ? '剩 ' + fmtCountdown(remSec) : '已到期 · 待刷新';
  });
}, 1000);

function renderBanner(data) {
  const ls = data.live_session || {};
  const q = data.quota || {};
  const ctx = ls.context_window;
  let ctxHtml = '<span class="v" style="color:var(--muted)">待推送</span>';
  if (ctx && ctx.used_percentage != null) {
    const u = Number(ctx.used_percentage);
    const col = u >= 80 ? 'var(--red)' : (u >= 55 ? 'var(--yellow)' : 'var(--cyan)');
    ctxHtml = `<span class="v" style="color:${col}">${u.toFixed(1)}%</span> <span style="color:var(--muted)">(${fmtTok((ctx.total_input_tokens||0)+(ctx.total_output_tokens||0))}/${fmtTok(ctx.context_window_size||0)})</span>`;
  }
  const slBadge = ls.connected
    ? `<span class="dot ok"></span>已连接 <span style="color:var(--muted);font-weight:400">(${esc(ls.captured_at_cst)})</span>`
    : (ls.statusline_configured
        ? `<span class="dot warn"></span>待触发推送`
        : `<span class="dot err"></span>未接入`);
  const slCmd = '/statusline ' + (ls.statusline_path || 'statusline.py');

  document.getElementById('live-banner').innerHTML = `
    <div class="strip-left">
      <div class="kv"><span class="k">实时通道</span><span class="v">${slBadge}</span></div>
      <div class="kv"><span class="k">主模型</span><span class="v" style="color:var(--cyan)">${esc(ls.active_model)}</span></div>
      <div class="kv"><span class="k">Planner</span><span class="v" style="color:var(--purple)">${esc(ls.configured_planner)}</span></div>
      <div class="kv"><span class="k">当前上下文</span>${ctxHtml}</div>
      ${ls.plan_tier && ls.plan_tier !== '-' ? `<div class="kv"><span class="badge">${esc(ls.plan_tier)}</span></div>` : ''}
      ${q.has_live_quota ? `<div class="kv"><span class="k">采样</span><span class="v">${q.snapshot_count}条</span></div>` : ''}
    </div>
    <span class="code-chip" title="点击复制" data-copy="${esc(slCmd)}">${esc(slCmd)}</span>
  `;
}

function renderInsights(data) {
  const list = data.insights || [];
  document.getElementById('insights-strip').innerHTML = list.map(i => `
    <div class="ichip ${esc(i.level)}"><b>${esc(i.title)}</b><span>${esc(i.detail)}</span></div>
  `).join('');
}

function renderQuota(data) {
  const q = data.quota || {};
  const ls = data.live_session || {};
  const el = document.getElementById('quota-section');

  if (!q.has_live_quota) {
    const slCmd = '/statusline ' + (ls.statusline_path || 'statusline.py');
    el.innerHTML = `
      <div class="card onboarding" style="margin-bottom:12px;">
        <div class="card-head" style="margin-bottom:6px;">
          <span class="card-title">接入官方每周限额 &amp; 5小时限额实时遥测</span>
          <span class="badge warn">${ls.statusline_configured ? '等待首次触发' : '差一步激活'}</span>
        </div>
        <div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px;">
          <span style="color:var(--muted);font-size:11.5px;">在已打开的 <code>agy</code> 窗口运行右侧命令（或新开一个会话），即可实时显示 Gemini 与 Claude/GPT 四桶精确剩余 % 与重置倒计时。</span>
          <div style="display:flex;gap:6px;align-items:center;">
            <span class="code-chip" data-copy="${esc(slCmd)}">${esc(slCmd)}</span>
            <button class="btn primary" data-copy="${esc(slCmd)}">复制命令</button>
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

    let badge = '<span class="badge ok">健康</span>';
    if (b.status === 'reset_ready') badge = '<span class="badge">待刷新</span>';
    else if (b.status === 'critical') badge = '<span class="badge crit">告急</span>';
    else if (b.status === 'warning') badge = '<span class="badge warn">偏快</span>';

    const resetEpoch = (!b.reset_passed && b.reset_time) ? new Date(b.reset_time).getTime() : 0;
    const winName = b.window_kind === 'five_hour' ? '当前用量 (5h 窗口)' : (b.window_kind === 'weekly' ? '每周限额 (7d 周期)' : b.label);

    const budgetBit = b.reset_passed
      ? '下次调用刷新'
      : (b.window_kind === 'weekly' && b.daily_safe_budget_pct != null
          ? `日均可用 <strong>${b.daily_safe_budget_pct}%</strong>`
          : (b.hourly_safe_budget_pct != null ? `每小时可用 <strong>${b.hourly_safe_budget_pct}%</strong>` : ''));
    const forecastBit = (!b.reset_passed && b.projected_rem_at_reset != null)
      ? (b.projected_rem_at_reset <= 0.1
          ? `<span style="color:var(--red)">预计 ${esc(b.projected_exhaust_text)} 耗尽</span>`
          : `重置前预计剩 <strong style="color:var(--green)">${b.projected_rem_at_reset.toFixed(1)}%</strong>`)
      : '';
    const ratioBit = (!b.reset_passed && b.pacing_ratio != null) ? `配速 <strong>${b.pacing_ratio}x</strong>` : '';
    const tokBit = b.tokens_per_1pct ? `1%≈<strong>${fmtTok(b.tokens_per_1pct)}</strong>` : '';

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
            <span class="mini-ring-lbl">已用</span>
          </div>
        </div>
        <div style="min-width:0">
          <div class="b-top">
            <div><span class="b-name">${esc(winName)}</span> <span style="color:var(--muted)">剩 ${remDisp}%</span> ${badge}</div>
            <span style="color:var(--cyan);font-weight:600;font-size:11px" ${resetEpoch ? `data-reset-ts="${resetEpoch}"` : ''}>${b.reset_passed ? '已到期 · 待刷新' : '剩 ' + esc(b.reset_in_text)}</span>
          </div>
          <div class="dual-bar" data-tip-title="${esc(b.label)}" data-tip="${esc(`已用额度: ${usedDisp}% · 周期时间已过: ${(b.time_elapsed_pct||0).toFixed(1)}%\n重置时间: ${b.reset_time_cst} (${data.timezone_label || 'UTC+8'})`)}">
            <div class="dual-fill" style="width:${used}%;background:${col}"></div>
            ${b.time_elapsed_pct != null ? `<div class="time-marker" style="left:${Math.min(99, b.time_elapsed_pct)}%"></div>` : ''}
          </div>
          <div class="b-meta">
            <span>重置 ${esc(b.reset_time_cst)}</span>
            <span>${[ratioBit, budgetBit, forecastBit, tokBit].filter(Boolean).join(' · ')}</span>
          </div>
        </div>
      </div>
    `;
  }

  const pools = [
    { key: 'gemini', cls: 'pool-gemini', dot: '#38bdf8', title: 'Google Gemini 模型池', sub: 'Gemini 4 Neon / Carbon / Flash', items: q.buckets.filter(b => (b.pool_key || '').startsWith('gemini')) },
    { key: 'claude', cls: 'pool-claude', dot: '#a78bfa', title: 'Claude / GPT 第三方模型池 (3P)', sub: 'Claude Opus / Sonnet 5.5 · GPT', items: q.buckets.filter(b => b.pool_key === 'claude_gpt') },
    { key: 'other', cls: '', dot: '#64748b', title: '其他限额池', sub: '', items: q.buckets.filter(b => !(b.pool_key || '').startsWith('gemini') && b.pool_key !== 'claude_gpt') },
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
  let wowBadge = '<span class="badge muted" data-tip-title="自然周同进度环比" data-tip="上周同期缺少本地样本，暂不可比">较上周: 暂不可比</span>';
  if (wow.comparable && wow.delta_pct != null) {
    const cls = wow.delta_pct <= 0 ? 'ok' : (wow.delta_pct >= 35 ? 'warn' : 'purple');
    const prevTok = fmtTok((wow.previous || {}).billable_tokens || 0);
    const curTok = fmtTok((wow.current || {}).billable_tokens || 0);
    const tipTxt = `本周已过 ${wow.elapsed_hours || 0}h: ${curTok}\n上周同期 ${wow.elapsed_hours || 0}h: ${prevTok}\n注: 按本地自然周同进度统计，独立于滚动配额周期`;
    wowBadge = `<span class="badge ${cls}" style="cursor:help" data-tip-title="本周 vs 上周同进度环比" data-tip="${esc(tipTxt)}">${esc(wow.badge_text)}</span>`;
  } else if (wow.badge_text) {
    wowBadge = `<span class="badge muted" style="cursor:help" data-tip-title="自然周同进度环比" data-tip="${esc(wow.reason || '')}">${esc(wow.badge_text)}</span>`;
  }
  document.getElementById('kpi-cards').innerHTML = `
    <div class="card kpi-card">
      <div style="display:flex;justify-content:space-between;align-items:center;"><span class="card-sub">近 5 小时有效消耗</span><span class="badge">燃速 ${fmtTok(b5.billable_tokens_per_hour||0)}/h</span></div>
      <div class="kpi-val" style="color:var(--cyan)">${fmtTok(w5.billable_tokens)}</div>
      <div class="kpi-sub">输入 ${fmtTok(w5.input_tokens)} · 输出 ${fmtTok(w5.output_tokens)}</div>
      <div class="kpi-foot"><span>${w5.calls || 0} 次调用 (${b5.calls_per_hour||0}/h)</span><span>估算 ${fmtUsd(w5.est_cost_usd)}</span></div>
    </div>
    <div class="card kpi-card">
      <div style="display:flex;justify-content:space-between;align-items:center;"><span class="card-sub">今日累计有效消耗</span><span class="badge ok">Today</span></div>
      <div class="kpi-val">${fmtTok(wt.billable_tokens)}</div>
      <div class="kpi-sub">输入 ${fmtTok(wt.input_tokens)} · 输出 ${fmtTok(wt.output_tokens)}</div>
      <div class="kpi-foot"><span>${wt.calls || 0} 次调用 · ${wt.tool_calls || 0} 工具</span><span>估算 ${fmtUsd(wt.est_cost_usd)}</span></div>
    </div>
    <div class="card kpi-card">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:4px;"><span class="card-sub">近 7 天周累计</span>${wowBadge}</div>
      <div class="kpi-val" style="color:var(--purple)">${fmtTok(w7.billable_tokens)}</div>
      <div class="kpi-sub">含缓存总吞吐 ${fmtTok(w7.total_tokens)}</div>
      <div class="kpi-foot"><span>${w7.calls || 0} 次调用 · ${w7.conversations || 0} 会话</span><span>估算 ${fmtUsd(w7.est_cost_usd)}</span></div>
    </div>
    <div class="card kpi-card">
      <div style="display:flex;justify-content:space-between;align-items:center;"><span class="card-sub">缓存节省 (${esc(WIN_NAMES[currentWin]||currentWin)})</span><span class="badge ok">命中 ${wsel.cache_hit_pct||0}%</span></div>
      <div class="kpi-val" style="color:var(--green)">${fmtUsd(wsel.cache_saved_usd)}</div>
      <div class="kpi-sub">命中 ${fmtTok(wsel.cache_read_tokens)} tok (省 ${wsel.cache_saved_pct||0}%)</div>
      <div class="kpi-foot"><span>实际估算 ${fmtUsd(wsel.est_cost_usd)}</span><span>无缓存 ${fmtUsd((wsel.est_cost_usd||0)+(wsel.cache_saved_usd||0))}</span></div>
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
      box.innerHTML = `<div style="height:210px;display:grid;place-items:center;color:var(--muted);">采样点积累中（随会话进行自动生成变化曲线）</div>`;
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
      // Deduplicate consecutive identical remaining_pct values (keep endpoints & changes)
      const raw = b.history;
      const slim = raw.filter((pt, i) => i === 0 || i === raw.length - 1 || pt.used_pct !== raw[i - 1].used_pct);
      const coords = slim.map(p => ({
        x: padL + ((new Date(p.ts).getTime() - minT) / spanT) * (W - padL - padR),
        y: padT + (1 - (p.used_pct || 0) / 100) * (H - padT - padB),
        p,
      }));
      paths += `<polyline fill="none" stroke="${c}" stroke-width="2" points="${coords.map(o => `${o.x.toFixed(1)},${o.y.toFixed(1)}`).join(' ')}" />`;
      coords.forEach(o => {
        const tipTitle = `${b.label} · ${o.p.ts_cst}`;
        const tipTxt = `已使用: ${o.p.used_pct}% · 剩余: ${o.p.remaining_pct}%`;
        paths += `<circle cx="${o.x.toFixed(1)}" cy="${o.y.toFixed(1)}" r="3" fill="${c}" style="cursor:pointer" data-tip-title="${esc(tipTitle)}" data-tip="${esc(tipTxt)}" />`;
      });
      leg += `<span class="legend-item"><span class="swatch" style="background:${c}"></span>${esc(b.label)}</span>`;
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
    const tipTxt =
      `有效Token: ${fmtTok(d.billable_tokens)} (输入 ${fmtTok(d.input_tokens)} / 输出 ${fmtTok(d.output_tokens)})\n` +
      `缓存命中: ${fmtTok(d.cache_read_tokens)} · 调用: ${d.calls}次 · 估算 ${fmtUsd(d.est_cost_usd)}`;

    svg += `<g style="cursor:pointer" data-tip-title="${esc(d.label)}" data-tip="${esc(tipTxt)}">`;
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
      svg += `<text x="${lx.toFixed(1)}" y="${H - 7}" text-anchor="middle" fill="var(--muted)" font-size="9.5">${esc(d.label)}</text>`;
    }
  });

  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:210px;display:block">${svg}</svg>`;
  legEl.innerHTML = currentMetric === 'billable_tokens'
    ? `<span class="legend-item"><span class="swatch" style="background:#38bdf8"></span>Gemini Pro / 旗舰</span>
       <span class="legend-item"><span class="swatch" style="background:#a78bfa"></span>Claude / GPT (3P)</span>
       <span class="legend-item"><span class="swatch" style="background:#10b981"></span>Gemini Flash</span>`
    : `<span class="legend-item">当前指标：${esc(document.querySelector('#metric-pills .pill.active')?.textContent || '')}（悬停柱体查看完整明细）</span>`;
}

function renderHeatmapAndPools(data) {
  const rows = data.heatmap_7x24 || [];
  let maxVal = 1;
  rows.forEach(r => r.hours.forEach(h => { if (h.billable_tokens > maxVal) maxVal = h.billable_tokens; }));

  let html = '<table class="heatmap-table"><thead><tr><th></th>';
  for (let h = 0; h < 24; h++) html += `<th>${h % 2 === 0 ? String(h).padStart(2, '0') : ''}</th>`;
  html += '</tr></thead><tbody>';

  rows.forEach(r => {
    html += `<tr><td class="day-lbl">${esc(r.label)}</td>`;
    r.hours.forEach(c => {
      const ratio = c.billable_tokens / maxVal;
      let bg = 'var(--heat-0)';
      if (c.billable_tokens > 0) {
        if (ratio >= 0.72) bg = 'var(--heat-4)';
        else if (ratio >= 0.42) bg = 'var(--heat-3)';
        else if (ratio >= 0.16) bg = 'var(--heat-2)';
        else bg = 'var(--heat-1)';
      }
      const tipTitle = `${r.label} ${String(c.hour).padStart(2,'0')}:00`;
      const tipTxt = `有效Token: ${fmtTok(c.billable_tokens)} · 调用: ${c.calls}次 · 估算 ${fmtUsd(c.est_cost_usd)}`;
      html += `<td><div class="hcell" style="background:${bg}" data-tip-title="${esc(tipTitle)}" data-tip="${esc(tipTxt)}"></div></td>`;
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById('heatmap-box').innerHTML = html;

  document.getElementById('win-badge-pool').textContent = WIN_NAMES[currentWin] || currentWin;
  const pools = data.by_pool || [];
  const totalTok = pools.reduce((s, p) => s + (p.billable_tokens || 0), 0);
  document.getElementById('pool-total-lbl').textContent = `总有效 ${fmtTok(totalTok)}`;

  // Stacked single horizontal bar + compact legend rows
  const barSegs = pools.map(p => `<div style="width:${p.share_billable_pct}%;background:${POOL_COLORS[p.pool]||'#38bdf8'};height:100%" data-tip-title="${esc(p.label)}" data-tip="${esc(`有效: ${fmtTok(p.billable_tokens)} (${p.share_billable_pct}%) · ${p.calls}次 · ${fmtUsd(p.est_cost_usd)}`)}"></div>`).join('');
  const listRows = pools.map(p => `
    <span class="legend-item" style="margin-right:10px;">
      <span class="swatch" style="background:${POOL_COLORS[p.pool]||'#38bdf8'}"></span>
      <span style="color:var(--text)">${esc(p.label.replace(' 系列', '').replace(' 第三方', ''))}</span>
      <strong>${p.share_billable_pct}%</strong>
      <span style="color:var(--muted)">(${fmtTok(p.billable_tokens)})</span>
    </span>
  `).join('');
  document.getElementById('pool-compact-bars').innerHTML = `
    <div style="display:flex;height:7px;border-radius:99px;overflow:hidden;background:var(--track);margin-bottom:7px;">${barSegs}</div>
    <div style="display:flex;flex-wrap:wrap;gap:4px 8px;font-size:11px;">${listRows || '<span style="color:var(--muted)">当前窗口暂无调用</span>'}</div>
  `;
}

function renderDetailPanes(data) {
  renderConvTable();

  document.getElementById('model-tbody').innerHTML = (data.by_model || []).map(m => `
    <tr>
      <td class="mono" style="color:var(--text-strong)">${esc(m.model)}</td>
      <td style="color:var(--muted)">${esc(m.pool_label)}</td>
      <td class="num">${m.calls}</td>
      <td class="num">${fmtTok(m.input_tokens)}</td>
      <td class="num" style="color:var(--muted)">${fmtTok(m.cache_read_tokens)}</td>
      <td class="num">${fmtTok(m.output_tokens)}</td>
      <td class="num" style="color:var(--green)">${m.cache_hit_pct}%</td>
      <td class="num">${fmtUsd(m.est_cost_usd)}</td>
    </tr>
  `).join('') || '<tr><td colspan="8" style="color:var(--muted);text-align:center">暂无数据</td></tr>';

  document.getElementById('project-list').innerHTML = (data.projects || []).slice(0, 8).map(p => `
    <div style="margin-bottom:8px;">
      <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">
        <span class="mono">${esc(p.workspace)}</span>
        <span><strong style="font-weight:600">${fmtTok(p.billable_tokens)}</strong> <span style="color:var(--muted)">(${p.share_billable_pct}% · ${p.calls}次)</span></span>
      </div>
      <div class="bar-track"><div class="bar-fill" style="width:${p.share_billable_pct}%;background:#3b82f6"></div></div>
    </div>
  `).join('') || '<div style="color:var(--muted)">暂无数据</div>';

  const tools = data.top_tools || [];
  const maxTool = Math.max(1, ...tools.map(t => t.count));
  document.getElementById('tools-list').innerHTML = tools.slice(0, 8).map(t => `
    <div style="display:grid;grid-template-columns:120px 1fr 68px;gap:8px;align-items:center;margin-bottom:6px;font-size:11px;">
      <span class="mono ellipsis">${esc(t.name)}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${(t.count/maxTool*100).toFixed(1)}%;background:#a78bfa"></div></div>
      <span class="num" style="color:var(--muted)">${t.count} (${t.share_pct}%)</span>
    </div>
  `).join('') || '<div style="color:var(--muted)">暂无工具调用</div>';

  document.getElementById('recent-tbody').innerHTML = (data.recent_calls || []).slice(0, 18).map(r => {
    const tns = r.tool_names || [];
    const toolHtml = tns.length ? `<span class="tool-pill">${esc(tns[0])}${tns.length > 1 ? ' +' + (tns.length - 1) : ''}</span>` : '';
    return `
      <tr class="clickable" data-session="${esc(r.conversation_id)}">
        <td class="mono" style="color:var(--muted);white-space:nowrap">${esc(r.ts_cst.slice(6))}</td>
        <td>
          <div class="mono" style="color:${POOL_COLORS[r.pool]||'var(--cyan)'}">${esc(r.model)}${toolHtml}</div>
          <div class="ellipsis" style="font-size:10.5px;color:var(--muted)">${esc(r.title)}</div>
        </td>
        <td class="num">${fmtTok(r.input_tokens)}</td>
        <td class="num" style="color:var(--muted)">${fmtTok(r.cache_read_tokens)}</td>
        <td class="num">${fmtTok(r.output_tokens)}</td>
      </tr>
    `;
  }).join('') || '<tr><td colspan="5" style="color:var(--muted);text-align:center">暂无调用</td></tr>';
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
        <div class="ellipsis" style="font-weight:600;color:var(--text-strong);max-width:250px">${esc(c.title)}${c.is_subagent ? '<span class="tag">子代理</span>' : ''}</div>
        <div class="mono" style="color:var(--muted);font-size:10px">${esc(c.short_id)} · ${esc(c.last_ts_cst)}</div>
      </td>
      <td class="mono ellipsis" style="color:var(--muted);max-width:120px">${esc(c.workspace)}</td>
      <td class="num">${c.calls}</td>
      <td class="num" style="font-weight:600;color:var(--text-strong)">${fmtTok(c.billable_tokens)}</td>
      <td class="num" style="color:var(--muted)">${fmtTok(c.peak_context)}</td>
      <td class="num" style="color:var(--green)">${c.cache_hit_pct}%</td>
      <td class="num">${fmtUsd(c.est_cost_usd)}</td>
    </tr>
  `).join('') || '<tr><td colspan="7" style="color:var(--muted);text-align:center">未匹配到会话</td></tr>';
}

async function openSession(cid) {
  if (!cid) return;
  document.getElementById('backdrop').classList.add('open');
  document.getElementById('session-drawer').classList.add('open');
  document.getElementById('dr-title').textContent = '加载会话详情...';
  document.getElementById('dr-sub').textContent = cid;
  document.getElementById('dr-body').innerHTML = '<div style="color:var(--muted)">读取中...</div>';

  try {
    const res = await fetch('/api/session/' + encodeURIComponent(cid), { cache: 'no-store' });
    const d = await res.json();
    const s = d.summary || {};
    document.getElementById('dr-title').textContent = d.title + (d.is_subagent ? ' [子代理]' : '');
    document.getElementById('dr-sub').textContent = `${d.short_id} · 工作区 ${d.workspace} · ${s.calls} 轮调用`;

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
        <div class="card kpi-card"><div class="card-sub">有效 Token</div><div style="font-size:14px;font-weight:650;color:var(--cyan);margin-top:2px">${fmtTok(s.billable_tokens)}</div></div>
        <div class="card kpi-card"><div class="card-sub">峰值上下文</div><div style="font-size:14px;font-weight:650;color:var(--purple);margin-top:2px">${fmtTok(d.peak_context)}</div></div>
        <div class="card kpi-card"><div class="card-sub">缓存命中率</div><div style="font-size:14px;font-weight:650;color:var(--green);margin-top:2px">${s.cache_hit_pct}%</div></div>
        <div class="card kpi-card"><div class="card-sub">估算 / 省额</div><div style="font-size:13px;font-weight:650;margin-top:2px">${fmtUsd(s.est_cost_usd)} / <span style="color:var(--green)">${fmtUsd(s.cache_saved_usd)}</span></div></div>
      </div>

      <div style="font-size:11.5px;font-weight:600;margin-bottom:5px;color:var(--text-strong)">上下文窗口膨胀曲线</div>
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:135px;background:var(--chip-bg);border-radius:8px;border:1px solid var(--border);margin-bottom:12px;">
        <polygon points="${areaPts}" fill="rgba(56,189,248,0.14)" />
        <polyline points="${pts.join(' ')}" fill="none" stroke="#38bdf8" stroke-width="2" />
        <text x="6" y="16" fill="var(--muted)" font-size="9.5">${fmtTok(maxCtx)}</text>
        <text x="6" y="${H - 6}" fill="var(--muted)" font-size="9.5">0</text>
        <text x="${W - 8}" y="${H - 6}" text-anchor="end" fill="var(--muted)" font-size="9.5">共 ${turns.length} 轮</text>
      </svg>

      ${(d.tools || []).length ? `<div style="margin-bottom:12px;">
        <div style="font-size:11.5px;font-weight:600;margin-bottom:5px;color:var(--text-strong)">工具调用统计</div>
        <div>${d.tools.map(t => `<span class="tool-pill">${esc(t.name)} ×${t.count}</span>`).join(' ')}</div>
      </div>` : ''}

      <div style="font-size:11.5px;font-weight:600;margin-bottom:5px;color:var(--text-strong)">逐轮记录（最新在前）</div>
      <table>
        <thead><tr><th>#</th><th>时间</th><th>模型</th><th class="num">上下文</th><th class="num">新增</th><th class="num">输出</th></tr></thead>
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
    document.getElementById('dr-body').innerHTML = `<div style="color:var(--red)">加载失败: ${esc(e)}</div>`;
  }
}

function closeOverlays() {
  document.getElementById('backdrop').classList.remove('open');
  document.getElementById('session-drawer').classList.remove('open');
  document.getElementById('quota-modal').classList.remove('open');
}

async function refresh() {
  try {
    const res = await fetch('/api/stats?window=' + encodeURIComponent(currentWin), { cache: 'no-store' });
    const data = await res.json();
    lastData = data;
    document.getElementById('subtitle').textContent = `同步于 ${data.generated_at_cst} · 统计窗口：${WIN_NAMES[currentWin] || currentWin}`;
    const tzLbl = data.timezone_label || 'UTC+8';
    const tzEl = document.getElementById('tz-lbl');
    if (tzEl) tzEl.textContent = tzLbl;
    const mTzEl = document.getElementById('modal-tz-lbl');
    if (mTzEl) mTzEl.textContent = tzLbl;
    const nOn = !!(data.notifications && data.notifications.enabled);
    const nBtn = document.getElementById('notify-btn');
    if (nBtn) {
      nBtn.textContent = nOn ? '🔔 提醒: 开' : '🔔 提醒: 关';
      nBtn.classList.toggle('live-on', nOn);
    }
    renderBanner(data);
    renderInsights(data);
    renderQuota(data);
    renderKPIs(data);
    renderMainChart(data);
    renderHeatmapAndPools(data);
    renderDetailPanes(data);
  } catch (err) {
    document.getElementById('subtitle').textContent = '同步中断: ' + err;
  }
}

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
  b.innerHTML = liveEnabled ? '<span class="dot ok"></span>实时 3s' : '<span class="dot"></span>已暂停';
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

document.getElementById('theme-btn').addEventListener('click', () => {
  const cur = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('agy-usage-theme', next);
  document.getElementById('theme-btn').textContent = next === 'dark' ? '☀ 亮色' : '☾ 暗色';
});

document.getElementById('mq-save-btn').addEventListener('click', async () => {
  const bucket = document.getElementById('mq-bucket').value;
  const used = parseFloat(document.getElementById('mq-used').value);
  const reset = document.getElementById('mq-reset').value.trim();
  const msg = document.getElementById('mq-msg');
  if (isNaN(used) || used < 0 || used > 100) {
    msg.textContent = '请输入 0~100 之间的已使用百分比';
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
      msg.textContent = out.error || '保存失败';
      return;
    }
    closeOverlays();
    refresh();
  } catch (e) {
    msg.textContent = '请求失败: ' + e;
  }
});

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeOverlays(); });

refresh();
pollTimer = setInterval(refresh, 3000);
</script>
</body>
</html>
"""
