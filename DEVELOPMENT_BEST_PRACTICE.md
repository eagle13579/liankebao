# 链客宝开发最佳实践 SOP

> 版本: 2.0 | 最后更新: 2026-06-01
> 项目: 链客宝 (FastAPI + React 19 + Vite 6)
> 部署: liankebao.top (Nginx)
> 远程: github.com:eagle13579/liankebao.git

---

## 一、核心理念

**三环境 + 五铁律**

| 环境 | 角色 | 放什么 | 不放什么 |
|:-----|:-----|:-------|:---------|
| **D:\链客宝\** | 代码唯一真相源 | 源码/部署脚本/git/ARCHITECTURE | AI会话记录、技能缓存 |
| **profiles/chainke-dev/** | Hermes工作区 | SOUL.md/会话/.env/config | 项目源代码 |
| **记忆宫殿 L1-L5** | 反哺目的地 | 代码快照/ADR/心智模型/复盘/归档 | 项目完整代码 |

| 铁律 | 内容 |
|:-----|:------|
| **A: 先读SOUL** | 每次开发前加载 profiles/chainke-dev/SOUL.md，对齐三要素 |
| **B: 代码在项目** | 所有代码改到 D:\链客宝\ 目录 |
| **C: 沉淀三步** | 代码完成 → git commit → 反哺记忆宫殿 |
| **D: 三问自检** | delegate_task返回后：提取了？写入了？下次会注入？ |
| **E: 复盘归档** | 每次里程碑 → L4博物馆/复盘 → L2档案馆 |

---

## 二、三个环境的职责划分

### 1. D:\链客宝\ — 代码唯一真相源

```
D:\链客宝\
├── backend/           # FastAPI 后端源码
│   ├── app/
│   │   ├── main.py    # 主入口
│   │   ├── models/    # 数据模型
│   │   ├── routers/   # API路由
│   │   └── services/  # 业务逻辑
│   └── requirements.txt
├── src/               # React 前端源码
│   ├── App.tsx
│   ├── components/
│   └── pages/
├── scripts/           # 部署&运维脚本
├── deploy/            # 部署配置
├── ARCHITECTURE.md    # 架构文档
├── package.json
└── vite.config.ts
```

**铁律**: 此目录下的一切受 git 版本控制。未跟踪的临时文件在任务结束时清理。

### 2. profiles/chainke-dev/ — Hermes 工作区

路径: `D:\向海容的知识库\wiki\wiki\记忆宫殿\profiles\chainke-dev\`

| 文件 | 用途 |
|:-----|:------|
| SOUL.md | 项目上下文注入文件，每次启动AI时最先加载 |
| .env | API密钥、模型配置（私有，不进git） |
| config.yaml | Hermes 模型参数、工具配置 |
| sessions/ | AI会话记录，开发历史可回溯 |
| plans/ | 任务拆解、执行计划 |
| logs/ | 构建日志、调试日志 |

**启动方式**: `hermes --profile chainke-dev --continue`

### 3. 记忆宫殿 L1-L5 — 知识反哺目的地

| 层级 | 目录 | 内容 | 更新时机 |
|:-----|:-----|:------|:---------|
| **L1** 图书馆 | L1图书馆/代码资产库/链客宝/ | 代码架构快照、模块结构、接口文档 | 每次大功能完成 |
| **L1** 图书馆 | L1图书馆/ADR/ | 架构决策记录 (ADR-008-*) | 每次关键决策 |
| **L4** 博物馆 | L4博物馆/复盘/ | 项目复盘、员工复盘、成长记录 | 每个上线周期后 |
| **L5** 孵化室 | L5孵化室/五池/模型池/ | 可复用的心智模型、模式抽象 | 每周定期萃取 |

---

## 三、五铁律详解

### A: 先读SOUL
启动 chainke-dev profile 前，确认 SOUL.md 已加载正确的项目上下文。
```
hermes --profile chainke-dev --continue
# 确认 SOUL.md 包含当前分支上下文
```

### B: 代码在项目
所有代码改动在 D:\链客宝\ 下完成，不在记忆宫殿里写代码。
```
cd D:\链客宝\
# 修改代码 → git commit → git push
```

### C: 沉淀三步
代码改完后的标准流程：
1. `git commit -m "feat(模块): 描述"`
2. 反哺记忆宫殿：代码收割到 L1 + ADR到 L1 + 心智模型到五池
3. 员工记忆注入 + MEMORY.md 追加

### D: 三问自检
每次 delegate_task 返回后，自检三问：
- [ ] 关键发现提取了没有？
- [ ] 写入员工的SQLite记忆库了没有？
- [ ] 下次派他时，我会注入历史记忆吗？

### E: 复盘归档
- 每次里程牌 → L4博物馆/复盘/{日期}/{时间}_{主题}.md
- 更新 L2档案馆/复盘记录.md 索引

---

## 四、每日工作流

```
hermes --profile chainke-dev --continue
    ↓
加载SOUL.md + TODO
    ↓
cd D:\链客宝\
    ↓
delegate_task 派单（烛龙写代码 / 文鳐写文档）
    ↓
代码验证 → git commit
    ↓
反哺闭环（代码收割→ADR→心智模型→员工注入→MEMORY→汇报）
```

---

## 五、Git分支规范

### 分支全景
```
main (生产 · 仅从release合并)
  └── develop (集成分支)
       ├── feature/模块名-功能
       └── fix/问题描述
```

### 提交规范
```
feat(模块): 新功能描述
fix(模块): Bug修复描述
docs(模块): 文档更新
refactor(模块): 重构
test(模块): 测试
chore(模块): 构建/工具
```

### push前安全清单
```bash
git ls-files .env                    # 应空
git ls-files | grep -E "\.db$"      # 应空
git ls-files | grep -E "password|secret|token"  # 应空
```

---

## 六、合规红线

- 分润严格二级（推广员从自己推荐企业拿分润）
- 用语: 推广员/流量合伙人（非分销/代理/上级下级）
- 数据三层隔离: L1公开(GitHub) / L2商业策略 / L3内部运营

---

## 七、已知陷阱速查

| 域 | # | 陷阱 | 严重度 |
|:---|:-:|:-----|:------:|
| 📍 路径 | 1 | systemd活动路径≠直觉路径 | 🔴 P0 |
| 📍 路径 | 2 | 双代码库路径（主代码库 vs 网关） | 🔴 P0 |
| 💻 部署 | 3 | __pycache__缓存中毒 | 🔴 P0 |
| 🌐 Nginx | 4 | $变量被Shell展开 | 🔴 P0 |
| 🌐 Nginx | 5 | 尾斜杠决定前缀剥离 | 🔴 P0 |
| 🌐 Nginx | 6 | HTTPS混合内容拦截 | 🔴 P0 |
| 🐍 Python | 7 | Flask Blueprint注册到FastAPI | 🔴 P0 |
| 🐍 Python | 8 | 引用目标项目不存在的模型 | 🔴 P0 |
| 🔐 安全 | 9 | .env提交到GitHub历史 | 🔴 P0 |
| 🔐 合规 | 10 | 三级分销描述（违法） | 🔴 P0 |
| 🔐 合规 | 11 | 前端API路径硬编码HTTP | 🔴 P0 |

---

## 八、链客宝服务端口

| 服务 | 端口 | 路径 |
|:-----|:----:|:------|
| 旧后端(退役中) | 8000 | D:/链客宝/backend/ |
| 新后端(主服务) | 8001 | D:/链客宝/backend_v2/ |
| AI数字名片 | 8003 | 记忆宫殿/L5/数字名片/ |
| 统一网关 | 5136 | 记忆宫殿/L5/链客宝/统一API网关.py |
| 前端(Vite开发) | 5173 | D:/链客宝/ |
| 生产域名 | 443 | https://liankebao.top |

---

## 九、开发流程铁律

| 铁律 | 内容 |
|:-----|:------|
| 先拆后做 | 收到需求后，先拆成MECE模块，画模块依赖图，再执行 |
| 一次一模块 | 一个delegate_task只做一个模块（≤2个文件改动） |
| 本地不改远程 | 本地代码改完→Git提交→CI验证→PR合并→再部署 |
| 验证先行 | 每次改动后必须验证：后端语法+前端编译+API可达 |
| 不重复造轮 | 任何新功能前先扫现有skills/原子库/代码资产库 |

---

## 十、部署规范

| 属性 | 值 |
|:-----|:-----|
| 服务器IP | 47.116.116.87 |
| SSH用户 | root |
| 后端路径 | /opt/chainke/backend/ |
| Nginx配置 | /etc/nginx/sites-enabled/ |
| 域名 | liankebao.top |

### 验证门禁
```bash
curl http://127.0.0.1:8000/health                  # 200
systemctl status chainke-backend | grep active      # active
curl https://liankebao.top/ -o /dev/null -w "%{http_code}"  # 200
```
