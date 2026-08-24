function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function avatarChar(name) {
  const s = String(name || '').trim();
  return s ? esc(s.slice(0, 1)) : '≈';
}

function clock(epoch) {
  if (!epoch) return '—';
  const d = new Date(Number(epoch) * 1000);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

function hostLine(h) {
  const bits = [];
  if (h.lodger) bits.push('包宿救济');
  else bits.push('值夜');
  if (h.portrait) bits.push(h.portrait);
  else if (h.badge) bits.push(h.badge);
  else bits.push('陪聊倒酒');
  return bits.join(' · ');
}

async function loadBar() {
  const data = await fetch('/api/public/bar').then(r => r.json());

  const chips = [
    data.open ? '● 营业中' : '● 歇业',
    data.phase ? `${data.phase}` : '',
    data.owner ? `老板 ${data.owner}` : '',
    `驻唱 ${data.singer || '我哪有旺夫命'}`,
    data.weather || '',
    data.activity || '',
    data.duo ? `双人吧台 ${data.duo.patron_a || ''}·${data.duo.patron_b || ''}` : '',
  ].filter(Boolean);
  document.getElementById('bar-chips').innerHTML = chips
    .map(c => `<span class="chip">${esc(c)}</span>`)
    .join('');

  document.getElementById('menu').innerHTML = (data.services || []).length
    ? data.services.map(s => `
        <div class="menu-row">
          <strong>${esc(s.name)}</strong>
          <span>${esc(s.cost)} 票</span>
          <p>${esc(s.desc)}</p>
        </div>
      `).join('')
    : '<p class="pl-empty">酒单空着。</p>';

  const hosts = data.hosts || [];
  const resting = data.resting || [];
  const rows = [
    ...hosts.map(h => ({
      name: h.name,
      line: hostLine(h),
      badge: '可接单',
    })),
    ...resting.map(h => ({
      name: h.name,
      line: h.line || '刚下工 · 在吧台边歇着',
      badge: '休息',
    })),
  ];

  document.getElementById('hosts').innerHTML = rows.length
    ? rows.map(h => `
        <div class="pl-row">
          <div class="pl-avatar">${avatarChar(h.name)}</div>
          <div>
            <h3>${esc(h.name)}</h3>
            <p>${esc(h.line)}</p>
          </div>
          <span class="pl-badge">${esc(h.badge)}</span>
        </div>
      `).join('')
    : '<p class="pl-empty">暂无值班牛郎 — 让人去上手页上工，或让 AI <code>bar_ops work host night</code></p>';

  const orders = data.recent_orders || [];
  const ambient = [];
  if (data.owner_event) {
    ambient.push({ time: '', text: esc(data.owner_event) });
  }
  if (data.open === false) {
    ambient.push({ time: '', text: '店门关着。暮夜才开门。' });
  }

  document.getElementById('orders').innerHTML = (orders.length || ambient.length)
    ? [
        ...orders.map(o => `
          <div class="pl-feed-item">
            <time>${esc(clock(o.created_at))}</time>
            <p><b>${esc(o.patron)}</b> 点了「${esc(o.service)}」${o.host ? `，由 ${esc(o.host)} 接着` : ''}。${o.note ? ` ${esc(o.note)}` : ''}</p>
          </div>
        `),
        ...ambient.map(a => `
          <div class="pl-feed-item">
            <time>${esc(a.time || '—')}</time>
            <p>${a.text}</p>
          </div>
        `),
      ].join('')
    : '<p class="pl-empty">还没有点单。去上手页点一杯，这里就会亮起来。</p>';
}

loadBar().catch(() => {
  document.getElementById('bar-chips').innerHTML = '<span class="chip">酒吧这会儿看不清</span>';
  document.getElementById('hosts').innerHTML = '<p class="pl-empty">稍后再来。</p>';
});
setInterval(() => { loadBar().catch(() => {}); }, 10000);
