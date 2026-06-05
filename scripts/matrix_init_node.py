#!/usr/bin/env python3
"""
matrix_init_node.py — 盖娅矩阵新Node初始化工具
从 _template/ 复制模板，生成项目专属 SOUL.md，创建独立目录结构。

用法:
  python matrix_init_node.py --name "链客宝" --type SaaS
  python matrix_init_node.py --name "go-aiport" --type Website --desc "中韩出海数智港"
  python matrix_init_node.py --name "盖娅之城" --type Tool --port 8080
  python matrix_init_node.py --list-types               # 列出可用项目类型
"""
import os
import sys
import json
import shutil
import logging
import argparse
from datetime import datetime

# ── 全局路径 ──
HERMES = r"D:\向海容的知识库\wiki\wiki\记忆宫殿"
PROFILES_DIR = os.path.join(HERMES, "profiles")
TEMPLATE_DIR = os.path.join(PROFILES_DIR, "_template")
SHARED_DIR = os.path.join(PROFILES_DIR, "_shared")
INIT_LOG = os.path.join(HERMES, "_backfeed_archive", "matrix_init.log")

# ── 支持的 Node 类型 ──
NODE_TYPES = {
    "SaaS": {
        "description": "SaaS 产品项目",
        "data_isolation": "RLS",
        "subdirs": ["skills", "sessions", "memory", "config", "deploy"]
    },
    "Website": {
        "description": "网站/前端项目",
        "data_isolation": "Schema",
        "subdirs": ["skills", "sessions", "memory", "config", "public"]
    },
    "Tool": {
        "description": "工具/CLI项目",
        "data_isolation": "SeparateDB",
        "subdirs": ["skills", "sessions", "memory", "config", "bin"]
    },
    "Service": {
        "description": "微服务/API项目",
        "data_isolation": "Schema",
        "subdirs": ["skills", "sessions", "memory", "config", "api"]
    },
    "Library": {
        "description": "库/SDK项目",
        "data_isolation": "SeparateDB",
        "subdirs": ["skills", "sessions", "memory", "config", "lib"]
    },
    "Data": {
        "description": "数据分析/研究项目",
        "data_isolation": "SeparateDB",
        "subdirs": ["skills", "sessions", "memory", "data", "notebooks"]
    }
}

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(INIT_LOG, encoding="utf-8")
    ]
)
logger = logging.getLogger("matrix_init")


def ensure_dirs():
    """确保必要的目录存在"""
    os.makedirs(os.path.dirname(INIT_LOG), exist_ok=True)


def list_types():
    """列出所有可用的项目类型"""
    print(f"\n可用项目类型 ({len(NODE_TYPES)}):")
    print(f"{'─'*60}")
    for key, info in NODE_TYPES.items():
        isolation = info.get("data_isolation", "RLS")
        subdirs = ", ".join(info.get("subdirs", []))
        print(f"  {key:12s} {info['description']:20s} 隔离:{isolation:12s} 子目录:{subdirs}")
    print(f"{'─'*60}")


def validate_project_name(name: str) -> str:
    """验证并规范化项目名"""
    if not name or not name.strip():
        raise ValueError("项目名不能为空")

    # 清理：只保留字母、数字、中横线、下划线、中文
    import re
    cleaned = re.sub(r'[^\w\-\u4e00-\u9fff]', '', name.strip())
    if not cleaned:
        raise ValueError("项目名只能包含字母、数字、中文、中横线和下划线")

    # 生成目录名（小写英文字母+中横线）
    dir_name = cleaned.lower().replace(' ', '-')
    # 如果是中文，用英文简化
    if re.match(r'^[\u4e00-\u9fff]+$', dir_name):
        # 尝试拼音简化（这里简单处理：直接使用中文目录名）
        dir_name = cleaned

    return cleaned, dir_name


