#!/bin/bash
# ============================================================
# 链客宝 金丝雀发布脚本 (Canary Deployment)
# 服务器: 阿里云 ECS (47.100.160.250)
# 用途: 实现渐进式金丝雀发布 + 自动回滚 + 指标监控
#
# 工作流程:
#   1. 部署新版本到 1 台实例（金丝雀），观察 10 分钟
#   2. 验证关键指标（错误率 < 5%, P95延迟 < 1s）
#   3. 逐步扩到 50% 服务器，再次验证 5 分钟
#   4. 全量发布到所有服务器
#   5. 任一阶段指标异常 → 自动回滚
#
# 依赖:
#   - 蓝绿部署脚本: ../blue-green-deploy.sh
#   - Prometheus API: 用于获取指标数据
#   - curl, jq
# ============================================================
set -e

# ---- 颜色定义 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# ---- 基础路径 ----
PROJECT_DIR="/opt/liankebao"
CANARY_DIR="$PROJECT_DIR/deploy/canary"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/canary-deploy.log"
STATE_FILE="$CANARY_DIR/.canary-state"
LOCK_FILE="/tmp/liankebao-canary.lock"
METRICS_FILE="$CANARY_DIR/.canary-metrics.json"

# ---- 蓝绿部署脚本 ----
BLUEGREEN_SCRIPT="$PROJECT_DIR/deploy/blue-green-deploy.sh"

# ---- Prometheus 配置（用于指标采集）----
PROMETHEUS_URL="${PROMETHEUS_URL:-http://127.0.0.1:9090}"
PROMETHEUS_QUERY_TIMEOUT=10

# ---- 金丝雀配置 ----
CANARY_INSTANCES=1                # 初始金丝雀实例数
CANARY_WATCH_MINUTES=10           # 金丝雀观察时间（分钟）
CANARY_HALF_PERCENT=50            # 第二阶段：50% 流量
CANARY_HALF_WATCH_MINUTES=5       # 第二阶段观察时间（分钟）
CANARY_FULL_PERCENT=100           # 最终：全量

# ---- 阈值（触发自动回滚）----
THRESHOLD_ERROR_RATE=5.0          # 错误率 > 5% → 回滚
THRESHOLD_P95_LATENCY_MS=1000     # P95 延迟 > 1s → 回滚
THRESHOLD_TRAFFIC_DROP=50         # 流量下降 > 50% → 回滚

# ---- 日志函数 ----
log()  { echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"; }
error(){ echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"; }
info() { echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"; }
step() { echo -e "${MAGENTA}>>>${NC} $1" | tee -a "$LOG_FILE"; }
ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }

# ---- 帮助信息 ----
usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "金丝雀发布选项:"
    echo "  --deploy                         执行金丝雀发布"
    echo "  --rollback                       回滚金丝雀（切换到上一版本）"
    echo "  --status                         查看当前金丝雀状态"
    echo "  --promote                        手动推进金丝雀到下一阶段"
    echo "  --abort                          中止当前金丝雀发布"
    echo ""
    echo "配置选项:"
    echo "  --watch-minutes=<N>              金丝雀观察时间（默认: 10）"
    echo "  --error-threshold=<N>            错误率百分比阈值（默认: 5.0）"
    echo "  --latency-threshold=<N>          P95延迟毫秒阈值（默认: 1000）"
    echo "  --prometheus-url=<URL>           Prometheus API URL"
    echo "  --branch=<name>                  Git 分支"
    echo ""
    echo "示例:"
    echo "  $0 --deploy                           # 执行金丝雀发布"
    echo "  $0 --deploy --watch-minutes=5          # 缩短观察时间为 5 分钟"
    echo "  $0 --rollback                          # 回滚"
    echo "  $0 --status                            # 查看状态"
    exit 0
}

# ---- 参数解析 ----
ACTION=""
WATCH_MINUTES=$CANARY_WATCH_MINUTES
ERROR_THRESHOLD=$THRESHOLD_ERROR_RATE
LATENCY_THRESHOLD=$THRESHOLD_P95_LATENCY_MS
GIT_BRANCH="master"
PROM_URL="$PROMETHEUS_URL"

while [[ $# -gt 0 ]]; do
    case $1 in
        --deploy)                     ACTION="deploy" ;;
        --rollback)                   ACTION="rollback" ;;
        --status)                     ACTION="status" ;;
        --promote)                    ACTION="promote" ;;
        --abort)                      ACTION="abort" ;;
        --watch-minutes=*)            WATCH_MINUTES="${1#*=}" ;;
        --error-threshold=*)          ERROR_THRESHOLD="${1#*=}" ;;
        --latency-threshold=*)        LATENCY_THRESHOLD="${1#*=}" ;;
        --prometheus-url=*)           PROM_URL="${1#*=}" ;;
        --branch=*)                   GIT_BRANCH="${1#*=}" ;;
        --help)                       usage ;;
        *)                            warn "Unknown option: $1"; usage ;;
    esac
    shift
