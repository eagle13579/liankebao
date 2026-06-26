#!/usr/bin/env bash
# ==============================================================================
# 链客宝 — K8s 部署脚本
# ==============================================================================
# 功能:
#   1. Docker build（使用 deploy/docker/Dockerfile.prod）
#   2. 镜像推送到阿里云容器镜像服务 (ACR)
#   3. kubectl apply -k deploy/k8s/
#   4. kubectl rollout status 等待新版本就绪
#   5. 调用 healthcheck.sh 验证服务健康
# ==============================================================================

set -euo pipefail

# ── 颜色输出 ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── 项目根目录 ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# ── 配置（可通过环境变量覆盖）─────────────────────────────────────────────────
# 阿里云 ACR 地址
REGISTRY="${REGISTRY:-registry.cn-hangzhou.aliyuncs.com}"
NAMESPACE="${NAMESPACE:-liankebao}"
IMAGE_NAME="${IMAGE_NAME:-web}"

# K8s 命名空间
K8S_NAMESPACE="${K8S_NAMESPACE:-chainke-prod}"

# イメージ标签: 默认使用 git commit hash + 时间戳
GIT_HASH="${GIT_HASH:-$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')}"
BUILD_TS="$(date '+%Y%m%d-%H%M%S')"
IMAGE_TAG="${IMAGE_TAG:-${GIT_HASH}-${BUILD_TS}}"
# 完整镜像地址
FULL_IMAGE="${REGISTRY}/${NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}"
FULL_IMAGE_LATEST="${REGISTRY}/${NAMESPACE}/${IMAGE_NAME}:latest"

# 是否强制推送 latest 标签
PUSH_LATEST="${PUSH_LATEST:-true}"

# ── 前置检查 ─────────────────────────────────────────────────────────────────
info "===== 链客宝 K8s 部署脚本 ====="
info "项目目录:  $PROJECT_DIR"
info "镜像地址:  $FULL_IMAGE"
echo ""

# 检查必需工具
for cmd in docker kubectl git; do
    if ! command -v "$cmd" &>/dev/null; then
        err "缺少必需命令: $cmd"
        exit 1
    fi
done

# 检查 Dockerfile 是否存在
DOCKERFILE="$PROJECT_DIR/deploy/docker/Dockerfile.prod"
if [ ! -f "$DOCKERFILE" ]; then
    err "Dockerfile 不存在: $DOCKERFILE"
    exit 1
fi

# 检查 K8s 配置目录
if [ ! -d "$PROJECT_DIR/deploy/k8s" ]; then
    err "K8s 配置目录不存在: $PROJECT_DIR/deploy/k8s"
    exit 1
fi

# ── Step 1: Docker Build ─────────────────────────────────────────────────────
info "──────────────────────────────────────────"
info "Step 1/5: Docker build (${IMAGE_TAG})"
info "──────────────────────────────────────────"

docker build \
    -f "$DOCKERFILE" \
    -t "$FULL_IMAGE" \
    -t "$FULL_IMAGE_LATEST" \
    "$PROJECT_DIR"

ok "Docker build 完成: $FULL_IMAGE"

# ── Step 2: 推送到阿里云 ACR ─────────────────────────────────────────────────
info "──────────────────────────────────────────"
info "Step 2/5: 推送到阿里云容器镜像服务"
info "──────────────────────────────────────────"

# 检查是否已登录 ACR（若无则提示）
if ! docker inspect "$REGISTRY" &>/dev/null 2>&1; then
    warn "可能未登录 ACR，尝试登录..."
    warn "请确保已执行: docker login --username=<阿里云用户名> $REGISTRY"
    docker login "$REGISTRY" 2>/dev/null || {
        err "ACR 登录失败，请先手动登录: docker login $REGISTRY"
        exit 1
    }
fi

info "推送镜像: $FULL_IMAGE"
docker push "$FULL_IMAGE"

if [ "$PUSH_LATEST" = "true" ]; then
    info "推送镜像: $FULL_IMAGE_LATEST"
    docker push "$FULL_IMAGE_LATEST"
