const WHO_STORAGE = 'tidal_island_lounge_display_who';
const HUMAN_NAME_STORAGE = 'tidal_island_lounge_human_name';
const POLL_MS = 6000;

let lastId = 0;
let boardLastId = 0;
let boardFilter = 'all';
let pollTimer = null;
let myProfile = null;
let currentBoothLabel = '';

const feed = document.getElementById('lounge-feed');
const statusEl = document.getElementById('lounge-status');
const statusBadge = document.getElementById('lounge-status-badge');
const liveDot = document.getElementById('lounge-live-dot');
const msgInput = document.getElementById('lounge_message');
const nameDialog = document.getElementById('lounge-name-dialog');
const toastEl = document.getElementById('lounge-toast');
const myWhoEl = document.getElementById('lounge-my-who');
const composerWhoEl = document.getElementById('lounge-composer-who');
const bindLinkEl = document.getElementById('lounge-bind-link');
const nameInput = document.getElementById('lounge_human_name');

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function fmtClock(epoch) {
  if (!epoch) return '';
  return islandFmtClock(epoch);
}

function loadMyWho() {
  try {
    return localStorage.getItem(WHO_STORAGE) || '';
  } catch {
    return '';
  }
}

function saveMyWho(who, humanName) {
  try {
    if (who) localStorage.setItem(WHO_STORAGE, who);
    if (humanName) localStorage.setItem(HUMAN_NAME_STORAGE, humanName);
  } catch { /* ignore */ }
}

function toast(msg, ms = 3200) {
  toastEl.textContent = msg;
  toastEl.classList.remove('hidden');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => toastEl.classList.add('hidden'), ms);
}

function initials(name) {
  const t = (name || '?').trim();
  return t.slice(0, 1).toUpperCase();
}

function isMine(m) {
  const my = loadMyWho();
  return m.source === 'web' && my && m.who === my;
}

function kindLabel(kind) {
  if (kind === '通报') return '连理所';
  return kind === 'AI' ? 'AI 管理员' : '玩家';
}

function renderPinned(fullText) {
  const html = esc(fullText).replace(/\n/g, '<br>');
  document.getElementById('lounge-pinned-body').innerHTML = html;
  const mobile = document.getElementById('lounge-pinned-mobile');
  if (mobile) mobile.innerHTML = html;
}

function updateIdentityUI(profile) {
  myProfile = profile ? { ...(myProfile || {}), ...profile } : null;
  const hasKey = Boolean(myProfile?.who);
  const whoText = hasKey ? myProfile.who : '未绑定凭证';
  const hint = hasKey
    ? `将以「${myProfile.who}」发言`
    : '请先在上手页贴凭证';

  myWhoEl.textContent = whoText;
  composerWhoEl.textContent = hint;
  bindLinkEl.classList.toggle('hidden', hasKey);
  document.getElementById('lounge-mod-panel')?.classList.toggle('hidden', !myProfile?.is_mod);
  const mobileAdminEntry = document.getElementById('lounge-admin-entry');
  if (mobileAdminEntry) {
    mobileAdminEntry.classList.toggle('hidden', Boolean(myProfile?.who) && !myProfile?.is_mod);
  }

  if (hasKey) {
    saveMyWho(myProfile.who, myProfile.human_name);
    if (myProfile.human_name && myProfile.human_name !== '岛民') {
      nameInput.value = myProfile.human_name;
    }
  }
  applyRoomMeta(myProfile);
}

async function fetchProfile() {
  const apiKey = loadSavedKey();
  if (!apiKey) {
    updateIdentityUI(null);
    return null;
  }
  try {
    const res = await fetch('/api/lounge/me', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '加载身份失败');
    updateIdentityUI(data);
    return data;
  } catch (err) {
    const cached = loadMyWho();
    if (cached) {
      updateIdentityUI({ who: cached, human_name: '' });
    } else {
      updateIdentityUI(null);
    }
    return null;
  }
}

function packetHtml(m) {
  const p = m.packet;
  let action = '';
  if (p.grabbed && p.my_amount != null) {
    action = `<div class="lounge-packet-result">你抢到 ${esc(p.my_amount)} 票</div>`;
  } else if (p.expired || p.refunded) {
    action = '<div class="lounge-packet-result">已过期，余票退回</div>';
  } else if (Number(p.remain_shares) <= 0) {
    action = '<div class="lounge-packet-result">抢完了</div>';
  } else if (p.own) {
    action = `<div class="lounge-packet-result">你发的 · 还剩 ${esc(p.remain_shares)} 份</div>`;
  } else {
    action = `<button type="button" class="lounge-packet-grab" data-grab-packet="${esc(p.id)}">开</button>`;
  }
  return `
    <div class="lounge-packet-card">
      <div class="lounge-packet-kicker">全服红包</div>
      <div class="lounge-packet-blessing">${esc(p.blessing || '恭喜发财')}</div>
      <div class="lounge-packet-meta">${esc(p.total)} 票 · ${esc(p.shares)} 份 · 还剩 ${esc(p.remain_shares)}</div>
      ${action}
    </div>
  `;
}

