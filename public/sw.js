/* =============================================================================
 * 链客宝 — Service Worker
 * 缓存策略: Cache-First (静态资源) / Network-First (API) / Stale-While-Revalidate (翻译)
 * ============================================================================= */

const CACHE_NAME = 'chainke-cache-v1';
const STATIC_CACHE = 'chainke-static-v1';
const DYNAMIC_CACHE = 'chainke-dynamic-v1';
const TRANSLATION_CACHE = 'chainke-translations-v1';

// ---- 预缓存资源列表 ----
const PRECACHE_URLS = [
  '/',
  '/offline.html',
  '/manifest.json',
  // JS/CSS 资源将在 install 事件中动态添加
];

// ---- 安装阶段：预缓存所有静态资源 ----
self.addEventListener('install', (event) => {
  console.log('[SW] 安装中...');
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(PRECACHE_URLS).then(() => {
        console.log('[SW] 预缓存完成');
        return self.skipWaiting();
      });
    })
  );
});

// ---- 激活阶段：清理旧缓存 ----
self.addEventListener('activate', (event) => {
  console.log('[SW] 激活中...');
  const cacheWhitelist = [CACHE_NAME, STATIC_CACHE, DYNAMIC_CACHE, TRANSLATION_CACHE];
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => !cacheWhitelist.includes(name))
          .map((name) => {
            console.log('[SW] 删除旧缓存:', name);
            return caches.delete(name);
          })
      );
    }).then(() => {
      console.log('[SW] 激活完成，接管所有客户端');
      return self.clients.claim();
    })
  );
});

// ---- 判断请求类型 ----
function isApiRequest(url) {
  return url.pathname.startsWith('/api/') || url.pathname.startsWith('/health');
}

function isTranslationRequest(url) {
  return url.pathname.includes('/i18n/') || 
         url.pathname.endsWith('.json') && url.pathname.includes('translations');
}

function isStaticAsset(url) {
  const ext = url.pathname.split('.').pop();
  return ['js', 'css', 'woff', 'woff2', 'ttf', 'eot', 'svg', 'ico', 'png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext);
}

// ---- 动态缓存过期管理（5分钟） ----
const DYNAMIC_CACHE_MAX_AGE = 5 * 60 * 1000; // 5分钟

function isCacheExpired(cachedResponse) {
  if (!cachedResponse) return true;
  const dateHeader = cachedResponse.headers.get('date');
  if (!dateHeader) return false;
  const cachedTime = new Date(dateHeader).getTime();
  return (Date.now() - cachedTime) > DYNAMIC_CACHE_MAX_AGE;
}

// ---- 获取请求 ----
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // 跳过非 HTTP 请求
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

  // ---- Navigation: 导航请求（离线降级） ----
  if (event.request.mode === 'navigate') {
    event.respondWith(networkFirstWithOfflineFallback(event.request));
    return;
  }

  // 其他请求：Network-First
  event.respondWith(networkFirstStrategy(event.request));
});

// ---- Cache-First 策略 ----
async function cacheFirstStrategy(request) {
  const cachedResponse = await caches.match(request);
  if (cachedResponse) {
    return cachedResponse;
  }
  try {
    const networkResponse = await fetch(request);
    if (networkResponse && networkResponse.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    return new Response('离线模式', { status: 503, statusText: 'Service Unavailable' });
  }
}

// ---- Network-First 策略 ----
async function networkFirstStrategy(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse && networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
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
        { status: 503, headers: { 'Content-Type': 'application/json' } }
      );
    }
    return new Response('您处于离线状态，部分功能不可用', {
      status: 503,
      statusText: 'Service Unavailable',
    });
  }
}

// ---- Stale-While-Revalidate 策略 (翻译) ----
async function staleWhileRevalidateStrategy(request) {
  const cache = await caches.open(TRANSLATION_CACHE);
  const cachedResponse = await cache.match(request);

  // 返回缓存的响应（如果存在）
  const responsePromise = fetch(request).then((networkResponse) => {
    if (networkResponse && networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  }).catch(() => {
    return cachedResponse;
  });

  return cachedResponse || responsePromise;
}

// ---- Navigation 请求：Network-First 带离线降级 ----
async function networkFirstWithOfflineFallback(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse && networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    // 尝试返回离线页面
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

// ---- 推送通知事件 ----
self.addEventListener('push', (event) => {
  console.log('[SW] 收到推送通知:', event);

  let data = { title: '链客宝', body: '您有新消息', icon: '/icons/icon-192x192.png' };

  if (event.data) {
    try {
      const parsed = event.data.json();
      data = { ...data, ...parsed };
    } catch (e) {
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

// ---- 通知点击事件 ----
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] 通知点击:', event.notification.tag);
  event.notification.close();

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      if (clientList.length > 0) {
        // 有已打开的窗口，聚焦到第一个
        return clientList[0].focus();
      }
      // 没有打开的窗口，打开新窗口
      return clients.openWindow('/');
    })
  );
});
