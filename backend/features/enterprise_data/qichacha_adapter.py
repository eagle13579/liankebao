"""
链客宝 - 企查查企业数据API适配器
==================================
封装企查查开放平台 API，提供统一的企业信息查询接口。

能力矩阵：
┌──────────────────────────┬─────────────────────────────────────┐
│ 方法                      │ 说明                                │
├──────────────────────────┼─────────────────────────────────────┤
│ get_credit_info          │ 企业信用信息（评级/风险/处罚）      │
│ get_abnormal_list        │ 经营异常列表                        │
│ get_intellectual_property│ 知识产权（商标/专利/软著）          │
└──────────────────────────┴─────────────────────────────────────┘

设计原则：
1. 所有异常均不抛出，失败返回 None（调用方自行处理）
2. 无 API_KEY 时自动进入模拟模式，返回模拟数据用于开发
3. 统一使用 EnterpriseInfo 数据模型
4. 支持超时和限流保护

快速开始:
    from backend.features.enterprise_data import QichachaAdapter

    adapter = QichachaAdapter()
    info = adapter.get_credit_info("阿里巴巴")
    if info:
        print(info.risk_count, info.business_status_detail)
"""

import json
import os
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .tianyancha_adapter import EnterpriseInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 企查查开放平台 API 地址（官方文档标准端点）
QICHACHA_BASE_URL = "https://openapi.qichacha.com"
QICHACHA_CREDIT_URL = f"{QICHACHA_BASE_URL}/Company/CreditInfo"
QICHACHA_ABNORMAL_URL = f"{QICHACHA_BASE_URL}/Company/AbnormalList"
QICHACHA_IP_URL = f"{QICHACHA_BASE_URL}/Company/IntellectualProperty"

DEFAULT_TIMEOUT = 10        # 请求超时（秒）
RATE_LIMIT_SLEEP = 0.5      # 限流休眠（秒）

# 环境变量名
ENV_API_KEY = "QICHACHA_API_KEY"

# 模拟数据缓存（避免每次重复创建）
_MOCK_DATA: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# 企查查 API 适配器
# ---------------------------------------------------------------------------


