/**
 * App — 链客宝前端根组件
 *
 * 架构:
 *   1. ModuleProvider 在顶层获取模块列表（从 /api/kernel/modules）
 *   2. Shell 提供统一布局（侧边栏 + 顶栏 + 内容区）
 *   3. 路由: 仪表盘为静态路由，其余模块路由由 DynamicRoutes 动态生成
 *
 * 瘦身后的 App.tsx 不再硬编码路由，模块路由由后端配置驱动。
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import Shell from './shell/Shell';
import { ModuleProvider, DynamicRoutes } from './shell/ModuleLoader';

/* ------------------------------------------------------------------ */
/*  全局懒加载页面（不归属任何业务模块）                                */
/* ------------------------------------------------------------------ */

const Dashboard = lazy(() => import('./pages/dashboard/Dashboard'));

/* ------------------------------------------------------------------ */
/*  登录页（占位，后续由 auth 模块接管）                                */
/* ------------------------------------------------------------------ */

function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md w-96">
        <h1 className="text-2xl font-bold text-center mb-6">链客宝</h1>
        <p className="text-center text-gray-500 text-sm">
          登录功能由 auth 模块提供
        </p>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  根组件                                                            */
/* ------------------------------------------------------------------ */

export default function App() {
  return (
    <BrowserRouter>
      <ModuleProvider baseUrl="/api/kernel">
        <Routes>
          {/* 全局静态路由（登录页等）放在 Shell 外 */}
          <Route path="/login" element={<LoginPage />} />

          {/* 所有需要登录 + 布局的路由进入 Shell */}
          <Route path="/*" element={<Shell />}>
            {/* 默认首页跳转 */}
            <Route index element={<Navigate to="/dashboard" replace />} />

            {/* 仪表盘（静态路由，不归属任何模块） */}
            <Route
              path="dashboard"
              element={
                <Suspense fallback={<div className="p-4 text-gray-400">加载中...</div>}>
                  <Dashboard />
                </Suspense>
              }
            />

            {/* 其余所有模块路由由 DynamicRoutes 动态生成 */}
            <DynamicRoutes />
          </Route>
        </Routes>
      </ModuleProvider>
    </BrowserRouter>
  );
}
