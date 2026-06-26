/* =============================================================================
 * 链客宝 — PWA 工具模块
 * Service Worker 注册 / 更新检测 / 推送通知 / 在线状态
 * ============================================================================= */

import { useEffect, useState, useCallback } from 'react';

// ===== 类型定义 =====

export interface SWRegistrationResult {
  registered: boolean;
  registration: ServiceWorkerRegistration | null;
  error?: Error;
}

export type UpdateCallback = (registration: ServiceWorkerRegistration) => void;

// ===== Service Worker 注册 =====

/**
 * 注册 Service Worker
 * @param swPath  SW 文件路径，默认 /sw.js
 * @param scope   SW 作用域，默认 /
 * @returns       Promise<SWRegistrationResult>
 */
export async function registerServiceWorker(
  swPath: string = '/sw.js',
  scope: string = '/'
): Promise<SWRegistrationResult> {
  if (!('serviceWorker' in navigator)) {
    console.warn('[PWA] 当前浏览器不支持 Service Worker');
    return { registered: false, registration: null };
  }

  try {
    const registration = await navigator.serviceWorker.register(swPath, { scope });

    console.log('[PWA] Service Worker 注册成功:', registration.scope);

    // 监听更新
    registration.addEventListener('updatefound', () => {
      const installingWorker = registration.installing;
      if (!installingWorker) return;

      installingWorker.addEventListener('statechange', () => {
        if (installingWorker.state === 'installed') {
          if (navigator.serviceWorker.controller) {
            // 新版本已安装，等待激活
            console.log('[PWA] 新版本已下载，等待激活');
          } else {
            // 首次安装成功
            console.log('[PWA] 首次安装完成，内容已缓存');
          }
        }
      });
    });

    return { registered: true, registration };
  } catch (error) {
    console.error('[PWA] Service Worker 注册失败:', error);
    return {
      registered: false,
      registration: null,
      error: error instanceof Error ? error : new Error(String(error)),
    };
  }
}

// ===== 更新检测 =====

/**
 * 检测 Service Worker 更新
 * @param callback  发现更新时的回调函数
 * @param interval  检查间隔（毫秒），默认 60 秒
 * @returns         清理函数
 */
export function onUpdate(
  callback: UpdateCallback,
  interval: number = 60_000
): () => void {
  if (!('serviceWorker' in navigator)) {
    return () => {};
  }

  let isActive = true;

  const checkForUpdates = async () => {
    if (!isActive) return;

    try {
      const registration = await navigator.serviceWorker.getRegistration();
      if (!registration) return;

      // 每 24 小时检查一次更新（根据 interval 参数调整实际行为）
      registration.update().then(() => {
        if (registration.waiting && isActive) {
          callback(registration);
        }
      });
    } catch (error) {
      console.warn('[PWA] 更新检测失败:', error);
    }
  };

  // 立即检查一次
  checkForUpdates();

  // 定时检查
  const timerId = setInterval(checkForUpdates, interval);

  // 监听 controllerchange（新 SW 激活）
  const onControllerChange = () => {
    console.log('[PWA] 新 Service Worker 已激活');
  };
  navigator.serviceWorker.addEventListener('controllerchange', onControllerChange);

  return () => {
    isActive = false;
    clearInterval(timerId);
    navigator.serviceWorker.removeEventListener('controllerchange', onControllerChange);
  };
}

// ===== 推送通知 =====

/**
 * 请求通知权限
 * @returns Promise<'granted' | 'denied' | 'default'>
 */
export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!('Notification' in window)) {
    console.warn('[PWA] 当前浏览器不支持 Notification API');
    return 'denied';
  }

  // 如果已经是 granted，直接返回
  if (Notification.permission === 'granted') {
    return 'granted';
  }

  try {
    const permission = await Notification.requestPermission();
    console.log('[PWA] 通知权限:', permission);
    return permission;
  } catch (error) {
    console.error('[PWA] 请求通知权限失败:', error);
    return 'denied';
  }
}

/**
 * 显示推送通知
 * @param title   通知标题
 * @param body    通知内容
 * @param options 额外选项
 */
export async function showNotification(
  title: string,
  body: string,
  options?: {
    icon?: string;
    tag?: string;
    vibrate?: number[];
    data?: Record<string, unknown>;
  }
): Promise<void> {
  // 检查是否已有 Service Worker 注册
  if ('serviceWorker' in navigator) {
    try {
      const registration = await navigator.serviceWorker.getRegistration();
      if (registration && 'showNotification' in registration) {
        await registration.showNotification(title, {
          body,
          icon: options?.icon || '/icons/icon-192x192.png',
          badge: '/icons/icon-192x192.png',
          tag: options?.tag || 'chainke-notification',
          vibrate: options?.vibrate || [200, 100, 200],
          data: options?.data || {},
          requireInteraction: true,
        });
        return;
      }
    } catch (error) {
      console.warn('[PWA] Service Worker 通知失败，降级到普通通知:', error);
    }
  }

  // 降级：使用普通 Notification API
  if (Notification.permission === 'granted') {
    new Notification(title, {
      body,
      icon: options?.icon || '/icons/icon-192x192.png',
    });
  }
}

// ===== 在线状态 Hook =====

/**
 * useOnlineStatus — 跟踪网络在线状态
 * @returns { isOnline: boolean }
 *
 * 用法:
 *   const { isOnline } = useOnlineStatus();
 *   if (!isOnline) { /* 显示离线提示 *\/ }
 */
export function useOnlineStatus(): { isOnline: boolean } {
  const [isOnline, setIsOnline] = useState<boolean>(
    typeof navigator !== 'undefined' ? navigator.onLine : true
  );

  const handleOnline = useCallback(() => {
    console.log('[PWA] 网络已恢复在线');
    setIsOnline(true);
  }, []);

  const handleOffline = useCallback(() => {
    console.log('[PWA] 网络已断开');
    setIsOnline(false);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    // 同步当前状态
    setIsOnline(navigator.onLine);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [handleOnline, handleOffline]);

  return { isOnline };
}

// ===== 应用更新提示组件 =====

/**
 * 检查并等待 SW 更新激活
 * 在用户确认后，向 waiting SW 发送 skipWaiting 消息
 */
export function skipWaitingAndReload(): void {
  if (!('serviceWorker' in navigator)) return;

  navigator.serviceWorker.getRegistration().then((registration) => {
    if (!registration || !registration.waiting) return;

    // 向 waiting 的 SW 发送激活消息
    registration.waiting.postMessage({ type: 'SKIP_WAITING' });

    // 等待新 SW 激活后刷新页面
    const onControllerChange = () => {
      window.location.reload();
      navigator.serviceWorker.removeEventListener('controllerchange', onControllerChange);
    };
    navigator.serviceWorker.addEventListener('controllerchange', onControllerChange);
  });
}

export default {
  registerServiceWorker,
  onUpdate,
  requestNotificationPermission,
  showNotification,
  useOnlineStatus,
  skipWaitingAndReload,
};
