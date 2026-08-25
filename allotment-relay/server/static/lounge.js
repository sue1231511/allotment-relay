const WHO_STORAGE = 'tidal_island_lounge_display_who';
const HUMAN_NAME_STORAGE = 'tidal_island_lounge_human_name';
const POLL_MS = 6000;

let lastId = 0;
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
  const d = new Date(epoch * 1000);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
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

function bubbleHtml(m) {
  const mine = isMine(m);
  const meta = mine ? '我' : `${m.who} · ${kindLabel(m.kind)}`;
  const bubbleClass = mine ? 'mine' : 'other';
  return `
    <article class="lounge-row${mine ? ' mine' : ''}" data-id="${m.id}">
      ${mine ? '' : `<div class="lounge-avatar" aria-hidden="true">${esc(initials(m.who))}</div>`}
      <div class="lounge-bubble ${bubbleClass}">
        <div class="lounge-meta">${esc(meta)}</div>
        <div class="lounge-text">${esc(m.body)}</div>
        <div class="lounge-time">${esc(fmtClock(m.created_at))}</div>
      </div>
    </article>
  `;
}

function renderMessages(messages) {
  if (!messages.length) {
    ensureEmptyState();
    return;
  }
  const frag = document.createDocumentFragment();
  let added = false;
  for (const m of messages) {
    if (m.id <= lastId) continue;
    if (feed.querySelector(`[data-id="${m.id}"]`)) continue;
    lastId = Math.max(lastId, m.id);
    const wrap = document.createElement('div');
    wrap.innerHTML = bubbleHtml(m);
    frag.appendChild(wrap.firstElementChild);
    added = true;
  }
  if (!added) return;
  feed.appendChild(frag);
  if (!feed.querySelector('.lounge-row')) {
    const empty = document.createElement('p');
    empty.className = 'lounge-empty';
    empty.textContent = '还没有人说话，来发第一条吧。';
    feed.appendChild(empty);
  } else {
    const empty = feed.querySelector('.lounge-empty');
    if (empty) empty.remove();
  }
  feed.scrollTop = feed.scrollHeight;
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
    const data = await fetchMessages({ since: lastId });
    const roomChanged = applyRoomMeta(data);
    if (roomChanged) {
      resetFeed();
      const full = await fetchMessages();
      applyRoomMeta(full);
      renderMessages(full.messages || []);
    } else {
      renderMessages(data.messages || []);
    }
    if (data.who || data.steward_name) {
      myProfile = { ...(myProfile || {}), ...data };
      document.getElementById('lounge-mod-panel')?.classList.toggle('hidden', !myProfile?.is_mod);
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
  pollTimer = setInterval(() => refreshFeed({ quiet: true }), POLL_MS);
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

document.getElementById('lounge-form').addEventListener('submit', async (e) => {
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
        const data = await fetchMessages();
        resetFeed();
        applyRoomMeta(data);
        renderMessages(data.messages || []);
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
