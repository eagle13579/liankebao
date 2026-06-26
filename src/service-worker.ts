/**
 * 链客宝 — Service Worker (TypeScript)
 * =============================================================================
 * 缓存策略:
 *   - Cache First: 静态资源 (JS, CSS, Fonts, Images)
 *   - Network First: API 请求 (/api/*, /health)
 *   - Stale-While-Revalidate: i18n 翻译资源
 *   - Network First w/ Offline Fallback: 导航请求
 * =============================================================================
 *
 * 此文件为 TypeScript 源码, 通过构建工具编译输出到 public/sw.js。
 * 开发环境中直接引用 public/sw.js 亦可。
 *
 * 编译方式:
 *   npx tsc src/service-worker.ts --outDir public --lib es6,dom --target es2020 --module es2020 --moduleResolution node --skipLibCheck
 */

/// <reference lib="webworker" />

declare const self: ServiceWorkerGlobalScope;

// ===== 缓存名称 =====
const CACHE_NAMES = {
  STATIC: 'chainke-static-v1',
  DYNAMIC: 'chainke-dynamic-v1',
  TRANSLATION: 'chainke-translations-v1',
} as const;

// ===== 预缓存资源列表 =====
const PRECACHE_URLS: string[] = [
  '/',
  '/offline.html',
  '/manifest.json',
];

// ===== 静态资源扩展名 =====
const STATIC_EXTENSIONS = new Set([
  'js', 'css', 'woff', 'woff2', 'ttf', 'eot',
  'svg', 'ico', 'png', 'jpg', 'jpeg', 'gif', 'webp',
]);

// ===== 动态缓存过期时间 (5 分钟) =====
const DYNAMIC_CACHE_MAX_AGE_MS = 5 * 60 * 1000;

// ===== 请求分类器 =====
function isApiRequest(url: URL): boolean {
  return url.pathname.startsWith('/api/') || url.pathname.startsWith('/health');
}

function isTranslationRequest(url: URL): boolean {
  return (
    url.pathname.includes('/i18n/') ||
    (url.pathname.endsWith('.json') && url.pathname.includes('translations'))
  );
}

function isStaticAsset(url: URL): boolean {
  const ext = url.pathname.split('.').pop()?.toLowerCase() ?? '';
  return STATIC_EXTENSIONS.has(ext);
}

function isCacheExpired(response: Response): boolean {
  const dateHeader = response.headers.get('date');
  if (!dateHeader) return false;
  const cachedTime = new Date(dateHeader).getTime();
  return Date.now() - cachedTime > DYNAMIC_CACHE_MAX_AGE_MS;
}

// ===== 安装阶段：预缓存 =====
self.addEventListener('install', (event: ExtendableEvent) => {
  console.log('[SW] 安装中...');
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_NAMES.STATIC);
      await cache.addAll(PRECACHE_URLS);
      console.log('[SW] 预缓存完成');
      await self.skipWaiting();
    })()
  );
});

// ===== 激活阶段：清理旧缓存 =====
self.addEventListener('activate', (event: ExtendableEvent) => {
  console.log('[SW] 激活中...');
  const allowedCaches = new Set(Object.values(CACHE_NAMES));
  event.waitUntil(
    (async () => {
      const cacheNames = await caches.keys();
      await Promise.all(
        cacheNames
          .filter((name) => !allowedCaches.has(name))
          .map((name) => {
            console.log('[SW] 删除旧缓存:', name);
            return caches.delete(name);
          })
      );
      console.log('[SW] 激活完成，接管所有客户端');
      await self.clients.claim();
    })()
  );
});

// ===== 消息处理 (SKIP_WAITING) =====
self.addEventListener('message', (event: ExtendableMessageEvent) => {
  if (event.data?.type === 'SKIP_WAITING') {
    console.log('[SW] 收到 SKIP_WAITING 消息，跳过等待');
    self.skipWaiting();
  }
});

// ===== 缓存策略实现 =====

/**
 * Cache-First 策略
 * 优先返回缓存内容，缓存未命中时回退到网络并更新缓存。
 */
