/**
 * 链客宝 — React 应用入口
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import './globals.css';
import App from './App';

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Root element not found');

// 隐藏骨架屏 (由 index.html 中的 __hideSkeleton 函数处理)
// 在 React 完成首次渲染后执行
function hideSkeleton() {
  if (typeof window.__hideSkeleton === 'function') {
    // 延迟一帧确保 React DOM 已提交
    requestAnimationFrame(() => {
      window.__hideSkeleton();
    });
  }
}

const root = ReactDOM.createRoot(rootElement);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// 首次渲染完成后隐藏骨架屏
// 使用 React 的调度机制确保在布局效果之后触发
setTimeout(hideSkeleton, 50);