def generate_soul_md(project_name: str, project_type: str, description: str = "",
                     port: int = None, layers: dict = None) -> str:
    """生成项目专属 SOUL.md"""
    type_info = NODE_TYPES.get(project_type, NODE_TYPES["SaaS"])
    isolation = type_info["data_isolation"]

    if not description:
        description = f"{project_name} — {type_info['description']}"

    if layers is None:
        layers = {
            "layer1": f"D:\\projects\\{project_name}\\",
            "layer2": os.path.join(HERMES, "L5孵化室", "产品开发", project_name, ""),
            "layer3": os.path.join(PROFILES_DIR, project_name.lower().replace(' ', '-'), "")
        }

    port_line = ""
    if port:
        port_line = f"""\n### 值守

- 端口: {port}
- 健康检查: `http://localhost:{port}/health`
"""

    # 子目录结构
    subdirs = type_info.get("subdirs", [])
    subdirs_list = "\n".join([f"- {sd}/" for sd in subdirs])

    soul = f"""# SOUL.md — {project_name} Profile

> **定位**: {description}
> **类型**: {project_type}
> **数据隔离**: {isolation}

## 母体继承

参见 `profiles/_shared/SOUL_REFERENCE.md`

- 继承母体铁律
- 可调用母体员工池
- 技能索引: `_shared/SKILL_INDEX.yaml`
- 员工索引: `_shared/EMPLOYEE_INDEX.yaml`
- 心智模型索引: `_shared/MENTAL_MODEL_INDEX.yaml`

## 项目专属配置

### 三层路径

| 层 | 路径 | 说明 |
|:---|:-----|:------|
| Layer 1 工程代码 | `{layers['layer1']}` | 后端 + 前端 + 部署 |
| Layer 2 产品资产 | `{layers['layer2']}` | 文档 + 设计 |
| Layer 3 工作环境 | `{layers['layer3']}` | 当前 Profile 目录 |

### 项目规则

- [rule-001] 所有用户数据必须走数据契约
- [rule-002] 新技能产出必须触发反哺
- [rule-003] 数据隔离级别: {isolation}

### 目录结构

{subdirs_list}
{port_line}
### 创建信息

- 创建时间: {datetime.now().isoformat()[:19]}
- 创建工具: matrix_init_node.py v1.0
- 模板来源: profiles/_template/SOUL.md
"""
    return soul


def create_node_directory(project_dir: str, type_info: dict) -> dict:
    """
    创建 Node 目录结构
    返回 {subdir: path} 映射
    """
    created = {}
    for subdir in type_info.get("subdirs", []):
        path = os.path.join(project_dir, subdir)
        os.makedirs(path, exist_ok=True)
        created[subdir] = path
        logger.debug("创建目录: %s", path)

    return created


def copy_template_files(project_dir: str, project_name: str):
    """从 _template/ 复制模板文件（如果有）"""
    copied = []
    if os.path.isdir(TEMPLATE_DIR):
        for item in os.listdir(TEMPLATE_DIR):
            src = os.path.join(TEMPLATE_DIR, item)
            dst = os.path.join(project_dir, item)
            if item == "SOUL.md":
                continue  # SOUL.md 由本工具单独生成
            if os.path.isfile(src):
                shutil.copy2(src, dst)
                copied.append(item)
                logger.debug("复制模板文件: %s", item)
            elif os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
                copied.append(item + "/")
                logger.debug("复制模板目录: %s", item)
    return copied


def create_readme(project_dir: str, project_name: str, project_type: str, description: str):
    """创建项目 README.md"""
    readme_path = os.path.join(project_dir, "README.md")
    content = f"""# {project_name}

> **类型**: {project_type}
> **描述**: {description}
> **创建时间**: {datetime.now().isoformat()[:19]}

## 目录结构

```
{project_name}/
├── SOUL.md          ← 项目灵魂文件（继承母体铁律+专属规则）
├── skills/          ← 项目专属技能（仅项目特有）
├── sessions/        ← 独立会话记录
├── memory/          ← 项目专属本地记忆
├── config/          ← 项目专属配置
└── README.md        ← 本文件
```

## 母体继承

本项目是盖娅矩阵的一个独立 Node，继承母体记忆宫殿的全部能力：
- 190+ 技能原子
- 166 员工（AI数智军团）
- 194 心智模型（五池）
- 23+ 铁律

## 快速开始

1. 查看 SOUL.md 了解项目配置
2. 运行同步: `python ../scripts/matrix_sync.py --apply --profile {os.path.basename(project_dir)}`
3. 运行反哺检测: `python ../scripts/matrix_backfeed.py --profile {os.path.basename(project_dir)}`
"""
    try:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("创建 README.md: %s", readme_path)
        return True
    except Exception as e:
        logger.error("创建 README.md 失败: %s", e)
        return False


