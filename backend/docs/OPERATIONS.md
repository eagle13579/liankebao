# 链客宝多租户运维手册 (OPERATIONS)

- **版本**: 1.0
- **最后更新**: 2026-06-10
- **维护人**: 文鳐 / 烛龙
- **适用范围**: 生产环境 (47.116.116.87) 及预发布环境

---

## 1. 环境变量配置

### 1.1 `DATABASE_URL` 配置说明

链客宝支持两种数据库模式切换，由环境变量控制：

#### SQLite 模式（开发/单机/回滚兜底）

```bash
# 无需设置 DB_TYPE，默认即为 sqlite
# 可选自定义目录与文件名
export SQLITE_DIR=/data/chainke
export SQLITE_DB_NAME=chainke.db
```

**数据路径**: `${SQLITE_DIR}/${SQLITE_DB_NAME}`，默认 `./data/chainke.db`

#### PostgreSQL 模式（生产/多租户）

```bash
export DB_TYPE=postgres
export DATABASE_URL="postgresql+psycopg2://chainke_app:密码@127.0.0.1:5432/chainke_prod"
# 或使用拆分变量（DATABASE_URL 优先级更高）:
export PG_HOST=127.0.0.1
export PG_PORT=5432
export PG_USER=chainke_app
export PG_PASSWORD=密码
export PG_DATABASE=chainke_prod
```

### 1.2 多租户开关

```bash
# PostgreSQL 模式下默认启用
export IS_MULTI_TENANT=true   # 或 "1" / "yes"

# 紧急关闭（RLS 误触发时使用）
export IS_MULTI_TENANT=false
```

**注意**: `IS_MULTI_TENANT` 在 `database.py` 中由 `is_multi_tenant()` 函数控制，该函数仅检查 `DB_TYPE == "postgres"`。`IS_MULTI_TENANT` 环境变量在 `tenant.py` 中控制 `Membership` 模型是否定义，两者协同工作。

### 1.3 快速切换示例

```bash
# 当前: SQLite → 切到 PG（迁移后）
export DB_TYPE=postgres
export DATABASE_URL="postgresql+psycopg2://chainke_app:pass@localhost:5432/chainke_prod"
systemctl restart chainke-backend

# 回滚: PG → SQLite
unset DB_TYPE
unset DATABASE_URL
systemctl restart chainke-backend
```

---

## 2. 部署检查清单

### 生产环境首次部署 / 迁移后验证

| # | 检查项 | 验证方法 | 通过标准 |
|---|--------|----------|----------|
| 1 | `DB_TYPE` 环境变量 | `echo $DB_TYPE` | 输出 `postgres` |
| 2 | `DATABASE_URL` 连接性 | `psql "$DATABASE_URL" -c "SELECT 1"` | 返回 `1` 行 |
| 3 | RLS 策略已创建 | `psql -c "\d+ 表名"` | `Policies:` 字段显示策略 |
| 4 | 18 张表均含 `organization_id` | `psql -c "\dt+"` + 逐表检查 | 每张表含该列 |
| 5 | 存量数据 `organization_id` 无 NULL | `psql -c "SELECT count(*) FROM 表 WHERE organization_id IS NULL;"` | 所有表结果为 0 |
| 6 | 应用启动日志 | `journalctl -u chainke-backend --since "5 min ago"` | 日志显示 `数据库模式: postgres` |
| 7 | 跨租户隔离验证 | 用两个不同 org 的 token 请求 API | 数据互不可见 |
| 8 | 心跳/健康检查 | `curl http://localhost:8000/health` | 返回 `200 OK` |
| 9 | 备份策略已配置 | `crontab -l` | 包含 pg_dump 定时任务 |
| 10 | 监控告警已接入 | 检查 Prometheus / Grafana | PG 连接数、慢查询指标正常 |

---

## 3. 日常运维

### 3.1 备份策略

#### PostgreSQL 备份（生产环境）

```bash
# === 全量备份（每日） ===
# crontab: 0 3 * * *  pg_dump -h localhost -U chainke_app chainke_prod > /backup/pg/chainke_$(date +\%Y\%m\%d).sql
pg_dump -h localhost -U chainke_app -Fc chainke_prod > /backup/pg/chainke_$(date +%Y%m%d).dump

# === WAL 归档（开启 PITR 能力） ===
# 在 postgresql.conf 中设置:
#   wal_level = replica
#   archive_mode = on
#   archive_command = 'cp %p /backup/pg/wal/%f'

# === 保留策略 ===
# - 每日全量: 保留 30 天
# - WAL 归档: 保留 7 天
# - 每月归档: 保留 12 个月
```