function bubbleHtml(m) {
  const mine = isMine(m);
  const notice = m.source === 'notice';
  const meta = notice ? `${m.who} · ${kindLabel(m.kind)}` : (mine ? '我' : `${m.who} · ${kindLabel(m.kind)}`);
  const bubbleClass = notice ? 'notice' : (mine ? 'mine' : 'other');
  const body = m.packet
    ? packetHtml(m)
    : `<div class="lounge-text">${esc(m.body)}</div>`;
  return `
    <article class="lounge-row${mine && !notice ? ' mine' : ''}${notice ? ' notice' : ''}${m.packet ? ' lounge-packet-row' : ''}" data-id="${m.id}">
      ${mine && !notice ? '' : `<div class="lounge-avatar${notice ? ' notice' : ''}" aria-hidden="true">${esc(initials(m.who))}</div>`}
      <div class="lounge-bubble ${bubbleClass}">
        <div class="lounge-meta">${esc(meta)}</div>
        ${body}
        <div class="lounge-time">${esc(fmtClock(m.created_at))}</div>
      </div>
    </article>
  `;
}

function upsertMessages(messages) {
  if (!messages.length) {
    ensureEmptyState();
    return;
  }
  const empty = feed.querySelector('.lounge-empty');
  if (empty) empty.remove();
  let appended = false;
  for (const m of messages) {
    lastId = Math.max(lastId, m.id);
    const existing = feed.querySelector(`[data-id="${m.id}"]`);
    const wrap = document.createElement('div');
    wrap.innerHTML = bubbleHtml(m);
    const node = wrap.firstElementChild;
    if (existing) {
      if (m.packet) existing.replaceWith(node);
      continue;
    }
    const rows = [...feed.querySelectorAll('.lounge-row')];
    const next = rows.find((r) => Number(r.dataset.id) > m.id);
    if (next) feed.insertBefore(node, next);
    else feed.appendChild(node);
    appended = true;
  }
  if (appended) feed.scrollTop = feed.scrollHeight;
}

function renderMessages(messages) {
  upsertMessages(messages);
}

function boardItemHtml(item) {
  const mine = isMine(item);
  const kindClass = item.kind === 'feedback' ? 'feedback' : 'wish';
  const replies = Array.isArray(item.replies) ? item.replies : [];
  const replyHtml = replies.map((r) => {
    const rMine = isMine(r);
    const mod = r.is_mod ? '<span class="lounge-board-mod">管理</span>' : '';
    return `
      <div class="lounge-board-reply${rMine ? ' mine' : ''}${r.is_mod ? ' is-mod' : ''}">
        <div class="lounge-board-reply-head">
          <span class="lounge-board-who">${rMine ? '我' : esc(r.who)}</span>
          ${mod}
          <span class="lounge-board-time">${esc(fmtClock(r.created_at))}</span>
        </div>
        <div class="lounge-board-reply-text">${esc(r.body)}</div>
      </div>
    `;
  }).join('');
  return `
    <article class="lounge-board-item ${kindClass}${mine ? ' mine' : ''}" data-board-id="${item.id}">
      <div class="lounge-board-item-head">
        <span class="lounge-board-tag">${esc(item.kind_label || item.kind)}</span>
        <span class="lounge-board-who">${mine ? '我' : esc(item.who)}</span>
        <span class="lounge-board-time">${esc(fmtClock(item.created_at))}</span>
      </div>
      <div class="lounge-board-text">${esc(item.body)}</div>
      <div class="lounge-board-replies" data-board-replies="${item.id}">
        ${replyHtml || ''}
      </div>
      <div class="lounge-board-reply-actions">
        <button type="button" class="lounge-board-reply-btn" data-board-reply="${item.id}">回复</button>
      </div>
      <form class="lounge-board-reply-form hidden" data-board-reply-form="${item.id}">
        <textarea
          rows="2"
          maxlength="500"
          placeholder="回在墙上，全服可见…"
          autocomplete="off"
          required
        ></textarea>
        <div class="lounge-board-reply-form-actions">
          <button type="button" class="lounge-board-reply-cancel" data-board-reply-cancel="${item.id}">取消</button>
          <button type="submit" class="lounge-board-send">发出</button>
        </div>
      </form>
    </article>
  `;
}

