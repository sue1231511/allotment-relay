function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmt(n) {
  return Number(n || 0).toLocaleString('zh-CN');
}

function padRank(n) {
  return String(n).padStart(2, '0');
}

function barWidth(value, max) {
  if (!max) return 8;
  return Math.max(8, Math.min(100, Math.round((Number(value) / max) * 100)));
}

function findMine(rows, name) {
  if (!name) return null;
  const i = rows.findIndex((r) => r.name === name);
  if (i < 0) return null;
  return { row: rows[i], rank: i + 1 };
}

function tideRow(p, i, kind) {
  const n = i + 1;
  const cls = n === 1 ? 'top1' : n === 2 ? 'top2' : n === 3 ? 'top3' : '';
  const title = p.display_title || p.title || '';
  const flavor = p.bond_flavor || '';
  const left = `
    <div class="tide-left">
      <div>
        <span class="name">${esc(p.name)}</span>
        <span class="sub">${kind === 'tickets'
          ? `Lv${esc(p.level)} · ${esc(title)}`
          : `${esc(flavor)}`}</span>
      </div>
      <span class="rank-num">${padRank(n)}</span>
    </div>`;
  const right = kind === 'tickets'
    ? `<div class="tide-right"><span class="score">${esc(fmt(p.tickets))} 票</span></div>`
    : `<div class="tide-right"><span class="score">${esc(fmt(p.island_bond))}<small>∞ · ${esc(flavor)}</small></span></div>`;
  return `
    <button type="button" class="tide-row ${cls}" data-steward="${esc(p.id)}" data-name="${esc(p.name)}">
      ${left}<div class="tide-node" aria-hidden="true"></div>${right}
    </button>`;
}

function renderBoard(kind, rows, boardId) {
  const el = document.getElementById(boardId);
  if (!rows.length) {
    el.innerHTML = '<p class="pl-empty" style="padding:18px 4px;color:var(--muted);font-size:13px">还没有人上榜。去上手页 enroll 之后就会出现。</p>';
    return;
  }
  el.innerHTML = rows.map((p, i) => tideRow(p, i, kind)).join('');
}

function renderMe(kind, mine, meId, unbound) {
  const el = document.getElementById(meId);
  if (unbound) {
    el.innerHTML = `
      <div class="board-me-inner">
        <div>
          <strong>你的名次</strong>
          <small><a href="/play">去上手页贴凭证</a> 后，这里会标出你。</small>
        </div>
        <div class="mine-r"><b>—</b></div>
      </div>`;
    return;
  }
  if (!mine) {
    el.innerHTML = `
      <div class="board-me-inner">
        <div>
          <strong>未进前 ${esc(window.__boardLimit || 20)}</strong>
          <small>继续干活，榜会看见你。</small>
        </div>
        <div class="mine-r"><b>—</b></div>
      </div>`;
    return;
  }
  const p = mine.row;
  el.innerHTML = `
    <div class="board-me-inner">
      <div>
        <strong>${esc(p.name)}</strong>
        <small>${kind === 'tickets'
          ? `当前持有 ${esc(fmt(p.tickets))} 票`
          : `岛缘 ${esc(fmt(p.island_bond))} ∞ · ${esc(p.bond_flavor || '')}`}</small>
      </div>
      <div class="mine-r">
        <b>#${esc(mine.rank)}</b>
        ${kind === 'tickets' ? `${esc(fmt(p.tickets))} 票` : `${esc(fmt(p.island_bond))} ∞`}
      </div>
    </div>`;
}

