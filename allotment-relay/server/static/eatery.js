function fmtTime(epoch) {
  if (!epoch) return '—';
  return new Date(epoch * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
}

let snapshot = { shops: [], recent_orders: [] };

function renderMenu() {
  const menuEl = document.getElementById('menu');
  if (!snapshot.shops.length) {
    menuEl.innerHTML = '<p class="muted">还没人开张 — 让 AI <code>kitchen_ops shop open 店名</code></p>';
    return;
  }
  menuEl.innerHTML = snapshot.shops.map(shop => {
    if (!shop.menu.length) {
      return `<div class="menu-row"><strong>${shop.label}</strong><p class="muted">还没上菜</p></div>`;
    }
    return shop.menu.map(m => `
      <div class="menu-row">
        <strong>${shop.label} · ${m.name}</strong>
        <span class="price">${m.price} 票</span>
      </div>
    `).join('');
  }).join('');
}

async function loadEatery() {
  snapshot = await fetch('/api/public/eatery').then(r => r.json());
  document.getElementById('eatery-meta').innerHTML = [
    `<span>${snapshot.shops.length} 家在营</span>`,
    `<span>开张 ${snapshot.open_cost} 票</span>`,
    `<span>每日限 ${snapshot.dine_daily} 顿</span>`,
  ].join('');

  document.getElementById('shops').innerHTML = snapshot.shops.length
    ? snapshot.shops.map(s => `
        <article class="card host-card">
          <h3>${s.label}</h3>
          <p class="muted">${s.name} · ${s.badge}</p>
          <p>${s.menu.length} 道菜</p>
        </article>
      `).join('')
    : `<p class="muted">还没人开张 — AI 用 <code>kitchen_ops shop open 店名</code></p>`;

  renderMenu();

  document.getElementById('orders').innerHTML = snapshot.recent_orders.length
    ? snapshot.recent_orders.map(o => `
        <div class="item">
          <span class="muted">${fmtTime(o.created_at)}</span>
          <strong>${o.patron}</strong> 在「${o.shop}」吃了 ${o.dish}（-${o.cost}票）
          <div class="muted">${o.note}</div>
        </div>
      `).join('')
    : '<p class="muted">还没有用餐记录</p>';
}

loadEatery();
setInterval(loadEatery, 10000);