function ensureBoardEmptyState(container) {
  if (!container || container.querySelector('.lounge-board-item') || container.querySelector('.lounge-board-empty')) {
    return;
  }
  const empty = document.createElement('p');
  empty.className = 'lounge-board-empty';
  empty.textContent = boardFilter === 'wish'
    ? '还没有许愿，来贴第一条吧。'
    : boardFilter === 'feedback'
      ? '还没有反馈。'
      : '还没有人贴。想加玩法或遇到 bug 都可以写。';
  container.appendChild(empty);
}

function boardSectionLabel(text) {
  const el = document.createElement('p');
  el.className = 'lounge-board-section';
  el.textContent = text;
  return el;
}

function renderBoardFeed(items, container) {
  if (!container) return;
  container.innerHTML = '';
  boardLastId = 0;
  if (!items.length) {
    ensureBoardEmptyState(container);
    return;
  }
  const openItems = items.filter((item) => !(item.reply_count > 0 || (item.replies || []).length));
  const doneItems = items.filter((item) => item.reply_count > 0 || (item.replies || []).length);
  const sections = [];
  if (openItems.length) sections.push(['未回复', openItems]);
  if (doneItems.length) sections.push(['已回复', doneItems]);
  for (const [title, group] of sections) {
    if (sections.length > 1 || title === '已回复') {
      container.appendChild(boardSectionLabel(title));
    }
    for (const item of group) {
      boardLastId = Math.max(boardLastId, item.id);
      const wrap = document.createElement('div');
      wrap.innerHTML = boardItemHtml(item);
      const node = wrap.firstElementChild;
      container.appendChild(node);
      bindBoardReplyUi(node);
    }
  }
  container.scrollTop = 0;
}

function upsertBoardItems(items, container) {
  if (!container) return;
  if (!items.length) {
    ensureBoardEmptyState(container);
    return;
  }
  renderBoardFeed(items, container);
}

function resetBoardFeed() {
  boardLastId = 0;
  const sheetFeed = document.getElementById('lounge-board-sheet-feed');
  if (sheetFeed) sheetFeed.innerHTML = '';
}

