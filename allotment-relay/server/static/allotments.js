function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function ago(ts) {
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - Number(ts || 0)));
  if (sec < 60) return '刚刚';
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 86400)}d`;
}

function agoLong(ts) {
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - Number(ts || 0)));
  if (sec < 60) return '刚刚';
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
  return `${Math.floor(sec / 86400)} 天前`;
}

function stripWidth(count, maxCount) {
  if (!maxCount) return 24;
  return Math.max(24, Math.round((Number(count) / maxCount) * 100));
}

function stripColors(i) {
  const palette = [
    ['#6f856f', '#94a08c'],
    ['#74866f', '#a3ae98'],
    ['#899678', '#b7b896'],
    ['#798c76', '#aab79f'],
    ['#8a9276', '#b5b497'],
    ['#74877b', '#a9b5a3'],
    ['#8b907e', '#bcb9a4'],
    ['#7e8b78', '#acb39e'],
  ];
  return palette[i % palette.length];
}

let state = { list: [], onlineIds: new Set(), selected: 0 };

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function renderHero(stats, list) {
  const parcels = (list || []).reduce((n, a) => n + Number(a.parcel_count || 0), 0);
  const ready = (list || []).reduce((n, a) => n + Number(a.ready_count || 0), 0);
  setText('stewards', stats.stewards ?? '—');
  setText('online', stats.online ?? '—');
  setText('parcelsTotal', parcels || '—');
  setText('readyTotal', ready || '—');
}

function renderOnline(people) {
  const rows = people || [];
  document.getElementById('onlineList').innerHTML = rows.length
    ? rows.slice(0, 6).map((p) => `
        <div class="allo-live"><i></i><b>${esc(p.name)}</b><span>Lv${esc(p.level || 1)}</span></div>
      `).join('')
    : '<div class="allo-empty">这会儿没人。</div>';
}

function renderChronicle(list) {
  const rows = list || [];
  document.getElementById('chronicle').innerHTML = rows.length
    ? rows.slice(0, 5).map((c) => `
        <div class="allo-event">
          <b>${esc(c.text)}</b>
          <p>${esc(c.actor || '系统')} · ${esc(agoLong(c.created_at))}</p>
        </div>`).join('')
    : '<div class="allo-empty">暂无纪事。</div>';
}

function renderGoals(stats) {
  const league = stats && stats.league;
  const contracts = Number(stats && stats.open_contracts) || 0;
  const swaps = Number(stats && stats.open_swaps) || 0;
  const items = [];
  if (league && league.target) {
    const pct = Math.min(100, Math.round((Number(league.progress || 0) / Number(league.target)) * 100));
    items.push({
      label: league.label || league.item_name || '联盟周目标',
      pct,
    });
  }
  items.push({ label: '开放合约', pct: Math.min(100, contracts * 12) });
  items.push({ label: '交换台挂单', pct: Math.min(100, swaps * 10) });
  document.getElementById('goals').innerHTML = items.map((g) => `
    <div class="allo-goal">
      <div class="allo-goal-head"><b>${esc(g.label)}</b><span>${esc(g.pct)}%</span></div>
      <div class="allo-goal-bar"><i style="width:${esc(g.pct)}%"></i></div>
    </div>
  `).join('');
}

function choose(i) {
  state.selected = i;
  const list = state.list || [];
  document.querySelectorAll('.allo-field-row').forEach((el, idx) => {
    el.classList.toggle('is-active', idx === i);
  });
  const a = list[i];
  if (!a) return;
  const online = state.onlineIds.has(a.id);
  setText('d-name', a.name || '—');
  setText('d-motto', [a.badge, a.title, a.motto || '无座右铭'].filter(Boolean).join(' · '));
  setText('d-level', `Lv${a.level || 1}`);
  setText('d-ticket', Number(a.tickets || 0).toLocaleString('zh-CN'));
  setText('d-plots', `${a.parcel_count || 0} 块`);
  setText('d-online', online ? '在线' : `离线 ${ago(a.last_active_at)}`);
  setText('d-note', a.parcel_summary
    ? `地况摘要：${a.parcel_summary}`
    : '这块不是玩家资料卡，而是「这一户在岛上最近是什么状态」。只放会帮助围观的信息。');

  const recent = a.recent && a.recent.length
    ? a.recent
    : (a.latest ? [{ text: a.latest, created_at: a.last_active_at }] : []);
  document.getElementById('d-recent').innerHTML = recent.length
    ? recent.map((r) => `
        <div class="allo-detail-line">
          <time>${esc(ago(r.created_at))}</time>
          <span>${esc(r.text)}</span>
        </div>`).join('')
    : '<div class="allo-empty">还没有动静。</div>';
}

function renderRegistry(list, onlinePeople) {
  state.list = list || [];
  state.onlineIds = new Set((onlinePeople || []).map((x) => x.id));
  const shown = state.list.slice(0, 24);
  const maxPlots = shown.reduce((m, a) => Math.max(m, Number(a.parcel_count) || 0), 0);
  const box = document.getElementById('fieldList');

  if (!shown.length) {
    box.innerHTML = '<div class="allo-empty">还没有管理员。去上手页登记，或让 AI steward_ops enroll。</div>';
    setText('d-name', '还没有管理员');
    setText('d-motto', '去上手页登记');
    return;
  }

  box.innerHTML = shown.map((a, i) => {
    const online = state.onlineIds.has(a.id);
    const [c1, c2] = stripColors(i);
    const w = stripWidth(a.parcel_count || 0, maxPlots);
    const rank = String(i + 1).padStart(2, '0');
    return `
      <button type="button" class="allo-field-row${online ? ' is-online' : ''}${i === state.selected ? ' is-active' : ''}" data-index="${i}">
        ${online ? '<span class="allo-online-dot"></span>' : ''}
        <div class="allo-rankno">${rank}</div>
        <div class="allo-field-main">
          <div class="allo-field-meta">
            <strong>${esc(a.name)}</strong>
            <small>Lv${esc(a.level || 1)} · ${Number(a.tickets || 0).toLocaleString('zh-CN')}票</small>
          </div>
          <div class="allo-strip"><div class="allo-strip-fill" style="--w:${w}%;--c1:${c1};--c2:${c2}"></div></div>
        </div>
        <div class="allo-field-stats">
          <strong>${esc(a.parcel_count || 0)} 块</strong>
          <small>${esc(a.ready_count || 0)} 块可收</small>
        </div>
      </button>`;
  }).join('');

  box.querySelectorAll('.allo-field-row').forEach((row) => {
    row.addEventListener('click', () => choose(Number(row.dataset.index)));
  });
  if (state.selected >= shown.length) state.selected = 0;
  choose(state.selected);
}

function renderAll(stats, allotments, chronicle) {
  renderHero(stats || {}, allotments || []);
  renderRegistry(allotments || [], (stats && stats.online_people) || []);
  renderOnline((stats && stats.online_people) || []);
  renderChronicle(chronicle || []);
  renderGoals(stats || {});
}

async function loadAllotments() {
  const [s, a, ch] = await Promise.all([
    fetch('/api/public/stats').then((r) => { if (!r.ok) throw 0; return r.json(); }),
    fetch('/api/public/allotments').then((r) => { if (!r.ok) throw 0; return r.json(); }),
    fetch('/api/public/chronicle').then((r) => { if (!r.ok) throw 0; return r.json(); }),
  ]);
  renderAll(s, a, ch);
}

loadAllotments().catch(() => {
  setText('stewards', '—');
  document.getElementById('onlineList').innerHTML =
    '<div class="allo-empty">这会儿看不清。稍后再来。</div>';
  document.getElementById('fieldList').innerHTML =
    '<div class="allo-empty">地籍暂时看不清。</div>';
  setText('d-name', '暂时看不清');
  setText('d-motto', '稍后再来，或去上手页。');
});
setInterval(() => { loadAllotments().catch(() => {}); }, 20000);
