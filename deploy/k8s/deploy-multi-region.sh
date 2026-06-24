#!/usr/bin/env bash
# ============================================================
# 链客宝AI — 多区域 K8s 部署脚本
# ============================================================
# 说明:
#   支持在亚洲、欧洲、北美三个区域部署链客宝服务。
#   每个区域独立命名空间，区域感知路由通过 Ingress 实现。
#
# 前置条件:
#   - kubectl + kustomize 已安装
#   - 已配置多集群 kubeconfig context: chainke-asia, chainke-eu, chainke-na
#   - 容器镜像已构建并推送至 registry
#
# 使用方式:
#   ./deploy-multi-region.sh --version v1.2.3 --region asia
#   ./deploy-multi-region.sh --version v1.2.3 --region all
#   ./deploy-multi-region.sh --version v1.2.3 --region asia,eu --skip-build
#
# 区域缩写:
#   asia  - 亚洲 (Asia-Pacific, 阿里云/腾讯云)
#   eu    - 欧洲 (Europe, AWS Frankfurt/Azure Netherlands)
#   na    - 北美 (North America, AWS us-east/GCP us-central)
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
NC='\033[0m' # No Color

# ============================================================
# 默认配置
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
K8S_DIR="$SCRIPT_DIR"

REGISTRY="${REGISTRY:-registry.cn-hangzhou.aliyuncs.com/chainke}"
VERSION="${VERSION:-latest}"
REGIONS=""
SKIP_BUILD=false
SKIP_PUSH=false
DRY_RUN=false
NAMESPACE_PREFIX="chainke"
IMAGE_PULL_SECRET="${IMAGE_PULL_SECRET:-}"

# 区域配置: [context_name] [namespace] [region_label] [zone]
declare -A REGION_CONFIG
REGION_CONFIG=(
  ["asia"]="chainke-asia asia asia-east1"
  ["eu"]="chainke-eu europe europe-west1"
  ["na"]="chainke-na northamerica us-central1"
)

# K8s context 名称映射
declare -A K8S_CONTEXT
K8S_CONTEXT=(
  ["asia"]="chainke-asia"
  ["eu"]="chainke-eu"
  ["na"]="chainke-na"
)

# ============================================================
# 帮助信息
# ============================================================
usage() {
  cat <<EOF
链客宝AI — 多区域 K8s 部署脚本

用法:
  $0 [选项]

必选参数:
  --version VERSION    镜像版本号 (例如: v1.2.3)
  --region REGION      部署区域 (asia, eu, na) 或 all

可选参数:
  --registry URL       镜像仓库地址 (默认: $REGISTRY)
  --skip-build         跳过 Docker 构建
  --skip-push          跳过 Docker 推送
  --dry-run            只打印部署计划，不实际执行
  --help               显示此帮助信息

示例:
  # 部署到亚洲
  $0 --version v1.2.3 --region asia

  # 部署到所有区域
  $0 --version v1.2.3 --region all

  # 部署到亚洲和欧洲，跳过构建
  $0 --version v1.2.3 --region asia,eu --skip-build

  # 预览部署计划
  $0 --version v1.2.3 --region all --dry-run

区域说明:
  asia  - 亚洲 (k8s context: ${K8S_CONTEXT[asia]})
  eu    - 欧洲 (k8s context: ${K8S_CONTEXT[eu]})
  na    - 北美 (k8s context: ${K8S_CONTEXT[na]})
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
      --region)
        REGIONS="$2"
        shift 2
        ;;
      --registry)
        REGISTRY="$2"
        shift 2
        ;;
      --skip-build)
        SKIP_BUILD=true
        shift
        ;;
      --skip-push)
        SKIP_PUSH=true
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

  # 校验必选参数
  if [[ -z "$VERSION" ]]; then
    log_error "缺少 --version 参数"
    usage
  fi

  if [[ -z "$REGIONS" ]]; then
    log_error "缺少 --region 参数"
    usage
  fi

  # 处理 "all" 和逗号分隔的区域列表
  if [[ "$REGIONS" == "all" ]]; then
    REGIONS="asia eu na"
  else
    REGIONS="${REGIONS//,/ }"
  fi

  # 校验区域名
  for r in $REGIONS; do
    if [[ ! "${K8S_CONTEXT[$r]+isset}" ]]; then
      log_error "不支持的区域: $r (支持: asia, eu, na)"
      exit 1
    fi
  done
}

