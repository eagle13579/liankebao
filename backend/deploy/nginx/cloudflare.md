# =============================================================================
# 链客宝 — Cloudflare CDN 配置模板
# =============================================================================
# 本文件记录了 Cloudflare Dashboard 和 API 的推荐配置。
# 通过 Cloudflare Dashboard (dash.cloudflare.com) 或 API 应用。
# =============================================================================

# ═════════════════════════════════════════════════════════════════════════════
# 1. DNS 记录
# ═════════════════════════════════════════════════════════════════════════════
# 类型  名称            内容                    代理状态
# ────────────────────────────────────────────────────────────────────────────
# A     @               <服务器公网IP>          已代理 (Proxied - 橙色云朵)
# A     api             <服务器公网IP>          已代理 (Proxied - 橙色云朵)
# CNAME www             @                       已代理 (Proxied - 橙色云朵)

# ═════════════════════════════════════════════════════════════════════════════
# 2. SSL/TLS
# ═════════════════════════════════════════════════════════════════════════════
# 加密模式:        Full (Strict)  — 需要 Nginx 配置有效证书
# 最低 TLS 版本:   1.2
# Always Use HTTPS:      ON
# Automatic HTTPS Rewrites: ON
# SSL/TLS Recommender:   ON

# ═════════════════════════════════════════════════════════════════════════════
# 3. 缓存规则 (Cloudflare Cache Rules — 新引擎)
# ═════════════════════════════════════════════════════════════════════════════
# 规则 1: 静态资源 — 1 年缓存
#   Condition: URI 路径包含 .js 或 .css 或 .png 或 .jpg 或 .jpeg 或
#              .gif 或 .ico 或 .svg 或 .woff2 或 .woff 或 .ttf 或 .eot
#   Action:    Edge Cache TTL → 覆盖源站 → 31536000 秒 (1 年)
#   Browser Cache TTL → 覆盖源站 → 31536000 秒

# 规则 2: 上传文件 — 30 天缓存
#   Condition: URI 路径包含 /uploads/
#   Action:    Edge Cache TTL → 覆盖源站 → 2592000 秒 (30 天)
#   Browser Cache TTL → 覆盖源站 → 3600 秒 (1 小时)

# 规则 3: API 响应 — 不缓存
#   Condition: URI 路径包含 /api/
#   Action:    Cache Status → Bypass
#   Edge Cache TTL → 不覆盖 (尊重源站 Cache-Control)

# 规则 4: HTML — 不缓存
#   Condition: URI 路径包含 .html
#   Action:    Edge Cache TTL → 覆盖源站 → 0 秒 (不缓存)

# 规则 5: 健康检查 — 绕过缓存
#   Condition: URI 路径等于 /health
#   Action:    Cache Status → Bypass

# ═════════════════════════════════════════════════════════════════════════════
# 4. WAF (Web Application Firewall) 规则
# ═════════════════════════════════════════════════════════════════════════════
# 规则 1: API 速率限制
#   Description: API 端点 — 每分钟 300 请求
#   Field:       URI Path — Contains — /api/
#   Expression:  (http.request.uri.path contains "/api/")
#   Action:      Block
#   Rate Limit:  300 requests per 60 seconds
#   Mitigation Timeout: 600 秒 (10 分钟)

# 规则 2: 登录/Auth 速率限制
#   Description: 登录端点 — 每分钟 10 请求 (防暴力破解)
#   Field:       URI Path — Contains — /api/auth/login
#   Expression:  (http.request.uri.path contains "/api/auth/login") or
#                (http.request.uri.path contains "/api/auth/register")
#   Action:      Block
#   Rate Limit:  10 requests per 60 seconds
#   Mitigation Timeout: 1800 秒 (30 分钟)

# 规则 3: 屏蔽恶意机器人
#   Description: 屏蔽未经验证的机器人
#   Expression:  (cf.client.bot) and (not cf.bot_management.verified_bot)
#   Action:      Block

