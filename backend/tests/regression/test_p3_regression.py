"""
链客宝 P3 全量回归测试
======================
覆盖: Docker · Neo4j · i18n · 跨境匹配 · 特征工厂 · CI/CD · 全面回归
总计: 25+ 个测试用例

Author: 朱獳 (P6, 技术部, QA/自动化测试)
"""

import os
import sys
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(os.environ.get(
    "CHAINKE_ROOT",
    "D:\\chainke-full",
)).resolve()
BACKEND_ROOT = PROJECT_ROOT / "backend"
TESTS_ROOT = BACKEND_ROOT / "tests"
REGRESSION_ROOT = TESTS_ROOT / "regression"

# 确保 backend 在 sys.path 中
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ===================================================================
# A. Docker 相关 (3 个)
# ===================================================================

class TestDocker:
    """Dockerfile / docker-compose / .dockerignore 完整性验证"""

    DOCKERFILE = PROJECT_ROOT / "Dockerfile"
    COMPOSE = PROJECT_ROOT / "docker-compose.yml"
    DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"

    def test_a1_dockerfile_multi_stage(self):
        """Dockerfile 存在且含多阶段构建关键词"""
        assert self.DOCKERFILE.is_file(), f"Dockerfile 不存在: {self.DOCKERFILE}"
        content = self.DOCKERFILE.read_text(encoding="utf-8")

        # 多阶段构建特征
        assert "AS build" in content or "as build" in content, \
            "缺少 build 阶段 (AS build)"
        assert "FROM" in content, "缺少 FROM 指令"
        assert "AS runtime" in content or "as runtime" in content, \
            "缺少 runtime 阶段 (AS runtime)"
        assert "COPY --from=" in content, "缺少跨阶段文件复制 (COPY --from=)"

    def test_a2_compose_three_services(self):
        """docker-compose.yml 含 backend / redis / nginx 三服务"""
        assert self.COMPOSE.is_file(), f"docker-compose.yml 不存在: {self.COMPOSE}"
        content = self.COMPOSE.read_text(encoding="utf-8")

        assert "backend:" in content, "缺少 backend 服务"
        assert "redis:" in content, "缺少 redis 服务"
        assert "nginx:" in content, "缺少 nginx 服务"

    def test_a3_dockerignore_contents(self):
        """.dockerignore 含 __pycache__ / .env* / *.db"""
        assert self.DOCKERIGNORE.is_file(), f".dockerignore 不存在: {self.DOCKERIGNORE}"
        content = self.DOCKERIGNORE.read_text(encoding="utf-8")

        assert "__pycache__" in content, "缺少 __pycache__/"
        assert ".env" in content, "缺少 .env"
        assert "*.db" in content, "缺少 *.db"


# ===================================================================
# B. Neo4j 迁移 (3 个)
# ===================================================================

class TestNeo4j:
    """Neo4jClient 降级模式 / 迁移 / Cypher 回退验证"""

    def test_b1_neo4j_client_degradation(self):
        """Neo4jClient 降级模式正常工作 (无密码时自动 networkx)"""
        from backend.ml.knowledge_graph.neo4j_client import Neo4jClient

        client = Neo4jClient(password=None)
        result = client.connect()
        assert result is False, "无密码时应返回 False (降级)"
        assert client.mode == "networkx", \
            f"预期 mode='networkx', 实际 mode='{client.mode}'"
        client.close()

    def test_b2_migrate_from_networkx_双模式(self):
        """migrate_from_networkx 在 Neo4j 模式下跳过, 返回正确统计"""
        from backend.ml.knowledge_graph.neo4j_client import Neo4jClient, migrate_from_networkx
        import networkx as nx

        client = Neo4jClient(password=None)
        client.connect()
        assert client.mode == "networkx"

        g = nx.DiGraph()
        g.add_node("e001", _type="Enterprise", name="测试企业")

        stats = migrate_from_networkx(client, g)
        assert isinstance(stats, dict), "迁移结果应为 dict"
        assert "nodes_migrated" in stats
        assert "edges_migrated" in stats
        # networkx 模式下应当返回全 0
        assert stats["nodes_migrated"] == 0
        assert stats["edges_migrated"] == 0

    def test_b3_cypher_networkx_fallback(self):
        """Cypher 查询在 NetworkX 模式有对应实现 (find_competitors)"""
        from backend.ml.knowledge_graph.neo4j_client import Neo4jClient
        import networkx as nx

        g = nx.DiGraph()
        g.add_node("e001", _type="Enterprise", name="链客宝")
        g.add_node("e002", _type="Enterprise", name="竞对企业")
        g.add_edge("e001", "e002", _type="COMPETES_WITH")

        client = Neo4jClient(password=None)
        client.connect()
        client.set_fallback_graph(g)

        # find_competitors 在 NetworkX 模式下应返回结果
        result = client.find_competitors("e001")
        assert isinstance(result, (list, dict))
        # 即使降级, 应该能正常返回
        client.close()


