#!/usr/bin/env python3
"""
数据契约系统 (Data Contract System)
====================================
安全架构的基础层 —— 每个模块写入 core schema 前必须声明契约。

核心组件:
  - ContractYAML        : 加载、解析、校验 YAML 契约文件
  - ContractValidator   : 对传入数据做契约校验
  - ContractManager     : 版本管理、热加载、迁移
  - ContractAutoGenerator: 从 SQLAlchemy model 自动生成契约 YAML

设计原则:
  1. 零外部依赖 (仅 Python 标准库 + 可选 PyYAML)
  2. 契约即文档，文档即校验
  3. 热加载不重启，生产友好
  4. 严格模式默认，宽松模式可选
"""

import copy
import fnmatch
import hashlib
import os
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

# ---------------------------------------------------------------------------
# 尝试导入 PyYAML，如果不可用则使用内置的简易 YAML 解析器
# ---------------------------------------------------------------------------
try:
    import yaml as _yaml_lib

    HAS_PYYAML = True
except ImportError:
    HAS_PYYAML = False

# ===================================================================
# 简易 YAML 解析器后备 (fallback) —— 只支持 data_contract 所需子集
# ===================================================================


class _SimpleYAML:
    """极简 YAML 解析器，仅支持契约文件需要的键值对、列表、嵌套字典。"""

    @staticmethod
    def load(stream) -> dict:
        return _SimpleYAML._parse(_SimpleYAML._tokenize(stream.read()))

    @staticmethod
    def dump(data, stream, **kwargs) -> None:
        # 如果可用则用 PyYAML，否则自己序列化
        if HAS_PYYAML:
            _yaml_lib.dump(data, stream, default_flow_style=False, allow_unicode=True, **kwargs)
        else:
            stream.write(_SimpleYAML._serialize(data))

    @staticmethod
    def _tokenize(text: str) -> list[tuple]:
        lines = text.split("\n")
        tokens = []
        for lineno, raw in enumerate(lines, 1):
            stripped = raw.rstrip()
            if not stripped.strip() or stripped.strip().startswith("#"):
                continue
            indent = len(raw) - len(raw.lstrip())
            tokens.append((lineno, indent, stripped.strip()))
        return tokens

    @staticmethod
    def _parse(tokens: list[tuple]) -> dict:
        result = {}
        stack = [("root", 0, result)]
        i = 0
        while i < len(tokens):
            lineno, indent, content = tokens[i]
            while stack and stack[-1][1] >= indent:
                stack.pop()
            parent = stack[-1][2] if stack else result
            if ":" in content:
                key_end = content.index(":")
                key = content[:key_end].strip()
                value = content[key_end + 1 :].strip()
                if value == "":
                    # 下一行是子项
                    nested = {}
                    parent[key] = nested
                    stack.append((key, indent, nested))
                else:
                    # 尝试类型转换
                    parent[key] = _SimpleYAML._convert(value)
            elif content.startswith("- "):
                # 列表项
                val = _SimpleYAML._convert(content[2:])
                if isinstance(parent, list):
                    parent.append(val)
                else:
                    # 找到最近的列表父级
                    for st in reversed(stack):
                        p = st[2]
                        if isinstance(p, list):
                            p.append(val)
                            break
                    else:
                        # 自动创建列表
                        parent.setdefault("__list__", []).append(val)
            i += 1
        return result

    @staticmethod
    def _convert(value: str) -> Any:
        v = value.strip()
        if v == "~" or v == "null":
            return None
        if v == "true" or v == "True":
            return True
        if v == "false" or v == "False":
            return False
        try:
            return int(v)
        except ValueError:
            pass
        try:
            return float(v)
        except ValueError:
            pass
        if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
            return v[1:-1]
        return v

    @staticmethod
    def _serialize(data, indent=0) -> str:
        lines = []
        prefix = "  " * indent
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (dict, OrderedDict)):
                    lines.append(f"{prefix}{k}:")
                    lines.append(_SimpleYAML._serialize(v, indent + 1))
                elif isinstance(v, list):
                    lines.append(f"{prefix}{k}:")
                    for item in v:
                        if isinstance(item, (dict, OrderedDict)):
                            lines.append(f"{prefix}  -")
                            for sk, sv in item.items():
                                lines.append(f"{prefix}    {sk}: {_SimpleYAML._serialize_scalar(sv)}")
                        else:
                            lines.append(f"{prefix}  - {_SimpleYAML._serialize_scalar(item)}")
                else:
                    lines.append(f"{prefix}{k}: {_SimpleYAML._serialize_scalar(v)}")
        elif isinstance(data, list):
            for item in data:
                lines.append(f"{prefix}- {_SimpleYAML._serialize_scalar(item)}")
        else:
            lines.append(f"{prefix}{_SimpleYAML._serialize_scalar(data)}")
        return "\n".join(lines)

    @staticmethod
    def _serialize_scalar(value) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, (int, float)):
            return str(value)
        return str(value)


def _yaml_load(stream):
    """统一 YAML 加载入口"""
    if HAS_PYYAML:
        return _yaml_lib.safe_load(stream)
    return _SimpleYAML.load(stream)


def _yaml_dump(data, stream, **kwargs):
    """统一 YAML 导出入口"""
    if HAS_PYYAML:
        _yaml_lib.dump(data, stream, default_flow_style=False, allow_unicode=True, **kwargs)
    else:
        stream.write(_SimpleYAML._serialize(data))


# ===================================================================
# 异常定义
# ===================================================================


class DataContractError(Exception):
    """数据契约系统基础异常"""

    pass


class ContractNotFoundError(DataContractError):
    """契约文件未找到"""

    pass


class ContractValidationError(DataContractError):
    """数据校验失败"""

    def __init__(self, message: str, errors: list[dict] | None = None):
        super().__init__(message)
        self.errors = errors or []


class ContractSchemaError(DataContractError):
    """契约 Schema 本身格式错误"""

    pass


class ContractVersionError(DataContractError):
    """版本不兼容错误"""

    pass


# ===================================================================
# ContractYAML —— 契约文件的加载、解析、校验
# ===================================================================