async function cacheFirstStrategy(request: Request): Promise<Response> {
  const cachedResponse = await caches.match(request);
  if (cachedResponse) {
    return cachedResponse;
  }
  try {
    const networkResponse = await fetch(request);
    if (networkResponse && networkResponse.ok) {
      const cache = await caches.open(CACHE_NAMES.STATIC);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    return new Response('离线模式', { status: 503, statusText: 'Service Unavailable' });
  }
}

/**
 * Network-First 策略
 * 优先从网络获取，网络失败时回退到缓存。
 */
async function networkFirstStrategy(request: Request): Promise<Response> {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse && networkResponse.ok) {
      const cache = await caches.open(CACHE_NAMES.DYNAMIC);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    // API 请求离线时返回 JSON 错误
    if (request.headers.get('Accept')?.includes('application/json')) {
      return new Response(
        JSON.stringify({ error: '您处于离线状态，部分功能不可用', offline: true }),
        {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        }
      );
    }
    return new Response('您处于离线状态，部分功能不可用', {
      status: 503,
      statusText: 'Service Unavailable',
    });
  }
}

/**
 * Stale-While-Revalidate 策略
 * 立即返回缓存内容，同时异步更新缓存。
 */
async function staleWhileRevalidateStrategy(request: Request): Promise<Response> {
  const cache = await caches.open(CACHE_NAMES.TRANSLATION);
  const cachedResponse = await cache.match(request);

  const networkPromise = fetch(request)
    .then((networkResponse) => {
      if (networkResponse && networkResponse.ok) {
        cache.put(request, networkResponse.clone());
      }
      return networkResponse;
    })
    .catch(() => cachedResponse);

  return cachedResponse || networkPromise;
}

/**
 * Network-First 带离线降级 (导航请求)
 */
async function networkFirstWithOfflineFallback(request: Request): Promise<Response> {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse && networkResponse.ok) {
      const cache = await caches.open(CACHE_NAMES.DYNAMIC);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    const offlineResponse = await caches.match('/offline.html');
    if (offlineResponse) {
      return offlineResponse;
    }
    return new Response('您处于离线状态，部分功能不可用', {
      status: 503,
      statusText: 'Service Unavailable',
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  }
}

// ===== Fetch 事件：路由请求到对应策略 =====
self.addEventListener('fetch', (event: FetchEvent) => {
  const url = new URL(event.request.url);

  // 只处理同域请求
  if (url.origin !== self.location.origin) return;
  // 跳过非 HTTP(S) 请求
  if (!event.request.url.startsWith('http')) return;

  // ---- Network-First: API 请求 ----
  if (isApiRequest(url)) {
    event.respondWith(networkFirstStrategy(event.request));
    return;
  }

  // ---- Stale-While-Revalidate: 翻译资源 ----
  if (isTranslationRequest(url)) {
    event.respondWith(staleWhileRevalidateStrategy(event.request));
    return;
  }

  // ---- Cache-First: 静态资源 ----
  if (isStaticAsset(url)) {
    event.respondWith(cacheFirstStrategy(event.request));
    return;
  }

  // ---- Navigation: 导航请求 (离线降级) ----
  if (event.request.mode === 'navigate') {
    event.respondWith(networkFirstWithOfflineFallback(event.request));
    return;
  }

  // 其他请求: Network-First
  event.respondWith(networkFirstStrategy(event.request));
});

// ===== 推送通知 =====
self.addEventListener('push', (event: PushEvent) => {
  let data: Record<string, string> = {
    title: '链客宝',
    body: '您有新消息',
    icon: '/icons/icon-192x192.png',
  };

  if (event.data) {
    try {
      const parsed = event.data.json();
      data = { ...data, ...parsed };
    } catch {
      data.body = event.data.text();
    }
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: data.icon,
      badge: '/icons/icon-192x192.png',
      vibrate: [200, 100, 200],
      tag: 'chainke-notification',
      renotify: true,
      requireInteraction: true,
    })
  );
});

// ===== 通知点击 =====
self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close();

  event.waitUntil(
    clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        if (clientList.length > 0) {
          return clientList[0].focus();
        }
        return clients.openWindow('/');
      })
  );
});

export {}; // 确保此文件为模块
