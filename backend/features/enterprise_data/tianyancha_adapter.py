"""
链客宝 - 天眼查企业数据API适配器
==================================
封装天眼查开放平台 API，提供统一的企业信息查询接口。

能力矩阵：
┌─────────────────┬─────────────────────────────────────────┐
│ 方法             │ 说明                                    │
├─────────────────┼─────────────────────────────────────────┤
│ get_basic_info  │ 企业基本信息（统一社会信用代码、法人等）│
│ get_shareholder │ 股东信息（股东名称、出资比例等）        │
│ get_business_status │ 经营状态（存续/在业/注销等）       │
└─────────────────┴─────────────────────────────────────────┘

设计原则：
1. 所有异常均不抛出，失败返回 None（调用方自行处理）
2. 无 API_KEY 时自动进入模拟模式，返回模拟数据用于开发
3. 统一使用 EnterpriseInfo 数据模型
4. 支持超时和限流保护

快速开始:
    from backend.features.enterprise_data import TianyanchaAdapter

    adapter = TianyanchaAdapter()
    info = adapter.get_basic_info("阿里巴巴")
    if info:
        print(info.legal_person, info.reg_capital)
"""

import json
import os
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 天眼查开放平台 API 地址
TIANYANCHA_BASE_URL = "https://open.api.tianyancha.com"
TIANYANCHA_SEARCH_URL = f"{TIANYANCHA_BASE_URL}/services/open/api/baseinfo/search"
TIANYANCHA_BASIC_URL = f"{TIANYANCHA_BASE_URL}/services/open/api/baseinfo/GetBasicInfo"
TIANYANCHA_SHAREHOLDER_URL = f"{TIANYANCHA_BASE_URL}/services/open/api/baseinfo/GetShareHolder"
TIANYANCHA_STATUS_URL = f"{TIANYANCHA_BASE_URL}/services/open/api/baseinfo/GetBusinessStatus"

DEFAULT_TIMEOUT = 10  # 请求超时（秒）
RATE_LIMIT_SLEEP = 0.5  # 限流休眠（秒）

# 环境变量名
ENV_API_KEY = "TIANYANCHA_API_KEY"

