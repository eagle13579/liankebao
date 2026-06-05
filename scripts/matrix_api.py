#!/usr/bin/env python3
"""
matrix_api.py — 盖娅矩阵统一母体API（轻量版）
基于 FastAPI 的 RESTful 服务，提供统一母体资源查询接口。

接口:
  GET  /api/v1/matrix/skills?category=xxx        — 查询技能
  GET  /api/v1/matrix/employees?role=xxx         — 查询员工
  GET  /api/v1/matrix/mental-models?tag=xxx      — 查询心智模型
  GET  /api/v1/matrix/mental-models/related?name=xxx  — 关联心智模型
  GET  /api/v1/matrix/mental-models/search?q=xxx      — 搜索心智模型
  GET  /api/v1/matrix/status                     — 健康检查

用法:
  python matrix_api.py                         # 默认启动 :5199
  python matrix_api.py --port 5199
  python matrix_api.py --reload                # 开发模式自动重载
  python matrix_api.py --check                 # 仅检查配置，不启动
"""
import os
import sys
import json
import argparse
import logging
from datetime import datetime
from typing import Optional

# ── 导入知识图谱引擎（纯 Python 零外部依赖） ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import knowledge_graph as kg

# ── 全局路径 ──
HERMES = r"D:\向海容的知识库\wiki\wiki\记忆宫殿"
PROFILES_DIR = os.path.join(HERMES, "profiles")
SKILLS_DIR = os.path.join(HERMES, "skills")
EMPLOYEES_DIR = os.path.join(HERMES, "employees")
POOL_DIR = os.path.join(HERMES, "L5孵化室", "五池", "模型池")

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("matrix_api")


# ══════════════════════════════════════════════
#  数据层（纯函数，可脱离 FastAPI 独立测试）
# ══════════════════════════════════════════════

