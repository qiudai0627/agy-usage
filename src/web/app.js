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
  const grp = b.pool_key === 'claude_gpt' ? 'Claude · GPT' : (b.pool_key === 'gemini_flash' ? 'Gemini Flash' : 'Gemini');
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

function burstSparks(cx, cy) {
  if (!cx && !cy) return;
  const cols = ['#38bdf8', '#a78bfa', '#fbbf24', '#f97316', '#10b981'];
  for (let i = 0; i < 10; i++) {
    const d = document.createElement('div');
    d.className = 'spark-dot';
    d.style.background = cols[i % cols.length];
    d.style.left = (cx - 2.5) + 'px';
    d.style.top = (cy - 2.5) + 'px';
    document.body.appendChild(d);
    const ang = (Math.PI * 2 * i) / 10 + (Math.random() - 0.5) * 0.3;
    const dist = 20 + Math.random() * 28;
    requestAnimationFrame(() => {
      d.style.transform = `translate(${Math.cos(ang) * dist}px, ${Math.sin(ang) * dist - 6}px) scale(0.2)`;
      d.style.opacity = '0';
    });
    setTimeout(() => d.remove(), 600);
  }
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
        <div class="card kpi-card"><div class="card-sub">${esc(tr('dr_bill'))}</div><div style="font-size:15px;font-weight:700;color:var(--gem-accent);margin-top:3px">${fmtTok(s.billable_tokens)}</div></div>
        <div class="card kpi-card"><div class="card-sub">${esc(tr('dr_peak'))}</div><div style="font-size:15px;font-weight:700;color:var(--cld-accent);margin-top:3px">${fmtTok(d.peak_context)}</div></div>
        <div class="card kpi-card"><div class="card-sub">${esc(tr('dr_hit'))}</div><div style="font-size:15px;font-weight:700;color:var(--green);margin-top:3px">${s.cache_hit_pct}%</div></div>
        <div class="card kpi-card"><div class="card-sub">${esc(tr('dr_cost_save'))}</div><div style="font-size:13.5px;font-weight:700;margin-top:3px">${fmtUsd(s.est_cost_usd)} / <span style="color:var(--green)">${fmtUsd(s.cache_saved_usd)}</span></div></div>
      </div>

      <div style="font-size:11.5px;font-weight:600;margin-bottom:6px;color:var(--text-strong)">${esc(tr('dr_curve'))}</div>
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:135px;background:var(--chip-bg);border-radius:10px;border:1px solid var(--border);margin-bottom:12px;">
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
  const subEl = document.getElementById('subtitle');
  if (subEl) subEl.textContent = `${data.generated_at_cst} · ${winName(currentWin)}`;
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
    const subEl = document.getElementById('subtitle');
    if (subEl) subEl.textContent = tr('sync_err', err);
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
