<#
.SYNOPSIS
    链客宝 — PostgreSQL 数据库备份脚本 (Windows)
    LianKeBao — PostgreSQL Backup Script for Windows

.DESCRIPTION
    本地开发环境 PostgreSQL 备份
    - pg_dump 压缩备份
    - 保留最近 7 天每日备份
    - 详细日志记录
    - 可选 S3 同步

.PARAMETER S3
    备份后同步到 S3

.PARAMETER List
    列出已有备份

.PARAMETER Clean
    仅清理过期备份

.EXAMPLE
    .\scripts\backup_db.ps1
    .\scripts\backup_db.ps1 -S3
    .\scripts\backup_db.ps1 -List
#>

param(
    [switch]$S3,
    [switch]$List,
    [switch]$Clean,
    [switch]$DryRun
)

# ── 配置 ───────────────────────────────────────────────────────────────────
$DB_NAME     = if ($env:DB_NAME) { $env:DB_NAME } else { "chainke" }
$DB_USER     = if ($env:DB_USER) { $env:DB_USER } else { "chainke" }
$DB_HOST     = if ($env:DB_HOST) { $env:DB_HOST } else { "localhost" }
$DB_PORT     = if ($env:DB_PORT) { $env:DB_PORT } else { "5432" }
$DB_PASSWORD = if ($env:PGPASSWORD) { $env:PGPASSWORD } else { "" }

$PROJECT_DIR  = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$BACKUP_DIR   = if ($env:BACKUP_DIR) { $env:BACKUP_DIR } else { Join-Path $PROJECT_DIR "data\backups\postgres" }
$LOG_DIR      = if ($env:LOG_DIR) { $env:LOG_DIR } else { Join-Path $PROJECT_DIR "logs" }
$LOG_FILE     = Join-Path $LOG_DIR "backup_db.log"
$RETENTION_DAYS = if ($env:RETENTION_DAYS) { [int]$env:RETENTION_DAYS } else { 7 }
$TIMESTAMP    = Get-Date -Format "yyyyMMdd_HHmmss"
$DATE_TAG     = Get-Date -Format "yyyy-MM-dd"

$S3_BUCKET    = $env:S3_BUCKET
$S3_PREFIX    = if ($env:S3_PREFIX) { $env:S3_PREFIX } else { "chainke-backups/postgres" }
$S3_REGION    = if ($env:S3_REGION) { $env:S3_REGION } else { "ap-northeast-1" }

# ── 日志函数 ───────────────────────────────────────────────────────────────
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logLine = "[${timestamp}] [${Level}] ${Message}"
    Write-Host $logLine
    Add-Content -Path $LOG_FILE -Value $logLine
}

function Write-OK {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor Green
    Write-Log -Message $Message -Level "OK"
}

function Write-Warn {
    param([string]$Message)
    Write-Host "⚠️  $Message" -ForegroundColor Yellow
    Write-Log -Message $Message -Level "WARN"
}

function Write-Error {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor Red
    Write-Log -Message $Message -Level "ERROR"
}

# ── 前置检查 ───────────────────────────────────────────────────────────────
function Test-Prerequisites {
    $ok = $true

    if (-not (Get-Command "pg_dump" -ErrorAction SilentlyContinue)) {
        Write-Error "pg_dump 未安装 (不在 PATH 中)"
        Write-Host "  提示: 请确保 PostgreSQL bin 目录在 PATH 中" -ForegroundColor Cyan
        $ok = $false
    }

    if (-not (Get-Command "psql" -ErrorAction SilentlyContinue)) {
        Write-Error "psql 未安装"
        $ok = $false
    }

    # 测试数据库连接
    $env:PGPASSWORD = $DB_PASSWORD
    $result = psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "SELECT 1" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "数据库连接失败: ${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
        Write-Host "  $result" -ForegroundColor Gray
        $ok = $false
    }

    return $ok
}

# ── 执行备份 ───────────────────────────────────────────────────────────────
function Invoke-Backup {
    $backupFile = Join-Path $BACKUP_DIR "${DB_NAME}_${DATE_TAG}_${TIMESTAMP}.sql.gz"

    Write-Host ""
    Write-Log "════════════════════════════════════════════"
    Write-Log "  链客宝数据库备份 (Windows)"
    Write-Log "  DB: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
    Write-Log "  目标: ${backupFile}"
    Write-Log "════════════════════════════════════════════"

    # 创建目录
    New-Item -ItemType Directory -Force -Path $BACKUP_DIR | Out-Null
    New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null

    # 获取数据库大小
    $env:PGPASSWORD = $DB_PASSWORD
    $dbSize = psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME `
        -t -c "SELECT pg_size_pretty(pg_database_size('${DB_NAME}'));" 2>$null
    Write-Log "数据库大小: $($dbSize.Trim())"

    # 执行 pg_dump
    Write-Log "开始导出..."
    $startTime = Get-Date

    $env:PGPASSWORD = $DB_PASSWORD
    $dumpResult = pg_dump `
        -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME `
        --format=custom --compress=9 --verbose `
        --file="$backupFile" 2>&1

    if ($LASTEXITCODE -eq 0 -and (Test-Path $backupFile)) {
        $fileSize = (Get-Item $backupFile).Length
        $duration = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)
        $sizeStr = if ($fileSize -gt 1GB) {
            "{0:N2} GB" -f ($fileSize / 1GB)
        } elseif ($fileSize -gt 1MB) {
            "{0:N2} MB" -f ($fileSize / 1MB)
        } else {
            "{0:N2} KB" -f ($fileSize / 1KB)
        }
        Write-OK "备份完成! 大小: ${sizeStr}, 耗时: ${duration}s"
    } else {
        Write-Error "备份失败"
        Write-Host $dumpResult -ForegroundColor Red
        if (Test-Path $backupFile) { Remove-Item $backupFile -Force }
        return $false
    }

    return $true
}

