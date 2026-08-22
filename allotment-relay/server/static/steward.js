function fmtTime(epoch) {
  if (!epoch) return '—';
  return new Date(epoch * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function renderDashboard(data) {
  document.getElementById('steward-dashboard').classList.remove('hidden');
  document.getElementById('steward-error').classList.add('hidden');

  document.getElementById('profile').innerHTML = [
    `<span><strong>${esc(data.name)}</strong> · ${esc(data.badge)}</span>`,
    `<span>Lv${data.level} ${esc(data.title)}</span>`,
    `<span>${data.tickets} 票</span>`,
    `<span>${esc(data.motto || '—')}</span>`,
    data.portrait ? `<span>${esc(data.portrait)}</span>` : '',
    `<span class="muted">${esc(data.climate)}</span>`,
  ].filter(Boolean).join('');

  const pulse = data.pulse;
  const pulseLine = pulse
    ? `<p class="muted pulse-${pulse.kind}">全服脉冲 · ${esc(pulse.label)}（约 ${Math.floor(pulse.remaining / 60)} 分）</p>`
    : '';

  document.getElementById('meters').innerHTML = [
    `<p>${esc(data.meter_lines.survival)}</p>`,
    `<p>${esc(data.meter_lines.health)}</p>`,
    `<p>${esc(data.meter_lines.energy)}</p>`,
    `<p>${esc(data.meter_lines.bar_duty)}</p>`,
    data.voyage ? `<p>出海：${esc(data.voyage)}</p>` : '',
    pulseLine,
  ].filter(Boolean).join('');

  document.getElementById('parcels').innerHTML = data.parcels.length
    ? data.parcels.map(p => `
        <div class="item">
          <strong>#${p.slot}${p.greenhouse ? ' 🪴' : ''}</strong>
          <span>${esc(p.label)}</span>
        </div>
      `).join('')
    : '<p class="muted">暂无份地</p>';

  document.getElementById('stock').innerHTML = data.stock.length
    ? `<p class="muted">共 ${data.stock_count} 种</p>` + data.stock.map(i => `
        <div class="item">
          <strong>${esc(i.name)}</strong> x${i.qty}
          <span class="muted">${esc(i.item)}</span>
        </div>
      `).join('')
    : '<p class="muted">行囊是空的</p>';

  const flags = [];
  if (data.flags.greenhouse) flags.push('温室');
  if (data.flags.hut_built) flags.push('小屋');
  if (data.flags.barn_built) flags.push('畜栏');
  if (data.flags.eatery_open) flags.push('小馆');
  if (data.flags.boat) flags.push('有船');

  const incidentHtml = data.incidents.length
    ? data.incidents.map(i => `
        <div class="item">
          <strong>#${i.id}</strong> ${esc(i.label)}
          <span class="muted">repair ${i.repair_tickets} 票</span>
        </div>
      `).join('')
    : '<p class="muted">无未处理意外</p>';

  document.getElementById('ops').innerHTML = [
    `<p>集市摊格 <strong>${data.market.used}/${data.market.cap}</strong></p>`,
    flags.length ? `<p class="muted">${flags.join(' · ')}</p>` : '',
    '<h3 class="muted">意外</h3>',
    incidentHtml,
  ].join('');

  document.getElementById('gifts').innerHTML = data.gifts.length
    ? data.gifts.map(g => `
        <div class="item">
          <span class="muted">${fmtTime(g.created_at)}</span>
          <strong>[${esc(g.kind)}] ${esc(g.who)}</strong>
          <div class="muted">${esc(g.text)}</div>
        </div>
      `).join('')
    : '<p class="muted">还没有收礼或酒吧打赏记录</p>';
}

document.getElementById('steward-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errBox = document.getElementById('steward-error');
  errBox.classList.add('hidden');
  try {
    const res = await fetch('/api/steward/dashboard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: document.getElementById('api_key').value.trim() }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '查询失败');
    renderDashboard(data);
  } catch (err) {
    errBox.classList.remove('hidden');
    errBox.innerHTML = `<p class="muted">${esc(err.message)}</p>`;
    document.getElementById('steward-dashboard').classList.add('hidden');
  }
});
