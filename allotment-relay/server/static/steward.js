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

const MEMORY_KIND_LABELS = { tale: '潮闻', story: '故事', npc: '相遇' };
let memoryCatalog = [];
let memoryFilter = 'all';
let activeMemory = null;
let activeMemoryChapter = 0;
let continuousMemoryMode = false;
let memoryReturnFocus = null;

function saveKey(key) {
  saveSiteKey(key);
}

function clearSavedKey() {
  clearSiteKey();
}

function setSavedUi(hasKey) {
  document.getElementById('steward-forget').classList.toggle('hidden', !hasKey);
  document.getElementById('steward-refresh').classList.toggle('hidden', !hasKey);
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
        <span class="plot-slot">${p.greenhouse ? '棚' : (p.orchard ? '园' : '#')}${p.slot}</span>
        ${gh}
        <span class="plot-emoji">${p.emoji || '🌱'}</span>
      </div>
      <strong class="plot-name">${esc(p.name || p.label)}</strong>
      <p class="plot-detail">${esc(p.detail || '')}</p>
    </article>
  `;
}

function agoLabel(epoch) {
  if (!epoch) return '尚无活动';
  const sec = Math.max(0, Math.floor(Date.now() / 1000) - Number(epoch));
  if (sec < 60) return '刚刚';
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
  return `${Math.floor(sec / 86400)} 天前`;
}

function fmtMemoryDate(epoch) {
  if (!epoch) return '已收录';
  return new Date(Number(epoch) * 1000).toLocaleDateString('zh-CN', {
    year: 'numeric', month: 'long', day: 'numeric',
  });
}

function multiline(value) {
  return esc(value).replace(/\n/g, '<br>');
}

function renderMemories(memories) {
  memoryCatalog = Array.isArray(memories) ? memories : [];
  const root = document.getElementById('memories');
  const visible = memoryFilter === 'all'
    ? memoryCatalog
    : memoryCatalog.filter(item => item.kind === memoryFilter);
  if (!visible.length) {
    root.innerHTML = `<div class="memory-empty">
      <span>〰</span>
      <strong>${memoryCatalog.length ? '这个分类还没有回忆' : '岛上回忆册还是空的'}</strong>
      <p>只有真正完成的潮闻、人物故事和 NPC 小事件才会出现在这里，未完成内容不会提前剧透。</p>
    </div>`;
    return;
  }
  root.innerHTML = visible.map(item => {
    const index = memoryCatalog.indexOf(item);
    const keepsakes = (item.souvenirs || []).slice(0, 4).map(s =>
      `<span class="memory-keepsake" title="${esc(s.description || s.name)}">${esc(s.emoji || '◌')} ${esc(s.name)}</span>`
    ).join('');
    const variants = item.variants || [];
    const chooser = variants.length > 1 ? `
      <label class="memory-variant-label">
        <span>选择结局</span>
        <select data-memory-variant-select="${index}">
          ${variants.map((v, i) => `<option value="${i}">${esc(v.label)}</option>`).join('')}
        </select>
      </label>` : '';
    const count = Number(item.chapter_count) > 0 ? `${item.chapter_count} 幕` : '旧档案';
    return `
      <article class="memory-card kind-${esc(item.kind)}" data-memory-card="${index}">
        <div class="memory-card-top">
          <span class="memory-kind">${esc(MEMORY_KIND_LABELS[item.kind] || item.kind)}</span>
          <time>${esc(fmtMemoryDate(item.completed_at))}</time>
        </div>
        <h3>《${esc(item.title)}》</h3>
        <p class="memory-blurb">${esc(item.blurb)}</p>
        <div class="memory-card-meta">
          <span>${esc(count)}</span>
          ${item.ending ? `<span>${esc(item.ending)}</span>` : ''}
        </div>
        ${keepsakes ? `<div class="memory-keepsakes">${keepsakes}</div>` : ''}
        <div class="memory-card-action">
          ${chooser}
          <button type="button" class="btn primary memory-watch" data-memory-watch="${index}">再次观看</button>
        </div>
      </article>`;
  }).join('');
}

function memorySouvenirs(items) {
  if (!items || !items.length) return '';
  return `<section class="memory-reader-souvenirs">
    <h4>一同留下的纪念</h4>
    <div>${items.map(item => `
      <span title="${esc(item.description || '')}">${esc(item.emoji || '◌')} ${esc(item.name)}</span>
    `).join('')}</div>
  </section>`;
}

function renderMemoryReader() {
  if (!activeMemory) return;
  const chapters = activeMemory.chapters || [];
  const toc = document.getElementById('memory-reader-toc');
  const page = document.getElementById('memory-reader-page');
  document.getElementById('memory-reader-title').textContent = `《${activeMemory.title}》`;
  document.getElementById('memory-reader-kicker').textContent = `${MEMORY_KIND_LABELS[activeMemory.kind] || '岛上'} · 回忆重映`;
  document.getElementById('memory-reader-meta').textContent = [
    fmtMemoryDate(activeMemory.completed_at),
    activeMemory.ending ? `留下：${activeMemory.ending}` : '',
  ].filter(Boolean).join(' · ');
  document.getElementById('memory-reader-notice').textContent = activeMemory.notice || '';
  toc.innerHTML = chapters.map((chapter, i) => `
    <button type="button" class="memory-toc-item${!continuousMemoryMode && i === activeMemoryChapter ? ' is-active' : ''}" data-memory-chapter="${i}">
      <span>${String(i + 1).padStart(2, '0')}</span>${esc(chapter.title)}
    </button>
  `).join('');
  if (continuousMemoryMode) {
    page.innerHTML = chapters.map((chapter, i) => `
      <section class="memory-chapter" id="memory-chapter-${i}">
        <span class="memory-chapter-count">${i + 1} / ${chapters.length}</span>
        <h3>${esc(chapter.title)}</h3>
        <div class="memory-prose">${multiline(chapter.text)}</div>
      </section>
    `).join('') + memorySouvenirs(activeMemory.souvenirs);
  } else {
    const chapter = chapters[activeMemoryChapter] || { title: '回忆', text: '' };
    page.innerHTML = `
      <section class="memory-chapter">
        <span class="memory-chapter-count">${activeMemoryChapter + 1} / ${chapters.length}</span>
        <h3>${esc(chapter.title)}</h3>
        <div class="memory-prose">${multiline(chapter.text)}</div>
      </section>
      ${activeMemoryChapter === chapters.length - 1 ? memorySouvenirs(activeMemory.souvenirs) : ''}`;
  }
  document.getElementById('memory-reader-progress').textContent = continuousMemoryMode
    ? `共 ${chapters.length} 幕`
    : `${activeMemoryChapter + 1} / ${chapters.length}`;
  document.getElementById('memory-reader-prev').disabled = continuousMemoryMode || activeMemoryChapter <= 0;
  document.getElementById('memory-reader-next').disabled = continuousMemoryMode || activeMemoryChapter >= chapters.length - 1;
  document.getElementById('memory-reader-mode').textContent = continuousMemoryMode ? '按幕阅读' : '连续阅读';
}

async function openMemory(index, trigger) {
  const item = memoryCatalog[index];
  if (!item) return;
  const card = trigger.closest('[data-memory-card]');
  const select = card ? card.querySelector('[data-memory-variant-select]') : null;
  const variantIndex = select ? Number(select.value) : 0;
  const variant = (item.variants || [])[variantIndex];
  trigger.disabled = true;
  trigger.textContent = '取回中…';
  try {
    const apiKey = document.getElementById('api_key').value.trim() || loadSavedKey();
    const res = await fetch('/api/steward/memory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: apiKey,
        kind: item.kind,
        key: item.key,
        variant: variant ? String(variant.id) : '',
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '回忆暂时无法打开');
    activeMemory = data;
    activeMemoryChapter = 0;
    continuousMemoryMode = false;
    memoryReturnFocus = trigger;
    renderMemoryReader();
    document.getElementById('memory-modal').classList.remove('hidden');
    document.body.classList.add('memory-open');
    document.querySelector('.memory-reader-close').focus();
  } catch (err) {
    const errBox = document.getElementById('steward-error');
    errBox.textContent = err.message;
    errBox.classList.remove('hidden');
  } finally {
    trigger.disabled = false;
    trigger.textContent = '再次观看';
  }
}

function closeMemory() {
  document.getElementById('memory-modal').classList.add('hidden');
  document.body.classList.remove('memory-open');
  activeMemory = null;
  if (memoryReturnFocus) memoryReturnFocus.focus();
  memoryReturnFocus = null;
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
  const statusOnline = !!st.online;
  const statusFlags = (st.flags || []).map(f =>
    `<span class="steward-chip warn">${esc(f)}</span>`
  ).join('');

  document.getElementById('hero').innerHTML = `
    <div class="steward-hero-grid">
      <div class="steward-hero-main">
        <div class="steward-hero-badge">Lv${data.level} · ${esc(data.title)}</div>
        <h2 class="steward-hero-name">${esc(data.name)}</h2>
        <p class="steward-hero-role">${esc(badgeLabel(data.badge))}${data.portrait ? ` · ${esc(data.portrait)}` : ''}</p>
        ${data.motto ? `<blockquote class="steward-hero-motto">「${esc(data.motto)}」</blockquote>` : ''}
        <div class="steward-hero-chips">
          <span class="steward-chip ${statusOnline ? 'is-online' : 'is-offline'}">
            状态 · ${esc(st.label || (statusOnline ? '在线' : '离线'))}
            <em class="steward-chip-sub">${esc(agoLabel(st.last_active_at))}</em>
          </span>
          <span class="steward-chip shadow-chip">
            影信 · ${shadow.rep ?? '—'}
            ${shadow.tier ? `<em class="steward-chip-sub">${esc(shadow.tier)}</em>` : ''}
          </span>
          ${statusFlags}
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
          <strong class="steward-stat-value steward-stat-status ${statusOnline ? 'is-online' : 'is-offline'}">${esc(st.label || (statusOnline ? '在线' : '离线'))}</strong>
        </div>
        <div class="steward-stat-tile">
          <span class="steward-stat-label">影信</span>
          <strong class="steward-stat-value">${shadow.rep ?? '—'}</strong>
          ${shadow.tier ? `<span class="steward-stat-sub">${esc(shadow.tier)}</span>` : ''}
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
    meterBar('影信', m.shadow_rep ?? shadow.rep, 100, 'ink'),
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
      ${data.quarry && data.quarry.line ? `<p class="steward-note-voyage">⚒️ ${esc(data.quarry.line)}</p>` : ''}
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
    : '<p class="steward-empty">无未处理意外</p>';

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
    : '<p class="steward-empty">行囊空</p>';

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
    : '<p class="steward-empty">暂无收礼 / 打赏</p>';

  renderMemories(data.memories || []);

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
  closeMemory();
  clearSavedKey();
  document.getElementById('api_key').value = '';
  document.getElementById('steward-dashboard').classList.add('hidden');
  document.getElementById('steward-error').classList.add('hidden');
  setSavedUi(false);
});

