#!/usr/bin/env python3
"""
链客宝 — Puppeteer 动态预渲染服务
=============================================================================
功能: 基于 Puppeteer (pyppeteer) 的 SSR 预渲染服务, 为爬虫/搜索引擎返回
      动态渲染后的完整 HTML (含 JS 执行后的内容).

架构:
    Nginx 检测到爬虫 → 先尝试静态预渲染文件 (/prerendered/xxx.html)
    → 文件不存在时代理到此服务进行动态渲染 → 缓存结果 → 返回 HTML

使用方式:
    uvicorn prerender_server:app --host 0.0.0.0 --port 3001

    或作为模块运行:
    python -m backend.scripts.prerender_server

环境变量:
    PRERENDER_PORT        — 监听端口 (默认 3001)
    PRERENDER_HOST        — 监听地址 (默认 0.0.0.0)
    PRERENDER_CACHE_SIZE  — 缓存条目数 (默认 100)
    PRERENDER_TIMEOUT     — 单页渲染超时秒数 (默认 30)
    PRERENDER_BROWSER_WS  — 远程浏览器 WebSocket 端点 (可选, 默认启动本地浏览器)
    LOG_LEVEL             — 日志级别 (默认 info)
=============================================================================
"""

import asyncio
import logging
import os
import time
from collections import OrderedDict
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# ── 日志配置 ────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("prerender")

# ── 配置 ────────────────────────────────────────────────────────────────────
PORT = int(os.getenv("PRERENDER_PORT", "3001"))
HOST = os.getenv("PRERENDER_HOST", "0.0.0.0")
CACHE_SIZE = int(os.getenv("PRERENDER_CACHE_SIZE", "100"))
RENDER_TIMEOUT = int(os.getenv("PRERENDER_TIMEOUT", "30"))
BROWSER_WS = os.getenv("PRERENDER_BROWSER_WS", "")

# ── 爬虫 User-Agent (渲染时模拟, 触发 SPA 的 SSR 模式) ─────────────────────
BOT_UA = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; "
    "+http://www.google.com/bot.html)"
)

# ── 应用 ────────────────────────────────────────────────────────────────────
app = FastAPI(title="Chainke Prerender Service", version="1.0.0")

# ── LRU 缓存 ────────────────────────────────────────────────────────────────
class LRUCache:
    """线程安全的 LRU 缓存 (用于生产环境中缓存已渲染的页面)"""

    def __init__(self, capacity: int):
        self._cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._capacity = capacity

    def get(self, key: str) -> Optional[str]:
        if key not in self._cache:
            return None
        # 移到末尾 (最近使用)
        timestamp, html = self._cache.pop(key)
        self._cache[key] = (timestamp, html)
        logger.debug("Cache HIT: %s", key[:80])
        return html

    def put(self, key: str, html: str, ttl: int = 300):
        """存入缓存, ttl=缓存有效秒数 (默认 5 分钟)"""
        if key in self._cache:
            self._cache.pop(key)
        elif len(self._cache) >= self._capacity:
            self._cache.popitem(last=False)  # 淘汰最久未使用的
        self._cache[key] = (time.time(), html)
        logger.debug("Cache PUT: %s (%d bytes)", key[:80], len(html))

    def is_expired(self, key: str, ttl: int = 300) -> bool:
        """检查缓存条目是否过期"""
        if key not in self._cache:
            return True
        timestamp, _ = self._cache[key]
        return (time.time() - timestamp) > ttl

    @property
    def size(self) -> int:
        return len(self._cache)

    def invalidate(self, key: str):
        """主动失效某个缓存条目"""
        self._cache.pop(key, None)

    def clear(self):
        """清空所有缓存"""
        self._cache.clear()


# 全局缓存实例
cache = LRUCache(CACHE_SIZE)

# 全局浏览器实例
_browser = None


# ── 浏览器生命周期 ──────────────────────────────────────────────────────────
async def get_browser():
    """获取 (或创建) 全局 Puppeteer 浏览器实例"""
    global _browser
    if _browser is not None and _browser.isConnected:
        return _browser

    try:
        from pyppeteer import launch

        launch_args = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-sync",
                "--no-first-run",
            ],
            "ignoreHTTPSErrors": True,
        }

        if BROWSER_WS:
            # 连接到远程浏览器实例 (如 Docker 中的 browserless/chromium)
            from pyppeteer import connect

            logger.info("连接到远程浏览器: %s", BROWSER_WS)
            _browser = await connect(browserWSEndpoint=BROWSER_WS)
        else:
            logger.info("启动本地 Chromium 浏览器...")
            _browser = await launch(**launch_args)

        logger.info("✅ 浏览器已就绪")
        return _browser
    except ImportError:
        logger.error(
            "pyppeteer 未安装. 请执行: pip install pyppeteer"
        )
        raise
    except Exception as e:
        logger.error("❌ 浏览器启动失败: %s", e)
        raise


async def close_browser():
    """优雅关闭浏览器"""
    global _browser
    if _browser is not None:
        try:
            await _browser.close()
            logger.info("浏览器已关闭")
        except Exception as e:
            logger.warning("关闭浏览器时出错: %s", e)
        finally:
            _browser = None


