"""数据安全模块 — 数据契约系统单元测试 (core/data_contract.py)"""

import os
import sys
import tempfile

import pytest

# 将 core/ 加入 sys.path
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CORE = os.path.join(_BASE, "data_security", "core")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from data_contract import (
    ContractAutoGenerator,
    ContractManager,
    ContractNotFoundError,
    ContractSchemaError,
    ContractValidationError,
    ContractValidator,
    ContractYAML,
    DataContractError,
    _SimpleYAML,
)

# ── 测试用 YAML 契约样本 ──────────────────────────────────────────

SAMPLE_CONTRACT_YAML = """
module: test_module
version: "1.0"
description: 测试用数据契约
tables:
  - name: users
    description: 用户表
    allowed_fields:
      - id
      - name
      - email
      - phone
      - age
    required:
      - name
      - email
    constraints:
      name:
        type: string
        max_length: 50
        min_length: 1
      email:
        type: string
        regex: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\\\.[a-zA-Z]{2,}$"
      age:
        type: integer
        min: 0
        max: 150
    not_allowed: []
  - name: products
    allowed_fields:
      - id
      - title
      - price
    required:
      - title
    constraints:
      price:
        type: float
        min: 0
"""

INVALID_CONTRACT_NO_MODULE = """
version: "1.0"
tables: []
"""

INVALID_CONTRACT_NO_TABLES = """
module: test
version: "1.0"
"""


class TestSimpleYAML:
    """内置简易 YAML 解析器测试"""

    def test_parse_simple_key_value(self):
        yaml_str = "name: 张三\nage: 25\n"
        result = _SimpleYAML._parse(_SimpleYAML._tokenize(yaml_str))
        assert result["name"] == "张三"
        assert result["age"] == 25

    def test_parse_nested(self):
        yaml_str = "user:\n  name: 张三\n  age: 25\n"
        result = _SimpleYAML._parse(_SimpleYAML._tokenize(yaml_str))
        assert result["user"]["name"] == "张三"
        assert result["user"]["age"] == 25

    def test_parse_list(self):
        yaml_str = "items:\n  - apple\n  - banana\n  - cherry\n"
        result = _SimpleYAML._parse(_SimpleYAML._tokenize(yaml_str))
        assert "items" in result
        assert "apple" in str(result)

    def test_parse_bool_and_null(self):
        yaml_str = "active: true\nflag: false\ndata: null\n"
        result = _SimpleYAML._parse(_SimpleYAML._tokenize(yaml_str))
        assert result["active"] is True
        assert result["flag"] is False
        assert result["data"] is None

    def test_parse_numbers(self):
        yaml_str = "int_val: 42\nfloat_val: 3.14\n"
        result = _SimpleYAML._parse(_SimpleYAML._tokenize(yaml_str))
        assert result["int_val"] == 42
        assert result["float_val"] == 3.14


class TestContractYAML:
    """ContractYAML 加载与校验测试"""

    def test_load_from_string_valid(self):
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        assert contract.get_module_name() == "test_module"
        assert contract.get_version() == "1.0"

    def test_get_all_table_names(self):
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        tables = contract.get_all_table_names()
        assert "users" in tables
        assert "products" in tables

    def test_get_table(self):
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        table = contract.get_table("users")
        assert table is not None
        assert table["name"] == "users"
        assert "id" in table["allowed_fields"]

    def test_get_table_not_found(self):
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        assert contract.get_table("nonexistent") is None

    def test_get_allowed_fields(self):
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        fields = contract.get_allowed_fields("users")
        assert "name" in fields
        assert "email" in fields

    def test_get_required_fields(self):
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        required = contract.get_required_fields("users")
        assert "name" in required
        assert "email" in required

    def test_get_constraints(self):
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        constraints = contract.get_constraints("users")
        assert "name" in constraints
        assert "email" in constraints
        assert constraints["age"]["type"] == "integer"

    def test_load_invalid_no_module(self):
        with pytest.raises(ContractSchemaError, match=".*module.*"):
            ContractYAML(content=INVALID_CONTRACT_NO_MODULE)

    def test_load_invalid_no_tables(self):
        with pytest.raises(ContractSchemaError, match=".*tables.*"):
            ContractYAML(content=INVALID_CONTRACT_NO_TABLES)

    def test_load_not_a_dict(self):
        with pytest.raises(ContractSchemaError):
            ContractYAML(content="just a string")

    def test_file_not_found(self):
        with pytest.raises(ContractNotFoundError):
            ContractYAML(path="/nonexistent/contract.yaml")

    def test_load_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(SAMPLE_CONTRACT_YAML)
            f.flush()
            fname = f.name
        try:
            contract = ContractYAML(path=fname)
            assert contract.get_module_name() == "test_module"
        finally:
            os.unlink(fname)

    def test_reload(self):
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        contract.reload()
        assert contract.get_module_name() == "test_module"

    def test_contract_schema_version(self):
        assert ContractYAML.CONTRACT_SCHEMA_VERSION == "2.0"

    def test_checksum_provided(self):
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        assert contract._checksum is not None
        assert len(contract._checksum) == 32  # md5


