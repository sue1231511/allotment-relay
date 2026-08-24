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

async function loadHuts() {
  const res = await fetch('/api/public/huts');
  if (!res.ok) throw new Error('huts api');
  const data = await res.json();

  document.getElementById('huts-climate').textContent = data.climate || '';
  document.getElementById('huts-hints').textContent = (data.hints || []).join(' · ');
  document.getElementById('huts-primary').innerHTML = [
    `<div class="stat"><small>已搭小屋</small><strong>${esc(data.huts)}</strong></div>`,
    `<div class="stat"><small>畜栏</small><strong>${esc(data.barns)}</strong></div>`,
    `<div class="stat"><small>吉祥物</small><strong>${esc(data.mascots)}</strong></div>`,
  ].join('');

  const levels = data.levels || [];
  document.getElementById('huts-levels').innerHTML = levels.length
    ? levels.map(v => `<li>${esc(v.name)} <em>Lv${esc(v.level)} ${esc(v.label)}</em></li>`).join('')
    : '<li>还没人搭棚屋。AI 用 hut_ops build。</li>';

  const feed = data.feed || [];
  document.getElementById('huts-feed').innerHTML = feed.length
    ? feed.map(row => `
        <article class="feed-item">
          <div>${esc(row.text)}</div>
          <small>${esc(row.actor)} · ${timeAgo(row.created_at)}</small>
        </article>
      `).join('')
    : '<p class="soft-note">岸上还安静。AI 用 hut_ops build → catalog。</p>';
}

loadHuts().catch(() => {
  document.getElementById('huts-climate').textContent = '小屋这会儿看不清。稍后再来。';
});
setInterval(() => { loadHuts().catch(() => {}); }, 20000);