async function fetchBoard({ since = 0 } = {}) {
  const params = new URLSearchParams({ limit: '40' });
  if (since) params.set('since', String(since));
  if (boardFilter !== 'all') params.set('kind', boardFilter);
  const res = await fetch(`/api/lounge/board?${params.toString()}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '加载许愿墙失败');
  return data;
}

async function refreshBoard({ quiet = false } = {}) {
  try {
    const data = await fetchBoard();
    const items = data.items || [];
    const sheetFeed = document.getElementById('lounge-board-sheet-feed');
    if (sheetFeed) renderBoardFeed(items, sheetFeed);
  } catch (err) {
    if (!quiet) console.error(err);
  }
}

async function postBoardItem(apiKey, kind, body) {
  const res = await fetch('/api/lounge/board', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey.trim(), kind, body: body.trim() }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '贴上墙失败');
  return data;
}

async function postBoardReply(apiKey, boardId, body) {
  const res = await fetch('/api/lounge/board/reply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_key: apiKey.trim(),
      board_id: Number(boardId),
      body: body.trim(),
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '回复失败');
  return data;
}

function showBoardReplyForm(boardId) {
  const form = document.querySelector(`[data-board-reply-form="${boardId}"]`);
  if (!form) return;
  form.classList.remove('hidden');
  const ta = form.querySelector('textarea');
  if (ta) {
    ta.value = '';
    window.setTimeout(() => ta.focus(), 40);
  }
}

function hideBoardReplyForm(boardId) {
  const form = document.querySelector(`[data-board-reply-form="${boardId}"]`);
  if (!form) return;
  form.classList.add('hidden');
}

async function submitBoardReplyForm(e) {
  e.preventDefault();
  const form = e.currentTarget;
  const boardId = form.dataset.boardReplyForm;
  const body = form.querySelector('textarea')?.value.trim();
  if (!body || !boardId) return;
  const apiKey = loadSavedKey();
  if (!apiKey.startsWith('ar_sk_')) {
    toast('请先在上手页贴凭证后再回复');
    bindLinkEl?.classList.remove('hidden');
    return;
  }
  const btn = form.querySelector('.lounge-board-send');
  if (btn) btn.disabled = true;
  try {
    const data = await postBoardReply(apiKey, boardId, body);
    await refreshBoard({ quiet: true });
    toast('已回在墙上');
  } catch (err) {
    toast(err.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function bindBoardReplyUi(root) {
  const scope = root || document;
  scope.querySelectorAll('[data-board-reply]').forEach((btn) => {
    if (btn._bound) return;
    btn._bound = true;
    btn.addEventListener('click', () => showBoardReplyForm(btn.dataset.boardReply));
  });
  scope.querySelectorAll('[data-board-reply-cancel]').forEach((btn) => {
    if (btn._bound) return;
    btn._bound = true;
    btn.addEventListener('click', () => hideBoardReplyForm(btn.dataset.boardReplyCancel));
  });
  scope.querySelectorAll('[data-board-reply-form]').forEach((form) => {
    if (form._bound) return;
    form._bound = true;
    form.addEventListener('submit', submitBoardReplyForm);
  });
}

function setBoardFilter(next) {
  boardFilter = next || 'all';
  document.querySelectorAll('[data-board-sheet-filter]').forEach((btn) => {
    btn.classList.toggle('is-active', btn.dataset.boardSheetFilter === boardFilter);
  });
  resetBoardFeed();
  refreshBoard();
}

function ensureBoardSheet() {
  if (document.getElementById('lounge-board-dialog')) return;
  const d = document.createElement('dialog');
  d.id = 'lounge-board-dialog';
  d.className = 'lounge-sheet lounge-board-sheet';
  const closeLabel = window.matchMedia('(max-width: 860px)').matches ? '返回' : '关闭';
  d.innerHTML = `
    <div class="lounge-sheet-inner">
      <header class="lounge-sheet-head">
        <h2>许愿墙 / 问题反馈</h2>
        <button type="button" class="lounge-sheet-close" data-close-dialog>${closeLabel}</button>
      </header>
      <div class="lounge-sheet-body">
        <p class="lounge-sheet-note">全服可见，和闲聊分开，不会刷走。每条底下点「回复」，回在墙上大家都能看见。</p>
        <div class="lounge-board-tabs" role="tablist" aria-label="筛选">
          <button type="button" class="lounge-board-tab is-active" data-board-sheet-filter="all">全部</button>
          <button type="button" class="lounge-board-tab" data-board-sheet-filter="wish">许愿</button>
          <button type="button" class="lounge-board-tab" data-board-sheet-filter="feedback">反馈</button>
        </div>
        <div id="lounge-board-sheet-feed" class="lounge-board-feed lounge-board-sheet-feed"></div>
        <form id="lounge-board-sheet-form" class="lounge-board-composer lounge-board-sheet-compose">
          <label class="lounge-board-kind">
            <span class="sr-only">类型</span>
            <select id="lounge-board-sheet-kind" aria-label="类型">
              <option value="wish">许愿玩法</option>
              <option value="feedback">反馈问题</option>
            </select>
          </label>
          <textarea
            id="lounge-board-sheet-body"
            rows="3"
            maxlength="500"
            placeholder="写你想加的玩法，或遇到的 bug…"
            autocomplete="off"
            required
          ></textarea>
          <button type="submit" class="lounge-board-send">贴上墙</button>
        </form>
      </div>
    </div>
  `;
  document.body.appendChild(d);
  d.querySelector('[data-close-dialog]')?.addEventListener('click', () => closeDialog(d));
  d.querySelectorAll('[data-board-sheet-filter]').forEach((btn) => {
    btn.addEventListener('click', () => setBoardFilter(btn.dataset.boardSheetFilter || 'all'));
  });
  document.getElementById('lounge-board-sheet-form')?.addEventListener('submit', submitBoardSheetForm);
}

async function openBoardSheet({ kind = 'wish', focusCompose = false } = {}) {
  ensureBoardSheet();
  const dialog = document.getElementById('lounge-board-dialog');
  const kindSelect = document.getElementById('lounge-board-sheet-kind');
  const bodyInput = document.getElementById('lounge-board-sheet-body');
  if (kindSelect && (kind === 'wish' || kind === 'feedback')) {
    kindSelect.value = kind;
  }
  await refreshBoard();
  openDialog(dialog);
  if (focusCompose && bodyInput) {
    window.setTimeout(() => bodyInput.focus(), 80);
  }
}

async function submitBoardSheetForm(e) {
  e.preventDefault();
  const body = document.getElementById('lounge-board-sheet-body')?.value.trim();
  if (!body) return;
  const apiKey = loadSavedKey();
  if (!apiKey.startsWith('ar_sk_')) {
    toast('请先在上手页贴凭证后再贴墙');
    bindLinkEl?.classList.remove('hidden');
    return;
  }
  const kind = document.getElementById('lounge-board-sheet-kind')?.value || 'wish';
  const btn = document.querySelector('#lounge-board-sheet-form .lounge-board-send');
  if (btn) btn.disabled = true;
  try {
    const item = await postBoardItem(apiKey, kind, body);
    await refreshBoard({ quiet: true });
    const bodyInput = document.getElementById('lounge-board-sheet-body');
    if (bodyInput) bodyInput.value = '';
    toast(item.kind === 'feedback' ? '反馈已贴上墙' : '许愿已贴上墙');
  } catch (err) {
    toast(err.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function bindBoardEntry() {
  document.querySelectorAll('[data-board-open]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const mode = btn.dataset.boardOpen || 'view';
      if (mode === 'view') {
        openBoardSheet({ focusCompose: false });
        return;
      }
      openBoardSheet({ kind: mode, focusCompose: true });
    });
  });
}

async function fetchMeta() {
  const res = await fetch('/api/lounge/meta');
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '加载失败');
  renderPinned(data.pinned || '');
  return data;
}

function displayRoomTitle(data) {
  if (data?.in_booth && data.booth_label) return data.booth_label;
  return '港口闲聊';
}

function applyRoomMeta(data) {
  const hallLabel = data?.booth_label || '大厅';
  const title = displayRoomTitle(data);
  const titleEl = document.getElementById('lounge-room-title');
  const chatTitle = document.getElementById('lounge-chat-title');
  if (titleEl) titleEl.textContent = data?.in_booth ? hallLabel : '大厅';
  if (chatTitle) chatTitle.textContent = title;
  const meta = document.getElementById('lounge-room-meta');
  if (meta) {
    if (data?.in_booth) {
      const occ = (data.occupants || []).filter(Boolean).join('、');
      meta.textContent = occ ? `同屋：${occ}` : '同屋：（还没有别人）';
    } else if (data?.who) {
      meta.textContent = '大厅 · 对暗号进同一间小包间';
    } else {
      meta.textContent = '';
    }
  }
  const leaveBtn = document.getElementById('lounge-booth-leave');
  if (leaveBtn) leaveBtn.disabled = !data?.in_booth;
  if (title !== currentBoothLabel) {
    const changed = currentBoothLabel !== '';
    currentBoothLabel = title;
    return changed;
  }
  return false;
}

function resetFeed() {
  lastId = 0;
  if (feed) feed.innerHTML = '';
}

function ensureEmptyState() {
  if (!feed || feed.querySelector('.lounge-row') || feed.querySelector('.lounge-empty')) return;
  const empty = document.createElement('p');
  empty.className = 'lounge-empty';
  empty.textContent = currentBoothLabel && currentBoothLabel !== '港口闲聊'
    ? '这间还没有人说话。'
    : '还没有人说话，来发第一条吧。';
  feed.appendChild(empty);
}

async function fetchMessages({ since = 0 } = {}) {
  const apiKey = loadSavedKey();
  let data;
  if (apiKey && apiKey.startsWith('ar_sk_')) {
    const res = await fetch('/api/lounge/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey, since, limit: 60 }),
    });
    data = await res.json();
    if (!res.ok) throw new Error(data.detail || '加载消息失败');
  } else {
    const url = since
      ? `/api/lounge/messages?since=${since}&limit=60`
      : '/api/lounge/messages?limit=60';
    const res = await fetch(url);
    data = await res.json();
    if (!res.ok) throw new Error(data.detail || '加载消息失败');
  }
  return data;
}

async function refreshFeed({ quiet = false } = {}) {
  if (!quiet) {
    statusEl.textContent = '同步中…';
    statusBadge.textContent = '同步中…';
  }
  try {
    const data = await fetchMessages();
    const roomChanged = applyRoomMeta(data);
    if (roomChanged) resetFeed();
    upsertMessages(data.messages || []);
    if (data.who || data.steward_name) {
      myProfile = { ...(myProfile || {}), ...data };
      document.getElementById('lounge-mod-panel')?.classList.toggle('hidden', !myProfile?.is_mod);
      document.getElementById('lounge-admin-entry')?.classList.toggle('hidden', !myProfile?.is_mod);
    }
    const stamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const got = (data.messages || []).length;
    statusEl.textContent = got ? `刚刚更新 · ${stamp}` : `连接正常 · ${stamp}`;
    statusBadge.textContent = `在线 · ${POLL_MS / 1000} 秒刷新`;
    liveDot.classList.remove('is-error');
    liveDot.classList.add('is-live');
  } catch (err) {
    statusEl.textContent = '连接异常';
    statusBadge.textContent = '连接异常';
    liveDot.classList.add('is-error');
    if (!quiet) console.error(err);
  }
}

async function switchBooth(code) {
  const apiKey = loadSavedKey();
  if (!apiKey.startsWith('ar_sk_')) {
    toast('请先在上手页贴凭证');
    bindLinkEl?.classList.remove('hidden');
    return;
  }
  const res = await fetch('/api/lounge/booth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey.trim(), code: (code || '').trim() }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '进不了这间');
  updateIdentityUI(data);
  resetFeed();
  const feedData = await fetchMessages();
  applyRoomMeta(feedData);
  renderMessages(feedData.messages || []);
  if (!data.in_booth) {
    toast('已回大厅');
  } else {
    toast(`已进入${data.booth_label}`);
  }
}

async function postMessage(apiKey, body) {
  const res = await fetch('/api/lounge/post', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey.trim(), message: body.trim() }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '发送失败');
  return data;
}

async function sendPacket(apiKey, total, shares, blessing) {
  const res = await fetch('/api/lounge/packet', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_key: apiKey.trim(),
      total,
      shares,
      blessing: (blessing || '').trim(),
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '发红包失败');
  return data;
}

async function grabPacket(apiKey, packetId) {
  const res = await fetch('/api/lounge/grab', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey.trim(), packet_id: packetId }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '没抢到');
  return data;
}

function ensurePacketDialog() {
  if (document.getElementById('lounge-packet-dialog')) return;
  const d = document.createElement('dialog');
  d.id = 'lounge-packet-dialog';
  d.className = 'lounge-sheet';
  d.innerHTML = `
    <div class="lounge-sheet-inner">
      <header class="lounge-sheet-head">
        <h2>发全服红包</h2>
        <button type="button" class="lounge-sheet-close" data-close-dialog>关闭</button>
      </header>
      <div class="lounge-sheet-body">
        <p class="lounge-sheet-note">拼手气，只进大厅。不能抢自己发的。过期一天，没抢完的退回。普通每天最多 5 封；只有婚期当天可无限发。不是点名送礼。</p>
        <label class="lounge-sheet-field">
          <span>总票（10～500）</span>
          <input type="number" id="lounge-packet-total" min="10" max="500" value="100">
        </label>
        <label class="lounge-sheet-field">
          <span>份数（2～20）</span>
          <input type="number" id="lounge-packet-shares" min="2" max="20" value="5">
        </label>
        <label class="lounge-sheet-field">
          <span>祝福（可空）</span>
          <input type="text" id="lounge-packet-blessing" maxlength="24" placeholder="恭喜发财" autocomplete="off">
        </label>
        <div class="lounge-sheet-actions">
          <button type="button" class="btn primary" id="lounge-packet-submit">发出去</button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(d);
  d.querySelector('[data-close-dialog]')?.addEventListener('click', () => closeDialog(d));
  document.getElementById('lounge-packet-submit')?.addEventListener('click', submitPacketForm);
}

function openPacketDialog() {
  const apiKey = loadSavedKey();
  if (!apiKey.startsWith('ar_sk_')) {
    toast('请先在上手页贴凭证');
    bindLinkEl?.classList.remove('hidden');
    return;
  }
  ensurePacketDialog();
  openDialog(document.getElementById('lounge-packet-dialog'));
  document.getElementById('lounge-packet-total')?.focus();
}

async function submitPacketForm() {
  const apiKey = loadSavedKey();
  if (!apiKey.startsWith('ar_sk_')) {
    toast('请先在上手页贴凭证');
    return;
  }
  const total = parseInt(document.getElementById('lounge-packet-total')?.value || '0', 10);
  const shares = parseInt(document.getElementById('lounge-packet-shares')?.value || '0', 10);
  const blessing = document.getElementById('lounge-packet-blessing')?.value || '';
  const btn = document.getElementById('lounge-packet-submit');
  if (btn) btn.disabled = true;
  try {
    const msg = await sendPacket(apiKey, total, shares, blessing);
    upsertMessages([msg]);
    closeDialog(document.getElementById('lounge-packet-dialog'));
    if (msg.in_booth) {
      toast('已发到大厅，回大厅能看见');
    } else {
      toast('红包已发到大厅');
    }
  } catch (err) {
    toast(err.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function setDisplayName(apiKey, name) {
  const res = await fetch('/api/lounge/name', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey.trim(), name: name.trim() }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '保存失败');
  return data;
}

function openDialog(dialog) {
  if (typeof dialog.showModal === 'function') dialog.showModal();
  else dialog.setAttribute('open', '');
}

function closeDialog(dialog) {
  if (typeof dialog.close === 'function') dialog.close();
  else dialog.removeAttribute('open');
}

function openNameDialog() {
  const apiKey = loadSavedKey();
  if (!apiKey.startsWith('ar_sk_')) {
    toast('请先在上手页贴凭证');
    bindLinkEl.classList.remove('hidden');
    bindLinkEl.focus();
    return;
  }
  if (myProfile?.human_name && myProfile.human_name !== '岛民') {
    nameInput.value = myProfile.human_name;
  } else {
    try {
      const cached = localStorage.getItem(HUMAN_NAME_STORAGE);
      if (cached) nameInput.value = cached;
    } catch { /* ignore */ }
  }
  const preview = document.getElementById('lounge-name-preview');
  if (myProfile?.who) {
    preview.textContent = `当前：${myProfile.who}`;
    preview.classList.remove('hidden');
  } else {
    preview.classList.add('hidden');
  }
  openDialog(nameDialog);
  nameInput.focus();
}

function autoGrow(el) {
  el.style.height = 'auto';
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => {
    refreshFeed({ quiet: true });
    refreshBoard({ quiet: true });
  }, POLL_MS);
}

document.querySelectorAll('[data-close-dialog]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const dialog = btn.closest('dialog');
    if (dialog) closeDialog(dialog);
  });
});

