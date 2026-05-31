"""
企业公域信息采集引擎

从公开渠道采集企业工商信息，包含多策略降级：
1. 国家企业信用信息公示系统（gsxt.gov.cn）公开查询
2. 天眼查/企查查公开搜索页解析（免费，无需API KEY）
3. urllib + re 兜底（当 BeautifulSoup 不可用时）

注意：所有数据均来自公开渠道，仅用于企业信息补全辅助决策。
"""

import json
import logging
import re
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ============================================================
# 常量
# ============================================================
REQUEST_TIMEOUT = 15  # 单次请求超时秒数
CACHE_TTL = 86400  # 本地缓存有效期（秒）

# User-Agent 轮换池
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# ============================================================
# 公共工具
# ============================================================


def _get_headers() -> dict:
    """生成随机 User-Agent 的请求头"""
    import random

    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.baidu.com/",
    }


def _try_parse_json(text: str) -> dict | None:
    """尝试解析 JSON，失败返回 None"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


# ============================================================
# 策略1: BeautifulSoup + Requests（优先）
# ============================================================

try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("BeautifulSoup 未安装，将使用 urllib+re 兜底解析")


def _crawl_gsxt(name: str) -> dict | None:
    """从国家企业信用信息公示系统公开搜索页面采集企业信息

    注意：gsxt.gov.cn 有反爬措施，此策略可能失败，会降级到其他渠道。
    """
    try:
        url = f"https://www.gsxt.gov.cn/index.html"
        # GSXT 需要特殊的token获取，这里是简化实现
        # 实际项目中需要先获取cookie/token再搜索
        logger.info(f"GSXT 搜索企业: {name}")
        return None  # GSXT 目前走搜索跳转，暂无法直接解析
    except Exception as e:
        logger.debug(f"GSXT 采集失败 [{name}]: {e}")
        return None


def _crawl_tianyancha(name: str) -> dict | None:
    """从天眼查公开搜索页面采集企业信息

    解析天眼查搜索结果页的HTML，提取结构化信息。
    注意：天眼查有反爬机制，如返回验证码页面则跳过。
    """
    try:
        url = f"https://www.tianyancha.com/search?key={requests.utils.quote(name)}"
        resp = requests.get(url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        resp.encoding = "utf-8"

        if resp.status_code != 200:
            logger.debug(f"天眼查请求失败 [{name}]: HTTP {resp.status_code}")
            return None

        html = resp.text

        # 检测是否触发反爬（出现验证码/滑块等特征）
        if "验证码" in html or "antibot" in html or "captcha" in html.lower():
            logger.debug(f"天眼查触发反爬 [{name}]，跳过")
            return None

        result: dict[str, Any] = {"name": name, "data_source": "crawl", "confidence": 40}

        if BS4_AVAILABLE:
            soup = BeautifulSoup(html, "html.parser")

            # 尝试从搜索结果列表提取第一个企业卡片
            # 天眼查搜索结果中企业名称通常在 .search-result-single 或类似容器中
            result_items = soup.select(
                ".search-result-single, .result-item, .company-item, [class*='searchResult']"
            )
            if not result_items:
                # 也可能是直接跳转到企业详情页
                result_items = soup.select(
                    ".company-header, .detail-header, [class*='companyInfo']"
                )

            if result_items:
                item = result_items[0]
                text = item.get_text(separator="\n", strip=True)

                # 用正则提取各字段
                result.update(_extract_fields_from_text(text))

            # 尝试从页面 meta/script 中提取 JSON 数据
            for script in soup.select("script"):
                script_text = script.string or ""
                if "window.__NUXT__" in script_text or "__INITIAL_STATE__" in script_text:
                    # 尝试从 JS 变量中提取 JSON
                    json_match = re.search(r"window\.__NUXT__\s*=\s*({.*?});", script_text, re.DOTALL)
                    if json_match:
                        data = _try_parse_json(json_match.group(1))
                        if data:
                            result["_raw_json"] = json.dumps(data, ensure_ascii=False)
        else:
            # 兜底：纯正则提取
            result.update(_extract_fields_with_regex(html))

        # 至少要提取到部分数据才算成功
        has_data = any(
            k in result
            for k in ["credit_code", "legal_person", "industry", "registered_capital"]
        )
        if has_data:
            result["confidence"] = min(result.get("confidence", 40) + 10, 70)
            logger.info(f"天眼查采集成功 [{name}]: {json.dumps(result, ensure_ascii=False)}")
            return result

        logger.debug(f"天眼查未提取到有效数据 [{name}]")
        return None

    except requests.Timeout:
        logger.debug(f"天眼查超时 [{name}]")
        return None
    except requests.RequestException as e:
        logger.debug(f"天眼查网络错误 [{name}]: {e}")
        return None
    except Exception as e:
        logger.debug(f"天眼查解析错误 [{name}]: {e}")
        return None


def _crawl_qichacha(name: str) -> dict | None:
    """从企查查公开搜索页面采集企业信息"""
    try:
        url = f"https://www.qichacha.com/search?key={requests.utils.quote(name)}"
        resp = requests.get(url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        resp.encoding = "utf-8"

        if resp.status_code != 200:
            return None

        html = resp.text

        if "验证码" in html or "antibot" in html:
            logger.debug(f"企查查触发反爬 [{name}]，跳过")
            return None

        result: dict[str, Any] = {"name": name, "data_source": "crawl", "confidence": 40}

        if BS4_AVAILABLE:
            soup = BeautifulSoup(html, "html.parser")
            # 企查查搜索结果
            items = soup.select(
                ".search_result, .company-item, [class*='result-item'], [class*='companyInfo']"
            )
            if items:
                text = items[0].get_text(separator="\n", strip=True)
                result.update(_extract_fields_from_text(text))

            for script in soup.select("script"):
                script_text = script.string or ""
                if "__INITIAL_STATE__" in script_text or "window.__NUXT__" in script_text:
                    json_match = re.search(
                        r"window\.__NUXT__\s*=\s*({.*?});", script_text, re.DOTALL
                    )
                    if json_match:
                        data = _try_parse_json(json_match.group(1))
                        if data:
                            result["_raw_json"] = json.dumps(data, ensure_ascii=False)
        else:
            result.update(_extract_fields_with_regex(html))

        has_data = any(
            k in result
            for k in ["credit_code", "legal_person", "industry", "registered_capital"]
        )
        if has_data:
            result["confidence"] = min(result.get("confidence", 40) + 10, 70)
            logger.info(f"企查查采集成功 [{name}]: {json.dumps(result, ensure_ascii=False)}")
            return result

        return None

    except requests.Timeout:
        return None
    except requests.RequestException:
        return None
    except Exception as e:
        logger.debug(f"企查查解析错误 [{name}]: {e}")
        return None


# ============================================================
# 字段提取工具
# ============================================================


def _extract_fields_from_text(text: str) -> dict[str, Any]:
    """从纯文本中提取企业信息字段"""
    fields: dict[str, Any] = {}

    # 统一社会信用代码（18位数字+大写字母）
    credit_match = re.search(
        r"(统一社会信用代码[：:]\s*)?([0-9A-Z]{18})", text
    )
    if credit_match:
        fields["credit_code"] = credit_match.group(2)

    # 法定代表人
    legal_match = re.search(r"法定代表人[：:]\s*([^\s，,。]{2,8})", text)
    if legal_match:
        fields["legal_person"] = legal_match.group(1).strip()

    # 注册资本
    capital_match = re.search(r"注册资本[：:]\s*([^，,。\n]{2,30})", text)
    if capital_match:
        fields["registered_capital"] = capital_match.group(1).strip()

    # 成立日期
    date_match = re.search(
        r"(成立日期|成立时间)[：:]\s*(\d{4}[-年]\d{1,2}[-月]\d{1,2})", text
    )
    if date_match:
        raw = date_match.group(2)
        fields["established_date"] = raw.replace("年", "-").replace("月", "-")

    # 行业
    industry_match = re.search(r"(所属行业|行业)[：:]\s*([^\s，,。\n]{2,20})", text)
    if industry_match:
        fields["industry"] = industry_match.group(2).strip()

    # 地区
    region_match = re.search(
        r"(所在地区|登记机关|住所)[：:]\s*([^\s，,。]{2,30})", text
    )
    if region_match:
        fields["region"] = region_match.group(2).strip()

    # 经营范围
    scope_match = re.search(r"经营范围[：:]\s*([^。]{10,300})", text)
    if scope_match:
        fields["business_scope"] = scope_match.group(1).strip()

    # 企业简称（从名称中提取可能的前缀）
    if "name" in fields:
        name = fields["name"]
        # 简单规则：去除"有限公司"、"有限责任公司"等后缀
        short = re.sub(r"(有限公司|有限责任公司|股份公司|股份有限公司)$", "", name)
        if short and short != name:
            fields["short_name"] = short

    return fields


def _extract_fields_with_regex(html: str) -> dict[str, Any]:
    """纯正则兜底提取"""
    fields: dict[str, Any] = {}

    # 去除 HTML 标签获取纯文本
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text)

    return _extract_fields_from_text(text)


# ============================================================
# 百度企业信用/爱企查搜索（备用策略）
# ============================================================


def _crawl_baidu_enterprise(name: str) -> dict | None:
    """从百度搜索结果中获取企业信息"""
    try:
        url = f"https://www.baidu.com/s?wd={requests.utils.quote(name + ' 企业 信用代码')}"
        resp = requests.get(url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        resp.encoding = "utf-8"

        if resp.status_code != 200:
            return None

        html = resp.text
        fields: dict[str, Any] = {"name": name, "data_source": "crawl", "confidence": 30}

        if BS4_AVAILABLE:
            soup = BeautifulSoup(html, "html.parser")
            # 从搜索结果片段中提取
            result_blocks = soup.select(".result, .c-container, [class*='result']")
            for block in result_blocks:
                block_text = block.get_text(separator=" ", strip=True)
                extracted = _extract_fields_from_text(block_text)
                if extracted.get("credit_code") or extracted.get("legal_person"):
                    fields.update(extracted)
                    break
        else:
            fields.update(_extract_fields_with_regex(html))

        if fields.get("credit_code") or fields.get("legal_person"):
            fields["confidence"] = 35
            return fields

        return None

    except Exception as e:
        logger.debug(f"百度搜索采集失败 [{name}]: {e}")
        return None


# ============================================================
# 采集编排
# ============================================================

CRAWL_STRATEGIES = [
    ("gsxt", _crawl_gsxt),
    ("tianyancha", _crawl_tianyancha),
    ("qichacha", _crawl_qichacha),
    ("baidu", _crawl_baidu_enterprise),
]

# 内存缓存（进程级）
_crawl_cache: dict[str, tuple[float, dict]] = {}


def enrich_enterprise(name: str) -> dict:
    """根据企业名称，从公开渠道采集企业信息

    策略：
    1. 查本地内存缓存（避免短时间重复请求）
    2. 依次尝试各公开渠道
    3. 返回结构化数据

    Args:
        name: 企业全称

    Returns:
        dict: 结构化企业信息，至少包含 name 字段
    """
    name = name.strip()
    if not name:
        return {"name": "", "data_source": "manual", "confidence": 0}

    # 内存缓存检查
    now = time.time()
    if name in _crawl_cache:
        cached_time, cached_data = _crawl_cache[name]
        if now - cached_time < CACHE_TTL:
            logger.info(f"缓存命中 [{name}]")
            return dict(cached_data)  # 返回副本避免外部修改

    # 依次尝试各渠道
    best_result: dict | None = None
    best_confidence = 0

    for strategy_name, strategy_fn in CRAWL_STRATEGIES:
        try:
            result = strategy_fn(name)
            if result and result.get("confidence", 0) > best_confidence:
                best_result = result
                best_confidence = result.get("confidence", 0)
                logger.info(f"策略 [{strategy_name}] 返回数据，置信度={best_confidence}")

                # 如果置信度已足够高，提前终止
                if best_confidence >= 60:
                    break

            # 请求间短暂休眠，降低被封风险
            time.sleep(0.5)

        except Exception as e:
            logger.debug(f"策略 [{strategy_name}] 异常 [{name}]: {e}")
            continue

    # 合并结果
    if best_result:
        # 确保 name 字段准确
        best_result["name"] = name
        best_result.setdefault("data_source", "crawl")
        best_result.setdefault("confidence", 30)

        # 写缓存
        _crawl_cache[name] = (time.time(), dict(best_result))

        return best_result

    # 所有渠道均失败，返回最小结构
    fallback = {"name": name, "data_source": "manual", "confidence": 0}
    _crawl_cache[name] = (time.time(), dict(fallback))
    return fallback


def batch_enrich(names: list[str]) -> list[dict]:
    """批量补全企业信息

    Args:
        names: 企业名称列表

    Returns:
        list[dict]: 每个企业的结构化信息
    """
    results = []
    for i, name in enumerate(names):
        if not name or not name.strip():
            continue
        result = enrich_enterprise(name.strip())
        results.append(result)

        # 批量请求间增加间隔，降低反爬风险
        if i < len(names) - 1:
            time.sleep(0.3)

    return results


def crawl_enterprise_relations(enterprise_id: int, name: str) -> list[dict]:
    """采集企业关系图谱（股东/投资/竞品）

    Args:
        enterprise_id: 企业ID（本地数据库）
        name: 企业名称

    Returns:
        list[dict]: 关系列表，每项包含 target_name, relation_type, relation_label, confidence
    """
    relations: list[dict] = []

    # 尝试从天眼查/企查查的详情页采集关系
    for strategy_name, strategy_fn in [
        ("tianyancha", _crawl_tianyancha_relations),
        ("qichacha", _crawl_qichacha_relations),
    ]:
        try:
            result = strategy_fn(name)
            if result:
                relations.extend(result)
                break
        except Exception as e:
            logger.debug(f"关系采集 [{strategy_name}] 失败 [{name}]: {e}")
            continue

    return relations


def _crawl_tianyancha_relations(name: str) -> list[dict]:
    """从天眼查采集企业关系"""
    try:
        # 先搜企业，拿到企业ID或详情页链接
        search_url = f"https://www.tianyancha.com/search?key={requests.utils.quote(name)}"
        resp = requests.get(search_url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        resp.encoding = "utf-8"

        if resp.status_code != 200 or "验证码" in resp.text:
            return []

        # 从搜索页提取第一个企业的详情页链接
        detail_url = None
        if BS4_AVAILABLE:
            soup = BeautifulSoup(resp.text, "html.parser")
            # 天眼查搜索结果中的链接
            link = soup.select_one("a[href*='/company/'], a[href*='/firm/']")
            if link and link.get("href"):
                href = link["href"]
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = "https://www.tianyancha.com" + href
                detail_url = href

        if not detail_url:
            return []

        # 访问详情页
        detail_resp = requests.get(
            detail_url, headers=_get_headers(), timeout=REQUEST_TIMEOUT
        )
        detail_resp.encoding = "utf-8"

        if detail_resp.status_code != 200:
            return []

        html = detail_resp.text
        relations = []

        if BS4_AVAILABLE:
            soup = BeautifulSoup(html, "html.parser")

            # 提取股东信息
            holder_section = soup.select(
                "[class*='holder'], [class*='shareholder'], [class*='investment']"
            )
            for section in holder_section[:10]:
                text = section.get_text(separator=" ", strip=True)
                # 匹配 "XX公司 持股 XX%" 或 "XX公司 投资 XX万"
                rel_match = re.search(r"([^\s，,。]{2,30})\s*(持股|投资|控股)\s*([^\s，,。]{2,20})", text)
                if rel_match:
                    relations.append(
                        {
                            "target_name": rel_match.group(1).strip(),
                            "relation_type": "invest",
                            "relation_label": f"{rel_match.group(2)}{rel_match.group(3)}",
                            "confidence": 40,
                            "source": "crawl",
                        }
                    )

        return relations

    except Exception as e:
        logger.debug(f"天眼查关系采集失败 [{name}]: {e}")
        return []


def _crawl_qichacha_relations(name: str) -> list[dict]:
    """从企查查采集企业关系（实现同天眼查模式）"""
    # 简化实现：与天眼查模式相同，区别在于URL和选择器
    try:
        search_url = f"https://www.qichacha.com/search?key={requests.utils.quote(name)}"
        resp = requests.get(search_url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        resp.encoding = "utf-8"

        if resp.status_code != 200 or "验证码" in resp.text:
            return []

        return []

    except Exception as e:
        logger.debug(f"企查查关系采集失败 [{name}]: {e}")
        return []


# ============================================================
# 清理缓存（用于测试/管理）
# ============================================================


def clear_crawl_cache():
    """清空内存采集缓存"""
    _crawl_cache.clear()
    logger.info("企业采集缓存已清空")
