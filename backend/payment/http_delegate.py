"""
HttpDelegate — HTTP 委托抽象层
基于 IJPay ch-03
httpx.AsyncClient 默认实现
支持 SSL 双向认证（微信 V3 需要）
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Tuple

import httpx

logger = logging.getLogger(__name__)


# ============================================================
# HTTP 响应封装
# ============================================================

@dataclass
class HttpResponse:
    """统一 HTTP 响应"""
    status: int = 200
    body: str = ""
    body_bytes: bytes = b""
    headers: Dict[str, str] = field(default_factory=dict)

    def json(self) -> Optional[dict]:
        """尝试解析 JSON 响应"""
        if not self.body:
            return None
        try:
            return json.loads(self.body)
        except json.JSONDecodeError:
            return None

    def is_success(self) -> bool:
        """是否成功 (2xx)"""
        return 200 <= self.status < 300


# ============================================================
# HttpDelegate — HTTP 委托抽象层
# ============================================================

class HttpDelegate:
    """
    HTTP 委托抽象层

    基于 httpx.AsyncClient，支持:
    - GET/POST/PUT/DELETE 请求
    - JSON / 表单 / 文本 body
    - SSL 双向认证 (微信 V3 退款、企业付款等)
    - 自定义请求头
    - 超时控制

    用法:
        delegate = HttpDelegate()
        resp = await delegate.post("https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi", json=body)
    """

    def __init__(
        self,
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
        timeout: int = 30,
        headers: Optional[Dict[str, str]] = None,
        verify: bool = True,
    ):
        """
        Args:
            cert_path: 客户端证书路径 (pem)
            key_path: 客户端私钥路径 (pem)
            timeout: 超时秒数
            headers: 默认请求头
            verify: 是否验证 SSL (可传 CA 路径字符串)
        """
        self._cert_path = cert_path
        self._key_path = key_path
        self._timeout = timeout
        self._default_headers = headers or {}
        self._verify = verify
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 httpx.AsyncClient 实例"""
        if self._client is None or self._client.is_closed:
            client_kwargs: Dict[str, Any] = {
                "timeout": httpx.Timeout(self._timeout),
                "verify": self._verify,
            }

            # SSL 双向认证
            if self._cert_path and self._key_path:
                client_kwargs["cert"] = (self._cert_path, self._key_path)

            self._client = httpx.AsyncClient(**client_kwargs)
        return self._client

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _merge_headers(self, headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """合并默认头与自定义头"""
        merged = dict(self._default_headers)
        if headers:
            merged.update(headers)
        return merged

    # ===== GET =====

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> HttpResponse:
        """GET 请求"""
        client = await self._get_client()
        merged_headers = self._merge_headers(headers)

        try:
            resp = await client.get(url, params=params, headers=merged_headers)
            return HttpResponse(
                status=resp.status_code,
                body=resp.text,
                body_bytes=resp.content,
                headers=dict(resp.headers),
            )
        except httpx.HTTPError as e:
            logger.error(f"GET 请求失败: {url} — {e}")
            return HttpResponse(status=0, body=str(e))

    # ===== POST =====

    async def post(
        self,
        url: str,
        data: Optional[str] = None,
        json_body: Optional[dict] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> HttpResponse:
        """POST 请求"""
        client = await self._get_client()
        merged_headers = self._merge_headers(headers)

        try:
            resp = await client.post(
                url, content=data, json=json_body, headers=merged_headers
            )
            return HttpResponse(
                status=resp.status_code,
                body=resp.text,
                body_bytes=resp.content,
                headers=dict(resp.headers),
            )
        except httpx.HTTPError as e:
            logger.error(f"POST 请求失败: {url} — {e}")
            return HttpResponse(status=0, body=str(e))

    # ===== PUT =====

    async def put(
        self,
        url: str,
        data: Optional[str] = None,
        json_body: Optional[dict] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> HttpResponse:
        """PUT 请求"""
        client = await self._get_client()
        merged_headers = self._merge_headers(headers)

        try:
            resp = await client.put(
                url, content=data, json=json_body, headers=merged_headers
            )
            return HttpResponse(
                status=resp.status_code,
                body=resp.text,
                body_bytes=resp.content,
                headers=dict(resp.headers),
            )
        except httpx.HTTPError as e:
            logger.error(f"PUT 请求失败: {url} — {e}")
            return HttpResponse(status=0, body=str(e))

    # ===== DELETE =====

    async def delete(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> HttpResponse:
        """DELETE 请求"""
        client = await self._get_client()
        merged_headers = self._merge_headers(headers)

        try:
            resp = await client.delete(url, headers=merged_headers)
            return HttpResponse(
                status=resp.status_code,
                body=resp.text,
                body_bytes=resp.content,
                headers=dict(resp.headers),
            )
        except httpx.HTTPError as e:
            logger.error(f"DELETE 请求失败: {url} — {e}")
            return HttpResponse(status=0, body=str(e))

    # ===== 工厂方法 =====

    @staticmethod
    def default() -> "HttpDelegate":
        """创建默认 HTTP 委托"""
        return HttpDelegate(
            headers={
                "User-Agent": "liankebao-payment/1.0",
                "Accept": "application/json",
            }
        )

    @staticmethod
    def with_ssl_cert(cert_path: str, key_path: str) -> "HttpDelegate":
        """创建带双向 SSL 认证的 HTTP 委托"""
        return HttpDelegate(
            cert_path=cert_path,
            key_path=key_path,
            headers={
                "User-Agent": "liankebao-payment/1.0",
                "Accept": "application/json",
            }
        )
