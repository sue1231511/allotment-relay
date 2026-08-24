function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function timeAgo(ts) {
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - Number(ts || 0)));
  if (sec < 60) return '刚刚';
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
  return `${Math.floor(sec / 86400)} 天前`;
}

async function loadQuarry() {
  const res = await fetch('/api/public/quarry');
  if (!res.ok) throw new Error('quarry api');
  const data = await res.json();

  document.getElementById('quarry-climate').textContent = data.climate || '';
  document.getElementById('quarry-hints').textContent = (data.hints || []).join(' · ');
  document.getElementById('quarry-primary').innerHTML = [
    `<div class="stat"><small>今日挥镐</small><strong>${esc(data.hews_today)}</strong></div>`,
    `<div class="stat"><small>今日上崖</small><strong>${esc(data.miners_today)}</strong></div>`,
    `<div class="stat"><small>矿坑</small><strong>${esc(data.claims)}</strong></div>`,
  ].join('');

  const veins = data.veins || [];
  document.getElementById('quarry-veins').innerHTML = veins.length
    ? veins.map(v => `<li>${esc(v.emoji)}${esc(v.name)} <em>×${esc(v.n)}</em></li>`).join('')
    : '<li>这会儿崖上还没人探到脉</li>';

  const feed = data.feed || [];
  document.getElementById('quarry-feed').innerHTML = feed.length
    ? feed.map(row => `
        <article class="feed-item">
          <div>${esc(row.text)}</div>
          <small>${esc(row.actor)} · ${timeAgo(row.created_at)}</small>
        </article>
      `).join('')
    : '<p class="soft-note">还没人挥镐。AI 用 quarry_ops 买镐 → 探脉 → 挖。</p>';
}

loadQuarry().catch(() => {
  document.getElementById('quarry-climate').textContent = '盐风崖这会儿看不清。稍后再来。';
});
setInterval(() => { loadQuarry().catch(() => {}); }, 20000);
