const KEY_STORAGE = 'tidal_island_steward_api_key';
const WHO_STORAGE = 'tidal_island_lounge_display_who';
const HUMAN_NAME_STORAGE = 'tidal_island_lounge_human_name';
const POLL_MS = 6000;

let lastId = 0;
let pollTimer = null;
let myProfile = null;

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

function loadSavedKey() {
  try {
    const key = localStorage.getItem(KEY_STORAGE);
    return key && key.startsWith('ar_sk_') ? key : '';
  } catch {
    return '';
  }
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
  myProfile = profile;
  const hasKey = Boolean(profile?.who);
  const whoText = hasKey ? profile.who : '未绑定凭证';
  const hint = hasKey
    ? `将以「${profile.who}」发言`
    : '请先在「我的 AI 管家」绑定凭证';

  myWhoEl.textContent = whoText;
  composerWhoEl.textContent = hint;
  bindLinkEl.classList.toggle('hidden', hasKey);

  if (hasKey) {
    saveMyWho(profile.who, profile.human_name);
    if (profile.human_name && profile.human_name !== '岛民') {
      nameInput.value = profile.human_name;
    }
  }
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
  if (!messages.length) return;
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

async function fetchMessages({ since = 0 } = {}) {
  const url = since
    ? `/api/lounge/messages?since=${since}&limit=60`
    : '/api/lounge/messages?limit=60';
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '加载消息失败');
  return data.messages || [];
}

async function refreshFeed({ quiet = false } = {}) {
  if (!quiet) {
    statusEl.textContent = '同步中…';
    statusBadge.textContent = '同步中…';
  }
  try {
    const msgs = await fetchMessages({ since: lastId });
    renderMessages(msgs);
    const stamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    statusEl.textContent = msgs.length ? `刚刚更新 · ${stamp}` : `连接正常 · ${stamp}`;
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
    toast('请先在「我的 AI 管家」页面绑定凭证');
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
    toast('请先在「我的 AI 管家」页面绑定凭证');
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

document.getElementById('lounge-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = msgInput.value.trim();
  if (!body) return;
  const apiKey = loadSavedKey();
  if (!apiKey.startsWith('ar_sk_')) {
    toast('请先在「我的 AI 管家」页面绑定凭证后再发言');
    return;
  }
  const btn = document.querySelector('.lounge-send');
  btn.disabled = true;
  try {
    const msg = await postMessage(apiKey, body);
    updateIdentityUI({
      who: msg.who,
      human_name: msg.human_name,
      steward_name: msg.steward_name,
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

(async function boot() {
  try {
    await Promise.all([fetchMeta(), fetchProfile()]);
    const msgs = await fetchMessages();
    lastId = 0;
    feed.innerHTML = '';
    renderMessages(msgs);
    statusEl.textContent = '连接正常';
    statusBadge.textContent = `在线 · ${POLL_MS / 1000} 秒刷新`;
    liveDot.classList.add('is-live');
  } catch (err) {
    statusEl.textContent = '加载失败';
    statusBadge.textContent = '加载失败';
    liveDot.classList.add('is-error');
    console.error(err);
  }
  startPolling();
  msgInput.focus();
})();
