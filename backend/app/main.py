"""
链客宝 Backend — FastAPI 应用入口
======================================
服务入口文件，注册所有路由模块。

规则：纯新增，不修改现有业务逻辑
路由注册原则：
  - 所有 router 通过 app.include_router() 注册
  - brochure_bridge 同时注册 /api/brochures/（复数）别名路由
    以满足小程序 brochure/index.js 的调用路径
"""

import os
import sys
from pathlib import Path

from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ── 确保项目根目录在 sys.path ────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── 结构化日志初始化 (优先执行，确保所有模块继承统一配置) ─────────
from app.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger("chainke.boot")

# ── Sentry 错误追踪初始化 ─────────────────────────────────────────
from app.sentry import init_sentry
init_sentry()

# ===================================================================
# FastAPI 应用实例
# ===================================================================

app = FastAPI(
    title="链客宝 API",
    description="链客宝 — 企业家供需匹配平台后端服务",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3099",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:5136",
        "http://liankebao.top",
        "https://liankebao.top",
        "http://www.liankebao.top",
        "https://www.liankebao.top",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── i18n 多语言中间件 ────────────────────────────────────────────
from app.i18n import I18nMiddleware
app.add_middleware(I18nMiddleware)

# ── 监控/可观测中间件 ────────────────────────────────────────────
from app.middleware import MetricsMiddleware, LoggingMiddleware, AuthMiddleware, SentryMiddleware, JsonLdMiddleware
app.add_middleware(MetricsMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(SentryMiddleware)

# ── JSON-LD 结构化数据注入 ──────────────────────────────────────
app.add_middleware(JsonLdMiddleware)
logger.info("[Boot] JsonLdMiddleware 已注册 — 自动注入 WebSite/Organization/Product Schema")

# ===================================================================
# 路由注册
# ===================================================================

# ── M1 基础能力 ──────────────────────────────────────────────────
from app.routers.business_card import router as business_card_router
from app.routers.brochure_bridge import router as brochure_bridge_router
from app.routers.auth import router as auth_router

# ── i18n 多语言路由 ────────────────────────────────────────────
from app.i18n import i18n_bp
app.include_router(i18n_bp)

# ── i18n URL 前缀路由 (多语言独立URL支持) ─────────────────────
from app.routers.i18n_router import router as i18n_router
app.include_router(i18n_router)
logger.info("[Boot] i18n_router 已注册 — 支持 /en/ /ko/ 独立URL前缀")

app.include_router(business_card_router)
app.include_router(brochure_bridge_router)
app.include_router(auth_router)

# ── Feature Flags 功能开关 ──────────────────────────────────────
try:
    from app.features import feature_flags_bp
    if feature_flags_bp is not None:
        app.include_router(feature_flags_bp)
        logger.info("[Boot] feature_flags 已注册")
except ImportError:
    logger.info("[Boot] feature_flags 未安装，跳过")

# ── 冷启动引导 ─────────────────────────────────────────────
from app.routers.onboarding import router as onboarding_router
app.include_router(onboarding_router)

# ── M2 假设验证门禁 ─────────────────────────────────────────────
try:
    from app.routers.hypothesis_gate import router as hypothesis_router
    if hypothesis_router is not None:
        app.include_router(hypothesis_router)
        logger.info("[Boot] hypothesis_gate 已注册")
except ImportError:
    logger.info("[Boot] hypothesis_gate 未安装，跳过")

# ── M3 学习中心 ─────────────────────────────────────────────────
try:
    from app.routers.learning_center import router as learning_router
    if learning_router is not None:
        app.include_router(learning_router)
        logger.info("[Boot] learning_center 已注册")
except ImportError:
    logger.info("[Boot] learning_center 未安装，跳过")

# ── M4 留存洞察 ─────────────────────────────────────────────────
try:
    from app.routers.retention_insights import router as retention_router
    if retention_router is not None:
        app.include_router(retention_router)
        logger.info("[Boot] retention_insights 已注册")
except ImportError:
    logger.info("[Boot] retention_insights 未安装，跳过")

# ── M5 回顾看板 ─────────────────────────────────────────────────
try:
    from app.routers.retro_board import router as retro_router
    if retro_router is not None:
        app.include_router(retro_router)
        logger.info("[Boot] retro_board 已注册")
except ImportError:
    logger.info("[Boot] retro_board 未安装，跳过")

# ── M6 单位经济 ─────────────────────────────────────────────────
try:
    from app.routers.unit_economics import router as unit_econ_router
    if unit_econ_router is not None:
        app.include_router(unit_econ_router)
        logger.info("[Boot] unit_economics 已注册")
except ImportError:
    logger.info("[Boot] unit_economics 未安装，跳过")

# ── M7 匹配引擎 ────────────────────────────────────────────────
try:
    from app.routers.matching_engine import router as matching_router
    if matching_router is not None:
        app.include_router(matching_router)
        logger.info("[Boot] matching_engine 已注册")
except ImportError:
    logger.info("[Boot] matching_engine 未安装，跳过 — 可使用 /d/链客宝/backend/ 的完整匹配引擎")

# ── M7b 多样性匹配（MMR） ───────────────────────────────────
try:
    from app.routers.matching_engine import v1_router as diverse_router
    if diverse_router is not None:
        app.include_router(diverse_router)
        logger.info("[Boot] diverse_matching (MMR) 已注册")
except ImportError:
    logger.info("[Boot] diverse_matching (MMR) 未安装 — v1_router 不存在")

# ── M8 会员与额度 ─────────────────────────────────────────────
try:
    from app.routers.membership import router as membership_router
    if membership_router is not None:
        app.include_router(membership_router)
        logger.info("[Boot] membership 已注册")
except ImportError:
    logger.info("[Boot] membership 未安装，跳过 — 可使用 /d/链客宝/backend/ 的完整会员模块")

# ── 用户反馈采集管道 ────────────────────────────────────────────
try:
    from app.routers.feedback import router as feedback_router
    if feedback_router is not None:
        app.include_router(feedback_router)
        logger.info("[Boot] feedback 已注册")
except ImportError:
    logger.info("[Boot] feedback 未安装，跳过")

# ── ABACC 销售话术 ──────────────────────────────────────────────
try:
    from app.routers.sales_script import router as sales_script_router
    if sales_script_router is not None:
        app.include_router(sales_script_router)
        logger.info("[Boot] sales_script 已注册")
except ImportError:
    logger.info("[Boot] sales_script 未安装，跳过")

# ── IM Bot 通知模块 (飞书/钉钉) ──────────────────────────────────
try:
    from app.routers.notification_router import router as notification_router
    if notification_router is not None:
        app.include_router(notification_router)
        logger.info("[Boot] notification_router 已注册 → /api/notifications/bot/*")
except ImportError:
    logger.info("[Boot] notification_router 未安装，跳过")

# ── AI 对话助手 ──────────────────────────────────────────────────
try:
    from app.routers.chat import router as chat_router
    if chat_router is not None:
        app.include_router(chat_router)
        logger.info("[Boot] chat (AI对话) 已注册 → POST /api/v1/chat")
except ImportError:
    logger.info("[Boot] chat 未安装，跳过")

# ── 审计日志系统 ────────────────────────────────────────────────
try:
    from app.routers.audit import router as audit_router
    if audit_router is not None:
        app.include_router(audit_router)
        logger.info("[Boot] audit 已注册")
except ImportError:
    logger.info("[Boot] audit 未安装，跳过")

# ── M9 合规审查 ──────────────────────────────────────────────────
from app.routers import compliance
app.include_router(compliance.router)
logger.info("[Boot] compliance 已注册")

# ── 开发者门户 ──────────────────────────────────────────────────
try:
    from app.routers.developer_portal import router as developer_portal_router
    if developer_portal_router is not None:
        app.include_router(developer_portal_router)
        logger.info("[Boot] developer_portal 已注册 → /api/developer/*")
except ImportError as e:
    logger.info("[Boot] developer_portal 未安装，跳过 (%s)", e)

# ── API Key 认证中间件 ──────────────────────────────────────────
try:
    from app.middleware.api_key_auth import api_key_middleware
    app.middleware("http")(api_key_middleware)
    logger.info("[Boot] api_key_middleware 已注册")
except ImportError:
    logger.info("[Boot] api_key_middleware 未安装，跳过")

# ── 文件存储服务 ────────────────────────────────────────────────
try:
    from app.routers.storage_router import router as storage_router
    if storage_router is not None:
        app.include_router(storage_router)
        logger.info("[Boot] storage_router 已注册 → /api/storage/*")
except ImportError:
    logger.info("[Boot] storage_router 未安装，跳过")

# ── 通知服务 ──────────────────────────────────────────────────────
try:
    from app.routers.notification_router import router as notification_router
    if notification_router is not None:
        app.include_router(notification_router)
        logger.info("[Boot] notification 已注册")
except ImportError:
    logger.info("[Boot] notification 未安装，跳过")

# ── 微信 JS-SDK 集成 ──────────────────────────────────────────────
try:
    from app.routers.wechat_router import router as wechat_router
    if wechat_router is not None:
        app.include_router(wechat_router)
        logger.info("[Boot] wechat_router 已注册 → /api/wechat/*")
except ImportError as e:
    logger.info("[Boot] wechat_router 未安装，跳过 (%s)", e)

# ── 支付宝支付 ─────────────────────────────────────────────────────
try:
    from app.routers.alipay import router as alipay_router
    if alipay_router is not None:
        app.include_router(alipay_router)
        logger.info("[Boot] alipay_router 已注册 → /api/payment/alipay/*")
except ImportError as e:
    logger.info("[Boot] alipay_router 未安装，跳过 (%s)", e)

# ── 充值模块 ───────────────────────────────────────────────────────
try:
    from app.routers.recharge import router as recharge_router
    if recharge_router is not None:
        app.include_router(recharge_router)
        logger.info("[Boot] recharge_router 已注册 → /api/recharge/*")
except ImportError as e:
    logger.info("[Boot] recharge_router 未安装，跳过 (%s)", e)

# ── 信任评分系统 ──────────────────────────────────────────────────
try:
    from app.routers.trust_score import router as trust_score_router
    if trust_score_router is not None:
        app.include_router(trust_score_router)
        logger.info("[Boot] trust_score 已注册 → /api/trust/*")
except ImportError as e:
    logger.info("[Boot] trust_score 未安装，跳过 (%s)", e)

# ── 信任引擎增强API（适配旧版 trust.py 遗漏端点） ──────────────
try:
    from app.routers.trust_engine_api import router as trust_engine_api_router
    if trust_engine_api_router is not None:
        app.include_router(trust_engine_api_router)
        logger.info("[Boot] trust_engine_api 已注册 → /api/trust/* (增强端点)")
except ImportError as e:
    logger.info("[Boot] trust_engine_api 未安装，跳过 (%s)", e)

# ── 订单管理模块 ──────────────────────────────────────────────────
try:
    from app.routers.orders import router as orders_router
    if orders_router is not None:
        app.include_router(orders_router)
        logger.info("[Boot] orders 已注册 → /api/orders/*")
except ImportError as e:
    logger.info("[Boot] orders 未安装，跳过 (%s)", e)

# ── 产品管理模块 ──────────────────────────────────────────────────
try:
    from app.routers.products import router as products_router
    if products_router is not None:
        app.include_router(products_router)
        logger.info("[Boot] products 已注册 → /api/products/*")
except ImportError as e:
    logger.info("[Boot] products 未安装，跳过 (%s)", e)

# ── 推广分润模块 ──────────────────────────────────────────────────
try:
    from app.routers.promoter import router as promoter_router
    if promoter_router is not None:
        app.include_router(promoter_router)
        logger.info("[Boot] promoter 已注册 → /api/promoter/*")
except ImportError as e:
    logger.info("[Boot] promoter 未安装，跳过 (%s)", e)

# ── 联系人管理模块 ────────────────────────────────────────────────
try:
    from app.routers.contacts import router as contacts_router
    if contacts_router is not None:
        app.include_router(contacts_router)
        logger.info("[Boot] contacts 已注册 → /api/contacts/*")
except ImportError as e:
    logger.info("[Boot] contacts 未安装，跳过 (%s)", e)

# ── 联系人活动时间线模块 ──────────────────────────────────────────
try:
    from app.routers.activities import router as activities_router
    if activities_router is not None:
        app.include_router(activities_router)
        logger.info("[Boot] activities 已注册 → /api/contacts/{contact_id}/activities/*")
except ImportError as e:
    logger.info("[Boot] activities 未安装，跳过 (%s)", e)

# ── 商机/需求管理模块 ────────────────────────────────────────────
try:
    from app.routers.needs import router as needs_router
    if needs_router is not None:
        app.include_router(needs_router)
        logger.info("[Boot] needs 已注册 → /api/needs/*")
except ImportError as e:
    logger.info("[Boot] needs 未安装，跳过 (%s)", e)

# ── 外部集成模块（迁移自旧版链客宝 backend/modules/external/） ────
try:
    from app.routers.external import router as external_router
    if external_router is not None:
        app.include_router(external_router)
        logger.info("[Boot] external 已注册 → /api/external/*")
except ImportError as e:
    logger.info("[Boot] external 未安装，跳过 (%s)", e)

# ── SEO 基础路由 (sitemap.xml / robots.txt / JSON-LD schema) ──────
from app.routers.seo import router as seo_router
app.include_router(seo_router)
try:
    from app.routers.subscription import router as subscription_router
    app.include_router(subscription_router)
    print("[Main] 订阅路由已注册")
except Exception as e:
    print(f"[Main] 订阅路由注册失败: {e}")
try:
    from app.routers.kg_coldstart import router as kg_coldstart_router
    app.include_router(kg_coldstart_router)
    print("[Main] 知识图谱冷启动路由已注册")
except Exception as e:
    print(f"[Main] 知识图谱冷启动路由注册失败: {e}")
logger.info("[Boot] seo_router 已注册 → /sitemap.xml, /robots.txt, /api/seo/schema")

# ── SSR 预渲染路由 (Puppeteer 动态渲染代理) ──────────────────────
try:
    from app.routers.ssr_router import router as ssr_router
    app.include_router(ssr_router)
    logger.info("[Boot] ssr_router 已注册 → /_ssr/render, /_ssr/health")
except ImportError as e:
    logger.info("[Boot] ssr_router 未加载，跳过 (%s)", e)

# ── 别名路由：/api/brochures/（复数） → brochure_bridge ──────────
# 小程序 brochure/index.js 调用的是 /api/brochures/{userId}（复数）
# brochure_bridge_router 内已包含 GET /api/brochures/{user_id}，
# 此处额外注册一个显式别名路由器以确保兼容性
brochures_alias = APIRouter(prefix="/api/brochures")

# 将 brochure_bridge 的复数路径再暴露一次（已在 bridge 内部注册，
# 此处保留以应对未来可能的路径拆分需求）
logger.info("[Boot] 别名路由就绪: /api/brochures/{user_id} → brochure_bridge")

# ===================================================================
# 模型初始化
# ===================================================================

try:
    from app.models import init_models
    init_models()
except Exception as e:
    logger.error("[Boot] 数据库表初始化失败: %s", e)

# ===================================================================
# 健康检查
# ===================================================================


@app.get("/api/health", tags=["健康检查"])
async def health_check():
    """健康检查端点"""
    return {
        "status": "ok",
        "service": "链客宝 Backend API",
        "version": "1.0.0",
    }


@app.get("/health", tags=["健康检查"])
async def health_check_short():
    return {"status": "ok"}


# ── Sentry 错误报告测试端点 ─────────────────────────────────────


@app.post("/api/health/error-report", tags=["健康检查"])
async def error_report(request: Request):
    """
    错误报告测试端点。

    用于验证 Sentry 集成是否正常工作。
    提交一个测试异常到 Sentry。

    请求体 (JSON):
        {
            "message": "自定义错误描述（可选）",
            "level": "error"           # info / warning / error / fatal
        }
    """
    from app.sentry import sentry_is_active
    import logging

    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    message = body.get("message", "前端主动上报的错误")
    level = body.get("level", "error")

    logger = logging.getLogger("chainke.sentry")

    if sentry_is_active():
        import sentry_sdk
        sentry_sdk.set_level(level)
        sentry_sdk.capture_message(message, level=level)
        logger.info("[ErrorReport] Sentry 已上报: level=%s, message=%s", level, message)
        return {
            "status": "reported",
            "message": "错误已上报到 Sentry",
            "sentry_active": True,
        }
    else:
        logger.info("[ErrorReport] Sentry 未激活，本地记录: level=%s, message=%s", level, message)
        return {
            "status": "logged",
            "message": "Sentry 未激活，错误已在本地记录",
            "sentry_active": False,
        }


# ===================================================================
# 启动入口
# ===================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8001"))
    logger.info("链客宝后端服务启动 → http://0.0.0.0:%s", port)
    logger.info("电子画册 API: GET /api/brochure/{user_id}")
    logger.info("电子画册 API: GET /api/brochures/{user_id} (小程序别名)")
    logger.info("名片 API:     GET /api/business-card/cards")
    logger.info("生成名片 API:  POST /api/business-card/generate-card")

# ── 注册端点（main.py 层直连注册，绕开 router 注册问题）─────────────
@app.post("/api/auth/register")
async def register_main(req: dict):
    """用户注册"""
    from app.database import SessionLocal as _SessionLocal
    from app.models import User as _User, hash_password as _hash
    import jwt as _jwt
    import datetime as _dt
    
    db = _SessionLocal()
    try:
        username = req.get("username", "").strip()
        if not username:
            return {"detail": "用户名不能为空"}, 400
        password = req.get("password", "")
        
        existing = db.query(_User).filter(
            _User.username == username,
            _User.is_deleted == False,
        ).first()
        if existing:
            return {"detail": "用户名已存在"}, 400
        
        user = _User(
            username=username,
            password_hash=_hash(password),
            name=req.get("name", ""),
            phone=req.get("phone", ""),
            company=req.get("company", ""),
            position=req.get("position", ""),
            role="user",
            avatar=f"https://api.dicebear.com/7.x/avataaars/svg?seed={username}",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        now = _dt.datetime.now(_dt.timezone.utc)
        token = _jwt.encode({
            "sub": user.username, "user_id": user.id,
            "role": user.role, "iat": now,
            "exp": now + _dt.timedelta(hours=24),
        }, os.getenv("JWT_SECRET", "chainke-dev-secret-key"), algorithm="HS256")
        
        return {"token": token, "user": user.to_dict(), "message": "注册成功"}
    except Exception as e:
        return {"detail": str(e)}, 500
    finally:
        db.close()

# ── 注册端点 END ──────────────────────────────────────────────────


    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