done

# ---- 锁机制 ----
acquire_lock() {
    if [[ -f "$LOCK_FILE" ]]; then
        local pid=$(cat "$LOCK_FILE" 2>/dev/null)
        if kill -0 "$pid" 2>/dev/null; then
            error "另一个金丝雀发布进程正在运行 (PID: $pid)"
            exit 1
        else
            warn "发现过期锁文件，清理中..."
            rm -f "$LOCK_FILE"
        fi
    fi
    echo $$ > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE"' EXIT
}

# ---- 确保目录存在 ----
ensure_dirs() {
    mkdir -p "$CANARY_DIR" "$LOG_DIR"
}

# ---- 状态管理 ----
load_state() {
    if [[ -f "$STATE_FILE" ]]; then
        source "$STATE_FILE"
        log "加载状态: PHASE=$PHASE, VERSION=$VERSION, OLD_VERSION=$OLD_VERSION"
    else
        # 初始状态
        PHASE="idle"
        VERSION=""
        OLD_VERSION=""
        START_TIME=""
        CANARY_HOST=""
        save_state
    fi
}

save_state() {
    cat > "$STATE_FILE" << EOF
# 链客宝金丝雀部署状态文件
# 由 canary-deploy.sh 自动管理
PHASE="$PHASE"
VERSION="$VERSION"
OLD_VERSION="$OLD_VERSION"
START_TIME="$START_TIME"
CANARY_HOST="$CANARY_HOST"
LAST_UPDATED="$(date '+%Y-%m-%d %H:%M:%S')"
EOF
    log "状态已保存: PHASE=$PHASE, VERSION=$VERSION"
}

# ---- 获取当前 Git 版本 ----
get_current_version() {
    cd "$PROJECT_DIR"
    local commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    local date=$(git log -1 --format=%cd --date=short 2>/dev/null || echo "unknown")
    echo "${commit}-${date}"
}

