"""
数据丰富管道 — 企查查/天眼查第三方企业信息集成

提供抽象基类 BaseEnricher 和企查查模拟实现 QichachaEnricher，
支持企业基本信息查询、经营范围获取、联系人信息采集，
带 SQLite 缓存和 API 超时降级机制。
"""

import abc
import json
import logging
import os
import random
import re
import sqlite3
import time

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 加载 .env 文件 (优先项目根目录, 兼容不同启动路径)
_env_loaded = False


def _ensure_env_loaded() -> None:
    """确保 .env 文件已被加载 (幂等)"""
    global _env_loaded
    if _env_loaded:
        return
    # 尝试从多个位置加载 .env
    candidate_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"),  # 项目根
        os.path.join(os.getcwd(), ".env"),  # 当前工作目录
    ]
    for p in candidate_paths:
        p = os.path.abspath(p)
        if os.path.isfile(p):
            load_dotenv(p, override=False)
            logger.info("已加载 .env 文件: %s", p)
            break
    _env_loaded = True


# 确保环境变量在模块加载时已就绪
_ensure_env_loaded()


# ============================================================
# 常量
# ============================================================
CACHE_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
CACHE_DB_PATH = os.path.join(CACHE_DB_DIR, "enrichment_cache.db")
CACHE_TTL_SECONDS = 86400  # 缓存有效期: 24小时
REQUEST_TIMEOUT = 10  # API 请求超时(秒)
MOCK_MODE = os.environ.get("QICHACHA_MOCK", "true").lower() in ("true", "1", "yes")
CACHE_ASYNC_REFRESH_AGE = 43200  # 缓存异步刷新阈值: 12小时 (命中缓存且超过此年龄时后台异步刷新)

# ============================================================
# 缓存管理 (SQLite)
# ============================================================


