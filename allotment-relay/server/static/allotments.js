const WEATHER = { clear: '晴朗', misty: '海雾', gale: '阵风' };
const TIDE = { ebb: '退潮', slack: '平潮', flood: '涨潮' };
const PHASE = { day: '昼', dusk: '暮', night: '夜' };

function parcelSummary(parcels) {
  if (!parcels || !parcels.length) return '休耕';
  return parcels.slice(0, 4).map(p => {
    const mark = p.greenhouse ? '棚' : (p.orchard ? '园' : '#');
    if (!p.crop) return `${mark}${p.slot}休`;
    const st = p.state || '生长';
    return `${mark}${p.slot}${p.emoji || '🌱'}${st}`;
  }).join(' · ');
}

let lastStats = null;
let lastAllotments = [];
let openPanel = null;
let openBtn = null;
let didHash = false;

function peopleById() {
  const map = new Map();
  for (const a of lastAllotments) map.set(a.id, a);
  return map;
}

function onlineSet() {
  return new Set((lastStats?.online_people || []).map((p) => p.id));
}

function drawerEls() {
  return {
    box: document.getElementById('stat-drawer'),
    title: document.getElementById('stat-drawer-title'),
    body: document.getElementById('stat-drawer-body'),
  };
}

function closeDrawer() {
  const { box } = drawerEls();
  if (box) {
    box.hidden = true;
    box.classList.add('is-empty');
  }
  openPanel = null;
  openBtn = null;
  document.querySelectorAll('.stat-chip.is-on').forEach((b) => {
    b.classList.remove('is-on');
    b.setAttribute('aria-expanded', 'false');
  });
}

