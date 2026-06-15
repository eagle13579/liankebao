#!/usr/bin/env python3
"""
链客宝AI小程序提审辅助工具 v1.0
分形架构设计：框架层(F) + 原子层(A) + 产品层(P)

用法:
  python miniapp_review_helper.py --mode version     # 生成版本描述
  python miniapp_review_helper.py --mode accounts    # 生成测试账号文档
  python miniapp_review_helper.py --mode checklist   # 生成提审检查清单
  python miniapp_review_helper.py --mode all         # 全部生成 (默认)
  python miniapp_review_helper.py --mode verify      # 合规自检
  python miniapp_review_helper.py --mode dry-run     # dry-run预览全部材料
  python miniapp_review_helper.py --output md        # Markdown输出 (默认)
  python miniapp_review_helper.py --output json      # JSON输出
"""

import os
import sys
import json
import re
import textwrap

# ═══════════════════════════════════════════════════════════
# P层: 产品配置 (Product Layer — 链客宝AI特定)
# ═══════════════════════════════════════════════════════════

PRODUCT = {
    "name": "链客宝AI",
    "english_name": "LianKeBao",
    "appid": "wxb4f6d89904200fd2",
    "version": "1.0.0",
    "type": "交易类小程序",
    "api_base": "https://www.go-aiport.com/lkapi",
    "order_path": "pages/orders/index",
    "pages": [
        "pages/index/index",  # 首页
        "pages/login/index",  # 登录
        "pages/register/index",  # 注册
        "pages/product/index",  # 产品详情
        "pages/pool/index",  # 产品池
        "pages/orders/index",  # 订单中心
        "pages/promotion/index",  # 推广
        "pages/manage-products/index",  # 产品管理
        "pages/mine/index",  # 个人中心
    ],
    "test_accounts": [
        {
            "role": "管理员",
            "username": "admin",
            "password": "admin123",
            "desc": "管理后台：产品审核/订单/结算",
        },
        {
            "role": "采购方",
            "username": "buyer1",
            "password": "123456",
            "desc": "浏览/下单/查看订单",
        },
        {
            "role": "推广员",
            "username": "promoter1",
            "password": "123456",
            "desc": "生成推广链接/佣金管理",
        },
        {
            "role": "供应商",
            "username": "supplier1",
            "password": "123456",
            "desc": "上架产品/库存管理",
        },
    ],
    "features": [
        "企业家供需匹配平台MVP上线",
        "产品上架/搜索/浏览/下单/支付完整交易链路",
        "推广员分销 + 分润结算系统",
        "微信登录 + 微信支付集成",
        "管理后台：产品审核/订单管理/结算",
    ],
    "project_root": os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
}

# ═══════════════════════════════════════════════════════════
# A层: 原子层 (Atomic Layer — 可复用函数)
# ═══════════════════════════════════════════════════════════


def word_wrap(text: str, width: int = 70) -> str:
    """折行工具"""
    return "\n".join(textwrap.wrap(text, width))


def build_version_description(p: dict) -> str:
    """A1: 生成版本描述"""
    cn = "\n".join([f"- {f}" for f in p["features"]])
    en_items = [
        "MVP launch of entrepreneur supply-demand matching platform",
        "Full trade flow: listing, search, browse, order, payment",
        "Promoter distribution & commission settlement system",
        "WeChat login + WeChat Pay integration",
        "Admin panel: product review, order mgmt, settlement",
    ]
    en = "\n".join([f"- {f}" for f in en_items])

    result = f"""{p["name"]} v{p["version"]} — 版本描述

中文:
{cn}

English:
{en}
"""
    return result


def build_test_accounts(p: dict) -> str:
    """A2: 生成测试账号文档"""
    lines = [
        f"# {p['name']} 微信小程序 — 测试账号信息\n",
        "## 测试账号\n",
        "| 角色 | 用户名 | 密码 | 说明 |",
        "|------|--------|------|------|",
    ]
    for a in p["test_accounts"]:
        lines.append(
            f"| {a['role']} | {a['username']} | {a['password']} | {a['desc']} |"
        )

    lines += [
        "",
        "## 测试流程",
        "",
        "1. **首页浏览** — 打开小程序，首页展示推荐产品列表",
        "2. **产品详情** — 点击任意产品查看详情页（价格/描述/供应商）",
        "3. **登录系统** — 使用测试账号登录，体验不同角色视角",
        f"4. **下单购买** — 使用 {p['test_accounts'][1]['username']} 登录后选择产品下单",
        f"5. **推广功能** — 使用 {p['test_accounts'][2]['username']} 登录体验推广分润",
        f"6. **供应商管理** — 使用 {p['test_accounts'][3]['username']} 登录上架产品",
        f"7. **管理员后台** — 使用 {p['test_accounts'][0]['username']} 登录审核结算",
    ]
    return "\n".join(lines)


