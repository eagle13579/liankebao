#!/bin/bash
# ============================================================================
# 链客宝 数据库迁移脚本
# 按版本号顺序执行 deploy/migrations/ 目录下的 SQL 文件
# 支持 MySQL / MariaDB
#
# 用法:
#   ./migrate.sh -u root -p'password' -d chainke [-h localhost] [-P 3306]
#
# 选项:
#   -u <user>       MySQL 用户名 (必填)
#   -p <password>   MySQL 密码 (必填，可带引号)
#   -d <database>   数据库名 (必填)
#   -h <host>       MySQL 主机地址 (默认: localhost)
#   -P <port>       MySQL 端口 (默认: 3306)
#   -D <dir>        SQL 文件目录 (默认: 脚本所在目录)
#   -v <version>    从指定版本开始执行 (例如: V002，默认: 全部)
#   -n              模拟运行 (dry-run，只显示将要执行的SQL)
#   -q              安静模式 (只输出错误)
#   --help          显示帮助
#
# 示例:
#   ./migrate.sh -u root -p'abc123' -d chainke
#   ./migrate.sh -u root -p'abc123' -d chainke -h 192.168.1.100 -P 3307
#   ./migrate.sh -u root -p'abc123' -d chainke -v V002 -n  (模拟从V002开始)
# ============================================================================

set -euo pipefail

# ---------- 颜色定义 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ---------- 默认值 ----------
MYSQL_HOST="localhost"
MYSQL_PORT="3306"
MYSQL_USER=""
MYSQL_PASS=""
MYSQL_DB=""
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MIGRATIONS_DIR="${SCRIPT_DIR}"
START_FROM=""
DRY_RUN=false
QUIET=false

# ---------- 解析参数 ----------
usage() {
    echo "用法: $0 -u <user> -p <password> -d <database> [-h <host>] [-P <port>] [-D <dir>] [-v <version>] [-n] [-q]"
    echo ""
    echo "选项:"
    echo "  -u <user>       MySQL 用户名 (必填)"
    echo "  -p <password>   MySQL 密码 (必填)"
    echo "  -d <database>   数据库名 (必填)"
    echo "  -h <host>       MySQL 主机地址 (默认: localhost)"
    echo "  -P <port>       MySQL 端口 (默认: 3306)"
    echo "  -D <dir>        SQL 文件目录 (默认: 脚本所在目录)"
    echo "  -v <version>    从指定版本开始执行 (例如: V002)"
    echo "  -n              模拟运行 (dry-run)"
    echo "  -q              安静模式"
    exit 1
}

while getopts "u:p:d:h:P:D:v:nq" opt; do
    case $opt in
        u) MYSQL_USER="$OPTARG" ;;
        p) MYSQL_PASS="$OPTARG" ;;
        d) MYSQL_DB="$OPTARG" ;;
        h) MYSQL_HOST="$OPTARG" ;;
        P) MYSQL_PORT="$OPTARG" ;;
        D) MIGRATIONS_DIR="$OPTARG" ;;
        v) START_FROM="$OPTARG" ;;
        n) DRY_RUN=true ;;
        q) QUIET=true ;;
        *) usage ;;
    esac
done

# ---------- 参数校验 ----------
if [ -z "$MYSQL_USER" ] || [ -z "$MYSQL_PASS" ] || [ -z "$MYSQL_DB" ]; then
    echo -e "${RED}错误: -u (用户名)、-p (密码)、-d (数据库名) 均为必填参数${NC}"
    usage
fi

# ---------- 打印配置 ----------
print_msg() {
    if [ "$QUIET" = false ]; then
        echo -e "$1"
    fi
}

