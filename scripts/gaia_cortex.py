#!/usr/bin/env python3
"""
gaia_cortex.py — 盖娅进化大脑 七层调度器 v1.0.0

整合6个现有进化引擎为统一七层飞轮。
每层复用现有资产，不做重复造轮。

用法:
  python gaia_cortex.py              # 全七层运行
  python gaia_cortex.py --layer L0   # 单层
  python gaia_cortex.py --daemon     # 值守模式 (30min循环)
  python gaia_cortex.py --status     # 状态查看
  python gaia_cortex.py --dry-run    # 预览模式 (不执行创造)
"""

import os, sys, json, time, re
from datetime import datetime
from pathlib import Path
from collections import Counter

# ── 双三角模型 D2(审美积累) + D3(体系库) ──
try:
    from gaia_aesthetics import run_aesthetics_collection, show_aesthetic_status
    _HAVE_D2 = True
except ImportError:
    _HAVE_D2 = False
    log("D2审美积累模块未加载", "WARN")
try:
    from gaia_system_library import run_system_library_build, recommend_systems, show_system_library_status
    _HAVE_D3 = True
except ImportError:
    _HAVE_D3 = False
    log("D3体系库模块未加载", "WARN")

# ── 路径 ──
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
HERMES_HOME = os.path.dirname(SCRIPTS_DIR)

# ── 加载数据契约 ──
sys.path.insert(0, SCRIPTS_DIR)
from _data_contract import (
    L0Output, L1Output, L2Output, L3Output, L4Output, L5Output, L6Output,
    AssetSnapshot, Gap, Proposition, Creation, ArchiveRecord, CycleRecord,
    SkillGap,
    MacroAssessmentItem, MacroAssessmentOutput,
    MesoAssessmentItem, MesoAssessmentOutput,
    MicroAssessmentItem, MicroAssessmentOutput,
    ThreeLayerAssessmentOutput,
    to_dict, to_json
)

# ── 加载YAML配置 ──
try:
    import yaml
    CONFIG_PATH = os.path.join(SCRIPTS_DIR, "gaia_cortex_config.yaml")
    CONFIG = {}
    if os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            CONFIG = yaml.safe_load(f) or {}
except ImportError:
    CONFIG = {}

# ── 加载三层评估配置 ──
THREE_LAYER_CONFIG = {}
THREE_LAYER_CONFIG_PATH = os.path.join(SCRIPTS_DIR, "gaia_cortex_three_layer.yaml")
if os.path.isfile(THREE_LAYER_CONFIG_PATH):
    try:
        with open(THREE_LAYER_CONFIG_PATH, "r", encoding="utf-8") as f:
            THREE_LAYER_CONFIG = yaml.safe_load(f) or {}
    except Exception as e:
        log(f"三层评估配置加载失败: {e}", "WARN")


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [盖娅皮层/{level}] {msg}")


# ── 辅助：执行日志→技能缺口分析 ──

def _find_delegate_logs():
    """查找delegate_task执行日志文件"""
    candidates = []
    # agent.log 是主要的执行日志
    agent_log = os.path.join(HERMES_HOME, "logs", "agent.log")
    if os.path.isfile(agent_log):
        candidates.append(agent_log)
    errors_log = os.path.join(HERMES_HOME, "logs", "errors.log")
    if os.path.isfile(errors_log):
        candidates.append(errors_log)
    # 检查进化日志目录
    evo_dir = os.path.join(HERMES_HOME, "L5孵化室", "进化日志")
    if os.path.isdir(evo_dir):
        exec_logs = sorted(
            [os.path.join(evo_dir, f) for f in os.listdir(evo_dir)
             if f.startswith("exec_") and f.endswith(".json")],
            reverse=True
        )[:20]
        candidates.extend(exec_logs)
    return candidates

def _extract_task_type_from_agent_log(line):
    """从agent.log中提取delegate_task类型"""
    m = re.search(r'派发任务\s+\[\d+\]\s+(.+?):\s+', line)
    if m:
        return m.group(1).strip()
    m = re.search(r'delegate_task.*?["\']task_type["\']:\s*["\']([^"\']+)["\']', line)
    if m:
        return m.group(1).strip()
    return None

def _extract_task_type_from_review_filename(filename):
    """从复盘文件名中提取任务类型
    模式: 角色_任务类型_复盘.md  或  日期_任务类型.md
    """
    name = filename.replace(".md", "")
    # 去掉日期前缀 (e.g. 20260603_120540_)
    name = re.sub(r'^\d{8}_?\d{0,6}_?', '', name)
    # 跳过第一个_前的角色名
    parts = name.split("_")
    if len(parts) >= 2 and parts[0] in ("白泽", "文鳐", "烛龙", "乘黄", "计然",
                                          "狴犴", "猼訑", "鲲鹏", "商羊", "数据分析专家",
                                          "龙虾数据管道", "投资大师"):
        return "_".join(parts[1:]).replace("复盘", "").replace("工业化", "").strip("_")
    # 普通文件名直接返回
    return name.replace("复盘", "").strip("_")

def _has_matching_skill(task_type, existing_skills):
    """检查已有skill是否覆盖该任务类型"""
    keywords = task_type.lower().replace("_", " ").replace("-", " ").split()
    for skill in existing_skills:
        skill_lower = skill.lower()
        for kw in keywords:
            if len(kw) >= 3 and kw in skill_lower:
                return True
    return False


# ════════════════════════════════════════════════════════════════
#  L0 感知层 — 资产全景 + 外部信号
# ════════════════════════════════════════════════════════════════