# 模拟数据缓存（避免每次重复创建）
_MOCK_DATA: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class EnterpriseInfo:
    """统一企业信息数据模型"""

    # 基本信息
    company_name: str = ""  # 企业名称
    credit_code: str = ""  # 统一社会信用代码
    legal_person: str = ""  # 法定代表人
    reg_capital: str = ""  # 注册资本
    reg_status: str = ""  # 登记状态（存续/在业/注销/吊销/迁入/迁出）
    established_date: str = ""  # 成立日期
    company_type: str = ""  # 企业类型
    address: str = ""  # 注册地址
    business_scope: str = ""  # 经营范围
    phone: str = ""  # 联系方式
    email: str = ""  # 邮箱

    # 股东信息（get_shareholder 填充）
    shareholders: list[dict[str, Any]] = field(default_factory=list)

    # 经营状态扩展（get_business_status 填充）
    business_status_detail: str = ""  # 经营状态详情
    risk_count: int = 0  # 风险数量

    # 元信息
    source: str = "tianyancha"
    raw_data: dict[str, Any] = field(default_factory=dict)
    fetched_at: str = ""

    def __post_init__(self) -> None:
        if not self.fetched_at:
            self.fetched_at = datetime.utcnow().isoformat() + "Z"

    @property
    def is_active(self) -> Optional[bool]:
        """企业是否处于存续/在业状态"""
        if not self.reg_status:
            return None
        return self.reg_status in ("存续", "在业")

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（去掉 raw_data 避免冗余）"""
        result = {}
        for k, v in self.__dict__.items():
            if k == "raw_data":
                continue
            result[k] = v
        return result


# ---------------------------------------------------------------------------
# 天眼查 API 适配器
# ---------------------------------------------------------------------------


class TianyanchaAdapter:
    """天眼查开放平台 API 适配器

    提供企业信息查询能力，支持模拟模式（无 API_KEY 时自动降级）。

    Usage:
        adapter = TianyanchaAdapter(api_key="your_key")
        # 或者从环境变量读取（不传参）
        adapter = TianyanchaAdapter()

        info = adapter.get_basic_info("阿里巴巴")
        if info:
            print(f"法人: {info.legal_person}")
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        """初始化适配器

        Args:
            api_key: 天眼查 API Key，不传则从环境变量 TIANYANCHA_API_KEY 读取。
                     环境变量未设置时自动进入模拟模式。
        """
        self._api_key = api_key or os.environ.get(ENV_API_KEY, "")
        self._mock_mode = not bool(self._api_key)
        self._last_request_time: float = 0.0

        if self._mock_mode:
            logger.info(
                "天眼查适配器: 模拟模式激活 "
                "(未检测到 %s 环境变量)", ENV_API_KEY
            )
        else:
            logger.info(
                "天眼查适配器: API 模式 (key=%s...)",
                self._api_key[:6] + "***" if len(self._api_key) > 6 else "***",
            )

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def get_basic_info(self, company_name: str) -> Optional[EnterpriseInfo]:
        """查询企业基本信息

        通过企业全称或关键字获取：统一社会信用代码、法定代表人、
        注册资本、成立日期、登记状态等。

        Args:
            company_name: 企业全称或关键字（如 "阿里巴巴"）

        Returns:
            EnterpriseInfo 对象，查询失败或无结果返回 None
        """
        if not company_name or not company_name.strip():
            logger.warning("天眼查: 企业名称为空")
            return None

        company_name = company_name.strip()

        if self._mock_mode:
            return self._mock_basic_info(company_name)

        try:
            self._rate_limit()
            params = {"keyword": company_name}
            resp_data = self._request("POST", TIANYANCHA_BASIC_URL, params=params)
            return self._parse_basic_info(resp_data, company_name)
        except Exception as exc:
            logger.error("天眼查 get_basic_info 异常: %s", exc)
            return None

    def get_shareholder(self, company_name: str) -> Optional[EnterpriseInfo]:
        """查询股东信息

        返回企业股东列表及其出资比例。

        Args:
            company_name: 企业全称或关键字

        Returns:
            EnterpriseInfo 对象（shareholders 字段包含股东列表），
            查询失败或无结果返回 None
        """
        if not company_name or not company_name.strip():
            logger.warning("天眼查: 企业名称为空")
            return None

        company_name = company_name.strip()

        if self._mock_mode:
            return self._mock_shareholder(company_name)

        try:
            self._rate_limit()
            params = {"keyword": company_name}
            resp_data = self._request(
                "POST", TIANYANCHA_SHAREHOLDER_URL, params=params
            )
            return self._parse_shareholder(resp_data, company_name)
        except Exception as exc:
            logger.error("天眼查 get_shareholder 异常: %s", exc)
            return None

    def get_business_status(self, company_name: str) -> Optional[EnterpriseInfo]:
        """查询企业经营状态

        获取企业当前经营状态详情及相关风险信息。

        Args:
            company_name: 企业全称或关键字

        Returns:
            EnterpriseInfo 对象（business_status_detail 和 risk_count 字段），
            查询失败或无结果返回 None
        """
        if not company_name or not company_name.strip():
            logger.warning("天眼查: 企业名称为空")
            return None

        company_name = company_name.strip()

        if self._mock_mode:
            return self._mock_business_status(company_name)

        try:
            self._rate_limit()
            params = {"keyword": company_name}
            resp_data = self._request(
                "POST", TIANYANCHA_STATUS_URL, params=params
            )
            return self._parse_business_status(resp_data, company_name)
        except Exception as exc:
            logger.error("天眼查 get_business_status 异常: %s", exc)
            return None

    @property
    def is_mock_mode(self) -> bool:
        """是否处于模拟模式"""
        return self._mock_mode

    # ------------------------------------------------------------------
    # 内部 HTTP 方法
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """发送 HTTP 请求到天眼查 API

        Args:
            method: HTTP 方法（仅支持 POST）
            url: API 端点
            params: 请求参数

        Returns:
            解析后的 JSON 数据，失败返回 None
        """
        try:
            import requests
        except ImportError:
            logger.error(
                "天眼查: requests 库未安装，请执行 pip install requests"
            )
            return None

        headers = {
            "Authorization": self._api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            if method.upper() == "POST":
                resp = requests.post(
                    url,
                    data=params or {},
                    headers=headers,
                    timeout=DEFAULT_TIMEOUT,
                )
            else:
                resp = requests.get(
                    url,
                    params=params or {},
                    headers=headers,
                    timeout=DEFAULT_TIMEOUT,
                )

            # 检查 HTTP 状态码
            if resp.status_code == 429:
                logger.warning("天眼查: 请求限流 (HTTP 429)")
                time.sleep(2)
                return None
            if resp.status_code == 403:
                logger.error("天眼查: API Key 无效或权限不足 (HTTP 403)")
                return None
            if resp.status_code == 404:
                logger.warning("天眼查: 接口不存在 (HTTP 404)")
                return None
            if resp.status_code != 200:
                logger.warning(
                    "天眼查: HTTP %s - %s", resp.status_code, resp.text[:200]
                )
                return None

            data = resp.json()

            # 天眼查返回码检查
            code = data.get("code")
            if code is None:
                logger.warning("天眼查: 响应缺少 code 字段")
                return None
            if code != 0 and code != 200:
                message = data.get("message", data.get("msg", "未知错误"))
                logger.warning(
                    "天眼查: API 返回错误 code=%s, msg=%s", code, message
                )
                if code in (400, 401):
                    logger.error("天眼查: API Key 可能无效，建议检查配置")
                return None

            return data.get("result") or data

        except requests.exceptions.Timeout:
            logger.error(
                "天眼查: 请求超时 (超过 %s 秒)", DEFAULT_TIMEOUT
            )
            return None
        except requests.exceptions.ConnectionError as exc:
            logger.error("天眼查: 网络连接失败 - %s", exc)
            return None
        except requests.exceptions.RequestException as exc:
            logger.error("天眼查: 请求异常 - %s", exc)
            return None
        except json.JSONDecodeError:
            logger.error("天眼查: 响应 JSON 解析失败")
            return None

    def _rate_limit(self) -> None:
        """简易限流：确保两次请求之间至少间隔 RATE_LIMIT_SLEEP 秒"""
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_SLEEP:
            time.sleep(RATE_LIMIT_SLEEP - elapsed)
        self._last_request_time = time.time()

    # ------------------------------------------------------------------
    # 响应解析
    # ------------------------------------------------------------------

    def _parse_basic_info(
        self,
        data: Optional[dict[str, Any]],
        company_name: str,
    ) -> Optional[EnterpriseInfo]:
        """解析企业基本信息响应"""
        if not data:
            logger.info("天眼查: %s 无查询结果", company_name)
            return None

        # 天眼查可能返回列表（搜索模式）
        items = data
        if isinstance(data, list):
            if not data:
                return None
            items = data[0] if isinstance(data[0], dict) else data
        if not isinstance(items, dict):
            return None

        return EnterpriseInfo(
            company_name=items.get("companyName") or items.get("name", company_name),
            credit_code=items.get("creditCode") or items.get("regNumber", ""),
            legal_person=items.get("legalPerson") or items.get("legalPersonName", ""),
            reg_capital=items.get("regCapital") or items.get("registerCapital", ""),
            reg_status=items.get("regStatus") or items.get("companyStatus", ""),
            established_date=items.get("establishedDate") or items.get("setupDate", ""),
            company_type=items.get("companyType") or items.get("companyOrgType", ""),
            address=items.get("address") or items.get("regAddress", ""),
            business_scope=items.get("businessScope") or "",
            phone=items.get("phone") or items.get("base", "phone", ""),
            email=items.get("email") or "",
            raw_data=items,
        )

    def _parse_shareholder(
        self,
        data: Optional[dict[str, Any]],
        company_name: str,
    ) -> Optional[EnterpriseInfo]:
        """解析股东信息响应"""
        if not data:
            logger.info("天眼查: %s 无股东信息", company_name)
            return None

        items = data
        if isinstance(data, list):
            if not data:
                return None
            items = data[0] if isinstance(data[0], dict) else data

        # 股东可能直接返回列表
        shareholders = []
        shareholder_data = items.get("shareholderList") or items.get("holders") or []

        if isinstance(shareholder_data, list):
            for sh in shareholder_data:
                shareholders.append({
                    "name": sh.get("name") or sh.get("shareholderName", ""),
                    "ratio": sh.get("ratio") or sh.get("fundRatio", ""),
                    "amount": sh.get("amount") or sh.get("shouldCapi", ""),
                    "date": sh.get("date") or sh.get("shareholderDate", ""),
                })

        return EnterpriseInfo(
            company_name=items.get("companyName") or company_name,
            shareholders=shareholders,
            raw_data=items,
        )

    def _parse_business_status(
        self,
        data: Optional[dict[str, Any]],
        company_name: str,
    ) -> Optional[EnterpriseInfo]:
        """解析经营状态响应"""
        if not data:
            logger.info("天眼查: %s 无经营状态信息", company_name)
            return None

        items = data
        if isinstance(data, list):
            if not data:
                return None
            items = data[0] if isinstance(data[0], dict) else data

        status_detail = items.get("businessStatus") or items.get("regStatus", "")
        risk_count = int(items.get("riskCount") or items.get("riskNum", 0))

        return EnterpriseInfo(
            company_name=items.get("companyName") or company_name,
            reg_status=items.get("regStatus", ""),
            business_status_detail=status_detail,
            risk_count=risk_count,
            raw_data=items,
        )

    # ------------------------------------------------------------------
    # 模拟数据（开发模式）
    # ------------------------------------------------------------------

    @staticmethod
    def _get_or_create_mock(name: str) -> dict[str, Any]:
        """获取或创建模拟数据集"""
        if name not in _MOCK_DATA:
            _MOCK_DATA[name] = _build_mock_data(name)
        return _MOCK_DATA[name]

    def _mock_basic_info(self, company_name: str) -> EnterpriseInfo:
        """模拟企业基本信息查询"""
        mock = self._get_or_create_mock(company_name)
        info = EnterpriseInfo(
            company_name=mock["company_name"],
            credit_code=mock["credit_code"],
            legal_person=mock["legal_person"],
            reg_capital=mock["reg_capital"],
            reg_status=mock["reg_status"],
            established_date=mock["established_date"],
            company_type=mock["company_type"],
            address=mock["address"],
            business_scope=mock["business_scope"],
            phone=mock["phone"],
            email=mock["email"],
            raw_data=mock,
        )
        logger.debug("天眼查[模拟]: get_basic_info(%s) -> %s", company_name, info.credit_code)
        return info

    def _mock_shareholder(self, company_name: str) -> EnterpriseInfo:
        """模拟股东信息查询"""
        mock = self._get_or_create_mock(company_name)
        info = EnterpriseInfo(
            company_name=mock["company_name"],
            shareholders=mock["shareholders"],
            raw_data=mock,
        )
        logger.debug("天眼查[模拟]: get_shareholder(%s) -> %s 位股东", company_name, len(info.shareholders))
        return info

    def _mock_business_status(self, company_name: str) -> EnterpriseInfo:
        """模拟经营状态查询"""
        mock = self._get_or_create_mock(company_name)
        info = EnterpriseInfo(
            company_name=mock["company_name"],
            reg_status=mock["reg_status"],
            business_status_detail="企业经营状态正常",
            risk_count=0,
            raw_data=mock,
        )
        logger.debug("天眼查[模拟]: get_business_status(%s) -> %s", company_name, info.reg_status)
        return info


# ---------------------------------------------------------------------------
# 模拟数据构建
# ---------------------------------------------------------------------------


def _build_mock_data(company_name: str) -> dict[str, Any]:
    """根据企业名称构建模拟数据集"""
    import hashlib

    # 用企业名 hash 生成伪唯一的信用代码/电话，让不同企业看起来不同
    h = hashlib.md5(company_name.encode("utf-8")).hexdigest()

    credit_code = f"91{h[:8].upper()}MA{h[8:12].upper()}ABCD"
    phone = f"138{h[:4]}0000"
    email = f"contact@{company_name}.com"

    return {
        "company_name": company_name,
        "credit_code": credit_code,
        "legal_person": f"张{h[0]}",
        "reg_capital": f"{hashlib.md5(company_name.encode()).digest()[0] % 9000 + 100}万元人民币",
        "reg_status": "存续",
        "established_date": "2010-03-15",
        "company_type": "有限责任公司",
        "address": f"北京市朝阳区{company_name}大厦",
        "business_scope": (
            "技术开发、技术咨询、技术服务；计算机系统服务；"
            "企业管理咨询；经济贸易咨询；会议服务；设计、制作、代理、发布广告。"
        ),
        "phone": phone,
        "email": email,
        "shareholders": [
            {
                "name": f"{company_name}科技集团有限公司",
                "ratio": "70%",
                "amount": "3500万元",
                "date": "2010-03-15",
            },
            {
                "name": f"杭州{company_name}投资合伙企业",
                "ratio": "30%",
                "amount": "1500万元",
                "date": "2015-06-01",
            },
        ],
    }


# ---------------------------------------------------------------------------
# 便利函数
# ---------------------------------------------------------------------------


def create_adapter(api_key: Optional[str] = None) -> TianyanchaAdapter:
    """创建天眼查适配器实例（便利函数）

    Args:
        api_key: 天眼查 API Key，不传则从环境变量读取

    Returns:
        TianyanchaAdapter 实例
    """
    return TianyanchaAdapter(api_key=api_key)


__all__ = [
    "EnterpriseInfo",
    "TianyanchaAdapter",
    "create_adapter",
]
