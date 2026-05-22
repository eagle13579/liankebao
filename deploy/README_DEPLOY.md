# 链客宝 部署说明文档

## 项目信息

- 项目名称: 链客宝 (LianKeBao)
- 域名: liankebao.top / www.liankebao.top
- 服务器: 阿里云 ECS (47.100.160.250)
- 前端: Vite + React (SPA)
- 后端: FastAPI + Uvicorn (Python 3.12, port 8000)
- 数据库: SQLite (本地文件)
- Web 服务器: Nginx (反向代理 + SSL)

## 目录结构 (服务器端)

```
/opt/liankebao/
├── dist/                    # 前端构建产物（静态文件）
├── backend/                 # 后端代码
│   ├── app/                 # FastAPI 应用
│   ├── data/                # SQLite 数据库
│   ├── venv/                # Python 虚拟环境
│   └── requirements.txt     # Python 依赖
├── deploy/                  # 部署脚本
├── logs/                    # 日志目录
│   ├── backend.log          # 后端运行时日志
│   └── backend-error.log    # 后端错误日志
├── deploy.sh                # 一键部署脚本
├── nginx.conf               # Nginx 配置文件
└── chainke.service          # Systemd 服务配置
```

## 部署方式

### 方式一：一键部署（本地服务器）

```bash
# 完整部署（前端构建 + 后端部署 + Nginx配置）
sudo bash /opt/liankebao/deploy.sh

# 仅重启服务
sudo bash /opt/liankebao/deploy.sh --restart-only

# 跳过前端构建
sudo bash /opt/liankebao/deploy.sh --skip-frontend
```

### 方式二：GitHub Actions CI/CD（推荐）

每次 push 到 `main` 分支后自动触发部署。

配置 GitHub Secrets:
- `HOST`: 服务器 IP (47.100.160.250)
- `USERNAME`: SSH 用户名
- `SSH_KEY`: SSH 私钥
- `DEPLOY_PATH`: 部署路径 (/opt/liankebao)

### 方式三：手动部署

```bash
# 1. 本地构建前端
npm ci && npm run build

# 2. 上传到服务器
scp -r dist/ user@47.100.160.250:/opt/liankebao/dist/
scp backend/* user@47.100.160.250:/opt/liankebao/backend/

# 3. SSH 连上服务器执行
ssh user@47.100.160.250
sudo bash /opt/liankebao/deploy.sh --skip-frontend
```

## 服务管理

```bash
# 后端服务
sudo systemctl status chainke     # 查看状态
sudo systemctl restart chainke    # 重启
sudo journalctl -u chainke -n 100 # 查看日志

# Nginx
sudo systemctl status nginx       # 查看状态
sudo systemctl reload nginx       # 重载配置
sudo nginx -t                     # 测试配置
```

## SSL 证书管理

```bash
# 申请证书
sudo certbot --nginx -d liankebao.top -d www.liankebao.top

# 续期测试
sudo certbot renew --dry-run

# 手动续期
sudo certbot renew
sudo nginx -s reload
```

证书自动续期通过 systemd timer 或 cron 任务管理。

## 日志查看

```bash
# 后端日志
tail -f /opt/liankebao/logs/backend.log

# Nginx 访问日志
tail -f /var/log/nginx/access.log

# Nginx 错误日志
tail -f /var/log/nginx/error.log

# 部署日志
tail -f /opt/liankebao/logs/auto_deploy.log
```

## 回滚

```bash
# 如果使用 Git 部署，切换到上一版本
cd /opt/liankebao
git log --oneline -5
git checkout <previous-commit-hash>
bash deploy.sh
```

## Nginx 安全加固

### 安全配置说明

链客宝使用 `nginx_security.conf` 提供以下安全防护：

| 安全措施 | 配置值 | 说明 |
|---------|--------|------|
| **HSTS** | `max-age=31536000; includeSubDomains` | 强制 HTTPS，有效期 1 年，包含子域名 |
| **X-Frame-Options** | `DENY` | 禁止页面被嵌入 iframe，防点击劫持 |
| **X-Content-Type-Options** | `nosniff` | 禁止浏览器 MIME 类型嗅探 |
| **Content-Security-Policy** | `default-src 'self'` | 限制资源加载来源，防 XSS |
| **请求体限制** | `client_max_body_size 1M` | 限制请求体大小，防大请求攻击 |
| **SSL 协议** | TLSv1.2 / TLSv1.3  | 仅启用安全 TLS 版本 |
| **速率限制** | 10 请求/秒/IP | 基于 IP 的速率限制，防 CC 攻击 |
| **敏感文件禁止** | `.db .sqlite .env .git .pyc` | 禁止访问数据库文件和环境变量文件 |

### 部署安全配置

