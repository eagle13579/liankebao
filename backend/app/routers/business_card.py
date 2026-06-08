"""
链客宝 AI 数字名片路由
========================
- POST /api/card/scan — 上传名片图片/PDF → AI提取字段
- POST /api/card/generate — 接受字段JSON → 生成数字名片
- GET  /api/card/{id} — 获取名片详情（公开分享）
- POST /api/card/{id}/match — 基于名片触发供需匹配
"""

import io
import json
import logging
import os
import tempfile
import uuid
from typing import Any

import qrcode
from fastapi import APIRouter, Depends, File, Header, Query, UploadFile, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, verify_token
from app.business_card_ai import (
    CARD_FIELDS,
    extract_fields,
    generate_digital_card,
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

    name: str | None = None
    position: str | None = None
    company: str | None = None
    phone: str | None = None
    email: str | None = None
    wechat: str | None = None
    address: str | None = None
    website: str | None = None
    cover_image: str | None = None


class CardGenerateRequest(BaseModel):
    """生成数字名片请求"""

    fields: CardFields


class CardMatchResult(BaseModel):
    """匹配结果条目"""

    type: str  # "need" or "product"
    id: int
    title: str
    category: str | None = None
    score: float
    reasons: list[str]


class CardResponse(BaseModel):
    """名片响应"""

    id: int | None = None
    share_token: str
    share_url: str
    name: str
    fields: dict[str, Any]
    cover_image: str | None = None
    album_meta: dict[str, Any] | None = None
    created_at: str
    view_count: int = 0


class ApiResponse(BaseModel):
    """统一 API 响应"""

    code: int = 200
    message: str = "success"
    data: Any = None


class CardSyncRequest(BaseModel):
    """小程序同步名片请求

    对应小程序 brochure-editor 表单字段:
      - name, company, position, bio, phone, wechat, email
      - products: [{name, price, desc, image}]
      - needs: [{title, description, category}]
    """

    name: str | None = None
    company: str | None = None
    position: str | None = None
    bio: str | None = None
    phone: str | None = None
    wechat: str | None = None
    email: str | None = None
    user_id: int | None = None  # 小程序用户ID（可选，优先用认证用户）
    openid: str | None = None  # 微信openid（可选，用来查找或创建用户）


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
        return JSONResponse(
            content={
                "code": 200,
                "message": "名片扫描完成，请确认字段信息",
                "data": {
                    "raw_text": raw_text,
                    "fields": fields,
                    "suggestions": _generate_suggestions(fields),
                },
            }
        )

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


def _generate_suggestions(fields: dict[str, Any]) -> list[str]:
    """根据字段完整性生成优化建议"""
    suggestions = []
    missing = [f for f in CARD_FIELDS if not fields.get(f)]
    if missing:
        missing_names = {
            "name": "姓名",
            "position": "职位",
            "company": "公司",
            "phone": "手机",
            "email": "邮箱",
            "wechat": "微信",
            "address": "地址",
            "website": "官网",
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

            return JSONResponse(
                content={
                    "code": 200,
                    "message": "数字名片生成成功",
                    "data": card_data,
                }
            )

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
    card = (
        db.query(BusinessCard)
        .filter(
            BusinessCard.id == id,
            BusinessCard.is_deleted == False,
        )
        .first()
    )

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
        "updated_at": card.updated_at.isoformat() if card.updated_at else "",
        "view_count": card.view_count,
        "brochure_user_id": card.brochure_id or f"u_{card.user_id:08x}",
    }

    return JSONResponse(
        content={
            "code": 200,
            "message": "success",
            "data": card_response,
        }
    )


# ============================================================
# GET /api/card/token/{token} — 通过 share_token 获取名片
# ============================================================


@router.get("/token/{token}", summary="通过分享令牌获取名片", description="通过 share_token 获取名片详情（公开分享）")
async def get_card_by_token(
    token: str,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """通过 share_token 获取名片"""
    card = (
        db.query(BusinessCard)
        .filter(
            BusinessCard.share_token == token,
            BusinessCard.is_deleted == False,
        )
        .first()
    )

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

    return JSONResponse(
        content={
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
                "updated_at": card.updated_at.isoformat() if card.updated_at else "",
                "view_count": card.view_count,
                "brochure_user_id": card.brochure_id or f"u_{card.user_id:08x}",
            },
        }
    )


# ============================================================
# POST /api/card/sync-from-miniapp — 小程序数据同步
# ============================================================


@router.post(
    "/sync-from-miniapp",
    summary="小程序同步名片",
    description="接收小程序填写的名片数据，写入BusinessCard表并自动生成album_meta翻页图册",
)
async def sync_card_from_miniapp(
    request: CardSyncRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None, description="Bearer token（可选）"),
) -> JSONResponse:
    """从小程序同步名片数据

    1. 确定用户身份（优先用token认证用户，其次用 user_id/openid）
    2. 构建名片字段JSON
    3. 调用 generate_digital_card 生成album_meta
    4. 持久化到 BusinessCard 表
    """
    with tracer.start_as_current_span("card.sync_from_miniapp") as span:
        # --- Step 1: 确定用户身份 ---
        user: User | None = None

        # 1a. 优先尝试从 Authorization header 解析token
        if authorization and authorization.startswith("Bearer "):
            token_str = authorization[7:]
            payload = verify_token(token_str, expected_type="access")
            if payload:
                username = payload.get("sub")
                if username:
                    user = db.query(User).filter(User.username == username, User.is_deleted.is_(False)).first()

        # 1b. 其次通过 openid 查找
        if not user and request.openid:
            user = db.query(User).filter(User.wechat_openid == request.openid, User.is_deleted.is_(False)).first()

        # 1c. 最后通过 user_id 查找
        if not user and request.user_id:
            user = db.query(User).filter(User.id == request.user_id, User.is_deleted.is_(False)).first()

        if not user:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"code": 401, "message": "无法识别用户身份，请先登录"},
            )

        span.set_attribute("user_id", user.id)

        # --- Step 2: 构建名片字段 ---
        fields_dict: dict[str, Any] = {}
        if request.name:
            fields_dict["name"] = request.name
        if request.company:
            fields_dict["company"] = request.company
        if request.position:
            fields_dict["position"] = request.position
        if request.phone:
            fields_dict["phone"] = request.phone
        if request.wechat:
            fields_dict["wechat"] = request.wechat
        if request.email:
            fields_dict["email"] = request.email
        if request.bio:
            fields_dict["bio"] = request.bio

        # 如果没有姓名，不能生成名片
        if not fields_dict.get("name"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"code": 400, "message": "姓名(name)为必填字段"},
            )

        try:
            # --- Step 3: 生成数字名片数据（含album_meta）---
            card_data = generate_digital_card(fields_dict)
            share_token = card_data["share_token"]

            # --- Step 4: 持久化到数据库 ---
            db_card = BusinessCard(
                user_id=user.id,
                fields=json.dumps(fields_dict, ensure_ascii=False),
                share_token=share_token,
                view_count=0,
                cover_image=fields_dict.get("cover_image"),
                album_meta=json.dumps(card_data["album_meta"], ensure_ascii=False),
            )
            db.add(db_card)
            db.commit()
            db.refresh(db_card)

            card_data["id"] = db_card.id
            card_data["share_url"] = f"/card/{share_token}"

            span.set_attribute("card_id", db_card.id)
            span.set_attribute("share_token", share_token)

            logger.info(f"小程序名片同步成功: id={db_card.id}, user={user.id}")

            return JSONResponse(
                content={
                    "code": 200,
                    "message": "名片同步成功",
                    "data": card_data,
                }
            )
        except Exception as e:
            db.rollback()
            logger.error(f"小程序名片同步失败: {e}", exc_info=True)
            span.set_attribute("error", str(e))
            span.record_exception(e)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"code": 500, "message": f"同步失败: {str(e)}"},
            )


