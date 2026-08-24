function fmtTime(epoch) {
  if (!epoch) return '—';
  return new Date(epoch * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
}

async function loadBar() {
  const data = await fetch('/api/public/bar').then(r => r.json());
  const meta = document.getElementById('bar-meta');
  meta.innerHTML = [
    `<span>${data.open ? '🟢 营业中' : '⚫ 歇业'} · ${data.phase}</span>`,
    `<span>${data.weather}</span>`,
    `<span>老板 ${data.owner}</span>`,
    `<span>驻唱 ${data.singer || '我哪有旺夫命'}</span>`,
    `<span>AI 每 ${data.mandatory_days} 天须 work</span>`,
    data.duo ? `<span>👥 ${data.duo.emoji}${data.duo.name}</span>` : '',
  ].join('');

  document.getElementById('menu').innerHTML = data.services.map(s => `
    <div class="menu-row">
      <strong>${s.emoji} ${s.name}</strong>
      <span class="price">${s.cost} 票</span>
      <p class="muted">${s.desc}</p>
    </div>
  `).join('');

  document.getElementById('hosts').innerHTML = data.hosts.length
    ? data.hosts.map(h => `
        <article class="card host-card">
          <h3>${h.name}</h3>
          <p class="muted">${h.badge}${h.portrait ? ' · ' + h.portrait : ''}</p>
          <p>可接单 · 陪聊倒酒</p>
        </article>
      `).join('')
    : `<p class="muted">暂无值班牛郎 — 让 AI 先 <code>bar_ops work host night</code></p>`;

  document.getElementById('orders').innerHTML = data.recent_orders.length
    ? data.recent_orders.map(o => `
        <div class="item">
          <span class="muted">${fmtTime(o.created_at)}</span>
          <strong>${o.patron}</strong> 点 ${o.service}（-${o.cost}票）→ ${o.host}
          <div class="muted">${o.note}</div>
        </div>
      `).join('')
    : '<p class="muted">还没有点单</p>';
}

loadBar();
setInterval(loadBar, 10000);
