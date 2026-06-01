/* ==========================================
 * AI数字名片 - Service Worker
 * Version: 1.0.0
 * Cache Strategy: Cache First → Network Update
 * ========================================== */

const CACHE_NAME = 'ai-business-card-v1';

// ── 预缓存清单 ──────────────────────────────
const PRECACHE_URLS = [
  '/',
  '/offline',
  '/static/manifest.json',
  '/static/pwa-icon.svg',
  'https://cdn.tailwindcss.com',
  'https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js',
  'https://cdn.jsdelivr.net/npm/stpageflip@1.0.4/dist/stpageflip.min.js'
];

// ── 安装事件：预缓存核心资源 ────────────────
self.addEventListener('install', (event) => {
  console.log('[SW] Install event fired');
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Precaching core resources');
      return cache.addAll(PRECACHE_URLS).catch((err) => {
        // CDN resources might fail; that's acceptable
        console.warn('[SW] Precaching partial failure:', err.message);
      });
    }).then(() => {
      // Force new SW to take over immediately
      return self.skipWaiting();
    })
  );
});

// ── 激活事件：清理旧缓存 ────────────────────
self.addEventListener('activate', (event) => {
  console.log('[SW] Activate event fired');
  const currentCaches = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return cacheNames.filter((name) => !currentCaches.includes(name));
    }).then((cachesToDelete) => {
      return Promise.all(
        cachesToDelete.map((name) => {
          console.log('[SW] Deleting old cache:', name);
          return caches.delete(name);
        })
      );
    }).then(() => {
      // Take control of all clients immediately
      return self.clients.claim();
    })
  );
});

// ── 请求拦截：Cache First 策略 ──────────────
self.addEventListener('fetch', (event) => {
  const request = event.request;

  // 仅缓存 GET 请求
  if (request.method !== 'GET') return;

  // 不缓存 chrome-extension 等非标准协议
  if (!request.url.startsWith('http')) return;

  // API 请求使用 Network First（不缓存动态数据到持久缓存，但支持离线fallback）
  if (request.url.includes('/api/v1/')) {
    event.respondWith(networkFirstWithFallback(request));
    return;
  }

  // Cache First 策略（静态资源 + HTML 页面）
  event.respondWith(cacheFirstWithNetworkUpdate(request));
});

/**
 * Cache First 策略
 * 1. 从缓存获取 → 命中则直接返回
 * 2. 未命中 → 从网络获取 → 更新缓存 → 返回
 * 3. 网络失败 → 返回离线fallback页面
 */
async function cacheFirstWithNetworkUpdate(request) {
  const cachedResponse = await caches.match(request);

  if (cachedResponse) {
    // 缓存命中：立即返回，同时静默更新缓存
    if (navigator.onLine !== false) {
      // We can only check navigator.onLine in SW context via self.registration
      // So always try to update in background
      fetchAndUpdateCache(request).catch(() => {});
    }
    return cachedResponse;
  }

  try {
    const networkResponse = await fetch(request);
    if (networkResponse && networkResponse.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone()).catch(() => {});
    }
    return networkResponse;
  } catch (error) {
    console.warn('[SW] Cache miss & network failed:', request.url);
    // If it's an HTML navigation request, show offline page
    if (request.mode === 'navigate') {
      const offlineResponse = await caches.match('/offline');
      if (offlineResponse) return offlineResponse;
      // Fallback: return a minimal HTML
      return new Response(
        `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>离线</title><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{background:#0f0c29;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:sans-serif;text-align:center;padding:20px}h1{font-size:24px;color:#f5576c}p{color:rgba(255,255,255,0.5);margin-top:8px}</style></head><body><div><h1>📡 无网络连接</h1><p>请检查网络后重试</p></div></body></html>`,
        { headers: { 'Content-Type': 'text/html; charset=UTF-8' } }
      );
    }
    // For non-navigation requests, return a simple error response
    return new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
  }
}

/**
 * Network First 策略（用于 API 请求）
 */
async function networkFirstWithFallback(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse && networkResponse.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone()).catch(() => {});
    }
    return networkResponse;
  } catch (error) {
    // Try to serve from cache as fallback
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    // Return a JSON error for API requests
    return new Response(
      JSON.stringify({ error: 'offline', message: '网络不可用，请检查连接' }),
      { headers: { 'Content-Type': 'application/json' }, status: 503 }
    );
  }
}

/**
 * 在后台静默获取并更新缓存
 */
async function fetchAndUpdateCache(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse && networkResponse.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
  } catch (e) {
    // Silently fail - cache is fine
  }
}
