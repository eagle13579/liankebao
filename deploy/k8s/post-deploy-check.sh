#!/usr/bin/env bash
# ============================================================
# 链客宝AI — 部署后健康检查脚本
# ============================================================
# 说明:
#   检查所有 K8s 资源是否正常运行:
#     - 所有 Pod 处于 Running/Completed 状态
#     - 所有 Deployment 可用
#     - Service 端点可达
#     - Ingress 配置正确
#     - HPA 状态正常
#
# 使用方式:
#   ./post-deploy-check.sh                    # 检查默认 namespace (chainke)
#   ./post-deploy-check.sh -n production      # 指定命名空间
#   ./post-deploy-check.sh --verbose          # 详细输出
#   ./post-deploy-check.sh --wait             # 等待所有 Pod 就绪 (最多 180s)
#   ./post-deploy-check.sh --endpoint-check   # 执行端点可达性测试
# ============================================================

set -euo pipefail

# ============================================================
# 颜色输出
# ============================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ============================================================
# 默认配置
# ============================================================
NAMESPACE="chainke"
VERBOSE=false
WAIT_READY=false
ENDPOINT_CHECK=false
EXIT_ON_FAILURE=false

# 错误计数
ERRORS=0
WARNINGS=0

# ============================================================
# 帮助信息
# ============================================================
usage() {
  cat <<EOF
链客宝AI — 部署后健康检查脚本

用法:
  $0 [选项]

选项:
  -n, --namespace NAME  命名空间 (默认: chainke)
  -v, --verbose         详细输出 (显示所有资源详情)
  -w, --wait            等待所有 Pod 就绪 (最多 180 秒)
  -e, --endpoint-check  执行端点可达性测试 (需集群内 curl)
  -f, --fail-on-error   检查失败时返回非零退出码
  -h, --help            显示此帮助信息

示例:
  # 基本检查
  $0

  # 详细检查 + 等待就绪 + 端点测试
  $0 --verbose --wait --endpoint-check

  # 自定义命名空间
  $0 -n staging
EOF
  exit 0
}

# ============================================================
# 日志函数
# ============================================================
log_info()    { echo -e "${BLUE}[INFO]${NC}   $*"; }
log_ok()      { echo -e "${GREEN}[OK]${NC}     $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}   $*"; ((WARNINGS++)); }
log_error()   { echo -e "${RED}[ERROR]${NC}  $*" >&2; ((ERRORS++)); }
log_section() { echo -e "\n${CYAN}════════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"; }

# ============================================================
# 参数解析
# ============================================================
parse_args() {
  while [[ $# -gt 0 ]]; do
    case $1 in
      -n|--namespace)
        NAMESPACE="$2"
        shift 2
        ;;
      -v|--verbose)
        VERBOSE=true
        shift
        ;;
      -w|--wait)
        WAIT_READY=true
        shift
        ;;
      -e|--endpoint-check)
        ENDPOINT_CHECK=true
        shift
        ;;
      -f|--fail-on-error)
        EXIT_ON_FAILURE=true
        shift
        ;;
      -h|--help)
        usage
        ;;
      *)
        log_error "未知参数: $1"
        usage
        ;;
    esac
  done
}

# ============================================================
# 前置检查
# ============================================================
check_prerequisites() {
  if ! command -v kubectl &>/dev/null; then
    log_error "kubectl 未安装"
    exit 1
  fi

  if ! kubectl cluster-info --request-timeout=5s &>/dev/null; then
    log_error "无法连接 K8s 集群"
    log_info "请检查 kubeconfig 配置: kubectl cluster-info"
    exit 1
  fi

  log_ok "kubectl $(kubectl version --client --short 2>/dev/null | head -1)"
  log_ok "集群连接正常"
}

# ============================================================
# 检查 Namespace 是否存在
# ============================================================
check_namespace() {
  log_section "检查 Namespace"

  if kubectl get namespace "$NAMESPACE" &>/dev/null; then
    log_ok "Namespace '$NAMESPACE' 存在"
    if [[ "$VERBOSE" == true ]]; then
      kubectl get namespace "$NAMESPACE" -o yaml | grep -E "  (name|status|labels):" | sed 's/^/  /'
    fi
  else
    log_error "Namespace '$NAMESPACE' 不存在"
    log_info "请先创建命名空间: kubectl create namespace $NAMESPACE"
    return 1
  fi
}

