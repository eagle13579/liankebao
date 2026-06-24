#!/usr/bin/env bash
# ============================================================
# 链客宝AI SQLite → PostgreSQL 一键迁移脚本 (Linux/Mac)
# ============================================================
# 用法:
#   ./auto_migrate.sh               — 完整迁移: 建表+数据迁移+验证
#   ./auto_migrate.sh --verify      — 仅验证数据一致性
#   ./auto_migrate.sh --dry-run     — 预览迁移内容，不实际写入
#   ./auto_migrate.sh --truncate    — 迁移前清空 PG 表
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo " 链客宝AI SQLite → PostgreSQL 迁移"
echo " 时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo " 目录: $(pwd)"
echo "============================================================"
echo ""

# 检查 Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "[错误] 未找到 Python"
    exit 1
fi
PYTHON=$(command -v python3 || command -v python)
echo "[信息] 使用 Python: $($PYTHON --version)"

# 默认 PG 配置
export PG_HOST="${PG_HOST:-localhost}"
export PG_PORT="${PG_PORT:-5432}"
export PG_USER="${PG_USER:-chainke}"
export PG_PASSWORD="${PG_PASSWORD:-chainke_pg_2026}"
export PG_DATABASE="${PG_DATABASE:-chainke}"

echo "[信息] PostgreSQL 目标: ${PG_USER}@${PG_HOST}:${PG_PORT}/${PG_DATABASE}"
echo ""

# 步骤 1: 检查 PG 连接
echo "[步骤 1/4] 检查 PostgreSQL 连接..."
$PYTHON scripts/check_pg_connection.py
echo ""

# 步骤 2: Alembic 迁移
echo "[步骤 2/4] 执行 Alembic 迁移（建表）..."
export DB_TYPE=postgres
export USE_POSTGRES=1
if command -v alembic &>/dev/null; then
    alembic upgrade head || {
        echo "[警告] Alembic 迁移失败，尝试直接通过 SQLAlchemy 创建表..."
        $PYTHON -c "
import os
os.environ['DB_TYPE'] = 'postgres'
os.environ['USE_POSTGRES'] = '1'
from app.database import engine, Base
import app.models
Base.metadata.create_all(bind=engine)
print('表结构创建完成')
"
    }
else
    echo "[信息] alembic 未安装，使用 SQLAlchemy 直接建表..."
    $PYTHON -c "
import os
os.environ['DB_TYPE'] = 'postgres'
os.environ['USE_POSTGRES'] = '1'
from app.database import engine, Base
import app.models
Base.metadata.create_all(bind=engine)
print('表结构创建完成')
"
fi
echo ""

# 步骤 3: 数据迁移
echo "[步骤 3/4] 迁移数据从 SQLite 到 PostgreSQL..."
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}"
$PYTHON data_migration.py "$@"
echo ""

# 步骤 4: 验证
echo "[步骤 4/4] 验证数据一致性..."
$PYTHON data_migration.py --verify

echo ""
echo "============================================================"
echo " 迁移完成报告"
echo "============================================================"
echo " 源数据库: SQLite (backend/data/chainke.db)"
echo " 目标数据库: PostgreSQL (${PG_HOST}:${PG_PORT}/${PG_DATABASE})"
echo " 时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo " 后续切换:"
echo "  - 切换到 PG:  export USE_POSTGRES=1  (或 DB_TYPE=postgres)"
echo "  - 切换回 SQLite: export USE_POSTGRES=0 (或 unset USE_POSTGRES)"
echo "============================================================"
