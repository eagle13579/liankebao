# 链客宝AI 部署说明文档

## 项目信息

| 项目 | 值 |
|------|-----|
| 项目名称 | 链客宝AI (LianKeBao) |
| 域名 | liankebao.top / www.liankebao.top |
| 服务器 | 阿里云 ECS (47.100.160.250) |
| 前端 | Vite + React (SPA) |
| 后端 | FastAPI + Uvicorn (Python 3.12, port **8001**) |
| 数据库 | SQLite (本地文件) |
| Web 服务器 | Nginx (反向代理 + SSL) |
| Git 仓库 | `git@github.com:eagle13579/liankebao.git` |
| 默认分支 | `master` |

> **端口说明**: 后端 Uvicorn 监听 `127.0.0.1:8001`（不对外暴露）。
> Nginx 监听 80/443 对外提供服务，通过 proxy_pass 反向代理到 `127.0.0.1:8001`。
> 如需直接访问后端 API：`curl http://127.0.0.1:8001/health`

## 目录结构（服务器端）

```
/opt/liankebao/
├── dist/                    # 前端构建产物（静态文件）
├── backend/                 # 后端代码
│   ├── app/                 # FastAPI 应用
│   ├── data/                # SQLite 数据库
│   ├── venv/                # Python 虚拟环境
│   └── requirements.txt     # Python 依赖
├── deploy/                  # 部署脚本和配置
│   ├── auto_deploy.sh       # 自动部署脚本（CI/CD 入口）
│   ├── deploy.sh            # 完整部署脚本
│   ├── chainke.service      # Systemd 服务配置
│   ├── nginx.conf           # Nginx 主配置
│   ├── nginx_security.conf  # Nginx 安全加固
│   ├── nginx_lkapi_location.conf  # 小程序 API 路由
│   ├── README_DEPLOY.md     # 本文件
│   ├── SSL_SETUP.md         # SSL 证书指南
│   └── 阿里云部署执行清单.md # 部署检查清单
├── logs/                    # 日志目录
│   ├── backend.log          # 后端运行时日志
│   ├── backend-error.log    # 后端错误日志
│   └── auto_deploy.log      # 自动部署日志
├── .env                     # 环境变量配置文件
└── deploy.sh -> deploy/deploy.sh  # 快捷入口
```

## 部署方式

### 方式一：GitHub Actions CI/CD（推荐）

每次 push 到 `master` 分支后自动触发完整 CI/CD 流水线。

**CI/CD 流水线步骤**:

```
push → [Backend Test] → [Frontend Build] → [Security Audit] → [Deploy] → [Health Check] → [Notify]
  │        │                  │                   │               │           │             │
  │    python lint      npm ci + build        .env 检查       SCP 上传    7项验证      失败通知
  │    + pytest         上传 artifact         密钥扫描       SSH 执行     Nginx ↓     打印回滚命令
  │                                                          auto_deploy 端口 ↓
  │                                                                       Health ↓
  │                                                                       API ↓
  │                                                                       资源 ↓
```

1. **Backend Test**: Python lint (ruff) + pytest + syntax check + Hermes logout 残留检测
2. **Frontend Build**: `npm ci && npm run build`（vite），产物保存为 artifact
3. **Security Audit**: 检查 .env 是否被 Git 跟踪、硬编码密钥扫描
4. **Deploy**: 打包项目 → SCP 上传 → SSH 执行 `auto_deploy.sh --skip-git-pull`
5. **Health Check**: 7 项验证（见下文健康检查章节）
6. **Notify**: 部署失败时输出回滚命令

**配置 GitHub Secrets**（Settings → Secrets and variables → Actions）：

| Secret 名称 | 说明 | 示例值 |
|-------------|------|--------|
| `HOST` | 服务器 IP 地址 | `47.100.160.250` |
| `USERNAME` | SSH 登录用户名 | `opc` 或 `deploy` |
| `SSH_KEY` | SSH 私钥（完整内容） | `-----BEGIN OPENSSH PRIVATE KEY-----\n...` |
| `DEPLOY_PATH` | 部署目录 | `/opt/liankebao` |

**生成专用部署密钥**：

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_deploy
ssh-copy-id -i ~/.ssh/github_deploy.pub opc@47.100.160.250
cat ~/.ssh/github_deploy  # 复制到 GitHub SSH_KEY Secret
```

### 方式二：一键部署（服务器本地）

```bash
# 完整部署（拉取代码 + 构建 + 部署）
sudo bash /opt/liankebao/deploy/deploy.sh

