"""
导入API路由：预览 / 确认导入 / 导入历史
全部端点需 JWT 认证
"""
import json
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Contact, ImportHistory
from app.schemas import (
    ApiResponse,
    ImportPreviewResponse,
    ImportConfirmRequest,
    ImportConfirmResponse,
    ImportHistoryItem,
    ImportHistoryResponse,
)
from app.auth import get_current_user
from app.services.importer import ImportEngine, detect_format, parse_csv, parse_vcf
from app.services.dedup import detect_duplicates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/imports", tags=["导入引擎"])

# 临时存储批次数据（内存中，生产环境建议 Redis）
# key: batch_id, value: {"engine": ImportEngine, "raw_content": bytes, "filename": str}
_batch_store: dict = {}

# 最大上传文件大小：10MB
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


@router.post("/preview", response_model=ApiResponse)
async def import_preview(
    file: UploadFile = File(..., description="CSV或VCF文件"),
    current_user: User = Depends(get_current_user),
):
    """
    上传文件 → 解析 → AI识别列名 → 返回预览（前20行）

    Args:
        file: 上传的 CSV 或 VCF 文件

    Returns:
        {batch_id, total_rows, preview_rows, headers, field_mapping, mapped_preview}
    """
    # 检查文件大小
    raw_content = await file.read()
    if len(raw_content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail="文件过大，最大允许 10MB",
        )

    filename = file.filename or "unknown"

    # 检测格式
    fmt = detect_format(filename, raw_content)
    if fmt not in ("csv", "vcf"):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {fmt}，仅支持 CSV 和 VCF（vCard）",
        )

    # 创建导入引擎
    engine = ImportEngine()

    # 解析
    try:
        parsed = engine.parse_file(filename, raw_content)
    except Exception as e:
        logger.error(f"文件解析失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"文件解析失败: {str(e)}",
        )

    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="文件中未找到有效数据",
        )

    # AI 列名识别
    engine.recognize_columns()

    # 应用映射
    engine.apply_mapping()

    # 存储批次数据
    _batch_store[engine.batch_id] = {
        "engine": engine,
        "raw_content": raw_content,
        "filename": filename,
        "file_type": fmt,
        "user_id": current_user.id,
    }

    # 构建预览响应
    headers = list(parsed[0].keys()) if parsed else []
    preview_rows = parsed[:20]
    mapped_preview = engine.mapped_data[:20]

    return ApiResponse(
        code=200,
        message="预览生成成功",
        data=ImportPreviewResponse(
            batch_id=engine.batch_id,
            total_rows=len(parsed),
            preview_rows=preview_rows,
            headers=headers,
            field_mapping=engine.field_mapping,
            mapped_preview=mapped_preview,
        ).model_dump(),
    )


