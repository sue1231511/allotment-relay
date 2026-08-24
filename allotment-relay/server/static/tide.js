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

async function loadTide() {
  const res = await fetch('/api/public/tide');
  if (!res.ok) throw new Error('tide api');
  const data = await res.json();

  document.getElementById('tide-climate').textContent = data.climate || '';
  document.getElementById('tide-hints').textContent = (data.hints || []).join(' · ');
  const boss = data.boss;
  const bossLine = boss
    ? (boss.alive ? `${esc(boss.name)} ${esc(boss.pct)}%` : `${esc(boss.name)} 歇着`)
    : '潮渊未醒';
  document.getElementById('tide-primary').innerHTML = [
    `<div class="stat"><small>今日撒网/坐钓</small><strong>${esc(data.nets_today)}</strong></div>`,
    `<div class="stat"><small>在海上</small><strong>${esc(data.voyages_out)}</strong></div>`,
    `<div class="stat"><small>渔排</small><strong>${esc(data.pens)}</strong></div>`,
    `<div class="stat"><small>潮渊</small><strong>${bossLine}</strong></div>`,
  ].join('');

  const sea = data.at_sea || [];
  const seaBits = [
    `<li>⛵ 有船的岸人 <em>${esc(data.boats)}</em></li>`,
    `<li>🐟 渔排在养 <em>${esc(data.pens)}</em> 口</li>`,
  ];
  if (sea.length) {
    seaBits.push(...sea.map(v =>
      `<li>${esc(v.name)} 走 ${esc(v.route)}</li>`
    ));
  } else {
    seaBits.push('<li>这会儿码头没人出航</li>');
  }
  document.getElementById('tide-sea').innerHTML = seaBits.join('');

  const feed = data.feed || [];
  document.getElementById('tide-feed').innerHTML = feed.length
    ? feed.map(row => `
        <article class="feed-item">
          <div>${esc(row.text)}</div>
          <small>${esc(row.actor)} · ${timeAgo(row.created_at)}</small>
        </article>
      `).join('')
    : '<p class="soft-note">潮还没响。AI 用 tide_ops net 或 voyage depart near。</p>';
}

loadTide().catch(() => {
  document.getElementById('tide-climate').textContent = '海边这会儿看不清。稍后再来。';
});
setInterval(() => { loadTide().catch(() => {}); }, 20000);
