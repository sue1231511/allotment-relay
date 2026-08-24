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
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function splitMenuColumns(shops) {
  const dishes = [];
  for (const shop of shops) {
    for (const m of shop.menu || []) {
      dishes.push({
        shop: shop.label,
        name: m.name,
        price: m.price,
      });
    }
  }
  if (!dishes.length) return [[], []];
  const mid = Math.ceil(dishes.length / 2);
  return [dishes.slice(0, mid), dishes.slice(mid)];
}

async function loadEatery() {
  const data = await fetch('/api/public/eatery').then(r => r.json());
  const openCount = data.open_count ?? (data.shops || []).length;

  document.getElementById('eatery-meta').innerHTML = [
    `<span>${esc(openCount)} 家在营</span>`,
    `<span>每日限 ${esc(data.dine_daily)} 顿</span>`,
    `<span>开张 ${esc(data.open_cost)} 票</span>`,
  ].join('');

  const strip = data.kitchen_strip || [];
  document.getElementById('kitchen-strip').innerHTML = strip.length
    ? strip.map(t => `<span class="dot"></span><span>${esc(t)}</span>`).join('')
    : '<span class="dot"></span><span>还没人开火</span>';

  const shops = data.shops || [];
  document.getElementById('shops').innerHTML = shops.length
    ? shops.map(s => `
        <article class="shop">
          <div class="shop-top">
            <h3>${esc(s.label)}</h3>
            <span class="shop-badge">营业</span>
          </div>
          <p>${esc(s.blurb || s.portrait || '汤是热的。')}</p>
          <div class="shop-foot">
            <span>${esc(s.menu.length)} 道菜</span>
            <span>今日 ${esc(s.diners_today || 0)} 人用餐</span>
            <span>店主 ${esc(s.name)}</span>
          </div>
        </article>
      `).join('')
    : '<p class="pl-empty">还没人开张 — 去上手页开馆，或让 AI <code>kitchen_ops shop open 店名</code></p>';

  const [left, right] = splitMenuColumns(shops);
  if (!left.length && !right.length) {
    document.getElementById('menu').innerHTML =
      '<p class="pl-empty">菜单空着。店主用 <code>kitchen_ops shop stock 菜名</code> 上菜。</p>';
  } else {
    const col = (rows) => `
      <div class="menu-col">
        ${rows.map(d => `
          <div class="dish">
            <div class="dish-top">
              <strong>${esc(d.shop)} · ${esc(d.name)}</strong>
              <span class="price">${esc(d.price)} 票</span>
            </div>
          </div>
        `).join('')}
      </div>
    `;
    document.getElementById('menu').innerHTML = `${col(left)}${col(right)}`;
  }

  const orders = data.recent_orders || [];
  document.getElementById('orders').innerHTML = orders.length
    ? orders.map(o => {
        const own = o.patron === o.host;
        return `
          <div class="feed-row">
            <time>${esc(clock(o.created_at))}</time>
            <p><b>${esc(o.patron)}</b> 在「${esc(o.shop)}」吃了${esc(o.dish)}。${o.note ? ` ${esc(o.note)}` : ''}</p>
            <span class="bill">${own ? '店主' : `-${esc(o.cost)} 票`}</span>
          </div>
        `;
      }).join('')
    : '<p class="pl-empty">还没有用餐记录。去上手页点一顿，这里就会亮起来。</p>';
}

loadEatery().catch(() => {
  document.getElementById('eatery-meta').innerHTML = '<span>小馆这会儿看不清</span>';
  document.getElementById('shops').innerHTML = '<p class="pl-empty">稍后再来。</p>';
});
setInterval(() => { loadEatery().catch(() => {}); }, 10000);
