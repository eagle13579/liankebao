/**
 * 链客宝 — 应用根组件
 * 路由配置：
 *   /           → 首页/名片页
 *   /card       → 数字名片 H5 分享页
 *   /card/:id   → 数字名片 H5 分享页（带ID）
 *   /login      → 登录页
 *   /onboarding → 三步冷启动
 *   /admin      → 管理后台
 *
 * 优化: React.lazy + Suspense 实现路由级代码分割, 降低首屏 JS 体积
 */
import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import SEOHead from './components/SEOHead';

// ── 路由级懒加载 (代码分割) ──────────────────────────────────────────────
// 核心路由, 预加载提示: 这些页面会在用户交互前提前加载
const BusinessCardPage = lazy(() => import('./pages/business-card'));
const LoginPage = lazy(() => import('./pages/login/LoginPage'));
const OnboardingPage = lazy(() => import('./pages/onboarding'));
const TrustScorePage = lazy(() => import('./pages/trust/TrustScorePage'));
const BillingPage = lazy(() => import('./pages/billing/BillingPage'));

// ── 内联加载的轻量首页 ────────────────────────────────────────────────────
// 首页非常轻量 (仅 ~1KB JS), 不必做代码分割, 直接内联以减少请求
function HomePage() {
  return (
    <div style={{ textAlign: 'center', padding: '60px 20px', fontFamily: 'system-ui, sans-serif' }}>
      <h1 style={{ fontSize: '2rem', marginBottom: '12px' }}>链客宝</h1>
      <p style={{ color: '#666', marginBottom: '24px' }}>企业家供需匹配平台</p>
      <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', flexWrap: 'wrap' }}>
        <a href="/login" style={{ padding: '10px 24px', background: '#07C160', color: '#fff', borderRadius: '8px', textDecoration: 'none', fontWeight: 'bold' }}>
          微信一键登录
        </a>
        <a href="/card" style={{ padding: '10px 24px', background: '#2563eb', color: '#fff', borderRadius: '8px', textDecoration: 'none' }}>
          数字名片
        </a>
        <a href="/onboarding" style={{ padding: '10px 24px', background: '#f3f4f6', color: '#333', borderRadius: '8px', textDecoration: 'none' }}>
          三步冷启动
        </a>
      </div>
    </div>
  );
}

// ── Suspense 回退组件 (轻量内联, 无额外请求) ────────────────────────────
function RouteFallback() {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '60vh',
      color: '#9ca3af',
      fontSize: '0.875rem',
    }}>
      加载中...
    </div>
  );
}

/** 根据当前路径生成 breadcrumb 数据 */
function usePageMeta() {
  const location = useLocation();
  const path = location.pathname;

  const metaMap: Record<string, { title: string; description: string; breadcrumbs: Array<{ name: string; url: string }> }> = {
    '/': {
      title: '首页',
      description: '链客宝 — 企业家供需匹配平台，帮助企业家高效匹配资源、商机和合作伙伴。',
      breadcrumbs: [{ name: '首页', url: '/' }],
    },
    '/login': {
      title: '登录',
      description: '登录链客宝，开启企业家供需匹配之旅。',
      breadcrumbs: [
        { name: '首页', url: '/' },
        { name: '登录', url: '/login' },
      ],
    },
    '/card': {
      title: '数字名片',
      description: '链客宝数字名片 — 展示企业家个人品牌与业务信息，高效链接合作伙伴。',
      breadcrumbs: [
        { name: '首页', url: '/' },
        { name: '数字名片', url: '/card' },
      ],
    },
    '/onboarding': {
      title: '三步冷启动',
      description: '链客宝三步冷启动引导 — 快速完成资料填写，开启供需匹配。',
      breadcrumbs: [
        { name: '首页', url: '/' },
        { name: '冷启动', url: '/onboarding' },
      ],
    },
    '/trust': {
      title: '信任评分',
      description: '链客宝信任评分系统 — 查看和提升您的企业家信用分数。',
      breadcrumbs: [
        { name: '首页', url: '/' },
        { name: '信任评分', url: '/trust' },
      ],
    },
    '/billing': {
      title: '订阅与计费',
      description: '链客宝订阅计费中心 — 选择适合您的方案并完成支付。',
      breadcrumbs: [
        { name: '首页', url: '/' },
        { name: '订阅与计费', url: '/billing' },
      ],
    },
  };

  // 匹配 /card/:id 路径
  const cardMatch = path.match(/^\/card\/(.+)/);
  if (cardMatch) {
    return {
      title: '数字名片',
      description: '链客宝数字名片 — 查看企业家个人品牌信息。',
      breadcrumbs: [
        { name: '首页', url: '/' },
        { name: '数字名片', url: '/card' },
        { name: `名片 #${cardMatch[1]}`, url: path },
      ],
    };
  }

  return metaMap[path] || metaMap['/'];
}

function AppContent() {
  const meta = usePageMeta();
  return (
    <>
      <SEOHead {...meta} />
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/card" element={<BusinessCardPage />} />
          <Route path="/card/:id" element={<BusinessCardPage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/trust" element={<TrustScorePage />} />
          <Route path="/billing" element={<BillingPage />} />
        </Routes>
      </Suspense>
    </>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}

export default App;
