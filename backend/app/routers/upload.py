"""上传路由：接收产品主图/文件上传，保存到服务器目录"""

import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.auth import get_current_user
from app.models import User
from app.schemas import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["上传"])

# 上传文件存储目录
UPLOAD_DIR = "/var/www/liankebao/uploads/"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 允许的图片扩展名（去掉 SVG 防止 XSS 脚本注入）
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

# 最大上传大小（5MB）
MAX_UPLOAD_SIZE = 5 * 1024 * 1024

# 允许的 MIME 类型白名单
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
}


@router.post("/upload", response_model=ApiResponse)
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """上传图片/文件，返回可公开访问的URL（需要认证）"""
    # 验证 MIME 类型
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的图片类型: {file.content_type}",
        )

    # 获取文件扩展名
    original_filename = file.filename or "upload"
    ext = os.path.splitext(original_filename)[1].lower()
    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件扩展名: {ext}",
        )

    # 生成唯一文件名
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    # 保存文件（带大小限制）
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="文件大小超过限制（最大 5MB）",
        )

    with open(filepath, "wb") as f:
        f.write(content)

    logger.info(
        "文件上传成功: %s (%d bytes) by user %s",
        filename,
        len(content),
        current_user.username,
    )

    return ApiResponse(
        code=200,
        message="上传成功",
        data={
            "url": f"https://liankebao.top/uploads/{filename}",
        },
    )
