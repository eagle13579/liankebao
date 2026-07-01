import { BrowserRouter as Router, Routes, Route, useLocation, Link } from 'react-router-dom';
import { AnimatePresence } from 'motion/react';
import ErrorBoundary from './components/ErrorBoundary';
import PageTransition from './components/PageTransition';
import PwaUpdatePrompt from './pwa';
import RelationGraphPage from './pages/RelationGraph';
import React, { Suspense, lazy, useState, useEffect } from 'react';
import { I18nProvider } from './i18n';
import FloatingLangSwitcher from './components/FloatingLangSwitcher';
import { Globe } from 'lucide-react';
import { useLocale } from './i18n';
import { ThemeProvider } from './contexts/ThemeContext';
import './styles/themes.css';

// Lazy-loaded screen components for code splitting
const LoginPageLazy = lazy(() => import('./screens/AuthScreens').then(m => ({ default: m.LoginPage })));
const UserRegistrationLazy = lazy(() => import('./screens/AuthScreens').then(m => ({ default: m.UserRegistration })));
const LiankebaoHomepageLazy = lazy(() => import('./screens/MainScreens').then(m => ({ default: m.LiankebaoHomepage })));
const ProductPoolLazy = lazy(() => import('./screens/MainScreens').then(m => ({ default: m.ProductPool })));
const PromotionCenterLazy = lazy(() => import('./screens/MainScreens').then(m => ({ default: m.PromotionCenter })));
const NotificationsScreenLazy = lazy(() => import('./screens/NotificationsScreen'));
const ProductDetailPageLazy = lazy(() => import('./screens/ProductScreens').then(m => ({ default: m.ProductDetailPage })));
const MyProductsLazy = lazy(() => import('./screens/ProductScreens').then(m => ({ default: m.MyProducts })));
const AddProductLazy = lazy(() => import('./screens/ProductScreens').then(m => ({ default: m.AddProduct })));
const OrderConfirmationLazy = lazy(() => import('./screens/OrderScreens').then(m => ({ default: m.OrderConfirmation })));
const PaymentSuccessScreensLazy = lazy(() => import('./screens/OrderScreens').then(m => ({ default: m.PaymentSuccessScreens })));
const MyOrdersLazy = lazy(() => import('./screens/OrderScreens').then(m => ({ default: m.MyOrders })));
const OrderManagementLazy = lazy(() => import('./screens/OrderScreens').then(m => ({ default: m.OrderManagement })));
const PaymentBridgeLazy = lazy(() => import('./screens/PaymentBridge'));
const AdminBackendLazy = lazy(() => import('./screens/AdminScreens').then(m => ({ default: m.AdminBackend })));
const SubordinatePageLazy = lazy(() => import('./screens/SubordinateScreens').then(m => ({ default: m.SubordinatePage })));
const PromotionTutorialLazy = lazy(() => import('./screens/TutorialScreens').then(m => ({ default: m.PromotionTutorial })));
const MembershipCenterLazy = lazy(() => import('./screens/MembershipScreens').then(m => ({ default: m.MembershipCenter })));
const MembershipUpgradeLazy = lazy(() => import('./screens/MembershipScreens').then(m => ({ default: m.MembershipUpgradePage })));
const PartnerPolicyLazy = lazy(() => import('./screens/PartnerPolicy'));
const RechargeAmountPageLazy = lazy(() => import('./screens/RechargeScreens').then(m => ({ default: m.RechargeAmountPage })));
const RechargePaymentPageLazy = lazy(() => import('./screens/RechargeScreens').then(m => ({ default: m.RechargePaymentPage })));
const RechargeResultPageLazy = lazy(() => import('./screens/RechargeScreens').then(m => ({ default: m.RechargeResultPage })));
const RechargeHistoryPageLazy = lazy(() => import('./screens/RechargeScreens').then(m => ({ default: m.RechargeHistoryPage })));
const BalanceDetailPageLazy = lazy(() => import('./screens/RechargeScreens').then(m => ({ default: m.BalanceDetailPage })));
const ContactsPageLazy = lazy(() => import('./pages/ContactsPage'));
const ContactsImportPageLazy = lazy(() => import('./pages/ContactsImportPage'));
const ContactDetailPageLazy = lazy(() => import('./pages/ContactDetailPage'));
const ContactMergePageLazy = lazy(() => import('./pages/ContactMergePage'));
const ProfilePageLazy = lazy(() => import('./pages/ProfilePage'));
const BusinessCardPageLazy = lazy(() => import('./pages/business-card/BusinessCardPage'));
const BIPageLazy = lazy(() => import('./pages/BIPage'));
const DashboardPageLazy = lazy(() => import('./pages/DashboardPage'));
const RecommendPageLazy = lazy(() => import('./pages/RecommendPage'));
const PipelinePageLazy = lazy(() => import('./pages/PipelinePage'));
const DataEnrichPageLazy = lazy(() => import('./pages/DataEnrichPage'));
const GrowthPageLazy = lazy(() => import('./pages/GrowthPage'));
const MatchingEventsPageLazy = lazy(() => import('./pages/MatchingEventsPage'));
const MatchingMetricsPageLazy = lazy(() => import('./pages/MatchingMetricsPage'));
const PrivateBoardPageLazy = lazy(() => import('./pages/PrivateBoardPage'));
// ===== P0心智模型注入页面 =====
const HypothesisGatePageLazy = lazy(() => import('./pages/admin/HypothesisGatePage'));
const UnitEconomicsPageLazy = lazy(() => import('./pages/admin/UnitEconomicsPage'));
const RetroBoardPageLazy = lazy(() => import('./pages/admin/RetroBoardPage'));
const RetentionDashboardPageLazy = lazy(() => import('./pages/admin/RetentionDashboardPage'));
const LearningCenterPageLazy = lazy(() => import('./pages/LearningCenterPage'));
const SupplyDemandHallLazy = lazy(() => import('./screens/SupplyDemandScreens').then(m => ({ default: m.SupplyDemandHall })));
const NeedDetailLazy = lazy(() => import('./screens/SupplyDemandScreens').then(m => ({ default: m.NeedDetail })));
const PostNeedLazy = lazy(() => import('./screens/PostNeedScreen').then(m => ({ default: m.PostNeed })));
const PromoterPageLazy = lazy(() => import('./screens/PromoterScreen').then(m => ({ default: m.PromoterPage })));
const ActivityLogLazy = lazy(() => import('./screens/ActivityScreens').then(m => ({ default: m.ActivityLog })));
const DeveloperPortalPageLazy = lazy(() => import('./pages/developer/DeveloperPortalPage'));
const ContractsPageLazy = lazy(() => import('./pages/contracts/ContractsPage'));
const ContractDetailPageLazy = lazy(() => import('./pages/contracts/ContractDetailPage'));
const PaymentHistoryPageLazy = lazy(() => import('./pages/contracts/PaymentHistoryPage'));

