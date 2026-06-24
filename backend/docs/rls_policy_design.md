# 链客宝多租户 RLS 策略设计文档

> 版本: 1.0
> 日期: 2026-06-10
> 作者: 狴犴（多租户安全架构）

---

## 1. 概述

本文档定义链客宝 PostgreSQL Row-Level Security（RLS）策略的完整设计方案。当 `IS_MULTI_TENANT=true` 且数据库为 PostgreSQL 时，RLS 在数据库层面提供**强制行级隔离**，作为应用层 `TenantSessionWrapper` 的纵深防御。

### 1.1 设计目标

| 目标 | 说明 |
|------|------|
| 行级隔离 | 每个用户只能看到自己组织（organization_id）的数据行 |
| 管理员豁免 | 全局管理员（role='admin'）可跨组织查看/管理 |
| 防护纵深 | 即使应用层过滤被绕过，RLS 提供最后一道防线 |
| 零侵入 | 业务代码无需修改，RLS 完全由 DDL 和 session 变量驱动 |
| 可回滚 | 关闭 IS_MULTI_TENANT 即可恢复（通过 `app.is_multi_tenant` session 变量） |

### 1.2 架构关系

```
HTTP Request
    │
    ▼
Tenant Middleware (app/middleware/tenant_middleware.py)
    │  ┌─────────────────────────────────────┐
    │  │ 1. 读取 X-Tenant-ID Header          │
    │  │ 2. 验证 JWT Token                   │
    │  │ 3. 解析 tenant_id & role from JWT   │
    │  │ 4. 设置 g.organization_id           │
    │  │ 5. 调用 SET app.current_org_id = X  │ ← PostgreSQL session var
    │  │   调用 SET app.current_user_role = Y│ ← PostgreSQL session var
    │  │   调用 SET app.is_multi_tenant = 1  │ ← PostgreSQL session var
    │  └─────────────────────────────────────┘
    │
    ▼
    ┌─────────────────────────────┐
    │ SQLAlchemy ORM Query Engine │
    └─────────────────────────────┘
    │
    ▼
    ┌─────────────────────────────┐
    │ PostgreSQL RLS              │ ◄── 最终强制过滤
    │ ─ 自动附加 organization_id  │
    │ ─ 管理员豁免                │
    └─────────────────────────────┘
    │
    ▼
  Filtered Result
```

### 1.3 双保险模式

链客宝采用 **应用层过滤 + 数据库层 RLS** 的双保险策略：

| 层级 | 组件 | 职责 | 绕过风险 |
|------|------|------|----------|
| 应用层 | `TenantSessionWrapper` | 自动附加 `WHERE organization_id = ?` | 直接 SQL / raw connection |
| 应用层 | `apply_tenant_filter()` | 手动附加过滤条件 | 忘记调用 |
| 数据库层 | RLS Policy | 强制行级过滤 | 无（不可绕过） |

---

## 2. PostgreSQL Session 变量约定

RLS 策略依赖三个自定义 PostgreSQL session 变量，由中间件在每次请求进入时设置：

### 2.1 变量定义

| Session 变量 | 类型 | 默认值 | 说明 |
|-------------|------|--------|------|
| `app.is_multi_tenant` | text | `'0'` | 多租户模式开关。`'1'`=启用, `'0'`=禁用 |
| `app.current_org_id` | text | `''` | 当前请求所属组织 ID（字符串，需转型为 int） |
| `app.current_user_role` | text | `''` | 当前请求用户的角色（`admin` / `member` / `buyer` 等） |

### 2.2 设置方式

在中间件中通过 `SET SESSION` 或 `SELECT set_config()` 设置：

```sql
-- PostgreSQL 9.6+ 推荐方式
SELECT set_config('app.is_multi_tenant', '1', false);
SELECT set_config('app.current_org_id', '42', false);
SELECT set_config('app.current_user_role', 'member', false);
```

第三个参数 `false` 表示仅当前事务可见（如果需要跨事务持久，使用 `true` 表示 `SESSION` 级别）。

> **注意**: 链客宝使用 `false`（事务级），因为每个请求独立使用一个数据库会话/事务，请求结束后自动清除。

