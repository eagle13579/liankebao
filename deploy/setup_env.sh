#!/bin/bash
# =============================================================================
# 链客宝AI 环境变量配置向导
# 用途: 交互式引导用户输入各配置项并写入 /opt/liankebao/.env
# 用法: sudo bash deploy/setup_env.sh
# 说明: 直接回车使用默认值（[]中显示），留空敏感字段则跳过
# =============================================================================
set -e

# ---- 颜色定义 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ---- 目标路径 ----
ENV_FILE="/opt/liankebao/.env"

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
ok()    { echo -e "${GREEN}  ✓${NC} $1"; }
prompt(){ echo -en "${CYAN}==>${NC} $1"; }

# ---- 前置检查 ----
if [[ $EUID -ne 0 ]]; then
    warn "建议以 root 执行以确保写入权限: sudo bash $0"
fi

echo ""
echo "==============================================="
echo "   链客宝AI 环境变量配置向导"
echo "   $(date '+%Y-%m-%d %H:%M:%S')"
echo "   配置将写入: $ENV_FILE"
echo "==============================================="
echo ""

# 询问是否覆盖已有文件
if [[ -f "$ENV_FILE" ]]; then
    warn "$ENV_FILE 已存在"
    prompt "是否覆盖？(y/N): "
    read -r overwrite
    if [[ "$overwrite" != "y" && "$overwrite" != "Y" ]]; then
        info "保留现有配置，退出"
        exit 0
    fi
fi

# ---- 辅助函数 ----
read_val() {
    # $1: 提示文字  $2: 默认值
    local label="$1" default_val="$2" val
    if [[ -n "$default_val" ]]; then
        prompt "$label [$default_val]: "
    else
        prompt "$label: "
    fi
    read -r val
    if [[ -z "$val" && -n "$default_val" ]]; then
        echo "$default_val"
    else
        echo "$val"
    fi
}

read_masked() {
    # $1: 提示文字  $2: 默认值（敏感字段通常无默认值）
    local label="$1" default_val="$2" val
    if [[ -n "$default_val" ]]; then
        prompt "$label [****]: "
    else
        prompt "$label (输入将隐藏): "
    fi
    # 使用 stty 隐藏输入
    stty -echo 2>/dev/null
    read -r val
    stty echo 2>/dev/null
    echo ""
    if [[ -z "$val" && -n "$default_val" ]]; then
        echo "$default_val"
    else
        echo "$val"
    fi
}

write_env() {
    echo "# $1" >> "$ENV_FILE"
}

write_kv() {
    # $1: key  $2: value  $3: comment（可选）
    local key="$1" val="$2" comment="${3:-}"
    if [[ -n "$val" ]]; then
        if [[ -n "$comment" ]]; then
            echo "${key}=${val}    # ${comment}" >> "$ENV_FILE"
        else
            echo "${key}=${val}" >> "$ENV_FILE"
        fi
    fi
}

# ---- 开始生成 .env ----
cat > "$ENV_FILE" << 'HEADER'
# =============================================================================
# 链客宝AI 环境变量配置 — 由 setup_env.sh 自动生成
# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')
# 警告: 本文件包含敏感信息，切勿提交到 Git！
# =============================================================================

HEADER

# 使用临时文件替换上面的模板变量
cat > "$ENV_FILE" << HEADER
# =============================================================================
# 链客宝AI 环境变量配置 — 由 setup_env.sh 自动生成
# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')
# 警告: 本文件包含敏感信息，切勿提交到 Git！
# =============================================================================

HEADER

echo ""
echo "==============================================="
echo "  一、应用核心配置"
echo "==============================================="
echo ""

SECRET_KEY_VAL=$(read_masked "JWT 签名密钥（建议 64 位随机字符串）")
LOG_LEVEL_VAL=$(read_val "日志级别" "INFO")
LOG_FILE_VAL=$(read_val "日志文件路径（留空=stdout）")

echo "" >> "$ENV_FILE"
write_env "应用核心配置"
write_kv "SECRET_KEY"     "$SECRET_KEY_VAL"   "JWT 签名密钥"
write_kv "LOG_LEVEL"      "$LOG_LEVEL_VAL"     "日志级别"
write_kv "LOG_FILE"       "$LOG_FILE_VAL"      "日志文件路径"

echo ""
echo "==============================================="
echo "  二、数据库配置"
echo "==============================================="
echo ""

