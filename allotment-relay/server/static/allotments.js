function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function ago(ts) {
  if (typeof islandFmtStamp === 'function') return islandFmtStamp(ts);
  return '—';
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function isReady(state) {
  const s = String(state || '');
  return s === '可收' || s === '过熟' || s === 'ready' || s === 'overripe';
}

function slotLabel(p) {
  if (p.greenhouse) return `棚${p.slot}`;
  if (p.orchard) return `园${p.slot}`;
  return `#${p.slot}`;
}

function landTotal(a) {
  return Number(a.parcel_count || 0)
    + Number(a.orchard_count || 0)
    + Number(a.greenhouse_count || 0);
}

function splitParcels(a) {
  const parcels = a.parcels || [];
  return {
    veg: parcels.filter((p) => !p.orchard && !p.greenhouse),
    orch: parcels.filter((p) => p.orchard && !p.greenhouse),
    glass: parcels.filter((p) => p.greenhouse),
  };
}

function cropRows(a) {
  return (a.parcels || [])
    .filter((p) => p.crop || (p.state && p.state !== '休耕'))
    .map((p) => ({
      token: slotLabel(p),
      name: p.name || (p.crop ? String(p.crop) : '—'),
      state: p.state || '—',
      ready: isReady(p.state),
    }));
}

let state = { list: [], onlineIds: new Set(), selected: 0, chronicle: [] };

function renderHero(stats, list) {
  const totalLand = (list || []).reduce((n, a) => n + landTotal(a), 0);
  const ready = (list || []).reduce((n, a) => n + Number(a.ready_count || 0), 0);
  setText('stewards', stats.stewards ?? '—');
  setText('online', stats.online ?? '—');
  setText('parcelsTotal', totalLand || '—');
  setText('readyTotal', ready || '—');
}

function renderExpansion(chronicle) {
  const cut = Math.floor(Date.now() / 1000) - 86400;
  const rows = (chronicle || []).filter((c) => Number(c.created_at || 0) >= cut);
  let veg = 0;
  let orch = 0;
  let glass = 0;
  for (const c of rows) {
    const t = String(c.text || '');
    if (/买棚|温室/.test(t)) glass += 1;
    else if (/买园|果园|树位/.test(t)) orch += 1;
    else if (/买地|份地/.test(t)) veg += 1;
  }
  setText('expVeg', veg ? `+${veg}` : '0');
  setText('expOrch', orch ? `+${orch}` : '0');
  setText('expGlass', glass ? `+${glass}` : '0');
}

function plotGrid(prefix, count, parcels) {
  const bySlot = new Map();
  for (const p of parcels || []) bySlot.set(Number(p.slot), p);
  const n = Math.max(Number(count) || 0, 0);
  const cells = Math.max(n, 7);
  let html = '';
  for (let i = 1; i <= cells; i += 1) {
    if (i > n) {
      html += '<span class="allo-plot"></span>';
      continue;
    }
    const p = bySlot.get(i);
    const planted = !!(p && (p.crop || (p.state && p.state !== '休耕')));
    const ready = !!(p && isReady(p.state));
    const cls = ['allo-plot'];
    if (planted) cls.push('on');
    if (ready) cls.push('ready');
    html += `<span class="${cls.join(' ')}">${esc(prefix)}${i}</span>`;
  }
  return html;
}

function readyCount(parcels) {
  return (parcels || []).filter((p) => isReady(p.state)).length;
}

function select(i) {
  state.selected = i;
  const list = state.list || [];
  document.querySelectorAll('.allo-person').forEach((el, idx) => {
    el.classList.toggle('is-active', idx === i);
  });
  const a = list[i];
  if (!a) return;

  const online = state.onlineIds.has(a.id);
  const total = landTotal(a);
  const vegN = Number(a.parcel_count || 0);
  const orchN = Number(a.orchard_count || 0);
  const glassN = Number(a.greenhouse_count || 0);
  const parts = splitParcels(a);
  const vegReady = readyCount(parts.veg);
  const orchReady = readyCount(parts.orch);
  const glassReady = readyCount(parts.glass);
  const ready = Number(a.ready_count || 0) || (vegReady + orchReady + glassReady);
  const rows = cropRows(a);

  setText('name', a.name || '—');
  setText(
    'meta',
    `Lv${a.level || 1} · ${online ? '在线' : `离线 ${ago(a.last_active_at)}`} · ${Number(a.tickets || 0).toLocaleString('zh-CN')} 工分票`,
  );
  setText('total', String(total));
  setText('vegCount', String(vegN));
  setText('orchCount', String(orchN));
  setText('glassCount', String(glassN));
  setText('rVeg', String(vegN));
  setText('rOrch', String(orchN));
  setText('rGlass', String(glassN));

  document.getElementById('vegGrid').innerHTML = plotGrid('#', vegN, parts.veg);
  document.getElementById('orchGrid').innerHTML = plotGrid('园', orchN, parts.orch);
  document.getElementById('glassGrid').innerHTML = plotGrid('棚', glassN, parts.glass);

  setText('vegReady', `${vegReady} 成熟`);
  setText('orchReady', `${orchReady} 结果`);
  setText('glassReady', `${glassReady} 成熟`);

  const statusBox = document.getElementById('statusList');
  statusBox.innerHTML = rows.length
    ? rows.slice(0, 8).map((r) => `
        <div class="allo-status-row">
          <code>${esc(r.token)}</code>
          <span>${esc(r.name)}</span>
          <b>${esc(r.state)}</b>
        </div>`).join('')
    : '<div class="allo-empty">这会儿地都空着。</div>';

  const recent = (a.recent && a.recent.length)
    ? a.recent
    : (a.latest ? [{ text: a.latest, created_at: a.last_active_at }] : []);
  document.getElementById('activity').innerHTML = recent.length
    ? recent.map((r) => `
        <div class="allo-activity-item">
          <time>${esc(ago(r.created_at))}</time>
          <div>
            <b>${esc(r.text)}</b>
            <span>${esc(a.name)} 的经营记录</span>
          </div>
        </div>`).join('')
    : '<div class="allo-empty">还没有动静。</div>';

  document.getElementById('miniLand').innerHTML = rows.length
    ? rows.slice(0, 5).map((r) => `
        <div class="allo-mini-land">
          <code>${esc(r.token)}</code>
          <span>${esc(r.name)}</span>
          <b>${esc(r.state)}</b>
        </div>`).join('')
    : '<div class="allo-empty">暂无在种地块。</div>';

  const rate = total ? Math.round((ready / total) * 100) : 0;
  const vegPct = total ? Math.round((vegN / total) * 100) : 0;
  setText('mReady', `${ready} 处`);
  setText('mRate', `${rate}%`);
  setText('mVeg', `${vegPct}%`);
  setText('mOther', `${total ? 100 - vegPct : 0}%`);
  setText('mRank', `#${String(i + 1).padStart(2, '0')}`);
  setText('mTotal', `${total} 处`);
  setText(
    'note',
    `${a.name || '这位岛民'} 当前登记 ${total} 处经营土地：菜地 ${vegN}、果园 ${orchN}、温室 ${glassN}。其中 ${ready} 处已经进入可收获或结果状态。`,
  );
}

function renderPeople(list, onlinePeople) {
  state.list = list || [];
  state.onlineIds = new Set((onlinePeople || []).map((x) => x.id));
  const shown = state.list.slice(0, 40);
  const box = document.getElementById('people');

  if (!shown.length) {
    box.innerHTML = '<div class="allo-empty">还没有管理员。去上手页登记。</div>';
    setText('name', '还没有管理员');
    setText('meta', '去上手页登记');
    return;
  }

  box.innerHTML = shown.map((a, i) => {
    const online = state.onlineIds.has(a.id);
    const total = landTotal(a);
    const rank = String(i + 1).padStart(2, '0');
    return `
      <button type="button" class="allo-person${i === state.selected ? ' is-active' : ''}" data-index="${i}">
        <span class="no">${rank}</span>
        <span>
          <b>${esc(a.name)}${online ? '<i class="allo-online-dot"></i>' : ''}</b>
          <small>Lv${esc(a.level || 1)} · ${esc(a.ready_count || 0)} 可收</small>
        </span>
        <span class="sum">${esc(total)}</span>
      </button>`;
  }).join('');

  box.querySelectorAll('.allo-person').forEach((btn) => {
    btn.addEventListener('click', () => select(Number(btn.dataset.index)));
  });
  if (state.selected >= shown.length) state.selected = 0;
  select(state.selected);
}

function renderAll(stats, allotments, chronicle) {
  state.chronicle = chronicle || [];
  renderHero(stats || {}, allotments || []);
  renderExpansion(chronicle || []);
  renderPeople(allotments || [], (stats && stats.online_people) || []);
}

async function loadJson(url, fallback) {
  try {
    const r = await fetch(url);
    if (!r.ok) return fallback;
    return await r.json();
  } catch (ex) {
    return fallback;
  }
}

async function loadAllotments() {
  const [s, a, ch] = await Promise.all([
    loadJson('/api/public/stats', {}),
    loadJson('/api/public/allotments', null),
    loadJson('/api/public/chronicle', []),
  ]);
  if (!Array.isArray(a)) throw 0;
  renderAll(s, a, ch);
}

loadAllotments().catch(() => {
  setText('stewards', '—');
  document.getElementById('people').innerHTML =
    '<div class="allo-empty">地籍暂时看不清。</div>';
  setText('name', '暂时看不清');
  setText('meta', '稍后再来，或去上手页。');
  setText('note', '地籍暂时看不清。稍后再来，或去上手页动手。');
});

setInterval(() => { loadAllotments().catch(() => {}); }, 20000);
