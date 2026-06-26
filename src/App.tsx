/**
 * 链客宝 — 应用根组件
 * 路由配置：
 *   /           → 首页/名片页
 *   /card       → 数字名片 H5 分享页
 *   /card/:id   → 数字名片 H5 分享页（带ID）
 *   /login      → 登录页
 *   /onboarding → 三步冷启动
 *   /admin      → 管理后台
 */
import React from 'react';
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import BusinessCardPage from './pages/business-card';
import OnboardingPage from './pages/onboarding';
import LoginPage from './pages/login/LoginPage';
import TrustScorePage from './pages/trust/TrustScorePage';
import SEOHead from './components/SEOHead';

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
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/card" element={<BusinessCardPage />} />
        <Route path="/card/:id" element={<BusinessCardPage />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/trust" element={<TrustScorePage />} />
      </Routes>
    </>
  );
}

function HomePage() {
  return (
    <div style={{ textAlign: 'center', padding: '60px 20px', fontFamily: 'system-ui, sans-serif' }}>
      <h1 style={{ fontSize: '2rem', marginBottom: '12px' }}>链客宝</h1>
      <p style={{ color: '#666', marginBottom: '24px' }}>企业家供需匹配平台</p>
      <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
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

function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}

export default App;
