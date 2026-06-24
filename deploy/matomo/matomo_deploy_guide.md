# Matomo 自建部署指南

> **目标服务器**: 阿里云/腾讯云 ECS (CentOS 7+ 或 Ubuntu 20.04+)
> **部署方式**: Docker Compose + Nginx 反向代理
> **文档版本**: v1.0
> **适用项目**: 链客宝前端追踪

---

## 目录

1. [前提条件](#1-前提条件)
2. [部署步骤](#2-部署步骤)
3. [初始化配置](#3-初始化配置)
4. [Nginx 配置](#4-nginx-配置)
5. [SSL 证书](#5-ssl-证书)
6. [安全加固](#6-安全加固)
7. [Matomo 配置要点](#7-matomo-配置要点)
8. [备份策略](#8-备份策略)
9. [常见问题](#9-常见问题)

---

## 1. 前提条件

### 服务器要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU  | 1 核    | 2 核    |
| 内存 | 2 GB    | 4 GB    |
| 磁盘 | 20 GB   | 50 GB (SSD) |
| 带宽 | 1 Mbps  | 5 Mbps  |
| 操作系统 | CentOS 7+ / Ubuntu 20.04+ | AlmaLinux 9 / Ubuntu 22.04 |

### 需要安装的软件

```bash
# ----- Docker -----
# 阿里云 ECS 一键安装 Docker
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
sudo systemctl enable --now docker

# ----- Docker Compose v2 -----
# Docker Compose 已内置于 Docker 新版中，验证:
docker compose version

# ----- Nginx -----
# CentOS
sudo yum install -y nginx
sudo systemctl enable --now nginx

# Ubuntu
sudo apt update && sudo apt install -y nginx
sudo systemctl enable --now nginx
```

### Docker 镜像加速器（国内服务器必配）

创建或编辑 `/etc/docker/daemon.json`:

```json
{
  "registry-mirrors": ["https://<your-id>.mirror.aliyuncs.com"]
}
```

> 登录 [阿里云容器镜像服务](https://cr.console.aliyun.com/) 获取您的专属加速地址。

重启 Docker:

```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
```

### 开放防火墙端口

```bash
# 阿里云/腾讯云控制台: 安全组规则中开放 80, 443 端口
# 服务器内部防火墙:
sudo firewall-cmd --add-service={http,https} --permanent
sudo firewall-cmd --reload
```

---

## 2. 部署步骤

### 2.1 获取部署文件

将本目录 (`matomo/`) 下的所有文件上传到服务器，或直接在服务器上创建。

推荐目录结构:

```
/opt/matomo/
├── docker-compose.yml       # Docker Compose 编排文件
├── matomo_nginx.conf        # Nginx 反向代理配置
├── tracking_snippet.html    # 前端追踪代码片段
├── data/
│   ├── db/                  # MariaDB 数据卷（自动创建）
│   └── matomo/              # Matomo 数据卷（自动创建）
└── config/
    └── config.ini.php       # 可选: Matomo 自定义配置
```

### 2.2 修改配置

**编辑 `docker-compose.yml`**，修改以下密码:

| 变量 | 说明 |
|------|------|
| `MYSQL_ROOT_PASSWORD` | 数据库 root 密码（强烈建议 20 位以上随机） |
| `MYSQL_PASSWORD` | Matomo 专用数据库用户密码 |

> 可使用以下命令生成密码:
> ```bash
> openssl rand -base64 24
> ```

### 2.3 启动服务

```bash
cd /opt/matomo

# 创建数据目录
mkdir -p data/db data/matomo config
chmod 755 data/db data/matomo

# 启动所有服务
docker compose up -d

# 查看启动状态
docker compose ps

# 查看日志（确认无报错）
docker compose logs -f
```

### 2.4 验证数据库连接

```bash
# 确认 Matomo 能连上数据库
docker compose exec matomo php /var/www/html/console diagnostics:analyze-database-connection
```

---

## 3. 初始化配置

### 3.1 访问 Web 安装向导

浏览器打开: `http://<服务器公网IP>:8080` (如果映射了端口)
或通过 Nginx 域名: `https://matomo.你的域名.com`

### 3.2 安装步骤

1. **欢迎页面** → 点击 "Next"
2. **系统检查** → 全部绿色 ✔ 后点 "Next"
3. **数据库设置**:
   - 数据库主机: `db` (Docker 内部服务名)
   - 数据库用户名: `matomo`
   - 数据库密码: `CHANGE_ME_MATOMO_PASSWORD` (docker-compose.yml 中设置的值)
   - 数据库名: `matomo`
   - 表前缀: `matomo_`
   - 点击 "Next"
4. **创建管理员账号**:
   - 用户名: 如 `admin`
   - 密码: （强密码，建议 16 位以上）
   - 邮箱: 管理员邮箱
5. **添加第一个站点**:
   - 网站名称: `链客宝`
   - 网站地址: `https://www.链客宝.com` (替换为实际域名)
   - 时区: `Asia/Shanghai`
   - 电子商务: 根据需要启用
6. **安装完成** → 获取追踪代码

### 3.3 生成追踪代码

安装完成后，Matomo 会给出 JavaScript 追踪代码。
**也可直接使用本项目提供的 `tracking_snippet.html`**（已包含自定义维度支持）。

---

## 4. Nginx 配置

### 4.1 修改配置文件

编辑 `matomo_nginx.conf`，替换以下占位符:

| 占位符 | 说明 |
|--------|------|
| `matomo.你的域名.com` | 你的实际域名 |
| `/etc/nginx/ssl/你的域名.com/...` | SSL 证书路径 |
| IP 白名单 / Basic Auth | 按需启用 |

### 4.2 部署 Nginx 配置

```bash
# 复制配置文件
sudo cp /opt/matomo/matomo_nginx.conf /etc/nginx/conf.d/matomo.conf

# 测试配置
sudo nginx -t

# 重载 Nginx
sudo systemctl reload nginx
```

### 4.3 配置防火墙（Docker 端口隔离）

Matomo 容器默认映射 8080 端口，建议仅允许 Nginx 访问:

```bash
# 修改 docker-compose.yml，去掉 matomo 端口的 public 映射
# 改为仅内部网络访问（见 docker-compose.yml 中的注释）
# 然后重启:
docker compose up -d
```

> 更安全的做法: 使用 Nginx 容器（而不是宿主机 Nginx）+ Docker 内部网络通信。

---

## 5. SSL 证书

### 使用 Let's Encrypt (Certbot)

```bash
# CentOS
sudo yum install -y certbot python3-certbot-nginx

# Ubuntu
sudo apt install -y certbot python3-certbot-nginx

# 申请证书（自动配置 Nginx）
sudo certbot --nginx -d matomo.你的域名.com

# 查看证书有效期
sudo certbot certificates

# 证书自动续期（certbot 已配置 systemd timer）
sudo certbot renew --dry-run
```

### 使用商业证书

将证书文件上传到服务器，路径与 `matomo_nginx.conf` 中配置一致:

```
/etc/nginx/ssl/你的域名.com/
├── fullchain.pem
└── privkey.pem
```

---

## 6. 安全加固

### 6.1 数据库安全

- **密码策略**: 数据库密码使用 20 位以上随机字符串
- **端口隔离**: 数据库端口绑定 `127.0.0.1:3307`，禁止公网访问
- **独立用户**: Matomo 使用专用数据库账号，仅拥有 `matomo` 库权限

### 6.2 访问控制

推荐启用 **方案A + 方案B** 双重保护:

1. **IP 白名单**: 仅允许公司出口 IP 访问 Matomo 管理后台
2. **Basic Auth**: 额外一层认证

创建 Basic Auth 用户:

```bash
# 安装 httpd-tools
sudo yum install -y httpd-tools   # CentOS
sudo apt install -y apache2-utils # Ubuntu

# 创建用户（会提示输入密码）
sudo htpasswd -c /etc/nginx/.htpasswd admin
```

### 6.3 Matomo 安全配置

- 登录 Matomo 后台 → **管理** → **安全**
- 启用双因素认证 (2FA) 对管理员账号
- 设置会话超时时间
- 限制登录尝试次数

### 6.4 系统安全

```bash
# 自动安全更新
sudo yum install -y yum-cron && sudo systemctl enable --now yum-cron  # CentOS
sudo dpkg-reconfigure --priority=low unattended-upgrades              # Ubuntu

# Fail2ban 防暴力破解
sudo yum install -y fail2ban   # CentOS
sudo apt install -y fail2ban   # Ubuntu
sudo systemctl enable --now fail2ban
```

---

## 7. Matomo 配置要点

### 7.1 网站 ID

每个被追踪的网站都有一个唯一 ID（如 `1`, `2`, `3`）。
查看路径: **管理** → **网站** → **管理** → 网站列表

### 7.2 追踪代码放置位置

- **链客宝前端**: 在 `<head>` 或 `</body>` 前插入追踪代码
- **单页应用 (SPA)**: 使用 Matomo 的 SPA 追踪插件或在路由切换时调用 `_paq.push(['trackPageView'])`
- **可选的部署方式**:
  - 直接嵌入 HTML
  - 通过 GTM (Google Tag Manager) 加载
  - 作为 JS 模块引入（ES Module 或 CommonJS）

### 7.3 自定义维度

本项目的 `tracking_snippet.html` 已内置以下自定义维度支持:

| 维度名称 | 维度索引 | 说明 |
|---------|---------|------|
| 用户ID   | 1       | 登录用户唯一标识 |
| 企业名称 | 2       | 企业版/商户名称 |
| 用户角色 | 3       | 如: admin, user, vip |

> **前置操作**: 在 Matomo 后台创建自定义维度
> 路径: **管理** → **自定义维度** → **创建新的维度**
> 创建 3 个维度，索引分别对应 1, 2, 3

### 7.4 追踪事件示例

```javascript
// 追踪按钮点击
_paq.push(['trackEvent', '按钮', '点击', '立即咨询']);

// 追踪页面浏览时长
_paq.push(['trackEvent', '会话', '页面停留', '产品页', 120]);

// 追踪目标转化
_paq.push(['trackGoal', 1]);  // 目标ID: 1
```

---

## 8. 备份策略

### 8.1 数据库备份 (推荐)

创建定时备份脚本 `/opt/matomo/backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/opt/matomo/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_PASSWORD="CHANGE_ME_ROOT_PASSWORD"   # ← 替换为实际密码

mkdir -p $BACKUP_DIR

docker compose exec -T db mysqldump \
  -u root -p$DB_PASSWORD \
  --all-databases --single-transaction --quick \
  | gzip > $BACKUP_DIR/matomo_db_$DATE.sql.gz

# 保留最近 30 天
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
```

```bash
chmod +x /opt/matomo/backup.sh

# 添加到 crontab（每天凌晨 3 点备份）
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/matomo/backup.sh") | crontab -
```

### 8.2 文件备份

```bash
# Matomo 插件和配置
tar -czf /opt/matomo/backups/matomo_files_$DATE.tar.gz \
  /opt/matomo/data/matomo/plugins \
  /opt/matomo/data/matomo/config
```

### 8.3 恢复备份

```bash
# 恢复数据库
gunzip < matomo_db_20250101_030000.sql.gz | docker compose exec -T db mysql -u root -p$DB_PASSWORD
```

---

## 9. 常见问题

### Q1: 安装向导中数据库连接失败

- 确保 `docker compose up -d` 已启动所有服务
- 检查数据库主机名是否为 `db`（Docker 内部服务名）
- 检查密码是否一致

### Q2: Matomo 页面显示 "Cannot connect to the database"

```bash
# 检查数据库容器状态
docker compose ps
docker compose logs db

# 进入数据库检查
docker compose exec db mysql -u matomo -p -e "SHOW DATABASES;"
```

### Q3: Nginx 502 Bad Gateway

- 确认 Matomo 容器正在运行: `docker compose ps`
- 检查 upstream 配置中的端口是否与容器映射一致
- 查看 Nginx 错误日志: `tail -f /var/log/nginx/error.log`

### Q4: 追踪代码无数据上报

- 检查网站 ID 是否匹配
- 浏览器打开开发者工具 → Network → 过滤 `matomo.php` 或 `piwik.php`
- 确认 Matomo 服务器能收到请求
- 检查防火墙是否阻止了上报请求

### Q5: Docker 镜像拉取慢

- 确认已配置阿里云镜像加速器
- 或手动拉取镜像后再启动:
  ```bash
  docker pull mariadb:10.11
  docker pull matomo:5-apache
  docker pull phpmyadmin:5
  ```

---

## 附录

### A. 快速启动命令速查

```bash
# 启动
docker compose up -d

# 停止
docker compose down

# 重启单个服务
docker compose restart matomo

# 查看日志
docker compose logs -f matomo

# 更新镜像
docker compose pull
docker compose up -d --force-recreate
```

### B. 端口映射说明

| 容器 | 内部端口 | 宿主机映射 | 说明 |
|------|---------|-----------|------|
| Matomo | 80 (Apache) | 127.0.0.1:8080 | Nginx 通过此端口代理 |
| MariaDB | 3306 | 127.0.0.1:3307 | 仅本地访问 |
| phpMyAdmin | 80 | 未公开 | 通过 `docker compose --profile admin up -d` 临时启动 |

### C. 监控与告警

建议配置服务器监控（可选）:

- 磁盘使用率: 监控 `data/db` 和 `data/matomo` 目录增长
- 内存使用: Matomo 归档任务可能消耗较多内存
- 配置云监控告警: CPU > 80%, 磁盘 > 85%

---

> **文档结束** — 如有问题请联系运维团队