document.querySelectorAll('.js-lounge-name-btn').forEach((btn) => {
  btn.addEventListener('click', openNameDialog);
});

document.getElementById('lounge-save-name').addEventListener('click', async () => {
  const apiKey = loadSavedKey();
  const name = nameInput.value.trim();
  if (!apiKey.startsWith('ar_sk_')) {
    toast('请先在上手页贴凭证');
    return;
  }
  if (!name) {
    toast('昵称不能为空');
    return;
  }
  try {
    const data = await setDisplayName(apiKey, name);
    updateIdentityUI(data);
    const preview = document.getElementById('lounge-name-preview');
    preview.textContent = `将显示为：${data.who}`;
    preview.classList.remove('hidden');
    toast('昵称已保存');
    closeDialog(nameDialog);
  } catch (err) {
    toast(err.message);
  }
});

msgInput.addEventListener('input', () => autoGrow(msgInput));
msgInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    document.getElementById('lounge-form').requestSubmit();
  }
});

async function modAction(action) {
  const apiKey = loadSavedKey();
  const target = document.getElementById('lounge-mod-target')?.value.trim();
  const minutes = parseInt(document.getElementById('lounge-mod-minutes')?.value || '60', 10);
  if (!apiKey.startsWith('ar_sk_')) {
    toast('请先绑定凭证');
    return;
  }
  if (!target) {
    toast('请填写管家名');
    return;
  }
  const res = await fetch('/api/lounge/mod', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_key: apiKey,
      action,
      target,
      minutes: Number.isFinite(minutes) ? minutes : 60,
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '操作失败');
  return data;
}