# 规则 4: 搜索引擎爬虫放行
#   Description: 允许已验证爬虫访问 SEO 文件
#   Expression:  (cf.bot_management.verified_bot) and
#                (http.request.uri.path eq "/robots.txt" or
#                 http.request.uri.path eq "/sitemap.xml")
#   Action:      Skip

# 规则 5: Cloudflare 托管规则集 (安全)
#   Description: SQL 注入、XSS 等通用防护
#   Expression:  true
#   Action:      Execute (Cloudflare Managed Ruleset)
#   Paranoia Level: Medium (推荐生产)

# ═════════════════════════════════════════════════════════════════════════════
# 5. 页面规则 (Page Rules) — 旧引擎 (兼容配置)
# ═════════════════════════════════════════════════════════════════════════════
# Cloudflare 正逐步迁移 Page Rules 到缓存规则 / 规则集引擎
# 以下是推荐的 Page Rules 配置 (如仍在使用旧引擎):

# 规则 1:
#   URL:          *liankebao.top/*
#   Setting:      Always Use HTTPS → ON
#
# 规则 2:
#   URL:          *liankebao.top/sitemap.xml
#   Setting:      Cache Level → Cache Everything
#   Setting:      Edge Cache TTL → 1 day
#
# 规则 3:
#   URL:          *liankebao.top/api/*
#   Setting:      Cache Level → Bypass
#
# 规则 4:
#   URL:          *liankebao.top/*.js
#   Setting:      Cache Level → Cache Everything
#   Setting:      Edge Cache TTL → 1 year

# ═════════════════════════════════════════════════════════════════════════════
# 6. 性能优化
# ═════════════════════════════════════════════════════════════════════════════
# Auto Minify:       JavaScript ON, CSS ON, HTML ON
# Brotli:            ON
# Early Hints:       ON
# HTTP/2:            ON
# HTTP/3 (QUIC):     ON
# 0-RTT Connection:  ON
# Rocket Loader:     OFF (可能破坏 SPA 功能)
# Mirage:            OFF
# Polish:            ON (lossless — 无损图片优化)
# WebP:              ON
# IP Geolocation:    ON (后端可读取 CF-IPCountry 头)

# ═════════════════════════════════════════════════════════════════════════════
# 7. 安全优化
# ═════════════════════════════════════════════════════════════════════════════
# Bot Fight Mode:       ON
# Browser Integrity Check: ON
# Challenge Passage:    30 分钟
# Security Level:       High
# WAF:                  ON
# Email Obfuscation:    OFF (API 场景不需要)
# Hotlink Protection:   OFF (API 和 SPA 需要跨域资源)
# Server-Side Excludes: ON
# Privacy Pass:         ON

# ═════════════════════════════════════════════════════════════════════════════
# 8. 网络
# ═════════════════════════════════════════════════════════════════════════════
# WebSocket:           ON (用于实时通信)
# gRPC:                ON (如果使用 gRPC)
# HTTP/2 Origin:       ON
# Argo Smart Routing:  ON (推荐，减少延迟)
# Tiered Cache:        ON (减少源站负载)
# Proxy Read Timeout:  120 秒
# Proxy Connect Timeout: 30 秒
# Max Upload Size:     100 MB

# ═════════════════════════════════════════════════════════════════════════════
# 9. Cloudflare Workers 推荐
# ═════════════════════════════════════════════════════════════════════════════
# Worker 1: JWT 边缘验证
#   - 在 Cloudflare 边缘验证 JWT 令牌
#   - 减少后端无效请求
#   - 适用于 /api/ 路径
#
# Worker 2: 地域路由
#   - 根据用户 CF-IPCountry 头路由到最近区域
#   - 适用于多区域部署
#
# Worker 3: A/B 测试分流
#   - 根据 Cookie/Header 路由到不同版本
#   - 与灰度发布配合