# ===================================================================
# C. i18n 多语言 (4 个)
# ===================================================================

class TestI18n:
    """多语言翻译 / API / 变量替换 / Accept-Language 检测"""

    def test_c1_three_languages_exist(self):
        """zh / ko / en 三语翻译都存在 (backend i18n)"""
        from app.i18n.translations import TRANSLATIONS

        assert "zh" in TRANSLATIONS, "缺少中文 (zh)"
        assert "ko" in TRANSLATIONS, "缺少韩语 (ko)"
        assert "en" in TRANSLATIONS, "缺少英语 (en)"

        for lang_code in ("zh", "ko", "en"):
            t_dict = TRANSLATIONS[lang_code]
            assert len(t_dict) >= 30, \
                f"{lang_code} 翻译条数不足 30 (当前 {len(t_dict)})"

    def test_c2_translation_api_format(self):
        """翻译 API 端点返回正确格式"""
        from app.i18n.routes import i18n_bp
        assert i18n_bp is not None, "i18n 路由未加载"

        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(i18n_bp)
        client = TestClient(app)

        # GET /api/v1/i18n/translations
        resp = client.get("/api/v1/i18n/translations?lang=ko")
        assert resp.status_code == 200, f"status_code={resp.status_code}"
        data = resp.json()
        assert "lang" in data, "返回中缺少 lang"
        assert "translations" in data, "返回中缺少 translations"
        assert data["lang"] == "ko"
        assert isinstance(data["translations"], dict)

        # GET /api/v1/i18n/languages
        resp2 = client.get("/api/v1/i18n/languages")
        assert resp2.status_code == 200
        lang_data = resp2.json()
        assert "languages" in lang_data
        assert "default" in lang_data
        assert "zh" in lang_data["languages"]

    def test_c3_variable_substitution(self):
        """变量替换 {n} 正常工作"""
        from app.i18n.translations import Translator

        t = Translator("zh")
        result = t.t("form_min_length", n=10)
        assert "10" in result, f"变量替换失败: {result}"
        assert "个字符" in result

        # 韩语
        t2 = Translator("ko")
        result2 = t2.t("form_min_length", n=5)
        assert "5" in result2, f"韩语变量替换失败: {result2}"

        # 英语
        t3 = Translator("en")
        result3 = t3.t("form_min_length", n=8)
        assert "8" in result3, f"英语变量替换失败: {result3}"

    def test_c4_accept_language_detection(self):
        """Accept-Language 头能正确检测语言"""
        from app.i18n.middleware import _detect_language

        # 韩语优先
        lang = _detect_language("ko-KR,ko;q=0.9,en;q=0.8,zh;q=0.7")
        assert lang == "ko", f"应检测为 ko, 实际为 {lang}"

        # 英语优先
        lang = _detect_language("en;q=0.9,zh;q=0.8")
        assert lang == "en", f"应检测为 en, 实际为 {lang}"

        # 中文优先
        lang = _detect_language("zh;q=1.0,en;q=0.5")
        assert lang == "zh", f"应检测为 zh, 实际为 {lang}"

        # 空值回退
        lang = _detect_language(None)
        assert lang == "zh", f"空值应回退 zh, 实际为 {lang}"

        # 不支持的语种回退
        lang = _detect_language("ja;q=0.9,fr;q=0.8")
        assert lang == "zh", f"不支持语种应回退 zh, 实际为 {lang}"


