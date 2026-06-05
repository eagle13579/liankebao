#!/usr/bin/env python3
"""
matrix_backfeed.py — 盖娅矩阵反哺检测引擎
扫描 profile 目录下是否有新技能/心智模型产出，生成检测报告。

设计原则:
  1. 只检测不写入（纯扫描模式），写入由 backfeed_engine.py 处理
  2. 内容哈希去重：与母体已有内容相同则标记为"重复"而非"新增"
  3. 审计追踪：每次检测记录到日志

用法:
  python matrix_backfeed.py --profile <profile_name>
  python matrix_backfeed.py --profile <profile_name> --report out.json
  python matrix_backfeed.py --profile <profile_name> --verbose
  python matrix_backfeed.py --list-profiles
"""
import os
import sys
import json
import hashlib
import logging
import argparse
from datetime import datetime

# ── 全局路径 ──
HERMES = r"D:\向海容的知识库\wiki\wiki\记忆宫殿"
PROFILES_DIR = os.path.join(HERMES, "profiles")
SKILLS_MOTHER = os.path.join(HERMES, "skills")
POOL_DIR = os.path.join(HERMES, "L5孵化室", "五池", "模型池")
BACKFEED_LOG = os.path.join(HERMES, "_backfeed_archive", "backfeed_detect.log")
BACKFEED_ARCHIVE = os.path.join(HERMES, "_backfeed_archive")

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BACKFEED_LOG, encoding="utf-8")
    ]
)
logger = logging.getLogger("matrix_backfeed")


def ensure_dirs():
    """确保必要的目录存在"""
    os.makedirs(BACKFEED_ARCHIVE, exist_ok=True)


def compute_file_hash(filepath: str) -> str:
    """计算文件 SHA256 哈希"""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_mother_skill_hashes() -> set:
    """构建母体所有技能的 SHA256 哈希集合，用于去重"""
    hashes = set()
    if not os.path.isdir(SKILLS_MOTHER):
        return hashes
    for root, dirs, files in os.walk(SKILLS_MOTHER):
        for f in files:
            if f.endswith(".md"):
                fp = os.path.join(root, f)
                try:
                    hashes.add(compute_file_hash(fp))
                except Exception as e:
                    logger.warning("读取技能文件失败 %s: %s", fp, e)
    logger.debug("母体技能哈希集合: %d 个", len(hashes))
    return hashes


def build_mother_model_hashes() -> set:
    """构建母体心智模型哈希集合"""
    hashes = set()
    if not os.path.isdir(POOL_DIR):
        return hashes
    for f in os.listdir(POOL_DIR):
        if f.endswith(".md"):
            fp = os.path.join(POOL_DIR, f)
            try:
                hashes.add(compute_file_hash(fp))
            except Exception as e:
                logger.warning("读取模型文件失败 %s: %s", fp, e)
    return hashes


def scan_profile_skills(profile_name: str, mother_hashes: set) -> list:
    """
    扫描 profile/skills/ 下新增的 SKILL.md
    返回 [{type, name, file, size, hash, status}, ...]
    status: "new" | "duplicate" | "error"
    """
    candidates = []
    profile_skills_dir = os.path.join(PROFILES_DIR, profile_name, "skills")
    if not os.path.isdir(profile_skills_dir):
        logger.info("Profile %s 没有 skills/ 目录", profile_name)
        return candidates

    for root, dirs, files in os.walk(profile_skills_dir):
        for f in files:
            if f == "SKILL.md":
                fp = os.path.join(root, f)
                try:
                    content_hash = compute_file_hash(fp)
                    size = os.path.getsize(fp)
                    skill_name = os.path.basename(root)
                    status = "duplicate" if content_hash in mother_hashes else "new"
                    # 检查是否已反哺
                    mother_skill_path = os.path.join(
                        HERMES, "skills", "profiles", f"{profile_name}_{skill_name}.md"
                    )
                    if os.path.isfile(mother_skill_path):
                        mother_skill_hash = compute_file_hash(mother_skill_path)
                        if mother_skill_hash == content_hash:
                            status = "already_backfed"

                    candidates.append({
                        "type": "skill",
                        "name": f"{profile_name}_{skill_name}",
                        "file": fp,
                        "size": size,
                        "hash": content_hash,
                        "status": status,
                        "detected_at": datetime.now().isoformat()
                    })
                except Exception as e:
                    logger.error("扫描技能文件失败 %s: %s", fp, e)
                    candidates.append({
                        "type": "skill",
                        "name": os.path.basename(root),
                        "file": fp,
                        "size": 0,
                        "hash": "",
                        "status": "error",
                        "error": str(e)
                    })

    logger.info("Profile %s skills/: 发现 %d 个技能文件", profile_name, len(candidates))
    return candidates