### 2.3 读取方式

在 RLS Policy 或 SQL 查询中读取：

```sql
-- 获取当前组织 ID
SELECT NULLIF(current_setting('app.current_org_id', true), '')::int;

-- 获取当前用户角色
SELECT NULLIF(current_setting('app.current_user_role', true), '');

-- 检查多租户是否启用
SELECT current_setting('app.is_multi_tenant', true) = '1';
```

第二个参数 `true` 表示如果变量未设置则返回 NULL 而非报错。

---

## 3. RLS 策略设计

### 3.1 核心策略规则

每条 RLS Policy 遵循以下统一逻辑：

```
┌──────────────────────────────────────────────────────┐
│ IF app.is_multi_tenant = '0' THEN                    │
│     └→ ALLOW (多租户已关闭，不过滤)                    │
│ ELSE IF app.current_user_role = 'admin' THEN         │
│     └→ ALLOW (管理员可跨组织查看)                      │
│ ELSE IF app.current_org_id 为空 THEN                  │
│     └→ DENY (无租户上下文，拒绝查询)                    │
│ ELSE                                                  │
│     └→ FILTER WHERE organization_id = app.current_org_id │
└──────────────────────────────────────────────────────┘
```

### 3.2 PostgreSQL RLS 实现

```sql
-- 底层辅助函数：统一判断是否启用多租户
CREATE OR REPLACE FUNCTION app._rls_is_active()
RETURNS boolean
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN current_setting('app.is_multi_tenant', true) = '1';
END;
$$;

-- 底层辅助函数：获取当前组织 ID（安全转型）
CREATE OR REPLACE FUNCTION app._rls_current_org_id()
RETURNS int
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    val text;
BEGIN
    val := NULLIF(current_setting('app.current_org_id', true), '');
    IF val IS NULL THEN
        RETURN NULL;
    END IF;
    RETURN val::int;
END;
$$;

-- 底层辅助函数：检查当前用户是否为管理员
CREATE OR REPLACE FUNCTION app._rls_is_admin()
RETURNS boolean
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN NULLIF(current_setting('app.current_user_role', true), '') = 'admin';
END;
$$;
```

### 3.3 通用 Policy 模板

所有 18 张表使用相同模板：

```sql
CREATE POLICY tenant_isolation_{{table_name}} ON {{schema}}.{{table_name}}
FOR ALL
USING (
    NOT app._rls_is_active()                    -- 多租户关闭 → 放行
    OR app._rls_is_admin()                      -- 管理员 → 放行
    OR organization_id IS NULL                  -- 无组织归属（极少情况）→ 放行
    OR organization_id = app._rls_current_org_id()  -- 匹配组织 → 放行
)
WITH CHECK (
    NOT app._rls_is_active()
    OR app._rls_is_admin()
    OR app._rls_current_org_id() IS NULL
    OR organization_id = app._rls_current_org_id()
);
```

> **注意**: `FOR ALL` 等价于 `FOR SELECT, INSERT, UPDATE, DELETE`。`USING` 控制已有行的可见性，`WITH CHECK` 控制新插入/修改行的约束。

### 3.4 覆盖的 18 张表

| # | 表名 | SQLAlchemy 模型 | 备注 |
|---|------|-----------------|------|
| 1 | `users` | User | 用户表 |
| 2 | `brochures` | Brochure | 电子宣传册 |
| 3 | `products` | Product | 产品 |
| 4 | `orders` | Order | 订单 |
| 5 | `payments` | Payment | 支付记录 |
| 6 | `discussions` | Discussion | 讨论 |
| 7 | `hypotheses` | BusinessHypothesis | 商业假设 |
| 8 | `experiments` | InnovationExperiment | 创新实验 |
| 9 | `opportunities` | InnovationOpportunity | 创新机会 |
| 10 | `design_reviews` | DesignReviewReport | 设计审查报告 |
| 11 | `aesthetic_scores` | AestheticScoreCardRecord | 审美评分卡 |
| 12 | `messages` | Message | 消息 |
| 13 | `notifications` | Notification | 通知 |
| 14 | `settings` | Setting | 设置 |
| 15 | `audit_logs` | AuditLog | 审计日志 |
| 16 | `sessions` | Session | 会话 |
| 17 | `api_keys` | ApiKey | API 密钥 |
| 18 | `templates` | Template | 模板 |

