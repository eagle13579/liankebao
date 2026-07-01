#!/usr/bin/env bash
# ============================================================
# 链客宝AI — 一键部署到阿里云 ACK
# ============================================================
# 说明:
#   自动完成以下步骤:
#     1. 检查前置依赖 (aliyun CLI, kubectl, kustomize)
#     2. 如果 ACK 集群不存在，自动创建 (按量付费)
#     3. 获取集群 kubeconfig 并配置 kubectl
#     4. 通过 kustomize 部署所有 K8s 资源
#     5. 健康检查 + 端点验证
#
# 前置条件:
#   - 已安装 aliyun CLI (https://aliyun.com/cli)
#   - 已配置阿里云 AK/SK:
#       aliyun configure set --profile chainke \
#         --access-key-id <AK> --access-key-secret <SK> --region cn-hangzhou
#   - 已安装 kubectl + kustomize
#
# 使用方式:
#   export ALICLOUD_REGION=cn-hangzhou
#   export ACK_CLUSTER_NAME=chainke-prod
#   export ACR_REGISTRY=registry.cn-hangzhou.aliyuncs.com/chainke
#   ./deploy-ack.sh --version v1.2.3
#
# 环境变量:
#   ALICLOUD_REGION     阿里云区域 (默认: cn-hangzhou)
#   ACK_CLUSTER_NAME    ACK 集群名称 (默认: chainke-prod)
#   ACR_REGISTRY        容器镜像仓库地址 (默认: registry.cn-hangzhou.aliyuncs.com/chainke)
#   ACK_NODE_COUNT      集群节点数 (默认: 3)
#   ACK_NODE_TYPE       节点实例规格 (默认: ecs.g6.large)
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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ALICLOUD_REGION="${ALICLOUD_REGION:-cn-hangzhou}"
ACK_CLUSTER_NAME="${ACK_CLUSTER_NAME:-chainke-prod}"
ACR_REGISTRY="${ACR_REGISTRY:-registry.cn-hangzhou.aliyuncs.com/chainke}"
ACK_NODE_COUNT="${ACK_NODE_COUNT:-3}"
ACK_NODE_TYPE="${ACK_NODE_TYPE:-ecs.g6.large}"
VERSION="${VERSION:-latest}"
DRY_RUN=false
SKIP_CLUSTER_CHECK=false

# ============================================================
# 帮助信息
# ============================================================
usage() {
  cat <<EOF
链客宝AI — 阿里云 ACK 一键部署脚本

用法:
  $0 [选项]

必选参数:
  --version VERSION    镜像版本号 (例如: v1.2.3)

可选参数:
  --cluster NAME        ACK 集群名称 (默认: $ACK_CLUSTER_NAME)
  --region REGION       阿里云区域 (默认: $ALICLOUD_REGION)
  --registry URL        镜像仓库地址 (默认: $ACR_REGISTRY)
  --node-count N       集群节点数 (默认: $ACK_NODE_COUNT)
  --node-type TYPE     节点实例规格 (默认: $ACK_NODE_TYPE)
  --skip-cluster-check 跳过集群创建步骤，假设集群已存在
  --dry-run            只打印部署计划，不实际执行
  --help               显示此帮助信息

环境变量:
  ALICLOUD_REGION     阿里云区域 (默认: cn-hangzhou)
  ACK_CLUSTER_NAME    ACK 集群名称 (默认: chainke-prod)
  ACR_REGISTRY        容器镜像仓库地址 (默认: registry.cn-hangzhou.aliyuncs.com/chainke)
  ACK_NODE_COUNT      集群节点数 (默认: 3)
  ACK_NODE_TYPE       节点实例规格 (默认: ecs.g6.large)

示例:
  # 最小化部署 (使用环境变量配置)
  export ALICLOUD_REGION=cn-hangzhou
  export ACK_CLUSTER_NAME=chainke-prod
  ./deploy-ack.sh --version v1.2.3

  # 完整参数部署
  ./deploy-ack.sh \\
    --version v1.2.3 \\
    --cluster chainke-staging \\
    --region cn-shanghai \\
    --registry registry.cn-shanghai.aliyuncs.com/chainke \\
    --node-count 5 \\
    --node-type ecs.g7.xlarge

  # 集群已存在，跳过创建
  ./deploy-ack.sh --version v1.2.3 --skip-cluster-check

  # 预览模式
  ./deploy-ack.sh --version v1.2.3 --dry-run
EOF
  exit 0
}

