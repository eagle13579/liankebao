"""HttpDelegate — HTTP 委托抽象层

从 payment/http_delegate.py 直接提取，不做修改。
基于 httpx.AsyncClient，支持 SSL 双向认证。
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

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
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> dict | None:
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
    """HTTP 委托抽象层

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
        cert_path: str | None = None,
        key_path: str | None = None,
        timeout: int = 30,
        headers: dict[str, str] | None = None,
        verify: bool = True,
    ):
        self._cert_path = cert_path
        self._key_path = key_path
        self._timeout = timeout
        self._default_headers = headers or {}
        self._verify = verify
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            client_kwargs: dict[str, Any] = {
                "timeout": httpx.Timeout(self._timeout),
                "verify": self._verify,
            }
            if self._cert_path and self._key_path:
                client_kwargs["cert"] = (self._cert_path, self._key_path)
            self._client = httpx.AsyncClient(**client_kwargs)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _merge_headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        merged = dict(self._default_headers)
        if headers:
            merged.update(headers)
        return merged

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
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

    async def post(
        self,
        url: str,
        data: str | None = None,
        json_body: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        client = await self._get_client()
        merged_headers = self._merge_headers(headers)
        try:
            resp = await client.post(url, content=data, json=json_body, headers=merged_headers)
            return HttpResponse(
                status=resp.status_code,
                body=resp.text,
                body_bytes=resp.content,
                headers=dict(resp.headers),
            )
        except httpx.HTTPError as e:
            logger.error(f"POST 请求失败: {url} — {e}")
            return HttpResponse(status=0, body=str(e))

    async def put(
        self,
        url: str,
        data: str | None = None,
        json_body: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        client = await self._get_client()
        merged_headers = self._merge_headers(headers)
        try:
            resp = await client.put(url, content=data, json=json_body, headers=merged_headers)
            return HttpResponse(
                status=resp.status_code,
                body=resp.text,
                body_bytes=resp.content,
                headers=dict(resp.headers),
            )
        except httpx.HTTPError as e:
            logger.error(f"PUT 请求失败: {url} — {e}")
            return HttpResponse(status=0, body=str(e))

    async def delete(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
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
            },
        )
