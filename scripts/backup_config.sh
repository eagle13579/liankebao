#!/bin/bash
# =============================================================================
# 链客宝AI数据库备份策略 — 配置文件
# =============================================================================
# 此文件由 backup.sh 自动读取，也可被其他备份工具 source 引用。
# =============================================================================

# ── 项目路径 ────────────────────────────────────────────────────────────────
PROJECT_ROOT="/var/www/liankebao"
BACKEND_DIR="${PROJECT_ROOT}/backend"
SCRIPTS_DIR="${PROJECT_ROOT}/scripts"

# ── 数据库 ──────────────────────────────────────────────────────────────────
DB_NAME="digital_brochure.db"
DB_PATH="${BACKEND_DIR}/${DB_NAME}"

# ── 备份目录 ────────────────────────────────────────────────────────────────
BACKUP_BASE="/var/backups/liankebao"
BACKUP_DIR="${BACKUP_BASE}/brochure"

# ── 保留策略 ────────────────────────────────────────────────────────────────
RETENTION_DAYS=30

# ── 日志 ────────────────────────────────────────────────────────────────────
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/backup_digital_brochure.log"

# ── 工具命令 ────────────────────────────────────────────────────────────────
SQLITE3_BIN="/usr/bin/sqlite3"
MKDIR_BIN="/bin/mkdir"
RM_BIN="/bin/rm"
CP_BIN="/bin/cp"
DATE_BIN="/bin/date"
FIND_BIN="/usr/bin/find"