echo ""
info "数据库类型选择:"
echo "  1) SQLite（开发/轻量，默认）"
echo "  2) MySQL / MariaDB"
echo "  3) PostgreSQL"
prompt "请选择 (1/2/3) [1]: "
read -r db_choice
case "${db_choice:-1}" in
    2) DB_TYPE_VAL="mysql" ;;
    3) DB_TYPE_VAL="postgres" ;;
    *) DB_TYPE_VAL="sqlite" ;;
esac
ok "数据库类型: $DB_TYPE_VAL"

echo "" >> "$ENV_FILE"
write_env "数据库配置"
write_kv "DB_TYPE" "$DB_TYPE_VAL" "数据库类型"

if [[ "$DB_TYPE_VAL" == "mysql" ]]; then
    echo ""
    info "MySQL 配置（输入连接串或逐项填写）"
    DATABASE_URL_VAL=$(read_val "完整连接串 (DATABASE_URL)\n  示例: mysql+pymysql://user:pass@host:3306/db?charset=utf8mb4" "")
    write_kv "DATABASE_URL" "$DATABASE_URL_VAL" "MySQL 连接串"

elif [[ "$DB_TYPE_VAL" == "postgres" ]]; then
    echo ""
    info "PostgreSQL 配置"
    PG_URL_VAL=$(read_val "完整连接串 (PG_URL)\n  示例: postgresql+psycopg2://user:pass@host:5432/db" "")

    if [[ -z "$PG_URL_VAL" ]]; then
        PG_HOST_VAL=$(read_val "主机 (PG_HOST)" "localhost")
        PG_PORT_VAL=$(read_val "端口 (PG_PORT)" "5432")
        PG_USER_VAL=$(read_val "用户 (PG_USER)")
        PG_PASSWORD_VAL=$(read_masked "密码 (PG_PASSWORD)")
        PG_DATABASE_VAL=$(read_val "数据库名 (PG_DATABASE)")
        write_kv "PG_HOST"     "$PG_HOST_VAL"
        write_kv "PG_PORT"     "$PG_PORT_VAL"
        write_kv "PG_USER"     "$PG_USER_VAL"
        write_kv "PG_PASSWORD" "$PG_PASSWORD_VAL"
        write_kv "PG_DATABASE" "$PG_DATABASE_VAL"
    else
        write_kv "PG_URL" "$PG_URL_VAL" "PostgreSQL 完整连接串"
    fi

else  # sqlite
    echo ""
    info "SQLite 配置（使用默认值即可）"
    SQLITE_DIR_VAL=$(read_val "数据目录 (SQLITE_DIR)" "/opt/liankebao/backend/data")
    SQLITE_DB_NAME_VAL=$(read_val "数据库文件名 (SQLITE_DB_NAME)" "chainke.db")
    write_kv "SQLITE_DIR"    "$SQLITE_DIR_VAL"
    write_kv "SQLITE_DB_NAME" "$SQLITE_DB_NAME_VAL"

    # SQLite 模式自动生成 SQLite 路径作为 DATABASE_URL
    DATABASE_URL_VAL="sqlite:///${SQLITE_DIR_VAL}/${SQLITE_DB_NAME_VAL}"
    write_kv "DATABASE_URL" "$DATABASE_URL_VAL" "SQLite 连接串（自动生成）"
fi

echo ""
echo "==============================================="
echo "  三、微信支付配置"
echo "==============================================="
echo ""

info "微信支付需要以下配置，如暂不启用可直接回车跳过"

echo ""
echo "--- 3.1 基础配置（wechat_pay.py V2 原生） ---"
echo ""

WEIXIN_APPID_VAL=$(read_val "小程序 AppID (WEIXIN_APPID)")
MCH_ID_VAL=$(read_val "商户号 (MCH_ID)")
API_KEY_VAL=$(read_masked "V2 密钥 32位 (API_KEY)")
API_SECRET_VAL=$(read_masked "小程序 AppSecret (API_SECRET)")
APIv3_KEY_VAL=$(read_masked "V3 密钥 32位 (APIv3_KEY，可选)")
NOTIFY_URL_VAL=$(read_val "支付回调地址 (NOTIFY_URL)" "https://liankebao.top/api/payment/wxpay/callback")
REFUND_NOTIFY_URL_VAL=$(read_val "退款回调地址 (REFUND_NOTIFY_URL，默认同 NOTIFY_URL)")
SERVER_IP_VAL=$(read_val "服务器出口 IP (SERVER_IP)" "47.100.160.250")