class ContractYAML:
    """
    契约 YAML 加载与校验引擎。

    职责:
      1. 从文件路径或字符串加载 YAML
      2. 校验契约自身的结构完整性
      3. 导出 / 格式化契约内容
      4. 契约 Schema 版本兼容性检查
    """

    # 契约 Schema 自身版本
    CONTRACT_SCHEMA_VERSION = "2.0"

    # 契约顶层必需的字段
    REQUIRED_TOP_KEYS = {"module", "version", "tables"}

    # 每个表必需的字段
    REQUIRED_TABLE_KEYS = {"allowed_fields"}

    # 约束支持的子键
    SUPPORTED_CONSTRAINT_KEYS = {
        "regex",
        "max_length",
        "min_length",
        "enum",
        "min",
        "max",
        "format",
        "pattern",
        "exclusive_min",
        "exclusive_max",
        "multiple_of",
        "default",
        "type",
    }

    def __init__(self, path: str | None = None, content: str | None = None):
        """
        初始化 ContractYAML。

        Args:
            path: YAML 文件路径
            content: YAML 字符串内容（与 path 二选一）
        """
        self._path = path
        self._raw_content = content
        self._data: dict | None = None
        self._loaded_at: float | None = None
        self._checksum: str | None = None

        if path:
            self.load(path)
        elif content:
            self.loads(content)

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def load(self, path: str) -> "ContractYAML":
        """
        从文件加载契约。

        Args:
            path: YAML 文件路径

        Returns:
            self 以支持链式调用

        Raises:
            ContractNotFoundError: 文件不存在或不可读
            ContractSchemaError: 契约结构非法
        """
        if not os.path.isfile(path):
            raise ContractNotFoundError(f"契约文件未找到: {path}")

        self._path = os.path.abspath(path)
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            raise ContractNotFoundError(f"无法读取契约文件 {path}: {e}")

        self._raw_content = raw
        self._checksum = hashlib.md5(raw.encode("utf-8")).hexdigest()
        return self._parse_and_validate(raw)

    def loads(self, content: str) -> "ContractYAML":
        """
        从字符串加载契约。

        Args:
            content: YAML 格式字符串

        Returns:
            self
        """
        self._raw_content = content
        self._checksum = hashlib.md5(content.encode("utf-8")).hexdigest()
        return self._parse_and_validate(content)

    def reload(self) -> "ContractYAML":
        """
        重新加载（热加载用）。

        Returns:
            self
        """
        if self._path:
            return self.load(self._path)
        if self._raw_content:
            return self.loads(self._raw_content)
        raise DataContractError("无可重新加载的源")

    def _parse_and_validate(self, raw: str) -> "ContractYAML":
        """解析并校验 YAML 结构"""
        try:
            import io

            stream = io.StringIO(raw)
            data = _yaml_load(stream)
        except Exception as e:
            raise ContractSchemaError(f"YAML 解析失败: {e}")

        if not isinstance(data, dict):
            raise ContractSchemaError("契约顶层必须是字典结构")

        self._data = data
        self._loaded_at = time.time()

        # 校验顶层结构
        self._validate_top_level()
        # 校验每个表的结构
        self._validate_tables()
        # 补充默认值
        self._apply_defaults()

        return self

    def _validate_top_level(self):
        """校验顶层必需字段"""
        missing = self.REQUIRED_TOP_KEYS - set(self._data.keys())
        if missing:
            raise ContractSchemaError(f"契约缺失顶层字段: {', '.join(sorted(missing))}")

        if not isinstance(self._data["module"], str) or not self._data["module"].strip():
            raise ContractSchemaError("契约 module 字段必须为非空字符串")

        if not isinstance(self._data["version"], str):
            raise ContractSchemaError("契约 version 字段必须为字符串 (如 '1.0')")

        if not isinstance(self._data["tables"], (list, dict)):
            raise ContractSchemaError("契约 tables 字段必须为列表或字典")

    def _validate_tables(self):
        """校验每个表的结构"""
        tables = self._get_tables_list()
        table_names = set()

        for idx, table in enumerate(tables):
            if not isinstance(table, dict):
                raise ContractSchemaError(f"tables[{idx}] 必须是字典")

            # 表名必需
            if "name" not in table:
                raise ContractSchemaError(f"tables[{idx}] 缺少 'name' 字段")
            tname = table["name"]
            if not isinstance(tname, str) or not tname.strip():
                raise ContractSchemaError(f"tables[{idx}] 'name' 必须为非空字符串")

            # 检查重名
            if tname in table_names:
                raise ContractSchemaError(f"表名重复: {tname}")
            table_names.add(tname)

            # allowed_fields 必需
            af = table.get("allowed_fields", [])
            if not isinstance(af, list):
                raise ContractSchemaError(f"表 {tname} 的 allowed_fields 必须是列表")
            if not af:
                raise ContractSchemaError(f"表 {tname} 的 allowed_fields 不能为空列表")

            # 校验 allowed_fields 内的字段
            for fd in af:
                if not isinstance(fd, str) or not fd.strip():
                    raise ContractSchemaError(f"表 {tname} 的 allowed_fields 包含非法字段名: {fd}")

            # required 可选，但必须是列表
            req = table.get("required", [])
            if not isinstance(req, list):
                raise ContractSchemaError(f"表 {tname} 的 required 必须是列表")

            # required 必须是 allowed_fields 的子集
            for r in req:
                if r not in set(af):
                    raise ContractSchemaError(f"表 {tname} 的 required 字段 '{r}' 不在 allowed_fields 中")

            # constraints 可选
            cons = table.get("constraints", {})
            if not isinstance(cons, dict):
                raise ContractSchemaError(f"表 {tname} 的 constraints 必须是字典")

            # 校验每个约束
            for field_name, rules in cons.items():
                if field_name not in set(af):
                    raise ContractSchemaError(
                        f"表 {tname} 的 constraints 引用了未在 allowed_fields 中的字段: {field_name}"
                    )
                if not isinstance(rules, dict):
                    raise ContractSchemaError(f"表 {tname} 的 constraints.{field_name} 必须是字典")
                for rule_key in rules:
                    if rule_key not in self.SUPPORTED_CONSTRAINT_KEYS:
                        raise ContractSchemaError(
                            f"表 {tname} 的 constraints.{field_name} 包含不支持的约束: {rule_key}"
                        )

            # not_allowed 可选，但必须是列表
            na = table.get("not_allowed", [])
            if not isinstance(na, list):
                raise ContractSchemaError(f"表 {tname} 的 not_allowed 必须是列表")

    def _apply_defaults(self):
        """补充默认值"""
        tables = self._data.get("tables", [])
        if isinstance(tables, dict):
            tables = list(tables.values())
        for table in tables:
            table.setdefault("required", [])
            table.setdefault("constraints", {})
            table.setdefault("not_allowed", [])
            table.setdefault("description", "")

    # ------------------------------------------------------------------
    # 查询方法
    # ------------------------------------------------------------------

    def get_module_name(self) -> str:
        """获取模块名称"""
        return self._data.get("module", "")

    def get_version(self) -> str:
        """获取契约版本号"""
        return self._data.get("version", "")

    def get_description(self) -> str:
        """获取模块描述"""
        return self._data.get("description", "")

    def get_all_table_names(self) -> list[str]:
        """获取所有表名列表"""
        return [t["name"] for t in self._get_tables_list()]

    def get_table(self, table_name: str) -> dict | None:
        """获取指定表的契约配置"""
        for t in self._get_tables_list():
            if t["name"] == table_name:
                return t
        return None

    def get_allowed_fields(self, table_name: str) -> list[str]:
        """获取指定表的允许字段列表"""
        table = self.get_table(table_name)
        return table.get("allowed_fields", []) if table else []

    def get_required_fields(self, table_name: str) -> list[str]:
        """获取指定表的必需字段列表"""
        table = self.get_table(table_name)
        return table.get("required", []) if table else []

    def get_constraints(self, table_name: str) -> dict:
        """获取指定表的约束字典"""
        table = self.get_table(table_name)
        return table.get("constraints", {}) if table else {}

    def get_not_allowed_fields(self, table_name: str) -> list[str]:
        """获取指定表的禁用字段列表"""
        table = self.get_table(table_name)
        return table.get("not_allowed", []) if table else []

    def get_raw_data(self) -> dict:
        """获取原始契约数据 (深拷贝)"""
        return copy.deepcopy(self._data)

    def get_path(self) -> str | None:
        """获取契约文件路径"""
        return self._path

    def get_checksum(self) -> str | None:
        """获取当前契约内容的 MD5 校验和"""
        return self._checksum

    def get_loaded_at(self) -> float | None:
        """获取加载时间戳"""
        return self._loaded_at

    def is_dirty(self) -> bool:
        """
        检查契约文件是否已被外部修改（热加载用）。

        Returns:
            如果文件内容发生变化返回 True
        """
        if not self._path:
            return False
        try:
            with open(self._path, encoding="utf-8") as f:
                current = hashlib.md5(f.read().encode("utf-8")).hexdigest()
            return current != self._checksum
        except OSError:
            return False

    def _get_tables_list(self) -> list[dict]:
        """获取 tables 的列表形式（兼容 dict/list 两种格式）"""
        tables = self._data.get("tables", [])
        if isinstance(tables, dict):
            return list(tables.values())
        return tables

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """导出为字典"""
        return self.get_raw_data()

    def to_yaml(self) -> str:
        """导出为 YAML 字符串"""
        import io

        buf = io.StringIO()
        _yaml_dump(self._data, buf)
        return buf.getvalue()

    def save(self, path: str | None = None) -> str:
        """
        保存契约到文件。

        Args:
            path: 目标路径，默认覆盖原文件

        Returns:
            保存的文件路径
        """
        target = path or self._path
        if not target:
            raise DataContractError("未指定保存路径")
        with open(target, "w", encoding="utf-8") as f:
            _yaml_dump(self._data, f)
        self._path = os.path.abspath(target)
        with open(target, encoding="utf-8") as f:
            self._checksum = hashlib.md5(f.read().encode("utf-8")).hexdigest()
        return self._path

    # ------------------------------------------------------------------
    # Schema 版本兼容性
    # ------------------------------------------------------------------

    @classmethod
    def check_schema_compatibility(cls, version: str) -> tuple[bool, str]:
        """
        检查契约 Schema 版本兼容性。

        Args:
            version: 待检查的版本号

        Returns:
            (是否兼容, 消息)
        """
        try:
            v1_parts = [int(x) for x in version.split(".")]
            v2_parts = [int(x) for x in cls.CONTRACT_SCHEMA_VERSION.split(".")]
        except (ValueError, AttributeError):
            return False, f"无法解析版本号: {version}"

        # 主版本不同则不兼容
        if v1_parts[0] != v2_parts[0]:
            return False, (f"主版本不兼容: 契约版本 {version}, 引擎支持 {cls.CONTRACT_SCHEMA_VERSION}")
        return True, "兼容"