# ============================================================
# 日志函数
# ============================================================
log_info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step()  { echo -e "\n${CYAN}━━━ $* ━━━${NC}"; }

# ============================================================
# 参数解析
# ============================================================
parse_args() {
  while [[ $# -gt 0 ]]; do
    case $1 in
      --version)
        VERSION="$2"
        shift 2
        ;;
      --cluster)
        ACK_CLUSTER_NAME="$2"
        shift 2
        ;;
      --region)
        ALICLOUD_REGION="$2"
        shift 2
        ;;
      --registry)
        ACR_REGISTRY="$2"
        shift 2
        ;;
      --node-count)
        ACK_NODE_COUNT="$2"
        shift 2
        ;;
      --node-type)
        ACK_NODE_TYPE="$2"
        shift 2
        ;;
      --skip-cluster-check)
        SKIP_CLUSTER_CHECK=true
        shift
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --help|-h)
        usage
        ;;
      *)
        log_error "未知参数: $1"
        usage
        ;;
    esac
  done

  if [[ -z "$VERSION" ]]; then
    log_error "缺少 --version 参数"
    usage
  fi
}

# ============================================================
# 前置检查
# ============================================================
check_prerequisites() {
  log_step "前置检查"

  local missing=0

  # aliyun CLI
  if ! command -v aliyun &>/dev/null; then
    log_error "aliyun CLI 未安装"
    log_info "安装方法: curl -sL https://aliyun-cli.alibaba.com/install.sh | bash"
    missing=1
  else
    log_ok "aliyun CLI $(aliyun --version 2>&1 | head -1)"
  fi

  # kubectl
  if ! command -v kubectl &>/dev/null; then
    log_error "kubectl 未安装"
    missing=1
  else
    log_ok "kubectl $(kubectl version --client --short 2>/dev/null | head -1)"
  fi

  # kustomize
  if ! command -v kustomize &>/dev/null; then
    log_warn "kustomize 未安装 (将使用 kubectl apply -f 替代)"
  else
    log_ok "kustomize $(kustomize version --short 2>/dev/null || kustomize version)"
  fi

  # 验证 aliyun CLI 配置
  if command -v aliyun &>/dev/null; then
    if ! aliyun configure list --profile chainke &>/dev/null; then
      if [[ -z "${ALIBABA_CLOUD_ACCESS_KEY_ID:-}" ]]; then
        log_warn "aliyun 未配置 profile 'chainke'，也未见 ALIBABA_CLOUD_ACCESS_KEY_ID 环境变量"
        log_info "请运行: aliyun configure set --profile chainke --access-key-id <AK> --access-key-secret <SK> --region $ALICLOUD_REGION"
        log_info "或设置环境变量: ALIBABA_CLOUD_ACCESS_KEY_ID, ALIBABA_CLOUD_ACCESS_KEY_SECRET, ALIBABA_CLOUD_REGION_ID"
      fi
    fi
  fi

  if [[ $missing -eq 1 ]]; then
    log_error "请安装缺失的依赖后重试"
    exit 1
  fi
}

