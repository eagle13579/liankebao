"""Rewrite config.py with proper Settings class"""

config_content = '''"""企盟后端 · 配置管理"""

from pydantic_settings import BaseSettings
from typing import Optional
import secrets


class Settings(BaseSettings):
    """应用配置，从 .env 文件和环境变量读取"""

    # JWT
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7

    # 数据库
    DATABASE_URL: str = "sqlite:///./qimeng.db"

    # 微信
    WX_APPID: Optional[str] = None
    WX_SECRET: Optional[str] = None

    # CORS
    CORS_ORIGINS: str = "*"

    # 服务器
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 前端地址（用于生成推广二维码URL）
    BASE_URL: str = "http://localhost:5173"

    # 分润比例
    PLATFORM_FEE_RATE: float = 0.20  # 平台抽佣 20%
    PROMOTER_SHARE_RATE: float = 0.50  # 推广员占平台抽佣的 50%

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"


settings = Settings()
'''

import ast
ast.parse(config_content)
with open("/opt/chainke/backend/app/config.py", "w") as f:
    f.write(config_content)
print("Syntax OK, written")