# ===================================================================
# ContractValidator —— 数据校验引擎
# ===================================================================


class ContractValidator:
    """
    契约校验器 —— 对传入数据执行严格或宽松的契约校验。

    校验顺序:
      1. 字段白名单 (allowed_fields) —— 仅允许白名单内的字段
      2. 必需字段 (required) —— 检查非空
      3. 禁用字段 (not_allowed) —— 拒绝黑名单字段
      4. 约束规则 (constraints) —— regex, max_length, enum 等
    """

    # 约束类型与校验函数的映射
    CONSTRAINT_CHECKERS: dict[str, Callable] = {}

    # 日期/时间格式的正则缓存
    _format_patterns = {
        "date": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
        "time": re.compile(r"^\d{2}:\d{2}:\d{2}$"),
        "datetime": re.compile(
            r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
            r"(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$"
        ),
        "email": re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"),
        "phone": re.compile(r"^\+?1?\d{7,15}$"),
        "uuid": re.compile(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        ),
        "uri": re.compile(r"^https?://[^\s/$.?#].[^\s]*$"),
    }

    def __init__(self, contract: ContractYAML, strict_mode: bool = True):
        """
        初始化校验器。

        Args:
            contract: ContractYAML 实例
            strict_mode: True=严格模式(拒绝所有未声明字段),
                        False=宽松模式(仅校验声明的规则，额外字段静默通过)
        """
        self._contract = contract
        self._strict_mode = strict_mode

    # ------------------------------------------------------------------
    # 主校验入口
    # ------------------------------------------------------------------

    def validate(
        self,
        table_name: str,
        data: dict,
        context: dict | None = None,
    ) -> dict:
        """
        校验单条数据。

        Args:
            table_name: 表名
            data: 待校验的数据字典
            context: 上下文信息（调试用）

        Returns:
            清洗后的数据字典（去除了非法字段）

        Raises:
            ContractValidationError: 校验失败
        """
        errors: list[dict] = []
        table = self._contract.get_table(table_name)
        if not table:
            raise ContractValidationError(
                f"表 '{table_name}' 未在契约中定义", [{"field": "_table", "message": f"未定义的表: {table_name}"}]
            )

        allowed = set(table.get("allowed_fields", []))
        required = set(table.get("required", []))
        not_allowed = set(table.get("not_allowed", []))
        constraints = table.get("constraints", {})

        # 计算输入字段集合
        input_fields = set(data.keys())
        cleaned = {}

        # ---- 步骤1: 禁用字段检查 ----
        for field in input_fields:
            if field in not_allowed:
                errors.append(
                    {
                        "field": field,
                        "value": data[field],
                        "rule": "not_allowed",
                        "message": f"字段 '{field}' 被禁止写入",
                    }
                )

        # ---- 步骤2: 白名单检查 ----
        if self._strict_mode:
            extra_fields = input_fields - allowed
            for field in extra_fields:
                if field in not_allowed:
                    continue  # 已记录
                errors.append(
                    {
                        "field": field,
                        "value": data[field],
                        "rule": "not_allowed",
                        "message": (f"字段 '{field}' 不在 allowed_fields 中"),
                    }
                )

        # ---- 步骤3: 必需字段检查 ----
        missing_required = required - input_fields
        for field in sorted(missing_required):
            errors.append(
                {
                    "field": field,
                    "value": None,
                    "rule": "required",
                    "message": f"必需字段 '{field}' 缺失",
                }
            )

        # 空值检查（字段存在但值为 None/空字符串）
        for field in required:
            if field in data and data[field] is None:
                errors.append(
                    {
                        "field": field,
                        "value": None,
                        "rule": "required",
                        "message": f"必需字段 '{field}' 值为空 (None)",
                    }
                )

        # ---- 步骤4: 约束校验 ----
        for field in input_fields:
            if field in not_allowed:
                continue
            value = data[field]
            if field not in constraints:
                continue
            rules = constraints[field]

            # 空值跳过约束（required 已在上一步检查）
            if value is None:
                continue

            field_errors = self._check_constraints(field, value, rules)
            errors.extend(field_errors)

        # ---- 如果有错误，抛出异常 ----
        if errors:
            # 在宽松模式下，只报错确实违反约束的字段，忽略白名单外字段
            if not self._strict_mode:
                filtered_errors = [
                    e for e in errors if e["rule"] != "not_allowed" or "不在 allowed_fields" not in e["message"]
                ]
                # 但仍然保留 not_allowed 的硬禁止
                hard_blocked = [e for e in errors if e["rule"] == "not_allowed" and "被禁止写入" in e["message"]]
                errors = hard_blocked + filtered_errors

            if errors:
                raise ContractValidationError(f"表 '{table_name}' 数据校验失败 ({len(errors)} 个错误)", errors)

        # ---- 步骤5: 清洗（仅保留 allowed_fields 内的字段，去除 not_allowed）----
        if self._strict_mode:
            for field in allowed:
                if field in data and field not in not_allowed:
                    cleaned[field] = data[field]
        else:
            # 宽松模式：保留所有字段，但去除 not_allowed
            for field in data:
                if field not in not_allowed:
                    cleaned[field] = data[field]

        return cleaned

    def validate_batch(
        self,
        table_name: str,
        records: list[dict],
        raise_first: bool = False,
        context: dict | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """
        批量校验多条数据。

        Args:
            table_name: 表名
            records: 数据列表
            raise_first: 遇到第一条非法数据即抛出异常
            context: 上下文信息

        Returns:
            (合格数据列表, 不合格数据列表)
            不合格数据附加了 '_errors' 字段

        Raises:
            ContractValidationError: 当 raise_first=True 时
        """
        passed: list[dict] = []
        failed: list[dict] = []

        for idx, record in enumerate(records):
            try:
                cleaned = self.validate(table_name, record, context)
                passed.append(cleaned)
            except ContractValidationError as e:
                failed_record = copy.deepcopy(record)
                failed_record["_errors"] = e.errors
                failed_record["_row_index"] = idx
                failed.append(failed_record)
                if raise_first:
                    raise ContractValidationError(f"批量校验失败 (第 {idx} 行): {e}", e.errors) from e

        return passed, failed

    def validate_schema(
        self,
        table_name: str,
        fields: dict[str, type],
    ) -> list[dict]:
        """
        校验传入字段的 schema 类型是否与契约一致。

        Args:
            table_name: 表名
            fields: 字段名到 Python 类型的映射

        Returns:
            类型不匹配的错误列表
        """
        errors = []
        table = self._contract.get_table(table_name)
        if not table:
            return [{"field": "_table", "message": f"未定义的表: {table_name}"}]

        allowed = set(table.get("allowed_fields", []))
        for field, py_type in fields.items():
            if field not in allowed:
                continue
            # 这里仅做基础类型检查提示，不抛异常
            if py_type not in (str, int, float, bool, list, dict, type(None)):
                errors.append(
                    {
                        "field": field,
                        "message": f"不支持的 Python 类型: {py_type.__name__}",
                    }
                )
        return errors

    # ------------------------------------------------------------------
    # 约束检查
    # ------------------------------------------------------------------

    def _check_constraints(self, field: str, value: Any, rules: dict) -> list[dict]:
        """对单个字段执行所有约束规则"""
        errors = []

        for rule_name, rule_value in rules.items():
            checker = self.CONSTRAINT_CHECKERS.get(rule_name)
            if checker:
                try:
                    checker(self, field, value, rule_value, errors)
                except Exception as e:
                    errors.append(
                        {
                            "field": field,
                            "value": value,
                            "rule": rule_name,
                            "message": f"约束检查异常: {e}",
                        }
                    )
            else:
                # 内置检查
                try:
                    self._check_builtin(field, value, rule_name, rule_value, errors)
                except Exception as e:
                    errors.append(
                        {
                            "field": field,
                            "value": value,
                            "rule": rule_name,
                            "message": f"约束检查内部错误: {e}",
                        }
                    )

        return errors

    def _check_builtin(self, field: str, value: Any, rule: str, param: Any, errors: list[dict]):
        """内置约束检查"""
        # ---- regex ----
        if rule == "regex":
            if not isinstance(value, str):
                errors.append(
                    {
                        "field": field,
                        "value": value,
                        "rule": rule,
                        "message": f"字段 '{field}' 必须为字符串才能执行正则匹配",
                    }
                )
                return
            try:
                if not re.match(param, value):
                    errors.append(
                        {
                            "field": field,
                            "value": value,
                            "rule": rule,
                            "message": f"字段 '{field}' 不匹配正则: {param}",
                        }
                    )
            except re.error as e:
                errors.append(
                    {
                        "field": field,
                        "value": value,
                        "rule": rule,
                        "message": f"正则表达式错误 '{param}': {e}",
                    }
                )

        # ---- max_length ----
        elif rule == "max_length":
            if isinstance(value, (str, list, dict, tuple)):
                if len(value) > int(param):
                    errors.append(
                        {
                            "field": field,
                            "value": value,
                            "rule": rule,
                            "message": (f"字段 '{field}' 长度 {len(value)} 超过最大限制 {param}"),
                        }
                    )

        # ---- min_length ----
        elif rule == "min_length":
            if isinstance(value, (str, list, dict, tuple)):
                if len(value) < int(param):
                    errors.append(
                        {
                            "field": field,
                            "value": value,
                            "rule": rule,
                            "message": (f"字段 '{field}' 长度 {len(value)} 低于最小限制 {param}"),
                        }
                    )

        # ---- enum ----
        elif rule == "enum":
            if isinstance(param, (list, tuple)) and value not in param:
                errors.append(
                    {
                        "field": field,
                        "value": value,
                        "rule": rule,
                        "message": (f"字段 '{field}' 的值 '{value}' 不在允许枚举值 {param} 中"),
                    }
                )

        # ---- min ----
        elif rule == "min":
            try:
                if float(value) < float(param):
                    errors.append(
                        {
                            "field": field,
                            "value": value,
                            "rule": rule,
                            "message": (f"字段 '{field}' 的值 {value} 小于最小值 {param}"),
                        }
                    )
            except (ValueError, TypeError):
                pass

        # ---- max ----
        elif rule == "max":
            try:
                if float(value) > float(param):
                    errors.append(
                        {
                            "field": field,
                            "value": value,
                            "rule": rule,
                            "message": (f"字段 '{field}' 的值 {value} 大于最大值 {param}"),
                        }
                    )
            except (ValueError, TypeError):
                pass

        # ---- exclusive_min ----
        elif rule == "exclusive_min":
            try:
                if float(value) <= float(param):
                    errors.append(
                        {
                            "field": field,
                            "value": value,
                            "rule": rule,
                            "message": (f"字段 '{field}' 的值 {value} 必须严格大于 {param}"),
                        }
                    )
            except (ValueError, TypeError):
                pass

        # ---- exclusive_max ----
        elif rule == "exclusive_max":
            try:
                if float(value) >= float(param):
                    errors.append(
                        {
                            "field": field,
                            "value": value,
                            "rule": rule,
                            "message": (f"字段 '{field}' 的值 {value} 必须严格小于 {param}"),
                        }
                    )
            except (ValueError, TypeError):
                pass

        # ---- multiple_of ----
        elif rule == "multiple_of":
            try:
                v = float(value)
                m = float(param)
                if m != 0 and v % m != 0:
                    errors.append(
                        {
                            "field": field,
                            "value": value,
                            "rule": rule,
                            "message": (f"字段 '{field}' 的值 {value} 不是 {param} 的倍数"),
                        }
                    )
            except (ValueError, TypeError):
                pass

        # ---- format ----
        elif rule == "format":
            pattern = self._format_patterns.get(param)
            if pattern:
                if not isinstance(value, str):
                    errors.append(
                        {
                            "field": field,
                            "value": value,
                            "rule": rule,
                            "message": f"字段 '{field}' 必须为字符串才能校验格式 '{param}'",
                        }
                    )
                elif not pattern.match(value):
                    errors.append(
                        {
                            "field": field,
                            "value": value,
                            "rule": rule,
                            "message": (f"字段 '{field}' 的值 '{value}' 不符合格式 '{param}'"),
                        }
                    )
            else:
                errors.append(
                    {
                        "field": field,
                        "value": value,
                        "rule": rule,
                        "message": f"不支持的格式类型: '{param}'",
                    }
                )

        # ---- default ----
        elif rule == "default":
            # default 在清洗时使用，不在校验时报错
            pass

        # ---- type ----
        elif rule == "type":
            type_map = {
                "string": str,
                "str": str,
                "integer": int,
                "int": int,
                "float": float,
                "number": (int, float),
                "boolean": bool,
                "bool": bool,
                "list": list,
                "array": list,
                "dict": dict,
                "object": dict,
            }
            expected_type = type_map.get(str(param).lower())
            if expected_type and not isinstance(value, expected_type):
                type_name = str(param)
                actual_type = type(value).__name__
                errors.append(
                    {
                        "field": field,
                        "value": value,
                        "rule": rule,
                        "message": (f"字段 '{field}' 期望类型为 {type_name}, 实际为 {actual_type}"),
                    }
                )

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def strict_mode(self) -> bool:
        return self._strict_mode

    @strict_mode.setter
    def strict_mode(self, value: bool):
        self._strict_mode = value

    @property
    def contract(self) -> ContractYAML:
        return self._contract


# ===================================================================
# ContractManager —— 版本管理、热加载、迁移
# ===================================================================


class ContractManager:
    """
    契约管理器 —— 全局单例风格的契约管理。

    功能:
      1. 多模块契约注册与统一管理
      2. 契约热加载（文件改动自动感知）
      3. 版本管理（v1.0 -> v2.0 迁移）
      4. 校验器缓存
    """

    def __init__(self, auto_reload: bool = True, poll_interval: int = 10):
        """
        初始化契约管理器。

        Args:
            auto_reload: 是否启用热加载（轮询文件变更）
            poll_interval: 轮询间隔（秒）
        """
        self._contracts: dict[str, ContractYAML] = OrderedDict()
        self._validators: dict[str, ContractValidator] = {}
        self._auto_reload = auto_reload
        self._poll_interval = poll_interval
        self._last_poll_time: float = 0.0
        self._migration_scripts: dict[str, dict[str, Callable]] = {}
        # 模块 -> [(from_ver, to_ver, script)]
        self._migration_paths: dict[str, list[tuple[str, str, Callable]]] = {}

    # ------------------------------------------------------------------
    # 注册与加载
    # ------------------------------------------------------------------

    def register(self, module_name: str, contract: ContractYAML) -> "ContractManager":
        """
        注册一个契约。

        Args:
            module_name: 模块名称（唯一标识）
            contract: ContractYAML 实例
        """
        if module_name in self._contracts:
            raise DataContractError(f"模块 '{module_name}' 的契约已注册")
        self._contracts[module_name] = contract
        self._validators[module_name] = ContractValidator(contract)
        return self

    def register_from_file(self, module_name: str, path: str) -> "ContractManager":
        """
        从文件注册契约。

        Args:
            module_name: 模块名称
            path: YAML 文件路径
        """
        contract = ContractYAML(path)
        return self.register(module_name, contract)

    def unregister(self, module_name: str) -> bool:
        """注销一个契约"""
        self._contracts.pop(module_name, None)
        self._validators.pop(module_name, None)
        return True

    def get_contract(self, module_name: str) -> ContractYAML | None:
        """获取指定模块的契约"""
        self._check_reload()
        return self._contracts.get(module_name)

    def get_validator(self, module_name: str, strict_mode: bool | None = None) -> ContractValidator | None:
        """
        获取指定模块的校验器。

        Args:
            module_name: 模块名称
            strict_mode: 覆盖严格模式（None=使用当前设置）
        """
        self._check_reload()
        validator = self._validators.get(module_name)
        if validator and strict_mode is not None:
            validator.strict_mode = strict_mode
        return validator

    def validate(
        self,
        module_name: str,
        table_name: str,
        data: dict,
        strict_mode: bool | None = None,
    ) -> dict:
        """
        便捷方法：校验数据。

        Args:
            module_name: 模块名称
            table_name: 表名
            data: 待校验数据
            strict_mode: 覆盖严格模式

        Returns:
            清洗后的数据
        """
        validator = self.get_validator(module_name, strict_mode)
        if not validator:
            raise ContractNotFoundError(f"模块 '{module_name}' 未注册契约")
        return validator.validate(table_name, data)

    def validate_batch(
        self,
        module_name: str,
        table_name: str,
        records: list[dict],
        raise_first: bool = False,
        strict_mode: bool | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """便捷方法：批量校验"""
        validator = self.get_validator(module_name, strict_mode)
        if not validator:
            raise ContractNotFoundError(f"模块 '{module_name}' 未注册契约")
        return validator.validate_batch(table_name, records, raise_first)

    def list_modules(self) -> list[str]:
        """列出所有已注册的模块名"""
        self._check_reload()
        return list(self._contracts.keys())

    # ------------------------------------------------------------------
    # 热加载
    # ------------------------------------------------------------------

    def _check_reload(self):
        """检查是否需要热加载（轮询）"""
        if not self._auto_reload:
            return
        now = time.time()
        if now - self._last_poll_time < self._poll_interval:
            return
        self._last_poll_time = now
        self._reload_dirty()

    def _reload_dirty(self):
        """重新加载所有变脏的契约"""
        for module_name, contract in list(self._contracts.items()):
            if contract.is_dirty():
                try:
                    old_version = contract.get_version()
                    contract.reload()
                    new_version = contract.get_version()
                    # 版本迁移
                    if old_version != new_version:
                        self._run_migration(module_name, old_version, new_version)
                    # 刷新校验器
                    self._validators[module_name] = ContractValidator(contract)
                except Exception:
                    # 热加载失败不应阻断，记录即可
                    pass

    def force_reload(self, module_name: str | None = None) -> int:
        """
        强制重新加载契约。

        Args:
            module_name: 指定模块（None=全部）

        Returns:
            重载成功的数量
        """
        count = 0
        targets = [module_name] if module_name else list(self._contracts.keys())
        for name in targets:
            contract = self._contracts.get(name)
            if contract:
                try:
                    old_version = contract.get_version()
                    contract.reload()
                    if contract.get_version() != old_version:
                        self._run_migration(name, old_version, contract.get_version())
                    self._validators[name] = ContractValidator(contract)
                    count += 1
                except Exception:
                    pass
        return count

    # ------------------------------------------------------------------
    # 版本管理与迁移
    # ------------------------------------------------------------------

    def register_migration(
        self,
        module_name: str,
        from_version: str,
        to_version: str,
        script: Callable[[dict], dict],
    ) -> "ContractManager":
        """
        注册版本迁移脚本。

        Args:
            module_name: 模块名
            from_version: 源版本
            to_version: 目标版本
            script: 迁移函数 (data: Dict) -> Dict
        """
        key = f"{from_version}->{to_version}"
        self._migration_scripts.setdefault(module_name, {})[key] = script
        self._migration_paths.setdefault(module_name, []).append((from_version, to_version, script))
        return self

    def _run_migration(self, module_name: str, from_ver: str, to_ver: str):
        """执行版本迁移"""
        scripts = self._migration_scripts.get(module_name, {})
        key = f"{from_ver}->{to_ver}"
        if key in scripts:
            try:
                contract = self._contracts.get(module_name)
                if contract:
                    raw = contract.get_raw_data()
                    migrated = scripts[key](raw)
                    # 写回
                    new_contract = ContractYAML(content=_yaml_dump_to_str(migrated))
                    self._contracts[module_name] = new_contract
            except Exception as e:
                raise ContractVersionError(f"模块 '{module_name}' 从 {from_ver} 迁移到 {to_ver} 失败: {e}") from e

    def get_migration_chain(self, module_name: str, from_version: str, to_version: str) -> list[tuple[str, str]]:
        """
        获取迁移路径链。

        Args:
            module_name: 模块名
            from_version: 起始版本
            to_version: 目标版本

        Returns:
            [(from, to), ...] 迁移步骤列表
        """
        paths = self._migration_paths.get(module_name, [])
        # 简单贪心：找到从 from -> to 的路径
        chain = []
        current = from_version
        visited = {current}
        max_steps = 20
        while current != to_version and len(chain) < max_steps:
            found = False
            for fv, tv, _ in paths:
                if fv == current and tv not in visited:
                    chain.append((fv, tv))
                    current = tv
                    visited.add(tv)
                    found = True
                    break
            if not found:
                break
        return chain if current == to_version else []

    # ------------------------------------------------------------------
    # 批量管理
    # ------------------------------------------------------------------

    def load_directory(self, directory: str, pattern: str = "*.yaml") -> int:
        """
        从目录批量加载契约文件。

        Args:
            directory: 目录路径
            pattern: 文件匹配模式

        Returns:
            成功加载的数量
        """
        count = 0
        if not os.path.isdir(directory):
            raise ContractNotFoundError(f"目录不存在: {directory}")
        for fname in sorted(os.listdir(directory)):
            if fnmatch.fnmatch(fname, pattern):
                fpath = os.path.join(directory, fname)
                try:
                    # 使用文件名（不含扩展名）作为模块名
                    module_name = os.path.splitext(fname)[0]
                    self.register_from_file(module_name, fpath)
                    count += 1
                except Exception:
                    pass
        return count

    def summary(self) -> dict:
        """
        获取管理器摘要。

        Returns:
            {
                'modules': { 'module_name': { 'version', 'path', 'tables', 'checksum' } },
                'auto_reload': bool,
                'poll_interval': int,
            }
        """
        modules_info = {}
        for name, contract in self._contracts.items():
            modules_info[name] = {
                "version": contract.get_version(),
                "path": contract.get_path(),
                "tables": contract.get_all_table_names(),
                "checksum": contract.get_checksum(),
                "loaded_at": contract.get_loaded_at(),
            }
        return {
            "modules": modules_info,
            "auto_reload": self._auto_reload,
            "poll_interval": self._poll_interval,
            "module_count": len(self._contracts),
        }


# ===================================================================
# ContractAutoGenerator —— 从 SQLAlchemy Model 自动生成契约 YAML
# ===================================================================


class ContractAutoGenerator:
    """
    契约自动生成器 —— 从 SQLAlchemy 模型类自动生成 YAML 契约文件。

    用法:
        generator = ContractAutoGenerator()
        generator.register_model(MyModel, table_name='my_table')
        contract = generator.generate(module_name='my_module', version='1.0')
        contract.save('path/to/contract.yaml')
    """

    # Python 类型到约束的映射提示
    TYPE_CONSTRAINT_HINTS = {
        str: {"max_length": 255},
        int: {},
        float: {},
        bool: {},
        datetime: {"format": "datetime"},
        date: {"format": "date"},
    }

    def __init__(self):
        self._models: dict[str, Any] = OrderedDict()
        self._table_names: dict[str, str] = {}
        self._custom_constraints: dict[str, dict[str, dict]] = {}
        self._custom_required: dict[str, list[str]] = {}
        self._custom_not_allowed: dict[str, list[str]] = {}
        self._field_mapping: dict[str, dict[str, str]] = {}
        self._excluded_fields: dict[str, set[str]] = {}

    def register_model(
        self,
        model_class: Any,
        table_name: str | None = None,
        field_mapping: dict[str, str] | None = None,
        excluded_fields: list[str] | None = None,
    ) -> "ContractAutoGenerator":
        """
        注册一个 SQLAlchemy 模型类。

        Args:
            model_class: SQLAlchemy 模型类（或任何有 __table__ 和 columns 的类）
            table_name: 表名（默认使用 model.__tablename__）
            field_mapping: 字段名映射 {model_field: contract_field}
            excluded_fields: 排除的字段列表

        Returns:
            self
        """
        name = table_name or getattr(model_class, "__tablename__", model_class.__name__)
        self._models[name] = model_class
        self._table_names[name] = name

        if field_mapping:
            self._field_mapping[name] = field_mapping

        if excluded_fields:
            self._excluded_fields[name] = set(excluded_fields)

        return self

    def add_constraints(
        self,
        table_name: str,
        constraints: dict[str, dict],
    ) -> "ContractAutoGenerator":
        """
        为指定表添加自定义约束。

        Args:
            table_name: 表名
            constraints: {field_name: {rule: value, ...}}
        """
        self._custom_constraints.setdefault(table_name, {}).update(constraints)
        return self

    def add_required(
        self,
        table_name: str,
        fields: list[str],
    ) -> "ContractAutoGenerator":
        """添加必需字段"""
        self._custom_required.setdefault(table_name, []).extend(fields)
        return self

    def add_not_allowed(
        self,
        table_name: str,
        fields: list[str],
    ) -> "ContractAutoGenerator":
        """添加禁用字段"""
        self._custom_not_allowed.setdefault(table_name, []).extend(fields)
        return self

    def generate(
        self,
        module_name: str,
        version: str = "1.0",
        description: str = "",
        optional_defaults: bool = True,
    ) -> ContractYAML:
        """
        生成契约对象。

        Args:
            module_name: 模块名称
            version: 契约版本号
            description: 模块描述
            optional_defaults: 是否为可选字段设置 default 约束

        Returns:
            ContractYAML 实例
        """
        tables = []
        for table_name, model_class in self._models.items():
            table_def = self._generate_table(table_name, model_class, optional_defaults)
            tables.append(table_def)

        data = {
            "contract_schema": ContractYAML.CONTRACT_SCHEMA_VERSION,
            "module": module_name,
            "version": version,
            "description": description,
            "tables": tables,
        }

        yaml_str = _yaml_dump_to_str(data)
        return ContractYAML(content=yaml_str)

    def generate_and_save(
        self,
        output_dir: str,
        module_name: str,
        version: str = "1.0",
        description: str = "",
    ) -> str:
        """
        生成并保存契约文件。

        Args:
            output_dir: 输出目录
            module_name: 模块名（同时也是文件名）
            version: 版本号
            description: 描述

        Returns:
            保存的文件路径
        """
        contract = self.generate(module_name, version, description)
        os.makedirs(output_dir, exist_ok=True)
        fpath = os.path.join(output_dir, f"{module_name}.yaml")
        contract.save(fpath)
        return fpath

    def _generate_table(
        self,
        table_name: str,
        model_class: Any,
        optional_defaults: bool,
    ) -> dict:
        """从模型类生成单表定义"""
        allowed_fields = []
        constraints = {}
        required_fields = []

        excluded = self._excluded_fields.get(table_name, set())
        field_map = self._field_mapping.get(table_name, {})

        # 尝试从 SQLAlchemy 模型中提取列信息
        columns = self._extract_columns(model_class)

        for col_name, col in columns.items():
            if col_name in excluded:
                continue
            # 字段映射
            contract_name = field_map.get(col_name, col_name)
            allowed_fields.append(contract_name)

            # 提取列约束
            col_constraints = self._extract_column_constraints(col, optional_defaults)
            if col_constraints:
                constraints[contract_name] = col_constraints

            # 必填检查（nullable=False 且无 default）
            if self._is_required_column(col):
                required_fields.append(contract_name)

        # 合并自定义约束
        custom_cons = self._custom_constraints.get(table_name, {})
        for field, rules in custom_cons.items():
            if field in constraints:
                constraints[field].update(rules)
            else:
                constraints[field] = rules

        # 合并自定义 required
        custom_req = self._custom_required.get(table_name, [])
        for f in custom_req:
            if f not in required_fields and f in allowed_fields:
                required_fields.append(f)

        # not_allowed
        not_allowed = self._custom_not_allowed.get(table_name, [])

        return {
            "name": table_name,
            "allowed_fields": allowed_fields,
            "required": required_fields,
            "constraints": constraints,
            "not_allowed": not_allowed,
        }

    def _extract_columns(self, model_class) -> dict:
        """提取模型类的列信息"""
        columns = OrderedDict()

        # SQLAlchemy 声明式模型
        if hasattr(model_class, "__table__") and model_class.__table__ is not None:
            for col in model_class.__table__.columns:
                columns[col.name] = col
            return columns

        # SQLAlchemy 2.0+ mapped_column
        if hasattr(model_class, "__mapper__"):
            for col in model_class.__mapper__.columns:
                columns[col.name] = col
            return columns

        # 备用：遍历类属性推断
        for attr_name in dir(model_class):
            if attr_name.startswith("_"):
                continue
            attr = getattr(model_class, attr_name, None)
            if attr is not None and hasattr(attr, "type"):
                columns[attr_name] = attr

        return columns

    def _extract_column_constraints(self, column, optional_defaults: bool) -> dict:
        """从列信息中提取约束规则"""
        constraints = {}

        col_type = getattr(column, "type", None)
        if col_type is None:
            return constraints

        type_name = str(col_type).lower()

        # 字符串类型
        if "varchar" in type_name or "string" in type_name or "text" in type_name:
            length = getattr(col_type, "length", None)
            if length:
                constraints["max_length"] = length
            # 如果列有 Python 类型提示
            if hasattr(column, "type") and hasattr(column.type, "python_type"):
                pass

        # 整数 / 浮点数
        elif "integer" in type_name or "int" in type_name:
            constraints.setdefault("min", 0)

        elif "float" in type_name or "numeric" in type_name or "decimal" in type_name:
            constraints.setdefault("min", 0.0)

        # 布尔
        elif "boolean" in type_name or "bool" in type_name:
            constraints["enum"] = [True, False]

        # 日期时间
        elif "datetime" in type_name:
            constraints["format"] = "datetime"

        elif "date" in type_name:
            constraints["format"] = "date"

        # enum 类型
        if hasattr(col_type, "enums"):
            constraints["enum"] = list(col_type.enums)

        # 默认值
        if optional_defaults:
            default = getattr(column, "default", None)
            if default is not None and not callable(default):
                constraints.setdefault("default", default)

        return constraints

    def _is_required_column(self, column) -> bool:
        """判断列是否为必需"""
        nullable = getattr(column, "nullable", True)
        if nullable:
            return False
        default = getattr(column, "default", None)
        server_default = getattr(column, "server_default", None)
        return default is None and server_default is None

    # ------------------------------------------------------------------
    # 从现有数据库 Schema 生成
    # ------------------------------------------------------------------

    @staticmethod
    def from_dict_schema(
        module_name: str,
        version: str,
        schema_dict: dict[str, dict],
        description: str = "",
    ) -> ContractYAML:
        """
        从手动定义的字典 Schema 生成契约。

        Args:
            module_name: 模块名称
            version: 版本号
            schema_dict: {
                'table_name': {
                    'fields': ['field1', 'field2', ...],
                    'required': ['field1'],
                    'constraints': {'field1': {'max_length': 100}},
                    'not_allowed': [],
                }
            }
            description: 模块描述

        Returns:
            ContractYAML 实例
        """
        tables = []
        for table_name, table_def in schema_dict.items():
            entry = {
                "name": table_name,
                "allowed_fields": table_def.get("fields", []),
                "required": table_def.get("required", []),
                "constraints": table_def.get("constraints", {}),
                "not_allowed": table_def.get("not_allowed", []),
                "description": table_def.get("description", ""),
            }
            tables.append(entry)

        data = {
            "contract_schema": ContractYAML.CONTRACT_SCHEMA_VERSION,
            "module": module_name,
            "version": version,
            "description": description,
            "tables": tables,
        }

        yaml_str = _yaml_dump_to_str(data)
        return ContractYAML(content=yaml_str)


# ===================================================================
# 工具函数
# ===================================================================


def _yaml_dump_to_str(data: dict) -> str:
    """将字典序列化为 YAML 字符串"""
    import io

    buf = io.StringIO()
    _yaml_dump(data, buf)
    return buf.getvalue()


def diff_contracts(
    old_contract: ContractYAML,
    new_contract: ContractYAML,
) -> dict:
    """
    对比两个契约的差异。

    Returns:
        {
            'module': {'old': ..., 'new': ...},
            'version': {'old': ..., 'new': ...},
            'tables_added': [...],
            'tables_removed': [...],
            'tables_modified': {
                'table_name': {
                    'fields_added': [...],
                    'fields_removed': [...],
                    'required_changed': {...},
                    'constraints_changed': {...},
                }
            }
        }
    """
    diff = {
        "module": {
            "old": old_contract.get_module_name(),
            "new": new_contract.get_module_name(),
        },
        "version": {
            "old": old_contract.get_version(),
            "new": new_contract.get_version(),
        },
        "tables_added": [],
        "tables_removed": [],
        "tables_modified": {},
    }

    old_tables = {t["name"]: t for t in old_contract._get_tables_list()}
    new_tables = {t["name"]: t for t in new_contract._get_tables_list()}

    old_names = set(old_tables.keys())
    new_names = set(new_tables.keys())

    diff["tables_added"] = sorted(new_names - old_names)
    diff["tables_removed"] = sorted(old_names - new_names)

    for name in sorted(old_names & new_names):
        ot = old_tables[name]
        nt = new_tables[name]
        modification = {}

        old_fields = set(ot.get("allowed_fields", []))
        new_fields = set(nt.get("allowed_fields", []))

        added = new_fields - old_fields
        removed = old_fields - new_fields

        if added:
            modification["fields_added"] = sorted(added)
        if removed:
            modification["fields_removed"] = sorted(removed)

        # 检查 required 变化
        old_req = set(ot.get("required", []))
        new_req = set(nt.get("required", []))
        if old_req != new_req:
            modification["required_changed"] = {
                "old": sorted(old_req),
                "new": sorted(new_req),
            }

        # 检查约束变化
        old_cons = ot.get("constraints", {})
        new_cons = nt.get("constraints", {})
        if old_cons != new_cons:
            modification["constraints_changed"] = {
                "old": old_cons,
                "new": new_cons,
            }

        if modification:
            diff["tables_modified"][name] = modification

    return diff


def validate_yaml_file(path: str) -> tuple[bool, list[str]]:
    """
    验证一个 YAML 文件是否是合法的契约文件。

    Args:
        path: YAML 文件路径

    Returns:
        (是否合法, 错误消息列表)
    """
    errors = []
    try:
        contract = ContractYAML(path)
        errors.append(f"✓ 模块: {contract.get_module_name()}")
        errors.append(f"✓ 版本: {contract.get_version()}")
        errors.append(f"✓ 表数: {len(contract.get_all_table_names())}")
        for tname in contract.get_all_table_names():
            fields = len(contract.get_allowed_fields(tname))
            req = len(contract.get_required_fields(tname))
            errors.append(f"  - {tname}: {fields} 字段, {req} 必填")
        return True, errors
    except (ContractNotFoundError, ContractSchemaError) as e:
        return False, [str(e)]
    except Exception as e:
        return False, [f"未知错误: {e}"]


# ===================================================================
# 快速入口
# ===================================================================

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("  数据契约系统 Data Contract System v2.0")
    print("  Schema 版本:", ContractYAML.CONTRACT_SCHEMA_VERSION)
    print("=" * 60)

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "validate" and len(sys.argv) > 2:
            for fpath in sys.argv[2:]:
                ok, msgs = validate_yaml_file(fpath)
                print(f"\n--- {fpath} ---")
                for m in msgs:
                    print(f"  {m}")
                print(f"  结果: {'通过' if ok else '失败'}")