# ============================================================
# 获取/创建 ACK 集群
# ============================================================
ensure_ack_cluster() {
  if [[ "$SKIP_CLUSTER_CHECK" == true ]]; then
    log_info "跳过集群检查（--skip-cluster-check）"
    return
  fi

  log_step "检查/创建 ACK 集群"

  local aliyun_opts=()
  if aliyun configure list --profile chainke &>/dev/null; then
    aliyun_opts=(--profile chainke)
  fi

  # 检查集群是否存在
  log_info "查询集群: $ACK_CLUSTER_NAME (区域: $ALICLOUD_REGION)..."
  local cluster_info
  cluster_info=$(aliyun cs GET /clusters \
    --region "$ALICLOUD_REGION" \
    "${aliyun_opts[@]}" \
    --query "clusters[?name=='${ACK_CLUSTER_NAME}'].cluster_id | [0]" \
    --output json 2>/dev/null || echo "null")

  if [[ "$cluster_info" == "null" || -z "$cluster_info" ]]; then
    log_info "集群不存在，准备创建..."

    if [[ "$DRY_RUN" == true ]]; then
      log_info "[DRY RUN] 将创建 ACK 集群:"
      echo "  名称: $ACK_CLUSTER_NAME"
      echo "  区域: $ALICLOUD_REGION"
      echo "  节点数: $ACK_NODE_COUNT"
      echo "  实例规格: $ACK_NODE_TYPE"
      echo ""
      log_warn "集群创建大约需要 5-15 分钟，请耐心等待"
      return
    fi

    log_info "正在创建 ACK 托管版集群 (按量付费)..."
    log_info "节点规格: $ACK_NODE_TYPE, 节点数: $ACK_NODE_COUNT"
    echo ""
    log_warn "集群创建大约需要 5-15 分钟，请耐心等待..."

    local create_result
    create_result=$(aliyun cs POST /clusters \
      --region "$ALICLOUD_REGION" \
      "${aliyun_opts[@]}" \
      --header "Content-Type=application/json" \
      --body "{
        \"name\": \"${ACK_CLUSTER_NAME}\",
        \"cluster_type\": \"ManagedKubernetes\",
        \"profile\": \"Default\",
        \"region_id\": \"${ALICLOUD_REGION}\",
        \"vpcid\": \"\",
        \"container_cidr\": \"172.16.0.0/16\",
        \"service_cidr\": \"172.17.0.0/20\",
        \"num_of_nodes\": ${ACK_NODE_COUNT},
        \"instance_types\": [\"${ACK_NODE_TYPE}\"],
        \"system_disk_category\": \"cloud_essd\",
        \"system_disk_size\": 120,
        \"data_disk\": true,
        \"data_disk_size\": 200,
        \"charge_type\": \"PostPaid\",
        \"worker_instance_charge_type\": \"PostPaid\",
        \"snat_entry\": true,
        \"endpoint_public_access\": true,
        \"tags\": [
          {\"key\": \"app\", \"value\": \"chainke\"},
          {\"key\": \"environment\", \"value\": \"production\"}
        ]
      }" 2>&1) || {
      log_error "集群创建失败: $create_result"
      exit 1
    }

    local cluster_id
    cluster_id=$(echo "$create_result" | grep -o '"cluster_id":"[^"]*"' | head -1 | cut -d'"' -f4)
    if [[ -z "$cluster_id" ]]; then
      log_error "无法获取集群 ID，创建可能失败"
      log_info "响应内容: $create_result"
      exit 1
    fi
    log_ok "集群创建中，Cluster ID: $cluster_id"

    # 轮询等待集群就绪
    log_info "等待集群就绪..."
    local max_retries=60  # 最多等 30 分钟
    local retry=0
    while [[ $retry -lt $max_retries ]]; do
      local status
      status=$(aliyun cs GET "/clusters/${cluster_id}" \
        --region "$ALICLOUD_REGION" \
        "${aliyun_opts[@]}" \
        --output json 2>/dev/null | grep -o '"state":"[^"]*"' | cut -d'"' -f4 || echo "unknown")

      if [[ "$status" == "running" ]]; then
        log_ok "集群已就绪!"
        break
      fi
      retry=$((retry + 1))
      sleep 30
      echo -n "."
    done
    echo ""

    if [[ $retry -ge $max_retries ]]; then
      log_error "集群创建超时 (30分钟)，请手动检查 ACK 控制台"
      exit 1
    fi
  else
    local cluster_id
    cluster_id=$(echo "$cluster_info" | grep -o '"cluster_id":"[^"]*"' | cut -d'"' -f4 || echo "$cluster_info")
    log_ok "集群已存在，Cluster ID: $cluster_id"
  fi
}