class TestContractValidator:
    """契约校验器测试"""

    @pytest.fixture
    def contract(self):
        return ContractYAML(content=SAMPLE_CONTRACT_YAML)

    def test_validate_valid_data(self, contract):
        validator = ContractValidator(contract)
        data = {"name": "张三", "email": "zhangsan@test.com", "age": 25}
        result = validator.validate("users", data)
        assert result["name"] == "张三"
        assert result["email"] == "zhangsan@test.com"

    def test_validate_missing_required_field(self, contract):
        validator = ContractValidator(contract)
        data = {"name": "张三"}  # 缺少 email (required)
        with pytest.raises(ContractValidationError):
            validator.validate("users", data)

    def test_validate_not_allowed_field(self, contract):
        validator = ContractValidator(contract)
        data = {"name": "张三", "email": "a@b.com", "hacker_field": "evil"}
        with pytest.raises(ContractValidationError):
            validator.validate("users", data)

    def test_validate_table_not_in_contract(self, contract):
        validator = ContractValidator(contract)
        with pytest.raises(ContractValidationError):
            validator.validate("nonexistent_table", {"name": "test"})

    def test_validate_constraint_regex(self, contract):
        validator = ContractValidator(contract)
        data = {"name": "李四", "email": "not-an-email"}  # email 不匹配 regex
        with pytest.raises(ContractValidationError):
            validator.validate("users", data)

    def test_validate_constraint_min_max(self, contract):
        validator = ContractValidator(contract)
        # age 超出范围
        data = {"name": "王五", "email": "wangwu@test.com", "age": 200}
        with pytest.raises(ContractValidationError):
            validator.validate("users", data)

    def test_validate_age_below_min(self, contract):
        validator = ContractValidator(contract)
        data = {"name": "赵六", "email": "zhao@test.com", "age": -1}
        with pytest.raises(ContractValidationError):
            validator.validate("users", data)


class TestContractManager:
    """契约管理器测试"""

    def test_register_and_get_contract(self):
        mgr = ContractManager()
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        mgr.register("test_module", contract)
        retrieved = mgr.get_contract("test_module")
        assert retrieved is not None
        assert retrieved.get_module_name() == "test_module"

    def test_get_contract_nonexistent(self):
        mgr = ContractManager()
        assert mgr.get_contract("nonexistent") is None

    def test_get_validator(self):
        mgr = ContractManager()
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        mgr.register("test_module", contract)
        validator = mgr.get_validator("test_module")
        assert validator is not None

    def test_get_validator_nonexistent(self):
        mgr = ContractManager()
        assert mgr.get_validator("nonexistent") is None

    def test_register_duplicate_raises(self):
        mgr = ContractManager()
        contract1 = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        contract2 = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        mgr.register("test_module", contract1)
        with pytest.raises(DataContractError):
            mgr.register("test_module", contract2)

    def test_unregister(self):
        mgr = ContractManager()
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        mgr.register("test_module", contract)
        assert mgr.unregister("test_module") is True
        assert mgr.get_contract("test_module") is None

    def test_register_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(SAMPLE_CONTRACT_YAML)
            fname = f.name
        try:
            mgr = ContractManager()
            mgr.register_from_file("test_module", fname)
            contract = mgr.get_contract("test_module")
            assert contract is not None
            assert contract.get_module_name() == "test_module"
        finally:
            os.unlink(fname)

    def test_validate_through_manager(self):
        mgr = ContractManager()
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        mgr.register("test_module", contract)
        result = mgr.validate("test_module", "users", {"name": "张三", "email": "a@b.com"})
        assert result["name"] == "张三"

    def test_validate_fail_through_manager(self):
        mgr = ContractManager()
        contract = ContractYAML(content=SAMPLE_CONTRACT_YAML)
        mgr.register("test_module", contract)
        with pytest.raises(ContractValidationError):
            mgr.validate("test_module", "users", {"name": "张三"})  # 缺少 email


class TestContractAutoGenerator:
    """契约自动生成器测试"""

    def test_register_model_and_generate(self):
        """使用简单对象模拟 SQLAlchemy 模型"""

        class FakeColumn:
            def __init__(self, name, type_cls, primary_key=False, nullable=True):
                self.name = name
                self.type = type_cls
                self.primary_key = primary_key
                self.nullable = nullable

        class FakeModel:
            __tablename__ = "test_table"
            __table__ = type(
                "obj",
                (object,),
                {
                    "columns": [
                        FakeColumn("id", int, primary_key=True, nullable=False),
                        FakeColumn("name", str, nullable=False),
                        FakeColumn("email", str, nullable=True),
                    ]
                },
            )()

        generator = ContractAutoGenerator()
        generator.register_model(FakeModel, table_name="test_table")
        contract = generator.generate(module_name="test_mod", version="1.0")
        assert contract is not None
        assert isinstance(contract, ContractYAML)
        assert contract.get_module_name() == "test_mod"
        assert "test_table" in contract.get_all_table_names()
