"""
通用导入引擎：CSV/VCF 解析 + DeepSeek AI 列名识别 + 模糊去重
"""
import csv
import io
import json
import os
import re
import uuid
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple

from app.services.dedup import (
    detect_duplicates,
    DuplicateGroup,
    NAME_SIMILARITY_THRESHOLD,
)

logger = logging.getLogger(__name__)

# ============================================================
# DeepSeek API 配置
# ============================================================
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_TIMEOUT = 30  # 秒

# ============================================================
# 字段映射定义
# ============================================================

# 系统标准字段列表
STANDARD_FIELDS = [
    "name",       # 姓名
    "phone",      # 手机号
    "wechat_id",  # 微信ID
    "company",    # 公司
    "position",   # 职位
    "email",      # 邮箱
    "notes",      # 备注
    "tags",       # 标签
]

# 常见列名 -> 标准字段的映射表（用作 DeepSeek 的 fallback / 快速匹配）
COMMON_COLUMN_MAP: Dict[str, str] = {
    # 中文
    "姓名": "name",
    "名字": "name",
    "名称": "name",
    "联系人": "name",
    "手机": "phone",
    "手机号": "phone",
    "电话": "phone",
    "手机号码": "phone",
    "联系电话": "phone",
    "移动电话": "phone",
    "微信号": "wechat_id",
    "微信": "wechat_id",
    "微信ID": "wechat_id",
    "公司": "company",
    "公司名称": "company",
    "企业": "company",
    "单位": "company",
    "工作单位": "company",
    "职位": "position",
    "职务": "position",
    "岗位": "position",
    "邮箱": "email",
    "邮件": "email",
    "E-mail": "email",
    "Email": "email",
    "备注": "notes",
    "说明": "notes",
    "标签": "tags",
    "分类": "tags",
    # 英文
    "name": "name",
    "full name": "name",
    "fullname": "name",
    "contact": "name",
    "contact name": "name",
    "first name": "name",
    "last name": "name",
    "phone": "phone",
    "mobile": "phone",
    "telephone": "phone",
    "tel": "phone",
    "cell": "phone",
    "cellphone": "phone",
    "wechat": "wechat_id",
    "wechat id": "wechat_id",
    "weixin": "wechat_id",
    "company": "company",
    "organization": "company",
    "org": "company",
    "employer": "company",
    "company name": "company",
    "position": "position",
    "title": "position",
    "job title": "position",
    "role": "position",
    "email": "email",
    "e-mail": "email",
    "notes": "notes",
    "note": "notes",
    "comment": "notes",
    "remarks": "notes",
    "tags": "tags",
    "labels": "tags",
}

# VCF vCard 字段映射
VCF_FIELD_MAP: Dict[str, str] = {
    "FN": "name",
    "N": "name",
    "TEL": "phone",
    "CELL": "phone",
    "EMAIL": "email",
    "ORG": "company",
    "TITLE": "position",
    "ROLE": "position",
    "NOTE": "notes",
    "CATEGORIES": "tags",
}


# ============================================================
# 格式检测与解析
# ============================================================

def detect_format(filename: str, raw_content: bytes) -> str:
    """
    检测文件格式：csv / vcf

    Args:
        filename: 原始文件名
        raw_content: 文件二进制内容

    Returns:
        'csv' 或 'vcf'
    """
    # 按扩展名优先
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".vcf", ".vcard"):
        return "vcf"
    if ext == ".csv":
        return "csv"

    # 无扩展名或未知扩展名，检测内容
    try:
        text = raw_content.decode("utf-8", errors="ignore")[:1000]
    except Exception:
        text = ""

    # vCard 特征：BEGIN:VCARD
    if "BEGIN:VCARD" in text.upper() or "BEGIN:VCF" in text.upper():
        return "vcf"

    # 含逗号或制表符分隔的多行 => CSV
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) >= 2:
        # 检查第一行是否有常见分隔符
        first_line = lines[0]
        comma_count = first_line.count(",")
        tab_count = first_line.count("\t")
        semi_count = first_line.count(";")
        # CSV 一般至少 2 个逗号
        if comma_count >= 1 or (tab_count >= 1 and tab_count > semi_count):
            return "csv"

    # 默认用 CSV
    return "csv"


