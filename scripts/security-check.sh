#!/usr/bin/env bash
# =============================================================================
# 链客宝 安全自动化检查脚本
# =============================================================================
# 执行 10 项安全检查，检测常见安全隐患。
# 用法:
#   chmod +x scripts/security-check.sh
#   ./scripts/security-check.sh
#   ./scripts/security-check.sh --verbose    # 显示详细输出
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VERBOSE=false
EXIT_CODE=0
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

# ── 颜色 ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ── 参数解析 ─────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--verbose" ]] || [[ "${1:-}" == "-v" ]]; then
    VERBOSE=true
fi

# ── 辅助函数 ──────────────────────────────────────────────────────────────────

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
pass()  { echo -e "${GREEN}[PASS]${NC}  $*"; ((PASS_COUNT++)); }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; ((FAIL_COUNT++)); EXIT_CODE=1; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; ((SKIP_COUNT++)); }

header() {
    echo ""
    echo "================================================================"
    echo -e "  ${CYAN}$1${NC}"
    echo "================================================================"
}

check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        warn "命令 '$1' 未安装，跳过检查 #$2"
        return 1
    fi
    return 0
}

# =============================================================================
# 开始检查
# =============================================================================

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       链客宝 安全自动化检查                                 ║${NC}"
echo -e "${CYAN}║       项目路径: ${PROJECT_DIR}               ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
info "检查开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
info "检查项目根目录: $PROJECT_DIR"
echo ""

# ── 检查 #1: .env 文件权限 ───────────────────────────────────────────────────
header "检查 #1: .env 文件权限（应为 600）"

if [[ -f "$PROJECT_DIR/.env" ]]; then
    PERMS=$(stat -c "%a" "$PROJECT_DIR/.env" 2>/dev/null || stat -f "%OLp" "$PROJECT_DIR/.env" 2>/dev/null)
    if [[ "$PERMS" == "600" ]]; then
        pass ".env 权限正确: $PERMS"
    else
        fail ".env 权限不安全: $PERMS（应为 600）"
        info "  修复: chmod 600 $PROJECT_DIR/.env"
    fi
else
    warn ".env 文件不存在，跳过"
fi

# ── 检查 #2: .gitignore 是否存在且包含关键条目 ───────────────────────────────
header "检查 #2: .gitignore 关键条目"

if [[ ! -f "$PROJECT_DIR/.gitignore" ]]; then
    fail ".gitignore 文件不存在！"
