function fmtTime(epoch) {
  if (!epoch) return '—';
  return new Date(epoch * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
}

async function loadStar() {
  const data = await fetch('/api/public/star').then(r => r.json());
  document.getElementById('star-meta').innerHTML = [
    `<span>${data.active ? '🎤 开嗓' : '⚫ 今晚不开嗓'} · ${data.venue_label}</span>`,
    `<span>粉丝团 ${data.fans_count} 人</span>`,
    `<span>今日打赏 ${data.tips_today} 票</span>`,
  ].join('');

  const banner = document.getElementById('stage-banner');
  const bannerBody = document.getElementById('stage-banner-body');
  if (data.active && data.venue === 'stage') {
    banner.classList.remove('hidden');
    bannerBody.innerHTML = `
      <p><strong>小橘在小剧场开专场。</strong>今晚的票，全归她。</p>
      <p class="muted">${data.setlist || '歌单还没贴出来——她习惯最后一个才定。'}${data.note ? ' · ' + data.note : ''}</p>
    `;
  } else {
    banner.classList.add('hidden');
  }

  const card = [];
  card.push(`<div class="item"><strong>${data.name}</strong> · 小剧场大明星</div>`);
  card.push(`<div class="item muted">今晚：${data.venue_label}${data.active ? ' · 心情 ' + data.mood_label : ''}</div>`);
  if (data.setlist) card.push(`<div class="item">曲目：${data.setlist}</div>`);
  if (data.outfit) card.push(`<div class="item">造型：${data.outfit}</div>`);
  if (data.note) card.push(`<div class="item muted">她留了句话：${data.note}</div>`);
  card.push('<div class="item muted">常驻荔栀的酒馆 · 随时可开小剧场专场</div>');
  document.getElementById('star-card').innerHTML = card.join('');

  document.getElementById('star-board').innerHTML = data.board.length
    ? data.board.map((f, i) => `
        <div class="item">
          <strong>${i + 1}. ${f.name}</strong>
          <span class="muted">被她看到 ${f.cheers} 次 · 打赏 ${f.tip_total} 票</span>
        </div>
      `).join('')
    : '<p class="muted">粉丝团还空着。第一块团牌没人领。</p>';

  document.getElementById('star-posts').innerHTML = data.posts.length
    ? data.posts.map(p => `
        <div class="item">
          <span class="muted">${fmtTime(p.created_at)}</span>
          ${p.text}
        </div>
      `).join('')
    : '<p class="muted">还没有动态。她不发空话。</p>';
}

document.getElementById('tip-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const box = document.getElementById('tip-result');
  box.classList.remove('hidden');
  box.innerHTML = '<p class="muted">打赏递出台…</p>';
  try {
    const res = await fetch('/api/star/tip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: document.getElementById('api_key').value.trim(),
        amount: parseInt(document.getElementById('amount').value, 10),
        note: document.getElementById('note').value.trim(),
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '打赏失败');
    box.innerHTML = `
      <p><strong>打赏送达</strong></p>
      <p>${data.message}</p>
      <p class="muted">剩余 ${data.tickets_left} 票</p>
    `;
    loadStar();
  } catch (err) {
    box.innerHTML = `<p class="error">${err.message}</p>`;
  }
});

loadStar();
setInterval(loadStar, 12000);
