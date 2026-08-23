/** 全站共用本机凭证。只在「我的 AI 管家」绑定 / 清除，其它页只读取。 */
const SITE_KEY_STORAGE = 'tidal_island_steward_api_key';

function siteKeyEsc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function loadSavedKey() {
  try {
    const key = localStorage.getItem(SITE_KEY_STORAGE);
    return key && key.startsWith('ar_sk_') ? key : '';
  } catch {
    return '';
  }
}

function saveSiteKey(key) {
  try {
    localStorage.setItem(SITE_KEY_STORAGE, key);
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
    + '<a href="/steward">去「我的 AI 管家」绑定</a>'
    + '。酒吧、小馆、星光共用这一份，刷新还在。</p>'
  );
  return false;
}
