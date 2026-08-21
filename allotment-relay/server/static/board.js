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
    '<span>票榜 · 现票</span>',
    '<span>等级榜 · 累计入账</span>',
  ].join('');
  fillBoard(document.getElementById('ticket-board'), data.tickets, 'tickets');
  fillBoard(document.getElementById('level-board'), data.levels, 'level');
}

document.getElementById('board-meta').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-panel="online"]');
  if (!btn) return;
  location.href = '/allotments#online';
});

bindStewardHits(document);
load();
setInterval(load, 12000);
