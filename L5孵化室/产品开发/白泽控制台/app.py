"""
白泽控制台 v0.1 — CEO仪表盘
Flask + Alpine.js + Tailwind CDN (零构建步骤)

架构模式:
  - @with_analytics 装饰器 (参考 windows-mcp/analytics.py)
  - Registry + @action 注册模式 (参考 browser-use-mcp)
  - EventStream 事件流 (参考 openhands/event_stream.py)
  - HexSpace 前端状态管理 (参考 multica 六边形空间模式)
  - Server 入口模式: env → logging → init → start (参考 browser-use-mcp)
"""

import logging
import os
import re
import sqlite3
import sys
import time
from datetime import date, datetime
from functools import wraps
from pathlib import Path

import yaml

from flask import Flask, render_template, jsonify, request

# 白泽独立工具库 (内联定义 — 原 baize_libs 模块已内联到本文件)

# ----- LLM_PRICES -----
LLM_PRICES = {
    "input_per_1m": 2.5,   # 元/百万输入token (deepseek-chat)
    "output_per_1m": 10.0,  # 元/百万输出token
}


# ----- with_analytics 装饰器 -----
def with_analytics(name=None):
    """装饰器：测量API耗时/成功/失败"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            start = datetime.now()
            try:
                result = f(*args, **kwargs)
                elapsed = (datetime.now() - start).total_seconds()
                logger.info(f"[analytics] {name or f.__name__} OK in {elapsed:.2f}s")
                return result
            except Exception as e:
                elapsed = (datetime.now() - start).total_seconds()
                logger.warning(f"[analytics] {name or f.__name__} FAIL in {elapsed:.2f}s: {e}")
                raise
        return wrapper
    return decorator


# ----- ActionRegistry -----
class ActionRegistry:
    """Registry + @action 注册模式"""
    def __init__(self):
        self._actions = {}

    def action(self, name=None):
        def decorator(f):
            key = name or f.__name__
            self._actions[key] = f
            return f
        return decorator

    def execute(self, name, **kwargs):
        if name not in self._actions:
            raise KeyError(f"Unknown action: {name}")
        return self._actions[name](**kwargs)

    def list_actions(self):
        return list(self._actions.keys())


# ── 烛龙Pipeline管理 ──
PIPELINE_STAGES = [
    {"id": "s0", "name": "0. 需求分析", "icon": "📋"},
    {"id": "s1", "name": "1. 技术方案", "icon": "🔧"},
    {"id": "s2", "name": "2. 数据模型", "icon": "🗄️"},
    {"id": "s3", "name": "3. API设计", "icon": "🔌"},
    {"id": "s4", "name": "4. 后端开发", "icon": "⚙️"},
    {"id": "s5", "name": "5. 前端开发", "icon": "🎨"},
    {"id": "s6", "name": "6. 集成测试", "icon": "🧪"},
    {"id": "s7", "name": "7. 代码审查", "icon": "🔍"},
    {"id": "s8", "name": "8. 合规审查", "icon": "⚖️"},
    {"id": "s9", "name": "9. 部署上线", "icon": "🚀"},
    {"id": "s10", "name": "10. 线上验证", "icon": "✅"},
    {"id": "s11", "name": "11. 客户验收", "icon": "👥"},
    {"id": "s12", "name": "12. 数据分析", "icon": "📊"},
    {"id": "s13", "name": "13. 复盘沉淀", "icon": "💎"},
]
_pipeline_runs = {}  # run_id -> run_data
_pipeline_run_counter = 0


# ----- _safe_read_db -----
def _safe_read_db(db_path):
    """获取SQLite连接，设置row_factory=sqlite3.Row，返回None或连接"""
    try:
        if db_path and Path(db_path).exists():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            return conn
    except Exception as e:
        logger.warning(f"_safe_read_db 失败 {db_path}: {e}")
    return None


# ----- _parse_yaml_robust -----
def _parse_yaml_robust(filepath):
    """先 yaml.safe_load 尝试，失败后行解析回退"""
    try:
        if filepath and Path(filepath).exists():
            raw = Path(filepath).read_text("utf-8", errors="replace")
            return yaml.safe_load(raw) or {}
    except Exception:
        pass
    return {}


# ----- CostController -----
class CostController:
    """Token消耗监控"""
    def __init__(self, db_path, daily_token_limit=500000, monthly_token_limit=10000000,
                 cost_warning=50.0):
        self.db_path = db_path
        self.daily_token_limit = daily_token_limit
        self.monthly_token_limit = monthly_token_limit
        self.cost_warning = cost_warning
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile TEXT DEFAULT 'default',
                model TEXT DEFAULT 'deepseek-chat',
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                cost_yuan REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_token_usage_created ON token_usage(created_at)")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"CostController DB init failed: {e}")

    def calculate_cost(self, input_tokens, output_tokens):
        input_cost = (input_tokens / 1_000_000) * LLM_PRICES["input_per_1m"]
        output_cost = (output_tokens / 1_000_000) * LLM_PRICES["output_per_1m"]
        return round(input_cost + output_cost, 4)

    def record_usage(self, input_tokens, output_tokens, profile="default", model="deepseek-chat"):
        total_tokens = input_tokens + output_tokens
        cost = self.calculate_cost(input_tokens, output_tokens)
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO token_usage (profile, model, input_tokens, output_tokens, total_tokens, cost_yuan) VALUES (?,?,?,?,?,?)",
                (profile, model, input_tokens, output_tokens, total_tokens, cost)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"record_usage failed: {e}")

    def get_daily_usage(self):
        today = date.today().isoformat()
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT COUNT(*) as call_count, COALESCE(SUM(total_tokens),0) as total_tokens, COALESCE(SUM(cost_yuan),0) as cost_yuan FROM token_usage WHERE created_at LIKE ?",
                (today + "%",)
            ).fetchone()
            conn.close()
            return dict(row)
        except Exception:
            return {"call_count": 0, "total_tokens": 0, "cost_yuan": 0}

    def get_monthly_usage(self):
        month_start = date.today().strftime("%Y-%m")
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT COUNT(*) as call_count, COALESCE(SUM(total_tokens),0) as total_tokens, COALESCE(SUM(cost_yuan),0) as cost_yuan FROM token_usage WHERE created_at LIKE ?",
                (month_start + "%",)
            ).fetchone()
            conn.close()
            return dict(row)
        except Exception:
            return {"call_count": 0, "total_tokens": 0, "cost_yuan": 0}

    def check_quota(self):
        daily = self.get_daily_usage()
        monthly = self.get_monthly_usage()
        return {
            "daily_exceeded": daily["total_tokens"] >= self.daily_token_limit,
            "monthly_exceeded": monthly["total_tokens"] >= self.monthly_token_limit,
            "cost_exceeded": monthly["cost_yuan"] >= self.cost_warning,
            "daily_usage": daily,
            "monthly_usage": monthly,
        }

    def get_profile_breakdown(self, days=7):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT profile, COUNT(*) as call_count, COALESCE(SUM(total_tokens),0) as total_tokens,
                   COALESCE(SUM(cost_yuan),0) as cost_yuan
                   FROM token_usage
                   WHERE created_at >= datetime('now', ?)
                   GROUP BY profile ORDER BY cost_yuan DESC""",
                (f"-{days} days",)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []


# ------------------------------------------------------------
# 配置加载（从 config.yaml 读取路径，不存在时 fallback 硬编码）
# ------------------------------------------------------------
CONFIG_CACHE = None


def load_config():
    """从同目录 config.yaml 加载配置，返回路径字典。
    如果文件不存在则返回 None（触发 fallback 到硬编码）。
    """
    global CONFIG_CACHE
    if CONFIG_CACHE is not None:
        return CONFIG_CACHE
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            CONFIG_CACHE = cfg.get("baize_console", {}).get("paths", {})
            return CONFIG_CACHE
        except Exception as e:
            print(f"[config] 加载 config.yaml 失败: {e}，使用硬编码 fallback")
    return None


