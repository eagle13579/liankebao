# 链客宝微信小程序配置SOP（手把手版）

> 版本: v2.0 | 适用: liankebao-weapp (Taro) + AI数字名片H5
> AppID: `wxb4f6d89904200fd2`
> 服务器: 47.116.116.87 | 域名: liankebao.top
> 预估耗时: 30-45分钟（不含微信审核等待时间）

---

## 目录

1. [准备阶段](#1-准备阶段)
2. [微信公众平台配置](#2-微信公众平台配置)
3. [项目代码配置](#3-项目代码配置)
4. [开发者工具导入](#4-开发者工具导入)
5. [构建与上传](#5-构建与上传)
6. [提交审核与发布](#6-提交审核与发布)
7. [AI数字名片H5特殊配置](#7-ai数字名片h5特殊配置)
8. [常见问题](#8-常见问题)
9. [附录：项目结构 + 关键文件速查](#9-附录项目结构--关键文件速查)

---

## 1. 准备阶段

### 1.1 确认已完成微信认证

微信小程序需要每年认证（300元/年），未认证无法发布上线。

**检查方法**：
1. 打开 https://mp.weixin.qq.com
2. 微信扫码登录
3. 顶部导航栏点「小程序」
4. 左侧菜单 → **设置** → **基本设置**
5. 查看「认证状态」是否为 **「已认证」**

> 如果显示「未认证」或「认证已过期」：
> - 点击「去认证」
> - 填写营业执照信息
> - 支付 300 元认证费
> - 等待1-2个工作日审核

### 1.2 确认AppID

项目已配置 AppID: **wxb4f6d89904200fd2**

在公众平台 → **开发** → **开发管理** → **开发设置** 中确认 AppID 一致。

### 1.3 准备好工具

| 工具 | 用途 | 下载 |
|:-----|:------|:------|
| 微信开发者工具 | 上传代码、预览调试 | https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html |
| Node.js v18+ | 构建Taro项目 | 已安装（chainke-full 项目依赖） |
| SSH客户端 | 登录服务器配Nginx | Windows Terminal / CMD |

---

## 2. 微信公众平台配置

### 2.1 配置服务器域名白名单

> **路径**: 公众平台 → **开发** → **开发管理** → **服务器域名**

**request合法域名**（必须配，否则所有API 400+）：

| 域名 | 说明 |
|:-----|:------|
| `https://liankebao.top` | **主域名** — 小程序前端 + API |
| `https://liankebao.top` | 唯一API域名 |

**操作步骤**：
1. 在「request合法域名」输入框输入 `https://liankebao.top`
2. 点击「添加」
4. 点击「保存并发布」

**uploadFile / downloadFile 合法域名**（如需图片上传/下载）：
- 同样添加 `https://liankebao.top`

> ⚠️ 配置后需要5-10分钟生效。开发者工具中可勾选「不校验合法域名」绕过（仅开发调试时）。

### 2.2 更新用户隐私保护指引

> **路径**: 左侧菜单 → **功能** → **用户隐私保护指引**

1. 点击「更新」
2. 勾选以下收集的信息：
   ```
   ☑ 微信昵称、头像（用户资料）
   ☑ 手机号
   ☑ 位置信息（GEO诊断功能）
   ☑ 订单信息
   ```
3. 用途说明填写：
   ```
   用于用户注册登录、企业家供需匹配、AI数字名片展示、GEO诊断服务和订单管理
   ```
4. 点击「提交」

> ⚠️ 2023年9月起，隐私指引未更新 = 审核必被驳回。

### 2.3 选择服务类目

> **路径**: 左侧菜单 → **设置** → **基本设置** → **服务类目**

建议选择：
1. **工具 → 企业管理**（主业类目）
2. **商业服务 → 企业服务**（副类目）

需上传营业执照。

### 2.4 设置小程序头像和简介

> **路径**: 左侧菜单 → **设置** → **基本设置**

- **名称**: 链客宝
- **头像**: 上传项目logo（在 `D:\chainke-full\public\` 中）
- **简介**: 「AI驱动的企业家供需匹配平台 · 数字名片 · GEO诊断 · 人脉对接」

### 2.5 开通微信支付（如需交易功能）

> **路径**: 左侧菜单 → **功能** → **微信支付**

1. 点击「开通」
2. 填写商户资料（营业执照、法人信息、对公账户）
3. 经营类目：**电商平台** 或 **小程序商城**
4. 审核1-3个工作日

开通后拿到 **商户号（MCH_ID）**，在服务器上配置：

```bash
ssh opc@47.116.116.87
sudo vi /etc/systemd/system/chainke.service
# 在 [Service] 段添加:
Environment="WEIXIN_APPID=wxb4f6d89904200fd2"
Environment="MCH_ID=你的商户号"
Environment="API_KEY=你的API密钥"
Environment="NOTIFY_URL=https://liankebao.top/lkapi/pay-notify"
# 保存后:
sudo systemctl daemon-reload && sudo systemctl restart chainke
```

---

## 3. 项目代码配置

### 3.1 确认API地址

**liankebao-weapp (Taro版 — 当前主版本)**：

文件：`D:\chainke-full\liankebao-weapp\src\api\client.ts`
```typescript
const API_BASE = '/miniapp-api/api'   // ✅ 正确，不需要改
```

`/miniapp-api/api` 路径由网关（:5136）转发到后端（:8001），Nginx rewrite规则已配置。

**liankebao-miniapp (原生版 — 旧版)**：

文件：`D:\chainke-full\liankebao-miniapp\utils\api.js`
```javascript
var BASE_URL = 'https://liankebao.top/lkapi'   // ✅ 已修正
```

### 3.2 确认project.config.json

**liankebao-weapp (Taro版)**：
```json
{
  "miniprogramRoot": "dist/",          // ✅ Taro构建产物目录
  "projectname": "链客宝",
  "appid": "wxb4f6d89904200fd2",      // ✅ AppID 已配置
  "setting": {
    "packNpmManually": true,
    "packNpmRelationList": [
      {"packageJsonPath": "./package.json", "miniprogramNpmDistDir": "./dist"}
    ]
  }
}
```

> ⚠️ 缺少 `urlCheck: true`、`es6: true`、`minified: true` 等字段。上线前建议补齐：
> ```json
> "setting": {
>   "urlCheck": true,
>   "es6": true,
>   "minified": true,
>   "packNpmManually": true,
>   "packNpmRelationList": [...]
> }
> ```

**liankebao-miniapp (原生版)**：
设置已完整（urlCheck: true, es6: true, minified: true），无需修改。

### 3.3 构建Taro项目（liankebao-weapp）

```bash
# 进入weapp目录
cd D:\chainke-full\liankebao-weapp

# 安装依赖（首次或新增依赖时需要）
npm install

# 构建微信小程序版本
npm run build:weapp
# 或: npx taro build --type weapp
```

构建成功后，`dist/` 目录会生成微信小程序可识别的代码（wxml/wxss/js/json）。

### 3.4 确认 pages 注册完整

**liankebao-weapp 页面列表**（在 `src/app.config.ts` 中注册）：

| 页面路径 | 说明 |
|:---------|:------|
| pages/index/index | 首页（Banner + 供需列表） |
| pages/login/index | 微信登录页 |
| pages/mine/index | 个人中心 |
| pages/contacts/index | 人脉管理 |
| pages/contacts/detail | 人脉详情 |
| pages/orders/index | 我的订单 |
| pages/membership/index | 会员中心 |
| pages/product/index | 产品详情 |
| pages/notifications/index | 通知列表 |
| pages/activities/index | 活动时间线 |
| pages/recharge/index | 充值 |
| pages/promoter/index | 推广分润 |
| pages/search/index | 搜索 |
| pages/supply-demand/index | 供需匹配 |
| pages/admin/index | 管理后台 |
| pages/imports/index | 数据导入 |
| pages/tutorial/index | 使用教程 |

> 如果缺少页面文件（.tsx），构建时会报错，需注释或删除未完成的页面注册。

---

## 4. 开发者工具导入

### 4.1 打开微信开发者工具

双击 `D:\chainke-full\打开微信小程序.bat`（如存在），或手动打开开发者工具。

### 4.2 导入项目

**方式A：导入Taro构建版（推荐 — AI数字名片最新版）**

```
项目目录: D:\chainke-full\liankebao-weapp
AppID:    wxb4f6d89904200fd2
```

> ⚠️ 注意：开发者工具的项目目录选 `liankebao-weapp` 根目录（不是 dist/）。
> `miniprogramRoot` 已配置为 `dist/`，工具会自动识别。

**方式B：导入原生版（旧版，5个页面）**

```
项目目录: D:\chainke-full\liankebao-miniapp
AppID:    wxb4f6d89904200fd2
```

### 4.3 开发调试设置

导入后，点击顶部菜单 **详情 → 本地设置**：

```
☑ 不校验合法域名、web-view（业务域名）、TLS版本及HTTPS证书
   ← 开发调试时勾选，上传前取消勾选
☑ 启用热重载
```

---

## 5. 构建与上传

### 5.1 重新构建（确保最新代码）

```bash
cd D:\chainke-full\liankebao-weapp
npm run build:weapp
```

### 5.2 在开发者工具中预览

1. 点击工具栏 **「预览」** 按钮
2. 扫码后在手机上测试所有功能
3. 重点测试：登录、AI数字名片编辑、匹配、人脉

### 5.3 上传代码

1. 点击工具栏 **「上传」** 按钮
2. 版本号填写：`2.0.0`（或递增）
3. 版本描述（预存在 `D:\chainke-full\version_description.txt`）：

```
链客宝v2.0 — AI数字名片
功能：AI名片创建编辑、供需匹配引擎、会员体系、GEO诊断
技术栈：React + Taro + FastAPI + 网关:5136
```

4. 点击「上传」

### 5.4 上传成功确认

上传成功后，登录微信公众平台 → **版本管理**，可在「开发版本」列表中看到刚上传的版本。

---

## 6. 提交审核与发布

### 6.1 提交审核前置检查清单

- [ ] AppID已完成微信认证（认证费300元/年）
- [ ] request合法域名已配 `https://liankebao.top`
- [ ] 小程序服务类目已选择（工具-企业管理）
- [ ] 用户隐私保护指引已更新
- [ ] 开发者工具「不校验合法域名」已**取消勾选**
- [ ] 在开发者工具中已完成预览测试
- [ ] 构建产物 `dist/` 为最新版本
- [ ] AI数字名片H5的API路径已改为 `/api/`（非 `/api/v1/`）

### 6.2 提审流程

1. 登录 https://mp.weixin.qq.com
2. 左侧菜单 → **版本管理**
3. 在「开发版本」中找到刚上传的版本
4. 点击 **「提交审核」**
5. 填写配置：
   - **功能页面**: 勾选首页、AI数字名片、供需匹配
   - **测试账号**: 用微信扫码登录即可
   - **审核说明**: 「链客宝AI企业家供需匹配平台，含数字名片创建展示、供需匹配引擎、会员体系等功能」
6. 点击 **「提交审核」**

### 6.3 审核周期

| 情况 | 时间 |
|:-----|:------|
| 正常审核 | 1-7天（最快几小时） |
| 被驳回 | 看驳回原因 → 修改 → 重新提交 |
| 加急审核 | 部分类目支持加急（需付费） |

### 6.4 审核通过后发布

1. 审核通过后，会收到微信通知
2. 登录公众平台 → **版本管理** → 审核通过版本
3. 点击 **「发布」**
4. 发布范围选择 **「全量发布」**
5. 确认发布

✅ **完成**！用户可以通过微信搜索「链客宝」访问小程序。

---

## 7. AI数字名片H5特殊配置

### 7.1 了解架构

AI数字名片是 **H5页面**（非小程序原生页面），通过微信小程序的 **web-view** 组件或直接在浏览器中访问。

```
用户 → 微信小程序 → web-view → https://liankebao.top/brochure_editor.html
                                           ↓
                                  网关(:5136) → AI数字名片后端(:8003)
```

### 7.2 web-view业务域名（必须配）

AI数字名片H5页面通过小程序的 `web-view` 加载时，必须配置业务域名：

> **路径**: 公众平台 → **开发** → **开发管理** → **业务域名**

```
https://liankebao.top
```

**操作步骤**：
1. 在「业务域名」输入框输入 `https://liankebao.top`
2. 下载微信提供的校验文件 `MP_verify_xxxx.txt`
3. 上传到服务器的 `/var/www/html/` 目录：
   ```bash
   scp MP_verify_xxxx.txt opc@47.116.116.87:/var/www/html/
   ```
4. 点击「保存并发布」

> ⚠️ 不配业务域名 = web-view加载H5页面时白屏。

### 7.3 数字名片编辑器路径

AI数字名片编辑器的入口地址：
```
https://liankebao.top/brochure_editor.html
```

小程序中打开方式（在某个页面添加）：
```javascript
wx.navigateTo({
  url: '/pages/webview/index?url=https://liankebao.top/brochure_editor.html'
});
```

### 7.4 确认网关已启动

AI数字名片通过网关（:5136）代理到后端（:8003）。确保网关进程在运行：

```bash
# 在服务器上检查
curl -s http://localhost:5136/health
# 应返回 {"status": "ok"}

# 检查AI数字名片后端
curl -s http://localhost:8003/api/health
# 应返回 {"status": "ok"}
```

---

## 8. 常见问题

| # | 问题 | 原因 | 解决 |
|:-:|:-----|:------|:------|
| 1 | 预览一片空白 | 构建产物未生成或路径不对 | 先 `npm run build:weapp` 生成 dist/ |
| 2 | API报 404 | 路径多了 v1/ 或域名没配白名单 | 检查代码中 `/api/v1/` → `/api/` 改好没 |
| 3 | API报 400 (invalid url) | request域名没配白名单 | 去公众平台配 `https://liankebao.top` |
| 4 | 登录失败 code无效 | appid/secret 不匹配 | 检查服务器环境变量中的 appid |
| 5 | web-view白屏 | 业务域名没配 | 去配 `https://liankebao.top` |
| 6 | AI数字名片发布失败 | 后端(:8003)未启动 | SSH检查: `curl localhost:8003/api/health` |
| 7 | 审核被拒「类目不符」 | 类目选错了 | 改选「工具-企业管理」或「商业服务」 |
| 8 | 审核被拒「隐私指引」 | 第四步没做 | 去更新隐私保护指引 |
| 9 | 上传报错「分包过大」 | 代码体积超过2MB | 检查 dist/ 大小，压缩图片 |
| 10 | Taro构建报错 | 缺依赖或TS类型错误 | 执行 `npm install` 或 `npx taro build --type weapp 2>&1` 看具体错误 |

---

## 9. 附录：项目结构 + 关键文件速查

### 9.1 项目目录结构

```
D:\chainke-full\
├── liankebao-weapp\              ← Taro版小程序（主版本）
│   ├── project.config.json       ← 项目配置（appid/构建路径）
│   ├── src/
│   │   ├── app.config.ts         ← 页面注册表
│   │   ├── api/client.ts         ← API_BASE = '/miniapp-api/api'
│   │   └── pages/                ← 所有页面
│   └── dist/                     ← 构建产物（上传到微信的代码）
│
├── liankebao-miniapp\            ← 原生版小程序（旧版，5页面）
│   ├── project.config.json
│   ├── utils/api.js              ← BASE_URL = 'liankebao.top/lkapi'
│   └── pages/
│
├── backend\                      ← 后端FastAPI (:8001)
│   └── app/main.py               ← 路由注册（/api/ + /api/v1/ 双轨）
│
├── gateway.py                    ← 统一网关(:5136)
├── deploy/                       ← Nginx配置
│   ├── nginx.conf
│   └── nginx_lkapi_location.conf ← /lkapi/ → :8001 rewrite规则
│
└── dist/                         ← 网页版React SPA构建产物
```

### 9.2 关键文件速查

| 文件 | 用途 | 上线前需修改？ |
|:-----|:------|:--------------:|
| `liankebao-weapp/project.config.json` | 小程序appid/构建配置 | ✅ 补setting字段 |
| `liankebao-weapp/src/api/client.ts` | API_BASE | ❌ 已正确 |
| `liankebao-weapp/src/app.config.ts` | 页面注册 | ❌ 已注册17页 |
| `liankebao-miniapp/utils/api.js` | BASE_URL + 所有API调用 | ❌ 已修复 |
| `gateway.py` | :5136路由规则 | ❌ 生产已配置 |
| `deploy/nginx.conf` | 服务器Nginx配置 | ❌ 已在线上 |

### 9.3 服务器端口清单

| 端口 | 服务 | 域名路径 |
|:----:|:-----|:---------|
| 443 | Nginx HTTPS | `https://liankebao.top` |
| 5136 | 统一网关 | 转发到各后端 |
| 8001 | 链客宝主后端 | `/lkapi/` → `/api/` |
| 8003 | AI数字名片 | `/api/brochures/`、`/api/match/` |
| 5061-5063 | GEO诊断 | `/api/geo/` |

---

## 快速启动命令（复制即用）

```bash
# 1. 构建Taro小程序
cd D:\chainke-full\liankebao-weapp
npm install
npm run build:weapp

# 2. 打开开发者工具
start D:\chainke-full\打开微信小程序.bat

# 3. 确认服务器网关在线
curl -s http://localhost:5136/health

# 4. 确认AI数字名片在线
curl -s http://localhost:8003/api/health

# 5. 上传（在开发者工具中点「上传」按钮）
```

---

> **文档版本**: v2.0 (2026-06-04)
> **编写**: 白泽
> **适用小程序**: liankebao-weapp (Taro·v2) + AI数字名片H5
> **关联技能**: `spa-deployment` · `chainke-development-best-practice`