# ── 清理过期备份 ─────────────────────────────────────────────────────────────
function Clear-OldBackups {
    Write-Log "清理 ${RETENTION_DAYS} 天前的旧备份..."
    $cutoff = (Get-Date).AddDays(-$RETENTION_DAYS)
    $count = 0

    Get-ChildItem -Path $BACKUP_DIR -Filter "${DB_NAME}_*.sql.gz" | Where-Object {
        $_.LastWriteTime -lt $cutoff
    } | ForEach-Object {
        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
        # 也删除对应的 .md5
        $md5File = $_.FullName + ".md5"
        if (Test-Path $md5File) { Remove-Item $md5File -Force -ErrorAction SilentlyContinue }
        $count++
    }

    if ($count -gt 0) {
        Write-Warn "删除了 ${count} 个过期备份"
    } else {
        Write-OK "无过期备份需要清理"
    }
}

# ── 列出备份 ─────────────────────────────────────────────────────────────────
function Get-BackupList {
    Write-Host ""
    Write-Host "════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  链客宝数据库备份列表" -ForegroundColor Cyan
    Write-Host "  目录: ${BACKUP_DIR}" -ForegroundColor Cyan
    Write-Host "════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host ""

    $files = Get-ChildItem -Path $BACKUP_DIR -Filter "${DB_NAME}_*.sql.gz" | Sort-Object Name -Descending

    if ($files.Count -eq 0) {
        Write-Warn "暂无备份文件"
        return
    }

    $totalSize = 0
    foreach ($f in $files) {
        $sizeStr = if ($f.Length -gt 1GB) {
            "{0:N2} GB" -f ($f.Length / 1GB)
        } elseif ($f.Length -gt 1MB) {
            "{0:N2} MB" -f ($f.Length / 1MB)
        } else {
            "{0:N2} KB" -f ($f.Length / 1KB)
        }
        $valid = "✅"
        $md5File = $f.FullName + ".md5"
        Write-Host "  ${valid}  $($f.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))  $($sizeStr.PadLeft(8))  $($f.Name)"
        $totalSize += $f.Length
    }

    $totalSizeStr = if ($totalSize -gt 1GB) {
        "{0:N2} GB" -f ($totalSize / 1GB)
    } elseif ($totalSize -gt 1MB) {
        "{0:N2} MB" -f ($totalSize / 1MB)
    } else {
        "{0:N2} KB" -f ($totalSize / 1KB)
    }
    Write-Host ""
    Write-Host "  总计: $($files.Count) 个备份, ${totalSizeStr}" -ForegroundColor Cyan
}

# ── S3 同步 ──────────────────────────────────────────────────────────────────
function Sync-ToS3 {
    if (-not $S3_BUCKET) {
        Write-Warn "S3_BUCKET 未配置，跳过 S3 同步"
        return
    }

    if (-not (Get-Command "aws" -ErrorAction SilentlyContinue)) {
        Write-Warn "AWS CLI 未安装，跳过 S3 同步"
        return
    }

    Write-Log "同步备份到 S3: s3://${S3_BUCKET}/${S3_PREFIX}/"

    $s3Args = @(
        "s3", "sync", $BACKUP_DIR, "s3://${S3_BUCKET}/${S3_PREFIX}/",
        "--region", $S3_REGION,
        "--storage-class", "STANDARD_IA",
        "--no-progress"
    )

    $result = & aws $s3Args 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "S3 同步完成"
    } else {
        Write-Error "S3 同步失败: $result"
    }
}

# ── 主流程 ──────────────────────────────────────────────────────────────────
function Main {
    # 创建日志目录
    New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null

    if ($List) {
        Get-BackupList
        return
    }

    if ($Clean) {
        if (-not (Test-Prerequisites)) { return }
        Clear-OldBackups
        return
    }

    # 前置检查
    if (-not (Test-Prerequisites)) {
        Write-Host "前置检查未通过，请修复后重试" -ForegroundColor Red
        return
    }

    if ($DryRun) {
        Write-Host ""
        Write-Log "[DRY-RUN] 将执行以下操作:"
        Write-Log "  备份:  ${DB_NAME}@${DB_HOST}:${DB_PORT} → ${BACKUP_DIR}\"
        Write-Log "  保留:  ${RETENTION_DAYS} 天"
        if ($S3) { Write-Log "  S3:    s3://${S3_BUCKET}/${S3_PREFIX}/" }
        return
    }

    # 执行备份
    $backupOk = Invoke-Backup
    if (-not $backupOk) { return }

    # 清理过期备份
    Clear-OldBackups

    # S3 同步
    if ($S3) { Sync-ToS3 }

    # 最终报告
    Write-Host ""
    Write-Log "════════════════════════════════════════════"
    Write-Log "  备份完成报告"
    Write-Log "  数据库: ${DB_NAME}"
    Write-Log "  日期:   ${DATE_TAG}"
    Write-Log "  目录:   ${BACKUP_DIR}"
    Write-Log "  保留:   ${RETENTION_DAYS} 天"
    if ($S3) { Write-Log "  S3:     s3://${S3_BUCKET}/${S3_PREFIX}/" }
    Write-Log "  日志:   ${LOG_FILE}"
    Write-Log "════════════════════════════════════════════"
}

Main