# ============================================================
# 检查 Deployment
# ============================================================
check_deployments() {
  log_section "检查 Deployment"

  local deployments
  deployments=$(kubectl -n "$NAMESPACE" get deployments -o name 2>/dev/null | sed 's|deployment.apps/||' | sed 's|deployment/||')

  if [[ -z "$deployments" ]]; then
    log_warn "Namespace '$NAMESPACE' 中没有 Deployment"
    return
  fi

  local all_available=true
  for dep in $deployments; do
    local ready_replicas desired_replicas available
    ready_replicas=$(kubectl -n "$NAMESPACE" get deployment "$dep" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    desired_replicas=$(kubectl -n "$NAMESPACE" get deployment "$dep" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
    available=$(kubectl -n "$NAMESPACE" get deployment "$dep" -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null || echo "False")

    if [[ "$available" == "True" ]]; then
      log_ok "$dep — 就绪: ${ready_replicas}/${desired_replicas} 副本"
    else
      log_error "$dep — 不可用 (就绪: ${ready_replicas}/${desired_replicas})"
      all_available=false
      if [[ "$VERBOSE" == true ]]; then
        echo "  Deployment 详情:"
        kubectl -n "$NAMESPACE" describe deployment "$dep" 2>/dev/null | grep -E "(Status:|Conditions:|Replicas:)" | sed 's/^/    /' || true
        echo "  Pod 事件:"
        local dep_selector
        dep_selector=$(kubectl -n "$NAMESPACE" get deployment "$dep" -o jsonpath='{.spec.selector.matchLabels}' 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(' '.join([f'{k}={v}' for k,v in d.items()]))
" 2>/dev/null || echo "")
        if [[ -n "$dep_selector" ]]; then
          kubectl -n "$NAMESPACE" get pods -l "$dep_selector" 2>/dev/null | sed 's/^/    /' || true
        fi
      fi
    fi
  done

  if [[ "$all_available" == false ]]; then
    return 1
  fi
}

# ============================================================
# 检查 Pod 状态
# ============================================================
check_pods() {
  log_section "检查 Pod 状态"

  local pods
  pods=$(kubectl -n "$NAMESPACE" get pods --no-headers 2>/dev/null)

  if [[ -z "$pods" ]]; then
    log_warn "Namespace '$NAMESPACE' 中没有 Pod"
    return
  fi

  local total=0 running=0 pending=0 failed=0 unknown=0 others=0

  while IFS= read -r line; do
    ((total++))
    local name status restarts
    name=$(echo "$line" | awk '{print $1}')
    status=$(echo "$line" | awk '{print $3}')
    restarts=$(echo "$line" | awk '{print $4}')

    case "$status" in
      Running)
        ((running++))
        if [[ "$VERBOSE" == true ]]; then
          log_ok "$name — Running (重启: $restarts)"
        fi
        ;;
      Completed)
        ((others++))
        if [[ "$VERBOSE" == true ]]; then
          log_ok "$name — Completed"
        fi
        ;;
      Pending|Init:*|ContainerCreating|PodInitializing)
        ((pending++))
        log_warn "$name — $status"
        if [[ "$VERBOSE" == true ]]; then
          kubectl -n "$NAMESPACE" describe pod "$name" 2>/dev/null | grep -A5 "Conditions:" | head -10 | sed 's/^/  /' || true
        fi
        ;;
      CrashLoopBackOff|Error|ImagePullBackOff|ErrImagePull|CreateContainerConfigError)
        ((failed++))
        log_error "$name — $status"
        if [[ "$VERBOSE" == true ]]; then
          echo "  --- 最近日志 ---"
          kubectl -n "$NAMESPACE" logs "$name" --tail=20 2>/dev/null | sed 's/^/  /' || echo "  (日志不可用)"
          echo "  --- 事件 ---"
          kubectl -n "$NAMESPACE" get events --field-selector involvedObject.name="$name" --sort-by='.lastTimestamp' 2>/dev/null | tail -5 | sed 's/^/  /' || true
        fi
        ;;
      *)
        ((unknown++))
        log_warn "$name — $status"
        ;;
    esac
  done <<< "$pods"

  echo ""
  echo "  Pod 统计: 总计=$total  运行中=$running  等待中=$pending  失败=$failed  已完成=$others  其他=$unknown"
  echo ""

  if [[ "$failed" -gt 0 ]]; then
    log_error "$failed 个 Pod 处于失败状态"
    # 显示失败的 Pod
    kubectl -n "$NAMESPACE" get pods --no-headers 2>/dev/null | \
      awk '{if ($3 != "Running" && $3 != "Completed") print "  " $0}' || true
    return 1
  fi

  if [[ "$pending" -gt 0 ]]; then
    log_warn "$pending 个 Pod 仍在等待中"
  fi
}

