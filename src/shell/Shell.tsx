/**
 * Shell — 链客宝统一布局组件
 *
 * 提供：侧边栏导航（从模块列表自动生成）、顶部栏、主内容区。
 * 配合 ModuleLoader 使用，侧边栏菜单项完全由后端模块定义驱动。
 *
 * 依赖：需要 <ModuleProvider> 包裹在祖先组件中提供模块列表。
 */

import { useState, useCallback, useContext, type ReactNode } from 'react';
import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { ModuleContext } from './ModuleLoader';
import type { ModuleInfo } from './ModuleLoader';

/* ------------------------------------------------------------------ */
/*  常量                                                              */
/* ------------------------------------------------------------------ */

/** 模块名称 → 中文标签映射（用于侧边栏显示） */
const MODULE_LABELS: Record<string, string> = {
  dashboard:       '仪表盘',
  auth:            '认证',
  admin:           '管理后台',
  contacts:        '人脉管理',
  needs:           '需求管理',
  orders:          '订单管理',
  products:        '产品管理',
  promoter:        '推广分润',
  imports:         '数据导入',
  insights:        '数据洞察',
  invoice:         '发票管理',
  matching_engine: '匹配引擎',
  payment:         '支付管理',
  placeholder:     '工具',
  recharge:        '充值管理',
  reconciliation:  '对账管理',
  search:          '搜索',
};

/** 模块 → 图标（使用 emoji / 文字图标，后续可替换为 lucide-react） */
const MODULE_ICONS: Record<string, string> = {
  dashboard:       '📊',
  auth:            '🔐',
  admin:           '⚙️',
  contacts:        '👥',
  needs:           '📋',
  orders:          '📦',
  products:        '🏷️',
  promoter:        '📢',
  imports:         '📥',
  insights:        '📈',
  invoice:         '🧾',
  matching_engine: '🔗',
  payment:         '💳',
  placeholder:     '🛠️',
  recharge:        '💰',
  reconciliation:  '📑',
  search:          '🔍',
};

/** 顶栏用户菜单 */
const USER_MENU_ITEMS = [
  { label: '个人设置', path: '/admin/settings' },
  { label: '退出登录', path: '/logout' },
];

/* ------------------------------------------------------------------ */
/*  Shell 组件                                                       */
/* ------------------------------------------------------------------ */

interface ShellProps {
  /** 应用标题（显示在顶栏） */
  title?: string;
  /** 应用 Logo URL */
  logoUrl?: string;
  /** 可选：显式传入模块列表（覆盖上下文中自动获取的列表） */
  modules?: ModuleInfo[];
  /** 子元素，未使用 Outlet 时回退 */
  children?: ReactNode;
  /** 顶栏右侧额外操作区 */
  headerExtra?: ReactNode;
}

