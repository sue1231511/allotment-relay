const KEY_STORAGE = 'tidal_island_steward_api_key';
const POLL_MS = 8000;

let lastId = 0;
let pollTimer = null;

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function fmtTime(epoch) {
  if (!epoch) return '—';
  return new Date(epoch * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
}

function loadSavedKey() {
  try {
    const key = localStorage.getItem(KEY_STORAGE);
    return key && key.startsWith('ar_sk_') ? key : '';
  } catch {
    return '';
  }
}

function saveKey(key) {
  try {
    localStorage.setItem(KEY_STORAGE, key);
  } catch { /* ignore */ }
}

function clearSavedKey() {
  try {
    localStorage.removeItem(KEY_STORAGE);
  } catch { /* ignore */ }
}

function setSavedUi(hasKey) {
  document.getElementById('lounge-forget').classList.toggle('hidden', !hasKey);
  document.getElementById('lounge-saved-hint').classList.toggle('hidden', !hasKey);
}

function renderPinned(meta) {
  const body = document.getElementById('lounge-pinned-body');
  body.innerHTML = esc(meta.pinned).replace(/\n/g, '<br>');
}

function renderMessages(messages, { prepend = false } = {}) {
  const feed = document.getElementById('lounge-feed');
  if (!messages.length) {
    if (!feed.children.length) {
      feed.innerHTML = '<p class="lounge-empty">还没有人说话。来发第一条吧。</p>';
    }
    return;
  }
  const empty = feed.querySelector('.lounge-empty');
  if (empty) empty.remove();

  const frag = document.createDocumentFragment();
  for (const m of messages) {
    if (m.id <= lastId && !prepend) continue;
    lastId = Math.max(lastId, m.id);
    const el = document.createElement('article');
    el.className = `lounge-msg lounge-msg--${m.source === 'web' ? 'human' : 'ai'}`;
    el.dataset.id = String(m.id);
    el.innerHTML = `
      <div class="lounge-msg-meta">
        <span class="lounge-msg-who">${esc(m.who)}</span>
        <span class="lounge-msg-kind">${esc(m.kind)}</span>
        <time class="lounge-msg-time">${esc(fmtTime(m.created_at))}</time>
      </div>
      <p class="lounge-msg-body">${esc(m.body)}</p>
    `;
    frag.appendChild(el);
  }
  feed.appendChild(frag);
  feed.scrollTop = feed.scrollHeight;
}

async function fetchMeta() {
  const res = await fetch('/api/lounge/meta');
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '加载失败');
  renderPinned(data);
  return data;
}

async function fetchMessages({ since = 0 } = {}) {
  const url = since
    ? `/api/lounge/messages?since=${since}&limit=50`
    : '/api/lounge/messages?limit=50';
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '加载消息失败');
  return data.messages || [];
}

async function refreshFeed({ quiet = false } = {}) {
  const status = document.getElementById('lounge-status');
  if (!quiet) status.textContent = '刷新中…';
  try {
    const msgs = await fetchMessages({ since: lastId });
    renderMessages(msgs);
    status.textContent = `在线 · ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    status.textContent = '连接异常';
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

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => refreshFeed({ quiet: true }), POLL_MS);
}

document.getElementById('lounge-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errBox = document.getElementById('lounge-error');
  const btn = document.querySelector('.lounge-send');
  const keyInput = document.getElementById('lounge_api_key');
  const msgInput = document.getElementById('lounge_message');
  errBox.classList.add('hidden');
  const apiKey = keyInput.value.trim();
  const body = msgInput.value.trim();
  if (!apiKey.startsWith('ar_sk_')) {
    errBox.textContent = '请填写有效的 ar_sk_ 凭证';
    errBox.classList.remove('hidden');
    return;
  }
  if (!body) return;
  btn.disabled = true;
  btn.textContent = '发送中…';
  try {
    const msg = await postMessage(apiKey, body);
    saveKey(apiKey);
    setSavedUi(true);
    renderMessages([msg]);
    msgInput.value = '';
    msgInput.focus();
  } catch (err) {
    errBox.textContent = err.message;
    errBox.classList.remove('hidden');
    if (String(err.message).includes('无效')) {
      clearSavedKey();
      setSavedUi(false);
    }
  } finally {
    btn.disabled = false;
    btn.textContent = '发送';
  }
});

document.getElementById('lounge-forget').addEventListener('click', () => {
  clearSavedKey();
  document.getElementById('lounge_api_key').value = '';
  setSavedUi(false);
});

(async function boot() {
  const saved = loadSavedKey();
  if (saved) {
    document.getElementById('lounge_api_key').value = saved;
    setSavedUi(true);
  }
  try {
    await fetchMeta();
    const msgs = await fetchMessages();
    renderMessages(msgs);
    document.getElementById('lounge-status').textContent = '已连接';
  } catch (err) {
    document.getElementById('lounge-status').textContent = '加载失败';
    console.error(err);
  }
  startPolling();
})();
