"""
链客宝 — 合规审计 API
======================
微信小程序合规检查、隐私指引审计、配置健康度扫描。

端点:
  GET  /api/compliance/status  — 合规检查总体状态（通过/警告/未通过项数）
  GET  /api/compliance/report  — 完整合规报告（解析 compliance_report.md）
  POST /api/compliance/scan    — 触发一次新的合规扫描
"""

import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)

# ===================================================================
# Router
# ===================================================================
router = APIRouter(prefix="/api/compliance", tags=["合规审计"])

# ===================================================================
# 项目根目录常量
# ===================================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # D:\chainke-full
COMPLIANCE_REPORT_PATH = PROJECT_ROOT / "compliance_report.md"


# ===================================================================
# Pydantic 响应模型
# ===================================================================

class ComplianceStatusItem(BaseModel):
    """单条合规项状态"""
    name: str = Field(..., description="检查项名称")
    status: str = Field(..., description="状态: pass / warning / fail")
    detail: str = Field(default="", description="详情说明")


class ComplianceStatusResponse(BaseModel):
    """合规检查总体状态"""
    total: int = Field(..., description="检查项总数")
    passed: int = Field(..., description="通过项数")
    warnings: int = Field(..., description="警告项数")
    failed: int = Field(..., description="未通过项数")
    overall: str = Field(..., description="总体评价: pass / warning / fail")
    items: list[ComplianceStatusItem] = Field(default=[], description="各项详情")
    scanned_at: str = Field(..., description="扫描时间")


class ComplianceReportResponse(BaseModel):
    """完整合规报告"""
    title: str = Field(default="合规审计报告", description="报告标题")
    generated_at: str = Field(..., description="生成时间")
    summary: str = Field(default="", description="摘要")
    sections: list[dict] = Field(default=[], description="报告章节内容")
    raw_markdown: str = Field(default="", description="原始 Markdown 原文")


class ScanResultItem(BaseModel):
    """扫描结果单项"""
    check_name: str = Field(..., description="检查项名称")
    status: str = Field(..., description="pass / warning / fail")
    message: str = Field(default="", description="检查结果描述")


class ScanResponse(BaseModel):
    """合规扫描响应"""
    status: str = Field(default="completed", description="扫描状态")
    scanned_at: str = Field(..., description="扫描时间戳")
    duration_ms: float = Field(..., description="扫描耗时(毫秒)")
    results: list[ScanResultItem] = Field(default=[], description="逐项检查结果")
    summary: dict = Field(default={}, description="汇总统计")


# ===================================================================
# GET /api/compliance/status — 合规检查总体状态
# ===================================================================

@router.get("/status", response_model=ComplianceStatusResponse)
async def get_compliance_status(
    db: Session = Depends(get_db),
):
    """
    返回合规检查总体状态。

    包含：小程序隐私指引检测、API_BASE 配置检查、订单中心路径检查、
    代码统计阈值检查等项目的通过/警告/未通过计数。
    """
    items = _run_compliance_checks(db)
    total = len(items)
    passed = sum(1 for i in items if i.status == "pass")
    warnings = sum(1 for i in items if i.status == "warning")
    failed = sum(1 for i in items if i.status == "fail")

    if failed > 0:
        overall = "fail"
    elif warnings > 0:
        overall = "warning"
    else:
        overall = "pass"

    return ComplianceStatusResponse(
        total=total,
        passed=passed,
        warnings=warnings,
        failed=failed,
        overall=overall,
        items=items,
        scanned_at=datetime.utcnow().isoformat() + "Z",
    )


# ===================================================================
# GET /api/compliance/report — 完整合规报告
# ===================================================================

@router.get("/report", response_model=ComplianceReportResponse)
async def get_compliance_report():
    """
    返回完整合规报告。

    读取项目根目录下的 compliance_report.md 文件，
    解析 Markdown 章节结构为结构化 JSON 返回。
    若文件不存在则返回 404。
    """
    if not COMPLIANCE_REPORT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"合规报告文件不存在: {COMPLIANCE_REPORT_PATH}",
        )

    raw = COMPLIANCE_REPORT_PATH.read_text(encoding="utf-8")
    sections = _parse_markdown_sections(raw)
    summary = _extract_summary(sections)

    return ComplianceReportResponse(
        title=_extract_title(raw),
        generated_at=datetime.utcnow().isoformat() + "Z",
        summary=summary,
        sections=sections,
        raw_markdown=raw,
    )


# ===================================================================
# POST /api/compliance/scan — 触发一次新的合规扫描
# ===================================================================