echo "" >> "$ENV_FILE"
write_env "微信支付 — V2 原生对接 (wechat_pay.py)"
write_kv "WEIXIN_APPID"       "$WEIXIN_APPID_VAL"       "小程序 AppID"
write_kv "MCH_ID"             "$MCH_ID_VAL"             "商户号"
write_kv "API_KEY"            "$API_KEY_VAL"             "V2 签名密钥"
write_kv "API_SECRET"         "$API_SECRET_VAL"          "小程序 AppSecret"
write_kv "APIv3_KEY"          "$APIv3_KEY_VAL"           "V3 密钥（回调解密）"
write_kv "NOTIFY_URL"         "$NOTIFY_URL_VAL"          "支付回调地址"
write_kv "REFUND_NOTIFY_URL"  "${REFUND_NOTIFY_URL_VAL:-$NOTIFY_URL_VAL}" "退款回调地址"
write_kv "SERVER_IP"          "$SERVER_IP_VAL"           "服务器出口 IP"

echo ""
echo "--- 3.2 微信证书路径（退款/企业付款需要） ---"
echo ""

WECHAT_CERT_PATH_VAL=$(read_val "apiclient_cert.pem 路径 (WECHAT_CERT_PATH)")
WECHAT_KEY_PATH_VAL=$(read_val "apiclient_key.pem 路径 (WECHAT_KEY_PATH)")
WECHAT_ROOT_CA_PATH_VAL=$(read_val "rootca.pem 路径 (WECHAT_ROOT_CA_PATH，可选)")

write_kv "WECHAT_CERT_PATH"    "$WECHAT_CERT_PATH_VAL"   "商户证书 cert.pem"
write_kv "WECHAT_KEY_PATH"     "$WECHAT_KEY_PATH_VAL"    "商户证书 key.pem"
write_kv "WECHAT_ROOT_CA_PATH" "$WECHAT_ROOT_CA_PATH_VAL" "根证书（可选）"

echo ""
echo "--- 3.3 支付模式 & IJPay 层配置（可选覆盖） ---"
echo ""

PAYMENT_MODE_VAL=$(read_val "支付模式 (PAYMENT_MODE): real=真实支付, mock=模拟" "mock")

echo "" >> "$ENV_FILE"
write_env "支付模式 & IJPay 封装层"
write_kv "PAYMENT_MODE" "$PAYMENT_MODE_VAL" "支付模式: real/mock"

# 询问是否要覆盖 IJPay 层配置
prompt "是否配置 IJPay 层独立变量（覆盖 wechat_pay.py 的变量）?(y/N): "
read -r configure_ijpay
if [[ "$configure_ijpay" == "y" || "$configure_ijpay" == "Y" ]]; then
    WXPAY_APPID_VAL=$(read_val "WXPAY_APPID（若与 WEIXIN_APPID 不同）")
    WXPAY_MCH_ID_VAL=$(read_val "WXPAY_MCH_ID")
    WXPAY_API_KEY_VAL=$(read_masked "WXPAY_API_KEY")
    WXPAY_API_V3_KEY_VAL=$(read_masked "WXPAY_API_V3_KEY")
    WXPAY_NOTIFY_URL_VAL=$(read_val "WXPAY_NOTIFY_URL")
    WXPAY_CERT_PATH_VAL=$(read_val "WXPAY_CERT_PATH")
    WXPAY_ROOT_CA_PATH_VAL=$(read_val "WXPAY_ROOT_CA_PATH")

    write_kv "WXPAY_APPID"         "$WXPAY_APPID_VAL"
    write_kv "WXPAY_MCH_ID"        "$WXPAY_MCH_ID_VAL"
    write_kv "WXPAY_API_KEY"       "$WXPAY_API_KEY_VAL"
    write_kv "WXPAY_API_V3_KEY"    "$WXPAY_API_V3_KEY_VAL"
    write_kv "WXPAY_NOTIFY_URL"    "$WXPAY_NOTIFY_URL_VAL"
    write_kv "WXPAY_CERT_PATH"     "$WXPAY_CERT_PATH_VAL"
    write_kv "WXPAY_ROOT_CA_PATH"  "$WXPAY_ROOT_CA_PATH_VAL"
fi

echo ""
echo "==============================================="
echo "  四、支付宝配置（可选）"
echo "==============================================="
echo ""

