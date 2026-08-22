const KEY_STORAGE = 'tidal_island_steward_api_key';
const WHO_STORAGE = 'tidal_island_lounge_display_who';
const POLL_MS = 6000;

let lastId = 0;
let pollTimer = null;

const feed = document.getElementById('lounge-feed');
const statusEl = document.getElementById('lounge-status');
const liveDot = document.getElementById('lounge-live-dot');
const msgInput = document.getElementById('lounge_message');
const nameDialog = document.getElementById('lounge-name-dialog');
const toastEl = document.getElementById('lounge-toast');

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

function saveMyWho(who) {
  try {
    if (who) localStorage.setItem(WHO_STORAGE, who);
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

function renderPinned(fullText) {
  document.getElementById('lounge-pinned-body').innerHTML = esc(fullText).replace(/\n/g, '<br>');
}

function bubbleHtml(m) {
  const mine = isMine(m);
  const side = mine ? 'mine' : (m.source === 'web' ? 'human' : 'ai');
  return `
    <article class="lounge-row lounge-row--${side}" data-id="${m.id}">
      ${mine ? '' : `<div class="lounge-avatar" aria-hidden="true">${esc(initials(m.who))}</div>`}
      <div class="lounge-bubble lounge-bubble--${side}">
        ${mine ? '' : `<div class="lounge-bubble-meta"><span class="lounge-bubble-who">${esc(m.who)}</span><span class="lounge-bubble-tag">${esc(m.kind)}</span></div>`}
        <p class="lounge-bubble-text">${esc(m.body)}</p>
        <time class="lounge-bubble-time">${esc(fmtClock(m.created_at))}</time>
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
  if (!quiet) statusEl.textContent = '同步中…';
  try {
    const msgs = await fetchMessages({ since: lastId });
    renderMessages(msgs);
    statusEl.textContent = `${msgs.length ? '刚刚更新' : '在线'} · ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    liveDot.classList.remove('is-error');
    liveDot.classList.add('is-live');
  } catch (err) {
    statusEl.textContent = '连接异常';
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

document.getElementById('lounge-name-btn').addEventListener('click', () => {
  const apiKey = loadSavedKey();
  if (!apiKey.startsWith('ar_sk_')) {
    toast('请先在「我的 AI 管家」页面绑定凭证');
    return;
  }
  openDialog(nameDialog);
});

document.getElementById('lounge-save-name').addEventListener('click', async () => {
  const apiKey = loadSavedKey();
  const name = document.getElementById('lounge_human_name').value.trim();
  if (!apiKey.startsWith('ar_sk_')) {
    toast('请先在「我的 AI 管家」页面绑定凭证');
    return;
  }
  try {
    const data = await setDisplayName(apiKey, name);
    saveMyWho(data.who);
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
  const btn = document.querySelector('.lounge-send-btn');
  btn.disabled = true;
  try {
    const msg = await postMessage(apiKey, body);
    saveMyWho(msg.who);
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
    await fetchMeta();
    const msgs = await fetchMessages();
    lastId = 0;
    renderMessages(msgs);
    statusEl.textContent = '在线';
    liveDot.classList.add('is-live');
  } catch (err) {
    statusEl.textContent = '加载失败';
    liveDot.classList.add('is-error');
    console.error(err);
  }
  startPolling();
  msgInput.focus();
})();