class QichachaAdapter:
    """企查查开放平台 API 适配器

    提供企业信用信息、经营异常、知识产权等查询能力，
    支持模拟模式（无 API_KEY 时自动降级）。

    Usage:
        adapter = QichachaAdapter(api_key="your_key")
        # 或者从环境变量读取（不传参）
        adapter = QichachaAdapter()

        info = adapter.get_credit_info("阿里巴巴")
        if info:
            print(f"风险数: {info.risk_count}")
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        """初始化适配器

        Args:
            api_key: 企查查 API Key，不传则从环境变量 QICHACHA_API_KEY 读取。
                     环境变量未设置时自动进入模拟模式。
        """
        self._api_key = api_key or os.environ.get(ENV_API_KEY, "")
        self._mock_mode = not bool(self._api_key)
        self._last_request_time: float = 0.0

        if self._mock_mode:
            logger.info(
                "企查查适配器: 模拟模式激活 "
                "(未检测到 %s 环境变量)", ENV_API_KEY
            )
        else:
            logger.info(
                "企查查适配器: API 模式 (key=%s...)",
                self._api_key[:6] + "***" if len(self._api_key) > 6 else "***",
            )

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def get_credit_info(self, company_name: str) -> Optional[EnterpriseInfo]:
        """查询企业信用信息

        获取企业信用评级、风险信息、行政处罚等数据。

        Args:
            company_name: 企业全称或关键字

        Returns:
            EnterpriseInfo 对象（business_status_detail, risk_count 等字段），
            查询失败或无结果返回 None
        """
        if not company_name or not company_name.strip():
            logger.warning("企查查: 企业名称为空")
            return None

        company_name = company_name.strip()

        if self._mock_mode:
            return self._mock_credit_info(company_name)

        try:
            self._rate_limit()
            params = {"keyword": company_name}
            resp_data = self._request("POST", QICHACHA_CREDIT_URL, params=params)
            return self._parse_credit_info(resp_data, company_name)
        except Exception as exc:
            logger.error("企查查 get_credit_info 异常: %s", exc)
            return None

    def get_abnormal_list(self, company_name: str) -> Optional[EnterpriseInfo]:
        """查询企业经营异常列表

        获取企业被列入经营异常名录的记录列表。

        Args:
            company_name: 企业全称或关键字

        Returns:
            EnterpriseInfo 对象（abnormal_records 字段包含异常列表），
            查询失败或无结果返回 None
        """
        if not company_name or not company_name.strip():
            logger.warning("企查查: 企业名称为空")
            return None

        company_name = company_name.strip()

        if self._mock_mode:
            return self._mock_abnormal_list(company_name)

        try:
            self._rate_limit()
            params = {"keyword": company_name}
            resp_data = self._request("POST", QICHACHA_ABNORMAL_URL, params=params)
            return self._parse_abnormal_list(resp_data, company_name)
        except Exception as exc:
            logger.error("企查查 get_abnormal_list 异常: %s", exc)
            return None

    def get_intellectual_property(self, company_name: str) -> Optional[EnterpriseInfo]:
        """查询企业知识产权信息

        获取企业拥有的商标、专利、软件著作权等知识产权数据。

        Args:
            company_name: 企业全称或关键字

        Returns:
            EnterpriseInfo 对象（ip_list 字段包含知识产权列表），
            查询失败或无结果返回 None
        """
        if not company_name or not company_name.strip():
            logger.warning("企查查: 企业名称为空")
            return None

        company_name = company_name.strip()

        if self._mock_mode:
            return self._mock_intellectual_property(company_name)

        try:
            self._rate_limit()
            params = {"keyword": company_name}
            resp_data = self._request("POST", QICHACHA_IP_URL, params=params)
            return self._parse_intellectual_property(resp_data, company_name)
        except Exception as exc:
            logger.error("企查查 get_intellectual_property 异常: %s", exc)
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
        """发送 HTTP 请求到企查查 API

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
                "企查查: requests 库未安装，请执行 pip install requests"
            )
            return None

        headers = {
            "Token": self._api_key,
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
                logger.warning("企查查: 请求限流 (HTTP 429)")
                time.sleep(2)
                return None
            if resp.status_code == 403:
                logger.error("企查查: API Key 无效或权限不足 (HTTP 403)")
                return None
            if resp.status_code == 404:
                logger.warning("企查查: 接口不存在 (HTTP 404)")
                return None
            if resp.status_code != 200:
                logger.warning(
                    "企查查: HTTP %s - %s", resp.status_code, resp.text[:200]
                )
                return None

            data = resp.json()

            # 企查查返回码检查
            code = data.get("code") or data.get("status")
            if code is None:
                logger.warning("企查查: 响应缺少 code/status 字段")
                return None
            if code != 0 and code != 200:
                message = data.get("message", data.get("msg", "未知错误"))
                logger.warning(
                    "企查查: API 返回错误 code=%s, msg=%s", code, message
                )
                if code in (400, 401):
                    logger.error("企查查: API Key 可能无效，建议检查配置")
                return None

            # 企查查数据通常在 result/data 字段中
            return data.get("result") or data.get("data") or data

        except requests.exceptions.Timeout:
            logger.error(
                "企查查: 请求超时 (超过 %s 秒)", DEFAULT_TIMEOUT
            )
            return None
        except requests.exceptions.ConnectionError as exc:
            logger.error("企查查: 网络连接失败 - %s", exc)
            return None
        except requests.exceptions.RequestException as exc:
            logger.error("企查查: 请求异常 - %s", exc)
            return None
        except json.JSONDecodeError:
            logger.error("企查查: 响应 JSON 解析失败")
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

    def _parse_credit_info(
        self,
        data: Optional[dict[str, Any]],
        company_name: str,
    ) -> Optional[EnterpriseInfo]:
        """解析企业信用信息响应"""
        if not data:
            logger.info("企查查: %s 无信用信息", company_name)
            return None

        items = data
        if isinstance(data, list):
            if not data:
                return None
            items = data[0] if isinstance(data[0], dict) else data
        if not isinstance(items, dict):
            return None

        # 企查查信用字段映射
        return EnterpriseInfo(
            company_name=items.get("companyName") or items.get("name", company_name),
            credit_code=items.get("creditCode") or items.get("creditCode", ""),
            legal_person=items.get("legalPerson") or items.get("legalPersonName", ""),
            reg_status=items.get("regStatus") or items.get("companyStatus", ""),
            business_status_detail=(
                items.get("creditRating")
                or items.get("creditLevel")
                or items.get("businessStatus", "")
            ),
            risk_count=int(
                items.get("riskCount")
                or items.get("riskNum")
                or items.get("punishCount", 0)
            ),
            raw_data=items,
        )

    def _parse_abnormal_list(
        self,
        data: Optional[dict[str, Any]],
        company_name: str,
    ) -> Optional[EnterpriseInfo]:
        """解析经营异常列表响应"""
        if not data:
            logger.info("企查查: %s 无经营异常记录", company_name)
            return None

        items = data
        if isinstance(data, list):
            if not data:
                return None
            items = data[0] if isinstance(data[0], dict) else data
        if not isinstance(items, dict):
            return None

        # 提取异常记录列表
        abnormal_records = []
        records = (
            items.get("abnormalList")
            or items.get("abnormalRecords")
            or items.get("list")
            or []
        )

        if isinstance(records, list):
            for rec in records:
                abnormal_records.append({
                    "put_date": rec.get("putDate") or rec.get("abnormalDate", ""),
                    "put_reason": rec.get("putReason") or rec.get("reason", ""),
                    "put_department": rec.get("putDepartment") or rec.get("department", ""),
                    "remove_date": rec.get("removeDate") or rec.get("removeDate", ""),
                    "remove_reason": rec.get("removeReason") or rec.get("removeReason", ""),
                })

        return EnterpriseInfo(
            company_name=items.get("companyName") or company_name,
            raw_data={"abnormal_records": abnormal_records, **items},
        )

    def _parse_intellectual_property(
        self,
        data: Optional[dict[str, Any]],
        company_name: str,
    ) -> Optional[EnterpriseInfo]:
        """解析知识产权信息响应"""
        if not data:
            logger.info("企查查: %s 无知识产权信息", company_name)
            return None

        items = data
        if isinstance(data, list):
            if not data:
                return None
            items = data[0] if isinstance(data[0], dict) else data
        if not isinstance(items, dict):
            return None

        # 提取知识产权列表
        ip_list = []

        # 商标
        trademarks = (
            items.get("trademarkList")
            or items.get("trademarks")
            or items.get("trademark", [])
        )
        if isinstance(trademarks, list):
            for tm in trademarks:
                ip_list.append({
                    "type": "trademark",
                    "name": tm.get("name") or tm.get("trademarkName", ""),
                    "reg_number": tm.get("regNumber") or tm.get("registrationNumber", ""),
                    "status": tm.get("status") or tm.get("trademarkStatus", ""),
                    "apply_date": tm.get("applyDate") or tm.get("applicationDate", ""),
                    "category": tm.get("category") or tm.get("intCls", ""),
                })

        # 专利
        patents = (
            items.get("patentList")
            or items.get("patents")
            or items.get("patent", [])
        )
        if isinstance(patents, list):
            for pt in patents:
                ip_list.append({
                    "type": "patent",
                    "name": pt.get("name") or pt.get("patentName", ""),
                    "reg_number": pt.get("regNumber") or pt.get("patentNumber", ""),
                    "status": pt.get("status") or pt.get("patentStatus", ""),
                    "apply_date": pt.get("applyDate") or pt.get("applicationDate", ""),
                    "type_detail": pt.get("type") or pt.get("patentType", ""),
                })

        # 软件著作权
        soft_copyrights = (
            items.get("copyrightList")
            or items.get("copyrights")
            or items.get("softwareCopyright", [])
        )
        if isinstance(soft_copyrights, list):
            for sc in soft_copyrights:
                ip_list.append({
                    "type": "software_copyright",
                    "name": sc.get("name") or sc.get("softwareName", ""),
                    "reg_number": sc.get("regNumber") or sc.get("registrationNumber", ""),
                    "status": sc.get("status") or sc.get("copyrightStatus", ""),
                    "apply_date": sc.get("applyDate") or sc.get("publishDate", ""),
                })

        return EnterpriseInfo(
            company_name=items.get("companyName") or company_name,
            raw_data={"ip_list": ip_list, **items},
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

    def _mock_credit_info(self, company_name: str) -> EnterpriseInfo:
        """模拟企业信用信息查询"""
        mock = self._get_or_create_mock(company_name)
        info = EnterpriseInfo(
            company_name=mock["company_name"],
            credit_code=mock["credit_code"],
            legal_person=mock["legal_person"],
            reg_status=mock["reg_status"],
            business_status_detail=mock["business_status_detail"],
            risk_count=mock["risk_count"],
            raw_data=mock,
        )
        logger.debug(
            "企查查[模拟]: get_credit_info(%s) -> 风险数=%s",
            company_name, info.risk_count,
        )
        return info

    def _mock_abnormal_list(self, company_name: str) -> EnterpriseInfo:
        """模拟经营异常列表查询"""
        mock = self._get_or_create_mock(company_name)
        info = EnterpriseInfo(
            company_name=mock["company_name"],
            raw_data={"abnormal_records": mock["abnormal_records"]},
        )
        logger.debug(
            "企查查[模拟]: get_abnormal_list(%s) -> %s 条异常记录",
            company_name, len(mock["abnormal_records"]),
        )
        return info

    def _mock_intellectual_property(self, company_name: str) -> EnterpriseInfo:
        """模拟知识产权信息查询"""
        mock = self._get_or_create_mock(company_name)
        info = EnterpriseInfo(
            company_name=mock["company_name"],
            raw_data={"ip_list": mock["ip_list"]},
        )
        logger.debug(
            "企查查[模拟]: get_intellectual_property(%s) -> %s 项知识产权",
            company_name, len(mock["ip_list"]),
        )
        return info


# ---------------------------------------------------------------------------
# 模拟数据构建
# ---------------------------------------------------------------------------


def _build_mock_data(company_name: str) -> dict[str, Any]:
    """根据企业名称构建模拟数据集"""
    import hashlib

    # 用企业名 hash 生成伪唯一标识
    h = hashlib.md5(company_name.encode("utf-8")).hexdigest()

    credit_code = f"91{h[:8].upper()}MA{h[8:12].upper()}ABCD"
    risk_count = int(h[0], 16) % 10  # 0-9 风险数

    return {
        "company_name": company_name,
        "credit_code": credit_code,
        "legal_person": f"王{h[0]}",
        "reg_status": "存续",
        "business_status_detail": f"信用评级: A{risk_count % 3 + 1}",
        "risk_count": risk_count,
        "abnormal_records": [
            {
                "put_date": "2022-03-15",
                "put_reason": "通过登记的住所或者经营场所无法联系",
                "put_department": "北京市市场监督管理局",
                "remove_date": "2022-06-20",
                "remove_reason": "依法办理住所或者经营场所变更登记",
            },
            {
                "put_date": "2021-01-10",
                "put_reason": "未依照《企业信息公示暂行条例》第八条规定的期限公示年度报告",
                "put_department": "北京市市场监督管理局",
                "remove_date": "2021-04-15",
                "remove_reason": "补报并公示年度报告",
            },
        ] if risk_count > 3 else [],
        "ip_list": [
            {
                "type": "trademark",
                "name": f"{company_name}®",
                "reg_number": f"商标注册第{h[:6]}号",
                "status": "已注册",
                "apply_date": "2018-05-10",
                "category": "第35类",
            },
            {
                "type": "trademark",
                "name": f"{company_name}图形",
                "reg_number": f"商标注册第{h[6:12]}号",
                "status": "已注册",
                "apply_date": "2019-02-20",
                "category": "第42类",
            },
            {
                "type": "patent",
                "name": "一种数据处理方法及系统",
                "reg_number": f"CN{h[:8]}123456.X",
                "status": "授权",
                "apply_date": "2020-08-15",
                "type_detail": "发明专利",
            },
            {
                "type": "software_copyright",
                "name": f"{company_name}综合管理平台V1.0",
                "reg_number": f"软著登字第{h[:6]}号",
                "status": "原始取得",
                "apply_date": "2021-11-01",
            },
        ],
    }


# ---------------------------------------------------------------------------
# 便利函数
# ---------------------------------------------------------------------------


def create_adapter(api_key: Optional[str] = None) -> QichachaAdapter:
    """创建企查查适配器实例（便利函数）

    Args:
        api_key: 企查查 API Key，不传则从环境变量读取

    Returns:
        QichachaAdapter 实例
    """
    return QichachaAdapter(api_key=api_key)


__all__ = [
    "EnterpriseInfo",
    "QichachaAdapter",
    "create_adapter",
]