def _detect_csv_dialect(raw_text: str) -> dict:
    """
    自动检测CSV分隔符和引号字符

    Returns:
        {"delimiter": str, "quotechar": str}
    """
    # 尝试常见分隔符
    delimiters = [",", "\t", ";", "|"]
    best_delim = ","
    best_count = 0
    first_line = raw_text.splitlines()[0] if raw_text.splitlines() else ""

    for delim in delimiters:
        count = first_line.count(delim)
        # 制表符和分号的权重稍微调低（避免把 VCF 样式的 ; 误判）
        weight = 0.8 if delim in ("\t", ";") else 1.0
        weighted = count * weight
        if weighted > best_count:
            best_count = weighted
            best_delim = delim

    # 检测引号字符
    quotechar = '"'
    for q in ('"', "'"):
        if q in first_line:
            quotechar = q
            break

    return {"delimiter": best_delim, "quotechar": quotechar}


def _detect_encoding(raw_content: bytes) -> str:
    """检测文件编码：优先 UTF-8，fallback 到 GBK"""
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"):
        try:
            raw_content.decode(encoding)
            return encoding
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue
    return "utf-8"  # 最后 fallback


def parse_csv(raw_content: bytes, encoding: Optional[str] = None) -> List[Dict[str, str]]:
    """
    解析 CSV 文件内容，自动检测分隔符和编码

    Args:
        raw_content: 文件二进制内容
        encoding: 指定编码（None 则自动检测）

    Returns:
        list[dict] — 每行一个字典，key为第一行列名
    """
    if encoding is None:
        encoding = _detect_encoding(raw_content)

    text = raw_content.decode(encoding, errors="replace")

    # 去除 BOM
    if text.startswith("\ufeff"):
        text = text[1:]

    dialect = _detect_csv_dialect(text)
    delimiter = dialect["delimiter"]
    quotechar = dialect["quotechar"]

    # 先用第一行判断是否有列名
    lines = text.splitlines()
    if not lines:
        return []

    reader = csv.DictReader(
        io.StringIO(text),
        delimiter=delimiter,
        quotechar=quotechar,
    )

    # 如果第一行不能作为表头（无逗号/制表符），尝试用第一行做列名
    rows = []
    for row in reader:
        # 去除 key 和 value 的空格
        cleaned = {}
        for k, v in row.items():
            if k is not None:
                key = k.strip()
            else:
                key = ""
            val = v.strip() if v else ""
            if key:
                cleaned[key] = val
        if cleaned:
            rows.append(cleaned)

    return rows


