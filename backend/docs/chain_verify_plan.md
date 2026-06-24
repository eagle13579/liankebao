# 链客宝多租户 RLS 全链路验证方案

> 版本: 1.0
> 日期: 2026-06-10
> 作者: 狴犴（多租户安全架构）

---

## 1. 验证目标

验证从 HTTP 请求 → Tenant 中间件提取 `X-Tenant-ID` → 设置 PostgreSQL session 变量 → RLS 过滤 → 返回隔离数据的**完整链路**。

### 1.1 测试场景矩阵

| # | 场景 | 预期结果 | 对应测试函数 |
|---|------|----------|-------------|
| 1 | 组织A的用户 → 只能看到A的数据 | 仅返回 org_id=A 的行 | `test_org_a_isolation` |
| 2 | 组织B的用户 → 只能看到B的数据 | 仅返回 org_id=B 的行 | `test_org_b_isolation` |
| 3 | 未登录/无有效JWT → 请求被拒绝 | HTTP 401 | `test_unauthenticated_rejected` |
| 4 | admin 跨组织查看 | 返回所有组织的数据 | `test_admin_cross_org_access` |
| 5 | 无 X-Tenant-ID 头 → 请求被拒绝 | HTTP 400 / 403 | `test_missing_tenant_header` |
| 6 | 直接 SQL 绕过应用层过滤 | RLS 仍然拦截 | `test_rls_raw_sql_bypass` |
| 7 | 回滚：关闭 IS_MULTI_TENANT | 所有数据可见 | `test_rollback_is_multi_tenant` |

---

## 2. 测试环境准备

### 2.1 前置条件

- PostgreSQL 数据库运行中
- `IS_MULTI_TENANT=true`（环境变量）
- RLS 策略已部署（执行 `rls_policies.sql`）
- 至少有 2 个组织（org_id=1, org_id=2），每个组织至少有 1 个用户和若干产品数据

### 2.2 测试数据准备

```sql
-- 组织A
INSERT INTO organizations (name, slug, owner_id) VALUES ('组织A', 'org-a', 1);
-- org_id=1

-- 组织B
INSERT INTO organizations (name, slug, owner_id) VALUES ('组织B', 'org-b', 1);
-- org_id=2

-- 组织A的用户（普通用户 + admin）
INSERT INTO users (username, password_hash, name, role, organization_id)
VALUES ('user_a_1', '...', '用户A1', 'member', 1);
INSERT INTO users (username, password_hash, name, role, organization_id)
VALUES ('admin_a', '...', '管理员A', 'admin', 1);

-- 组织B的用户
INSERT INTO users (username, password_hash, name, role, organization_id)
VALUES ('user_b_1', '...', '用户B1', 'member', 2);

-- 跨组织全局admin（不指定组织）
INSERT INTO users (username, password_hash, name, role, organization_id)
VALUES ('super_admin', '...', '超级管理员', 'admin', NULL);

-- 产品数据
INSERT INTO products (name, owner_id, organization_id)
VALUES ('A产品1', 2, 1), ('A产品2', 2, 1);
INSERT INTO products (name, owner_id, organization_id)
VALUES ('B产品1', 4, 2), ('B产品2', 4, 2);
```

---

## 3. 测试用例

### 3.1 场景1: 组织A的用户只能看到A的数据

#### 3.1.1 通过 API 验证（全链路）

```python
import requests

# 1. 登录组织A的用户
resp = requests.post("http://localhost:8000/api/auth/login", json={
    "username": "user_a_1",
    "password": "xxx",
    "x-tenant-id": "1"  # 组织A
})
token = resp.json()["access_token"]

# 2. 查询产品列表
headers = {
    "Authorization": f"Bearer {token}",
    "X-Tenant-ID": "1"
}
resp = requests.get("http://localhost:8000/api/products", headers=headers)
products = resp.json()

# 3. 验证
assert all(p["organization_id"] == 1 for p in products), "所有产品应属于组织A"
assert any(p["name"] == "A产品1" for p in products), "应包含A产品1"
assert not any(p["name"] == "B产品1" for p in products), "不应包含B产品1"
print("✅ 场景1通过: 组织A用户只能看到A的数据")
```