def scan_profile_mental_models(profile_name: str, mother_hashes: set) -> list:
    """
    扫描 profile/mental_models/ 下新增的心智模型
    """
    candidates = []
    profile_model_dir = os.path.join(PROFILES_DIR, profile_name, "mental_models")
    if not os.path.isdir(profile_model_dir):
        logger.debug("Profile %s 没有 mental_models/ 目录", profile_name)
        return candidates

    for f in os.listdir(profile_model_dir):
        if f.endswith(".md"):
            fp = os.path.join(profile_model_dir, f)
            try:
                content_hash = compute_file_hash(fp)
                size = os.path.getsize(fp)
                status = "duplicate" if content_hash in mother_hashes else "new"

                # 检查是否已反哺
                mother_model_path = os.path.join(
                    POOL_DIR, f"{profile_name}_{f}"
                )
                if os.path.isfile(mother_model_path):
                    mother_model_hash = compute_file_hash(mother_model_path)
                    if mother_model_hash == content_hash:
                        status = "already_backfed"

                candidates.append({
                    "type": "mental_model",
                    "name": f"{profile_name}_{f}",
                    "file": fp,
                    "size": size,
                    "hash": content_hash,
                    "status": status,
                    "detected_at": datetime.now().isoformat()
                })
            except Exception as e:
                logger.error("扫描心智模型失败 %s: %s", fp, e)
                candidates.append({
                    "type": "mental_model",
                    "name": f,
                    "file": fp,
                    "size": 0,
                    "hash": "",
                    "status": "error",
                    "error": str(e)
                })

    logger.info("Profile %s mental_models/: 发现 %d 个模型文件", profile_name, len(candidates))
    return candidates


def scan_delegate_logs(profile_name: str) -> list:
    """
    扫描 profile/ 下的 delegate 日志（如果有 sessions/ 目录）
    返回可能包含新产出的会话列表
    """
    candidates = []
    sessions_dir = os.path.join(PROFILES_DIR, profile_name, "sessions")
    if not os.path.isdir(sessions_dir):
        return candidates

    try:
        session_files = sorted(
            [f for f in os.listdir(sessions_dir) if f.endswith(".json")],
            reverse=True
        )[:10]  # 最近10个会话
        for sf in session_files:
            fp = os.path.join(sessions_dir, sf)
            candidates.append({
                "type": "session_log",
                "name": sf,
                "file": fp,
                "size": os.path.getsize(fp),
                "detected_at": datetime.now().isoformat()
            })
    except Exception as e:
        logger.error("扫描 delegate 日志失败: %s", e)

    return candidates


def generate_report(profile_name: str, results: dict, output_path: str = None) -> dict:
    """生成检测报告"""
    report = {
        "report_id": hashlib.md5(f"{profile_name}_{datetime.now().isoformat()}".encode()).hexdigest()[:12],
        "profile": profile_name,
        "scanned_at": datetime.now().isoformat(),
        "summary": {
            "total_candidates": (
                len(results.get("skills", []))
                + len(results.get("mental_models", []))
                + len(results.get("delegate_logs", []))
            ),
            "new_skills": sum(1 for s in results.get("skills", []) if s.get("status") == "new"),
            "duplicate_skills": sum(1 for s in results.get("skills", []) if s.get("status") == "duplicate"),
            "already_backfed": sum(1 for s in results.get("skills", []) if s.get("status") == "already_backfed"),
            "new_models": sum(1 for m in results.get("mental_models", []) if m.get("status") == "new"),
            "new_session_logs": len(results.get("delegate_logs", [])),
            "errors": sum(1 for s in results.get("skills", []) + results.get("mental_models", []) if s.get("status") == "error"),
        },
        "details": results
    }

    if output_path:
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            logger.info("报告已保存: %s", output_path)
        except Exception as e:
            logger.error("保存报告失败 %s: %s", output_path, e)

    return report