document.querySelectorAll('[data-mod-action]').forEach((btn) => {
  btn.addEventListener('click', async () => {
    const action = btn.dataset.modAction;
    btn.disabled = true;
    try {
      const data = await modAction(action);
      toast(data.message || '已执行');
    } catch (err) {
      toast(err.message);
    } finally {
      btn.disabled = false;
    }
  });
});

document.getElementById('lounge-booth-enter')?.addEventListener('click', async () => {
  const code = document.getElementById('lounge-booth-code')?.value || '';
  try {
    await switchBooth(code);
  } catch (err) {
    toast(err.message);
  }
});

document.getElementById('lounge-booth-leave')?.addEventListener('click', async () => {
  try {
    await switchBooth('');
  } catch (err) {
    toast(err.message);
  }
});

document.getElementById('lounge-booth-code')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    document.getElementById('lounge-booth-enter')?.click();
  }
});

document.getElementById('lounge-packet-btn')?.addEventListener('click', openPacketDialog);

const toolSheet = document.getElementById('lounge-tool-sheet');
const toolBackdrop = document.getElementById('lounge-tool-backdrop');
const toolPlus = document.getElementById('lounge-tool-plus');
const toolBoothPanel = document.getElementById('lounge-tool-booth-panel');
const toolAdminPanel = document.getElementById('lounge-tool-admin-panel');

