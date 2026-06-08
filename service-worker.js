/* Offline support for the UKBOL Species Lookup.
   - App shell (HTML/JS/icons/Bootstrap CSS): cache-first.
   - Dataset (data.json / data.meta.json): stale-while-revalidate, with a
     notification to clients when the data version changes. */

const CACHE_VERSION = "v1";
const SHELL_CACHE = "shell-" + CACHE_VERSION;
const DATA_CACHE = "data-" + CACHE_VERSION;

// Same-origin shell assets (relative so this works at any deploy path).
const SHELL_ASSETS = [
  "./",
  "./index.html",
  "./worker.js",
  "./manifest.json",
  "./assets/icons/icon-192.png",
  "./assets/icons/icon-512.png",
];

const DATA_PATHS = ["data.json", "data.meta.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((c) => c.addAll(SHELL_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== SHELL_CACHE && k !== DATA_CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

function isData(url) {
  return DATA_PATHS.some((p) => url.pathname.endsWith("/" + p) || url.pathname.endsWith(p));
}

async function notifyDataUpdated(version) {
  const clients = await self.clients.matchAll({ includeUncontrolled: true });
  for (const c of clients) c.postMessage({ type: "data-updated", version });
}

// Stale-while-revalidate for the dataset; detect version changes via data.meta.json.
async function dataStrategy(request) {
  const cache = await caches.open(DATA_CACHE);
  const cached = await cache.match(request);

  const network = fetch(request).then(async (resp) => {
    if (resp && resp.ok) {
      if (request.url.endsWith("data.meta.json")) {
        try {
          const oldMeta = cached ? await cached.clone().json() : null;
          const newMeta = await resp.clone().json();
          if (oldMeta && newMeta.version && oldMeta.version !== newMeta.version) {
            notifyDataUpdated(newMeta.version);
          }
        } catch (_) { /* ignore */ }
      }
      cache.put(request, resp.clone());
    }
    return resp;
  }).catch(() => cached);

  return cached || network;
}

async function shellStrategy(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const resp = await fetch(request);
    // Runtime-cache successful GETs (e.g. the Bootstrap CSS from the CDN) for offline.
    if (resp && (resp.ok || resp.type === "opaque") && request.method === "GET") {
      const cache = await caches.open(SHELL_CACHE);
      cache.put(request, resp.clone());
    }
    return resp;
  } catch (err) {
    if (request.mode === "navigate") return caches.match("./index.html");
    throw err;
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin === self.location.origin && isData(url)) {
    event.respondWith(dataStrategy(request));
  } else {
    event.respondWith(shellStrategy(request));
  }
});