# ============================================================
# 检查 Service
# ============================================================
check_services() {
  log_section "检查 Service"

  local services
  services=$(kubectl -n "$NAMESPACE" get services --no-headers 2>/dev/null)

  if [[ -z "$services" ]]; then
    log_warn "Namespace '$NAMESPACE' 中没有 Service"
    return
  fi

  local svc_count=0
  while IFS= read -r line; do
    ((svc_count++))
    local name type cluster_ip ports
    name=$(echo "$line" | awk '{print $1}')
    type=$(echo "$line" | awk '{print $2}')
    cluster_ip=$(echo "$line" | awk '{print $3}')
    ports=$(echo "$line" | awk '{$1=$2=$3=$4=""; print $0}' | xargs)

    if [[ "$VERBOSE" == true ]]; then
      log_ok "$name — Type: $type, ClusterIP: $cluster_ip, Ports: $ports"
    fi
  done <<< "$services"

  log_ok "$svc_count 个 Service"
}

# ============================================================
# 检查 Ingress
# ============================================================
check_ingress() {
  log_section "检查 Ingress"

  local ingresses
  ingresses=$(kubectl -n "$NAMESPACE" get ingress --no-headers 2>/dev/null)

  if [[ -z "$ingresses" ]]; then
    log_ok "无 Ingress 配置 (可选)"
    return
  fi

  while IFS= read -r line; do
    local name hosts address
    name=$(echo "$line" | awk '{print $1}')
    hosts=$(echo "$line" | awk '{print $2}')
    address=$(echo "$line" | awk '{print $4}')

    if [[ -n "$address" && "$address" != "none" ]]; then
      log_ok "$name — 地址: $address, 域名: $hosts"
    else
      log_warn "$name — 地址未分配, 域名: $hosts"
      log_info "  请确保 Ingress Controller 已部署且已分配公网 IP"
    fi
  done <<< "$ingresses"
}

# ============================================================
# 检查 HPA
# ============================================================
check_hpa() {
  log_section "检查 HPA"

  local hpas
  hpas=$(kubectl -n "$NAMESPACE" get hpa --no-headers 2>/dev/null)

  if [[ -z "$hpas" ]]; then
    log_ok "无 HPA 配置 (可选)"
    return
  fi

  while IFS= read -r line; do
    local name ref target current min max
    name=$(echo "$line" | awk '{print $1}')
    ref=$(echo "$line" | awk '{print $2}')
    target=$(echo "$line" | awk '{print $3}')
    current=$(echo "$line" | awk '{print $4}')
    min=$(echo "$line" | awk '{print $5}')
    max=$(echo "$line" | awk '{print $6}')

    if [[ -n "$current" && "$current" != "<unknown>" ]]; then
      log_ok "$name — $ref, 当前: $current / 目标: $target, 副本: $min-$max"
    else
      log_warn "$name — 指标数据不可用 (可能 metrics-server 未安装)"
    fi
  done <<< "$hpas"
}