def resolve_path(key: str) -> str:
    """从配置中解析路径。对 base_dir 做平台检测，其他路径拼接 base_dir。"""
    cfg = load_config()
    if cfg is None:
        return None  # 触发 fallback
    base = cfg.get("base_dir", {})
    if sys.platform == "win32":
        base_dir = Path(base.get("windows", "D:/向海容的知识库/wiki/wiki/记忆宫殿"))
    else:
        base_dir = Path(base.get("linux", "/mnt/d/向海容的知识库/wiki/wiki/记忆宫殿"))
    rel = cfg.get(key)
    if rel is None:
        return None
    return str(base_dir / rel)


# ============================================================
# Token消耗监控 — 已抽取到 baize_libs/cost_controller.py
# 本文件通过 from baize_libs.cost_controller import ... 使用
# 保留 get_cost_controller 单例（因为依赖 app.py 的 BASE_DIR）
# ============================================================

# 全局单例（延迟初始化）
_cost_controller_instance = None


def get_cost_controller():
    """获取或创建 CostController 单例"""
    global _cost_controller_instance
    if _cost_controller_instance is None:
        _path = resolve_path("token_usage")
        if _path:
            db_path = _path
        else:
            db_path = str(BASE_DIR / "L5孵化室" / "产品开发" / "白泽控制台" / "token_usage.db")
        _cost_controller_instance = CostController(db_path)
    return _cost_controller_instance

# ============================================================
# 0. Server 入口模式: env → logging → init → start
# ============================================================

_cfg = load_config()
if _cfg is not None:
    # 从 config.yaml 读取
    base_cfg = _cfg.get("base_dir", {})
    if sys.platform == "win32":
        BASE_DIR = Path(base_cfg.get("windows", "D:/向海容的知识库/wiki/wiki/记忆宫殿"))
    else:
        BASE_DIR = Path(base_cfg.get("linux", "/mnt/d/向海容的知识库/wiki/wiki/记忆宫殿"))
    MEMORY_DB = BASE_DIR / _cfg.get("memory_db", "memory.db")
    EMPLOYEES_DIR = BASE_DIR / _cfg.get("employees", "employees")
    SKILLS_DIR = BASE_DIR / _cfg.get("skills", "skills")
    STATUS_MD = BASE_DIR / _cfg.get("status_md", "L0前厅/3+X窗口/状态总览.md")
    DECISIONS_DIR = BASE_DIR / _cfg.get("decisions_dir", "L3工作室/CEO战略分析/每日决策")
else:
    # fallback: 硬编码（向后兼容）
    if sys.platform == "win32":
        BASE_DIR = Path("D:/向海容的知识库/wiki/wiki/记忆宫殿")
    else:
        BASE_DIR = Path("/mnt/d/向海容的知识库/wiki/wiki/记忆宫殿")
    MEMORY_DB = BASE_DIR / "memory.db"
    EMPLOYEES_DIR = BASE_DIR / "employees"
    SKILLS_DIR = BASE_DIR / "skills"
    STATUS_MD = BASE_DIR / "L0前厅/3+X窗口/状态总览.md"
    DECISIONS_DIR = BASE_DIR / "L3工作室/CEO战略分析/每日决策"
# 清理文件末尾的logout残留
import _io as _cleanup_io
for _f in [MEMORY_DB, STATUS_MD]:
    if isinstance(_f, Path) and _f.exists():
        try:
            _raw = _f.read_text("utf-8", errors="replace")
            if _raw.rstrip().endswith("logout"):
                _f.write_text(_raw.rstrip()[:-6].rstrip() + "\n", "utf-8")
                logger.info(f"Cleaned logout residue from {_f.name}")
        except Exception:
            pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("baize")

app = Flask(__name__)

# ------------------------------------------------------------
# 数据获取函数 — 已抽取到 baize_libs/db_utils.py + yaml_parser.py
# 本文件通过 from baize_libs.xxx import ... 使用
# 保留 get_cost_controller 和 approve_log 相关（依赖 BASE_DIR）
# ------------------------------------------------------------

registry = ActionRegistry()


# ============================================================
# 审批日志表 (approve_log.db) — BUG-3 FIXED: 后端持久化审批
# ============================================================

APPROVE_DB = None  # 延迟初始化


def get_approve_db_path():
    """获取审批日志数据库路径"""
    _path = resolve_path("approve_log")
    if _path:
        db_dir = Path(_path).parent
        os.makedirs(str(db_dir), exist_ok=True)
        return str(Path(_path))
    db_dir = BASE_DIR / "L5孵化室" / "产品开发" / "白泽控制台"
    os.makedirs(str(db_dir), exist_ok=True)
    return str(db_dir / "approve_log.db")


def init_approve_db():
    """初始化审批日志数据库表"""
    global APPROVE_DB
    db_path = get_approve_db_path()
    APPROVE_DB = db_path
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS approve_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('approve','reject')),
                reason TEXT DEFAULT '',
                operator TEXT DEFAULT 'system',
                created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_approve_log_activity ON approve_log(activity_id)")
        conn.commit()
        logger.info(f"审批数据库已初始化: {db_path}")
    except Exception as e:
        logger.warning(f"审批数据库初始化失败: {e}")
    finally:
        conn.close()


def record_approval(activity_id: str, action: str, reason: str = "", operator: str = "system") -> dict:
    """记录一条审批操作到数据库"""
    if APPROVE_DB is None:
        init_approve_db()
    conn = sqlite3.connect(APPROVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "INSERT INTO approve_log (activity_id, action, reason, operator) VALUES (?,?,?,?)",
            (activity_id, action, reason, operator)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM approve_log WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row) if row else {"id": cur.lastrowid}
    except Exception as e:
        logger.error(f"记录审批失败: {e}")
        raise
    finally:
        conn.close()


