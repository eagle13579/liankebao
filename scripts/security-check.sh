#!/usr/bin/env bash
# =============================================================================
# 链客宝 安全检查脚本
# 用途: 工业化前置检查 — 在 CI / 部署前运行
# =============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
PASS=0
FAIL=0

check() {
    local desc="$1" status="$2"
    if [[ "$status" == "PASS" ]]; then
        echo -e "  ${GREEN}✓${NC} $desc"
        PASS=$((PASS+1))
    else
        echo -e "  ${RED}✗${NC} $desc"
        FAIL=$((FAIL+1))
    fi
}

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     链客宝 工业化安全检查               ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# 1. .env 权限检查
ENV_PERMS=$(stat -c "%a" .env 2>/dev/null || echo "000")
if [[ "$ENV_PERMS" == "600" ]]; then
    check ".env 权限正确 (600)" "PASS"
else
    check ".env 权限应为 600, 当前为 $ENV_PERMS" "FAIL"
fi

# 2. .env 是否在 .gitignore 中
if grep -q "^\.env$" .gitignore 2>/dev/null; then
    check ".env 在 .gitignore 中" "PASS"
else
    check ".env 未在 .gitignore 中" "FAIL"
fi

# 3. 检查硬编码密钥
HARDCODED=$(grep -rn "sk-[A-Za-z0-9]\{20,\}" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.js" backend/app/ src/ 2>/dev/null | grep -v "test_" | grep -v "__pycache__" | wc -l)
if [[ "$HARDCODED" -eq 0 ]]; then
    check "无硬编码 API 密钥" "PASS"
else
    check "发现 $HARDCODED 处可能的硬编码密钥" "FAIL"
fi

# 4. 检查密钥轮换机制
if grep -q "rotate_key\|key_rotation\|轮换" backend/app/security_hardening.py 2>/dev/null; then
    check "密钥轮换机制已实现" "PASS"
else
    check "密钥轮换机制未实现" "FAIL"
fi

# 5. 检查 CSP 头配置
if grep -q "Content-Security-Policy\|CSP" backend/app/security_hardening.py 2>/dev/null; then
    check "CSP 安全头已配置" "PASS"
else
    check "CSP 安全头未配置" "FAIL"
fi

# 6. 检查 SQL 注入防护
if grep -q "detect_raw_sql\|SQL注入" backend/app/security_hardening.py 2>/dev/null; then
    check "SQL 注入防护已实现" "PASS"
else
    check "SQL 注入防护未实现" "FAIL"
fi

# 7. 检查速率限制
if grep -q "rate_limit\|RateLimitMiddleware" backend/app/middleware/rate_limit.py 2>/dev/null; then
    check "速率限制已实现" "PASS"
else
    check "速率限制未实现" "FAIL"
fi

# 8. 检查测试覆盖率配置
if grep -q "\[tool.coverage\]\|coverage" pyproject.toml backend/pyproject.toml 2>/dev/null; then
    check "测试覆盖率配置已存在" "PASS"
else
    check "测试覆盖率配置缺失" "FAIL"
fi

# 9. 检查 OpenAPI docs 是否启用
if grep -q "docs_url=\"/docs\"" backend/app/main.py 2>/dev/null; then
    check "OpenAPI 文档已启用" "PASS"
else
    check "OpenAPI 文档未启用" "FAIL"
fi

# 10. 检查数据库连接字符串是否留空 (生产环境不应有明文密码)
if grep -q "PG_PASSWORD=\"\"\|PG_HOST=\"\"" .env 2>/dev/null; then
    check "生产数据库密码未明文存储 (留空=SQLite模式)" "PASS"
else
    check "检查 .env 中的数据库密码" "WARN"
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  结果: $PASS 通过 / $FAIL 失败"
echo "╚══════════════════════════════════════════╝"
echo ""

exit $FAIL
