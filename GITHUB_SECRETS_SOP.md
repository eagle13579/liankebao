# 链客宝 GitHub Secrets 配置 SOP

> 适用场景：链客宝 CI/CD 流水线需要 GitHub Secrets 才能运行
> 目标仓库：`https://github.com/{你的用户名}/liankebao`
> 前置条件：已将链客宝代码推送到 GitHub 仓库

---

## 步骤一：进入仓库 Secrets 设置页

```
登录 GitHub → 打开 liankebao 仓库
    → Settings (顶部导航栏)
        → Secrets and variables (左侧边栏)
            → Actions
                → 绿色按钮 [New repository secret]
```

**图示路径**: `仓库主页 → Settings → Secrets and variables → Actions → New repository secret`

---

## 步骤二：逐个添加以下 Secrets

### 必须配置（4个）

| Secret 名称 | 值 | 从哪里获取 | 用途 |
|:------------|:---|:-----------|:-----|
| `DEEPSEEK_API_KEY` | `sk-d15d74cc5720475a82ba6f8c2e46f31c` | 已有（当前会话用的就是它） | CI 中调用 LLM 能力 |
| `MYSQL_URL` | `mysql+pymysql://chainke:密码@localhost:3306/chainke` | 阿里云 ECS 上的 MySQL 配置 | 后端测试数据库连接 |
| `DEPLOY_HOST` | `47.116.116.87` | 阿里云 ECS 公网 IP | SSH 部署目标服务器 |
| `DEPLOY_KEY` | SSH 私钥内容（一整块文本） | 阿里云 ECS 的 `~/.ssh/id_rsa` | SSH 免密登录部署服务器 |

### 推荐配置（2个）

| Secret 名称 | 值 | 从哪里获取 | 用途 |
|:------------|:---|:-----------|:-----|
| `WECHAT_MCH_ID` | 微信商户号 | 微信支付商户平台 | 生产支付功能 |
| `ALIPAY_APP_ID` | 支付宝 APP ID | 支付宝开放平台 | 支付宝支付 |

### 可选配置

| Secret 名称 | 值 | 用途 |
|:------------|:---|:------|
| `SENTRY_DSN` | Sentry DSN | 错误监控 |
| `POSTHOG_API_KEY` | PostHog Key | 产品分析 |

---

## 步骤三：配置操作细节

### 添加 DEEPSEEK_API_KEY

```
Name (名称):     DEEPSEEK_API_KEY
Secret (密钥):   sk-d15d74cc5720475a82ba6f8c2e46f31c
→ 点击 [Add secret]
```

### 添加 DEPLOY_KEY（SSH 私钥）

从服务器获取私钥内容：

```bash
# SSH 登录阿里云 ECS
ssh root@47.116.116.87

# 查看私钥文件
cat ~/.ssh/id_rsa
# 如果不存在，需要先创建：
# ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
# cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
```

复制整个私钥内容（包括 `-----BEGIN OPENSSH PRIVATE KEY-----` 和 `-----END OPENSSH PRIVATE KEY-----`），粘贴到 GitHub Secrets 的 Value 字段。

---

## 步骤四：验证配置

配置完成后，手动触发一次 CI 验证：

```bash
# 在本地仓库执行
git commit --allow-empty -m "ci: trigger workflow test"
git push origin develop
```

然后在 GitHub 仓库页面：

```
Actions (顶部导航栏)
    → 应该看到新的 workflow 正在运行
    → 点击查看 backend / frontend / security 三个 job 的状态
```

验证要点：
- ✅ backend: ruff lint 通过 + pytest 通过
- ✅ frontend: tsc 零报错 + vitest 全部通过
- ✅ security: data_security 测试通过

---

## 步骤五：配置部署流水线（可选）

CI 通过后，可配置 CD（自动部署）：

```bash
# 在 .github/workflows/deploy.yml 中添加 deploy job
# 使用 DEPLOY_HOST + DEPLOY_KEY SSH 登录服务器
# git pull → npm build → rsync → nginx reload
```

注意：CD 需要先在服务器上配置好 SSH 免密登录到 GitHub（`ssh-keyscan github.com >> ~/.ssh/known_hosts`）

---

## 常见问题

| 问题 | 原因 | 解决 |
|:-----|:------|:------|
| CI 报 `Permission denied (publickey)` | DEPLOY_KEY 格式不对或未添加到 authorized_keys | 确认私钥包含完整的 `-----BEGIN...-----END...-----` 块 |
| CI 报 `Can't find 'pytest'` | requirements.txt 未包含 pytest | 确认 `backend/requirements.txt` 有 pytest |
| CI 前端超时 | npm ci 下载慢 | 检查是否启用了 npm cache (actions/setup-node 的 cache: 'npm') |
| CI 不触发 | workflow 文件名不是 ci.yml | 确认文件名是 `.github/workflows/ci.yml` |
| Secret 不小心暴露 | 写到了日志/输出中 | 立即到 GitHub 删除并重新生成新 Secret |

---

## ⚠️ 安全提醒

- ❌ 永远不要在代码中硬编码 Secret 值
- ❌ 永远不要在 Actions 日志中 print Secret
- ✅ Secret 在 CI 运行时自动注入为环境变量
- ✅ Secret 一旦保存，任何人（包括你）都无法再次查看原文——只能覆盖或删除
- ✅ 如果怀疑 Secret 泄露，立即删除并重新生成