def get_approval_logs(activity_id: str = None) -> list:
    """查询审批日志，可按activity_id过滤"""
    if APPROVE_DB is None:
        init_approve_db()
    conn = sqlite3.connect(APPROVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        if activity_id:
            rows = conn.execute(
                "SELECT * FROM approve_log WHERE activity_id=? ORDER BY created_at DESC",
                (activity_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM approve_log ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# 应用启动时初始化审批数据库
init_approve_db()

# ----- 指标卡数据 -----

@registry.action("stats")
def get_stats():
    """顶部4个指标卡 (带5秒缓存)"""
    now = time.time()
    if now - _stats_cache["ts"] < 5:
        return _stats_cache["data"]
    return _stats_compute()

# ----- stats 缓存 -----
_stats_cache = {"ts": 0, "data": {}}

def _stats_compute():
    """实际计算统计指标"""
    # 员工总数
    emp_dirs = [d for d in os.listdir(str(EMPLOYEES_DIR))
                if d.startswith("emp-") and os.path.isdir(os.path.join(str(EMPLOYEES_DIR), d))]
    total_employees = len(emp_dirs)

    # 在线员工 (有 memory/memory.db 的)
    online = 0
    for d in emp_dirs:
        mem_db = EMPLOYEES_DIR / d / "memory" / "memory.db"
        if mem_db.exists():
            online += 1

    # 今日记忆
    today_str = date.today().isoformat()
    today_memories = 0
    conn = _safe_read_db(MEMORY_DB)
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM memories WHERE created_at LIKE ?", (today_str + "%",))
            today_memories = cur.fetchone()[0]
        except Exception as e:
            logger.warning(f"Today memory count failed: {e}")
        finally:
            conn.close()

    # 技能总数（从 employee.yaml 统计去重技能数）
    skill_count = 0
    if EMPLOYEES_DIR.exists():
        unique_skills = set()
        for d in os.listdir(str(EMPLOYEES_DIR)):
            if not d.startswith("emp-") or not os.path.isdir(os.path.join(str(EMPLOYEES_DIR), d)):
                continue
            yaml_path = EMPLOYEES_DIR / d / "employee.yaml"
            data = _parse_yaml_robust(yaml_path)
            caps = data.get("capabilities", [])
            if isinstance(caps, list):
                for c in caps:
                    if isinstance(c, str):
                        unique_skills.add(c)
        skill_count = len(unique_skills)

    result = {
        "total_employees": total_employees,
        "online_employees": online,
        "today_memories": today_memories,
        "total_skills": skill_count,
    }
    _stats_cache["ts"] = time.time()
    _stats_cache["data"] = result
    return result


# ----- 员工状态表 -----

@registry.action("employees")
def get_employees():
    """所有员工状态表"""
    emp_dirs = sorted([
        d for d in os.listdir(str(EMPLOYEES_DIR))
        if d.startswith("emp-") and os.path.isdir(os.path.join(str(EMPLOYEES_DIR), d))
    ])

    employees = []
    for d in emp_dirs:
        emp_dir = EMPLOYEES_DIR / d
        yaml_path = emp_dir / "employee.yaml"
        mem_db = emp_dir / "memory" / "memory.db"

        # 解析yaml
        data = _parse_yaml_robust(yaml_path)

        # 员工名: name / metadata.name / soul_architecture.employee_name
        name = data.get("name", "")
        if not name and "metadata" in data and isinstance(data["metadata"], dict):
            name = data["metadata"].get("name", "")
        if not name and "soul_architecture" in data and isinstance(data["soul_architecture"], dict):
            name = data["soul_architecture"].get("employee_name", "")
        # fallback: 从目录名提取
        if not name:
            # emp-名称-id → 提取中间部分
            parts = d.split("-", 2)
            name = parts[1] if len(parts) > 1 else d

        # 角色: capabilities.type / capabilities[0] / soul_architecture.role
        role = ""
        capabilities = data.get("capabilities", [])
        if isinstance(capabilities, list) and capabilities:
            role = capabilities[0] if isinstance(capabilities[0], str) else str(capabilities[0])
        elif isinstance(capabilities, dict):
            role = capabilities.get("type", "")
        if not role and "soul_architecture" in data and isinstance(data["soul_architecture"], dict):
            role = data["soul_architecture"].get("role", "")
        # 从type字段
        if not role:
            role = data.get("type", "")

        # 级别
        level = data.get("level", "")

        # 记忆条数和最后活动
        memory_count = 0
        last_active = ""
        conn = _safe_read_db(mem_db)
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM memories")
                memory_count = cur.fetchone()[0]
                cur.execute("SELECT MAX(created_at) FROM memories")
                row = cur.fetchone()
                if row and row[0]:
                    last_active = row[0][:16]  # 格式化到分钟
            except Exception:
                pass
            finally:
                conn.close()

        employees.append({
            "id": d,
            "name": name or d,
            "role": role or "-",
            "level": level or "-",
            "memory_count": memory_count,
            "last_active": last_active or "-",
        })

    return {"employees": employees}


# ----- 员工心跳检测 -----

@registry.action("employee_heartbeat")
def get_employee_heartbeat():
    """扫描所有 employees/emp-*/employee.yaml，读取 evolution/collaboration/memory 状态"""
    emp_dirs = sorted([
        d for d in os.listdir(str(EMPLOYEES_DIR))
        if d.startswith("emp-") and os.path.isdir(os.path.join(str(EMPLOYEES_DIR), d))
    ])

    heartbeats = []
    for d in emp_dirs:
        emp_dir = EMPLOYEES_DIR / d
        yaml_path = emp_dir / "employee.yaml"
        mem_db = emp_dir / "memory" / "memory.db"

        data = _parse_yaml_robust(yaml_path)

        # 员工名
        name = data.get("name", "")
        if not name and "metadata" in data and isinstance(data["metadata"], dict):
            name = data["metadata"].get("name", "")
        if not name and "soul_architecture" in data and isinstance(data["soul_architecture"], dict):
            name = data["soul_architecture"].get("employee_name", "")
        if not name:
            parts = d.split("-", 2)
            name = parts[1] if len(parts) > 1 else d

        # 读取 evolution / collaboration / memory 状态
        evolution_status = ""
        collaboration_status = ""
        memory_status = ""

        if isinstance(data, dict):
            evo = data.get("evolution", {})
            if isinstance(evo, dict):
                evolution_status = evo.get("status", evo.get("phase", ""))

            col = data.get("collaboration", {})
            if isinstance(col, dict):
                collaboration_status = col.get("status", col.get("mode", ""))

            mem = data.get("memory", {})
            if isinstance(mem, dict):
                memory_status = mem.get("status", mem.get("state", ""))

        # memory.db 信息
        last_active = ""
        memory_count = 0
        conn = _safe_read_db(mem_db)
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM memories")
                memory_count = cur.fetchone()[0]
                cur.execute("SELECT MAX(created_at) FROM memories")
                row = cur.fetchone()
                if row and row[0]:
                    last_active = row[0][:16]
            except Exception:
                pass
            finally:
                conn.close()

        # activity_score (0-100): 基于 memory_count 和 last_active 新鲜度
        activity_score = 0
        if memory_count > 0:
            score_from_count = min(50, memory_count * 5)
            if last_active:
                try:
                    from datetime import datetime as dt
                    last = dt.strptime(last_active[:10], "%Y-%m-%d")
                    days_since = (dt.now() - last).days
                    freshness = max(0, 50 - days_since * 3)
                    activity_score = min(100, score_from_count + freshness)
                except Exception:
                    activity_score = score_from_count

        status = "online" if mem_db.exists() and memory_count > 0 else "offline"
        evolution_enabled = isinstance(data.get("evolution"), dict) and data["evolution"].get("enabled", False)
        collaboration_enabled = isinstance(data.get("collaboration"), dict) and data["collaboration"].get("enabled", False)

        heartbeats.append({
            "id": d,
            "name": name or d,
            "status": status,
            "evolution_enabled": evolution_enabled,
            "collaboration_enabled": collaboration_enabled,
            "evolution_status": evolution_status or "-",
            "collaboration_status": collaboration_status or "-",
            "memory_status": memory_status or "-",
            "memory_count": memory_count,
            "last_active": last_active or "-",
            "activity_score": activity_score,
        })

    return {"heartbeats": heartbeats, "total": len(heartbeats)}


# ----- 最近活动时间线 (EventStream 模式) — 已吸收 Mission Control Activity Event + 审计架构 -----

def _resolve_category(content, tags):
    """从内容和标签推断活动类别（Mission Control 风格事件类型）"""
    content_lower = (content or "").lower()
    tags_lower = (tags or "").lower()

    if any(kw in content_lower or kw in tags_lower for kw in ["审批", "审核", "approve", "批准"]):
        return "approval"
    elif any(kw in content_lower or kw in tags_lower for kw in ["部署", "发布", "deploy", "release"]):
        return "deployment"
    elif any(kw in content_lower or kw in tags_lower for kw in ["决策", "决定", "decide", "决策"]):
        return "decision"
    elif any(kw in content_lower or kw in tags_lower for kw in ["错误", "失败", "error", "fail", "异常"]):
        return "error"
    elif any(kw in content_lower or kw in tags_lower for kw in ["创建", "新增", "create", "添加", "注册"]):
        return "creation"
    elif any(kw in content_lower or kw in tags_lower for kw in ["更新", "修改", "update", "编辑", "变更"]):
        return "update"
    elif any(kw in content_lower or kw in tags_lower for kw in ["删除", "移除", "delete", "remove"]):
        return "deletion"
    else:
        return "general"


def _determine_audit_status(importance, category):
    """基于 Mission Control 审批三级 gate 模拟审计状态"""
    if category in ("approval", "deployment", "decision"):
        # 敏感操作，重要性 > 0.7 需要审批
        if importance >= 0.7:
            return "pending_review"
        elif importance >= 0.4:
            return "confirmed"
        else:
            return "confirmed"
    elif category in ("error",):
        return "pending_review"
    else:
        return "confirmed"


@registry.action("recent_activities")
def get_recent_activities():
    """从主memory.db取最近15条记录 (原始接口，向后兼容) — BUG-3: 同步审批状态"""
    conn = _safe_read_db(MEMORY_DB)
    if not conn:
        return {"activities": []}

    activities = []
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, session_id, project_name, content, importance,
                   tags, timestamp, created_at, employee_id
            FROM memories
            ORDER BY created_at DESC
            LIMIT 15
        """)
        for row in cur.fetchall():
            content = row["content"] or ""
            summary = content[:80] + "..." if len(content) > 80 else content
            ts = row["created_at"] or row["timestamp"] or ""
            imp = row["importance"] or 0
            stars = "★" * max(1, min(5, round(imp * 5)))
            tags = row["tags"] or ""
            employee_id = row["employee_id"] or ""

            category = _resolve_category(content, tags)
            activity_id = row["id"][:8]

            # BUG-3 FIXED: 先查审批日志确认是否有过审批操作
            existing_logs = get_approval_logs(activity_id)
            if existing_logs:
                # 以最新审批记录为准
                latest_action = existing_logs[0]["action"]
                audit_status = "confirmed" if latest_action == "approve" else "rejected"
            else:
                audit_status = _determine_audit_status(imp, category)

            activities.append({
                "id": activity_id,
                "time": ts[:16] if len(ts) > 16 else ts,
                "project": row["project_name"] or "-",
                "summary": summary,
                "importance": round(imp, 2),
                "stars": stars,
                "employee_id": employee_id,
                "category": category,
                "audit_status": audit_status,
                # BUG-3: 只在 pending_review 且无已有审批记录时允许操作
                "can_approve": audit_status == "pending_review" and not existing_logs,
            })
    except Exception as e:
        logger.warning(f"Recent activities query failed: {e}")
    finally:
        conn.close()

    return {"activities": activities}


@registry.action("activity_timeline")
def get_activity_timeline():
    """活动时间线审计版 — 按天分组，带category和审计状态（Mission Control Activity Event 模式）— BUG-3: 同步审批状态"""
    conn = _safe_read_db(MEMORY_DB)
    if not conn:
        return {"timeline": []}

    # 取更多数据用于按天分组
    all_activities = []
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, session_id, project_name, content, importance,
                   tags, timestamp, created_at, employee_id
            FROM memories
            WHERE created_at IS NOT NULL AND created_at != ''
            ORDER BY created_at DESC
            LIMIT 50
        """)
        for row in cur.fetchall():
            content = row["content"] or ""
            summary = content[:80] + "..." if len(content) > 80 else content
            ts = row["created_at"] or row["timestamp"] or ""
            imp = row["importance"] or 0
            stars = "★" * max(1, min(5, round(imp * 5)))
            tags = row["tags"] or ""
            employee_id = row["employee_id"] or ""

            category = _resolve_category(content, tags)
            activity_id = row["id"][:8]

            # BUG-3 FIXED: 先查审批日志确认是否有过审批操作
            existing_logs = get_approval_logs(activity_id)
            if existing_logs:
                latest_action = existing_logs[0]["action"]
                audit_status = "confirmed" if latest_action == "approve" else "rejected"
            else:
                audit_status = _determine_audit_status(imp, category)

            # 提取日期 (YYYY-MM-DD)
            date_key = ts[:10] if len(ts) >= 10 else "unknown"

            all_activities.append({
                "id": activity_id,
                "time": ts[:16] if len(ts) > 16 else ts,
                "date_key": date_key,
                "project": row["project_name"] or "-",
                "summary": summary,
                "importance": round(imp, 2),
                "stars": stars,
                "employee_id": employee_id,
                "category": category,
                "audit_status": audit_status,
                "can_approve": audit_status == "pending_review" and not existing_logs,
            })
    except Exception as e:
        logger.warning(f"Activity timeline query failed: {e}")
        return {"timeline": []}
    finally:
        if conn:
            conn.close()

    # 按天分组
    from collections import OrderedDict
    grouped = OrderedDict()
    for act in all_activities:
        dk = act.pop("date_key")
        if dk not in grouped:
            grouped[dk] = {"date": dk, "activities": [], "count": 0}
        grouped[dk]["activities"].append(act)
        grouped[dk]["count"] += 1

    return {"timeline": list(grouped.values())}


# ----- 系统概览 -----

@registry.action("system_overview")
def get_system_overview():
    """3+X窗口状态 + 今日决策板链接"""
    # 读取状态总览.md（加固解析：支持嵌套管道、行内格式、多行单元格）
    windows = []
    if STATUS_MD.exists():
        content = STATUS_MD.read_text("utf-8", errors="replace")
        in_table = False
        for line in content.split("\n"):
            # 检测表格行: 以|开头且不是对齐行(|---|)
            stripped = line.strip()
            if not stripped.startswith("|") or stripped.startswith("|:") or stripped.startswith("|-"):
                continue
            # 跳过表头行(包含"窗口"字样的第一行)
            if "窗口" in stripped and "模式" in stripped and "状态" in stripped:
                continue
            # 安全分割：先去掉首尾|，再按|分割，考虑转义管道(\\|)
            cells_raw = stripped.strip("|").split("|")
            cells = [c.strip() for c in cells_raw if c.strip()]
            if len(cells) < 3:
                continue
            window_name = cells[0]
            mode = cells[1] if len(cells) > 1 else ""
            status_raw = cells[2] if len(cells) > 2 else ""
            task = cells[3] if len(cells) > 3 else ""
            updated = cells[4] if len(cells) > 4 else ""

            # 状态转换成emoji（先清除markdown标记）
            clean_status = status_raw.replace("**", "").replace("*", "").strip()
            if "已完成" in clean_status or "活跃" in clean_status or "已唤醒" in clean_status or "已审计" in clean_status or "已复盘" in clean_status:
                status_icon = "🟢"
            elif "进行" in clean_status or "处理" in clean_status or "运行中" in clean_status:
                status_icon = "🟢"
            elif "待重启" in clean_status:
                status_icon = "🟡"
            elif "未创建" in clean_status:
                status_icon = "⚪"
            else:
                status_icon = "🔴"

            windows.append({
                "name": window_name,
                "mode": mode,
                "status": status_raw,
                "status_icon": status_icon,
                "task": task,
                "updated": updated,
            })

    # 当日决策板
    latest_decision = ""
    latest_decision_path = ""
    if DECISIONS_DIR.exists():
        files = sorted([
            f for f in os.listdir(str(DECISIONS_DIR))
            if f.endswith(".md") and "决策板" in f
        ], reverse=True)
        if files:
            latest_decision = files[0]
            latest_decision_path = str(DECISIONS_DIR / files[0])

    return {
        "windows": windows,
        "latest_decision": latest_decision,
        "latest_decision_path": latest_decision_path,
    }


# ----- 员工搜索 -----

@registry.action("search_employee")
def search_employee(query: str = ""):
    """搜索员工，支持姓名/角色/ID模糊匹配"""
    if not query or len(query.strip()) < 1:
        return get_employees()

    q = query.strip().lower()
    all_emps = get_employees().get("employees", [])
    results = []

    for emp in all_emps:
        if (q in emp.get("name", "").lower() or
            q in emp.get("role", "").lower() or
            q in emp.get("id", "").lower() or
            q in emp.get("level", "").lower()):
            results.append(emp)

    return {"employees": results, "total": len(all_emps), "matched": len(results)}


# ----- 员工灵魂查询 (Soul API) -----

def _parse_soul_role(behavior_text):
    """从behavior_protocol.md提取角色"""
    try:
        for line in behavior_text.split('\n'):
            line = line.strip()
            if line.startswith('> 角色：'):
                return line.split('> 角色：', 1)[1].strip()
            if '角色：' in line and '研发' in line or '架构' in line or '工程师' in line:
                # 尝试从行内提取
                if '角色：' in line:
                    return line.split('角色：', 1)[1].strip()
    except Exception:
        pass
    return ""


def _parse_soul_personality(behavior_text):
    """从behavior_protocol.md第2章提取说话风格标签"""
    personality = []
    try:
        in_speech_style = False
        for line in behavior_text.split('\n'):
            line = line.strip()
            if '二、说话风格' in line or '## 二、说话风格' in line:
                in_speech_style = True
                continue
            if in_speech_style:
                if line.startswith('## ') or (line.startswith('###') and '语气示例' not in line):
                    break
                if line.startswith('- **') and '**：' in line:
                    tag = line.split('- **', 1)[1].split('**', 1)[0].strip()
                    if tag:
                        personality.append(tag)
                # Also catch "技术直男" format
                if line.startswith('- **') and '**：' not in line and '**' in line:
                    tag = line.split('- **', 1)[1].split('**', 1)[0].strip()
                    if tag and tag not in personality:
                        personality.append(tag)
        # Fallback: scan for bullet speech traits
        if not personality:
            for line in behavior_text.split('\n'):
                line = line.strip()
                if '- **技术直男**' in line:
                    personality.append('技术直男')
                if '- **直接批评**' in line:
                    personality.append('直接批评')
                if '- **数据驱动**' in line:
                    personality.append('数据驱动')
                if '- **简洁粗暴**' in line:
                    personality.append('简洁粗暴')
    except Exception:
        pass
    return personality if personality else ['严肃', '专业']


def _parse_soul_core_duty(behavior_text, context_text):
    """从behavior或context提取核心职责"""
    # Try behavior_protocol first
    for text in [behavior_text, context_text]:
        for line in text.split('\n'):
            line = line.strip()
            if '核心职责：' in line:
                return line.split('核心职责：', 1)[1].strip()
            if '核心职责' in line and '：' in line:
                return line.split('核心职责', 1)[1].strip('：: ')
    # Try "我是..." pattern
    for text in [behavior_text, context_text]:
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('我是') and '。' in line and len(line) < 100:
                parts = line.split('。', 1)
                if len(parts) > 1 and '职责' in parts[1]:
                    duty = parts[1].strip()
                    if duty.startswith('的'):
                        duty = duty[1:].strip()
                    return duty
    return ""


def _parse_soul_team_relations(behavior_text, context_text):
    """从behavior_protocol第五章或context_template提取团队关系"""
    relations = []
    try:
        in_relations = False
        for line in behavior_text.split('\n'):
            line = line.strip()
            if '五、与同事的关系' in line or '## 五、与同事的关系' in line:
                in_relations = True
                continue
            if in_relations:
                if line.startswith('## ') or line.startswith('六、'):
                    break
                if line.startswith('|') and '|' in line and not line.startswith('|:') and not line.startswith('|-'):
                    cells = [c.strip() for c in line.strip('|').split('|')]
                    if len(cells) >= 2 and cells[0] not in ['场景', '关系', '']:
                        name = cells[0]
                        rel = cells[1] if len(cells) > 1 else ''
                        if '——' in rel:
                            rel = rel.split('——', 1)[1].strip()
                        elif '—' in rel:
                            rel = rel.split('—', 1)[1].strip()
                        if name and rel:
                            relations.append({"with": name, "relation": rel})

        # Fallback: from context_template
        if not relations:
            for line in context_text.split('\n'):
                line = line.strip()
                if line.startswith('- ') and '(' in line and ')' in line:
                    parts = line.split('(', 1)
                    name = parts[0].replace('- ', '').strip().rstrip('）)')
                    rel = parts[1].rstrip('）)') if len(parts) > 1 else ''
                    if name and rel:
                        relations.append({"with": name, "relation": rel})
    except Exception:
        pass
    return relations


def _parse_anchor_weights(anchors_data):
    """从emotional_anchors.json提取锚点权重"""
    weights = {}
    try:
        anchors = anchors_data.get('anchors', {}) if isinstance(anchors_data, dict) else {}
        for key, val in anchors.items():
            if isinstance(val, dict):
                w = val.get('weight', 0)
                if w:
                    weights[key] = w
    except Exception:
        pass
    return weights


@registry.action("employee_souls")
def get_employee_souls():
    """返回所有员工的灵魂信息（身份/性格/说话风格/团队关系）"""
    emp_dirs = sorted([
        d for d in os.listdir(str(EMPLOYEES_DIR))
        if d.startswith("emp-") and os.path.isdir(os.path.join(str(EMPLOYEES_DIR), d))
    ])

    souls = []
    for d in emp_dirs:
        try:
            emp_dir = EMPLOYEES_DIR / d
            soul_dir = emp_dir / "soul"
            yaml_path = emp_dir / "employee.yaml"
            mem_db = emp_dir / "memory" / "memory.db"

            # Parse employee.yaml for basic info
            data = _parse_yaml_robust(yaml_path)

            name = data.get("name", "")
            if not name and "metadata" in data and isinstance(data["metadata"], dict):
                name = data["metadata"].get("name", "")
            if not name:
                parts = d.split("-", 2)
                name = parts[1] if len(parts) > 1 else d

            level = data.get("level", "")
            soul_source = data.get("soul_source", "")
            role = data.get("type", "")

            # Read soul files (graceful fallback if missing)
            behavior_text = ""
            context_text = ""
            anchors_data = {}
            mental_models = []

            if soul_dir.exists():
                # behavior_protocol.md
                bp_file = soul_dir / "behavior_protocol.md"
                if bp_file.exists():
                    try:
                        behavior_text = bp_file.read_text("utf-8", errors="replace")
                    except Exception:
                        pass

                # context_template.md
                ct_file = soul_dir / "context_template.md"
                if ct_file.exists():
                    try:
                        context_text = ct_file.read_text("utf-8", errors="replace")
                    except Exception:
                        pass

                # emotional_anchors.json
                ea_file = soul_dir / "emotional_anchors.json"
                if ea_file.exists():
                    try:
                        import json as _json
                        anchors_data = _json.loads(ea_file.read_text("utf-8", errors="replace"))
                    except Exception:
                        anchors_data = {}

                # mental_models.json
                mm_file = soul_dir / "mental_models.json"
                if mm_file.exists():
                    try:
                        import json as _json
                        models_data = _json.loads(mm_file.read_text("utf-8", errors="replace"))
                        mental_models = models_data.get("models", []) if isinstance(models_data, dict) else []
                    except Exception:
                        mental_models = []

            # Parse role from behavior_protocol if available
            role_from_bp = _parse_soul_role(behavior_text)
            if role_from_bp:
                role = role_from_bp

            # Parse personality
            personality = _parse_soul_personality(behavior_text)

            # Parse core duty
            core_duty = _parse_soul_core_duty(behavior_text, context_text)

            # Fallback: role description from context_template
            if not role and context_text:
                for line in context_text.split('\n'):
                    line = line.strip()
                    if '我是' in line and '，' in line:
                        parts = line.split('，', 1)
                        if '我是' in parts[0]:
                            role = parts[1].strip().rstrip('。')
                            break

            # Parse team relations
            team_relations = _parse_soul_team_relations(behavior_text, context_text)

            # Parse anchor weights
            anchor_weights = _parse_anchor_weights(anchors_data)

            # Count mental models
            mental_models_count = len(mental_models)

            # Memory count and last active
            memory_count = 0
            last_active = ""
            conn = _safe_read_db(mem_db)
            if conn:
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM memories")
                    memory_count = cur.fetchone()[0]
                    cur.execute("SELECT MAX(created_at) FROM memories")
                    row = cur.fetchone()
                    if row and row[0]:
                        last_active = row[0][:19]  # ISO format
                except Exception:
                    pass
                finally:
                    conn.close()

            soul_entry = {
                "id": d,
                "name": name or d,
                "role": role or "-",
                "personality": personality,
                "core_duty": core_duty or "-",
                "soul_source": soul_source or "-",
                "level": level or "-",
                "team_relations": team_relations,
                "mental_models_count": mental_models_count,
                "anchor_weights": anchor_weights,
                "memory_count": memory_count,
                "last_active": last_active or "-",
            }
            souls.append(soul_entry)
        except Exception as e:
            logger.warning(f"[souls] 处理员工 {d} 时出错: {e}")
            # Add with defaults
            souls.append({
                "id": d,
                "name": d.replace("emp-", "").rsplit("-", 1)[0] if "-" in d else d,
                "role": "-",
                "personality": [],
                "core_duty": "-",
                "soul_source": "-",
                "level": "-",
                "team_relations": [],
                "mental_models_count": 0,
                "anchor_weights": {},
                "memory_count": 0,
                "last_active": "-",
            })

    return {"souls": souls, "total": len(souls)}


# ----- 员工记忆查询 -----

@registry.action("employee_memories")
def get_employee_memories(emp_id: str = "", limit: int = 30):
    """根据 emp_id 读取 memory.db, 按重要性排序返回"""
    if not emp_id:
        return {"memories": [], "total": 0, "importance_stats": {"high": 0, "medium": 0, "low": 0}}

    emp_dir = EMPLOYEES_DIR / emp_id
    mem_db = emp_dir / "memory" / "memory.db"
    conn = _safe_read_db(mem_db)
    if not conn:
        return {"memories": [], "total": 0, "importance_stats": {"high": 0, "medium": 0, "low": 0}}

    memories = []
    high = medium = low = 0
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, session_id, project_name, content, importance,
                   tags, timestamp, created_at
            FROM memories
            ORDER BY COALESCE(importance, 0) DESC
            LIMIT ?
        """, (limit,))
        for row in cur.fetchall():
            imp = row["importance"] or 0
            if imp >= 0.7:
                high += 1
            elif imp >= 0.4:
                medium += 1
            else:
                low += 1

            content = row["content"] or ""
            summary = content[:120] + "..." if len(content) > 120 else content

            memories.append({
                "id": row["id"][:8] if row["id"] else "",
                "session_id": row["session_id"] or "",
                "project_name": row["project_name"] or "",
                "summary": summary,
                "importance": round(imp, 2),
                "tags": row["tags"] or "",
                "timestamp": (row["created_at"] or row["timestamp"] or "")[:16],
            })
    except Exception as e:
        logger.warning(f"Employee memories query failed for {emp_id}: {e}")
    finally:
        conn.close()

    # 如果个人记忆为空，回退到全局 memory.db
    if not memories:
        global_conn = _safe_read_db(MEMORY_DB)
        if global_conn:
            try:
                cur = global_conn.cursor()
                # 匹配员工ID或名称
                cur.execute("""
                    SELECT id, session_id, project_name, content, importance,
                           tags, timestamp, created_at, employee_id
                    FROM memories
                    WHERE employee_id = ?
                    ORDER BY COALESCE(importance, 0) DESC, created_at DESC
                    LIMIT ?
                """, (emp_id, limit))
                for row in cur.fetchall():
                    content = row["content"] or ""
                    summary = content[:120] + "..." if len(content) > 120 else content
                    imp = row["importance"] or 0
                    if imp >= 0.7:
                        high += 1
                    elif imp >= 0.4:
                        medium += 1
                    else:
                        low += 1
                    memories.append({
                        "id": row["id"][:8] if row["id"] else "",
                        "session_id": row["session_id"] or "",
                        "project_name": row["project_name"] or "",
                        "summary": summary,
                        "importance": round(imp, 2),
                        "tags": row["tags"] or "",
                        "timestamp": (row["created_at"] or row["timestamp"] or "")[:16],
                    })
            except Exception as e:
                logger.warning(f"Global memory fallback query failed for {emp_id}: {e}")
            finally:
                global_conn.close()

    # 二次回退：用员工名模糊搜索
    if not memories:
        try:
            name_parts = emp_id.replace('emp-', '').rsplit('-', 1)
            search_name = name_parts[0] if len(name_parts) > 1 else emp_id
            global_conn2 = _safe_read_db(MEMORY_DB)
            if global_conn2:
                try:
                    cur = global_conn2.cursor()
                    cur.execute("""
                        SELECT id, session_id, project_name, content, importance,
                               tags, timestamp, created_at, employee_id
                        FROM memories
                        WHERE content LIKE ? OR employee_id LIKE ?
                        ORDER BY COALESCE(importance, 0) DESC
                        LIMIT ?
                    """, (f'%{search_name}%', f'%{search_name}%', limit))
                    for row in cur.fetchall():
                        content = row["content"] or ""
                        summary = content[:120] + "..." if len(content) > 120 else content
                        imp = row["importance"] or 0
                        if imp >= 0.7:
                            high += 1
                        elif imp >= 0.4:
                            medium += 1
                        else:
                            low += 1
                        memories.append({
                            "id": row["id"][:8] if row["id"] else "",
                            "session_id": row["session_id"] or "",
                            "project_name": row["project_name"] or "",
                            "summary": summary,
                            "importance": round(imp, 2),
                            "tags": row["tags"] or "",
                            "timestamp": (row["created_at"] or row["timestamp"] or "")[:16],
                        })
                except Exception as e:
                    logger.warning(f"Fuzzy search failed for {emp_id}: {e}")
                finally:
                    global_conn2.close()
        except Exception as e:
            logger.warning(f"Fuzzy search prep failed for {emp_id}: {e}")

    return {
        "memories": memories,
        "total": len(memories),
        "importance_stats": {"high": high, "medium": medium, "low": low},
    }


# ----- 能力分析 -----

@registry.action("capability_analysis")
def get_capability_analysis():
    """扫描所有 employee.yaml 的 capabilities, 按 type/role 分类统计"""
    emp_dirs = sorted([
        d for d in os.listdir(str(EMPLOYEES_DIR))
        if d.startswith("emp-") and os.path.isdir(os.path.join(str(EMPLOYEES_DIR), d))
    ])

    role_map = {}
    total_skills = 0

    for d in emp_dirs:
        yaml_path = EMPLOYEES_DIR / d / "employee.yaml"
        data = _parse_yaml_robust(yaml_path)
        if not data:
            continue

        capabilities = data.get("capabilities", [])
        if isinstance(capabilities, dict):
            cap_type = capabilities.get("type", "")
            skills = capabilities.get("skills", [])
            if not isinstance(skills, list):
                skills = [skills] if skills else []
        elif isinstance(capabilities, list):
            cap_type = data.get("type", "general")
            skills = capabilities
        else:
            cap_type = ""
            skills = []

        if cap_type:
            role_map.setdefault(cap_type, {"role": cap_type, "count": 0, "skills": set()})
            role_map[cap_type]["count"] += 1
            for s in skills:
                if isinstance(s, str) and s.strip():
                    role_map[cap_type]["skills"].add(s.strip())
                    total_skills += 1

    roles = []
    for r in role_map.values():
        roles.append({
            "role": r["role"],
            "count": r["count"],
            "skills": sorted(r["skills"]),
            "skill_count": len(r["skills"]),
        })
    roles.sort(key=lambda x: x["count"], reverse=True)

    return {
        "roles": roles,
        "total_roles": len(roles),
        "total_skills": total_skills,
        "total_employees": len(emp_dirs),
    }


# ----- 组织树 -----

@registry.action("organization_tree")
def get_organization_tree():
    """按 type/role 分组形成组织树"""
    emp_dirs = sorted([
        d for d in os.listdir(str(EMPLOYEES_DIR))
        if d.startswith("emp-") and os.path.isdir(os.path.join(str(EMPLOYEES_DIR), d))
    ])

    # 先收集所有员工信息
    emp_info = []
    for d in emp_dirs:
        yaml_path = EMPLOYEES_DIR / d / "employee.yaml"
        data = _parse_yaml_robust(yaml_path)

        name = data.get("name", "")
        if not name and "metadata" in data and isinstance(data["metadata"], dict):
            name = data["metadata"].get("name", "")
        if not name:
            parts = d.split("-", 2)
            name = parts[1] if len(parts) > 1 else d

        # 优先使用 employee.yaml 中的 type 字段作为角色分组依据
        cap_type = data.get("type", "")
        if not cap_type:
            capabilities = data.get("capabilities", [])
            if isinstance(capabilities, dict):
                cap_type = capabilities.get("type", "")
            elif isinstance(capabilities, list):
                cap_type = data.get("type", "")
            else:
                cap_type = ""

        level = data.get("level", "")
        mem_db = EMPLOYEES_DIR / d / "memory" / "memory.db"
        memory_count = data.get("memory_count", 0) or 0
        emp_status = "online" if mem_db.exists() and memory_count > 0 else "offline"
        emp_info.append({
            "id": d,
            "name": name or d,
            "role": cap_type or "-",
            "level": level or "-",
            "status": emp_status,
        })

    # 按 type 分组组织树（两层结构：角色组 → 员工）
    # 去掉冗余的子组层（原来是 role→subrole→employee，subrole和role同名的冗余映射）
    from collections import defaultdict
    tree_groups = defaultdict(list)
    for emp in emp_info:
        role = emp["role"]
        tree_groups[role].append(emp)

    tree = []
    for role in sorted(tree_groups.keys()):
        members = tree_groups[role]
        tree.append({
            "name": role,
            "count": len(members),
            "children": members,
        })

    return {
        "tree": tree,
        "total_roles": len(tree),
        "total_employees": len(emp_info),
    }


# ----- Token 成本看板 -----

@registry.action("token_costs")
def get_token_costs():
    """Token消耗统计和成本看板数据"""
    try:
        controller = get_cost_controller()
        daily = controller.get_daily_usage()
        monthly = controller.get_monthly_usage()
        profiles = controller.get_profile_breakdown(days=7)
        return {
            "daily": daily,
            "monthly": monthly,
            "profiles": profiles,
            "limits": {
                "daily_token_limit": controller.daily_token_limit,
                "monthly_token_limit": controller.monthly_token_limit,
                "cost_warning_yuan": controller.cost_warning,
                "price_per_1m_input": LLM_PRICES["input_per_1m"],
                "price_per_1m_output": LLM_PRICES["output_per_1m"],
            }
        }
    except Exception as e:
        logger.warning(f"Token costs query failed: {e}")
        return {
            "daily": {"call_count": 0, "total_tokens": 0, "cost_yuan": 0},
            "monthly": {"call_count": 0, "total_tokens": 0, "cost_yuan": 0},
            "profiles": [],
            "limits": {},
        }


# ----- 烛龙Pipeline Action注册 -----

@registry.action("pipeline_stages")
@with_analytics("pipeline_stages")
def get_pipeline_stages():
    """返回14阶段定义列表"""
    return {"stages": PIPELINE_STAGES, "total": len(PIPELINE_STAGES)}


@registry.action("pipeline_start")
@with_analytics("pipeline_start")
def start_pipeline():
    """创建新的Pipeline run"""
    global _pipeline_run_counter
    _pipeline_run_counter += 1
    run_id = f"pipeline-{_pipeline_run_counter}"
    now = datetime.now().isoformat()
    stages = []
    for s in PIPELINE_STAGES:
        stages.append({
            "stage_id": s["id"],
            "name": s["name"],
            "icon": s["icon"],
            "status": "pending",
            "assignee": "",
            "started_at": None,
            "completed_at": None,
        })
    run_data = {
        "run_id": run_id,
        "created_at": now,
        "status": "running",
        "current_stage": "s0",
        "stages": stages,
        "progress": 0,
    }
    _pipeline_runs[run_id] = run_data
    return {"success": True, "run": run_data}


@registry.action("pipeline_status")
@with_analytics("pipeline_status")
def get_pipeline_status(run_id):
    """查询指定Pipeline run的状态"""
    run = _pipeline_runs.get(run_id)
    if not run:
        return {"error": f"Run not found: {run_id}"}
    # 计算进度
    completed = sum(1 for s in run["stages"] if s["status"] == "completed")
    progress = round(completed / len(run["stages"]) * 100, 1) if run["stages"] else 0
    run["progress"] = progress
    return {"success": True, "run": run}


@registry.action("pipeline_update_stage")
@with_analytics("pipeline_update_stage")
def update_pipeline_stage(run_id, stage_id, status, assignee=None):
    """更新某一阶段的状态: pending -> running -> completed/failed"""
    run = _pipeline_runs.get(run_id)
    if not run:
        return {"error": f"Run not found: {run_id}"}

    stage = None
    for s in run["stages"]:
        if s["stage_id"] == stage_id:
            stage = s
            break
    if not stage:
        return {"error": f"Stage not found: {stage_id}"}

    now = datetime.now().isoformat()
    stage["status"] = status
    if assignee:
        stage["assignee"] = assignee
    if status == "running" and not stage["started_at"]:
        stage["started_at"] = now
    if status in ("completed", "failed"):
        stage["completed_at"] = now

    # 更新current_stage
    completed = sum(1 for s in run["stages"] if s["status"] == "completed")
    run["progress"] = round(completed / len(run["stages"]) * 100, 1)
    # 找下一个pending的stage作为current
    next_pending = None
    for s in run["stages"]:
        if s["status"] == "pending":
            next_pending = s["stage_id"]
            break
    run["current_stage"] = next_pending or stage_id

    # 如果所有完成或失败，整体状态调整
    all_done = all(s["status"] in ("completed", "failed") for s in run["stages"])
    if all_done:
        any_failed = any(s["status"] == "failed" for s in run["stages"])
        run["status"] = "failed" if any_failed else "completed"

    return {"success": True, "run": run}


@registry.action("pipeline_histories")
@with_analytics("pipeline_histories")
def get_pipeline_histories():
    """返回最近10次run的历史"""
    sorted_runs = sorted(
        _pipeline_runs.values(),
        key=lambda r: r["created_at"],
        reverse=True,
    )[:10]
    return {"runs": sorted_runs, "total": len(sorted_runs)}


# ============================================================
# 4. API 路由
# ============================================================

@app.route("/api/stats")
@with_analytics("api_stats")
def api_stats():
    return jsonify(registry.execute("stats"))


@app.route("/api/employees")
@with_analytics("api_employees")
def api_employees():
    return jsonify(registry.execute("employees"))


@app.route("/api/v2/employees/souls")
@with_analytics("api_employees_souls")
def api_employees_souls_v2():
    """返回所有员工的灵魂信息"""
    try:
        result = registry.execute("employee_souls")
        souls = result.get("souls", result) if isinstance(result, dict) else result
        return jsonify({"souls": souls})
    except Exception as e:
        logger.error(f"获取灵魂数据失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/activities")
@with_analytics("api_activities")
def api_activities():
    return jsonify(registry.execute("recent_activities"))


@app.route("/api/activities/timeline")
@with_analytics("api_activities_timeline")
def api_activities_timeline():
    return jsonify(registry.execute("activity_timeline"))


@app.route("/api/system")
@with_analytics("api_system")
def api_system():
    return jsonify(registry.execute("system_overview"))


@app.route("/api/search_employee")
@with_analytics("api_search")
def api_search():
    q = request.args.get("q", "").strip()
    return jsonify(registry.execute("search_employee", query=q))


@app.route("/api/decision_board")
@with_analytics("api_decision")
def api_decision():
    """返回当日决策板的文件内容"""
    system = registry.execute("system_overview")
    path = system.get("latest_decision_path", "")
    if not path or not os.path.exists(path):
        return jsonify({"exists": False, "content": "", "filename": ""})

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({
            "exists": True,
            "content": content,
            "filename": system.get("latest_decision", ""),
            "path": path,
        })
    except Exception as e:
        return jsonify({"exists": False, "error": str(e)}), 500


@app.route("/api/token_costs")
@with_analytics("api_token_costs")
def api_token_costs():
    """返回Token消耗统计和成本看板数据"""
    return jsonify(registry.execute("token_costs"))


@app.route("/api/employees/heartbeat")
@with_analytics("api_employees_heartbeat")
def api_employees_heartbeat():
    return jsonify(registry.execute("employee_heartbeat"))


@app.route("/api/employees/<emp_id>/memories")
@with_analytics("api_employee_memories")
def api_employee_memories(emp_id):
    limit = request.args.get("limit", 30, type=int)
    limit = min(limit, 100)
    return jsonify(registry.execute("employee_memories", emp_id=emp_id, limit=limit))


@app.route("/api/capabilities")
@with_analytics("api_capabilities")
def api_capabilities():
    return jsonify(registry.execute("capability_analysis"))


@app.route("/api/organization")
@with_analytics("api_organization")
def api_organization():
    return jsonify(registry.execute("organization_tree"))


# ----- 审批API (BUG-3 FIXED: 后端持久化审批) -----


@app.route("/api/activities/approve/<activity_id>", methods=["POST"])
@with_analytics("api_approve")
def api_approve_activity(activity_id):
    """审批通过一条活动记录"""
    try:
        data = request.get_json(silent=True) or {}
        reason = data.get("reason", "")
        operator = data.get("operator", "system")

        log = record_approval(activity_id, "approve", reason, operator)
        logger.info(f"[Audit] Approved activity {activity_id} by {operator}: {reason}")

        return jsonify({"success": True, "activity_id": activity_id, "action": "approve", "log": log})
    except Exception as e:
        logger.error(f"审批操作失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/activities/reject/<activity_id>", methods=["POST"])
@with_analytics("api_reject")
def api_reject_activity(activity_id):
    """驳回一条活动记录"""
    try:
        data = request.get_json(silent=True) or {}
        reason = data.get("reason", "")
        operator = data.get("operator", "system")

        log = record_approval(activity_id, "reject", reason, operator)
        logger.info(f"[Audit] Rejected activity {activity_id} by {operator}: {reason}")

        return jsonify({"success": True, "activity_id": activity_id, "action": "reject", "log": log})
    except Exception as e:
        logger.error(f"驳回操作失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ----- 烛龙Pipeline路由 -----


@app.route("/api/pipeline/stages")
@with_analytics("api_pipeline_stages")
def api_pipeline_stages():
    return jsonify(registry.execute("pipeline_stages"))


@app.route("/api/pipeline/start", methods=["POST"])
@with_analytics("api_pipeline_start")
def api_pipeline_start():
    return jsonify(registry.execute("pipeline_start"))


@app.route("/api/pipeline/status", methods=["POST"])
@with_analytics("api_pipeline_status")
def api_pipeline_status():
    data = request.get_json(silent=True) or {}
    run_id = data.get("run_id", "")
    return jsonify(registry.execute("pipeline_status", run_id=run_id))


@app.route("/api/pipeline/update_stage", methods=["POST"])
@with_analytics("api_pipeline_update_stage")
def api_pipeline_update_stage():
    data = request.get_json(silent=True) or {}
    run_id = data.get("run_id", "")
    stage_id = data.get("stage_id", "")
    status = data.get("status", "")
    assignee = data.get("assignee", None)
    return jsonify(registry.execute("pipeline_update_stage", run_id=run_id, stage_id=stage_id, status=status, assignee=assignee))


@app.route("/api/pipeline/histories")
@with_analytics("api_pipeline_histories")
def api_pipeline_histories():
    return jsonify(registry.execute("pipeline_histories"))


@app.route("/pipeline")
@with_analytics("api_pipeline_page")
def pipeline_page():
    return render_template("pipeline.html")


# ============================================================
# 5. 主页面
# ============================================================

@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/atoms")
@with_analytics("api_atoms")
def api_atoms():
    _atoms_path = resolve_path("atoms")
    if _atoms_path:
        atoms_dir = Path(_atoms_path)
    else:
        atoms_dir = BASE_DIR / "L5孵化室" / "产品开发" / "白泽控制台" / "atoms"
    if not atoms_dir.exists():
        return jsonify({"atoms": [], "total": 0})
    atoms = []
    for f in sorted(atoms_dir.iterdir()):
        if f.is_file():
            stat = f.stat()
            ext = f.suffix.lstrip(".").upper() or "未知"
            atoms.append({
                "name": f.name,
                "type": ext,
                "size": stat.st_size,
                "size_display": _fmt_size(stat.st_size),
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%m-%d %H:%M"),
            })
    return jsonify({"atoms": atoms, "total": len(atoms)})


@app.route("/api/atoms/<path:name>")
@with_analytics("api_atom_content")
def api_atom_content(name):
    safe = os.path.basename(name)
    _atoms_path = resolve_path("atoms")
    if _atoms_path:
        fpath = Path(_atoms_path) / safe
    else:
        fpath = BASE_DIR / "L5孵化室" / "产品开发" / "白泽控制台" / "atoms" / safe
    if not fpath.exists() or not fpath.is_file():
        return jsonify({"error": "文件不存在"}), 404
    try:
        return jsonify({"name": safe, "content": fpath.read_text("utf-8")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _fmt_size(b):
    for u in ["B", "KB", "MB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} GB"

# ============================================================
# 6. 入口
# ============================================================

# ===== 产品唤醒看板数据（2026-05-08 追加）=====
PRODUCT_LAUNCHPAD = [
    {"id": 1, "keyword": "计然", "name": "赛博参谋", "tagline": "创业决策沙盘", "status": "ready", "service": "CLI", "command": "python3 cybernetic_advisor.py", "staff": "计然P8", "desc": "创业者输入一个模糊想法，AI自动输出6步沙盘推演报告"},
    {"id": 2, "keyword": "云师", "name": "AI灵魂觉醒引擎", "tagline": "知识→AI员工的Web蒸馏流水线", "status": "ready", "service": "localhost:5015", "command": "python3 app.py", "staff": "云师P8", "desc": "粘贴URL/知识库文本，一键蒸馏为独立AI员工"},
    {"id": 3, "keyword": "白泽", "name": "白泽控制台", "tagline": "数字员工CEO驾驶舱", "status": "ready", "service": "localhost:5010", "command": "python3 app.py", "staff": "白泽P9", "desc": "AI数字员工运营管理面板，所有数字员工的中控台"},
    {"id": 4, "keyword": "招贤", "name": "数字员工SaaS", "tagline": "AI员工招聘市场", "status": "ready", "service": "localhost:5020", "command": "python3 app.py", "staff": "英招P9", "desc": "浏览/招聘/管理AI数字员工的招聘市场风格平台"},
    {"id": 5, "keyword": "文鳐", "name": "文鳐技能集市", "tagline": "技能包市场", "status": "ready", "service": "localhost:5012", "command": "python3 app.py", "staff": "文鳐P9", "desc": "技能包产品化市场：PDF工具/截图工具/Markdown转换"},
    {"id": 6, "keyword": "司南", "name": "3+X窗口管理面板", "tagline": "多窗口状态管理", "status": "ready", "service": "localhost:5008", "command": "python3 app.py", "staff": None, "desc": "管理白泽的3+X窗口体系，实时查看窗口context"},
    {"id": 7, "keyword": "藏经", "name": "大航海知识库", "tagline": "出海RAG问答系统", "status": "ready", "service": "localhost:5005", "command": "python3 run_knowledge_base.py", "staff": None, "desc": "中韩出海数智港专属知识库，文档上传→RAG问答"},
    {"id": 8, "keyword": "远航", "name": "大航海北极星看板", "tagline": "出海数智港北极星", "status": "ready", "service": "localhost:5004", "command": "python3 app.py", "staff": None, "desc": "6维度/16行动原子/健康度25.75%的北极星指标看板"},
    {"id": 9, "keyword": "奎", "name": "企业知识库RAG", "tagline": "企业文档AI问答", "status": "ready", "service": "MCP8000", "command": "src/bootstrap.sh", "staff": None, "desc": "企业级RAG引擎，14种格式解析+语义分块+混合检索"},
    {"id": 10, "keyword": "阿久", "name": "内容自动化工厂", "tagline": "AI内容生产流水线", "status": "ready", "service": "localhost:5000", "command": "python3 app.py", "staff": "乘黄P8", "desc": "RSS采集→LLM生成→小红书发布→Token监控全链路"},
    {"id": 11, "keyword": "䑏疏", "name": "䑏疏跨境助手", "tagline": "跨境商业智能", "status": "ready", "service": "CLI", "command": "python3 kuanshu_cli.py", "staff": "䑏疏P8", "desc": "MECE四象限情报框架，每条情报可追溯source_url"},
    {"id": 12, "keyword": "鸣蜩", "name": "会议智能小助手", "tagline": "飞阅会AI助理", "status": "ready", "service": "localhost:5014", "command": "python3 app.py", "staff": None, "desc": "飞阅会全流程AI辅助：议程/纪要/行动跟踪"},
    {"id": 13, "keyword": "翟如", "name": "飞阅会AI主持助理", "tagline": "飞阅会全流程AI主持", "status": "ready", "service": "localhost:5014", "command": "python3 app.py", "staff": None, "desc": "飞阅会AI主持——自动生成议程、主持讨论、生成纪要"},
]

@app.route("/api/products")
def api_products():
    return jsonify(PRODUCT_LAUNCHPAD)

@app.route("/api/products/<keyword>")
def api_product(keyword):
    for p in PRODUCT_LAUNCHPAD:
        if p["keyword"] == keyword:
            return jsonify(p)
    return jsonify({"error": "not found"}), 404

def resolve_product(keyword):
    for p in PRODUCT_LAUNCHPAD:
        if p["keyword"] == keyword:
            return p
    return None

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("  白泽控制台 v0.1 — CEO仪表盘")
    logger.info("  Port: 5010")
    logger.info("  Mode: Flask + Alpine.js + Tailwind CDN")
    logger.info("=" * 50)

    # 预热: 验证数据源
    stats = registry.execute("stats")
    logger.info(f"  员工: {stats['total_employees']} | "
                f"在线: {stats['online_employees']} | "
                f"今日记忆: {stats['today_memories']} | "
                f"技能: {stats['total_skills']}")

    app.run(host="0.0.0.0", port=5010, debug=False)