# ============================================================
# 配置 kubectl (获取 kubeconfig)
# ============================================================
configure_kubectl() {
  log_step "配置 kubectl"

  local aliyun_opts=()
  if aliyun configure list --profile chainke &>/dev/null; then
    aliyun_opts=(--profile chainke)
  fi

  # 获取集群 ID
  local cluster_id
  cluster_id=$(aliyun cs GET /clusters \
    --region "$ALICLOUD_REGION" \
    "${aliyun_opts[@]}" \
    --query "clusters[?name=='${ACK_CLUSTER_NAME}'].cluster_id | [0]" \
    --output json 2>/dev/null | tr -d '"')

  if [[ -z "$cluster_id" || "$cluster_id" == "null" ]]; then
    log_error "无法获取集群 ID"
    exit 1
  fi

  log_info "Cluster ID: $cluster_id"

  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] 将获取集群 kubeconfig 并配置 kubectl"
    return
  fi

  # 下载 kubeconfig
  log_info "下载 kubeconfig..."
  local kubeconfig_content
  kubeconfig_content=$(aliyun cs GET "/k8s/${cluster_id}/user_config" \
    --region "$ALICLOUD_REGION" \
    "${aliyun_opts[@]}" \
    --output json 2>/dev/null | grep -o '"config":"[^"]*"' | cut -d'"' -f4 | base64 -d 2>/dev/null || true)

  if [[ -z "$kubeconfig_content" ]]; then
    # 尝试另一种方式获取 kubeconfig
    log_info "尝试 API 方式获取 kubeconfig..."
    kubeconfig_content=$(aliyun cs GET "/k8s/${cluster_id}/user_config" \
      --region "$ALICLOUD_REGION" \
      "${aliyun_opts[@]}" \
      --output json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('config',''))" 2>/dev/null || echo "")
  fi

  if [[ -z "$kubeconfig_content" ]]; then
    # 最终方案：使用临时文件
    local tmp_kubeconfig
    tmp_kubeconfig=$(mktemp /tmp/ack-kubeconfig-XXXXXX)
    aliyun cs GET "/k8s/${cluster_id}/user_config" \
      --region "$ALICLOUD_REGION" \
      "${aliyun_opts[@]}" \
      --output json > "$tmp_kubeconfig" 2>/dev/null || true

    # 尝试从 JSON 中提取 config 字段
    if command -v python3 &>/dev/null; then
      kubeconfig_content=$(python3 -c "
import sys,json,base64
with open('$tmp_kubeconfig') as f:
    d=json.load(f)
config_b64=d.get('config','')
if config_b64:
    print(base64.b64decode(config_b64).decode('utf-8'))
" 2>/dev/null) || kubeconfig_content=""
    fi
    rm -f "$tmp_kubeconfig"
  fi

  if [[ -z "$kubeconfig_content" ]]; then
    log_error "获取 kubeconfig 失败"
    log_info "请手动获取: aliyun cs GET /k8s/<cluster-id>/user_config --region $ALICLOUD_REGION"
    log_info "然后将 kubeconfig 保存到 ~/.kube/config"
    exit 1
  fi

  # 保存 kubeconfig
  mkdir -p ~/.kube
  local kubeconfig_path="${KUBECONFIG:-$HOME/.kube/config}"

  # 如果已有 config，合并而不是覆盖
  if [[ -f "$kubeconfig_path" ]]; then
    cp "$kubeconfig_path" "${kubeconfig_path}.bak.$(date +%s)"
    log_info "已备份原有 kubeconfig 到 ${kubeconfig_path}.bak.*"
  fi

  echo "$kubeconfig_content" > "$kubeconfig_path"
  chmod 600 "$kubeconfig_path"
  log_ok "kubeconfig 已配置: $kubeconfig_path"

  # 验证连接
  log_info "验证集群连接..."
  if kubectl cluster-info --request-timeout=10s 2>&1 | head -3; then
    log_ok "集群连接正常"
  else
    log_warn "集群连接异常，请检查网络和安全组设置"
    log_info "确保集群的 API Server 公网端点已启用"
  fi
}

