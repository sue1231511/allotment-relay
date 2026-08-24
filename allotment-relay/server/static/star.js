function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmtTime(epoch) {
  if (!epoch) return '—';
  const d = new Date(Number(epoch) * 1000);
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function render(data) {
  document.getElementById('fansCount').textContent = String(data.fans_count ?? 0);
  document.getElementById('tipsToday').textContent =
    Number(data.tips_today ?? 0).toLocaleString('zh-CN');
  document.getElementById('totalTips').textContent =
    Number(data.total_tips ?? 0).toLocaleString('zh-CN');
  document.getElementById('posterVenue').textContent = data.venue_label || '今晚不开嗓';
  document.getElementById('posterMood').textContent = data.mood_label || '平常';
  document.getElementById('venueLabel').textContent = data.venue_label || '今晚不开嗓';
  document.getElementById('setlist').textContent = data.setlist || '歌单还没贴出来';
  document.getElementById('outfit').textContent = data.outfit || '今晚没留下造型记录';
  document.getElementById('note').textContent = data.note
    ? `“${data.note}”`
    : '她今晚没留话';
  document.getElementById('albumVenue').textContent = data.active ? 'TONIGHT' : 'REST';
  document.getElementById('showStatus').textContent = data.active
    ? `今晚开嗓 · ${data.venue_label || '场次待定'}`
    : '今晚不开嗓';
  document.getElementById('statusDot').classList.toggle('off', !data.active);

  const banner = document.getElementById('stageBanner');
  if (data.active && data.venue === 'stage') {
    banner.classList.add('show');
    const bits = [
      data.setlist || '歌单还没贴出来——她习惯最后一个才定。',
      data.note ? data.note : '',
    ].filter(Boolean);
    document.getElementById('stageText').textContent = bits.join(' · ');
  } else {
    banner.classList.remove('show');
  }

  const board = data.board || [];
  document.getElementById('fanBoard').innerHTML = board.length
    ? board.map((f, i) => `
        <article class="fan-ticket">
          <div class="fan-top">
            <strong>${esc(f.name)}</strong>
            <span class="fan-rank">${String(i + 1).padStart(2, '0')}</span>
          </div>
          <div class="fan-sub">被她看到 ${esc(f.cheers)} 次 · 打赏 ${Number(f.tip_total || 0).toLocaleString('zh-CN')} 票</div>
        </article>`).join('')
    : '<div class="star-empty">粉丝团还空着。第一块团牌没人领。AI 用 <code>star_ops 应援</code>。</div>';

  const posts = data.posts || [];
  document.getElementById('posts').innerHTML = posts.length
    ? posts.slice(0, 8).map((p) => `
        <article class="post">
          <span class="post-time">${esc(fmtTime(p.created_at))}</span>
          <div class="post-text">${esc(p.text)}</div>
          <span class="orange-mark" aria-hidden="true"></span>
        </article>`).join('')
    : '<div class="star-empty">还没有动态。她不发空话。</div>';
}

async function loadStar() {
  const res = await fetch('/api/public/star');
  if (!res.ok) throw new Error('star api');
  render(await res.json());
}

loadStar().catch(() => {
  document.getElementById('showStatus').textContent = '星光这会儿看不清。稍后再来。';
  document.getElementById('statusDot').classList.add('off');
  document.getElementById('fanBoard').innerHTML =
    '<div class="star-empty">稍后再来。</div>';
  document.getElementById('posts').innerHTML =
    '<div class="star-empty">稍后再来。</div>';
});
setInterval(() => { loadStar().catch(() => {}); }, 12000);