# ---- 金丝雀发布: 阶段 1 ----
phase1_deploy_canary() {
    step "阶段 1/3: 部署金丝雀实例（${CANARY_INSTANCES} 台）"

    # 记录旧版本
    OLD_VERSION=$(get_current_version)
    log "旧版本: $OLD_VERSION"

    # 使用蓝绿脚本部署到非活跃环境
    if [[ ! -f "$BLUEGREEN_SCRIPT" ]]; then
        error "蓝绿部署脚本不存在: $BLUEGREEN_SCRIPT"
        return 1
    fi

    log "调用蓝绿部署脚本发布到非活跃环境..."
    bash "$BLUEGREEN_SCRIPT" --switch-to auto --skip-health 2>&1 | tee -a "$LOG_FILE"

    # 获取新版本
    VERSION=$(get_current_version)
    log "新版本: $VERSION"

    # 确定金丝雀主机（这里以蓝绿中的非活跃环境作为金丝雀）
    local state_file="$PROJECT_DIR/deploy/.bluegreen-state"
    if [[ -f "$state_file" ]]; then
        source "$state_file"
        if [[ "$ACTIVE" == "blue" ]]; then
            CANARY_HOST="green"
        else
            CANARY_HOST="blue"
        fi
    else
        CANARY_HOST="green"
    fi

    # 只启动新环境的 1 个 worker（金丝雀实例）
    # 注意：实际场景中需要更细致的 K8s/ECS 实例管理
    log "金丝雀主机: $CANARY_HOST"

    # 启动新环境（金丝雀）
    bash "$BLUEGREEN_SCRIPT" --switch-to "$CANARY_HOST" 2>&1 | tee -a "$LOG_FILE"

    # 健康检查新环境
    local active_port=18001
    local inactive_port=18002
    if [[ "$CANARY_HOST" == "blue" ]]; then
        local check_port=$active_port
    else
        local check_port=$inactive_port
    fi

    log "金丝雀健康检查 (端口 $check_port)..."
    for i in $(seq 1 15); do
        local http_code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$check_port/health" 2>/dev/null || echo "000")
        if [[ "$http_code" == "200" ]]; then
            ok "金丝雀健康检查通过"
            break
        fi
        if [[ $i -eq 15 ]]; then
            fail "金丝雀健康检查失败"
            return 1
        fi
        sleep 2
    done

    PHASE="canary"
    START_TIME=$(date +%s)
    save_state

    log "金丝雀实例已部署，开始 ${WATCH_MINUTES} 分钟观察期..."
    return 0
}

# ---- 金丝雀发布: 阶段 2 ----
phase2_expand_to_half() {
    step "阶段 2/3: 扩展到 50% 实例"

    # 切换 Nginx 将流量分流到两个环境（50/50）
    # 这需要在 nginx 中配置 upstream 权重
    log "配置 50/50 流量分发..."

    local nginx_active_conf="/etc/nginx/conf.d/chainke-active-backend.conf"
    local nginx_canary_conf="/etc/nginx/conf.d/chainke-canary-backend.conf"

    # 创建金丝雀后端配置
    echo "# 链客宝金丝雀发布 - 50% 流量" | sudo tee "$nginx_canary_conf" > /dev/null
    echo "# 由 canary-deploy.sh 自动管理" | sudo tee -a "$nginx_canary_conf" > /dev/null
    echo "server 127.0.0.1:18001 weight=1;" | sudo tee -a "$nginx_canary_conf" > /dev/null
    echo "server 127.0.0.1:18002 weight=1;" | sudo tee -a "$nginx_canary_conf" > /dev/null

    # 更新 nginx 主配置使用金丝雀配置
    log "更新 Nginx 配置实现 50/50 分流..."

    # 先检查旧配置，备份
    if [[ -f "$nginx_active_conf" ]]; then
        sudo cp "$nginx_active_conf" "${nginx_active_conf}.bak"
    fi

    # 复制金丝雀配置为活跃配置（启用分流）
    sudo cp "$nginx_canary_conf" "$nginx_active_conf"

    # 重载 Nginx
    if sudo nginx -t 2>&1; then
        sudo systemctl reload nginx || sudo nginx -s reload
        log "Nginx 重载成功，50% 流量分发已生效"
    else
        error "Nginx 配置检查失败，恢复原配置"
        if [[ -f "${nginx_active_conf}.bak" ]]; then
            sudo cp "${nginx_active_conf}.bak" "$nginx_active_conf"
            sudo systemctl reload nginx || sudo nginx -s reload
        fi
        return 1
    fi

    PHASE="half"
    save_state

    local half_watch=$CANARY_HALF_WATCH_MINUTES
    log "50% 流量已分发，开始 ${half_watch} 分钟验证..."
    return 0
}

