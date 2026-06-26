/**
 * 链客宝 — Service Worker 注册入口
 * =============================================================================
 * 应用启动时调用此模块以注册 Service Worker。
 *
 * 用法:
 *   // 在应用入口 (main.tsx / index.tsx / App.tsx) 中:
 *   import './registerSW';
 *
 * 或按需注册:
 *   import { registerSW } from './registerSW';
 *   registerSW();
 * =============================================================================
 */

import { registerServiceWorker, onUpdate, skipWaitingAndReload } from '@/utils/pwa';

export type RegisterSWOptions = {
  /** SW 文件路径，默认 /sw.js */
  swPath?: string;
  /** SW 作用域，默认 / */
  scope?: string;
  /** 是否立即激活新版本（跳过等待），默认 true */
  immediateActivate?: boolean;
  /** 更新检查间隔（毫秒），默认 60 秒 */
  updateInterval?: number;
  /** 注册成功回调 */
  onRegistered?: () => void;
  /** 发现更新回调 */
  onUpdateAvailable?: () => void;
};

/**
 * 注册 Service Worker，支持更新检测与自动激活。
 *
 * @returns Promise<boolean> 是否注册成功
 */
export async function registerSW(options: RegisterSWOptions = {}): Promise<boolean> {
  const {
    swPath = '/sw.js',
    scope = '/',
    immediateActivate = true,
    updateInterval = 60_000,
    onRegistered,
    onUpdateAvailable,
  } = options;

  const result = await registerServiceWorker(swPath, scope);

  if (result.registered) {
    console.log('[PWA] Service Worker 注册成功，作用域:', result.registration?.scope);
    onRegistered?.();

    // 启动更新检测
    if (immediateActivate) {
      onUpdate((registration) => {
        console.log('[PWA] 检测到新版本可用');
        onUpdateAvailable?.();
        // 自动激活新版本
        skipWaitingAndReload();
      }, updateInterval);
    } else {
      onUpdate((registration) => {
        console.log('[PWA] 检测到新版本可用，等待用户确认');
        onUpdateAvailable?.();
      }, updateInterval);
    }
  } else {
    console.warn('[PWA] Service Worker 注册失败:', result.error?.message ?? '未知错误');
  }

  return result.registered;
}

/**
 * 应用入口调用此函数完成 SW 注册（默认配置）
 *
 * 在入口文件顶部直接导入:
 *   import './registerSW';
 * 等价于调用:
 *   initSW();
 */
export function initSW(): void {
  registerSW().catch((err) => {
    console.error('[PWA] Service Worker 初始化失败:', err);
  });
}

// 默认自动初始化（模块导入即执行注册）
initSW();

export default { registerSW, initSW };
