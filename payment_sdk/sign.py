"""PayKit — 签名门面 (纯函数)

从 payment/sign.py 直接提取，不做修改。
基于 cryptography 库，提供:
    - RSA 签名/验签 (微信 V3)
    - MD5 签名 (微信 V2)
    - HMAC-SHA256 签名
    - AES-GCM 解密 (微信 V3 回调 resource)
"""

import hashlib
import hmac
import logging

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

logger = logging.getLogger(__name__)


# ============================================================
# 通用工具
# ============================================================


def generate_nonce(length: int = 32) -> str:
    """生成随机字符串"""
    import secrets

    return secrets.token_hex(length // 2)[:length]


def md5(data: str) -> str:
    """MD5 哈希 (16进制小写)"""
    return hashlib.md5(data.encode("utf-8")).hexdigest()


def md5_upper(data: str) -> str:
    """MD5 哈希 (16进制大写) — 微信 V2 签名格式"""
    return md5(data).upper()


def hmac_sha256(data: str, key: str) -> str:
    """HMAC-SHA256 (16进制小写)"""
    h = hmac.new(key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256)
    return h.hexdigest()


def hmac_sha256_upper(data: str, key: str) -> str:
    """HMAC-SHA256 (16进制大写) — 微信 V2 签名格式"""
    return hmac_sha256(data, key).upper()


def sha256(data: str) -> str:
    """SHA-256 (16进制)"""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# ============================================================
# RSA 操作 (微信 V3)
# ============================================================


def _load_private_key(key_path: str) -> rsa.RSAPrivateKey:
    """从文件加载 RSA 私钥"""
    try:
        with open(key_path, "rb") as f:
            return serialization.load_pem_private_key(
                f.read(),
                password=None,
                backend=default_backend(),
            )
    except Exception as e:
        logger.error(f"加载私钥失败: {key_path} — {e}")
        raise


def _load_public_key(key_path: str) -> rsa.RSAPublicKey:
    """从文件加载 RSA 公钥"""
    try:
        with open(key_path, "rb") as f:
            return serialization.load_pem_public_key(
                f.read(),
                backend=default_backend(),
            )
    except Exception as e:
        logger.error(f"加载公钥失败: {key_path} — {e}")
        raise


def rsa_sign(content: str, private_key_path: str) -> str:
    """RSA-SHA256 签名 (微信 V3)"""
    import base64

    private_key = _load_private_key(private_key_path)
    signature = private_key.sign(
        content.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def rsa_sign_bytes(content_bytes: bytes, private_key_path: str) -> str:
    """RSA-SHA256 签名 (字节输入)"""
    import base64

    private_key = _load_private_key(private_key_path)
    signature = private_key.sign(
        content_bytes,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def rsa_verify(content: str, signature_b64: str, public_key_path: str) -> bool:
    """RSA-SHA256 验签 (微信 V3)"""
    import base64

    try:
        public_key = _load_public_key(public_key_path)
        signature = base64.b64decode(signature_b64)
        public_key.verify(
            signature,
            content.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception as e:
        logger.warning(f"RSA 验签失败: {e}")
        return False


def rsa_verify_with_key(content: str, signature_b64: str, public_key_pem: bytes) -> bool:
    """RSA-SHA256 验签 (使用 PEM 字节)"""
    import base64

    try:
        public_key = serialization.load_pem_public_key(public_key_pem, backend=default_backend())
        signature = base64.b64decode(signature_b64)
        public_key.verify(
            signature,
            content.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception as e:
        logger.warning(f"RSA 验签失败: {e}")
        return False


# ============================================================
# 微信 V3 签名串构建
# ============================================================


def build_v3_sign_str(method: str, url: str, timestamp: str, nonce: str, body: str) -> str:
    """构造微信 V3 签名串

    格式:
        HTTP动词\\n
        请求网址\\n
        请求时间戳\\n
        请求随机串\\n
        请求报文主体\\n
    """
    return f"{method}\n{url}\n{timestamp}\n{nonce}\n{body}\n"


def build_v3_response_sign_str(timestamp: str, nonce: str, body: str) -> str:
    """构造微信 V3 回调响应签名串

    格式:
        时间戳\\n
        随机串\\n
        报文主体\\n
    """
    return f"{timestamp}\n{nonce}\n{body}\n"


# ============================================================
# 微信 V2 签名构建
# ============================================================


def build_v2_sign(params: dict, api_key: str, sign_type: str = "MD5") -> str:
    """构建微信 V2 签名"""
    filtered = {k: v for k, v in params.items() if v != "" and v is not None and k != "sign"}
    sorted_keys = sorted(filtered.keys())
    parts = [f"{k}={filtered[k]}" for k in sorted_keys]
    sign_str = "&".join(parts) + f"&key={api_key}"

    if sign_type == "HMAC-SHA256":
        return hmac_sha256_upper(sign_str, api_key)
    else:
        return md5_upper(sign_str)


def verify_v2_sign(params: dict, api_key: str, sign_type: str = "MD5") -> bool:
    """验证微信 V2 签名"""
    received_sign = params.get("sign", "")
    if not received_sign:
        logger.warning("V2 回调中无 sign 字段")
        return False

    calculated = build_v2_sign(params, api_key, sign_type)
    if calculated == received_sign:
        return True

    # 如果指定了 MD5，尝试 HMAC-SHA256 (微信可能混合使用)
    if sign_type == "MD5":
        calculated2 = build_v2_sign(params, api_key, "HMAC-SHA256")
        if calculated2 == received_sign:
            return True

    return False


# ============================================================
# AES-GCM 解密 (微信 V3 回调 resource 解密)
# ============================================================


def aes_gcm_decrypt(ciphertext_b64: str, key: str, nonce: str, associated_data: str) -> str | None:
    """AES-256-GCM 解密 (微信 V3 回调 resource 解密)

    Args:
        ciphertext_b64: Base64 编码的密文
        key: APIv3 密钥 (32位)
        nonce: 随机串
        associated_data: 附加数据

    Returns:
        解密后的明文 JSON 字符串，失败返回 None
    """
    import base64

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        key_bytes = key.encode("utf-8")
        nonce_bytes = nonce.encode("utf-8")
        aad_bytes = associated_data.encode("utf-8")
        ciphertext = base64.b64decode(ciphertext_b64)

        aesgcm = AESGCM(key_bytes)
        plaintext = aesgcm.decrypt(nonce_bytes, ciphertext, aad_bytes)
        return plaintext.decode("utf-8")
    except Exception as e:
        logger.error(f"AES-GCM 解密失败: {e}")
        return None
