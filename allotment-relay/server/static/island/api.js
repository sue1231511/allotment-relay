/** /api/v1 客户端。凭证只走请求头，不写进 URL。 */

const STORAGE = "tidal_island_steward_api_key";

export function loadKey() {
  try {
    if (typeof loadSavedKey === "function") {
      const fromSite = loadSavedKey();
      if (fromSite) return fromSite;
    }
    const key = localStorage.getItem(STORAGE);
    return key && key.startsWith("ar_sk_") ? key : "";
  } catch {
    return "";
  }
}

export function saveKey(key) {
  try {
    if (typeof saveSiteKey === "function") saveSiteKey(key);
    else localStorage.setItem(STORAGE, key);
  } catch {
    /* private mode */
  }
}

function newIdem() {
  if (crypto && crypto.randomUUID) return crypto.randomUUID();
  return `idem-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function req(path, { method = "GET", body, idem } = {}) {
  const key = loadKey();
  const headers = { Accept: "application/json" };
  if (key) headers.Authorization = `Bearer ${key}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["Idempotency-Key"] = idem || newIdem();
  const res = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    data = { ok: false, error: { code: "BAD_RESPONSE", message: "服务端没有返回可读结果。" } };
  }
  if (!res.ok || data.ok === false) {
    const err = data.error || {};
    const error = new Error(err.message || "这次没做成。");
    error.code = err.code || "ACTION_FAILED";
    error.status = res.status;
    error.payload = data;
    throw error;
  }
  return data;
}

export const api = {
  session: (apiKey, name = "") => req("/api/v1/session", { method: "POST", body: { api_key: apiKey, name } }),
  me: () => req("/api/v1/me"),
  world: () => req("/api/v1/world"),
  farm: () => req("/api/v1/farm"),
  sow: (slot, crop, idem) => req(`/api/v1/farm/parcels/${encodeURIComponent(slot)}/sow`, { method: "POST", body: { crop }, idem }),
  water: (slot, idem) => req(`/api/v1/farm/parcels/${encodeURIComponent(slot)}/water`, { method: "POST", body: {}, idem }),
  harvest: (slot, idem) => req(`/api/v1/farm/parcels/${encodeURIComponent(slot)}/harvest`, { method: "POST", body: {}, idem }),
  shore: (mode, idem) => req("/api/v1/shore/cast", { method: "POST", body: { mode }, idem }),
  messages: () => req("/api/v1/lounge/messages"),
  say: (text, idem) => req("/api/v1/lounge/messages", { method: "POST", body: { text }, idem }),
};