def layer0_sense() -> L0Output:
    """感知层：扫描L1-L5全量资产 + 外部信号"""
    log("L0感知层启动...")
    out = L0Output()

    # 1. 员工扫描
    emp_dir = os.path.join(HERMES_HOME, "employees")
    emp_list = [d for d in os.listdir(emp_dir) if d.startswith("emp-")] if os.path.isdir(emp_dir) else []

    elite = std = shell = 0
    for emp in emp_list:
        sf = os.path.join(emp_dir, emp, "soul-injection.yaml")
        if os.path.isfile(sf):
            sz = os.path.getsize(sf)
            if sz >= 5000: elite += 1
            elif sz >= 2000: std += 1
            else: shell += 1

    # 2. 技能扫描
    skills_dir = os.path.join(HERMES_HOME, "skills")
    skill_cats = len([d for d in os.listdir(skills_dir) if os.path.isdir(os.path.join(skills_dir, d))]) if os.path.isdir(skills_dir) else 0

    # 3. 产品扫描
    prod_dir = os.path.join(HERMES_HOME, "L5孵化室", "产品开发")
    prod_list = [d for d in os.listdir(prod_dir) if os.path.isdir(os.path.join(prod_dir, d)) and not d.startswith("_")] if os.path.isdir(prod_dir) else []

    # 4. 代码资产扫描
    code_dir = os.path.join(HERMES_HOME, "L1图书馆", "代码资产库")
    code_list = [d for d in os.listdir(code_dir) if os.path.isdir(os.path.join(code_dir, d))] if os.path.isdir(code_dir) else []

    # 5. 心智模型扫描
    pool_dir = os.path.join(HERMES_HOME, "L5孵化室", "五池", "模型池")
    model_files = [f for f in os.listdir(pool_dir) if f.endswith(".md")] if os.path.isdir(pool_dir) else []

    out.assets = AssetSnapshot(
        employees=len(emp_list),
        products=len(prod_list),
        skills=skill_cats,
        code_assets=len(code_list),
        mental_models=len(model_files),
        employee_elite=elite,
        employee_standard=std,
        employee_shell=shell,
    )

    log(f"  资产: {len(emp_list)}员工({elite}精锐/{std}标准/{shell}浅魂) | {len(prod_list)}产品 | {skill_cats}技能 | {len(code_list)}代码资产 | {len(model_files)}心智模型")

    # 6. 外部信号 (复用 subconscious.py)
    sub_path = os.path.join(SCRIPTS_DIR, "subconscious.py")
    if os.path.isfile(sub_path):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("subconscious", sub_path)
            sub_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(sub_mod)
            for name, url in getattr(sub_mod, "RSS", [])[:3]:
                content = getattr(sub_mod, "curl_fetch", lambda x: None)(url)
                if content:
                    out.signals.append({"source": name, "summary": content[:200]})
            log(f"  外部信号: {len(out.signals)}条")
        except Exception as e:
            log(f"  外部信号采集失败: {e}", "WARN")

    # 7. 执行日志→新技能发现
    log("  技能缺口扫描...")
    task_type_counter = Counter()
    recent_records = []
    delegate_logs = _find_delegate_logs()

    if delegate_logs:
        for log_file in delegate_logs:
            try:
                if log_file.endswith(".json"):
                    with open(log_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if "type" in data:
                        tt = data.get("type", "")
                        if tt:
                            task_type_counter[tt] += 1
                            recent_records.append(log_file)
                else:
                    # Try common encodings for log files
                    for enc in ("utf-8", "gbk", "latin-1"):
                        try:
                            with open(log_file, "r", encoding=enc) as f:
                                for line in f:
                                    tt = _extract_task_type_from_agent_log(line)
                                    if tt:
                                        task_type_counter[tt] += 1
                                        recent_records.append(log_file)
                            break
                        except (UnicodeDecodeError, UnicodeError):
                            continue
            except Exception as e:
                log(f"    日志读取失败 {log_file}: {e}", "WARN")

    # Fallback: 扫描L4博物馆/复盘/的最新记录
    if not task_type_counter:
        review_dir = os.path.join(HERMES_HOME, "L4博物馆", "复盘")
        if os.path.isdir(review_dir):
            all_reviews = []
            for root, dirs, files in os.walk(review_dir):
                for f in files:
                    if f.endswith(".md") and not f.startswith("_"):
                        all_reviews.append(os.path.join(root, f))
            # 取最近20个复盘记录
            all_reviews.sort(key=os.path.getmtime, reverse=True)
            for rev_path in all_reviews[:20]:
                tt = _extract_task_type_from_review_filename(os.path.basename(rev_path))
                if tt and tt not in ("", "最终", "复盘进化"):
                    task_type_counter[tt] += 1
                    recent_records.append(rev_path)

    # 分析模式：同一task_type出现≥3次视为模式
    skills_dir = os.path.join(HERMES_HOME, "skills")
    existing_skills = set()
    if os.path.isdir(skills_dir):
        for root, dirs, files in os.walk(skills_dir):
            if "SKILL.md" in files:
                rel = os.path.relpath(root, skills_dir)
                existing_skills.add(rel.replace(os.sep, "/"))

    skill_gap_count = 0
    for task_type, count in task_type_counter.most_common():
        if count >= 3:
            has_skill = _has_matching_skill(task_type, existing_skills)
            if not has_skill:
                out.skill_gaps.append(SkillGap(
                    task_type=task_type,
                    occurrences=count,
                    has_skill=False,
                    source="delegate_log" if delegate_logs else "复盘",
                    recent_records=list(set(recent_records))[:3],
                ))
                out.signals.append({
                    "source": "技能缺口-新技能建议",
                    "summary": f"任务类型「{task_type}」出现{count}次但无对应SKILL.md，建议新建技能"
                })
                skill_gap_count += 1

    log(f"  技能缺口: 发现{skill_gap_count}个 (扫描{len(recent_records)}条记录, {len(task_type_counter)}种任务类型)")
    
    # ── 8. Bundle Weaver 信号 ──
    try:
        import subprocess
        bw_result = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "bundle_weaver.py"), "--dry-run"],
            capture_output=True, text=True, timeout=30
        )
        if bw_result.returncode == 0 and bw_result.stdout.strip():
            import json
            lines = bw_result.stdout.strip().split("\n")
            for line in reversed(lines):
                try:
                    bw_data = json.loads(line)
                    if isinstance(bw_data, dict):
                        if bw_data.get("new_skills", 0) > 0:
                            out.signals.append(Signal(
                                source="bundle_weaver",
                                type="new_skills",
                                data=bw_data,
                                priority=5
                            ))
                            log(f"  Bundle信号: 发现{bw_data['new_skills']}个未打包技能")
                        if bw_data.get("candidates", 0) > 0:
                            out.signals.append(Signal(
                                source="bundle_weaver",
                                type="bundle_candidates",
                                data=bw_data,
                                priority=6
                            ))
                            log(f"  Bundle信号: {bw_data['candidates']}个打包候选")
                    break
                except: continue
    except Exception as e:
        pass

    out.timestamp = datetime.now().isoformat()
    log(f"L0感知完成")
    return out


# ════════════════════════════════════════════════════════════════
#  L1 分析层 — 缺口 + ROI排序
# ════════════════════════════════════════════════════════════════

def layer1_analyze(l0: L0Output) -> L1Output:
    """分析层：基于资产快照分析缺口，按ROI排序"""
    log("L1分析层启动...")
    out = L1Output()

    total = l0.assets.employees
    if total == 0:
        out.timestamp = datetime.now().isoformat()
        return out

    # 1. 员工活跃率缺口
    active = l0.assets.employee_elite + l0.assets.employee_standard
    active_rate = active / total
    if active_rate < 0.8:
        out.gaps.append(Gap(
            dimension="员工活跃率", current=active_rate, target=0.9,
            gap=round(0.9 - active_rate, 2), priority="P0"
        ))

    # 2. 产品技能覆盖率缺口
    if l0.assets.skills > 0:
        coverage = l0.assets.products / l0.assets.skills
        if coverage < 0.3:
            out.gaps.append(Gap(
                dimension="产品技能覆盖率", current=coverage, target=0.5,
                gap=round(0.5 - coverage, 2), priority="P1"
            ))

    # 3. 心智模型密度缺口
    mm_rate = l0.assets.mental_models / max(total, 1)
    if mm_rate < 0.1:
        out.gaps.append(Gap(
            dimension="心智模型密度", current=mm_rate, target=0.2,
            gap=round(0.2 - mm_rate, 2), priority="P2"
        ))

    # 4. 浅魂率缺口
    shell_rate = l0.assets.employee_shell / max(total, 1)
    if shell_rate > 0.2:
        out.gaps.append(Gap(
            dimension="浅魂率", current=shell_rate, target=0.1,
            gap=round(shell_rate - 0.1, 2), priority="P1"
        ))

    # 5. ROI排序
    roi_weights = {"P0": 10.0, "P1": 5.0, "P2": 2.0}
    for g in out.gaps:
        g.roi_score = round(g.gap * roi_weights.get(g.priority, 1.0), 2)
    out.gaps.sort(key=lambda g: g.roi_score, reverse=True)

    log(f"  发现 {len(out.gaps)} 个缺口: {', '.join(g.dimension for g in out.gaps[:3])}")

    # ── MiroFish MF-01: 外部知识消化管道 ──
    try:
        from gaia_digest_pipeline import integrate_into_cortex
        digest_hook = integrate_into_cortex()
        digest_result = digest_hook['run'](l0)
        if digest_result.get("digested", 0) > 0:
            out.demands.append({
                "source": "MiroFish消化管道",
                "summary": f"消化了 {digest_result['digested']} 个外部知识源, 新增 {digest_result.get('entities', 0)} 实体, {digest_result.get('relations', 0)} 关系"
            })
            log(f"  ✅ MF-01消化管道: {digest_result['digested']}个源 → {digest_result.get('entities', 0)}实体")
    except ImportError:
        pass  # gaia_digest_pipeline 未安装
    except Exception as e:
        log(f"  ⚠️ MF-01消化管道异常: {e}", "WARN")

    out.timestamp = datetime.now().isoformat()
    return out


# ════════════════════════════════════════════════════════════════
#  L2 组合层 — 排列组合发现
# ════════════════════════════════════════════════════════════════

