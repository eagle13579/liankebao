# 链客宝 API 文档门户

> 本项目是链客宝后端的**独立 API 文档门户**，提供无需依赖后台服务的静态文档页面、Postman 集合和说明文档。

## 📂 目录结构

```
docs/
├── index.html              # 独立 API 文档页面（暗色主题）
├── postman_collection.json  # Postman / Insomnia 兼容集合
└── README.md               # 本文件（使用说明）
```

---

## 📄 API 文档页面 (index.html)

`index.html` 是一个**完全独立**的 HTML 页面，无需启动后端服务即可在浏览器中打开阅读。

### 使用方法

1. 在文件管理器中找到 `docs/index.html`
2. 双击用浏览器打开（或右键 → 打开方式 → 浏览器）
3. 左侧导航栏点击模块可快速跳转
4. 点击每个 API 卡片可展开查看详情和示例

### 特点

- 暗色主题，与链客宝品牌风格一致
- 11 个模块导航：认证、产品、搜索、供需匹配、推荐、CRM、企业数据、数据丰富、多租户组织、增长引擎、系统
- 每个端点标注 HTTP 方法、路径、说明和认证要求
- 点击卡片可展开查看请求/响应示例
- 首次打开时每个模块的第一个端点默认展开

---

## 📬 Postman 集合 (postman_collection.json)

兼容 **Postman** 和 **Insomnia** / **Bruno** 等 API 工具。

### 导入到 Postman

1. 打开 Postman
2. 点击 **Import** → **File** → 选择 `docs/postman_collection.json`
3. 点击 **Import** 完成导入

### 导入到 Insomnia

1. 打开 Insomnia
2. 点击 **Import/Export** → **Import Data** → **From File**
3. 选择 `docs/postman_collection.json`
4. 点击 **Import**

### 环境变量

导入后请配置环境变量：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `base_url` | `https://www.go-aiport.com` | API 基础地址（可切换为 staging 或 localhost） |
| `token` | （空） | Bearer 令牌（登录后自动填充） |

**推荐的 Postman 环境配置：**

- 生产环境: `https://www.go-aiport.com`
- 预发布环境: `https://staging.go-aiport.com`
- 本地开发: `http://localhost:7800`

登录请求的 **Tests** 脚本会自动将返回的 `access_token` 设为 `{{token}}` 环境变量，后续请求自动携带认证头。

### 集合内容

共 **30+ 个请求**，覆盖核心 API：

| 模块 | 请求数 | 主要端点 |
|------|--------|----------|
| 🔐 认证 | 6 | login, register, me, refresh, wechat, logout |
| 📦 产品 | 5 | list, create, detail, update, delete |
| 🔍 搜索 | 3 | search, vector search, rebuild index |
| 🤝 匹配 | 3 | needs→products, products→needs, refresh |
| ⭐ 推荐 | 4 | hot, personalized, AI personalized, feedback |
| 📊 CRM | 5 | deals CRUD, pipeline overview |
| 🏢 企业数据 | 3 | list, create, detail |
| 📎 数据丰富 | 4 | enrich company, basic, scope, contacts |
| 👥 多租户 | 3 | create org, list, detail |
| 📈 增长引擎 | 5 | create invite, list, detail, accept, stats |
| ⚙️ 系统 | 3 | banners, notifications, health |

---

## 🔗 在线 API 文档

链客宝后端基于 FastAPI 构建，运行后自动提供交互式 API 文档：

- **Swagger UI**: [https://www.go-aiport.com/docs](https://www.go-aiport.com/docs) — 可在页面内直接测试接口
- **ReDoc**: [https://www.go-aiport.com/redoc](https://www.go-aiport.com/redoc) — 另一种风格的可视化文档

本地开发环境：
- Swagger: `http://localhost:7800/docs`
- ReDoc: `http://localhost:7800/redoc`

---

## 💡 使用建议

1. **阅读文档**：先通过 `index.html` 了解 API 概览
2. **测试接口**：用 Postman 集合快速发起请求
3. **交互调试**：在 Swagger UI (`/docs`) 中直接在线测试
4. **开发集成**：参考响应格式对接前端/小程序

---

## 📝 维护说明

生成时间戳位于 `index.html` 页面底部和 Postman 集合的 `info.description` 字段中。

更新文档页面的方法：
1. 更新 `index.html` 中的端点描述
2. 更新 `postman_collection.json` 中的请求配置
3. 保持与后端路由代码同步