def parse_vcf(raw_content: bytes) -> List[Dict[str, str]]:
    """
    解析 VCF (vCard) 文件内容，支持 vCard 3.0 / 4.0

    Args:
        raw_content: 文件二进制内容

    Returns:
        list[dict] — 每个联系人的字段字典
    """
    text = raw_content.decode("utf-8", errors="replace")

    # 按 BEGIN:VCARD 分隔
    vcard_blocks = re.split(r'(?=BEGIN:VCARD)', text, flags=re.IGNORECASE)

    contacts = []
    for block in vcard_blocks:
        if "BEGIN:VCARD" not in block.upper():
            continue

        contact: Dict[str, str] = {}
        lines = block.splitlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 处理多行连续（以空格或制表符开头）
            while i + 1 < len(lines) and (
                lines[i + 1].startswith(" ") or lines[i + 1].startswith("\t")
            ):
                i += 1
                line += lines[i].strip()

            if not line or ":" not in line:
                i += 1
                continue

            # 解析：字段名[;参数...]:值
            colon_pos = line.index(":")
            raw_field = line[:colon_pos]
            value = line[colon_pos + 1:].strip()

            # 提取字段名（去掉参数部分）
            field_name = raw_field.split(";")[0].upper()

            # 处理 TYPE= 参数（如 TEL;TYPE=CELL）
            params = {}
            for part in raw_field.split(";")[1:]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    params[k.upper()] = v

            # 映射到标准字段
            std_field = VCF_FIELD_MAP.get(field_name, "")

            if field_name == "FN":
                contact["name"] = value
            elif field_name == "N":
                # N:LastName;FirstName;Middle;Prefix;Suffix
                if "name" not in contact:
                    parts = value.split(";")
                    last = parts[0] if len(parts) > 0 else ""
                    first = parts[1] if len(parts) > 1 else ""
                    middle = parts[2] if len(parts) > 2 else ""
                    contact["name"] = f"{first} {last}".strip()
                    if middle:
                        contact["name"] += f" {middle}".strip()
            elif field_name == "TEL":
                tel_type = params.get("TYPE", "").upper()
                # 优先手机号
                if "CELL" in tel_type or "VOICE" in tel_type:
                    # 如果已有手机号，存为额外电话（用备注字段）
                    if "phone" in contact:
                        contact.setdefault("notes", "")
                        notes = contact["notes"]
                        extra = f"电话: {value}"
                        contact["notes"] = f"{notes}\n{extra}".strip()
                    else:
                        contact["phone"] = value
                else:
                    if "phone" not in contact:
                        contact["phone"] = value
                    else:
                        contact.setdefault("notes", "")
                        notes = contact["notes"]
                        extra = f"电话: {value}"
                        contact["notes"] = f"{notes}\n{extra}".strip()
            elif field_name == "EMAIL":
                contact["email"] = value
            elif field_name == "ORG":
                contact["company"] = value
            elif field_name == "TITLE" or field_name == "ROLE":
                contact["position"] = value
            elif field_name == "NOTE":
                contact["notes"] = value
            elif field_name == "CATEGORIES":
                contact["tags"] = value
            elif field_name == "URL":
                contact.setdefault("notes", "")
                notes = contact.get("notes", "")
                extra = f"网址: {value}"
                contact["notes"] = f"{notes}\n{extra}".strip() if notes else extra
            elif field_name == "ADR":
                contact.setdefault("notes", "")
                notes = contact.get("notes", "")
                extra = f"地址: {value}"
                contact["notes"] = f"{notes}\n{extra}".strip() if notes else extra
            # 其他字段忽略

            i += 1

        # 确保有 name 字段
        if "name" not in contact:
            # 如果 name 没找到，用第一个非空字段
            for k, v in contact.items():
                if v and k != "notes":
                    contact["name"] = v
                    break
            if "name" not in contact:
                contact["name"] = "未知联系人"

        contacts.append(contact)

    return contacts


# ============================================================
# DeepSeek AI 列名识别
# ============================================================

def _build_field_mapping_prompt(
    headers: List[str],
    sample_rows: List[Dict[str, str]],
) -> str:
    """
    构建 DeepSeek 列名识别提示词
    """
    # 构建示例数据字符串
    sample_lines = []
    for i, row in enumerate(sample_rows[:5]):  # 最多5行
        parts = []
        for h in headers:
            val = row.get(h, "").strip()
            if val:
                parts.append(f"{h}={val}")
            else:
                parts.append(f"{h}=")
        sample_lines.append(" | ".join(parts))

    sample_str = "\n".join(sample_lines)

    prompt = f"""你是一个智能数据导入助手，需要将CSV文件列名映射到系统标准字段。

系统标准字段（共{len(STANDARD_FIELDS)}个）：
{', '.join(STANDARD_FIELDS)}

字段说明：
- name: 联系人姓名（必填）
- phone: 手机号（11位中国大陆手机号）
- wechat_id: 微信ID
- company: 公司/企业名称
- position: 职位/职务
- email: 电子邮箱
- notes: 备注/说明
- tags: 标签/分类

CSV列名列表：
{json.dumps(headers, ensure_ascii=False)}

示例数据（前{min(5, len(sample_rows))}行）：
{sample_str}

请分析这些列名，并返回一个JSON映射对象，格式为：
{{"csv_column_name": "standard_field", ...}}

要求：
1. 准确识别中英文列名
2. 不匹配的列映射为空字符串 ""
3. 只返回JSON，不要任何额外文字说明
4. 确保 name 字段映射正确"""

    return prompt


