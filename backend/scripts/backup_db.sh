#!/bin/bash
# ==============================================================================
# 链客宝 — PostgreSQL 数据库自动备份脚本
# LianKeBao — Automated PostgreSQL Backup Script
#
# 功能:
#   - pg_dump 压缩备份
#   - 保留最近 7 天每日备份
#   - 可选 S3 远程同步
#   - 详细日志记录
#   - 备份健康检查
#
# 用法:
#   ./scripts/backup_db.sh                        # 执行备份
#   ./scripts/backup_db.sh --s3                   # 备份 + S3 同步
#   ./scripts/backup_db.sh --list                 # 列出已有备份
#   ./scripts/backup_db.sh --clean                # 仅清理过期备份
#   ./scripts/backup_db.sh --dry-run              # 试运行
#
# 定时任务 (crontab -e):
#   0 3 * * * /root/liankebao/backend/scripts/backup_db.sh --s3
# ==============================================================================

set -euo pipefail

# ── 基础路径 ─────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── 配置 ─────────────────────────────────────────────────────────────────────
DB_NAME="${DB_NAME:-chainke}"
DB_USER="${DB_USER:-chainke}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_PASSWORD="${DB_PASSWORD:-}"

BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/data/backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
LOG_DIR="${LOG_DIR:-$PROJECT_DIR/logs}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/backup_db.log}"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
DATE_TAG="$(date '+%Y-%m-%d')"

# S3 配置 (可选)
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-chainke-backups/postgres}"
S3_REGION="${S3_REGION:-ap-northeast-1}"
S3_PROFILE="${S3_PROFILE:-default}"

# ── 颜色 ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ── 日志 ─────────────────────────────────────────────────────────────────────
log()     { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }
ok()      { echo -e "${GREEN}[✅]${NC} $*"; echo "[OK] $*" >> "$LOG_FILE"; }
warn()    { echo -e "${YELLOW}[⚠️]${NC} $*"; echo "[WARN] $*" >> "$LOG_FILE"; }
error()   { echo -e "${RED}[❌]${NC} $*"; echo "[ERROR] $*" >> "$LOG_FILE"; }

# ── 前置检查 ─────────────────────────────────────────────────────────────────
preflight() {
    local ok=true

    if ! command -v pg_dump &>/dev/null; then
        error "pg_dump 未安装 (not found)"
        ok=false
    fi

    if ! command -v psql &>/dev/null; then
        error "psql 未安装 (not found)"
        ok=false
    fi

    if ! command -v gzip &>/dev/null; then
        error "gzip 未安装 (not found)"
        ok=false
    fi

    # 测试数据库连接
    PGPASSWORD="$DB_PASSWORD" psql \
        -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -c "SELECT 1" &>/dev/null || {
        error "数据库连接失败: postgresql://$DB_USER@$DB_HOST:$DB_PORT/$DB_NAME"
        ok=false
    }

    $ok && return 0 || return 1
}

# ── 执行备份 ─────────────────────────────────────────────────────────────────
do_backup() {
    local backup_file="${BACKUP_DIR}/${DB_NAME}_${DATE_TAG}_${TIMESTAMP}.sql.gz"

    echo ""
    log "════════════════════════════════════════════"
    log "  链客宝数据库备份"
    log "  DB: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
    log "  目标: ${backup_file}"
    log "════════════════════════════════════════════"

    # 创建备份目录
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$LOG_DIR"

    # 获取数据库大小
    local db_size=""
    db_size=$(PGPASSWORD="$DB_PASSWORD" psql \
        -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -t -c "SELECT pg_size_pretty(pg_database_size('${DB_NAME}'));" 2>/dev/null | tr -d ' ')
    log "数据库大小: ${db_size:-unknown}"

    # 执行 pg_dump 压缩备份
    log "开始导出..."
    local start_time
    start_time=$(date +%s)

    PGPASSWORD="$DB_PASSWORD" pg_dump \
        -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        --format=custom \
        --compress=9 \
        --verbose \
        --file="${backup_file}" \
        2>> "$LOG_FILE"

    local exit_code=$?
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    if [ $exit_code -eq 0 ] && [ -f "$backup_file" ]; then
        local file_size
        file_size=$(du -h "$backup_file" | cut -f1)
        ok "备份完成! 大小: ${file_size}, 耗时: ${duration}s"
    else
        error "备份失败 (exit code: $exit_code)"
        rm -f "$backup_file"
        return 1
    fi

    # 生成校验和
    md5sum "$backup_file" > "${backup_file}.md5"
    ok "校验和: $(cat "${backup_file}.md5")"
}

