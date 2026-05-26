# 链客宝小程序 API 路由修复方案

---

## 1. 问题概述

### 1.1 现状

| 项目 | 当前值 | 状态 |
|---|---|---|
| 小程序 API_BASE | `https://www.go-aiport.com/lkapi` | 硬编码 |
| go-aiport.com Nginx | 无 `/lkapi/` location | 返回 404 |
| 后端 FastAPI | `localhost:8001` | 正常运行 |
| 链客宝 Nginx | 绑定了 `liankebao.top`，API 路由为 `/api/` | DNS 未解析，不可用 |

### 1.2 根因

- 微信小程序 `api.js` 中 API 基础地址写死为 `https://www.go-aiport.com/lkapi`
- 域名 `go-aiport.com` 的 Nginx 配置中没有为 `/lkapi/` 配置反向代理
- 链客宝专属域名 `liankebao.top` DNS 未指向阿里云 ECS（47.100.160.250），因此链客宝原有的 Nginx 配置虽然正确但 **无法生效**
- 后端 FastAPI 实际运行在 `127.0.0.1:8001`，API 端点以 `/api/` 为前缀

---

## 2. 修复方案（推荐：选项 C + A 混合）

**策略：改动最小原则** —— 不改小程序代码（减少发版审批），仅在 Nginx 层面修复。

### 2.1 方案对比

| 方案 | 操作 | 优点 | 缺点 |
|---|---|---|---|
| **A** | go-aiport.com Nginx 增加 `/lkapi/ → localhost:8001` | 不改小程序 | 路径前缀不匹配（小程序的 `/lkapi` → 后端 `/api`） |
| **B** | liankebao.top 配 DNS + 上线 | 架构规范 | DNS 生效慢，流程长 |
| **C** | 改小程序 API_BASE + go-aiport.com 加路由 | 路径一致 | 需小程序重新发版 |
| **A+ 路径重写** | go-aiport.com 加路由 + 路径 rewrite | 不改代码 + 路径正确 | 推荐 |

### 2.2 推荐方案：选项 A + 路径重写

在 `go-aiport.com` 的 Nginx 配置中新增 `/lkapi/` location 块，并将路径前缀 `/lkapi` 重写为 `/api`（与后端一致）：

```
客户端请求:  https://www.go-aiport.com/lkapi/user/login
                                │
                         Nginx 接收
                                │
                   location /lkapi/ 匹配
                                │
                   rewrite ^/lkapi(/.*)$ $1 break;
                                │
                   路径变为: /api/user/login
                                │
                   proxy_pass http://127.0.0.1:8001;
                                │
                         FastAPI (8001)
                         处理 /api/user/login
```

这样：
- **小程序代码不需修改** —— 现有 `https://www.go-aiport.com/lkapi` 继续可用
- **后端不需调整** —— 后端仍用 `/api/` 前缀
- **一次性修复** —— 仅改 Nginx 配置

---

## 3. SSH 操作步骤

### 3.1 登录阿里云 ECS

```bash
ssh root@47.100.160.250
```

### 3.2 确认后端运行正常

```bash
curl -s http://127.0.0.1:8001/api/health
# 或
curl -s http://127.0.0.1:8001/docs -o /dev/null -w "%{http_code}"
```

预期返回 `200` 或 JSON 健康检查响应。

### 3.3 查找 go-aiport.com 的 Nginx 配置

常见位置：

```bash
# Debian/Ubuntu 默认
ls /etc/nginx/sites-enabled/
ls /etc/nginx/conf.d/

# 或显式查找
grep -r "go-aiport.com" /etc/nginx/ 2>/dev/null
grep -r "server_name.*go-aiport" /etc/nginx/ 2>/dev/null
```

### 3.4 备份原配置

```bash
# 假设找到配置为 /etc/nginx/sites-enabled/go-aiport.com
cp /etc/nginx/sites-enabled/go-aiport.com /etc/nginx/sites-enabled/go-aiport.com.bak.$(date +%Y%m%d)
```