# ============================================================
# GET /api/card/{id}/qrcode — 生成名片QR码（公开分享）
# ============================================================


@router.get("/{id}/qrcode", summary="生成名片QR码", description="根据名片ID生成分享二维码PNG图片")
async def get_card_qrcode(
    id: int,
    download: bool = Query(False, description="是否作为附件下载（True=下载，False=预览）"),
    db: Session = Depends(get_db),
) -> Response:
    """生成名片分享二维码（返回PNG图片）

    支持 download 查询参数:
      - ?download=false (默认): 浏览器预览
      - ?download=true: 触发浏览器下载
    """
    card = (
        db.query(BusinessCard)
        .filter(
            BusinessCard.id == id,
            BusinessCard.is_deleted == False,
        )
        .first()
    )

    if not card:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"code": 404, "message": "名片不存在"},
        )

    # 构建名片分享链接
    share_url = f"https://www.go-aiport.com/card/{card.share_token}"

    # 生成QR码（带logo装饰 - 在QR码中心嵌入链客宝图标占位）
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(share_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # 输出为PNG字节流
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    disposition = "attachment" if download else "inline"

    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={
            "Content-Disposition": f'{disposition}; filename="card_{card.share_token}_qrcode.png"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


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

        card = (
            db.query(BusinessCard)
            .filter(
                BusinessCard.id == id,
                BusinessCard.is_deleted == False,
            )
            .first()
        )

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

            # match_supply_demand 返回 {enterprise_profile, items}
            if isinstance(match_results, dict):
                enterprise_profile = match_results.get("enterprise_profile")
                items = match_results.get("items", [])
            else:
                # 兼容旧格式（纯列表）
                enterprise_profile = None
                items = match_results

            span.set_attribute("match_count", len(items))
            span.set_attribute("has_enterprise_match", bool(enterprise_profile))

            response_data = {
                "total": len(items),
                "items": items,
            }
            if enterprise_profile:
                response_data["enterprise"] = enterprise_profile
                # 同时查询企业关联的供需（按行业/地区精准匹配）
                related = _get_enterprise_related_items(enterprise_profile, db, top_k)
                if related:
                    response_data["enterprise_related"] = related

            return JSONResponse(
                content={
                    "code": 200,
                    "message": "供需匹配完成",
                    "data": response_data,
                }
            )

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
    query = (
        db.query(BusinessCard)
        .filter(
            BusinessCard.user_id == current_user.id,
            BusinessCard.is_deleted == False,
        )
        .order_by(BusinessCard.created_at.desc())
    )

    total = query.count()
    cards = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for card in cards:
        fields = json.loads(card.fields) if isinstance(card.fields, str) else card.fields
        items.append(
            {
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
            }
        )

    return JSONResponse(
        content={
            "code": 200,
            "message": "success",
            "data": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": items,
            },
        }
    )


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
    card = (
        db.query(BusinessCard)
        .filter(
            BusinessCard.id == id,
            BusinessCard.is_deleted == False,
        )
        .first()
    )

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

    return JSONResponse(
        content={
            "code": 200,
            "message": "名片已删除",
        }
    )


# ============================================================
# 企业画像相关匹配工具
# ============================================================


def _get_enterprise_related_items(
    enterprise_profile: dict,
    db,
    top_k: int = 10,
) -> list[dict]:
    """根据企业画像（行业/地区）查询关联供需

    在名片匹配结果之外，额外推荐同行业/同地区的关联供需。
    实现方式：基于企业行业和地区，搜索 BusinessNeed 和 Product。
    """
    items = []
    industry = enterprise_profile.get("industry", "")
    region = enterprise_profile.get("region", "")

    if not industry and not region:
        return []

    try:
        from sqlalchemy import or_

        from app.models import BusinessNeed, Product

        # --- 查询关联需求 ---
        need_filters = [
            BusinessNeed.is_deleted == False,
            BusinessNeed.status == "open",
        ]
        or_clauses = []
        if industry:
            like_ind = f"%{industry}%"
            or_clauses.append(BusinessNeed.category.ilike(like_ind))
            or_clauses.append(BusinessNeed.title.ilike(like_ind))
        if region:
            like_reg = f"%{region}%"
            or_clauses.append(BusinessNeed.region.ilike(like_reg))

        if or_clauses:
            need_filters.append(or_(*or_clauses))

        needs = db.query(BusinessNeed).filter(*need_filters).order_by(BusinessNeed.created_at.desc()).limit(top_k).all()

        for n in needs:
            reasons = []
            if industry and n.category and industry in n.category:
                reasons.append(f"同行业: {industry}")
            if region and n.region and region in n.region:
                reasons.append(f"同地区: {region}")
            items.append(
                {
                    "type": "need",
                    "id": n.id,
                    "title": n.title,
                    "category": n.category,
                    "score": 0.9,
                    "reasons": reasons or ["企业画像关联推荐"],
                }
            )

        # --- 查询关联产品 ---
        prod_filters = [
            Product.is_deleted == False,
            Product.status == "approved",
        ]
        or_clauses_prod = []
        if industry:
            like_ind = f"%{industry}%"
            or_clauses_prod.append(Product.category.ilike(like_ind))
            or_clauses_prod.append(Product.tags.ilike(like_ind))
        if region:
            like_reg = f"%{region}%"
            or_clauses_prod.append(Product.specs.ilike(like_reg))

        if or_clauses_prod:
            prod_filters.append(or_(*or_clauses_prod))

        products = db.query(Product).filter(*prod_filters).order_by(Product.created_at.desc()).limit(top_k).all()

        for p in products:
            reasons = []
            if industry and p.category and industry in p.category:
                reasons.append(f"同行业: {industry}")
            items.append(
                {
                    "type": "product",
                    "id": p.id,
                    "title": p.name,
                    "category": p.category,
                    "score": 0.85,
                    "reasons": reasons or ["企业画像关联推荐"],
                }
            )

    except Exception as e:
        logger.debug(f"企业关联供需查询跳过: {e}")

    # 去重（按 id + type）
    seen = set()
    deduped = []
    for item in items:
        key = (item["type"], item["id"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    return deduped[:top_k]
