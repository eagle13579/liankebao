#!/bin/bash
set -euo pipefail

# ------------------------------------------------------------------------
# LianKeBao - digital_brochure.db (SQLite) auto-backup
# Location: /var/backups/liankebao/brochure/YYYY-MM-DD/
# Retention: 30 days + integrity check
# ------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/backup_config.sh" ]; then
    . "${SCRIPT_DIR}/backup_config.sh"
fi

PROJECT_ROOT=${PROJECT_ROOT:-/var/www/liankebao}
BACKEND_DIR=${BACKEND_DIR:-${PROJECT_ROOT}/backend}
DB_NAME=${DB_NAME:-digital_brochure.db}
DB_PATH=${DB_PATH:-${BACKEND_DIR}/${DB_NAME}}
BACKUP_BASE=${BACKUP_BASE:-/var/backups/liankebao}
BACKUP_DIR=${BACKUP_DIR:-${BACKUP_BASE}/brochure}
RETENTION_DAYS=${RETENTION_DAYS:-30}
LOG_DIR=${LOG_DIR:-${PROJECT_ROOT}/logs}
LOG_FILE=${LOG_FILE:-${LOG_DIR}/backup_digital_brochure.log}

log() {
    local level="$1" msg="$2"
    local ts=$(date +"%Y-%m-%d %H:%M:%S")
    mkdir -p "$(dirname "${LOG_FILE}")" 2>/dev/null || true
    echo "[${ts}] [${level}] ${msg}" | tee -a "${LOG_FILE}"
}

if [ ! -f "${DB_PATH}" ]; then
    log "ERROR" "DB not found: ${DB_PATH}"
    exit 1
fi

TODAY=$(date +"%Y-%m-%d")
TODAY_DIR="${BACKUP_DIR}/${TODAY}"
mkdir -p "${TODAY_DIR}"
log "INFO" "Backup dir: ${TODAY_DIR}"

BACKUP_FILE="${TODAY_DIR}/${DB_NAME}"
cp -a "${DB_PATH}" "${BACKUP_FILE}"
log "OK" "Copied to ${BACKUP_FILE}"

IR=$(sqlite3 "${BACKUP_FILE}" "PRAGDB integrity_check;" 2>&1)
if [ "${IR}" = "ok" ]; then
    log "OK" "Integrity: PASS"
else
    log "ERROR" "Integrity: FAIL! ${IR}"
    mv "${BACKUP_FILE}" "${BACKUP_FILE}.corrupted"
    log "WARN" "Backup marked as corrupted"
    exit 2
fi

PURGED=0
cutoff=$(date -d "${RETENTION_DAYS} days ago" +%s)
for dir in $(find "${BACKUP_DIR}" -maxdepth 2 -type d -name "????-??-??" 2>/dev/null); do
    d=$(basename "${dir}")
    e=$(date -d "${d}" +%s 2>/dev/null || echo 0)
    if [ "${e}" -gt 0 ] && [ "${e}" -lt "${cutoff}" ]; then
        rm -rf "${dir}"
        log "DELETE" "Removed expired backup: ${dir}"
        PURGED=$((PURGED + 1))
    fi
done
log "INFO" "Purged ${PURGED} old backup(s)"
log "INFO" "Backup complete"
exit 0