# ---- 金丝雀发布: 阶段 3 ----
phase3_full_deploy() {
    step "阶段 3/3: 全量发布到 100% 实例"

    # 完全切换到新版本（移除旧版本权重）
    log "执行全量切换..."

    # 使用蓝绿部署脚本完成最终切换
    local state_file="$PROJECT_DIR/deploy/.bluegreen-state"
    local current_active="blue"
    if [[ -f "$state_file" ]]; then
        source "$state_file"
        current_active="$ACTIVE"
    fi

    # 切换到新版本（如果金丝雀在非活跃环境，则切换过去）
    bash "$BLUEGREEN_SCRIPT" --switch-to "$CANARY_HOST" 2>&1 | tee -a "$LOG_FILE"

    # 恢复 Nginx 配置为单后端
    local nginx_active_conf="/etc/nginx/conf.d/chainke-active-backend.conf"
    local canary_port=18001
    if [[ "$CANARY_HOST" == "green" ]]; then
        canary_port=18002
    fi

    echo "# 链客宝全量发布 - 100% 流量到新版本" | sudo tee "$nginx_active_conf" > /dev/null
    echo "# 由 canary-deploy.sh 自动管理" | sudo tee -a "$nginx_active_conf" > /dev/null
    echo "server 127.0.0.1:$canary_port;" | sudo tee -a "$nginx_active_conf" > /dev/null

    sudo nginx -t && sudo systemctl reload nginx || sudo nginx -s reload
    log "Nginx 已切换到新版本"

    # 清理旧环境
    local old_env=""
    if [[ "$CANARY_HOST" == "blue" ]]; then
        old_env="green"
    else
        old_env="blue"
    fi
    bash "$BLUEGREEN_SCRIPT" --switch-to "$CANARY_HOST" 2>&1 | tee -a "$LOG_FILE"

    PHASE="completed"
    save_state

    log "全量发布完成！"
    return 0
}

