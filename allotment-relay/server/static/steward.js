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
}

function ago(epoch) {
  if (!epoch) return '从未活动';
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - Number(epoch)));
  if (sec < 60) return '刚刚';
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
  return `${Math.floor(sec / 86400)} 天前`;
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

  const st = data.status || {};
  const shadow = data.shadow || {};
  const statusTone = st.online ? 'live' : 'off';
  const statusFlags = (st.flags || []).map(f => `<span class="steward-chip warn">${esc(f)}</span>`).join('');
  const ailmentChips = (st.ailments || []).map(a => {
    const extra = a.stage_name ? ` · ${a.stage_name}` : '';
    return `<span class="steward-chip warn">${esc((a.emoji || '') + a.name + extra)}</span>`;
  }).join('');

  document.getElementById('hero').innerHTML = `
    <div class="steward-hero-grid">
      <div class="steward-hero-main">
        <div class="steward-hero-badge">Lv${data.level} · ${esc(data.title)}</div>
        <h2 class="steward-hero-name">${esc(data.name)}</h2>
        <p class="steward-hero-role">${esc(badgeLabel(data.badge))}${data.portrait ? ` · ${esc(data.portrait)}` : ''}</p>
        ${data.motto ? `<blockquote class="steward-hero-motto">「${esc(data.motto)}」</blockquote>` : ''}
        <div class="steward-hero-chips">
          <span class="steward-chip status-${statusTone}">${esc(st.label || '离线')}</span>
          ${statusFlags}
          ${ailmentChips}
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
          <span class="steward-stat-label">状态</span>
          <strong class="steward-stat-value">${esc(st.label || '离线')}</strong>
          <em class="steward-stat-sub">${esc(ago(st.last_active_at))}</em>
        </div>
        <div class="steward-stat-tile">
          <span class="steward-stat-label">影信</span>
          <strong class="steward-stat-value">${shadow.value ?? 10}</strong>
          <em class="steward-stat-sub">${esc(shadow.tier || '')}</em>
        </div>
        <div class="steward-stat-tile">
          <span class="steward-stat-label">等级</span>
          <strong class="steward-stat-value">Lv${data.level}</strong>
        </div>
      </div>
    </div>
  `;

  const m = data.meters || {};
  const ut = (st.undertide) || {};
  const utNotes = [];
  if (shadow.desc) utNotes.push(`影信 ${shadow.value ?? 10} · ${shadow.tier}${shadow.desc ? ' — ' + shadow.desc : ''}`);
  if (ut.jail) {
    const mins = Math.ceil((ut.jail_left || 0) / 60);
    utNotes.push(mins ? `潮下服刑中，约 ${mins} 分钟` : '潮下服刑中');
  }
  if (ut.k_room) utNotes.push('K 室待处理');
  if (ut.busted_count) utNotes.push(`案底 ${ut.busted_count} 条`);
  document.getElementById('meters').innerHTML = [
    meterBar('饱食', m.satiety, 100, 'sand'),
    meterBar('雾智', m.mist_wit, 100, 'sea'),
    meterBar('档信', m.standing, 100, 'green'),
    meterBar('影信', m.shadow_rep ?? shadow.value ?? 10, 100, 'shadow'),
    meterBar('健康', m.health, 100, 'rose'),
    meterBar('精力', m.energy, m.energy_max || 100, 'ink'),
  ].join('') + `
    <div class="steward-meter-notes">
      <p>${esc(data.meter_lines.health)}</p>
      <p>${esc(data.meter_lines.energy)}</p>
      <p>${esc(data.meter_lines.bar_duty)}</p>
      ${utNotes.map(n => `<p>${esc(n)}</p>`).join('')}
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
    : '<p class="steward-empty">无意外</p>';

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
    : '<p class="steward-empty">行囊是空的</p>';

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
    : '<p class="steward-empty">还没有收礼或打赏</p>';

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
