#!/usr/bin/env python3
"""一键替换链客宝小程序AppID

用法:
    python replace_appid.py 新AppID

示例:
    python replace_appid.py wxa1b2c3d4e5f6g7h8

说明:
    替换所有文件中旧AppID为新的AppID。
    旧AppID: wxb4f6d89904200fd2（显臻教育）
"""

import os, sys, re

PROJECT_DIR = r"D:\chainke-full"
OLD_APPID = "wxb4f6d89904200fd2"

def main():
    if len(sys.argv) < 2:
        print("❌ 用法: python replace_appid.py <新AppID>")
        sys.exit(1)
    
    new_appid = sys.argv[1].strip()
    if not new_appid.startswith("wx"):
        print("❌ AppID格式错误，应以 wx 开头")
        sys.exit(1)
    
    # 要替换的文件列表
    files = [
        r"liankebao-weapp\project.config.json",
        r"liankebao-miniapp\project.config.json",
        r"backend\app\routers\auth.py",
        r"backend\app\routers\orders.py",
        r"backend\app\routers\payment.py",
        r"backend\recharge\routes.py",
        r"scripts\miniapp_review_helper.py",
        r"README-小程序.md",
        r"submission_checklist.md",
        r"WECHAT_PAYMENT_PLAN.md",
        r"WECHAT_PAY_SETUP_CHECKLIST.md",
    ]
    
    replaced = 0
    not_found = 0
    for rel_path in files:
        fp = os.path.join(PROJECT_DIR, rel_path)
        if not os.path.isfile(fp):
            print(f"  ⚠️  不存在: {rel_path}")
            not_found += 1
            continue
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        if OLD_APPID in content:
            new_content = content.replace(OLD_APPID, new_appid)
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(new_content)
            count = content.count(OLD_APPID)
            print(f"  ✅ {rel_path} ({count}处)")
            replaced += 1
        else:
            print(f"  ➖ {rel_path} (无旧AppID)")
    
    print(f"\n完成: {replaced}个文件已替换, {not_found}个不存在")
    print(f"旧AppID: {OLD_APPID}")
    print(f"新AppID: {new_appid}")

if __name__ == "__main__":
    main()
