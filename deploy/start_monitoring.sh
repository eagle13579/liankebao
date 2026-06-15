#!/usr/bin/env bash
# ============================================================
# 链客宝AI 监控栈启动脚本
# ============================================================
# 一键启动 Prometheus + Grafana + Alertmanager + cAdvisor
#
# 使用方法:
#   bash deploy/start_monitoring.sh
#
# 停止:
#   docker compose -f deploy/docker-compose.monitoring.yml down -v
#
# 查看日志:
#   docker compose -f deploy/docker-compose.monitoring.yml logs -f
# ============================================================

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.monitoring.yml"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}  链客宝AI 生产级监控栈 启动脚本${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""

# --------------------------------------------------
# 前置检查
# --------------------------------------------------
echo -e "${YELLOW}[1/4] 检查前置依赖...${NC}"

# 检查 Docker
if ! command -v docker &>/dev/null; then
    echo -e "${RED}✗ Docker 未安装。请先安装 Docker。${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker: $(docker --version)${NC}"

# 检查 Docker Compose
if ! docker compose version &>/dev/null; then
    echo -e "${RED}✗ Docker Compose 不可用。请安装 Docker Compose v2。${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose: $(docker compose version)${NC}"

# 检查配置文件是否存在
CONFIG_FILES=(
    "${PROJECT_DIR}/deploy/prometheus/prometheus.yml"
    "${PROJECT_DIR}/deploy/prometheus/alerts/liankebao_alerts.yml"
    "${PROJECT_DIR}/deploy/grafana/datasources/prometheus.yml"
    "${PROJECT_DIR}/deploy/grafana/dashboards/chainke_overview.json"
    "${PROJECT_DIR}/deploy/alertmanager/alertmanager.yml"
)
for f in "${CONFIG_FILES[@]}"; do
    if [ ! -f "$f" ]; then
        echo -e "${RED}✗ 配置文件缺失: $f${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✓ 全部配置文件就位${NC}"

# --------------------------------------------------
# 语法验证
# --------------------------------------------------
echo ""
echo -e "${YELLOW}[2/4] 验证 YAML 语法...${NC}"

# Python YAML 验证
if command -v python3 &>/dev/null; then
    python3 -c "
import yaml, sys, os
files = [
    '${PROJECT_DIR}/deploy/prometheus/prometheus.yml',
    '${PROJECT_DIR}/deploy/prometheus/alerts/liankebao_alerts.yml',
    '${PROJECT_DIR}/deploy/alertmanager/alertmanager.yml',
    '${PROJECT_DIR}/deploy/grafana/datasources/prometheus.yml',
]
ok = True
for f in files:
    if os.path.isfile(f):
        try:
            with open(f) as fh:
                yaml.safe_load(fh)
            print(f\"  ✓ YAML 有效: {f}\")
        except yaml.YAMLError as e:
            print(f\"  ✗ YAML 错误: {f}: {e}\")
            ok = False
if not ok:
    sys.exit(1)
" && echo -e "${GREEN}✓ YAML 语法验证通过${NC}" || {
    echo -e "${RED}✗ YAML 语法验证失败${NC}"
    exit 1
}
else
    echo -e "${YELLOW}⚠ python3 不可用，跳过 YAML 验证${NC}"
fi

# Grafana Dashboard JSON 验证
if command -v python3 &>/dev/null; then
    python3 -c "
import json
with open('${PROJECT_DIR}/deploy/grafana/dashboards/chainke_overview.json') as f:
    json.load(f)
print('  ✓ Dashboard JSON 有效')
" || {
    echo -e "${RED}✗ Dashboard JSON 格式错误${NC}"
    exit 1
}
fi

# --------------------------------------------------
# 创建 Grafana dashboards 置入配置
# --------------------------------------------------
echo ""
echo -e "${YELLOW}[3/4] 配置 Grafana Dashboard 置入...${NC}"

DASHBOARDS_YAML="${PROJECT_DIR}/deploy/grafana/grafana-dashboards.yaml"
if [ ! -f "$DASHBOARDS_YAML" ]; then
    cat > "$DASHBOARDS_YAML" << 'DASHBOARDSCONF'
# ============================================================
# Grafana Dashboard 置入配置
# ============================================================
apiVersion: 1

providers:
  - name: "链客宝AI仪表盘"
    orgId: 1
    folder: "链客宝AI"
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
DASHBOARDSCONF
    echo -e "${GREEN}✓ 创建 grafana-dashboards.yaml${NC}"
else
    echo -e "${GREEN}✓ grafana-dashboards.yaml 已存在${NC}"
fi

# --------------------------------------------------
# 启动服务
# --------------------------------------------------
echo ""
echo -e "${YELLOW}[4/4] 启动监控容器...${NC}"

cd "$PROJECT_DIR"
docker compose -f "$COMPOSE_FILE" up -d

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  链客宝AI 监控栈启动完成!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo -e "  ${BLUE}Prometheus:${NC}       http://localhost:9090"
echo -e "  ${BLUE}Grafana:${NC}          http://localhost:3001  (admin/admin)"
echo -e "  ${BLUE}Alertmanager:${NC}     http://localhost:9093"
echo -e "  ${BLUE}cAdvisor:${NC}         http://localhost:8088"
echo ""
echo -e "  ${BLUE}指标抓取:${NC}"
echo -e "    - 健康看板:  http://localhost:9100/metrics  (每15s)"
echo -e "    - FastAPI:   http://localhost:8001/metrics  (每15s)"
echo ""
echo -e "  ${BLUE}部件状态:${NC}"
docker compose -f "$COMPOSE_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""

echo -e "${YELLOW}提示: 首次启动需等 Grafana 初始化 (约 30s)${NC}"
echo -e "${YELLOW}      Grafana 预置数据源和仪表盘将在初始化后自动加载${NC}"
echo ""