@router.post("/confirm", response_model=ApiResponse)
def import_confirm(
    req: ImportConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    确认导入（含去重策略）

    Args:
        req: 确认导入请求体
            - batch_id: 预览返回的批次ID
            - field_mapping: 最终确认的列名映射
            - strategy: 去重策略 skip / merge / update
            - duplicates: 逐行去重处理（可选，为空则统一应用strategy）

    Returns:
        {batch_id, import_id, total_rows, imported_rows, skipped_rows, merged_rows, duplicate_count}
    """
    # 获取批次数据
    batch = _batch_store.get(req.batch_id)
    if not batch:
        raise HTTPException(
            status_code=404,
            detail="批次不存在或已过期，请重新上传文件",
        )

    # 验证用户
    if batch["user_id"] != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="无权操作此批次",
        )

    engine: ImportEngine = batch["engine"]

    # 应用用户确认的列名映射
    engine.field_mapping = req.field_mapping
    engine.apply_mapping()

    # 查询数据库中该用户的已有联系人（排除已删除的）
    existing_contacts_q = db.query(Contact).filter(
        Contact.owner_id == current_user.id,
        Contact.is_deleted == False,
    ).all()
    existing_contacts = [
        {
            "name": c.name or "",
            "phone": c.phone or "",
            "wechat_id": c.wechat_id or "",
            "company": c.company or "",
            "email": c.email or "",
            "id": c.id,
        }
        for c in existing_contacts_q
    ]

    # 检测重复
    dup_groups = detect_duplicates(engine.mapped_data, existing_contacts)

    # 按导入数据索引分组（去重），记录哪些行需要跳过/合并
    skip_indices: set = set()
    merge_pairs: dict = {}  # source_idx -> existing_id
    update_pairs: dict = {}  # source_idx -> existing_id

    if req.duplicates:
        # 逐行指定
        for dup in req.duplicates:
            if dup.match_type == "skip":
                skip_indices.add(dup.row_index)
            elif dup.match_type == "merge" and dup.matched_contact_id:
                merge_pairs[dup.row_index] = dup.matched_contact_id
            elif dup.match_type == "update" and dup.matched_contact_id:
                update_pairs[dup.row_index] = dup.matched_contact_id
    else:
        # 统一策略
        for group in dup_groups:
            for dup in group:
                source_idx = dup.source_idx
                if source_idx < len(engine.mapped_data):
                    if req.strategy == "skip":
                        skip_indices.add(source_idx)
                    elif req.strategy == "merge":
                        # 找到匹配的 existing id
                        dup_idx = dup.duplicate_idx
                        if dup_idx >= len(engine.mapped_data):
                            rel_idx = dup_idx - len(engine.mapped_data)
                            if rel_idx < len(existing_contacts):
                                merge_pairs[source_idx] = existing_contacts[rel_idx]["id"]
                    elif req.strategy == "update":
                        dup_idx = dup.duplicate_idx
                        if dup_idx >= len(engine.mapped_data):
                            rel_idx = dup_idx - len(engine.mapped_data)
                            if rel_idx < len(existing_contacts):
                                update_pairs[source_idx] = existing_contacts[rel_idx]["id"]

    # 开始导入
    imported_count = 0
    skipped_count = 0
    merged_count = 0

    for idx, row in enumerate(engine.mapped_data):
        try:
            if idx in skip_indices:
                skipped_count += 1
                continue

            if idx in merge_pairs:
                # 合并：更新已有联系人（非空字段覆盖）
                existing_id = merge_pairs[idx]
                existing_contact = db.query(Contact).filter(
                    Contact.id == existing_id,
                    Contact.is_deleted == False,
                ).first()
                if existing_contact:
                    _merge_contact(existing_contact, row)
                    merged_count += 1
                else:
                    # 找不到已有联系人，重新创建
                    _create_contact(db, row, current_user.id, engine.batch_id)
                    imported_count += 1
                continue

            if idx in update_pairs:
                # 更新：新数据完全覆盖
                existing_id = update_pairs[idx]
                existing_contact = db.query(Contact).filter(
                    Contact.id == existing_id,
                    Contact.is_deleted == False,
                ).first()
                if existing_contact:
                    _update_contact(existing_contact, row)
                    merged_count += 1
                else:
                    _create_contact(db, row, current_user.id, engine.batch_id)
                    imported_count += 1
                continue

            # 正常导入
            _create_contact(db, row, current_user.id, engine.batch_id)
            imported_count += 1

        except Exception as e:
            logger.warning(f"导入第 {idx} 行失败: {e}")
            skipped_count += 1

    db.commit()

    # 记录导入历史
    import_history = ImportHistory(
        user_id=current_user.id,
        filename=batch["filename"],
        file_type=batch["file_type"],
        total_rows=len(engine.mapped_data),
        imported_rows=imported_count,
        skipped_rows=skipped_count,
        merged_rows=merged_count,
        duplicate_count=len(dup_groups),
        field_mapping=json.dumps(req.field_mapping, ensure_ascii=False),
        strategy=req.strategy,
        status="completed",
        batch_id=engine.batch_id,
    )
    db.add(import_history)
    db.commit()
    db.refresh(import_history)

    # 清理批次缓存
    _batch_store.pop(req.batch_id, None)

    return ApiResponse(
        code=200,
        message="导入完成",
        data=ImportConfirmResponse(
            batch_id=engine.batch_id,
            import_id=import_history.id,
            total_rows=len(engine.mapped_data),
            imported_rows=imported_count,
            skipped_rows=skipped_count,
            merged_rows=merged_count,
            duplicate_count=len(dup_groups),
            strategy=req.strategy,
        ).model_dump(),
    )


@router.get("/history", response_model=ApiResponse)
def import_history(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取当前用户的导入历史

    Args:
        page: 页码（从1开始）
        page_size: 每页条数（最大100）

    Returns:
        {total, page, page_size, items: [...]}
    """
    query = db.query(ImportHistory).filter(
        ImportHistory.user_id == current_user.id,
        ImportHistory.is_deleted == False,
    ).order_by(ImportHistory.created_at.desc())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return ApiResponse(
        code=200,
        message="success",
        data=ImportHistoryResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=[ImportHistoryItem.model_validate(item).model_dump() for item in items],
        ).model_dump(),
    )


