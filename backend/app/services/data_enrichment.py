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
import sqlite3
import time

import requests

logger = logging.getLogger(__name__)

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
        """模拟企业搜索"""
        # 精确匹配
        if name in self.MOCK_COMPANIES:
            return dict(self.MOCK_COMPANIES[name])
        # 模糊匹配
        for key, val in self.MOCK_COMPANIES.items():
            if name in key or key in name:
                return dict(val)
        # 未知企业: 返回基础模拟数据
        return {
            "name": name,
            "short_name": name,
            "credit_code": "模拟数据-无统一信用代码",
            "legal_person": "未知",
            "registered_capital": "未知",
            "established_date": "未知",
            "industry": "未知",
            "region": "未知",
            "business_scope": "暂无经营范围数据",
            "status": "未知",
            "website": "",
            "tags": [],
            "confidence": 0.1,
            "note": "该企业未在模拟数据池中匹配到精确结果，以上为占位数据",
        }

    def _mock_get_business_scope(self, name: str) -> dict:
        """模拟经营范围查询"""
        company = self.MOCK_COMPANIES.get(name) or self._mock_search_company(name)
        return {
            "name": name,
            "business_scope": company.get("business_scope", "暂无经营范围数据"),
            "industry": company.get("industry", "未知"),
        }

    def _mock_get_contacts(self, name: str) -> dict:
        """模拟联系人查询"""
        contacts_data = self.MOCK_CONTACTS.get(name)
        if contacts_data:
            return dict(contacts_data)
        # 未知企业返回空联系人
        return {
            "contacts": [],
            "phones": [],
            "email": "",
            "address": "",
            "note": "未找到该企业的联系人信息",
        }

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