#### SQLite 备份（开发环境 / 回滚兜底）

```bash
# 文件级备份（需停写或使用备份 API）
sqlite3 /data/chainke/chainke.db ".backup '/backup/sqlite/chainke_$(date +%Y%m%d).db'"

# 或使用 WAL 模式下的文件拷贝（风险较高）
cp /data/chainke/chainke.db /backup/sqlite/chainke_$(date +%Y%m%d).db
cp /data/chainke/chainke.db-wal /backup/sqlite/
```

**对比总结**:

| 特性 | PostgreSQL | SQLite |
|------|-----------|--------|
| 备份方式 | `pg_dump` / WAL 归档 | 文件拷贝 / `.backup` |
| 支持 PITR | ✅ 是 | ❌ 否 |
| 热备份 | ✅ 在线备份不影响读写 | ⚠️ 需 WAL 模式 + 只读备份 |
| 备份大小 | 压缩后约为数据量 30~50% | 等于数据文件大小 |
| 恢复时间 | 分钟级（全量 + WAL replay） | 秒级（拷贝文件） |

### 3.2 监控指标

| 指标 | 来源 | 告警阈值 | 说明 |
|------|------|----------|------|
| PG 连接数 | `pg_stat_activity` | > 80% max_connections | 连接池不足 |
| 活跃查询数 | `pg_stat_activity` | > 50 | 慢查询或锁竞争 |
| 死元组比例 | `pg_stat_user_tables` | > 20% | 需要 VACUUM |
| 复制延迟 | `pg_stat_replication` | > 10s | 主从不同步 |
| 最长事务时间 | `pg_stat_activity` | > 30min | 长事务阻塞 VACUUM |
| 慢查询 (>500ms) | `pg_stat_statements` | > 5/min | 需优化索引或 SQL |
| 磁盘使用率 | `df -h /var/lib/postgresql` | > 85% | 磁盘不足 |
| 应用 5xx 比率 | Nginx / Grafana | > 1% | 后端异常 |

### 3.3 日志位置

| 组件 | 日志路径 | 查看命令 |
|------|----------|----------|
| 后端应用 | `/var/log/chainke-backend/` 或 journald | `journalctl -u chainke-backend -f` |
| PostgreSQL | `/var/log/postgresql/postgresql-15-main.log` | `tail -f /var/log/postgresql/*.log` |
| Nginx | `/var/log/nginx/access.log` + `error.log` | `tail -f /var/log/nginx/access.log` |
| 迁移日志 | `/var/log/chainke/migration-YYYYMMDD.log` | `cat /var/log/chainke/migration-*.log` |
| RLS 审计日志 | `postgresql.conf` 中设置 `log_line_prefix` + `log_statement = 'ddl'` | `grep "POLICY" /var/log/postgresql/*.log` |

---

## 4. 故障恢复

### 4.1 PG 宕机 → 切回 SQLite 做读服务

**场景**: PostgreSQL 实例异常（服务不可用、磁盘满、数据损坏），需快速恢复系统可用性。

**步骤**:

```bash
# 1. 确认 PG 状态
pg_isready -h localhost
systemctl status postgresql

# 2. 如果 PG 无法快速恢复，切到 SQLite 只读模式
#    修改环境变量并重启
systemctl stop chainke-backend
unset DB_TYPE
unset DATABASE_URL
export SQLITE_DIR=/data/chainke
export SQLITE_DB_NAME=chainke.db
systemctl start chainke-backend

# 3. 验证只读服务可用
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/products  # 应返回缓存或存量数据

# 4. 限制写操作入口（关闭订单/创建 API 或返回503）
#    在 Nginx 层对 POST/PUT/DELETE 统一返回维护页
```

**恢复**:

```bash
# 1. PG 修复后，同步数据（从上次 SQLite 备份恢复写操作期间产生的增量数据）
# 2. 切回 PG 模式
export DB_TYPE=postgres
export DATABASE_URL="postgresql+psycopg2://chainke_app:pass@localhost:5432/chainke_prod"
systemctl restart chainke-backend
# 3. 验证数据完整性
```

### 4.2 数据损坏 → PITR 恢复

**场景**: 误操作或 bug 导致数据损坏，需要恢复到某个时间点。

**前提条件**: 已开启 WAL 归档。