# ── 清理过期备份 ──────────────────────────────────────────────────────────────
clean_old_backups() {
    echo ""
    log "清理 ${RETENTION_DAYS} 天前的旧备份..."
    local count=0

    while IFS= read -r -d '' f; do
        rm -f "$f" "${f}.md5" 2>/dev/null
        count=$((count + 1))
    done < <(find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -type f -mtime "+${RETENTION_DAYS}" -print0)

    if [ "$count" -gt 0 ]; then
        warn "删除了 ${count} 个过期备份"
    else
        ok "无过期备份需要清理"
    fi

    # 同时清理孤立的 .md5 文件
    find "$BACKUP_DIR" -name "*.md5" -type f | while read -r md5; do
        local base="${md5%.md5}"
        if [ ! -f "$base" ]; then
            rm -f "$md5"
            log "清理孤立的校验和文件: $md5"
        fi
    done
}

# ── 列出备份 ──────────────────────────────────────────────────────────────────
list_backups() {
    echo ""
    echo "════════════════════════════════════════════"
    echo "  链客宝数据库备份列表"
    echo "  目录: ${BACKUP_DIR}"
    echo "════════════════════════════════════════════"
    echo ""

    local total=0
    local total_size=0

    while IFS= read -r -d '' f; do
        local size
        size=$(du -h "$f" | cut -f1)
        local mtime
        mtime=$(stat -c '%y' "$f" 2>/dev/null | cut -d'.' -f1)
        local valid="✅"
        if [ -f "${f}.md5" ]; then
            if md5sum -c "${f}.md5" &>/dev/null; then
                valid="✅"
            else
                valid="❌"
            fi
        fi
        printf "  %s  %s  %s  %s\n" "$valid" "$mtime" "$(printf '%10s' "$size")" "$(basename "$f")"
        total=$((total + 1))
        # Get size in bytes for total calculation
        local bytes
        bytes=$(stat -c '%s' "$f" 2>/dev/null || echo 0)
        total_size=$((total_size + bytes))
    done < <(find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -type f -print0 | sort -z)

    echo ""
    echo "  总计: ${total} 个备份, $(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)"
}

# ── S3 同步 ───────────────────────────────────────────────────────────────────
sync_to_s3() {
    if [ -z "$S3_BUCKET" ]; then
        warn "S3_BUCKET 未配置，跳过 S3 同步"
        return 0
    fi

    if ! command -v aws &>/dev/null; then
        warn "AWS CLI 未安装，跳过 S3 同步"
        return 0
    fi

    echo ""
    log "同步备份到 S3: s3://${S3_BUCKET}/${S3_PREFIX}/"

    aws s3 sync "$BACKUP_DIR/" \
        "s3://${S3_BUCKET}/${S3_PREFIX}/" \
        --region "$S3_REGION" \
        --profile "$S3_PROFILE" \
        --storage-class STANDARD_IA \
        --no-progress \
        2>> "$LOG_FILE" || {
        error "S3 同步失败"
        return 1
    }

    ok "S3 同步完成"

    # 可选: 清理 S3 上的旧备份 (超过 30 天)
    log "清理 S3 上 30 天前的备份..."
    local cutoff
    cutoff=$(date -d "30 days ago" '+%Y-%m-%d')
    aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" \
        --region "$S3_REGION" \
        --profile "$S3_PROFILE" 2>/dev/null | while read -r line; do
        local s3_date
        s3_date=$(echo "$line" | awk '{print $1}')
        local filename
        filename=$(echo "$line" | awk '{print $4}')
        if [ -n "$s3_date" ] && [ -n "$filename" ] && [[ "$s3_date" < "$cutoff" ]]; then
            aws s3 rm "s3://${S3_BUCKET}/${S3_PREFIX}/${filename}" \
                --region "$S3_REGION" \
                --profile "$S3_PROFILE" 2>/dev/null || true
            log "  已删除 S3 旧备份: $filename"
        fi
    done
}