def load_skills_from_index() -> list:
    """从 SKILL_INDEX.yaml 加载技能列表"""
    index_path = os.path.join(PROFILES_DIR, "_shared", "SKILL_INDEX.yaml")
    if not os.path.isfile(index_path):
        return _fallback_scan_skills()
    try:
        import yaml
        with open(index_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        skills = []

        # 主技能索引
        for key in ["skills", "profile_skills"]:
            for item in data.get(key, []):
                skill = {
                    "name": item.get("name", ""),
                    "category": item.get("category", "general"),
                    "source": item.get("source", "mother"),
                    "path": item.get("path", ""),
                    "summary": item.get("summary", ""),
                    "backfed_at": item.get("backfed_at", "")
                }
                skills.append(skill)

        # 如果索引中没有 skills，回退到文件扫描
        if not skills:
            return _fallback_scan_skills()
        return skills
    except Exception as e:
        logger.warning("SKILL_INDEX.yaml 解析失败，回退到文件扫描: %s", e)
        return _fallback_scan_skills()


def _fallback_scan_skills() -> list:
    """回退方案：直接扫描 filesystem"""
    skills = []
    if os.path.isdir(SKILLS_DIR):
        for root, dirs, files in os.walk(SKILLS_DIR):
            for f in files:
                if f.endswith(".md"):
                    rel = os.path.relpath(os.path.join(root, f), SKILLS_DIR)
                    parts = rel.split(os.sep)
                    category = parts[0] if len(parts) > 1 else "general"
                    name = parts[-2] if len(parts) > 1 else f.replace(".md", "")
                    skills.append({
                        "name": name,
                        "category": category,
                        "source": "mother",
                        "path": os.path.join(root, f),
                        "summary": "",
                        "backfed_at": ""
                    })
    return skills


def load_employees_from_index() -> list:
    """从 EMPLOYEE_INDEX.yaml 加载员工列表"""
    index_path = os.path.join(PROFILES_DIR, "_shared", "EMPLOYEE_INDEX.yaml")
    if not os.path.isfile(index_path):
        return _fallback_scan_employees()
    try:
        import yaml
        with open(index_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        employees = []
        for item in data.get("employees", []):
            employees.append({
                "name": item.get("name", ""),
                "role": item.get("role", ""),
                "level": item.get("level", ""),
                "specialty": item.get("specialty", ""),
                "status": item.get("status", "active"),
                "path": item.get("path", "")
            })
        if not employees:
            return _fallback_scan_employees()
        return employees
    except Exception as e:
        logger.warning("EMPLOYEE_INDEX.yaml 解析失败，回退到文件扫描: %s", e)
        return _fallback_scan_employees()


def _fallback_scan_employees() -> list:
    """回退方案：直接扫描 employees/ 目录"""
    employees = []
    if os.path.isdir(EMPLOYEES_DIR):
        for f in sorted(os.listdir(EMPLOYEES_DIR)):
            if f.endswith(".md") or f.endswith(".yaml"):
                employees.append({
                    "name": f.replace(".md", "").replace(".yaml", ""),
                    "role": "unknown",
                    "level": "",
                    "specialty": "",
                    "status": "active",
                    "path": os.path.join(EMPLOYEES_DIR, f)
                })
    return employees


def load_mental_models_from_index() -> list:
    """从 MENTAL_MODEL_INDEX.yaml 加载心智模型列表"""
    index_path = os.path.join(PROFILES_DIR, "_shared", "MENTAL_MODEL_INDEX.yaml")
    if not os.path.isfile(index_path):
        return _fallback_scan_mental_models()
    try:
        import yaml
        with open(index_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        models = []
        for item in data.get("models", []):
            name = item.get("name", "")
            summary = item.get("summary", "")
            # 从名称推断 tag（子目录前缀）
            tags = []
            if "_原子" in name:
                tags.append("atomic")
            if "架构" in name:
                tags.append("architecture")
            if "模型" in name:
                tags.append("mental-model")
            if "铁律" in name or "安全" in name:
                tags.append("security")
            if "交易" in name or "投资" in name or "战法" in name:
                tags.append("trading")
            if "产品" in name:
                tags.append("product")

            models.append({
                "name": name,
                "summary": summary,
                "tags": tags,
                "source": "mother",
                "path": os.path.join(POOL_DIR, name) if os.path.exists(os.path.join(POOL_DIR, name)) else ""
            })
        if not models:
            return _fallback_scan_mental_models()
        return models
    except Exception as e:
        logger.warning("MENTAL_MODEL_INDEX.yaml 解析失败，回退到文件扫描: %s", e)
        return _fallback_scan_mental_models()


def _fallback_scan_mental_models() -> list:
    """回退方案：直接扫描模型池目录"""
    models = []
    if os.path.isdir(POOL_DIR):
        for f in sorted(os.listdir(POOL_DIR)):
            if f.endswith(".md"):
                tags = []
                if "原子" in f:
                    tags.append("atomic")
                if "架构" in f:
                    tags.append("architecture")
                models.append({
                    "name": f,
                    "summary": "",
                    "tags": tags,
                    "source": "mother",
                    "path": os.path.join(POOL_DIR, f)
                })
    return models


def get_system_status() -> dict:
    """获取系统健康状态"""
    status = {
        "service": "盖娅矩阵统一母体API",
        "version": "1.0.0",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "mother_path": HERMES,
        "checks": {}
    }

    # 检查各个目录
    checks = {
        "母体根目录": os.path.isdir(HERMES),
        "profiles 目录": os.path.isdir(PROFILES_DIR),
        "skills 目录": os.path.isdir(SKILLS_DIR),
        "employees 目录": os.path.isdir(EMPLOYEES_DIR),
        "模型池": os.path.isdir(POOL_DIR),
    }

    for name, ok in checks.items():
        status["checks"][name] = "✅" if ok else "❌"

    # 检查索引文件
    index_files = ["SKILL_INDEX.yaml", "EMPLOYEE_INDEX.yaml", "MENTAL_MODEL_INDEX.yaml"]
    for idx in index_files:
        idx_path = os.path.join(PROFILES_DIR, "_shared", idx)
        status["checks"][f"_shared/{idx}"] = "✅" if os.path.isfile(idx_path) else "⚠️"

    # 统计
    try:
        status["stats"] = {
            "skills": len(load_skills_from_index()),
            "employees": len(load_employees_from_index()),
            "mental_models": len(load_mental_models_from_index()),
        }
    except Exception as e:
        status["stats"] = {"error": str(e)}

    all_ok = all(checks.values())
    status["status"] = "healthy" if all_ok else "degraded"

    return status


# ══════════════════════════════════════════════
#  知识图谱缓存（惰性加载）
# ══════════════════════════════════════════════

_kg_cache = {"models": None, "index": None}

def _ensure_kg_loaded():
    """确保知识图谱数据已加载（惰性加载 + 缓存）"""
    if _kg_cache["models"] is None:
        logger.info("知识图谱：首次扫描模型池并构建索引...")
        models = kg.scan_model_files()
        index = kg.build_inverted_index(models)
        _kg_cache["models"] = models
        _kg_cache["index"] = index
        logger.info("知识图谱：加载完成 — %d 个模型, %d 个关键词", len(models), len(index))
    return _kg_cache["models"], _kg_cache["index"]


def _reset_kg_cache():
    """重置知识图谱缓存（用于热加载场景）"""
    _kg_cache["models"] = None
    _kg_cache["index"] = None
    logger.info("知识图谱缓存已重置")


# ══════════════════════════════════════════════
#  FastAPI 应用
# ══════════════════════════════════════════════

def create_app():
    """创建 FastAPI 应用（可导出用于测试）"""
    from fastapi import FastAPI, Query, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    app = FastAPI(
        title="盖娅矩阵统一母体API",
        description="Gaia Matrix Unified API — 统一母体资源查询接口",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # CORS（允许所有来源，开发阶段）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 健康检查 ──
    @app.get("/api/v1/matrix/status")
    async def get_status():
        """系统健康检查"""
        return get_system_status()

    @app.get("/health")
    async def simple_health():
        """简单健康检查（用于负载均衡）"""
        return {"status": "ok", "timestamp": datetime.now().isoformat()}

    # ── 技能查询 ──
    @app.get("/api/v1/matrix/skills")
    async def get_skills(
        category: Optional[str] = Query(None, description="按分类筛选"),
        name: Optional[str] = Query(None, description="按名称搜索"),
        limit: int = Query(100, ge=1, le=1000, description="返回数量上限")
    ):
        """查询母体技能"""
        try:
            skills = load_skills_from_index()

            if category:
                skills = [s for s in skills if category.lower() in s.get("category", "").lower()]

            if name:
                skills = [s for s in skills if name.lower() in s.get("name", "").lower()]

            return {
                "total": len(skills),
                "limit": limit,
                "skills": skills[:limit]
            }
        except Exception as e:
            logger.error("查询技能失败: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    # ── 员工查询 ──
    @app.get("/api/v1/matrix/employees")
    async def get_employees(
        role: Optional[str] = Query(None, description="按角色筛选"),
        level: Optional[str] = Query(None, description="按级别筛选"),
        name: Optional[str] = Query(None, description="按名称搜索"),
        limit: int = Query(100, ge=1, le=1000, description="返回数量上限")
    ):
        """查询母体员工（AI数智军团）"""
        try:
            employees = load_employees_from_index()

            if role:
                employees = [e for e in employees if role.lower() in e.get("role", "").lower()]

            if level:
                employees = [e for e in employees if level.lower() in e.get("level", "").lower()]

            if name:
                employees = [e for e in employees if name.lower() in e.get("name", "").lower()]

            return {
                "total": len(employees),
                "limit": limit,
                "employees": employees[:limit]
            }
        except Exception as e:
            logger.error("查询员工失败: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    # ── 心智模型查询 ──
    @app.get("/api/v1/matrix/mental-models")
    async def get_mental_models(
        tag: Optional[str] = Query(None, description="按标签筛选"),
        name: Optional[str] = Query(None, description="按名称搜索"),
        limit: int = Query(100, ge=1, le=1000, description="返回数量上限"),
        with_related: bool = Query(False, description="是否附带关联模型"),
    ):
        """查询母体心智模型"""
        try:
            models = load_mental_models_from_index()

            if tag:
                models = [m for m in models if any(tag.lower() in t.lower() for t in m.get("tags", []))]

            target_name = None
            if name:
                models = [m for m in models if name.lower() in m.get("name", "").lower()]
                # 如果有精确匹配，用于关联查询
                exact = [m for m in models if m.get("name", "").lower() == name.lower()]
                if exact:
                    target_name = exact[0].get("name", "")

            result_models = models[:limit]

            # 附加上下文关联（仅当查询了具体名称或有 with_related 标志）
            if (target_name or with_related) and result_models:
                try:
                    kg_models, kg_index = _ensure_kg_loaded()
                    for m in result_models:
                        m_name = m.get("name", "")
                        related = kg.compute_related_models(kg_models, kg_index, m_name, top_n=5)
                        if related:
                            m["related_models"] = [
                                {"name": r["name"], "weight": r["weight"]}
                                for r in related
                            ]
                        else:
                            m["related_models"] = []
                except Exception as kg_err:
                    logger.warning("知识图谱关联查询失败（非致命）: %s", kg_err)

            return {
                "total": len(models),
                "limit": limit,
                "mental_models": result_models
            }
        except Exception as e:
            logger.error("查询心智模型失败: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    # ── 心智模型关联查询 ──
    @app.get("/api/v1/matrix/mental-models/related")
    async def get_related_mental_models(
        name: str = Query(..., description="心智模型名称"),
        top_n: int = Query(10, ge=1, le=50, description="返回数量上限"),
    ):
        """返回与指定心智模型关联的其他模型"""
        try:
            models, index = _ensure_kg_loaded()
            related = kg.compute_related_models(models, index, name, top_n=top_n)
            if not related:
                # 尝试模糊匹配
                candidates = [m for m in models if name.lower() in m["name"].lower()]
                if candidates:
                    related = kg.compute_related_models(models, index, candidates[0]["name"], top_n=top_n)
                    name = candidates[0]["name"]
            return {
                "source": name,
                "total": len(related),
                "related_models": related
            }
        except Exception as e:
            logger.error("查询关联心智模型失败: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    # ── 心智模型搜索 ──
    @app.get("/api/v1/matrix/mental-models/search")
    async def search_mental_models(
        q: str = Query(..., description="搜索关键词"),
        top_n: int = Query(20, ge=1, le=100, description="返回数量上限"),
    ):
        """搜索心智模型（关键词匹配引擎）"""
        try:
            models, index = _ensure_kg_loaded()
            results = kg.search_models(index, models, q, top_n=top_n)
            return {
                "query": q,
                "total": len(results),
                "results": results
            }
        except Exception as e:
            logger.error("搜索心智模型失败: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    # ── 总览 ──
    @app.get("/api/v1/matrix")
    async def matrix_overview():
        """母体总览"""
        return get_system_status()

    # ── 全局异常处理 ──
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error("未处理的异常: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "timestamp": datetime.now().isoformat()}
        )

    return app


# ══════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="盖娅矩阵统一母体API服务（轻量版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s                          # 默认 :5199\n"
            "  %(prog)s --port 5199              # 指定端口\n"
            "  %(prog)s --reload                 # 热加载模式\n"
            "  %(prog)s --check                  # 仅检查配置\n"
        )
    )
    parser.add_argument("--port", type=int, default=5199, help="监听端口 (默认: 5199)")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--reload", action="store_true", help="开发模式热加载")
    parser.add_argument("--check", action="store_true", help="仅检查配置和目录结构，不启动服务")

    args = parser.parse_args()

    try:
        # 检查配置
        status = get_system_status()
        logger.info("盖娅矩阵路径: %s", HERMES)
        logger.info("系统状态: %s", status["status"])

        for check_name, check_result in status.get("checks", {}).items():
            logger.info("  检查 %s: %s", check_name, check_result)

        if "stats" in status:
            logger.info("技能数: %s", status["stats"].get("skills", "N/A"))
            logger.info("员工数: %s", status["stats"].get("employees", "N/A"))
            logger.info("心智模型数: %s", status["stats"].get("mental_models", "N/A"))

        if args.check:
            if status["status"] == "healthy":
                print("✅ 配置检查通过，所有组件正常")
            else:
                print("⚠️  配置检查完成，部分组件异常")
                for check_name, check_result in status.get("checks", {}).items():
                    if "❌" in check_result:
                        print(f"  ❌ {check_name}")
            return

        # 启动服务
        import uvicorn
        app = create_app()
        logger.info("启动盖娅矩阵API服务: %s:%d", args.host, args.port)
        logger.info("API文档: http://localhost:%d/docs", args.port)

        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level="info"
        )

    except KeyboardInterrupt:
        logger.info("服务已停止")
    except Exception as e:
        logger.exception("服务启动失败: %s", str(e))
        print(f"❌ 服务启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
