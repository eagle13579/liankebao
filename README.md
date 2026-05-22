# 链客宝 (Liankebao) - 一站式AI营销增长引擎

**企业家供需匹配平台** — 连接企业主、推广员与产品方，实现精准供需匹配。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | React 19 + TypeScript 5.8 |
| 构建工具 | Vite 6 |
| 样式 | Tailwind CSS v4 |
| 路由 | React Router v7 |
| 动画 | Motion (Framer Motion) |
| 后端 | FastAPI (Python) |
| 数据库 | MySQL |
| 反向代理 | Nginx |
| 小程序 | 微信原生小程序 / Taro (React) |

## 项目结构

```
链客宝/
├── src/                    # 前端源码 (React + Vite)
│   ├── api/                # API 客户端层
│   ├── components/         # 共享组件 (ErrorBoundary, PageTransition, StatusComponents)
│   ├── screens/            # 页面组件 (Auth, Main, Product, Order, Admin)
│   ├── App.tsx             # 根组件 (路由配置)
│   ├── main.tsx            # 入口文件
│   ├── types.ts            # TypeScript 类型定义
│   └── index.css           # 全局样式 + Tailwind
├── backend/                # 后端源码 (FastAPI)
├── liankebao-miniapp/      # 微信小程序 (原生)
├── liankebao-weapp/        # 微信小程序 (Taro/React)
├── dist/                   # 构建产物
├── index.html              # HTML 入口
├── vite.config.ts          # Vite 配置
├── package.json            # 依赖管理
└── README.md               # 项目说明
```

## 快速启动

### 环境要求

- Node.js >= 18
- Python >= 3.10
- MySQL >= 8.0

### 前端启动

```bash
# 1. 安装依赖
npm install

# 2. 配置环境变量 (复制并修改)
cp .env.example .env
# 编辑 .env，设置 VITE_API_BASE

# 3. 启动开发服务器 (默认端口 3000)
npm run dev

# 4. 生产构建
npm run build
```

### 后端启动

```bash
cd backend

# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置数据库
# 编辑 config.py 设置 MySQL 连接信息

# 4. 初始化数据库
alembic upgrade head

# 5. 启动服务 (默认端口 8000)
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 微信小程序

```bash
cd liankebao-miniapp
# 使用微信开发者工具打开此目录
```

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VITE_API_BASE` | API 基础路径 | `/lkapi` |
| `GEMINI_API_KEY` | Google Gemini API 密钥 | - |
| `APP_URL` | 应用部署 URL | - |

## 端口说明

| 端口 | 服务 | 说明 |
|------|------|------|
| 3000 | Vite 开发服务器 | 前端热更新开发 |
| 8000 | FastAPI 后端 | REST API 服务 |
| 3306 | MySQL | 数据库 |
| 80/443 | Nginx | 生产环境反向代理 |

## 部署方式

### 生产部署 (Nginx + 反向代理)

```
1. 构建前端: npm run build (输出到 dist/)
2. 配置 Nginx 将 / 指向 dist/
3. 配置 Nginx 将 /lkapi 反向代理到后端 :8000
4. 使用 supervisor/systemd 管理后端进程
```

Nginx 配置示例:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    root /path/to/liankebao/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /lkapi/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 功能模块

- **用户系统**: 微信登录 / 账号注册，买家/推广员/产品方三种角色
- **产品管理**: 商品上架、审核、分类检索
- **订单系统**: 下单、支付、订单管理
- **推广中心**: 分销推广、佣金结算
- **管理后台**: 数据看板、产品审核、提现审核、订单管理
