import React from 'react';
import { useState, useEffect } from 'react';

// Loading 组件 - 增强版
export function Loading({ text = '加载中...' }: { text?: string }) {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="flex flex-col items-center gap-4">
        <div className="relative w-10 h-10">
          <div className="absolute inset-0 border-2 border-sky-200 rounded-full" />
          <div className="absolute inset-0 border-2 border-sky-500 border-t-transparent rounded-full animate-spin" />
        </div>
        <span className="text-xs text-slate-400 font-medium tracking-wide">{text}</span>
      </div>
    </div>
  );
}

// Skeleton loading for cards
export function CardSkeleton({ count = 4, columns = 2 }: { count?: number; columns?: number }) {
  return (
    <div className={`grid grid-cols-${columns} gap-4`}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-white rounded-2xl overflow-hidden border border-slate-100">
          <div className="aspect-square skeleton" />
          <div className="p-3 space-y-2">
            <div className="h-3 skeleton rounded w-3/4" />
            <div className="h-4 skeleton rounded w-1/2" />
            <div className="h-8 skeleton rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Error 组件 - 增强版
export function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      <div className="w-16 h-16 bg-gradient-to-br from-red-50 to-rose-50 rounded-2xl flex items-center justify-center mb-4 border border-red-100 shadow-sm">
        <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
        </svg>
      </div>
      <p className="text-sm text-red-500 font-medium mb-4 max-w-xs">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-5 py-2.5 bg-gradient-to-r from-sky-500 to-blue-600 text-white rounded-xl text-xs font-bold active:scale-95 transition-all shadow-md shadow-sky-500/20 hover:shadow-lg"
        >
          重新加载
        </button>
      )}
    </div>
  );
}

// Empty 组件 - 增强版(动画+暗色适配)
export function Empty({ text = '暂无数据', icon, description, actionText, onAction }: { text?: string; icon?: string; description?: string; actionText?: string; onAction?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 animate-fadeIn">
      <div className="w-16 h-16 bg-gradient-to-br from-slate-50 to-sky-50 dark:from-dark-surface dark:to-sky-500/10 rounded-2xl flex items-center justify-center mb-4 border border-slate-100 dark:border-dark-border shadow-sm">
        <span className="text-2xl animate-bounce-subtle">{icon || '📭'}</span>
      </div>
      <p className="text-sm text-slate-500 dark:text-dark-muted font-medium">{text}</p>
      {description && (
        <p className="text-xs text-slate-400 dark:text-dark-muted/60 mt-1">{description}</p>
      )}
      {actionText && onAction && (
        <button onClick={onAction} className="mt-3 text-xs px-4 py-2 rounded-lg bg-gradient-to-r from-sky-500 to-blue-600 text-white font-medium shadow-md hover:shadow-lg hover:scale-105 active:scale-95 transition-all">
          {actionText}
        </button>
      )}
    </div>
  );
}

type Status = 'loading' | 'error' | 'success';

export function useApi<T>(fetcher: () => Promise<T>, deps: any[] = []): { data: T | null; status: Status; error: string; refetch: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [status, setStatus] = useState<Status>('loading');
  const [error, setError] = useState('');

  const fetch = async () => {
    setStatus('loading');
    try {
      const result = await fetcher();
      setData(result);
      setStatus('success');
    } catch (e: any) {
      setError(e.message || '请求失败');
      setStatus('error');
    }
  };

  useEffect(() => { fetch(); }, deps);

  return { data, status, error, refetch: fetch };
}
