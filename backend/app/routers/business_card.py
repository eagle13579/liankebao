"""
链客宝 AI 数字名片路由
========================
- POST /api/card/scan — 上传名片图片/PDF → AI提取字段
- POST /api/card/generate — 接受字段JSON → 生成数字名片
- GET  /api/card/{id} — 获取名片详情（公开分享）
- POST /api/card/{id}/match — 基于名片触发供需匹配
"""

import json
import logging
import os
import tempfile
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.business_card_ai import (
    CARD_FIELDS,
    extract_fields,
    generate_digital_card,
    generate_share_token,
    match_supply_demand,
    scan_card,
    validate_card_fields,
)
from app.database import get_db
from app.models import BusinessCard, User
from app.posthog_middleware import capture_card_generated

logger = logging.getLogger(__name__)

# ===== OpenTelemetry 自定义追踪 =====
from app.telemetry import tracer

router = APIRouter(prefix="/api/card", tags=["AI数字名片"])


# ============================================================
# Pydantic 请求/响应模型
# ============================================================

class CardFields(BaseModel):
    """名片字段"""
    name: Optional[str] = None
    position: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    wechat: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    cover_image: Optional[str] = None


class CardGenerateRequest(BaseModel):
    """生成数字名片请求"""
    fields: CardFields


class CardMatchResult(BaseModel):
    """匹配结果条目"""
    type: str  # "need" or "product"
    id: int
    title: str
    category: Optional[str] = None
    score: float
    reasons: List[str]


class CardResponse(BaseModel):
    """名片响应"""
    id: Optional[int] = None
    share_token: str
    share_url: str
    name: str
    fields: Dict[str, Any]
    cover_image: Optional[str] = None
    album_meta: Optional[Dict[str, Any]] = None
    created_at: str
    view_count: int = 0


class ApiResponse(BaseModel):
    """统一 API 响应"""
    code: int = 200
    message: str = "success"
    data: Any = None


# ============================================================
# POST /api/card/scan — 上传名片扫描
# ============================================================

@router.post("/scan", summary="扫描名片", description="上传名片图片/PDF → AI提取字段并返回可编辑的字段JSON")
async def scan_business_card(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """上传名片文件，AI提取字段

    支持格式: PDF, JPG, PNG, BMP, WebP
    """
    with tracer.start_as_current_span("card.scan") as span:
        span.set_attribute("user_id", current_user.id)
        span.set_attribute("filename", file.filename or "unknown")

        # 验证文件类型
        allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in allowed_extensions:
            span.set_attribute("error", "unsupported_format")
            span.set_attribute("file_ext", ext)
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "code": 400,
                    "message": f"不支持的文件格式: {ext}。支持: {', '.join(allowed_extensions)}",
                },
            )

    # 保存上传文件到临时目录
    try:
        tmp_dir = tempfile.mkdtemp(prefix="card_scan_")
        tmp_path = os.path.join(tmp_dir, f"{uuid.uuid4().hex}{ext}")

        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        logger.info(f"名片文件已保存: {tmp_path} ({len(content)} bytes)")

        # Step 1: 扫描（OCR）
        raw_text = scan_card(tmp_path)

        # Step 2: 提取字段
        fields = extract_fields(raw_text)

        # Step 3: 返回可编辑字段
        return JSONResponse(content={
            "code": 200,
            "message": "名片扫描完成，请确认字段信息",
            "data": {
                "raw_text": raw_text,
                "fields": fields,
                "suggestions": _generate_suggestions(fields),
            },
        })

    except Exception as e:
        logger.error(f"名片扫描失败: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": 500, "message": f"名片扫描失败: {str(e)}"},
        )
    finally:
        # 清理临时文件
        try:
            if "tmp_path" in dir():
                os.remove(tmp_path)
                os.rmdir(tmp_dir)
        except Exception:
            pass


def _generate_suggestions(fields: Dict[str, Any]) -> List[str]:
    """根据字段完整性生成优化建议"""
    suggestions = []
    missing = [f for f in CARD_FIELDS if not fields.get(f)]
    if missing:
        missing_names = {
            "name": "姓名", "position": "职位", "company": "公司",
            "phone": "手机", "email": "邮箱", "wechat": "微信",
            "address": "地址", "website": "官网",
        }
        missing_cn = [missing_names.get(m, m) for m in missing]
        suggestions.append(f"以下字段未识别到，请手动补充: {'、'.join(missing_cn)}")

    if not fields.get("phone") and not fields.get("email") and not fields.get("wechat"):
        suggestions.append("建议至少填写一种联系方式（手机、邮箱或微信）")

    return suggestions


