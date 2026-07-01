#!/usr/bin/env python3
"""
微信支付配置检查脚本
====================
检查微信支付 V3 环境变量配置是否完整。

用法:
    python check_wechat_config.py
    python check_wechat_config.py --verbose   # 显示所有配置值(不暴露密钥)
    python check_wechat_config.py --fix-env    # 尝试从 .env 文件加载

退出码:
    0 — 配置就绪
    1 — 配置不完整 (输出缺失项)
    2 — 关键文件缺失 (证书文件不存在)
"""

import argparse
import os
import sys

# 添加项目根目录到 PATH
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_PROJECT_ROOT, "backend")
if os.path.isdir(_BACKEND_DIR):
    sys.path.insert(0, _BACKEND_DIR)

# 尝试从 .env 加载
_DOTENV_LOADED = False
try:
    from dotenv import load_dotenv

    env_paths = [
        os.path.join(_PROJECT_ROOT, ".env"),
        os.path.join(_BACKEND_DIR, ".env"),
    ]
    for p in env_paths:
        if os.path.isfile(p):
            load_dotenv(p, override=False)
            _DOTENV_LOADED = True
            print(f"  ✓ 已加载 .env 文件: {p}")
            break
except ImportError:
    pass

# ============================================================
# 配置项定义
# ============================================================

REQUIRED_CONFIGS = {
    "WECHAT_APPID": {
        "label": "公众号/小程序 AppID",
        "doc": "在微信公众平台/小程序后台 → 开发 → 开发设置 中获取",
        "placeholder": "wx1234567890abcdef",
    },
    "WECHAT_MCHID": {
        "label": "微信商户号 ID",
        "doc": "微信支付商户平台 → 账户中心 → 商户信息 中获取",
        "placeholder": "1230000109",
    },
    "WECHAT_API_V3_KEY": {
        "label": "APIv3 密钥",
        "doc": "微信支付商户平台 → 账户中心 → API安全 → 设置APIv3密钥",
        "placeholder": "32位十六进制字符串",
    },
    "WECHAT_CERT_PATH": {
        "label": "商户私钥证书路径",
        "doc": "apiclient_key.pem 文件的绝对路径 (微信支付商户平台下载)",
        "placeholder": "/path/to/apiclient_key.pem",
    },
    "WECHAT_NOTIFY_URL": {
        "label": "支付回调通知 URL",
        "doc": "公网可达的 HTTPS 地址, 如 https://yourdomain.com/api/payment/wechat/notify",
        "placeholder": "https://yourdomain.com/api/payment/wechat/notify",
    },
}

OPTIONAL_CONFIGS = {
    "WECHAT_API_KEY": {
        "label": "APIv2 密钥 (V2 兼容)",
        "doc": "微信支付商户平台 → 账户中心 → API安全 → 设置API密钥 (如仅用V3可不填)",
    },
    "WECHAT_CERT_SERIAL": {
        "label": "商户证书序列号",
        "doc": "商户证书序列号 (如未设置, SDK 会自动从证书文件读取)",
    },
    "WECHAT_REFUND_NOTIFY_URL": {
        "label": "退款回调通知 URL",
        "doc": "可选的退款回调地址, 不填则使用 NOTIFY_URL",
    },
    "WECHAT_PLATFORM_CERT_DIR": {
        "label": "平台证书缓存目录",
        "doc": "微信平台公钥证书缓存目录, 默认 /tmp/wechat_certs",
    },
}

# ============================================================
# 检查逻辑
# ============================================================


def check_cert_serial(cert_path: str) -> str:
    """从证书文件读取序列号"""
    if not os.path.isfile(cert_path):
        return ""
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend

        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())
        serial = format(cert.serial_number, "X")
        return serial
    except Exception as e:
        print(f"  ⚠  读取证书序列号失败: {e}")
        return ""


