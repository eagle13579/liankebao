# 链客宝 微信小程序 — 提审前必做清单

> 链客宝 v1.0.0 · appid: wxb4f6d89904200fd2 · 交易类小程序
> 生成时间: 2026-05-16 13:50
> [D:\链客宝\scripts\miniapp_review_helper.py]

---

## □ 第一关：微信公众平台配置（你必须在 mp.weixin.qq.com 操作）

### □ 1.1 填写订单中心 path
- 登录 [微信公众平台](https://mp.weixin.qq.com) → 功能 → 小程序订单中心
- 填写: `pages/orders/index`
- **交易类小程序必填，缺了审核不通过**

### □ 1.2 配置服务器域名
- 开发管理 → 服务器域名 → request 合法域名
- 必填: `https://www.go-aiport.com` 或 `https://www.go-aiport.com/lkapi`
- 如用 go-aiport.com: 必须先加 nginx /lkapi/ 路由

### □ 1.3 用户隐私保护指引
- 功能 → 用户隐私保护指引 → 点击「更新」
- 声明收集范围：
  - 微信昵称、头像（wx.login 获取用户信息）
  - 手机号（用户注册/下单）
  - 收货地址（物流需求）
  - 订单信息
  - 以上均用于产品展示和交易履约

### □ 1.4 开通微信支付（如需完整交易）
- 功能 → 微信支付 → 申请开通
- 绑定商户号 → 配置支付回调URL

### □ 1.5 服务类目审核
- 设置 → 基本设置 → 服务类目
- 建议选：商业服务 → 企业管理/商务服务

---

## □ 第二关：代码合规自检（自动化可验证）

### □ 2.1 隐私弹窗
- 检查：登录/注册页是否有 wx.getPrivacySetting / 隐私授权弹窗
- 当前状态: ✅ 有用户服务协议弹窗
- 建议：为微信隐私新规添加 onNeedPrivacyAuthorization 回调

### □ 2.2 小程序代码审查
- 当前共 9 个页面
- 页面清单: pages/index/index, pages/login/index, pages/register/index, pages/product/index, pages/pool/index, pages/orders/index, pages/promotion/index, pages/manage-products/index, pages/mine/index
- 全部页面均已注册到 app.json

---

## □ 第三关：功能测试

### □ 3.1 注册流程
- 同意用户协议勾选框 ✅
- 微信一键登录 ✅
- 验证：使用测试账号 buyer1 / 123456 成功登录

### □ 3.2 产品浏览
- 首页产品列表展示 ✅
- 产品详情页：价格/描述/供应商/购买按钮 ✅
- 产品池搜索 ✅

### □ 3.3 下单流程
- 选择产品 → 立即购买 → 填写信息 → 提交 ✅
- 查看订单状态 ✅

### □ 3.4 推广员功能
- 推广码生成 → 分享 → 佣金查看 ✅

### □ 3.5 管理员后台
- 产品审核 → 订单管理 → 结算 ✅

---

## □ 第四关：提审前最终确认

- [ ] 后端 :8000 服务正常运行
- [ ] go-aiport.com nginx 已配置 /lkapi/ 路由
- [ ] SSL 证书有效（HTTPS正常）
- [ ] 测试账号均可使用
- [ ] 种子数据已初始化
- [ ] 版本描述已填写（见 version_description.txt）
- [ ] 图片截图已准备（至少3-5张关键页面）
- [ ] 隐私保护指引已更新
- [ ] 订单中心 path 已配置
- [ ] 无 console.log / 调试代码残留

---

生成工具: D:\链客宝\scripts\miniapp_review_helper.py
