# 链客宝微信小程序

## 快速启动

**方式1：双击 `打开微信小程序.bat`**（自动调用开发者工具CLI打开项目）

**方式2：手动打开**
1. 打开 **微信开发者工具**
2. 点击 **导入项目**
3. 目录：`D:\链客宝\liankebao-miniapp`
4. AppID：`wxb4f6d89904200fd2`（已填写）
5. 开发模式勾选 **"不使用云服务"**
6. 点击导入

## 开发调试注意事项

- 开发者工具中点击 **详情 → 本地设置** → 勾选 **"不校验合法域名..."**（因为当前API地址是IP，正式发布时再开启校验）
- 接口地址：`https://47.100.160.250/api`（等 `www.liankebao.com` DNS解析后改回域名）

## 发布流程

1. 重新认证小程序（有效期300元/年）
2. 配DNS：`www.liankebao.com → 47.100.160.250`
3. 通知我配SSL证书 + 改API地址回域名
4. 开发者工具 → 上传
5. 小程序后台 → 提审 → 发布

## 项目结构

```
liankebao-miniapp/
├── app.js              # 入口
├── app.json            # 全局配置（5个页面）
├── app.wxss            # 全局样式
├── project.config.json # 项目配置（含AppID）
├── utils/api.js        # API客户端
├── pages/
│   ├── index/          # 首页（产品列表）
│   ├── login/          # 登录页（微信一键登录）
│   ├── product/        # 产品详情
│   ├── orders/         # 我的订单
│   └── mine/           # 个人中心
└── components/
    └── productCard/    # 产品卡片组件
```
