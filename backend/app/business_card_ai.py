"""
链客宝AI AI 名片引擎模块
=======================
管线: 上传扫描 → AI字段提取 → 生成数字名片 → 供需匹配

功能:
  1. scan_card(image_path) — 用 pdfplumber/PIL 提取名片图片文字(OCR)
  2. extract_fields(text) — NLP 从名片文本提取字段
  3. generate_digital_card(fields) — 生成 JSON 数字名片数据结构
  4. match_supply_demand(card_data) — 用 matching_engine 匹配供需
"""

import json
import logging
import os
import re
import secrets
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# 名片字段定义
# ============================================================
CARD_FIELDS = [
    "name",  # 姓名
    "position",  # 职位
    "company",  # 公司
    "phone",  # 手机
    "email",  # 邮箱
    "wechat",  # 微信
    "address",  # 地址
    "website",  # 官网
]

# ============================================================
# 1. 扫描名片 — 文字提取
# ============================================================


def scan_card(image_path: str) -> str:
    """从名片图片/PDF中提取文字

    支持:
      - PDF 文件 → pdfplumber 逐页提取
      - 图片文件 → 模拟 OCR（实际项目中可对接百度OCR/Tesseract/DeepSeek Vision）

    Args:
        image_path: 名片文件路径

    Returns:
        提取的纯文本内容
    """
    if not os.path.isfile(image_path):
        logger.warning(f"名片文件不存在: {image_path}")
        return ""

    ext = os.path.splitext(image_path)[1].lower()

    # --- PDF 提取 ---
    if ext == ".pdf":
        try:
            import pdfplumber

            text_parts = []
            with pdfplumber.open(image_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text.strip())
            full_text = "\n".join(text_parts)
            logger.info(f"PDF 名片提取完成: {len(full_text)} chars from {len(pdf.pages)} pages")
            return full_text
        except Exception as e:
            logger.error(f"PDF 提取失败: {e}", exc_info=True)
            return ""

    # --- 图片提取（模拟 OCR / 实际可对接 API）---
    if ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"):
        try:
            # 优先使用 DeepSeek API 进行 OCR
            text = _ocr_with_deepseek(image_path)
            if text:
                return text

            # 降级：使用本地 OCR（pytesseract 可选）
            text = _ocr_with_tesseract(image_path)
            if text:
                return text

            # 最终降级：返回占位提示
            logger.warning(f"名片图片 OCR 未返回结果: {image_path}")
            return "[OCR 暂未返回文字，请手动输入名片信息]"
        except Exception as e:
            logger.error(f"图片 OCR 异常: {e}", exc_info=True)
            return "[OCR 处理失败，请手动输入名片信息]"

    logger.warning(f"不支持的文件格式: {ext}")
    return ""


def _ocr_with_deepseek(image_path: str) -> str:
    """使用模拟 DeepSeek API 进行名片 OCR

    实际项目中替换为真实的 DeepSeek Vision API 调用:
      - 上传图片到 DeepSeek API
      - 使用 prompt: "请识别这张名片上的所有文字信息"
      - 返回结构化文本

    当前实现: 返回空字符串触发降级
    """
    try:
        # === 真实对接代码（注释保留参考）===
        # import requests
        # api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        # if not api_key:
        #     return ""
        # with open(image_path, "rb") as f:
        #     files = {"image": f}
        #     resp = requests.post(
        #         "https://api.deepseek.com/v1/vision/ocr",
        #         headers={"Authorization": f"Bearer {api_key}"},
        #         files=files,
        #         timeout=30,
        #     )
        # if resp.ok:
        #     return resp.json().get("text", "")

        # 当前：使用 pdfplumber/PIL 提取（如果是图片就返回空，让 tesseract 处理）
        return ""
    except Exception as e:
        logger.debug(f"DeepSeek OCR 不可用: {e}")
        return ""


