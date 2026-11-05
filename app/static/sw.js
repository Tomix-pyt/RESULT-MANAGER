// Caches only the static shell. Pages are NEVER cached: they contain student results.
const CACHE = "rm-shell-v2";
const SHELL = ["/static/css/base.css", "/static/js/pwa.js", "/static/icons/icon-192.png", "/offline"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.pathname.startsWith("/static/")) {
    // Network first, cache as the offline fallback. (Cache-first made edited CSS/JS look "stuck".)
    e.respondWith(
      fetch(req)
        .then((res) => { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); return res; })
        .catch(() => caches.match(req))
    );
  } else if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("/offline")));
  }
});
