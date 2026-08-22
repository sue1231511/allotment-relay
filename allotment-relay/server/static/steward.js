function fmtTime(epoch) {
  if (!epoch) return '—';
  return new Date(epoch * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

const BADGE_LABELS = {
  naturalist: '博物家',
  mariner: '航海家',
  cook: '厨子',
  host: '掌柜',
  scout: '斥候',
  poet: '诗人',
};

function badgeLabel(key) {
  return BADGE_LABELS[key] || key || '—';
}

const STEWARD_KEY_STORAGE = 'tidal_island_steward_api_key';

function loadSavedKey() {
  try {
    const key = localStorage.getItem(STEWARD_KEY_STORAGE);
    return key && key.startsWith('ar_sk_') ? key : '';
  } catch {
    return '';
  }
}

function saveKey(key) {
  try {
    localStorage.setItem(STEWARD_KEY_STORAGE, key);
  } catch {
    /* private mode / quota */
  }
}

function clearSavedKey() {
  try {
    localStorage.removeItem(STEWARD_KEY_STORAGE);
  } catch {
    /* ignore */
  }
}

function setSavedUi(hasKey) {
  document.getElementById('steward-forget').classList.toggle('hidden', !hasKey);
  document.getElementById('steward-refresh').classList.toggle('hidden', !hasKey);
  document.getElementById('steward-saved-hint').classList.toggle('hidden', !hasKey);
}

async function fetchDashboard(apiKey, { scroll = true } = {}) {
  const btn = document.querySelector('.steward-submit');
  const refreshBtn = document.getElementById('steward-refresh');
  const errBox = document.getElementById('steward-error');
  errBox.classList.add('hidden');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '查询中…';
  }
  if (refreshBtn) refreshBtn.disabled = true;
  try {
    const res = await fetch('/api/steward/dashboard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey.trim() }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '查询失败');
    saveKey(apiKey.trim());
    document.getElementById('api_key').value = apiKey.trim();
    setSavedUi(true);
    renderDashboard(data, { scroll });
    return data;
  } catch (err) {
    errBox.classList.remove('hidden');
    errBox.textContent = err.message;
    document.getElementById('steward-dashboard').classList.add('hidden');
    if (String(err.message).includes('无效')) {
      clearSavedKey();
      setSavedUi(false);
    }
    throw err;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '查看状态';
    }
    if (refreshBtn) refreshBtn.disabled = false;
  }
}

function meterBar(label, value, max = 100, tone = 'sea') {
  const v = Math.max(0, Math.min(max, Number(value) || 0));
  const pct = Math.round((v / max) * 100);
  const low = pct < 35 ? ' is-low' : pct < 60 ? ' is-mid' : '';
  return `
    <div class="steward-meter">
      <div class="steward-meter-top">
        <span>${esc(label)}</span>
        <strong>${v}</strong>
      </div>
      <div class="steward-meter-track">
        <div class="steward-meter-fill tone-${tone}${low}" style="width:${pct}%"></div>
      </div>
    </div>
  `;
}

function plotCard(p) {
  const gh = p.greenhouse ? '<span class="plot-gh" title="温室">🪴</span>' : '';
  return `
    <article class="plot-card state-${p.state || 'fallow'}">
      <div class="plot-card-top">
        <span class="plot-slot">#${p.slot}</span>
        ${gh}
        <span class="plot-emoji">${p.emoji || '🌱'}</span>
      </div>
      <strong class="plot-name">${esc(p.name || p.label)}</strong>
      <p class="plot-detail">${esc(p.detail || '')}</p>
    </article>
  `;
}

function renderDashboard(data, { scroll = true } = {}) {
  document.getElementById('steward-dashboard').classList.remove('hidden');
  document.getElementById('steward-error').classList.add('hidden');

  const pulse = data.pulse;
  const pulseChip = pulse
    ? `<span class="steward-chip pulse-${pulse.kind}">脉冲 · ${esc(pulse.label)} · ${Math.floor(pulse.remaining / 60)}分</span>`
    : '';

  const flags = [];
  if (data.flags.greenhouse) flags.push('温室');
  if (data.flags.hut_built) flags.push('小屋');
  if (data.flags.barn_built) flags.push('畜栏');
  if (data.flags.eatery_open) flags.push('小馆');
  if (data.flags.boat) flags.push('有船');

  document.getElementById('hero').innerHTML = `
    <div class="steward-hero-grid">
      <div class="steward-hero-main">
        <div class="steward-hero-badge">Lv${data.level} · ${esc(data.title)}</div>
        <h2 class="steward-hero-name">${esc(data.name)}</h2>
        <p class="steward-hero-role">${esc(badgeLabel(data.badge))}${data.portrait ? ` · ${esc(data.portrait)}` : ''}</p>
        ${data.motto ? `<blockquote class="steward-hero-motto">「${esc(data.motto)}」</blockquote>` : ''}
        <div class="steward-hero-chips">
          ${pulseChip}
          <span class="steward-chip">${esc(data.climate)}</span>
          ${flags.map(f => `<span class="steward-chip soft">${esc(f)}</span>`).join('')}
        </div>
      </div>
      <div class="steward-hero-stats">
        <div class="steward-stat-tile highlight">
          <span class="steward-stat-label">工分票</span>
          <strong class="steward-stat-value">${data.tickets}</strong>
        </div>
        <div class="steward-stat-tile">
          <span class="steward-stat-label">等级</span>
          <strong class="steward-stat-value">Lv${data.level}</strong>
        </div>
        <div class="steward-stat-tile">
          <span class="steward-stat-label">行囊</span>
          <strong class="steward-stat-value">${data.stock_count} 种</strong>
        </div>
        <div class="steward-stat-tile">
          <span class="steward-stat-label">集市</span>
          <strong class="steward-stat-value">${data.market.used}/${data.market.cap}</strong>
        </div>
      </div>
    </div>
  `;

  const m = data.meters || {};
  document.getElementById('meters').innerHTML = [
    meterBar('饱食', m.satiety, 100, 'sand'),
    meterBar('雾智', m.mist_wit, 100, 'sea'),
    meterBar('档信', m.standing, 100, 'green'),
    meterBar('健康', m.health, 100, 'rose'),
    meterBar('精力', m.energy, m.energy_max || 100, 'ink'),
  ].join('') + `
    <div class="steward-meter-notes">
      <p>${esc(data.meter_lines.energy)}</p>
      <p>${esc(data.meter_lines.bar_duty)}</p>
      ${data.voyage ? `<p class="steward-note-voyage">⛵ ${esc(data.voyage)}</p>` : ''}
    </div>
  `;

  const marketPct = data.market.cap
    ? Math.round((data.market.used / data.market.cap) * 100)
    : 0;
  const incidentHtml = data.incidents.length
    ? data.incidents.map(i => `
        <div class="steward-incident">
          <span class="steward-incident-id">#${i.id}</span>
          <span class="steward-incident-label">${esc(i.label)}</span>
          <span class="steward-incident-cost">${i.repair_tickets} 票</span>
        </div>
      `).join('')
    : '<p class="steward-empty">无未处理意外，今天挺太平。</p>';

  document.getElementById('ops').innerHTML = `
    <div class="steward-ops-block">
      <div class="steward-ops-head">
        <span>集市摊格</span>
        <strong>${data.market.used} / ${data.market.cap}</strong>
      </div>
      <div class="steward-meter-track compact">
        <div class="steward-meter-fill tone-sea" style="width:${marketPct}%"></div>
      </div>
    </div>
    <div class="steward-ops-block">
      <h3>意外</h3>
      ${incidentHtml}
    </div>
  `;

  document.getElementById('parcels').innerHTML = data.parcels.length
    ? data.parcels.map(plotCard).join('')
    : '<p class="steward-empty">暂无份地</p>';

  document.getElementById('stock').innerHTML = data.stock.length
    ? `<div class="steward-stock-meta">共 ${data.stock_count} 种物品</div>
       <div class="steward-stock-grid">${data.stock.map(i => `
         <span class="stock-chip" title="${esc(i.item)}">
           <strong>${esc(i.name)}</strong>
           <em>×${i.qty}</em>
         </span>
       `).join('')}</div>`
    : '<p class="steward-empty">行囊是空的，去种地或赶海吧。</p>';

  document.getElementById('gifts').innerHTML = data.gifts.length
    ? data.gifts.map(g => `
        <article class="steward-gift">
          <div class="steward-gift-meta">
            <time>${fmtTime(g.created_at)}</time>
            <span class="steward-gift-kind kind-${g.kind === '打赏' ? 'tip' : 'gift'}">${esc(g.kind)}</span>
          </div>
          <div class="steward-gift-body">
            <strong>${esc(g.who)}</strong>
            <p>${esc(g.text)}</p>
          </div>
        </article>
      `).join('')
    : '<p class="steward-empty">还没有收礼或酒吧打赏记录。</p>';

  if (scroll) {
    document.getElementById('steward-dashboard').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

document.getElementById('steward-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  await fetchDashboard(document.getElementById('api_key').value);
});

document.getElementById('steward-refresh').addEventListener('click', () => {
  const key = document.getElementById('api_key').value.trim() || loadSavedKey();
  if (key) fetchDashboard(key, { scroll: false });
});

document.getElementById('steward-forget').addEventListener('click', () => {
  clearSavedKey();
  document.getElementById('api_key').value = '';
  document.getElementById('steward-dashboard').classList.add('hidden');
  document.getElementById('steward-error').classList.add('hidden');
  setSavedUi(false);
});

(function initStewardPage() {
  const saved = loadSavedKey();
  if (!saved) return;
  document.getElementById('api_key').value = saved;
  setSavedUi(true);
  fetchDashboard(saved, { scroll: false }).catch(() => {});
})();
