"""
链客宝 — 文件存储 API 路由
===========================
提供文件上传、删除、URL 获取的 REST API。

端点:
  POST   /api/storage/upload       — 上传文件（multipart/form-data）
  DELETE /api/storage/{path:path}  — 删除文件
  GET    /api/storage/{path:path}  — 获取文件公开 URL
"""

import os
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel, Field

from app.storage_service import (
    get_storage_backend,
    validate_file,
    generate_storage_path,
    StorageBackend,
)

logger = logging.getLogger(__name__)

# ===================================================================
# Router
# ===================================================================
router = APIRouter(prefix="/api/storage", tags=["文件存储"])


# ===================================================================
# Pydantic 响应模型
# ===================================================================

class UploadResponse(BaseModel):
    """上传文件响应"""
    url: str = Field(..., description="文件公开访问 URL")
    path: str = Field(..., description="文件存储路径")


class DeleteResponse(BaseModel):
    """删除文件响应"""
    success: bool
    message: str


class UrlResponse(BaseModel):
    """文件 URL 响应"""
    url: str = Field(..., description="文件公开访问 URL")
    path: str = Field(..., description="文件存储路径")


# ===================================================================
# POST /api/storage/upload — 上传文件
# ===================================================================

@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(..., description="要上传的文件"),
    subdir: str = Form("", description="子目录（可选，如 user_avatars/）"),
):
    """上传文件

    支持的文件类型: 图片 (jpeg/png/gif/webp/svg/bmp), PDF, Office 文档, 纯文本
    文件大小限制: 10MB
    """
    # 校验 Content-Type
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "unknown.bin"

    # 读取文件内容（同时进行大小校验）
    raw_data = await file.read()
    file_size = len(raw_data)

    try:
        validate_file(content_type, filename, file_size)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 生成存储路径
    storage_path = generate_storage_path(filename, subdir=subdir)

    # 上传到后端
    storage: StorageBackend = get_storage_backend()
    from io import BytesIO
    url = storage.upload(BytesIO(raw_data), storage_path)

    logger.info(f"[Storage] 上传成功: {filename} → {storage_path} ({file_size} bytes)")
    return UploadResponse(url=url, path=storage_path)


# ===================================================================
# DELETE /api/storage/{path} — 删除文件
# ===================================================================

@router.delete("/{path:path}", response_model=DeleteResponse)
async def delete_file(path: str):
    """删除已上传的文件

    Args:
        path: 文件存储路径（相对路径，如 a1b2c3d4-image.jpg）
    """
    storage: StorageBackend = get_storage_backend()
    success = storage.delete(path)

    if success:
        logger.info(f"[Storage] 删除成功: {path}")
        return DeleteResponse(success=True, message=f"文件已删除: {path}")
    else:
        logger.warning(f"[Storage] 删除失败（文件不存在）: {path}")
        raise HTTPException(
            status_code=404,
            detail=f"文件不存在: {path}",
        )


# ===================================================================
# GET /api/storage/{path} — 获取文件 URL
# ===================================================================

@router.get("/{path:path}", response_model=UrlResponse)
async def get_file_url(path: str):
    """获取文件的公开访问 URL

    Args:
        path: 文件存储路径（相对路径，如 a1b2c3d4-image.jpg）
    """
    storage: StorageBackend = get_storage_backend()
    try:
        url = storage.get_url(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return UrlResponse(url=url, path=path)