# ============================================================
# POST /api/card/generate — 生成数字名片
# ============================================================

@router.post("/generate", summary="生成数字名片", description="接受字段JSON → 生成数字名片(含图册元数据)并持久化")
async def generate_card(
    request: CardGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """基于字段JSON生成数字名片并保存到数据库"""
    fields_dict = request.fields.model_dump(exclude_none=True)

    with tracer.start_as_current_span("card.generate") as span:
        span.set_attribute("user_id", current_user.id)
        span.set_attribute("field_count", len(fields_dict))
        span.set_attribute("has_name", bool(fields_dict.get("name")))
        span.set_attribute("has_phone", bool(fields_dict.get("phone")))
        span.set_attribute("has_company", bool(fields_dict.get("company")))

        # 验证字段
        is_valid, errors = validate_card_fields(fields_dict)
        if not is_valid:
            span.set_attribute("validation_error", str(errors))
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"code": 400, "message": "字段验证失败", "data": {"errors": errors}},
            )

        try:
            # 生成数字名片数据
            card_data = generate_digital_card(fields_dict)
            share_token = card_data["share_token"]

            # 持久化到数据库
            db_card = BusinessCard(
                user_id=current_user.id,
                fields=json.dumps(fields_dict, ensure_ascii=False),
                share_token=share_token,
                view_count=0,
                cover_image=fields_dict.get("cover_image"),
                album_meta=json.dumps(card_data["album_meta"], ensure_ascii=False),
            )
            db.add(db_card)
            db.commit()
            db.refresh(db_card)

            # 更新返回数据中的 id
            card_data["id"] = db_card.id
            card_data["share_url"] = f"/card/{share_token}"

            span.set_attribute("card_id", db_card.id)
            span.set_attribute("share_token", share_token)

            logger.info(f"数字名片已保存: id={db_card.id}, user={current_user.id}")

            # PostHog 名片生成埋点
            try:
                capture_card_generated(
                    user_id=str(current_user.id),
                    card_properties={
                        "card_id": db_card.id,
                        "name": fields_dict.get("name", ""),
                        "company": fields_dict.get("company", ""),
                        "position": fields_dict.get("position", ""),
                        "has_phone": bool(fields_dict.get("phone")),
                        "has_email": bool(fields_dict.get("email")),
                        "has_wechat": bool(fields_dict.get("wechat")),
                        "field_count": len(fields_dict),
                    },
                )
            except Exception:
                pass

            return JSONResponse(content={
                "code": 200,
                "message": "数字名片生成成功",
                "data": card_data,
            })

        except Exception as e:
            db.rollback()
            logger.error(f"数字名片生成失败: {e}", exc_info=True)
            span.set_attribute("error", str(e))
            span.record_exception(e)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"code": 500, "message": f"生成失败: {str(e)}"},
            )


# ============================================================
# GET /api/card/{id} — 获取名片详情（公开分享）
# ============================================================

@router.get("/{id}", summary="获取名片详情", description="通过ID获取名片详情（公开分享，无需认证）")
async def get_card_detail(
    id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """获取名片详情，公开分享使用"""
    card = db.query(BusinessCard).filter(
        BusinessCard.id == id,
        BusinessCard.is_deleted == False,
    ).first()

    if not card:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"code": 404, "message": "名片不存在"},
        )

    # 增加浏览次数
    card.view_count = (card.view_count or 0) + 1
    db.commit()

    # 解析字段
    fields = json.loads(card.fields) if isinstance(card.fields, str) else card.fields
    album_meta = json.loads(card.album_meta) if isinstance(card.album_meta, str) else card.album_meta

    card_response = {
        "id": card.id,
        "share_token": card.share_token,
        "share_url": f"/card/{card.share_token}",
        "name": fields.get("name", "未知"),
        "fields": fields,
        "cover_image": card.cover_image,
        "album_meta": album_meta,
        "created_at": card.created_at.isoformat() if card.created_at else "",
        "view_count": card.view_count,
    }

    return JSONResponse(content={
        "code": 200,
        "message": "success",
        "data": card_response,
    })


# ============================================================
# GET /api/card/token/{token} — 通过 share_token 获取名片
# ============================================================

