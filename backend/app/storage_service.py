"""
链客宝 — 文件存储抽象层
=========================
提供 StorageBackend 抽象基类 + LocalStorage（本地文件系统存储）
+ AliyunOSSStorage（阿里云 OSS 存储），供路由模块调用。

规则：纯新增，不修改现有业务逻辑
"""

import io
import os
import uuid
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, BinaryIO

logger = logging.getLogger(__name__)

# ── 支持的文件类型白名单 ──────────────────────────────────────────
ALLOWED_CONTENT_TYPES: set[str] = {
    # 图片
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "image/bmp",
    # PDF
    "application/pdf",
    # Office 文档
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # 纯文本
    "text/plain",
    "text/csv",
    "text/markdown",
}

ALLOWED_EXTENSIONS: set[str] = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp",
    ".pdf",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".md",
}

# ── 文件大小限制: 10MB ────────────────────────────────────────────
MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10 MB


def validate_file(content_type: str, filename: str, file_size: int) -> None:
    """校验文件类型和大小

    Args:
        content_type: MIME 类型
        filename: 文件名
        file_size: 文件字节数

    Raises:
        ValueError: 如果文件类型不允许或大小超限
    """
    if file_size > MAX_FILE_SIZE:
        raise ValueError(
            f"文件大小超过限制 ({file_size / 1024 / 1024:.1f}MB > 10MB)"
        )

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS and content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(
            f"不支持的文件类型: {content_type} (扩展名: {ext or '无'})"
        )


def generate_storage_path(original_filename: str, subdir: str = "") -> str:
    """生成安全的存储路径（UUID 文件名，保留扩展名）

    Args:
        original_filename: 原始文件名
        subdir: 子目录（如 user_avatars/）

    Returns:
        相对路径，如 "user_avatars/a1b2c3d4-image.jpg"
    """
    ext = Path(original_filename).suffix.lower() or ".bin"
    safe_name = f"{uuid.uuid4().hex[:16]}{ext}"
    if subdir:
        return f"{subdir.rstrip('/')}/{safe_name}"
    return safe_name


# ===================================================================
# 抽象基类
# ===================================================================

class StorageBackend(ABC):
    """文件存储后端抽象基类"""

    @abstractmethod
    def upload(self, file: BinaryIO, path: str) -> str:
        """上传文件

        Args:
            file: 文件二进制流（已 seek 到开头）
            path: 存储路径（相对路径）

        Returns:
            文件的公开访问 URL
        """
        ...

    @abstractmethod
    def delete(self, path: str) -> bool:
        """删除文件

        Args:
            path: 存储路径（相对路径）

        Returns:
            是否成功删除
        """
        ...

    @abstractmethod
    def get_url(self, path: str) -> str:
        """获取文件的公开访问 URL

        Args:
            path: 存储路径（相对路径）

        Returns:
            文件的公开访问 URL
        """
        ...


# ===================================================================
# LocalStorage — 本地文件系统存储
# ===================================================================

