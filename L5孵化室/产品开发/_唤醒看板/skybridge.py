"""
skybridge.py — 快捷唤醒词解析模块
输入快捷唤醒词，返回对应的产品信息字典。
同时被 app.py 和外部 CLI 调用。
"""

# 完整产品清单（24个产品）
PRODUCTS = [
    # 🟢 可运行产品（13个）
    {
        "id": 1,
        "name": "赛博参谋",
        "keyword": "计然",
        "tagline": "创业决策沙盘，输入想法输出推演报告",
        "status": "ready",
        "status_label": "🟢 可运行",
        "command": "python3 cybernetic_advisor.py",
        "service": "CLI",
        "digital_staff": "计然P8",
    },
    {
        "id": 2,
        "name": "AI灵魂觉醒引擎",
        "keyword": "云师",
        "tagline": "知识→AI员工的Web蒸馏流水线",
        "status": "ready",
        "status_label": "🟢 可运行",
        "command": "python3 app.py",
        "service": "localhost:5015",
        "digital_staff": "云师P8",
    },
    {
        "id": 3,
        "name": "白泽控制台",
        "keyword": "白泽",
        "tagline": "数字员工CEO驾驶舱",
        "status": "ready",
        "status_label": "🟢 可运行",
        "command": "python3 app.py",
        "service": "localhost:5010",
        "digital_staff": "白泽P9",
    },
    {
        "id": 4,
        "name": "数字员工SaaS",
        "keyword": "招贤",
        "tagline": "AI员工招聘市场+管理平台",
        "status": "ready",
        "status_label": "🟢 可运行",
        "command": "python3 app.py",
        "service": "localhost:5020",
        "digital_staff": "英招P9",
    },
    {
        "id": 5,
        "name": "文鳐技能集市",
        "keyword": "文鳐",
        "tagline": "技能包搜索/下载/安装的产品化技能市场",
        "status": "ready",
        "status_label": "🟢 可运行",
        "command": "python3 app.py",
        "service": "localhost:5012",
        "digital_staff": "文鳐P9",
    },
    {
        "id": 6,
        "name": "3+X窗口管理面板",
        "keyword": "司南",
        "tagline": "白泽多窗口状态管理与快速切换",
        "status": "ready",
        "status_label": "🟢 可运行",
        "command": "python3 app.py",
        "service": "localhost:5008",
        "digital_staff": None,
    },
    {
        "id": 7,
        "name": "大航海知识库",
        "keyword": "藏经",
        "tagline": "出海知识库RAG问答系统",
        "status": "ready",
        "status_label": "🟢 可运行",
        "command": "python3 run_knowledge_base.py",
        "service": "localhost:5005",
        "digital_staff": None,
    },
    {
        "id": 8,
        "name": "大航海北极星看板",
        "keyword": "远航",
        "tagline": "中韩出海数智港专属北极星看板",
        "status": "ready",
        "status_label": "🟢 可运行",
        "command": "python3 app.py",
        "service": "localhost:5004",
        "digital_staff": None,
    },
    {
        "id": 9,
        "name": "企业知识库RAG",
        "keyword": "奎",
        "tagline": "企业文档自动索引+AI问答的知识引擎",
        "status": "ready",
        "status_label": "🟢 可运行",
        "command": "src/bootstrap.sh 或 MCP8000",
        "service": "MCP8000",
        "digital_staff": None,
    },
    {
        "id": 10,
        "name": "内容自动化工厂",
        "keyword": "阿久",
        "tagline": "AI内容生产全链路自动化流水线",
        "status": "ready",
        "status_label": "🟢 可运行",
        "command": "python3 app.py",
        "service": "localhost:5000",
        "digital_staff": "乘黄P8",
    },
    {
        "id": 11,
        "name": "䑏疏跨境助手",
        "keyword": "䑏疏",
        "tagline": "跨域合规与商业智能助手",
        "status": "ready",
        "status_label": "🟢 可运行",
        "command": "CLI + localhost",
        "service": "CLI+localhost",
        "digital_staff": "䑏疏P8",
    },
    {
        "id": 12,
        "name": "会议智能小助手",
        "keyword": "鸣蜩",
        "tagline": "飞阅会AI主持助理",
        "status": "ready",
        "status_label": "🟢 可运行",
        "command": "python3 app.py",
        "service": "localhost:5014",
        "digital_staff": None,
    },
    {
        "id": 13,
        "name": "飞阅会AI主持助理",
        "keyword": "翟如",
        "tagline": "飞阅会全流程AI主持",
        "status": "ready",
        "status_label": "🟢 可运行",
        "command": "localhost:5014",
        "service": "localhost:5014",
        "digital_staff": None,
    },
    # 🟡 部分就绪（7个）
    {
        "id": 14,
        "name": "乘黄内容工厂v2",
        "keyword": "乘黄",
        "tagline": "多平台AI内容中台",
        "status": "partial",
        "status_label": "🟡 部分就绪",
        "command": "代码8,341行但Flask入口未从v1复制",
        "service": "代码就绪，缺入口",
        "digital_staff": "乘黄P8",
    },
    {
        "id": 15,
        "name": "数字员工指挥官",
        "keyword": "将明",
        "tagline": "数字员工战略决策与指挥中心",
        "status": "partial",
        "status_label": "🟡 部分就绪",
        "command": "仅文档",
        "service": "仅文档",
        "digital_staff": None,
    },
    {
        "id": 16,
        "name": "浏览器自动化IDE",
        "keyword": "工坊",
        "tagline": "可视化浏览器自动化脚本开发IDE",
        "status": "partial",
        "status_label": "🟡 部分就绪",
        "command": "61个代码文件，MVP缺集成",
        "service": "61文件，缺集成",
        "digital_staff": None,
    },
    {
        "id": 17,
        "name": "烛龙工程流",
        "keyword": "烛龙",
        "tagline": "AI工程流水线—41个原子聚合",
        "status": "partial",
        "status_label": "🟡 部分就绪",
        "command": "文档+原子，缺运行代码",
        "service": "文档+原子",
        "digital_staff": "烛龙P8",
    },
    {
        "id": 18,
        "name": "辩论式代码审查流水线",
        "keyword": "狴犴",
        "tagline": "AI驱动多视角代码审查协作平台",
        "status": "partial",
        "status_label": "🟡 部分就绪",
        "command": "10代码文件+7原子",
        "service": "10代码+7原子",
        "digital_staff": "狴犴P8",
    },
    {
        "id": 19,
        "name": "中韩出海数智港",
        "keyword": "远航2",
        "tagline": "中韩出海全栈平台",
        "status": "partial",
        "status_label": "🟡 部分就绪",
        "command": "62文件完整前后端，需部署(8088)",
        "service": "localhost:8088",
        "digital_staff": None,
    },
    {
        "id": 20,
        "name": "项目管理北极星",
        "keyword": "玄鉴",
        "tagline": "项目级北极星指标管理",
        "status": "partial",
        "status_label": "🟡 部分就绪",
        "command": "仅文档+10原子",
        "service": "仅文档+10原子",
        "digital_staff": None,
    },
    # 🔴 早期/待确认（4个）
    {
        "id": 21,
        "name": "FreeClaudeCode代理",
        "keyword": "爻",
        "tagline": "Codex CLI代理收费方案",
        "status": "design",
        "status_label": "🔴 设计阶段",
        "command": "仅文档",
        "service": "仅文档",
        "digital_staff": None,
    },
    {
        "id": 22,
        "name": "SystemDesign学习工具",
        "keyword": "灵匠",
        "tagline": "系统设计知识库+练习工具",
        "status": "design",
        "status_label": "🔴 设计阶段",
        "command": "仅文档",
        "service": "仅文档",
        "digital_staff": None,
    },
    {
        "id": 23,
        "name": "数字员工管理体系",
        "keyword": "鲲鹏",
        "tagline": "数字员工组织的制度与流程规范",
        "status": "design",
        "status_label": "🔴 设计阶段",
        "command": "仅文档+无atoms",
        "service": "仅文档",
        "digital_staff": "鲲鹏P8",
    },
    {
        "id": 24,
        "name": "战略合作",
        "keyword": "连横",
        "tagline": "外部合作与联盟管理",
        "status": "design",
        "status_label": "🔴 设计阶段",
        "command": "23代码文件无文档",
        "service": "23代码文件",
        "digital_staff": None,
    },
]


def resolve(keyword: str) -> dict | None:
    """输入快捷唤醒词，返回对应的产品信息字典。
    
    例如:
        resolve('计然') → {'name':'赛博参谋', 'keyword':'计然', ...}
        resolve('不存在的词') → None
    
    Args:
        keyword: 快捷唤醒词（如'计然'、'云师'）
    
    Returns:
        匹配的产品字典，若未找到则返回 None
    """
    for product in PRODUCTS:
        if product["keyword"] == keyword:
            return product
    return None


def list_by_status(status: str | None = None) -> list:
    """按状态筛选产品列表。
    
    Args:
        status: 'ready' | 'partial' | 'design' | None (全部)
    
    Returns:
        筛选后的产品列表
    """
    if status is None:
        return PRODUCTS
    return [p for p in PRODUCTS if p["status"] == status]


def get_status_groups() -> dict:
    """获取按状态分组的产品字典。"""
    return {
        "ready": [p for p in PRODUCTS if p["status"] == "ready"],
        "partial": [p for p in PRODUCTS if p["status"] == "partial"],
        "design": [p for p in PRODUCTS if p["status"] == "design"],
    }