```bash
# 1. 停止应用
systemctl stop chainke-backend

# 2. 恢复到目标时间点
#    在 postgresql.conf 中设置:
#     restore_command = 'cp /backup/pg/wal/%f %p'
#     recovery_target_time = '2026-06-10 14:30:00 CST'
#    创建 recovery.signal 文件
touch /var/lib/postgresql/15/main/recovery.signal

# 3. 启动 PG，自动进入恢复模式
systemctl start postgresql
#    检查日志: 应看到 "recovery stopping at time ..."
tail -f /var/log/postgresql/postgresql-15-main.log

# 4. 验证数据
psql -c "SELECT COUNT(*) FROM orders;"
psql -c "SELECT * FROM products WHERE ..."

# 5. 确认无误后，停止 PG，删除 recovery.signal，重启进入正常模式
systemctl stop postgresql
rm /var/lib/postgresql/15/main/recovery.signal
systemctl start postgresql

# 6. 启动应用
systemctl start chainke-backend

# 7. 通知用户数据已恢复到指定时间点
```

**无 WAL 归档时的降级恢复**:

```bash
# 使用最近的全量备份恢复
pg_dump -h localhost -U chainke_app chainke_prod -Fc > /tmp/corrupted_backup.dump  # 备份已损坏数据用于分析
dropdb chainke_prod
createdb chainke_prod
pg_restore -h localhost -U chainke_app -d chainke_prod /backup/pg/chainke_latest.dump
```

### 4.3 RLS 误触发 → 关闭 IS_MULTI_TENANT

**场景**: RLS 策略配置错误，导致合法请求被拦截（如管理员无法查看跨租户数据、所有用户看不到任何数据）。

**症状**: API 返回空列表 `[]` 或 `403 Forbidden`，日志出现 `ERROR: new row violates row-level security policy for table`。

```bash
# 快速恢复（1~2 分钟内恢复服务）:

# 方案 A: 应用层关闭多租户（最快）
export IS_MULTI_TENANT=false
systemctl restart chainke-backend

# 验证: 此时所有 organization_id 过滤失效，所有用户可见全部数据（降级但可用）

# 方案 B: 保留 PG 但禁用 RLS（需 DBA 权限）
psql -U chainke_app -d chainke_prod -c "ALTER TABLE products DISABLE ROW LEVEL SECURITY;"
psql -U chainke_app -d chainke_prod -c "ALTER TABLE orders DISABLE ROW LEVEL SECURITY;"
# ... 对受影响的表执行相同操作

# 排查问题:
# 1. 检查 RLS 策略定义
psql -U chainke_app -d chainke_prod -c "\dp products"
psql -U chainke_app -d chainke_prod -c "\d+ products"

# 2. 测试 current_setting 值
#    在应用日志中确认 TenantContext 设置的值是否正确
journalctl -u chainke-backend --since "10 min ago" | grep "tenant_id\|org_id\|RLS"

# 3. 修复策略后重新启用
psql -U chainke_app -d chainke_prod -c "DROP POLICY IF EXISTS tenant_isolation ON products;"
psql -U chainke_app -d chainke_prod -c "CREATE POLICY tenant_isolation ON products FOR ALL USING (organization_id = current_setting('app.current_tenant_id')::int);"
psql -U chainke_app -d chainke_prod -c "ALTER TABLE products ENABLE ROW LEVEL SECURITY;"

# 4. 重新启用多租户
export IS_MULTI_TENANT=true
systemctl restart chainke-backend
```

---

## 5. 扩容指南

### 5.1 阶段一：单机 Docker PostgreSQL（当前，适合 < 1000 并发用户）

**部署方式**:

```yaml
# docker-compose.yml
version: "3.8"
services:
  postgres:
    image: postgres:15-alpine
    container_name: chainke-pg
    environment:
      POSTGRES_DB: chainke_prod
      POSTGRES_USER: chainke_app
      POSTGRES_PASSWORD: ${PG_PASSWORD}
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./init-rls.sql:/docker-entrypoint-initdb.d/init-rls.sql
    ports:
      - "127.0.0.1:5432:5432"
    deploy:
      resources:
        limits:
          cpus: "2"
          memory: "4G"
    restart: unless-stopped

volumes:
  pg_data:
```

**性能预期**: 2 vCPU / 4 GB RAM 下支持 ~2000 TPS，~50 GB 数据。

### 5.2 阶段二：阿里云 RDS PostgreSQL（适合 1000~10000 并发用户）

