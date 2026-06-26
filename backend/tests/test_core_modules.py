"""链客宝核心模块测试套件"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── 测试1: 信任引擎评分算法 ──
class TestTrustEngine:
    def setup_method(self):
        from features.trust_engine.scoring import TrustScorer
        self.scorer = TrustScorer()
    
    def test_calculate_breakdown(self):
        result = self.scorer.calculate_breakdown(80, 70, 60)
        assert "overall" in result
        assert result["verification"] == 80
        assert result["behavior"] == 70
        assert result["guarantee"] == 60
    
    def test_tier_mapping(self):
        from features.trust_engine.tier import get_trust_tier
        assert get_trust_tier(750) == "platinum"
        assert get_trust_tier(600) == "gold"
        assert get_trust_tier(400) == "silver"
        assert get_trust_tier(200) == "bronze"
    
    def test_matching_adjustment(self):
        from features.trust_engine.matching import TrustEnhancedMatcher
        matcher = TrustEnhancedMatcher()
        score = matcher.adjust_score(0.85, 750)
        assert score > 0.85  # High trust should boost score


# ── 测试2: 订阅计费服务 ──
class TestSubscriptionService:
    def test_plan_tiers(self):
        from features.subscription.models import PlanTier
        assert PlanTier.FREE.value == "free"
        assert PlanTier.PRO.value == "pro"
        assert PlanTier.BUSINESS.value == "business"
        assert PlanTier.ENTERPRISE.value == "enterprise"
    
    def test_subscription_status(self):
        from features.subscription.models import SubscriptionStatus
        assert SubscriptionStatus.ACTIVE.value == "active"
        assert SubscriptionStatus.CANCELED.value == "canceled"
    
    def test_invoice_creation(self):
        from features.subscription.models import Invoice
        inv = Invoice(
            invoice_no="TEST-001",
            user_id=1,
            amount=100.0,
            total=106.0,
        )
        assert inv.invoice_no == "TEST-001"
        assert inv.total == 106.0


# ── 测试3: KG冷启动匹配 ──
class TestColdStartMatcher:
    def test_fallback_returns_recommendations(self):
        from features.kg_coldstart.coldstart_matcher import ColdStartMatcher
        matcher = ColdStartMatcher()
        recs = matcher._rule_based_fallback("科技", "50-200人", "北京", 5)
        assert len(recs) > 0
        assert recs[0]["match_type"] == "coldstart_fallback"
        assert recs[0]["confidence"] > 0
    
    def test_coldstart_without_params(self):
        from features.kg_coldstart.coldstart_matcher import ColdStartMatcher
        matcher = ColdStartMatcher()
        recs = matcher._rule_based_fallback(None, None, None, 3)
        assert len(recs) > 0


# ── 测试4: SEO模块 ──
class TestSEO:
    def test_sitemap_exists(self):
        import os
        from app.routers import seo
        assert hasattr(seo, "router")
    
    def test_json_ld_structure(self):
        import json
        from app.routers.seo import json_ld
        # Just verify the import works (actual test requires FastAPI test client)


# ── 测试5: 数据安全核心 ──
class TestDataSecurity:
    def test_sanitizer_import(self):
        from data_security.core.sanitizer import Sanitizer
        assert Sanitizer is not None
    
    def test_quarantine_import(self):
        from data_security.quarantine.quarantine_manager import QuarantineManager
        assert QuarantineManager is not None


# ── 测试6: 支付模块 ──
class TestPayment:
    def test_alipay_import(self):
        from payment.providers.alipay import AliPayProvider
        assert AliPayProvider is not None
    
    def test_wxpay_import(self):
        from payment.providers.wxpay import WxPayProvider
        assert WxPayProvider is not None
    
    def test_sdk_import(self):
        from payment.sdk.sign import SignTool
        assert SignTool is not None