prompt "是否配置支付宝支付？(y/N): "
read -r configure_alipay
if [[ "$configure_alipay" == "y" || "$configure_alipay" == "Y" ]]; then
    ALIPAY_APP_ID_VAL=$(read_val "支付宝 AppID (ALIPAY_APP_ID)")
    ALIPAY_PRIVATE_KEY_VAL=$(read_masked "应用私钥 (ALIPAY_PRIVATE_KEY)")
    ALIPAY_PUBLIC_KEY_VAL=$(read_val "支付宝公钥 (ALIPAY_PUBLIC_KEY)")
    ALIPAY_NOTIFY_URL_VAL=$(read_val "回调地址 (ALIPAY_NOTIFY_URL)" "https://liankebao.top/api/payment/alipay/callback")

    echo "" >> "$ENV_FILE"
    write_env "支付宝配置"
    write_kv "ALIPAY_APP_ID"      "$ALIPAY_APP_ID_VAL"
    write_kv "ALIPAY_PRIVATE_KEY" "$ALIPAY_PRIVATE_KEY_VAL"
    write_kv "ALIPAY_PUBLIC_KEY"  "$ALIPAY_PUBLIC_KEY_VAL"
    write_kv "ALIPAY_NOTIFY_URL"  "$ALIPAY_NOTIFY_URL_VAL"
fi

echo ""
echo "==============================================="
echo "  五、微信登录配置"
echo "==============================================="
echo ""

# 如果已填 API_SECRET，可复用
if [[ -n "$API_SECRET_VAL" ]]; then
    info "检测到已填写 API_SECRET（小程序 AppSecret），是否同步到 WECHAT_APP_SECRET？"
    prompt "同步到微信登录？(Y/n): "
    read -r sync_secret
    if [[ "$sync_secret" != "n" && "$sync_secret" != "N" ]]; then
        WECHAT_APP_SECRET_VAL="$API_SECRET_VAL"
        ok "已同步 API_SECRET → WECHAT_APP_SECRET"
    else
        WECHAT_APP_SECRET_VAL=$(read_masked "微信小程序 AppSecret (WECHAT_APP_SECRET)")
    fi
else
    WECHAT_APP_SECRET_VAL=$(read_masked "微信小程序 AppSecret (WECHAT_APP_SECRET)")
fi

echo "" >> "$ENV_FILE"
write_env "微信登录"
write_kv "WECHAT_APP_SECRET" "$WECHAT_APP_SECRET_VAL" "小程序 AppSecret（登录鉴权）"

echo ""
echo "==============================================="
echo "  六、搜索服务配置"
echo "==============================================="
echo ""

SEARCH_BACKEND_VAL=$(read_val "搜索后端 (SEARCH_BACKEND): auto/whoosh/fts5/elasticsearch" "auto")
USE_JIEBA_VAL=$(read_val "使用 jieba 分词 (USE_JIEBA): 1=启用 0=禁用" "1")

echo "" >> "$ENV_FILE"
write_env "搜索服务配置"
write_kv "SEARCH_BACKEND"  "$SEARCH_BACKEND_VAL"  "搜索后端引擎"
write_kv "USE_JIEBA"       "$USE_JIEBA_VAL"       "jieba 分词启用"

echo ""
echo "==============================================="
echo "  七、第三方 API（可选）"
echo "==============================================="
echo ""

DEEPSEEK_API_KEY_VAL=$(read_masked "DeepSeek API 密钥 (DEEPSEEK_API_KEY，可选)")

echo "" >> "$ENV_FILE"
write_env "第三方 API"
write_kv "DEEPSEEK_API_KEY" "$DEEPSEEK_API_KEY_VAL" "DeepSeek AI 密钥"

# ---- 完成 ----
echo ""
echo "==============================================="
ok "环境变量配置已生成!"
info "文件: $ENV_FILE"
line_count=$(wc -l < "$ENV_FILE")
info "共 $line_count 行配置"
echo ""
info "后续步骤:"
echo "  1. 检查 $ENV_FILE 确认所有值正确"
echo "  2. 执行: sudo bash deploy/deploy.sh"
echo "  3. 如需重新配置: sudo bash deploy/setup_env.sh"
echo ""
info "安全提醒:"
warn "  .env 文件包含敏感信息！"
warn "  请确保: chmod 600 $ENV_FILE"
echo "==============================================="
echo ""

# 设置安全权限
chmod 600 "$ENV_FILE" 2>/dev/null || true
ok "已设置文件权限: chmod 600"
echo ""
