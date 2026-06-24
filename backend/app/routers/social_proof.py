"""
链客宝社交证明 API 路由

提供社交证明（Social Proof）相关的数据端点：
  - GET  /api/social-proof/logos    — 合作企业Logo列表
  - POST /api/social-proof/logos    — 新增合作企业Logo
  - GET  /api/social-proof/cases    — 成功案例列表
  - POST /api/social-proof/cases    — 新增成功案例
  - GET  /api/social-proof/stats    — 平台统计数据（累计匹配数/交易数/入驻企业数）

数据默认使用内存存储（启动时填充示例数据），未来可迁移至数据库。
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/social-proof", tags=["社交证明"])

# ============================================================
# 数据模型
# ============================================================


class PartnerLogo(BaseModel):
    """合作企业Logo"""

    id: str = ""
    name: str = Field(..., min_length=1, max_length=100, description="企业名称")
    logo_url: str = Field(..., max_length=500, description="Logo图片URL")
    website: str | None = Field(None, max_length=500, description="企业官网")
    category: str = Field("", max_length=50, description="行业分类")
    sort_order: int = Field(0, ge=0, description="排序权重（越大越靠前）")
    created_at: str = ""


class SuccessCase(BaseModel):
    """成功案例"""

    id: str = ""
    company: str = Field(..., min_length=1, max_length=100, description="企业名称")
    title: str = Field(..., min_length=1, max_length=200, description="案例标题")
    description: str = Field(..., min_length=1, max_length=500, description="案例描述")
    icon: str = Field("🏢", max_length=10, description="展示图标emoji")
    metrics: dict[str, Any] = Field(default_factory=dict, description="关键指标（如 {'提升': '200%'}）")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    sort_order: int = Field(0, ge=0, description="排序权重")
    created_at: str = ""


class PlatformStats(BaseModel):
    """平台统计数据"""

    total_matches: int = Field(..., ge=0, description="累计匹配数")
    total_transactions: int = Field(..., ge=0, description="累计交易数")
    total_enterprises: int = Field(..., ge=0, description="入驻企业数")
    satisfaction_rate: float = Field(..., ge=0, le=100, description="满意度(%)")
    updated_at: str = ""


# ============================================================
# 请求模型
# ============================================================


class PartnerLogoCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    logo_url: str = Field(..., max_length=500)
    website: str | None = None
    category: str = ""
    sort_order: int = 0


class SuccessCaseCreate(BaseModel):
    company: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=500)
    icon: str = "🏢"
    metrics: dict[str, Any] = {}
    tags: list[str] = []
    sort_order: int = 0


# ============================================================
# 内存存储（启动时填充示例数据）
# ============================================================

_logos: list[PartnerLogo] = []
_cases: list[SuccessCase] = []

SEED_LOGOS = [
    {
        "name": "华为云",
        "logo_url": "/static/logos/huawei-cloud.svg",
        "website": "https://huaweicloud.com",
        "category": "云计算",
        "sort_order": 100,
    },
    {
        "name": "腾讯云",
        "logo_url": "/static/logos/tencent-cloud.svg",
        "website": "https://cloud.tencent.com",
        "category": "云计算",
        "sort_order": 99,
    },
    {
        "name": "阿里巴巴",
        "logo_url": "/static/logos/alibaba.svg",
        "website": "https://alibaba.com",
        "category": "电商",
        "sort_order": 98,
    },
    {
        "name": "百度AI",
        "logo_url": "/static/logos/baidu-ai.svg",
        "website": "https://ai.baidu.com",
        "category": "人工智能",
        "sort_order": 97,
    },
    {
        "name": "字节跳动",
        "logo_url": "/static/logos/bytedance.svg",
        "website": "https://bytedance.com",
        "category": "科技",
        "sort_order": 96,
    },
    {
        "name": "京东云",
        "logo_url": "/static/logos/jd-cloud.svg",
        "website": "https://jdcloud.com",
        "category": "云计算",
        "sort_order": 95,
    },
    {
        "name": "网易",
        "logo_url": "/static/logos/netease.svg",
        "website": "https://netease.com",
        "category": "互联网",
        "sort_order": 94,
    },
    {
        "name": "美团",
        "logo_url": "/static/logos/meituan.svg",
        "website": "https://meituan.com",
        "category": "生活服务",
        "sort_order": 93,
    },
    {
        "name": "小米",
        "logo_url": "/static/logos/xiaomi.svg",
        "website": "https://xiaomi.com",
        "category": "智能硬件",
        "sort_order": 92,
    },
    {
        "name": "360",
        "logo_url": "/static/logos/360.svg",
        "website": "https://360.cn",
        "category": "安全",
        "sort_order": 91,
    },
    {
        "name": "用友",
        "logo_url": "/static/logos/yonyou.svg",
        "website": "https://yonyou.com",
        "category": "企业服务",
        "sort_order": 90,
    },
    {
        "name": "金蝶",
        "logo_url": "/static/logos/kingdee.svg",
        "website": "https://kingdee.com",
        "category": "企业服务",
        "sort_order": 89,
    },
    {
        "name": "浪潮",
        "logo_url": "/static/logos/inspur.svg",
        "website": "https://inspur.com",
        "category": "IT基础设施",
        "sort_order": 88,
    },
    {
        "name": "中软国际",
        "logo_url": "/static/logos/chinasoft.svg",
        "website": "https://chinasoft.com",
        "category": "软件服务",
        "sort_order": 87,
    },
    {
        "name": "旷视科技",
        "logo_url": "/static/logos/megvii.svg",
        "website": "https://megvii.com",
        "category": "人工智能",
        "sort_order": 86,
    },
    {
        "name": "商汤科技",
        "logo_url": "/static/logos/sensetime.svg",
        "website": "https://sensetime.com",
        "category": "人工智能",
        "sort_order": 85,
    },
    {
        "name": "科大讯飞",
        "logo_url": "/static/logos/iflytek.svg",
        "website": "https://iflytek.com",
        "category": "人工智能",
        "sort_order": 84,
    },
    {
        "name": "海康威视",
        "logo_url": "/static/logos/hikvision.svg",
        "website": "https://hikvision.com",
        "category": "安防",
        "sort_order": 83,
    },
]

SEED_CASES = [
    {
        "company": "某科技公司",
        "title": "AI营销系统渠道拓展",
        "description": "通过链客宝AI匹配引擎，精准对接3家省级渠道商，月销售额提升200%，合作首季度即实现盈利。",
        "icon": "🏢",
        "metrics": {"销售额提升": "200%", "渠道商数": "3家"},
        "tags": ["AI营销", "渠道拓展"],
        "sort_order": 100,
    },
    {
        "company": "某制造企业",
        "title": "供应链需求48小时响应",
        "description": "发布供应链管理系统需求后48小时内收到15家供应商报价，最终与3家优质供应商达成长期合作，采购成本降低15%。",
        "icon": "🏭",
        "metrics": {"响应时间": "48小时", "成本降低": "15%"},
        "tags": ["供应链", "采购"],
        "sort_order": 99,
    },
    {
        "company": "某贸易公司",
        "title": "AI数字名片获客革命",
        "description": "使用链客宝AI数字名片替代传统纸质名片，客户转化率提升40%，名片打开率高达78%，累计获客200+。",
        "icon": "💼",
        "metrics": {"转化率提升": "40%", "累计获客": "200+"},
        "tags": ["数字名片", "获客"],
        "sort_order": 98,
    },
    {
        "company": "某连锁品牌",
        "title": "全国城市合伙人招募",
        "description": "通过链客宝平台发布合伙人招募计划，3个月内成功招募6个省份的城市合伙人，门店覆盖扩展至15个城市。",
        "icon": "🏪",
        "metrics": {"省份覆盖": "6个", "城市覆盖": "15个"},
        "tags": ["合伙人", "连锁"],
        "sort_order": 97,
    },
    {
        "company": "某科技团队",
        "title": "新品分销网络搭建",
        "description": "新产品上线首周通过链客宝推广中心获得300+分销商，首月销售额突破500万，成为行业现象级产品。",
        "icon": "📡",
        "metrics": {"分销商数": "300+", "首月销售额": "500万"},
        "tags": ["分销", "新品上市"],
        "sort_order": 96,
    },
    {
        "company": "某教育机构",
        "title": "精准招生获客方案",
        "description": "利用链客宝供需匹配系统，精准触达有培训需求的企业客户，单月获客成本降低60%，招生人数增长180%。",
        "icon": "🎓",
        "metrics": {"获客成本降低": "60%", "招生增长": "180%"},
        "tags": ["教育", "招生"],
        "sort_order": 95,
    },
    {
        "company": "某金融服务企业",
        "title": "企业信用评估加速",
        "description": "接入链客宝信任体系，企业资质认证时间从7天缩短至2小时，客户信任度提升35%，业务转化率提高50%。",
        "icon": "💳",
        "metrics": {"认证时间": "2小时", "信任度提升": "35%"},
        "tags": ["金融", "信用"],
        "sort_order": 94,
    },
    {
        "company": "某医疗科技公司",
        "title": "B端渠道快速突破",
        "description": "通过链客宝平台找到5家区域代理商，3个月内完成全国重点城市布局，销售额环比增长300%。",
        "icon": "🏥",
        "metrics": {"代理商家数": "5家", "销售额增长": "300%"},
        "tags": ["医疗", "渠道"],
        "sort_order": 93,
    },
]


def _seed_data():
    """初始化种子数据（内存存储）"""
    global _logos, _cases
    now = datetime.now(UTC).isoformat()

    _logos = []
    for i, item in enumerate(SEED_LOGOS):
        _logos.append(
            PartnerLogo(
                id=str(uuid.uuid4()),
                created_at=now,
                **item,
            )
        )

    _cases = []
    for i, item in enumerate(SEED_CASES):
        _cases.append(
            SuccessCase(
                id=str(uuid.uuid4()),
                created_at=now,
                **item,
            )
        )

    logger.info(f"社交证明种子数据已加载: {len(_logos)} logos, {len(_cases)} cases")


# 模块加载时初始化种子数据
_seed_data()


# ============================================================
# API 端点
# ============================================================

# ---------- 合作企业 Logo ----------


@router.get("/logos", summary="获取合作企业Logo列表")
def get_logos(category: str | None = None):
    """获取所有合作企业Logo，支持按分类筛选"""
    items = _logos
    if category:
        items = [l for l in items if l.category == category]
    items.sort(key=lambda x: x.sort_order, reverse=True)
    return {
        "code": 200,
        "message": "success",
        "data": {"items": [i.model_dump() for i in items], "total": len(items)},
    }


@router.post("/logos", summary="新增合作企业Logo")
def create_logo(logo: PartnerLogoCreate):
    """新增一个合作企业Logo"""
    new_logo = PartnerLogo(
        id=str(uuid.uuid4()),
        created_at=datetime.now(UTC).isoformat(),
        **logo.model_dump(),
    )
    _logos.append(new_logo)
    logger.info(f"新增合作企业Logo: {new_logo.name}")
    return {
        "code": 200,
        "message": "创建成功",
        "data": new_logo.model_dump(),
    }


# ---------- 成功案例 ----------


@router.get("/cases", summary="获取成功案例列表")
def get_cases(tag: str | None = None):
    """获取所有成功案例，支持按标签筛选"""
    items = _cases
    if tag:
        items = [c for c in items if tag in c.tags]
    items.sort(key=lambda x: x.sort_order, reverse=True)
    return {
        "code": 200,
        "message": "success",
        "data": {"items": [i.model_dump() for i in items], "total": len(items)},
    }


@router.post("/cases", summary="新增成功案例")
def create_case(case: SuccessCaseCreate):
    """新增一个成功案例"""
    new_case = SuccessCase(
        id=str(uuid.uuid4()),
        created_at=datetime.now(UTC).isoformat(),
        **case.model_dump(),
    )
    _cases.append(new_case)
    logger.info(f"新增成功案例: {new_case.title}")
    return {
        "code": 200,
        "message": "创建成功",
        "data": new_case.model_dump(),
    }


# ---------- 平台统计 ----------


@router.get("/stats", summary="获取平台统计数据")
def get_stats():
    """获取平台累计统计数据"""
    stats = PlatformStats(
        total_matches=12860,
        total_transactions=5680,
        total_enterprises=1280,
        satisfaction_rate=96.8,
        updated_at=datetime.now(UTC).isoformat(),
    )
    return {
        "code": 200,
        "message": "success",
        "data": stats.model_dump(),
    }
