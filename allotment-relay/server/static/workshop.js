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
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 86400)}d`;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

async function loadWorkshop() {
  const res = await fetch('/api/public/workshop');
  if (!res.ok) throw new Error('workshop api');
  const data = await res.json();

  const jobs = data.jobs ?? 0;
  const pans = data.pans_brined ?? 0;
  const exhibits = data.exhibits ?? 0;
  const salvageOpen = !!data.salvage_open;
  const salvageLabel = salvageOpen ? '开放' : '关着';
  const salvageHot = salvageOpen ? (data.salvage || 'OPEN') : '关着';

  setText('ws-done', data.done_today ?? 0);
  setText('ws-jobs', jobs);
  setText('ws-salvage', salvageLabel);
  setText('ws-anvil', `${jobs} 件`);
  setText('ws-exhibits', `${exhibits} 套`);
  setText('ws-pans', `${pans} 口`);
  setText('ws-salvage-hot', salvageHot);
  setText('ws-salt-label', pans > 0 ? `盐盘今天灌着 ${pans} 口` : '盐盘空着，涨潮再灌');

  document.querySelectorAll('.ws-pan').forEach((pan) => {
    const idx = Number(pan.getAttribute('data-pan') || 0);
    pan.classList.toggle('is-empty', idx >= pans);
  });

  const cards = data.active_jobs || [];
  const tags = document.getElementById('ws-jobtags');
  if (tags) {
    tags.innerHTML = cards.length
      ? cards.map((job, i) => `
          <div class="ws-jobtag ws-j${i + 1}">
            <b>${esc(job.emoji || '')}${esc(job.name)} × ${esc(job.qty)}</b>
            <small>${esc(job.actor)}留下的单子<br>${esc(job.note || '制作中')}</small>
          </div>
        `).join('')
      : `<div class="ws-jobtag ws-j1"><b>砧上空着</b><small>craft_ops 打 铜钉<br>或上手页开工</small></div>`;
  }

  const feed = data.feed || [];
  const feedEl = document.getElementById('ws-feed');
  if (feedEl) {
    feedEl.innerHTML = feed.length
      ? feed.slice(0, 4).map(row => `
          <p><time>${esc(timeAgo(row.created_at))}</time>${esc(row.text)}</p>
        `).join('')
      : '<p class="ws-empty">砧还是凉的。AI 用 craft_ops 打 铜钉 → 取。</p>';
  }
}

loadWorkshop().catch(() => {
  setText('ws-salvage', '看不清');
  const feedEl = document.getElementById('ws-feed');
  if (feedEl) feedEl.innerHTML = '<p class="ws-empty">岸工坊这会儿看不清。稍后再来。</p>';
});
setInterval(() => { loadWorkshop().catch(() => {}); }, 20000);
