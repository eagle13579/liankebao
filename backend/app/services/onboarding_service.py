"""冷启动引导 — 服务层

提供预设模板推荐 & 默认填充配置。
纯静态数据，无数据库依赖。
"""

# ===================================================================
# 预设模板列表（6个）
# ===================================================================
ONBOARDING_TEMPLATES = [
    {
        "id": "classic_business",
        "name": "经典商务",
        "description": "深蓝主色 + 金色点缀，适合传统企业、制造业、贸易公司",
        "preview_color": "#1a237e",
        "tags": ["商务", "稳重", "传统"],
    },
    {
        "id": "tech_frontier",
        "name": "科技前沿",
        "description": "蓝紫渐变 + 毛玻璃效果，适合互联网、AI、SaaS 企业",
        "preview_color": "linear-gradient(135deg, #667eea, #764ba2)",
        "tags": ["科技", "创新", "互联网"],
    },
    {
        "id": "modern_minimal",
        "name": "简约现代",
        "description": "纯白底色 + 极简留白，适合咨询、设计、个人品牌",
        "preview_color": "#f5f5f5",
        "tags": ["简约", "设计", "个人品牌"],
    },
    {
        "id": "luxury_gold",
        "name": "奢华金典",
        "description": "深色底 + 金属金色高光，适合高端品牌、地产、金融",
        "preview_color": "#1a1a2e",
        "tags": ["高端", "金融", "地产"],
    },
    {
        "id": "nature_fresh",
        "name": "自然清新",
        "description": "草木绿 + 暖白，适合环保、农业、健康产业",
        "preview_color": "#2e7d32",
        "tags": ["环保", "健康", "农业"],
    },
    {
        "id": "creative_art",
        "name": "创意艺术",
        "description": "多色渐变 + 不规则排版，适合文创、传媒、艺术工作室",
        "preview_color": "linear-gradient(135deg, #ff6b6b, #f093fb, #4facfe)",
        "tags": ["创意", "艺术", "传媒"],
    },
]


# ===================================================================
# 三步引导默认填充
# ===================================================================
ONBOARDING_STEPS = [
    {
        "step": 1,
        "name": "基本信息",
        "description": "填写企业核心信息，客户第一眼看到的内容",
        "fields": [
            {"key": "company_name", "label": "企业名称", "type": "text", "placeholder": "请输入您的企业/品牌名称", "default": ""},
            {"key": "position", "label": "职位", "type": "text", "placeholder": "如：创始人 / CEO / 销售总监", "default": ""},
            {"key": "phone", "label": "联系电话", "type": "tel", "placeholder": "请输入手机号", "default": ""},
            {"key": "email", "label": "电子邮箱", "type": "email", "placeholder": "请输入邮箱地址", "default": ""},
        ],
    },
    {
        "step": 2,
        "name": "企业展示",
        "description": "展示企业实力与服务，让客户快速了解您",
        "fields": [
            {"key": "company_slogan", "label": "企业标语", "type": "text", "placeholder": "一句话概括您的核心价值", "default": ""},
            {"key": "industry", "label": "所属行业", "type": "select", "options": [
                "互联网/科技", "制造业", "贸易/进出口", "金融/保险",
                "地产/建筑", "文化/传媒", "医疗/健康", "教育/培训",
                "餐饮/零售", "咨询/服务", "其他",
            ], "default": ""},
            {"key": "company_description", "label": "企业简介", "type": "textarea", "placeholder": "简要介绍您的企业（200字以内）", "default": ""},
            {"key": "website", "label": "企业官网", "type": "url", "placeholder": "https://", "default": ""},
        ],
    },
    {
        "step": 3,
        "name": "个性化设置",
        "description": "定制专属风格，让名片更具辨识度",
        "fields": [
            {"key": "theme_color", "label": "主题色", "type": "color", "default": "#1a237e"},
            {"key": "cover_image", "label": "封面图片", "type": "image", "placeholder": "上传一张封面图（建议尺寸 750×500）", "default": ""},
            {"key": "album_style", "label": "画册翻页风格", "type": "select", "options": [
                "翻页", "滑动", "淡入淡出",
            ], "default": "翻页"},
            {"key": "show_qrcode", "label": "显示微信二维码", "type": "boolean", "default": True},
        ],
    },
]


def get_templates() -> list[dict]:
    """获取所有预设模板"""
    return ONBOARDING_TEMPLATES


def get_defaults() -> dict:
    """获取三步引导默认配置"""
    return {
        "total_steps": len(ONBOARDING_STEPS),
        "steps": ONBOARDING_STEPS,
    }
