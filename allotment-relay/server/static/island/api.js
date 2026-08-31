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
  const ctrl = typeof AbortController === "function" ? new AbortController() : null;
  const timer = ctrl ? setTimeout(() => ctrl.abort(), 12000) : 0;
  let res;
  try {
    res = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctrl ? ctrl.signal : undefined,
    });
  } catch (err) {
    if (timer) clearTimeout(timer);
    const error = new Error(err && err.name === "AbortError" ? "等太久了。再点一次进入地图。" : "没能连上岛。再点一次进入地图。");
    error.code = err && err.name === "AbortError" ? "TIMEOUT" : "NETWORK";
    throw error;
  }
  if (timer) clearTimeout(timer);
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
  tend: (slot, idem) => req(`/api/v1/farm/parcels/${encodeURIComponent(slot)}/tend`, { method: "POST", body: {}, idem }),
  fertilize: (slot, idem) => req(`/api/v1/farm/parcels/${encodeURIComponent(slot)}/fertilize`, { method: "POST", body: {}, idem }),
  harvest: (slot, idem) => req(`/api/v1/farm/parcels/${encodeURIComponent(slot)}/harvest`, { method: "POST", body: {}, idem }),
  compost: (slot, idem) => req(`/api/v1/farm/parcels/${encodeURIComponent(slot)}/compost`, { method: "POST", body: {}, idem }),
  shake: (slot, idem) => req(`/api/v1/farm/parcels/${encodeURIComponent(slot)}/shake`, { method: "POST", body: {}, idem }),
  expand: (kind = "home", idem) => req("/api/v1/farm/expand", { method: "POST", body: { kind }, idem }),
  buy: (crop, qty = 1, idem) => req("/api/v1/farm/buy", { method: "POST", body: { crop, qty }, idem }),
  sleep: (idem) => req("/api/v1/hut/sleep", { method: "POST", body: {}, idem }),
  buildHut: (idem) => req("/api/v1/hut/build", { method: "POST", body: {}, idem }),
  work: (idem) => req("/api/v1/bar/work", { method: "POST", body: {}, idem }),
  eat: (item, idem) => req("/api/v1/kitchen/eat", { method: "POST", body: { item }, idem }),
  vend: (item, qty = 1, idem) => req("/api/v1/tote/vend", { method: "POST", body: { item, qty }, idem }),
  pay: (kind, idem) => req("/api/v1/hui/pay", { method: "POST", body: { kind }, idem }),
  shore: () => req("/api/v1/shore"),
  shoreAct: (kind, target = "", idem) => req("/api/v1/shore/act", { method: "POST", body: { kind, target }, idem }),
  shoreCast: (mode, idem) => req("/api/v1/shore/cast", { method: "POST", body: { mode }, idem }),
  messages: () => req("/api/v1/lounge/messages"),
  say: (text, idem) => req("/api/v1/lounge/messages", { method: "POST", body: { text }, idem }),
  shop: () => req("/api/v1/shop"),
  shopBuy: (item, qty = 1, idem) => req("/api/v1/shop/buy", { method: "POST", body: { item, qty }, idem }),
  workshop: () => req("/api/v1/workshop"),
  workshopAct: (kind, target = "", idem) => req("/api/v1/workshop/act", { method: "POST", body: { kind, target }, idem }),
  quarry: () => req("/api/v1/quarry"),
  quarryAct: (kind, target = "", idem) => req("/api/v1/quarry/act", { method: "POST", body: { kind, target }, idem }),
  bar: () => req("/api/v1/bar"),
  barAct: (kind, target = "", idem) => req("/api/v1/bar/act", { method: "POST", body: { kind, target }, idem }),
  writers: () => req("/api/v1/writers"),
  writersAct: (kind, target = "", idem) => req("/api/v1/writers/act", { method: "POST", body: { kind, target }, idem }),
  atelier: () => req("/api/v1/atelier"),
  atelierAct: (kind, target = "", idem) => req("/api/v1/atelier/act", { method: "POST", body: { kind, target }, idem }),
  hall: () => req("/api/v1/hall"),
  hallAct: (kind, target = "", idem) => req("/api/v1/hall/act", { method: "POST", body: { kind, target }, idem }),
  eatery: () => req("/api/v1/eatery"),
  eateryAct: (kind, target = "", idem) => req("/api/v1/eatery/act", { method: "POST", body: { kind, target }, idem }),
  market: () => req("/api/v1/market"),
  marketAct: (kind, target = "", idem) => req("/api/v1/market/act", { method: "POST", body: { kind, target }, idem }),
  ting: () => req("/api/v1/ting"),
  tingAct: (kind, target = "", idem) => req("/api/v1/ting/act", { method: "POST", body: { kind, target }, idem }),
  hui: () => req("/api/v1/hui"),
  huiAct: (kind, target = "", idem) => req("/api/v1/hui/act", { method: "POST", body: { kind, target }, idem }),
  lianli: () => req("/api/v1/lianli"),
  lianliAct: (kind, target = "", idem) => req("/api/v1/lianli/act", { method: "POST", body: { kind, target }, idem }),
  lighthouse: () => req("/api/v1/lighthouse"),
  lighthouseAct: (kind, target = "", idem) => req("/api/v1/lighthouse/act", { method: "POST", body: { kind, target }, idem }),
  lili: () => req("/api/v1/lili"),
  liliAct: (kind, target = "", idem) => req("/api/v1/lili/act", { method: "POST", body: { kind, target }, idem }),
  clinic: () => req("/api/v1/clinic"),
  clinicAct: (kind, target = "", idem) => req("/api/v1/clinic/act", { method: "POST", body: { kind, target }, idem }),
};