def layer2_combine(l0: L0Output, l1: L1Output) -> L2Output:
    """组合层：基于缺口，排列组合现有资产产生方案"""
    log("L2组合层启动...")
    out = L2Output()

    for gap in l1.gaps:
        # ── 动态三维评分（基于真实资产数据） ──
        priority_weight = {"P0": 1.0, "P1": 0.7, "P2": 0.4}
        pw = priority_weight.get(gap.priority, 0.5)
        
        # V1 支付意愿 = 优先级权重 × 缺口大小 × 资产规模因子
        v1_base = pw * min(gap.gap * 5, 5.0)
        v1 = round(min(v1_base + 1.0, 5.0), 1)
        
        # V2 替代成本 = 可用资源越少替代成本越高
        total_assets = l0.assets.skills + l0.assets.code_assets + l0.assets.products
        v2 = round(min(5.0 - (total_assets / 200), 4.5), 1)
        if gap.dimension in ("心智模型密度", "浅魂率"):
            v2 = max(v2, 2.0)  # 心智模型注入替代成本高
        
        # V3 交付难度 = 已有资产越多交付越容易
        if gap.dimension == "员工活跃率":
            v3 = round(min(l0.assets.skills / 50, 5.0), 1)
        elif gap.dimension == "产品技能覆盖率":
            v3 = round(min(l0.assets.code_assets / 30, 5.0), 1)
        elif gap.dimension == "心智模型密度":
            v3 = round(min(l0.assets.code_assets / 20, 5.0), 1)
        elif gap.dimension == "浅魂率":
            v3 = round(min(161 / l0.assets.employee_shell if l0.assets.employee_shell > 0 else 5.0, 5.0), 1)
        else:
            v3 = 3.0
        
        total = round((v1 * 0.4 + v2 * 0.3 + v3 * 0.3), 2)
        
        if gap.dimension == "员工活跃率":
            out.propositions.append(Proposition(
                name="批量心智模型注入提升活跃率",
                type="employee",
                description=f"从{l0.assets.skills}个技能中提取TOP心智模型，注入到浅魂员工",
                source_assets=["skills/classical-chinese/", "employees/*/soul-injection.yaml"],
                score_v1=v1, score_v2=v2, score_v3=v3,
                total_score=total,
            ))
        elif gap.dimension == "产品技能覆盖率":
            out.propositions.append(Proposition(
                name="原子×代码资产组合新产品扫描",
                type="product",
                description=f"扫描{l0.assets.skills}个技能与{l0.assets.code_assets}个代码资产的交叉组合机会",
                source_assets=["skills/*", "L1图书馆/代码资产库/*", "L5孵化室/原子集市/*"],
                score_v1=v1, score_v2=v2, score_v3=v3,
                total_score=total,
            ))
        elif gap.dimension == "心智模型密度":
            out.propositions.append(Proposition(
                name="从代码资产库提取架构心智模型",
                type="mental_model",
                description=f"从{l0.assets.code_assets}个项目中提取架构设计模式→写入模型池",
                source_assets=["L1图书馆/代码资产库/*", "L5孵化室/五池/模型池/"],
                score_v1=v1, score_v2=v2, score_v3=v3,
                total_score=total,
            ))
        elif gap.dimension == "浅魂率":
            out.propositions.append(Proposition(
                name="批量灵魂深度升级",
                type="employee",
                description=f"对{l0.assets.employee_shell}名浅魂员工追加情感锚点和心智模型",
                source_assets=["employees/*/soul-injection.yaml"],
                score_v1=v1, score_v2=v2, score_v3=v3,
                total_score=total,
            ))

    out.propositions.sort(key=lambda p: p.total_score, reverse=True)
    log(f"  生成 {len(out.propositions)} 个组合方案")
    out.timestamp = datetime.now().isoformat()
    return out


# ════════════════════════════════════════════════════════════════
#  L3 创造层 — 执行组合方案
# ════════════════════════════════════════════════════════════════

def layer3_create(l2: L2Output, l0: L0Output = None, dry_run: bool = False) -> L3Output:
    """创造层：执行组合方案，产出新skill/心智/原子/产品"""
    log("L3创造层启动..." + (" [DRY RUN]" if dry_run else ""))
    out = L3Output()

    for prop in l2.propositions[:3]:
        out.creations.append(Creation(
            type=prop.type,
            name=prop.name,
            target_path={
                "employee": "employees/*/soul-injection.yaml",
                "product": "L5孵化室/产品开发/",
                "mental_model": "L5孵化室/五池/模型池/",
            }.get(prop.type, ""),
            verification="dry_run" if dry_run else "pending"
        ))

    if not dry_run:
        # ── 统一委派队列：Hermes cronjob agent 读取此文件后自动 delegate_task ──
        queue = []
        
        # ① 从 L0 技能缺口生成委派项
        if l0 and hasattr(l0, 'skill_gaps') and l0.skill_gaps:
            for sg in l0.skill_gaps:
                queue.append({
                    "priority": "P0",
                    "type": "skill",
                    "name": f"创建技能: {sg.task_type}",
                    "description": f"任务类型「{sg.task_type}」已出现{sg.occurrences}次但无对应SKILL.md。来源: {sg.source}",
                    "goal": f"将任务类型「{sg.task_type}」封装为标准 Hermes SKILL.md，含触发条件、详细SOP步骤、陷阱表和验证方法",
                    "context": f"迭代类型: {sg.task_type} | 出现次数: {sg.occurrences}次 | 来源: {sg.source}",
                    "recommended_employee": "文鳐",
                    "task_type": "skill_creation",
                    "sources": sg.recent_records[:3],
                })
        
        # ② 从 L2 提案生成委派项
        for prop in l2.propositions[:3]:
            emp_map = {"employee": "烛龙", "product": "乘黄", "mental_model": "文鳐"}
            queue.append({
                "priority": prop.priority if hasattr(prop, 'priority') else "P1",
                "type": prop.type,
                "name": prop.name,
                "description": prop.description,
                "goal": prop.description,
                "context": f"三维评分: {prop.total_score} (V1支付意愿={prop.score_v1}/V2替代成本={prop.score_v2}/V3交付难度={prop.score_v3})",
                "recommended_employee": emp_map.get(prop.type, "文鳐"),
                "task_type": f"{prop.type}_improvement",
                "sources": prop.source_assets[:3],
            })
        
        # 写委派队列文件
        cache_dir = os.path.join(HERMES_HOME, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        queue_path = os.path.join(cache_dir, "gaia_delegation_queue.json")
        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "cycle_label": f"盖娅进化循环 {datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "total_pending": len(queue),
                "delegations": queue,
            }, f, ensure_ascii=False, indent=2)
        if queue:
            log(f"  ⏫ 写入委派队列: {queue_path} ({len(queue)}项待派)")
            for item in queue:
                log(f"    → [{item['priority']}] {item['name']} → {item['recommended_employee']}")
        else:
            log(f"  委派队列: 无待派事项")

        # 同时写进化日志（兼容旧格式）
        evo_dir = os.path.join(HERMES_HOME, "L5孵化室", "进化日志")
        os.makedirs(evo_dir, exist_ok=True)
        log_path = os.path.join(evo_dir, f"discoveries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "propositions": [to_dict(p) for p in l2.propositions],
                "creations": [to_dict(c) for c in out.creations],
                "delegation_queue": queue_path,
            }, f, ensure_ascii=False, indent=2)
        log(f"  发现记录: {log_path}")

    out.timestamp = datetime.now().isoformat()
    log(f"  创建 {len(out.creations)} 个产出计划")

    # ── MiroFish MF-08: InsightForge三模式检索辅助决策 ──
    try:
        from gaia_insightforge import unified_query
        # 对当前发现的top缺口做深度洞察
        if l2 and l2.propositions:
            top_topic = l2.propositions[0].name
            insight = unified_query(top_topic)
            if insight and insight.get("summary"):
                out.creations.append({
                    "type": "insightforge_scan",
                    "topic": top_topic,
                    "summary": insight["summary"][:200],
                    "panorama_hits": insight.get("panorama_hits", 0),
                    "deep_insights": len(insight.get("deep_findings", [])),
                })
                log(f"  ✅ MF-08 InsightForge: {top_topic} → {insight.get('panorama_hits', 0)}全景命中")
    except ImportError:
        pass
    except Exception as e:
        log(f"  ⚠️ MF-08 InsightForge异常: {e}", "WARN")

    return out


# ════════════════════════════════════════════════════════════════
#  L4 反哺层 — 归档到L1-L5
# ════════════════════════════════════════════════════════════════

def layer4_feed(l3: L3Output) -> L4Output:
    """反哺层：将产出归档到记忆宫殿L1-L5"""
    log("L4反哺层启动...")
    out = L4Output()

    # 1. 追加到 MEMORY.md（只新增不覆盖）
    memory_path = os.path.join(HERMES_HOME, "MEMORY.md")
    if os.path.isfile(memory_path):
        entry = f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} 盖娅进化大脑自动循环\n"
        entry += f"- L3创造: {len(l3.creations)} 个产出计划\n"
        entry += f"- L3创造: {len(l3.creations)} 个发现\n"
        with open(memory_path, "a", encoding="utf-8") as f:
            f.write(entry)
        out.archives.append(ArchiveRecord(
            to="MEMORY.md", what="盖娅进化循环记录",
            file_path=memory_path, verified=os.path.isfile(memory_path)
        ))

    # 2. 进化日志归档
    evo_dir = os.path.join(HERMES_HOME, "L5孵化室", "进化日志")
    os.makedirs(evo_dir, exist_ok=True)
    log_path = os.path.join(evo_dir, f"gaia_cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "layer": "L4",
            "archives": [to_dict(a) for a in out.archives],
        }, f, ensure_ascii=False, indent=2)
    out.archives.append(ArchiveRecord(
        to="L5孵化室/进化日志/",
        what="盖娅进化循环日志",
        file_path=log_path, verified=os.path.isfile(log_path)
    ))

    out.timestamp = datetime.now().isoformat()
    log(f"  反哺 {len(out.archives)} 条记录")
    return out


# ════════════════════════════════════════════════════════════════
#  L5 值守层 — 安排下个周期
# ════════════════════════════════════════════════════════════════