export default function Shell({
  title = '链客宝',
  logoUrl,
  modules: explicitModules,
  children,
  headerExtra,
}: ShellProps) {
  const location = useLocation();
  const navigate = useNavigate();

  // 从 ModuleProvider 上下文读取模块列表（如果未显式传入）
  const contextModules = useContext(ModuleContext);
  const modules = explicitModules ?? contextModules.modules;
  const loading = explicitModules ? false : contextModules.loading;

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  /* 获取模块的主路由路径（第一个路由）用于 NavLink 高亮 ------------ */
  const modulePrimaryRoute = useCallback(
    (mod: ModuleInfo): string => {
      const routes = mod.frontend?.routes ?? [];
      return routes.length > 0 ? routes[0] : `/${mod.name}`;
    },
    [],
  );

  const moduleLabel = useCallback(
    (mod: ModuleInfo): string =>
      MODULE_LABELS[mod.name] ?? mod.description ?? mod.name,
    [],
  );

  const moduleIcon = useCallback(
    (mod: ModuleInfo): string => MODULE_ICONS[mod.name] ?? '📄',
    [],
  );

  /* 侧边栏导航项 ------------------------------------------------- */
  const navItems = useCallback(() => {
    // 仪表盘置顶
    const items: { name: string; path: string; icon: string; label: string }[] = [
      { name: 'dashboard', path: '/dashboard', icon: '📊', label: '仪表盘' },
    ];

    for (const mod of modules) {
      const path = modulePrimaryRoute(mod);
      items.push({
        name: mod.name,
        path,
        icon: moduleIcon(mod),
        label: moduleLabel(mod),
      });
    }

    return items;
  }, [modules, modulePrimaryRoute, moduleIcon, moduleLabel]);

  /* 加载状态 — 显示简化布局 --------------------------------------- */
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-gray-400">加载中...</span>
        </div>
      </div>
    );
  }

  /* 主渲染 -------------------------------------------------------- */
  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {/* ============ 侧边栏 ============ */}
      <aside
        className={`
          flex-shrink-0 bg-white border-r border-gray-200
          transition-all duration-200 ease-in-out
          flex flex-col
          ${sidebarOpen ? 'w-56' : 'w-14'}
        `}
      >
        {/* Logo / 折叠按钮 */}
        <div className="h-14 flex items-center border-b border-gray-200 px-3 gap-2">
          <button
            onClick={() => setSidebarOpen((v) => !v)}
            className="flex-shrink-0 w-8 h-8 flex items-center justify-center
                       rounded-md hover:bg-gray-100 text-gray-500 text-sm
                       transition-colors"
            title={sidebarOpen ? '收起侧栏' : '展开侧栏'}
          >
            {sidebarOpen ? '◀' : '▶'}
          </button>
          {sidebarOpen && (
            <span className="font-semibold text-gray-800 truncate">
              {logoUrl ? <img src={logoUrl} alt={title} className="h-6 inline" /> : title}
            </span>
          )}
        </div>

        {/* 导航菜单 */}
        <nav className="flex-1 overflow-y-auto py-2 px-1 space-y-0.5">
          {navItems().map((item) => (
            <NavLink
              key={item.name}
              to={item.path}
              end={item.path === '/dashboard'}
              className={({ isActive }) =>
                `flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors ${
                  isActive
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-800'
                }`
              }
            >
              <span className="flex-shrink-0 w-6 text-center text-base">
                {item.icon}
              </span>
              {sidebarOpen && (
                <span className="truncate">{item.label}</span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* 侧边栏底部 */}
        <div className="border-t border-gray-200 p-2">
          {sidebarOpen && (
            <div className="text-xs text-gray-400 text-center">
              v{/* 版本号由构建注入 */}1.0.0
            </div>
          )}
        </div>
      </aside>

      {/* ============ 主内容区 ============ */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* --- 顶栏 --- */}
        <header className="h-14 flex-shrink-0 bg-white border-b border-gray-200
                          flex items-center justify-between px-4 gap-4">
          {/* 面包屑 / 当前页面 */}
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <span className="text-gray-300">/</span>
            <span className="text-gray-700 font-medium capitalize">
              {location.pathname.split('/').filter(Boolean).join(' / ')}
            </span>
          </div>

          {/* 右侧操作区 */}
          <div className="flex items-center gap-3">
            {headerExtra}

            {/* 用户菜单 */}
            <div className="relative">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setUserMenuOpen((v) => !v);
                }}
                className="w-8 h-8 rounded-full bg-blue-500 text-white
                           flex items-center justify-center text-sm font-medium
                           hover:bg-blue-600 transition-colors"
                title="用户菜单"
              >
                U
              </button>

              {userMenuOpen && (
                <div className="absolute right-0 mt-2 w-40 bg-white rounded-md
                              shadow-lg border border-gray-200 py-1 z-50">
                  {USER_MENU_ITEMS.map((item) => (
                    <button
                      key={item.label}
                      onClick={() => {
                        setUserMenuOpen(false);
                        navigate(item.path);
                      }}
                      className="w-full text-left px-3 py-1.5 text-sm
                                 text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </header>

        {/* --- 页面内容 --- */}
        <main className="flex-1 overflow-auto p-6">
          {children ?? <Outlet />}
        </main>
        {/* --- Footer — ICP备案号 --- */}
        <footer className="flex-shrink-0 border-t border-gray-200 text-center text-xs text-gray-400 py-3">
          <a
            href="https://beian.miit.gov.cn/"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-gray-500 transition-colors"
          >
            沪ICP备2026007459号-2
          </a>
        </footer>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  导出                                                              */
/* ------------------------------------------------------------------ */

export { MODULE_LABELS, MODULE_ICONS };