# ============================================================
# 前置检查
# ============================================================
check_prerequisites() {
  log_step "前置检查"

  local missing=0

  if ! command -v kubectl &>/dev/null; then
    log_error "kubectl 未安装"
    missing=1
  else
    log_ok "kubectl $(kubectl version --client --short 2>/dev/null | head -1)"
  fi

  if ! command -v kustomize &>/dev/null; then
    log_warn "kustomize 未安装 (将使用 kubectl apply -f)"
  else
    log_ok "kustomize $(kustomize version --short 2>/dev/null || kustomize version)"
  fi

  if ! command -v docker &>/dev/null && [[ "$SKIP_BUILD" == false ]]; then
    log_error "Docker 未安装 (或使用 --skip-build 跳过)"
    missing=1
  elif command -v docker &>/dev/null && [[ "$SKIP_BUILD" == false ]]; then
    log_ok "Docker $(docker --version 2>/dev/null)"
  fi

  # 检查 K8s 集群连通性
  for r in $REGIONS; do
    local ctx="${K8S_CONTEXT[$r]}"
    if kubectl config get-contexts -o name 2>/dev/null | grep -q "^${ctx}$"; then
      if kubectl --context "$ctx" cluster-info --request-timeout=5s 2>/dev/null | head -1; then
        log_ok "K8s 集群 $r ($ctx) 连接正常"
      else
        log_warn "K8s 集群 $r ($ctx) 配置存在但无法连接"
      fi
    else
      log_warn "K8s context '$ctx' 未找到，将直接使用 kubectl 默认 context"
    fi
  done

  if [[ $missing -eq 1 ]]; then
    log_error "请安装缺失的依赖后重试"
    exit 1
  fi
}

# ============================================================
# Docker 构建
# ============================================================
build_images() {
  if [[ "$SKIP_BUILD" == true ]]; then
    log_info "跳过 Docker 构建"
    return
  fi

  log_step "Docker 构建"

  local build_args=(
    --build-arg "BUILD_VERSION=$VERSION"
    --build-arg "BUILD_TIMESTAMP=$(date -u +'%Y%m%d%H%M%S')"
  )

  log_info "构建后端镜像..."
  docker build \
    -t "${REGISTRY}/backend:${VERSION}" \
    -t "${REGISTRY}/backend:latest" \
    --target backend \
    "${build_args[@]}" \
    -f "$PROJECT_ROOT/Dockerfile" \
    "$PROJECT_ROOT"

  log_ok "后端镜像构建完成"

  log_info "构建前端镜像..."
  docker build \
    -t "${REGISTRY}/frontend:${VERSION}" \
    -t "${REGISTRY}/frontend:latest" \
    --target frontend \
    "${build_args[@]}" \
    -f "$PROJECT_ROOT/Dockerfile" \
    "$PROJECT_ROOT"

  log_ok "前端镜像构建完成"
}

# ============================================================
# Docker 推送
# ============================================================
push_images() {
  if [[ "$SKIP_PUSH" == true ]]; then
    log_info "跳过 Docker 推送"
    return
  fi

  log_step "Docker 推送"

  log_info "推送后端镜像..."
  docker push "${REGISTRY}/backend:${VERSION}"
  docker push "${REGISTRY}/backend:latest"

  log_info "推送前端镜像..."
  docker push "${REGISTRY}/frontend:${VERSION}"
  docker push "${REGISTRY}/frontend:latest"

  log_ok "镜像推送完成"
}