def _call_deepseek_api(prompt: str) -> Optional[str]:
    """
    调用 DeepSeek API

    Args:
        prompt: 提示词内容

    Returns:
        API 响应文本，失败返回 None
    """
    if not DEEPSEEK_API_KEY:
        logger.warning("DEEPSEEK_API_KEY 未配置，跳过 AI 列名识别")
        return None

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一个数据导入助手，只输出JSON，不要任何额外文字。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,  # 低温度保证确定性
        "max_tokens": 1024,
    }

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=data_bytes,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=DEEPSEEK_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
        return content
    except urllib.error.HTTPError as e:
        logger.error(f"DeepSeek API HTTP 错误: {e.code} {e.reason}")
        return None
    except urllib.error.URLError as e:
        logger.error(f"DeepSeek API 连接失败: {e.reason}")
        return None
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error(f"DeepSeek API 响应解析失败: {e}")
        return None
    except Exception as e:
        logger.error(f"DeepSeek API 调用异常: {e}")
        return None


def _parse_ai_response(response: str, headers: List[str]) -> Dict[str, str]:
    """
    解析 DeepSeek 返回的 JSON 映射

    Args:
        response: API 返回的文本
        headers: CSV 列名列表

    Returns:
        {csv_column: standard_field, ...}
    """
    # 尝试提取 JSON
    response = response.strip()

    # 去除可能的 markdown 代码块标记
    if response.startswith("```json"):
        response = response[7:]
    elif response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]

    response = response.strip()

    try:
        mapping = json.loads(response)
    except json.JSONDecodeError:
        logger.warning(f"DeepSeek 返回不是有效JSON: {response[:200]}")
        return _fallback_mapping(headers)

    if not isinstance(mapping, dict):
        return _fallback_mapping(headers)

    # 验证映射结果
    result = {}
    for header in headers:
        mapped = mapping.get(header, "")
        if mapped in STANDARD_FIELDS:
            result[header] = mapped
        elif mapped:
            # 尝试模糊匹配
            matched = _fuzzy_match_field(mapped)
            if matched:
                result[header] = matched
            else:
                result[header] = ""
        else:
            result[header] = ""

    return result


def _fuzzy_match_field(field_name: str) -> Optional[str]:
    """
    模糊匹配字段名到标准字段
    """
    field_lower = field_name.lower().strip()
    for std_field in STANDARD_FIELDS:
        if std_field in field_lower or field_lower in std_field:
            return std_field
    return None


def _fallback_mapping(headers: List[str]) -> Dict[str, str]:
    """
    Fallback：基于 COMMON_COLUMN_MAP 做简单映射
    """
    result = {}
    for header in headers:
        header_lower = header.lower().strip()
        # 精确匹配
        if header_lower in COMMON_COLUMN_MAP:
            result[header] = COMMON_COLUMN_MAP[header_lower]
        else:
            # 模糊匹配：检查是否包含某些关键词
            matched = False
            for keyword, std_field in COMMON_COLUMN_MAP.items():
                if keyword in header_lower or header_lower in keyword:
                    result[header] = std_field
                    matched = True
                    break
            if not matched:
                # 尝试更松散的包含匹配
                for ch_keyword in ["姓名", "名字", "名称", "联系人"]:
                    if ch_keyword in header:
                        result[header] = "name"
                        matched = True
                        break
            if not matched:
                result[header] = ""
    return result


def ai_recognize_columns(
    headers: List[str],
    sample_data: List[Dict[str, str]],
) -> Dict[str, str]:
    """
    AI 列名识别：先尝试 DeepSeek API，失败则 fallback 到本地规则

    Args:
        headers: CSV 列名列表
        sample_data: 前几行示例数据

    Returns:
        {csv_column: standard_field, ...}
    """
    if not headers:
        return {}

    # 先尝试 DeepSeek
    if DEEPSEEK_API_KEY:
        prompt = _build_field_mapping_prompt(headers, sample_data)
        response = _call_deepseek_api(prompt)
        if response:
            mapping = _parse_ai_response(response, headers)
            logger.info(f"DeepSeek 列名识别结果: {json.dumps(mapping, ensure_ascii=False)}")
            return mapping

    # Fallback 到本地规则
    logger.info("使用本地规则进行列名映射（fallback）")
    return _fallback_mapping(headers)


