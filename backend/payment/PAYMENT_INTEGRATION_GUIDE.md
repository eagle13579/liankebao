# 统一支付集成指南 (Payment Integration Guide)

> 让军团内所有产品复用链客宝 payment/ 模块，5 行代码完成支付接入。
> 版本: v1.0 | 日期: 2026-05-23

---

## 目录

1. [统一支付模块架构说明](#1-统一支付模块架构说明)
2. [快速接入模板](#2-快速接入模板)
3. [收费定价方案建议](#3-收费定价方案建议)
4. [已接入产品清单](#4-已接入产品清单)
5. [附录：环境变量参考](#5-附录环境变量参考)

---

## 1. 统一支付模块架构说明

### 1.1 模块目录结构

```
payment/                          # 统一支付模块（可独立复制使用）
├── __init__.py                   # 顶层导出：ApiConfigKit, PayKit, WxPayApi, AliPayApi 等
├── config.py                     # ApiConfigKit 多平台配置注册中心
│   ├── WxPayConfig               #   微信支付配置数据类（from_env 自动加载）
│   ├── AliPayConfig              #   支付宝配置数据类
│   ├── register()                #   注册支付配置
│   ├── get_config()              #   获取配置（支持 ContextVar 线程安全）
│   ├── has_config()              #   检查配置是否存在
│   ├── is_real_mode()            #   检查是否为真实支付模式
│   ├── init_default_config()     #   从环境变量自动初始化
│   ├── payment_platform_middleware()  # FastAPI 中间件（自动路由匹配平台）
│   ├── PLATFORM_WXPAY            #   "wxpay" 平台常量
│   └── PLATFORM_ALIPAY           #   "alipay" 平台常量
├── sign.py                       # PayKit 签名门面
│   ├── rsa_sign() / rsa_verify() #   RSA-SHA256 签名/验签（微信 V3）
│   ├── build_v3_sign_str()       #   微信 V3 签名串构建
│   ├── build_v2_sign()           #   微信 V2 XML 签名
│   ├── aes_gcm_decrypt()         #   AES-256-GCM 解密（回调 resource）
│   ├── md5() / hmac_sha256()     #   通用哈希
│   └── generate_nonce()          #   随机字符串生成
├── http_delegate.py              # HttpDelegate HTTP 抽象层
│   ├── HttpDelegate              #   httpx.AsyncClient 封装（GET/POST/PUT/DELETE）
│   ├── HttpResponse              #   统一响应封装（.json() .is_success()）
│   ├── .default()                #   工厂：默认 HTTP 委托
│   └── .with_ssl_cert()          #   工厂：双向 SSL 认证（退款用）
├── wxpay/
│   └── __init__.py               # 微信支付实现
│       ├── WxPayApi              #   统一下单 / 查询 / 退款 / 关闭
│       │   ├── create_jsapi_order()   # V3 JSAPI 下单
│       │   ├── query_by_out_trade_no() # V3 按商户单号查询
│       │   ├── create_refund()        # V3 退款
│       │   ├── close_order()          # V3 关闭订单
│       │   └── create_order_v2()      # V2 兼容下单
│       ├── WxPayAuth             #   V3 鉴权头生成 (WECHATPAY2-SHA256-RSA2048)
│       └── WxPayCallback         #   回调签名验证 + resource 解密
└── alipay/
    └── __init__.py               # 支付宝实现（框架，待完善）
        ├── AliPayApi             #   统一下单 / 验签
        └── AliPayCore            #   签名 / 验签核心
```

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **零依赖注入** | 配置从环境变量自动加载，无需手动传参 |
| **Mock 优先** | 默认 Mock 模式，`PAYMENT_MODE=real` 切换真实支付 |
| **ContextVar 线程安全** | 每个请求/协程独立平台上下文 |
| **框架无关底层** | 核心库只依赖 `httpx` + `cryptography`，上层可适配 FastAPI/Flask/纯脚本 |
| **即插即用** | 复制 `payment/` 目录到新项目，改两行配置即可运行 |

### 1.3 依赖清单

```
httpx>=0.27.0          # HTTP 客户端
cryptography>=42.0.0   # RSA / AES-GCM 加密
```

FastAPI 项目额外依赖（仅中间件使用）：
```
fastapi>=0.100.0       # 可选，仅用于 payment_platform_middleware
```

### 1.4 如何在新项目中引入

**步骤 1：复制模块**

```bash
cp -r D:\链客宝\backend\payment\ <你的项目>/backend/payment/
```

目录结构只需保留：
```
your-project/backend/
├── payment/               # 完整复制
│   ├── __init__.py
│   ├── config.py
│   ├── sign.py
│   ├── http_delegate.py
│   ├── wxpay/__init__.py
│   └── alipay/__init__.py
├── app/                   # 你的业务代码
└── requirements.txt
```

**步骤 2：安装依赖**

```bash
pip install httpx cryptography
# FastAPI 项目额外安装：
pip install fastapi uvicorn
```

**步骤 3：配置环境变量**

创建 `.env` 文件（参见 [附录：环境变量参考](#5-附录环境变量参考)）：

```bash
# 支付模式（默认 mock，生产设为 real）
PAYMENT_MODE=real

# 微信支付（WXPAY_* 和 WECHAT_* 两种前缀均支持）
WXPAY_APPID=wx1234567890abcdef
WXPAY_MCH_ID=1600000001
WXPAY_API_KEY=your_v2_api_key_32chars
WXPAY_API_V3_KEY=your_v3_api_key_32chars
WXPAY_PRIVATE_KEY_PATH=/etc/certs/apiclient_key.pem
WXPAY_CERT_SERIAL_NO=1234567890ABCDEF
WXPAY_NOTIFY_URL=https://your-domain.com/api/pay/wxpay/notify

# 或者使用 WECHAT_* 前缀（后备方案）
WECHAT_APPID=wx1234567890abcdef
```

**步骤 4：在 app 启动时注册配置**

```python
# app/main.py
from payment import init_default_config

@app.on_event("startup")
async def startup():
    init_default_config()  # 一行代码加载所有支付配置
```

**步骤 5：添加支付路由（详见下一节模板）**

---

## 2. 快速接入模板

### 2.1 FastAPI 模板（推荐）

```python
"""
FastAPI 支付接入示例 — 约 5 行核心代码

完整文件：app/routers/payment.py
"""
import uuid
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from payment import (
    ApiConfigKit,
    is_real_mode,
    has_config,
    PLATFORM_WXPAY,
    PLATFORM_ALIPAY,
    WxPayApi,
    AliPayApi,
    register,
    WxPayConfig,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pay", tags=["支付"])


# ---- 请求/响应模型 ----

class UnifiedOrderRequest(BaseModel):
    openid: str
    out_trade_no: str
    total_fee: int          # 单位：分
    description: str
    platform: str = "wxpay"  # wxpay / alipay


class UnifiedOrderResponse(BaseModel):
    success: bool
    prepay_id: str = ""
    payment_params: dict = {}
    mock: bool = False


# ---- Step 1: 注册支付配置（在 app 启动时调用一次） ----

def register_payment_config():
    """注册支付配置（启动时调用一次）"""
    if not has_config(PLATFORM_WXPAY):
        cfg = WxPayConfig.from_env()
        if cfg.is_configured:
            ApiConfigKit.register(PLATFORM_WXPAY, cfg, set_default=True)
            logger.info("微信支付配置已注册")


# ---- Step 2: 统一下单 ----

@router.post("/unified-order", response_model=UnifiedOrderResponse)
async def unified_order(req: UnifiedOrderRequest):
    """
    统一下单接口

    使用方式：
        开发环境：默认返回 Mock 数据，无需真实微信商户号
        生产环境：设置 PAYMENT_MODE=real，自动调用微信支付 API
    """
    # Mock 模式 — 返回模拟数据
    if not is_real_mode():
        mock_prepay_id = "mock_" + uuid.uuid4().hex
        return UnifiedOrderResponse(
            success=True,
            prepay_id=mock_prepay_id,
            payment_params={
                "appId": "mock_appid",
                "timeStamp": str(int(__import__("time").time())),
                "nonceStr": uuid.uuid4().hex[:32],
                "package": f"prepay_id={mock_prepay_id}",
                "signType": "RSA",
                "paySign": "mock_signature",
            },
            mock=True,
        )

    # 真实模式 — 检查配置
    if not has_config(PLATFORM_WXPAY):
        raise HTTPException(status_code=503, detail="支付配置未注册")

    # 调用微信支付 API
    api = WxPayApi()
    result = await api.create_jsapi_order(
        openid=req.openid,
        out_trade_no=req.out_trade_no,
        total_fee=req.total_fee,
        description=req.description,
    )

    if result is None:
        raise HTTPException(status_code=502, detail="统一下单失败")

    return UnifiedOrderResponse(
        success=True,
        prepay_id=result["prepay_id"],
        payment_params=result["payment_params"],
        mock=False,
    )


# ---- Step 3: 支付回调通知 ----

@router.post("/wxpay/notify")
async def wxpay_notify(request: Request):
    """
    微信支付回调通知（V3 版）
    """
    from payment import WxPayCallback

    body = await request.body()
    wechatpay_signature = request.headers.get("Wechatpay-Signature", "")
    wechatpay_serial = request.headers.get("Wechatpay-Serial", "")
    wechatpay_timestamp = request.headers.get("Wechatpay-Timestamp", "")
    wechatpay_nonce = request.headers.get("Wechatpay-Nonce", "")

    callback = WxPayCallback()
    result = callback.verify_and_decrypt(
        body,
        wechatpay_signature,
        wechatpay_serial,
        wechatpay_timestamp,
        wechatpay_nonce,
    )

    if result is None:
        return {"code": "FAIL", "message": "验签失败"}

    # 处理业务逻辑（更新订单状态等）
    out_trade_no = result.get("out_trade_no", "")
    transaction_id = result.get("transaction_id", "")
    trade_state = result.get("trade_state", "")
    logger.info(f"支付回调: out_trade_no={out_trade_no}, tx={transaction_id}, state={trade_state}")

    # 返回成功应答
    return {"code": "SUCCESS", "message": "成功"}


# ---- Step 4: 注册中间件（可选，自动设置平台上下文） ----

# 在 app/main.py 中添加：
# from payment import payment_platform_middleware
# app.middleware("http")(payment_platform_middleware)
```

**app/main.py 完整启动示例：**

```python
from fastapi import FastAPI
from payment import init_default_config, payment_platform_middleware
from app.routers.payment import router as payment_router, register_payment_config

app = FastAPI(title="我的产品", version="1.0.0")

@app.on_event("startup")
async def startup():
    init_default_config()         # 从环境变量加载配置
    register_payment_config()     # 注册到 ApiConfigKit

# 可选：自动路由平台上下文（/api/pay/wxpay/* → wxpay, /api/pay/alipay/* → alipay）
app.middleware("http")(payment_platform_middleware)

# 注册支付路由
app.include_router(payment_router)
```

### 2.2 Flask 模板（Blueprint）

```python
"""
Flask 支付接入示例 — Blueprint + before_request

完整文件：app/blueprints/payment.py
"""
import uuid
import time
from flask import Blueprint, request, jsonify, current_app

from payment import (
    has_config,
    is_real_mode,
    PLATFORM_WXPAY,
    WxPayApi,
    WxPayCallback,
    WxPayConfig,
    register,
)

# 创建 Blueprint
payment_bp = Blueprint("payment", __name__, url_prefix="/api/pay")


# ---- before_request 自动设置平台上下文 ----

@payment_bp.before_request
def set_payment_platform():
    """根据路径自动设定支付平台（可选）"""
    from payment import set_current_platform

    path = request.path
    if "/wxpay/" in path:
        set_current_platform("wxpay")
    elif "/alipay/" in path:
        set_current_platform("alipay")


# ---- 初始化（在 create_app 中调用） ----

def init_payment(app):
    """Flask 应用初始化支付模块"""
    cfg = WxPayConfig.from_env()
    if cfg.is_configured:
        register(PLATFORM_WXPAY, cfg, set_default=True)
        app.logger.info("微信支付配置已注册")
    else:
        app.logger.warning("未检测到支付配置，将使用 Mock 模式")


# ---- 统一下单 ----

@payment_bp.route("/unified-order", methods=["POST"])
def unified_order():
    """统一下单"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "请求体为空"}), 400

    # Mock 模式
    if not is_real_mode():
        mock_prepay_id = "mock_" + uuid.uuid4().hex
        return jsonify({
            "success": True,
            "prepay_id": mock_prepay_id,
            "payment_params": {
                "appId": "mock_appid",
                "timeStamp": str(int(time.time())),
                "nonceStr": uuid.uuid4().hex[:32],
                "package": f"prepay_id={mock_prepay_id}",
                "signType": "RSA",
                "paySign": "mock_signature",
            },
            "mock": True,
        })

    # 真实模式
    if not has_config(PLATFORM_WXPAY):
        return jsonify({"success": False, "message": "支付配置未注册"}), 503

    import asyncio
    api = WxPayApi()
    result = asyncio.run(api.create_jsapi_order(
        openid=data.get("openid", ""),
        out_trade_no=data.get("out_trade_no", ""),
        total_fee=data.get("total_fee", 0),
        description=data.get("description", ""),
    ))

    if result is None:
        return jsonify({"success": False, "message": "统一下单失败"}), 502

    return jsonify({
        "success": True,
        "prepay_id": result["prepay_id"],
        "payment_params": result["payment_params"],
        "mock": False,
    })


# ---- 回调通知 ----

@payment_bp.route("/wxpay/notify", methods=["POST"])
def wxpay_notify():
    """微信支付回调"""
    body = request.get_data()
    wechatpay_signature = request.headers.get("Wechatpay-Signature", "")
    wechatpay_serial = request.headers.get("Wechatpay-Serial", "")
    wechatpay_timestamp = request.headers.get("Wechatpay-Timestamp", "")
    wechatpay_nonce = request.headers.get("Wechatpay-Nonce", "")

    callback = WxPayCallback()
    result = callback.verify_and_decrypt(
        body,
        wechatpay_signature,
        wechatpay_serial,
        wechatpay_timestamp,
        wechatpay_nonce,
    )

    if result is None:
        return jsonify({"code": "FAIL", "message": "验签失败"}), 200

    current_app.logger.info(f"支付回调: {result}")
    return jsonify({"code": "SUCCESS", "message": "成功"})
```

**app/__init__.py 完整启动示例：**

```python
from flask import Flask
from app.blueprints.payment import payment_bp, init_payment

def create_app():
    app = Flask(__name__)

    # 初始化支付模块
    init_payment(app)

    # 注册蓝图
    app.register_blueprint(payment_bp)

    return app
```

### 2.3 Mock 模式 vs 真实模式行为对照

| 模式 | 环境变量 | 行为 | 适用场景 |
|------|---------|------|---------|
| **Mock** | 不设置或 `PAYMENT_MODE=mock` | 返回 `mock_xxxx` 格式的 prepay_id，不调微信 | 本地开发、CI/CD 测试 |
| **Real** | `PAYMENT_MODE=real` | 调用微信支付真实 API | 生产环境、集成测试 |

### 2.4 支付 API 能力矩阵

| 能力 | WxPayApi (V3) | WxPayApi (V2) | AliPayApi |
|------|:------------:|:------------:|:---------:|
| JSAPI 统一下单 | ✓ `create_jsapi_order()` | ✓ `create_order_v2()` | — |
| APP 下单 | — | — | ✓ `unified_order()` |
| 订单查询（商户单号） | ✓ `query_by_out_trade_no()` | ✓ | — |
| 订单查询（微信单号） | ✓ `query_by_transaction_id()` | ✓ | — |
| 关闭订单 | ✓ `close_order()` | ✓ | — |
| 退款 | ✓ `create_refund()` | ✓ | — |
| 退款查询 | ✓ `query_refund()` | ✓ | — |
| 回调验签 | ✓ `WxPayCallback` | ✓ | ✓ `verify_notify()` |

---

## 3. 收费定价方案建议

> 基于链客宝 [PRICING.md](../PRICING.md) 和 [GO_TO_MARKET.md](../GO_TO_MARKET.md) 提炼的通用定价模型。

### 3.1 三层定价体系

| 层级 | 名称 | 月付 | 年付（约） | 目标客户 |
|------|------|------|-----------|---------|
| **L1** | 按产品定价 | — | ¥9,800 / 产品/年 | 单个产品/工具 |
| **L2** | 按产品定价（旗舰版） | — | ¥19,999 / 产品/年 | 企业级产品+API |
| **L3** | 平台订阅 | — | ¥58,000 / 年 | 全产品线打包 |

#### 3.1.1 L1：按产品定价 — ¥9,800/年

面向单一产品线，适合白泽控制台、中韩数智港等独立产品。

| 权益项 | 内容 |
|--------|------|
| 支付能力 | 微信支付 JSAPI 下单 + 回调通知 |
| 订单管理 | 订单查询、退款 |
| Mock 模式 | 本地开发 Mock 支付 |
| API 调用限额 | 10,000 次/月 |
| 技术支持 | 工单支持（响应 < 24h） |
| 环境 | 1 套生产环境 |

#### 3.1.2 L2：按产品定价（旗舰版）— ¥19,999/年

面向有高并发、API 集成需求的产品。

| 权益项 | 内容 |
|--------|------|
| L1 所有权益 | ✓ |
| API 调用限额 | 100,000 次/月 |
| 多支付平台 | 微信支付 + 支付宝 |
| 退款 API | 完整退款链路 |
| 技术支持 | 专属技术支持群（响应 < 4h） |
| 环境 | 生产 + 预发布 2 套 |
| SLA | 99.9% 可用性 |

#### 3.1.3 L3：平台订阅 — ¥58,000/年

面向军团内多个产品线统一使用。

| 权益项 | 内容 |
|--------|------|
| L2 所有权益 | ✓ |
| 产品数上限 | 不限（军团内所有产品） |
| API 调用限额 | 不限 |
| 定制开发 | 按需适配定制支付场景 |
| 私有化部署 | 可提供支付模块源码 + 部署文档 |
| 专属架构师 | 1 对 1 接入支持 |
| SLA | 99.99% + 故障 30 分钟响应 |

### 3.2 按使用量计费（备选方案）

| 计费维度 | 单价 | 说明 |
|---------|------|------|
| 每笔交易 | ¥0.30 / 笔 | 仅真实模式计费，Mock 不计费 |
| 每 API 调用 | ¥0.001 / 次 | GET/查询类调用 |
| 退款 | ¥0.30 / 笔 | 与下单同价 |

### 3.3 定价对比速查

```
定价层级                 L1              L2              L3
                      ─────           ─────           ─────
年费                  ¥9,800         ¥19,999         ¥58,000
适用产品数             1 个            1 个            不限
支付平台              微信            微信+支付宝       微信+支付宝
API 限额             1万/月          10万/月           不限
Mock 模式             ✓               ✓               ✓
退款 API              ✗               ✓               ✓
专属技术支持          工单             群聊             架构师
私有化部署             ✗               ✗               ✓
SLA                  99.9%           99.9%           99.99%
```

### 3.4 选择建议

| 产品 | 建议定价层 | 理由 |
|------|-----------|------|
| 白泽控制台 | L1 (¥9,800/年) | 单一工具产品，支付场景简单 |
| 中韩数智港 | L2 (¥19,999/年) | 跨境支付场景需支付宝+微信双通道 |
| 内容自动化工厂 | L1 (¥9,800/年) | 以订阅收费为主，支付为辅 |
| 赛博参谋 | L1 (¥9,800/年) | MVP 阶段，轻量支付需求 |
| 三产品打包 | L3 (¥58,000/年) | 性价比最高，节省 60%+ |

---

## 4. 已接入产品清单

### 4.1 已接入 ✅

| 产品 | 支付模块版本 | 状态 | 集成方式 |
|------|------------|------|---------|
| **链客宝** (Liankebao) | v1.0 (本模块) | **线上运行** | 原生集成 `payment/` 目录 |

### 4.2 待接入 ⏳

| 产品 | 产品负责人 | 优先度 | 建议接入方式 | 建议定价层 |
|------|----------|--------|------------|-----------|
| **白泽控制台** | — | 高 | FastAPI 模板（5 行代码） | L1 ¥9,800/年 |
| **中韩数智港** | — | 中 | FastAPI 模板 + 支付宝双通道 | L2 ¥19,999/年 |
| **内容自动化工厂** | — | 中 | Flask Blueprint 模板 | L1 ¥9,800/年 |
| **赛博参谋** | — | 低 | FastAPI 模板（MVP 阶段） | L1 ¥9,800/年 |

### 4.3 接入评分检查表

接入前请逐项确认：

```
[ ] payment/ 目录已复制到项目 backend/ 下
[ ] pip install httpx cryptography 已执行
[ ] .env 中 PAYMENT_MODE 已设置（开发=mock，生产=real）
[ ] 微信支付商户号已申请（生产环境需要）
[ ] WxPayConfig.from_env() 能正确读取配置
[ ] 启动时调用了 init_default_config()
[ ] 统一下单 API 在 Mock 模式下返回模拟数据
[ ] 支付回调地址已配置到微信支付商户平台
[ ] 生产环境证书文件（apiclient_key.pem）已就位
[ ] 年费 / 订阅模式已确定（建议参考第 3 节定价方案）
```

---

## 5. 附录：环境变量参考

### 5.1 通用配置

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|-------|------|
| `PAYMENT_MODE` | 否 | `mock` | `mock` 或 `real` |

### 5.2 微信支付配置

支持双前缀：`WXPAY_*` 优先，`WECHAT_*` 后备。

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `WXPAY_APPID` / `WECHAT_APPID` | 是 | 微信小程序/公众号 AppID |
| `WXPAY_MCH_ID` / `WECHAT_MCH_ID` | 是 | 微信支付商户号 |
| `WXPAY_API_KEY` / `WECHAT_API_KEY` | 是 | V2 密钥（32位） |
| `WXPAY_API_V3_KEY` / `WECHAT_API_V3_KEY` | 是* | V3 密钥（回调解密需要） |
| `WXPAY_PRIVATE_KEY_PATH` | 是* | apiclient_key.pem 路径 |
| `WXPAY_CERT_SERIAL_NO` | 是* | 证书序列号 |
| `WXPAY_NOTIFY_URL` | 是 | 支付回调 URL |
| `WXPAY_CERT_PATH` | 否 | apiclient_cert.pem（退款需要） |
| `WXPAY_REFUND_NOTIFY_URL` | 否 | 退款回调 URL |

> *标注：V3 模式必填；仅用 V2 模式时填写 `API_KEY` 即可。

### 5.3 支付宝配置

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `ALIPAY_APP_ID` | 是 | 支付宝应用 ID |
| `ALIPAY_PRIVATE_KEY` | 是 | 应用私钥（PEM 格式） |
| `ALIPAY_PUBLIC_KEY` | 是 | 支付宝公钥 |
| `ALIPAY_NOTIFY_URL` | 是 | 异步通知 URL |
| `ALIPAY_GATEWAY` | 否 | 网关（默认生产环境） |

### 5.4 `.env` 文件模板

```bash
# ==================== 支付模式 ====================
# mock  = 开发模式（返回模拟数据，无需真实商户号）
# real  = 生产模式（调用微信支付真实 API）
PAYMENT_MODE=mock

# ==================== 微信支付（双前缀兼容）====================
# WXPAY_* 为第一优先级，WECHAT_* 为后备
WXPAY_APPID=wx1234567890abcdef
WXPAY_MCH_ID=1600000001
WXPAY_API_KEY=your_v2_api_key_32_chars_long
WXPAY_API_V3_KEY=your_v3_key_32_chars_long
WXPAY_PRIVATE_KEY_PATH=/etc/wechat/apiclient_key.pem
WXPAY_CERT_SERIAL_NO=1234567890ABCDEF
WXPAY_NOTIFY_URL=https://your-domain.com/api/pay/wxpay/notify
WXPAY_REFUND_NOTIFY_URL=https://your-domain.com/api/pay/wxpay/refund-notify
WXPAY_CERT_PATH=/etc/wechat/apiclient_cert.pem

# ==================== 支付宝 ====================
ALIPAY_APP_ID=2021000000000000
ALIPAY_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----
ALIPAY_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----
ALIPAY_NOTIFY_URL=https://your-domain.com/api/pay/alipay/notify
```

---

## 修订历史

| 日期 | 版本 | 修订内容 | 作者 |
|------|------|---------|------|
| 2026-05-23 | v1.0 | 初版创建，含架构说明、接入模板、定价方案、产品清单 | — |