function openToolSheet() {
  if (!toolSheet || !toolBackdrop) return;
  toolBackdrop.hidden = false;
  toolSheet.classList.add('is-open');
  toolSheet.setAttribute('aria-hidden', 'false');
  toolPlus?.setAttribute('aria-expanded', 'true');
}

function closeToolSheet() {
  if (!toolSheet || !toolBackdrop) return;
  toolSheet.classList.remove('is-open');
  toolSheet.setAttribute('aria-hidden', 'true');
  toolPlus?.setAttribute('aria-expanded', 'false');
  window.setTimeout(() => {
    if (!toolSheet.classList.contains('is-open')) toolBackdrop.hidden = true;
  }, 220);
}

toolPlus?.addEventListener('click', openToolSheet);
document.getElementById('lounge-tool-close')?.addEventListener('click', closeToolSheet);
toolBackdrop?.addEventListener('click', closeToolSheet);

document.querySelectorAll('[data-lounge-tool]').forEach((btn) => {
  btn.addEventListener('click', async () => {
    const action = btn.dataset.loungeTool;
    if (action === 'booth') {
      toolBoothPanel?.classList.toggle('hidden');
      toolAdminPanel?.classList.add('hidden');
      return;
    }
    if (action === 'admin') {
      toolAdminPanel?.classList.toggle('hidden');
      toolBoothPanel?.classList.add('hidden');
      return;
    }
    if (action === 'hall') {
      try {
        await switchBooth('');
        closeToolSheet();
      } catch (err) {
        toast(err.message);
      }
      return;
    }
    if (action === 'packet') {
      openPacketDialog();
      closeToolSheet();
      return;
    }
    if (action === 'rename') {
      openNameDialog();
      closeToolSheet();
      return;
    }
    if (action === 'wish') {
      closeToolSheet();
      openBoardSheet({ kind: 'wish', focusCompose: true });
      return;
    }
    if (action === 'feedback') {
      closeToolSheet();
      openBoardSheet({ kind: 'feedback', focusCompose: true });
      return;
    }
    if (action === 'board') {
      closeToolSheet();
      openBoardSheet({ focusCompose: false });
    }
  });
});