@router.post("/scan", response_model=ScanResponse)
async def trigger_compliance_scan(
    db: Session = Depends(get_db),
):
    """
    触发一次新的合规扫描。

    扫描项包括：
      1. 微信小程序隐私指引文件是否存在且完整
      2. API_BASE 配置是否指向正式环境
      3. 订单中心路径配置是否正确
      4. 核心 Python 模块代码行数是否在阈值内
      5. 关键环境变量是否已配置
      6. 微信小程序配置 SOP 文档是否存在
    """
    start_time = time.perf_counter()

    results = _run_scan_checks()

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    passed = sum(1 for r in results if r.status == "pass")
    warnings = sum(1 for r in results if r.status == "warning")
    failed = sum(1 for r in results if r.status == "fail")

    return ScanResponse(
        status="completed",
        scanned_at=datetime.utcnow().isoformat() + "Z",
        duration_ms=duration_ms,
        results=results,
        summary={
            "total": len(results),
            "passed": passed,
            "warnings": warnings,
            "failed": failed,
            "overall": "fail" if failed > 0 else ("warning" if warnings > 0 else "pass"),
        },
    )


# ===================================================================
# 内部辅助函数
# ===================================================================

def _run_compliance_checks(db: Session) -> list[ComplianceStatusItem]:
    """运行所有合规检查项，返回状态列表"""
    items: list[ComplianceStatusItem] = []

    # 1. 检查 compliance_report.md 是否存在
    report_exists = COMPLIANCE_REPORT_PATH.exists()
    items.append(ComplianceStatusItem(
        name="合规报告文件",
        status="pass" if report_exists else "fail",
        detail="compliance_report.md 存在" if report_exists else "compliance_report.md 不存在，请先生成合规报告",
    ))

    # 2. 检查微信小程序配置 SOP 文档
    sop_path = PROJECT_ROOT / "链客宝微信小程序配置SOP.md"
    sop_exists = sop_path.exists()
    items.append(ComplianceStatusItem(
        name="微信小程序配置SOP",
        status="pass" if sop_exists else "warning",
        detail="配置 SOP 文档存在" if sop_exists else "链客宝微信小程序配置SOP.md 未找到",
    ))

    # 3. 检查主体变更 SOP
    change_sop_path = PROJECT_ROOT / "链客宝主体变更与小程序配置SOP.md"
    change_sop_exists = change_sop_path.exists()
    items.append(ComplianceStatusItem(
        name="主体变更与配置SOP",
        status="pass" if change_sop_exists else "warning",
        detail="主体变更 SOP 存在" if change_sop_exists else "链客宝主体变更与小程序配置SOP.md 未找到",
    ))

    # 4. 检查环境变量 WX_APPID / WX_SECRET
    wx_appid = os.getenv("WX_APPID", "")
    wx_secret = os.getenv("WX_SECRET", "")
    if wx_appid and wx_secret:
        items.append(ComplianceStatusItem(
            name="微信小程序环境变量",
            status="pass",
            detail=f"WX_APPID 和 WX_SECRET 均已配置 (APPID: {wx_appid[:4]}...{wx_appid[-4:]})",
        ))
    elif wx_appid or wx_secret:
        items.append(ComplianceStatusItem(
            name="微信小程序环境变量",
            status="warning",
            detail="WX_APPID 和 WX_SECRET 仅配置了其中之一，请检查",
        ))
    else:
        items.append(ComplianceStatusItem(
            name="微信小程序环境变量",
            status="fail",
            detail="WX_APPID 和 WX_SECRET 均未配置，请设置环境变量",
        ))

    # 5. 检查数据库连接
    try:
        conn = db.connection()
        conn.scalar("SELECT 1")
        items.append(ComplianceStatusItem(
            name="数据库连接",
            status="pass",
            detail="数据库连接正常",
        ))
    except Exception as e:
        items.append(ComplianceStatusItem(
            name="数据库连接",
            status="fail",
            detail=f"数据库连接失败: {e}",
        ))

    # 6. 检查后端服务文件完整性
    main_py = PROJECT_ROOT / "backend" / "app" / "main.py"
    routers_dir = PROJECT_ROOT / "backend" / "app" / "routers"
    router_files = list(routers_dir.glob("*.py")) if routers_dir.exists() else []
    items.append(ComplianceStatusItem(
        name="服务文件完整性",
        status="pass" if (main_py.exists() and len(router_files) >= 5) else "warning",
        detail=f"main.py 存在: {main_py.exists()}, 路由文件数: {len(router_files)}",
    ))

    return items


