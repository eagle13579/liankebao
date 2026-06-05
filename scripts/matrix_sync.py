#!/usr/bin/env python3
"""
matrix_sync.py — 盖娅矩阵母体→Node同步引擎
检测母体更新（对比缓存 hash vs 当前母体状态），生成差分清单，
支持 --check（仅检查不执行）和 --apply（执行同步）两种模式。

同步策略:
  1. 母体资产快照缓存 (_backfeed_archive/matrix_sync_cache.json)
  2. 对比当前母体 hash 与缓存 hash → 生成差分
  3. 按需同步到 _shared/ 索引（不拷贝文件到各 Node）
  4. 更新缓存状态

用法:
  python matrix_sync.py --check              # 仅检查差异
  python matrix_sync.py --apply              # 执行同步
  python matrix_sync.py --apply --profile chainke-dev  # 同步指定 profile
  python matrix_sync.py --status             # 查看同步状态
  python matrix_sync.py --reset-cache        # 重置缓存
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
SYNC_CACHE = os.path.join(HERMES, "_backfeed_archive", "matrix_sync_cache.json")
SYNC_LOG = os.path.join(HERMES, "_backfeed_archive", "matrix_sync.log")

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(SYNC_LOG, encoding="utf-8")
    ]
)
logger = logging.getLogger("matrix_sync")


def ensure_dirs():
    """确保必要的目录存在"""
    os.makedirs(os.path.dirname(SYNC_CACHE), exist_ok=True)


def file_hash(path: str) -> str:
    """计算文件 SHA256 哈希"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_mother_assets() -> dict:
    """
    扫描母体所有可同步资产，返回:
    {
      "skills/profiles/xxx.md": {"hash": "...", "size": N, "mtime": "..."},
      "models/xxx.md": {...},
      "_shared/SKILL_INDEX.yaml": {...},
      "_shared/EMPLOYEE_INDEX.yaml": {...},
      "_shared/MENTAL_MODEL_INDEX.yaml": {...}
    }
    """
    assets = {}

    # 1. 扫描 skills/profiles/ 下的技能
    skills_profiles = os.path.join(SKILLS_MOTHER, "profiles")
    if os.path.isdir(skills_profiles):
        for f in os.listdir(skills_profiles):
            if f.endswith(".md"):
                fp = os.path.join(skills_profiles, f)
                try:
                    assets[f"skills/profiles/{f}"] = {
                        "hash": file_hash(fp),
                        "size": os.path.getsize(fp),
                        "mtime": datetime.fromtimestamp(os.path.getmtime(fp)).isoformat()
                    }
                except Exception as e:
                    logger.warning("读取技能文件失败 %s: %s", fp, e)

    # 2. 扫描母体 skills/ 下的所有技能（非 profiles/ 子目录）
    if os.path.isdir(SKILLS_MOTHER):
        for root, dirs, files in os.walk(SKILLS_MOTHER):
            # 跳过 profiles/ 子目录 (已单独扫描)
            if root == skills_profiles or root.startswith(skills_profiles + os.sep):
                continue
            for f in files:
                if f.endswith(".md"):
                    fp = os.path.join(root, f)
                    rel = os.path.relpath(fp, SKILLS_MOTHER)
                    try:
                        assets[f"skills/{rel}"] = {
                            "hash": file_hash(fp),
                            "size": os.path.getsize(fp),
                            "mtime": datetime.fromtimestamp(os.path.getmtime(fp)).isoformat()
                        }
                    except Exception as e:
                        logger.warning("读取技能文件失败 %s: %s", fp, e)

    # 3. 扫描心智模型
    if os.path.isdir(POOL_DIR):
        for f in os.listdir(POOL_DIR):
            if f.endswith(".md"):
                fp = os.path.join(POOL_DIR, f)
                try:
                    assets[f"models/{f}"] = {
                        "hash": file_hash(fp),
                        "size": os.path.getsize(fp),
                        "mtime": datetime.fromtimestamp(os.path.getmtime(fp)).isoformat()
                    }
                except Exception as e:
                    logger.warning("读取模型文件失败 %s: %s", fp, e)

    # 4. 共享索引
    index_files = ["SKILL_INDEX.yaml", "EMPLOYEE_INDEX.yaml", "MENTAL_MODEL_INDEX.yaml"]
    for idx_file in index_files:
        idx_path = os.path.join(PROFILES_DIR, "_shared", idx_file)
        if os.path.isfile(idx_path):
            try:
                assets[f"_shared/{idx_file}"] = {
                    "hash": file_hash(idx_path),
                    "size": os.path.getsize(idx_path),
                    "mtime": datetime.fromtimestamp(os.path.getmtime(idx_path)).isoformat()
                }
            except Exception as e:
                logger.warning("读取索引文件失败 %s: %s", idx_path, e)

    return assets


