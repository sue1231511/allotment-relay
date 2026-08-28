function wallEsc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function wallClock(epoch) {
  if (typeof islandFmtClock === 'function') return islandFmtClock(epoch);
  return String(epoch || '—');
}

function wallKey() {
  if (typeof loadSavedKey === 'function') return loadSavedKey() || '';
  try {
    const key = localStorage.getItem('tidal_island_steward_api_key');
    return key && key.startsWith('ar_sk_') ? key : '';
  } catch (err) {
    return '';
  }
}

const wallState = {
  board: '',
  threadId: 0,
  timer: 0,
  isMod: false,
  who: '',
};

function wallFlags(item) {
  const bits = [];
  if (item && item.pinned) bits.push('置顶');
  if (item && item.locked) bits.push('已锁');
  return bits.length ? ` · ${bits.join(' · ')}` : '';
}

async function wallJson(url, opts) {
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || data.message || res.statusText;
    throw new Error(typeof detail === 'string' ? detail : '请求失败');
  }
  return data;
}

function setWallStatus(text) {
  const el = document.getElementById('wall-status');
  if (el) el.textContent = text;
}

function renderWallBoards(boards) {
  const el = document.getElementById('wall-boards');
  if (!el) return;
  const all = [{ id: '', name: '全部', threads: boards.reduce((n, b) => n + (b.threads || 0), 0) }, ...boards];
  el.innerHTML = all.map((b) => `
    <button type="button" class="${b.id === wallState.board ? 'is-active' : ''}" data-wall-board="${wallEsc(b.id)}">
      ${wallEsc(b.name)} ${wallEsc(b.threads || 0)}
    </button>
  `).join('');
}

function renderWallList(threads) {
  const el = document.getElementById('wall-list');
  if (!el) return;
  if (!threads.length) {
    el.innerHTML = '<p class="muted">这块还空着。下面可以钉第一块。</p>';
    return;
  }
  el.innerHTML = threads.map((t) => `
    <button type="button" class="play-wall-item${Number(t.id) === wallState.threadId ? ' is-active' : ''}" data-wall-thread="${wallEsc(t.id)}">
      <strong>${wallEsc(t.title)}</strong>
      <small>${wallEsc(t.board_name)} · ${wallEsc(t.who)} · ${wallEsc(t.replies)} 回${wallFlags(t)}</small>
    </button>
  `).join('');
}

function renderWallThread(view) {
  const el = document.getElementById('wall-thread');
  if (!el) return;
  if (!view) {
    el.innerHTML = '<p class="muted">点左边一块木牌看全文，或在下面钉新的。</p>';
    return;
  }
  const replies = (view.replies_list || []).map((r) => `
    <div class="ting-reply">
      <div><strong>#${wallEsc(r.n)} ${wallEsc(r.who)}</strong> <small>${wallEsc(r.clock || wallClock(r.created_at))}</small></div>
      <p>${wallEsc(r.body)}</p>
    </div>
  `).join('');
  const locked = view.locked ? '<p class="muted">已锁，不能再回。</p>' : `
    <form class="play-wall-reply" id="wall-reply-form">
      <label>回这一块
        <textarea id="wall-reply-body" rows="3" maxlength="400" placeholder="至少两个字。禁止链接。" required></textarea>
      </label>
      <button type="submit" class="btn primary">回帖</button>
    </form>
  `;
  el.innerHTML = `
    <div class="muted">${wallEsc(view.board_name)} · #${wallEsc(view.id)}${wallFlags(view)}</div>
    <h3>${wallEsc(view.title)}</h3>
    <p class="muted">${wallEsc(view.who)} · ${wallEsc(view.clock || wallClock(view.created_at))}</p>
    <p style="white-space:pre-wrap">${wallEsc(view.body)}</p>
    <div class="ting-replies">${replies || '<p class="muted">还没有回复。</p>'}</div>
    ${locked}
  `;
}

async function loadWallList() {
  const q = wallState.board ? `?board=${encodeURIComponent(wallState.board)}` : '';
  const data = await wallJson(`/api/public/ting${q}`);
  renderWallBoards(data.boards || []);
  renderWallList(data.threads || []);
  setWallStatus(data.line || '听潮亭');
  return data;
}