# ===================================================================
# D. 跨境匹配 (3 个)
# ===================================================================

class TestCrossBorder:
    """CrossBorderMatcher 实例化 / 评分范围 / 语言检测"""

    def test_d1_matcher_instantiable(self):
        """CrossBorderMatcher 存在且可实例化"""
        from backend.ml.models.cross_border import CrossBorderMatcher

        matcher = CrossBorderMatcher()
        assert matcher is not None, "无法实例化 CrossBorderMatcher"
        assert hasattr(matcher, "match_across_languages"), \
            "缺少 match_across_languages 方法"
        assert hasattr(matcher, "match_with_translation"), \
            "缺少 match_with_translation 方法"

    def test_d2_cross_language_score_range(self):
        """跨语言评分在 0~1 范围"""
        from backend.ml.models.cross_border import CrossBorderMatcher, BgeM3Embedder
        import numpy as np

        embedder = BgeM3Embedder()
        matcher = CrossBorderMatcher(embedder=embedder)

        candidates = [
            {"enterprise_id": "ent_001", "name": "韩国贸易公司",
             "description": "从事中韩贸易", "lang": "ko"},
            {"enterprise_id": "ent_002", "name": "China Export Ltd",
             "description": "Global trading partner", "lang": "en"},
        ]

        results = matcher.match_across_languages(
            query_text="寻找跨境合作伙伴",
            lang="zh",
            candidates=candidates,
            top_k=5,
        )

        assert len(results) <= len(candidates)
        for r in results:
            assert 0.0 <= r.score <= 1.0, \
                f"评分 {r.score} 超出范围 [0, 1]"
            assert 0.0 <= r.match_score <= 1.0, \
                f"match_score {r.match_score} 超出范围 [0, 1]"

    def test_d3_language_detection(self):
        """语言检测函数 detect_language 正确识别 zh/ko/en"""
        from backend.ml.models.cross_border import detect_language

        # 中文
        assert detect_language("你好世界") == "zh"
        assert detect_language("今天天气很好") == "zh"

        # 韩语
        assert detect_language("안녕하세요") == "ko"
        assert detect_language("한국어 테스트입니다") == "ko"

        # 英语
        assert detect_language("Hello world") == "en"
        assert detect_language("This is a test") == "en"

        # 空值 → en
        assert detect_language("") == "en"
        assert detect_language(None) == "en"


# ===================================================================
# E. 特征工厂 (3 个)
# ===================================================================