```bash
# 将安全配置复制到服务器
scp deploy/nginx_security.conf user@47.100.160.250:/tmp/

# SSH 登录服务器
ssh user@47.100.160.250

# 复制到 nginx 配置目录并启用
sudo cp /tmp/nginx_security.conf /etc/nginx/nginx_security.conf

# 在主配置中引入（在 http 块末尾添加一行）
# 编辑 /etc/nginx/nginx.conf，在 http 块添加：
# include /etc/nginx/nginx_security.conf;

# 测试并重载
sudo nginx -t && sudo nginx -s reload
```

### 验证安全头

```bash
# 使用 curl 检查安全响应头
curl -sI https://liankebao.top | grep -i -E "strict-transport-security|x-frame-options|x-content-type-options|content-security-policy"

# 在线测试（浏览器打开）
# https://securityheaders.com/?q=https://liankebao.top&followRedirects=on
```

## GitHub Actions CI/CD 配置

### GitHub Secrets 配置指南

在 GitHub 仓库设置中添加以下 Secrets（Settings → Secrets and variables → Actions）：

| Secret 名称 | 说明 | 示例值 |
|------------|------|--------|
| `HOST` | 服务器 IP 地址 | `47.100.160.250` |
| `USERNAME` | SSH 登录用户名 | `ubuntu` 或 `root` |
| `SSH_KEY` | SSH 私钥（完整内容） | `-----BEGIN OPENSSH PRIVATE KEY-----\n...` |
| `DEPLOY_PATH` | 服务器部署目录 | `/opt/liankebao` |

**生成 SSH 密钥对（如没有）：**

```bash
# 本地生成
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_deploy

# 将公钥添加到服务器的 ~/.ssh/authorized_keys
ssh-copy-id -i ~/.ssh/github_deploy.pub user@47.100.160.250

# 或手动添加
cat ~/.ssh/github_deploy.pub
# 将输出内容追加到服务器 ~/.ssh/authorized_keys

# 复制私钥内容添加到 GitHub Secrets
cat ~/.ssh/github_deploy
# 将完整内容（含 BEGIN 和 END 标记）添加到 SSH_KEY
```

### CI/CD 工作流程说明

工作流文件位于 `.github/workflows/deploy.yml`，触发方式：

1. **自动触发**：每次 push 到 `main` 分支
2. **手动触发**：GitHub Actions 页面点击 "Run workflow"

执行步骤：

1. Checkout 代码
2. 安装前端依赖并构建
3. 安装 Python 后端依赖
4. 运行 pytest 测试
5. 通过 SCP 上传构建产物到服务器
6. 通过 SSH 执行远程部署脚本
7. 验证部署状态（nginx 配置检查、健康检查）

## SSL 证书自动续期指南

### 方式一：Certbot 自动续期（推荐）

Certbot 安装后默认创建 systemd timer，每天检查两次证书有效期。

```bash
# 检查 timer 是否启用
sudo systemctl status certbot.timer

# 查看 timer 触发时间
sudo systemctl list-timers | grep certbot

# 测试续期（干运行）
sudo certbot renew --dry-run

# 查看续期日志
sudo journalctl -u certbot.service -n 50
```

### 方式二：Crontab 定时任务

```bash
# 编辑 crontab
sudo crontab -e

# 添加以下行（每月 1 号和 15 号凌晨 3 点检查续期）
0 3 1,15 * * /usr/bin/certbot renew --quiet && /usr/sbin/nginx -s reload

# 查看已添加的任务
sudo crontab -l
```

### 方式三：Systemd Timer（手动设置）

```bash
# 创建服务文件
sudo tee /etc/systemd/system/certbot-renew.service << 'EOF'
[Unit]
Description=Certbot Renewal

[Service]
Type=oneshot
ExecStart=/usr/bin/certbot renew --quiet --post-hook "systemctl reload nginx"
EOF

# 创建 timer 文件
sudo tee /etc/systemd/system/certbot-renew.timer << 'EOF'
[Unit]
Description=Certbot Renewal Timer

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=43200

[Install]
WantedBy=timers.target
EOF

# 启动并启用 timer
sudo systemctl daemon-reload
sudo systemctl enable --now certbot-renew.timer

# 验证
sudo systemctl list-timers | grep certbot
```

### 证书状态监控

```bash
# 查看证书过期时间
sudo openssl x509 -enddate -noout -in /etc/letsencrypt/live/liankebao.top/fullchain.pem

# 查看证书详情
sudo certbot certificates

# 添加监控告警（可选）
# 在 crontab 中添加证书到期前 30 天邮件通知
0 9 * * * /usr/bin/certbot renew --quiet --deploy-hook "echo '证书已续期' | mail -s 'SSL Cert Renewed' admin@liankebao.top"
```

## 健康检查

```bash
# 本地检查
curl http://localhost:8000/health

# 远程检查
curl https://liankebao.top/health

# 前端检查
curl -I https://liankebao.top

# 安全头检查
curl -sI https://liankebao.top | grep -i "strict-transport-security\|x-frame-options\|x-content-type-options"
```