# ============================================================
# 检查 ConfigMap
# ============================================================
check_configmaps() {
  log_section "检查 ConfigMap"

  local configmaps
  configmaps=$(kubectl -n "$NAMESPACE" get configmaps -o name 2>/dev/null | sed 's|configmap/||')

  if [[ -z "$configmaps" ]]; then
    log_warn "Namespace '$NAMESPACE' 中没有 ConfigMap"
    return
  fi

  local cm_count=0
  for cm in $configmaps; do
    ((cm_count++))
    if [[ "$VERBOSE" == true ]]; then
      log_ok "$cm"
    fi
  done

  log_ok "$cm_count 个 ConfigMap"
}

# ============================================================
# 检查 Secret
# ============================================================
check_secrets() {
  log_section "检查 Secret"

  local secrets
  secrets=$(kubectl -n "$NAMESPACE" get secrets -o name 2>/dev/null | sed 's|secret/||' | grep -v "^default-token\|^sh\.helm\|kubeseal\|default-secret")

  if [[ -z "$secrets" ]]; then
    log_warn "Namespace '$NAMESPACE' 中没有 Secret (除默认 token 外)"
    return
  fi

  for secret in $secrets; do
    log_ok "Secret '$secret' 存在"
  done
}

# ============================================================
# 端点可达性测试
# ============================================================
check_endpoints() {
  if [[ "$ENDPOINT_CHECK" != true ]]; then
    return
  fi

  log_section "端点可达性测试"

  local test_pod="chainke-connectivity-test"

  # 检查是否需要创建测试 Pod
  if ! kubectl -n "$NAMESPACE" get pod "$test_pod" &>/dev/null; then
    log_info "创建临时测试 Pod..."
    kubectl -n "$NAMESPACE" run "$test_pod" \
      --image=curlimages/curl:latest \
      --restart=Never \
      --command -- sleep 60 2>/dev/null || {
      log_warn "创建测试 Pod 失败，跳过端点测试"
      return
    }
    # 等待 Pod 就绪
    kubectl -n "$NAMESPACE" wait --for=condition=Ready "pod/$test_pod" --timeout=30s 2>/dev/null || {
      log_warn "测试 Pod 未就绪，跳过端点测试"
      kubectl -n "$NAMESPACE" delete pod "$test_pod" --grace-period=0 --ignore-not-found &>/dev/null || true
      return
    }
  fi

  local all_reachable=true

  # 遍历所有 Service 进行内部可达性测试
  local services
  services=$(kubectl -n "$NAMESPACE" get services --no-headers 2>/dev/null | awk '{print $1, $3, $5}')

  while IFS= read -r line; do
    local svc_name svc_ip svc_ports
    svc_name=$(echo "$line" | awk '{print $1}')
    svc_ip=$(echo "$line" | awk '{print $2}')
    svc_ports=$(echo "$line" | awk '{print $3}')

    # 跳过 headless service / external service
    if [[ "$svc_ip" == "None" || -z "$svc_ip" ]]; then
      continue
    fi

    # 提取端口 (取第一个端口)
    local port
    port=$(echo "$svc_ports" | cut -d',' -f1 | cut -d'/' -f1)

    if [[ -z "$port" ]]; then
      continue
    fi

    # 尝试 HTTP 连接
    if kubectl -n "$NAMESPACE" exec "$test_pod" -- curl -sf --max-time 3 "http://${svc_name}:${port}/" &>/dev/null; then
      log_ok "Service '$svc_name' 可达 (http://${svc_name}:${port}/)"
    elif kubectl -n "$NAMESPACE" exec "$test_pod" -- curl -sf --max-time 3 "http://${svc_name}:${port}/health" &>/dev/null; then
      log_ok "Service '$svc_name' 可达 (http://${svc_name}:${port}/health)"
    else
      # TCP 端口可达性测试
      if kubectl -n "$NAMESPACE" exec "$test_pod" -- timeout 3 bash -c "echo >/dev/tcp/${svc_name}/${port}" &>/dev/null; then
        log_ok "Service '$svc_name' TCP 端口可达 (${svc_name}:${port}) — 非 HTTP 服务"
      else
        log_warn "Service '$svc_name' 不可达 (${svc_name}:${port})"
        all_reachable=false
      fi
    fi
  done <<< "$services"

  # 清理测试 Pod
  kubectl -n "$NAMESPACE" delete pod "$test_pod" --grace-period=0 --ignore-not-found &>/dev/null || true

  if [[ "$all_reachable" == false ]]; then
    log_warn "部分 Service 端点不可达"
  fi
}