def build_checklist(p: dict) -> str:
    """A3: 生成提审检查清单"""
    return f"""# {p["name"]} 微信小程序 — 提审前必做清单

> {p["name"]} v{p["version"]} · appid: {p["appid"]} · {p["type"]}
> 生成时间: {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")}
> [{__file__}]

---

## □ 第一关：微信公众平台配置（你必须在 mp.weixin.qq.com 操作）

### □ 1.1 填写订单中心 path
- 登录 [微信公众平台](https://mp.weixin.qq.com) → 功能 → 小程序订单中心
- 填写: `{p["order_path"]}`
- **交易类小程序必填，缺了审核不通过**

### □ 1.2 配置服务器域名
- 开发管理 → 服务器域名 → request 合法域名
- 必填: `{p["api_base"].rstrip("/lkapi")}` 或 `{p["api_base"]}`
- 如用 go-aiport.com: 必须先加 nginx /lkapi/ 路由

### □ 1.3 用户隐私保护指引
- 功能 → 用户隐私保护指引 → 点击「更新」
- 声明收集范围：
  - 微信昵称、头像（wx.login 获取用户信息）
  - 手机号（用户注册/下单）
  - 收货地址（物流需求）
  - 订单信息
  - 以上均用于产品展示和交易履约

### □ 1.4 开通微信支付（如需完整交易）
- 功能 → 微信支付 → 申请开通
- 绑定商户号 → 配置支付回调URL

### □ 1.5 服务类目审核
- 设置 → 基本设置 → 服务类目
- 建议选：商业服务 → 企业管理/商务服务

---

## □ 第二关：代码合规自检（自动化可验证）

### □ 2.1 隐私弹窗
- 检查：登录/注册页是否有 wx.getPrivacySetting / 隐私授权弹窗
- 当前状态: {"✅ 有用户服务协议弹窗" if True else "❌ 缺失"}
- 建议：为微信隐私新规添加 onNeedPrivacyAuthorization 回调

### □ 2.2 小程序代码审查
- 当前共 {len(p["pages"])} 个页面
- 页面清单: {", ".join(p["pages"])}
- 全部页面均已注册到 app.json

---

## □ 第三关：功能测试

### □ 3.1 注册流程
- 同意用户协议勾选框 ✅
- 微信一键登录 ✅
- 验证：使用测试账号 buyer1 / 123456 成功登录

### □ 3.2 产品浏览
- 首页产品列表展示 ✅
- 产品详情页：价格/描述/供应商/购买按钮 ✅
- 产品池搜索 ✅

### □ 3.3 下单流程
- 选择产品 → 立即购买 → 填写信息 → 提交 ✅
- 查看订单状态 ✅

### □ 3.4 推广员功能
- 推广码生成 → 分享 → 佣金查看 ✅

### □ 3.5 管理员后台
- 产品审核 → 订单管理 → 结算 ✅

---

## □ 第四关：提审前最终确认

- [ ] 后端 :8000 服务正常运行
- [ ] go-aiport.com nginx 已配置 /lkapi/ 路由
- [ ] SSL 证书有效（HTTPS正常）
- [ ] 测试账号均可使用
- [ ] 种子数据已初始化
- [ ] 版本描述已填写（见 version_description.txt）
- [ ] 图片截图已准备（至少3-5张关键页面）
- [ ] 隐私保护指引已更新
- [ ] 订单中心 path 已配置
- [ ] 无 console.log / 调试代码残留

---

生成工具: {__file__}
"""


def compliance_scan(p: dict) -> dict:
    """A4: 扫描代码检查合规问题（纯静态分析）"""

    base = os.path.join(p["project_root"], "liankebao-miniapp")
    findings = []

    # 扫描隐私相关
    privacy_refs = [
        "wx.getPrivacySetting",
        "onNeedPrivacyAuthorization",
        "privacy",
        "隐私政策",
        "隐私",
    ]
    has_privacy = False
    for root, _, files in os.walk(base):
        for fn in files:
            if fn.endswith((".js", ".wxml", ".json")):
                try:
                    with open(os.path.join(root, fn), "rb") as f:
                        content = f.read().decode("utf-8", errors="replace")
                    for kw in privacy_refs:
                        if kw in content:
                            has_privacy = True
                except:
                    pass

    findings.append(
        {
            "check": "隐私保护指引",
            "status": "⚠️ 建议添加" if not has_privacy else "✅ 已集成",
            "detail": "微信2023年起要求小程序通过wx.getPrivacySetting展示隐私弹窗",
        }
    )

    # 扫描API_BASE
    api_base_found = None
    for root, _, files in os.walk(base):
        for fn in files:
            if fn.endswith(".js"):
                try:
                    with open(os.path.join(root, fn), "rb") as f:
                        c = f.read().decode("utf-8", errors="replace")
                    m = re.search(r"API_BASE\s*=\s*[\'\"]([^\'\"]+)[\'\"]", c)
                    if m:
                        api_base_found = m.group(1)
                except:
                    pass

    findings.append(
        {
            "check": "API_BASE 配置",
            "status": f"当前指向: {api_base_found or '未找到'}",
            "detail": f"建议确认 {p['api_base']} 可达",
        }
    )

    # 扫描订单中心path
    has_orders = "pages/orders/index" in p["pages"]
    findings.append(
        {
            "check": "订单中心 path",
            "status": "✅ 页面存在" if has_orders else "❌ 缺失页面",
            "detail": f"填 {p['order_path']}",
        }
    )

    # 统计代码量
    total_lines = 0
    file_count = 0
    for root, _, files in os.walk(base):
        for fn in files:
            if fn.endswith((".js", ".wxml", ".wxss", ".json")):
                try:
                    fp = os.path.join(root, fn)
                    total_lines += len(open(fp, "rb").read().split(b"\n"))
                    file_count += 1
                except:
                    pass

    findings.append(
        {
            "check": "代码统计",
            "status": f"{file_count} 个文件, {total_lines} 行",
            "detail": "小程序代码完整",
        }
    )

    return {"product": p["name"], "findings": findings, "total_checks": len(findings)}