def load_cache() -> dict:
    """加载同步缓存"""
    if os.path.isfile(SYNC_CACHE):
        try:
            with open(SYNC_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("读取缓存失败，将重建: %s", e)
    return {"version": "1.0", "created_at": None, "last_sync": None, "assets": {}}


def save_cache(assets: dict, sync_time: str = None):
    """保存同步缓存"""
    cache = {
        "version": "1.0",
        "created_at": sync_time if sync_time else datetime.now().isoformat(),
        "last_sync": sync_time if sync_time else datetime.now().isoformat(),
        "asset_count": len(assets),
        "assets": assets
    }
    try:
        with open(SYNC_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        logger.info("缓存已更新: %d 个资产", len(assets))
    except Exception as e:
        logger.error("保存缓存失败: %s", e)


def compute_diff(current: dict, cached: dict) -> dict:
    """
    对比当前母体与缓存，生成差分
    返回: {added: [...], changed: [...], removed: [...]}
    """
    added = []
    changed = []
    removed = []

    cached_assets = cached.get("assets", {})

    for key, cur_info in current.items():
        if key not in cached_assets:
            added.append({
                "key": key,
                "hash": cur_info["hash"],
                "size": cur_info["size"],
                "mtime": cur_info["mtime"]
            })
        elif cur_info["hash"] != cached_assets[key]["hash"]:
            changed.append({
                "key": key,
                "old_hash": cached_assets[key]["hash"],
                "new_hash": cur_info["hash"],
                "size": cur_info["size"],
                "mtime": cur_info["mtime"]
            })

    for key in cached_assets:
        if key not in current:
            removed.append({
                "key": key,
                "hash": cached_assets[key]["hash"]
            })

    return {
        "added": added,
        "changed": changed,
        "removed": removed,
        "total_diff": len(added) + len(changed) + len(removed)
    }


def get_available_profiles() -> list:
    """获取所有可用的 profile 列表"""
    if not os.path.isdir(PROFILES_DIR):
        return []
    return sorted([
        d for d in os.listdir(PROFILES_DIR)
        if os.path.isdir(os.path.join(PROFILES_DIR, d))
        and not d.startswith("_")
    ])


def sync_to_profile(diff: dict, profile_name: str, dry_run: bool = False) -> list:
    """
    将差分同步到指定 profile 的 _shared/ 索引
    返回操作列表
    """
    operations = []
    shared_dir = os.path.join(PROFILES_DIR, profile_name, "_shared")
    sync_dir = os.path.join(PROFILES_DIR, profile_name, "skills", "_shared_sync")

    # 需要同步的项目
    sync_items = diff.get("added", []) + diff.get("changed", [])

    for item in sync_items:
        key = item["key"]

        # 只同步共享索引
        if key.startswith("_shared/"):
            source_path = os.path.join(PROFILES_DIR, "_shared", os.path.basename(key))
            target_path = os.path.join(shared_dir, os.path.basename(key))
            if not dry_run:
                try:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    import shutil
                    shutil.copy2(source_path, target_path)
                    operations.append({
                        "action": "sync_index",
                        "key": key,
                        "target": target_path,
                        "status": "ok"
                    })
                except Exception as e:
                    operations.append({
                        "action": "sync_index",
                        "key": key,
                        "target": target_path,
                        "status": "error",
                        "error": str(e)
                    })
            else:
                operations.append({
                    "action": "sync_index",
                    "key": key,
                    "target": os.path.join(shared_dir, os.path.basename(key)),
                    "status": "dry_run"
                })

        # 同步技能引用到 _shared_sync/
        if key.startswith("skills/") or key.startswith("models/"):
            if key.startswith("skills/"):
                # 从母体 skills/ 找到源文件
                source_path = os.path.join(SKILLS_MOTHER, key[len("skills/"):])
            elif key.startswith("models/"):
                source_path = os.path.join(POOL_DIR, os.path.basename(key))
            else:
                continue

            target_path = os.path.join(sync_dir, key)
            if not dry_run:
                try:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    import shutil
                    shutil.copy2(source_path, target_path)
                    operations.append({
                        "action": "sync_asset",
                        "key": key,
                        "target": target_path,
                        "status": "ok"
                    })
                except Exception as e:
                    operations.append({
                        "action": "sync_asset",
                        "key": key,
                        "target": target_path,
                        "status": "error",
                        "error": str(e)
                    })
            else:
                operations.append({
                    "action": "sync_asset",
                    "key": key,
                    "target": target_path,
                    "status": "dry_run"
                })

    return operations


def print_diff(diff: dict):
    """打印差分报告"""
    print(f"\n{'='*60}")
    print(f"  盖娅矩阵同步差分报告")
    print(f"{'='*60}")
    print(f"  新增:  {len(diff['added'])}  变更: {len(diff['changed'])}  移除: {len(diff['removed'])}")
    print(f"  总计差异: {diff['total_diff']} 项")
    print(f"{'-'*60}")

    if diff["added"]:
        print(f"\n  🆕 新增 ({len(diff['added'])}):")
        for item in diff["added"][:10]:
            print(f"    + {item['key']} ({item['size']} bytes)")
        if len(diff["added"]) > 10:
            print(f"    ... 还有 {len(diff['added']) - 10} 项")

    if diff["changed"]:
        print(f"\n  🔄 变更 ({len(diff['changed'])}):")
        for item in diff["changed"][:10]:
            print(f"    ~ {item['key']}")
            print(f"      hash: {item['old_hash'][:12]} → {item['new_hash'][:12]}")
        if len(diff["changed"]) > 10:
            print(f"    ... 还有 {len(diff['changed']) - 10} 项")

    if diff["removed"]:
        print(f"\n  🗑️  移除 ({len(diff['removed'])}):")
        for item in diff["removed"][:5]:
            print(f"    - {item['key']}")
        if len(diff["removed"]) > 5:
            print(f"    ... 还有 {len(diff['removed']) - 5} 项")

    print(f"\n{'='*60}")


def print_status(cache: dict):
    """打印同步状态"""
    print(f"\n{'='*60}")
    print(f"  盖娅矩阵同步状态")
    print(f"{'='*60}")
    print(f"  缓存版本:    {cache.get('version', 'N/A')}")
    print(f"  创建时间:    {cache.get('created_at', 'N/A')[:19] if cache.get('created_at') else 'N/A'}")
    print(f"  上次同步:    {cache.get('last_sync', 'N/A')[:19] if cache.get('last_sync') else '从未同步'}")
    print(f"  缓存资产数:  {cache.get('asset_count', 0)}")
    print(f"  可用 profiles: {len(get_available_profiles())}")
    if not cache.get("last_sync"):
        print(f"  ⚠️  从未执行过同步，建议先运行 --check")
    print(f"{'='*60}")


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(
        description="盖娅矩阵母体→Node同步引擎 — 检测差异并同步",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s --check            # 仅检查差异\n"
            "  %(prog)s --apply            # 执行同步\n"
            "  %(prog)s --apply --profile chainke-dev  # 同步指定 profile\n"
            "  %(prog)s --status           # 查看同步状态\n"
            "  %(prog)s --reset-cache      # 重置缓存\n"
        )
    )
    parser.add_argument("--check", action="store_true", help="仅检查差异，不执行同步")
    parser.add_argument("--apply", action="store_true", help="执行同步（将差异应用到 Node）")
    parser.add_argument("--profile", help="仅同步指定 profile（可选）")
    parser.add_argument("--status", action="store_true", help="查看当前同步状态")
    parser.add_argument("--reset-cache", action="store_true", help="重置同步缓存")
    parser.add_argument("--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    try:
        ensure_dirs()

        # --status
        if args.status:
            cache = load_cache()
            print_status(cache)
            return

        # --reset-cache
        if args.reset_cache:
            cache = {"version": "1.0", "created_at": datetime.now().isoformat(),
                     "last_sync": None, "asset_count": 0, "assets": {}}
            save_cache(cache)
            print("✅ 缓存已重置")
            return

        # 默认行为或 --check / --apply
        if not args.check and not args.apply:
            parser.print_help()
            sys.exit(1)

        # 扫描母体当前资产
        logger.info("扫描母体资产...")
        current_assets = scan_mother_assets()
        logger.info("母体资产: %d 项", len(current_assets))

        # 加载缓存
        cache = load_cache()

        # 计算差分
        diff = compute_diff(current_assets, cache)
        print_diff(diff)

        if args.check:
            if diff["total_diff"] == 0:
                print("✅ 母体与缓存一致，无需同步")
            else:
                print(f"💡 发现 {diff['total_diff']} 项差异，使用 --apply 执行同步")
            # 更新缓存扫描时间戳（不更新资产快照）
            cache["last_sync"] = datetime.now().isoformat()
            save_cache(cache, sync_time=datetime.now().isoformat())
            return

        if args.apply:
            if diff["total_diff"] == 0:
                print("✅ 母体与缓存一致，无需同步")
                # 仍然更新时间戳
                cache["last_sync"] = datetime.now().isoformat()
                save_cache(current_assets, sync_time=datetime.now().isoformat())
                return

            # 执行同步
            profiles = [args.profile] if args.profile else get_available_profiles()

            if not profiles:
                logger.warning("没有找到可同步的 profile")
                print("⚠️  没有找到可同步的 profile")

            total_ops = 0
            for profile_name in profiles:
                ops = sync_to_profile(diff, profile_name, dry_run=False)
                total_ops += len(ops)

                ok_ops = sum(1 for op in ops if op["status"] == "ok")
                err_ops = sum(1 for op in ops if op["status"] == "error")
                logger.info("%s: %d 操作 (%d 成功, %d 失败)",
                           profile_name, len(ops), ok_ops, err_ops)

                if args.verbose:
                    for op in ops:
                        icon = "✅" if op["status"] == "ok" else "❌"
                        print(f"  {icon} [{op['action']}] {op['key']} → {op['target']}")

            # 更新缓存
            save_cache(current_assets, sync_time=datetime.now().isoformat())

            print(f"\n{'='*60}")
            print(f"  同步完成")
            print(f"  Profiles:    {len(profiles)}")
            print(f"  总操作数:   {total_ops}")
            print(f"  缓存已更新: {len(current_assets)} 项资产")
            print(f"{'='*60}")

            # 验证：确认缓存文件存在
            if os.path.isfile(SYNC_CACHE):
                logger.info("✅ 缓存文件已确认: %s", SYNC_CACHE)
            else:
                logger.error("❌ 缓存文件写入失败")

    except Exception as e:
        logger.exception("同步执行失败: %s", str(e))
        print(f"❌ 执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
