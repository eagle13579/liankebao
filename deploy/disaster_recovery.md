# 链客宝 多区域灾备方案

> 版本: 1.0 | 最后更新: 2026-05-29
> 目标: RTO ≤ 30分钟, RPO ≤ 5分钟

---

## 1. 总体架构

```
                          ┌─────────────────────────────────┐
                          │     阿里云 DNS (云解析)          │
                          │    健康检查 + 故障切换           │
                          │    TTL: 2分钟                    │
                          └──────────┬──────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
            ┌───────▼───────┐  ┌────▼────────┐  ┌───┴────────┐
            │  北京 Region   │  │  上海 Region │  │   第三方    │
            │  (主)          │  │  (备)        │  │   CDN      │
            │  cn-beijing    │  │  cn-shanghai  │  │(静态资源)   │
            └───────┬───────┘  └────┬────────┘  └────────────┘
                    │                │
       ┌────────────┼────────────┐  │
       │            │            │  │
  ┌────▼───┐  ┌────▼───┐  ┌────▼──┐│
  │ SLB    │  │ API    │  │ OSS   ││
  │ (负载) │  │ Gateway│  │ (主)  ││
  └────┬───┘  └────┬───┘  └───┬───┘│
       │           │           │    │
  ┌────▼───────────▼──────┐    │    │
  │  K8s 集群 (ACK)       │    │    │
  │  - 链客宝服务实例 x3   │    │    │
  │  - Nginx Ingress      │    │    │
  └────┬──────────────────┘    │    │
       │                       │    │
  ┌────▼──────────────┐       │    │
  │  PostgreSQL 主库   │◄──────┘    │
  │  (北京)            │            │
  └────┬───────────────┘            │
       │ 流复制 (异步)              │
       │ RPO ≤ 5分钟                │
  ┌────▼──────────────┐            │
  │ PostgreSQL 从库    │            │
  │  (上海 + 北京本地)  │            │
  └────────────────────┘            │
                                    │
  ┌─────────────────────────────────┘
  │
  ▼
  OSS 跨区域同步 (北京 ⇄ 上海)
  ─ 用户上传文件自动同步
  ─ 存储日志自动同步
```

### 1.1 区域规格

| 区域 | 角色 | VPC CIDR | K8s集群 | 数据库实例 |
|------|------|----------|---------|-----------|
| 北京 (cn-beijing) | 主 | 10.1.0.0/16 | ACK 8C16G x3 | PG 主 4C8G 100GB SSD |
| 上海 (cn-shanghai) | 备 | 10.2.0.0/16 | ACK 4C8G x2 | PG 从 4C8G 100GB SSD |

### 1.2 关键配置参数

| 指标 | 参数 | 说明 |
|------|------|------|
| DNS TTL | 2 分钟 | 阿里云DNS A记录 |
| DNS健康检查 | 每30秒1次 | HTTP GET /health |
| DNS故障阈值 | 连续3次失败 | 切换至上海 |
| RTO | ≤ 30 分钟 | 从故障发生到完全恢复 |
| RPO | ≤ 5 分钟 | 异步流复制延迟 |
| 数据校验 | 每15分钟 | WAL位置对比 |

---

## 2. 数据库灾备

### 2.1 PostgreSQL 主从流复制

**北京主库 → 上海从库 (异步流复制)**

```sql
-- 主库配置 (postgresql.conf)
wal_level = replica
max_wal_senders = 10
wal_keep_size = 1024    -- MB
max_replication_slots = 10
hot_standby = on

-- 从库配置 (postgresql.conf)
primary_conninfo = 'host=10.1.x.x port=5432 user=replicator password=*** sslmode=require'
primary_slot_name = 'shanghai_slot'
hot_standby = on
hot_standby_feedback = on
```

**复制槽管理脚本** (`deploy/db/replication_slot_check.sh`):

```bash
#!/bin/bash
# 每5分钟检查复制延迟
PGHOST=localhost PGUSER=postgres PGDATABASE=chainke psql -c "
SELECT slot_name, slot_type, active,
       pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) AS restart_delta,
       pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn) AS flush_delta
FROM pg_replication_slots
WHERE slot_name = 'shanghai_slot';
"
```

### 2.2 监控复制延迟

```sql
-- 查看复制延迟
SELECT
  application_name,
  state,
  sync_state,
  pg_wal_lsn_diff(pg_current_wal_lsn(), write_lsn) AS write_delay,
  pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) AS flush_delay,
  pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_delay
FROM pg_stat_replication;
```

### 2.3 主从切换步骤

> 手动切换，预计耗时 5-10 分钟