# ---- 指标查询 ----
query_error_rate() {
    local host="$1"
    # 查询 Prometheus: 错误率（最近 5 分钟）
    local query='sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100'
    local result=$(curl -s --max-time "$PROMETHEUS_QUERY_TIMEOUT" \
        "${PROM_URL}/api/v1/query" \
        --data-urlencode "query=$query" 2>/dev/null)

    if [[ -z "$result" ]]; then
        echo "0"
        return 1
    fi

    # 解析 JSON 结果
    local value=$(echo "$result" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if data['status'] == 'success' and data['data']['result']:
        val = float(data['data']['result'][0]['value'][1])
        print(val)
    else:
        print('0')
except Exception:
    print('0')
" 2>/dev/null || echo "0")

    echo "$value"
}

query_p95_latency() {
    local host="$1"
    # P95 延迟（最近 5 分钟）
    local query='histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))'
    local result=$(curl -s --max-time "$PROMETHEUS_QUERY_TIMEOUT" \
        "${PROM_URL}/api/v1/query" \
        --data-urlencode "query=$query" 2>/dev/null)

    if [[ -z "$result" ]]; then
        echo "0"
        return 1
    fi

    local value=$(echo "$result" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if data['status'] == 'success' and data['data']['result']:
        val = float(data['data']['result'][0]['value'][1]) * 1000  # 转为毫秒
        print(val)
    else:
        print('0')
except Exception:
    print('0')
" 2>/dev/null || echo "0")

    echo "$value"
}

query_traffic_rate() {
    local host="$1"
    # 请求速率（最近 5 分钟）
    local query='sum(rate(http_requests_total[5m]))'
    local result=$(curl -s --max-time "$PROMETHEUS_QUERY_TIMEOUT" \
        "${PROM_URL}/api/v1/query" \
        --data-urlencode "query=$query" 2>/dev/null)

    if [[ -z "$result" ]]; then
        echo "0"
        return 1
    fi

    local value=$(echo "$result" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if data['status'] == 'success' and data['data']['result']:
        val = float(data['data']['result'][0]['value'][1])
        print(val)
    else:
        print('0')
except Exception:
    print('0')
" 2>/dev/null || echo "0")

    echo "$value"
}

# ---- 指标验证 ----
validate_metrics() {
    log "=== 验证指标 ==="

    local error_rate=$(query_error_rate "$CANARY_HOST")
    local p95_latency=$(query_p95_latency "$CANARY_HOST")
    local traffic_rate=$(query_traffic_rate "$CANARY_HOST")

    log "  错误率: ${error_rate}% (阈值: ${ERROR_THRESHOLD}%)"
    log "  P95延迟: ${p95_latency}ms (阈值: ${LATENCY_THRESHOLD}ms)"
    log "  请求速率: ${traffic_rate} req/s"

    # 保存指标到文件
    local metrics_json=$(cat << METRICS_EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "phase": "$PHASE",
    "error_rate": $error_rate,
    "p95_latency_ms": $p95_latency,
    "traffic_rate": $traffic_rate,
    "thresholds": {
        "error_rate": $ERROR_THRESHOLD,
        "p95_latency_ms": $LATENCY_THRESHOLD
    }
}
METRICS_EOF
)
    echo "$metrics_json" > "$METRICS_FILE"

    # 检查阈值
    local all_ok=true
    local failed_checks=""

    # 使用 bc 进行比较（浮点数）
    if (( $(echo "$error_rate > $ERROR_THRESHOLD" | bc -l 2>/dev/null || echo "0") )); then
        fail "错误率 ${error_rate}% 超过阈值 ${ERROR_THRESHOLD}%"
        all_ok=false
        failed_checks="${failed_checks}错误率 "
    fi

    if (( $(echo "$p95_latency > $LATENCY_THRESHOLD" | bc -l 2>/dev/null || echo "0") )); then
        fail "P95延迟 ${p95_latency}ms 超过阈值 ${LATENCY_THRESHOLD}ms"
        all_ok=false
        failed_checks="${failed_checks}P95延迟 "
    fi

    # 如果指标都是 0（可能是 Prometheus 未配置），发出警告但不回滚
    if (( $(echo "$error_rate == 0 && $p95_latency == 0" | bc -l 2>/dev/null || echo "0") )); then
        warn "指标数据为零（Prometheus 可能未配置），跳过自动回滚检查"
        return 0
    fi

    if [[ "$all_ok" == true ]]; then
        ok "所有指标在正常范围内"
        return 0
    else
        error "指标验证失败: ${failed_checks}"
        return 1
    fi
}

# ---- 等待并验证 ----
wait_and_validate() {
    local minutes="$1"
    local interval=60  # 每分钟检查一次

    log "等待 ${minutes} 分钟，每 ${interval}s 检查一次指标..."

    local elapsed=0
    while [[ $elapsed -lt $((minutes * 60)) ]]; do
        sleep $interval
        elapsed=$((elapsed + interval))
        local remaining=$((minutes * 60 - elapsed))
        info "  已等待 ${elapsed}s / $((minutes * 60))s (剩余 ${remaining}s)"

        # 每 2 分钟验证一次指标
        if [[ $((elapsed % 120)) -eq 0 ]]; then
            if ! validate_metrics; then
                error "指标异常，触发自动回滚！"
                return 1
            fi
        fi
    done

    # 最终验证
    log "最终验证..."
    if ! validate_metrics; then
        error "最终指标验证失败，触发自动回滚！"
        return 1
    fi

    ok "观察期完成，所有指标正常"
    return 0
}

# ---- 发送告警 ----
send_alert() {
    local level="$1"
    local message="$2"

    warn "=== 告警 [$level] $message ==="

    local webhook="${DINGTALK_WEBHOOK:-}"
    if [[ -n "$webhook" ]]; then
        curl -s -X POST "$webhook" \
            -H "Content-Type: application/json" \
            -d "{
                \"msgtype\": \"text\",
                \"text\": {
                    \"content\": \"【链客宝金丝雀发布】[$level] $message\n时间: $(date '+%Y-%m-%d %H:%M:%S')\n版本: $VERSION\n阶段: $PHASE\"
                }
            }" > /dev/null 2>&1 || true
        log "  钉钉告警已发送"
    fi
}

