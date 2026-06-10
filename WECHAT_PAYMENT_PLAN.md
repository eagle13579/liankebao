# 链客宝AI微信支付对接方案

> 路线：微信小程序JSAPI支付（微信支付最成熟的小程序支付方式）
> 当前状态：订单系统已建、微信登录已对接、小程序AppID已注册（wxb4f6d89904200fd2）、域名已上线（www.go-aiport.com）

---

## 一、前置准备（微信支付商户平台配置）

### 1.1 注册微信支付商户号
- 前往 [pay.weixin.qq.com](https://pay.weixin.qq.com) 申请微信支付商户号
- 需要材料：营业执照、法人身份证、对公账户、小程序AppID授权
- 审核周期：1-3个工作日

### 1.2 商户号绑定小程序
- 在商户平台 -> 产品中心 -> AppID账号管理 中关联小程序AppID `wxb4f6d89904200fd2`
- 小程序后台 -> 微信支付 -> 关联商户号

### 1.3 获取关键配置（需存入.env文件）
| 配置项 | 说明 | 获取位置 |
|--------|------|----------|
| `WXPAY_MCH_ID` | 商户号（例：1600000000） | 商户平台首页 |
| `WXPAY_API_KEY` | APIv3密钥（32位字符串） | 商户平台 -> 账户中心 -> API安全 |
| `WXPAY_API_V3_KEY` | APIv3密钥（用于证书解密） | 同上 |
| `WXPAY_SERIAL_NO` | 证书序列号 | API安全 -> 证书管理 |
| `WXPAY_NOTIFY_URL` | 支付回调地址 | 需要自己在后端提供，见下文 |

### 1.4 下载证书
- 商户平台 -> 账户中心 -> API安全 -> 申请API证书
- 下载证书文件包（cert.zip），内含：
  - `apiclient_cert.p12`（PKCS12格式）
  - `apiclient_key.pem`（私钥）
  - `apiclient_cert.pem`（公钥）
- 将 `apiclient_key.pem` 和 `apiclient_cert.pem` 放入后端项目：
  ```
  /mnt/d/链客宝AI/backend/certs/
  ├── apiclient_key.pem
  └── apiclient_cert.pem
  ```

### 1.5 配置支付回调域名（重要）
- 商户平台 -> 产品中心 -> 开发配置 -> 支付回调域名：`www.go-aiport.com`
- 如果Nginx反向代理需要正确转发 `/api/pay/notify` 路径到FastAPI

---

## 二、后端改造清单

### 2.1 新增文件清单

| # | 文件路径 | 用途 |
|---|---------|------|
| 1 | `backend/app/payment.py` | 微信支付核心模块：统一下单、签名、回调验证、退款 |
| 2 | `backend/app/routers/pay.py` | 支付路由：调起支付、支付回调、订单查询、退款 |
| 3 | `backend/app/payment_config.py` | 支付配置（从.env读取） |

### 2.2 修改文件清单

| # | 文件路径 | 改动内容 |
|---|---------|---------|
| 1 | `backend/app/models.py` | Orders表新增支付相关字段 |
| 2 | `backend/app/schemas.py` | 新增支付请求/响应Schema |
| 3 | `backend/app/routers/orders.py` | 创建订单不再mock支付参数，改为返回order_id |
| 4 | `backend/app/main.py` | 注册新的pay路由 |
| 5 | `backend/app/database.py` | 迁移脚本（新增列） |
| 6 | `backend/requirements.txt` | 新增依赖 `wechatpayv3` 或 `requests` |
| 7 | `backend/.env`（新建） | 存储微信支付敏感配置 |

### 2.3 数据库改动（models.py）

**Orders表新增字段：**

```python
class Order(Base):
    # ... 现有字段保持不变 ...

    # === 新增：微信支付相关字段 ===
    payment_status = Column(String(20), nullable=False, default="pending")
    # pending/paid/refunded/closed

    transaction_id = Column(String(64), nullable=True, index=True)
    # 微信支付系统生成的订单号（transaction_id）

    prepay_id = Column(String(64), nullable=True)
    # 预支付ID（用于小程序调起支付）

    paid_at = Column(DateTime, nullable=True)
    # 支付完成时间

    refund_id = Column(String(64), nullable=True)
    # 退款单号（微信侧）

    refunded_at = Column(DateTime, nullable=True)
    # 退款完成时间
```

**注意：** `payment_status` 与现有的 `status` 字段是两套逻辑——
- `status`：业务订单状态（pending/paid/shipped/received/refunded）
- `payment_status`：支付资金状态（pending/paid/refunded/closed）
- 关系：`payment_status=paid` 时 `status` 才能变成 `paid`

### 2.4 支付核心模块（payment.py）设计

需要实现的核心函数：

```
wechatpay_unified_order(order_id, total_fee, description, openid)
  -> 返回 prepay_id

wechatpay_sign_params(prepay_id, appid)
  -> 返回小程序调起支付所需的6个参数包

verify_payment_notification(request_body, request_headers)
  -> 验证签名，返回解密后的支付结果

wechatpay_refund(order_id, refund_fee, total_fee, transaction_id)
  -> 发起退款

query_order(transaction_id)
  -> 查询订单支付状态
```

### 2.5 支付路由设计（routers/pay.py）

需要新增的API端点：

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| POST | `/api/pay/unified-order` | 统一下单（生成prepay_id并签名） | 需登录 |
| POST | `/api/pay/notify` | 微信支付结果回调（需对外开放） | 无需认证 |
| GET | `/api/pay/query/{order_id}` | 查询订单支付状态 | 需登录 |
| POST | `/api/pay/refund` | 发起退款 | 需管理员/产品方 |

#### 端详：POST /api/pay/unified-order

请求体：
```json
{
  "order_id": 123
}
```

处理流程：
1. 验证订单属于当前用户
2. 检查订单状态为pending
3. 获取用户的wechat_openid
4. 调用微信统一下单接口（金额单位：分）
5. 生成小程序调起支付的签名参数
6. 返回prepay_id、paySign等参数给前端

返回体：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "timeStamp": "1234567890",
    "nonceStr": "xxxxxxxx",
    "package": "prepay_id=wx1234567890",
    "signType": "RSA",
    "paySign": "xxxxxx"
  }
}
```

#### 端详：POST /api/pay/notify

- 这是微信服务器主动调用的回调接口
- 无需JWT认证，但要验证微信签名
- 处理逻辑：
  1. 验证签名
  2. 解析通知数据
  3. 更新订单 `payment_status=paid`, `transaction_id`, `paid_at`
  4. 更新业务 `status` 为 `paid`
  5. 返回 `{"code": "SUCCESS", "message": "OK"}` 给微信

### 2.6 创建订单流程改造（orders.py）

当前 `create_order` 直接返回mock支付参数，需要改为：

```
1. 创建订单（status=pending, payment_status=pending）
2. 返回 order_id 给前端
3. 前端拿着 order_id 去调 /api/pay/unified-order
```

### 2.7 requirements.txt 新增依赖

```
# 微信支付（推荐使用官方SDK或纯HTTP实现）
wechatpayv3==0.1.8
# 或
cryptography==41.0.0   # 用于证书签名（如果手写实现）
httpx==0.27.0          # 已有，用于HTTP请求
```

---

## 三、前端（小程序）改造清单

### 3.1 新增页面/文件

| # | 文件路径 | 用途 |
|---|---------|------|
| 1 | `pages/payment/index.wxml` | 支付中间页 |
| 2 | `pages/payment/index.js` | 调起微信支付逻辑 |
| 3 | `pages/payment/index.json` | 页面配置 |
| 4 | `pages/payment/index.wxss` | 页面样式 |
| 5 | `pages/order-result/index.wxml` | 支付结果页 |
| 6 | `pages/order-result/index.js` | 支付结果逻辑 |
| 7 | `pages/order-result/index.json` | 页面配置 |
| 8 | `pages/order-result/index.wxss` | 页面样式 |

### 3.2 修改文件清单

| # | 文件路径 | 改动内容 |
|---|---------|---------|
| 1 | `app.json` | 注册新页面路径 |
| 2 | `utils/api.js` | 新增微信支付相关的API方法 |
| 3 | `pages/product/index.js` | 购买按钮：下单后跳转支付页而非订单列表 |
| 4 | `pages/orders/index.js` | 待付款订单的「去付款」按钮改为调起支付 |

### 3.3 支付中间页逻辑（pages/payment/index.js）

```
1. 接收 order_id 参数
2. 调后端 /api/pay/unified-order 获取支付参数
3. 调用 wx.requestPayment() 调起微信支付面板
4. 根据支付结果跳转结果页或提示重试