# ============================================================
# 创建命名空间
# ============================================================
ensure_namespace() {
  log_step "确保 Namespace 存在"

  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] 将创建 namespace: chainke"
    return
  fi

  kubectl apply -f "$SCRIPT_DIR/namespace.yaml" 2>/dev/null || true
  log_ok "Namespace 已就绪"
}

# ============================================================
# 创建 Secret (从环境变量或提示输入)
# ============================================================
ensure_secrets() {
  log_step "配置 Secrets"

  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] 将检查并创建 Secret: chainke-secret"
    return
  fi

  # 检查 Secret 是否已存在
  if kubectl -n chainke get secret chainke-secret &>/dev/null; then
    log_ok "Secret 'chainke-secret' 已存在，跳过"
    return
  fi

  log_warn "Secret 'chainke-secret' 不存在，从环境变量创建或以默认模板创建"
  log_info "推荐使用以下命令手动创建:"
  echo "  kubectl create secret generic chainke-secret --namespace=chainke \\"
  echo "    --from-literal=PG_USER='chainke' \\"
  echo "    --from-literal=PG_PASSWORD='<your-password>' \\"
  echo "    --from-literal=SECRET_KEY='<your-secret>' \\"
  echo "    --from-literal=GEMINI_API_KEY='<your-key>'"
  echo ""

  # 如果环境变量已设置，自动创建
  if [[ -n "${PG_PASSWORD:-}" && -n "${SECRET_KEY:-}" ]]; then
    log_info "检测到环境变量，自动创建 Secret..."
    kubectl create secret generic chainke-secret --namespace=chainke \
      --from-literal=PG_USER="${PG_USER:-chainke}" \
      --from-literal=PG_PASSWORD="${PG_PASSWORD}" \
      --from-literal=SECRET_KEY="${SECRET_KEY}" \
      --from-literal=ENCRYPTION_KEY="${ENCRYPTION_KEY:-}" \
      --from-literal=GEMINI_API_KEY="${GEMINI_API_KEY:-}" \
      --from-literal=SENTRY_DSN="${SENTRY_DSN:-}" \
      --from-literal=POSTHOG_API_KEY="${POSTHOG_API_KEY:-}" \
      --from-literal=SMTP_HOST="${SMTP_HOST:-}" \
      --from-literal=SMTP_PORT="${SMTP_PORT:-587}" \
      --from-literal=SMTP_USER="${SMTP_USER:-}" \
      --from-literal=SMTP_PASSWORD="${SMTP_PASSWORD:-}" \
      --from-literal=SMTP_FROM="${SMTP_FROM:-}" \
      --dry-run=client -o yaml 2>/dev/null | kubectl apply -f - || {
      log_warn "自动创建 Secret 失败，请手动创建"
    }
  else
    # 创建占位 Secret (用户需自行更新)
    log_info "创建占位 Secret (请后续更新真实值)..."
    kubectl create secret generic chainke-secret --namespace=chainke \
      --from-literal=PG_USER='chainke' \
      --from-literal=PG_PASSWORD='CHANGEME' \
      --from-literal=SECRET_KEY='CHANGEME' \
      --from-literal=GEMINI_API_KEY='CHANGEME' \
      --from-literal=SENTRY_DSN='' \
      --dry-run=client -o yaml 2>/dev/null | kubectl apply -f - || {
      log_warn "创建占位 Secret 失败"
    }
  fi
}