| 配置项 | 建议值 |
|--------|--------|
| 规格 | rds.pg.gp2.small（2C8G）起步 |
| 存储 | ESSD PL1，500 GB，自动扩容 |
| 连接池 | PgBouncer（RDS 内置） |
| 备份 | 自动备份 + 日志备份（7 天） |
| 安全组 | 仅放行应用服务器 IP |
| 费用预估 | ¥300~800/月 |

**切换步骤**:

```bash
# 1. 在 RDS 控制台创建实例，白名单添加应用服务器 IP
# 2. 从单机 PG 导出数据
pg_dump -h localhost -U chainke_app -Fc chainke_prod > /tmp/chainke_rds.dump
# 3. 导入 RDS
pg_restore -h rds-endpoint.aliyuncs.com -U chainke_app -d chainke_prod /tmp/chainke_rds.dump
# 4. 修改环境变量
export DATABASE_URL="postgresql+psycopg2://chainke_app:密码@rds-endpoint.aliyuncs.com:5432/chainke_prod"
systemctl restart chainke-backend
# 5. 验证后停止单机 PG 容器
docker stop chainke-pg
```

### 5.3 阶段三：PG 主从 + 读写分离（适合 > 10000 并发用户）

**架构**:

```
                ┌─────────────┐
                │  PgBouncer   │ 连接池
                └──────┬──────┘
                       │
               ┌───────┴────────┐
               │   MaxScale /    │  读写分离代理
               │  HAProxy 等     │
               └──┬──────────┬──┘
                  │          │
          ┌───────▼──┐  ┌───▼────────┐
          │  PG 主   │  │  PG 只读1   │
          │ (写入)   │  │ (查询)      │
          └───────┬──┘  └────────────┘
                  │           │
                  │     ┌─────▼──────┐
                  │     │  PG 只读2   │
                  │     │ (报表查询)  │
                  │     └────────────┘
                  │
          ┌───────▼────────┐
          │  Streaming     │
          │  Replication   │
          └────────────────┘
```

**配置要点**:

```bash
# 主库 postgresql.conf
wal_level = replica
max_wal_senders = 5
wal_keep_size = 1024  # MB

# 从库（standby.signal 文件）
primary_conninfo = 'host=主库IP port=5432 user=replicator password=密码'
```

**应用适配**:

```python
# 在 database.py 中配置读写分离引擎
from sqlalchemy import create_engine

reader_engine = create_engine(
    "postgresql+psycopg2://user:pass@reader-endpoint:5432/chainke_prod",
    pool_size=20,
    max_overflow=40,
)
writer_engine = create_engine(
    "postgresql+psycopg2://user:pass@writer-endpoint:5432/chainke_prod",
    pool_size=10,
    max_overflow=20,
)
# 获取 Session 时按需选择引擎
```

---

## 6. 附录

### 6.1 环境变量速查表

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DB_TYPE` | `sqlite` | 数据库类型: `sqlite` / `postgres` / `mysql` |
| `DATABASE_URL` | 空 | 完整连接 URL，优先于拆分变量 |
| `IS_MULTI_TENANT` | `true` | 多租户开关 |
| `PG_HOST` | `localhost` | PG 主机地址 |
| `PG_PORT` | `5432` | PG 端口 |
| `PG_USER` | 空 | PG 用户名 |
| `PG_PASSWORD` | 空 | PG 密码 |
| `PG_DATABASE` | 空 | PG 数据库名 |
| `SQLITE_DIR` | `./data` | SQLite 文件目录 |
| `SQLITE_DB_NAME` | `chainke.db` | SQLite 文件名 |

### 6.2 相关文件

| 文件 | 用途 |
|------|------|
| `D:\链客宝\backend\app\database.py` | 数据库引擎创建、连接管理 |
| `D:\链客宝\backend\app\tenant.py` | 多租户上下文管理、应用层过滤 |
| `D:\链客宝\backend\app\models.py` | ORM 模型定义，`_org_fk()` 多租户外键 |
| `D:\链客宝\backend\docs\ADR-009.md` | 多租户迁移架构决策记录 |
| `/docker-compose.yml` | Docker Compose 部署配置 |
| `/init-rls.sql` | RLS 策略初始化脚本 |

### 6.3 相关联系人

| 角色 | 姓名 | 职责 |
|------|------|------|
| 架构师 | 文鳐 | ADR-009 决策记录、技术方案设计 |
| 后端负责人 | 白泽 | 应用层改造、数据迁移脚本 |
| DevOps | 烛龙 | PG 部署、备份策略、故障恢复 |
| 测试负责人 | 狴犴 | 多租户隔离验证、压力测试 |
