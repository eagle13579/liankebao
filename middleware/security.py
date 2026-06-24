# security.py — 安全中间件模块 (从gateway.py拆分)
# 按B1隔离边界原则: 安全逻辑与路由逻辑分离, 多Agent可并行开发

import os
import re
from functools import wraps
from urllib.parse import urlparse

# ── JWT校验 ──
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET 环境变量未配置！请用 openssl rand -hex 32 生成")

JWT_ALGORITHM = "HS256"

# ── URL门禁 ──
ALLOWED_EXTERNAL_HOSTS = {
    "api.deepseek.com",
    "api.weixin.qq.com",
    "openapi.alipay.com",
    "127.0.0.1",
    "localhost",
    "0.0.0.0",
}


def is_allowed_external_url(url: str) -> bool:
    try:
        host = urlparse(url).hostname
        return host in ALLOWED_EXTERNAL_HOSTS
    except:
        return False


# ── 输入验证 ──
def validate_input(param_rules):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import request, jsonify

            data = request.get_json(silent=True) or {}
            for param, (required, pattern, msg) in param_rules.items():
                value = data.get(param)
                if required and not value:
                    return jsonify({"error": f"缺少必填字段: {param}"}), 400
                if value and not re.match(pattern, str(value)):
                    return jsonify({"error": msg or f"字段格式错误: {param}"}), 400
            return f(*args, **kwargs)

        return wrapper

    return decorator


# ── CORS ──
CORS_ALLOW_ORIGINS = os.environ.get(
    "CORS_ALLOW_ORIGINS", "http://localhost:3000,http://localhost:5173"
)
CORS_ALLOW_ORIGINS_LIST = [
    o.strip() for o in CORS_ALLOW_ORIGINS.split(",") if o.strip()
]