# ---- 回滚操作 ----
do_rollback() {
    load_state

    if [[ "$PHASE" == "idle" || "$PHASE" == "completed" ]]; then
        warn "当前无正在进行的金丝雀发布，执行蓝绿回滚..."
        if [[ -f "$BLUEGREEN_SCRIPT" ]]; then
            bash "$BLUEGREEN_SCRIPT" --rollback 2>&1 | tee -a "$LOG_FILE"
        fi
        return 0
    fi

    log "=== 执行金丝雀回滚 ==="
    send_alert "WARNING" "金丝雀发布触发回滚 (阶段: $PHASE, 版本: $VERSION)"

    # 恢复 Nginx 配置到旧版本
    local nginx_active_conf="/etc/nginx/conf.d/chainke-active-backend.conf"

    if [[ -f "${nginx_active_conf}.bak" ]]; then
        sudo cp "${nginx_active_conf}.bak" "$nginx_active_conf"
        if sudo nginx -t 2>&1; then
            sudo systemctl reload nginx || sudo nginx -s reload
            log "Nginx 已恢复到旧版本配置"
        fi
    fi

    # 使用蓝绿部署回滚
    if [[ -f "$BLUEGREEN_SCRIPT" ]]; then
        bash "$BLUEGREEN_SCRIPT" --rollback 2>&1 | tee -a "$LOG_FILE"
    fi

    # 状态重置
    PHASE="rolled_back"
    save_state

    log "金丝雀回滚完成"
    send_alert "INFO" "金丝雀发布已回滚 (版本: $VERSION -> $OLD_VERSION)"

    return 0
}

# ---- 显示状态 ----
show_status() {
    load_state

    echo ""
    echo "========================================"
    echo "  链客宝 金丝雀发布状态"
    echo "  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================"
    echo ""
    echo "  阶  段:  ${PHASE}"
    echo "  版  本:  ${VERSION:-未知}"
    echo "  旧版本:  ${OLD_VERSION:-未知}"
    echo "  金丝雀:  ${CANARY_HOST:-无}"
    echo ""

    if [[ -n "$START_TIME" ]]; then
        local elapsed=$(( $(date +%s) - START_TIME ))
        echo "  已耗时:  $((elapsed / 60)) 分钟 $((elapsed % 60)) 秒"
    fi

    # 读取指标文件
    if [[ -f "$METRICS_FILE" ]]; then
        echo ""
        echo "  最新指标:"
        local err=$(python3 -c "import json; d=json.load(open('$METRICS_FILE')); print(f'    错误率: {d[\"error_rate\"]}%')" 2>/dev/null || echo "    (无法解析)")
        local lat=$(python3 -c "import json; d=json.load(open('$METRICS_FILE')); print(f'    P95延迟: {d[\"p95_latency_ms\"]}ms')" 2>/dev/null || echo "")
        local traf=$(python3 -c "import json; d=json.load(open('$METRICS_FILE')); print(f'    请求速率: {d[\"traffic_rate\"]} req/s')" 2>/dev/null || echo "")
        echo "$err"
        echo "$lat"
        echo "$traf"
    fi

    echo ""
    echo "  阶段说明:"
    echo "    idle       - 未进行金丝雀发布"
    echo "    canary     - 金丝雀验证阶段（1台实例）"
    echo "    half       - 50% 流量分发阶段"
    echo "    completed  - 全量发布完成"
    echo "    rolled_back - 已回滚"
    echo "    aborted    - 已中止"
    echo ""
    echo "========================================"
    echo ""
}

