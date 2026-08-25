function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function clock(epoch) {
  if (!epoch) return '—';
  const d = new Date(Number(epoch) * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

async function loadHui() {
  const data = await fetch('/api/public/hui').then((r) => r.json());
  const league = data.league || {};
  const done = Boolean(league.completed);
  const pct = league.target
    ? Math.min(100, Math.round((Number(league.progress) || 0) / Number(league.target) * 100))
    : 0;

  document.getElementById('hui-meta').innerHTML = [
    `<span>值事 ${esc(data.clerk || '阿簿')}</span>`,
    `<span>公仓 ${esc(data.larder_kinds ?? 0)} 种</span>`,
    `<span>公物在架 ${esc(data.commons_live ?? 0)}</span>`,
  ].join('');

  document.getElementById('hui-strip').innerHTML =
    `<span class="dot"></span><span>${esc(data.clerk || '阿簿')}：「${esc(data.line || '坐。先报名字。')}」</span>`;

  document.getElementById('hui-week').innerHTML = `
    <div class="hui-card">
      <small>本周牌子</small>
      <strong>${esc(league.label || '尚未写上')}</strong>
      <p>${done ? '本周已收齐。' : `${esc(league.progress || 0)} / ${esc(league.target || 0)}`}</p>
      <div class="hui-progress" aria-hidden="true"><span style="width:${pct}%"></span></div>
    </div>
  `;

  const larder = data.larder || [];
  document.getElementById('hui-larder').innerHTML = larder.length
    ? larder.map((it) => (
      `<div class="hui-item"><span>${esc(it.name)}</span><small>×${esc(it.qty)}</small></div>`
    )).join('')
    : '<p class="pl-empty">公仓是空的。欢迎捐。</p>';

  const beacons = data.beacons || [];
  document.getElementById('hui-beacons').innerHTML = beacons.length
    ? beacons.map((b) => (
      `<div class="hui-notice"><span>${esc(b.body)}</span><small>${esc(b.author)}</small></div>`
    )).join('')
    : '<p class="pl-empty">墙上还空着。</p>';

  const recent = data.recent || [];
  document.getElementById('hui-feed').innerHTML = recent.length
    ? recent.map((r) => (
      `<div class="hui-log">${esc(r.text)}<small> · ${clock(r.created_at)}</small></div>`
    )).join('')
    : '<p class="pl-empty">还没有人来办事。</p>';
}

loadHui();
setInterval(loadHui, 12000);
