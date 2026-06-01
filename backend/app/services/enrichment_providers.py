"""
数据丰富多Provider真实API接入

提供:
  - TianyanchaEnricher: 天眼查API (https://openapi.tianyancha.com)
  - AiqichaEnricher:   爱企查API (https://openapi.aiqicha.com)
  - CompositeEnricher:  多源聚合 (请求所有provider, 合并去重, 取置信度最高的)

每个provider的 search_company / get_business_scope / get_contacts 均有
try/except兜底: 异常时若有缓存返回缓存, 无缓存返回模拟数据并标记"数据来源: 模拟"
"""

import logging
import os
import threading

import requests

from app.services.data_enrichment import (
    REQUEST_TIMEOUT,
    BaseEnricher,
    _cache_get,
    _cache_get_with_refresh_flag,
    _cache_set,
)

logger = logging.getLogger(__name__)


# ============================================================
# 天眼查 Enricher
# ============================================================


class TianyanchaEnricher(BaseEnricher):
    """
    天眼查数据丰富器 (https://openapi.tianyancha.com)

    环境变量:
      TIANYANCHA_API_KEY   — API密钥
      TIANYANCHA_BASE_URL  — API基础地址 (默认 https://openapi.tianyancha.com)
    """

    def __init__(self, api_key: str = "", base_url: str = ""):
        super().__init__(api_key, base_url)
        self.api_key = api_key or os.environ.get("TIANYANCHA_API_KEY", "")
        self.base_url = base_url or os.environ.get("TIANYANCHA_BASE_URL", "https://openapi.tianyancha.com")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
        )
        if self.api_key:
            self.session.headers["Authorization"] = self.api_key

    # ---- internal API call ----

    def _call_api(self, endpoint: str, params: dict) -> dict | None:
        """调用天眼查真实API，失败返回None"""
        try:
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("error_code") != 0:
                logger.warning(
                    "天眼查API返回异常: error_code=%s msg=%s", data.get("error_code"), data.get("message", "unknown")
                )
                return None
            return data.get("result")
        except requests.Timeout:
            logger.warning("天眼查API请求超时 (endpoint=%s)", endpoint)
            return None
        except requests.RequestException as exc:
            logger.warning("天眼查API请求失败: %s", exc)
            return None

    # ---- mock fallback ----

    def _mock_search_company(self, name: str) -> dict:
        return {
            "name": name,
            "credit_code": "模拟数据-天眼查-无统一信用代码",
            "legal_person": "未知",
            "registered_capital": "未知",
            "established_date": "未知",
            "industry": "未知",
            "region": "未知",
            "status": "未知",
            "website": "",
            "tags": [],
            "confidence": 0.1,
            "data_source": "模拟(天眼查)",
            "note": "天眼查API不可用，返回模拟数据",
        }

    def _mock_get_business_scope(self, name: str) -> dict:
        return {
            "name": name,
            "business_scope": "暂无经营范围数据",
            "industry": "未知",
            "data_source": "模拟(天眼查)",
        }

    def _mock_get_contacts(self, name: str) -> dict:
        return {
            "name": name,
            "contacts": [],
            "phones": [],
            "email": "",
            "address": "",
            "data_source": "模拟(天眼查)",
        }

    # ---- public methods ----

    def search_company(self, name: str) -> dict:
        cache_key = f"tianyancha:company:{name}"
        cached, needs_refresh = _cache_get_with_refresh_flag(cache_key)
        if cached is not None:
            if needs_refresh:
                _background_refresh(cache_key, lambda: self._do_search_company(name))
            return cached

        try:
            result = self._do_search_company(name)
        except Exception as exc:
            logger.error("天眼查search_company异常: %s", exc)
            stale = _cache_get(cache_key)
            if stale is not None:
                return stale
            result = self._mock_search_company(name)
            result["data_source"] = "模拟(天眼查-异常)"

        _cache_set(cache_key, result)
        return result

    def get_business_scope(self, name: str) -> dict:
        cache_key = f"tianyancha:scope:{name}"
        cached, needs_refresh = _cache_get_with_refresh_flag(cache_key)
        if cached is not None:
            if needs_refresh:
                _background_refresh(cache_key, lambda: self._do_get_business_scope(name))
            return cached

        try:
            result = self._do_get_business_scope(name)
        except Exception as exc:
            logger.error("天眼查get_business_scope异常: %s", exc)
            stale = _cache_get(cache_key)
            if stale is not None:
                return stale
            result = self._mock_get_business_scope(name)
            result["data_source"] = "模拟(天眼查-异常)"

        _cache_set(cache_key, result)
        return result

    def get_contacts(self, name: str) -> dict:
        cache_key = f"tianyancha:contacts:{name}"
        cached, needs_refresh = _cache_get_with_refresh_flag(cache_key)
        if cached is not None:
            if needs_refresh:
                _background_refresh(cache_key, lambda: self._do_get_contacts(name))
            return cached

        try:
            result = self._do_get_contacts(name)
        except Exception as exc:
            logger.error("天眼查get_contacts异常: %s", exc)
            stale = _cache_get(cache_key)
            if stale is not None:
                return stale
            result = self._mock_get_contacts(name)
            result["data_source"] = "模拟(天眼查-异常)"

        _cache_set(cache_key, result)
        return result

    # ---- actual API call wrappers (extracted for async refresh reuse) ----

    def _do_search_company(self, name: str) -> dict | None:
        result = self._call_api("companies/detail", {"keyword": name})
        if result is None:
            return None
        # 统一字段名
        return {
            "name": result.get("name", name),
            "short_name": result.get("shortName", ""),
            "credit_code": result.get("creditCode", ""),
            "legal_person": result.get("legalPerson", ""),
            "registered_capital": result.get("regCapital", ""),
            "established_date": result.get("estiblishTime", ""),
            "industry": result.get("industry", ""),
            "region": result.get("area", ""),
            "business_scope": result.get("businessScope", ""),
            "status": result.get("regStatus", ""),
            "website": result.get("website", ""),
            "tags": result.get("tags", []),
            "confidence": 0.85,
            "data_source": "天眼查",
        }

    def _do_get_business_scope(self, name: str) -> dict | None:
        result = self._call_api("companies/businessScope", {"keyword": name})
        if result is None:
            return None
        return {
            "name": name,
            "business_scope": result.get("businessScope", ""),
            "industry": result.get("industry", ""),
            "data_source": "天眼查",
        }

    def _do_get_contacts(self, name: str) -> dict | None:
        result = self._call_api("companies/contacts", {"keyword": name})
        if result is None:
            return None
        return {
            "name": name,
            "contacts": result.get("contacts", []),
            "phones": result.get("phones", []),
            "email": result.get("email", ""),
            "address": result.get("address", ""),
            "data_source": "天眼查",
        }