> **缺口标记**: 上述表名中的部分（如 `brochures`, `payments`, `discussions`, `messages`, `notifications`, `settings`, `audit_logs`, `sessions`, `api_keys`, `templates`）在现有 `models.py` 中尚未定义对应的 SQLAlchemy 模型。RLS 策略脚本会在这些表**实际创建后**自动生效（脚本使用 `IF NOT EXISTS` 和 `DO $$ ... EXCEPTION` 容错）。这些表需要在后续步骤中补充模型或由 Alembic 迁移创建。

---

## 4. 管理员的跨组织访问

### 4.1 判断依据

管理员有两种含义，RLS 策略识别的是**全局角色**为 `admin` 的用户：

| 角色来源 | 示例值 | RLS 是否豁免 |
|----------|--------|-------------|
| `users.role` = `'admin'` | 全局超级管理员 | ✅ 是 |
| `organization_members.role` = `'admin'` | 组织级管理员 | ❌ 否（仅限本组织） |
| `users.role` = `'buyer'` | 普通买家 | ❌ 否 |
| `users.role` = `'promoter'` | 推广员 | ❌ 否 |

### 4.2 工作原理

JWT 令牌生成时（`create_access_token`），若 `IS_MULTI_TENANT=true` 且用户存在 `organization_id`，会将 `org_id` 和 `role` 注入 JWT payload：

```python
# auth.py:98-101
to_encode["org_id"] = user.organization_id
to_encode["role"] = user.role or "viewer"
```

中间件解析 JWT 后，将 `role` 写入 PostgreSQL session 变量 `app.current_user_role`，RLS 策略据此判断是否需要豁免。

---

## 5. 与现有架构的兼容性

### 5.1 TenantSessionWrapper 共存

```python
# tenant.py - 应用层过滤（现有）
class TenantSessionWrapper:
    def query(self, *entities, **kwargs):
        q = self._session.query(*entities, **kwargs)
        org_id = get_current_org_id()
        if org_id is not None and IS_MULTI_TENANT:
            for entity in entities:
                if hasattr(entity, "organization_id"):
                    q = q.filter(entity.organization_id == org_id)
        return q
```

RLS 启用后，`TenantSessionWrapper` 的过滤在查询层面**仍然保留**。RLS 作为二层防御：

1. 正常流程：应用层过滤掉大部分数据 → RLS 兜底 → 安全
2. 绕过场景：应用层未过滤（如 raw SQL）→ RLS 拦截 → 安全

### 5.2 get_db() 依赖注入

```python
# database.py - 现有 get_db() 已在 PostgreSQL 模式下设置 tenant_org_id
def get_db():
    db = SessionLocal()
    try:
        if is_multi_tenant():
            from app.tenant import get_current_org_id
            org_id = get_current_org_id()
            if org_id is not None:
                db.info["tenant_org_id"] = org_id
        yield db
    finally:
        db.close()
```

RLS 策略与此兼容。中间件在设置 `g.organization_id` 的同时设置 PostgreSQL session 变量，两者并行。

### 5.3 对 test_tenant.py 的影响

现有测试基于 SQLite，RLS 是 PostgreSQL 专属特性。测试不需要修改，因为：

- SQLite 模式下 `IS_MULTI_TENANT` 为 False → 不执行 RLS 脚本
- 现有 `TestTenantIsolationORM` 和 `TestTenantIsolationFullChain` 测试的是应用层隔离
- 新增的 RLS 测试（见验证方案）仅在 PostgreSQL 环境下运行

---

## 6. 安全注意事项

### 6.1 Session 变量注入风险

PostgreSQL session 变量通过 `set_config()` 设置，仅当前会话可见，**不存在 SQL 注入风险**（变量名和值是参数化的）。

### 6.2 organization_id 字段要求

所有受 RLS 保护的表**必须**包含 `organization_id` 列，类型为 `INTEGER` 或 `BIGINT`。现有 `_org_fk()` 函数已确保这一点。

