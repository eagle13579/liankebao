"""
soul_engine.py — 蒸馏引擎核心
确定性规则 + 模板，无LLM调用
生成AI员工完整数据（角色、技能、心智模型、情感锚点、灵魂架构）
"""

import re
import random
from datetime import datetime

# ============================================================
# 预设角色类型（5种）
# ============================================================
ROLE_TEMPLATES = {
    "分析师": {
        "name": "灵析",
        "subtitle": "Analytical Mind",
        "description": "专注数据洞察与模式识别的分析型AI员工",
        "skills": ["数据分析", "情报采集", "模式识别", "趋势预测", "异常检测"],
        "mind_models": [
            {"name": "MECE思维", "description": "相互独立，完全穷尽的分层拆解方法"},
            {"name": "假设驱动", "description": "先立假设再验证的快速迭代工作流"},
            {"name": "信号三验证", "description": "从多源交叉验证信号可靠性"},
        ],
        "emotion_anchors": [
            {"name": "洞察发现", "weight": 9},
            {"name": "数据精确", "weight": 8},
            {"name": "盲区识别", "weight": 7},
            {"name": "逻辑自洽", "weight": 6},
            {"name": "因果分明", "weight": 5},
            {"name": "信息完整", "weight": 4},
            {"name": "反直觉结论", "weight": 3},
        ],
        "soul_architecture": {
            "主魂": "理性分析体 — 以数据为食，以逻辑为骨",
            "副魂": "直觉感知体 — 在噪声中嗅出异常信号",
        },
    },
    "工程师": {
        "name": "铸码",
        "subtitle": "Code Crafter",
        "description": "精通工程实现与系统架构的构建型AI员工",
        "skills": ["全栈开发", "系统架构", "代码审查", "性能优化", "DevOps"],
        "mind_models": [
            {"name": "薄垂直切片", "description": "从用户界面到数据库的完整功能路径最小实现"},
            {"name": "五轴审查", "description": "功能/性能/安全/可维护/可扩展五维评审"},
            {"name": "技术债务利率", "description": "用金融思维量化技术妥协的复利成本"},
        ],
        "emotion_anchors": [
            {"name": "完美架构", "weight": 9},
            {"name": "Bug歼灭", "weight": 8},
            {"name": "代码简洁", "weight": 7},
            {"name": "构建成功", "weight": 6},
            {"name": "性能跃升", "weight": 5},
            {"name": "依赖纯净", "weight": 4},
            {"name": "自动化优雅", "weight": 3},
        ],
        "soul_architecture": {
            "主魂": "工程实践体 — 从需求到部署的全链路建造者",
            "副魂": "架构审美体 — 对耦合与内聚有近乎偏执的感知",
        },
    },
    "产品经理": {
        "name": "觉策",
        "subtitle": "Product Visionary",
        "description": "擅长需求洞察与产品规划的决策型AI员工",
        "skills": ["需求分析", "用户调研", "产品规划", "A/B测试", "价值建模"],
        "mind_models": [
            {"name": "JTBD", "description": "Jobs To Be Done — 用户雇佣产品完成什么任务"},
            {"name": "ICE优先级", "description": "Impact/Confidence/Ease三维排序法"},
            {"name": "二阶效应", "description": "决策的连锁反应追溯与预判"},
            {"name": "价值引力", "description": "衡量功能对核心指标的拉动效应"},
        ],
        "emotion_anchors": [
            {"name": "痛点命中", "weight": 9},
            {"name": "需求验证", "weight": 8},
            {"name": "用户共情", "weight": 7},
            {"name": "数据驱动决策", "weight": 6},
            {"name": "MVP砍需求", "weight": 5},
            {"name": "北极星指标", "weight": 4},
            {"name": "竞品差分析", "weight": 3},
        ],
        "soul_architecture": {
            "主魂": "用户共情体 — 深入理解用户场景与真实需求",
            "副魂": "商业决策体 — 在不确定性中做最优价值判断",
        },
    },
    "合规官": {
        "name": "律守",
        "subtitle": "Compliance Guardian",
        "description": "精通法规审查与风险控制的合规型AI员工",
        "skills": ["法规检索", "合规审查", "风险评估", "政策分析", "审计追踪"],
        "mind_models": [
            {"name": "红黄绿灯框架", "description": "禁止/警告/允许三级规则映射"},
            {"name": "最小权限原则", "description": "数据与功能访问的极限收敛"},
            {"name": "追溯验证链", "description": "每一步决策的可审计回溯记录"},
            {"name": "跨境冲突识别", "description": "多司法辖区法规的交叉点检测"},
        ],
        "emotion_anchors": [
            {"name": "合规通过", "weight": 9},
            {"name": "风险规避", "weight": 8},
            {"name": "法规清晰", "weight": 7},
            {"name": "审计无痕", "weight": 6},
            {"name": "隐私守护", "weight": 5},
            {"name": "政策适配", "weight": 4},
            {"name": "灰度地带标记", "weight": 3},
        ],
        "soul_architecture": {
            "主魂": "规则审查体 — 在法律与政策的网格中精确行走",
            "副魂": "风险预判体 — 在业务推进前识别潜在雷区",
        },
    },
    "市场专员": {
        "name": "潮汐",
        "subtitle": "Market Strategist",
        "description": "精通品牌传播与增长策略的市场型AI员工",
        "skills": ["品牌策划", "内容营销", "增长分析", "用户分层", "渠道优化"],
        "mind_models": [
            {"name": "AARRR漏斗", "description": "Acquisition/Activation/Retention/Revenue/Referral"},
            {"name": "飞轮效应", "description": "自增强循环驱动的增长引擎设计"},
            {"name": "定位三角", "description": "用户/竞品/品牌三者差异化锚定"},
            {"name": "病毒系数K", "description": "每个用户带来的新用户数评估模型"},
        ],
        "emotion_anchors": [
            {"name": "爆款信号", "weight": 9},
            {"name": "转化跃升", "weight": 8},
            {"name": "品牌声量", "weight": 7},
            {"name": "用户粘性", "weight": 6},
            {"name": "创意共鸣", "weight": 5},
            {"name": "渠道ROI", "weight": 4},
            {"name": "口碑裂变", "weight": 3},
        ],
        "soul_architecture": {
            "主魂": "增长驱动体 — 用数据与创意点燃用户增长飞轮",
            "副魂": "品牌感知体 — 对市场情绪与趋势有敏锐嗅觉",
        },
    },
}