### 3.5 在 server 块内插入 /lkapi/ location

```bash
# 使用 sed 在 server 块末尾（最后一个 } 前）插入
sed -i '/^}$/i\
\
    location /lkapi/ {\
        rewrite ^/lkapi(/.*)$ $1 break;\
        proxy_pass http://127.0.0.1:8001;\
        proxy_set_header Host $host;\
        proxy_set_header X-Real-IP $remote_addr;\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\
        proxy_set_header X-Forwarded-Proto $scheme;\
    }' /etc/nginx/sites-enabled/go-aiport.com
```

> **注意**：`sed` 插入位置取决于配置结构。如果 `server` 块不是以单行 `}` 结尾，建议手动编辑或用下方指令逐行插入。

### 3.6 手动编辑（推荐，更安全）

```bash
vim /etc/nginx/sites-enabled/go-aiport.com
```

在 `server` 块内部（建议放在 `location /` 或其他 location 块之后，最后一个 `}` 之前）粘贴：

```nginx
    location /lkapi/ {
        rewrite ^/lkapi(/.*)$ $1 break;
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
```

### 3.7 测试 Nginx 配置

```bash
nginx -t
```

预期输出：

```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### 3.8 重载 Nginx

```bash
nginx -s reload
# 或
systemctl reload nginx
```

### 3.9 验证修复

```bash
# 模拟小程序 API 请求
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://www.go-aiport.com/lkapi/health

# 查看实际响应内容（如果有）
curl -s https://www.go-aiport.com/lkapi/health

# 测试一个真实 API 端点
curl -s https://www.go-aiport.com/lkapi/user/login
```

预期应返回 200（或后端应用的实际响应），**不再返回 404**。

---

## 4. 其他备选方案

### 4.1 方案 B：修复 liankebao.top DNS + 使用链客宝独立 Nginx

如果希望用独立域名访问，操作如下：

```bash
# 1. 在 DNS 服务商处添加 A 记录
#    liankebao.top → 47.100.160.250

# 2. 在 ECS 上验证 DNS
dig liankebao.top +short
# 预期: 47.100.160.250

# 3. 链客宝 Nginx 已配好（/opt/liankebao/deploy/nginx.conf），含：
#    location /api/ { proxy_pass http://127.0.0.1:8001/; }
#    但注意路径是 /api/ 而不是 /lkapi/

# 4. 也可在链客宝 Nginx 中增加 /lkapi/ 重写
#    参考 3.5 节相同配置

# 5. 申请 SSL 证书
certbot --nginx -d liankebao.top

# 6. 重载
nginx -s reload
```

### 4.2 方案 C：修改小程序 + go-aiport.com 直通

如果小程序可重新发版，将 `api.js` 中：

```javascript
// 修改前
const API_BASE = 'https://www.go-aiport.com/lkapi';

// 修改后
const API_BASE = 'https://www.go-aiport.com/api';
```

然后在 go-aiport.com Nginx 中增加：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8001;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

优点：路径透明，无需 rewrite。缺点：需小程序发版。

---

## 5. 回滚方案

若修复后出现问题，立即回滚：

```bash
# 如果有备份
cp /etc/nginx/sites-enabled/go-aiport.com.bak.20260516 /etc/nginx/sites-enabled/go-aiport.com
nginx -t && nginx -s reload
```

无备份则移除新增的 location 块后重载即可。

---

## 6. 总结

| 操作项 | 详情 |
|---|---|
| **推荐方案** | 选项 A + 路径重写（不改小程序） |
| **修改文件** | go-aiport.com 的 Nginx server 配置 |
| **新增内容** | `location /lkapi/` 块，重写路径 `/lkapi → /api` |
| **需修改配置的服务器** | 47.100.160.250 (go-aiport.com Nginx) |
| **无需修改** | 小程序代码、后端 FastAPI、链客宝 Nginx |
| **风险等级** | 低。仅新增 Nginx location，不影响现有路由 |
| **预计耗时** | 5-10 分钟 |