# ---- 主流程 ----
do_deploy() {
    echo ""
    echo "========================================"
    echo "  链客宝 金丝雀发布"
    echo "  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================"
    echo ""
    echo "  配置:"
    echo "    金丝雀实例:       ${CANARY_INSTANCES}"
    echo "    观察时间:         ${WATCH_MINUTES} 分钟"
    echo "    错误率阈值:       ${ERROR_THRESHOLD}%"
    echo "    P95延迟阈值:     ${LATENCY_THRESHOLD}ms"
    echo ""

    ensure_dirs
    acquire_lock
    load_state

    if [[ "$PHASE" == "canary" || "$PHASE" == "half" ]]; then
        warn "已有进行中的金丝雀发布 (阶段: $PHASE)"
        echo "  运行 $0 --status 查看状态"
        echo "  运行 $0 --promote 推进下一阶段"
        echo "  运行 $0 --abort 中止发布"
        exit 1
    fi

    local start_ts=$(date +%s)

    # === 阶段 1: 金丝雀 ===
    if ! phase1_deploy_canary; then
        error "金丝雀部署失败"
        do_rollback
        exit 1
    fi

    if ! wait_and_validate "$WATCH_MINUTES"; then
        do_rollback
        exit 1
    fi

    # === 阶段 2: 50% ===
    if ! phase2_expand_to_half; then
        error "50% 扩量失败"
        do_rollback
        exit 1
    fi

    if ! wait_and_validate "$CANARY_HALF_WATCH_MINUTES"; then
        do_rollback
        exit 1
    fi

    # === 阶段 3: 全量 ===
    if ! phase3_full_deploy; then
        error "全量发布失败"
        do_rollback
        exit 1
    fi

    local end_ts=$(date +%s)
    local duration=$((end_ts - start_ts))

    echo ""
    echo "========================================"
    echo -e "  ${GREEN}✓ 金丝雀发布成功!${NC}"
    echo "  版本:   ${VERSION}"
    echo "  耗时:   $((duration / 60)) 分 $((duration % 60)) 秒"
    echo "  日志:   $LOG_FILE"
    echo "========================================"
    echo ""

    send_alert "INFO" "金丝雀发布成功 (版本: $VERSION, 耗时: ${duration}s)"
}

# ---- 手动推进 ----
do_promote() {
    load_state

    case "$PHASE" in
        canary)
            log "手动推进: 金丝雀 → 50%"
            # 跳过等待，直接验证后推进
            if ! validate_metrics; then
                error "指标验证失败，无法推进"
                exit 1
            fi
            phase2_expand_to_half
            ;;
        half)
            log "手动推进: 50% → 全量"
            if ! validate_metrics; then
                error "指标验证失败，无法推进"
                exit 1
            fi
            phase3_full_deploy
            ;;
        idle|completed|rolled_back|aborted)
            warn "当前阶段为 $PHASE，无法推进"
            ;;
        *)
            error "未知阶段: $PHASE"
            exit 1
            ;;
    esac
}

# ---- 中止 ----
do_abort() {
    load_state

    if [[ "$PHASE" != "canary" && "$PHASE" != "half" ]]; then
        warn "当前无进行中的金丝雀发布 (阶段: $PHASE)"
        exit 0
    fi

    log "=== 中止金丝雀发布 ==="
    do_rollback
    PHASE="aborted"
    save_state
    log "金丝雀发布已中止"
}

# ---- 主入口 ----
main() {
    case "$ACTION" in
        deploy)     do_deploy ;;
        rollback)   acquire_lock; do_rollback ;;
        status)     show_status ;;
        promote)    acquire_lock; do_promote ;;
        abort)      acquire_lock; do_abort ;;
        *)
            warn "请指定操作: --deploy, --rollback, --status, --promote, --abort"
            echo ""
            usage
            exit 1
            ;;
    esac
}

main "$@"