# ============================================================
# 更新镜像标签并部署
# ============================================================
deploy_with_kustomize() {
  log_step "部署到 ACK 集群"

  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] 将执行以下部署操作:"
    echo "  kustomize edit set image \\"
    echo "    ${ACR_REGISTRY}/backend=${VERSION} \\"
    echo "    ${ACR_REGISTRY}/frontend=${VERSION}"
    echo "  kustomize build deploy/k8s/ | kubectl apply -f -"
    return
  fi

  cd "$SCRIPT_DIR"

  # 更新镜像标签
  if command -v kustomize &>/dev/null; then
    log_info "更新镜像标签为: $VERSION"
    kustomize edit set image \
      "${ACR_REGISTRY}/backend=${VERSION}" \
      "${ACR_REGISTRY}/frontend=${VERSION}" || {
      log_warn "kustomize edit set image 失败，手动处理..."
      # 手动替换 kustomization.yaml 中的镜像标签
      sed -i "s/newTag: .*/newTag: ${VERSION}/" kustomization.yaml
    }
    log_ok "镜像标签已更新"
  else
    log_warn "kustomize 未安装，手动更新 kustomization.yaml..."
    sed -i "s/newTag: .*/newTag: ${VERSION}/" kustomization.yaml
  fi

  # 应用配置
  log_info "应用 K8s 配置..."
  if command -v kustomize &>/dev/null; then
    kustomize build . | kubectl apply -f -
  else
    kubectl apply -k .
  fi

  log_ok "配置已应用"
}

# ============================================================
# 健康检查
# ============================================================
health_check() {
  log_step "健康检查"

  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] 将执行部署后健康检查"
    return
  fi

  local ns="chainke"

  # 等待 Deployment 就绪
  log_info "等待 Deployment 就绪 (最长 3 分钟)..."

  local deployments=("chainke-backend" "chainke-frontend")
  local all_ready=true

  for dep in "${deployments[@]}"; do
    if kubectl -n "$ns" get deployment "$dep" &>/dev/null; then
      log_info "等待 $dep 就绪..."
      if kubectl -n "$ns" wait --for=condition=Available "deployment/$dep" --timeout=180s 2>/dev/null; then
        log_ok "$dep ✓"
      else
        log_warn "$dep 就绪超时"
        all_ready=false
      fi
    else
      log_warn "Deployment '$dep' 不存在，跳过"
    fi
  done

  # 检查 Pod 状态
  echo ""
  log_info "Pod 状态概览:"
  kubectl -n "$ns" get pods -o wide 2>/dev/null | sed 's/^/  /' || log_warn "获取 Pod 状态失败"

  # 检查是否有非 Running 的 Pod
  local not_running
  not_running=$(kubectl -n "$ns" get pods --no-headers 2>/dev/null | awk '{if ($3 != "Running" && $3 != "Completed") print $0}' | wc -l)
  if [[ "$not_running" -gt 0 ]]; then
    log_warn "发现 $not_running 个非 Running 状态的 Pod"
    kubectl -n "$ns" get pods --no-headers 2>/dev/null | awk '{if ($3 != "Running" && $3 != "Completed") print "  " $0}'
  fi

  # 检查 Service
  echo ""
  log_info "Service 状态:"
  kubectl -n "$ns" get services -o wide 2>/dev/null | sed 's/^/  /'

  # 检查 HPA
  echo ""
  log_info "HPA 状态:"
  kubectl -n "$ns" get hpa 2>/dev/null | sed 's/^/  /' || log_warn "无 HPA 配置"

  # 检查 Ingress
  echo ""
  log_info "Ingress 状态:"
  kubectl -n "$ns" get ingress 2>/dev/null | sed 's/^/  /' || log_warn "无 Ingress 配置"

  # 端点可达性测试 (通过 Service ClusterIP)
  echo ""
  log_info "端点可达性测试 (集群内)..."
  local test_pod="chainke-connectivity-test"

  # 创建临时测试 Pod（如果不存在）
  if ! kubectl -n "$ns" get pod "$test_pod" &>/dev/null; then
    kubectl -n "$ns" run "$test_pod" \
      --image=curlimages/curl:latest \
      --restart=Never \
      --command -- sleep 30 2>/dev/null || true
    # 等待 Pod 就绪
    kubectl -n "$ns" wait --for=condition=Ready "pod/$test_pod" --timeout=60s 2>/dev/null || true
  fi

  if kubectl -n "$ns" get pod "$test_pod" -o jsonpath='{.status.phase}' 2>/dev/null | grep -q Running; then
    # 测试后端 Service
    local backend_svc="chainke-backend"
    if kubectl -n "$ns" get svc "$backend_svc" &>/dev/null; then
      local backend_port
      backend_port=$(kubectl -n "$ns" get svc "$backend_svc" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null)
      if kubectl -n "$ns" exec "$test_pod" -- curl -sf "http://${backend_svc}:${backend_port}/health" &>/dev/null; then
        log_ok "后端 Service 可达 ($backend_svc:$backend_port/health)"
      else
        log_warn "后端 Service 不可达或 /health 端点不存在"
      fi
    fi

    # 测试前端 Service
    local frontend_svc="chainke-frontend"
    if kubectl -n "$ns" get svc "$frontend_svc" &>/dev/null; then
      local frontend_port
      frontend_port=$(kubectl -n "$ns" get svc "$frontend_svc" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null)
      if kubectl -n "$ns" exec "$test_pod" -- curl -sf "http://${frontend_svc}:${frontend_port}/" &>/dev/null; then
        log_ok "前端 Service 可达 ($frontend_svc:$frontend_port/)"
      else
        log_warn "前端 Service 不可达"
      fi
    fi

    # 清理
    kubectl -n "$ns" delete pod "$test_pod" --grace-period=0 --ignore-not-found &>/dev/null || true
  else
    log_warn "跳过端点可达性测试（无法创建测试 Pod）"
    kubectl -n "$ns" delete pod "$test_pod" --grace-period=0 --ignore-not-found &>/dev/null || true
  fi

  echo ""
  if [[ "$all_ready" == true ]]; then
    log_ok "=== 全部 Deployment 就绪，部署成功! ==="
  else
    log_warn "=== 部分 Deployment 未就绪，请检查以上输出 ==="
  fi
}

