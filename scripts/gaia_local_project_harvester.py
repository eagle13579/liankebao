#!/usr/bin/env python3
"""
gaia_local_project_harvester.py — D盘本地项目知识收割管道 v1.0

7×24自动扫描D:\\\\下的高价值项目 → 提取心智模型 → 注入五池 → 封装Feature

运行模式:
  python gaia_local_project_harvester.py --scan       # 扫描项目清单
  python gaia_local_project_harvester.py --harvest     # 收割本轮最高ROI项目
  python gaia_local_project_harvester.py --status      # 收割状态
"""

import os, json, sys, re
from datetime import datetime

HERMES = r"D:\向海容的知识库\wiki\wiki\记忆宫殿"
HARVEST_STATE_PATH = os.path.join(HERMES, "cache", "local_harvest_state.json")

# ── 高价值项目白名单（已筛选，按ROI排序） ──
# 格式: (目录名, 优先级, 领域标签, 说明)
TARGET_PROJECTS = [
    # P0: AI相关项目 → 最直接可吸收
    ("dify", "P0", "AI平台", "LangGenius开源的LLM应用开发平台, 2700+ Python文件, RAG/Agent/工作流引擎"),
    ("fastgpt", "P0", "AI平台", "AI知识库+工作流平台, 对标dify, 有独特的知识库分块和Flow模式"),
    ("coze-loop", "P0", "AI Agent", "Coze AI Bot开发实践, Agent编排模式"),
    ("LobsterAI", "P1", "AI金融", "AI交易/金融分析项目, 445 Python文件, 适合量化Feature"),
    
    # P1: 框架/架构项目 → 提取设计模式
    ("JeecgBoot", "P1", "Java架构", "Java低代码平台, 可提取微服务/权限/工作流设计模式"),
    ("opc", "P1", "IoT/通信", "OPC UA通信协议实现, 可提取工业物联网架构模式"),
    ("openclaw", "P1", "Web架构", "大型Web应用, 17K+ JS文件, 前端架构模式"),
    
    # P2: 工具/平台项目
    ("ruflo", "P2", "自动化", "工作流自动化引擎"),
    ("codex", "P2", "AI编码", "AI代码生成相关"),
    ("omi", "P2", "多模态", "多模态AI项目"),
    ("twenty", "P2", "CRM", "开源CRM, 可提取B2B SaaS Feature模式"),
]

# ── 已收割记录 ──
def load_state():
    if os.path.isfile(HARVEST_STATE_PATH):
        with open(HARVEST_STATE_PATH, 'r') as f:
            return json.load(f)
    return {"harvested": [], "last_scan": None, "pipeline_runs": 0}