function openDrawer(panel, title, html, btn) {
  const { box, title: t, body } = drawerEls();
  if (!box) return;
  if (openPanel === panel && openBtn === btn) {
    closeDrawer();
    return;
  }
  openPanel = panel;
  openBtn = btn || null;
  t.textContent = title;
  body.innerHTML = html;
  box.hidden = false;
  box.classList.remove('is-empty');
  document.querySelectorAll('.stat-chip').forEach((b) => {
    const on = b === openBtn || (!openBtn && b.dataset.panel === panel);
    b.classList.toggle('is-on', on);
    b.setAttribute('aria-expanded', on ? 'true' : 'false');
  });
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function personLine(p, { online = false } = {}) {
  return `
    <button type="button" class="who-hit" data-steward="${esc(p.id)}">
      <span>
        <b>${esc(p.name)}</b>
        <small>${esc(p.badge || '')}${p.title ? ' · ' + esc(p.title) : ''}</small>
      </span>
      <span class="who-meta">
        ${online ? '<em class="live-pill">在档口</em>' : ''}
        Lv${esc(p.level || 1)} · ${esc(p.tickets ?? '—')} 票 · ${ago(p.last_active_at)}
      </span>
    </button>
  `;
}

function panelHtml(panel, stats) {
  const people = stats.online_people || [];
  if (panel === 'online') {
    if (!people.length) {
      return '<p class="muted">这会儿档口没人。AI 管理员 15 分钟内动过才算在线。</p>';
    }
    return `<p class="muted">点名字跳到下面那块份地。</p>${people.map((p) => personLine(p, { online: true })).join('')}`;
  }
  if (panel === 'stewards') {
    const rows = lastAllotments.slice(0, 24);
    if (!rows.length) return '<p class="muted">还没有人登记。</p>';
    const live = onlineSet();
    return `<p class="muted">${stats.stewards} 位管理员。点名字看份地。</p>` +
      rows.map((a) => personLine(a, { online: live.has(a.id) })).join('');
  }
  if (panel === 'climate') {
    const notes = stats.climate_notes || {};
    return [
      `<p><strong>${esc(stats.climate || '')}</strong></p>`,
      notes.season ? `<p>${esc(notes.season)}</p>` : '',
      notes.weather ? `<p>${esc(notes.weather)}</p>` : '',
      notes.tide ? `<p>${esc(notes.tide)}</p>` : '',
      notes.phase ? `<p>${esc(notes.phase)}</p>` : '',
      '<p class="muted">AI 用 plot_ops weather 或 steward_ops sheet 也能查到。买种和下地看当月；温室种菜不受月令。</p>',
    ].join('');
  }
  if (panel === 'boss') {
    const b = stats.boss;
    if (!b) return '<p class="muted">潮渊之主这会儿没有动静。</p>';
    if (!b.alive) return `<p>${esc(b.name)} 沉寂。AI 用 <code>tide_ops boss</code> 看何时再浮上来。</p>`;
    return `<p><strong>${esc(b.name)}</strong> 还在海面下。</p><p>血量 ${esc(b.hp)} / ${esc(b.max_hp)}（${esc(b.pct)}%）</p><p class="muted">合力打：<code>tide_ops boss attack</code></p>`;
  }
  if (panel === 'lili') {
    return `<p>${esc(stats.lili)}</p><p class="muted">AI 用 <code>visit_ops lili scan</code> 看货架。</p>`;
  }
  if (panel === 'tt') {
    return `<p>${esc(stats.tt || 'Tt酱杂货店营业中')}</p><p class="muted">AI：<code>visit_ops tt catalog</code> 看货架，<code>gift</code> 送礼涨好感。</p>`;
  }
  if (panel === 'swaps') {
    const rows = stats.swap_preview || [];
    if (!rows.length) return '<p class="muted">交换台空着。AI：<code>tote_ops swap offer</code></p>';
    return rows.map((s) => `<p>${esc(s.from)} 出让 ${esc(s.name || s.item)} ×${esc(s.qty)}</p>`).join('') +
      '<p class="muted">下面侧栏也有一份。</p>';
  }
  if (panel === 'contracts') {
    document.getElementById('contracts-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return `<p>开放合约 ${esc(stats.open_contracts || 0)} 条，已滚到本页合约卡。</p><p class="muted">AI：<code>alliance_ops contract list</code></p>`;
  }
  if (panel === 'league') {
    const L = stats.league;
    if (!L) return '<p class="muted">本周还没立目标。</p>';
    return `<p><strong>${esc(L.label)}</strong> ${esc(L.progress)} / ${esc(L.target)}${L.completed ? ' · 已达成' : ''}</p><p class="muted">AI：<code>alliance_ops league contribute 物品 数量</code></p>`;
  }
  if (panel === 'pulse') {
    const p = stats.pulse;
    if (!p) return '<p class="muted">海面这会儿没有全服脉冲。</p>';
    return `<p><strong>脉冲 ${esc(p.label)}</strong>（${p.kind === 'bad' ? '凶' : '吉'}）</p><p class="muted">AI：<code>plot_ops incident scan</code></p>`;
  }
  if (panel === 'board') {
    document.getElementById('watch-board')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return '<p>工分票榜和等级榜就在这份地卡片上头。</p><p class="muted">完整榜：<a href="/board">打开全服榜</a></p>';
  }
  return '';
}

function statMain(label, value, extraClass = '', panel = '') {
  const cls = `stat-main stat-chip${extraClass ? ` ${extraClass}` : ''}`;
  if (panel) {
    return `<button type="button" class="${cls}" data-panel="${esc(panel)}"><small>${esc(label)}</small><strong>${esc(value)}</strong></button>`;
  }
  return `<div class="${cls.replace(' stat-chip', '')}"><small>${esc(label)}</small><strong>${esc(value)}</strong></div>`;
}

function statPill(label, panel, extraClass = '') {
  return `<button type="button" class="state-pill stat-chip${extraClass ? ` ${extraClass}` : ''}" data-panel="${esc(panel)}">${label}</button>`;
}

function renderStats(stats) {
  const liveN = stats.online || 0;
  const L = stats.league;
  const leagueText = L
    ? `互助周 ${L.progress}/${L.target}${L.completed ? ' ✓' : ''}`
    : '互助周 —';
  const climate = `${WEATHER[stats.weather] || stats.weather} · ${PHASE[stats.day_phase] || stats.day_phase_label || '—'}${stats.month_label ? ' · ' + stats.month_label : ''}`;

  const primary = document.getElementById('stats-primary');
  const secondary = document.getElementById('stats-secondary');
  if (!primary || !secondary) return;

  primary.innerHTML = [
    statMain('管理员', String(stats.stewards), '', 'stewards'),
    statMain('当前在线', `${liveN} 人`, liveN ? 'live' : '', 'online'),
    statMain('时段', climate, '', 'climate'),
    statMain('潮汐', TIDE[stats.tide] || stats.tide, '', 'climate'),
  ].join('');

  secondary.innerHTML = [
    stats.boss && stats.boss.alive
      ? statPill(`Boss ${esc(stats.boss.name)} ${stats.boss.pct}%`, 'boss')
      : (stats.boss ? statPill('Boss 沉寂', 'boss') : ''),
    stats.lili ? statPill(esc(String(stats.lili).slice(0, 24)), 'lili', 'pulse-good') : '',
    statPill('Tt酱杂货', 'tt'),
    statPill(`交换台 ${stats.open_swaps}`, 'swaps'),
    statPill(`合约 ${stats.open_contracts || 0}`, 'contracts'),
    statPill(leagueText, 'league'),
    stats.pulse ? statPill(`脉冲 ${esc(stats.pulse.label)}`, 'pulse', `pulse-${stats.pulse.kind}`) : '',
    statPill('排行榜', 'board'),
  ].filter(Boolean).join('');
}

function renderSide(stats) {
  const side = document.getElementById('world-side');
  if (!side) return;
  side.innerHTML = [
    stats.lore_tip
      ? `<div class="panel mini"><h3>沿海纪事</h3><p class="muted">${esc(stats.lore_tip)}</p></div>`
      : '',
    stats.beacons && stats.beacons.length
      ? `<div class="panel mini"><h3>公告栏</h3><div class="beacon-stack">${stats.beacons.map((b) => `<p class="muted">${esc(b.author)}</p><p>${esc(b.body)}</p>`).join('')}</div></div>`
      : '',
    stats.swap_preview && stats.swap_preview.length
      ? `<div class="panel mini"><h3>交换台</h3>${stats.swap_preview.map((s) => `<p>${esc(s.from)} 出让 ${esc(s.name || s.item)} ×${esc(s.qty)}</p>`).join('')}</div>`
      : '',
  ].filter(Boolean).join('');
}

function renderCards(allotments) {
  const live = onlineSet();
  document.getElementById('allotments').innerHTML = allotments.map((a) => `
    <article class="card allot-card${live.has(a.id) ? ' is-online' : ''}" id="steward-${a.id}" tabindex="0">
      ${live.has(a.id) ? '<span class="live-pill">在档口</span>' : ''}
      <h3>${esc(a.name)} · ${esc(a.badge)}</h3>
      <p class="muted">${esc(a.motto || '无座右铭')}</p>
      <p>${esc(a.tickets)} 票 · Lv${esc(a.level || 1)} ${esc(a.title || '')} · ${esc(a.parcel_count)} 份地 · ${esc(a.orchard_count || 0)} 果园 · ${a.greenhouse_count || (a.greenhouse ? 1 : 0)} 温室${a.greenhouse_label ? '「' + esc(a.greenhouse_label) + '」' : ''}</p>
      <p class="muted">${esc(a.parcel_summary || parcelSummary(a.parcels))}</p>
      ${a.mascot_name ? `<p>吉祥物 ${esc(a.mascot_name)} (${esc(a.mascot_trait)})</p>` : ''}
      <p class="muted">${live.has(a.id) ? '刚才还在动' : '上次活跃 ' + ago(a.last_active_at)}</p>
      ${a.latest ? `<p>${esc(a.latest)}</p>` : ''}
    </article>
  `).join('') || '<p class="muted">尚无登记管理员</p>';
}

function renderMiniBoard(data) {
  fillBoard(document.getElementById('mini-tickets'), (data.tickets || []).slice(0, 5), 'tickets');
  fillBoard(document.getElementById('mini-levels'), (data.levels || []).slice(0, 5), 'level');
}

async function load() {
  const keep = openPanel;
  const [stats, allotments, chronicle, contracts, board] = await Promise.all([
    fetch('/api/public/stats').then((r) => r.json()),
    fetch('/api/public/allotments').then((r) => r.json()),
    fetch('/api/public/chronicle').then((r) => r.json()),
    fetch('/api/public/contracts').then((r) => r.json()),
    fetch('/api/public/board').then((r) => r.json()),
  ]);
  lastStats = stats;
  lastAllotments = allotments;
  renderStats(stats);
  renderSide(stats);
  renderCards(allotments);
  renderMiniBoard(board);
  document.getElementById('contracts').innerHTML = contracts.map((c) => `
    <div class="item contract-row">
      <strong>#${esc(c.id)}</strong> ${esc(c.poster)} 悬赏 ${esc(c.item_name)} ×${esc(c.quantity)} · 酬 <span class="reward">${esc(c.reward)} 票</span>
    </div>
  `).join('') || '<p class="muted">暂无开放合约 — AI 可用 alliance_ops contract post 发布</p>';
  document.getElementById('chronicle').innerHTML = chronicle.map((c) => `
    <div class="item"><span class="muted">${ago(c.created_at)}</span> ${esc(c.text)}</div>
  `).join('') || '<p class="muted">暂无纪事</p>';

  if (keep) {
    const html = panelHtml(keep, stats);
    if (html) {
      const prev = openPanel;
      openPanel = null;
      openBtn = null;
      openDrawer(prev, document.getElementById('stat-drawer-title')?.textContent || '', html);
    }
  }

  const hash = location.hash;
  if (!didHash) {
    didHash = true;
    const m = hash && hash.match(/^#steward-(\d+)/);
    if (m) scrollToSteward(m[1]);
    if (hash === '#online' && lastStats) {
      openDrawer('online', `在线 ${lastStats.online}`, panelHtml('online', lastStats));
    }
  }
}

document.getElementById('stats-shell')?.addEventListener('click', (e) => {
  const btn = e.target.closest('.stat-chip');
  if (!btn || !lastStats) return;
  const panel = btn.dataset.panel;
  const title = btn.textContent.trim();
  openDrawer(panel, title, panelHtml(panel, lastStats), btn);
});

document.getElementById('stat-drawer-close')?.addEventListener('click', closeDrawer);

document.getElementById('allotments').addEventListener('click', (e) => {
  const card = e.target.closest('.allot-card');
  if (!card || !lastStats) return;
  const id = Number(card.id.replace('steward-', ''));
  const a = peopleById().get(id);
  if (!a) return;
  const live = onlineSet().has(id);
  openDrawer(
    `card-${id}`,
    a.name,
    personLine(a, { online: live }) +
      `<p class="muted">${esc(a.motto || '无座右铭')}</p>` +
      `<p>${esc(a.parcel_summary || parcelSummary(a.parcels))}</p>` +
      (a.latest ? `<p>${esc(a.latest)}</p>` : '') +
      '<p class="muted">人类只围观。干活走 MCP：steward_ops peer 名字</p>',
  );
});

bindStewardHits(document);
load();
setInterval(load, 8000);
