"""
企查查开放平台 API 客户端 (openapi.qichacha.com)

使用 AppKey + AppSecret 认证方式，提供企业信息查询能力：
  - 企业三要素核验（名称 + 统一社会信用代码 + 法定代表人）
  - 企业基本信息查询
  - 企业工商信息查询

环境变量:
    QICHACHA_APP_KEY      — AppKey（必填）
    QICHACHA_APP_SECRET   — AppSecret（必填）
    QICHACHA_BASE_URL     — API 基础地址（默认 https://openapi.qichacha.com）
    QICHACHA_TIMEOUT      — 请求超时秒数（默认 15）
    QICHACHA_CACHE_TTL    — 缓存 TTL（默认 86400 秒 = 24 小时）

使用示例:
    client = QichachaClient()
    # 三要素核验
    result = client.verify_enterprise("北京字节跳动科技有限公司", "91110108MA01BKLE31", "张一鸣")
    # 企业基本信息
    info = client.get_company_detail("91110108MA01BKLE31")
"""

import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ============================================================
# 常量
# ============================================================
DEFAULT_BASE_URL = "https://openapi.qichacha.com"
DEFAULT_TIMEOUT = 15  # 秒
DEFAULT_CACHE_TTL = 86400  # 默认缓存 TTL: 24 小时
VERIFY_CACHE_TTL = 86400  # 三要素核验缓存: 24 小时（企业信息不常变）
DETAIL_CACHE_TTL = 43200  # 企业详情缓存: 12 小时
LRU_CACHE_CAPACITY = 512  # LRU 缓存最大条目数


# ============================================================
# LRU 内存缓存（线程不安全，适用于单线程/异步场景）
# ============================================================

class LRUCache:
    """LRU 内存缓存，带 TTL 过期

    Attributes:
        capacity: 最大缓存条目数
        default_ttl: 默认过期时间（秒）
    """

    def __init__(self, capacity: int = LRU_CACHE_CAPACITY, default_ttl: int = DEFAULT_CACHE_TTL):
        self.capacity = capacity
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        """获取缓存项，过期或不存在返回 None"""
        if key not in self._cache:
            return None
        expired_at, value = self._cache[key]
        if time.time() > expired_at:
            del self._cache[key]
            return None
        # 移到末尾标记为最近使用
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """设置缓存项

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），默认使用 default_ttl
        """
        ttl = ttl if ttl is not None else self.default_ttl
        expired_at = time.time() + ttl
        self._cache[key] = (expired_at, value)
        self._cache.move_to_end(key)
        # LRU 淘汰：超出容量时移除最久未使用的条目
        while len(self._cache) > self.capacity:
            self._cache.popitem(last=False)

    def delete(self, key: str) -> None:
        """删除缓存项"""
        self._cache.pop(key, None)

    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()

    @property
    def size(self) -> int:
        """当前缓存条目数"""
        return len(self._cache)

    @property
    def keys(self) -> list[str]:
        """所有缓存键的列表"""
        return list(self._cache.keys())


# ============================================================
# 全局缓存实例（模块级单例）
# ============================================================
_cache = LRUCache(capacity=LRU_CACHE_CAPACITY, default_ttl=DEFAULT_CACHE_TTL)


# ============================================================
# 企查查 API 客户端
# ============================================================