fi

ok "镜像推送完成"

# ── Step 3: 更新 K8s 资源配置中的镜像标签 ──────────────────────────────────
info "──────────────────────────────────────────"
info "Step 3/5: 更新 K8s 部署镜像版本"
info "──────────────────────────────────────────"

# 使用 kubectl set image 原地更新，避免修改 YAML 文件
kubectl set image \
    -n "$K8S_NAMESPACE" \
    deployment/chainke-web \
    "web=${FULL_IMAGE}" \
    --record 2>/dev/null || {
    warn "kubectl set image 失败（可能首次部署），改用 kustomize 方式..."
    # 首次部署：直接 apply kustomization
    kubectl apply -k "$PROJECT_DIR/deploy/k8s/"
    ok "kubectl apply -k deploy/k8s/ 完成"
}

# ── Step 4: kubectl rollout status ───────────────────────────────────────────
info "──────────────────────────────────────────"
info "Step 4/5: 等待 rollout 完成"
info "──────────────────────────────────────────"

if kubectl get deployment chainke-web -n "$K8S_NAMESPACE" &>/dev/null 2>&1; then
    info "等待 deployment/chainke-web rollout 完成..."
    if kubectl rollout status deployment/chainke-web \
        -n "$K8S_NAMESPACE" \
        --timeout="${ROLLOUT_TIMEOUT:-5m}"; then
        ok "Rollout 完成"
    else
        err "Rollout 超时或失败"
        err "执行以下命令查看状态:"
        err "  kubectl describe deployment chainke-web -n $K8S_NAMESPACE"
        err "  kubectl get pods -n $K8S_NAMESPACE"
        kubectl get pods -n "$K8S_NAMESPACE" --no-headers 2>/dev/null | head -10
        exit 1
    fi
else
    info "首次部署，跳过 rollout 等待（kubectl apply 已处理）"
fi

# ── Step 5: 健康检查 ─────────────────────────────────────────────────────────
info "──────────────────────────────────────────"
info "Step 5/5: 等待服务健康"
info "──────────────────────────────────────────"

HEALTHCHECK_SCRIPT="$SCRIPT_DIR/healthcheck.sh"
if [ -f "$HEALTHCHECK_SCRIPT" ]; then
    info "调用健康检查脚本..."
    # 等待一小段时间让服务完全启动
    for i in $(seq 1 12); do
        if bash "$HEALTHCHECK_SCRIPT"; then
            ok "健康检查通过"
            break
        fi
        if [ "$i" -eq 12 ]; then
            err "健康检查超时（约60秒），部署可能未完全就绪"
            err "请手动检查 Pod 状态:"
            err "  kubectl get pods -n $K8S_NAMESPACE"
            err "  kubectl logs -n $K8S_NAMESPACE deployment/chainke-web"
            exit 1
        fi
        info "等待服务启动... (${i}/12, 间隔5s)"
        sleep 5
    done
else
    warn "未找到 healthcheck.sh，跳过健康检查步骤"
    warn "请手动验证服务:"
    warn "  kubectl get pods -n $K8S_NAMESPACE"
    warn "  kubectl port-forward -n $K8S_NAMESPACE deployment/chainke-web 8001:8001"
    warn "  curl http://localhost:8001/health"
fi

# ── 部署总结 ─────────────────────────────────────────────────────────────────
echo ""
ok "===== 部署完成 ====="
echo ""
echo "  镜像:        $FULL_IMAGE"
echo "  命名空间:    $K8S_NAMESPACE"
echo "  Deployment:  chainke-web"
echo ""
echo "查看 Pod 状态:"
echo "  kubectl get pods -n $K8S_NAMESPACE"
echo ""
echo "查看实时日志:"
echo "  kubectl logs -n $K8S_NAMESPACE -l app=chainke-web --tail=100 -f"
echo ""
echo "端口转发（本地调试）:"
echo "  kubectl port-forward -n $K8S_NAMESPACE deployment/chainke-web 8001:8001"
