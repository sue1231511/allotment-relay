const CACHE = "tidal-manual-v1";
const PRECACHE = [
  "/offline",
  "/manual",
  "/static/style.css?v=wedding-fold2",
  "/static/island-manual.css?v=pwa1",
  "/static/pwa.js?v=pwa1",
  "/manifest.webmanifest",
  "/static/pwa/icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const path = url.pathname;
  if (path.startsWith("/api/") || path.startsWith("/mcp")) return;

  const isManual = path === "/manual" || path === "/offline"
    || path.startsWith("/static/")
    || path === "/manifest.webmanifest";
  event.respondWith(isManual ? cacheFirst(req) : networkFirst(req));
});

async function networkFirst(req) {
  try {
    return await fetch(req);
  } catch (err) {
    const cached = await caches.match(req);
    if (cached) return cached;
    if (req.mode === "navigate") {
      const offline = await caches.match("/offline");
      if (offline) return offline;
    }
    throw err;
  }
}

async function cacheFirst(req) {
  const cached = await caches.match(req);
  if (cached) return cached;
  try {
    const fresh = await fetch(req);
    const cache = await caches.open(CACHE);
    cache.put(req, fresh.clone());
    return fresh;
  } catch (err) {
    if (req.mode === "navigate") {
      const offline = await caches.match("/offline");
      if (offline) return offline;
    }
    throw err;
  }
}