# ============================================================
# 爱企查 Enricher
# ============================================================


class AiqichaEnricher(BaseEnricher):
    """
    爱企查数据丰富器 (https://openapi.aiqicha.com)

    环境变量:
      AIQICHA_API_KEY   — API密钥
      AIQICHA_BASE_URL  — API基础地址 (默认 https://openapi.aiqicha.com)
    """

    def __init__(self, api_key: str = "", base_url: str = ""):
        super().__init__(api_key, base_url)
        self.api_key = api_key or os.environ.get("AIQICHA_API_KEY", "")
        self.base_url = base_url or os.environ.get("AIQICHA_BASE_URL", "https://openapi.aiqicha.com")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Content-Type": "application/json;charset=UTF-8",
            }
        )
        if self.api_key:
            self.session.headers["x-aiqicha-token"] = self.api_key

    # ---- internal API call ----

    def _call_api(self, endpoint: str, params: dict) -> dict | None:
        """调用爱企查真实API，失败返回None"""
        try:
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 200:
                logger.warning("爱企查API返回异常: code=%s msg=%s", data.get("code"), data.get("message", "unknown"))
                return None
            return data.get("data")
        except requests.Timeout:
            logger.warning("爱企查API请求超时 (endpoint=%s)", endpoint)
            return None
        except requests.RequestException as exc:
            logger.warning("爱企查API请求失败: %s", exc)
            return None

    # ---- mock fallback ----

    def _mock_search_company(self, name: str) -> dict:
        return {
            "name": name,
            "credit_code": "模拟数据-爱企查-无统一信用代码",
            "legal_person": "未知",
            "registered_capital": "未知",
            "established_date": "未知",
            "industry": "未知",
            "region": "未知",
            "status": "未知",
            "website": "",
            "tags": [],
            "confidence": 0.1,
            "data_source": "模拟(爱企查)",
            "note": "爱企查API不可用，返回模拟数据",
        }

    def _mock_get_business_scope(self, name: str) -> dict:
        return {
            "name": name,
            "business_scope": "暂无经营范围数据",
            "industry": "未知",
            "data_source": "模拟(爱企查)",
        }

    def _mock_get_contacts(self, name: str) -> dict:
        return {
            "name": name,
            "contacts": [],
            "phones": [],
            "email": "",
            "address": "",
            "data_source": "模拟(爱企查)",
        }

    # ---- public methods ----

    def search_company(self, name: str) -> dict:
        cache_key = f"aiqicha:company:{name}"
        cached, needs_refresh = _cache_get_with_refresh_flag(cache_key)
        if cached is not None:
            if needs_refresh:
                _background_refresh(cache_key, lambda: self._do_search_company(name))
            return cached

        try:
            result = self._do_search_company(name)
        except Exception as exc:
            logger.error("爱企查search_company异常: %s", exc)
            stale = _cache_get(cache_key)
            if stale is not None:
                return stale
            result = self._mock_search_company(name)
            result["data_source"] = "模拟(爱企查-异常)"

        _cache_set(cache_key, result)
        return result

    def get_business_scope(self, name: str) -> dict:
        cache_key = f"aiqicha:scope:{name}"
        cached, needs_refresh = _cache_get_with_refresh_flag(cache_key)
        if cached is not None:
            if needs_refresh:
                _background_refresh(cache_key, lambda: self._do_get_business_scope(name))
            return cached

        try:
            result = self._do_get_business_scope(name)
        except Exception as exc:
            logger.error("爱企查get_business_scope异常: %s", exc)
            stale = _cache_get(cache_key)
            if stale is not None:
                return stale
            result = self._mock_get_business_scope(name)
            result["data_source"] = "模拟(爱企查-异常)"

        _cache_set(cache_key, result)
        return result

    def get_contacts(self, name: str) -> dict:
        cache_key = f"aiqicha:contacts:{name}"
        cached, needs_refresh = _cache_get_with_refresh_flag(cache_key)
        if cached is not None:
            if needs_refresh:
                _background_refresh(cache_key, lambda: self._do_get_contacts(name))
            return cached

        try:
            result = self._do_get_contacts(name)
        except Exception as exc:
            logger.error("爱企查get_contacts异常: %s", exc)
            stale = _cache_get(cache_key)
            if stale is not None:
                return stale
            result = self._mock_get_contacts(name)
            result["data_source"] = "模拟(爱企查-异常)"

        _cache_set(cache_key, result)
        return result

    # ---- actual API call wrappers ----

    def _do_search_company(self, name: str) -> dict | None:
        result = self._call_api("company/detail", {"companyName": name})
        if result is None:
            return None
        return {
            "name": result.get("companyName", name),
            "short_name": result.get("shortName", ""),
            "credit_code": result.get("creditCode", ""),
            "legal_person": result.get("legalPerson", ""),
            "registered_capital": result.get("regCapital", ""),
            "established_date": result.get("establishDate", ""),
            "industry": result.get("industry", ""),
            "region": result.get("area", ""),
            "business_scope": result.get("businessScope", ""),
            "status": result.get("companyStatus", ""),
            "website": result.get("website", ""),
            "tags": result.get("tags", []),
            "confidence": 0.85,
            "data_source": "爱企查",
        }

    def _do_get_business_scope(self, name: str) -> dict | None:
        result = self._call_api("company/businessScope", {"companyName": name})
        if result is None:
            return None
        return {
            "name": name,
            "business_scope": result.get("businessScope", ""),
            "industry": result.get("industry", ""),
            "data_source": "爱企查",
        }

    def _do_get_contacts(self, name: str) -> dict | None:
        result = self._call_api("company/contacts", {"companyName": name})
        if result is None:
            return None
        return {
            "name": name,
            "contacts": result.get("contacts", []),
            "phones": result.get("phones", []),
            "email": result.get("email", ""),
            "address": result.get("address", ""),
            "data_source": "爱企查",
        }