```bash
# === 步骤1: 检查上海从库状态 ===
psql -h shanghai-db -c "SELECT pg_is_in_recovery();"
# 返回 true 表示是从库

# === 步骤2: 上海从库提升为主库 ===
psql -h shanghai-db -c "SELECT pg_promote();"

# === 步骤3: 验证上海已变为主库 ===
psql -h shanghai-db -c "SELECT pg_is_in_recovery();"
# 返回 false

# === 步骤4: 更新应用数据库连接配置 ===
# 修改环境变量 DATABASE_URL 指向上海
# 重启应用实例

# === 步骤5: 北京原主库降为从库 (当北京恢复后) ===
# 在北京库上执行:
pg_ctl -D /var/lib/postgresql/data promote  # 先确保它是主
# 然后配置上海为主库
```

---

## 3. 文件存储灾备 (OSS)

### 3.1 跨区域同步规则

阿里云 OSS 跨区域复制 (CRR) 配置:

| 配置项 | 值 |
|--------|-----|
| 源Bucket | chainke-beijing (北京) |
| 目标Bucket | chainke-shanghai (上海) |
| 同步范围 | 全部文件 |
| 对象加密 | AES-256 服务端加密 |
| 同步类型 | 异步 (最终一致性) |
| 权限 | 继承源Bucket权限 |

### 3.2 手动同步脚本

```bash
#!/bin/bash
# deploy/oss_sync.sh — 手动触发OSS同步
# 使用场景: 故障切换后确保上海Bucket数据最新

OSS_SRC_BUCKET="chainke-beijing"
OSS_DST_BUCKET="chainke-shanghai"
OSS_SRC_ENDPOINT="oss-cn-beijing.aliyuncs.com"
OSS_DST_ENDPOINT="oss-cn-shanghai.aliyuncs.com"

# 列出北京Bucket最近5分钟修改的文件
ossutil ls "oss://${OSS_SRC_BUCKET}" \
  --endpoint "${OSS_SRC_ENDPOINT}" \
  --last-modified-time "$(date -d '5 minutes ago' +%Y-%m-%dT%H:%M:%S)" \
  | while read -r line; do
    file=$(echo "$line" | awk '{print $NF}')
    if [ -n "$file" ]; then
      ossutil cp "$file" "oss://${OSS_DST_BUCKET}/${file#oss://${OSS_SRC_BUCKET}/}" \
        --endpoint "${OSS_DST_ENDPOINT}"
    fi
done
```

---

## 4. DNS 故障切换

### 4.1 阿里云DNS配置

| 记录 | 类型 | 北京值 | 上海值 | TTL | 权重 |
|------|------|--------|--------|-----|------|
| api.chainke.com | A | 北京SLB IP | 上海SLB IP | 120s | 100:0 |
| www.chainke.com | CNAME | CDN域名 | CDN域名 | 60s | - |
| db.chainke.com | A | 北京PG IP | 上海PG IP | 120s | 内部 |

### 4.2 健康检查配置

```yaml
# 阿里云DNS健康检查
CheckConfig:
  Protocol: HTTP
  Port: 8001
  URI: /health
  Interval: 30          # 秒
  Timeout: 5            # 秒
  FailureThreshold: 3   # 连续3次失败触发切换
  SuccessThreshold: 2   # 连续2次成功恢复
```

### 4.3 故障切换触发条件

自动触发:
- DNS健康检查连续3次失败 (约90秒)
- 北京主库宕机超过2分钟

手动触发:
- 运维人员执行切换脚本
- 定期故障演练

### 4.4 DNS切换脚本

```bash
#!/bin/bash
# deploy/dns_failover.sh — DNS故障切换

ACTION=$1  # to-shanghai 或 recover-beijing
DOMAIN="chainke.com"
RECORD="api"
BEIJING_IP="1.2.3.4"    # 北京SLB IP
SHANGHAI_IP="4.3.2.1"   # 上海SLB IP
ALICDN_API="https://dns.aliyuncs.com"

update_dns() {
    local ip=$1
    local weight=$2
    # 调用阿里云DNS API更新解析记录
    aliyun alidns UpdateDomainRecord \
        --RecordId "xxxxx" \
        --RR "${RECORD}" \
        --Type "A" \
        --Value "${ip}" \
        --TTL 120
    echo "[$(date)] DNS切换至: ${ip} (权重: ${weight})"
}

case "${ACTION}" in
    to-shanghai)
        echo "=== 开始DNS切换至上海 ==="
        update_dns "${SHANGHAI_IP}" 100
        echo "=== DNS切换完成 (预计2分钟生效) ==="
        ;;
    recover-beijing)
        echo "=== 开始恢复DNS至北京 ==="
        update_dns "${BEIJING_IP}" 100
        echo "=== DNS恢复完成 ==="
        ;;
    *)
        echo "用法: $0 {to-shanghai|recover-beijing}"
        exit 1
        ;;
esac
```

---

## 5. 故障切换流程 (SOP)

