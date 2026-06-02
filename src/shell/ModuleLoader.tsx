/**
 * ModuleLoader — 动态模块加载器
 *
 * 启动时从 /api/kernel/modules 获取活跃模块列表，根据每个模块的
 * frontend.routes 动态生成 React Router Route 元素。
 *
 * 所有模块的前端组件在同一个 bundle 中（已通过 vite.config.ts 的
 * manualChunks 配置懒加载），ModuleLoader 根据后端返回的模块列表
 * 仅加载活跃模块的路由。
 *
 * 用法：在 <Routes> 内使用 <DynamicRoutes /> 作为 Route 元素集合，
 *       或在 App.tsx 中使用 useModuleRoutes() hook 获取路由配置数组。
 */

import { useEffect, useState, lazy, Suspense, createContext, useContext, useCallback } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import type { ComponentType, ReactElement } from 'react';

/* ------------------------------------------------------------------ */
/*  类型定义                                                           */
/* ------------------------------------------------------------------ */

interface FrontendConfig {
  /** 模块前端入口路径（如 ./frontend/AuthModule） */
  entry: string;
  /** 该模块声明的前端路由列表 */
  routes: string[];
}

interface ModuleInfo {
  name: string;
  version: string;
  description: string;
  enabled: boolean;
  frontend: FrontendConfig;
}

interface ModulesResponse {
  modules: ModuleInfo[];
}

interface ModuleRouteConfig {
  moduleName: string;
  path: string;
  entry: string;
}

/* ------------------------------------------------------------------ */
/*  组件注册表 — 将模块入口映射到懒加载组件                            */
/* ------------------------------------------------------------------ */
/*  所有模块组件已在同一 bundle 中，通过 React.lazy + manualChunks   */
/*  实现代码分割。新模块只需在此注册即可。                            */

const moduleComponentMap: Record<string, React.LazyExoticComponent<ComponentType<any>>> = {
  './frontend/AuthModule':           lazy(() => import('../pages/auth/AuthModule')),
  './frontend/AdminModule':          lazy(() => import('../pages/admin/AdminModule')),
  './frontend/ContactsModule':       lazy(() => import('../pages/contacts/ContactsModule')),
  './frontend/NeedsModule':          lazy(() => import('../pages/needs/NeedsModule')),
  './frontend/OrdersModule':         lazy(() => import('../pages/orders/OrdersModule')),
  './frontend/ProductsModule':       lazy(() => import('../pages/products/ProductsModule')),
  './frontend/PromoterModule':       lazy(() => import('../pages/promoter/PromoterModule')),
  './frontend/ImportsModule':        lazy(() => import('../pages/imports/ImportsModule')),
  './frontend/InsightsModule':       lazy(() => import('../pages/insights/InsightsModule')),
  './frontend/InvoiceModule':        lazy(() => import('../pages/invoice/InvoiceModule')),
  './frontend/MatchingEngineModule': lazy(() => import('../pages/matching/MatchingEngineModule')),
  './frontend/PaymentModule':        lazy(() => import('../pages/payment/PaymentModule')),
  './frontend/PlaceholderModule':    lazy(() => import('../pages/placeholder/PlaceholderModule')),
  './frontend/RechargeModule':       lazy(() => import('../pages/recharge/RechargeModule')),
  './frontend/ReconciliationModule': lazy(() => import('../pages/reconciliation/ReconciliationModule')),
  './frontend/SearchModule':         lazy(() => import('../pages/search/SearchModule')),
  './frontend/BusinessCardModule':   lazy(() => import('../pages/business-card/BusinessCardModule')),
};

/* ------------------------------------------------------------------ */
/*  上下文 — 跨组件共享模块列表                                        */
/* ------------------------------------------------------------------ */

interface ModuleContextValue {
  modules: ModuleInfo[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

const ModuleContext = createContext<ModuleContextValue>({
  modules: [],
  loading: true,
  error: null,
  refresh: () => {},
});

/* ------------------------------------------------------------------ */
/*  Provider — 在 Shell 或 App 顶层获取模块列表                        */
/* ------------------------------------------------------------------ */

interface ModuleProviderProps {
  baseUrl?: string;
  children?: React.ReactNode;
}

export function ModuleProvider({
  baseUrl = '/api/kernel',
  children,
}: ModuleProviderProps) {
  const [modules, setModules] = useState<ModuleInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchModules = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const res = await fetch(`${baseUrl}/modules`, {
        credentials: 'include',
        headers: { Accept: 'application/json' },
      });

      if (!res.ok) {
        throw new Error(`请求失败: ${res.status} ${res.statusText}`);
      }

      const data: ModulesResponse = await res.json();
      const activeModules = (data.modules ?? []).filter((m) => m.enabled);
      setModules(activeModules);
    } catch (err) {
      const message = err instanceof Error ? err.message : '未知错误';
      setError(message);
      console.error('[ModuleLoader] 获取模块列表失败:', err);
    } finally {
      setLoading(false);
    }
  }, [baseUrl]);

  useEffect(() => {
    fetchModules();
  }, [fetchModules]);

  return (
    <ModuleContext.Provider value={{ modules, loading, error, refresh: fetchModules }}>
      {children}
    </ModuleContext.Provider>
  );
}

