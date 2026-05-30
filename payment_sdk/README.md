# liankebao-payment-sdk

**链客宝支付模块独立 SDK** — 微信支付 V2/V3、支付宝（预留）

---

## 概述

`liankebao-payment-sdk` 是链客宝支付模块的独立 pip 包，从 `backend/payment/` 核心逻辑提取。

遵循 **ADR-002 方案C**，实现支付模块独立 SDK 化。

### 设计原则

| 原则 | 说明 |
|------|------|
| **C-PAY-001** | 不依赖 `backend/app/` 下的任何业务模块 |
| **C-PAY-002** | 纯函数 + 依赖注入，不持有全局状态 |
| **C-PAY-003** | 从现有 `payment/` 目录提取核心逻辑，不是重写 |

---

## 安装

```bash
# 从本地安装
pip install D:/链客宝/payment_sdk/

# 开发模式安装
pip install -e D:/链客宝/payment_sdk/

# 仅在虚拟环境中依赖
pip install httpx cryptography
```

---

## 快速开始

### 1. 配置

```python
from payment_sdk import WxPayConfig

# 从环境变量加载（支持 WXPAY_* 和 WECHAT_* 前缀）
config = WxPayConfig.from_env()

# 或手动构造
config = WxPayConfig(
    app_id="wx1234567890abcdef",
    mch_id="1600000001",
    api_key="your_v2_api_key_32chars",
)
```

### 2. 微信 V3 支付

```python
import asyncio
from payment_sdk import WxPayV3Provider, WxPayConfig

async def main():
    provider = WxPayV3Provider(config=WxPayConfig.from_env())

    # 统一下单
    result = await provider.pay(
        openid="o12345",
        out_trade_no="ORDER20260001",
        total_fee=100,  # 单位：分
        description="测试商品",
    )

    if result.success:
        print("预支付ID:", result.provider_order_id)
        print("调起支付参数:", result.data["payment_params"])
    else:
        print("失败:", result.message)

asyncio.run(main())
```

### 3. 微信 V2 支付

```python
from payment_sdk import WxPayV2Provider

provider = WxPayV2Provider(config=WxPayConfig.from_env())
result = await provider.pay(
    openid="o12345",
    out_trade_no="ORDER20260001",
    total_fee=100,
    description="测试商品",
)
```

### 4. 回调验签

```python
from payment_sdk import WxPayV3Provider

provider = WxPayV3Provider(config=WxPayConfig.from_env())

result = await provider.callback_verify(
    body=request_body_bytes,
    headers={
        "Wechatpay-Signature": "...",
        "Wechatpay-Serial": "...",
        "Wechatpay-Timestamp": "...",
        "Wechatpay-Nonce": "...",
    },
    platform_cert_map={"SERIAL_NO": b"-----BEGIN PUBLIC KEY-----\n..."},
)

if result.verified:
    print("回调数据:", result.data)
```

---

## API 参考

### IPaymentProvider 接口

所有支付提供者实现此接口:

| 方法 | 参数 | 返回 |
|------|------|------|
| `pay()` | openid, out_trade_no, total_fee, description | `PaymentResult` |
| `refund()` | out_trade_no, out_refund_no, refund_amount, total_amount | `PaymentResult` |
| `query()` | out_trade_no | `PaymentResult` |
| `callback_verify()` | body, headers | `CallbackResult` |

### 内置提供者

| 类 | 协议 | 状态 |
|----|------|------|
| `WxPayV2Provider` | 微信支付 V2 (XML+MD5) | ✅ 完整实现 |
| `WxPayV3Provider` | 微信支付 V3 (JSON+RSA) | ✅ 完整实现 |
| `AliPayProvider` | 支付宝 (预留) | 🚧 仅回调验签 |

### 结果类型

- **PaymentResult**: `success`, `code`, `message`, `data`, `provider_order_id`, `out_trade_no`
- **CallbackResult**: `verified`, `data`, `raw`, `message`

### 配置数据类

- **WxPayConfig**: `app_id`, `mch_id`, `api_key`, `api_v3_key`, `private_key_path`, `cert_serial_no`, `notify_url`, `refund_notify_url`, `cert_path`, `root_ca_path`
- **AliPayConfig**: `app_id`, `private_key`, `alipay_public_key`, `gateway`, `charset`, `sign_type`, `notify_url`

---

## 目录结构

```
payment_sdk/
├── __init__.py                  # 包初始化，导出所有公开 API
├── config.py                    # 配置数据类 (WxPayConfig, AliPayConfig)
├── sign.py                      # 签名工具 (RSA/MD5/HMAC-SHA256/AES-GCM)
├── http_delegate.py             # HTTP 委托抽象层 (httpx)
├── payment_provider.py          # 抽象接口 IPaymentProvider + 结果类型
├── providers/
│   ├── __init__.py              # 提供者导出
│   ├── wxpay_v2.py              # 微信支付 V2 实现
│   ├── wxpay_v3.py              # 微信支付 V3 实现
│   └── alipay.py                # 支付宝 (预留桩)
├── tests/
│   ├── __init__.py
│   ├── test_payment_provider.py # 接口约定测试
│   ├── test_wxpay_v2.py         # V2 提供者测试
│   ├── test_wxpay_v3.py         # V3 提供者测试
│   ├── test_config.py           # 配置数据类测试
│   └── test_sign.py             # 签名工具测试
├── pyproject.toml               # pip 包配置 (推荐)
├── setup.py                     # pip 包配置 (兼容)
└── README.md                    # 本文件
```

---

## 与 backend/payment/ 的关系

| 原模块 | SDK 位置 | 变更 |
|--------|----------|------|
| `payment/config.py` | `config.py` | 移除全局注册中心 / ContextVar / FastAPI 中间件 |
| `payment/sign.py` | `sign.py` | 原样提取 |
| `payment/http_delegate.py` | `http_delegate.py` | 原样提取 |
| `payment/wxpay/__init__.py` | `providers/wxpay_v2.py` + `providers/wxpay_v3.py` | 拆分为 V2/V3，实现 IPaymentProvider 接口 |
| `payment/alipay/__init__.py` | `providers/alipay.py` | 提取为预留桩 |
| `payment/__init__.py` | `__init__.py` | 精简导出 |

---

## 测试

```bash
# 安装测试依赖
pip install -e .[dev]

# 运行所有测试
cd D:/链客宝/payment_sdk/
python -m pytest tests/ -v

# 指定测试文件
python -m pytest tests/test_wxpay_v2.py -v

# 覆盖率
python -m pytest tests/ --cov=payment_sdk -v
```

注意: 所有测试均使用 mock，不依赖外部网络 (C-PAY-002)。

---

## 许可证

Proprietary — 链客宝团队