# ============================================================
# 导入引擎主类
# ============================================================

class ImportEngine:
    """通用导入引擎"""

    def __init__(self):
        self.batch_id = str(uuid.uuid4())
        self.parsed_data: List[Dict[str, str]] = []
        self.field_mapping: Dict[str, str] = {}
        self.mapped_data: List[Dict[str, str]] = []

    def detect_format(self, filename: str, raw_content: bytes) -> str:
        """检测文件格式"""
        return detect_format(filename, raw_content)

    def parse_file(self, filename: str, raw_content: bytes) -> List[Dict[str, str]]:
        """
        解析文件（自动检测格式）
        """
        fmt = self.detect_format(filename, raw_content)
        if fmt == "csv":
            self.parsed_data = parse_csv(raw_content)
        elif fmt == "vcf":
            self.parsed_data = parse_vcf(raw_content)
        else:
            raise ValueError(f"不支持的文件格式: {fmt}")
        return self.parsed_data

    def recognize_columns(self) -> Dict[str, str]:
        """
        识别列名映射
        """
        if not self.parsed_data:
            return {}

        headers = list(self.parsed_data[0].keys())
        self.field_mapping = ai_recognize_columns(headers, self.parsed_data[:5])
        return self.field_mapping

    def apply_mapping(self) -> List[Dict[str, str]]:
        """
        应用列名映射，返回标准化数据
        """
        self.mapped_data = []
        for row in self.parsed_data:
            mapped_row: Dict[str, str] = {}
            for csv_col, std_field in self.field_mapping.items():
                if std_field and csv_col in row:
                    mapped_row[std_field] = row[csv_col]
            # 确保 name 字段存在
            if "name" not in mapped_row or not mapped_row["name"]:
                # 尝试从其他字段找名字
                for possible in ["姓名", "名字", "名称", "联系人", "name", "Name"]:
                    if possible in row and row[possible]:
                        mapped_row["name"] = row[possible]
                        break
            self.mapped_data.append(mapped_row)
        return self.mapped_data

    def detect_duplicates_with_db(
        self,
        existing_contacts: List[Dict[str, Any]],
    ) -> List[DuplicateGroup]:
        """
        检测导入数据与数据库中已有联系人的重复

        Args:
            existing_contacts: 数据库中的联系人列表
                [{name, phone, wechat_id, company, email, ...}, ...]

        Returns:
            List[DuplicateGroup]
        """
        if not self.mapped_data:
            self.apply_mapping()
        return detect_duplicates(self.mapped_data, existing_contacts)

    def merge_strategy(
        self,
        dup_group: List[DuplicateGroup],
        strategy: str = "skip",
    ) -> Dict[str, Any]:
        """
        根据去重策略返回操作指令

        Args:
            dup_group: 一组重复候选
            strategy: skip | merge | update

        Returns:
            {"action": "skip"|"merge"|"update", "target_fields": [...]}
        """
        best = dup_group[0]  # 相似度最高的
        if strategy == "skip":
            return {"action": "skip", "target_fields": []}
        elif strategy == "merge":
            # 合并：保留所有字段，非空优先
            return {"action": "merge", "target_fields": ["name", "phone", "wechat_id", "company", "position", "email", "notes", "tags"]}
        elif strategy == "update":
            # 更新：新数据覆盖旧数据
            return {"action": "update", "target_fields": ["phone", "wechat_id", "company", "position", "email", "notes", "tags"]}
        else:
            return {"action": "skip", "target_fields": []}

    def preview(self, max_rows: int = 20) -> dict:
        """
        返回预览信息

        Returns:
            {
                "total_rows": int,
                "preview_rows": list[dict],
                "headers": list[str],
                "field_mapping": dict,
                "suggestions": dict
            }
        """
        headers = list(self.parsed_data[0].keys()) if self.parsed_data else []

        return {
            "batch_id": self.batch_id,
            "total_rows": len(self.parsed_data),
            "preview_rows": self.parsed_data[:max_rows],
            "headers": headers,
            "field_mapping": self.field_mapping,
            "mapped_preview": self.mapped_data[:max_rows] if self.mapped_data else [],
        }