### 5.1 故障发现 → 切换 (预计 5-15 分钟)

| 阶段 | 步骤 | 负责人 | 预计耗时 |
|------|------|--------|---------|
| 1. 确认故障 | 检查告警 → 确认北京Region不可用 | 值班运维 | 2分钟 |
| 2. 数据库提升 | 上海从库提升为主库 | DBA | 3分钟 |
| 3. OSS确认 | 确认OSS跨区域同步完成 | DBA | 1分钟 |
| 4. DNS切换 | 更新DNS记录指向上海SLB | 值班运维 | 2分钟 |
| 5. 应用启动 | 上海K8s集群扩容 (如需要) | 运维 | 5分钟 |
| 6. 验证 | 测试 /health 端点与核心API | 值班运维 | 2分钟 |

### 5.2 应用层恢复步骤

```bash
# === 1. 切换数据库连接 ===
kubectl apply -f deploy/k8s/configmap-shanghai.yaml
# configmap 内容:
#   DATABASE_URL=postgresql://user:pass@shanghai-db:5432/chainke

# === 2. 重启应用Pod ===
kubectl rollout restart deployment/chainke-api -n production
kubectl rollout status deployment/chainke-api -n production --timeout=120s

# === 3. 验证应用健康 ===
curl -s http://shanghai-slb:8001/health | python3 -m json.tool

# === 4. 验证核心业务API ===
curl -s http://shanghai-slb:8001/api/v1/auth/login -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test"}' | head -c 200
```

### 5.3 DNS层恢复步骤

```bash
# === 1. 检查DNS传播 ===
dig api.chainke.com +short
nslookup api.chainke.com 8.8.8.8

# === 2. 更新DNS记录指向上海 ===
bash deploy/dns_failover.sh to-shanghai

# === 3. 验证全球DNS解析 ===
# 使用阿里云DNS诊断工具或dig来自不同地域的DNS服务器
for ns in 8.8.8.8 1.1.1.1 114.114.114.114; do
    echo "=== $ns ==="
    dig @$ns api.chainke.com +short
done
```

### 5.4 灾难恢复核对清单

```
□ 确认故障类型 (网络/计算/存储/数据)
□ 通知团队 (钉钉/飞书/邮件)
□ 数据库从库提升为主库
□ 修改应用数据库连接配置
□ 重启应用实例
□ 更新DNS记录
□ 验证核心业务可用
□ 确认OSS文件可访问
□ 记录事件时间线
□ 启动根因分析
□ 通知用户 (如有必要)
□ 北京恢复后, 清理并重建复制
□ 故障演练复盘
```

---

## 6. 故障演练计划 (每季度一次)

### 6.1 演练场景矩阵

| 场景 | 类型 | 频率 | 停止服务时间 | 备注 |
|------|------|------|------------|------|
| 数据库主库宕机 | 数据层 | 季度 | ≤5分钟 | 模拟PG主库进程崩溃 |
| 北京Region网络故障 | 网络 | 季度 | ≤10分钟 | 模拟VPC网络中断 |
| 应用实例批量故障 | 计算 | 季度 | ≤5分钟 | 模拟K8s节点损坏 |
| OSS北京不可用 | 存储 | 半年 | ≤1分钟 | 模拟OSS服务故障 |
| DNS故障切换 | 网络 | 季度 | 连续 | 不切实际流量,仅验证配置 |

### 6.2 演练剧本: 数据库主库宕机

**前置条件:**
- 演练窗口: 凌晨02:00-04:00 (低流量时段)
- 已通知团队
- 已备份元数据

**步骤:**

```
[00:00] 准备阶段
  - 确认上海从库复制正常
  - 确认上海K8s集群就绪
  - 记录演练开始时间

[00:05] 注入故障
  - 在北京主库上执行: pg_ctl stop -m fast
  - 确认告警管理器触发CRITICAL告警

[00:08] 故障确认
  - 确认监控面板显示主库离线
  - 确认上海从库数据完整

[00:10] 数据库切换
  - 在上海从库执行: SELECT pg_promote();
  - 验证上海变为主库

[00:12] 应用切换
  - 更新ConfigMap数据库连接
  - 滚动重启应用Pod

[00:15] DNS切换
  - 执行 dns_failover.sh to-shanghai
  - 验证DNS传播

[00:18] 验证
  - 核心业务API测试
  - 确认告警恢复

[00:20] 回滚 (如演练完成)
  - 恢复北京主库
  - 重建复制关系
  - DNS切换回北京

[00:30] 演练结束
  - 记录用时
  - 问题复盘
```

### 6.3 演练评分标准