class QichachaClient:
    """企查查开放平台 API 客户端

    使用 AppKey + AppSecret 签名认证。所有公开方法均有 try/except 兜底，
    异常时记录日志并返回包含 error 字段的 dict。
    """

    def __init__(
        self,
        app_key: str | None = None,
        app_secret: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        cache: LRUCache | None = None,
    ):
        """
        Args:
            app_key: AppKey，默认从环境变量 QICHACHA_APP_KEY 读取
            app_secret: AppSecret，默认从环境变量 QICHACHA_APP_SECRET 读取
            base_url: API 基础地址，默认从环境变量 QICHACHA_BASE_URL 或 DEFAULT_BASE_URL
            timeout: 请求超时秒数，默认从环境变量 QICHACHA_TIMEOUT 或 DEFAULT_TIMEOUT
            cache: 缓存实例，默认使用模块级全局缓存
        """
        self.app_key = app_key or os.environ.get("QICHACHA_APP_KEY", "")
        self.app_secret = app_secret or os.environ.get("QICHACHA_APP_SECRET", "")
        self.base_url = (base_url or os.environ.get("QICHACHA_BASE_URL", "") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout or int(os.environ.get("QICHACHA_TIMEOUT", str(DEFAULT_TIMEOUT)))
        self.cache = cache or _cache

        if not self.app_key or not self.app_secret:
            logger.warning(
                "企查查 API 未配置: 请设置 QICHACHA_APP_KEY 和 QICHACHA_APP_SECRET 环境变量"
            )

        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json;charset=UTF-8",
        })

    # --------------------------------------------------
    # 内部工具
    # --------------------------------------------------

    def _sign(self) -> str:
        """生成签名: MD5(AppKey + Timestamp + AppSecret)"""
        timestamp = str(int(time.time()))
        raw = f"{self.app_key}{timestamp}{self.app_secret}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()

    def _get_auth_headers(self) -> dict[str, str]:
        """生成认证请求头（企查查开放平台标准认证方式）"""
        timestamp = str(int(time.time()))
        sign = self._sign()
        return {
            "AppKey": self.app_key,
            "Time": timestamp,
            "Sign": sign,
        }

    def _request(self, endpoint: str, params: dict[str, Any] | None = None) -> dict | None:
        """向企查查 API 发送 GET 请求

        Args:
            endpoint: API 路径，如 /Company/GetCompanyDetail
            params: 查询参数

        Returns:
            解析后的 JSON data 字段，失败返回 None
        """
        if not self.app_key or not self.app_secret:
            logger.error("企查查 API 未配置凭据，无法发起请求")
            return None

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {**self._session.headers, **self._get_auth_headers()}

        try:
            resp = self._session.get(url, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(data)
        except requests.Timeout:
            logger.error("企查查 API 请求超时 [%s]: params=%s", endpoint, params)
            return None
        except requests.RequestException as e:
            logger.error("企查查 API 请求失败 [%s]: %s", endpoint, e)
            return None
        except json.JSONDecodeError as e:
            logger.error("企查查 API 返回非 JSON [%s]: %s", endpoint, e)
            return None

    @staticmethod
    def _parse_response(data: dict) -> dict | None:
        """解析企查查 API 统一响应格式

        企查查标准响应:
            {
                "Status": "200",       // 200 成功, 其他失败
                "Message": "成功",
                "Result": { ... },     // 业务数据（部分接口返回）
                "Paging": { ... }      // 分页信息（可选）
            }

        Returns:
            业务数据字段 (Result)，若 Status 非 200 返回 None
        """
        status = str(data.get("Status", ""))
        if status != "200":
            msg = data.get("Message", "未知错误")
            logger.warning("企查查 API 返回错误: Status=%s, Message=%s", status, msg)
            return None
        return data.get("Result") or data.get("result") or data

    # --------------------------------------------------
    # 缓存工具
    # --------------------------------------------------

    def _cache_key(self, prefix: str, *parts: str) -> str:
        """生成统一的缓存键"""
        return f"qichacha:{prefix}:{':'.join(parts)}"

    # --------------------------------------------------
    # 公开 API 方法
    # --------------------------------------------------

    def verify_enterprise(
        self,
        name: str,
        credit_code: str,
        legal_person: str,
    ) -> dict:
        """企业三要素核验

        核验企业名称、统一社会信用代码、法定代表人是否一致。

        Args:
            name: 企业名称
            credit_code: 统一社会信用代码（18 位）
            legal_person: 法定代表人姓名

        Returns:
            dict: {
                "verified": bool,       // 是否核验通过
                "match_score": int,     // 匹配分数 0-100
                "detail": str,          // 核验详情
                "raw_data": dict | None // 原始返回数据
            }
        """
        cache_key = self._cache_key("verify", credit_code)
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.info("三要素核验缓存命中 [%s]", credit_code)
            return dict(cached)  # 返回副本

        result = self._request("/Company/ThreeElementsVerify", {
            "companyName": name,
            "creditCode": credit_code,
            "legalPersonName": legal_person,
        })

        if result is None:
            fallback = {
                "verified": False,
                "match_score": 0,
                "detail": "企查查 API 暂不可用，无法完成核验",
                "raw_data": None,
            }
            return fallback

        # 解析核验结果
        # 企查查三要素核验返回通常包含: ResultType / Result / Description
        verified = str(result.get("ResultType", "")) == "1" or result.get("Result") is True
        detail = result.get("Description", "") or result.get("Message", "")

        verify_result = {
            "verified": verified,
            "match_score": 100 if verified else 0,
            "detail": detail or ("核验通过" if verified else "核验不通过"),
            "raw_data": result,
        }

        # 写入缓存（三要素结果缓存 24 小时）
        self.cache.set(cache_key, verify_result, ttl=VERIFY_CACHE_TTL)
        return verify_result

    def get_company_detail(self, credit_code: str) -> dict:
        """企业基本信息查询

        根据统一社会信用代码查询企业详细信息。

        Args:
            credit_code: 统一社会信用代码（18 位）

        Returns:
            dict: 企业基本信息，包含 name / credit_code / legal_person / registered_capital /
                  established_date / industry / region / business_scope / status 等字段
        """
        cache_key = self._cache_key("detail", credit_code)
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.info("企业详情缓存命中 [%s]", credit_code)
            return dict(cached)

        result = self._request("/Company/GetCompanyDetail", {
            "key": credit_code,
        })

        if result is None:
            return {
                "credit_code": credit_code,
                "error": "企查查 API 暂不可用",
                "data_source": "qichacha_api",
            }

        detail = self._normalize_company_detail(result, credit_code)
        self.cache.set(cache_key, detail, ttl=DETAIL_CACHE_TTL)
        return detail

    def get_company_base_info(self, credit_code: str) -> dict:
        """企业工商信息查询

        查询企业工商登记信息（注册资本、成立日期、经营范围、登记机关等）。

        Args:
            credit_code: 统一社会信用代码（18 位）

        Returns:
            dict: 企业工商信息
        """
        cache_key = self._cache_key("baseinfo", credit_code)
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.info("企业工商信息缓存命中 [%s]", credit_code)
            return dict(cached)

        result = self._request("/Company/GetCompanyBaseInfo", {
            "key": credit_code,
        })

        if result is None:
            return {
                "credit_code": credit_code,
                "error": "企查查 API 暂不可用",
                "data_source": "qichacha_api",
            }

        info = self._normalize_company_base_info(result, credit_code)
        self.cache.set(cache_key, info, ttl=DETAIL_CACHE_TTL)
        return info

    def search_by_name(self, name: str, page: int = 1, page_size: int = 20) -> dict:
        """按企业名称搜索

        Args:
            name: 企业名称（支持模糊搜索）
            page: 页码（默认 1）
            page_size: 每页条数（默认 20，最大 100）

        Returns:
            dict: {
                "items": list[dict],   // 企业列表
                "total": int,          // 总数
                "page": int,
                "page_size": int
            }
        """
        cache_key = self._cache_key("search", name, str(page), str(page_size))
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.info("企业搜索缓存命中 [%s]", name)
            return dict(cached)

        result = self._request("/Company/Search", {
            "key": name,
            "pageIndex": page,
            "pageSize": min(page_size, 100),
        })

        if result is None:
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "error": "企查查 API 暂不可用",
            }

        # 搜索返回通常在 Result 中有 List 字段
        items_raw = result.get("List") or result.get("list") or result.get("items") or []
        if isinstance(items_raw, dict):
            items_raw = [items_raw]

        items = []
        for item in items_raw:
            normalized = self._normalize_company_detail(item, item.get("CreditCode") or "")
            items.append(normalized)

        search_result = {
            "items": items,
            "total": result.get("Total") or result.get("total") or len(items),
            "page": page,
            "page_size": page_size,
        }

        self.cache.set(cache_key, search_result, ttl=DETAIL_CACHE_TTL)
        return search_result

    # --------------------------------------------------
    # 字段标准化
    # --------------------------------------------------

    @staticmethod
    def _normalize_company_detail(data: dict, credit_code: str) -> dict:
        """统一企查查返回字段名为项目标准命名"""
        return {
            "name": data.get("CompanyName")
                    or data.get("companyName")
                    or data.get("Name")
                    or data.get("name", ""),
            "short_name": data.get("ShortName")
                          or data.get("shortName")
                          or data.get("short_name", ""),
            "credit_code": data.get("CreditCode")
                           or data.get("creditCode")
                           or credit_code,
            "legal_person": data.get("LegalPerson")
                            or data.get("legalPerson")
                            or data.get("legal_person", ""),
            "registered_capital": data.get("RegCapital")
                                  or data.get("regCapital")
                                  or data.get("registered_capital", ""),
            "established_date": data.get("EstiblishTime")
                                or data.get("estiblishTime")
                                or data.get("established_date", ""),
            "industry": data.get("Industry")
                        or data.get("industry", ""),
            "region": data.get("Area")
                      or data.get("area")
                      or data.get("region", ""),
            "business_scope": data.get("BusinessScope")
                              or data.get("businessScope")
                              or data.get("business_scope", ""),
            "status": data.get("RegStatus")
                      or data.get("regStatus")
                      or data.get("status", ""),
            "website": data.get("Website")
                       or data.get("website", ""),
            "phone": data.get("Phone")
                     or data.get("phone", ""),
            "email": data.get("Email")
                     or data.get("email", ""),
            "address": data.get("Address")
                       or data.get("address", ""),
            "tags": data.get("Tags")
                    or data.get("tags")
                    or [],
            "data_source": "qichacha_api",
            "confidence": 90,
        }

    @staticmethod
    def _normalize_company_base_info(data: dict, credit_code: str) -> dict:
        """统一企查查工商信息返回字段"""
        return {
            "credit_code": data.get("CreditCode")
                           or data.get("creditCode")
                           or credit_code,
            "name": data.get("CompanyName")
                    or data.get("companyName")
                    or data.get("Name")
                    or data.get("name", ""),
            "legal_person": data.get("LegalPerson")
                            or data.get("legalPerson")
                            or data.get("legal_person", ""),
            "registered_capital": data.get("RegCapital")
                                  or data.get("regCapital")
                                  or data.get("registered_capital", ""),
            "paid_capital": data.get("PaidCapital")
                            or data.get("paidCapital")
                            or data.get("paid_capital", ""),
            "established_date": data.get("EstiblishTime")
                                or data.get("estiblishTime")
                                or data.get("established_date", ""),
            "status": data.get("RegStatus")
                      or data.get("regStatus")
                      or data.get("status", ""),
            "industry": data.get("Industry")
                        or data.get("industry", ""),
            "region": data.get("Area")
                      or data.get("area")
                      or data.get("region", ""),
            "business_scope": data.get("BusinessScope")
                              or data.get("businessScope")
                              or data.get("business_scope", ""),
            "registration_authority": data.get("RegistrationAuthority")
                                      or data.get("registrationAuthority", ""),
            "approved_date": data.get("ApprovedDate")
                             or data.get("approvedDate", ""),
            "taxpayer_qual": data.get("TaxpayerQual")
                             or data.get("taxpayerQual", ""),
            "enterprise_type": data.get("EnterpriseType")
                               or data.get("enterpriseType", ""),
            "data_source": "qichacha_api",
            "confidence": 90,
        }

    # --------------------------------------------------
    # 缓存管理
    # --------------------------------------------------

    def clear_cache(self) -> None:
        """清空所有缓存"""
        self.cache.clear()
        logger.info("企查查客户端缓存已清空")

    @property
    def cache_size(self) -> int:
        """当前缓存条目数"""
        return self.cache.size
