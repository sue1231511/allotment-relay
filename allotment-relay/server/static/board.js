function medal(i) {
  return { 1: '①', 2: '②', 3: '③' }[i] || String(i);
}

function rowHtml(r, i, kind) {
  const top = i <= 3 ? ' is-top' : '';
  const score = kind === 'tickets'
    ? `<strong>${r.tickets}</strong> 票`
    : `<strong>Lv${r.level}</strong> ${r.title || ''}`;
  const sub = kind === 'tickets'
    ? `Lv${r.level} · ${r.title || ''}`
    : `${r.xp} 入账 · ${r.tickets} 票`;
  return `
    <li class="board-row${top}">
      <span class="board-rank">${medal(i)}</span>
      <span class="board-who">
        <b>${r.name}</b>
        <small>${r.badge || ''}</small>
      </span>
      <span class="board-score">${score}</span>
      <span class="board-sub">${sub}</span>
    </li>
  `;
}

function fill(id, rows, kind) {
  const el = document.getElementById(id);
  if (!rows || !rows.length) {
    el.innerHTML = '<li class="muted">尚无登记管理员</li>';
    return;
  }
  el.innerHTML = rows.map((r, i) => rowHtml(r, i + 1, kind)).join('');
}

async function load() {
  const data = await fetch('/api/public/board').then(r => r.json());
  const n = (data.tickets || []).length;
  document.getElementById('board-meta').innerHTML = [
    `<span>上榜 ${n}</span>`,
    '<span>票榜 · 现票</span>',
    '<span>等级榜 · 累计入账</span>',
  ].join('');
  fill('ticket-board', data.tickets, 'tickets');
  fill('level-board', data.levels, 'level');
}

load();
setInterval(load, 12000);
