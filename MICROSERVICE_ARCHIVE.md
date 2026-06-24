# 微服务归档说明

> 归档日期：2026-06-22 | 操作：架构简化

## 背景

链客宝当前为 **0 用户阶段**，已搭建了 7 个微服务目录，但每个服务仅包含 1 个启动文件（空壳），并未真正实现微服务拆分。为降低运维复杂度、加速迭代，决定将这些微服务存根归档，统一在单体 FastAPI 中运行。

## 归档的服务

| 服务 | 原端口 | 状态 | 说明 |
|------|--------|------|------|
| `crm-service/` | 8005 | 🗄️ 归档 | 仅 1 个 crm_server.py，路由已在主 backend 中存在 |
| `crm_engine/` | - | 🗄️ 归档 | NPS 路由器，内存存储（TODO替换为数据库） |
| `user-service/` | 8002 | 🗄️ 归档 | 独立认证服务，功能已在主 backend auth 模块中实现 |
| `payment-service/` | 8006 | 🗄️ 归档 | 仅 1 个 payment_server.py，路由已在主 backend 中 |
| `notification-service/` | 8007 | 🗄️ 归档 | 直接操作 SQLite，功能已在主 backend 中实现 |
| `search-service/` | 8008 | 🗄️ 归档 | 全文搜索，功能已在主 backend search_index 中实现 |
| `matching-service/` | - | 🗄️ 归档 | 匹配引擎，功能已在主 backend matching_engine 中实现 |

## 保留的服务

| 服务 | 原因 |
|------|------|
| `trust_engine/` | 信任评分核心引擎，被主 backend 直接 import 使用 |
| `payment_sdk/` | 支付 SDK 库，含微信支付 V2/V3 和支付宝完整实现 |

## 当前架构

```
链客宝AI (单体 FastAPI)
├── backend/app/          # 主应用（36个路由模块）
├── trust_engine/         # 信任评分引擎（库）
├── payment_sdk/          # 支付 SDK（库）
├── liankebao-miniapp/    # 微信原生小程序
├── liankebao-weapp/      # Taro 版小程序
└── src/                  # React Web 前端
```

## 未来微服务拆分时机

当满足以下条件之一时，考虑拆分：
1. 日活用户 > 10,000
2. 特定模块（如支付/搜索）QPS 成为瓶颈
3. 需要独立团队维护特定模块
4. 需要独立扩缩容策略

## 恢复方法

如需恢复某个微服务，各服务的原代码仍在对应目录中，可直接使用。