else
    MISSING=()
    for ENTRY in ".env" "*.db" "*.jsonl" "__pycache__/" "data/"; do
        if ! grep -qF "$ENTRY" "$PROJECT_DIR/.gitignore" 2>/dev/null; then
            MISSING+=("$ENTRY")
        fi
    done
    if [[ ${#MISSING[@]} -eq 0 ]]; then
        pass ".gitignore 包含所有关键安全条目"
    else
        fail ".gitignore 缺少条目: ${MISSING[*]}"
    fi
fi

# ── 检查 #3: 密钥硬编码检测 ───────────────────────────────────────────────────
header "检查 #3: 源代码中密钥硬编码"

if check_cmd "grep" "3"; then
    SUSPICIOUS=0
    # 排除 .env、.gitignore、检查脚本自身、node_modules
    while IFS= read -r -d '' FILE; do
        if grep -HnE '(secret|SECRET|password|PASSWORD|token|TOKEN|api.?key|API.?KEY|private.?key|PRIVATE.?KEY)' "$FILE" 2>/dev/null \
            | grep -ivE '(\.env|\.gitignore|security-check\.sh|node_modules|\.pytest_cache|test_|mock|placeholder|example|TODO|FIXME)' \
            | grep -vE '("[^"]{50,}"|'"'"'[^'"'"']{50,}'"'"')' \
            | grep -qvE 'os\.getenv|os\.environ|environ\.get|config\(|settings\.'; then
            ((SUSPICIOUS++)) || true
        fi
    done < <(find "$PROJECT_DIR" -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.yaml" -o -name "*.yml" -o -name "*.json" -o -name "*.toml" \) \
        ! -path "*/node_modules/*" \
        ! -path "*/__pycache__/*" \
        ! -path "*/.pytest_cache/*" \
        ! -path "*/dist/*" \
        ! -path "*/.git/*" \
        -print0 2>/dev/null || true)

    if [[ "$SUSPICIOUS" -eq 0 ]]; then
        pass "未发现明显的密钥硬编码"
    else
        warn "发现 $SUSPICIOUS 个可能包含密钥的文件（需人工复核）"
    fi
fi

# ── 检查 #4: 依赖漏洞（pip-audit / safety） ───────────────────────────────────
header "检查 #4: Python 依赖漏洞扫描"

if check_cmd "pip-audit" "4"; then
    if pip-audit --requirement "$PROJECT_DIR/backend/requirements.txt" 2>&1; then
        pass "pip-audit: 未发现已知漏洞"
    else
        fail "pip-audit: 发现已知漏洞！请执行 pip-audit --fix 修复"
    fi
elif check_cmd "safety" "4"; then
    if safety check --full-report -r "$PROJECT_DIR/backend/requirements.txt" 2>&1; then
        pass "safety: 未发现已知漏洞"
    else
        fail "safety: 发现已知漏洞！"
    fi
else
    warn "pip-audit 和 safety 均未安装，跳过依赖漏洞检查"
    info "  安装: pip install pip-audit 或 pip install safety"
fi

# ── 检查 #5: CORS 配置审查 ────────────────────────────────────────────────────
header "检查 #5: CORS 配置安全性"

CORS_FILES=$(find "$PROJECT_DIR/backend" -name "*.py" -exec grep -l "CORSMiddleware" {} \; 2>/dev/null || true)
if [[ -n "$CORS_FILES" ]]; then
    WILDCARD_CORS=false
    for CF in $CORS_FILES; do
        if grep -q 'allow_origins=\["\*"\]' "$CF" 2>/dev/null; then
            WILDCARD_CORS=true
            fail "CORS 配置使用了通配符 '*'（文件: $CF）"
        fi
    done
    if ! $WILDCARD_CORS; then
        pass "CORS 配置未使用通配符 '*'"
        if $VERBOSE; then
            info "  相关文件: $CORS_FILES"
        fi
    fi
else
    warn "未发现 CORS 配置（可能不需要）"
fi

# ── 检查 #6: 数据库文件泄露 ───────────────────────────────────────────────────
header "检查 #6: 数据库文件泄露"

DB_FILES=$(find "$PROJECT_DIR" -maxdepth 3 -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" 2>/dev/null || true)
if [[ -n "$DB_FILES" ]]; then
    fail "发现数据库文件未被 .gitignore 忽略:"
    while IFS= read -r DB; do
        DB_REL="${DB#$PROJECT_DIR/}"
        # 检查是否被 git 跟踪
        if git -C "$PROJECT_DIR" ls-files --error-unmatch "$DB" &>/dev/null 2>&1; then
            echo "    [已跟踪] $DB_REL"
        else
            echo "    [未跟踪] $DB_REL"
        fi
    done <<< "$DB_FILES"
else
    pass "未发现数据库文件泄露"
fi

# ── 检查 #7: 日志文件中是否包含敏感信息 ───────────────────────────────────────
header "检查 #7: 日志文件敏感信息"

LOG_FILES=$(find "$PROJECT_DIR" -maxdepth 2 -name "*.log" 2>/dev/null || true)
if [[ -n "$LOG_FILES" ]]; then
    warn "发现日志文件，请确认不包含敏感信息:"
    while IFS= read -r LF; do
        echo "    ${LF#$PROJECT_DIR/}"
    done <<< "$LOG_FILES"
else
    pass "未发现日志文件"
fi

# ── 检查 #8: Python 依赖固定版本 ─────────────────────────────────────────────
header "检查 #8: 依赖版本固定"

if [[ -f "$PROJECT_DIR/backend/requirements.txt" ]]; then
    UNPINNED=$(grep -cE '^[a-zA-Z][a-zA-Z0-9_.-]+[[:space:]]*$' "$PROJECT_DIR/backend/requirements.txt" 2>/dev/null || true)
    if [[ "$UNPINNED" -gt 0 ]]; then
        warn "requirements.txt 中有 $UNPINNED 个依赖未固定版本号"
    else
        pass "所有依赖均已固定版本号"
    fi
else
    warn "backend/requirements.txt 不存在，跳过"
fi

# ── 检查 #9: Git 已提交文件中的敏感信息 ──────────────────────────────────────
header "检查 #9: Git 历史中的敏感文件"

if git -C "$PROJECT_DIR" rev-parse --git-dir &>/dev/null; then
    SENSITIVE_IN_HISTORY=$(git -C "$PROJECT_DIR" log --diff-filter=A --diff-filter=A --name-only --pretty=format: \
        -- "*.env" ".env.*" "*.pem" "*.key" "secrets/*" 2>/dev/null | head -20 || true)
    if [[ -n "$SENSITIVE_IN_HISTORY" ]]; then
        fail "Git 历史中包含敏感文件:"
        echo "$SENSITIVE_IN_HISTORY" | while IFS= read -r SF; do
            echo "    $SF"
        done
        info "  修复: git filter-branch 或 BFG 清理历史"
    else
        pass "Git 历史中未发现敏感文件"
    fi
else
    warn "不是 Git 仓库，跳过"
fi

# ── 检查 #10: Bandit 安全检查（如果安装） ─────────────────────────────────────
header "检查 #10: Bandit 代码安全扫描"

if check_cmd "bandit" "10"; then
    BANDIT_OUTPUT=$(bandit -r "$PROJECT_DIR/backend" \
        --configfile "$PROJECT_DIR/backend/pyproject.toml" \
        -f custom \
        --msg-template "{abspath}:{lineno}: {test_id} {severity} {msg}" \
        2>&1 || true)
    HIGH_COUNT=$(echo "$BANDIT_OUTPUT" | grep -c "HIGH" 2>/dev/null || true)
    MED_COUNT=$(echo "$BANDIT_OUTPUT" | grep -c "MEDIUM" 2>/dev/null || true)
    if [[ "$HIGH_COUNT" -gt 0 ]]; then
        fail "Bandit 发现 $HIGH_COUNT 个高风险问题"
        if $VERBOSE; then
            echo "$BANDIT_OUTPUT" | head -30
        fi
    elif [[ "$MED_COUNT" -gt 0 ]]; then
        warn "Bandit 发现 $MED_COUNT 个中风险问题"
    else
        pass "Bandit 未发现安全问题"
    fi
else
    warn "bandit 未安装，跳过"
    info "  安装: pip install bandit"
fi

# =============================================================================
# 汇总
# =============================================================================
echo ""
echo "================================================================"
echo -e "  ${CYAN}安全检查汇总${NC}"
echo "================================================================"
echo -e "  ${GREEN}通过:${NC} $PASS_COUNT"
echo -e "  ${RED}失败:${NC} $FAIL_COUNT"
echo -e "  ${YELLOW}跳过:${NC} $SKIP_COUNT"
echo -e "  总计: $((PASS_COUNT + FAIL_COUNT + SKIP_COUNT))"
echo ""
echo "  检查完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

if [[ "$EXIT_CODE" -eq 0 ]]; then
    echo -e "${GREEN}✓ 全部检查通过，安全状态良好${NC}"
else
    echo -e "${RED}✗ 有 $FAIL_COUNT 项检查未通过，请修复后重新运行${NC}"
fi

exit "$EXIT_CODE"
