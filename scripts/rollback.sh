#!/bin/bash
# 链客宝回滚脚本
set -e

BACKUP_DIR="/opt/chainke/backups"
CURRENT_VERSION=$(cat /opt/chainke/current_version.txt 2>/dev/null || echo "none")
PREVIOUS_VERSION=$(cat /opt/chainke/previous_version.txt 2>/dev/null || echo "none")

echo "[回滚] 当前版本: $CURRENT_VERSION"
echo "[回滚] 回滚目标: $PREVIOUS_VERSION"

if [ "$PREVIOUS_VERSION" = "none" ]; then
    echo "[回滚] 无可用回滚版本"
    exit 1
fi

echo "[回滚] 切换到版本 $PREVIOUS_VERSION"
docker-compose -f /opt/chainke/docker-compose.yml down
docker-compose -f /opt/chainke/docker-compose.yml up -d

echo "$CURRENT_VERSION" > /opt/chainke/previous_version.txt
echo "$PREVIOUS_VERSION" > /opt/chainke/current_version.txt

echo "[回滚] 完成"