document.getElementById('memory-filters').addEventListener('click', (e) => {
  const button = e.target.closest('[data-memory-filter]');
  if (!button) return;
  memoryFilter = button.dataset.memoryFilter;
  document.querySelectorAll('[data-memory-filter]').forEach(item => {
    item.classList.toggle('is-active', item === button);
  });
  renderMemories(memoryCatalog);
});

document.getElementById('memories').addEventListener('click', (e) => {
  const button = e.target.closest('[data-memory-watch]');
  if (!button) return;
  openMemory(Number(button.dataset.memoryWatch), button);
});

document.getElementById('memory-reader-toc').addEventListener('click', (e) => {
  const button = e.target.closest('[data-memory-chapter]');
  if (!button || !activeMemory) return;
  const index = Number(button.dataset.memoryChapter);
  if (continuousMemoryMode) {
    document.getElementById(`memory-chapter-${index}`)?.scrollIntoView({ behavior: 'smooth' });
    return;
  }
  activeMemoryChapter = index;
  renderMemoryReader();
  document.getElementById('memory-reader-page').scrollTop = 0;
});

document.getElementById('memory-reader-prev').addEventListener('click', () => {
  if (!activeMemory || activeMemoryChapter <= 0) return;
  activeMemoryChapter -= 1;
  renderMemoryReader();
  document.getElementById('memory-reader-page').scrollTop = 0;
});

document.getElementById('memory-reader-next').addEventListener('click', () => {
  if (!activeMemory || activeMemoryChapter >= activeMemory.chapters.length - 1) return;
  activeMemoryChapter += 1;
  renderMemoryReader();
  document.getElementById('memory-reader-page').scrollTop = 0;
});

document.getElementById('memory-reader-mode').addEventListener('click', () => {
  continuousMemoryMode = !continuousMemoryMode;
  renderMemoryReader();
  document.getElementById('memory-reader-page').scrollTop = 0;
});

document.querySelectorAll('[data-memory-close]').forEach(button => {
  button.addEventListener('click', closeMemory);
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !document.getElementById('memory-modal').classList.contains('hidden')) {
    closeMemory();
  }
});

(function initStewardPage() {
  const saved = loadSavedKey();
  if (!saved) return;
  document.getElementById('api_key').value = saved;
  setSavedUi(true);
  fetchDashboard(saved, { scroll: false }).catch(() => {});
})();