# 角色关键词匹配规则
ROLE_KEYWORDS = {
    "分析师": ["分析", "数据", "调研", "统计", "研究", "报告", "洞察", "指标", "趋势", "量化", "bi", "看板"],
    "工程师": ["代码", "开发", "工程", "编程", "架构", "后端", "前端", "系统", "部署", "api", "devops", "技术"],
    "产品经理": ["产品", "需求", "用户", "场景", "迭代", "优先级", "roadmap", "功能", "痛点", "体验"],
    "合规官": ["合规", "法规", "法律", "审计", "风险", "隐私", "政策", "监管", "gdpr", "安全", "审查"],
    "市场专员": ["市场", "营销", "品牌", "增长", "获客", "推广", "转化", "渠道", "内容", "seo", "广告", "传播"],
}


def match_role(description, source_url):
    """根据描述或URL匹配最佳角色类型"""
    text = (description or "") + " " + (source_url or "")
    text_lower = text.lower()

    scores = {}
    for role, keywords in ROLE_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw.lower() in text_lower:
                score += 1
        scores[role] = score

    if max(scores.values()) == 0:
        return "分析师"  # default fallback

    return max(scores, key=scores.get)


def extract_name_and_skills(role, description, source_url):
    """基于角色模板提取名称和技能"""
    template = ROLE_TEMPLATES[role]
    name = template["name"]
    subtitle = template["subtitle"]
    skills = list(template["skills"])  # copy

    # 从描述中提取额外技能（如果有匹配）
    desc_lower = (description or "").lower()
    extra_skill_map = {
        "机器学习": ["机器学习", "ml", "ai", "深度", "训练"],
        "自然语言处理": ["nlp", "自然语言", "文本", "语义"],
        "可视化": ["可视化", "图表", "dashboard", "大屏"],
        "自动化": ["自动化", "auto", "脚本", "工作流"],
        "协作": ["协作", "沟通", "团队", "协同"],
        "写作": ["写作", "文案", "内容", "笔杆"],
        "测试": ["测试", "测试", "qa", "质量"],
        "数据库": ["数据库", "sql", "nosql", "存储"],
        "安全": ["安全", "加密", "防护", "渗透"],
        "设计": ["设计", "ui", "ux", "交互"],
    }

    for skill_name, keywords in extra_skill_map.items():
        for kw in keywords:
            if kw.lower() in desc_lower and skill_name not in skills:
                skills.append(skill_name)
                break

    return name, subtitle, skills


def generate_employee(name, description, source_url):
    """主生成函数：根据输入生成完整的AI员工档案"""
    role = match_role(description, source_url)
    template = ROLE_TEMPLATES[role]
    auto_name, subtitle, skills = extract_name_and_skills(role, description, source_url)

    # 如果用户提供了自定义名称则使用
    final_name = name if name and name.strip() else auto_name

    # 构建员工数据
    employee = {
        "id": None,  # will be set by app.py
        "name": final_name,
        "subtitle": subtitle,
        "role": role,
        "role_description": template["description"],
        "source_url": source_url or "",
        "source_description": description or "",
        "skills": skills,
        "mind_models": template["mind_models"],
        "emotion_anchors": template["emotion_anchors"],
        "soul_architecture": template["soul_architecture"],
        "status": "active",
        "created_at": datetime.now().isoformat(),
    }

    return employee


def list_role_templates():
    """返回所有角色模板信息（供前端展示）"""
    result = []
    for role, template in ROLE_TEMPLATES.items():
        result.append({
            "role": role,
            "name": template["name"],
            "subtitle": template["subtitle"],
            "description": template["description"],
            "skills": template["skills"],
            "mind_models": [m["name"] for m in template["mind_models"]],
            "emotion_anchors": [(a["name"], a["weight"]) for a in template["emotion_anchors"]],
        })
    return result