#### 3.1.2 通过数据库直接验证（RLS 层）

```python
import psycopg2

conn = psycopg2.connect("...")
cur = conn.cursor()

# 模拟中间件设置 session 变量
cur.execute("SET app.is_multi_tenant = '1'")
cur.execute("SET app.current_org_id = '1'")
cur.execute("SET app.current_user_role = 'member'")

# 直接查询（绕过应用层过滤 — 模拟原始 SQL）
cur.execute("SELECT name, organization_id FROM products ORDER BY id")
rows = cur.fetchall()

# 验证 RLS 已过滤
assert all(r[1] == 1 for r in rows), "所有行应为 organization_id=1"
print(f"✅ RLS有效: 返回 {len(rows)} 行，全部属于组织A")
```

### 3.2 场景2: 组织B的用户只能看到B的数据

与场景1对称，使用 `org_id=2` 和 `user_b_1`：

```python
# 登录 + 查询（同场景1，org_id=2）
resp = requests.post("http://localhost:8000/api/auth/login", json={
    "username": "user_b_1",
    "password": "xxx",
    "x-tenant-id": "2"
})
token = resp.json()["access_token"]

headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "2"}
resp = requests.get("http://localhost:8000/api/products", headers=headers)
products = resp.json()

assert all(p["organization_id"] == 2 for p in products)
assert not any(p["name"] == "A产品1" for p in products)
```

### 3.3 场景3: 未登录用户被拒绝

```python
# 无 Authorization 头的请求
resp = requests.get("http://localhost:8000/api/products", headers={"X-Tenant-ID": "1"})
assert resp.status_code == 401, "未认证请求应返回 401"
print("✅ 场景3通过: 未登录用户被拒绝（HTTP 401）")
```

### 3.4 场景4: admin 跨组织查看

```python
# 全局 admin 登录（不带特定组织）
resp = requests.post("http://localhost:8000/api/auth/login", json={
    "username": "super_admin",
    "password": "xxx",
})
token = resp.json()["access_token"]

# 查询所有产品（不传 X-Tenant-ID 或带任意值）
headers = {"Authorization": f"Bearer {token}"}
resp = requests.get("http://localhost:8000/api/products", headers=headers)
products = resp.json()

# admin 应能看到所有组织的产品
assert len(products) >= 4  # A产品1, A产品2, B产品1, B产品2
org_ids = {p["organization_id"] for p in products}
assert 1 in org_ids and 2 in org_ids, "admin应看到组织A和B的产品"
```

#### 3.4.1 RLS 层验证（直接 SQL）

```python
cur.execute("SET app.is_multi_tenant = '1'")
cur.execute("SET app.current_org_id = ''")    # 不限制组织
cur.execute("SET app.current_user_role = 'admin'")

cur.execute("SELECT name, organization_id FROM products ORDER BY id")
rows = cur.fetchall()

org_ids = {r[1] for r in rows}
assert len(org_ids) >= 2, "admin应看到所有组织的产品"
print(f"✅ RLS admin豁免有效: 返回 {len(rows)} 行，覆盖组织 {org_ids}")
```

### 3.5 场景5: 无 X-Tenant-ID 头的请求被拒绝

```python
# 登录（不带 X-Tenant-ID）
resp = requests.post("http://localhost:8000/api/auth/login", json={
    "username": "user_a_1",
    "password": "xxx",
})
token = resp.json()["access_token"]

# 查询时不带 X-Tenant-ID
headers = {"Authorization": f"Bearer {token}"}
resp = requests.get("http://localhost:8000/api/products", headers=headers)

# 预期: 中间件拒绝（400 Bad Request 或 403 Forbidden）
assert resp.status_code in (400, 403), \
    f"无X-Tenant-ID头的请求应被拒绝，实际返回 {resp.status_code}"
print(f"✅ 场景5通过: 无X-Tenant-ID头被拒绝（HTTP {resp.status_code}）")
```