核心调用代码：

// 调起微信支付
wx.requestPayment({
  timeStamp: res.data.timeStamp,
  nonceStr: res.data.nonceStr,
  package: res.data.package,
  signType: res.data.signType,
  paySign: res.data.paySign,
  success: function(payRes) {
    // 支付成功，跳转到结果页
    wx.redirectTo({
      url: '/pages/order-result/index?status=success&order_id=' + orderId
    })
  },
  fail: function(err) {
    // 支付失败或取消
    wx.redirectTo({
      url: '/pages/order-result/index?status=fail&order_id=' + orderId
    })
  }
})
```

### 3.4 产品详情页购买流程改造

当前 `handleBuy` 下单后直接跳订单列表，改为：

```
1. 调 api.post('/orders', {...})
2. 成功后获取 order_id
3. 跳转到支付中间页：wx.navigateTo({ url: '/pages/payment/index?order_id=' + orderId })
```

### 3.5 订单列表页「去付款」改造

当前 `handlePay` 直接调用状态更新，改为调起微信支付：

```
1. 获取 order_id
2. 跳转到支付中间页
3. 支付页面自动调后台统一下单并调起支付
```

---

## 四、实施步骤（按执行顺序）

### Step 1：环境准备
- [ ] 注册微信支付商户号（等待审核通过）
- [ ] 下载API证书和密钥
- [ ] 创建 `backend/certs/` 目录，放入证书文件
- [ ] 创建 `backend/.env` 文件，写入微信支付配置
- [ ] 商户平台配置支付回调域名

### Step 2：后端数据库改动
- [ ] 修改 `models.py` 中 Order 类，新增支付字段
- [ ] 执行数据库迁移（删除旧db或手动ALTER TABLE）
- [ ] 修改 `schemas.py`，新增支付相关Schema
- [ ] 修改 `OrderResponse` 包含新字段

### Step 3：后端支付模块开发
- [ ] 创建 `backend/app/payment_config.py`（读取.env配置）
- [ ] 创建 `backend/app/payment.py`（核心支付逻辑）
- [ ] 创建 `backend/app/routers/pay.py`（支付路由）
- [ ] 安装依赖 `pip install wechatpayv3 cryptography`

### Step 4：后端订单流程调整
- [ ] 修改 `orders.py` create_order（只创建订单，不mock支付）
- [ ] 修改 `orders.py` 状态流转（pending -> paid 由支付回调触发）

### Step 5：后端注册新路由
- [ ] 修改 `main.py`，注册 `pay.router`

### Step 6：后端部署与验证
- [ ] 部署后端
- [ ] 用curl测试 `/api/pay/unified-order` 和 `/api/pay/notify` 能通
- [ ] 检查Nginx是否转发正确

### Step 7：前端页面开发
- [ ] 创建支付中间页（payment）
- [ ] 创建支付结果页（order-result）
- [ ] 注册新页面到app.json

### Step 8：前端购买流程改造
- [ ] 修改产品详情页的handleBuy
- [ ] 修改订单列表页的handlePay
- [ ] 修改utils/api.js（如需新增方法）

### Step 9：联调测试
- [ ] 开发者工具中「真机调试」测试支付流程
- [ ] 测试支付成功、支付取消、支付失败三种场景
- [ ] 测试支付回调正确更新订单状态

### Step 10：发布上线
- [ ] 小程序提审（注意：微信支付相关功能需要小程序发布后才能完全验证）
- [ ] 商户平台提交支付验证

---

## 五、状态流转图（改造后）

```
                  ┌───────────────┐
                  │  创建订单      │
                  │ status=pending │
                  │ pay_status=   │
                  │   pending     │
                  └───────┬───────┘
                          │
                  调起微信支付
                          │
                          ▼
                  ┌───────────────┐
                  │  支付回调成功  │
                  │ status=paid   │  ← payment.py notify 更新
                  │ pay_status=   │
                  │   paid        │
                  │ transaction_id│
                  │ paid_at       │
                  └───────┬───────┘
                          │
                ┌────────┴────────┐
                ▼                 ▼
        ┌──────────────┐  ┌──────────────┐
        │ 发货(产品方)  │  │ 退款(买家)   │
        │ status=      │  │ pay_status=  │
        │ shipped      │  │ refunded    │
        └──────┬───────┘  │ refunded_at │
               ▼           └──────────────┘
        ┌──────────────┐
        │ 确认收货     │
        │ status=      │
        │ received     │
        └──────────────┘