# ── 页面渲染核心逻辑 ──────────────────────────────────────────────────────
def _generate_cache_key(url: str, user_agent: str = "") -> str:
    """生成缓存键 (URL + UA 关键部分)"""
    # 仅取 UA 的前 50 字符避免键过长
    ua_suffix = user_agent[:50] if user_agent else BOT_UA[:50]
    return f"{url}|{ua_suffix}"


async def render_page(url: str, user_agent: str = "") -> str:
    """
    使用 Puppeteer 渲染指定 URL, 返回完整 HTML

    Args:
        url: 要渲染的页面 URL (完整 URL, 含协议和域名)
        user_agent: 使用的 User-Agent (空则使用 Googlebot)

    Returns:
        渲染后的完整 HTML 字符串

    Raises:
        HTTPException: 渲染失败时抛出
    """
    # 参数验证
    if not url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail=f"无效的 URL: {url} (必须包含 http:// 或 https://)",
        )

    # 检查缓存
    cache_key = _generate_cache_key(url, user_agent)
    if not cache.is_expired(cache_key):
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    browser = await get_browser()
    page = await browser.newPage()

    try:
        # 设置 User-Agent
        ua = user_agent if user_agent else BOT_UA
        await page.setUserAgent(ua)

        # 设置视口 (桌面端)
        await page.setViewport({"width": 1280, "height": 720})

        # 导航到目标 URL
        logger.info("🌐 渲染: %s", url)
        await page.goto(
            url,
            {
                "waitUntil": "networkidle0",
                "timeout": RENDER_TIMEOUT * 1000,
            },
        )

        # 额外等待动态内容完成
        await asyncio.sleep(1)

        # 额外等待: 确保 React 水合完成
        try:
            await page.waitForFunction(
                "document.querySelector('#root')?.childElementCount > 0",
                {"timeout": 5000},
            )
        except Exception:
            logger.debug("页面可能未完全水合: %s", url)

        # 获取渲染后的 HTML
        html = await page.content()
        logger.info(
            "✅ 渲染完成: %s (%d bytes)",
            url,
            len(html),
        )

        # 写入缓存
        cache.put(cache_key, html)
        return html

    except Exception as e:
        error_msg = f"渲染失败 [{url}]: {e}"
        logger.error(error_msg)
        raise HTTPException(status_code=502, detail=error_msg)
    finally:
        await page.close()


# ── FastAPI 端点 ──────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    """应用启动时初始化浏览器"""
    logger.info("=" * 60)
    logger.info("  链客宝 — Puppeteer 动态预渲染服务")
    logger.info("=" * 60)
    logger.info("缓存容量: %d 条目", CACHE_SIZE)
    logger.info("渲染超时: %d 秒", RENDER_TIMEOUT)
    try:
        await get_browser()
    except Exception as e:
        logger.warning(
            "浏览器初始化失败 (服务仍可接受请求): %s", e
        )


@app.on_event("shutdown")
async def shutdown():
    """应用关闭时释放资源"""
    await close_browser()
    cache.clear()
    logger.info("服务已关闭, 资源已释放")


@app.get("/health", include_in_schema=False)
async def health():
    """健康检查端点"""
    browser_ok = _browser is not None and _browser.isConnected
    return {
        "status": "ok" if browser_ok else "degraded",
        "browser": "connected" if browser_ok else "disconnected",
        "cache_size": cache.size,
        "cache_capacity": CACHE_SIZE,
    }


@app.get("/render", response_class=HTMLResponse)
async def render(
    url: str = Query(..., description="要渲染的页面完整 URL"),
    ua: str = Query("", description="模拟的 User-Agent (留空使用 Googlebot)"),
    no_cache: bool = Query(False, description="跳过缓存, 强制重新渲染"),
):
    """
    渲染指定 URL 并返回完整 HTML

    参数:
        url: 要渲染的页面完整 URL (如 https://liankebao.top/about)
        ua: 模拟的 User-Agent (默认 Googlebot)
        no_cache: 设为 true 可跳过缓存强制重新渲染
    """
    if no_cache:
        cache_key = _generate_cache_key(url, ua)
        cache.invalidate(cache_key)

    html = await render_page(url, ua)
    return HTMLResponse(content=html)


@app.get("/cache/status", include_in_schema=False)
async def cache_status():
    """查看缓存状态"""
    return {
        "size": cache.size,
        "capacity": CACHE_SIZE,
        "keys": list(cache._cache.keys()) if hasattr(cache, "_cache") else [],
    }


@app.post("/cache/clear", include_in_schema=False)
async def cache_clear():
    """清空渲染缓存"""
    cache.clear()
    return {"status": "ok", "message": "缓存已清空"}


# ── 直接运行 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    logger.info("启动预渲染服务: %s:%d", HOST, PORT)
    uvicorn.run(
        "prerender_server:app",
        host=HOST,
        port=PORT,
        log_level=LOG_LEVEL.lower(),
        reload=False,
    )