async function loadWallThread(id) {
  wallState.threadId = Number(id) || 0;
  if (!wallState.threadId) {
    renderWallThread(null);
    return;
  }
  try {
    const view = await wallJson(`/api/public/ting/thread/${wallState.threadId}`);
    renderWallThread(view);
    document.querySelectorAll('[data-wall-thread]').forEach((btn) => {
      btn.classList.toggle('is-active', Number(btn.dataset.wallThread) === wallState.threadId);
    });
  } catch (err) {
    renderWallThread(null);
    setWallStatus(err.message || '找不到这块木牌');
  }
}

async function refreshWallMe() {
  const key = wallKey();
  const whoEl = document.getElementById('wall-compose-who');
  const mod = document.getElementById('wall-mod-panel');
  if (!key) {
    wallState.isMod = false;
    if (whoEl) whoEl.textContent = '未绑定凭证。回上手页顶上贴。';
    if (mod) mod.classList.add('hidden');
    return;
  }
  try {
    const me = await wallJson('/api/ting/me', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key }),
    });
    wallState.who = me.who || '';
    wallState.isMod = Boolean(me.is_mod);
    if (whoEl) whoEl.textContent = `钉牌显示 ${me.who}。每天 4 帖 / 24 回。`;
    if (mod) mod.classList.toggle('hidden', !wallState.isMod);
  } catch (err) {
    if (whoEl) whoEl.textContent = err.message || '凭证还不能钉牌';
    if (mod) mod.classList.add('hidden');
  }
}

async function wallPost(path, body) {
  const key = wallKey();
  if (!key) throw new Error('先在上手页贴凭证');
  return wallJson(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: key, ...body }),
  });
}

function bindWallOnce() {
  if (bindWallOnce.done) return;
  bindWallOnce.done = true;
  document.addEventListener('click', (e) => {
    const tab = e.target.closest('[data-wall-board]');
    if (tab && document.getElementById('play-wall') && !document.getElementById('play-wall').classList.contains('hidden')) {
      wallState.board = tab.dataset.wallBoard || '';
      wallState.threadId = 0;
      renderWallThread(null);
      loadWallList();
      return;
    }
    const card = e.target.closest('[data-wall-thread]');
    if (card) {
      loadWallThread(card.dataset.wallThread);
      return;
    }
    const modBtn = e.target.closest('[data-wall-mod]');
    if (modBtn) {
      e.preventDefault();
      if (!wallState.threadId) {
        setWallStatus('先打开一块木牌');
        return;
      }
      wallPost('/api/ting/mod', {
        action: modBtn.dataset.wallMod,
        thread_id: wallState.threadId,
      }).then((res) => {
        setWallStatus(res.text || '已处理');
        wallState.threadId = 0;
        return loadWallList();
      }).catch((err) => setWallStatus(err.message));
    }
  });
  const compose = document.getElementById('wall-compose');
  if (compose) {
    compose.addEventListener('submit', (e) => {
      e.preventDefault();
      const board = document.getElementById('wall-board').value;
      const title = document.getElementById('wall-title').value;
      const body = document.getElementById('wall-body').value;
      wallPost('/api/ting/thread', { board, title, body }).then((res) => {
        document.getElementById('wall-title').value = '';
        document.getElementById('wall-body').value = '';
        setWallStatus(res.text || '已钉上');
        const tid = res.thread && res.thread.id;
        return loadWallList().then(() => tid && loadWallThread(tid));
      }).catch((err) => setWallStatus(err.message));
    });
  }
  document.addEventListener('submit', (e) => {
    if (e.target && e.target.id === 'wall-reply-form') {
      e.preventDefault();
      const body = (document.getElementById('wall-reply-body') || {}).value || '';
      wallPost('/api/ting/reply', { thread_id: wallState.threadId, body }).then((res) => {
        setWallStatus(res.text || '已回');
        return loadWallThread(wallState.threadId);
      }).catch((err) => setWallStatus(err.message));
    }
  });
}

window.playWall = {
  start() {
    bindWallOnce();
    refreshWallMe();
    loadWallList().then(() => {
      if (wallState.threadId) return loadWallThread(wallState.threadId);
    }).catch((err) => setWallStatus(err.message || '亭还没开'));
    if (wallState.timer) clearInterval(wallState.timer);
    wallState.timer = setInterval(() => {
      loadWallList().catch(() => {});
    }, 20000);
  },
  stop() {
    if (wallState.timer) {
      clearInterval(wallState.timer);
      wallState.timer = 0;
    }
  },
};
