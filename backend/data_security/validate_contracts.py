#!/usr/bin/env python3
"""快速验证脚本：测试数据契约系统的加载与校验"""

import os
import sys

# 添加 backend 目录到 sys.path，使得 data_security 包可被导入
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from data_security.core.data_contract import ContractManager, ContractValidator, validate_yaml_file

contracts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contracts")

print("=" * 70)
print("  数据契约系统 — 验证报告")
print("=" * 70)

# 1. 逐个验证 YAML 文件
files = ["ai_card.yaml", "chainke.yaml", "digital_port.yaml"]
all_ok = True

for fname in files:
    fpath = os.path.join(contracts_dir, fname)
    ok, msgs = validate_yaml_file(fpath)
    status = "✓ 通过" if ok else "✗ 失败"
    print(f"\n  [{status}] {fname}")
    for m in msgs:
        print(f"    {m}")
    if not ok:
        all_ok = False

# 2. 测试批量加载到 ContractManager
print("\n" + "-" * 70)
print("  批量加载测试 (ContractManager.load_directory)")
print("-" * 70)

manager = ContractManager(auto_reload=False)
count = manager.load_directory(contracts_dir)
print(f"  成功加载 {count}/{len(files)} 个契约")
print(f"  注册模块: {manager.list_modules()}")

# 3. 测试校验
print("\n" + "-" * 70)
print("  校验器测试 (ContractValidator)")
print("-" * 70)

# 测试 ai_card 模块
contract = manager.get_contract("ai_card")
if contract:
    validator = ContractValidator(contract, strict_mode=True)
    print("\n  ai_card 模块 — 严格模式")

    # 合法数据
    valid_data = {
        "uuid": "550e8400-e29b-41d4-a716-446655440000",
        "username": "test_user",
        "nickname": "测试用户",
        "status": "active",
    }
    try:
        cleaned = validator.validate("users", valid_data)
        print(f"  ✓ 合法用户数据通过校验: {cleaned['username']}")
    except Exception as e:
        print(f"  ✗ 合法数据被拒: {e}")
        all_ok = False

    # 非法数据（含不在白名单的字段）
    invalid_data = {
        "uuid": "550e8400-e29b-41d4-a716-446655440000",
        "username": "test",
        "password_hash": "should_not_pass",
    }
    try:
        cleaned = validator.validate("users", invalid_data)
        print("  ✗ 非法数据通过了校验!")
        all_ok = False
    except Exception:
        print("  ✓ 非法数据被拦截 (含 password_hash)")

    # 测试 card_profiles
    valid_card = {
        "uuid": "550e8400-e29b-41d4-a716-446655440001",
        "user_id": 1,
        "display_name": "张三",
        "is_public": True,
        "layout_style": "modern",
    }
    try:
        cleaned = validator.validate("card_profiles", valid_card)
        print("  ✓ 合法名片数据通过校验")
    except Exception as e:
        print(f"  ✗ 合法名片被拒: {e}")
        all_ok = False

# 测试 chainke 模块
contract2 = manager.get_contract("chainke")
if contract2:
    validator2 = ContractValidator(contract2, strict_mode=True)
    print("\n  chainke 模块 — 严格模式")

    valid_order = {
        "uuid": "550e8400-e29b-41d4-a716-446655440002",
        "order_id": "ORD-2024-001",
        "status": "pending",
        "items": [{"sku": "ITEM-001", "qty": 2, "price": 99.99}],
        "total": 199.98,
        "is_express": False,
    }
    try:
        cleaned = validator2.validate("orders", valid_order)
        print(f"  ✓ 合法订单数据通过校验: {cleaned['order_id']}")
    except Exception as e:
        print(f"  ✗ 合法订单被拒: {e}")
        all_ok = False

# 测试 digital_port 模块
contract3 = manager.get_contract("digital_port")
if contract3:
    validator3 = ContractValidator(contract3, strict_mode=True)
    print("\n  digital_port 模块 — 严格模式")

    valid_ent = {
        "uuid": "550e8400-e29b-41d4-a716-446655440003",
        "organization_id": 1,
        "enterprise_code": "E20260529001A",
        "enterprise_type": "chinese_enterprise",
        "registration_country": "中国",
        "main_industry": "电子制造",
        "main_contact_name": "李四",
        "main_contact_phone": "+861****8000",
    }
    try:
        cleaned = validator3.validate("dp_enterprises", valid_ent)
        print("  ✓ 合法企业数据通过校验")
    except Exception as e:
        print(f"  ✗ 合法企业被拒: {e}")
        all_ok = False

# 4. 测试宽松模式
print("\n" + "-" * 70)
print("  宽松模式测试")
print("-" * 70)
if contract:
    loose_validator = ContractValidator(contract, strict_mode=False)
    loose_data = {
        "uuid": "550e8400-e29b-41d4-a716-446655440004",
        "username": "loose_user",
        "extra_field": "should_be_allowed_in_loose_mode",
    }
    try:
        cleaned = loose_validator.validate("users", loose_data)
        print("  ✓ 宽松模式: 额外字段被允许 (strict_mode=False)")
    except Exception as e:
        print(f"  ✗ 宽松模式异常: {e}")
        all_ok = False

# 5. 测试热加载检查
print("\n" + "-" * 70)
print("  热加载 & 版本检查")
print("-" * 70)
if contract:
    print(f"  文件路径: {contract.get_path()}")
    print(f"  版本号: {contract.get_version()}")
    print(f"  校验和: {contract.get_checksum()}")
    print(f"  是否有变更: {contract.is_dirty()}")

# 6. 汇总
print("\n" + "=" * 70)
if all_ok:
    print("  所有测试通过 ✓  数据契约系统运行正常")
else:
    print("  存在失败的测试 ✗  请检查以上日志")
print("=" * 70)
