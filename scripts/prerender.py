"""
链客宝轻量级预渲染脚本
在构建后生成关键页面的静态HTML副本，供爬虫和首屏加载使用
"""
import os
import subprocess
import sys

DIST_DIR = os.path.join(os.path.dirname(__file__), "..", "dist")
PRERENDER_DIR = os.path.join(DIST_DIR, "prerendered")

# 需要预渲染的关键页面
PRERENDER_PAGES = [
    {"route": "/", "file": "index.html", "priority": 1.0},
    {"route": "/login", "file": "login/index.html", "priority": 0.6},
    {"route": "/business-card", "file": "business-card/index.html", "priority": 0.8},
    {"route": "/trust", "file": "trust/index.html", "priority": 0.7},
    {"route": "/pricing", "file": "pricing/index.html", "priority": 0.8},
    {"route": "/about", "file": "about/index.html", "priority": 0.5},
]

PRERENDER_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <meta name="description" content="{description}" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:type" content="website" />
  <meta property="og:url" content="https://liankebao.top{route}" />
  <meta name="robots" content="index, follow" />
  <link rel="canonical" href="https://liankebao.top{route}" />
  <style>
    /* Skeleton screen styles */
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 0; background: #f5f5f5; color: #333; }}
    .skeleton-header {{ height: 64px; background: linear-gradient(90deg, #e0e0e0 25%, #f0f0f0 50%, #e0e0e0 75%); background-size: 200% 100%; animation: shimmer 1.5s infinite; }}
    .skeleton-hero {{ height: 400px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); display: flex; align-items: center; justify-content: center; color: white; }}
    .skeleton-hero h1 {{ font-size: 2.5rem; margin: 0; }}
    .skeleton-hero p {{ font-size: 1.2rem; opacity: 0.9; }}
    .skeleton-content {{ max-width: 1200px; margin: 0 auto; padding: 40px 20px; }}
    .skeleton-card {{ height: 200px; background: white; border-radius: 12px; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
    @keyframes shimmer {{ 0% {{ background-position: -200% 0; }} 100% {{ background-position: 200% 0; }} }}
  </style>
</head>
<body>
  <div id="root">
    <div class="skeleton-header"></div>
    <div class="skeleton-hero">
      <div style="text-align:center">
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
    </div>
    <div class="skeleton-content">
      <div class="skeleton-card"></div>
      <div class="skeleton-card"></div>
      <div class="skeleton-card"></div>
    </div>
  </div>
</body>
</html>"""

PAGE_META = {
    "/": {"title": "链客宝 - AI企业智能匹配平台", "description": "AI驱动的企业智能匹配平台，基于三塔DNN和知识图谱技术，为企业提供精准的供需匹配"},
    "/login": {"title": "登录 - 链客宝", "description": "登录链客宝账号，开始您的智能匹配之旅"},
    "/business-card": {"title": "数字名片 - 链客宝", "description": "创建和管理您的企业数字名片，让商业机会找到您"},
    "/trust": {"title": "信任评估 - 链客宝", "description": "基于三维信任评分体系，了解潜在合作伙伴的可信度"},
    "/pricing": {"title": "定价 - 链客宝", "description": "查看链客宝的定价方案，选择最适合您企业的计划"},
    "/about": {"title": "关于我们 - 链客宝", "description": "了解链客宝的使命、团队和核心技术"},
}


def prerender():
    """生成预渲染HTML"""
    os.makedirs(PRERENDER_DIR, exist_ok=True)
    
    for page in PRERENDER_PAGES:
        route = page["route"]
        file_path = os.path.join(PRERENDER_DIR, page["file"])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        meta = PAGE_META.get(route, {"title": "链客宝", "description": "AI企业智能匹配平台"})
        html = PRERENDER_HTML_TEMPLATE.format(
            route=route,
            title=meta["title"],
            description=meta["description"]
        )
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)
        
        size = os.path.getsize(file_path)
        print(f"  ✅ {route} → {file_path} ({size:,} bytes)")
    
    print(f"\n预渲染完成: {len(PRERENDER_PAGES)} pages → {PRERENDER_DIR}")


def install_nginx_prerender_config():
    """生成nginx预渲染配置片段"""
    config = """# ======================
# 链客宝 预渲染配置
# ======================
# 对爬虫返回预渲染HTML, 对普通用户返回正常SPA

map $http_user_agent $is_bot {
    default 0;
    ~*googlebot|bingbot|baiduspider|yandexbot|facebookexternalhit|twitterbot|rogerbot|linkedinbot|embedly|quora|pinterest|slack|vkshare|w3c_validator|whatsapp|applebot|semrushbot|ahrefsbot|dotbot 1;
    ~*mj12bot|exabot|screaming|grapeshot|ia_archiver|curl|python-requests|wget 1;
}

location /prerendered/ {
    internal;
    alias /app/frontend/prerendered/;
}

# 针对爬虫的预渲染路由
location / {
    try_files $uri $uri/ /index.html;

    # 如果检测到爬虫, 返回预渲染版本
    if ($is_bot) {
        rewrite ^/(.*)$ /prerendered/$1/index.html break;
    }
}
"""
    config_path = os.path.join(os.path.dirname(__file__), "..", "deploy", "nginx", "prerender.conf")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config)
    print(f"nginx预渲染配置已创建: {config_path}")


if __name__ == "__main__":
    print("=" * 50)
    print("链客宝 轻量级预渲染生成器")
    print("=" * 50)
    prerender()
    install_nginx_prerender_config()
    print("\n请在docker-compose或nginx中include prerender.conf")