def create_gitignore(project_dir: str):
    """创建 .gitignore"""
    gitignore_path = os.path.join(project_dir, ".gitignore")
    content = """# Python
__pycache__/
*.py[cod]
*.pyo
*.egg-info/
.venv/
venv/

# Node
node_modules/

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Project
state.db
*.log
.env
"""
    try:
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error("创建 .gitignore 失败: %s", e)
        return False


def verify_node(project_dir: str, expected_subdirs: list) -> dict:
    """验证 Node 创建完整性"""
    result = {
        "exists": os.path.isdir(project_dir),
        "soul_exists": os.path.isfile(os.path.join(project_dir, "SOUL.md")),
        "readme_exists": os.path.isfile(os.path.join(project_dir, "README.md")),
        "subdirs": {}
    }

    for subdir in expected_subdirs:
        path = os.path.join(project_dir, subdir)
        result["subdirs"][subdir] = os.path.isdir(path)

    result["all_ok"] = (
        result["exists"]
        and result["soul_exists"]
        and all(result["subdirs"].values())
    )

    return result


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(
        description="盖娅矩阵新Node初始化工具 — 创建独立项目节点",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s --name \"链客宝\" --type SaaS\n"
            "  %(prog)s --name \"go-aiport\" --type Website --desc \"中韩出海数智港\"\n"
            "  %(prog)s --name \"盖娅之城\" --type Tool --port 8080\n"
            "  %(prog)s --list-types\n"
        )
    )
    parser.add_argument("--name", help="项目名称")
    parser.add_argument("--type", choices=list(NODE_TYPES.keys()), default="SaaS",
                        help=f"项目类型 (默认: SaaS)，可选: {', '.join(NODE_TYPES.keys())}")
    parser.add_argument("--desc", help="项目描述（可选）")
    parser.add_argument("--port", type=int, help="服务端口（可选）")
    parser.add_argument("--layer1", help="Layer 1 工程代码路径（可选）")
    parser.add_argument("--layer2", help="Layer 2 产品资产路径（可选）")
    parser.add_argument("--list-types", action="store_true", help="列出所有可用项目类型")
    parser.add_argument("--force", action="store_true", help="强制覆盖已存在的目录")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不实际创建")

    args = parser.parse_args()

    try:
        ensure_dirs()

        # --list-types
        if args.list_types:
            list_types()
            return

        # 参数验证
        if not args.name:
            parser.print_help()
            sys.exit(1)

        project_name, dir_name = validate_project_name(args.name)

        # 项目目录
        project_dir = os.path.join(PROFILES_DIR, dir_name)

        if os.path.exists(project_dir) and not args.force:
            logger.error("目录已存在: %s", project_dir)
            print(f"❌ 目录已存在: {project_dir}")
            print(f"   使用 --force 强制覆盖，或选择其他名称")
            sys.exit(1)

        if args.dry_run:
            print(f"\n{'='*60}")
            print(f"  🔍 模拟模式 — 以下操作将被执行:")
            print(f"{'='*60}")
            print(f"  项目名:     {project_name}")
            print(f"  目录名:     {dir_name}")
            print(f"  类型:       {args.type}")
            print(f"  路径:       {project_dir}")
            desc_display = args.desc or f'{project_name} -- {NODE_TYPES[args.type]["description"]}'
            print(f"  描述:       {desc_display}")
            print(f"  端口:       {args.port or '未指定'}")
            print(f"  子目录:     {', '.join(NODE_TYPES[args.type]['subdirs'])}")
            print(f"{'='*60}")
            return

        # 开始创建
        print(f"\n{'='*60}")
        print(f"  🚀 创建盖娅矩阵 Node: {project_name}")
        print(f"{'='*60}")

        type_info = NODE_TYPES[args.type]

        # 1. 创建项目目录
        if os.path.exists(project_dir) and args.force:
            shutil.rmtree(project_dir)
            logger.info("删除已有目录: %s", project_dir)

        os.makedirs(project_dir, exist_ok=True)
        logger.info("创建项目目录: %s", project_dir)
        print(f"  📁 创建目录: {project_dir}")

        # 2. 创建子目录结构
        subdirs_created = create_node_directory(project_dir, type_info)
        print(f"  📂 创建子目录: {', '.join(subdirs_created.keys())}")

        # 3. 复制模板文件
        copied = copy_template_files(project_dir, project_name)
        if copied:
            print(f"  📄 复制模板文件: {', '.join(copied)}")

        # 4. 生成 SOUL.md
        layers = {}
        if args.layer1:
            layers["layer1"] = args.layer1
        else:
            layers["layer1"] = f"D:\\projects\\{project_name}\\"

        if args.layer2:
            layers["layer2"] = args.layer2
        else:
            layers["layer2"] = os.path.join(HERMES, "L5孵化室", "产品开发", project_name, "")

        layers["layer3"] = project_dir + "\\"

        soul_content = generate_soul_md(
            project_name=project_name,
            project_type=args.type,
            description=args.desc or "",
            port=args.port,
            layers=layers
        )

        soul_path = os.path.join(project_dir, "SOUL.md")
        try:
            with open(soul_path, "w", encoding="utf-8") as f:
                f.write(soul_content)
            logger.info("生成 SOUL.md: %s", soul_path)
            print(f"  📝 生成 SOUL.md: {soul_path}")
        except Exception as e:
            logger.error("生成 SOUL.md 失败: %s", e)
            print(f"  ❌ 生成 SOUL.md 失败: {e}")

        # 5. 创建 README.md
        create_readme(project_dir, project_name, args.type, args.desc or "")

        # 6. 创建 .gitignore
        create_gitignore(project_dir)

        # 7. 验证
        print(f"\n{'─'*60}")
        print(f"  🔍 验证 Node 完整性...")
        verification = verify_node(project_dir, type_info["subdirs"])

        if verification["all_ok"]:
            print(f"  ✅ 全部创建成功！")
        else:
            print(f"  ⚠️  部分验证未通过:")
            if not verification["soul_exists"]:
                print(f"    ❌ SOUL.md 不存在")
            for subdir, ok in verification["subdirs"].items():
                if not ok:
                    print(f"    ❌ {subdir}/ 不存在")

        # 8. 总结
        print(f"\n{'='*60}")
        print(f"  ✅ Node 创建完成！")
        print(f"{'='*60}")
        print(f"  项目:    {project_name}")
        print(f"  类型:    {args.type}")
        print(f"  路径:    {project_dir}")
        print(f"  SOUL:    {soul_path}")
        print(f"  隔离:    {type_info['data_isolation']}")
        print(f"  子目录:  {', '.join(subdirs_created.keys())}")
        print(f"{'─'*60}")
        print(f"  下一步:")
        print(f"  1. cd {project_dir}")
        print(f"  2. 运行同步: python ../scripts/matrix_sync.py --apply --profile {dir_name}")
        print(f"  3. 运行反哺检测: python ../scripts/matrix_backfeed.py --profile {dir_name}")
        print(f"{'='*60}")

        # 最终验证
        assert os.path.isdir(project_dir), f"目录创建失败: {project_dir}"
        assert os.path.isfile(soul_path), f"SOUL.md 创建失败: {soul_path}"
        logger.info("✅ Node 创建验证通过: %s", project_name)

    except Exception as e:
        logger.exception("Node 初始化失败: %s", str(e))
        print(f"❌ 初始化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
