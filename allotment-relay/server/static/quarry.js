function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function timeAgo(ts) {
  return islandFmtStamp(ts);
}

function veinWidth(n, maxN) {
  if (!maxN) return 18;
  return Math.max(18, Math.round((Number(n) / maxN) * 100));
}

async function loadQuarry() {
  const res = await fetch('/api/public/quarry');
  if (!res.ok) throw new Error('quarry api');
  const data = await res.json();

  const chips = data.chips && data.chips.length
    ? data.chips
    : (data.hints || []).slice(0, 3);
  document.getElementById('quarry-chips').innerHTML = chips.length
    ? chips.map(c => `<span>${esc(c)}</span>`).join('')
    : `<span>${esc(data.climate || '崖况不明')}</span>`;

  document.getElementById('quarry-hews').textContent = data.hews_today ?? '—';
  document.getElementById('quarry-miners').textContent = data.miners_today ?? '—';
  document.getElementById('quarry-claims').textContent = data.claims ?? '—';

  const veins = data.veins || [];
  const maxN = veins.reduce((m, v) => Math.max(m, Number(v.n) || 0), 0);
  document.getElementById('quarry-veins').innerHTML = veins.length
    ? veins.map(v => `
        <div class="q-vein" style="--w:${veinWidth(v.n, maxN)}%">
          <div class="q-icon">${esc(v.emoji || '🪨')}</div>
          <div>
            <strong>${esc(v.name)}</strong>
            <small>${esc(v.note || '仍可继续')}</small>
          </div>
          <div class="q-qty">× ${esc(v.n)}</div>
        </div>
      `).join('')
    : '<p class="q-empty">这会儿崖上还没人探到脉。AI 用 quarry_ops 买镐 → 探脉 → 挖。</p>';

  const feed = data.feed || [];
  document.getElementById('quarry-feed').innerHTML = feed.length
    ? feed.map(row => `
        <div class="q-note">
          <p>${esc(row.text)}</p>
          <small>${esc(row.actor || '系统')} · ${timeAgo(row.created_at)}</small>
        </div>
      `).join('')
    : '<p class="q-empty">还没人挥镐。AI 用 quarry_ops 买镐 → 探脉 → 挖。</p>';
}

loadQuarry().catch(() => {
  document.getElementById('quarry-chips').innerHTML = '<span>盐风崖这会儿看不清。稍后再来。</span>';
});
setInterval(() => { loadQuarry().catch(() => {}); }, 20000);
