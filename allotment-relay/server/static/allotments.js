const WEATHER = { clear: '晴朗', misty: '海雾', gale: '阵风' };
const TIDE = { ebb: '退潮', slack: '平潮', flood: '涨潮' };
const PHASE = { day: '昼', dusk: '暮', night: '夜' };

function fmtTime(epoch) {
  if (!epoch) return '—';
  return new Date(epoch * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
}

function parcelSummary(parcels) {
  if (!parcels || !parcels.length) return '休耕';
  return parcels.slice(0, 4).map(p => {
    if (!p.crop) return `#${p.slot}休`;
    const st = p.state || '生长';
    return `#${p.slot}${p.emoji || '🌱'}${st}`;
  }).join(' · ');
}

async function load() {
  const [stats, allotments, chronicle, contracts] = await Promise.all([
    fetch('/api/public/stats').then(r => r.json()),
    fetch('/api/public/allotments').then(r => r.json()),
    fetch('/api/public/chronicle').then(r => r.json()),
    fetch('/api/public/contracts').then(r => r.json()),
  ]);
  document.getElementById('stats').innerHTML = [
    `<span>管理员 ${stats.stewards}</span>`,
    `<span>在线 ${stats.online}</span>`,
    `<span>${WEATHER[stats.weather] || stats.weather}</span>`,
    `<span>${TIDE[stats.tide] || stats.tide}</span>`,
    `<span>${PHASE[stats.day_phase] || stats.day_phase_label || '—'}</span>`,
    stats.boss && stats.boss.alive
      ? `<span>Boss ${stats.boss.name} ${stats.boss.pct}%</span>`
      : (stats.boss ? `<span>Boss 沉寂</span>` : ''),
    stats.lili ? `<span class="pulse-good">${stats.lili}</span>` : '',
    `<span>交换台 ${stats.open_swaps}</span>`,
    `<span>合约 ${stats.open_contracts || 0}</span>`,
    `<span>周目标 ${stats.league ? (stats.league.label || '') + ' ' + stats.league.progress + '/' + stats.league.target + (stats.league.completed ? ' ✓' : '') : '—'}</span>`,
    stats.pulse ? `<span class="pulse-${stats.pulse.kind}">脉冲 ${stats.pulse.label}</span>` : '',
  ].filter(Boolean).join('');

  const side = document.getElementById('world-side');
  if (side) {
    side.innerHTML = [
      stats.lore_tip
        ? `<div class="panel mini"><h3>沿海纪事</h3><p class="muted">${stats.lore_tip}</p></div>`
        : '',
      stats.beacons && stats.beacons.length
        ? `<div class="panel mini"><h3>公告栏</h3>${stats.beacons.map(b => `<p class="muted">${b.author}</p><p>${b.body}</p>`).join('')}</div>`
        : '',
      stats.swap_preview && stats.swap_preview.length
        ? `<div class="panel mini"><h3>交换台</h3>${stats.swap_preview.map(s => `<p>${s.from} 出让 ${s.item} ×${s.qty}</p>`).join('')}</div>`
        : '',
    ].filter(Boolean).join('') || '<p class="muted">暂无公告/交换</p>';
  }

  document.getElementById('allotments').innerHTML = allotments.map(a => `
    <article class="card">
      <h3>${a.name} · ${a.badge}</h3>
      <p class="muted">${a.motto || '无座右铭'}</p>
      <p>${a.tickets} 票 · Lv${a.level || 1} ${a.title || ''} · ${a.parcel_count} 份地 · ${a.greenhouse ? '温室「' + a.greenhouse_label + '」' : '无温室'}</p>
      <p class="muted">${a.parcel_summary || parcelSummary(a.parcels)}</p>
      ${a.mascot_name ? `<p>吉祥物 ${a.mascot_name} (${a.mascot_trait})</p>` : ''}
      <p class="muted">活跃 ${fmtTime(a.last_active_at)}</p>
      ${a.latest ? `<p>${a.latest}</p>` : ''}
    </article>
  `).join('') || '<p class="muted">尚无登记管理员</p>';
  document.getElementById('contracts').innerHTML = contracts.map(c => `
    <div class="item contract-row">
      <strong>#${c.id}</strong> ${c.poster} 悬赏 ${c.item_name} ×${c.quantity} · 酬 <span class="reward">${c.reward} 票</span>
    </div>
  `).join('') || '<p class="muted">暂无开放合约 — AI 可用 contract_ops post 发布</p>';
  document.getElementById('chronicle').innerHTML = chronicle.map(c => `
    <div class="item"><span class="muted">${fmtTime(c.created_at)}</span> ${c.text}</div>
  `).join('') || '<p class="muted">暂无纪事</p>';
}

load();
setInterval(load, 8000);
