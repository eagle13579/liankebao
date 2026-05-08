import React from 'react';
import { useState, useEffect } from 'react';

// Loading 组件
export function Loading({ text = '加载中...' }: { text?: string }) {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-primary-container border-t-transparent rounded-full animate-spin" />
        <span className="text-xs text-text-muted">{text}</span>
      </div>
    </div>
  );
}

// Error 组件
export function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
      <div className="w-14 h-14 bg-red-50 rounded-full flex items-center justify-center mb-3">
        <span className="text-red-500 text-2xl">⚠</span>
      </div>
      <p className="text-sm text-red-600 mb-4">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="px-4 py-2 bg-primary-container text-white rounded-lg text-xs font-bold active:scale-95 transition-transform">
          重试
        </button>
      )}
    </div>
  );
}

// Empty 组件
export function Empty({ text = '暂无数据', icon }: { text?: string; icon?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16">
      <span className="text-4xl mb-3">{icon || '📭'}</span>
      <p className="text-sm text-text-muted">{text}</p>
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