# ── 健康检查 ──────────────────────────────────────────────────────────────────
verify_backup() {
    echo ""
    log "最近一次备份完整性检查..."

    local latest
    latest=$(find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -type f -print0 | sort -z | tail -1 | tr -d '\0')
    if [ -z "$latest" ]; then
        warn "无备份文件可检查"
        return 0
    fi

    log "检查: $(basename "$latest")"

    # 检查文件完整性
    gunzip -t "$latest" 2>/dev/null && ok "压缩文件完整性通过" || {
        error "压缩文件损坏: $latest"
        return 1
    }

    # 检查校验和
    if [ -f "${latest}.md5" ]; then
        if md5sum -c "${latest}.md5" &>/dev/null; then
            ok "MD5 校验通过"
        else
            error "MD5 校验失败 — 文件可能已损坏"
            return 1
        fi
    fi

    # 使用 pg_restore 验证内容 (只列出目录，不恢复)
    if command -v pg_restore &>/dev/null; then
        if pg_restore --list "$latest" &>/dev/null; then
            ok "备份内容有效 (pg_restore --list 通过)"
        else
            warn "备份内容验证失败 (pg_restore --list 失败)"
        fi
    fi
}

# ── 主流程 ────────────────────────────────────────────────────────────────────
main() {
    local DO_S3=false
    local DO_LIST=false
    local DO_CLEAN=false
    local DRY_RUN=false

    for arg in "$@"; do
        case "$arg" in
            --s3)      DO_S3=true ;;
            --list)    DO_LIST=true ;;
            --clean)   DO_CLEAN=true ;;
            --dry-run) DRY_RUN=true ;;
            --help|-h)
                echo "用法: $0 [--s3] [--list] [--clean] [--dry-run] [--help]"
                echo ""
                echo "  --s3        备份并同步到 S3 远程存储"
                echo "  --list      列出已有备份"
                echo "  --clean     仅清理过期备份"
                echo "  --dry-run   试运行（不实际执行）"
                echo "  --help      显示此帮助"
                exit 0
                ;;
        esac
    done

    # 创建日志目录
    mkdir -p "$LOG_DIR"

    if [ "$DO_LIST" = true ]; then
        list_backups
        exit 0
    fi

    if [ "$DO_CLEAN" = true ]; then
        preflight || exit 1
        clean_old_backups
        exit 0
    fi

    # 前置检查
    preflight || exit 1

    if [ "$DRY_RUN" = true ]; then
        echo ""
        log "[DRY-RUN] 将执行以下操作:"
        log "  备份:  ${DB_NAME}@${DB_HOST}:${DB_PORT} → ${BACKUP_DIR}/"
        log "  保留:  ${RETENTION_DAYS} 天"
        if [ "$DO_S3" = true ]; then
            log "  S3:    s3://${S3_BUCKET}/${S3_PREFIX}/"
        fi
        exit 0
    fi

    # 执行备份
    do_backup || exit 1

    # 清理过期备份
    clean_old_backups

    # 验证
    verify_backup || true

    # S3 同步
    if [ "$DO_S3" = true ]; then
        sync_to_s3 || true
    fi

    # 最终报告
    echo ""
    log "════════════════════════════════════════════"
    log "  备份完成报告"
    log "  数据库: ${DB_NAME}"
    log "  日期:   ${DATE_TAG}"
    log "  目录:   ${BACKUP_DIR}"
    log "  保留:   ${RETENTION_DAYS} 天"
    [ "$DO_S3" = true ] && log "  S3:     s3://${S3_BUCKET}/${S3_PREFIX}/"
    log "  日志:   ${LOG_FILE}"
    log "════════════════════════════════════════════"
}

main "$@"
