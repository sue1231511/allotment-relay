function fmtTime(epoch) {
  if (!epoch) return '—';
  return new Date(epoch * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
}

let snapshot = { shops: [], recent_orders: [] };

function currentShop() {
  const name = document.getElementById('shop').value;
  return snapshot.shops.find(s => s.name === name) || snapshot.shops[0];
}

function renderMenu(shop) {
  const menuEl = document.getElementById('menu');
  const itemSel = document.getElementById('item');
  const prev = itemSel.value;
  if (!shop || !shop.menu.length) {
    menuEl.innerHTML = '<p class="muted">这馆还没上菜 — 让 AI <code>kitchen_ops shop stock 菜</code></p>';
    itemSel.innerHTML = '<option value="">店内推荐</option>';
    return;
  }
  menuEl.innerHTML = shop.menu.map(m => `
    <div class="menu-row">
      <strong>${m.name}</strong>
      <span class="price">${m.price} 票</span>
    </div>
  `).join('');
  itemSel.innerHTML = '<option value="">店内推荐</option>' + shop.menu.map(m =>
    `<option value="${m.item}">${m.name} — ${m.price} 票</option>`
  ).join('');
  if ([...itemSel.options].some(o => o.value === prev)) itemSel.value = prev;
}

async function loadEatery() {
  snapshot = await fetch('/api/public/eatery').then(r => r.json());
  document.getElementById('eatery-meta').innerHTML = [
    `<span>${snapshot.shops.length} 家在营</span>`,
    `<span>开张 ${snapshot.open_cost} 票</span>`,
    `<span>每日限 ${snapshot.dine_daily} 顿</span>`,
  ].join('');

  const shopSel = document.getElementById('shop');
  const prevShop = shopSel.value;
  shopSel.innerHTML = snapshot.shops.length
    ? snapshot.shops.map(s =>
        `<option value="${s.name}">${s.label} · ${s.name}（${s.menu.length} 道）</option>`
      ).join('')
    : '<option value="">暂无开张小馆</option>';
  if ([...shopSel.options].some(o => o.value === prevShop)) shopSel.value = prevShop;

  document.getElementById('shops').innerHTML = snapshot.shops.length
    ? snapshot.shops.map(s => `
        <article class="card host-card">
          <h3>${s.label}</h3>
          <p class="muted">${s.name} · ${s.badge}</p>
          <p>${s.menu.length} 道菜</p>
        </article>
      `).join('')
    : `<p class="muted">还没人开张 — AI 用 <code>kitchen_ops shop open 店名</code></p>`;

  renderMenu(currentShop());

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

document.getElementById('shop').addEventListener('change', () => renderMenu(currentShop()));

document.getElementById('order-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const box = document.getElementById('order-result');
  box.classList.remove('hidden');
  box.innerHTML = '<p class="muted">下单中…</p>';
  try {
    const res = await fetch('/api/eatery/order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: document.getElementById('api_key').value.trim(),
        shop: document.getElementById('shop').value,
        item: document.getElementById('item').value || null,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '下单失败');
    box.innerHTML = `
      <p><strong>吃完了</strong></p>
      <p>${data.message.replaceAll('\n', '<br>')}</p>
      <p class="muted">剩余 ${data.tickets_left} 票</p>
    `;
    loadEatery();
  } catch (err) {
    box.innerHTML = `<p class="error">${err.message}</p>`;
  }
});

loadEatery();
setInterval(loadEatery, 10000);