| 项目 | 达标 | 满分 | 说明 |
|------|------|------|------|
| 故障发现时间 | ≤ 2分钟 | ≤ 1分钟 | 从故障注入到告警触发 |
| 数据库切换时间 | ≤ 5分钟 | ≤ 3分钟 | 从库提升+验证 |
| DNS切换时间 | ≤ 5分钟 | ≤ 3分钟 | 含传播等待 |
| 总RTO | ≤ 30分钟 | ≤ 15分钟 | 完全恢复 |
| RPO | ≤ 5分钟 | ≤ 1分钟 | 数据丢失量 |
| 操作无失误 | - | - | 未造成额外故障 |

---

## 7. 日常运维

### 7.1 每日检查

```bash
#!/bin/bash
# deploy/db/daily_check.sh

echo "=== 数据库复制状态检查 ==="
psql -h localhost -c "SELECT * FROM pg_stat_replication;"

echo "=== 复制延迟 ==="
psql -h localhost -c "
SELECT application_name,
       pg_wal_lsn_diff(pg_current_wal_lsn(), write_lsn) AS write_delay_bytes,
       pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) AS flush_delay_bytes,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_delay_bytes
FROM pg_stat_replication;
"

echo "=== OSS跨区域同步状态 ==="
ossutil stat oss://chainke-beijing --endpoint oss-cn-beijing.aliyuncs.com
```

### 7.2 监控告警阈值

| 指标 | 告警级别 | 阈值 | 处理 |
|------|---------|------|------|
| 复制延迟 | WARNING | > 30秒 | 检查网络/IO |
| 复制延迟 | CRITICAL | > 5分钟 | 触发切换 |
| 复制状态 | ERROR | 复制中断 | 重建从库 |
| OSS同步延迟 | WARNING | > 10分钟 | 检查同步任务 |
| OSS同步失败 | ERROR | 连续3次 | 手动同步 |
| DNS健康检查 | CRITICAL | 3次连续失败 | 触发DNS切换 |

### 7.3 从库重建步骤

```bash
# 当从库损坏需要重建时：
# 1. 停止从库
systemctl stop postgresql

# 2. 清空从库数据目录
rm -rf /var/lib/postgresql/data/*

# 3. 从主库重新创建基础备份
pg_basebackup -h main-db-host -D /var/lib/postgresql/data \
  -U replicator -P -v --wal-method=stream

# 4. 配置从库连接
cat >> /var/lib/postgresql/data/postgresql.auto.conf << EOF
primary_conninfo = 'host=main-db-host port=5432 user=replicator password=*** sslmode=require'
primary_slot_name = 'shanghai_slot'
EOF

# 5. 启动从库
systemctl start postgresql

# 6. 验证复制
psql -c "SELECT * FROM pg_stat_replication;"
```

---

## 8. 附录

### 8.1 环境变量

```bash
# 数据库
DATABASE_URL=postgresql://user:pass@localhost:5432/chainke
DATABASE_URL_BEIJING=postgresql://user:pass@beijing-db:5432/chainke
DATABASE_URL_SHANGHAI=postgresql://user:pass@shanghai-db:5432/chainke
DATABASE_REPLICA_URL=postgresql://replicator:pass@shanghai-db:5432/chainke

# 存储
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
OSS_ENDPOINT_SHANGHAI=oss-cn-shanghai.aliyuncs.com
OSS_BUCKET=chainke-beijing
OSS_BUCKET_DR=chainke-shanghai

# DNS
DNS_TTL=120
DNS_HEALTH_CHECK_INTERVAL=30
DNS_FAILURE_THRESHOLD=3
```

### 8.2 相关脚本索引

| 脚本 | 路径 | 用途 |
|------|------|------|
| DNS故障切换 | `deploy/dns_failover.sh` | 手动切换DNS至上海/北京 |
| OSS同步 | `deploy/oss_sync.sh` | 手动触发OSS跨区域同步 |
| 数据库每日检查 | `deploy/db/daily_check.sh` | 检查复制延迟与状态 |
| 复制槽检查 | `deploy/db/replication_slot_check.sh` | 监控复制槽状态 |
| 从库重建 | `deploy/db/rebuild_replica.sh` | 从主库重建从库 |
| 故障演练脚本 | `deploy/dr_drill.sh` | 自动化故障演练 |

### 8.3 架构决策记录 (ADR)

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-05-29 | 异步流复制(非同步) | 同步复制会影响主库写入性能(跨区域延迟约20ms) |
| 2026-05-29 | DNS切换(非GSLB) | 阿里云DNS健康检查+TTL 2分钟足够满足RTO 30分钟 |
| 2026-05-29 | 不采用Active-Active | 业务不需要双向写,Active-Passive架构更简单可靠 |
| 2026-05-29 | 手动切换(非自动) | 自动切换有可能误触发,人工确认更安全 |

---

> **文档维护**: 链客宝基础设施团队
> **更新周期**: 每季度(结合故障演练)
> **审批**: 技术负责人