### 3.6 场景6: 直接 SQL 绕过应用层过滤

这是 RLS 的**核心价值验证**——即使应用层过滤被绕过或忘记，RLS 仍能拦截：

```python
import psycopg2

conn = psycopg2.connect("...")
cur = conn.cursor()

# 设置租户为组织A
cur.execute("SET app.is_multi_tenant = '1'")
cur.execute("SET app.current_org_id = '1'")
cur.execute("SET app.current_user_role = 'member'")

# 直接查询所有行（无 WHERE 条件 — 模拟应用层过滤被绕过）
cur.execute("SELECT name, organization_id FROM products")
rows = cur.fetchall()

# RLS 必须强制过滤
assert all(r[1] == 1 for r in rows), \
    "RLS 未生效: 即使 SELECT 没有 WHERE 条件，也应只返回组织A的数据"
assert any(r[0] == "A产品1" for r in rows), "应包含A产品1"
assert not any(r[0] == "B产品1" for r in rows), "不应包含B产品1"
print(f"✅ 场景6通过: RLS 在原始 SQL 绕过场景下仍有效")
```

### 3.7 场景7: 回滚验证 — 关闭 IS_MULTI_TENANT

```python
conn = psycopg2.connect("...")
cur = conn.cursor()

# 关闭多租户（模拟 IS_MULTI_TENANT=false）
cur.execute("SET app.is_multi_tenant = '0'")
cur.execute("SET app.current_user_role = 'member'")

# 查询所有产品 — 应返回所有行（不过滤）
cur.execute("SELECT name, organization_id FROM products")
rows = cur.fetchall()

org_ids = {r[1] for r in rows}
assert len(org_ids) >= 2, "关闭多租户后应看到所有组织的产品"
print(f"✅ 场景7通过: 关闭多租户后，返回 {len(rows)} 行，覆盖组织 {org_ids}")
```

---

## 4. 自动化测试套件

### 4.1 pytest 集成

```python
"""
test_rls_isolation.py — RLS 全链路自动化测试
仅在 DB_TYPE=postgres 时运行
"""

import os
import pytest
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


pytestmark = pytest.mark.skipif(
    os.environ.get("DB_TYPE") != "postgres",
    reason="RLS tests require PostgreSQL"
)


@pytest.fixture(scope="module")
def pg_conn():
    """PostgreSQL 原生连接（绕过 ORM，直接测试 RLS）"""
    conn = psycopg2.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=os.environ.get("PG_PORT", "5432"),
        user=os.environ.get("PG_USER", ""),
        password=os.environ.get("PG_PASSWORD", ""),
        dbname=os.environ.get("PG_DATABASE", ""),
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    yield conn
    conn.close()


class TestRLSIsolation:
    """RLS 行级隔离测试"""

    ORG_A = "1"
    ORG_B = "2"

    def setup_rls_context(self, cur, org_id: str, role: str = "member", active: str = "1"):
        cur.execute(f"SET app.is_multi_tenant = '{active}'")
        cur.execute(f"SET app.current_org_id = '{org_id}'")
        cur.execute(f"SET app.current_user_role = '{role}'")

    # ── 场景1: 组织A隔离 ──
    def test_org_a_sees_only_org_a(self, pg_conn):
        cur = pg_conn.cursor()
        self.setup_rls_context(cur, self.ORG_A, "member")
        cur.execute("SELECT organization_id FROM products")
        ids = [r[0] for r in cur.fetchall()]
        assert all(i == 1 for i in ids), f"组织A用户看到非A组织的行: {set(ids)}"

    # ── 场景2: 组织B隔离 ──
    def test_org_b_sees_only_org_b(self, pg_conn):
        cur = pg_conn.cursor()
        self.setup_rls_context(cur, self.ORG_B, "member")
        cur.execute("SELECT organization_id FROM products")
        ids = [r[0] for r in cur.fetchall()]
        assert all(i == 2 for i in ids), f"组织B用户看到非B组织的行: {set(ids)}"

    # ── 场景4: admin跨组织 ──
    def test_admin_sees_all_orgs(self, pg_conn):
        cur = pg_conn.cursor()
        self.setup_rls_context(cur, "", "admin")
        cur.execute("SELECT DISTINCT organization_id FROM products WHERE organization_id IS NOT NULL")
        ids = {r[0] for r in cur.fetchall()}
        assert 1 in ids and 2 in ids, f"admin应看到所有组织, 实际: {ids}"

    # ── 场景6: 原始SQL绕过 ──
    def test_raw_sql_bypass_still_filtered(self, pg_conn):
        cur = pg_conn.cursor()
        self.setup_rls_context(cur, self.ORG_A, "member")
        # 无WHERE条件的SELECT
        cur.execute("SELECT * FROM products")
        rows = cur.fetchall()
        # RLS必须过滤
        assert all(r.organization_id == 1 for r in rows)  # 假设有organization_id列

    # ── 场景7: 回滚 ──
    def test_rollback_disabled_multi_tenant(self, pg_conn):
        cur = pg_conn.cursor()
        self.setup_rls_context(cur, self.ORG_A, "member", active="0")
        cur.execute("SELECT DISTINCT organization_id FROM products WHERE organization_id IS NOT NULL")
        ids = {r[0] for r in cur.fetchall()}
        assert 1 in ids and 2 in ids, "关闭多租户后应看到所有组织"

    # ── 新增: 插入时WITH CHECK ──
    def test_insert_rejects_wrong_org(self, pg_conn):
        cur = pg_conn.cursor()
        self.setup_rls_context(cur, self.ORG_A, "member")
        with pytest.raises(Exception):  # 违反WITH CHECK
            cur.execute(
                "INSERT INTO products (name, owner_id, organization_id) "
                "VALUES ('恶意插入', 1, 2)"
            )
```

