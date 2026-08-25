/** 本机持久 device_id。只作风控信号，不是登录凭证。nav 已引入；页面再引一次会直接跳过。 */
(function () {
  if (window.getOrCreateDeviceId) return;

  const DEVICE_STORAGE = 'tidal_island_device_id';
  const DEVICE_COOKIE = 'tidal_did';
  const INVITE_STORAGE = 'tidal_island_invite_code';

  function _readCookie(name) {
    const parts = (`; ${document.cookie}`).split(`; ${name}=`);
    if (parts.length < 2) return '';
    return decodeURIComponent(parts.pop().split(';').shift() || '');
  }

  function getOrCreateDeviceId() {
    let id = '';
    try { id = localStorage.getItem(DEVICE_STORAGE) || ''; } catch { /* ignore */ }
    if (!id) id = _readCookie(DEVICE_COOKIE) || '';
    if (!id || !/^[0-9a-f-]{16,80}$/i.test(id)) {
      if (window.crypto && crypto.randomUUID) id = crypto.randomUUID();
      else {
        id = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
          const r = Math.random() * 16 | 0;
          return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
      }
    }
    try { localStorage.setItem(DEVICE_STORAGE, id); } catch { /* ignore */ }
    document.cookie = `${DEVICE_COOKIE}=${encodeURIComponent(id)};path=/;max-age=31536000;SameSite=Lax`;
    return id;
  }

  function peekInviteCode() {
    const q = new URLSearchParams(location.search);
    const fromUrl = (q.get('invite') || q.get('code') || '').trim();
    if (fromUrl) {
      try { sessionStorage.setItem(INVITE_STORAGE, fromUrl); } catch { /* ignore */ }
      return fromUrl;
    }
    try { return sessionStorage.getItem(INVITE_STORAGE) || ''; } catch { return ''; }
  }

  function clearStoredInvite() {
    try { sessionStorage.removeItem(INVITE_STORAGE); } catch { /* ignore */ }
  }

  window.getOrCreateDeviceId = getOrCreateDeviceId;
  window.peekInviteCode = peekInviteCode;
  window.clearStoredInvite = clearStoredInvite;
  getOrCreateDeviceId();
})();
