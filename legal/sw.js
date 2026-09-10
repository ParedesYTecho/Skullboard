// SkullBoard Service Worker (PWA Offline & Asset Caching v2.5.0)
const CACHE_NAME = 'skb-cache-v2.5.0';
const STATIC_ASSETS = [
  '/',
  '/dashboard',
  '/cambios',
  '/privacy',
  '/terms',
  '/styles.css',
  '/skullboard_icon.png',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return key.startsWith('skb-') ? caches.delete(key) : undefined;
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.pathname === '/api' || url.pathname.startsWith('/api/') ||
      url.searchParams.has('code') || url.searchParams.has('state') || url.searchParams.has('error') ||
      url.pathname === '/callback') {
    return;
  }
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        const cacheControl = networkResponse?.headers.get('cache-control') || '';
        if (networkResponse && networkResponse.status === 200 && !/no-store/i.test(cacheControl)) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return networkResponse;
      })
      .catch(() => caches.match(event.request))
  );
});
