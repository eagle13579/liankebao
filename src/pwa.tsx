import { useState, useEffect, useCallback } from 'react';

/**
 * PWA Service Worker 更新提示组件
 * 检测到新版本时显示"有新版本"更新提示
 */
export default function PwaUpdatePrompt() {
  const [showUpdate, setShowUpdate] = useState(false);

  useEffect(() => {
    const handleUpdate = () => setShowUpdate(true);
    window.addEventListener('sw-update', handleUpdate);
    return () => window.removeEventListener('sw-update', handleUpdate);
  }, []);

  const handleRefresh = useCallback(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.getRegistration().then(reg => {
        if (reg?.waiting) {
          // 让 waiting SW 接管
          reg.waiting.postMessage({ type: 'SKIP_WAITING' });
          // 刷新页面加载新版本
          window.location.reload();
        }
      });
    }
  }, []);

  if (!showUpdate) return null;

  return (
    <div style={{
      position: 'fixed',
      bottom: 24,
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: 9999,
      background: '#1f2937',
      color: '#fff',
      padding: '12px 20px',
      borderRadius: 12,
      boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      fontSize: 14,
      maxWidth: '90vw',
    }}>
      <span>🎉 发现新版本</span>
      <button
        onClick={handleRefresh}
        style={{
          background: '#3B82F6',
          color: '#fff',
          border: 'none',
          borderRadius: 8,
          padding: '6px 16px',
          fontSize: 13,
          cursor: 'pointer',
          fontWeight: 500,
          whiteSpace: 'nowrap',
        }}
      >
        立即更新
      </button>
      <button
        onClick={() => setShowUpdate(false)}
        style={{
          background: 'transparent',
          color: '#9ca3af',
          border: 'none',
          fontSize: 18,
          cursor: 'pointer',
          lineHeight: 1,
          padding: '0 4px',
        }}
        aria-label="关闭"
      >
        ✕
      </button>
    </div>
  );
}
