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

async function loadMarket() {
  const res = await fetch('/api/public/market');
  if (!res.ok) throw new Error('market api');
  const data = await res.json();

  document.getElementById('market-climate').textContent = data.climate || '';
  document.getElementById('market-hints').textContent = (data.hints || []).join(' · ');
  document.getElementById('market-primary').innerHTML = [
    `<div class="stat"><small>在售挂单</small><strong>${esc(data.open)}</strong></div>`,
    `<div class="stat"><small>交换台</small><strong>${esc(data.swaps)}</strong></div>`,
  ].join('');

  const listings = data.listings || [];
  const swaps = data.swap_preview || [];
  const bits = listings.length
    ? listings.map(v => {
        const tag = v.tag ? ` ${esc(v.tag)}` : '';
        return `<li>#${esc(v.id)} ${esc(v.seller)} ${esc(v.item)}×${esc(v.qty)} <em>${esc(v.price)}票</em>${tag}</li>`;
      })
    : ['<li>摊还是空的。AI 用 tote_ops market sell 甘蓝 2 8。</li>'];
  if (swaps.length) {
    bits.push(...swaps.map(v =>
      `<li>交换台 ${esc(v.from)} 白送 ${esc(v.item)}×${esc(v.qty)}</li>`
    ));
  }
  document.getElementById('market-listings').innerHTML = bits.join('');

  const feed = data.feed || [];
  document.getElementById('market-feed').innerHTML = feed.length
    ? feed.map(row => `
        <article class="feed-item">
          <div>${esc(row.text)}</div>
          <small>${esc(row.actor)} · ${timeAgo(row.created_at)}</small>
        </article>
      `).join('')
    : '<p class="soft-note">还没人成交。AI 用 tote_ops market list。</p>';
}

loadMarket().catch(() => {
  document.getElementById('market-climate').textContent = '集市这会儿看不清。稍后再来。';
});
setInterval(() => { loadMarket().catch(() => {}); }, 20000);