def _ocr_with_tesseract(image_path: str) -> str:
    """使用 Tesseract OCR（可选依赖）

    需要安装:
      - pip install pytesseract
      - 系统安装 Tesseract (https://github.com/tesseract-ocr/tesseract)

    Returns:
        识别文本，若不可用返回空字符串
    """
    try:
        import pytesseract
        from PIL import Image

        # 尝试设置 tesseract 路径（Windows 常见路径）
        _possible_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
        ]
        for p in _possible_paths:
            if os.path.isfile(p):
                pytesseract.pytesseract.tesseract_cmd = p
                break

        img = Image.open(image_path)
        # 增强图片：转灰度+二值化提升OCR准确率
        img = img.convert("L")  # 灰度
        # 使用中文+英文语言包
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
        text = text.strip()
        if text:
            logger.info(f"Tesseract OCR 提取 {len(text)} chars")
        return text
    except ImportError:
        logger.debug("pytesseract 未安装，跳过本地 OCR")
        return ""
    except Exception as e:
        logger.debug(f"Tesseract OCR 失败: {e}")
        return ""


# ============================================================
# 2. NLP 字段提取
# ============================================================


def extract_fields(text: str) -> dict[str, str | None]:
    """从名片文本中提取结构化字段

    使用规则+正则 NLP 方式提取:
      - 手机号: 1xx-xxxx-xxxx / 1xxxxxxxxxx
      - 邮箱: xxx@xxx.xxx
      - 微信: wechat/微信号/微信ID
      - 网址: http(s)://... / xxx.com / xxx.cn
      - 姓名: 文本第一行或第二行（常用中文名模式）
      - 职位: 常见职位关键词
      - 公司: 常见公司后缀
      - 地址: 省市区关键词

    Args:
        text: OCR 提取的原始文本

    Returns:
        字段字典 {field: value or None}
    """
    if not text or not text.strip():
        return {f: None for f in CARD_FIELDS}

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    full_text = " ".join(lines)

    result: dict[str, str | None] = {}

    # --- 手机号 ---
    phone = _extract_phone(full_text)
    result["phone"] = phone

    # --- 邮箱 ---
    email = _extract_email(full_text)
    result["email"] = email

    # --- 微信 ---
    wechat = _extract_wechat(full_text, lines)
    result["wechat"] = wechat

    # --- 网址 ---
    website = _extract_website(full_text)
    result["website"] = website

    # --- 姓名 ---
    name = _extract_name(lines)
    result["name"] = name

    # --- 公司 ---
    company = _extract_company(lines, result)
    result["company"] = company

    # --- 职位 ---
    position = _extract_position(lines, result)
    result["position"] = position

    # --- 地址 ---
    address = _extract_address(lines)
    result["address"] = address

    logger.info(f"名片字段提取完成: name={result.get('name')}, company={result.get('company')}")
    return result


