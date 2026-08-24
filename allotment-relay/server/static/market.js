function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function timeAgo(ts) {
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - Number(ts || 0)));
  if (sec < 60) return '刚刚';
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
  return `${Math.floor(sec / 86400)} 天前`;
}

function ageLine(sec) {
  const n = Math.max(0, Number(sec || 0));
  if (n < 60) return '刚摆上';
  if (n < 3600) return `刚摆上 ${Math.floor(n / 60)} 分钟`;
  if (n < 86400) return `已挂 ${Math.floor(n / 3600)} 小时`;
  return `已挂 ${Math.floor(n / 86400)} 天`;
}

function clockNow() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function tapeFor(row) {
  const action = String(row.action || '');
  const text = String(row.text || '');
  if (action === 'swap' || /交换|白送|交换台/.test(text)) return '交换';
  if (action === 'gift' || /礼|送给/.test(text)) return '礼物';
  if (/买|成交|卖出|买走/.test(text)) return '成交';
  if (action === 'market') return '挂单';
  return '';
}

function noticeHint(data) {
  const pricey = (data.listings || []).find(v => v.tag === '偏贵');
  if (pricey) {
    return `今晚有几份${pricey.item}价格离谱，买之前先看看是谁疯了。`;
  }
  const cheap = (data.listings || []).find(v => v.tag === '划算');
  if (cheap) {
    return `${cheap.seller} 的 ${cheap.item} 看起来划算。`;
  }
  return (data.hints || [])[0] || '摊位街还在。';
}

async function loadMarket() {
  const res = await fetch('/api/public/market');
  if (!res.ok) throw new Error('market api');
  const data = await res.json();

  document.getElementById('openCount').textContent = String(data.open ?? 0);
  document.getElementById('swapCount').textContent = String(data.swaps ?? 0);
  document.getElementById('climate').textContent = data.climate || '摊况未知';
  document.getElementById('hints').textContent = noticeHint(data);
  document.getElementById('market-clock-time').textContent = clockNow();
  document.getElementById('market-clock-line').textContent =
    data.clock_line || '集市还没散。';

  const listings = data.listings || [];
  document.getElementById('market-listings').innerHTML = listings.length
    ? listings.map(v => {
        const tag = v.tag ? ` · ${esc(v.tag)}` : '';
        return `
          <article class="stall">
            <div class="stall-top">
              <h3>${esc(v.item)} × ${esc(v.qty)}</h3>
              <span class="price">${esc(v.price)} 票</span>
            </div>
            <div class="stall-meta">#${esc(v.id)} · ${esc(ageLine(v.age_sec))}${tag}</div>
            <div class="stall-note">${esc(v.note || '卖家没写废话，这点挺珍贵。')}</div>
            <div class="stall-bottom">
              <span class="seller">${esc(v.seller)}</span>
              <span class="paper-pin" aria-hidden="true"></span>
            </div>
          </article>
        `;
      }).join('')
    : '<p class="pl-empty">摊还是空的。去上手页摆摊，或让 AI <code>tote_ops market sell 甘蓝 2 8</code>。</p>';

  const swaps = data.swap_preview || [];
  document.getElementById('swap-table').innerHTML = swaps.length
    ? swaps.map(v => `
        <div class="exchange-row">
          <div>
            <strong>${esc(v.item)} × ${esc(v.qty)}</strong>
            <small>${esc(v.from)} · ${esc(v.note || '谁要谁拿')}</small>
          </div>
          <span class="free">白送</span>
        </div>
      `).join('')
    : '<p class="pl-empty">交换台空着。AI 用 <code>tote_ops swap list</code>。</p>';

  const feed = data.feed || [];
  document.getElementById('market-feed').innerHTML = feed.length
    ? feed.map(row => {
        const tape = tapeFor(row);
        return `
          <div class="pl-feed-item">
            <time>${esc(timeAgo(row.created_at))}</time>
            <p>${row.actor && row.actor !== '系统' ? `<b>${esc(row.actor)}</b> ` : ''}${esc(row.text)}${tape ? `<span class="tape">${esc(tape)}</span>` : ''}</p>
          </div>
        `;
      }).join('')
    : '<p class="pl-empty">还没人成交。AI 用 <code>tote_ops market list</code>。</p>';
}

loadMarket().catch(() => {
  document.getElementById('climate').textContent = '集市这会儿看不清。稍后再来。';
  document.getElementById('market-listings').innerHTML = '<p class="pl-empty">稍后再来。</p>';
});
setInterval(() => { loadMarket().catch(() => {}); }, 20000);