def save_state(state):
    os.makedirs(os.path.dirname(HARVEST_STATE_PATH), exist_ok=True)
    with open(HARVEST_STATE_PATH, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [本地收割/{level}] {msg}")

def scan_projects():
    """扫描D盘项目，识别未收割的高价值项目"""
    state = load_state()
    harvested_names = set(state.get("harvested", []))
    
    log(f"已收割项目: {len(harvested_names)}个")
    
    # 检查白名单中哪些项目还未收割
    pending = []
    for name, pri, domain, desc in TARGET_PROJECTS:
        if name in harvested_names:
            log(f"  ✅ 已收割: {name}")
        else:
            # 检查项目目录是否存在
            proj_path = os.path.join("D:\\", name)
            if os.path.isdir(proj_path):
                # 快速统计
                py_count = 0
                for root, dirs, files in os.walk(proj_path):
                    # 限制深度，避免卡死
                    depth = root.replace(proj_path, '').count(os.sep)
                    if depth > 5:
                        dirs[:] = []
                        continue
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', '.git', 'venv']]
                    for f in files:
                        if f.endswith('.py'): py_count += 1
                pending.append((name, pri, domain, desc, py_count))
                log(f"  ⏳ 待收割: {name} ({domain}, {py_count}个Python文件)")
            else:
                log(f"  ⚠️ 目录不存在: {name}")
    
    state["last_scan"] = datetime.now().isoformat()
    save_state(state)
    
    # 按优先级排序
    pri_order = {"P0": 0, "P1": 1, "P2": 2}
    pending.sort(key=lambda x: pri_order.get(x[1], 99))
    
    return pending

def harvest_project(project_name, description):
    """收割单个项目：提取核心心智模型"""
    log(f"开始收割: {project_name}")
    
    proj_path = os.path.join("D:\\", project_name)
    if not os.path.isdir(proj_path):
        log(f"❌ 目录不存在: {proj_path}", "WARN")
        return False
    
    # 1. 扫描项目结构
    readme_paths = []
    core_files = []
    for root, dirs, files in os.walk(proj_path):
        depth = root.replace(proj_path, '').count(os.sep)
        if depth > 3:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', '.git', 'venv']]
        for f in files:
            fp = os.path.join(root, f)
            try:
                sz = os.path.getsize(fp)
            except:
                continue
            if f.lower() == 'readme.md' or f.lower() == 'readme.md':
                readme_paths.append((fp, sz))
            elif f.endswith('.py') and sz < 100000 and sz > 1000:
                # Core Python files: main/app/core files
                rel = os.path.relpath(fp, proj_path)
                if any(kw in rel.lower() for kw in ['main', 'app', 'core', 'engine', 'agent', 'workflow']):
                    core_files.append((fp, sz, rel))
    
    log(f"  发现 {len(readme_paths)} 个README, {len(core_files)} 个核心文件")
    
    # 2. 读取README了解项目
    project_info = description
    for rp, sz in sorted(readme_paths, key=lambda x: -x[1])[:2]:
        try:
            with open(rp, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(5000)
            project_info += f"\n\nREADME摘录: {content[:2000]}"
        except:
            pass
    
    # 3. 读取核心文件（找关键架构）
    architecture_notes = []
    for fp, sz, rel in sorted(core_files, key=lambda x: -x[1])[:10]:
        try:
            with open(fp, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(3000)
            # 提取类定义和函数定义
            classes = re.findall(r'class (\w+)', content)
            functions = re.findall(r'def (\w+)', content)
            if classes or functions:
                architecture_notes.append(f"  {rel}: class={classes[:5]}, def={functions[:5]}")
        except:
            pass
    
    log(f"  架构提取完成, {len(architecture_notes)} 个关键模块")
    
    # 4. 输出收割报告
    report = {
        "project": project_name,
        "harvested_at": datetime.now().isoformat(),
        "description": description[:200],
        "key_modules": architecture_notes[:20],
        "readme_excerpt": project_info[:2000],
    }
    
    # 保存收割报告
    report_dir = os.path.join(HERMES, "L1图书馆", "代码资产库", "本地项目收割")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"{project_name}_harvest_{datetime.now().strftime('%Y%m%d')}.json")
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    log(f"  报告已保存: {report_path}")
    
    # 更新状态
    state = load_state()
    if project_name not in state["harvested"]:
        state["harvested"].append(project_name)
    state["pipeline_runs"] = state.get("pipeline_runs", 0) + 1
    save_state(state)
    
    return True

def show_status():
    """展示收割管道状态"""
    state = load_state()
    print(f"\n{'='*60}")
    print(f"  D盘本地项目收割管道 · 状态")
    print(f"{'='*60}")
    print(f"  累积运行: {state.get('pipeline_runs', 0)} 次")
    print(f"  最后扫描: {state.get('last_scan', '从未')}")
    print(f"  已收割:   {len(state.get('harvested', []))} 个项目")
    
    harvested = state.get("harvested", [])
    if harvested:
        print(f"  ─── 已收割清单 ───")
        for h in harvested:
            print(f"    ✅ {h}")
    
    print(f"\n  白名单总计: {len(TARGET_PROJECTS)} 个潜在项目")
    remaining = len(TARGET_PROJECTS) - len(harvested)
    print(f"  待收割:     {remaining} 个")
    print(f"{'='*60}\n")

# ── 主入口 ──
if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "--status":
        show_status()
    elif sys.argv[1] == "--scan":
        pending = scan_projects()
        print(f"\n待收割优先级: {len(pending)} 个项目")
        for name, pri, domain, desc, py_count in pending:
            print(f"  {pri} {name:20s} {domain:10s} {py_count:>5d}个Py文件  {desc[:60]}")
    elif sys.argv[1] == "--harvest":
        if len(sys.argv) > 2:
            target = sys.argv[2]
            for name, pri, domain, desc in TARGET_PROJECTS:
                if name == target:
                    harvest_project(name, desc)
                    break
            else:
                log(f"未知项目: {target}", "WARN")
        else:
            # 自动收割最高优先级未收割项目
            pending = scan_projects()
            if pending:
                name, pri, domain, desc, py_count = pending[0]
                log(f"自动收割最高优先级: {name} ({pri})")
                harvest_project(name, desc)
            else:
                log("所有白名单项目已收割，等待新项目加入")
