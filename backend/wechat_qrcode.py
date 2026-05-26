"""
微信小程序码模块 — wxacode.getUnlimited 接口封装
==================================================

功能:
  1. 自动获取/缓存 access_token（7000 秒过期自动续期）
  2. 调用微信 wxacode.getUnlimited 生成小程序码（B 类二维码，参数放在 scene）
  3. Mock 降级：环境变量未配置 WECHAT_APPID / WECHAT_APP_SECRET 时，
     使用本地 qrcode 库生成兜底二维码（无数量限制）

使用（在 promoter.py 路由中调用）:
    from wechat_qrcode import get_wxacode_unlimited
    result = await get_wxacode_unlimited(scene="...", page="...")
    # result 为 dict: {"image_data": bytes, "content_type": str, "is_mock": bool}
"""
import os
import io
import time
import json
import hashlib
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ============================================================
# 配置常量
# ============================================================
WECHAT_APPID = os.environ.get("WECHAT_APPID", "").strip()
WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET", "").strip()

# 微信 access_token 接口
TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
# 微信小程序码接口（B 类：wxacode.getUnlimited，数量无上限）
WXACODE_URL = "https://api.weixin.qq.com/wxa/getwxacodeunlimit"

# token 缓存（进程级内存）
_token_cache: Dict[str, Any] = {
    "access_token": None,
    "expires_at": 0,  # Unix timestamp
}

# 是否可用微信原生能力（仅当 APPID + SECRET 均配置）
_WX_CONFIGURED = bool(WECHAT_APPID and WECHAT_APP_SECRET)


# ============================================================
# 工具函数：判断是否配置了微信小程序
# ============================================================
def is_wechat_configured() -> bool:
    """检查是否配置了微信小程序 AppId 和 Secret"""
    return _WX_CONFIGURED


# ============================================================
# 1. Access Token 管理（自动缓存，7000 秒过期）
# ============================================================
def _get_access_token_from_api() -> Optional[str]:
    """
    调用微信接口获取 access_token。
    返回 access_token 字符串，失败返回 None。
    """
    if not is_wechat_configured():
        logger.warning("微信小程序未配置（WECHAT_APPID / WECHAT_APP_SECRET 缺失），无法获取 access_token")
        return None

    import requests
    params = {
        "grant_type": "client_credential",
        "appid": WECHAT_APPID,
        "secret": WECHAT_APP_SECRET,
    }
    try:
        resp = requests.get(TOKEN_URL, params=params, timeout=10)
        data = resp.json()
        if "access_token" in data:
            token = data["access_token"]
            # 微信返回的 expires_in 通常是 7200 秒，我们缓存 7000 秒以防边界
            expires_in = data.get("expires_in", 7200)
            _token_cache["access_token"] = token
            _token_cache["expires_at"] = time.time() + min(expires_in, 7000)
            logger.info("微信 access_token 获取成功，缓存 %d 秒", min(expires_in, 7000))
            return token
        else:
            logger.error("微信 access_token 获取失败: %s", data.get("errmsg", "未知错误"))
            return None
    except Exception as e:
        logger.error("微信 access_token 请求异常: %s", e)
        return None


def get_access_token(force_refresh: bool = False) -> Optional[str]:
    """
    获取缓存的 access_token（自动续期）。
    - force_refresh=True 时强制刷新
    - 缓存未过期时直接返回
    - 过期或不存在时自动调用 API
    """
    if not is_wechat_configured():
        return None

    now = time.time()
    cached = _token_cache.get("access_token")
    expires_at = _token_cache.get("expires_at", 0)

    if not force_refresh and cached and now < expires_at:
        return cached

    # 过期了，重新获取
    logger.info("access_token 过期或未缓存，重新获取")
    return _get_access_token_from_api()


