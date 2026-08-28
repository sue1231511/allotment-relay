function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function clock(epoch) {
  if (typeof islandFmtClock === 'function') return islandFmtClock(epoch);
  if (!epoch) return '—';
  const d = new Date(Number(epoch) * 1000);
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

const state = { board: '', threadId: 0 };

function flags(item) {
  const bits = [];
  if (item.pinned) bits.push('置顶');
  if (item.locked) bits.push('已锁');
  return bits.length ? `<span class="ting-flags">${bits.map(esc).join(' · ')}</span>` : '';
}

function renderBoards(boards, active) {
  const el = document.getElementById('ting-boards');
  if (!el) return;
  const all = [{ id: '', name: '全部', hint: '最近钉上的', threads: boards.reduce((n, b) => n + (b.threads || 0), 0) }, ...boards];
  el.innerHTML = all.map((b) => `
    <button type="button" class="ting-board-tab${b.id === active ? ' is-active' : ''}" data-board="${esc(b.id)}">
      ${esc(b.name)}
      <small>${esc(b.threads || 0)} 帖</small>
    </button>
  `).join('');
}

function renderList(threads) {
  const el = document.getElementById('ting-list');
  if (!el) return;
  if (!threads.length) {
    el.innerHTML = '<p class="pl-empty">这块还空着。去上手页钉第一块。</p>';
    return;
  }
  el.innerHTML = threads.map((t) => `
    <button type="button" class="ting-card${Number(t.id) === state.threadId ? ' is-active' : ''}" data-thread="${esc(t.id)}">
      <div class="kicker">${esc(t.board_name)} · #${esc(t.id)}${flags(t)}</div>
      <strong>${esc(t.title)}</strong>
      <p>${esc(t.excerpt || '')}</p>
      <div class="meta">${esc(t.who)} · ${esc(t.replies)} 回 · ${esc(t.clock || clock(t.bumped_at))}</div>
    </button>
  `).join('');
}

function renderThread(view) {
  const el = document.getElementById('ting-thread');
  if (!el) return;
  if (!view) {
    el.innerHTML = '<p class="pl-empty">点左边一块木牌看全文。</p>';
    return;
  }
  const replies = (view.replies_list || []).map((r) => `
    <div class="ting-reply">
      <div class="who">#${esc(r.n)} ${esc(r.who)} · ${esc(r.clock || clock(r.created_at))}</div>
      <div class="body">${esc(r.body)}</div>
    </div>
  `).join('');
  el.innerHTML = `
    <div class="kicker">${esc(view.board_name)} · #${esc(view.id)}${flags(view)}</div>
    <h3>${esc(view.title)}</h3>
    <div class="who">${esc(view.who)} · ${esc(view.clock || clock(view.created_at))}</div>
    <div class="body">${esc(view.body)}</div>
    <div class="ting-replies">
      ${replies || '<p class="pl-empty">还没有回复。去上手页回。</p>'}
    </div>
  `;
}

async function loadThread(id) {
  state.threadId = Number(id) || 0;
  if (!state.threadId) {
    renderThread(null);
    return;
  }
  const view = await fetch(`/api/public/ting/thread/${state.threadId}`).then((r) => {
    if (!r.ok) throw new Error('missing');
    return r.json();
  }).catch(() => null);
  renderThread(view);
  document.querySelectorAll('.ting-card').forEach((btn) => {
    btn.classList.toggle('is-active', Number(btn.dataset.thread) === state.threadId);
  });
}

async function loadTing() {
  const q = state.board ? `?board=${encodeURIComponent(state.board)}` : '';
  const data = await fetch(`/api/public/ting${q}`).then((r) => r.json());
  const boards = data.boards || [];
  const total = data.total || 0;
  document.getElementById('ting-meta').innerHTML = [
    `<span>木牌 ${esc(total)} 块</span>`,
    ...boards.map((b) => `<span>${esc(b.name)} ${esc(b.threads)}</span>`),
  ].join('');
  document.getElementById('ting-strip').innerHTML =
    `<span class="dot"></span><span>${esc(data.line || '亭里还安静。')}</span>`;
  const title = document.getElementById('ting-list-title');
  if (title) title.textContent = data.board_name ? `${data.board_name}的木牌` : '最近的木牌';
  renderBoards(boards, state.board);
  renderList(data.threads || []);
  if (state.threadId) await loadThread(state.threadId);
}

document.addEventListener('click', (e) => {
  const tab = e.target.closest('[data-board]');
  if (tab) {
    state.board = tab.dataset.board || '';
    state.threadId = 0;
    renderThread(null);
    loadTing();
    return;
  }
  const card = e.target.closest('[data-thread]');
  if (card) loadThread(card.dataset.thread);
});

loadTing();
setInterval(loadTing, 20000);