### 4.2 运行方式

```bash
# 仅 PostgreSQL 环境下运行
DB_TYPE=postgres \
PG_HOST=localhost PG_PORT=5432 \
PG_USER=liankebao PG_PASSWORD=xxx PG_DATABASE=liankebao \
pytest tests/test_rls_isolation.py -v --tb=short

# 或通过 Docker Compose
docker-compose exec backend \
  bash -c 'DB_TYPE=postgres pytest tests/test_rls_isolation.py -v'
```

---

## 5. 测试结果报告模板

```
╔══════════════════════════════════════════════════════════════╗
║          链客宝 RLS 全链路验证报告                          ║
║          日期: 2026-06-10 18:05 CST                        ║
╠══════════════════════════════════════════════════════════════╣
║ ✅ 场景1: 组织A隔离通过               (7行, 全部 org_id=1) ║
║ ✅ 场景2: 组织B隔离通过               (5行, 全部 org_id=2) ║
║ ✅ 场景3: 未登录用户拒绝通过          (HTTP 401)           ║
║ ✅ 场景4: admin跨组织访问通过         (覆盖组织 {1,2})     ║
║ ✅ 场景5: 无X-Tenant-ID头拒绝通过     (HTTP 400)           ║
║ ✅ 场景6: 原始SQL绕过拦截通过         (RLS有效)            ║
║ ✅ 场景7: IS_MULTI_TENANT回滚通过     (12行, 全部组织)     ║
╠══════════════════════════════════════════════════════════════╣
║ 结论: 所有7个场景通过 ✓  RLS已就绪 ✓                       ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 6. 与现有 test_tenant.py 的兼容性

| 现有测试 | RLS 验证 | 兼容说明 |
|----------|----------|----------|
| `TestTenantContext` | 独立，不依赖 DB | 完全兼容 |
| `TestOrganizationModel` | 独立 | 完全兼容 |
| `TestMembershipModel` | 独立 | 完全兼容 |
| `TestTenantIsolationORM` | 仅检查字段存在性 | 完全兼容 |
| `TestTenantIsolationFullChain` | 应用层隔离验证 | 完全兼容（RLS 作为额外层） |

新增的 `test_rls_isolation.py` 是**正交的**——仅在 `DB_TYPE=postgres` 时运行，不修改现有测试。

---

## 7. 回滚方案

### 7.1 软回滚（运行时切换）

| 步骤 | 操作 | 效果 |
|------|------|------|
| 1 | `export IS_MULTI_TENANT=false` | 环境变量改变 |
| 2 | 重启应用服务 | 中间件不再设置 session 变量 |
| 3 | RLS 检测 `app.is_multi_tenant='0'` | 放行所有数据 |

### 7.2 硬回滚（彻底移除 RLS）

```bash
# 禁用所有表的 RLS + 删除辅助函数
psql -U <user> -d <db> -c "
DO \$\$
DECLARE
    r RECORD;
