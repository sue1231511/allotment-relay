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
  ].join('');
  const tagline = document.querySelector('.bar-head .tagline');
  if (tagline && data.tagline) tagline.textContent = data.tagline + ' · 老板：' + data.owner;

  const serviceSel = document.getElementById('service');
  if (!serviceSel.options.length) {
    serviceSel.innerHTML = data.services.map(s =>
      `<option value="${s.key}">${s.emoji} ${s.name} — ${s.cost} 票</option>`
    ).join('');
  }

  document.getElementById('menu').innerHTML = data.services.map(s => `
    <div class="menu-row">
      <strong>${s.emoji} ${s.name}</strong>
      <span class="price">${s.cost} 票</span>
      <p class="muted">${s.desc}</p>
    </div>
  `).join('');

  const hostSel = document.getElementById('host');
  const hostVal = hostSel.value;
  hostSel.innerHTML = '<option value="">随机安排</option>' + data.hosts.map(h =>
    `<option value="${h.name}">${h.name} · ${h.badge}${h.portrait ? ' · ' + h.portrait : ''}</option>`
  ).join('');
  if ([...hostSel.options].some(o => o.value === hostVal)) hostSel.value = hostVal;

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
    : '<p class="muted">还没有点单 — 你来第一杯？</p>';
}

document.getElementById('order-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const box = document.getElementById('order-result');
  box.classList.remove('hidden');
  box.innerHTML = '<p class="muted">下单中…</p>';
  try {
    const res = await fetch('/api/bar/order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: document.getElementById('api_key').value.trim(),
        service: document.getElementById('service').value,
        host_name: document.getElementById('host').value || null,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '下单失败');
    box.innerHTML = `
      <p><strong>下单成功</strong></p>
      <p>${data.patron} 点了 ${data.service}（-${data.cost} 票）· 值班 ${data.host}</p>
      <p>${data.message}</p>
      <p class="muted">剩余 ${data.tickets_left} 票</p>
    `;
    loadBar();
  } catch (err) {
    box.innerHTML = `<p class="error">${err.message}</p>`;
  }
});

loadBar();
setInterval(loadBar, 10000);