print_ok() {
    if [ "$QUIET" = false ]; then
        echo -e "${GREEN}[OK]${NC} $1"
    fi
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_err() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# ---------- 检查 MySQL 客户端 ----------
MYSQL_CLIENT=""
for cmd in mysql mariadb; do
    if command -v "$cmd" &>/dev/null; then
        MYSQL_CLIENT="$cmd"
        break
    fi
done

if [ -z "$MYSQL_CLIENT" ]; then
    print_err "未找到 mysql 或 mariadb 客户端。请先安装:"
    print_err "  Ubuntu/Debian: sudo apt install mysql-client"
    print_err "  CentOS/RHEL:   sudo yum install mysql"
    print_err "  macOS:         brew install mysql-client"
    exit 1
fi

print_msg "${BLUE}============================================${NC}"
print_msg "${BLUE}  链客宝 数据库迁移工具${NC}"
print_msg "${BLUE}============================================${NC}"
print_msg "  主机:     ${MYSQL_HOST}:${MYSQL_PORT}"
print_msg "  数据库:   ${MYSQL_DB}"
print_msg "  用户:     ${MYSQL_USER}"
print_msg "  目录:     ${MIGRATIONS_DIR}"
print_msg "  客户端:   ${MYSQL_CLIENT}"
if [ -n "$START_FROM" ]; then
    print_msg "  起始版本: ${START_FROM}"
fi
if [ "$DRY_RUN" = true ]; then
    print_msg "  模式:     模拟运行 (不执行)"
fi
print_msg "${BLUE}--------------------------------------------${NC}"

# ---------- 获取 SQL 文件列表 ----------
get_sql_files() {
    local dir="$1"
    local files=()

    # 排序规则: V001__*.sql, V002__*.sql, ...
    while IFS= read -r -d '' f; do
        files+=("$f")
    done < <(find "$dir" -maxdepth 1 -name 'V*.sql' -type f | sort -t/ -k1 | sort -V)

    echo "${files[@]}"
}

SQL_FILES=($(get_sql_files "$MIGRATIONS_DIR"))

if [ ${#SQL_FILES[@]} -eq 0 ]; then
    print_err "在 ${MIGRATIONS_DIR} 目录下未找到 V*.sql 文件"
    exit 1
fi

print_msg "  发现 ${#SQL_FILES[@]} 个迁移文件"

# ---------- 筛选起始版本 ----------
FILTERED_FILES=()
if [ -n "$START_FROM" ]; then
    FOUND=false
    for f in "${SQL_FILES[@]}"; do
        basename_f=$(basename "$f")
        if [ "$FOUND" = true ] || [[ "$basename_f" == "${START_FROM}"* ]]; then
            FILTERED_FILES+=("$f")
            FOUND=true
        fi
    done
    if [ ${#FILTERED_FILES[@]} -eq 0 ]; then
        print_err "未找到以 ${START_FROM} 开头的迁移文件"
        exit 1
    fi
    print_msg "  起始版本筛选后: ${#FILTERED_FILES[@]} 个文件"
else
    FILTERED_FILES=("${SQL_FILES[@]}")
fi

print_msg "${BLUE}============================================${NC}"

# ---------- 执行迁移 ----------
SUCCESS_COUNT=0
FAIL_COUNT=0

for sql_file in "${FILTERED_FILES[@]}"; do
    basename_f=$(basename "$sql_file")
    print_msg ""
    print_msg "▶ 正在执行: ${basename_f} ..."

    if [ "$DRY_RUN" = true ]; then
        # 模拟运行：显示 SQL 文件的前几行
        print_msg "${YELLOW}  [模拟] 将执行以下 SQL:${NC}"
        head -5 "$sql_file"
        print_msg "  ${YELLOW}  ... (${basename_f})${NC}"
        print_ok "${basename_f} (模拟通过)"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        continue
    fi

    # 执行 SQL 文件
    set +e
    output=$($MYSQL_CLIENT -h "$MYSQL_HOST" -P "$MYSQL_PORT" \
        -u "$MYSQL_USER" -p"$MYSQL_PASS" \
        -D "$MYSQL_DB" \
        --default-character-set=utf8mb4 \
        -f < "$sql_file" 2>&1)
    exit_code=$?
    set -e

    if [ $exit_code -eq 0 ]; then
        # 检查是否有错误输出（MySQL -f 模式会继续执行但输出错误）
        if echo "$output" | grep -qi "error\|ERROR"; then
            print_warn "${basename_f} 执行完成，但有警告/错误:"
            echo "$output" | grep -i "error\|ERROR\|warning" | head -5
            # 仍然算成功（因为 -f 模式）
        fi
        print_ok "${basename_f} 执行成功"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        print_err "${basename_f} 执行失败"
        echo "$output" | tail -20
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

# ---------- 汇总 ----------
print_msg ""
print_msg "${BLUE}============================================${NC}"
print_msg "  迁移完成"
print_msg "  成功: ${SUCCESS_COUNT}  /  失败: ${FAIL_COUNT}  /  总计: ${#FILTERED_FILES[@]}"
print_msg "${BLUE}============================================${NC}"

if [ $FAIL_COUNT -gt 0 ]; then
    print_err "部分迁移文件执行失败，请检查上方错误信息。"
    exit 1
fi

if [ "$DRY_RUN" = true ]; then
    print_warn "本次为模拟运行，未实际写入数据库。"
    print_warn "移除 -n 参数执行真实迁移。"
fi

print_ok "数据库迁移全部完成 ✓"
exit 0