# ============================================================
# 辅助函数
# ============================================================

def _create_contact(db: Session, row: dict, owner_id: int, batch_id: str) -> Contact:
    """创建联系人记录"""
    contact = Contact(
        owner_id=owner_id,
        name=row.get("name", "") or "未知联系人",
        phone=row.get("phone", ""),
        wechat_id=row.get("wechat_id", ""),
        company=row.get("company", ""),
        position=row.get("position", ""),
        email=row.get("email", ""),
        notes=row.get("notes", ""),
        tags=row.get("tags", ""),
        source="import",
        import_batch_id=batch_id,
    )
    db.add(contact)
    db.flush()
    return contact


def _merge_contact(existing: Contact, row: dict) -> None:
    """合并：非空字段覆盖"""
    if row.get("name") and row["name"].strip():
        existing.name = row["name"].strip()
    if row.get("phone") and row["phone"].strip():
        existing.phone = row["phone"].strip()
    if row.get("wechat_id") and row["wechat_id"].strip():
        existing.wechat_id = row["wechat_id"].strip()
    if row.get("company") and row["company"].strip():
        existing.company = row["company"].strip()
    if row.get("position") and row["position"].strip():
        existing.position = row["position"].strip()
    if row.get("email") and row["email"].strip():
        existing.email = row["email"].strip()
    if row.get("notes") and row["notes"].strip():
        existing_notes = existing.notes or ""
        new_notes = row["notes"].strip()
        if new_notes not in existing_notes:
            existing.notes = f"{existing_notes}\n{new_notes}".strip()
    if row.get("tags") and row["tags"].strip():
        existing_tags = set(t.strip() for t in (existing.tags or "").split(",") if t.strip())
        new_tags = set(t.strip() for t in row["tags"].split(",") if t.strip())
        existing.tags = ",".join(existing_tags | new_tags)


def _update_contact(existing: Contact, row: dict) -> None:
    """更新：完全用新数据覆盖"""
    if "name" in row:
        existing.name = row["name"].strip() or existing.name
    if "phone" in row:
        existing.phone = row["phone"].strip() or ""
    if "wechat_id" in row:
        existing.wechat_id = row["wechat_id"].strip() or ""
    if "company" in row:
        existing.company = row["company"].strip() or ""
    if "position" in row:
        existing.position = row["position"].strip() or ""
    if "email" in row:
        existing.email = row["email"].strip() or ""
    if "notes" in row:
        existing.notes = row["notes"].strip() or ""
    if "tags" in row:
        existing.tags = row["tags"].strip() or ""
