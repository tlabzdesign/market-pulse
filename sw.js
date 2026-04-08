const CACHE = "market-pulse-v1";
const URLS = ["/"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(URLS)));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", e => {
  if (e.request.url.includes("/api/")) {
    // Network first for API calls
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
  } else {
    // Cache first for static assets
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
  }
});
