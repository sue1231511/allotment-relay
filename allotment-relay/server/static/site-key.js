/** 全站共用本机凭证。上手页绑定 / 清除。点单打赏只在 /play。 */
const SITE_KEY_STORAGE = 'tidal_island_steward_api_key';

function siteKeyEsc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function normalizeSiteKey(raw) {
  const text = String(raw || '').trim();
  if (!text) return '';
  if (text.indexOf('ar_sk_') === 0 && text.indexOf('://') < 0 && text.indexOf('=') < 0) {
    return text.split(/\s/)[0];
  }
  const m = text.match(/ar_sk_[A-Za-z0-9_-]+/);
  return m ? m[0] : '';
}

function loadSavedKey() {
  try {
    return normalizeSiteKey(localStorage.getItem(SITE_KEY_STORAGE) || '');
  } catch {
    return '';
  }
}

function saveSiteKey(key) {
  const clean = normalizeSiteKey(key);
  if (!clean) return;
  try {
    localStorage.setItem(SITE_KEY_STORAGE, clean);
  } catch {
    /* private mode / quota */
  }
}

function clearSiteKey() {
  try {
    localStorage.removeItem(SITE_KEY_STORAGE);
  } catch {
    /* ignore */
  }
}

async function fetchBoundSteward() {
  const apiKey = loadSavedKey();
  if (!apiKey) return null;
  try {
    const res = await fetch('/api/lounge/me', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    });
    const data = await res.json();
    if (!res.ok) return null;
    return {
      apiKey,
      name: data.steward_name || '',
      who: data.who || data.steward_name || '',
    };
  } catch {
    return null;
  }
}

function renderPatronBind(el, bound, verb) {
  if (!el) return Boolean(bound && bound.name);
  const action = verb || '下单';
  if (bound && bound.name) {
    el.classList.remove('is-unbound');
    el.innerHTML = `<p class="patron-who">本机管家「${siteKeyEsc(bound.name)}」${action}，扣 TA 的票。</p>`;
    return true;
  }
  el.classList.add('is-unbound');
  el.innerHTML = (
    '<p class="patron-who">还没绑定凭证。'
    + '<a href="/play">去上手页贴凭证</a>'
    + '。点单、打赏只在上手页。</p>'
  );
  return false;
}
