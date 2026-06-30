#!/bin/bash
# =============================================================================
# 链客宝 一键部署脚本 — ICP备案号 + 微信扫码登录
# 2026-06-30
# =============================================================================
set -e

echo "=== Step 1: 编译前端 ==="
cd "$(dirname "$0")/../deploy/docker"
npm run build

echo ""
echo "=== Step 2: 提交代码到 GitHub ==="
cd ../..
git add -A
git commit -m "feat: 添加ICP备案号+微信扫码登录(qrconnect)

- 登录页底部添加沪ICP备2026007459号-2
- 非微信浏览器自动跳转开放平台扫码登录
- wechat_sdk.py 新增 qrconnect_url + for_qrconnect()
- wechat_router.py 新增 POST /api/wechat/qrconnect-url
- 需配置 OPEN_WECHAT_APPID / OPEN_WECHAT_SECRET"
git push origin main

echo ""
echo "=== Step 3: GitHub Actions 自动部署 ==="
echo "等待 ~5 分钟后访问 https://liankebao.top 验证"
echo ""
echo "=== 后置步骤 ==="
echo "1. 注册微信开放平台 → https://open.weixin.qq.com/"
echo "2. 创建网站应用 → 获取 AppID + AppSecret"
echo "3. 配置到服务器 .env: OPEN_WECHAT_APPID / OPEN_WECHAT_SECRET"
echo "4. 重启 Docker 容器使配置生效"