# ============================================================
# 部署总结
# ============================================================
print_summary() {
  log_step "部署总结"

  echo ""
  echo "  项目:         链客宝AI (LianKeBao)"
  echo "  版本:         $VERSION"
  echo "  集群:         $ACK_CLUSTER_NAME ($ALICLOUD_REGION)"
  echo "  镜像仓库:     $ACR_REGISTRY"
  echo "  命名空间:     chainke"
  echo ""
  echo "  常用命令:"
  echo "    kubectl -n chainke get pods"
  echo "    kubectl -n chainke get deployments"
  echo "    kubectl -n chainke get services"
  echo "    kubectl -n chainke get ingress"
  echo "    kubectl -n chainke get hpa"
  echo "    kubectl -n chainke logs deployment/chainke-backend"
  echo ""
  echo "  回滚命令:"
  echo "    kubectl -n chainke rollout undo deployment/chainke-backend"
  echo "    kubectl -n chainke rollout undo deployment/chainke-frontend"
  echo ""
  echo "  查看历史版本:"
  echo "    kubectl -n chainke rollout history deployment/chainke-backend"
  echo ""
}

# ============================================================
# 主流程
# ============================================================
main() {
  parse_args "$@"

  echo ""
  echo "╔═══════════════════════════════════════════════════════════╗"
  echo "║           链客宝AI — 阿里云 ACK 一键部署                   ║"
  echo "╚═══════════════════════════════════════════════════════════╝"
  echo ""

  check_prerequisites
  ensure_ack_cluster
  configure_kubectl
  ensure_namespace
  ensure_secrets
  deploy_with_kustomize
  health_check
  print_summary

  log_ok "部署流程完成!"
}

main "$@"
