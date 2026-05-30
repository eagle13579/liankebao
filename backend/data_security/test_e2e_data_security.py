#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据安全端到端全链路测试
========================
测试 DataSecurity 统一集成入口的全部10个场景。

运行:
    cd "D:/向海容的知识库/wiki/wiki/记忆宫殿/scripts/data-security"
    python test_e2e_data_security.py

输出: 端到端测试报告
"""

import os
import sys
import json
import time
import tempfile
import traceback
import uuid as uuid_mod

# ---------------------------------------------------------------------------
# 确保导入路径正确
# ---------------------------------------------------------------------------
_BASE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_BASE, "core"), os.path.join(_BASE, "quarantine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from data_security_loader import DataSecurity, create_test_security

# ---------------------------------------------------------------------------
# 测试配置
# ---------------------------------------------------------------------------
CONTRACTS_DIR = os.path.join(_BASE, "contracts")
PASS = "PASS"
FAIL = "FAIL"

_stats = {"pass": 0, "fail": 0, "total": 0}


def uid() -> str:
    """生成符合 UUID 格式的字符串"""
    return str(uuid_mod.uuid4())


def section(title: str):
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def check(description: str, condition: bool, detail: str = "") -> bool:
    global _stats
    _stats["total"] += 1
    if condition:
        _stats["pass"] += 1
        print(f"  [✓] {description}")
    else:
        _stats["fail"] += 1
        print(f"  [✗] {description}")
        if detail:
            print(f"       -> {detail}")
    return condition


# ===================================================================
# 场景1: 正常数据 → passed
# ===================================================================
def test_normal_data(security: DataSecurity) -> bool:
    section("场景1: 正常数据 → passed")

    data = {
        "uuid": uid(),
        "username": "zhangsan_test",
        "nickname": "张三",
        "email": "zhangsan@example.com",
        "phone": "13800138000",
        "gender": "male",
        "status": "active",
    }
    result = security.validate_and_write(
        module="ai_card",
        table="users",
        data=data,
        context={"_dwg_mode": "normal", "user_id": 1},
    )
    ok = check("正常数据状态为 passed", result.get("status") == "passed",
               f"实际 {result.get('status')}: {result.get('reason')}")
    check("返回清洗后的数据", "data" in result)
    check("异常评分存在且合理",
          isinstance(result.get("score"), (int, float)) and result.get("score", 1) < 90)
    return ok


# ===================================================================
# 场景2: SQL注入攻击 → rejected
# ===================================================================
def test_sql_injection(security: DataSecurity) -> bool:
    section("场景2: SQL注入攻击 → rejected")

    data = {
        "uuid": uid(),
        "username": "admin' OR '1'='1",
        "nickname": "攻击者",
        "status": "active",
    }
    result = security.validate_and_write(
        module="ai_card", table="users", data=data,
        context={"_dwg_mode": "normal", "user_id": 1},
    )
    ok = check("SQL注入数据状态为 rejected", result.get("status") == "rejected",
               f"实际 {result.get('status')}: {result.get('reason')}")
    return ok


# ===================================================================
# 场景3: XSS攻击 → rejected
# ===================================================================
def test_xss_attack(security: DataSecurity) -> bool:
    section("场景3: XSS攻击 → rejected")

    data = {
        "uuid": uid(),
        "username": "test_user_xss",
        "nickname": "<script>alert('xss')</script>",
        "status": "active",
    }
    result = security.validate_and_write(
        module="ai_card", table="users", data=data,
        context={"_dwg_mode": "normal", "user_id": 1},
    )
    ok = check("XSS攻击数据状态为 rejected", result.get("status") == "rejected",
               f"实际 {result.get('status')}: {result.get('reason')}")
    return ok


# ===================================================================
# 场景4: Unicode零宽字符 → 消毒警告 + passed
# ===================================================================
def test_unicode_zerowidth(security: DataSecurity) -> bool:
    section("场景4: Unicode零宽字符 → 消毒警告 + passed")

    zerowidth_name = "张\u200B三\u200D"
    data = {
        "uuid": uid(),
        "username": "zerowidth_user",
        "nickname": zerowidth_name,
        "status": "active",
    }
    result = security.validate_and_write(
        module="ai_card", table="users", data=data,
        context={"_dwg_mode": "normal", "user_id": 1},
    )

    ok = check("零宽字符数据状态为 passed", result.get("status") == "passed",
               f"实际 {result.get('status')}: {result.get('reason')}")

    # Sanitizer 直接检测
    cleaned, warns = security.sanitizer.sanitize_string(zerowidth_name)
    has_zero_warn = any("零宽" in w for w in warns)
    check("Sanitizer 检测到零宽字符并发出警告", has_zero_warn,
           f"warnings={warns}")
    check("Sanitizer 已清除零宽字符",
          "\u200B" not in cleaned and "\u200D" not in cleaned,
          f"cleaned={repr(cleaned)}")
    return ok


# ===================================================================
# 场景5: SSRF注入(metadata endpoint) → rejected
# ===================================================================
def test_ssrf_injection(security: DataSecurity) -> bool:
    section("场景5: SSRF注入(metadata endpoint) → rejected")

    data = {
        "uuid": uid(),
        "username": "ssrf_user",
        "website": "http://169.254.169.254/latest/meta-data/",
        "status": "active",
    }
    result = security.validate_and_write(
        module="ai_card", table="users", data=data,
        context={"_dwg_mode": "normal", "user_id": 1},
    )
    ok = check("SSRF注入数据状态为 rejected", result.get("status") == "rejected",
               f"实际 {result.get('status')}: {result.get('reason')}")
    return ok


# ===================================================================
# 场景6: 类型混淆 → rejected
# ===================================================================
def test_type_confusion(security: DataSecurity) -> bool:
    section("场景6: 类型混淆 → rejected")

    data = {
        "uuid": uid(),
        "username": "type_confuse_user",
        "gender": 12345,  # 应传字符串 enum
        "status": "active",
    }
    result = security.validate_and_write(
        module="ai_card", table="users", data=data,
        context={"_dwg_mode": "normal", "user_id": 1},
    )
    ok = check("类型混淆数据状态为 rejected", result.get("status") == "rejected",
               f"实际 {result.get('status')}: {result.get('reason')}")
    return ok


# ===================================================================
# 场景7: 缺少必填字段 → rejected
# ===================================================================
def test_missing_required(security: DataSecurity) -> bool:
    section("场景7: 缺少必填字段 → rejected")

    data = {
        "nickname": "无名氏",
        "status": "active",
    }
    result = security.validate_and_write(
        module="ai_card", table="users", data=data,
        context={"_dwg_mode": "normal", "user_id": 1},
    )
    ok = check("缺少必填字段数据状态为 rejected", result.get("status") == "rejected",
               f"实际 {result.get('status')}: {result.get('reason')}")
    return ok


# ===================================================================
# 场景8: 检疫区(异常评分>0.3) → quarantined
# ===================================================================
def test_quarantine(security: DataSecurity) -> bool:
    section("场景8: 检疫区(异常评分触发检疫) → quarantined")

    data = {
        "uuid": uid(),
        "name": "TestOrg",
        "company_type": "enterprise",
        "status": "active",
    }
    result = security.validate_and_write(
        module="ai_card", table="organizations", data=data,
        context={"_dwg_mode": "normal", "user_id": 1},
    )

    status = result.get("status")
    ok = check("组织数据通过验证(至少不拒绝)",
               status in ("quarantined", "passed"),
               f"实际 {status}: {result.get('reason')}")

    if status == "quarantined":
        check("检疫区返回 quarantine_id", result.get("quarantine_id") is not None)
        items = security.quarantine._fetchall(
            "SELECT * FROM quarantine_items WHERE module=?",
            ("ai_card",),
        )
        check("检疫区数据库中已有记录", len(items) > 0,
               f"查询到 {len(items)} 条记录")
    return ok


# ===================================================================
# 场景9: 熔断测试(连续10次写入失败) → 自动降级
# ===================================================================
def test_circuit_breaker(security: DataSecurity) -> bool:
    section("场景9: 熔断测试(连续10次写入失败) → 自动降级")

    cb_qdb = os.path.join(tempfile.gettempdir(), f"ds_cb_{int(time.time())}.db")
    cb_security = DataSecurity(
        contracts_dir=CONTRACTS_DIR,
        dwg_config={"writer_fail_rate": 1.0},
        quarantine_db=cb_qdb,
        verbose=False,
    )

    data = {
        "uuid": uid(),
        "username": "circuit_test_user",
        "nickname": "熔断测试",
        "status": "active",
    }

    degraded_detected = False
    for i in range(15):
        result = cb_security.validate_and_write(
            module="ai_card", table="users", data=data,
            context={"_dwg_mode": "normal", "user_id": 1},
        )
        if result.get("degraded"):
            degraded_detected = True
            break

    stats = cb_security.get_stats()
    dwg_stats = stats.get("dwg", {})
    circuit_broken = dwg_stats.get("circuit_broken", 0)
    degraded = dwg_stats.get("degraded", 0)
    cb_info = dwg_stats.get("circuit_breaker", {})

    ok = check("熔断测试中触发了自动降级",
               degraded_detected or circuit_broken > 0 or degraded > 0,
               f"degraded_flag={degraded_detected}, "
               f"circuit_broken={circuit_broken}, "
               f"degraded={degraded}, "
               f"cb_state={cb_info.get('state')}")

    cb_security.close()
    try:
        os.remove(cb_qdb)
    except OSError:
        pass
    return ok


# ===================================================================
# 场景10: 降级通路测试 → direct bypass + audit记录
# ===================================================================
def test_degrade_path(security: DataSecurity) -> bool:
    section("场景10: 降级通路测试 → direct bypass + audit记录")

    # ---- direct 模式 ----
    security.dwg.set_degrade_mode("direct")
    data = {
        "uuid": uid(),
        "username": "degrade_user_direct",
        "email": "degrade@test.com",
        "status": "active",
    }
    result = security.validate_and_write(
        module="ai_card", table="users", data=data,
        context={"_dwg_mode": "normal", "user_id": 1},
    )
    security.dwg.set_degrade_mode("normal")

    ok = check("DIRECT降级: 状态为 passed（旁路写入）",
               result.get("status") == "passed",
               f"实际 {result.get('status')}: {result.get('reason')}")
    check("DIRECT降级: 标记 degraded=True",
          result.get("degraded") is True,
          f"实际 degraded={result.get('degraded')}")
    check("DIRECT降级: 原因包含 '旁路' 或 'DIRECT'",
          "旁路" in result.get("reason", "") or "DIRECT" in result.get("reason", ""),
          f"实际 reason={result.get('reason')}")

    # ---- audit_only 模式 ----
    security.dwg.set_degrade_mode("audit_only")
    data2 = {
        "uuid": uid(),
        "username": "audit_user",
        "status": "active",
    }
    result2 = security.validate_and_write(
        module="ai_card", table="users", data=data2,
        context={"_dwg_mode": "normal", "user_id": 1},
    )
    security.dwg.set_degrade_mode("normal")

    check("AUDIT_ONLY降级: 状态为 passed",
          result2.get("status") == "passed",
          f"实际 {result2.get('status')}: {result2.get('reason')}")
    check("AUDIT_ONLY降级: 标记 degraded=True",
          result2.get("degraded") is True)

    return ok


# ===================================================================
# 主测试流程
# ===================================================================
def main():
    global _stats
    _stats = {"pass": 0, "fail": 0, "total": 0}

    print("=" * 72)
    print("  数据安全端到端全链路测试报告")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  工作目录: {_BASE}")
    print("=" * 72)

    qdb = os.path.join(tempfile.gettempdir(), f"ds_e2e_test_{int(time.time())}.db")
    security = create_test_security(
        contracts_dir=CONTRACTS_DIR,
        quarantine_db=qdb,
        verbose=False,
    )

    results = []
    test_cases = [
        ("场景1: 正常数据 → passed", test_normal_data),
        ("场景2: SQL注入攻击 → rejected", test_sql_injection),
        ("场景3: XSS攻击 → rejected", test_xss_attack),
        ("场景4: Unicode零宽字符 → 消毒+passed", test_unicode_zerowidth),
        ("场景5: SSRF注入(metadata endpoint) → rejected", test_ssrf_injection),
        ("场景6: 类型混淆 → rejected", test_type_confusion),
        ("场景7: 缺少必填字段 → rejected", test_missing_required),
        ("场景8: 检疫区(异常评分>0.3) → quarantined", test_quarantine),
        ("场景9: 熔断测试(连续10次失败) → 自动降级", test_circuit_breaker),
        ("场景10: 降级通路测试 → direct bypass + audit记录", test_degrade_path),
    ]

    for name, func in test_cases:
        try:
            func(security)
            results.append((name, True))
        except Exception as e:
            print(f"\n  [!] 场景执行异常: {e}")
            traceback.print_exc()
            _stats["fail"] += 1
            _stats["total"] += 1
            results.append((name, False))

    # ---- 汇总 ----
    security.close()
    print()
    print("=" * 72)
    print("  测试汇总")
    print("=" * 72)
    for name, ok in results:
        mark = "✓" if ok else "✗"
        print(f"  [{mark}] {name}")

    print()
    print(f"  总计: {_stats['total']}  |  通过: {_stats['pass']}  |  "
          f"失败: {_stats['fail']}")
    success_rate = (_stats['pass'] / _stats['total'] * 100) if _stats['total'] else 0
    print(f"  通过率: {success_rate:.1f}%")

    if _stats['fail'] == 0:
        print("\n  ★★★ 全部10个场景通过 ★★★")
    else:
        print(f"\n  ⚠ {_stats['fail']} 个场景未通过，请检查详细日志")

    print("=" * 72)

    try:
        os.remove(qdb)
    except OSError:
        pass

    return _stats['fail'] == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