# 仅重启服务（不更新代码）
sudo bash /opt/liankebao/deploy/deploy.sh --restart-only

# 跳过前端构建（前端已单独构建）
sudo bash /opt/liankebao/deploy/deploy.sh --skip-frontend

# 指定分支
sudo bash /opt/liankebao/deploy/deploy.sh --branch=develop
```

### 方式三：定时自动部署（Crontab）

```bash
# 每天凌晨 3 点自动部署
sudo crontab -e
0 3 * * * /opt/liankebao/deploy/auto_deploy.sh >> /opt/liankebao/logs/cron.log 2>&1
```

### 方式四：手动部署

```bash
# 1. 本地构建前端
npm ci && npm run build

# 2. 上传到服务器
scp -r dist/ opc@47.100.160.250:/opt/liankebao/dist/
scp backend/* opc@47.100.160.250:/opt/liankebao/backend/

# 3. SSH 连上服务器执行
ssh opc@47.100.160.250
sudo bash /opt/liankebao/deploy/deploy.sh --skip-frontend --skip-git-pull
```

## Health Check 健康检查

### 部署后的自动健康检查（GitHub Actions）

每部署后自动执行以下 7 项验证：

| # | 检查项 | 失败处理 |
|---|--------|----------|
| 1 | Nginx 配置 (`nginx -t`) | 输出错误详情 |
| 2 | Systemd 服务 (`chainke.service`) | 打印最近 30 行日志 |
| 3 | TCP 端口监听 (`:8001`) | 检查端口是否被占用 |
| 4 | HTTP Health Endpoint（重试 12 次，间隔 3s） | 打印 journalctl 日志 |
| 5 | HTTPS 前端访问 (`https://liankebao.top`) | 仅告警，不阻断 |
| 6 | API 功能验证 (`/api/`) | 仅告警，不阻断 |
| 7 | 系统资源（磁盘/内存/负载） | 磁盘 >85% 告警 |

### Manual Health Check

```bash
# 1. 基础健康检查
curl http://127.0.0.1:8001/health
# 期望: {"status":"ok"}

# 2. 通过 Nginx 外部访问
curl https://liankebao.top/health

# 3. 前端可用性
curl -I https://liankebao.top

# 4. API 路由检查
curl https://liankebao.top/api/
curl https://liankebao.top/api/auth/login

# 5. 安全头检查
curl -sI https://liankebao.top | grep -i "strict-transport-security\|x-frame-options\|x-content-type-options"

# 6. 服务器资源
echo "磁盘: $(df -h / | awk 'NR==2{print $5}')"
echo "内存: $(free -h | awk '/Mem:/{print $3"/"$2}')"
echo "负载: $(uptime | awk -F'load average:' '{print $2}')"

# 7. 服务状态汇总
sudo systemctl status chainke --no-pager
sudo systemctl status nginx --no-pager
```

### 健康检查脚本

```bash
# 快速健康检查
/opt/liankebao/deploy/auto_deploy.sh --skip-git-pull --skip-notify

# 仅执行健康检查（不部署）
curl -s http://127.0.0.1:8001/health && echo "OK" || echo "FAIL"
```

## 服务管理

```bash
# 后端服务
sudo systemctl status chainke          # 查看状态
sudo systemctl restart chainke         # 重启
sudo systemctl start chainke           # 启动
sudo systemctl stop chainke            # 停止
sudo systemctl enable chainke          # 开机自启
sudo journalctl -u chainke -n 100 -f   # 实时查看日志

# Nginx
sudo systemctl status nginx            # 查看状态
sudo systemctl reload nginx            # 重载配置
sudo systemctl restart nginx           # 重启
sudo nginx -t                          # 测试配置
```

## 日志查看

```bash
# 后端日志
tail -f /opt/liankebao/logs/backend.log
tail -f /opt/liankebao/logs/backend-error.log

# 自动部署日志
tail -f /opt/liankebao/logs/auto_deploy.log

# Nginx 日志
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# Systemd 日志
sudo journalctl -u chainke -n 100 --no-pager
sudo journalctl -u chainke -f          # 实时
```

## 回滚方案

### 方式一：使用备份目录回滚（推荐）

服务器上保留最近 5 个部署备份（`/opt/liankebao.bak.YYYYMMDD_HHMMSS/`）：

```bash
# 列出可用备份
ls -d /opt/liankebao.bak.* 2>/dev/null

# 查看备份时间戳
ls -lt /opt/liankebao.bak.* | head -5

# 恢复指定备份
sudo rm -rf /opt/liankebao
sudo cp -r /opt/liankebao.bak.20260527_120000 /opt/liankebao
sudo systemctl restart chainke
sudo nginx -s reload

# 或使用 auto_deploy.sh 自动回滚到最近备份
sudo bash /opt/liankebao/deploy/auto_deploy.sh --rollback
```

### 方式二：Git 回滚

```bash
cd /opt/liankebao
git log --oneline -10
git checkout <上一个稳定commit>
sudo bash deploy/deploy.sh --skip-frontend
```

### 方式三：GitHub Actions 回滚

1. 前往 GitHub Actions 找到上一次成功的部署
2. 点击 "Re-run all jobs"
3. 或手动触发 workflow 并指定旧 commit

### 方式四：CI/CD 自动回滚

当部署后的健康检查失败时，`auto_deploy.sh` 会自动触发回滚：

```
部署失败 → 健康检查失败 → 自动恢复备份 → 重启服务 → 发送通知
           ↓
     保留当前版本为 backup.rollback-* 供手动分析
```

## SSL 证书管理

详见 `deploy/SSL_SETUP.md`。

```bash
# 申请证书
sudo certbot --nginx -d liankebao.top -d www.liankebao.top

# 续期测试
sudo certbot renew --dry-run

# 手动续期
sudo certbot renew
sudo nginx -s reload

# 查看证书过期时间
sudo openssl x509 -enddate -noout -in /etc/letsencrypt/live/liankebao.top/fullchain.pem
```

## Nginx 安全加固

详见 `deploy/nginx_security.conf` 和 `deploy/nginx.conf`。

| 安全措施 | 配置值 | 说明 |
|---------|--------|------|
| **HSTS** | `max-age=31536000; includeSubDomains` | 强制 HTTPS |
| **X-Frame-Options** | `DENY` | 防点击劫持 |
| **X-Content-Type-Options** | `nosniff` | 防 MIME 嗅探 |
| **Content-Security-Policy** | `default-src 'self'` | 防 XSS |
| **速率限制** | 10 请求/秒/IP | 防 CC 攻击 |
| **敏感文件禁止** | `.db .sqlite .env .git .pyc` | 禁止访问敏感文件 |

## 部署清单

首次部署请按以下顺序操作：

1. **服务器环境准备**（一次性）
   - [ ] Ubuntu 22.04 系统
   - [ ] Python 3.12, Node.js 20, Nginx, Git, Certbot
   - [ ] 安全组开放 22, 80, 443 端口

2. **SSH 和密钥配置**
   - [ ] SSH 密钥登录
   - [ ] 创建专用 deploy 用户（可选）
   - [ ] GitHub Secrets 配置

3. **代码部署**
   - [ ] `git clone git@github.com:eagle13579/liankebao.git /opt/liankebao`
   - [ ] 初始化后端：`python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
   - [ ] 配置 `.env`（复制 `.env.example` 后填入真实密钥）
   - [ ] 前端构建：`npm ci && npm run build`

4. **Nginx 和后端服务**
   - [ ] 部署 nginx.conf：`sudo cp deploy/nginx.conf /etc/nginx/nginx.conf`
   - [ ] 部署 chainke.service：`sudo cp deploy/chainke.service /etc/systemd/system/`
   - [ ] 启动服务：`sudo systemctl daemon-reload && sudo systemctl enable --now chainke`
   - [ ] 重载 Nginx：`sudo nginx -t && sudo systemctl reload nginx`

5. **SSL 证书**
   - [ ] 申请：`sudo certbot --nginx -d liankebao.top -d www.liankebao.top`
   - [ ] 验证：`curl -I https://liankebao.top`
   - [ ] 续期测试：`sudo certbot renew --dry-run`

6. **CI/CD 配置**
   - [ ] GitHub Secrets 配置（HOST, USERNAME, SSH_KEY, DEPLOY_PATH）
   - [ ] 推送到 master 触发首次自动部署
   - [ ] 验证 Actions 日志
   - [ ] 可选：配置钉钉/Slack 通知

## 故障排查

### 部署失败

```bash
# 1. 检查 GitHub Actions 日志
# 2. SSH 登录服务器排查
ssh opc@47.100.160.250

# 3. 检查后端服务
sudo systemctl status chainke
sudo journalctl -u chainke -n 50 --no-pager

# 4. 检查 Nginx
sudo nginx -t
sudo systemctl status nginx

# 5. 检查端口
ss -tlnp | grep 8001

# 6. 手动测试
curl http://127.0.0.1:8001/health
curl -I https://liankebao.top

# 7. 回滚到上一个版本
sudo bash /opt/liankebao/deploy/auto_deploy.sh --rollback
```

### 健康检查失败

| 检查项 | 可能原因 | 解决方法 |
|--------|----------|----------|
| Nginx 配置错误 | nginx.conf 语法错误 | `sudo nginx -t` 查看详细错误 |
| chainke 未运行 | Python 依赖缺失 | `sudo journalctl -u chainke -n 50` |
| 端口 8001 未监听 | 服务启动失败 | 检查 venv 和 requirements |
| Health 返回非 200 | 应用启动异常 | 检查 backend-error.log |
| HTTPS 访问失败 | SSL 证书过期 | `sudo certbot renew` |
| 磁盘 > 85% | 日志或备份堆积 | `sudo journalctl --vacuum-time=7d` |

### 常见错误

```
# Error: Permission denied (publickey)
解决: 检查 SSH 密钥是否正确添加到服务器 authorized_keys

# Error: port 8001 already in use
解决: sudo fuser -k 8001/tcp

# Error: ModuleNotFoundError
解决: source venv/bin/activate && pip install -r requirements.txt

# Error: nginx: [emerg] bind() to 0.0.0.0:80 failed
解决: sudo lsof -i :80 检查端口占用
```

## 持续改进

- [ ] 配置 Slack/钉钉/企业微信部署通知
- [ ] 添加 Blue-Green 部署支持
- [ ] 迁移到 PostgreSQL（可选）
- [ ] 添加性能测试到 CI/CD 流水线
- [x] Docker 容器化部署 ✅

## Docker 容器化部署

### 概述

链客宝AI支持完整的 Docker 容器化部署方案，包含以下组件：

| 服务 | 镜像/基础 | 端口 | 说明 |
|------|-----------|------|------|
| **backend** | Python 3.12-slim | 8001 | FastAPI + Uvicorn（2 workers） |
| **frontend** | nginx:1.27-alpine | 80 | React SPA + API 反向代理 |
| **redis** | redis:7-alpine（可选） | 6379 | 缓存/会话/消息队列 |

### 前置条件

- Docker Engine >= 24.0
- Docker Compose >= 2.20（或 `docker compose` 插件）
- Git

### 快速启动

```bash
# 1. 克隆仓库
git clone git@github.com:eagle13579/liankebao.git /opt/liankebao
cd /opt/liankebao

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入真实密钥（SECRET_KEY, 微信支付等）

# 3. 构建并启动所有服务
docker compose up -d

# 4. 查看启动日志
docker compose logs -f

# 5. 验证部署
curl http://localhost/health
curl -I http://localhost
```

### 文件说明

| 文件 | 用途 |
|------|------|
| `Dockerfile` | 多阶段构建（前端构建 → 后端服务 → Nginx 前端） |
| `docker-compose.yml` | 服务编排（backend + frontend + redis） |
| `.dockerignore` | 构建上下文排除（node_modules, venv, .git 等） |
| `deploy/nginx.docker.conf` | Docker 环境专用 Nginx 配置 |

### Dockerfile 构建阶段

```
frontend-builder (node:20-alpine)
    ↓ npm ci && npm run build
    ↓ 产物: dist/ 静态文件
    ├──→ backend (python:3.12-slim)
    │      └── uvicorn app.main:app --port 8001
    └──→ frontend (nginx:1.27-alpine)
           └── 静态文件服务 + API 反向代理
```

### 常用命令

```bash
# 启动所有服务
docker compose up -d

# 启动所有服务（含 Redis）
docker compose --profile optional up -d

# 停止所有服务
docker compose down

# 重建镜像（代码更新后）
docker compose build
docker compose up -d

# 重建单个服务
docker compose build backend
docker compose up -d backend

# 查看日志
docker compose logs -f
docker compose logs -f backend
docker compose logs -f frontend

# 进入容器
docker compose exec backend sh
docker compose exec frontend sh

# 查看资源使用
docker compose stats

# 健康检查
docker compose ps
curl http://localhost/health
curl http://localhost:8001/health

# 备份数据库
docker compose exec backend sh -c "cp /app/backend/data/*.db /tmp/db-backup.sqlite"
docker compose cp backend:/tmp/db-backup.sqlite ./backup-$(date +%Y%m%d).sqlite
```

### 环境变量说明

Docker 环境下 `.env` 文件中的以下变量会被自动加载：

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `SECRET_KEY` | JWT 签名密钥 | **必须修改** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 访问令牌过期时间 | 1440 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 刷新令牌过期时间 | 7 |
| `CORS_ORIGINS` | 跨域允许来源 | `*` |
| `TZ` | 时区 | `Asia/Shanghai` |

> **注意**：Docker 环境下 `GEMINI_API_KEY` 等前端构建时使用的环境变量需在构建时传入：
> ```bash
> docker compose build --build-arg GEMINI_API_KEY=your_key
> ```
> 如需持久化，可在 `docker-compose.yml` 的 `frontend` 服务 `build.args` 中添加。

### 数据持久化

| 数据卷 | 挂载点 | 说明 |
|--------|--------|------|
| `db_data` | `/app/backend/data` | SQLite 数据库文件 |
| `logs` | `/app/logs` | 后端运行时日志 |
| `redis_data` | `/data` | Redis 持久化数据 |

数据卷默认存储在 Docker 管理的目录中（`/var/lib/docker/volumes/`）。如需备份：

```bash
# 查看数据卷位置
docker volume inspect liankebao_db_data

# 通过容器导出数据库
docker compose exec backend sh -c "cat /app/backend/data/chainke.db" > chainke-backup.db
```

### 生产环境部署

#### 方案一：Docker Compose（单机）

```bash
# 生产环境启动（不带 Redis）
docker compose -f docker-compose.yml up -d

# 设置开机自启（通过 systemd）
sudo tee /etc/systemd/system/liankebao-docker.service <<'EOF'
[Unit]
Description=链客宝AI Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/liankebao
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
StandardOutput=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now liankebao-docker
```

#### 方案二：Nginx SSL 反向代理（生产环境推荐）

在 Docker 环境前再加一层宿主机 Nginx，提供 SSL 终结：

```nginx
# /etc/nginx/conf.d/liankebao.ssl.conf
server {
    listen 443 ssl http2;
    server_name liankebao.top www.liankebao.top;

    ssl_certificate     /etc/letsencrypt/live/liankebao.top/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/liankebao.top/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:80;  # 转发到 Docker frontend
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name liankebao.top www.liankebao.top;
    return 301 https://$host$request_uri;
}
```

#### 方案三：Docker Swarm（生产集群）

Docker Compose 文件兼容 Docker Stack 部署：

```bash
# 初始化 Swarm
docker swarm init

# 部署 Stack
docker stack deploy -c docker-compose.yml liankebao
```

> **生产环境建议**：
> - 在前端加一层宿主机 Nginx 做 SSL 终结（方案二）
> - 启用 Redis `--profile optional` 提升性能
> - 配置 Docker 日志轮转（`/etc/docker/daemon.json`）
> - 定期备份 `db_data` 数据卷

### 从裸机迁移到 Docker

```bash
# 1. 备份现有数据
cp /opt/liankebao/backend/data/*.db /tmp/
cp /opt/liankebao/.env /tmp/

# 2. 停止旧服务
sudo systemctl stop chainke
sudo systemctl disable chainke

# 3. 启动 Docker 版
cd /opt/liankebao
docker compose up -d

# 4. 复制现有数据库
docker compose cp /tmp/chainke.db backend:/app/backend/data/

# 5. 验证迁移
curl http://localhost/health
curl http://localhost/api/auth/login
```

### 故障排查

```bash
# 容器未启动
docker compose ps
docker compose logs backend
docker compose logs frontend

# 端口冲突
sudo lsof -i :80 -i :8001 -i :6379

# 数据库问题
docker compose exec backend sh -c "ls -la /app/backend/data/"
docker compose exec backend sh -c "sqlite3 /app/backend/data/chainke.db .tables"

# 重建全部
docker compose down -v   # 注意: -v 会删除数据卷！
docker compose build --no-cache
docker compose up -d

# 进入容器调试
docker compose exec backend sh
docker compose exec frontend sh
```

### CI/CD 与 Docker

在 GitHub Actions 中集成 Docker 部署：

```yaml
# .github/workflows/deploy.yml 片段
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and Deploy with Docker
        run: |
          scp -r . opc@47.100.160.250:/opt/liankebao/
          ssh opc@47.100.160.250 "cd /opt/liankebao && docker compose build && docker compose up -d"
```

### 安全注意事项

1. **永远不要**将 `.env` 提交到 Git 仓库（已在 `.gitignore` 和 `.dockerignore` 中排除）
2. Docker Compose 默认不暴露 Redis 端口到外网（仅限 `liankebao-net` 内部网络）
3. 生产环境建议在前端加宿主机 Nginx 做 SSL 终结（参见方案二）
4. 定期更新基础镜像：`docker compose pull`
5. 扫描镜像漏洞：`docker scout quick` 或 `trivy image liankebao-backend:latest`