function renderTicketWing(data, mine) {
  const lead = data.ticket_lead;
  document.getElementById('ticket-lead-n').textContent = lead ? fmt(lead.tickets) : '—';
  document.getElementById('ticket-lead-gap').innerHTML = lead
    ? `领先第二名 <strong>+${esc(fmt(lead.gap_second))}</strong>`
    : '领先第二名 <strong>—</strong>';

  const top = (data.tickets || []).slice(0, 7);
  const maxT = top.length ? Number(top[0].tickets) || 1 : 1;
  document.getElementById('ticket-spark').innerHTML = top.length
    ? [...top].reverse().map((p) => `<i style="height:${barWidth(p.tickets, maxT)}%"></i>`).join('')
    : '';
  document.getElementById('ticket-spark-label').textContent = top.length ? `${top.length} 人` : '空';

  document.getElementById('wing-my-tickets').textContent = mine ? fmt(mine.row.tickets) : '—';
  document.getElementById('wing-my-ticket-rank').textContent = mine ? `#${mine.rank}` : '—';

  const rows = data.tickets || [];
  const gaps = [];
  if (rows.length >= 2) {
    gaps.push({ label: '#1→#2', value: rows[0].tickets - rows[1].tickets });
  }
  if (rows.length >= 3) {
    gaps.push({ label: '#2→#3', value: rows[1].tickets - rows[2].tickets });
  }
  if (mine && mine.rank > 1) {
    gaps.push({
      label: `#${mine.rank - 1}→你`,
      value: rows[mine.rank - 2].tickets - mine.row.tickets,
    });
  }
  if (mine && mine.rank < rows.length) {
    gaps.push({
      label: `你→#${mine.rank + 1}`,
      value: mine.row.tickets - rows[mine.rank].tickets,
    });
  }
  const maxGap = Math.max(1, ...gaps.map((g) => Math.abs(g.value)));
  document.getElementById('ticket-ladder').innerHTML = gaps.length
    ? gaps.map((g) => `
        <div class="ladder-row">
          <span>${esc(g.label)}</span>
          <em><i style="width:${barWidth(Math.abs(g.value), maxGap)}%"></i></em>
          <b>+${esc(fmt(Math.abs(g.value)))}</b>
        </div>`).join('')
    : '<div class="ladder-row"><span>差距</span><em><i style="width:8%"></i></em><b>—</b></div>';

  const notes = [];
  if (lead) notes.push(['榜首', `${lead.name} · ${fmt(lead.tickets)} 票`]);
  if (lead && lead.gap_second) notes.push(['与第二名', `+${fmt(lead.gap_second)}`]);
  if (rows[9]) notes.push(['第十名门槛', `${fmt(rows[9].tickets)} 票`]);
  document.getElementById('ticket-notes').innerHTML = notes.map(([a, b]) => `
    <div class="record"><em></em><span>${esc(a)}</span><span>${esc(b)}</span></div>
  `).join('') || '<div class="record"><em></em><span>暂无笔记</span><span>—</span></div>';
}

function bondRows(data) {
  return data.bonds || data.levels || [];
}