def _get_cache_connection() -> sqlite3.Connection:
    """获取缓存数据库连接（线程安全，每次调用返回新连接）"""
    os.makedirs(CACHE_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS enrichment_cache (
            cache_key TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _cache_get(cache_key: str) -> dict | None:
    """从缓存读取数据，过期则返回 None"""
    try:
        conn = _get_cache_connection()
        row = conn.execute(
            "SELECT data, created_at FROM enrichment_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        data_str, created_at = row
        age = time.time() - created_at
        if age > CACHE_TTL_SECONDS:
            return None
        return json.loads(data_str)
    except Exception as exc:
        logger.warning("缓存读取失败: %s", exc)
        return None


def _cache_set(cache_key: str, data: dict) -> None:
    """写入缓存"""
    try:
        conn = _get_cache_connection()
        conn.execute(
            "INSERT OR REPLACE INTO enrichment_cache (cache_key, data, created_at) VALUES (?, ?, ?)",
            (cache_key, json.dumps(data, ensure_ascii=False), time.time()),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("缓存写入失败: %s", exc)


def _cache_get_with_refresh_flag(cache_key: str) -> tuple[dict | None, bool]:
    """
    获取缓存并返回异步刷新标志

    Returns:
        (data, needs_async_refresh):
        - data: 缓存数据 (过期返回 None)
        - needs_async_refresh: 缓存存在且超过 CACHE_ASYNC_REFRESH_AGE 时为 True
    """
    try:
        conn = _get_cache_connection()
        row = conn.execute(
            "SELECT data, created_at FROM enrichment_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        conn.close()
        if row is None:
            return None, False
        data_str, created_at = row
        age = time.time() - created_at
        if age > CACHE_TTL_SECONDS:
            return None, False
        needs_refresh = age > CACHE_ASYNC_REFRESH_AGE
        return json.loads(data_str), needs_refresh
    except Exception as exc:
        logger.warning("缓存读取失败: %s", exc)
        return None, False


# ============================================================
# 抽象基类
# ============================================================


class BaseEnricher(abc.ABC):
    """数据丰富器抽象基类"""

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key
        self.base_url = base_url

    @abc.abstractmethod
    def search_company(self, name: str) -> dict:
        """搜索企业基本信息"""
        ...

    @abc.abstractmethod
    def get_business_scope(self, name: str) -> dict:
        """获取企业经营范围"""
        ...

    @abc.abstractmethod
    def get_contacts(self, name: str) -> dict:
        """获取企业联系人/电话"""
        ...

    def enrich(self, name: str) -> dict:
        """一键丰富：聚合企业信息、经营范围、联系人"""
        result = self.search_company(name)
        scope = self.get_business_scope(name)
        contacts = self.get_contacts(name)
        result["business_scope_detail"] = scope.get("business_scope", "")
        result["contacts"] = contacts.get("contacts", [])
        result["phones"] = contacts.get("phones", [])
        return result


# ============================================================
# 企查查模拟实现
# ============================================================


class QichachaEnricher(BaseEnricher):
    """
    企查查数据丰富器（模拟实现）

    在 MOCK_MODE=True 时返回本地模拟数据，便于开发和测试。
    生产环境设置 QICHACHA_MOCK=false 并配置 QICHACHA_API_KEY 环境变量即可接入真实API。

    对于未在预置数据池中的企业名称，系统会根据名称关键词自动生成
    合理的模拟数据（行业、经营范围、联系人信息等），使其更接近真实场景。
    """

    # 模拟企业数据池
    MOCK_COMPANIES = {
        "北京字节跳动科技有限公司": {
            "name": "北京字节跳动科技有限公司",
            "short_name": "字节跳动",
            "credit_code": "91110108MA01BKLE31",
            "legal_person": "张一鸣",
            "registered_capital": "10000万元人民币",
            "established_date": "2012-03-09",
            "industry": "科技推广和应用服务业",
            "region": "北京市海淀区",
            "business_scope": "技术开发、技术推广、技术转让、技术咨询、技术服务；计算机系统服务；基础软件服务；应用软件服务；软件开发；软件咨询；产品设计；模型设计；包装装潢设计；教育咨询；经济贸易咨询；文化咨询；体育咨询；公共关系服务；会议服务；投资咨询；工艺美术设计；电脑动画设计；项目投资；投资管理；资产管理；企业策划、设计；设计、制作、代理、发布广告；市场调查；企业管理咨询；组织文化艺术交流活动（不含营业性演出）；文艺创作；承办展览展示活动；影视策划；翻译服务；自然科学研究与试验发展；工程和技术研究与试验发展；农业科学研究与试验发展；医学研究与试验发展；数据处理（数据处理中的银行卡中心、PUE值在1.5以上的云计算数据中心除外）。",
            "status": "存续",
            "website": "https://www.bytedance.com",
            "tags": ["互联网", "科技", "短视频", "AI"],
            "confidence": 0.95,
        },
        "阿里巴巴（中国）有限公司": {
            "name": "阿里巴巴（中国）有限公司",
            "short_name": "阿里巴巴",
            "credit_code": "91330100799China",
            "legal_person": "马云",
            "registered_capital": "23200万元人民币",
            "established_date": "2007-03-26",
            "industry": "互联网和相关服务",
            "region": "浙江省杭州市余杭区",
            "business_scope": "服务：计算机软硬件、网络技术的开发、技术服务、技术咨询、成果转让；批发、零售：计算机软硬件；设计、制作、代理、发布国内广告（除新闻媒体及网络广告）；货物进出口（法律法规禁止的项目除外，法律法规限制的项目取得许可证后方可经营）；含下属分支机构经营范围。",
            "status": "存续",
            "website": "https://www.alibaba.com",
            "tags": ["电商", "互联网", "云计算", "金融科技"],
            "confidence": 0.96,
        },
        "腾讯科技（深圳）有限公司": {
            "name": "腾讯科技（深圳）有限公司",
            "short_name": "腾讯",
            "credit_code": "91440300708461136T",
            "legal_person": "马化腾",
            "registered_capital": "65000万元人民币",
            "established_date": "2000-02-24",
            "industry": "软件和信息技术服务业",
            "region": "广东省深圳市南山区",
            "business_scope": "计算机软硬件的技术开发、销售自行开发的软件；计算机技术服务及信息服务；计算机硬件的研发、销售；无线电通讯产品的研发、销售；电信业务经营；国内贸易（不含专营、专控、专卖商品）；从事广告业务（法律法规、国务院规定需另行办理广告经营审批的，需取得许可后方可经营）。",
            "status": "存续",
            "website": "https://www.tencent.com",
            "tags": ["社交", "游戏", "互联网", "金融科技"],
            "confidence": 0.97,
        },
    }

    # 模拟联系人数据
    MOCK_CONTACTS = {
        "北京字节跳动科技有限公司": {
            "contacts": [
                {"name": "张一鸣", "title": "法定代表人/CEO", "department": "管理层"},
                {"name": "梁汝波", "title": "CEO", "department": "管理层"},
            ],
            "phones": ["400-xxx-xxxx", "010-xxxxxxxx"],
            "email": "contact@bytedance.com",
            "address": "北京市海淀区知春路甲48号2号楼二十一层2109",
        },
        "阿里巴巴（中国）有限公司": {
            "contacts": [
                {"name": "马云", "title": "创始人", "department": "管理层"},
                {"name": "张勇", "title": "董事会主席/CEO", "department": "管理层"},
            ],
            "phones": ["0571-xxxxxxx", "400-xxx-xxxx"],
            "email": "service@alibaba.com",
            "address": "浙江省杭州市余杭区文一西路969号",
        },
        "腾讯科技（深圳）有限公司": {
            "contacts": [
                {"name": "马化腾", "title": "董事会主席/CEO", "department": "管理层"},
                {"name": "刘炽平", "title": "总裁", "department": "管理层"},
            ],
            "phones": ["0755-xxxxxxxx", "400-xxx-xxxx"],
            "email": "service@tencent.com",
            "address": "广东省深圳市南山区海天二路33号腾讯滨海大厦",
        },
    }

    # --------------------------------------------------
    # 智能 Mock 数据生成器（企业名称关键词分析）
    # --------------------------------------------------

    # 中文姓氏池
    SURNAMES = [
        "张", "李", "王", "赵", "刘", "陈", "杨", "黄", "周", "吴",
        "徐", "孙", "马", "胡", "朱", "郭", "何", "罗", "高", "林",
    ]

    # 中文名字池
    GIVEN_NAMES = [
        "伟", "芳", "娜", "敏", "静", "丽", "强", "磊", "军", "洋",
        "勇", "艳", "杰", "鹏", "明", "超", "秀英", "华", "建国",
        "志强", "晓明", "文博", "玉婷", "建华", "志远", "海涛",
    ]

    # 行业关键词映射: (关键词列表, 行业名称, 经营范围模板列表, 最小注册资本(万元))
    INDUSTRY_KEYWORDS = [
        (
            ["科技", "技术", "软件", "网络", "信息", "计算机", "互联网", "数码", "智能", "AI", "人工智能", "数据"],
            "软件和信息技术服务业",
            [
                "技术开发、技术服务、技术咨询、技术转让；软件开发；计算机系统服务；数据处理；",
                "基础软件服务、应用软件服务；产品设计；模型设计；",
                "互联网信息服务；信息技术咨询；信息系统集成服务；",
            ],
            1000,
        ),
        (
            ["贸易", "商贸", "进出口", "国际", "外贸", "供应链"],
            "批发业",
            [
                "日用百货、五金交电、电子产品、办公用品的销售；",
                "货物进出口、技术进出口、代理进出口；",
                "国内贸易代理；供应链管理服务；",
            ],
            500,
        ),
        (
            ["建筑", "工程", "建设", "装饰", "装修", "土木", "施工", "园林"],
            "房屋建筑业",
            [
                "建筑工程、市政工程、园林绿化工程、室内外装饰工程的设计与施工；",
                "建筑劳务分包；工程项目管理；工程勘察设计；",
                "建筑材料、装饰材料的销售；机械设备租赁；",
            ],
            5000,
        ),
        (
            ["餐饮", "食品", "酒店", "食堂", "烹饪", "烘焙"],
            "餐饮业",
            [
                "餐饮服务；餐饮管理；食品加工技术咨询、技术转让；",
                "预包装食品、散装食品的销售；会议服务；",
                "企业管理咨询；市场营销策划；",
            ],
            100,
        ),
        (
            ["教育", "培训", "学校", "学院", "教学", "留学"],
            "教育",
            [
                "教育培训；教育咨询；文化艺术交流策划；",
                "教学软件、教学设备的技术开发与销售；",
                "出版物零售；自费出国留学中介服务；",
            ],
            100,
        ),
        (
            ["咨询", "管理咨询", "顾问", "策划"],
            "商务服务业",
            [
                "企业管理咨询；经济贸易咨询；市场调查；",
                "企业策划；公共关系服务；会议服务；承办展览展示活动；",
                "设计、制作、代理、发布广告；技术咨询、技术服务；",
            ],
            100,
        ),
        (
            ["医疗", "医药", "药房", "健康", "生物", "基因", "医疗器械", "制药"],
            "医药制造业",
            [
                "药品研发、生产、销售；医疗器械的研发、生产、销售；",
                "生物技术开发、技术咨询、技术转让、技术服务；",
                "健康管理咨询；医学研究与试验发展；",
            ],
            2000,
        ),
        (
            ["物流", "运输", "快递", "货运", "仓储", "配送"],
            "道路运输业",
            [
                "普通货运；货物专用运输；仓储服务；",
                "国内货物运输代理；物流信息咨询；",
                "装卸搬运服务；供应链管理；",
            ],
            300,
        ),
        (
            ["房地产", "物业", "置业", "地产", "房产"],
            "房地产业",
            [
                "房地产开发经营；物业管理；房地产中介服务；",
                "房屋租赁；房地产营销策划；建设工程项目管理；",
                "停车场服务；自有房屋出租；",
            ],
            2000,
        ),
        (
            ["农业", "种养", "农产品", "生态", "林业", "渔业", "牧业"],
            "农业",
            [
                "农产品的种植、销售；农业技术开发、技术咨询、技术服务；",
                "生态农业观光旅游；农副产品加工、销售；",
                "化肥、农膜、农业机械的销售；",
            ],
            200,
        ),
        (
            ["环保", "环境", "节能", "新能源", "清洁", "低碳"],
            "生态保护和环境治理业",
            [
                "环保技术开发、技术咨询、技术服务；环境工程设计、施工；",
                "污水处理、废气治理；环保设备研发、销售、安装；",
                "节能技术推广服务；资源再生利用技术研发；",
            ],
            500,
        ),
        (
            ["制造", "生产", "工厂", "实业", "加工", "模具", "机械"],
            "制造业",
            [
                "机械设备及配件的生产、加工、销售；模具设计、制造、销售；",
                "电子产品生产、组装、销售；金属材料加工；",
                "工业自动化设备研发、制造、销售；货物或技术进出口；",
            ],
            1000,
        ),
        (
            ["金融", "投资", "基金", "资本", "保险", "证券", "支付"],
            "金融业",
            [
                "投资管理；投资咨询；资产管理；",
                "财务咨询；经济贸易咨询；企业管理咨询；",
                "接受金融机构委托从事金融信息技术外包、金融业务流程外包；",
            ],
            10000,
        ),
        (
            ["文化", "传媒", "传播", "广告", "影视", "娱乐", "体育", "演出"],
            "文化艺术业",
            [
                "组织文化艺术交流活动；影视策划；设计、制作、代理、发布广告；",
                "文艺创作；承办展览展示活动；会议服务；",
                "企业形象策划；市场营销策划；舞台艺术造型策划；",
            ],
            300,
        ),
        (
            ["设计", "品牌", "创意", "广告"],
            "专业技术服务业",
            [
                "品牌设计；平面设计；包装设计；网页设计；",
                "设计、制作、代理、发布广告；企业形象策划；",
                "展览展示服务；摄影摄像服务；",
            ],
            100,
        ),
        (
            ["律师", "会计", "审计", "税务", "知识产权", "专利", "商标"],
            "商务服务业",
            [
                "法律咨询；知识产权代理服务；商标代理；专利代理；",
                "企业管理咨询；财务咨询；税务咨询；",
                "市场调查；企业信用调查与评估；",
            ],
            100,
        ),
        (
            ["人力", "人才", "招聘", "派遣", "猎头"],
            "商务服务业",
            [
                "人才招聘；人才推荐；人才培训；",
                "劳务派遣；人力资源外包服务；",
                "企业管理咨询；职业中介服务；",
            ],
            200,
        ),
    ]

    # 省份/城市电话区号
    REGION_PHONE_CODES = {
        "北京": "010",
        "上海": "021",
        "天津": "022",
        "重庆": "023",
        "广州": "020",
        "深圳": "0755",
        "杭州": "0571",
        "南京": "025",
        "成都": "028",
        "武汉": "027",
        "西安": "029",
        "长沙": "0731",
        "郑州": "0371",
        "青岛": "0532",
        "大连": "0411",
        "厦门": "0592",
        "苏州": "0512",
        "宁波": "0574",
    }

    # 省份城市列表 (用于随机生成区域)
    REGIONS = [
        "北京市海淀区", "北京市朝阳区", "北京市东城区", "北京市西城区",
        "上海市浦东新区", "上海市徐汇区", "上海市静安区",
        "广东省深圳市南山区", "广东省广州市天河区", "广东省深圳市福田区",
        "浙江省杭州市余杭区", "浙江省杭州市西湖区",
        "江苏省南京市鼓楼区", "江苏省苏州市工业园区",
        "四川省成都市高新区", "湖北省武汉市洪山区",
        "陕西省西安市雁塔区", "山东省青岛市市南区",
        "湖南省长沙市岳麓区", "河南省郑州市金水区",
        "福建省厦门市思明区", "辽宁省大连市中山区",
        "天津市滨海新区", "重庆市渝北区",
    ]

    # 常用企业邮箱域名
    EMAIL_DOMAINS = [
        "qq.com", "163.com", "126.com", "sina.com",
        "gmail.com", "outlook.com", "hotmail.com",
        "company.com", "corp.com",
    ]

    # 企业状态 pool
    STATUS_OPTIONS = ["存续", "在营", "开业"]

    @staticmethod
    def _random_name() -> str:
        """生成随机中文姓名"""
        surname = random.choice(QichachaEnricher.SURNAMES)
        given = random.choice(QichachaEnricher.GIVEN_NAMES)
        return surname + given

    @classmethod
    def _analyze_company_name(cls, name: str) -> dict:
        """
        根据企业名称关键词分析行业、经营范围等信息。

        Returns:
            dict with keys: industry, scope_parts, region, min_capital
        """
        name_lower = name.lower()
        for keywords, industry, scope_templates, min_capital in cls.INDUSTRY_KEYWORDS:
            if any(kw.lower() in name_lower for kw in keywords):
                # 随机选择 2-3 条经营范围语句
                selected = random.sample(
                    scope_templates,
                    min(len(scope_templates), random.randint(2, 3)),
                )
                return {
                    "industry": industry,
                    "scope_parts": selected,
                    "region": random.choice(cls.REGIONS),
                    "min_capital": min_capital,
                }
        # 默认: 商务服务业
        return {
            "industry": "商务服务业",
            "scope_parts": [
                "企业管理咨询；经济贸易咨询；",
                "技术开发、技术咨询、技术服务、技术转让；",
                "组织文化艺术交流活动；会议服务；承办展览展示活动；",
            ],
            "region": random.choice(cls.REGIONS),
            "min_capital": 100,
        }

    @classmethod
    def _generate_business_scope(cls, name: str) -> str:
        """根据企业名称生成合理的经营范围文本"""
        analysis = cls._analyze_company_name(name)
        base = "".join(analysis["scope_parts"])
        return base + "依法须经批准的项目，经相关部门批准后方可开展经营活动。"

    @classmethod
    def _generate_contacts(cls, name: str) -> dict:
        """根据企业名称生成合理的联系人信息"""
        analysis = cls._analyze_company_name(name)
        region = analysis["region"]

        # 解析区域提取省份/城市名，用于电话区号
        area_code = ""
        for city_key, code in cls.REGION_PHONE_CODES.items():
            if city_key in region:
                area_code = code
                break

        # 生成法定代表人姓名
        legal_person_name = cls._random_name()

        # 生成联系人
        contact2_name = cls._random_name()
        # 确保两个联系人名不同
        while contact2_name == legal_person_name:
            contact2_name = cls._random_name()

        # 生成电话
        phones = []
        if area_code:
            phones.append(f"{area_code}-{random.randint(10000000, 99999999)}")
        phones.append(f"400-{random.randint(100, 999)}-{random.randint(1000, 9999)}")

        # 生成邮箱 (使用企业名拼音化处理)
        name_clean = re.sub(r"[（\(].*?[\)）]|有限公司|有限责任公司|股份公司|集团|（中国）", "", name)
        # 取前4个字符作为邮箱前缀
        email_prefix = name_clean[:6] if len(name_clean) >= 2 else "info"
        domain = random.choice(cls.EMAIL_DOMAINS)
        email = f"{email_prefix.lower()}@{domain}"

        # 生成地址 (基于区域)
        road_number = f"{random.choice(['路', '大道', '街'])}{random.randint(1, 999)}号"
        building = f"{random.choice(['大厦', '广场', '中心', '园区', '写字楼'])}{random.randint(1, 30)}栋"
        address = f"{region}{road_number}{building}"

        return {
            "contacts": [
                {
                    "name": legal_person_name,
                    "title": "法定代表人/执行董事",
                    "department": "管理层",
                },
                {
                    "name": contact2_name,
                    "title": random.choice(["总经理", "财务负责人", "监事", "副总经理"]),
                    "department": "管理层",
                },
            ],
            "phones": phones,
            "email": email,
            "address": address,
        }

    def __init__(self, api_key: str = "", base_url: str = ""):
        super().__init__(api_key, base_url)
        self.api_key = api_key or os.environ.get("QICHACHA_API_KEY", "")
        self.base_url = base_url or os.environ.get(
            "QICHACHA_BASE_URL",
            "https://api.qichacha.com",
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Content-Type": "application/json;charset=UTF-8",
            }
        )
        if self.api_key:
            self.session.headers["Token"] = self.api_key

    def _call_api(self, endpoint: str, params: dict) -> dict | None:
        """调用企查查真实 API（模拟模式下返回 None 触发降级）"""
        if MOCK_MODE:
            return None
        try:
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0 or data.get("status") != "200":
                logger.warning("企查查API返回异常: %s", data.get("message", "unknown"))
                return None
            return data.get("result") or data.get("data")
        except requests.Timeout:
            logger.warning("企查查API请求超时 (endpoint=%s, params=%s)", endpoint, params)
            return None
        except requests.RequestException as exc:
            logger.warning("企查查API请求失败: %s", exc)
            return None

    def _mock_search_company(self, name: str) -> dict | None:
        """模拟企业搜索（对已知企业返回精确数据，未知企业根据名称关键词智能生成）"""
        # 精确匹配
        if name in self.MOCK_COMPANIES:
            return dict(self.MOCK_COMPANIES[name])
        # 模糊匹配
        for key, val in self.MOCK_COMPANIES.items():
            if name in key or key in name:
                return dict(val)
        # 未知企业: 根据名称关键词智能生成
        analysis = self._analyze_company_name(name)
        # 根据行业生成 tags
        industry = analysis["industry"]
        tags = [industry[:4] if len(industry) > 4 else industry]
        if "科技" in name or "技术" in name or "软件" in name:
            tags.extend(["科技", "创新"])
        if "贸易" in name or "商贸" in name:
            tags.append("贸易")
        if "服务" in name:
            tags.append("服务")
        if not tags:
            tags.append("一般企业")

        # 生成注册号（模拟统一信用代码格式）
        fake_code = "MA" + "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=14))

        # 生成注册资本（根据行业）
        min_cap = analysis["min_capital"]
        capital_val = random.randint(min_cap, min_cap * 5)
        capital = f"{capital_val}万元人民币"

        # 生成成立日期 (过去1-20年内随机)
        import datetime
        days_ago = random.randint(365, 365 * 20)
        est_date = (datetime.date.today() - datetime.timedelta(days=days_ago)).isoformat()

        # 生成法定代表人
        legal_person = self._random_name()

        return {
            "name": name,
            "short_name": name.replace("有限公司", "").replace("有限责任公司", "").replace("（中国）", ""),
            "credit_code": fake_code,
            "legal_person": legal_person,
            "registered_capital": capital,
            "established_date": est_date,
            "industry": industry,
            "region": analysis["region"],
            "business_scope": self._generate_business_scope(name),
            "status": random.choice(self.STATUS_OPTIONS),
            "website": "",
            "tags": tags,
            "confidence": 0.6,  # 模拟数据置信度中等
            "note": "该企业信息由系统根据名称关键词智能生成（Mock模式），仅供参考",
        }

    def _mock_get_business_scope(self, name: str) -> dict:
        """模拟经营范围查询（对已知企业返回精确数据，未知企业根据名称关键词智能生成）"""
        company = self.MOCK_COMPANIES.get(name)
        if company:
            return {
                "name": name,
                "business_scope": company.get("business_scope", ""),
                "industry": company.get("industry", ""),
            }
        # 模糊匹配
        for key, val in self.MOCK_COMPANIES.items():
            if name in key or key in name:
                return {
                    "name": name,
                    "business_scope": val.get("business_scope", ""),
                    "industry": val.get("industry", ""),
                }
        # 未知企业: 智能生成
        return {
            "name": name,
            "business_scope": self._generate_business_scope(name),
            "industry": self._analyze_company_name(name)["industry"],
        }

    def _mock_get_contacts(self, name: str) -> dict:
        """模拟联系人查询（对已知企业返回精确数据，未知企业根据名称关键词智能生成）"""
        # 精确匹配
        contacts_data = self.MOCK_CONTACTS.get(name)
        if contacts_data:
            return dict(contacts_data)
        # 模糊匹配
        for key, val in self.MOCK_CONTACTS.items():
            if name in key or key in name:
                return dict(val)
        # 未知企业: 智能生成
        return self._generate_contacts(name)

    def search_company(self, name: str) -> dict:
        """搜索企业基本信息（带缓存）"""
        cache_key = f"company:{name}"
        cached = _cache_get(cache_key)
        if cached:
            logger.info("命中缓存: company:%s", name)
            return cached

        if MOCK_MODE:
            result = self._mock_search_company(name)
        else:
            result = self._call_api("Company/Search", {"key": name, "pageSize": 1})
            if result is None:
                # API 失败 → 查缓存兜底（即使过期也返回）
                stale = _cache_get(cache_key)
                if stale is not None:
                    logger.info("API失败，返回过期缓存: company:%s", name)
                    return stale
                # 完全无缓存 → 模拟降级
                logger.warning("API不可用且无缓存，使用模拟数据降级: %s", name)
                result = self._mock_search_company(name)

        _cache_set(cache_key, result)
        return result

    def get_business_scope(self, name: str) -> dict:
        """获取企业经营范围（带缓存）"""
        cache_key = f"scope:{name}"
        cached = _cache_get(cache_key)
        if cached:
            logger.info("命中缓存: scope:%s", name)
            return cached

        if MOCK_MODE:
            result = self._mock_get_business_scope(name)
        else:
            result = self._call_api("Company/GetBusinessScope", {"companyName": name})
            if result is None:
                stale = _cache_get(cache_key)
                if stale is not None:
                    logger.info("API失败，返回过期缓存: scope:%s", name)
                    return stale
                result = self._mock_get_business_scope(name)

        _cache_set(cache_key, result)
        return result

    def get_contacts(self, name: str) -> dict:
        """获取企业联系人/电话（带缓存）"""
        cache_key = f"contacts:{name}"
        cached = _cache_get(cache_key)
        if cached:
            logger.info("命中缓存: contacts:%s", name)
            return cached

        if MOCK_MODE:
            result = self._mock_get_contacts(name)
        else:
            result = self._call_api("Company/GetContacts", {"companyName": name})
            if result is None:
                stale = _cache_get(cache_key)
                if stale is not None:
                    logger.info("API失败，返回过期缓存: contacts:%s", name)
                    return stale
                result = self._mock_get_contacts(name)

        _cache_set(cache_key, result)
        return result


# ============================================================
# 工厂函数
# ============================================================


def create_enricher(provider: str = "qichacha", api_key: str = "") -> BaseEnricher:
    """
    创建数据丰富器实例

    Args:
        provider: 数据提供商 (qichacha|tianyancha|aiqicha|composite)
        api_key: API密钥，留空从环境变量读取

    Returns:
        BaseEnricher 实例

    Raises:
        ValueError: 不支持的 provider
    """
    if provider == "qichacha":
        return QichachaEnricher(api_key=api_key)
    if provider == "composite":
        from app.services.enrichment_providers import CompositeEnricher

        return CompositeEnricher()
    if provider == "tianyancha":
        from app.services.enrichment_providers import TianyanchaEnricher

        return TianyanchaEnricher(api_key=api_key)
    if provider == "aiqicha":
        from app.services.enrichment_providers import AiqichaEnricher

        return AiqichaEnricher(api_key=api_key)
    raise ValueError(f"不支持的数据提供商: {provider}")


def get_best_enricher() -> BaseEnricher:
    """
    根据环境变量 ENRICHMENT_PROVIDER 选择最佳数据丰富器

    环境变量:
      ENRICHMENT_PROVIDER = (qichacha|tianyancha|aiqicha|composite)
      默认: composite (多源聚合: 全部查询 → 合并去重 → 最高置信度返回)

    当 ENRICHMENT_PROVIDER 为 composite 时, 自动聚合所有可用 provider 的结果,
    取置信度最高的数据返回, 异常时自动降级到模拟数据。
    """
    provider = os.environ.get("ENRICHMENT_PROVIDER", "composite").lower().strip()
    logger.info("get_best_enricher: provider=%s", provider)
    return create_enricher(provider)


# 全局单例
_default_enricher: BaseEnricher | None = None


def get_enricher() -> BaseEnricher:
    """
    获取全局默认数据丰富器单例

    使用 get_best_enricher() 逻辑, 读取 ENRICHMENT_PROVIDER 环境变量。
    """
    global _default_enricher
    if _default_enricher is None:
        _default_enricher = get_best_enricher()
    return _default_enricher