### 6.3 性能影响

RLS 会在每个查询的每条记录上执行策略函数。为减轻性能影响：

- `app._rls_current_org_id()` 和 `app._rls_is_admin()` 标记为 `STABLE`，允许 PostgreSQL 优化器缓存
- 建议在 `organization_id` 列上创建索引（现有 `_org_fk()` 已设置 `index=True`）
- 查询已包含 `WHERE organization_id = ?`（应用层过滤），RLS 的额外开销通常在 1-3%

### 6.4 超级用户绕过

以下 PostgreSQL 角色不受 RLS 限制：
- `postgres` 超级用户
- 拥有 `BYPASSRLS` 属性的角色

因此，即使 RLS 启用，数据库管理员仍可查看所有数据。这是设计有意为之的——应用层控制业务隔离，DBA 保留运维权限。

---

## 7. 回滚方案

### 7.1 软回滚（推荐）

将 `IS_MULTI_TENANT` 环境变量设为 `false`（或删除/注释掉），重启应用。中间件停止设置 `app.is_multi_tenant = '1'`，RLS 策略检测到 `app._rls_is_active() = false` 后放行所有数据。

### 7.2 硬回滚（彻底移除）

如需完全移除 RLS（例如切换回 SQLite），执行：

```sql
-- 禁用所有表的 RLS
SELECT format('ALTER TABLE %I.%I DISABLE ROW LEVEL SECURITY;', table_schema, table_name)
FROM information_schema.tables
WHERE table_schema = 'public' AND table_name IN (
    'users', 'brochures', 'products', 'orders', 'payments',
    'discussions', 'hypotheses', 'experiments', 'opportunities',
    'design_reviews', 'aesthetic_scores', 'messages', 'notifications',
    'settings', 'audit_logs', 'sessions', 'api_keys', 'templates'
);

-- 删除辅助函数
DROP FUNCTION IF EXISTS app._rls_is_active();
DROP FUNCTION IF EXISTS app._rls_current_org_id();
DROP FUNCTION IF EXISTS app._rls_is_admin();
```

---

## 8. schema 命名空间

所有 RLS 辅助函数放置在 `app` schema 中，与业务表（`public`）分离：

```sql
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION CURRENT_USER;
```

这确保：
1. 辅助函数不污染 `public` 命名空间
2. 未来可添加更多 `app.*` 工具函数
3. 所有权清晰

---

## 附录 A: 启用/禁用流程图

```
┌──────────────────┐
│  HTTP Request     │
│  + X-Tenant-ID   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Tenant Middleware │
│                   │
│ IS_MULTI_TENANT?  │
│  ├─ No  → 跳过    │
│  └─ Yes → 继续    │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────┐
│ Validate Token           │
│ Extract org_id & role    │
└────────┬─────────────────┘
         │
         ▼
┌───────────────────────────────────────┐
│ PostgreSQL: SET SESSION variables     │
│ app.is_multi_tenant = '1'             │
│ app.current_org_id = '<org_id>'       │
│ app.current_user_role = '<role>'      │
└────────┬──────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────┐
│ SQLAlchemy Query → PostgreSQL         │
│                                       │
│ RLS Policy Evaluation:                │
│                                       │
│  is_multi_tenant = '0'? ──→ ALLOW    │
│  role = 'admin'?        ──→ ALLOW    │
│  org_id IS NULL?        ──→ ALLOW    │
│  organization_id = org_id? ──→ ALLOW │
│  否则                    ──→ DENY    │
└───────────────────────────────────────┘
```

## 附录 B: 与 _org_fk() 的互操作

`_org_fk()` 函数在 `models.py` 中定义如下：

```python
def _org_fk():
    if not _IS_MULTI_TENANT:
        return Column(Integer, nullable=True, default=None)
    return Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
```

RLS 策略假设 `organization_id` 列存在且为整数类型。当 `IS_MULTI_TENANT=False` 时：
- `_org_fk()` 返回 `nullable=True` 的列
- RLS 策略通过 `app._rls_is_active()` 检测到多租户未启用，放行所有数据
- 两者协同工作，无需额外配置