def run_check(verbose: bool = False) -> int:
    """执行配置检查, 返回退出码"""
    print("=" * 60)
    print("  链客宝 — 微信支付配置检查")
    print("=" * 60)
    print()

    # ---- 检查必需配置 ----
    missing = []
    file_issues = []
    cert_path_value = ""

    print("【必需配置项】")
    print("-" * 40)

    for key, info in REQUIRED_CONFIGS.items():
        value = os.environ.get(key, "")
        if not value:
            missing.append(key)
            print(f"  ✗ {info['label']} ({key})")
            print(f"    说明: {info['doc']}")
            if verbose:
                print(f"    示例: {info['placeholder']}")
            print()
        else:
            masked = value[:6] + "****" if key in ("WECHAT_API_V3_KEY",) else value
            print(f"  ✓ {info['label']}: {masked}")
            if key == "WECHAT_CERT_PATH":
                cert_path_value = value
            if verbose:
                print(f"    说明: {info['doc']}")
            print()

    # ---- 检查可选配置 ----
    print("【可选配置项】")
    print("-" * 40)
    for key, info in OPTIONAL_CONFIGS.items():
        value = os.environ.get(key, "")
        if value:
            masked = value[:6] + "****" if key in ("WECHAT_API_KEY",) else value
            print(f"  ✓ {info['label']} ({key}): {masked}")
        else:
            print(f"  - {info['label']} ({key}): 未设置 (可选)")
        if verbose:
            print(f"    说明: {info['doc']}")
        print()

    # ---- 证书文件检查 ----
    if cert_path_value:
        print("【证书检查】")
        print("-" * 40)
        if os.path.isfile(cert_path_value):
            print(f"  ✓ 商户私钥证书存在: {cert_path_value}")
        else:
            print(f"  ✗ 商户私钥证书不存在: {cert_path_value}")
            file_issues.append(f"证书文件未找到: {cert_path_value}")

        # 尝试读取序列号
        serial_env = os.environ.get("WECHAT_CERT_SERIAL", "")
        if serial_env:
            print(f"  ✓ 证书序列号 (环境变量): {serial_env}")
        elif cert_path_value and os.path.isfile(cert_path_value):
            serial = check_cert_serial(cert_path_value)
            if serial:
                print(f"  ℹ  证书序列号 (从文件读取): {serial}")
                print(f"     建议设置 WECHAT_CERT_SERIAL={serial} 到 .env")
            else:
                print("  ⚠  无法读取证书序列号")
        print()

    # ---- 回调 URL 可达性 ----
    notify_url = os.environ.get("WECHAT_NOTIFY_URL", "")
    if notify_url:
        print("【回调 URL 检查】")
        print("-" * 40)
        if notify_url.startswith("https://"):
            print(f"  ✓ 回调 URL 使用 HTTPS: {notify_url}")
        else:
            print(f"  ⚠  回调 URL 建议使用 HTTPS: {notify_url}")
        print()

    # ---- 总结 ----
    print("=" * 60)
    if not missing and not file_issues:
        print("  ✅ 微信支付配置完整, 可以启用真实支付!")
        print()
        print("  下一步:")
        print("  1. 重启后端服务")
        print("  2. 调用 /api/payment/wxpay/unified-order 测试下单")
        print("  3. 配置微信商户平台回调 URL → 你的公网地址/api/payment/wechat/notify")
        print("=" * 60)
        return 0
    else:
        print("  ❌ 微信支付配置不完整, 当前使用 Mock 模式.")
        print()
        if missing:
            print(f"  缺失必需配置 ({len(missing)} 项):")
            for key in missing:
                info = REQUIRED_CONFIGS[key]
                print(f"    - {info['label']} ({key})")
        if file_issues:
            print(f"  文件问题 ({len(file_issues)} 项):")
            for issue in file_issues:
                print(f"    - {issue}")
        print()
        print("  修复后重新运行此脚本确认.")
        print("  详细指南请查阅: WECHAT_PAY_SETUP_CHECKLIST.md")
        print("=" * 60)
        return 2 if file_issues else 1


def main():
    parser = argparse.ArgumentParser(
        description="链客宝微信支付配置检查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python check_wechat_config.py              # 基本检查\n"
            "  python check_wechat_config.py --verbose     # 显示所有详细信息\n"
            "  python check_wechat_config.py --fix-env     # 尝试从 .env 加载\n"
        ),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="显示更详细的配置说明",
    )
    parser.add_argument(
        "--fix-env",
        "-f",
        action="store_true",
        help="尝试从项目根目录的 .env 文件加载配置",
    )
    parser.add_argument(
        "--dotenv-path",
        type=str,
        default="",
        help="指定 .env 文件路径",
    )

    args = parser.parse_args()

    # 如果指定了 dotenv 路径, 尝试加载
    if args.dotenv_path:
        try:
            from dotenv import load_dotenv

            if load_dotenv(args.dotenv_path, override=False):
                print(f"  ✓ 已加载 .env 文件: {args.dotenv_path}")
        except ImportError:
            print("  ⚠  请安装 python-dotenv: pip install python-dotenv")
    elif args.fix_env:
        # 已在模块级别加载过
        if not _DOTENV_LOADED:
            print("  ⚠  未找到 .env 文件, 请手动设置环境变量或创建 .env")
            print()

    exit_code = run_check(verbose=args.verbose)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
