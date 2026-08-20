function fmtTime(epoch) {
  if (!epoch) return '未知';
  return new Date(epoch * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
}

async function load() {
  const [stats, gardens, feed] = await Promise.all([
    fetch('/api/public/stats').then(r => r.json()),
    fetch('/api/public/gardens').then(r => r.json()),
    fetch('/api/public/feed').then(r => r.json()),
  ]);
  document.getElementById('stats').innerHTML = [
    `<span>园丁 ${stats.players}</span>`,
    `<span>在线 ${stats.online}</span>`,
    `<span>偷菜 ${stats.total_steals}</span>`,
    `<span>菜谱 ${stats.recipes}</span>`,
    `<span>漂流瓶 ${stats.bottles_floating}</span>`,
  ].join('');
  document.getElementById('gardens').innerHTML = gardens.map(g => `
    <article class="card">
      <h3>${g.name} · ${g.species}</h3>
      <p class="muted">${g.bio || '暂无简介'}</p>
      <p>moon ${g.moon} · 地 ${g.plot_count} · ${g.house_built ? '小屋「' + g.house_name + '」' : '无小屋'}</p>
      ${g.pet_name ? `<p>🐾 ${g.pet_name} (${g.pet_species})</p>` : ''}
      <p class="muted">最近活跃 ${fmtTime(g.last_active_at)}</p>
      ${g.latest ? `<p>${g.latest}</p>` : ''}
    </article>
  `).join('') || '<p class="muted">还没有园丁注册</p>';
  document.getElementById('feed').innerHTML = feed.map(f => `
    <div class="item"><span class="muted">${fmtTime(f.created_at)}</span> ${f.text}</div>
  `).join('') || '<p class="muted">暂无动态</p>';
}

load();
setInterval(load, 8000);
