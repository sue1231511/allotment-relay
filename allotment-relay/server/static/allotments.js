const WEATHER = { clear: '晴朗', misty: '海雾', gale: '阵风' };
const TIDE = { ebb: '退潮', slack: '平潮', flood: '涨潮' };

function fmtTime(epoch) {
  if (!epoch) return '—';
  return new Date(epoch * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
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
    `<span>交换台 ${stats.open_swaps}</span>`,
    `<span>合约 ${stats.open_contracts || 0}</span>`,
    `<span>周目标 ${stats.league ? (stats.league.label || '') + ' ' + stats.league.progress + '/' + stats.league.target + (stats.league.completed ? ' ✓' : '') : '—'}</span>`,
    `<span>灶台 ${stats.hearth_recipes}</span>`,
  ].join('');
  document.getElementById('allotments').innerHTML = allotments.map(a => `
    <article class="card">
      <h3>${a.name} · ${a.badge}</h3>
      <p class="muted">${a.motto || '无座右铭'}</p>
      <p>${a.tickets} 票 · ${a.parcel_count} 份地 · ${a.greenhouse ? '温室「' + a.greenhouse_label + '」' : '无温室'}</p>
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
