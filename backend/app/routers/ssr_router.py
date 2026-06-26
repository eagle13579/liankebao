"""
链客宝 — SSR 预渲染路由
=============================================================================
功能: 为 nginx 提供 SSR 预渲染代理端点, 转发爬虫请求到 Puppeteer 预渲染服务.

架构:
    爬虫请求 → Nginx (检测 $is_bot) → 静态预渲染文件 /prerendered/ 优先
    → 静态文件不存在则代理到 Prerender Service (port 3001) → 返回渲染 HTML

使用方式:
    在 app/main.py 中注册:
        from app.routers.ssr_router import router as ssr_router
        app.include_router(ssr_router)

    或保持独立: Nginx 直接代理到 prerender_server.py (端口 3001)

环境变量:
    PRERENDER_SERVICE_URL — 预渲染服务地址 (默认 http://127.0.0.1:3001)
    SITE_URL              — 站点基础 URL (默认 https://liankebao.top)
=============================================================================
"""

import logging
import os

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger("ssr_router")

router = APIRouter(tags=["ssr"])

# ── 配置 ────────────────────────────────────────────────────────────────────
PRERENDER_SERVICE_URL = os.getenv(
    "PRERENDER_SERVICE_URL",
    "http://127.0.0.1:3001",
)
SITE_URL = os.getenv("SITE_URL", "https://liankebao.top")

# ── HTTP 客户端 (连接池) ────────────────────────────────────────────────────
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """获取或创建共享 HTTP 客户端"""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=60.0,
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
            ),
        )
    return _client


@router.on_event("shutdown")
async def shutdown():
    """关闭 HTTP 客户端"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ── 路由 ────────────────────────────────────────────────────────────────────
@router.get("/_ssr/render", response_class=HTMLResponse)
async def ssr_render(
    request: Request,
    path: str = Query(
        ...,
        description="要渲染的页面路径 (如 /about, /pricing)",
    ),
    no_cache: bool = Query(
        False,
        description="跳过缓存, 强制重新渲染",
    ),
):
    """
    SSR 预渲染代理端点

    接收一个页面路径, 转发到 Puppeteer 预渲染服务进行动态渲染,
    返回渲染后的完整 HTML.

    Nginx 用法:
        location @prerender-dynamic {
            proxy_pass http://127.0.0.1:8001/_ssr/render?path=$uri&no_cache=false;
            proxy_set_header X-Real-IP $remote_addr;
        }
    """
    # 构建完整的渲染 URL
    render_url = f"{SITE_URL}{path}"

    # 获取原始请求中的 User-Agent (爬虫的 UA)
    bot_ua = request.headers.get("user-agent", "")

    try:
        client = get_client()

        params = {"url": render_url, "ua": bot_ua}
        if no_cache:
            params["no_cache"] = "true"

        resp = await client.get(
            f"{PRERENDER_SERVICE_URL}/render",
            params=params,
        )

        if resp.status_code != 200:
            logger.error(
                "预渲染服务返回 %d (path=%s): %s",
                resp.status_code,
                path,
                resp.text[:200],
            )
            raise HTTPException(
                status_code=502,
                detail=f"预渲染服务错误: {resp.status_code}",
            )

        html = resp.text

        # 添加 X-Render-Source 头标识
        from fastapi.responses import Response

        return Response(
            content=html,
            media_type="text/html",
            headers={
                "X-Render-Source": "puppeteer-dynamic",
                "X-Cache": "MISS" if no_cache else "HIT",
            },
        )

    except httpx.ConnectError as e:
        logger.error(
            "无法连接到预渲染服务 (%s): %s",
            PRERENDER_SERVICE_URL,
            e,
        )
        raise HTTPException(
            status_code=503,
            detail=f"预渲染服务不可用: {PRERENDER_SERVICE_URL}",
        )
    except httpx.TimeoutException as e:
        logger.error("预渲染请求超时 (path=%s): %s", path, e)
        raise HTTPException(
            status_code=504,
            detail="预渲染请求超时",
        )


@router.get("/_ssr/health")
async def ssr_health():
    """SSR 预渲染服务健康检查"""
    try:
        client = get_client()
        resp = await client.get(f"{PRERENDER_SERVICE_URL}/health", timeout=5.0)
        if resp.status_code == 200:
            return {
                "status": "ok",
                "prerender_service": "connected",
                "prerender_detail": resp.json(),
            }
        return {
            "status": "degraded",
            "prerender_service": f"unexpected_status:{resp.status_code}",
        }
    except Exception as e:
        return {
            "status": "error",
            "prerender_service": "unreachable",
            "error": str(e),
        }


@router.post("/_ssr/cache/clear")
async def ssr_cache_clear():
    """清空预渲染服务缓存"""
    try:
        client = get_client()
        resp = await client.post(f"{PRERENDER_SERVICE_URL}/cache/clear", timeout=5.0)
        return resp.json()
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"清空缓存失败: {e}",
        )
