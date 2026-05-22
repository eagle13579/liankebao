import { BrowserRouter as Router, Routes, Route, useLocation, Link } from 'react-router-dom';
import { AnimatePresence } from 'motion/react';
import ErrorBoundary from './components/ErrorBoundary';
import PageTransition from './components/PageTransition';
import { LoginPage, UserRegistration } from './screens/AuthScreens';
import { LiankebaoHomepage, ProductPool, PromotionCenter } from './screens/MainScreens';
import { ProductDetailPage, MyProducts, AddProduct } from './screens/ProductScreens';
import { OrderConfirmation, PaymentSuccessScreens, MyOrders, OrderManagement } from './screens/OrderScreens';
import PaymentBridge from './screens/PaymentBridge';
import { AdminBackend } from './screens/AdminScreens';
import { SubordinatePage } from './screens/SubordinateScreens';
import { PromotionTutorial } from './screens/TutorialScreens';
import { MembershipCenter } from './screens/MembershipScreens';
import RechargeScreens, { RechargeAmountPage, RechargePaymentPage, RechargeResultPage, RechargeHistoryPage, BalanceDetailPage } from './screens/RechargeScreens';
import ContactsPage from './pages/ContactsPage';
import ContactsImportPage from './pages/ContactsImportPage';
import ContactDetailPage from './pages/ContactDetailPage';
import ContactMergePage from './pages/ContactMergePage';

function AnimatedRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait">
      <Routes location={location}>
        <Route path="/" element={<PageTransition><LoginPage /></PageTransition>} />
        <Route path="/register" element={<PageTransition><UserRegistration /></PageTransition>} />
        <Route path="/home" element={<PageTransition><LiankebaoHomepage /></PageTransition>} />
        <Route path="/product-pool" element={<PageTransition><ProductPool /></PageTransition>} />
        <Route path="/promotion-center" element={<PageTransition><PromotionCenter /></PageTransition>} />
        <Route path="/subordinates" element={<PageTransition><SubordinatePage /></PageTransition>} />
        <Route path="/promotion-tutorial" element={<PageTransition><PromotionTutorial /></PageTransition>} />
        <Route path="/membership" element={<PageTransition><MembershipCenter /></PageTransition>} />
        <Route path="/recharge" element={<PageTransition><RechargeAmountPage /></PageTransition>} />
        <Route path="/recharge/pay" element={<PageTransition><RechargePaymentPage /></PageTransition>} />
        <Route path="/recharge/result" element={<PageTransition><RechargeResultPage /></PageTransition>} />
        <Route path="/recharge/history" element={<PageTransition><RechargeHistoryPage /></PageTransition>} />
        <Route path="/recharge/balance" element={<PageTransition><BalanceDetailPage /></PageTransition>} />
        <Route path="/product-detail" element={<PageTransition><ProductDetailPage /></PageTransition>} />
        <Route path="/my-products" element={<PageTransition><MyProducts /></PageTransition>} />
        <Route path="/add-product" element={<PageTransition><AddProduct /></PageTransition>} />
        <Route path="/order-confirm" element={<PageTransition><OrderConfirmation /></PageTransition>} />
        <Route path="/payment-bridge" element={<PageTransition><PaymentBridge /></PageTransition>} />
        <Route path="/payment-success" element={<PageTransition><PaymentSuccessScreens /></PageTransition>} />
        <Route path="/my-orders" element={<PageTransition><MyOrders /></PageTransition>} />
        <Route path="/admin" element={<PageTransition><AdminBackend /></PageTransition>} />
        <Route path="/merchant-orders" element={<PageTransition><OrderManagement /></PageTransition>} />
        <Route path="/contacts" element={<PageTransition><ContactsPage /></PageTransition>} />
        <Route path="/contacts/import" element={<PageTransition><ContactsImportPage /></PageTransition>} />
        <Route path="/contacts/:id" element={<PageTransition><ContactDetailPage /></PageTransition>} />
        <Route path="/contacts/merge" element={<PageTransition><ContactMergePage /></PageTransition>} />
      </Routes>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <Router basename="/liankebao">
      <ErrorBoundary>
      <div className="bg-neutral-bg min-h-screen text-on-surface select-none">
        <AnimatedRoutes />
        
        {/* Hidden toggle for Admin vs User experience - not in spec but useful for preview */}
        <div className="fixed bottom-20 left-4 z-[9999] flex gap-2 opacity-5 pointer-events-none hover:opacity-100 hover:pointer-events-auto transition-opacity">
          <Link to="/" className="p-2 bg-white rounded shadow text-[10px]">User</Link>
          <Link to="/admin" className="p-2 bg-white rounded shadow text-[10px]">Admin</Link>
        </div>
      </div>
      </ErrorBoundary>
    </Router>
  );
}
