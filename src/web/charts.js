// ==================== Dashboard Component Renderers (Quota, KPIs, SVG Charts, Heatmap & Tables) ====================

function stripHtmlTags(s) {
  return String(s == null ? '' : s).replace(/<\/?[a-zA-Z0-9]+>/g, '');
}

function renderBanner(data) {
  const ls = data.live_session || {};
  const q = data.quota || {};
  const sel = data.selected_summary || {};
  const ctx = ls.context_window;

  const planSlot = document.getElementById('plan-badge-slot');
  if (planSlot) {
    planSlot.innerHTML = (ls.plan_tier && ls.plan_tier !== '-')
      ? `<span class="badge">${esc(ls.plan_tier)}</span>`
      : '';
  }

  // Upgrade Header Share CTA with live magnetic achievement hook
  const shareLbl = document.getElementById('hdr-share-lbl');
  if (shareLbl) {
    const cleanBtnTxt = String(tr('sc_btn')).replace(/^📸\s*/, '');
    if ((sel.total_tokens || 0) > 0) {
      const saveBit = (sel.cache_saved_usd || 0) >= 1 ? ` · ${fmtUsd(sel.cache_saved_usd)}` : '';
      shareLbl.innerHTML = `<span class="fire-stat-hl">${esc(fmtTok(sel.total_tokens))}${esc(saveBit)}</span> ▸ ${esc(cleanBtnTxt)}`;
    } else {
      shareLbl.textContent = cleanBtnTxt;
    }
  }

  let ctxHtml = `<span class="v" style="color:var(--muted)">—</span>`;
  if (ctx && ctx.used_percentage != null) {
    const u = Number(ctx.used_percentage);
    const col = u >= 80 ? 'var(--red)' : (u >= 55 ? 'var(--yellow)' : 'var(--gem-accent)');
    ctxHtml = `<span class="v" style="color:${col}">${u.toFixed(1)}%</span> <span style="color:var(--muted)">(${fmtTok((ctx.total_input_tokens||0)+(ctx.total_output_tokens||0))}/${fmtTok(ctx.context_window_size||0)})</span>`;
  }

  const slBadge = ls.connected
    ? `<span class="dot ok"></span><span>${esc(tr('st_connected'))}</span>`
    : (ls.statusline_configured
        ? `<span class="dot warn"></span><span>${esc(tr('st_wait_push'))}</span>`
        : `<span class="dot err"></span><span>${esc(tr('st_not_linked'))}</span>`);

  const slCmd = '/statusline ' + (ls.statusline_path || 'statusline.py');
  const slDisp = '/statusline ' + (ls.statusline_display_path || ls.statusline_path || 'statusline.py');
  const syncClock = String(data.generated_at_cst || '').replace(/^\d{4}-\d{2}-\d{2}\s+/, '');

  const items = [
    `<div class="kv"><span class="v" style="display:inline-flex;align-items:center;gap:5px">${slBadge}</span></div>`,
    `<div class="kv"><span class="k">${esc(tr('st_model'))}</span><span class="v" style="color:var(--gem-accent)">${esc(ls.active_model)}</span></div>`,
  ];
  if (ls.configured_planner && ls.configured_planner !== '-') {
    items.push(`<div class="kv"><span class="k">Planner</span><span class="v" style="color:var(--cld-accent)">${esc(ls.configured_planner)}</span></div>`);
  }
  items.push(`<div class="kv"><span class="k">${esc(tr('st_ctx'))}</span>${ctxHtml}</div>`);
  if (syncClock) {
    items.push(`<div class="kv"><span class="k" style="font-variant-numeric:tabular-nums">${esc(syncClock)}</span></div>`);
  }

  document.getElementById('live-banner').innerHTML = `
    <div class="tbar-items">${items.join('<span class="tbar-sep"></span>')}</div>
    ${!q.has_live_quota ? `<div><span class="code-chip" title="${esc(tr('click_copy'))}" data-copy="${esc(slCmd)}">${esc(slDisp)}</span></div>` : ''}
  `;
}