def layer5_watch() -> L5Output:
    """值守层：确认下个周期安排"""
    log("L5值守层启动...")
    out = L5Output()
    out.next_cycle = datetime.fromtimestamp(time.time() + 1800).isoformat()
    out.timestamp = datetime.now().isoformat()
    log(f"  下个周期: 30分钟后 ({out.next_cycle})")
    return out


# ════════════════════════════════════════════════════════════════
#  L6 追溯层 — 全链路记录
# ════════════════════════════════════════════════════════════════

def layer6_trace(start_time: float, l0: L0Output, l1: L1Output,
                 l2: L2Output, l3: L3Output, l4: L4Output, l5: L5Output) -> L6Output:
    """追溯层：完整进化日志 + 北极星数据"""
    log("L6追溯层启动...")
    out = L6Output()

    duration = time.time() - start_time
    out.cycle = CycleRecord(
        layers_executed=["L0", "L1", "L2", "L3", "L4", "L5", "L6"],
        propositions_generated=len(l2.propositions),
        creations_made=len(l3.creations),
        archives_made=len(l4.archives),
        duration_seconds=round(duration, 2),
    )

    # 写入 polaris_data.json (复用 evolve_bridge 模式)
    polaris_path = os.path.join(HERMES_HOME, "polaris_data.json")
    history = []
    if os.path.isfile(polaris_path):
        try:
            with open(polaris_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    history.append({
        "timestamp": datetime.now().isoformat(),
        "type": "gaia_cortex_cycle",
        "dimensions": {
            "感知_资产分": min(l0.assets.products / max(l0.assets.skills, 1) * 100, 100) if l0.assets.skills > 0 else 0,
            "分析_缺口数": len(l1.gaps),
            "组合_方案数": len(l2.propositions),
            "创造_产出数": len(l3.creations),
            "反哺_归档数": len(l4.archives),
            "耗时_秒": round(duration, 1),
            "员工数": l0.assets.employees,
            "心智模型数": l0.assets.mental_models,
            "产品数": l0.assets.products,
            "技能数": l0.assets.skills,
            "精锐员工": l0.assets.employee_elite,
            "标准员工": l0.assets.employee_standard,
        }
    })
    history = history[-500:]
    with open(polaris_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    out.timestamp = datetime.now().isoformat()
    out.log_path = os.path.join(HERMES_HOME, "L5孵化室", "进化日志",
                                f"gaia_cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

    # ── 写入心跳文件 (供 gaia_heartbeat.py 5058 仪表盘读取) ──
    try:
        heartbeat = {
            "last_run": datetime.now().isoformat(),
            "status": "healthy",
            "duration_seconds": round(duration, 2),
            "employees_covered": l0.assets.employees,
            "gaps_found": len(l1.gaps) if l1.gaps else 0,
        }
        heartbeat_path = os.path.join(HERMES_HOME, "cache", "gaia_heartbeat.json")
        os.makedirs(os.path.dirname(heartbeat_path), exist_ok=True)
        with open(heartbeat_path, "w", encoding="utf-8") as f:
            json.dump(heartbeat, f, ensure_ascii=False, indent=2)
        if not os.path.isfile(heartbeat_path):
            log(f"  心跳文件写入后验证失败: {heartbeat_path}", "WARN")
    except Exception as e:
        log(f"  心跳文件写入失败: {e}", "WARN")

    log(f"  循环完成，耗时 {duration:.1f}秒")
    return out


# ════════════════════════════════════════════════════════════════
#  宏观·中观·微观 三层评估引擎
# ════════════════════════════════════════════════════════════════
#  作为新的感知维度，与L0-L6七层飞轮并行运行，不破坏现有循环。
#  评估结果可被L0感知层作为外部信号引用，也可独立执行。
# ════════════════════════════════════════════════════════════════

def three_layer_config() -> dict:
    """获取三层评估配置（含默认值兜底）"""
    cfg = THREE_LAYER_CONFIG
    if not cfg:
        return {
            "macro_layer": {"enabled": True, "evaluation_dimensions": {}, "thresholds": {}},
            "meso_layer": {"enabled": True, "evaluation_dimensions": {}, "thresholds": {}},
            "micro_layer": {"enabled": True, "evaluation_dimensions": {}, "thresholds": {}},
        }
    return cfg


def _get_weight_safely(dim_dict: dict, dim_key: str, sub_name: str, default_weight: float = 0.33) -> float:
    """安全获取子维度权重，兜底"""
    sub_dims = dim_dict.get(dim_key, {}).get("sub_dimensions", [])
    for sd in sub_dims:
        if sd.get("name") == sub_name:
            return sd.get("weight", default_weight)
    return default_weight


def _scan_products() -> list:
    """扫描产品目录，返回产品名称列表"""
    prod_dir = os.path.join(HERMES_HOME, "L5孵化室", "产品开发")
    if not os.path.isdir(prod_dir):
        return []
    return sorted([
        d for d in os.listdir(prod_dir)
        if os.path.isdir(os.path.join(prod_dir, d)) and not d.startswith("_")
    ])


def _scan_features(product_name: str) -> list:
    """扫描某个产品的feature目录/文件，返回feature名称列表"""
    prod_dir = os.path.join(HERMES_HOME, "L5孵化室", "产品开发", product_name)
    if not os.path.isdir(prod_dir):
        return []
    candidates = []
    # 扫描feature目录
    for item in os.listdir(prod_dir):
        item_path = os.path.join(prod_dir, item)
        if item.startswith("_"):
            continue
        if os.path.isdir(item_path) and (item.startswith("feature-") or item.startswith("F-")):
            candidates.append(item)
        elif os.path.isfile(item_path) and item.endswith(".md") and not item.startswith("_"):
            # 也可能是单文件feature描述
            candidates.append(item.replace(".md", ""))
    return sorted(candidates)


def _scan_evolution_logs(product_name: str = None) -> list:
    """扫描进化日志，获取与产品相关的记录"""
    evo_dir = os.path.join(HERMES_HOME, "L5孵化室", "进化日志")
    if not os.path.isdir(evo_dir):
        return []
    all_logs = sorted(
        [f for f in os.listdir(evo_dir) if f.endswith(".json") and f.startswith("gaia_")],
        reverse=True
    )[:30]
    return [os.path.join(evo_dir, f) for f in all_logs]


def _count_product_iterations(product_name: str, feature_name: str = None) -> int:
    """粗略统计某个产品/feature在进化日志中的迭代次数"""
    logs = _scan_evolution_logs(product_name)
    count = 0
    for log_path in logs:
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 检查内容中是否提到产品名或feature名
            raw = json.dumps(data, ensure_ascii=False)
            if product_name in raw:
                if feature_name is None or feature_name in raw:
                    count += 1
        except Exception:
            continue
    return count


# ── 宏观层评估：商业竞争力 ──

def three_layer_assess_macro(l0: L0Output = None) -> MacroAssessmentOutput:
    """宏观层评估：扫描所有产品/项目，评估商业竞争力"""
    log("三层评估[宏观层]启动 — 商业竞争力评估...")
    cfg = three_layer_config()
    macro_cfg = cfg.get("macro_layer", {})
    dims = macro_cfg.get("evaluation_dimensions", {})
    thresholds = macro_cfg.get("thresholds", {})

    out = MacroAssessmentOutput()
    products = _scan_products()

    if not products:
        log("  无产品数据，宏观层评估跳过")
        out.status = "no_data"
        return out

    # 收集L0资产数据作为评分上下文
    total_skills = l0.assets.skills if l0 else 0
    total_emp = l0.assets.employees if l0 else 0

    for prod in products:
        prod_dir = os.path.join(HERMES_HOME, "L5孵化室", "产品开发", prod)
        features = _scan_features(prod)
        evo_count = _count_product_iterations(prod)

        # ── 子维度评分 (0-10)，基于可量化数据估算 ──
        # 这些评分会随真实数据接入而精确化；当前基于资产启发式

        # 目标客户明确度: 产品目录下是否有PRD/README/用户画像文档
        has_prd = any(f.endswith(".md") and ("prd" in f.lower() or "readme" in f.lower() or "用户" in f or "persona" in f.lower()) for f in os.listdir(prod_dir)) if os.path.isdir(prod_dir) else False
        customer_clarity = 7.0 if has_prd else (3.0 if len(features) > 0 else 1.0)

        # 真问题解决深度: feature数量+迭代次数作为代理指标
        problem_depth = min(5.0 + min(evo_count / 5, 5.0), 10.0) if evo_count > 0 else min(len(features) * 1.5, 5.0)

        # 护城河强度: 是否有代码资产库引用、技能数
        code_dir = os.path.join(HERMES_HOME, "L1图书馆", "代码资产库")
        prod_code_refs = 0
        if os.path.isdir(code_dir):
            for cd in os.listdir(code_dir):
                cd_path = os.path.join(code_dir, cd)
                if os.path.isdir(cd_path):
                    # 检查目录名或内容是否引用产品名
                    if prod.lower() in cd.lower():
                        prod_code_refs += 1
        moat = min(2.0 + prod_code_refs * 1.5, 10.0)

        # 商业竞争力总分
        comp_weight = _get_weight_safely(dims, "business_competitiveness", "目标客户明确度", 0.30)
        prob_weight = _get_weight_safely(dims, "business_competitiveness", "真问题解决深度", 0.40)
        moat_weight = _get_weight_safely(dims, "business_competitiveness", "护城河强度", 0.30)
        competitiveness = round(
            customer_clarity * comp_weight +
            problem_depth * prob_weight +
            moat * moat_weight, 2
        )

        # 细分领域定位: 产品名中是否包含领域关键词
        domain_keywords = ["智能", "AI", "分析", "自动化", "数据", "平台", "引擎", "工具", "助手", "代理"]
        has_domain_keyword = any(kw in prod for kw in domain_keywords)
        domain_positioning = 6.0 if has_domain_keyword else 3.0

        # 行业标杆对标: 使用技能数作为行业知识深度的代理
        industry_benchmark = min(3.0 + total_skills * 0.1, 8.0)

        # 差异化优势: feature数量多说明有独特功能
        diff_advantage = min(3.0 + len(features) * 0.5, 8.0)

        dp_weight1 = _get_weight_safely(dims, "domain_penetration", "细分领域定位", 0.30)
        dp_weight2 = _get_weight_safely(dims, "domain_penetration", "行业标杆对标", 0.40)
        dp_weight3 = _get_weight_safely(dims, "domain_penetration", "差异化优势", 0.30)
        penetration = round(
            domain_positioning * dp_weight1 +
            industry_benchmark * dp_weight2 +
            diff_advantage * dp_weight3, 2
        )

        # AI for Business成熟度
        ai_depth = min(2.0 + total_emp * 0.3, 8.0)  # 有AI员工团队
        scenario_closure = min(2.0 + len(features) * 0.5, 8.0)  # feature多闭环度高
        biz_value = min(2.0 + evo_count * 0.3, 7.0)  # 迭代多说明有价值

        ai_w1 = _get_weight_safely(dims, "ai_business_maturity", "AI嵌入深度", 0.40)
        ai_w2 = _get_weight_safely(dims, "ai_business_maturity", "场景闭环度", 0.30)
        ai_w3 = _get_weight_safely(dims, "ai_business_maturity", "业务价值可量化", 0.30)
        maturity = round(
            ai_depth * ai_w1 +
            scenario_closure * ai_w2 +
            biz_value * ai_w3, 2
        )

        # 加权总分
        macro_weight = dims.get("business_competitiveness", {}).get("weight", 0.40)
        domain_weight = dims.get("domain_penetration", {}).get("weight", 0.35)
        ai_weight = dims.get("ai_business_maturity", {}).get("weight", 0.25)
        overall = round(
            competitiveness * macro_weight +
            penetration * domain_weight +
            maturity * ai_weight, 2
        )

        item = MacroAssessmentItem(
            product_name=prod,
            business_competitiveness=competitiveness,
            domain_penetration=penetration,
            ai_business_maturity=maturity,
            overall_score=overall,
            sub_scores={
                "customer_clarity": customer_clarity,
                "problem_depth": problem_depth,
                "moat": moat,
                "domain_positioning": domain_positioning,
                "industry_benchmark": industry_benchmark,
                "diff_advantage": diff_advantage,
                "ai_depth": ai_depth,
                "scenario_closure": scenario_closure,
                "biz_value": biz_value,
            },
            evidence=[
                f"feature数: {len(features)}",
                f"迭代次数: {evo_count}",
                f"代码资产引用: {prod_code_refs}",
                f"有PRD/README: {'是' if has_prd else '否'}",
            ],
        )
        out.items.append(item)
        log(f"  [{prod}] 竞争力={competitiveness} 穿透度={penetration} AI成熟度={maturity} → 总分={overall}")

    # 汇总
    if out.items:
        scores = [i.overall_score for i in out.items]
        out.overall_avg_score = round(sum(scores) / len(scores), 2)
        out.strongest_product = max(out.items, key=lambda i: i.overall_score).product_name
        out.weakest_product = min(out.items, key=lambda i: i.overall_score).product_name

        # 找出最弱维度
        avg_comp = sum(i.business_competitiveness for i in out.items) / len(out.items)
        avg_pen = sum(i.domain_penetration for i in out.items) / len(out.items)
        avg_mat = sum(i.ai_business_maturity for i in out.items) / len(out.items)
        dim_map = {"商业竞争力": avg_comp, "领域穿透度": avg_pen, "AI成熟度": avg_mat}
        out.weakest_dimension = min(dim_map, key=dim_map.get)

    log(f"  宏观层完成: {len(out.items)}个产品 平均分={out.overall_avg_score} 最强={out.strongest_product} 最弱维度={out.weakest_dimension}")
    return out


# ── 中观层评估：饱和攻击状态 ──

def three_layer_assess_meso() -> MesoAssessmentOutput:
    """中观层评估：评估战役层面的饱和攻击状态"""
    log("三层评估[中观层]启动 — 饱和攻击状态评估...")
    cfg = three_layer_config()
    meso_cfg = cfg.get("meso_layer", {})
    dims = meso_cfg.get("evaluation_dimensions", {})
    thresholds = meso_cfg.get("thresholds", {})

    out = MesoAssessmentOutput()
    products = _scan_products()

    if not products:
        log("  无产品数据，中观层评估跳过")
        out.status = "no_data"
        return out

    for prod in products:
        features = _scan_features(prod)
        evo_count = _count_product_iterations(prod)

        # 战场聚焦度评估
        # 产品越多 → 可能多线作战
        total_products = len(products)
        battlefield_focus_raw = max(10.0 - (total_products - 1) * 2.0, 1.0)

        # 该产品feature是否集中在一个方向
        feature_focus_penalty = min(len(features) * 0.5, 3.0) if len(features) > 5 else 0
        battlefield_focus = round(max(battlefield_focus_raw - feature_focus_penalty, 1.0), 2)

        # 资源集中度: 迭代次数占全部产品比例
        total_evo = sum(_count_product_iterations(p) for p in products)
        resource_concentration = round(min((evo_count / max(total_evo, 1)) * 10, 10.0), 2) if total_evo > 0 else 5.0

        bf_weight1 = _get_weight_safely(dims, "battlefield_focus", "战场收敛度", 0.50)
        bf_weight2 = _get_weight_safely(dims, "battlefield_focus", "资源集中度", 0.50)
        focus_score = round(battlefield_focus * bf_weight1 + resource_concentration * bf_weight2, 2)

        # 单点打穿度
        # 完成度: 有feature说明在推进
        completion = min(3.0 + len(features) * 0.8, 9.0)
        # 迭代深度: 迭代次数作为代理
        iteration_depth = min(2.0 + evo_count * 0.5, 9.0)
        # 验证闭环: 是否有日志记录
        has_validation = evo_count > 3
        validation = 7.0 if has_validation else 3.0

        sp_w1 = _get_weight_safely(dims, "single_point_penetration", "完成度", 0.40)
        sp_w2 = _get_weight_safely(dims, "single_point_penetration", "迭代深度", 0.30)
        sp_w3 = _get_weight_safely(dims, "single_point_penetration", "验证闭环", 0.30)
        penetration_score = round(completion * sp_w1 + iteration_depth * sp_w2 + validation * sp_w3, 2)

        # 实事求是门禁
        # 数据真实性: 进化日志可回溯
        data_truth = min(5.0 + min(evo_count, 5), 9.0) if evo_count > 0 else 3.0
        # 识别坦诚度: 产品目录下是否有复盘/反思文档
        has_review = any("复盘" in f or "反思" in f or "retro" in f.lower() for f in os.listdir(os.path.join(HERMES_HOME, "L5孵化室", "产品开发", prod))) if os.path.isdir(os.path.join(HERMES_HOME, "L5孵化室", "产品开发", prod)) else False
        honesty = 7.0 if has_review else 4.0

        tg_w1 = _get_weight_safely(dims, "truth_gate", "数据真实性", 0.50)
        tg_w2 = _get_weight_safely(dims, "truth_gate", "识别坦诚度", 0.50)
        truth_score = round(data_truth * tg_w1 + honesty * tg_w2, 2)

        # 加权总分
        bf_dim_weight = dims.get("battlefield_focus", {}).get("weight", 0.35)
        sp_dim_weight = dims.get("single_point_penetration", {}).get("weight", 0.40)
        tg_dim_weight = dims.get("truth_gate", {}).get("weight", 0.25)
        overall = round(
            focus_score * bf_dim_weight +
            penetration_score * sp_dim_weight +
            truth_score * tg_dim_weight, 2
        )

        # 多线作战预警
        multi_front = total_products > 2 and resource_concentration < 3.0

        item = MesoAssessmentItem(
            project_name=prod,
            battlefield_focus=focus_score,
            single_point_penetration=penetration_score,
            truth_gate=truth_score,
            overall_score=overall,
            sub_scores={
                "battlefield_focus_raw": battlefield_focus,
                "resource_concentration": resource_concentration,
                "completion": completion,
                "iteration_depth": iteration_depth,
                "validation": validation,
                "data_truth": data_truth,
                "honesty": honesty,
            },
            evidence=[
                f"feature数: {len(features)}",
                f"迭代次数: {evo_count}",
                f"全局产品数: {total_products}",
                f"有复盘文档: {'是' if has_review else '否'}",
            ],
            current_battlefield=f"{prod} ({len(features)}个feature)",
            multi_front_warning=multi_front,
        )
        out.items.append(item)
        log(f"  [{prod}] 战场聚焦={focus_score} 单点打穿={penetration_score} 实事求是={truth_score} → 总分={overall}{' ⚠️多线作战' if multi_front else ''}")
        if multi_front:
            out.multi_front_projects.append(prod)

    # 汇总
    if out.items:
        scores = [i.overall_score for i in out.items]
        out.overall_avg_score = round(sum(scores) / len(scores), 2)

        avg_focus = sum(i.battlefield_focus for i in out.items) / len(out.items)
        avg_pen = sum(i.single_point_penetration for i in out.items) / len(out.items)
        avg_truth = sum(i.truth_gate for i in out.items) / len(out.items)
        dim_map = {"战场聚焦度": avg_focus, "单点打穿度": avg_pen, "实事求是门禁": avg_truth}
        out.weakest_dimension = min(dim_map, key=dim_map.get)

    log(f"  中观层完成: {len(out.items)}个项目 平均分={out.overall_avg_score} 最弱维度={out.weakest_dimension} 多线预警={len(out.multi_front_projects)}个")
    return out


# ── 微观层评估：Feature打磨度 ──

def three_layer_assess_micro() -> MicroAssessmentOutput:
    """微观层评估：扫描所有feature，评估打磨深度"""
    log("三层评估[微观层]启动 — Feature打磨度评估...")
    cfg = three_layer_config()
    micro_cfg = cfg.get("micro_layer", {})
    dims = micro_cfg.get("evaluation_dimensions", {})
    thresholds = micro_cfg.get("thresholds", {})

    out = MicroAssessmentOutput()
    products = _scan_products()

    if not products:
        log("  无产品数据，微观层评估跳过")
        out.status = "no_data"
        return out

    iteration_gate_min = thresholds.get("iteration_gate_min", 3) if thresholds else 3

    for prod in products:
        features = _scan_features(prod)
        if not features:
            continue

        for feat in features:
            evo_count = _count_product_iterations(prod, feat)

            # ── 迭代深度 ──
            iter_count = evo_count
            passed_gate = iter_count >= iteration_gate_min
            iteration_score = min(iter_count * 2.5, 10.0)  # 4次迭代=满分

            # 迭代质量: 多次迭代说明质量在提升
            iter_quality = min(3.0 + iter_count * 1.0, 9.0) if iter_count > 0 else 1.0

            it_w1 = _get_weight_safely(dims, "iteration_depth", "迭代次数", 0.50)
            it_w2 = _get_weight_safely(dims, "iteration_depth", "迭代质量", 0.50)
            iteration_depth_score = round(iteration_score * it_w1 + iter_quality * it_w2, 2)

            # ── 交付评分 ──
            target_gap = max(10.0 - iteration_depth_score, 0.0)
            user_satisfaction = min(3.0 + iter_count * 1.2, 9.0)

            dl_w1 = _get_weight_safely(dims, "delivery_score", "10/10目标差距", 0.60)
            dl_w2 = _get_weight_safely(dims, "delivery_score", "使用者满意度", 0.40)
            delivery = round(
                (10.0 - target_gap) * dl_w1 + user_satisfaction * dl_w2, 2
            )

            # ── Feature RORY完成度 ──
            # 是否有资产提取: 检查代码资产库中是否有该feature的引用
            code_dir = os.path.join(HERMES_HOME, "L1图书馆", "代码资产库")
            has_asset_extract = False
            if os.path.isdir(code_dir):
                for cd in os.listdir(code_dir):
                    if feat.lower() in cd.lower() or prod.lower() in cd.lower():
                        has_asset_extract = True
                        break
            reusable_assets = 7.0 if has_asset_extract else (3.0 if iter_count > 0 else 1.0)

            # 知识沉淀: 是否有文档记录
            knowledge = min(3.0 + iter_count * 0.8, 9.0)

            rory_w1 = _get_weight_safely(dims, "feature_rory", "可复用资产提取", 0.50)
            rory_w2 = _get_weight_safely(dims, "feature_rory", "知识沉淀度", 0.50)
            rory_score = round(reusable_assets * rory_w1 + knowledge * rory_w2, 2)

            # 加权总分
            it_dim_weight = dims.get("iteration_depth", {}).get("weight", 0.35)
            dl_dim_weight = dims.get("delivery_score", {}).get("weight", 0.35)
            rory_dim_weight = dims.get("feature_rory", {}).get("weight", 0.30)
            overall = round(
                iteration_depth_score * it_dim_weight +
                delivery * dl_dim_weight +
                rory_score * rory_dim_weight, 2
            )

            item = MicroAssessmentItem(
                feature_name=feat,
                project_name=prod,
                iteration_depth=iteration_depth_score,
                delivery_score=delivery,
                feature_rory=rory_score,
                overall_score=overall,
                sub_scores={
                    "iteration_count_score": iteration_score,
                    "iteration_quality": iter_quality,
                    "target_gap": target_gap,
                    "user_satisfaction": user_satisfaction,
                    "reusable_assets": reusable_assets,
                    "knowledge": knowledge,
                },
                evidence=[
                    f"实际迭代次数: {iter_count}",
                    f"迭代门限: {iteration_gate_min}次",
                    f"有代码资产: {'是' if has_asset_extract else '否'}",
                ],
                iteration_count=iter_count,
                passed_three_gate=passed_gate,
                gap_to_target=round(target_gap, 1),
            )
            out.items.append(item)
            log(f"    [{prod}/{feat}] 迭代深度={iteration_depth_score} 交付={delivery} RORY={rory_score} → 总分={overall} {'✅过门' if passed_gate else '❌未过门'}")

            if not passed_gate:
                out.features_below_gate.append(f"{prod}/{feat}")

    # 汇总
    if out.items:
        scores = [i.overall_score for i in out.items]
        out.overall_avg_score = round(sum(scores) / len(scores), 2)

        avg_iter = sum(i.iteration_depth for i in out.items) / len(out.items)
        avg_del = sum(i.delivery_score for i in out.items) / len(out.items)
        avg_rory = sum(i.feature_rory for i in out.items) / len(out.items)
        dim_map = {"迭代深度": avg_iter, "交付评分": avg_del, "RORY完成度": avg_rory}
        out.weakest_dimension = min(dim_map, key=dim_map.get)

    log(f"  微观层完成: {len(out.items)}个feature 平均分={out.overall_avg_score} 最弱维度={out.weakest_dimension} 未过门={len(out.features_below_gate)}个")
    return out


def run_three_layer_assessment(l0: L0Output = None) -> ThreeLayerAssessmentOutput:
    """运行完整三层评估，产出综合报告"""
    log("=" * 50)
    log(" 三层评估引擎启动 — 宏观·中观·微观")
    log("=" * 50)

    cfg = three_layer_config()

    # 宏观层
    if cfg.get("macro_layer", {}).get("enabled", True):
        macro_out = three_layer_assess_macro(l0=l0)
    else:
        log("  宏观层已禁用")
        macro_out = MacroAssessmentOutput(status="disabled")

    # 中观层
    if cfg.get("meso_layer", {}).get("enabled", True):
        meso_out = three_layer_assess_meso()
    else:
        log("  中观层已禁用")
        meso_out = MesoAssessmentOutput(status="disabled")

    # 微观层
    if cfg.get("micro_layer", {}).get("enabled", True):
        micro_out = three_layer_assess_micro()
    else:
        log("  微观层已禁用")
        micro_out = MicroAssessmentOutput(status="disabled")

    # 综合健康度: 三层平均分加权
    scores = []
    if macro_out.items:
        scores.append(macro_out.overall_avg_score)
    if meso_out.items:
        scores.append(meso_out.overall_avg_score)
    if micro_out.items:
        scores.append(micro_out.overall_avg_score)

    overall_health = round(sum(scores) / len(scores), 2) if scores else 0.0

    out = ThreeLayerAssessmentOutput(
        macro=macro_out,
        meso=meso_out,
        micro=micro_out,
        overall_health_score=overall_health,
    )

    # 写入评估报告
    output_cfg = cfg.get("output", {})
    report_dir = output_cfg.get("output_dir", os.path.join(HERMES_HOME, "L5孵化室", "三层评估"))
    os.makedirs(report_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(report_dir, f"three_layer_assessment_{ts}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(to_dict(out), f, ensure_ascii=False, indent=2)
    out.report_path = report_path
    log(f"  评估报告写入: {report_path}")

    # 也生成人类可读的Markdown报告
    md_path = os.path.join(report_dir, f"three_layer_assessment_{ts}.md")
    _write_markdown_report(md_path, out)
    log(f"  Markdown报告: {md_path}")

    log("=" * 50)
    log(f" 三层评估完成 | 宏观={macro_out.overall_avg_score if macro_out.items else 'N/A'} "
        f"中观={meso_out.overall_avg_score if meso_out.items else 'N/A'} "
        f"微观={micro_out.overall_avg_score if micro_out.items else 'N/A'} | "
        f"综合健康度={overall_health}")
    log("=" * 50)

    return out


def _write_markdown_report(path: str, assessment: ThreeLayerAssessmentOutput):
    """将评估结果写成人类可读的Markdown报告"""
    lines = []
    lines.append("# 盖娅进化大脑 — 宏观·中观·微观 三层评估报告")
    lines.append(f"")
    lines.append(f"**生成时间**: {assessment.timestamp}")
    lines.append(f"**综合健康度**: {assessment.overall_health_score}/10")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 一、宏观层 — 商业竞争力评估")
    lines.append("")
    macro = assessment.macro
    if macro.items:
        lines.append(f"| 产品 | 商业竞争力 | 领域穿透度 | AI成熟度 | 总分 |")
        lines.append(f"|------|-----------|-----------|---------|-----:|")
        for item in sorted(macro.items, key=lambda x: x.overall_score, reverse=True):
            lines.append(f"| {item.product_name} | {item.business_competitiveness} | {item.domain_penetration} | {item.ai_business_maturity} | **{item.overall_score}** |")
        lines.append("")
        lines.append(f"- **平均分**: {macro.overall_avg_score}")
        lines.append(f"- **最强产品**: {macro.strongest_product}")
        lines.append(f"- **最弱产品**: {macro.weakest_product}")
        lines.append(f"- **最弱维度**: {macro.weakest_dimension}")
    else:
        lines.append("*无产品数据*")
    lines.append("")
    lines.append("## 二、中观层 — 饱和攻击状态评估")
    lines.append("")
    meso = assessment.meso
    if meso.items:
        lines.append(f"| 项目 | 战场聚焦 | 单点打穿 | 实事求是 | 总分 | 预警 |")
        lines.append(f"|------|---------|---------|---------|-----:|:----:|")
        for item in sorted(meso.items, key=lambda x: x.overall_score, reverse=True):
            warn = "⚠️" if item.multi_front_warning else ""
            lines.append(f"| {item.project_name} | {item.battlefield_focus} | {item.single_point_penetration} | {item.truth_gate} | **{item.overall_score}** | {warn} |")
        lines.append("")
        lines.append(f"- **平均分**: {meso.overall_avg_score}")
        lines.append(f"- **最弱维度**: {meso.weakest_dimension}")
        if meso.multi_front_projects:
            lines.append(f"- **⚠️ 多线作战预警项目**: {', '.join(meso.multi_front_projects)}")
    else:
        lines.append("*无项目数据*")
    lines.append("")
    lines.append("## 三、微观层 — Feature打磨度评估")
    lines.append("")
    micro = assessment.micro
    if micro.items:
        lines.append(f"| 产品/Feature | 迭代深度 | 交付评分 | RORY | 总分 | 迭代次数 | 过门? |")
        lines.append(f"|-------------|---------|---------|------|-----:|:-------:|:----:|")
        for item in sorted(micro.items, key=lambda x: x.overall_score, reverse=True):
            gate = "✅" if item.passed_three_gate else "❌"
            lines.append(f"| {item.project_name}/{item.feature_name} | {item.iteration_depth} | {item.delivery_score} | {item.feature_rory} | **{item.overall_score}** | {item.iteration_count} | {gate} |")
        lines.append("")
        lines.append(f"- **平均分**: {micro.overall_avg_score}")
        lines.append(f"- **最弱维度**: {micro.weakest_dimension}")
        if micro.features_below_gate:
            lines.append(f"- **❌ 未过三次迭代门 ({len(micro.features_below_gate)}个)**:")
            for f in micro.features_below_gate:
                lines.append(f"  - {f}")
    else:
        lines.append("*无Feature数据*")
    lines.append("")
    lines.append("---")
    lines.append("")
    if macro.items:
        lines.append("### 宏观层改进建议")
        weakest_prod = min(macro.items, key=lambda x: x.overall_score)
        lines.append(f"- **{weakest_prod.product_name}** 总分最低 ({weakest_prod.overall_score}), 建议优先提升")
        if weakest_prod.business_competitiveness < 5:
            lines.append("  - 商业竞争力偏低: 明确目标客户画像，验证真问题")
        if weakest_prod.domain_penetration < 5:
            lines.append("  - 领域穿透度不足: 对标行业标杆，聚焦细分领域")
        if weakest_prod.ai_business_maturity < 5:
            lines.append("  - AI成熟度偏低: 推动AI从Demo走向生产级场景闭环")
    if meso.items:
        lines.append("")
        lines.append("### 中观层改进建议")
        widest = max(meso.items, key=lambda x: x.multi_front_warning)
        if widest.multi_front_warning:
            lines.append(f"- **{widest.project_name}** 存在多线作战风险, 建议收敛战场")
        weakest_meso = min(meso.items, key=lambda x: x.overall_score)
        lines.append(f"- **{weakest_meso.project_name}** 总分最低, 检查单点是否真正打穿")
    if micro.items:
        lines.append("")
        lines.append("### 微观层改进建议")
        below = [i for i in micro.items if not i.passed_three_gate]
        if below:
            lines.append(f"- **{len(below)}个feature** 未过3次迭代门, 建议持续打磨到10/10")
        lowest_rory = min(micro.items, key=lambda x: x.feature_rory)
        lines.append(f"- **{lowest_rory.project_name}/{lowest_rory.feature_name}** RORY最低, 建议萃取可复用资产")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ════════════════════════════════════════════════════════════════
#  入口
# ════════════════════════════════════════════════════════════════

def run_full_cycle(dry_run: bool = False):
    """全七层一次运行"""
    start = time.time()
    log("=" * 50)
    log(" 盖娅进化大脑 — 完整进化循环开始" + (" [DRY RUN]" if dry_run else ""))
    log("=" * 50)

    l0 = layer0_sense()
    l1 = layer1_analyze(l0)
    l2 = layer2_combine(l0, l1)
    l3 = layer3_create(l2, l0=l0, dry_run=dry_run)
    l4 = layer4_feed(l3)
    l5 = layer5_watch()
    l6 = layer6_trace(start, l0, l1, l2, l3, l4, l5)

    log("=" * 50)
    log(f" 七层飞轮完成 | {l0.assets.employees}员工 {len(l1.gaps)}缺口 {len(l2.propositions)}方案 {len(l3.creations)}产出 | {l6.cycle.duration_seconds}s")
    log("=" * 50)

    # ── 附加：三层评估引擎（与七层飞轮并行，不破坏L0-L6逻辑） ──
    log("")
    log("─" * 40)
    log(" 启动三层评估引擎（宏观·中观·微观）...")
    log("─" * 40)
    try:
        three_layer_out = run_three_layer_assessment(l0=l0)
        # 将三层评估结果作为信号追加到L0，供下个周期感知
        if three_layer_out.status == "ok":
            l0.signals.append({
                "source": "三层评估引擎",
                "summary": f"宏观={three_layer_out.macro.overall_avg_score} 中观={three_layer_out.meso.overall_avg_score} 微观={three_layer_out.micro.overall_avg_score} 综合健康度={three_layer_out.overall_health_score}",
                "report_path": three_layer_out.report_path,
            })
            log(f"  三层评估信号已注入L0感知层")
    except Exception as e:
        log(f"  三层评估异常: {e}", "WARN")
        import traceback
        traceback.print_exc()

    # ── 附加：双三角模型 D2(审美积累) + D3(体系库)（与七层飞轮并行） ──
    log("")
    log("─" * 40)
    log(" 启动双三角模型 D2(审美积累) + D3(体系库)...")
    log("─" * 40)

    # D2 审美积累
    if _HAVE_D2:
        try:
            d2_result = run_aesthetics_collection(verbose=False)
            l0.signals.append({
                "source": "双三角模型-D2审美积累",
                "summary": f"采集{d2_result['total_practices']}个最佳实践, 平均审美指数={d2_result['avg_aesthetic_score']}, TOP={d2_result['top_practices'][0]['title'] if d2_result['top_practices'] else 'N/A'}",
            })
            log(f"  ✅ D2审美积累: {d2_result['total_practices']}个实践, 平均分={d2_result['avg_aesthetic_score']}")
        except Exception as e:
            log(f"  ❌ D2审美积累异常: {e}", "WARN")
            import traceback
            traceback.print_exc()
    else:
        log("  ⏭️ D2审美积累模块未安装，跳过")

    # D3 体系库
    if _HAVE_D3:
        try:
            d3_result = run_system_library_build(verbose=False)
            l0.signals.append({
                "source": "双三角模型-D3体系库",
                "summary": f"建设{d3_result['total_systems']}个体系框架, 覆盖{len(d3_result['domain_distribution'])}个领域, TOP={d3_result['top_systems'][0]['title'] if d3_result['top_systems'] else 'N/A'}",
            })
            log(f"  ✅ D3体系库: {d3_result['total_systems']}个体系, 领域分布={d3_result['domain_distribution']}")
        except Exception as e:
            log(f"  ❌ D3体系库异常: {e}", "WARN")
            import traceback
            traceback.print_exc()
    else:
        log("  ⏭️ D3体系库模块未安装，跳过")

    # ── MiroFish MF-07: ReACT日报生成 ──
    try:
        from gaia_react_reporter import plan_report, generate_section, integrate_report
        context = f"盖娅进化大脑第{getattr(l6, 'cycle', None) and l6.cycle.layers_executed or '7层'}飞轮完成 | {l0.assets.employees}员工 {len(l1.gaps)}缺口 {len(l2.propositions)}方案 {len(l3.creations)}产出"
        outline = plan_report(context)
        sections = []
        for sec in outline.get("sections", [])[:3]:  # 最多3章
            sec_text = generate_section(sec, {"scan_employees": lambda: l0.assets.employees})
            sections.append(sec_text)
        report = integrate_report(sections)
        report_dir = os.path.join(HERMES_HOME, "L5孵化室", "进化日志")
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, f"react_daily_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        l0.signals.append({
            "source": "MiroFish-ReACT日报",
            "summary": f"生成 {len(sections)} 章深度报告 → {os.path.basename(report_path)}"
        })
        log(f"  ✅ MF-07 ReACT日报: {report_path}")
    except ImportError:
        pass  # gaia_react_reporter 未安装
    except Exception as e:
        log(f"  ⚠️ MF-07 ReACT日报异常: {e}", "WARN")

    log("=" * 50)
    log(f" 循环完成 | 综合健康度: {three_layer_out.overall_health_score if 'three_layer_out' in dir() else 'N/A'}")
    log("=" * 50)

    return {
        "cycle": to_dict(l6.cycle),
        "assets": to_dict(l0.assets),
        "gaps": [to_dict(g) for g in l1.gaps],
        "propositions": [to_dict(p) for p in l2.propositions],
    }


def show_status():
    """显示盖娅进化大脑状态"""
    print("=" * 50)
    print("  盖娅进化大脑 · 状态")
    print("=" * 50)

    files = {
        "调度器": os.path.join(SCRIPTS_DIR, "gaia_cortex.py"),
        "配置": os.path.join(SCRIPTS_DIR, "gaia_cortex_config.yaml"),
        "三层评估配置": os.path.join(SCRIPTS_DIR, "gaia_cortex_three_layer.yaml"),
        "数据契约": os.path.join(SCRIPTS_DIR, "_data_contract.py"),
        "3+X窗口": os.path.join(HERMES_HOME, "L0前厅", "3+X窗口", "窗口X2_盖娅进化大脑_context.md"),
        "进化日志目录": os.path.join(HERMES_HOME, "L5孵化室", "进化日志"),
        "三层评估目录": os.path.join(HERMES_HOME, "L5孵化室", "三层评估"),
    }
    for name, path in files.items():
        exists = os.path.isfile(path) if not (path.endswith("进化日志") or path.endswith("三层评估")) else os.path.isdir(path)
        print(f"  {'✅' if exists else '❌'} {name}: {path}")

    evo_dir = os.path.join(HERMES_HOME, "L5孵化室", "进化日志")
    if os.path.isdir(evo_dir):
        logs = sorted([f for f in os.listdir(evo_dir) if f.startswith("gaia_")], reverse=True)[:5]
        print(f"  📋 进化日志: {len(logs)} 条")
        if logs:
            print(f"     最近: {logs[0]}")

    # 三层评估状态
    assess_dir = os.path.join(HERMES_HOME, "L5孵化室", "三层评估")
    if os.path.isdir(assess_dir):
        assess_logs = sorted([f for f in os.listdir(assess_dir) if f.endswith(".json") and f.startswith("three_layer_")], reverse=True)[:3]
        assess_mds = sorted([f for f in os.listdir(assess_dir) if f.endswith(".md") and f.startswith("three_layer_")], reverse=True)[:3]
        print(f"  📋 三层评估报告: {len(assess_logs)} 条JSON + {len(assess_mds)} 条Markdown")
        if assess_mds:
            print(f"     最近: {assess_mds[0]}")
        if assess_logs:
            # 读取最近一条的摘要
            try:
                with open(os.path.join(assess_dir, assess_logs[0]), "r", encoding="utf-8") as f:
                    last_assess = json.load(f)
                health = last_assess.get("overall_health_score", "N/A")
                print(f"     综合健康度: {health}/10")
            except Exception:
                pass

    config_ok = os.path.isfile(os.path.join(SCRIPTS_DIR, "gaia_cortex_config.yaml"))
    contract_ok = os.path.isfile(os.path.join(SCRIPTS_DIR, "_data_contract.py"))
    print(f"  🟢 就绪度: {'全系统就绪' if config_ok and contract_ok else '部分缺失'}")
    print()


# ════════════════════════════════════════════════════════════════
#  CLI入口
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="盖娅进化大脑 — 七层进化调度器")
    parser.add_argument("--layer", type=str, help="只运行特定层 (L0-L6)")
    parser.add_argument("--daemon", action="store_true", help="值守模式 (30分钟循环)")
    parser.add_argument("--status", action="store_true", help="显示状态")
    parser.add_argument("--dry-run", action="store_true", help="预览模式 (不执行创造)")
    parser.add_argument("--assess", action="store_true", help="只运行三层评估引擎 (宏观·中观·微观)")
    parser.add_argument("--assess-layer", type=str, help="只运行特定评估层 (macro/meso/micro)")
    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.assess:
        l0 = layer0_sense()
        result = run_three_layer_assessment(l0=l0)
        print(to_json(result))
    elif args.assess_layer:
        l0 = layer0_sense()
        if args.assess_layer == "macro":
            result = three_layer_assess_macro(l0=l0)
        elif args.assess_layer == "meso":
            result = three_layer_assess_meso()
        elif args.assess_layer == "micro":
            result = three_layer_assess_micro()
        else:
            print(f"未知评估层: {args.assess_layer}，可选: macro/meso/micro")
            sys.exit(1)
        print(to_json(result))
    elif args.layer:
        layers = {
            "L0": layer0_sense,
            "L1": lambda: layer1_analyze(layer0_sense()),
            "L2": lambda: layer2_combine(layer0_sense(), layer1_analyze(layer0_sense())),
            "L3": lambda: layer3_create(layer2_combine(layer0_sense(), layer1_analyze(layer0_sense())), dry_run=args.dry_run),
            "L4": lambda: layer4_feed(layer3_create(layer2_combine(layer0_sense(), layer1_analyze(layer0_sense())), dry_run=args.dry_run)),
            "L5": layer5_watch,
        }
        fn = layers.get(args.layer)
        if fn:
            result = fn()
            print(to_json(result))
        else:
            print(f"未知层: {args.layer}")
    elif args.daemon:
        log("值守模式启动，每30分钟循环... (Ctrl+C 停止)")
        try:
            while True:
                run_full_cycle(dry_run=False)
                time.sleep(1800)
        except KeyboardInterrupt:
            log("值守模式已停止")
    else:
        result = run_full_cycle(dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
