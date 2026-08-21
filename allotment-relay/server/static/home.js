async function loadHome() {
  const card = document.getElementById('live-card');
  const names = document.getElementById('live-names');
  const board = document.getElementById('home-board');
  if (!card || !names) return;
  try {
    const [stats, data] = await Promise.all([
      fetch('/api/public/stats').then((r) => r.json()),
      fetch('/api/public/board').then((r) => r.json()),
    ]);
    const people = stats.online_people || [];
    const line = document.getElementById('live-online-line');
    if (line) {
      line.textContent = people.length
        ? `${people.length} 人在档口`
        : '这会儿档口没人';
    }
    names.innerHTML = people.length
      ? people.slice(0, 6).map((p) => (
        `<a class="live-name" href="/allotments#steward-${esc(p.id)}">${esc(p.name)}</a>`
      )).join('')
      : '<span class="muted">去份地围观看谁留下过</span>';
    const status = card.querySelector('.status-text');
    if (status) {
      status.textContent = [
        { clear: '晴朗', misty: '海雾', gale: '阵风' }[stats.weather] || stats.weather,
        { ebb: '退潮', slack: '平潮', flood: '涨潮' }[stats.tide] || stats.tide,
        stats.day_phase_label || '',
      ].filter(Boolean).join(' · ');
    }
    if (board) {
      const top = (data.tickets || []).slice(0, 3);
      board.innerHTML = top.length
        ? '<p class="home-board-kicker">工分票榜</p>' + top.map((r, i) => (
          `<a class="home-board-row" href="/allotments#steward-${esc(r.id)}">` +
            `<span>${medal(i + 1)} ${esc(r.name)}</span>` +
            `<span>${esc(r.tickets)} 票</span>` +
          '</a>'
        )).join('') + '<a class="home-board-more" href="/board">看全榜</a>'
        : '';
    }
  } catch (err) {
    names.innerHTML = '<span class="muted">海况暂时读不到</span>';
  }
}

loadHome();
setInterval(loadHome, 12000);