# ============================================================
# 多源聚合 CompositeEnricher
# ============================================================


class CompositeEnricher(BaseEnricher):
    """
    多源聚合数据丰富器

    请求所有注册的provider, 合并去重, 返回置信度最高的结果。
    如果所有provider都失败, 返回模拟数据并标记"数据来源: 模拟"。

    默认providers: [QichachaEnricher, TianyanchaEnricher, AiqichaEnricher]
    """

    def __init__(self, providers: list[BaseEnricher] | None = None):
        super().__init__()
        self._providers = providers  # 延迟加载, 避免循环导入

    def _get_providers(self) -> list[BaseEnricher]:
        """懒加载默认providers (避免模块级别循环导入)"""
        if self._providers is None:
            from app.services.data_enrichment import QichachaEnricher

            self._providers = [
                QichachaEnricher(),
                TianyanchaEnricher(),
                AiqichaEnricher(),
            ]
        return self._providers

    # ---- search_company ----

    def search_company(self, name: str) -> dict:
        """多源聚合搜索: 请求所有provider, 取置信度最高的"""
        cache_key = f"composite:company:{name}"
        cached, needs_refresh = _cache_get_with_refresh_flag(cache_key)
        if cached is not None:
            if needs_refresh:
                _background_refresh(cache_key, lambda: self._do_search_company(name))
            return cached

        try:
            result = self._do_search_company(name)
        except Exception as exc:
            logger.error("CompositeEnricher search_company 异常: %s", exc)
            stale = _cache_get(cache_key)
            if stale is not None:
                return stale
            result = self._mock_data(name, "search_company")

        if result is None:
            result = self._mock_data(name, "search_company")

        _cache_set(cache_key, result)
        return result

    def _do_search_company(self, name: str) -> dict | None:
        """调用所有provider搜索并取最佳结果"""
        results = []
        for provider in self._get_providers():
            try:
                r = provider.search_company(name)
                if r and r.get("confidence", 0) > 0:
                    results.append(r)
            except Exception as exc:
                logger.warning("Composite provider异常 (%s): %s", type(provider).__name__, exc)

        if not results:
            return None

        best = max(results, key=lambda r: r.get("confidence", 0))
        merged = dict(best)
        merged["data_source"] = "多源聚合"
        merged["_sources"] = [r.get("data_source", "未知") for r in results]
        return merged

    # ---- get_business_scope ----

    def get_business_scope(self, name: str) -> dict:
        """多源聚合获取经营范围"""
        cache_key = f"composite:scope:{name}"
        cached, needs_refresh = _cache_get_with_refresh_flag(cache_key)
        if cached is not None:
            if needs_refresh:
                _background_refresh(cache_key, lambda: self._do_get_business_scope(name))
            return cached

        try:
            result = self._do_get_business_scope(name)
        except Exception as exc:
            logger.error("CompositeEnricher get_business_scope 异常: %s", exc)
            stale = _cache_get(cache_key)
            if stale is not None:
                return stale
            result = self._mock_data(name, "get_business_scope")

        if result is None:
            result = self._mock_data(name, "get_business_scope")

        _cache_set(cache_key, result)
        return result

    def _do_get_business_scope(self, name: str) -> dict | None:
        """调用所有provider获取经营范围, 取最长最详细的"""
        results = []
        for provider in self._get_providers():
            try:
                r = provider.get_business_scope(name)
                if r and r.get("business_scope"):
                    results.append(r)
            except Exception as exc:
                logger.warning("Composite scope provider异常 (%s): %s", type(provider).__name__, exc)

        if not results:
            return None

        # 取经营范围字符串最长的作为最佳
        best = max(results, key=lambda r: len(r.get("business_scope", "") or ""))
        merged = dict(best)
        merged["data_source"] = "多源聚合"
        return merged

    # ---- get_contacts ----

    def get_contacts(self, name: str) -> dict:
        """多源聚合获取联系人"""
        cache_key = f"composite:contacts:{name}"
        cached, needs_refresh = _cache_get_with_refresh_flag(cache_key)
        if cached is not None:
            if needs_refresh:
                _background_refresh(cache_key, lambda: self._do_get_contacts(name))
            return cached

        try:
            result = self._do_get_contacts(name)
        except Exception as exc:
            logger.error("CompositeEnricher get_contacts 异常: %s", exc)
            stale = _cache_get(cache_key)
            if stale is not None:
                return stale
            result = self._mock_data(name, "get_contacts")

        if result is None:
            result = self._mock_data(name, "get_contacts")

        _cache_set(cache_key, result)
        return result

    def _do_get_contacts(self, name: str) -> dict | None:
        """调用所有provider获取联系人, 合并去重"""
        all_contacts: list[dict] = []
        all_phones: set[str] = set()
        email = ""
        address = ""

        for provider in self._get_providers():
            try:
                r = provider.get_contacts(name)
                if r:
                    all_contacts.extend(r.get("contacts", []))
                    all_phones.update(r.get("phones", []))
                    if not email and r.get("email"):
                        email = r["email"]
                    if not address and r.get("address"):
                        address = r["address"]
            except Exception as exc:
                logger.warning("Composite contacts provider异常 (%s): %s", type(provider).__name__, exc)

        if not all_contacts and not all_phones:
            return None

        merged = {
            "name": name,
            "contacts": self._deduplicate_contacts(all_contacts),
            "phones": sorted(all_phones),
            "email": email,
            "address": address,
            "data_source": "多源聚合",
        }
        return merged

    # ---- helpers ----

    def _mock_data(self, name: str, method: str) -> dict:
        """返回模拟降级数据"""
        if method == "search_company":
            return {
                "name": name,
                "credit_code": "模拟数据-多源聚合-无数据",
                "legal_person": "未知",
                "registered_capital": "未知",
                "established_date": "未知",
                "industry": "未知",
                "region": "未知",
                "status": "未知",
                "website": "",
                "tags": [],
                "confidence": 0.1,
                "data_source": "模拟(多源聚合-所有provider均不可用)",
            }
        elif method == "get_business_scope":
            return {
                "name": name,
                "business_scope": "暂无经营范围数据",
                "industry": "未知",
                "data_source": "模拟(多源聚合-所有provider均不可用)",
            }
        else:
            return {
                "name": name,
                "contacts": [],
                "phones": [],
                "email": "",
                "address": "",
                "data_source": "模拟(多源聚合-所有provider均不可用)",
            }

    @staticmethod
    def _deduplicate_contacts(contacts: list[dict]) -> list[dict]:
        """联系人按 name 去重"""
        seen: set[str] = set()
        unique = []
        for c in contacts:
            cname = c.get("name", "")
            if cname and cname not in seen:
                seen.add(cname)
                unique.append(c)
            elif not cname:
                unique.append(c)
        return unique


# ============================================================
# 后台异步刷新辅助
# ============================================================


def _background_refresh(cache_key: str, refresh_func, timeout: int = 30):
    """
    在后台守护线程中刷新缓存, 不影响当前请求响应

    Args:
        cache_key: 缓存键
        refresh_func: 无参可调用对象, 返回值将写入缓存
        timeout: 单个刷新操作的超时(秒)
    """

    def _do_refresh():
        try:
            result = refresh_func()
            if result is not None:
                _cache_set(cache_key, result)
                logger.info("异步缓存刷新完成: %s", cache_key)
            else:
                logger.info("异步缓存刷新无新数据, 保留旧缓存: %s", cache_key)
        except Exception as exc:
            logger.warning("异步缓存刷新失败 (%s): %s", cache_key, exc)

    t = threading.Thread(target=_do_refresh, daemon=True, name=f"cache-refresh-{cache_key[:30]}")
    t.start()
