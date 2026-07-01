# 链客宝微信支付 V3 接入 — 设置检查清单

本文档指导完成 **微信支付商户号注册 → APIv3 密钥配置 → 证书上传 → 回调 URL 配置** 全流程，从零到生产可用。

---

## 目录

1. [前置条件](#1-前置条件)
2. [注册微信商户号](#2-注册微信商户号)
3. [开通 JSAPI 支付能力](#3-开通-jsapi-支付能力)
4. [配置 APIv3 密钥](#4-配置-apiv3-密钥)
5. [申请并下载商户证书](#5-申请并下载商户证书)
6. [配置回调 URL](#6-配置回调-url)
7. [配置链客宝环境变量](#7-配置链客宝环境变量)
8. [验证配置](#8-验证配置)
9. [生产上线检查清单](#9-生产上线检查清单)
10. [排错指南](#10-排错指南)
11. [附录: 证书序列号获取](#附录-证书序列号获取)

---

## 1. 前置条件

| 条件 | 说明 |
|------|------|
| ✅ 已认证的微信公众号 或 小程序 | 用于获取 AppID |
| ✅ 企业营业执照 | 个体户/企业均可，必须是已完成微信认证的 |
| ✅ 对公银行账户（可选） | 企业商户需要，个体户可用法人银行卡 |
| ✅ 公网 HTTPS 域名 | 用于接收微信支付回调通知 |

> **注意**: 微信支付商户号与公众号/小程序是**不同主体**也可以（服务商模式），但建议同一主体以减少审核问题。

---

## 2. 注册微信商户号

### 2.1 访问商户平台

打开 [微信支付商户平台](https://pay.weixin.qq.com/) → 点击 **"注册成为商户"**

### 2.2 选择主体类型

- **企业**: 需提供营业执照、法人身份证、对公账户
- **个体户**: 需提供营业执照、经营者身份证、法人银行卡

### 2.3 提交资料

按照页面指引填写:
1. 联系信息（管理员手机号、邮箱）
2. 经营信息（商户简称、经营类目）
3. 资质信息（上传营业执照照片）
4. 银行账户（对公账户验证）

### 2.4 审核

通常 1-3 个工作日审核完成，审核通过后登录商户平台。

### 2.5 获取商户号

登录后 → **账户中心** → **商户信息** → 查看 **"微信支付商户号"**（一串数字，如 `1230000109`）

---

## 3. 开通 JSAPI 支付能力

> JSAPI 支付 = 公众号/小程序内 H5 支付，是链客宝最常用的支付方式。

### 3.1 产品中心

商户平台 → **产品中心** → **JSAPI支付** → 点击 **"开通"**

### 3.2 关联 AppID

1. 在 JSAPI 支付详情页 → **"开发配置"**
2. 点击 **"关联 AppID"**
3. 输入你的公众号/小程序的 AppID
4. 提交后需在公众平台确认授权

### 3.3 公众平台确认授权

1. 登录 [微信公众平台](https://mp.weixin.qq.com/) 或 [小程序后台](https://mp.weixin.qq.com/)
2. 进入 **功能** → **微信支付**
3. 找到商户号关联请求，点击 **"确认"**

### 3.4 设置支付目录（重要）

在 JSAPI 支付开发配置中:
- **支付授权目录**: 填写你前端页面的 URL 目录
  - 例如: `https://yourdomain.com/wxpay/`
  - 支持通配符，但必须是 HTTPS

---

## 4. 配置 APIv3 密钥

APIv3 密钥用于:
- 回调通知 resource 的 AES-256-GCM 解密
- 平台证书的加密传输

### 4.1 设置密钥

商户平台 → **账户中心** → **API安全** → **设置APIv3密钥**

### 4.2 密钥规则

- 32 位十六进制字符（0-9, a-f）
- 例如: `a1b2c3d4e5f6789012345678abcdef90`
- **务必保存好**，设置后无法找回，只能重置

### 4.3 保存到安全位置

将密钥记录到密码管理器或安全文件中。

---

## 5. 申请并下载商户证书

### 5.1 申请证书

商户平台 → **账户中心** → **API安全** → **申请API证书**

三种方式:
1. **自动生成**（推荐）: 使用"证书工具"一键生成
2. **手动生成**: 使用 OpenSSL 生成 CSR
3. **已有证书**: 直接上传

### 5.2 使用证书工具（推荐）

1. 下载并运行 "微信支付证书工具"
2. 输入商户号，点击 "生成证书"
3. 工具会在当前目录生成:
   - `apiclient_cert.pem` — 商户证书（公钥）
   - `apiclient_key.pem` — 商户私钥（**非常重要，勿泄露**）

### 5.3 下载证书到服务器

将 `apiclient_key.pem` 安全地传输到链客宝服务器:

```bash
# 示例: 放到 /etc/wechat_certs/ 目录
scp apiclient_key.pem root@your-server:/etc/wechat_certs/
```

> **安全建议**:
> - 设置文件权限 `chmod 600 apiclient_key.pem`
> - 不要将私钥文件提交到 Git 仓库
> - 定期轮换证书（通常有效期 5 年）

### 5.4 获取证书序列号

商户平台 → **账户中心** → **API安全** → 查看已安装证书的 **"证书序列号"**

或使用命令行读取:

```bash
openssl x509 -in apiclient_cert.pem -noout -serial
```

输出类似: `serial=1234ABCD5678EF90` → 取 `=` 后面的部分: `1234ABCD5678EF90`

---

## 6. 配置回调 URL

### 6.1 确定回调地址

链客宝的微信支付回调地址为:

```
https://yourdomain.com/api/payment/wechat/notify
```

### 6.2 配置到商户平台

商户平台 → **产品中心** → **开发配置** → **支付配置** → **支付回调通知**

填写完整 URL（必须是 HTTPS）。

### 6.3 配置到代码

在 `.env` 文件中设置:

```bash
WECHAT_NOTIFY_URL=https://yourdomain.com/api/payment/wechat/notify
```

---

## 7. 配置链客宝环境变量

### 7.1 编辑 .env 文件

打开 `D:/链客宝/.env`，找到 `[支付] 微信支付 V3 SDK` 部分，取消注释并填写:

```bash
# =============================================================================
# [支付] 微信支付 V3 SDK — 取消注释并填入实际值
# =============================================================================

WECHAT_APPID=wx1234567890abcdef          # 改: 你的公众号/小程序 AppID
WECHAT_MCHID=1230000109                   # 改: 你的商户号
WECHAT_API_V3_KEY=a1b2c3d4e5f6789012345678abcdef90  # 改: 你的 APIv3 密钥
WECHAT_CERT_SERIAL=1234ABCD5678EF90       # 改: 你的证书序列号
WECHAT_CERT_PATH=/etc/wechat_certs/apiclient_key.pem  # 改: 你的私钥路径
WECHAT_NOTIFY_URL=https://yourdomain.com/api/payment/wechat/notify  # 改: 你的回调URL
```

### 7.2 可选配置

```bash
WECHAT_API_KEY=                           # APIv2 密钥 (如需 V2 兼容)
WECHAT_REFUND_NOTIFY_URL=                 # 退款回调 URL (可选)
WECHAT_PLATFORM_CERT_DIR=/tmp/wechat_certs   # 平台证书缓存目录
```

---

## 8. 验证配置

### 8.1 运行配置检查脚本

```bash
cd /path/to/liankebao
python check_wechat_config.py --verbose
```

预期输出:

```
============================================================
  链客宝 — 微信支付配置检查
============================================================

【必需配置项】
----------------------------------------
  ✓ 公众号/小程序 AppID: wx1234567890abcdef
  ✓ 微信商户号 ID: 1230000109
  ✓ APIv3 密钥: a1b2c3****
  ✓ 商户私钥证书路径: /etc/wechat_certs/apiclient_key.pem
  ✓ 支付回调通知 URL: https://yourdomain.com/api/payment/wechat/notify

【可选配置项】
----------------------------------------
  ...

【证书检查】
----------------------------------------
  ✓ 商户私钥证书存在: /etc/wechat_certs/apiclient_key.pem
  ℹ  证书序列号 (从文件读取): 1234ABCD5678EF90

【回调 URL 检查】
----------------------------------------
  ✓ 回调 URL 使用 HTTPS: https://yourdomain.com/api/payment/wechat/notify

============================================================
  ✅ 微信支付配置完整, 可以启用真实支付!
============================================================
```

### 8.2 首次启动时初始化平台证书

启动链客宝后端服务后，调用一次证书下载接口（或在代码初始化时调用）:

```python
from app.payment.wechat_pay import WeChatPay

wxpay = WeChatPay.from_env()
await wxpay.download_platform_certs()
```

> 平台证书用于验证微信回调签名的真实性。证书会自动缓存到 `WECHAT_PLATFORM_CERT_DIR` 目录，有效期内无需重复下载。

### 8.3 测试下单

调用统一下单接口:
```bash
curl -X POST https://yourdomain.com/api/payment/wxpay/unified-order \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"order_id": 1, "openid": "用户openid"}'
```

---

## 9. 生产上线检查清单

| # | 检查项 | 状态 |
|---|--------|------|
| 1 | 微信商户号已注册并通过审核 | ☐ |
| 2 | JSAPI 支付已开通，AppID 已关联 | ☐ |
| 3 | APIv3 密钥已设置 | ☐ |
| 4 | 商户证书已申请，`apiclient_key.pem` 已部署到服务器 | ☐ |
| 5 | 证书文件权限设置为 `600` | ☐ |
| 6 | 回调 URL 已配置到商户平台 | ☐ |
| 7 | `.env` 中配置已取消注释并填入正确值 | ☐ |
| 8 | `check_wechat_config.py` 运行通过 | ☐ |
| 9 | 平台证书已下载（首次调用） | ☐ |
| 10 | 回调 URL 公网可达 (用 curl 测试) | ☐ |
| 11 | HTTPS 证书有效（微信要求 TLS 1.2+） | ☐ |

---

## 10. 排错指南

### 10.1 回调验签失败

**表现**: 支付成功但系统未更新订单状态

**排查步骤**:

1. **检查回调日志**
   ```bash
   grep "wechat_notify" /var/log/liankebao/app.log
   ```

2. **检查平台证书**
   - 确保已调用 `download_platform_certs()`
   - 检查证书缓存目录是否存在正确的 PEM 文件
   - 微信平台证书会定期轮换，SDK 会自动处理

3. **序列号不匹配**
   - 回调头的 `Wechatpay-Serial` 与缓存的证书 serial 不一致
   - 重新下载平台证书即可

4. **手动验证签名** (通过微信官方工具):
   https://pay.weixin.qq.com/wiki/doc/apiv3/wechatpay/wechatpay4_1.shtml

### 10.2 下单返回签名错误

**表现**: 调用下单接口返回 `SIGN_ERROR`

**排查步骤**:

1. **检查商户证书序列号**:
   - 确保 `WECHAT_CERT_SERIAL` 与商户平台显示的序列号一致
   - 序列号格式为大写十六进制，不含空格

2. **检查私钥文件**:
   - 确认 `WECHAT_CERT_PATH` 指向 `apiclient_key.pem`（不是 `apiclient_cert.pem`）
   - 文件格式为 PEM（`-----BEGIN PRIVATE KEY-----`）

3. **检查商户号**:
   - `WECHAT_MCHID` 必须是纯数字字符串

### 10.3 回调 URL 收不到通知

**可能原因**:

1. 回调 URL 未在商户平台配置
2. URL 必须是 HTTPS（微信强制要求）
3. 服务器防火墙拦截了微信 IP 段
4. 返回给微信的 HTTP 状态码不是 200

**微信服务器 IP 段** (请加入白名单):
- 所有微信支付回调来自固定的 IP 段，可在商户平台查询
- 建议先放行全部，稳定后再限制

### 10.4 AES-GCM 解密失败

**表现**: 收到回调但解密 resource 失败

**原因**: `WECHAT_API_V3_KEY` 与商户平台配置的不一致

**解决**:
1. 在商户平台 → API安全 → APIv3密钥 → 重置密钥
2. 更新 `.env` 中的 `WECHAT_API_V3_KEY`
3. 重新下载平台证书

---

## 附录: 证书序列号获取

### 方法一: 商户平台查看

商户平台 → 账户中心 → API安全 → 已安装证书 → **证书序列号**

### 方法二: OpenSSL 命令行

```bash
openssl x509 -in /path/to/apiclient_cert.pem -noout -serial
# 输出: serial=1234ABCD5678EF90
```

### 方法三: Python 读取

```python
from cryptography import x509
from cryptography.hazmat.backends import default_backend

with open("apiclient_cert.pem", "rb") as f:
    cert = x509.load_pem_x509_certificate(f.read(), default_backend())
    serial = format(cert.serial_number, "X")
    print(f"证书序列号: {serial}")
```

---

## 参考链接

| 资源 | 链接 |
|------|------|
| 微信支付商户平台 | https://pay.weixin.qq.com/ |
| APIv3 文档 | https://pay.weixin.qq.com/wiki/doc/apiv3/wxpay/pages/api.shtml |
| 签名验证 | https://pay.weixin.qq.com/wiki/doc/apiv3/wechatpay/wechatpay4_0.shtml |
| 回调通知 | https://pay.weixin.qq.com/wiki/doc/apiv3/wechatpay/wechatpay7_0.shtml |
| 证书管理 | https://pay.weixin.qq.com/wiki/doc/apiv3/wechatpay/wechatpay3_1.shtml |

---

> **提示**: 配置过程中如有问题，请先运行 `python check_wechat_config.py -v` 查看详细诊断信息。
