"""
链客宝统一API网关 v4
======================
统一路由：链客宝前端(:5133) → 3个后端服务

路由表：
  /lkapi/*              → 链客宝后端  :8001   (strip /lkapi → /api)
  /api/brochure/*       → AI数字名片  :8003   (直通)
  /api/tag/*            → AI数字名片  :8003   (直通)
  /api/match/*          → AI数字名片  :8003   (直通)
  /api/external/*       → AI数字名片  :8003   (直通)
  /api/digital-brochure/auth/* → AI数字名片 :8003 (重写 /api/digital-brochure/auth → /api/auth)
  /api/geo/diagnose     → GEO诊断     :5061   (直通 /api/diagnose)
  /api/geo/diagnosis/report/* → GEO诊断 :5061  (直通 /api/report/*)
  /api/geo/positioning  → GEO定位     :5062   (直通 /api/position/*)
  /api/geo/content-plan → GEO内容     :5063   (直通 /api/content-plan/*)
  /*                    → 链客宝前端静态文件

网页端访问 :5133，小程序通过 /lkapi/ 调用链客宝后端API，
通过其余 `/api/` 路径调用数字名片和GEO。
"""

import http.server
import urllib.request
import os
import json
import socketserver

from functools import wraps

JWT_SECRET = os.environ.get("JWT_SECRET", "")

ALLOWED_EXTERNAL_HOSTS = {
    "api.deepseek.com",
    "api.weixin.qq.com",
    "openapi.alipay.com",
    "127.0.0.1",
    "localhost",
}


def isAllowedExternalUrl(url: str) -> bool:
    from urllib.parse import urlparse

    try:
        host = urlparse(url).hostname
        return host in ALLOWED_EXTERNAL_HOSTS
    except:
        return False


def require_jwt(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {"error": "Missing or invalid Authorization header"}
                ).encode()
            )
            return
        return func(self, *args, **kwargs)

    return wrapper


# ── 配置 ──────────────────────────────────────────────────
DIST = r"D:\向海容的知识库\wiki\wiki\记忆宫殿\L5孵化室\产品开发\战略合作\链客宝\linkbao\frontend\dist"
BROCHURE_H5 = r"D:\向海容的知识库\wiki\wiki\记忆宫殿\L5孵化室\产品开发\AI数字名片\code\frontend\h5"
PORT = 5136

ROUTES = [
    # (前缀, 目标基础URL, 路径重写函数或None)
    ("/lkapi/", "http://localhost:8000", lambda p: p[6:]),
    ("/lkapi", "http://localhost:8000", lambda p: p[5:] if len(p) > 5 else "/"),
    (
        "/api/orders",
        "http://localhost:8000",
        lambda p: "/api/orders" + ("?" + p.split("?")[1] if "?" in p else ""),
    ),
    ("/api/orders/", "http://localhost:8000", None),
    (
        "/api/brochures/",
        "http://localhost:8003",
        lambda p: "/api/brochure/" + p.split("/api/brochures/", 1)[1],
    ),
    ("/api/brochure/", "http://localhost:8003", None),
    ("/api/tag/", "http://localhost:8003", None),
    # 修复: /api/matching/* → 主匹配引擎(8001)，/api/match/* → 数字名片(8003)
    ("/api/matching/", "http://localhost:8001", None),
    ("/api/match/", "http://localhost:8003", None),
    ("/api/external/", "http://localhost:8003", None),
    (
        "/api/digital-brochure/auth/",
        "http://localhost:8003",
        lambda p: "/api/auth/" + p.split("/api/digital-brochure/auth/", 1)[1],
    ),
    ("/api/geo/diagnose", "http://localhost:5061", lambda p: "/api/diagnose"),
    (
        "/api/geo/diagnosis/",
        "http://localhost:5061",
        lambda p: "/" + p.split("/api/geo/diagnosis/", 1)[1],
    ),
    (
        "/api/geo/positioning/",
        "http://localhost:5062",
        lambda p: "/" + p.split("/api/geo/positioning/", 1)[1],
    ),
    (
        "/api/geo/content/",
        "http://localhost:5063",
        lambda p: "/" + p.split("/api/geo/content/", 1)[1],
    ),
    ("/geo-diagnosis", "http://localhost:5061", lambda p: "/"),
    ("/geo-diagnosis/", "http://localhost:5061", lambda p: "/"),
    (
        "/tianji",
        "http://localhost:5070",
        lambda p: "/" + p.split("/tianji", 1)[1].lstrip("/")
        if len(p) > len("/tianji")
        else "/",
    ),
    (
        "/tianji/",
        "http://localhost:5070",
        lambda p: "/" + p.split("/tianji/", 1)[1].lstrip("/")
        if len(p) > len("/tianji/")
        else "/",
    ),
    ("/health", "http://localhost:8000", lambda p: "/health"),
    # 会员体系 API → 链客宝后端
    ("/api/v1/membership/", "http://localhost:8000", None),
    ("/api/v1/membership", "http://localhost:8000", lambda p: "/api/v1/membership"),
]


def _match_route(path: str):
    """找到匹配的路由，返回 (target_url, is_api)"""
    for prefix, base_url, rewriter in ROUTES:
        if path.startswith(prefix):
            if rewriter:
                backend_path = rewriter(path)
            else:
                backend_path = path
            return f"{base_url}{backend_path}", True
    return None, False


class GatewayHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIST, **kw)

    def _proxy(self, method, target_url):
        try:
            body = None
            content_length = self.headers.get("content-length")
            if content_length and int(content_length) > 0:
                body = self.rfile.read(int(content_length))

            req = urllib.request.Request(
                target_url, data=body, headers=dict(self.headers), method=method
            )
            resp = urllib.request.urlopen(req, timeout=15)
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                kl = k.lower()
                if kl not in (
                    "transfer-encoding",
                    "content-encoding",
                    "content-length",
                    "connection",
                    "server",
                    "date",
                ):
                    self.send_header(k, v)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for k, v in e.headers.items():
                kl = k.lower()
                if kl not in (
                    "transfer-encoding",
                    "content-encoding",
                    "content-length",
                ):
                    self.send_header(k, v)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _serve_static(self, path: str):
        """提供静态文件（自动判断 MIME type）"""
        # 安全检查：防止目录穿越
        clean_path = path.split("?")[0]
        file_path = os.path.normpath(
            os.path.join(self.directory, clean_path.lstrip("/"))
        )
        if not file_path.startswith(os.path.normpath(self.directory)):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden")
            return False
        if not os.path.isfile(file_path):
            return False
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".html": "text/html; charset=utf-8",
            ".htm": "text/html; charset=utf-8",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".ttf": "font/ttf",
            ".eot": "application/vnd.ms-fontobject",
            ".wasm": "application/wasm",
            ".txt": "text/plain; charset=utf-8",
            ".map": "application/json",
            ".webp": "image/webp",
            ".avif": "image/avif",
            ".mjs": "application/javascript; charset=utf-8",
        }
        content_type = mime_map.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        # 静态文件强缓存：JS/CSS/字体/图片缓存1年
        if ext in (
            ".js",
            ".css",
            ".woff",
            ".woff2",
            ".ttf",
            ".eot",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".svg",
            ".ico",
            ".webp",
            ".avif",
            ".wasm",
        ):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())
        return True

    def _handle(self, method):
        full_path = self.path
        path = full_path.split("?")[0]  # 路径部分
        qs = full_path.split("?", 1)[1] if "?" in full_path else ""  # 查询参数
        # 调试日志
        with open(r"D:\chainke_gw_debug.log", "a") as df:
            df.write(f"PATH: method={method} path={path} full={full_path} qs={qs}\n")

        # AI数字名片 H5 静态文件
        if path.startswith("/digital-brochure/"):
            relative = path[len("/digital-brochure/") :]
            if relative == "" or relative == "/":
                relative = "index.html"
            # 安全检查：禁止跳出目录
            file_path = os.path.normpath(os.path.join(BROCHURE_H5, relative))
            if not file_path.startswith(os.path.normpath(BROCHURE_H5)):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden")
                return
            if os.path.isfile(file_path):
                self.send_response(200)
                # 根据扩展名设置 Content-Type
                ext = os.path.splitext(file_path)[1].lower()
                content_type = {
                    ".html": "text/html; charset=utf-8",
                    ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".json": "application/json",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".gif": "image/gif",
                    ".svg": "image/svg+xml",
                    ".ico": "image/x-icon",
                }.get(ext, "application/octet-stream")
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                # 缓存策略：JS/CSS/图片/字体强缓存1年，HTML缓存1小时
                cache_exts = {
                    ".js",
                    ".css",
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".svg",
                    ".ico",
                }
                if ext in cache_exts:
                    self.send_header(
                        "Cache-Control", "public, max-age=31536000, immutable"
                    )
                else:
                    self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"File not found")
            return

        target_url, is_api = _match_route(path)
        if is_api:
            # 保留查询参数
            if qs:
                target_url += "?" + qs
            print(f"  → {method} {full_path} → {target_url}")
            with open(r"D:\chainke_gw_debug.log", "a") as df:
                df.write(f"PROXY: {method} → {target_url}\n")
            self._proxy(method, target_url)
        elif path.startswith("/api/"):
            # 未匹配的 /api/* 路径默认走链客宝后端
            target = f"http://localhost:8000{path}"
            if qs:
                target += "?" + qs
            print(f"  → {method} {full_path} → {target} (默认)")
            with open(r"D:\chainke_gw_debug.log", "a") as df:
                df.write(f"PROXY-DEF: {method} → {target}\n")
            self._proxy(method, target)
        elif method == "GET":
            # 直接提供静态文件
            served = self._serve_static(self.path)
            if served:
                return
            # SPA fallback
            try:
                index_path = os.path.join(self.directory, "index.html")
                with open(index_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(f"Not found: {e}".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        """CORS preflight"""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"
        )
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    def log_message(self, *a):
        pass


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """多线程HTTP服务器 — 解决单线程同步阻塞问题"""

    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    print(f"🚀 链客宝统一API网关 :{PORT} (多线程)")
    print(f"   📦 静态文件: {DIST}")
    print("   🔗 链客宝  → :8001")
    print("   🔗 数字名片 → :8003")
    print("   🔗 GEO诊断  → :5061")
    print("   🔗 GEO定位  → :5062")
    print("   🔗 GEO内容  → :5063")
    print("   🔗 天机预测 → :5070")
    print("   ⚡ 线程池: ThreadingMixIn (自动扩展)")
    ThreadedHTTPServer(("0.0.0.0", PORT), GatewayHandler).serve_forever()
