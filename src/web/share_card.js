// ==================== Flagship Bento + Leica-Frame Share Card Renderer (2x Retina Canvas) ====================
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
  const W = 780, H = 524;
  cv.width = W * S;
  cv.height = H * S;
  ctx.save();
  ctx.scale(S, S);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';

  const showUsd = document.getElementById('sc-usd-chk').checked;
  const wins = lastData.windows || {};
  const wObj = wins[scWin] || lastData.selected_summary || {};
  const q = lastData.quota || {};
  const buckets = q.buckets || [];
  const ls = lastData.live_session || {};
  const wow = lastData.week_over_week || {};
  const hmRows = lastData.heatmap_7x24 || [];

  const PALS = {
    tongtou: {
      bg0: '#F8F4EF', bg1: '#EDE5DC', glowA: 'rgba(123,167,167,0.28)', glowB: 'rgba(196,168,130,0.25)',
      dotGrid: 'rgba(77,124,124,0.10)',
      border: '#D8CFC4', text: '#243442', muted: '#6E6963',
      card: 'rgba(255,253,251,0.90)', cardBd: '#E3DBD1', cardSub: 'rgba(255,253,251,0.78)',
      badgeBg: 'rgba(77,124,124,0.13)', badgeBd: 'rgba(77,124,124,0.32)', badgeFg: '#2F5C5C',
      pillBg: 'rgba(5,150,105,0.12)', pillBd: 'rgba(5,150,105,0.28)', pillFg: '#047857',
      gem: '#4D7C7C', cld: '#9A7B4F', track: '#E6DFD6', ok: '#059669', warn: '#D97706', crit: '#DC2626',
      heat: ['#EAE3DA', '#C6D6D6', '#7BA7A7', '#C4A882', '#2C3E50'],
      footBg: '#FFFDFB', footBd: '#E4DDD4', urlBg: '#F1EBE3', urlFg: '#356262',
    },
    light: {
      bg0: '#FFF9FC', bg1: '#F2EAFF', glowA: 'rgba(244,114,182,0.28)', glowB: 'rgba(167,139,250,0.26)',
      dotGrid: 'rgba(219,39,119,0.09)',
      border: '#F9A8D4', text: '#321D29', muted: '#745664',
      card: 'rgba(255,255,255,0.86)', cardBd: '#FBCFE8', cardSub: 'rgba(255,255,255,0.74)',
      badgeBg: 'rgba(219,39,119,0.11)', badgeBd: 'rgba(219,39,119,0.28)', badgeFg: '#BE185D',
      pillBg: 'rgba(124,58,237,0.11)', pillBd: 'rgba(124,58,237,0.26)', pillFg: '#6D28D9',
      gem: '#0E7490', cld: '#6D28D9', track: '#FCE7F3', ok: '#059669', warn: '#D97706', crit: '#DC2626',
      heat: ['#FCE7F3', '#FBCFE8', '#F472B6', '#E879F9', '#8B5CF6'],
      footBg: '#FFFFFF', footBd: '#FBCFE8', urlBg: '#FDF2F8', urlFg: '#9D174D',
    },
    dark: {
      bg0: '#162033', bg1: '#0B1120', glowA: 'rgba(56,189,248,0.22)', glowB: 'rgba(167,139,250,0.22)',
      dotGrid: 'rgba(148,163,184,0.11)',
      border: '#334155', text: '#F8FAFC', muted: '#94A3B8',
      card: 'rgba(30,41,59,0.88)', cardBd: 'rgba(148,163,184,0.22)', cardSub: 'rgba(15,23,42,0.68)',
      badgeBg: 'rgba(56,189,248,0.14)', badgeBd: 'rgba(56,189,248,0.34)', badgeFg: '#38BDF8',
      pillBg: 'rgba(16,185,129,0.15)', pillBd: 'rgba(52,211,153,0.32)', pillFg: '#34D399',
      gem: '#38BDF8', cld: '#C084FC', track: '#334155', ok: '#34D399', warn: '#FBBF24', crit: '#F87171',
      heat: ['#1E293B', '#164E63', '#0284C7', '#38BDF8', '#A78BFA'],
      footBg: '#090F1D', footBd: '#1E293B', urlBg: '#1E293B', urlFg: '#38BDF8',
    },
  };
  const P = PALS[scTheme] || PALS.tongtou;
  const ff = '-apple-system, BlinkMacSystemFont, "Inter", "SF Pro Display", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei UI", sans-serif';
  const mono = 'ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, Consolas, monospace';

  // 1. Canvas Clip + Rich Aurora Atmosphere + Subtle Precision Dot Matrix
  scRoundRect(ctx, 0, 0, W, H, 24);
  ctx.clip();
  const bgG = ctx.createLinearGradient(0, 0, W, H);
  bgG.addColorStop(0, P.bg0);
  bgG.addColorStop(1, P.bg1);
  ctx.fillStyle = bgG;
  ctx.fillRect(0, 0, W, H);

  const g1 = ctx.createRadialGradient(110, 24, 12, 110, 24, 380);
  g1.addColorStop(0, P.glowA); g1.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g1; ctx.fillRect(0, 0, W, H);

  const g2 = ctx.createRadialGradient(W - 90, 70, 12, W - 90, 70, 350);
  g2.addColorStop(0, P.glowB); g2.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g2; ctx.fillRect(0, 0, W, H);

  ctx.fillStyle = P.dotGrid;
  for (let gx = W - 260; gx < W - 24; gx += 14) {
    for (let gy = 22; gy < 156; gy += 14) {
      ctx.beginPath();
      ctx.arc(gx, gy, 1.15, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // 2. Top Row: Bordered Achievement Medal Pill + Tier/Window Capsule
  const gemW = buckets.find(b => String(b.pool_key || '').startsWith('gemini') && b.window_kind === 'weekly') || buckets[0];
  const cldW = buckets.find(b => b.pool_key === 'claude_gpt' && b.window_kind === 'weekly') || buckets[1];
  const totTok = Number(wObj.total_tokens || 0);
  const hitPct = Number(wObj.cache_hit_pct || 0);
  let rankTxt = tr('sc_rank_zen');
  if (buckets.some(b => b.used_pct != null && b.used_pct >= 80 && !b.reset_passed)) rankTxt = tr('sc_rank_edge');
  else if (totTok >= 1e8 && hitPct >= 85) rankTxt = tr('sc_rank_save');
  else if ((gemW && gemW.used_pct != null && gemW.used_pct <= 5) || (cldW && cldW.used_pct != null && cldW.used_pct <= 5)) rankTxt = tr('sc_rank_reset');
  else if (totTok >= 3e7) rankTxt = tr('sc_rank_power');

  ctx.font = '700 13px ' + ff;
  const bw = ctx.measureText(rankTxt).width + 28;
  scRoundRect(ctx, 32, 26, bw, 31, 15.5);
  ctx.fillStyle = P.badgeBg; ctx.fill();
  ctx.strokeStyle = P.badgeBd; ctx.lineWidth = 1; ctx.stroke();
  ctx.fillStyle = P.badgeFg; ctx.fillText(rankTxt, 46, 46);

  const tierBit = (ls.plan_tier && ls.plan_tier !== '-') ? (' · ' + ls.plan_tier) : '';
  const dateStr = tr('sc_win_lbl', winName(scWin)) + tierBit;
  ctx.font = '600 12px ' + ff;
  const dw = ctx.measureText(dateStr).width + 22;
  scRoundRect(ctx, W - 32 - dw, 27, dw, 29, 14.5);
  ctx.fillStyle = P.cardSub; ctx.fill();
  ctx.strokeStyle = P.cardBd; ctx.lineWidth = 1; ctx.stroke();
  ctx.fillStyle = P.muted;
  ctx.textAlign = 'right';
  ctx.fillText(dateStr, W - 32 - 11, 46);
  ctx.textAlign = 'left';

  // 3. Hero Spotlight: Massive Tabular Token Figure + High-Contrast Savings Pill
  ctx.font = '600 12.5px ' + ff;
  ctx.fillStyle = P.muted;
  ctx.fillText(tr('sc_kicker'), 32, 82);

  const tokStr = fmtTok(totTok);
  ctx.font = '800 56px ' + ff;
  ctx.fillStyle = P.text;
  ctx.fillText(tokStr, 32, 139);
  const tokW = ctx.measureText(tokStr).width;

  const pillStr = showUsd
    ? tr('sc_save_pill', hitPct.toFixed(1), fmtUsd(wObj.cache_saved_usd || 0))
    : tr('sc_hit_pill', hitPct.toFixed(1));
  ctx.font = '700 14px ' + ff;
  const pw = ctx.measureText(pillStr).width + 26;
  const px = Math.min(W - pw - 32, 32 + tokW + 18);
  scRoundRect(ctx, px, 106, pw, 34, 10);
  ctx.fillStyle = P.pillBg; ctx.fill();
  ctx.strokeStyle = P.pillBd; ctx.lineWidth = 1; ctx.stroke();
  ctx.fillStyle = P.pillFg; ctx.fillText(pillStr, px + 13, 128);

  // 4. Dual Pool Bento Cards with Radial Gauge Rings + Progress Bars
  function drawPoolBox(bx, by, boxW, boxH, title, accentCol, bkt) {
    scRoundRect(ctx, bx, by, boxW, boxH, 16);
    ctx.fillStyle = P.card; ctx.fill();
    ctx.strokeStyle = P.cardBd; ctx.lineWidth = 1; ctx.stroke();

    // Top 2.5px pool accent line inside card
    ctx.save();
    scRoundRect(ctx, bx, by, boxW, boxH, 16);
    ctx.clip();
    ctx.fillStyle = accentCol;
    ctx.fillRect(bx, by, boxW, 3);
    ctx.restore();

    const hasU = bkt && bkt.used_pct != null;
    const u = hasU ? Number(bkt.used_pct) : 0;
    const exp = !!(bkt && bkt.reset_passed);
    const vCol = !hasU ? P.muted : (exp ? P.gem : (u >= 80 ? P.crit : (u >= 55 ? P.warn : P.ok)));
    const stWord = !hasU ? tr('st_pending') : (exp ? tr('b_ready') : (u >= 80 ? tr('b_crit') : (u >= 55 ? tr('b_warn') : tr('b_ok'))));

    // Radial Gauge Ring on Left
    const rcx = bx + 42, rcy = by + 56, rr = 24;
    ctx.beginPath();
    ctx.arc(rcx, rcy, rr, 0, Math.PI * 2);
    ctx.strokeStyle = P.track;
    ctx.lineWidth = 5.5;
    ctx.stroke();

    if (hasU && u > 0) {
      const sweep = Math.max(0.12, (Math.min(100, u) / 100) * Math.PI * 2);
      ctx.beginPath();
      ctx.arc(rcx, rcy, rr, -Math.PI / 2, -Math.PI / 2 + sweep);
      ctx.strokeStyle = vCol;
      ctx.lineWidth = 5.5;
      ctx.lineCap = 'round';
      ctx.stroke();
      ctx.lineCap = 'butt';
    }

    ctx.textAlign = 'center';
    ctx.font = '800 11.5px ' + ff;
    ctx.fillStyle = vCol;
    ctx.fillText(hasU ? (u < 10 && u > 0 ? u.toFixed(1) : Math.round(u)) + '%' : '—', rcx, rcy + 4);
    ctx.textAlign = 'left';

    const contentX = bx + 80;
    const contentW = boxW - 98;

    ctx.font = '700 13px ' + ff;
    ctx.fillStyle = accentCol;
    ctx.fillText(title, contentX, by + 30);

    ctx.textAlign = 'right';
    ctx.font = '700 11.5px ' + ff;
    ctx.fillStyle = vCol;
    ctx.fillText(stWord, bx + boxW - 18, by + 30);
    ctx.textAlign = 'left';

    const valMain = hasU ? (tr('used_lbl') + ' ' + u.toFixed(1) + '%') : '—';
    ctx.font = '800 22px ' + ff;
    ctx.fillStyle = P.text;
    ctx.fillText(valMain, contentX, by + 62);

    const rstSub = !hasU ? '' : (exp ? tr('expired_wait') : (bkt.reset_in_seconds != null ? tr('rem_time', fmtCountdown(bkt.reset_in_seconds)) : (bkt.reset_time_cst && bkt.reset_time_cst !== '-' ? bkt.reset_time_cst : '')));
    ctx.textAlign = 'right';
    ctx.font = '600 11px ' + ff;
    ctx.fillStyle = P.muted;
    ctx.fillText(rstSub, bx + boxW - 18, by + 61);
    ctx.textAlign = 'left';

    scRoundRect(ctx, contentX, by + 77, contentW, 7.5, 3.75);
    ctx.fillStyle = P.track; ctx.fill();
    if (hasU && u > 0) {
      const fw = Math.max(7.5, Math.min(contentW, (contentW * u) / 100));
      scRoundRect(ctx, contentX, by + 77, fw, 7.5, 3.75);
      ctx.fillStyle = vCol; ctx.fill();
    }
  }

  const boxW = (W - 64 - 16) / 2;
  drawPoolBox(32, 160, boxW, 108, tr('sc_gem_lbl'), P.gem, gemW);
  drawPoolBox(32 + boxW + 16, 160, boxW, 108, tr('sc_cld_lbl'), P.cld, cldW);

  // 5. Lower Bento Row: 3 Proportioned Stat Tiles + Live 7x24 Mini Activity Heatmap Signature
  const bentoY = 284, bentoH = 98;
  const hmW = 244;
  const statsTotalW = W - 64 - hmW - 12;
  const statGap = 10;
  const usableW = statsTotalW - statGap * 2;
  const tileWidths = [Math.round(usableW * 0.28), Math.round(usableW * 0.32), usableW - Math.round(usableW * 0.28) - Math.round(usableW * 0.32)];

  const modelClean = String(ls.active_model || '-')
    .replace(/\s*\([^)]*\)/g, '')
    .trim() || '-';

  const statTiles = [
    { k: tr('th_calls'), v: tr('n_calls', wObj.calls || 0), sub: `${wObj.conversations || 0} convs`, c: P.text },
    showUsd && wow && wow.comparable && scWin === '7d'
      ? { k: tr('kpi_7d_t'), v: (wow.delta_pct <= 0 ? '↓ ' : '↑ ') + Math.abs(wow.delta_pct).toFixed(1) + '%', sub: 'WoW pace', c: wow.delta_pct <= 0 ? P.ok : P.warn }
      : { k: tr('sc_net_tok'), v: fmtTok(wObj.billable_tokens || 0), sub: `In ${fmtTok(wObj.input_tokens || 0)}`, c: P.gem },
    { k: tr('st_model'), v: modelClean, sub: `Out ${fmtTok(wObj.output_tokens || 0)}`, c: P.cld },
  ];

  let curSx = 32;
  statTiles.forEach((st, idx) => {
    const tw = tileWidths[idx];
    const sx = curSx;
    curSx += tw + statGap;

    scRoundRect(ctx, sx, bentoY, tw, bentoH, 14);
    ctx.fillStyle = P.cardSub; ctx.fill();
    ctx.strokeStyle = P.cardBd; ctx.lineWidth = 1; ctx.stroke();

    ctx.save();
    scRoundRect(ctx, sx, bentoY, tw, bentoH, 14);
    ctx.clip();

    ctx.font = '600 11px ' + ff;
    ctx.fillStyle = P.muted;
    ctx.fillText(st.k, sx + 13, bentoY + 26);

    let fs = 17;
    ctx.font = `800 ${fs}px ` + ff;
    while (fs > 12 && ctx.measureText(st.v).width > tw - 24) {
      fs -= 0.5;
      ctx.font = `800 ${fs}px ` + ff;
    }
    ctx.fillStyle = st.c;
    ctx.fillText(st.v, sx + 13, bentoY + 55);

    ctx.font = '500 10.5px ' + mono;
    ctx.fillStyle = P.muted;
    ctx.fillText(st.sub, sx + 13, bentoY + 78);
    ctx.restore();
  });

  // 4th Bento Tile: GitHub-Unwrapped-style 7x24 Mini Heatmap
  const hx = W - 32 - hmW;
  scRoundRect(ctx, hx, bentoY, hmW, bentoH, 14);
  ctx.fillStyle = P.cardSub; ctx.fill();
  ctx.strokeStyle = P.cardBd; ctx.lineWidth = 1; ctx.stroke();

  ctx.font = '600 10.5px ' + ff;
  ctx.fillStyle = P.muted;
  ctx.fillText('7×24 Activity', hx + 14, bentoY + 22);

  ctx.textAlign = 'right';
  ctx.font = '600 10px ' + mono;
  ctx.fillStyle = P.gem;
  ctx.fillText(fmtTok(wObj.billable_tokens || 0) + ' net', hx + hmW - 14, bentoY + 22);
  ctx.textAlign = 'left';

  let maxCell = 1;
  hmRows.forEach(r => (r.hours || []).forEach(c => { if (c.billable_tokens > maxCell) maxCell = c.billable_tokens; }));
  const cellW = 7.4, cellH = 6.8, gapX = 1.8, gapY = 1.8;
  const gridStartX = hx + 14, gridStartY = bentoY + 31;
  for (let rIdx = 0; rIdx < 7; rIdx++) {
    const hArr = (hmRows[rIdx] && hmRows[rIdx].hours) || [];
    for (let cIdx = 0; cIdx < 24; cIdx++) {
      const val = (hArr[cIdx] && hArr[cIdx].billable_tokens) || 0;
      const ratio = val / maxCell;
      let lv = 0;
      if (val > 0) {
        lv = ratio >= 0.72 ? 4 : (ratio >= 0.42 ? 3 : (ratio >= 0.16 ? 2 : 1));
      }
      scRoundRect(ctx, gridStartX + cIdx * (cellW + gapX), gridStartY + rIdx * (cellH + gapY), cellW, cellH, 1.8);
      ctx.fillStyle = P.heat[lv];
      ctx.fill();
    }
  }

  // 6. Leica-Style Brand Watermark Footer (Crisp 4x Retina Logo)
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
      scRoundRect(ctx, 32, fy + 16, 44, 44, 11);
      ctx.clip();
      ctx.drawImage(logoImg, 32, fy + 16, 44, 44);
      ctx.restore();
    } else {
      logoImg.addEventListener('load', drawShareCard, { once: true });
    }
  }

  ctx.font = '800 14.5px ' + ff;
  ctx.fillStyle = scTheme === 'dark' ? '#38BDF8' : (scTheme === 'light' ? '#0284C7' : '#0F766E');
  ctx.fillText(tr('h1'), 88, fy + 35);
  ctx.font = '500 11px ' + ff;
  ctx.fillStyle = P.muted;
  ctx.fillText(tr('sc_tag_sub'), 88, fy + 54);

  const repoUrl = 'github.com/qiudai0627/agy-usage';
  ctx.font = '700 12px ' + mono;
  const uw = ctx.measureText(repoUrl).width + 24;
  scRoundRect(ctx, W - 32 - uw, fy + 23, uw, 30, 8);
  ctx.fillStyle = P.urlBg; ctx.fill();
  ctx.fillStyle = P.urlFg;
  ctx.fillText(repoUrl, W - 32 - uw + 12, fy + 42);

  // Outer Precision Rim
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
