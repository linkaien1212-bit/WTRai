/* AI HOT 日报 — Service Worker
 * 策略：
 *   - install: 预缓存入口页与图标（"添加到主屏幕"后断网也能打开）
 *   - fetch:
 *     1) 已在预缓存里的资源 → 直接返回（cache-first，离线可用）
 *     2) 其他 GET 请求 → stale-while-fallback：先回缓存，再异步拉新；失败回缓存
 */
const CACHE_VERSION = 'aihot-v1';
const CORE_ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-512-maskable.png',
  './icons/apple-touch-icon.png',
  './icons/favicon.ico'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then((cache) => cache.addAll(CORE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  // 1) 预缓存命中
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;

      // 2) 网络优先 + 失败回缓存
      return fetch(req).then((resp) => {
        // 只缓存同源 GET 且 200 的响应
        if (resp && resp.status === 200 && resp.type === 'basic') {
          const copy = resp.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(req, copy));
        }
        return resp;
      }).catch(() => {
        // 网络失败：回退到入口页（用户从主屏幕打开时离线也能看到内容）
        if (req.mode === 'navigate') {
          return caches.match('./index.html');
        }
        return new Response('', { status: 504, statusText: 'offline' });
      });
    })
  );
});