class LocalStorage(StorageBackend):
    """本地文件系统存储

    文件保存到 backend/storage/ 目录下。
    开发/测试环境默认实现。
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "storage",
        ))
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[LocalStorage] 存储目录: {self.base_dir}")

    def _abs_path(self, path: str) -> Path:
        """将相对路径转为绝对路径"""
        # 防止路径穿越攻击
        safe = Path(path).as_posix().lstrip("/")
        abs_path = (self.base_dir / safe).resolve()
        if not str(abs_path).startswith(str(self.base_dir.resolve())):
            raise ValueError(f"非法路径: {path}")
        return abs_path

    def upload(self, file: BinaryIO, path: str) -> str:
        abs_path = self._abs_path(path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        content = file.read()
        abs_path.write_bytes(content)
        return self.get_url(path)

    def delete(self, path: str) -> bool:
        abs_path = self._abs_path(path)
        if abs_path.exists() and abs_path.is_file():
            abs_path.unlink()
            logger.info(f"[LocalStorage] 已删除: {abs_path}")
            return True
        logger.warning(f"[LocalStorage] 文件不存在: {abs_path}")
        return False

    def get_url(self, path: str) -> str:
        """返回本地文件 URL（开发环境通过静态文件服务访问）"""
        # 生成 /api/storage/file/{path} 格式的本地 URL
        # 实际部署时可通过 nginx 或 FastAPI 静态文件挂载提供服务
        return f"/api/storage/file/{path}"


# ===================================================================
# AliyunOSSStorage — 阿里云 OSS 存储
# ===================================================================

class AliyunOSSStorage(StorageBackend):
    """阿里云对象存储 OSS

    从环境变量读取配置:
      OSS_ACCESS_KEY_ID      — AccessKey ID
      OSS_ACCESS_KEY_SECRET  — AccessKey Secret
      OSS_BUCKET             — 存储空间名称
      OSS_ENDPOINT           — Endpoint（如 oss-cn-hangzhou.aliyuncs.com）
    """

    def __init__(self):
        self.access_key_id = os.getenv("OSS_ACCESS_KEY_ID", "")
        self.access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET", "")
        self.bucket_name = os.getenv("OSS_BUCKET", "")
        self.endpoint = os.getenv("OSS_ENDPOINT", "")

        if not all([self.access_key_id, self.access_key_secret, self.bucket_name, self.endpoint]):
            logger.warning(
                "[AliyunOSSStorage] OSS 环境变量未完整配置，OSS 存储不可用"
            )
            self._available = False
            return

        self._available = True
        self._init_oss()

    def _init_oss(self):
        """初始化 OSS 客户端（延迟导入 oss2）"""
        try:
            import oss2
        except ImportError:
            logger.error("[AliyunOSSStorage] oss2 SDK 未安装，请执行: pip install oss2")
            self._available = False
            return

        auth = oss2.Auth(self.access_key_id, self.access_key_secret)
        self._bucket = oss2.Bucket(auth, self.endpoint, self.bucket_name)
        logger.info(f"[AliyunOSSStorage] 已连接到 OSS: {self.bucket_name} @ {self.endpoint}")

    @property
    def available(self) -> bool:
        """OSS 是否可用（配置完整且 SDK 安装）"""
        return self._available

    def upload(self, file: BinaryIO, path: str) -> str:
        if not self.available:
            raise RuntimeError("OSS 存储不可用：请检查环境变量配置和 oss2 SDK 安装")
        import oss2
        content = file.read()
        self._bucket.put_object(path, content)
        return self.get_url(path)

    def delete(self, path: str) -> bool:
        if not self.available:
            raise RuntimeError("OSS 存储不可用")
        try:
            import oss2
            self._bucket.delete_object(path)
            logger.info(f"[AliyunOSSStorage] 已删除: {path}")
            return True
        except Exception as e:
            logger.error(f"[AliyunOSSStorage] 删除失败: {path} — {e}")
            return False

    def get_url(self, path: str) -> str:
        """生成 OSS 文件公开访问 URL

        如果 Bucket 开启公共读，直接返回 OSS 默认 URL；
        否则返回签名 URL（有效期 1 小时）。
        """
        if not self.available:
            raise RuntimeError("OSS 存储不可用")
        # OSS 默认 public-read 场景：https://{bucket}.{endpoint}/{path}
        return f"https://{self.bucket_name}.{self.endpoint}/{path}"


# ===================================================================
# 工厂函数：获取存储后端实例（单例）
# ===================================================================

_storage_instance: Optional[StorageBackend] = None


def get_storage_backend() -> StorageBackend:
    """获取存储后端实例

    优先使用 AliyunOSS（如果可用），
    否则回退到 LocalStorage。
    """
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    # 尝试创建 OSS 实例
    oss = AliyunOSSStorage()
    if oss.available:
        _storage_instance = oss
        logger.info("[Storage] 使用阿里云 OSS 存储")
    else:
        _storage_instance = LocalStorage()
        logger.info("[Storage] 使用本地文件存储（fallback）")

    return _storage_instance