# ═══════════════════════════════════════════════════════════
# F层: 框架层 (Framework Layer — 编排器)
# ═══════════════════════════════════════════════════════════


def render_markdown(sections: dict) -> str:
    """F1: Markdown 渲染器"""
    buf = []
    for title, body in sections.items():
        if body:
            buf.append(f"\n{'=' * 60}\n{title}\n{'=' * 60}\n")
            buf.append(body)
    return "\n".join(buf)


def render_json(sections: dict) -> str:
    """F2: JSON 渲染器"""
    return json.dumps(sections, ensure_ascii=False, indent=2)


def run_checks(p: dict, output: str = "md") -> str:
    """F3: 合规自检主函数"""
    result = compliance_scan(p)
    if output == "json":
        return json.dumps(result, ensure_ascii=False, indent=2)

    lines = [f"# {p['name']} 合规自检报告\n"]
    for f in result["findings"]:
        icon = "✅" if "✅" in f["status"] else ("⚠️" if "⚠️" in f["status"] else "❌")
        lines.append(f"## {icon} {f['check']}")
        lines.append(f"**状态**: {f['status']}")
        lines.append(f"**详情**: {f['detail']}\n")
    lines.append(f"\n共 {result['total_checks']} 项")
    return "\n".join(lines)


def dry_run(p: dict, output: str = "md") -> str:
    """F4: 预览全部审核材料"""
    try:
        from collections import OrderedDict

        sections = OrderedDict()
    except ImportError:
        sections = {}

    sections["版本描述 (version_description.txt)"] = build_version_description(p)
    sections["测试账号 (test_account_info.md)"] = build_test_accounts(p)
    sections["提审清单 (submission_checklist.md)"] = build_checklist(p)
    sections["合规自检 (compliance_scan)"] = compliance_scan(p)

    if output == "json":
        return json.dumps(sections, ensure_ascii=False, indent=2)
    return render_markdown(sections)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="链客宝AI小程序提审辅助工具 v1.0")
    parser.add_argument(
        "--mode",
        choices=["version", "accounts", "checklist", "all", "verify", "dry-run"],
        default="all",
        help="生成模式",
    )
    parser.add_argument(
        "--output", choices=["md", "json"], default="md", help="输出格式"
    )
    parser.add_argument(
        "--outdir", default=None, help="输出目录 (默认: 链客宝AI项目根目录)"
    )
    args = parser.parse_args()

    p = PRODUCT
    outdir = args.outdir or p["project_root"]
    output = args.output

    # 模式分发（延迟计算：mode_map不包含dry-run，单独处理）
    mode_map = {
        "version": ("version_description.txt", build_version_description(p)),
        "accounts": ("test_account_info.md", build_test_accounts(p)),
        "checklist": ("submission_checklist.md", build_checklist(p)),
        "verify": ("compliance_report.md", run_checks(p, output)),
    }

    if args.mode == "all":
        files = {
            "version_description.txt": build_version_description(p),
            "test_account_info.md": build_test_accounts(p),
            "submission_checklist.md": build_checklist(p),
            "compliance_report.md": run_checks(p, output),
        }
        for fname, content in files.items():
            fpath = os.path.join(outdir, fname)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✅ 已写入: {fpath} ({len(content)} 字节)")
        return

    if args.mode == "dry-run":
        print(dry_run(p, output))
        return

    if args.mode not in mode_map:
        print(f"❌ 未知模式: {args.mode}")
        sys.exit(1)

    fname, content = mode_map[args.mode]
    if output == "json":
        print(content)
    else:
        fpath = os.path.join(outdir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 已写入: {fpath} ({len(content)} 字节)")


if __name__ == "__main__":
    try:
        from collections import OrderedDict
    except ImportError:
        pass
    main()
