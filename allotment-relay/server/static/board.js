async function load() {
  const [data, stats] = await Promise.all([
    fetch('/api/public/board').then((r) => r.json()),
    fetch('/api/public/stats').then((r) => r.json()).catch(() => null),
  ]);
  const n = (data.tickets || []).length;
  const live = (stats && stats.online) || 0;
  const people = (stats && stats.online_people) || [];
  const namesHint = people.length
    ? people.map((p) => p.name).slice(0, 6).join('、')
    : '';
  document.getElementById('board-meta').innerHTML = [
    chip(
      'online',
      `<span class="stat-chip-label">在线</span><span class="stat-chip-value">${live}</span>`,
      live ? 'has-live' : '',
    ),
    `<span class="stat-chip stat-chip--static" title="工分票榜与等级榜上榜人数"><span class="stat-chip-label">上榜</span><span class="stat-chip-value">${n}</span></span>`,
  ].join('');
  const onlineChip = document.querySelector('#board-meta [data-panel="online"]');
  if (onlineChip && namesHint) onlineChip.title = namesHint;
  const onlineN = document.getElementById('board-online-n');
  if (onlineN) onlineN.textContent = live ? String(live) : '0';
  fillBoard(document.getElementById('ticket-board'), data.tickets, 'tickets');
  fillBoard(document.getElementById('level-board'), data.levels, 'level');
}

function jumpOnline() {
  location.href = '/allotments#online';
}

document.getElementById('board-meta').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-panel="online"]');
  if (!btn) return;
  jumpOnline();
});

document.getElementById('board-online-card')?.addEventListener('click', jumpOnline);

bindStewardHits(document);
load();
setInterval(load, 12000);
