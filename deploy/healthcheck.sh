#!/usr/bin/env bash
# ==============================================================================
# 链客宝 — K8s 健康检查脚本
# ==============================================================================
# 功能:
#   1. curl 本地 8001 端口的 /web 端点（验证应用运行）
#   2. curl 本地 8001 端口的 /health 端点（验证应用健康）
#   3. 连接 PostgreSQL 检查数据库可用性（通过 PG_URL 环境变量）
#   4. 输出 JSON 格式的健康检查结果
# ==============================================================================

set -euo pipefail

# ── 配置（可通过环境变量覆盖）─────────────────────────────────────────────────
BASE_URL="${HEALTH_CHECK_URL:-http://127.0.0.1:8001}"
TIMEOUT="${HEALTH_CHECK_TIMEOUT:-5}"
PG_URL="${PG_URL:-}"

# ── JSON 输出 ─────────────────────────────────────────────────────────────────
# 使用 jq 构建 JSON（如果可用），否则用 shell 拼接
HAS_JQ=false
if command -v jq &>/dev/null; then
    HAS_JQ=true
fi

# ── 辅助函数 ──────────────────────────────────────────────────────────────────
json_escape() {
    # 简单 JSON 字符串转义（替换 " → \", 换行 → \n）
    echo "$1" | sed 's/"/\\"/g' | sed ':a;N;$!ba;s/\n/\\n/g'
}

build_json() {
    local status="$1"
    local http_code="$2"
    local http_body="$3"
    local pg_status="$4"
    local pg_error="$5"
    local timestamp
    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    if $HAS_JQ; then
        jq -n \
            --arg status "$status" \
            --arg timestamp "$timestamp" \
            --argjson http_code "$http_code" \
            --arg http_body "$http_body" \
            --arg pg_status "$pg_status" \
            --arg pg_error "$pg_error" \
            '{
                status: $status,
                timestamp: $timestamp,
                checks: {
                    http: {
                        endpoint: "/web",
                        code: $http_code,
                        body: $http_body
                    },
                    postgresql: {
                        status: $pg_status,
                        error: $pg_error
                    }
                }
            }'
    else
        local http_body_esc
        http_body_esc="$(json_escape "$http_body")"
        local pg_error_esc
        pg_error_esc="$(json_escape "$pg_error")"
        cat <<EOF
{
  "status": "$status",
  "timestamp": "$timestamp",
  "checks": {
    "http": {
      "endpoint": "/web",
      "code": $http_code,
      "body": "$http_body_esc"
    },
    "postgresql": {
      "status": "$pg_status",
      "error": "$pg_error_esc"
    }
  }
}
EOF
    fi
}

# ── Check 1: HTTP /web 端点 ──────────────────────────────────────────────────
check_http() {
    local url="${BASE_URL}/web"
    local code=000
    local body=""

    # 使用 curl 检查，捕获 HTTP 状态码和响应体
    if response=$(curl -s -o /tmp/chainke_health_body.txt \
        -w "%{http_code}" \
        --connect-timeout "$TIMEOUT" \
        --max-time "$TIMEOUT" \
        "$url" 2>/dev/null); then
        code="$response"
        body="$(cat /tmp/chainke_health_body.txt 2>/dev/null || true)"
    else
        code=000
        body="curl failed: connection error or timeout"
    fi

    echo "$code|$body"
}

# ── Check 2: PostgreSQL 连接检查 ─────────────────────────────────────────────
check_postgres() {
    if [ -z "$PG_URL" ]; then
        echo "skipped|PG_URL 环境变量未设置，跳过 PostgreSQL 检查"
        return
    fi

    # 尝试用 Python 连接（优先使用项目中已有的 SQLAlchemy）
    if command -v python3 &>/dev/null; then
        result=$(python3 -c "
import sys
try:
    # 尝试 psycopg2 直接连接
    import psycopg2
    conn = psycopg2.connect('${PG_URL}', connect_timeout=5)
    cur = conn.cursor()
    cur.execute('SELECT 1')
    cur.close()
    conn.close()
    print('ok|')
    sys.exit(0)
except ImportError:
    # 尝试 SQLAlchemy
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine('${PG_URL}', pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        print('ok|')
        sys.exit(0)
    except ImportError:
        print('error|Python 未安装 psycopg2 或 SQLAlchemy')
        sys.exit(1)
except Exception as e:
    print(f'error|{e}')
    sys.exit(1)
" 2>&1) || true
    elif command -v psql &>/dev/null; then
        # 回退到 psql
        if psql "${PG_URL}" -c "SELECT 1" -t -q &>/dev/null; then
            echo "ok|"
        else
            echo "error|psql connection failed"
        fi
    else
        echo "error|找不到 Python3 或 psql 客户端"
    fi
}

# ── 全局状态变量 ──────────────────────────────────────────────────────────────
OVERALL_STATUS="healthy"

# ── 主流程 ────────────────────────────────────────────────────────────────────
main() {
    local http_code=0
    local http_body=""
    local pg_status=""
    local pg_error=""

    # ── HTTP 检查 ────────────────────────────────────────────────────────
    IFS='|' read -r http_code http_body <<< "$(check_http)"
    if [ "$http_code" = "000" ] || [ "$http_code" -ge 500 ]; then
        OVERALL_STATUS="unhealthy"
    fi

    # ── PG 检查 ──────────────────────────────────────────────────────────
    IFS='|' read -r pg_status pg_error <<< "$(check_postgres)"
    if [ "$pg_status" = "error" ]; then
        OVERALL_STATUS="unhealthy"
    fi

    # 如果 PG_URL 未设置，仍标记为健康（PG 非必需时）
    if [ -z "$PG_URL" ]; then
        pg_status="skipped"
        pg_error="PG_URL 未设置"
    fi

    # ── 输出 JSON ────────────────────────────────────────────────────────
    build_json "$OVERALL_STATUS" "$http_code" "$http_body" "$pg_status" "$pg_error"
}

# ── 执行并清理 ────────────────────────────────────────────────────────────────
main
rm -f /tmp/chainke_health_body.txt

# 退出码：所有检查通过则 0，否则 1
if echo "$OVERALL_STATUS" | grep -q "unhealthy"; then
    exit 1
fi
exit 0