@router.get("/token/{token}", summary="通过分享令牌获取名片", description="通过 share_token 获取名片详情（公开分享）")
async def get_card_by_token(
    token: str,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """通过 share_token 获取名片"""
    card = db.query(BusinessCard).filter(
        BusinessCard.share_token == token,
        BusinessCard.is_deleted == False,
    ).first()

    if not card:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"code": 404, "message": "名片不存在或链接已失效"},
        )

    # 增加浏览次数
    card.view_count = (card.view_count or 0) + 1
    db.commit()

    fields = json.loads(card.fields) if isinstance(card.fields, str) else card.fields
    album_meta = json.loads(card.album_meta) if isinstance(card.album_meta, str) else card.album_meta

    return JSONResponse(content={
        "code": 200,
        "message": "success",
        "data": {
            "id": card.id,
            "share_token": card.share_token,
            "share_url": f"/card/{card.share_token}",
            "name": fields.get("name", "未知"),
            "fields": fields,
            "cover_image": card.cover_image,
            "album_meta": album_meta,
            "created_at": card.created_at.isoformat() if card.created_at else "",
            "view_count": card.view_count,
        },
    })


# ============================================================
# POST /api/card/{id}/match — 基于名片触发供需匹配
# ============================================================

@router.post("/{id}/match", summary="名片供需匹配", description="基于名片信息触发供需匹配（需求+产品）")
async def match_card(
    id: int,
    top_k: int = Query(10, ge=1, le=50, description="返回最大匹配数"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """基于名片信息匹配供需

    匹配逻辑:
      1. 从名片中提取公司/职位/业务关键词
      2. 搜索 BusinessNeed 和 Product
      3. 按相似度排序返回
    """
    with tracer.start_as_current_span("card.match") as span:
        span.set_attribute("card_id", id)
        span.set_attribute("user_id", current_user.id)
        span.set_attribute("top_k", top_k)

        card = db.query(BusinessCard).filter(
            BusinessCard.id == id,
            BusinessCard.is_deleted == False,
        ).first()

        if not card:
            span.set_attribute("error", "card_not_found")
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"code": 404, "message": "名片不存在"},
            )

        # 验证权限（仅名片所有者可触发匹配）
        if card.user_id != current_user.id:
            span.set_attribute("error", "permission_denied")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"code": 403, "message": "无权操作此名片"},
            )

        try:
            fields = json.loads(card.fields) if isinstance(card.fields, str) else card.fields

            card_data = {
                "fields": fields,
                "cover_image": card.cover_image,
            }

            match_results = match_supply_demand(
                card_data=card_data,
                top_k=top_k,
                db_session=db,
            )

            span.set_attribute("match_count", len(match_results))

            return JSONResponse(content={
                "code": 200,
                "message": "供需匹配完成",
                "data": {
                    "total": len(match_results),
                    "items": match_results,
                },
            })

        except Exception as e:
            logger.error(f"名片供需匹配失败: {e}", exc_info=True)
            span.set_attribute("error", str(e))
            span.record_exception(e)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"code": 500, "message": f"匹配失败: {str(e)}"},
            )


# ============================================================
# GET /api/card — 获取当前用户的名片列表
# ============================================================

@router.get("", summary="我的名片列表", description="获取当前用户的所有数字名片")
async def list_my_cards(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """获取当前用户的名片列表"""
    query = db.query(BusinessCard).filter(
        BusinessCard.user_id == current_user.id,
        BusinessCard.is_deleted == False,
    ).order_by(BusinessCard.created_at.desc())

    total = query.count()
    cards = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for card in cards:
        fields = json.loads(card.fields) if isinstance(card.fields, str) else card.fields
        items.append({
            "id": card.id,
            "share_token": card.share_token,
            "share_url": f"/card/{card.share_token}",
            "name": fields.get("name", "未知"),
            "company": fields.get("company", ""),
            "position": fields.get("position", ""),
            "fields": fields,
            "cover_image": card.cover_image,
            "view_count": card.view_count,
            "created_at": card.created_at.isoformat() if card.created_at else "",
        })

    return JSONResponse(content={
        "code": 200,
        "message": "success",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        },
    })


# ============================================================
# DELETE /api/card/{id} — 删除名片
# ============================================================

@router.delete("/{id}", summary="删除名片", description="软删除名片")
async def delete_card(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """软删除名片"""
    card = db.query(BusinessCard).filter(
        BusinessCard.id == id,
        BusinessCard.is_deleted == False,
    ).first()

    if not card:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"code": 404, "message": "名片不存在"},
        )

    if card.user_id != current_user.id:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"code": 403, "message": "无权操作此名片"},
        )

    from datetime import datetime
    card.is_deleted = True
    card.deleted_at = datetime.utcnow()
    db.commit()

    return JSONResponse(content={
        "code": 200,
        "message": "名片已删除",
    })