def print_report(report: dict, verbose: bool = False):
    """在终端打印可读报告"""
    s = report["summary"]
    print(f"\n{'='*60}")
    print(f"  盖娅矩阵反哺检测报告")
    print(f"{'='*60}")
    print(f"  Profile:     {report['profile']}")
    print(f"  扫描时间:    {report['scanned_at'][:19]}")
    print(f"  报告ID:      {report['report_id']}")
    print(f"{'-'*60}")
    print(f"  总检测项:    {s['total_candidates']}")
    print(f"  ├─ 新技能:   {s['new_skills']}")
    print(f"  ├─ 重复技能:  {s['duplicate_skills']}")
    print(f"  ├─ 已反哺:    {s['already_backfed']}")
    print(f"  ├─ 新心智模型: {s['new_models']}")
    print(f"  ├─ 会话日志:  {s['new_session_logs']}")
    if s['errors']:
        print(f"  └─ ❌ 错误:    {s['errors']}")
    print(f"{'-'*60}")

    if verbose:
        for cat in ["skills", "mental_models"]:
            items = report["details"].get(cat, [])
            if items:
                print(f"\n  [{cat}]")
                for item in items:
                    status_icon = {"new": "🆕", "duplicate": "🔁", "already_backfed": "✅", "error": "❌"}.get(item.get("status"), "❓")
                    print(f"    {status_icon} {item['name']} ({item.get('size', 0)} bytes)")
                    if item.get("status") == "error" and item.get("error"):
                        print(f"      错误: {item['error']}")

        logs = report["details"].get("delegate_logs", [])
        if logs:
            print(f"\n  [delegate_logs]")
            for log in logs:
                print(f"    📄 {log['name']} ({log.get('size', 0)} bytes)")

    print(f"{'='*60}")


def list_profiles():
    """列出所有可用 profile"""
    if not os.path.isdir(PROFILES_DIR):
        print("profiles/ 目录不存在")
        return
    profiles = sorted([
        d for d in os.listdir(PROFILES_DIR)
        if os.path.isdir(os.path.join(PROFILES_DIR, d)) and not d.startswith("_")
    ])
    if profiles:
        print(f"可用 profiles ({len(profiles)}):")
        for p in profiles:
            print(f"  - {p}")
    else:
        print("没有找到 profile 目录")


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(
        description="盖娅矩阵反哺检测引擎 — 扫描 profile 产出，生成检测报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s --profile chainke-dev\n"
            "  %(prog)s --profile chainke-dev --report report.json\n"
            "  %(prog)s --profile chainke-dev --verbose\n"
            "  %(prog)s --list-profiles\n"
        )
    )
    parser.add_argument("--profile", help="要扫描的 profile 名称（如 chainke-dev）")
    parser.add_argument("--report", help="输出报告 JSON 文件路径（可选）")
    parser.add_argument("--verbose", action="store_true", help="显示详细检测项")
    parser.add_argument("--list-profiles", action="store_true", help="列出所有可用 profile")

    args = parser.parse_args()

    try:
        ensure_dirs()

        if args.list_profiles:
            list_profiles()
            return

        if not args.profile:
            parser.print_help()
            sys.exit(1)

        profile_dir = os.path.join(PROFILES_DIR, args.profile)
        if not os.path.isdir(profile_dir):
            logger.error("Profile 不存在: %s", profile_dir)
            print(f"❌ Profile '{args.profile}' 不存在于 {PROFILES_DIR}")
            sys.exit(1)

        logger.info("开始扫描 profile: %s", args.profile)

        # 构建母体哈希集
        mother_skill_hashes = build_mother_skill_hashes()
        mother_model_hashes = build_mother_model_hashes()

        # 扫描
        skills = scan_profile_skills(args.profile, mother_skill_hashes)
        models = scan_profile_mental_models(args.profile, mother_model_hashes)
        logs = scan_delegate_logs(args.profile)

        results = {
            "skills": skills,
            "mental_models": models,
            "delegate_logs": logs
        }

        report = generate_report(args.profile, results, args.report)
        print_report(report, verbose=args.verbose)

        # 验证：确认输出文件存在
        if args.report:
            if os.path.isfile(args.report):
                logger.info("✅ 报告文件已确认存在: %s", args.report)
            else:
                logger.error("❌ 报告文件写入失败: %s", args.report)

    except Exception as e:
        logger.exception("反哺检测执行失败: %s", str(e))
        print(f"❌ 执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