# ============================================================
# 2. 调用 wxacode.getUnlimited 生成小程序码
# ============================================================
async def get_wxacode_unlimited(
    scene: str,
    page: str = "pages/index/index",
    width: int = 280,
    auto_color: bool = False,
    line_color: Optional[Dict[str, int]] = None,
    is_hyaline: bool = False,
    check_path: bool = True,
    env_version: str = "release",
) -> Dict[str, Any]:
    """
    调用微信 wxacode.getUnlimited 接口生成小程序码。

    参数:
        scene: 场景参数（最大 32 个字符，推广场景建议格式 "pid=xxx&uid=xxx"）
        page: 小程序页面路径（默认首页）
        width: 二维码宽度（单位 px，最小 280，最大 1280）
        auto_color: 是否自动配色
        line_color: 线条颜色，如 {"r":0,"g":0,"b":0}
        is_hyaline: 是否需要透明底色
        check_path: 是否检查 page 是否存在
        env_version: 要打开的小程序版本（release/trial/develop）

    返回:
        {
            "image_data": bytes,   # 小程序码图片二进制（PNG）
            "content_type": "image/png",
            "is_mock": bool,       # True 表示来自 mock 降级
            "width": width,
        }
        失败时返回 is_mock=True 的降级结果。
    """
    # 尝试获取 access_token
    token = get_access_token()
    if token:
        # 微信原生接口
        import requests as sync_requests
        url = f"{WXACODE_URL}?access_token={token}"
        payload = {
            "scene": scene,
            "page": page,
            "width": width,
            "auto_color": auto_color,
            "is_hyaline": is_hyaline,
            "check_path": check_path,
            "env_version": env_version,
        }
        if line_color:
            payload["line_color"] = line_color

        try:
            resp = sync_requests.post(url, json=payload, timeout=15)
            content_type = resp.headers.get("Content-Type", "")

            # 微信成功时返回 image/png，失败时返回 application/json
            if "image" in content_type:
                logger.info(
                    "微信 wxacode.getUnlimited 成功: scene=%s, page=%s, size=%d bytes",
                    scene, page, len(resp.content),
                )
                return {
                    "image_data": resp.content,
                    "content_type": "image/png",
                    "is_mock": False,
                    "width": width,
                }
            else:
                # 微信返回了 JSON 错误
                err_data = resp.json()
                errcode = err_data.get("errcode", -1)
                errmsg = err_data.get("errmsg", "未知错误")

                # access_token 过期或无效，尝试刷新后重试一次
                if errcode in (40001, 42001, 40014):
                    logger.warning("access_token 失效 (errcode=%d)，尝试刷新重试", errcode)
                    new_token = get_access_token(force_refresh=True)
                    if new_token:
                        url2 = f"{WXACODE_URL}?access_token={new_token}"
                        resp2 = sync_requests.post(url2, json=payload, timeout=15)
                        ct2 = resp2.headers.get("Content-Type", "")
                        if "image" in ct2:
                            return {
                                "image_data": resp2.content,
                                "content_type": "image/png",
                                "is_mock": False,
                                "width": width,
                            }
                        else:
                            err_data = resp2.json()
                            logger.error("重试后仍然失败: %s", err_data)

                logger.error(
                    "微信 wxacode.getUnlimited 失败: errcode=%d, errmsg=%s",
                    errcode, errmsg,
                )
                # 失败后降级到 mock
                return _mock_qrcode(scene, width)

        except Exception as e:
            logger.error("微信 wxacode.getUnlimited 请求异常: %s", e)
            return _mock_qrcode(scene, width)
    else:
        # 没有配置微信或 token 获取失败，降级到 mock
        logger.warning("微信小程序码不可用（无 access_token），使用 mock 降级")
        return _mock_qrcode(scene, width)


# ============================================================
# 3. Mock 降级 — 使用 Python qrcode 库本地生成
# ============================================================
def _mock_qrcode(scene: str, width: int = 280) -> Dict[str, Any]:
    """
    本地生成二维码兜底（依赖 qrcode + Pillow 库）。
    如果依赖库不存在，则生成一个纯色占位 PNG。
    """
    try:
        import qrcode
        from qrcode.image.pil import PilImage

        # 构造分享链接（用于扫描后跳转的落地页）
        from urllib.parse import urlencode
        base_url = "https://www.go-aiport.com/share"
        params = {}
        for pair in scene.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = v
        share_link = f"{base_url}?{urlencode(params)}" if params else base_url

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(share_link)
        qr.make(fit=True)

        img = qr.make_image(fill_color="#1a73e8", back_color="white")
        # 缩放到指定宽度
        img = img.resize((width, width))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        logger.info("Mock 二维码生成成功: scene=%s, width=%d", scene, width)
        return {
            "image_data": buf.getvalue(),
            "content_type": "image/png",
            "is_mock": True,
            "width": width,
        }
    except ImportError:
        logger.warning("qrcode 库未安装，生成占位图降级")
        return _fallback_placeholder(width)
    except Exception as e:
        logger.error("Mock 二维码生成异常: %s", e)
        return _fallback_placeholder(width)


def _fallback_placeholder(width: int = 280) -> Dict[str, Any]:
    """
    最后兜底：返回一个 1x1 PNG 占位图（不依赖任何外部库）。
    """
    # 极简 1x1 白色 PNG（不需要 Pillow）
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return {
        "image_data": png_bytes,
        "content_type": "image/png",
        "is_mock": True,
        "width": width,
        "fallback": True,
    }


# ============================================================
# 4. 便捷函数：生成推广小程序码的 scene 参数
# ============================================================
def build_promoter_scene(product_id: int, promoter_id: int) -> str:
    """
    构建推广场景的 scene 参数字符串。
    格式: "pid={product_id}&uid={promoter_id}"
    注意: scene 最长 32 字符。
    """
    scene = f"pid={product_id}&uid={promoter_id}"
    if len(scene) > 32:
        # 如果超出 32 字符限制，改用短 ID 模式
        scene = f"p{product_id}u{promoter_id}"
        if len(scene) > 32:
            # 极限情况，截断
            scene = scene[:32]
    return scene