```

---

## 六、安全注意事项

1. **签名验证不可跳过**：支付回调必须验证微信签名，防止伪造通知
2. **金额单位**：微信支付金额单位是**分**（整数），后端需做 `total_price * 100` 转换
3. **幂等处理**：支付回调可能多次收到，需用 `transaction_id` 做幂等判断
4. **敏感信息**：API密钥、证书不要提交到Git仓库，使用.env + .gitignore
5. **超时处理**：prepay_id有效期2小时，超时需重新调统一下单
6. **退款权限**：退款接口需严格鉴权，仅管理员或产品方有权发起

---

## 七、附录：参考文档

- [微信支付JSAPI开发文档](https://pay.weixin.qq.com/wiki/doc/apiv3/open/pay/chapter2_7_0.shtml)
- [小程序调起支付API](https://developers.weixin.qq.com/miniprogram/dev/api/payment/wx.requestPayment.html)
- [微信支付回调通知](https://pay.weixin.qq.com/wiki/doc/apiv3/apis/chapter3_1_5.shtml)
- [退款接口文档](https://pay.weixin.qq.com/wiki/doc/apiv3/apis/chapter3_1_9.shtml)

---

## 八、改动文件速查清单（共约13个文件）

```
后端（8个文件）：
  [新] backend/app/payment.py              — 微信支付核心逻辑
  [新] backend/app/payment_config.py       — 支付配置
  [新] backend/app/routers/pay.py          — 支付路由
  [改] backend/app/models.py               — Orders表新增4个字段
  [改] backend/app/schemas.py              — 新增支付Schema
  [改] backend/app/routers/orders.py       — 创建订单返回order_id
  [改] backend/app/main.py                 — 注册pay路由
  [改] backend/requirements.txt            — 新增依赖

前端（5个文件）：
  [新] pages/payment/index.*               — 支付中间页
  [新] pages/order-result/index.*          — 支付结果页
  [改] app.json                            — 注册新页面
  [改] pages/product/index.js              — 购买后跳支付
  [改] pages/orders/index.js              — 去付款调支付
```
