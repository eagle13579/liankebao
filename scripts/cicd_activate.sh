#!/bin/bash
# ============================================================
# 链客宝 CI/CD 激活脚本
# 运行环境: 阿里云 ECS (root@47.116.116.87)
# 使用方法: 在 GitHub 仓库 Settings → Secrets and variables → Actions 中设置
# ============================================================
set -e

echo "============================================"
echo "  链客宝 CI/CD 激活指引"
echo "============================================"
echo ""

# 检查 .git 是否存在
if [ -d ".git" ]; then
    echo "[✓] Git 仓库已初始化"
else
    echo "[!] Git 仓库未初始化。请执行:"
    echo "    git init"
    echo "    git remote add origin https://github.com/YOUR_ORG/chainke.git"
    echo "    git add ."
    echo "    git commit -m 'Initial commit'"
    echo "    git branch -M main"
    echo "    git push -u origin main"
    echo ""
fi

# 检查 GitHub 远程仓库
REMOTE=$(git config --get remote.origin.url 2>/dev/null || echo "")
if [ -n "$REMOTE" ]; then
    echo "[✓] Git 远程仓库: $REMOTE"
else
    echo "[!] 未设置 Git 远程仓库"
fi

echo ""
echo "============================================"
echo "  步骤 1: 创建 GitHub 仓库"
echo "============================================"
echo "  1. 访问 https://github.com/new"
echo "  2. 仓库名: chainke (或 liankebao)"
echo "  3. 设为 Private (推荐)"
echo "  4. 不要初始化 README/.gitignore"
echo "  5. 创建后执行:"
echo ""
echo "  cd /var/www/liankebao"
echo "  git remote add origin git@github.com:YOUR_ORG/chainke.git"
echo "  git add ."
echo "  git commit -m '初始提交'"
echo "  git push -u origin main"
echo ""

echo "============================================"
echo "  步骤 2: 设置 GitHub Secrets"
echo "============================================"
echo "  在 GitHub 仓库: Settings → Secrets and variables → Actions"
echo "  添加以下 Repository secrets:"
echo ""
echo "  ┌─────────────────────────────────────────┐"
echo "  │  Secret Name        │  Value            │"
echo "  ├─────────────────────────────────────────┤"
echo "  │  SSH_HOST           │  47.116.116.87    │"
echo "  │  SSH_USER           │  root             │"
echo "  │  SSH_PRIVATE_KEY    │  (服务器的私钥)    │"
echo "  │  DEPLOY_PATH        │  /var/www/liankebao│"
echo "  └─────────────────────────────────────────┘"
echo ""

echo "============================================"
echo "  步骤 3: 设置 GitHub Actions 权限"
echo "============================================"
echo "  Settings → Actions → General → Workflow permissions"
echo "  勾选: Read and write permissions"
echo "  勾选: Allow GitHub Actions to create and approve pull requests"
echo ""

echo "============================================"
echo "  步骤 4: 触发首次部署"
echo "============================================"
echo "  git push origin main"
echo ""
echo "  或手动触发:"
echo "  GitHub → Actions → 链客宝 CI/CD → Run workflow"
echo ""

echo "============================================"
echo "  已存在的工作流文件:"
echo "============================================"
echo "  📄 .github/workflows/deploy.yml  - CI/CD 部署"
echo "  📄 .github/workflows/lint.yml    - Ruff 代码检查"
echo ""
echo "  工作流需要以下 Secrets:"
echo "  - SSH_HOST: 47.116.116.87"
echo "  - SSH_USER: root"
echo "  - SSH_PRIVATE_KEY: (服务器 SSH 私钥)"
echo "  - DEPLOY_PATH: /var/www/liankebao"
echo ""

echo "============================================"
echo "  CI/CD 工作流程说明"
echo "============================================"
echo "  push → develop 分支: 构建 + 测试"
echo "  push → main 分支:   构建 + 测试 + 自动部署到阿里云 ECS"
echo ""
echo "  部署流程:"
echo "    1. git pull (拉取最新代码)"
echo "    2. pip install (更新依赖)"
echo "    3. 重启 uvicorn 后端"
echo "    4. nginx reload (重载 Nginx)"
echo ""

echo "=== CI/CD 激活指引输出完毕 ==="