class TestFeatureFactory:
    """FeatureFactory 维度 / 缓存 / 特征名称"""

    def test_e1_build_all_200plus_dim(self):
        """FeatureFactory.build_all 返回 200+ 维"""
        from backend.ml.features.feature_factory import FeatureFactory

        factory = FeatureFactory(enable_cache=False)

        # 提供模拟原始数据（各 Builder 的 raw 数据格式）
        extra_data = {
            "user": {
                "match_history": {"total": 10, "success": 5,
                                  "recent_7d": 3, "recent_30d": 8,
                                  "avg_response_time": 2.5,
                                  "most_common_type": 1, "most_common_type_count": 4},
                "feedback": {"like_count": 3, "dislike_count": 1, "ratings": [4.0, 5.0, 3.0]},
                "activity": {"login_count_7d": 5, "login_count_30d": 20,
                             "last_login_hours_ago": 2,
                             "login_freq_std": 0.5,
                             "browse_count_7d": 15, "browse_count_30d": 60,
                             "browse_avg_duration": 120.0, "browse_total_duration": 1800.0,
                             "session_count": 8, "session_avg_duration": 300.0,
                             "session_std_duration": 50.0},
                "social": {"contact_count": 15, "common_contact_count": 3,
                           "circle_density": 0.3, "circle_size": 20,
                           "group_count": 5, "active_group_count": 3,
                           "message_count_7d": 10, "message_count_30d": 40,
                           "avg_response_time": 1.5,
                           "following_count": 10, "follower_count": 5},
            },
            "enterprise": {
                "business": {"registered_capital": 1000000, "established_years": 5,
                             "shareholder_count": 3, "branch_count": 2,
                             "capital_change_count": 1, "legal_rep_age": 45,
                             "region_code": 310000, "company_type_code": 1,
                             "is_listed": 0},
                "credit": {"credit_score": 750, "admin_penalty_count": 0,
                           "judicial_risk_count": 0, "operation_risk_count": 1,
                           "ip_count": 5, "trademark_count": 3, "patent_count": 2,
                           "copyright_count": 1, "tax_credit_level": 1,
                           "env_credit_score": 80, "social_credit_code": "hash_001",
                           "litigation_count": 0, "execution_count": 0},
                "industry": {"industry_code": 1, "industry_category": 2,
                             "industry_chain_position": 3,
                             "upstream_supplier_count": 10,
                             "downstream_customer_count": 20,
                             "industry_competition_index": 0.5,
                             "industry_growth_rate": 0.15,
                             "industry_profit_margin": 0.2,
                             "cross_industry_count": 2,
                             "main_business_ratio": 0.8,
                             "industry_rank": 5, "supplier_concentration": 0.3},
                "scale": {"employee_count": 100, "estimated_revenue": 5000000,
                          "coverage_province_count": 3, "coverage_city_count": 5,
                          "coverage_country_count": 1, "asset_total": 8000000,
                          "estimated_revenue_per_employee": 50000},
                "extra": {"website_rank": 100000, "social_media_followers": 500,
                          "recruitment_count": 3, "certification_count": 2,
                          "qualification_count": 1, "annual_report_score": 85,
                          "govt_subsidy_amount": 50000, "tax_contribution": 200000,
                          "import_export_volume": 1000000, "investment_count": 2},
            },
            "graph": {
                "degree": {"degree": 10, "total_nodes": 100,
                           "cooperation_count": 5, "competition_count": 2,
                           "supplier_count": 3, "customer_count": 4,
                           "investor_count": 1, "investee_count": 0,
                           "in_degree": 6, "out_degree": 4},
                "centrality": {"pagerank": 0.05, "betweenness": 0.01,
                              "closeness": 0.3, "eigenvector": 0.1,
                              "harmonic": 0.4, "katz": 0.02,
                              "load": 0.01, "subgraph": 0.5,
                              "edge_betweenness": 0.001, "approx_closeness": 0.25},
                "community": {"community_id": 1, "community_size": 50,
                             "community_density": 0.2, "community_modularity": 0.6,
                             "num_communities": 5, "community_conductance": 0.1,
                             "community_cut_ratio": 0.05,
                             "community_normalized_cut": 0.08,
                             "community_triangle_count": 100,
                             "community_transitivity": 0.3,
                             "community_sq_clustering": 0.2,
                             "community_avg_degree": 8},
                "path": {"shortest_path_length": 2, "common_neighbors_count": 5,
                        "jaccard_similarity": 0.3, "adamic_adar_index": 1.5,
                        "resource_allocation_index": 0.5,
                        "preferential_attachment": 20, "total_paths_2hop": 10,
                        "total_paths_3hop": 30, "avg_path_length": 3.5,
                        "diameter": 8},
                "extra": {"clustering_coefficient": 0.4,
                         "square_clustering": 0.3, "core_number": 2,
                         "rich_club_coefficient": 0.1, "eccentricity": 5,
                         "pagerank_trust": 0.03, "random_walk_landing": 0.01,
                         "graph_hash_signature": 0.5},
            },
            "temporal": {
                "trend": {"daily_match_counts": [3, 5, 2, 4, 6, 3, 5] * 10},
                "seasonal": {"is_holiday": False},
                "decay": {"decay_weights_1d": 0.9, "decay_weights_3d": 0.7,
                         "decay_weights_7d": 0.5, "decay_weights_14d": 0.3,
                         "decay_weights_30d": 0.1, "decay_sums_7d": 15,
                         "decay_sums_30d": 50, "decay_avgs_7d": 2.0,
                         "decay_avgs_30d": 1.5, "decay_half_life": 5.0},
            },
            "text": {
                "embedding": [0.1 + i * 0.01 for i in range(10)],
                "tfidf": [f"word_{i}" for i in range(10)],
            },
        }
        fv = factory.build_all("user", "test_user_001",
                               extra_data=extra_data)

        assert fv is not None
        assert fv.dim >= 200, \
            f"特征维度不足 200: 实际 {fv.dim}"
        assert "user_match_total" in fv.features
        assert "ent_reg_capital_raw" in fv.features
        assert "graph_degree" in fv.features
        assert "temp_match_ma7" in fv.features
        assert "text_embedding_01" in fv.features

    def test_e2_feature_store_cache_hit_miss(self):
        """FeatureStore 缓存命中/未命中统计正常"""
        from backend.ml.features.feature_factory import (
            FeatureStore, FeatureVector,
        )

        store = FeatureStore(max_size=100)

        # 初始统计
        stats = store.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0

        # 未命中
        result = store.cache_get("nonexistent")
        assert result is None
        stats = store.stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 0

        # 写入并命中
        fv = FeatureVector(
            features={"test": 1.0},
            entity_type="user",
            entity_id="u001",
        )
        store.cache_set("test_key", fv)
        result = store.cache_get("test_key")
        assert result is not None
        stats = store.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

        # hit_rate
        assert stats["hit_rate"] == 0.5

    def test_e3_get_feature_names_non_empty(self):
        """get_feature_names 非空"""
        from backend.ml.features.feature_factory import FeatureFactory

        factory = FeatureFactory()

        all_names = factory.get_feature_names()
        assert len(all_names) >= 200, \
            f"全量特征名不足 200: {len(all_names)}"

        # 各类别非空
        for cat in ("user", "enterprise", "graph", "temporal", "text"):
            names = factory.get_feature_names(category=cat)
            assert len(names) > 0, f"{cat} 类别特征名为空"


