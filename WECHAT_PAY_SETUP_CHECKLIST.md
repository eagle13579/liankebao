# 链客宝AI微信支付商户号注册 + 证书配置操作指南

> **目标**: 从 mock 模式切换到真实微信支付
> **前提**: 小程序已注册（AppID: wxb4f6d89904200fd2），后端代码已统一（P0-1完成）
> **预计总耗时**: 注册审核 1-3 工作日 + 配置部署 30 分钟
> **最后更新**: 2026-05-24

---

## 目录

1. [注册微信支付商户号](#1-注册微信支付商户号)
2. [获取 APIv3 密钥和证书](#2-获取-apiv3-密钥和证书)
3. [部署证书到服务器](#3-部署证书到服务器)
4. [配置环境变量](#4-配置环境变量)
5. [验证支付流程](#5-验证支付流程)
6. [附录：常见问题](#6-附录常见问题)

---

## 1. 注册微信支付商户号

> 详细步骤已在 `微信支付商户号注册SOP.md` 中说明，这里给出精简版。

### 1.1 准备材料清单

| 材料 | 说明 | 注意事项 |
|:-----|:-----|:---------|
| 营业执照 | 彩色照片或扫描件 | 四角完整、无反光 |
| 法人身份证 | 正反面彩色照片 | 在有效期内 |
| 对公银行账户 | 开户行、账号 | 个体户可用法人个人银行卡 |
| 法人实名手机号 | 接收验证码 | 必须运营商实名认证 |
| 邮箱 | 未注册过微信支付的邮箱 | 接收审核通知 |
| 小程序 AppID | `wxb4f6d89904200fd2` | 已注册，直接使用 |

### 1.2 注册操作

```bash
# 打开浏览器访问
https://pay.weixin.qq.com/

# 点击右上角「注册微信支付商户号」
# 选择「我是普通商户」→「微信小程序」
# 输入 AppID: wxb4f6d89904200fd2
```

### 1.3 关键填写项

| 字段 | 填写值 |
|:-----|:-------|
| 商户简称 | 链客宝AI |
| 经营类目 | 综合电商/电子商务平台（费率 0.6%） |
| 经营场景 | 小程序 |
| 结算周期 | T+1 |
| 绑定 AppID | `wxb4f6d89904200fd2` |

### 1.4 审核通过后绑定小程序

1. 登录 pay.weixin.qq.com → **产品中心** → **AppID账号管理**
2. 点击「关联AppID」，输入 `wxb4f6d89904200fd2`
3. 小程序管理员微信确认同意
4. 登录 mp.weixin.qq.com → **功能** → **微信支付** → 确认关联

---

## 2. 获取 APIv3 密钥和证书

> 微信支付 V3 API 需要：APIv3 密钥（32位） + 商户API证书（apiclient_key.pem）

### 2.1 设置 APIv3 密钥

```
登录 pay.weixin.qq.com → 账户中心 → API安全 → APIv3密钥
```

- 点击「设置密钥」
- 输入一个 **32位随机字符串**（字母+数字，大小写敏感）
- 建议用密码管理器生成，或执行：
  ```bash
  # 生成 32 位随机密钥（在本地终端执行）
  openssl rand -hex 16
  ```
- **保存好！此密钥只在设置时可见一次**

### 2.2 获取商户证书（apiclient_key.pem + apiclient_cert.pem）

```
登录 pay.weixin.qq.com → 账户中心 → API安全 → 证书管理
```

操作步骤：
1. 点击「下载证书」
2. 下载得到一个 `cert.zip` 压缩包
3. 解压后包含以下文件：
   ```
   cert/
   ├── apiclient_cert.pem    # 商户证书（公钥）
   ├── apiclient_key.pem     # 商户私钥（⚠️ 绝对保密！）
   └── ── 其他文件
   ```

### 2.3 查看证书序列号

```
登录 pay.weixin.qq.com → 账户中心 → API安全 → 证书管理
```

- 在证书列表中查看「证书序列号」
- 或者通过 openssl 查看：
  ```bash
  # 在解压后的 cert/ 目录中执行
  openssl x509 -in apiclient_cert.pem -noout -serial
  # 输出: serial=XXXXXXXXXXXX   ← 这就是证书序列号
  ```

### 2.4 下载微信支付平台证书

平台证书用于回调验签。有两种方式获取：

**方式一（推荐）：启动后自动下载**
代码中的 `WxPayCallback` 会在首次处理回调时尝试从微信服务器拉取平台证书并缓存。

**方式二（手动下载）**：
```bash
# 使用微信官方工具（需安装 Python）
pip install wechatpayv3
python -c "
from wechatpayv3 import WeChatPay
pay = WeChatPay(
    appid='wxb4f6d89904200fd2',
    mchid='你的商户号',
    private_key_path='./apiclient_key.pem',
    cert_serial_no='你的证书序列号',
    api_v3_key='你的APIv3密钥'
)
certs = pay.get_certificates()
print(certs)
"
```
或从商户平台 → 账户中心 → API安全 → 证书管理 → 下载平台证书（PKCS#12/pem格式）。

---

## 3. 部署证书到服务器

### 3.1 创建证书目录

```bash
# 本地开发环境
mkdir -p /d/链客宝AI/backend/certs/
```

### 3.2 复制证书文件

将以下两个文件复制到 `certs/` 目录：

```bash
# 从解压后的目录复制
cp /path/to/apiclient_key.pem    /d/链客宝AI/backend/certs/
cp /path/to/apiclient_cert.pem   /d/链客宝AI/backend/certs/

# 如果有平台证书，也复制过来
cp /path/to/platform_cert.pem    /d/链客宝AI/backend/certs/
```

最终 `certs/` 目录结构：
```
backend/certs/
├── apiclient_key.pem        # 商户私钥（⚠️ 不要提交到 Git）
├── apiclient_cert.pem       # 商户公钥证书
└── platform_cert.pem        # 微信平台证书（下载后放入）
```

### 3.3 添加到 .gitignore

确保私钥不被提交到 Git 仓库：

```bash
# 检查 .gitignore 是否包含
echo "certs/apiclient_key.pem" >> /d/链客宝AI/.gitignore
echo "certs/*.pem" >> /d/链客宝AI/.gitignore
```

### 3.4 生产环境部署

生产环境服务器路径：`/opt/liankebao/certs/`

```bash
# 通过 scp 上传到生产服务器
scp /d/链客宝AI/backend/certs/apiclient_key.pem     user@your-server:/opt/liankebao/certs/
scp /d/链客宝AI/backend/certs/apiclient_cert.pem    user@your-server:/opt/liankebao/certs/
scp /d/链客宝AI/backend/certs/platform_cert.pem     user@your-server:/opt/liankebao/certs/

# 设置文件权限（安全考虑）
ssh user@your-server "chmod 600 /opt/liankebao/certs/apiclient_key.pem"
ssh user@your-server "chmod 644 /opt/liankebao/certs/*.pem"
```

---

## 4. 配置环境变量

### 4.1 编辑 .env 文件

```bash
# 编辑本地 .env
vim /d/链客宝AI/.env
```

### 4.2 填写以下配置项

```ini
# =============================================================================
# [支付] 微信支付 (V3) — 全部填写后开启真实支付
# =============================================================================

# 支付模式：real 为真实支付，mock 为模拟支付
PAYMENT_MODE=real

# 小程序 AppID（已固定）
WXPAY_APPID=wxb4f6d89904200fd2

# 微信支付商户号（审核通过后获得）
WXPAY_MCHID=你的商户号

# APIv3 密钥（32位，在商户平台设置的）
WXPAY_API_V3_KEY=你的32位APIv3密钥

# 证书序列号（在商户平台证书管理中查看）
WXPAY_CERT_SERIAL_NO=你的证书序列号

# 商户 API 证书私钥路径（相对于 backend/ 或绝对路径）
WXPAY_CERT_PATH=certs/apiclient_key.pem

# 微信支付平台证书路径（用于回调验签）
WXPAY_PLATFORM_CERT_PATH=certs/platform_cert.pem

# 微信支付回调通知 URL（需公网可访问）
WXPAY_NOTIFY_URL=https://www.go-aiport.com/api/recharge/callback/wxpay

# 退款回调通知 URL
WXPAY_REFUND_NOTIFY_URL=https://www.go-aiport.com/api/recharge/callback/wxpay

# 小程序 AppSecret（在 mp.weixin.qq.com 获取）
WECHAT_APP_SECRET=你的小程序AppSecret
```

> **注意**：代码同时支持 `WXPAY_*` 和 `WECHAT_*` 两种前缀，`WXPAY_*` 优先。
> 如果使用 `WECHAT_*` 前缀，命名规则是 `WECHAT_APPID`, `WECHAT_MCH_ID` 等。
> 建议统一使用 `WXPAY_*` 前缀。

### 4.3 配置字段对照表

| .env 字段 | 从哪里获取 | 用途 |
|:----------|:----------|:-----|
| `WXPAY_MCHID` | 商户平台首页「商户号」 | 商户身份标识 |
| `WXPAY_API_V3_KEY` | 账户中心→API安全→APIv3密钥 | 支付签名(AES-GCM解密) |
| `WXPAY_CERT_SERIAL_NO` | 账户中心→API安全→证书管理 | V3鉴权头中标识证书 |
| `apiclient_key.pem` | 下载的证书zip包 | V3请求签名(RSA-SHA256) |
| `platform_cert.pem` | 微信平台证书 | 回调响应验签 |
| `WXPAY_NOTIFY_URL` | https://www.go-aiport.com/api/recharge/callback/wxpay | 支付结果通知 |
| `WECHAT_APP_SECRET` | mp.weixin.qq.com → 开发 → 开发管理 | 获取 openid / session_key |

---

## 5. 验证支付流程

### 5.1 启动后端服务

```bash
cd /d/链客宝AI/backend

# 激活虚拟环境并启动
source venv_new/Scripts/activate  # Windows git-bash
# 或: .\venv_new\Scripts\activate  # Windows cmd/powershell

python start_chainke.py
# 默认监听 http://0.0.0.0:8001
```

### 5.2 检查配置是否加载

```bash
# 用 curl 检查支付配置（无需认证）
curl -s http://localhost:8001/api/payment/config | python -m json.tool

# 预期输出中包含 wxpay.configured=true
# 示例：
# {
#   "code": 200,
#   "message": "success",
#   "data": {
#     "wxpay": {
#       "app_id": "wxb4f6d89904200fd2",
#       "mch_id": "你的商户号",
#       "configured": true
#     }
#   }
# }
```

### 5.3 检查支付模式

```bash
# 查看服务端日志是否打印了支付模式
# 期望看到类似：
# INFO 支付模式: real (微信支付已配置)
# 或
# WARNING 支付模式: mock (微信支付未配置或配置不完整)
```

### 5.4 测试统一下单接口

```bash
# 需要先获取一个有效的 JWT token（登录后获得）
# 然后用 token 测试下单

# 1. 先登录获取 token（替换为实际账号）
curl -s -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "test_user", "password": "test_pass"}' \
  | python -m json.tool

# 2. 从响应中提取 token，然后测试充值预创建
# 替换 {token} 为实际 token
curl -s -X POST http://localhost:8001/api/recharge/precreate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {token}" \
  -d '{"amount": 0.01, "platform": "wxpay"}' \
  | python -m json.tool

# 预期输出（real模式）：
# {
#   "code": 200,
#   "message": "success",
#   "data": {
#     "order_id": 1,
#     "order_no": "RC1...",
#     "amount": 0.01,
#     "prepay_id": "wx...",
#     "payment_params": { ... }
#   }
# }
```

### 5.5 测试 mock 回调（验证回调逻辑）

```bash
# 先获取一个 order_no（从上一步获取）
# 然后测试 mock 回调
curl -s -X POST http://localhost:8001/api/recharge/callback/mock \
  -H "Content-Type: application/json" \
  -d '{"out_trade_no": "RC1...", "transaction_id": "test_tx_001"}' \
  | python -m json.tool

# 预期输出：
# {"code": "SUCCESS", "message": "Mock 支付成功"}
```

### 5.6 用 1 分钱测试真实支付

> 微信支付支持 0.01 元=1分测试金额，验证完整链路的正确性。

**测试流程**：

1. 确保服务器绑定了公网域名（如 `www.go-aiport.com`），或使用内网穿透工具
2. 确认 `WXPAY_NOTIFY_URL` 配置的域名能正确访问到服务器
3. 在小程序端发起充值（前端调用 `/api/recharge/precreate`）
4. 微信弹出支付确认框 → 输入支付密码
5. 支付成功后跳转回小程序
6. 检查回调日志：
   ```bash
   # 查看服务端日志，期望看到：
   # INFO  充值支付成功: order_no=RC..., user_id=..., amount=0.01, balance_after=0.01
   ```
7. 查询余额是否增加：
   ```bash
   curl -s http://localhost:8001/api/recharge/balance \
     -H "Authorization: Bearer {token}" | python -m json.tool
   ```

### 5.7 验证回调的完整测试

如果微信回调暂时无法触发，可以用 curl 模拟微信 V3 回调：

```bash
# 构造一个模拟的微信支付回调请求
# 注意：实际 V3 回调需要 Wechatpay-Signature 等头，微信服务器会带
# 这是模拟请求，仅用于测试路由可达

curl -v -X POST https://www.go-aiport.com/api/recharge/callback/wxpay \
  -H "Content-Type: application/json" \
  -H "Wechatpay-Signature: test_signature" \
  -H "Wechatpay-Serial: test_serial" \
  -H "Wechatpay-Timestamp: 1234567890" \
  -H "Wechatpay-Nonce: test_nonce" \
  -d '{"resource":{"ciphertext":"...","nonce":"...","associated_data":"..."}}'
```

**注意**: 微信回调的 `WxPayCallback.verify_and_decrypt()` 中，平台证书路径硬编码为 `/certs/wechat_platform_{serial}.pem`。如果回调验签时报错找不到平台证书，有两种方案：

**方案A**（推荐）：在 `payment/wxpay/__init__.py` 的 `_get_platform_cert` 方法中，加载 `WXPAY_PLATFORM_CERT_PATH` 指向的文件作为平台证书。

**方案B**：将平台证书按 `wechat_platform_{serial}.pem` 命名格式放到项目根 `/certs/` 目录下。

---

## 6. 附录：常见问题

### Q1: 如何从 mock 切换到 real？

答：只需设置 `PAYMENT_MODE=real` 并填充完整的微信支付环境变量。代码的 `is_real_mode()` 和 `has_config()` 两个条件都满足时会自动走真实支付。

### Q2: 证书过期怎么办？

商户 API 证书有效期通常为 5 年。过期前微信会发通知。续期流程：
1. 登录 pay.weixin.qq.com → 账户中心 → API安全 → 证书管理
2. 重新下载证书，更新 `apiclient_key.pem`
3. 更新 `WXPAY_CERT_SERIAL_NO` 为新证书序列号
4. 重启后端服务

### Q3: 回调验签失败？

| 可能原因 | 检查项 |
|:---------|:-------|
| 平台证书未下载/未放到正确位置 | 确认 `WXPAY_PLATFORM_CERT_PATH` 路径正确 |
| 证书序列号不匹配 | 确认 `WXPAY_CERT_SERIAL_NO` 与商户平台一致 |
| APIv3 密钥错误 | 确认 `WXPAY_API_V3_KEY` 为32位正确密钥 |

### Q4: 微信支付报错 "商户号未配置 APIv3 密钥"？

答：登录 pay.weixin.qq.com → 账户中心 → API安全 → APIv3密钥 → 设置密钥。

### Q5: 生产环境需要 HTTPS 吗？

答：**必须**。微信支付回调通知只接受 HTTPS 地址。链客宝AI生产域名 `www.go-aiport.com` 已配置 HTTPS。

### Q6: 调试日志怎么看？

为便于调试支付流程，可将日志级别设为 DEBUG：

```bash
# 通过 API 动态切换（需管理员 token）
curl -X PUT "http://localhost:8001/api/system/log-level?level=DEBUG" \
  -H "Authorization: Bearer {admin_token}"
```

---

## 参考文档

- [微信支付商户平台](https://pay.weixin.qq.com/)
- [微信支付 V3 API 文档](https://pay.weixin.qq.com/wiki/doc/apiv3/wxpay/pages/JSAPI.shtml)
- [微信公众平台](https://mp.weixin.qq.com/)
- [链客宝AI支付实现代码](backend/payment/) — 代码见 `payment/` 目录
- [微信支付商户号注册SOP](微信支付商户号注册SOP.md) — 更详细的注册步骤