/* ------------------------------------------------------------------ */
/*  Hook — 获取模块路由配置数组                                        */
/* ------------------------------------------------------------------ */

export function useModuleRoutes(): {
  loading: boolean;
  error: string | null;
  routes: ModuleRouteConfig[];
} {
  const { modules, loading, error } = useContext(ModuleContext);

  const routes: ModuleRouteConfig[] = [];
  for (const mod of modules) {
    const entry = mod.frontend?.entry;
    const moduleRoutes = mod.frontend?.routes ?? [];
    if (!entry) continue;
    for (const routePath of moduleRoutes) {
      routes.push({ moduleName: mod.name, path: routePath, entry });
    }
  }

  return { loading, error, routes };
}

/* ------------------------------------------------------------------ */
/*  加载 / 错误占位组件                                                */
/* ------------------------------------------------------------------ */

function LoadingFallback() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="text-gray-400 text-sm">加载中...</div>
    </div>
  );
}

function NotFoundFallback({ path }: { path: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-64 text-gray-500">
      <div className="text-4xl mb-2">404</div>
      <div className="text-sm">模块组件未找到: {path}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  DynamicRoutes — 在 <Routes> 内生成 <Route> 元素集合                */
/* ------------------------------------------------------------------ */
/*  用法:                                                             */
/*    <Routes>                                                        */
/*      <Route path="/dashboard" element={<Dashboard />} />           */
/*      <Route path="*" element={<DynamicRoutes />} />                */
/*    </Routes>                                                       */
/*                                                                   */
/*  注意: DynamicRoutes 自身不包裹 <Routes>，只生成 <Route> 片段。    */
/*  它依赖外层的 <Routes> 来做路径匹配。                               */
/* ------------------------------------------------------------------ */

export function DynamicRoutes() {
  const { modules, loading, error } = useContext(ModuleContext);

  /* 加载中 — 返回空，由 Shell 或上层处理 loading 状态 */
  if (loading) return null;

  /* 错误状态 — 降级为通配重定向 */
  if (error) {
    return <Route path="*" element={<Navigate to="/dashboard" replace />} />;
  }

  const routeElements: ReactElement[] = [];

  for (const mod of modules) {
    const entry = mod.frontend?.entry;
    const routes = mod.frontend?.routes ?? [];

    if (!entry || routes.length === 0) continue;

    const LazyComponent = moduleComponentMap[entry];

    for (const routePath of routes) {
      routeElements.push(
        <Route
          key={`${mod.name}:${routePath}`}
          path={routePath}
          element={
            <Suspense fallback={<LoadingFallback />}>
              {LazyComponent ? (
                <LazyComponent />
              ) : (
                <NotFoundFallback path={entry} />
              )}
            </Suspense>
          }
        />,
      );
    }
  }

  // 兜底路由
  routeElements.push(
    <Route key="__fallback" path="*" element={<Navigate to="/dashboard" replace />} />,
  );

  return <>{routeElements}</>;
}

/* ------------------------------------------------------------------ */
/*  原始 ModuleLoader 组件（兼容旧用法 — 直接渲染 Routes）              */
/* ------------------------------------------------------------------ */

interface ModuleLoaderProps {
  baseUrl?: string;
  defaultRedirect?: string;
  onModulesLoaded?: (modules: ModuleInfo[]) => void;
}

export default function ModuleLoader({
  baseUrl = '/api/kernel',
  defaultRedirect = '/dashboard',
  onModulesLoaded,
}: ModuleLoaderProps) {
  const { modules, loading, error, refresh } = useContext(ModuleContext);

  /* 通知外部模块已加载 */
  useEffect(() => {
    if (!loading && !error && modules.length > 0) {
      onModulesLoaded?.(modules);
    }
  }, [modules, loading, error, onModulesLoaded]);

  /* 加载中 */
  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-gray-400">加载模块中...</span>
        </div>
      </div>
    );
  }

  /* 错误 */
  if (error) {
    console.warn('[ModuleLoader] 降级为静态路由, 原因:', error);
    return (
      <Routes>
        <Route path="*" element={<Navigate to={defaultRedirect} replace />} />
      </Routes>
    );
  }

  /* 正常渲染动态路由 */
  return (
    <Routes>
      <DynamicRoutes />
    </Routes>
  );
}

/* ------------------------------------------------------------------ */
/*  导出                                                              */
/* ------------------------------------------------------------------ */

export type { ModuleInfo, FrontendConfig, ModulesResponse, ModuleRouteConfig };
export { moduleComponentMap, ModuleContext };
