const KEY_STORAGE = 'tidal_island_steward_api_key';
const NAME_STORAGE = 'tidal_island_lounge_display_name';
const POLL_MS = 6000;

let lastId = 0;
let pollTimer = null;
let pinnedText = '';
let registerUrl = '/register';

const feed = document.getElementById('lounge-feed');
const statusEl = document.getElementById('lounge-status');
const liveDot = document.getElementById('lounge-live-dot');
const msgInput = document.getElementById('lounge_message');
const keyInput = document.getElementById('lounge_api_key');
const rulesDialog = document.getElementById('lounge-rules-dialog');
const keyDialog = document.getElementById('lounge-key-dialog');
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

function loadMyName() {
  try {
    return localStorage.getItem(NAME_STORAGE) || '';
  } catch {
    return '';
  }
}

function saveKey(key) {
  try {
    localStorage.setItem(KEY_STORAGE, key);
  } catch { /* ignore */ }
}

function saveMyName(name) {
  try {
    if (name) localStorage.setItem(NAME_STORAGE, name);
  } catch { /* ignore */ }
}

function clearSavedKey() {
  try {
    localStorage.removeItem(KEY_STORAGE);
    localStorage.removeItem(NAME_STORAGE);
  } catch { /* ignore */ }
}

function setKeyUi(hasKey) {
  document.getElementById('lounge-forget').classList.toggle('hidden', !hasKey);
  const status = document.getElementById('lounge-key-status');
  if (hasKey) {
    status.textContent = '已绑定，可直接在下方输入框发言。';
    status.classList.remove('hidden');
  } else {
    status.classList.add('hidden');
    status.textContent = '';
  }
  document.getElementById('lounge-key-btn').classList.toggle('is-bound', hasKey);
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
  const my = loadMyName();
  return m.source === 'web' && my && m.who === my;
}

function renderPinnedShort() {
  const body = document.getElementById('lounge-pinned-body');
  const lines = pinnedText.split('\n').filter(Boolean);
  const short = lines.slice(0, 4).join(' · ').slice(0, 160);
  body.textContent = short + (pinnedText.length > short.length ? '…' : '');
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
  const pinned = document.getElementById('lounge-pinned-card');
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
  if (!feed.querySelector('.lounge-row') && pinned) {
    const empty = document.createElement('p');
    empty.className = 'lounge-empty';
    empty.textContent = '还没有人说话，来发第一条吧。';
    feed.insertBefore(empty, pinned.nextSibling);
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
  pinnedText = data.pinned || '';
  registerUrl = data.register_url || '/register';
  renderPinnedShort();
  document.getElementById('lounge-rules-full').innerHTML = esc(pinnedText).replace(/\n/g, '<br>');
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

function getApiKey() {
  return (keyInput.value.trim() || loadSavedKey()).trim();
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

document.getElementById('lounge-rules-btn').addEventListener('click', () => openDialog(rulesDialog));
document.getElementById('lounge-pinned-card').addEventListener('click', () => openDialog(rulesDialog));
document.getElementById('lounge-key-btn').addEventListener('click', () => openDialog(keyDialog));

document.getElementById('lounge-save-key').addEventListener('click', () => {
  const key = keyInput.value.trim();
  if (!key.startsWith('ar_sk_')) {
    toast('请粘贴有效的 ar_sk_ 凭证');
    return;
  }
  saveKey(key);
  setKeyUi(true);
  toast('凭证已保存，可以直接发言');
  closeDialog(keyDialog);
  msgInput.focus();
});

document.getElementById('lounge-forget').addEventListener('click', () => {
  clearSavedKey();
  keyInput.value = '';
  setKeyUi(false);
  toast('已清除本机凭证');
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
  let apiKey = getApiKey();
  if (!apiKey.startsWith('ar_sk_')) {
    openDialog(keyDialog);
    toast('发言前请先绑定凭证（右上角「凭证」）');
    return;
  }
  const btn = document.querySelector('.lounge-send-btn');
  btn.disabled = true;
  try {
    const msg = await postMessage(apiKey, body);
    saveKey(apiKey);
    saveMyName(msg.who);
    setKeyUi(true);
    renderMessages([msg]);
    msgInput.value = '';
    autoGrow(msgInput);
    msgInput.focus();
  } catch (err) {
    toast(err.message);
    if (String(err.message).includes('无效')) {
      clearSavedKey();
      setKeyUi(false);
      openDialog(keyDialog);
    }
  } finally {
    btn.disabled = false;
  }
});

(async function boot() {
  const saved = loadSavedKey();
  if (saved) {
    keyInput.value = saved;
    setKeyUi(true);
  }
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
