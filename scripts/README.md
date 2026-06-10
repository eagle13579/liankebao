# 链客宝AI小程序提审辅助工具

## 快速开始

```bash
# 1. 生成全部审核材料
python scripts/miniapp_review_helper.py

# 2. 合规自检
python scripts/miniapp_review_helper.py --mode verify

# 3. 预览全部（不写文件）
python scripts/miniapp_review_helper.py --mode dry-run
```

## 命令

| 命令 | 用途 | 产出文件 |
|:-----|:------|:---------|
| `--mode version` | 版本描述 | `version_description.txt` |
| `--mode accounts` | 测试账号 | `test_account_info.md` |
| `--mode checklist` | 提审清单 | `submission_checklist.md` |
| `--mode verify` | 合规自检 | `compliance_report.md` |
| `--mode dry-run` | 预览全部 | 终端打印 |
| `--mode all` | 全部生成 | 4个文件（默认） |

## 选项

| 参数 | 说明 |
|:-----|:------|
| `--output md` | Markdown 输出（默认） |
| `--output json` | JSON 输出（CI集成用） |
| `--outdir PATH` | 输出目录（默认：链客宝AI根目录） |

## 分形架构

```
F层 — 框架层: 编排器/渲染器/分发器
  ├── render_markdown()     Markdown渲染
  ├── render_json()         JSON渲染
  ├── run_checks()          合规自检编排
  └── dry_run()             预览编排

A层 — 原子层: 可复用函数
  ├── build_version_description()
  ├── build_test_accounts()
  ├── build_checklist()
  └── compliance_scan()

P层 — 产品层: 链客宝AI配置
  └── PRODUCT dict (appid/域名/密码/页面列表)
```

## 依赖

零外部依赖（仅 Python 3.8+ 标准库）。
