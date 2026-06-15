# 链客宝 CI/CD Secrets 配置指南

## 概述

链客宝已配置完整的 GitHub Actions CI/CD 流水线，包含三个工作流：

| 工作流文件 | 触发条件 | 说明 |
|-----------|---------|------|
| `ci.yml` | push/PR → develop/main | 后端 ruff lint + pytest + 安全测试 + 前端构建验证 |
| `lint.yml` | push/PR → main/develop | Ruff lint + format check |
| `deploy.yml` | push → develop/main | 测试 → Docker 构建 → 推送到 ghcr.io → SSH 部署到阿里云 ECS |

**要启用自动部署，需在 GitHub 仓库配置以下 Secrets。**

---

## 必填 Secrets（部署必需）

### 1. ECS SSH 私钥 — `ECS_SSH_KEY`

SSH 免密登录阿里云 ECS 的私钥（RSA/ED25519）。

```
# 在本地生成密钥对（如已有则跳过）
ssh-keygen -t ed25519 -f ~/.ssh/liankebao-deploy -C "github-actions"

# 将公钥添加到 ECS 服务器的 ~/.ssh/authorized_keys
ssh-copy-id -i ~/.ssh/liankebao-deploy.pub root@<ECS_IP>

# 复制私钥内容（全部，包括 -----BEGIN 和 -----END）
cat ~/.ssh/liankebao-deploy
```

在 GitHub 仓库 → Settings → Secrets and variables → Actions → 添加：
- **Name:** `ECS_SSH_KEY`
- **Secret:** 粘贴完整私钥内容

**别名：** 也可使用 `SSH_PRIVATE_KEY`

### 2. ECS 主机地址 — `ECS_HOST`

阿里云 ECS 的公网 IP 或域名。

- **Name:** `ECS_HOST`
- **Secret:** `47.100.160.250`（或实际 IP/域名）

**别名：** 也可使用 `SSH_HOST`

### 3. ECS 用户名 — `ECS_USER`

SSH 登录用户名。

- **Name:** `ECS_USER`
- **Secret:** `root`（或实际用户名）

**别名：** 也可使用 `SSH_USER`

---

## 可选 Secrets

### 4. SSH 端口 — `ECS_PORT`

SSH 端口，默认为 22。

- **Name:** `ECS_PORT`
- **Secret:** `22`（或自定义端口）

### 5. SSH 密码（备用认证方式）— `ECS_PASSWORD`

如使用密码认证而非密钥，配置此 Secret。仅当密钥认证失败时自动降级使用。

- **Name:** `ECS_PASSWORD`
- **Secret:** （SSH 密码）

**别名：** 也可使用 `SSH_PASSWORD`

---

## 内置 Secret（无需配置）

| Secret | 说明 |
|--------|------|
| `GITHUB_TOKEN` | GitHub Actions 自动提供，用于登录 ghcr.io 和 API 调用 |

---

## 配置步骤（向海容操作指南）

### 第 1 步：准备 SSH 密钥

在本地电脑（或 ECS 服务器上）执行：

```bash
# 生成部署专用密钥
ssh-keygen -t ed25519 -f ~/.ssh/liankebao-gh-deploy -C "github-actions"

# 查看公钥
cat ~/.ssh/liankebao-gh-deploy.pub
# 输出类似：ssh-ed25519 AAAAC3... github-actions
```

### 第 2 步：将公钥添加到 ECS 服务器

```bash
# 登录 ECS
ssh root@47.100.160.250

# 确保 ~/.ssh/authorized_keys 存在
mkdir -p ~/.ssh && chmod 700 ~/.ssh

# 将上一步的公钥追加到 authorized_keys
echo "ssh-ed25519 AAAAC3... github-actions" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### 第 3 步：在 GitHub 配置 Secrets

1. 打开 https://github.com/eagle13579/liankebao/settings/secrets/actions
2. 点击 **"New repository secret"**
3. 依次添加以下 3 个必填 Secret：

| Secret | 值 |
|--------|-----|
| `ECS_SSH_KEY` | 私钥完整内容（`cat ~/.ssh/liankebao-gh-deploy`） |
| `ECS_HOST` | `47.100.160.250` |
| `ECS_USER` | `root` |

### 第 4 步：验证

推送代码到 `develop` 或 `main` 分支，观察 Actions 运行状态：

```
https://github.com/eagle13579/liankebao/actions
```

---

## CI/CD 流水线流程说明

```
push → develop/main
  │
  ├── ci.yml ──→ ruff lint + pytest + vitest + 前端构建验证
  │
  └── deploy.yml
        ├── job: test       → Python 测试 + 前端构建验证
        ├── job: build      → Docker 镜像构建 → 推送到 ghcr.io
        └── job: deploy     → SSH 连接阿里云 ECS → 拉取镜像 → docker compose up
```

- `develop` 分支 → 部署到 **staging** 环境
- `main` 分支 → 部署到 **production** 环境

---

## 注意事项

1. **ECS 服务器预装要求：** Docker、docker compose、git
2. **SSL 证书：** 部署脚本会自动检查 `/etc/letsencrypt/live/liankebao.top/` 证书
3. **首次部署：** ECS 上需先手动执行一次部署脚本初始化目录结构
4. **安全：** 私钥需妥善保管，建议定期轮换

---

> 配置完成后，向海容只需推送代码到 GitHub，CI/CD 即可自动运行 🚀