# ===================================================================
# F. CI/CD (3 个)
# ===================================================================

class TestCICD:
    """Workflow YAML / rollback.sh / CI 门禁验证"""

    WORKFLOW_DIR = PROJECT_ROOT / ".github" / "workflows"
    ROLLBACK_SCRIPT = PROJECT_ROOT / "scripts" / "rollback.sh"

    def test_f1_three_workflow_files(self):
        """3 个 workflow yaml 文件存在且语法正确"""
        yaml_files = sorted(self.WORKFLOW_DIR.glob("*.yml"))
        assert len(yaml_files) >= 3, \
            f"workflow yaml 文件不足 3: 找到 {len(yaml_files)} 个"

        found_names = {f.name for f in yaml_files}
        assert "ci.yml" in found_names, "缺少 ci.yml"
        assert "deploy-staging.yml" in found_names, "缺少 deploy-staging.yml"
        assert "deploy-prod.yml" in found_names, "缺少 deploy-prod.yml"

        # 验证 yaml 可解析 (基本语法检查)
        for yf in yaml_files:
            content = yf.read_text(encoding="utf-8")
            assert "name:" in content, f"{yf.name} 缺少 name 字段"
            assert "on:" in content, f"{yf.name} 缺少 on 触发条件"
            assert "jobs:" in content or "jobs" in content, \
                f"{yf.name} 缺少 jobs"

    def test_f2_rollback_script_exists(self):
        """rollback.sh 存在且可执行"""
        assert self.ROLLBACK_SCRIPT.is_file(), \
            f"rollback.sh 不存在: {self.ROLLBACK_SCRIPT}"
        content = self.ROLLBACK_SCRIPT.read_text(encoding="utf-8")
        assert "#!/bin/bash" in content, "缺少 shebang"
        assert "docker-compose" in content or "docker" in content, \
            "脚本应含 docker 操作"

    def test_f3_ci_contains_test_gate(self):
        """CI 文件含 test 门禁步骤"""
        ci_file = self.WORKFLOW_DIR / "ci.yml"
        assert ci_file.is_file(), f"ci.yml 不存在: {ci_file}"
        content = ci_file.read_text(encoding="utf-8")

        # 验证有测试运行步骤
        assert "pytest" in content, "ci.yml 中缺少 pytest 执行"
        # 验证有门禁步骤 (Gate)
        assert "Gate" in content or "gate" in content or "门禁" in content, \
            "ci.yml 中缺少门禁 (Gate) 步骤"
        # 验证有覆盖率门禁
        assert "coverage" in content.lower(), "ci.yml 中缺少覆盖率检查"