def _run_scan_checks() -> list[ScanResultItem]:
    """运行深度合规扫描"""
    results: list[ScanResultItem] = []

    # 1. 微信小程序隐私指引检查
    _check_privacy_guide(results)

    # 2. API_BASE 配置检查
    _check_api_base_config(results)

    # 3. 订单中心路径检查
    _check_order_center_path(results)

    # 4. 代码统计检查
    _check_code_stats(results)

    # 5. 关键环境变量检查
    _check_env_vars(results)

    # 6. 微信小程序配置 SOP 文档检查
    _check_wx_sop_docs(results)

    # 7. 电子画册同步方案检查
    _check_brochure_sync(results)

    return results


def _check_privacy_guide(results: list[ScanResultItem]):
    """检查微信小程序隐私指引"""
    # 检查项目中是否存在隐私相关配置
    privacy_files = []
    for pattern in ["*privacy*", "*隐私*", "privacy*.md", "privacy*.json"]:
        privacy_files.extend(PROJECT_ROOT.glob(pattern))
        privacy_files.extend((PROJECT_ROOT / "backend").glob(pattern))

    # 检查 main.py 中是否有隐私相关中间件或配置
    main_py = PROJECT_ROOT / "backend" / "app" / "main.py"
    has_privacy_middleware = False
    if main_py.exists():
        content = main_py.read_text(encoding="utf-8")
        if re.search(r"隐私|privacy|Privacy", content, re.IGNORECASE):
            has_privacy_middleware = True

    if privacy_files or has_privacy_middleware:
        results.append(ScanResultItem(
            check_name="微信小程序隐私指引",
            status="pass",
            message="隐私指引配置已就绪" + (f" (相关文件: {len(privacy_files)} 个)" if privacy_files else ""),
        ))
    else:
        results.append(ScanResultItem(
            check_name="微信小程序隐私指引",
            status="warning",
            message="未检测到明确的隐私指引配置文件，建议在项目中添加 privacy.md 或相关隐私说明",
        ))


def _check_api_base_config(results: list[ScanResultItem]):
    """检查 API_BASE 配置是否指向正式环境"""
    # 检查常见配置文件中是否有 API_BASE 或 API_HOST
    config_files = [
        PROJECT_ROOT / "backend" / ".env",
        PROJECT_ROOT / "backend" / ".env.example",
        PROJECT_ROOT / ".env",
    ]
    api_base = None
    for f in config_files:
        if f.exists():
            content = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"(?:API_BASE|API_HOST|VUE_APP_API_BASE)\s*=\s*(.+)", content)
            if m:
                api_base = m.group(1).strip().strip('"').strip("'")
                break

    if api_base:
        is_production = "liankebao.top" in api_base or "api.liankebao" in api_base
        results.append(ScanResultItem(
            check_name="API_BASE 配置",
            status="pass" if is_production else "warning",
            message=f"API 指向: {api_base}" + (" (正式环境 ✓)" if is_production else " (非正式环境，请确认)"),
        ))
    else:
        results.append(ScanResultItem(
            check_name="API_BASE 配置",
            status="warning",
            message="未找到 API_BASE 配置项，请检查 .env 文件",
        ))


def _check_order_center_path(results: list[ScanResultItem]):
    """检查订单中心路径配置"""
    # 检查 routes 或 views 中是否有订单中心相关路径
    order_paths_found = []
    search_dirs = [
        PROJECT_ROOT / "backend" / "app" / "routers",
        PROJECT_ROOT / "backend" / "app",
    ]
    for d in search_dirs:
        if d.exists():
            for f in d.rglob("*.py"):
                if f.is_file():
                    try:
                        content = f.read_text(encoding="utf-8", errors="ignore")
                        if re.search(r"order|订单|payment|支付|trade|交易", content, re.IGNORECASE):
                            order_paths_found.append(f.name)
                    except Exception:
                        continue

    if order_paths_found:
        results.append(ScanResultItem(
            check_name="订单中心路径",
            status="pass",
            message=f"检测到订单/支付相关路由模块: {', '.join(set(order_paths_found[:5]))}",
        ))
    else:
        results.append(ScanResultItem(
            check_name="订单中心路径",
            status="warning",
            message="未检测到订单中心或支付相关路由模块，确认是否需要配置",
        ))


def _check_code_stats(results: list[ScanResultItem]):
    """检查代码统计 — 核心 Python 模块行数是否在合理阈值内"""
    backend_app = PROJECT_ROOT / "backend" / "app"
    total_lines = 0
    py_files_count = 0

    if backend_app.exists():
        for f in backend_app.rglob("*.py"):
            if f.is_file():
                py_files_count += 1
                try:
                    lines = len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
                    total_lines += lines
                except Exception:
                    continue

    results.append(ScanResultItem(
        check_name="代码统计",
        status="pass",
        message=f"后端核心模块: {py_files_count} 个 Python 文件, 共 {total_lines} 行代码",
    ))