# ============================================================
# 等待所有 Pod 就绪
# ============================================================
wait_for_readiness() {
  if [[ "$WAIT_READY" != true ]]; then
    return
  fi

  log_section "等待 Pod 就绪"

  log_info "等待所有 Pod 进入 Running 状态 (最长 180 秒)..."

  local deadline=$((SECONDS + 180))
  local all_ready=false

  while [[ $SECONDS -lt $deadline ]]; do
    all_ready=true
    local pending_pods
    pending_pods=$(kubectl -n "$NAMESPACE" get pods --no-headers 2>/dev/null | \
      awk '{if ($3 != "Running" && $3 != "Completed") print $1}' || true)

    if [[ -z "$pending_pods" ]]; then
      all_ready=true
      break
    fi

    all_ready=false
    echo -n "."
    sleep 5
  done
  echo ""

  if [[ "$all_ready" == true ]]; then
    log_ok "所有 Pod 已就绪"
  else
    log_warn "等待超时，仍有 Pod 未就绪"
    kubectl -n "$NAMESPACE" get pods --no-headers 2>/dev/null | \
      awk '{if ($3 != "Running" && $3 != "Completed") print "  " $0}' || true
  fi
}

# ============================================================
# 检查事件 (最近异常)
# ============================================================
check_events() {
  log_section "最近异常事件"

  local warnings
  warnings=$(kubectl -n "$NAMESPACE" get events --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | tail -10)

  if [[ -z "$warnings" ]]; then
    log_ok "无异常事件"
    return
  fi

  local count
  count=$(echo "$warnings" | wc -l)
  if [[ "$count" -le 1 ]]; then
    log_ok "无异常事件"
    return
  fi

  log_warn "以下为最近 Warning 事件:"
  echo "$warnings" | sed 's/^/  /'
}

# ============================================================
# 输出总结
# ============================================================
print_summary() {
  log_section "检查总结"

  echo ""
  if [[ "$ERRORS" -eq 0 && "$WARNINGS" -eq 0 ]]; then
    echo -e "  ${GREEN}✅ 全部检查通过!${NC}"
    echo "  命名空间: $NAMESPACE"
    echo "  状态:     健康"
  elif [[ "$ERRORS" -eq 0 ]]; then
    echo -e "  ${YELLOW}⚠️  检查完成 — $WARNINGS 个警告${NC}"
    echo "  命名空间: $NAMESPACE"
    echo "  请检查以上警告项"
  else
    echo -e "  ${RED}❌ 检查完成 — $ERRORS 个错误, $WARNINGS 个警告${NC}"
    echo "  命名空间: $NAMESPACE"
    echo "  请修复以上错误后重试"
  fi
  echo ""

  if [[ "$ERRORS" -gt 0 ]]; then
    log_info "部署后诊断命令:"
    echo "  kubectl -n $NAMESPACE get pods -o wide"
    echo "  kubectl -n $NAMESPACE describe pod <pod-name>"
    echo "  kubectl -n $NAMESPACE logs <pod-name>"
    echo "  kubectl -n $NAMESPACE get events --sort-by='.lastTimestamp'"
  fi
}

# ============================================================
# 主流程
# ============================================================
main() {
  parse_args "$@"

  echo ""
  echo "╔═══════════════════════════════════════════════════════════╗"
  echo "║       链客宝AI — 部署后健康检查                           ║"
  echo "╚═══════════════════════════════════════════════════════════╝"
  echo ""

  check_prerequisites

  if [[ "$WAIT_READY" == true ]]; then
    wait_for_readiness
  fi

  check_namespace
  check_deployments
  check_pods
  check_services
  check_ingress
  check_hpa
  check_configmaps
  check_secrets
  check_events
  check_endpoints
  print_summary

  if [[ "$EXIT_ON_FAILURE" == true && "$ERRORS" -gt 0 ]]; then
    exit 1
  fi
}

main "$@"
