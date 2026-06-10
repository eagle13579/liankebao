"""上传路由：接收产品主图/文件上传，保存到服务器目录"""
import logging
import os
import uuid

from fastapi import APIRouter, UploadFile, File

from app.schemas import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["上传"])

# 上传文件存储目录
UPLOAD_DIR = "/var/www/liankebao/uploads/"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 允许的图片扩展名
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}


@router.post("/upload", response_model=ApiResponse)
async def upload_file(file: UploadFile = File(...)):
    """上传图片/文件，返回可公开访问的URL"""
    # 获取文件扩展名
    original_filename = file.filename or "upload"
    ext = os.path.splitext(original_filename)[1].lower()
    if not ext or ext not in ALLOWED_EXTENSIONS:
        ext = ".jpg"  # 兜底

    # 生成唯一文件名
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    # 保存文件
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    logger.info("文件上传成功: %s (%d bytes)", filename, len(content))

    return ApiResponse(
        code=200,
        message="上传成功",
        data={
            "url": f"https://liankebao.top/uploads/{filename}",
        },
    )