# ===================================================================
# G. 全面回归 (6 个)
# ===================================================================

# P0: 最核心模块 — 启动 / 路由 / 基础模型
P0_MODULES = [
    "backend.app.main",
    "app.i18n",
    "app.i18n.translations",
    "app.i18n.middleware",
    "app.i18n.routes",
    "backend.ml.knowledge_graph",
    "backend.ml.knowledge_graph.neo4j_client",
    "backend.ml.knowledge_graph.builder",
]

# P1: 重要模块 — ML 模型 / 特征 / 匹配
P1_MODULES = [
    "backend.ml.models",
    "backend.ml.models.user_tower",
    "backend.ml.models.enterprise_tower",
    "backend.ml.models.behavior_tower",
    "backend.ml.models.tower_ensemble",
    "backend.ml.models.cross_border",
    "backend.ml.features.feature_factory",
    "backend.ml.features.embed_scheduler",
    "backend.ml.pipelines",
    "backend.ml.pipelines.minute_indexer",
    "backend.ml.pipelines.realtime_sync",
    "backend.ml.knowledge_graph.schema",
]

# P2: 业务模块 — 路由 / 服务 / pipelines
P2_MODULES = [
    "app.routers.matching_engine",
    "app.routers.onboarding",
    "app.routers.auth",
    "app.routers.business_card",
    "app.routers.brochure_bridge",
    "app.routers.membership",
    "app.routers.feedback",
    "app.routers.hypothesis_gate",
    "app.routers.unit_economics",
    "app.routers.sales_script",
    "app.routers.learning_center",
    "app.routers.retention_insights",
    "app.routers.retro_board",
    "backend.features.embedding_service",
    "backend.features.embedding_cache",
    "backend.features.retrieval_pipeline",
    "backend.features.mmr_diversity",
    "backend.features.enterprise_data",
    "backend.ml.evaluation.champion_challenger",
    "backend.ml.evaluation.analysis_reporter",
    "backend.ml.online_learning",
]

# P3: 工具 / 脚本模块
P3_MODULES = [
    "backend.scripts.geo_cron",
    "backend.scripts.health_check",
    "backend.scripts.health_check_docker",
    "backend.scripts.monitor_setup",
    "backend.scripts.seo_optimizer",
    "backend.scripts.batch_embed",
    "backend.ml.online_learning_test",
    "app.services.onboarding_service",
    "app.services.feedback_service",
    "backend.features.enterprise_data.pipeline_orchestrator",
    "backend.features.enterprise_data.pipeline_scheduler",
    "backend.features.enterprise_data.merger",
    "backend.features.enterprise_data.qichacha_adapter",
    "backend.features.enterprise_data.tianyancha_adapter",
    "backend.features.enterprise_data.test_pipeline",
]


def _import_module(name: str) -> Any:
    """尝试导入模块, 失败时抛出 ImportError"""
    return __import__(name, fromlist=[""])


