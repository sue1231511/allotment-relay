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
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

function seaCondition(weather) {
  if (weather === 'gale') return '浪大';
  if (weather === 'misty') return '有雾';
  return '平稳';
}

async function loadTide() {
  const res = await fetch('/api/public/tide');
  if (!res.ok) throw new Error('tide api');
  const data = await res.json();

  const tideChip = data.tide_label
    ? (data.tide === 'slack' ? data.tide_label : `${data.tide_label}中`)
    : '海况未知';
  const chips = [
    tideChip,
    data.weather_label || '',
    data.sailing_hint || '',
  ].filter(Boolean);
  document.getElementById('tide-chips').innerHTML = chips
    .map(c => `<span class="chip">${esc(c)}</span>`)
    .join('');

  const near = Number(data.voyages_out || 0) + Number(data.shore_active || 0);
  document.getElementById('tide-stats').innerHTML = [
    `<div class="pl-stat"><small>潮位</small><strong>${esc(data.tide_label || '—')}</strong></div>`,
    `<div class="pl-stat"><small>海况</small><strong>${esc(seaCondition(data.weather))}</strong></div>`,
    `<div class="pl-stat"><small>近海人数</small><strong>${esc(near)}</strong></div>`,
    `<div class="pl-stat"><small>下一次潮变</small><strong>${esc(data.next_tide_clock || '—')}</strong></div>`,
  ].join('');

  const sea = data.at_sea || [];
  const rows = [];
  if (sea.length) {
    rows.push(...sea.map(v => ({
      mark: '舟',
      title: `${v.route || '近海'} · 出海`,
      line: `${v.name} 在船上`,
      badge: '出海中',
    })));
  }
  if (Number(data.pens || 0) > 0) {
    rows.push({
      mark: '排',
      title: `渔排 · ${data.pens} 口`,
      line: `岸边有 ${data.boats || 0} 人备了船`,
      badge: '在养',
    });
  }
  const boss = data.boss;
  if (boss) {
    rows.push({
      mark: '渊',
      title: boss.name,
      line: boss.alive ? `血量 ${boss.pct}%` : '歇着',
      badge: boss.alive ? '潮渊' : '沉睡',
    });
  }

  document.getElementById('tide-sea').innerHTML = rows.length
    ? rows.map(r => `
        <div class="pl-row">
          <div class="pl-avatar">${esc(r.mark)}</div>
          <div>
            <h3>${esc(r.title)}</h3>
            <p>${esc(r.line)}</p>
          </div>
          <span class="pl-badge">${esc(r.badge)}</span>
        </div>
      `).join('')
    : '<p class="pl-empty">这会儿码头没人出航。去上手页撒网，或让 AI <code>tide_ops voyage depart near</code>。</p>';

  const feed = data.feed || [];
  document.getElementById('tide-feed').innerHTML = feed.length
    ? feed.map(row => `
        <div class="pl-feed-item">
          <time>${esc(clock(row.created_at))}</time>
          <p>${row.actor && row.actor !== '系统' ? `<b>${esc(row.actor)}</b> ` : ''}${esc(row.text)}</p>
        </div>
      `).join('')
    : '<p class="pl-empty">潮还没响。AI 用 <code>tide_ops net</code> 或 <code>voyage depart near</code>。</p>';
}

loadTide().catch(() => {
  document.getElementById('tide-chips').innerHTML = '<span class="chip">海边这会儿看不清</span>';
  document.getElementById('tide-sea').innerHTML = '<p class="pl-empty">稍后再来。</p>';
});
setInterval(() => { loadTide().catch(() => {}); }, 20000);