def _extract_phone(text: str) -> str | None:
    """提取手机号"""
    # 标准手机号: 1开头的11位数字（支持分隔符）
    patterns = [
        r"1[3-9]\d[\s-]?\d{4}[\s-]?\d{4}",  # 手机号
        r"\d{3,4}[\s-]?\d{7,8}",  # 座机
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            raw = m.group(0)
            # 去空格和横线
            cleaned = re.sub(r"[\s-]", "", raw)
            if len(cleaned) >= 10:
                return cleaned
    return None


def _extract_email(text: str) -> str | None:
    """提取邮箱"""
    pat = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    m = re.search(pat, text)
    return m.group(0) if m else None


def _extract_wechat(text: str, lines: list[str]) -> str | None:
    """提取微信号"""
    # 模式1: "微信: xxx" / "wechat: xxx"
    for line in lines:
        wx_match = re.search(r"(?:微信|wechat|wx|微信号)[：:]\s*(\S+)", line, re.IGNORECASE)
        if wx_match:
            return wx_match.group(1)

    # 模式2: 行中独立的字母数字组合，长度6-20，非邮箱非网址
    for line in lines:
        candidates = re.findall(r"(?<![a-zA-Z0-9@.])[a-zA-Z][a-zA-Z0-9_-]{5,19}(?![a-zA-Z0-9@.])", line)
        for c in candidates:
            # 排除已匹配为邮箱/网址的
            if "@" not in c and "." not in c:
                return c

    return None


def _extract_website(text: str) -> str | None:
    """提取网址"""
    # 完整 URL
    pat = r"https?://[^\s,，；;]+"
    m = re.search(pat, text)
    if m:
        return m.group(0)

    # 裸域名: xxx.com / xxx.cn / xxx.com.cn
    pat2 = r"(?:www\.)?[a-zA-Z0-9-]+(?:\.(?:com|cn|net|org|com\.cn|io|cc|top|info)){1,2}(?:\/[^\s,，；;]*)?"
    m2 = re.search(pat2, text)
    if m2:
        url = m2.group(0)
        if not url.startswith("http"):
            url = "https://" + url
        return url

    return None


def _extract_name(lines: list[str]) -> str | None:
    """提取姓名"""
    if not lines:
        return None

    # 通常姓名为 2~4 个汉字，出现在前几行
    for line in lines[:5]:
        # 排除明显不是名字的行
        if re.search(r"[@.comhttp电话手机邮箱微信地址公司职位]", line, re.IGNORECASE):
            continue
        # 2~4 个中文字符
        m = re.match(r"^[\u4e00-\u9fff·]{2,4}$", line.strip())
        if m:
            return m.group(0)

    # 尝试第一行（很多名片第一行是姓名）
    first = lines[0].strip()
    cn_chars = re.findall(r"[\u4e00-\u9fff]", first)
    if len(cn_chars) >= 2 and len(first) <= 10:
        return first

    return None


COMPANY_SUFFIXES = [
    "有限公司",
    "有限责任公司",
    "集团",
    "股份公司",
    "股份有限公司",
    "科技",
    "技术",
    "网络",
    "信息",
    "文化",
    "传媒",
    "教育",
    "咨询",
    "服务",
    "贸易",
    "商贸",
    "实业",
    "投资",
    "（有限合伙）",
    "(有限合伙)",
    "工作室",
    "中心",
    "社",
]


def _extract_company(lines: list[str], existing: dict) -> str | None:
    """提取公司名"""
    if not lines:
        return None

    name = existing.get("name", "")
    position = existing.get("position", "")

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # 跳过姓名行
        if name and line_stripped == name:
            continue
        # 跳过职位行
        if position and position in line_stripped:
            continue
        # 跳过明显是联系信息的行
        if re.search(r"^(\d|[+@a-zA-Z])", line_stripped):
            continue

        # 匹配公司后缀
        for suffix in COMPANY_SUFFIXES:
            if suffix in line_stripped:
                return line_stripped

        # 行中包含"公司"关键词
        if "公司" in line_stripped and len(line_stripped) >= 4:
            return line_stripped

    # 降级: 寻找长度 4~30 且不含特殊字符的行
    for line in lines:
        line_stripped = line.strip()
        if 4 <= len(line_stripped) <= 30 and not re.search(r"[@http\d{11}]", line_stripped):
            if name and line_stripped == name:
                continue
            return line_stripped

    return None


POSITION_KEYWORDS = [
    "CEO",
    "CTO",
    "COO",
    "CFO",
    "VP",
    "总监",
    "经理",
    "主管",
    "董事长",
    "总经理",
    "总裁",
    "创始人",
    "合伙人",
    "主任",
    "顾问",
    "工程师",
    "设计师",
    "运营",
    "销售",
    "市场",
    "董事",
    "监事",
    "秘书",
    "助理",
    "专员",
    "代表",
    "校长",
    "院长",
    "教授",
    "律师",
    "会计师",
    "President",
    "Director",
    "Manager",
    "Founder",
    "Partner",
]


def _extract_position(lines: list[str], existing: dict) -> str | None:
    """提取职位"""
    name = existing.get("name", "")

    for line in lines:
        line_stripped = line.strip()
        if name and line_stripped == name:
            continue

        for kw in POSITION_KEYWORDS:
            if kw in line_stripped:
                # 截取合理长度的职位文本
                if len(line_stripped) <= 30:
                    return line_stripped
                # 如果太长，只取包含关键词的部分
                idx = line_stripped.index(kw)
                return line_stripped[max(0, idx - 5) : idx + len(kw) + 10]

    # 降级: 如果公司名已匹配到，公司名后面那行可能是职位
    company = existing.get("company", "")
    if company:
        for i, line in enumerate(lines):
            if line.strip() == company and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if 2 <= len(next_line) <= 20 and not re.search(r"\d", next_line):
                    return next_line

    return None


def _extract_address(lines: list[str]) -> str | None:
    """提取地址"""
    address_keywords = ["省", "市", "区", "县", "镇", "路", "号", "街", "层", "楼", "室"]

    for line in lines:
        # 匹配地址关键词
        kw_count = sum(1 for kw in address_keywords if kw in line)
        if kw_count >= 2 and len(line) >= 8:
            # 移除可能的前缀标签
            cleaned = re.sub(r"^(地址|addr|add|地点|位置)[：:]\s*", "", line, flags=re.IGNORECASE)
            return cleaned

        # 含"地址"前缀的行
        addr_match = re.match(r"(?:地址|addr|add|地点|位置)[：:]\s*(.+)", line, re.IGNORECASE)
        if addr_match:
            return addr_match.group(1).strip()

    return None


# ============================================================
# 3. 生成数字名片 JSON
# ============================================================


def generate_digital_card(fields: dict[str, Any]) -> dict[str, Any]:
    """生成数字名片 JSON 数据结构（含翻页图册元数据）

    Args:
        fields: 名片字段字典

    Returns:
        完整的数字名片数据（含翻页图册元数据）
    """
    now = datetime.utcnow().isoformat() + "Z"

    # 生成分享令牌
    share_token = secrets.token_urlsafe(32)

    # 构建名片封面信息
    name = fields.get("name", "未知")
    company = fields.get("company", "")
    position = fields.get("position", "")

    # 翻页图册元数据（turn.js 3D 翻页风格）
    album_pages = [
        {
            "page": 1,
            "type": "cover",
            "title": f"{name} 的数字名片",
            "subtitle": f"{position} @ {company}" if position and company else (position or company or ""),
            "style": {
                "background": "linear-gradient(135deg, #0ea5e9 0%, #2563eb 50%, #7c3aed 100%)",
                "textColor": "#ffffff",
                "accentColor": "#fbbf24",
            },
        },
        {
            "page": 2,
            "type": "contact",
            "title": "联系方式",
            "fields": _build_contact_fields(fields),
            "style": {
                "background": "#ffffff",
                "textColor": "#1e293b",
                "accentColor": "#0ea5e9",
            },
        },
        {
            "page": 3,
            "type": "company",
            "title": "企业信息",
            "content": {
                "company": fields.get("company", ""),
                "position": fields.get("position", ""),
                "address": fields.get("address", ""),
                "website": fields.get("website", ""),
            },
            "style": {
                "background": "#f8fafc",
                "textColor": "#1e293b",
                "accentColor": "#2563eb",
            },
        },
        {
            "page": 4,
            "type": "qrcode",
            "title": "扫码交换名片",
            "subtitle": "打开链客宝AIAPP扫码，一键保存联系人",
            "style": {
                "background": "#ffffff",
                "textColor": "#1e293b",
                "accentColor": "#7c3aed",
            },
        },
    ]

    card_data = {
        "id": None,  # 由数据库分配
        "share_token": share_token,
        "share_url": f"/card/{share_token}",
        "name": name,
        "fields": fields,
        "cover_image": fields.get("cover_image"),
        "album_meta": {
            "total_pages": len(album_pages),
            "pages": album_pages,
            "settings": {
                "turn_animation": "3d",
                "page_width": 320,
                "page_height": 520,
                "corner_radius": 12,
                "shadow": True,
            },
        },
        "created_at": now,
        "view_count": 0,
    }

    logger.info(f"数字名片已生成: {name} (token={share_token[:12]}...)")
    return card_data


def _build_contact_fields(fields: dict[str, Any]) -> list[dict[str, str]]:
    """构建联系方式字段列表（过滤空值）"""
    contact_items = [
        ("📞 电话", fields.get("phone")),
        ("📧 邮箱", fields.get("email")),
        ("💬 微信", fields.get("wechat")),
        ("🌐 网站", fields.get("website")),
        ("📍 地址", fields.get("address")),
    ]
    return [{"label": label, "value": value} for label, value in contact_items if value]


# ============================================================
# 4. 供需匹配
# ============================================================


def match_supply_demand(
    card_data: dict[str, Any],
    top_k: int = 10,
    db_session=None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """基于名片信息触发供需匹配（升级版：注入企业知识图谱）

    使用 matching_engine.MatchEngine 匹配名片对应的供需。

    匹配逻辑:
      1. 名片中的公司/职位 → 提取业务关键词
      2. 若公司名匹配到 enterprise 库，注入企业画像+关系图谱
      3. 用企业画像增强搜索 BusinessNeed 和 Product
      4. 返回匹配结果列表（含企业画像信息）

    Args:
        card_data: 数字名片数据
        top_k: 返回最大匹配数
        db_session: 数据库会话（可选，若为 None 则惰性获取）

    Returns:
        匹配结果列表 [{type, title, score, reasons}]
    """
    fields = card_data.get("fields", {})
    name = fields.get("name", "")
    company = fields.get("company", "")
    position = fields.get("position", "")

    # 构建搜索文本
    search_text = " ".join(filter(None, [company, position, name]))

    if not search_text.strip():
        logger.info("名片信息不足以触发供需匹配")
        return []

    try:
        return _run_matching_v2(search_text, fields, top_k, db_session)
    except Exception as e:
        logger.error(f"供需匹配失败: {e}", exc_info=True)
        return []


def _lookup_enterprise(company_name: str, db_session) -> dict | None:
    """在企业库中模糊匹配公司名，返回企业画像+关系图谱

    Args:
        company_name: 名片中的公司名
        db_session: 数据库会话

    Returns:
        匹配到的企业信息字典，含 relation_graph；未匹配则返回 None
    """
    if not company_name or not company_name.strip():
        return None

    from app.models import Enterprise

    try:
        # Step 1: 精确匹配
        ent = db_session.query(Enterprise).filter(Enterprise.name == company_name.strip()).first()
        if ent:
            return _build_enterprise_profile(ent, db_session)

        # Step 2: 模糊匹配（名称包含）
        keyword = f"%{company_name.strip()}%"
        ent = db_session.query(Enterprise).filter(Enterprise.name.ilike(keyword)).first()
        if ent:
            return _build_enterprise_profile(ent, db_session)

        # Step 3: ILIKE 反向匹配（企业名包含搜索词）
        ents = db_session.query(Enterprise).filter(Enterprise.short_name.ilike(keyword)).limit(1).all()
        if ents:
            return _build_enterprise_profile(ents[0], db_session)

    except Exception as e:
        logger.debug(f"企业查询跳过: {e}")

    return None


def _build_enterprise_profile(ent, db_session) -> dict:
    """构建企业画像字典（含关系图谱）"""
    profile = {
        "id": ent.id,
        "name": ent.name,
        "short_name": ent.short_name,
        "credit_code": ent.credit_code,
        "legal_person": ent.legal_person,
        "industry": ent.industry,
        "region": ent.region,
        "business_scope": ent.business_scope,
        "tags": ent.tags,
        "website": ent.website,
        "confidence": ent.confidence,
        "data_source": ent.data_source,
    }

    # 构建关系图谱
    from app.models import EnterpriseRelation

    relations_out = []
    try:
        for rel in db_session.query(EnterpriseRelation).filter(EnterpriseRelation.source_id == ent.id).all():
            target = db_session.query(Enterprise).filter(Enterprise.id == rel.target_id).first()
            if target:
                relations_out.append(
                    {
                        "direction": "out",
                        "relation_type": rel.relation_type,
                        "relation_label": rel.relation_label,
                        "confidence": rel.confidence,
                        "target": {
                            "id": target.id,
                            "name": target.name,
                            "short_name": target.short_name,
                            "industry": target.industry,
                            "region": target.region,
                        },
                    }
                )
    except Exception:
        pass

    relations_in = []
    try:
        for rel in db_session.query(EnterpriseRelation).filter(EnterpriseRelation.target_id == ent.id).all():
            source = db_session.query(Enterprise).filter(Enterprise.id == rel.source_id).first()
            if source:
                relations_in.append(
                    {
                        "direction": "in",
                        "relation_type": rel.relation_type,
                        "relation_label": rel.relation_label,
                        "confidence": rel.confidence,
                        "source": {
                            "id": source.id,
                            "name": source.name,
                            "short_name": source.short_name,
                            "industry": source.industry,
                            "region": source.region,
                        },
                    }
                )
    except Exception:
        pass

    profile["relation_graph"] = {"outgoing": relations_out, "incoming": relations_in}
    return profile


def _run_matching(
    search_text: str,
    fields: dict[str, Any],
    top_k: int,
    db_session=None,
) -> list[dict[str, Any]]:
    """执行匹配逻辑（注入企业知识图谱增强匹配）"""
    # 获取数据库会话
    close_session = False
    if db_session is None:
        from app.database import SessionLocal

        db_session = SessionLocal()
        close_session = True

    try:
        results: list[dict[str, Any]] = []

        # ===== 企业知识图谱增强 =====
        company = fields.get("company", "")
        enterprise_profile = _lookup_enterprise(company, db_session)
        enterprise_search_text = search_text

        if enterprise_profile:
            # 注入企业行业/经营范围到搜索文本
            biz_extras = []
            if enterprise_profile.get("industry"):
                biz_extras.append(enterprise_profile["industry"])
            if enterprise_profile.get("tags"):
                biz_extras.append(enterprise_profile["tags"])
            if enterprise_profile.get("business_scope"):
                biz_extras.append(enterprise_profile["business_scope"][:200])
            if enterprise_profile.get("region"):
                biz_extras.append(enterprise_profile["region"])

            if biz_extras:
                enterprise_search_text = (f"{search_text} {' '.join(biz_extras)}").strip()
                logger.info(f"企业知识图谱增强匹配: {company} → 注入 {len(biz_extras)} 个维度")

        # --- 匹配需求（名片 → BusinessNeed）---
        try:
            from app.models import BusinessNeed

            needs = (
                db_session.query(BusinessNeed)
                .filter(
                    BusinessNeed.is_deleted == False,
                    BusinessNeed.status == "open",
                )
                .limit(50)
                .all()
            )

            need_scores = []
            for need in needs:
                need_text = f"{need.title} {need.description or ''} {need.category or ''}"
                score = _calc_text_similarity(enterprise_search_text, need_text)

                # 如果企业画像匹配，使用企业行业/地区作为增强匹配因子
                bonus = 0.0
                if enterprise_profile:
                    # 同行业加分
                    if enterprise_profile.get("industry") and need.category:
                        industry_kw = enterprise_profile["industry"]
                        if any(kw in (need.category or "") for kw in industry_kw.split()):
                            bonus += 0.15
                        if any(kw in (need.title or "") for kw in industry_kw.split()):
                            bonus += 0.10
                    # 同地区加分
                    if enterprise_profile.get("region"):
                        region = enterprise_profile["region"]
                        if region and need.region and (region in need.region or need.region in region):
                            bonus += 0.10

                score = min(score + bonus, 1.0)
                if score > 0.1:
                    reasons = [f"业务领域匹配度 {int(score * 100)}%"]
                    if bonus > 0:
                        reasons.append(f"企业画像增强 (+{int(bonus * 100)}%)")
                    need_scores.append(
                        {
                            "type": "need",
                            "id": need.id,
                            "title": need.title,
                            "category": need.category,
                            "score": round(score, 2),
                            "reasons": reasons,
                        }
                    )

            need_scores.sort(key=lambda x: x["score"], reverse=True)
            results.extend(need_scores[:top_k])
        except Exception as e:
            logger.debug(f"需求匹配跳过: {e}")

        # --- 匹配产品（名片 → Product）---
        try:
            from app.models import Product

            products = (
                db_session.query(Product)
                .filter(
                    Product.is_deleted == False,
                    Product.status == "approved",
                )
                .limit(50)
                .all()
            )

            prod_scores = []
            for prod in products:
                prod_text = f"{prod.name or ''} {prod.description or ''} {prod.category or ''} {prod.tags or ''}"
                score = _calc_text_similarity(enterprise_search_text, prod_text)

                # 企业画像增强
                bonus = 0.0
                if enterprise_profile:
                    if enterprise_profile.get("industry") and prod.category:
                        industry_kw = enterprise_profile["industry"]
                        if any(kw in (prod.category or "") for kw in industry_kw.split()):
                            bonus += 0.15
                        if any(kw in (prod.name or "") for kw in industry_kw.split()):
                            bonus += 0.10
                    if enterprise_profile.get("region"):
                        region = enterprise_profile["region"]
                        if region:
                            try:
                                specs = json.loads(prod.specs) if prod.specs else {}
                                prod_region = specs.get("产地", specs.get("产地/发货地", ""))
                                if prod_region and (region in prod_region or prod_region in region):
                                    bonus += 0.10
                            except (json.JSONDecodeError, TypeError):
                                pass

                score = min(score + bonus, 1.0)
                if score > 0.1:
                    reasons = [f"业务关键词匹配度 {int(score * 100)}%"]
                    if bonus > 0:
                        reasons.append(f"企业画像增强 (+{int(bonus * 100)}%)")
                    prod_scores.append(
                        {
                            "type": "product",
                            "id": prod.id,
                            "title": prod.name,
                            "category": prod.category,
                            "score": round(score, 2),
                            "reasons": reasons,
                        }
                    )

            prod_scores.sort(key=lambda x: x["score"], reverse=True)
            results.extend(prod_scores[:top_k])
        except Exception as e:
            logger.debug(f"产品匹配跳过: {e}")

        # 综合排序
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:top_k]

        logger.info(
            f"供需匹配完成: {len(results)} 个匹配项" + (f" (企业画像: {company})" if enterprise_profile else "")
        )

        # 将企业画像注入到返回结果中（非破坏性扩展）
        enhanced_result = {
            "enterprise_profile": enterprise_profile,
            "items": results,
        }
        return enhanced_result

    finally:
        if close_session:
            db_session.close()


def _calc_text_similarity(text_a: str, text_b: str) -> float:
    """计算两段文本的相似度（基于关键词重叠）

    Returns:
        0.0 ~ 1.0 的相似度分数
    """
    if not text_a or not text_b:
        return 0.0

    # 分词 + 去停用词
    try:
        import jieba

        tokens_a = set(jieba.lcut(text_a.lower()))
        tokens_b = set(jieba.lcut(text_b.lower()))
    except ImportError:
        # 无 jieba：用简单字符分割
        tokens_a = set(re.findall(r"[\u4e00-\u9fff\w]+", text_a.lower()))
        tokens_b = set(re.findall(r"[\u4e00-\u9fff\w]+", text_b.lower()))

    # 过滤单字和停用词
    stop_words = {
        "的",
        "了",
        "在",
        "是",
        "我",
        "有",
        "和",
        "就",
        "不",
        "人",
        "都",
        "一",
        "一个",
        "上",
        "也",
        "很",
        "到",
        "说",
        "要",
        "去",
        "你",
        "会",
        "着",
        "没有",
        "看",
        "好",
        "自己",
        "这",
        "他",
        "她",
        "它",
        "们",
        "为",
        "与",
        "及",
        "等",
        "或",
        "之",
        "以",
        "被",
        "让",
        "给",
        "对",
        "从",
        "把",
        "向",
        "能",
        "做",
    }
    tokens_a = {t for t in tokens_a if len(t) >= 2 and t not in stop_words}
    tokens_b = {t for t in tokens_b if len(t) >= 2 and t not in stop_words}

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b

    if not union:
        return 0.0

    # Jaccard 相似度
    return len(intersection) / len(union)


# ============================================================
# 工具函数
# ============================================================


def generate_share_token(length: int = 32) -> str:
    """生成唯一的分享令牌"""
    return secrets.token_urlsafe(length)


def validate_card_fields(fields: dict[str, Any]) -> tuple[bool, list[str]]:
    """验证名片字段的完整性和合法性

    Returns:
        (is_valid, error_messages)
    """
    errors = []

    if not fields.get("name"):
        errors.append("姓名为必填字段")

    phone = fields.get("phone", "")
    if phone and not re.match(r"^1[3-9]\d{9}$", phone):
        errors.append("手机号格式不正确")

    email = fields.get("email", "")
    if email and not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        errors.append("邮箱格式不正确")

    return (len(errors) == 0, errors)


# ============================================================
# 匹配引擎升级 v2: MatchEngine 集成（保留企业知识图谱增强）
# ============================================================


def _run_matching_v2(
    search_text: str,
    fields: dict[str, Any],
    top_k: int,
    db_session=None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """升级版匹配：保留企业知识图谱查询，但匹配逻辑委托给MatchEngine

    MatchEngine v2.1 特性:
      - jieba分词 + TF-IDF余弦相似度
      - 冷启动加权（新用户/新商品加权）
      - MMR多样性重排序
      - A/B测试框架
    """
    close_session = False
    if db_session is None:
        from app.database import SessionLocal

        db_session = SessionLocal()
        close_session = True

    try:
        results: list[dict[str, Any]] = []

        # ===== 企业知识图谱增强（保留 =====
        company = fields.get("company", "")
        enterprise_profile = _lookup_enterprise(company, db_session)
        enterprise_search_text = search_text

        if enterprise_profile:
            biz_extras = []
            if enterprise_profile.get("industry"):
                biz_extras.append(enterprise_profile["industry"])
            if enterprise_profile.get("tags"):
                biz_extras.append(enterprise_profile["tags"])
            if enterprise_profile.get("business_scope"):
                biz_extras.append(enterprise_profile["business_scope"][:200])
            if enterprise_profile.get("region"):
                biz_extras.append(enterprise_profile["region"])
            if biz_extras:
                enterprise_search_text = (f"{search_text} {' '.join(biz_extras)}").strip()

        # ===== 使用 MatchEngine（如果可用）=====
        try:
            from matching_engine import MatchEngine

            engine = MatchEngine(db_session=db_session)

            # 匹配需求
            from app.models import BusinessNeed

            needs = (
                db_session.query(BusinessNeed)
                .filter(BusinessNeed.is_deleted == False, BusinessNeed.status == "open")
                .limit(50)
                .all()
            )

            need_scores = []
            for need in needs:
                need_text = f"{need.title} {need.description or ''} {need.category or ''}"
                # 使用MatchEngine的TF-IDF相似度
                tfidf_score = engine._compute_tfidf_similarity(enterprise_search_text, need_text)
                cat_score = engine._match_category(enterprise_search_text, need.category or "")
                score = tfidf_score * 0.7 + (cat_score / 100) * 0.3

                # 企业画像加分
                bonus = 0.0
                if enterprise_profile:
                    if enterprise_profile.get("industry") and need.category:
                        if any(kw in (need.category or "") for kw in enterprise_profile["industry"].split()):
                            bonus += 0.15
                    if enterprise_profile.get("region") and need.region:
                        if enterprise_profile["region"] in need.region or need.region in enterprise_profile["region"]:
                            bonus += 0.10

                score = min(score + bonus, 1.0)
                if score > 0.1:
                    reasons = [f"TF-IDF匹配度 {int(tfidf_score * 100)}%"]
                    if cat_score > 20:
                        reasons.append(f"类目匹配 {int(cat_score)}%")
                    if bonus > 0:
                        reasons.append(f"企业画像增强 (+{int(bonus * 100)}%)")
                    need_scores.append(
                        {
                            "type": "need",
                            "id": need.id,
                            "title": need.title,
                            "category": need.category,
                            "score": round(score, 2),
                            "reasons": reasons,
                        }
                    )

            need_scores.sort(key=lambda x: x["score"], reverse=True)
            results.extend(need_scores[:top_k])
        except Exception as e:
            logger.debug(f"MatchEngine需求匹配跳过: {e}")

        # ===== 匹配产品 =====
        try:
            from matching_engine import MatchEngine

            engine = MatchEngine(db_session=db_session)

            from app.models import Product

            products = (
                db_session.query(Product)
                .filter(Product.is_deleted == False, Product.status == "approved")
                .limit(50)
                .all()
            )

            prod_scores = []
            for prod in products:
                prod_text = f"{prod.name or ''} {prod.description or ''} {prod.category or ''} {prod.tags or ''}"
                tfidf_score = engine._compute_tfidf_similarity(enterprise_search_text, prod_text)
                cat_score = engine._match_category(enterprise_search_text, prod.category or "")
                score = tfidf_score * 0.7 + (cat_score / 100) * 0.3

                bonus = 0.0
                if enterprise_profile:
                    if enterprise_profile.get("industry") and prod.category:
                        if any(kw in (prod.category or "") for kw in enterprise_profile["industry"].split()):
                            bonus += 0.15

                score = min(score + bonus, 1.0)
                if score > 0.1:
                    reasons = [f"TF-IDF匹配度 {int(tfidf_score * 100)}%"]
                    if bonus > 0:
                        reasons.append(f"企业画像增强 (+{int(bonus * 100)}%)")
                    prod_scores.append(
                        {
                            "type": "product",
                            "id": prod.id,
                            "title": prod.name,
                            "category": prod.category,
                            "score": round(score, 2),
                            "reasons": reasons,
                        }
                    )

            prod_scores.sort(key=lambda x: x["score"], reverse=True)
            results.extend(prod_scores[:top_k])
        except Exception as e:
            logger.debug(f"MatchEngine产品匹配跳过: {e}")

        # 综合排序
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:top_k]

        logger.info(f"MatchEngine v2供需匹配完成: {len(results)} 个匹配项")

        enhanced_result = {
            "enterprise_profile": enterprise_profile,
            "items": results,
        }
        return enhanced_result

    finally:
        if close_session:
            db_session.close()