function renderQuota(data) {
  const q = data.quota || {};
  const ls = data.live_session || {};
  const el = document.getElementById('quota-section');

  if (!q.has_live_quota) {
    const slCmd = '/statusline ' + (ls.statusline_path || 'statusline.py');
    const slDisp = '/statusline ' + (ls.statusline_display_path || ls.statusline_path || 'statusline.py');
    el.innerHTML = `
      <div class="card onboarding" style="margin-bottom:14px;">
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
    const r = 23.5, circ = 2 * Math.PI * r;
    const dash = Math.max(used > 0 ? 2 : 0, circ * (used / 100));
    const usedDisp = (used > 0 && used < 10) ? used.toFixed(2) : used.toFixed(1);
    const remDisp = (used > 0 && used < 10) ? rem.toFixed(2) : rem.toFixed(1);

    let badge = `<span class="badge ok">${esc(tr('b_ok'))}</span>`;
    if (b.status === 'reset_ready') badge = `<span class="badge">${esc(tr('b_ready'))}</span>`;
    else if (b.status === 'critical') badge = `<span class="badge crit">${esc(tr('b_crit'))}</span>`;
    else if (b.status === 'warning') badge = `<span class="badge warn">${esc(tr('b_warn'))}</span>`;

    const resetEpoch = (!b.reset_passed && b.reset_time) ? new Date(b.reset_time).getTime() : 0;
    const winTitle = b.window_kind === 'five_hour' ? tr('win_5h') : (b.window_kind === 'weekly' ? tr('win_7d') : tr('win_other'));
    const remCountdown = b.reset_in_seconds != null ? fmtCountdown(b.reset_in_seconds) : '';

    const budgetBit = stripHtmlTags(
      b.reset_passed
        ? tr('next_call_refresh')
        : (b.window_kind === 'weekly' && b.daily_safe_budget_pct != null
            ? tr('daily_avail', b.daily_safe_budget_pct)
            : (b.hourly_safe_budget_pct != null ? tr('hourly_avail', b.hourly_safe_budget_pct) : ''))
    );
    const ratioBit = (!b.reset_passed && b.pacing_ratio != null) ? stripHtmlTags(tr('pace_val', b.pacing_ratio)) : '';
    const exhTxt = b.projected_exhaust_hours != null ? fmtCountdown(b.projected_exhaust_hours * 3600) : '-';
    const forecastTxt = (!b.reset_passed && b.projected_rem_at_reset != null)
      ? stripHtmlTags(b.projected_rem_at_reset <= 0.1 ? tr('est_exhaust', exhTxt) : tr('est_rem_reset', b.projected_rem_at_reset.toFixed(1)))
      : '';
    const tokTxt = b.tokens_per_1pct ? `1% ≈ ${fmtTok(b.tokens_per_1pct)} tok` : '';

    const bDisp = bucketDisplayLabel(b);
    const tipLines = [
      stripHtmlTags(tr('dual_tip', usedDisp, (b.time_elapsed_pct || 0).toFixed(1), b.reset_time_cst, data.timezone_label || 'UTC+8')),
      forecastTxt,
      tokTxt,
    ].filter(Boolean).join('\n');

    const leftReset = (b.reset_time_cst && b.reset_time_cst !== '-')
      ? esc(stripHtmlTags(tr('reset_at', b.reset_time_cst)))
      : '—';
    const rightMeta = (!b.reset_passed && b.projected_rem_at_reset != null && b.projected_rem_at_reset <= 0.1)
      ? `<span style="color:var(--red);font-weight:550">${esc(forecastTxt)}</span>`
      : esc([ratioBit, budgetBit].filter(Boolean).join(' · '));

    return `
      <div class="bucket-item" data-tip-title="${esc(bDisp)}" data-tip="${esc(tipLines)}">
        <div class="mini-ring">
          <svg width="58" height="58" viewBox="0 0 58 58">
            <circle cx="29" cy="29" r="${r}" fill="none" stroke="var(--track)" stroke-width="5" />
            <circle cx="29" cy="29" r="${r}" fill="none" stroke="${col}" stroke-width="5"
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
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
              <span class="b-name">${esc(winTitle)}</span>
              <span class="b-rem">${esc(tr('rem_val', remDisp))}</span>
              ${badge}
            </div>
            <span class="b-countdown" ${resetEpoch ? `data-reset-ts="${resetEpoch}"` : ''}>${b.reset_passed ? esc(tr('expired_wait')) : (remCountdown ? esc(tr('rem_time', remCountdown)) : '')}</span>
          </div>
          <div class="dual-bar">
            <div class="dual-fill" style="width:${used}%;background:${col}"></div>
            ${b.time_elapsed_pct != null ? `<div class="time-marker" style="left:${Math.min(99, b.time_elapsed_pct)}%"></div>` : ''}
          </div>
          <div class="b-meta">
            <span>${leftReset}</span>
            <span>${rightMeta}</span>
          </div>
        </div>
      </div>
    `;
  }

  const pools = [
    { key: 'gemini', cls: 'pool-gemini', dot: 'var(--gem-accent)', title: tr('pool_gem_t'), tag: '5h · 7d', items: q.buckets.filter(b => (b.pool_key || '').startsWith('gemini')) },
    { key: 'claude', cls: 'pool-claude', dot: 'var(--cld-accent)', title: tr('pool_cld_t'), tag: '5h · 7d', items: q.buckets.filter(b => b.pool_key === 'claude_gpt') },
    { key: 'other', cls: '', dot: '#64748b', title: tr('pool_oth_t'), tag: '', items: q.buckets.filter(b => !(b.pool_key || '').startsWith('gemini') && b.pool_key !== 'claude_gpt') },
  ].filter(g => g.items.length > 0);

  el.innerHTML = `<div class="grid ${pools.length >= 2 ? 'grid-2' : ''}">` + pools.map(g => `
    <div class="card ${g.cls}">
      <div class="card-head">
        <span class="card-title"><span class="swatch" style="background:${g.dot}"></span>${esc(g.title)}</span>
        ${g.tag ? `<span class="badge muted">${esc(g.tag)}</span>` : ''}
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
      <div class="kpi-top"><span class="card-sub">${esc(tr('kpi_5h_t'))}</span><span class="badge">${esc(tr('kpi_burn', fmtTok(b5.billable_tokens_per_hour||0)))}</span></div>
      <div class="kpi-val" style="color:var(--gem-accent)">${fmtTok(w5.billable_tokens)}</div>
      <div class="kpi-sub">${esc(tr('kpi_io', fmtTok(w5.input_tokens), fmtTok(w5.output_tokens)))}</div>
      <div class="kpi-foot"><span>${esc(tr('kpi_calls_rate', w5.calls || 0, b5.calls_per_hour || 0))}</span><span>${esc(tr('kpi_est', fmtUsd(w5.est_cost_usd)))}</span></div>
    </div>
    <div class="card kpi-card">
      <div class="kpi-top"><span class="card-sub">${esc(tr('kpi_today_t'))}</span><span class="badge ok">${esc(tr('w_today'))}</span></div>
      <div class="kpi-val">${fmtTok(wt.billable_tokens)}</div>
      <div class="kpi-sub">${esc(tr('kpi_io', fmtTok(wt.input_tokens), fmtTok(wt.output_tokens)))}</div>
      <div class="kpi-foot"><span>${esc(tr('kpi_calls_tools', wt.calls || 0, wt.tool_calls || 0))}</span><span>${esc(tr('kpi_est', fmtUsd(wt.est_cost_usd)))}</span></div>
    </div>
    <div class="card kpi-card">
      <div class="kpi-top"><span class="card-sub">${esc(tr('kpi_7d_t'))}</span>${wowBadge}</div>
      <div class="kpi-val" style="color:var(--cld-accent)">${fmtTok(w7.billable_tokens)}</div>
      <div class="kpi-sub">${esc(tr('kpi_total_thru', fmtTok(w7.total_tokens)))}</div>
      <div class="kpi-foot"><span>${esc(tr('kpi_calls_convs', w7.calls || 0, w7.conversations || 0))}</span><span>${esc(tr('kpi_est', fmtUsd(w7.est_cost_usd)))}</span></div>
    </div>
    <div class="card kpi-card">
      <div class="kpi-top"><span class="card-sub">${esc(tr('kpi_cache_t', winName(currentWin)))}</span><span class="badge ok">${esc(tr('kpi_hit', wsel.cache_hit_pct||0))}</span></div>
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
      box.innerHTML = `<div style="height:212px;display:grid;place-items:center;color:var(--muted);">${esc(tr('quota_empty'))}</div>`;
      legEl.innerHTML = '';
      return;
    }
    const colors = ['#38bdf8', '#a78bfa', '#10b981', '#f59e0b'];
    const W = 680, H = 212, padL = 42, padR = 14, padT = 12, padB = 24;
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
      if (coords.length >= 2) {
        const area = `${coords[0].x.toFixed(1)},${H - padB} ` + coords.map(o => `${o.x.toFixed(1)},${o.y.toFixed(1)}`).join(' ') + ` ${coords[coords.length - 1].x.toFixed(1)},${H - padB}`;
        paths += `<polygon points="${area}" fill="${c}" fill-opacity="0.08" />`;
      }
      paths += `<polyline fill="none" stroke="${c}" stroke-width="2" stroke-linejoin="round" points="${coords.map(o => `${o.x.toFixed(1)},${o.y.toFixed(1)}`).join(' ')}" />`;
      coords.forEach(o => {
        const tipTitle = `${bDisp} · ${o.p.ts_cst}`;
        const tipTxt = tr('q_tip', o.p.used_pct, o.p.remaining_pct);
        paths += `<circle cx="${o.x.toFixed(1)}" cy="${o.y.toFixed(1)}" r="3" fill="${c}" style="cursor:pointer" data-tip-title="${esc(tipTitle)}" data-tip="${esc(tipTxt)}" />`;
      });
      leg += `<span class="legend-item"><span class="swatch" style="background:${c}"></span>${esc(bDisp)}</span>`;
    });
    box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:212px;display:block">${grid}${paths}</svg>`;
    legEl.innerHTML = leg;
    return;
  }

  metricWrap.style.visibility = 'visible';
  const items = currentChartTab === '5h' ? (data.rolling_5h_10m || [])
              : currentChartTab === '24h' ? (data.hourly_24h || [])
              : (data.daily_7d || []);
  const W = 680, H = 212, padL = 46, padR = 14, padT = 12, padB = 26;
  const vals = items.map(d => Number(d[currentMetric] || 0));
  const maxVal = Math.max(0.0001, ...vals);
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const step = plotW / Math.max(1, items.length);
  const barW = Math.max(5, step * (currentChartTab === '7d' ? 0.46 : 0.64));

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
        svg += `<rect x="${x.toFixed(1)}" y="${curY.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" rx="2.5" fill="${s.color}" />`;
      }
    } else if (totalV > 0) {
      const h = Math.max(2, (totalV / maxVal) * plotH);
      const col = currentMetric === 'est_cost_usd' ? '#f59e0b' : (currentMetric === 'calls' ? '#3b82f6' : '#38bdf8');
      svg += `<rect x="${x.toFixed(1)}" y="${(padT + plotH - h).toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" rx="3" fill="${col}" />`;
    }
    svg += `</g>`;

    const showLbl = currentChartTab === '7d' ? true : (idx === items.length - 1 || (idx % 4 === 0 && idx < items.length - 2));
    if (showLbl) {
      const lx = padL + idx * step + step / 2;
      svg += `<text x="${lx.toFixed(1)}" y="${H - 7}" text-anchor="middle" fill="var(--muted)" font-size="9.5">${esc(dispLbl)}</text>`;
    }
  });

  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:212px;display:block">${svg}</svg>`;
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

  let html = '<table class="heatmap-table"><thead><tr><th class="day-col"></th>';
  for (let h = 0; h < 24; h++) html += `<th>${h % 3 === 0 ? String(h).padStart(2, '0') : ''}</th>`;
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
          <div class="mono" style="color:${POOL_COLORS[r.pool]||'var(--gem-accent)'}">${esc(r.model)}${toolHtml}</div>
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
        <div class="ellipsis" style="font-weight:600;color:var(--text-strong);max-width:255px">${esc(fmtTitle(c.title))}${c.is_subagent ? `<span class="tag">${esc(tr('subagent_tag'))}</span>` : ''}<span class="row-chevron">›</span></div>
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
