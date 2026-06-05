# ============================================================
# 链客宝 安全加固 + CI/CD + MySQL 迁移准备 摘要报告
# 执行日期: 2026-05-27 21:00 CST
# 服务器: 47.116.116.87
# ============================================================

## 一、安全加固 (90% → 100%)

### Nginx 安全配置 ✅

| 措施 | 状态 | 说明 |
|------|------|------|
| server_tokens off | ✅ | nginx.conf - 隐藏版本号 |
| 限流配置 | ✅ | general:10r/s, api_limit:30r/s |
| 敏感路径封禁 | ✅ | .git, .env, admin, config, db 等返回 403 |
| HSTS | ✅ | max-age=31536000; includeSubDomains |
| X-Content-Type-Options | ✅ | nosniff |
| X-Frame-Options | ✅ | SAMEORIGIN |
| X-XSS-Protection | ✅ | 1; mode=block |
| Referrer-Policy | ✅ | strict-origin-when-cross-origin |
| Permissions-Policy | ✅ | geolocation=(), microphone=(), camera=() |
| Content-Security-Policy | ✅ | default-src 'self'; script-src 'self' ... |
| CORS 白名单 | ✅ | 从 '*' 改为 'https://liankebao.top' |
| 备份 | ✅ | /etc/nginx/nginx.conf.bak.20260527, /etc/nginx/chainke.bak.20260527 |

### 后端安全中间件 ✅

- SecurityHeadersMiddleware 已导入到 main.py (第12行)
- 已在 CORS 中间件之后注册 (第137行)
- 提供: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, HSTS, CSP, Cache-Control

### systemd 服务修复 ✅

- WorkingDirectory: /opt/chainke/backend → /var/www/liankebao/backend
- 端口: 8000 → 8001 (与 nginx proxy_pass 一致)
- 添加环境变量: DB_TYPE, PYTHONPATH, UVICORN_PORT

## 二、CI/CD 激活

### 当前状态
- GitHub Workflow 文件存在: deploy.yml, lint.yml ✅
- 需要 Secrets: SSH_HOST, SSH_USER, SSH_PRIVATE_KEY, DEPLOY_PATH
- ❌ 项目没有 .git 目录 — 无法连接到 GitHub

### 激活步骤
1. 在 GitHub 创建仓库 (chainke)
2. 在服务器执行 git init + git remote add
3. push 到 GitHub
4. 在仓库 Settings → Secrets 设置4个变量
5. push main 分支触发自动部署

### 便利脚本
- /var/www/liankebao/scripts/cicd_activate.sh — 激活指引脚本

## 三、MySQL 迁移准备

| 项目 | 状态 | 说明 |
|------|------|------|
| MySQL 8.0 | ✅ | 运行中 :3306 |
| 数据库 liankebao | ✅ | 已创建, charset=utf8mb4 |
| MySQL 用户 | ✅ | liankebao@localhost (密码: CHANGE_ME_PLEASE) |
| Alembic 配置 | ✅ | 2 个迁移版本就绪 |
| 迁移脚本 | ✅ | one_click_migrate.py, migrate_to_mysql.py |
| 迁移文档 | ✅ | docs/MYSQL_MIGRATION_README.md |

### 迁移命令
```bash
cd /var/www/liankebao/backend
python scripts/one_click_migrate.py --to mysql -y
```

### 回滚
```bash
# 改回 .env: DB_TYPE=sqlite
sudo systemctl restart chainke
```

## 修改的文件

| 文件 | 修改内容 |
|------|----------|
| /etc/nginx/nginx.conf | 添加 limit_req_zone, 设置 server_tokens off |
| /etc/nginx/sites-enabled/chainke | 添加敏感路径封禁、限流、CSP、安全头、CORS白名单 |
| /etc/nginx/nginx.conf.bak.20260527 | 备份 |
| /etc/nginx/chainke.bak.20260527 | 备份 |
| /var/www/liankebao/backend/app/main.py | 导入并注册 SecurityHeadersMiddleware |
| /etc/systemd/system/chainke.service | 修复路径、端口、环境变量 |
| /var/www/liankebao/scripts/cicd_activate.sh | 新建 - CI/CD激活脚本 |
| /var/www/liankebao/docs/MYSQL_MIGRATION_README.md | 新建 - MySQL迁移准备文档 |
