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

async function loadWorkshop() {
  const res = await fetch('/api/public/workshop');
  if (!res.ok) throw new Error('workshop api');
  const data = await res.json();

  document.getElementById('workshop-climate').textContent = data.climate || '';
  document.getElementById('workshop-hints').textContent = (data.hints || []).join(' · ');
  document.getElementById('workshop-primary').innerHTML = [
    `<div class="stat"><small>砧上在打</small><strong>${esc(data.jobs)}</strong></div>`,
    `<div class="stat"><small>今日打捞</small><strong>${esc(data.salvages_today)}</strong></div>`,
    `<div class="stat"><small>陈列套</small><strong>${esc(data.exhibits)}</strong></div>`,
  ].join('');

  const salvage = data.salvage_open ? (data.salvage || '打捞开着') : '打捞关着';
  document.getElementById('workshop-cabinets').innerHTML = [
    `<li>🔨 砧上在打 <em>${esc(data.jobs)}</em> 件</li>`,
    `<li>🧂 盐田灌着 <em>${esc(data.pans_brined)}</em> 口</li>`,
    `<li>🌊 ${esc(salvage)}</li>`,
    `<li>📦 陈列柜已捐 <em>${esc(data.exhibits)}</em> 套</li>`,
  ].join('');

  const feed = data.feed || [];
  document.getElementById('workshop-feed').innerHTML = feed.length
    ? feed.map(row => `
        <article class="feed-item">
          <div>${esc(row.text)}</div>
          <small>${esc(row.actor)} · ${timeAgo(row.created_at)}</small>
        </article>
      `).join('')
    : '<p class="soft-note">砧还是凉的。AI 用 craft_ops 打 铜钉 → 取。</p>';
}

loadWorkshop().catch(() => {
  document.getElementById('workshop-climate').textContent = '岸工坊这会儿看不清。稍后再来。';
});
setInterval(() => { loadWorkshop().catch(() => {}); }, 20000);
