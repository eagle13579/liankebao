# 链客宝微信小程序上线 Checklist

## 1. 微信公众平台准备

### AppID
- 当前项目已配置 AppID: **wxb4f6d89904200fd2**
- 确认该AppID已完成微信认证（需300元/年认证费）
- 如未认证/续费，请登录 https://mp.weixin.qq.com/ 进行认证

### 小程序类目审核
- 根据链客宝"企业家供需匹配平台"定位，建议选择类目：
  - 工具 > 企业管理
  - 商业服务 > 企业服务
- 确保营业执照等相关资质已上传

---

## 2. 服务器域名白名单配置

登录微信公众平台 -> 开发 -> 开发设置 -> 服务器域名：

### request 合法域名（必须）
| 域名 | 说明 |
|------|------|
| `https://www.go-aiport.com` | 生产环境API及前端域名 |
| `https://47.100.160.250` | 当前开发用IP（上线后建议移除） |

### uploadFile 合法域名（如需文件上传）
| 域名 | 说明 |
|------|------|
| `https://www.go-aiport.com` | 上传接口所在域名 |

### downloadFile 合法域名（如需下载）
| 域名 | 说明 |
|------|------|
| `https://www.go-aiport.com` | 下载接口所在域名 |

### socket 合法域名（如未来需要）
- 暂无，保留空

> 注意：微信小程序只允许请求已配置白名单的域名。配置后需等待约5分钟生效。

---

## 3. 代码修改清单（上线前必须完成）

### 3.1 API地址改为域名
**文件**: `/mnt/d/链客宝/liankebao-miniapp/utils/api.js`
- 当前：`var API_BASE = 'https://47.100.160.250/api'`
- 改为：`var API_BASE = 'https://www.go-aiport.com/api'`

### 3.2 project.config.json 上线设置
**文件**: `/mnt/d/链客宝/liankebao-miniapp/project.config.json`
- `"urlCheck": true` (保持true，上线时校验域名)
- `"minified": true` (建议改为true，压缩代码)
- `"es6": true` (建议改为true，启用ES6转ES5)

### 3.3 新增推广中心页面（小程序缺失）
当前小程序 mine 页面有"推广收益"入口但无跳转目标页。需新增：
- `pages/promotion/index` 推广中心页面
- 在 `app.json` 中注册该页面路径

---

## 4. 小程序代码目录结构

```
liankebao-miniapp/
├── app.js                  # 入口文件 ✓
├── app.json                # 全局配置（5个页面） ✓
├── app.wxss                # 全局样式 ✓
├── project.config.json     # 项目配置（含AppID: wxb4f6d89904200fd2） ✓
├── project.private.config.json  # 私人配置 ✓
├── sitemap.json            # 站点地图 ✓
├── utils/
│   └── api.js              # API客户端（需修改API地址）
├── pages/
│   ├── index/              # 首页 - 产品列表 ✓
│   │   ├── index.js
│   │   ├── index.json
│   │   ├── index.wxml
│   │   └── index.wxss
│   ├── login/              # 登录页 ✓
│   │   ├── index.js
│   │   ├── index.json
│   │   ├── index.wxml
│   │   └── index.wxss
│   ├── product/            # 产品详情 ✓
│   │   ├── index.js
│   │   ├── index.json
│   │   ├── index.wxml
│   │   └── index.wxss
│   ├── orders/             # 我的订单 ✓
│   │   ├── index.js
│   │   ├── index.json
│   │   ├── index.wxml
│   │   └── index.wxss
│   └── mine/               # 个人中心 ✓
│       ├── index.js
│       ├── index.json
│       ├── index.wxml
│       └── index.wxss
└── components/
    └── productCard/        # 产品卡片组件 ✓
        ├── productCard.js
        ├── productCard.wxml
        └── productCard.wxss
```

### app.json 页面注册清单
| 页面路径 | 状态 | 说明 |
|----------|------|------|
| `pages/index/index` | ✓ 已注册 | 首页 |
| `pages/login/index` | ✓ 已注册 | 登录页 |
| `pages/product/index` | ✓ 已注册 | 产品详情 |
| `pages/orders/index` | ✓ 已注册 | 我的订单 |
| `pages/mine/index` | ✓ 已注册 | 个人中心 |

> 全部5个页面均已在 app.json 中正确注册。

### components 组件清单
| 组件路径 | 状态 | 说明 |
|----------|------|------|
| `components/productCard/productCard` | ✓ 已创建 | 产品卡片组件 |

---

## 5. 上传与提审流程

### 5.1 上传代码
1. 打开微信开发者工具
2. 选择项目：`D:\链客宝\liankebao-miniapp`
3. 点击工具右上角 **"上传"** 按钮
4. 填写版本号（建议：`1.0.0`）
5. 填写更新说明（如："初始版本，包含产品展示、购买、订单管理功能"）

### 5.2 提交审核前置条件
- [ ] AppID已完成微信认证（认证费300元/年）
- [ ] 服务器域名白名单已配置（www.go-aiport.com）
- [ ] 小程序服务类目已选择
- [ ] 小程序头像、名称、简介已设置
- [ ] API地址已从IP改为域名
- [ ] 已配置SSL证书（后端已通过Nginx代理，https正常）
- [ ] 已清除开发者工具本地设置中的"不校验合法域名"勾选
- [ ] 在开发者工具中完成本地预览测试
- [ ] 体验版二维码测试通过

### 5.3 提审步骤
1. 登录微信公众平台 (https://mp.weixin.qq.com/)
2. 进入 **版本管理** -> **提交审核**
3. 选择已上传的版本
4. 填写审核描述（说明小程序功能、测试账号等）
5. 提交审核（通常1-7个工作日内完成）

### 5.4 发布上线
1. 审核通过后，进入 **版本管理**
2. 点击 **"发布"** 按钮
3. 选择 **"全量发布"** 或 **"分批发布"**
4. 确认发布

---

## 6. 上线后检查

- [ ] 通过微信搜索可找到小程序
- [ ] 所有页面加载正常
- [ ] 产品列表正常显示
- [ ] 下单流程正常
- [ ] 微信支付功能正常
- [ ] 订单状态流转正确
- [ ] 个人中心功能正常

---

## 7. 已知问题与风险

1. **API地址硬编码**：当前 `api.js` 中 API_BASE 直接写死IP地址，需要改为域名
2. **缺少推广中心页面**：个人中心有"推广收益"入口，但无对应页面
3. **微信登录后端对接**：后端 `/auth/wechat-login` 接口需要微信小程序的appid和secret
4. **支付功能**：当前下单是直接调用API，未集成微信支付
5. **HTTPS证书**：请确认 go-aiport.com 已配置有效SSL证书

---

*生成日期：2026-05-10*
*文档版本：v1.0*
