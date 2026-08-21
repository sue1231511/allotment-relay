async function load() {
  const [data, stats] = await Promise.all([
    fetch('/api/public/board').then((r) => r.json()),
    fetch('/api/public/stats').then((r) => r.json()).catch(() => null),
  ]);
  const n = (data.tickets || []).length;
  const live = (stats && stats.online) || 0;
  const people = (stats && stats.online_people) || [];
  document.getElementById('board-meta').innerHTML = [
    chip('online', `在线 ${live}${live ? ' · ' + people.map((p) => esc(p.name)).slice(0, 3).join('、') : ''}`, live ? 'has-live' : ''),
    `<span>上榜 ${n}</span>`,
  ].join('');
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