function LazyPage({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-screen bg-[var(--bg-primary)]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-[var(--accent-primary)] border-t-transparent rounded-full animate-spin" />
          <span className="text-[var(--text-muted)] text-sm font-medium tracking-wide">加载中...</span>
        </div>
      </div>
    }>
      {children}
    </Suspense>
  );
}

function AnimatedRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait">
      <Routes location={location}>
        <Route path="/" element={<PageTransition><LazyPage><LoginPageLazy /></LazyPage></PageTransition>} />
        <Route path="/register" element={<PageTransition><LazyPage><UserRegistrationLazy /></LazyPage></PageTransition>} />
        <Route path="/home" element={<PageTransition><LazyPage><LiankebaoHomepageLazy /></LazyPage></PageTransition>} />
        <Route path="/notifications" element={<PageTransition><LazyPage><NotificationsScreenLazy /></LazyPage></PageTransition>} />
        <Route path="/product-pool" element={<PageTransition><LazyPage><ProductPoolLazy /></LazyPage></PageTransition>} />
        <Route path="/promotion-center" element={<PageTransition><LazyPage><PromotionCenterLazy /></LazyPage></PageTransition>} />
        <Route path="/subordinates" element={<PageTransition><LazyPage><SubordinatePageLazy /></LazyPage></PageTransition>} />
        <Route path="/promotion-tutorial" element={<PageTransition><LazyPage><PromotionTutorialLazy /></LazyPage></PageTransition>} />
        <Route path="/partner-policy" element={<PageTransition><LazyPage><PartnerPolicyLazy /></LazyPage></PageTransition>} />
        <Route path="/membership" element={<PageTransition><LazyPage><MembershipCenterLazy /></LazyPage></PageTransition>} />
        <Route path="/membership/upgrade" element={<PageTransition><LazyPage><MembershipUpgradeLazy /></LazyPage></PageTransition>} />
        <Route path="/recharge" element={<PageTransition><LazyPage><RechargeAmountPageLazy /></LazyPage></PageTransition>} />
        <Route path="/recharge/pay" element={<PageTransition><LazyPage><RechargePaymentPageLazy /></LazyPage></PageTransition>} />
        <Route path="/recharge/result" element={<PageTransition><LazyPage><RechargeResultPageLazy /></LazyPage></PageTransition>} />
        <Route path="/recharge/history" element={<PageTransition><LazyPage><RechargeHistoryPageLazy /></LazyPage></PageTransition>} />
        <Route path="/recharge/balance" element={<PageTransition><LazyPage><BalanceDetailPageLazy /></LazyPage></PageTransition>} />
        <Route path="/product-detail" element={<PageTransition><LazyPage><ProductDetailPageLazy /></LazyPage></PageTransition>} />
        <Route path="/my-products" element={<PageTransition><LazyPage><MyProductsLazy /></LazyPage></PageTransition>} />
        <Route path="/add-product" element={<PageTransition><LazyPage><AddProductLazy /></LazyPage></PageTransition>} />
        <Route path="/order-confirm" element={<PageTransition><LazyPage><OrderConfirmationLazy /></LazyPage></PageTransition>} />
        <Route path="/payment-bridge" element={<PageTransition><LazyPage><PaymentBridgeLazy /></LazyPage></PageTransition>} />
        <Route path="/payment-success" element={<PageTransition><LazyPage><PaymentSuccessScreensLazy /></LazyPage></PageTransition>} />
        <Route path="/my-orders" element={<PageTransition><LazyPage><MyOrdersLazy /></LazyPage></PageTransition>} />
        <Route path="/admin" element={<PageTransition><LazyPage><AdminBackendLazy /></LazyPage></PageTransition>} />
        <Route path="/merchant-orders" element={<PageTransition><LazyPage><OrderManagementLazy /></LazyPage></PageTransition>} />
        <Route path="/contacts" element={<PageTransition><LazyPage><ContactsPageLazy /></LazyPage></PageTransition>} />
        <Route path="/contacts/import" element={<PageTransition><LazyPage><ContactsImportPageLazy /></LazyPage></PageTransition>} />
        <Route path="/contacts/:id" element={<PageTransition><LazyPage><ContactDetailPageLazy /></LazyPage></PageTransition>} />
        <Route path="/contacts/merge" element={<PageTransition><LazyPage><ContactMergePageLazy /></LazyPage></PageTransition>} />
        <Route path="/supply-demand" element={<PageTransition><LazyPage><SupplyDemandHallLazy /></LazyPage></PageTransition>} />
        <Route path="/supply-demand/post" element={<PageTransition><LazyPage><PostNeedLazy /></LazyPage></PageTransition>} />
        <Route path="/supply-demand/:id" element={<PageTransition><LazyPage><NeedDetailLazy /></LazyPage></PageTransition>} />
        <Route path="/business-card" element={<PageTransition><LazyPage><BusinessCardPageLazy /></LazyPage></PageTransition>} />
        <Route path="/card/:token" element={<PageTransition><LazyPage><BusinessCardPageLazy /></LazyPage></PageTransition>} />
        <Route path="/profile" element={<PageTransition><LazyPage><ProfilePageLazy /></LazyPage></PageTransition>} />
        <Route path="/bi" element={<PageTransition><LazyPage><BIPageLazy /></LazyPage></PageTransition>} />
        <Route path="/dashboard" element={<PageTransition><LazyPage><DashboardPageLazy /></LazyPage></PageTransition>} />
        <Route path="/recommend" element={<PageTransition><LazyPage><RecommendPageLazy /></LazyPage></PageTransition>} />
        <Route path="/pipeline" element={<PageTransition><LazyPage><PipelinePageLazy /></LazyPage></PageTransition>} />
        <Route path="/enrich" element={<PageTransition><LazyPage><DataEnrichPageLazy /></LazyPage></PageTransition>} />
        <Route path="/growth" element={<PageTransition><LazyPage><GrowthPageLazy /></LazyPage></PageTransition>} />
        <Route path="/matching-events" element={<PageTransition><LazyPage><MatchingEventsPageLazy /></LazyPage></PageTransition>} />
        <Route path="/matching-metrics" element={<PageTransition><LazyPage><MatchingMetricsPageLazy /></LazyPage></PageTransition>} />
        <Route path="/private-board" element={<PageTransition><LazyPage><PrivateBoardPageLazy /></LazyPage></PageTransition>} />
        <Route path="/promoter" element={<PageTransition><LazyPage><PromoterPageLazy /></LazyPage></PageTransition>} />
        <Route path="/activities" element={<PageTransition><LazyPage><ActivityLogLazy /></LazyPage></PageTransition>} />
        <Route path="/developer" element={<PageTransition><LazyPage><DeveloperPortalPageLazy /></LazyPage></PageTransition>} />
        {/* ===== P0心智模型注入路由 ===== */}
        <Route path="/admin/hypothesis-gate" element={<PageTransition><LazyPage><HypothesisGatePageLazy /></LazyPage></PageTransition>} />
        <Route path="/admin/unit-economics" element={<PageTransition><LazyPage><UnitEconomicsPageLazy /></LazyPage></PageTransition>} />
        <Route path="/admin/retro-board" element={<PageTransition><LazyPage><RetroBoardPageLazy /></LazyPage></PageTransition>} />
        <Route path="/admin/retention" element={<PageTransition><LazyPage><RetentionDashboardPageLazy /></LazyPage></PageTransition>} />
        <Route path="/learning-center" element={<PageTransition><LazyPage><LearningCenterPageLazy /></LazyPage></PageTransition>} />
        {/* ===== 交易履约路由 ===== */}
        <Route path="/contracts" element={<PageTransition><LazyPage><ContractsPageLazy /></LazyPage></PageTransition>} />
        <Route path="/contracts/:id" element={<PageTransition><LazyPage><ContractDetailPageLazy /></LazyPage></PageTransition>} />
        <Route path="/contracts/:id/payments" element={<PageTransition><LazyPage><PaymentHistoryPageLazy /></LazyPage></PageTransition>} />
        <Route path="/relation-graph" element={<RelationGraphPage />} />
        </Routes>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <I18nProvider>
      <Router basename="/">
        <AppContent />
      </Router>
    </I18nProvider>
  );
}

function AppContent() {
  const { locale, setLocale } = useLocale();
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  return (
    <ErrorBoundary>
    <div className="bg-[var(--bg-primary)] min-h-screen text-[var(--text-primary)] select-none">
      <AnimatedRoutes />
      <PwaUpdatePrompt />

      {/* Floating draggable language switcher */}
      <FloatingLangSwitcher />

      {/* Theme toggle - bottom right */}
      <button
        onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
        className="fixed bottom-24 right-4 z-[9999] w-10 h-10 rounded-full bg-[var(--bg-card)] border border-[var(--border-primary)] flex items-center justify-center shadow-lg hover:scale-110 transition-transform"
        title="切换主题"
      >
        {theme === 'dark' ? '☀️' : '🌙'}
      </button>
    </div>
    </ErrorBoundary>
  );
}
