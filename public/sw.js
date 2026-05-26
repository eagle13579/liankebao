/* ============================================================
   链客宝 Service Worker
   ============================================================
   缓存策略:
     - 静态资源 (JS/CSS/字体/图片): Cache First
     - API 请求: Network First (fallback to cache)
     - 离线页面: Cache First (每次更新时预缓存)
   ============================================================ */

const CACHE_NAME = 'liankebao-v1';
const STATIC_CACHE = 'liankebao-static-v1';
const API_CACHE = 'liankebao-api-v1';

// 需要预缓存的离线兜底页面
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/offline.html',
];

// 静态资源扩展名（使用 Cache First 策略）
const STATIC_EXTENSIONS = [
  '.js', '.css', '.woff', '.woff2', '.ttf', '.eot',
  '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp',
  '.json', '.wasm',
];

// API 路径前缀（使用 Network First 策略）
const API_PREFIXES = [
  '/api/',
  '/lkapi/',
  '/banners',
  '/health',
  '/share',
];

/* ---- 判断请求类型 ---- */

function isStaticAsset(url) {
  const pathname = new URL(url).pathname;
  return STATIC_EXTENSIONS.some(ext => pathname.endsWith(ext))
    || pathname.startsWith('/assets/');
}

function isApiRequest(url) {
  const pathname = new URL(url).pathname;
  return API_PREFIXES.some(prefix => pathname.startsWith(prefix));
}

/* ---- 安装阶段：预缓存关键资源 ---- */

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(PRECACHE_URLS).catch(err => {
        console.warn('[SW] 预缓存部分资源失败（离线页面可能不可用）:', err);
      });
    }).then(() => {
      // 跳过等待，立即激活
      return self.skipWaiting();
    })
  );
});

/* ---- 激活阶段：清理旧缓存 ---- */

self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME, STATIC_CACHE, API_CACHE];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (!cacheWhitelist.includes(cacheName)) {
            console.log('[SW] 删除旧缓存:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      // 接管所有客户端（让当前打开的页面也受 SW 控制）
      return self.clients.claim();
    })
  );
});

/* ---- 请求拦截：根据策略路由 ---- */

self.addEventListener('fetch', event => {
  const { request } = event;

  // 忽略非 GET 请求
  if (request.method !== 'GET') return;

  // 忽略非 http(s) 请求（如 chrome-extension://）
  if (!request.url.startsWith('http')) return;

  // 策略 1: 静态资源 → Cache First
  if (isStaticAsset(request.url)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // 策略 2: API 请求 → Network First
  if (isApiRequest(request.url)) {
    event.respondWith(networkFirst(request));
    return;
  }

  // 策略 3: 导航请求（HTML 页面）→ Network First, fallback to offline page
  if (request.mode === 'navigate') {
    event.respondWith(
      networkFirst(request).catch(() => {
        return caches.match('/offline.html').then(cached => {
          return cached || caches.match('/index.html');
        });
      })
    );
    return;
  }

  // 默认策略：Network First
  event.respondWith(networkFirst(request));
});

/* ---- Cache First: 优先从缓存读取，失败时回退到网络 ---- */

async function cacheFirst(request) {
  const cachedResponse = await caches.match(request);
  if (cachedResponse) {
    return cachedResponse;
  }
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (err) {
    // 网络失败时返回缓存中的离线页面
    const fallback = await caches.match('/offline.html');
    if (fallback) return fallback;
    throw err;
  }
}

/* ---- Network First: 优先从网络获取，失败时读取缓存 ---- */

async function networkFirst(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (err) {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    // 对于导航请求，返回离线页面
    if (request.mode === 'navigate') {
      const fallback = await caches.match('/offline.html');
      if (fallback) return fallback;
    }
    throw err;
  }
}