function renderLevelWing(data, mine) {
  const lead = data.bond_lead || data.level_lead;
  const rows = bondRows(data);
  document.getElementById('level-lead-n').textContent = lead ? fmt(lead.bond) : '—';
  document.getElementById('level-lead-next').innerHTML = lead
    ? `口感 <strong>${esc(lead.flavor || '')}</strong>`
    : '口感 <strong>—</strong>';

  if (lead) {
    const hasNext = lead.next_need != null && Number(lead.to_next) > 0;
    document.getElementById('level-progress-label').textContent = hasNext
      ? `${lead.flavor || ''} → ${lead.next_label || ''}`
      : (lead.flavor || '最高口感');
    document.getElementById('level-progress-bar').style.width = `${lead.progress_pct || 0}%`;
    document.getElementById('level-progress-cur').textContent = fmt(lead.bond);
    document.getElementById('level-progress-pct').textContent = `${lead.progress_pct || 0}%`;
    document.getElementById('level-progress-next').textContent = hasNext
      ? fmt(lead.next_need)
      : '无上限';
  }

  document.getElementById('wing-my-level').textContent = mine ? fmt(mine.row.island_bond) : '—';
  document.getElementById('wing-my-xp').textContent = mine ? (mine.row.bond_flavor || '—') : '—';

  const notes = data.notes || {};
  const fifth = rows[4];
  const ladder = [
    { label: '榜首岛缘', value: lead ? lead.bond : 0, text: lead ? fmt(lead.bond) : '—' },
    { label: '前十门槛', value: notes.top10_bond_floor || 0, text: notes.top10_bond_floor ? fmt(notes.top10_bond_floor) : '—' },
    { label: '你的位置', value: mine ? mine.row.island_bond : 0, text: mine ? fmt(mine.row.island_bond) : '—' },
    {
      label: '距前五',
      value: mine && fifth
        ? Math.max(0, fifth.island_bond - mine.row.island_bond)
        : 0,
      text: mine && fifth
        ? (fifth.island_bond > mine.row.island_bond
          ? `还差 ${fmt(fifth.island_bond - mine.row.island_bond)}`
          : '已进前五')
        : '—',
    },
  ];
  const maxL = Math.max(1, ...ladder.map((x) => Number(x.value) || 0), lead ? lead.bond : 1);
  document.getElementById('level-ladder').innerHTML = ladder.map((g) => `
    <div class="ladder-row">
      <span>${esc(g.label)}</span>
      <em><i style="width:${barWidth(g.value || 1, maxL)}%"></i></em>
      <b>${esc(g.text)}</b>
    </div>
  `).join('');

  const levelNotes = [];
  if (lead) levelNotes.push(['最高岛缘', `${fmt(lead.bond)} · ${lead.flavor || ''}`]);
  if (lead && lead.gap_second) levelNotes.push(['与第二名', `+${fmt(lead.gap_second)}`]);
  if (notes.avg_bond) levelNotes.push(['上榜均缘', fmt(notes.avg_bond)]);
  if (notes.top10_bond_floor) levelNotes.push(['前十门槛', fmt(notes.top10_bond_floor)]);
  document.getElementById('level-notes').innerHTML = levelNotes.map(([a, b]) => `
    <div class="record"><em></em><span>${esc(a)}</span><span>${esc(b)}</span></div>
  `).join('') || '<div class="record"><em></em><span>暂无笔记</span><span>—</span></div>';
}

async function loadBoard() {
  const [data, stats, bound] = await Promise.all([
    fetch('/api/public/board').then((r) => r.json()),
    fetch('/api/public/stats').then((r) => r.json()).catch(() => null),
    (typeof fetchBoundSteward === 'function' ? fetchBoundSteward() : Promise.resolve(null)),
  ]);

  window.__boardLimit = data.limit || 20;
  const online = (stats && stats.online) || 0;
  const rows = bondRows(data);
  const count = data.count || Math.max((data.tickets || []).length, rows.length);

  document.getElementById('pill-online').textContent = `在线 ${online}`;
  document.getElementById('pill-count').textContent = `上榜 ${count}`;
  document.getElementById('strip-online').textContent = String(online);

  const myName = bound && bound.name ? bound.name : '';
  const ticketMine = findMine(data.tickets || [], myName);
  const levelMine = findMine(rows, myName);

  if (myName) {
    document.getElementById('strip-ticket-rank').textContent = ticketMine ? `#${ticketMine.rank}` : '未进榜';
    document.getElementById('strip-ticket-val').textContent = ticketMine
      ? `${fmt(ticketMine.row.tickets)} 票`
      : myName;
    document.getElementById('strip-level-rank').textContent = levelMine ? `#${levelMine.rank}` : '未进榜';
    document.getElementById('strip-level-val').textContent = levelMine
      ? `${fmt(levelMine.row.island_bond)} ∞ · ${levelMine.row.bond_flavor || ''}`
      : myName;
  }

  renderBoard('tickets', data.tickets || [], 'ticketsBoard');
  renderBoard('bond', rows, 'levelBoard');
  renderMe('tickets', ticketMine, 'ticketsMe', !myName);
  renderMe('level', levelMine, 'levelMe', !myName);
  renderTicketWing(data, ticketMine);
  renderLevelWing(data, levelMine);
}

document.addEventListener('click', (e) => {
  const hit = e.target.closest('[data-steward]');
  if (!hit) return;
  e.preventDefault();
  location.href = '/play?go=neighbors';
});

loadBoard().catch(() => {
  document.getElementById('ticketsBoard').innerHTML =
    '<p style="padding:18px 4px;color:var(--muted)">榜单这会儿看不清。</p>';
});
setInterval(() => { loadBoard().catch(() => {}); }, 12000);
