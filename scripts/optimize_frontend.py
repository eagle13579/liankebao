"""
链客宝 首屏性能优化配置
1. 关键CSS内联 (Critical CSS)
2. 骨架屏增强版
3. 资源预加载
"""
import os

# 关键CSS (首屏渲染所需的最小样式)
CRITICAL_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f8f9fa;color:#333}
.skeleton-header{height:64px;background:linear-gradient(90deg,#e8e8e8 25%,#f5f5f5 50%,#e8e8e8 75%);background-size:200% 100%;animation:shimmer 1.5s infinite}
.skeleton-hero{height:420px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);display:flex;align-items:center;justify-content:center;padding:0 20px}
.skeleton-hero h1{color:#fff;font-size:2.2rem;margin-bottom:12px;font-weight:700}
.skeleton-hero p{color:rgba(255,255,255,.85);font-size:1.1rem;max-width:600px}
.skeleton-content{max-width:1200px;margin:0 auto;padding:32px 20px}
.skeleton-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:24px}
.skeleton-card{height:200px;background:#fff;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.08);overflow:hidden}
.skeleton-card-bar{height:24px;background:linear-gradient(90deg,#eee 25%,#f5f5f5 50%,#eee 75%);background-size:200% 100%;animation:shimmer 1.5s infinite;margin:16px;border-radius:4px}
.skeleton-card-bar:nth-child(2){width:70%}
.skeleton-card-bar:nth-child(3){width:50%}
@keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
@media(max-width:768px){.skeleton-hero h1{font-size:1.6rem}.skeleton-grid{grid-template-columns:1fr}}
"""

# 预加载资源清单
PRELOAD_TAGS = """
<link rel="preconnect" href="https://api.liankebao.top" />
<link rel="dns-prefetch" href="https://api.liankebao.top" />
"""


def generate_optimized_html():
    """生成优化后的index.html骨架"""
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0" />
  <title>链客宝 - AI企业智能匹配平台</title>
  <meta name="description" content="链客宝是AI驱动的企业智能匹配平台，基于三塔DNN和知识图谱技术，为企业提供精准的供需匹配、信任评估和商业合作服务。" />
  <style>{CRITICAL_CSS}</style>
  {PRELOAD_TAGS}
  <link rel="modulepreload" href="/assets/index.js" />
</head>
<body>
  <div id="root">
    <div class="skeleton-header"></div>
    <div class="skeleton-hero">
      <div style="text-align:center">
        <h1>链客宝</h1>
        <p>AI驱动的企业智能匹配平台</p>
      </div>
    </div>
    <div class="skeleton-content">
      <div class="skeleton-grid">
        <div class="skeleton-card"><div class="skeleton-card-bar"></div><div class="skeleton-card-bar"></div><div class="skeleton-card-bar"></div></div>
        <div class="skeleton-card"><div class="skeleton-card-bar"></div><div class="skeleton-card-bar"></div><div class="skeleton-card-bar"></div></div>
        <div class="skeleton-card"><div class="skeleton-card-bar"></div><div class="skeleton-card-bar"></div><div class="skeleton-card-bar"></div></div>
      </div>
    </div>
  </div>
  <script type="module" src="/assets/index.js"></script>
</body>
</html>"""
    
    output_path = os.path.join(os.path.dirname(__file__), "..", "public", "index.html")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"优化后index.html已生成: {output_path}")
    print(f"大小: {len(html):,} bytes (关键CSS: {len(CRITICAL_CSS):,} bytes)")


if __name__ == "__main__":
    generate_optimized_html()