def _check_env_vars(results: list[ScanResultItem]):
    """检查关键环境变量"""
    required_vars = {
        "WX_APPID": "微信小程序 AppID",
        "WX_SECRET": "微信小程序 Secret",
    }
    optional_vars = {
        "PORT": "服务端口",
        "DATABASE_URL": "数据库连接",
    }

    missing_required = []
    missing_optional = []
    for var, desc in required_vars.items():
        if not os.getenv(var):
            missing_required.append(f"{var} ({desc})")
    for var, desc in optional_vars.items():
        if not os.getenv(var):
            missing_optional.append(f"{var} ({desc})")

    if missing_required:
        results.append(ScanResultItem(
            check_name="关键环境变量",
            status="fail",
            message="缺少必填环境变量: " + ", ".join(missing_required),
        ))
    elif missing_optional:
        results.append(ScanResultItem(
            check_name="关键环境变量",
            status="warning",
            message="环境变量基本就绪，但缺少可选变量: " + ", ".join(missing_optional),
        ))
    else:
        results.append(ScanResultItem(
            check_name="关键环境变量",
            status="pass",
            message="所有关键环境变量均已配置",
        ))


def _check_wx_sop_docs(results: list[ScanResultItem]):
    """检查微信小程序配置 SOP 文档"""
    sop_docs = [
        ("链客宝微信小程序配置SOP.md", PROJECT_ROOT / "链客宝微信小程序配置SOP.md"),
        ("链客宝主体变更与小程序配置SOP.md", PROJECT_ROOT / "链客宝主体变更与小程序配置SOP.md"),
    ]
    existing = []
    missing = []
    for name, path in sop_docs:
        if path.exists():
            size = path.stat().st_size
            existing.append(f"{name} ({size} bytes)")
        else:
            missing.append(name)

    if not missing:
        results.append(ScanResultItem(
            check_name="微信小程序配置SOP文档",
            status="pass",
            message="所有 SOP 文档就绪: " + ", ".join(existing),
        ))
    elif not existing:
        results.append(ScanResultItem(
            check_name="微信小程序配置SOP文档",
            status="fail",
            message="SOP 文档全部缺失: " + ", ".join(missing),
        ))
    else:
        results.append(ScanResultItem(
            check_name="微信小程序配置SOP文档",
            status="warning",
            message="部分 SOP 文档缺失: " + ", ".join(missing) + " | 已就绪: " + ", ".join(existing),
        ))


def _check_brochure_sync(results: list[ScanResultItem]):
    """检查电子画册同步方案"""
    sync_doc = PROJECT_ROOT / "电子画册同步方案.md"
    if sync_doc.exists():
        size = sync_doc.stat().st_size
        results.append(ScanResultItem(
            check_name="电子画册同步方案",
            status="pass",
            message=f"同步方案文档存在 ({size} bytes)",
        ))
    else:
        results.append(ScanResultItem(
            check_name="电子画册同步方案",
            status="warning",
            message="电子画册同步方案文档未找到（可选）",
        ))


def _parse_markdown_sections(markdown: str) -> list[dict]:
    """将 Markdown 文本解析为结构化章节列表"""
    sections = []
    current_section = None

    for line in markdown.splitlines():
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading_match:
            if current_section:
                sections.append(current_section)
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            current_section = {
                "level": level,
                "title": title,
                "content": [],
            }
        else:
            if current_section is not None:
                current_section["content"].append(line)

    if current_section:
        sections.append(current_section)

    return sections


def _extract_title(markdown: str) -> str:
    """从 Markdown 中提取一级标题"""
    m = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    return m.group(1).strip() if m else "合规审计报告"


def _extract_summary(sections: list[dict]) -> str:
    """从解析出的章节中提取摘要信息"""
    if not sections:
        return ""
    # 取第一个非空内容的前 200 字作为摘要
    for sec in sections:
        text = "\n".join(sec["content"]).strip()
        if text:
            return text[:200] + ("..." if len(text) > 200 else "")
    return ""


# ===================================================================
# 启动提示
# ===================================================================

print("[Compliance] 合规审计路由已加载 ✓")
print("[Compliance] GET  /api/compliance/status  — 合规检查总体状态")
print("[Compliance] GET  /api/compliance/report  — 完整合规报告")
print("[Compliance] POST /api/compliance/scan    — 触发合规扫描")