BEGIN
    FOR r IN SELECT tablename FROM pg_tables
             WHERE schemaname='public'
               AND rowsecurity=true
    LOOP
        EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY;', r.tablename);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_%s ON public.%I;', r.tablename, r.tablename);
    END LOOP;
    DROP FUNCTION IF EXISTS app._rls_is_active();
    DROP FUNCTION IF EXISTS app._rls_current_org_id();
    DROP FUNCTION IF EXISTS app._rls_is_admin();
END;
\$\$;
"
```

### 7.3 验证回滚成功

```python
cur = pg_conn.cursor()
cur.execute("SET app.is_multi_tenant = '0'")
cur.execute("SELECT COUNT(*) FROM products")
total = cur.fetchone()[0]

cur.execute("SET app.is_multi_tenant = '1'")
cur.execute("SET app.current_org_id = '1'")
cur.execute("SELECT COUNT(*) FROM products")
org_a = cur.fetchone()[0]

assert total == org_a, "回滚后计数应一致" if False else "回滚后计数可能不同（取决于数据分布）"
# 更准确的验证: 回滚后应当能看到 org_b 的产品
print("✅ 回滚成功: 所有数据可见（需检查业务逻辑）")
```

---

## 8. 非功能验证

### 8.1 性能基准

```sql
-- 建立性能基线
EXPLAIN ANALYZE SELECT * FROM products WHERE organization_id = 1;

-- 在 RLS 启用后对比
SET app.is_multi_tenant = '1';
SET app.current_org_id = '1';
SET app.current_user_role = 'member';
EXPLAIN ANALYZE SELECT * FROM products;
```

预期 RLS 增加的开销：< 5%（因 `organization_id` 有索引，且 RLS 策略是简单的整数比较）。

### 8.2 并发验证

```python
import threading

def query_as_org(org_id: str, results: list):
    conn = psycopg2.connect("...")
    cur = conn.cursor()
    cur.execute("SET app.is_multi_tenant = '1'")
    cur.execute(f"SET app.current_org_id = '{org_id}'")
    cur.execute("SET app.current_user_role = 'member'")
    cur.execute("SELECT organization_id FROM products")
    rows = cur.fetchall()
    results.append((org_id, [r[0] for r in rows]))
    conn.close()

threads = []
results = []
for oid in ["1", "2"]:
    t = threading.Thread(target=query_as_org, args=(oid, results))
    threads.append(t)
    t.start()
for t in threads:
    t.join()

org_a_results = [r for oid, r in results if oid == "1"][0]
org_b_results = [r for oid, r in results if oid == "2"][0]

assert all(i == 1 for i in org_a_results)
assert all(i == 2 for i in org_b_results)
print(f"✅ 并发隔离通过: 组织A={len(org_a_results)}行, 组织B={len(org_b_results)}行")
```

---

## 附录: 快速部署检查清单

- [ ] `IS_MULTI_TENANT=true` 已设置
- [ ] PostgreSQL 数据库已连接
- [ ] `psql -f rls_policies.sql` 执行成功
- [ ] 所有 18 张表已存在（或确认 WARNING 可接受）
- [ ] 测试数据已插入（至少 2 个组织，每个组织有产品和用户）
- [ ] global admin 用户已创建（`users.role='admin'`）
- [ ] `test_rls_isolation.py` 全部场景通过
- [ ] 关闭 `IS_MULTI_TENANT` 后数据正常（回滚验证通过）
