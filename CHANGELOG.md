# 链客宝AI Changelog

## [2.2.0] — 2026-06-02 — 工业化全量升级 + 会员体系交付

### 新增
- CI/CD 流水线 (GitHub Actions)
- bcrypt 密码加密 (SHA256→bcrypt)
- Alembic 数据库迁移框架
- pytest 测试框架 (38测试)
- Docker 容器化
- 国际化 i18n (中英)
- Sentry + Prometheus 监控
- 速率限制 + 请求ID追踪
- 会员体系 P0-P3: 3+1层会员(gold/diamond/board) + 线上对接会 + 私董会
- 支付回调支持会员订单处理 + 自动升级用户会员等级
- 工业化评分系统 — scripts/industrialize_score.py 10维度自动化评分工具
- 安全检查脚本 — scripts/security-check.sh 涵盖10项安全检查项

### 修复
- 网关路由冲突 — gateway.py: /api/match/ 路由从 :8000 修正为 :8003
- 安全加固 — .env 文件权限规范化
- 预提交钩子增强 — 新增 bandit 安全扫描 + detect-private-key + check-added-large-files
- 工具链完善 — backend/pyproject.toml 新增 coverage 配置(最低30%) + bandit 配置

### 变更
- Makefile 增强 — 新增 security, security-all, industrialize, pipeline 目标
- 工业化评分: 5.5 → 6.9/10 (详见 industrialization_report.json)
- 架构成熟度: 68 → 72
- 安全合规: 65 → 70
- 代码质量: 72 → 75
- 文档完备: 78 → 80

## [2.1.0] — 2026-05-31
3Tab SPA · 信任网络 · 匹配引擎 · 翻页图册 · 链客宝AI桥接

## [2.0.0] — 2026-05-30
FastAPI重写 · SQLite WAL · Bearer Token认证

## [1.0.0] — 2026-05-25
MVP: Flask + SQLite

### 前置版本 (概要)
- [0.9.0] FastAPI + React 19 基础架构完成
- [0.8.0] 多租户模型 + 数据安全层
- [0.7.0] 支付模块 + 充值系统
- [0.6.0] AI匹配引擎 + 向量搜索