class TestFullRegression:
    """全面回归 — 模块可导入性验证"""

    @pytest.mark.parametrize("module_name", P0_MODULES)
    def test_g1_p0_modules_importable(self, module_name):
        """所有 P0 核心模块可导入"""
        mod = _import_module(module_name)
        assert mod is not None, f"P0 模块导入失败: {module_name}"

    @pytest.mark.parametrize("module_name", P1_MODULES)
    def test_g2_p1_modules_importable(self, module_name):
        """所有 P1 核心模块可导入"""
        mod = _import_module(module_name)
        assert mod is not None, f"P1 模块导入失败: {module_name}"

    @pytest.mark.parametrize("module_name", P2_MODULES)
    def test_g3_p2_modules_importable(self, module_name):
        """所有 P2 核心模块可导入"""
        mod = _import_module(module_name)
        assert mod is not None, f"P2 模块导入失败: {module_name}"

    @pytest.mark.parametrize("module_name", P3_MODULES)
    def test_g4_p3_modules_importable(self, module_name):
        """所有 P3 核心模块可导入"""
        mod = _import_module(module_name)
        assert mod is not None, f"P3 模块导入失败: {module_name}"

    def test_g5_new_vs_old_no_conflict(self):
        """新功能与旧功能不冲突 (P0 + P1 + P2 + P3 共存无 ImportError)"""
        for m in P0_MODULES + P1_MODULES + P2_MODULES + P3_MODULES:
            try:
                _import_module(m)
            except ImportError as e:
                pytest.fail(f"导入 {m} 时冲突: {e}")

    def test_g6_overall_statistics(self):
        """整体数量统计: 文件数 / 测试数"""
        # 统计测试文件数
        test_files = list(TESTS_ROOT.rglob("test_*.py"))
        regression_files = list(REGRESSION_ROOT.rglob("test_*.py"))

        print(f"\n{'=' * 60}")
        print(f"📊 P3 全量回归统计")
        print(f"{'=' * 60}")
        print(f"  测试目录:         {TESTS_ROOT}")
        print(f"  总测试文件数:     {len(test_files)}")
        print(f"  当前回归测试文件: {len(regression_files)}")
        print(f"  P0 模块数:        {len(P0_MODULES)}")
        print(f"  P1 模块数:        {len(P1_MODULES)}")
        print(f"  P2 模块数:        {len(P2_MODULES)}")
        print(f"  P3 模块数:        {len(P3_MODULES)}")
        print(f"  可导入模块总数:   {len(P0_MODULES) + len(P1_MODULES) + len(P2_MODULES) + len(P3_MODULES)}")

        # 统计自身测试函数数量 (不含 parametrize 展开)
        import inspect
        test_methods = []
        for name, obj in inspect.getmembers(self.__class__, inspect.isfunction):
            if name.startswith("test_"):
                test_methods.append(name)
        # 以当前类统计太粗略, 我们在模块级别统计
        print(f"  本文件测试函数:   {count_tests_in_this_file()}")

        assert len(test_files) >= 5, f"测试文件不足 5 个: 共 {len(test_files)}"
        assert len(regression_files) >= 1, "回归测试文件不足 1 个"


def count_tests_in_this_file() -> int:
    """统计本文件中所有 test_ 开头的函数和 parametrize 展开数"""
    import inspect
    import pytest

    # 静态统计
    test_funcs = []
    # 简单的模式匹配统计
    with open(__file__, encoding="utf-8") as f:
        content = f.read()

    # 统计 def test_ 行数
    func_count = len(re.findall(r"^\s+def (test_\w+)", content, re.MULTILINE))
    # 统计 parametrize 数量
    param_sets = len(re.findall(r"@pytest\.mark\.parametrize", content))
    # 粗略估计: 每个 parametrize 展开为多个测试
    # 但准确的计算需要运行, 这里只返回函数定义数
    return func_count


# ===================================================================
# 手动聚合所有 TestClasses 以方便 pytest 收集
# ===================================================================
# 注: pytest 会自动收集所有 Test* 类,
# 以上类均可被 pytest 发现.


if __name__ == "__main__":
    # 直接运行时执行统计
    print(f"P3 回归测试文件: {__file__}")
    print(f"测试函数数量(定义): {count_tests_in_this_file()}")
    print("请使用: pytest tests/regression/ -v 运行")