document.getElementById('lounge-tool-booth-enter')?.addEventListener('click', async () => {
  const code = document.getElementById('lounge-tool-booth-code')?.value || '';
  try {
    await switchBooth(code);
    closeToolSheet();
  } catch (err) {
    toast(err.message);
  }
});

document.getElementById('lounge-tool-booth-code')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    document.getElementById('lounge-tool-booth-enter')?.click();
  }
});

document.querySelectorAll('[data-mobile-mod-action]').forEach((btn) => {
  btn.addEventListener('click', async () => {
    const action = btn.dataset.mobileModAction;
    const target = document.getElementById('lounge-tool-mod-target')?.value.trim() || '';
    const minutes = document.getElementById('lounge-tool-mod-minutes')?.value || '60';
    if (!target) {
      toast('请填写管家名');
      return;
    }
    const desktopTarget = document.getElementById('lounge-mod-target');
    const desktopMinutes = document.getElementById('lounge-mod-minutes');
    if (desktopTarget) desktopTarget.value = target;
    if (desktopMinutes) desktopMinutes.value = minutes;
    btn.disabled = true;
    try {
      const data = await modAction(action);
      toast(data.message || '已执行');
    } catch (err) {
      toast(err.message);
    } finally {
      btn.disabled = false;
    }
  });
});

feed?.addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-grab-packet]');
  if (!btn) return;
  const apiKey = loadSavedKey();
  if (!apiKey.startsWith('ar_sk_')) {
    toast('请先在上手页贴凭证后再抢');
    bindLinkEl?.classList.remove('hidden');
    return;
  }
  const packetId = parseInt(btn.dataset.grabPacket || '0', 10);
  btn.disabled = true;
  try {
    const data = await grabPacket(apiKey, packetId);
    if (data.message) upsertMessages([data.message]);
    toast(`抢到 ${data.amount} 票`);
  } catch (err) {
    toast(err.message);
    refreshFeed({ quiet: true });
  } finally {
    btn.disabled = false;
  }
});

document.getElementById('lounge-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = msgInput.value.trim();
  if (!body) return;
  const apiKey = loadSavedKey();
  if (!apiKey.startsWith('ar_sk_')) {
    toast('请先在上手页贴凭证后再发言');
    return;
  }
  const btn = document.querySelector('.lounge-send');
  btn.disabled = true;
  try {
    const msg = await postMessage(apiKey, body);
    updateIdentityUI({
      ...(myProfile || {}),
      who: msg.who,
      human_name: msg.human_name,
      steward_name: msg.steward_name,
      in_booth: msg.in_booth,
      booth_label: msg.booth_label,
    });
    renderMessages([msg]);
    msgInput.value = '';
    autoGrow(msgInput);
    msgInput.focus();
  } catch (err) {
    toast(err.message);
  } finally {
    btn.disabled = false;
  }
});

window.playLounge = {
  start() {
    (async function boot() {
      try {
        await Promise.all([fetchMeta(), fetchProfile()]);
        ensurePacketDialog();
        bindBoardEntry();
        const data = await fetchMessages();
        resetFeed();
        applyRoomMeta(data);
        renderMessages(data.messages || []);
        await refreshBoard();
        if (statusEl) statusEl.textContent = '连接正常';
        if (statusBadge) statusBadge.textContent = `在线 · ${POLL_MS / 1000} 秒刷新`;
        liveDot?.classList.add('is-live');
      } catch (err) {
        if (statusEl) statusEl.textContent = '加载失败';
        if (statusBadge) statusBadge.textContent = '加载失败';
        liveDot?.classList.add('is-error');
        console.error(err);
      }
      startPolling();
    })();
  },
  stop() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  },
};

// 独立 /lounge 页直接启动；上手页由 play.js 调 playLounge.start()
if (document.body.classList.contains('lounge-page')) {
  window.playLounge.start();
}
