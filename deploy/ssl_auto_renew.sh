#!/bin/bash
# ============================================================
# 链客宝AI SSL 证书自动续签脚本
# 服务器: 阿里云 ECS (47.100.160.250)
# 域名: liankebao.top / www.liankebao.top
# 支持: certbot 和 acme.sh 两种客户端
# ============================================================
set -e

# ---- 配置 ----
DOMAINS="liankebao.top,www.liankebao.top"
NGINX_CONF="/etc/nginx/nginx.conf"
CERT_DIR_LETSENCRYPT="/etc/letsencrypt/live/liankebao.top"
CERT_DIR_ACME="/root/.acme.sh/liankebao.top_ecc"
LOG_FILE="/var/log/ssl_auto_renew.log"
ACME_HOME="/root/.acme.sh"
ADMIN_EMAIL="admin@liankebao.top"

# ---- 颜色 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ---- 日志 ----
log()   { echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"; echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; echo "[WARN] $(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"; }

# ---- 前置检查 ----
pre_check() {
    # 确保日志目录存在
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true

    # 检查是否以 root 运行（certbot/acme.sh 需要 root 权限）
    if [[ $EUID -ne 0 ]]; then
        error "此脚本需要 root 权限运行！请使用 sudo 执行。"
        exit 1
    fi

    # 检查 nginx 是否安装
    if ! command -v nginx &>/dev/null; then
        error "Nginx 未安装，请先安装 nginx。"
        exit 1
    fi

    log "前置检查通过"
}

# ---- 检测 SSL 客户端 ----
detect_client() {
    if command -v certbot &>/dev/null; then
        CLIENT="certbot"
        log "检测到 SSL 客户端: certbot"
        return 0
    elif [[ -f "$ACME_HOME/acme.sh" ]]; then
        CLIENT="acme.sh"
        log "检测到 SSL 客户端: acme.sh"
        return 0
    else
        CLIENT=""
        warn "未检测到 certbot 或 acme.sh"
        warn "请先安装 SSL 证书管理工具："
        warn "  certbot: sudo apt install -y certbot python3-certbot-nginx"
        warn "  acme.sh:  curl https://get.acme.sh | sh"
        return 1
    fi
}

# ---- 检查当前证书到期时间 ----
check_cert_expiry() {
    local cert_file=""
    local days_left=0

    # 尝试多个可能的证书路径
    if [[ -f "$CERT_DIR_LETSENCRYPT/fullchain.pem" ]]; then
        cert_file="$CERT_DIR_LETSENCRYPT/fullchain.pem"
    elif [[ -f "$CERT_DIR_ACME/fullchain.cer" ]]; then
        cert_file="$CERT_DIR_ACME/fullchain.cer"
    else
        warn "未找到 SSL 证书文件"
        # 尝试自动发现
        cert_file=$(find /etc/letsencrypt/live -name "fullchain.pem" 2>/dev/null | head -1)
        if [[ -z "$cert_file" ]]; then
            cert_file=$(find "$ACME_HOME" -name "fullchain.cer" 2>/dev/null | head -1)
        fi
    fi

    if [[ -n "$cert_file" ]] && [[ -f "$cert_file" ]]; then
        local end_date=$(openssl x509 -enddate -noout -in "$cert_file" 2>/dev/null | cut -d= -f2)
        local end_epoch=$(date -d "$end_date" +%s 2>/dev/null)
        local now_epoch=$(date +%s)
        days_left=$(( (end_epoch - now_epoch) / 86400 ))
        log "当前证书到期: $end_date（剩余 ${days_left} 天）"
    else
        days_left=0
        warn "无法获取证书到期时间"
    fi

    echo "$days_left"
}

# ---- 使用 certbot 续签 ----
renew_certbot() {
    log "使用 certbot 续签证书..."

    # certbot renew 会自动检测所有需要续签的证书
    if certbot renew --non-interactive --quiet; then
        log "certbot 续签成功"
        return 0
    else
        local exit_code=$?
        # certbot 可能因为"尚未到期"而返回非 0，需要区分
        if certbot renew --dry-run --non-interactive --quiet 2>&1 | grep -q "success"; then
            log "证书尚未到期，无需续签（dry-run 成功）"
            return 0
        fi
        error "certbot 续签失败（exit code: $exit_code）"
        error "请手动运行: sudo certbot renew --verbose"
        return 1
    fi
}

# ---- 使用 acme.sh 续签 ----
renew_acme_sh() {
    log "使用 acme.sh 续签证书..."

    if [[ ! -f "$ACME_HOME/acme.sh" ]]; then
        error "acme.sh 未安装于 $ACME_HOME"
        return 1
    fi

    # 立即续签
    if bash "$ACME_HOME/acme.sh" --renew -d "liankebao.top" --force 2>&1 | tail -5; then
        log "acme.sh 续签成功"
        return 0
    else
        error "acme.sh 续签失败"
        error "请手动运行: bash $ACME_HOME/acme.sh --renew -d liankebao.top"
        return 1
    fi
}

# ---- 部署证书到 nginx ----
deploy_to_nginx() {
    log "部署证书到 nginx..."

    if [[ "$CLIENT" == "certbot" ]]; then
        # certbot --nginx 插件会自动处理，但为了保险我们手动重载
        :
    elif [[ "$CLIENT" == "acme.sh" ]]; then
        # acme.sh 部署到 nginx
        bash "$ACME_HOME/acme.sh" --installcert -d "liankebao.top" \
            --key-file /etc/nginx/ssl/liankebao.top.key \
            --fullchain-file /etc/nginx/ssl/liankebao.top.crt \
            --reloadcmd "nginx -s reload" || true
    fi

    log "证书部署完成"
}

# ---- 重载 nginx ----
reload_nginx() {
    log "验证并重载 nginx..."

    if nginx -t; then
        if nginx -s reload; then
            log "✓ Nginx 重载成功"
            return 0
        else
            error "Nginx 重载失败，请手动执行: nginx -s reload"
            return 1
        fi
    else
        error "Nginx 配置检查失败，请手动修复: nginx -t"
        return 1
    fi
}

# ---- 发送续签通知 ----
send_notification() {
    local status="$1"
    local message="$2"
    local endpoint="${WEBHOOK_URL:-}"

    if [[ -n "$endpoint" ]]; then
        curl -s -X POST "$endpoint" \
            -H "Content-Type: application/json" \
            -d "{\"project\":\"链客宝AI\",\"ssl_renewal\":\"$status\",\"message\":\"$message\"}" >/dev/null 2>&1 || true
        log "通知已发送到 webhook"
    fi

    # 如果安装了 mail/mailx，可以发送邮件通知
    if command -v mail &>/dev/null && [[ -n "$ADMIN_EMAIL" ]]; then
        echo "链客宝AI SSL 证书续签状态: $status

$message

服务器: 47.100.160.250
域名: $DOMAINS
时间: $(date)" | mail -s "[链客宝AI] SSL 证书续签: $status" "$ADMIN_EMAIL" 2>/dev/null || true
        log "邮件通知已发送到 $ADMIN_EMAIL"
    fi
}

# ---- 主流程 ----
main() {
    echo ""
    echo "======================================="
    echo "   链客宝AI SSL 证书自动续签"
    echo "   $(date '+%Y-%m-%d %H:%M:%S')"
    echo "======================================="
    echo ""

    pre_check

    # 检测证书客户端
    if ! detect_client; then
        send_notification "ERROR" "未检测到 SSL 客户端，请手动安装 certbot 或 acme.sh"
        exit 1
    fi

    # 续签前检查证书到期天数
    local days_left
    days_left=$(check_cert_expiry)

    # 如果证书剩余超过 30 天，且不是强制续签模式，则跳过
    if [[ "$1" != "--force" ]] && [[ "$days_left" -gt 30 ]]; then
        log "证书剩余 ${days_left} 天（>30 天），无需续签。"
        log "使用 --force 参数可强制续签。"
        send_notification "SKIPPED" "证书剩余 ${days_left} 天，无需续签"
        exit 0
    fi

    # 执行续签
    local renew_result=1
    if [[ "$CLIENT" == "certbot" ]]; then
        renew_certbot && renew_result=0 || renew_result=1
    elif [[ "$CLIENT" == "acme.sh" ]]; then
        renew_acme_sh && renew_result=0 || renew_result=1
    fi

    if [[ "$renew_result" -eq 0 ]]; then
        # 续签成功，重载 nginx
        reload_nginx
        log "✓ SSL 证书续签流程完成！"
        send_notification "SUCCESS" "SSL 证书已成功续签，nginx 已重载"
    else
        error "✗ SSL 证书续签失败，请手动排查"
        send_notification "FAILED" "SSL 证书续签失败，请手动运行: certbot renew --verbose"
        exit 1
    fi
}

main "$@"