# ============================================================
# 生成区域 K8s 配置
# ============================================================
generate_region_manifests() {
  local region="$1"
  local namespace="${NAMESPACE_PREFIX}-${region}"
  local region_label="$2"
  local zone="$3"

  local region_dir="/tmp/chainke-k8s-${region}"
  mkdir -p "$region_dir"

  log_info "生成区域 $region 的 K8s 配置..."

  # 复制基础配置
  cp "$K8S_DIR/namespace.yaml" \
     "$K8S_DIR/configmap.yaml" \
     "$K8S_DIR/backend-deployment.yaml" \
     "$K8S_DIR/backend-service.yaml" \
     "$K8S_DIR/frontend-deployment.yaml" \
     "$K8S_DIR/frontend-service.yaml" \
     "$K8S_DIR/ingress.yaml" \
     "$K8S_DIR/hpa.yaml" \
     "$K8S_DIR/kustomization.yaml" \
     "$region_dir/" 2>/dev/null || true

  # 更新命名空间 (使用 sed 保持跨平台兼容)
  if [[ "$(uname)" == "Darwin" ]]; then
    # macOS sed
    sed -i '' "s/namespace: chainke/namespace: ${namespace}/g" "$region_dir"/*.yaml
    sed -i '' "s/name: chainke$/name: ${namespace}/g" "$region_dir/namespace.yaml"
    sed -i '' "s/name: chainke-/name: ${namespace}-/g" "$region_dir"/*.yaml
    # 区域标签
    sed -i '' "s/app: chainke/app: chainke\n    region: ${region}/g" "$region_dir/namespace.yaml"
    # 更新 Ingress 域名后缀
    sed -i '' "s/\.top/.top/g" "$region_dir/ingress.yaml"
  else
    # Linux sed
    sed -i "s/namespace: chainke/namespace: ${namespace}/g" "$region_dir"/*.yaml
    sed -i "s/name: chainke$/name: ${namespace}/g" "$region_dir/namespace.yaml"
    sed -i "s/name: chainke-/name: ${namespace}-/g" "$region_dir"/*.yaml
    sed -i "/name: ${namespace}/a\    region: ${region}" "$region_dir/namespace.yaml"
  fi

  # 更新 ConfigMap 中的区域特定配置
  cat >> "$region_dir/configmap.yaml" << EOF

  # ==========================================================
  # 区域特定配置
  # ==========================================================
  REGION: "${region}"
  REGION_ZONE: "${zone}"
  # 区域感知 API 基础 URL
  API_BASE_URL: "https://api-${region}.liankebao.top"
  CDN_BASE_URL: "https://cdn-${region}.liankebao.top"
EOF

  # 更新 kustomization.yaml
  cat > "$region_dir/kustomization.yaml" << EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: ${namespace}

labels:
  - pairs:
      app: chainke
      region: ${region}
      managed-by: kustomize

commonAnnotations:
  description: "链客宝AI - ${region}区域部署"
  team: "chainke-dev"
  region: "${region}"

resources:
  - namespace.yaml
  - configmap.yaml
  - backend-deployment.yaml
  - backend-service.yaml
  - frontend-deployment.yaml
  - frontend-service.yaml
  - ingress.yaml
  - hpa.yaml

images:
  - name: registry.cn-hangzhou.aliyuncs.com/chainke/backend
    newTag: ${VERSION}
  - name: registry.cn-hangzhou.aliyuncs.com/chainke/frontend
    newTag: ${VERSION}
EOF

  echo "$region_dir"
}

# ============================================================
# 部署到指定区域
# ============================================================
deploy_to_region() {
  local region="$1"
  local ctx="${K8S_CONTEXT[$region]}"
  local config="${REGION_CONFIG[$region]}"
  IFS=' ' read -r namespace region_label zone <<< "$config"

  log_step "部署到区域: ${region} (${namespace})"

  # 生成区域配置
  local manifest_dir
  manifest_dir=$(generate_region_manifests "$region" "$region_label" "$zone")

  if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY RUN] 以下配置将被应用到区域 $region:"
    echo "----------------------------------------"
    kustomize build "$manifest_dir" 2>/dev/null || cat "$manifest_dir"/*.yaml
    echo "----------------------------------------"
    return
  fi

  # 检查 context 是否存在
  local kubectl_cmd="kubectl"
  if kubectl config get-contexts -o name 2>/dev/null | grep -q "^${ctx}$"; then
    kubectl_cmd="kubectl --context ${ctx}"
    log_info "使用 K8s context: $ctx"
  else
    log_warn "K8s context '$ctx' 不存在，使用默认 context"
  fi

  # 确保命名空间存在
  $kubectl_cmd apply -f "$manifest_dir/namespace.yaml" 2>/dev/null || true

  # 应用配置
  if command -v kustomize &>/dev/null; then
    log_info "使用 kustomize 部署..."
    kustomize build "$manifest_dir" | $kubectl_cmd apply -f -
  else
    log_info "使用 kubectl apply -f 部署..."
    $kubectl_cmd apply -f "$manifest_dir"
  fi

  # 等待部署完成
  log_info "等待 Deployment 就绪..."
  $kubectl_cmd -n "$namespace" wait \
    --for=condition=Available \
    deployment/chainke-backend \
    --timeout=180s 2>/dev/null || log_warn "后端部署就绪超时"

  $kubectl_cmd -n "$namespace" wait \
    --for=condition=Available \
    deployment/chainke-frontend \
    --timeout=180s 2>/dev/null || log_warn "前端部署就绪超时"

  # 显示状态
  log_ok "区域 $region 部署状态:"
  $kubectl_cmd -n "$namespace" get pods,deployments,services,ingress,hpa -o wide

  # 健康检查
  log_info "执行区域健康检查..."
  # 尝试通过 Ingress 访问
  local ingress_host="$($kubectl_cmd -n "$namespace" get ingress -o jsonpath='{.items[0].spec.rules[0].host}' 2>/dev/null || echo "")"
  if [[ -n "$ingress_host" ]]; then
    log_info "Ingress 地址: $ingress_host"
  fi

  log_ok "区域 $region 部署完成!"
}

# ============================================================
# 部署后验证
# ============================================================
verify_deployment() {
  log_step "全局部署验证"

  for r in $REGIONS; do
    local ctx="${K8S_CONTEXT[$r]}"
    local namespace="${NAMESPACE_PREFIX}-${r}"

    echo ""
    log_info "区域 $r 状态:"

    local kubectl_cmd="kubectl"
    if kubectl config get-contexts -o name 2>/dev/null | grep -q "^${ctx}$"; then
      kubectl_cmd="kubectl --context ${ctx}"
    fi

    echo "  Pods:"
    $kubectl_cmd -n "$namespace" get pods -o wide 2>/dev/null | sed 's/^/    /'
    echo "  Services:"
    $kubectl_cmd -n "$namespace" get services 2>/dev/null | sed 's/^/    /'
    echo "  HPA:"
    $kubectl_cmd -n "$namespace" get hpa 2>/dev/null | sed 's/^/    /'
  done

  echo ""
  log_ok "全部区域部署验证完成!"
}

# ============================================================
# 回滚函数
# ============================================================
rollback_region() {
  local region="$1"
  local revision="${2:-}"
  local namespace="${NAMESPACE_PREFIX}-${region}"

  log_step "回滚区域: $region"

  local kubectl_cmd="kubectl"
  if kubectl config get-contexts -o name 2>/dev/null | grep -q "^${K8S_CONTEXT[$region]}$"; then
    kubectl_cmd="kubectl --context ${K8S_CONTEXT[$region]}"
  fi

  if [[ -n "$revision" ]]; then
    $kubectl_cmd -n "$namespace" rollout undo deployment/chainke-backend --to-revision="$revision"
    $kubectl_cmd -n "$namespace" rollout undo deployment/chainke-frontend --to-revision="$revision"
  else
    $kubectl_cmd -n "$namespace" rollout undo deployment/chainke-backend
    $kubectl_cmd -n "$namespace" rollout undo deployment/chainke-frontend
  fi

  $kubectl_cmd -n "$namespace" rollout status deployment/chainke-backend --timeout=120s
  $kubectl_cmd -n "$namespace" rollout status deployment/chainke-frontend --timeout=120s

  log_ok "区域 $region 回滚完成"
}

# ============================================================
# 主流程
# ============================================================
main() {
  echo ""
  echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
  echo -e "${CYAN}  链客宝AI — 多区域 K8s 部署                      ${NC}"
  echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
  echo ""
  echo "  版本:    $VERSION"
  echo "  区域:    $REGIONS"
  echo "  仓库:    $REGISTRY"
  echo "  干运行:  $([ "$DRY_RUN" = true ] && echo '是' || echo '否')"
  echo ""

  # 前置检查
  check_prerequisites

  # 构建
  build_images

  # 推送
  push_images

  # 部署到各区域
  log_step "开始多区域部署"
  for r in $REGIONS; do
    local config="${REGION_CONFIG[$r]}"
    IFS=' ' read -r namespace region_label zone <<< "$config"
    deploy_to_region "$r" "$region_label" "$zone"
  done

  # 验证
  verify_deployment

  echo ""
  echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
  echo -e "${GREEN}  多区域部署完成!                                 ${NC}"
  echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
  echo ""
  echo "  版本: $VERSION"
  echo "  区域:"
  for r in $REGIONS; do
    echo "    - $r: https://$r.liankebao.top"
  done
  echo ""
}

# ============================================================
# 入口
# ============================================================
if [[ $# -eq 0 ]]; then
  usage
fi

parse_args "$@"
main
