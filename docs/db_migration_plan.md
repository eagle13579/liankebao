# 链客宝内存数据源盘点 & 数据库迁移计划

> 生成时间: 2026-06-08  
> 项目根目录: `/mnt/d/chainke-full/`

---

## 目录

1. [盘点说明](#1-盘点说明)
2. [完整内存数据源清单](#2-完整内存数据源清单)
3. [优先级排序与迁移路线图](#3-优先级排序与迁移路线图)
4. [详细迁移方案](#4-详细迁移方案)
5. [工作量评估](#5-工作量评估)
6. [风险与注意事项](#6-风险与注意事项)

---

## 1. 盘点说明

### 1.1 扫描范围

- 目录: `backend/app/` 及子目录下所有 `.py` 文件（93 个文件）
- 扫描对象: 模块级全局变量、类实例属性、类变量中用于"存储业务数据"或"维护运行时状态"的内存数据结构
- 排除: 函数局部临时变量、仅用于类型定义的 dataclass、ORM Model 类定义

### 1.2 分类标准

| 类别 | 说明 |
|------|------|
| **P0 关键业务数据** | 重启丢失会导致数据不一致 / 安全漏洞 / 业务中断 |
| **P1 重要数据** | 重启丢失影响服务质量但可自恢复 / 影响运营但无数据损失 |
| **P2 可优化** | 配置/模板/常量类数据，可外置化但非紧急 |

---

## 2. 完整内存数据源清单

### 2.1 P0 — 关键业务数据

#### #1 `auth.py` — Token 黑名单

| 字段 | 值 |
|------|-----|
| **变量名** | `_token_blacklist` (line 34) |
| **类型** | `set[str]` |
| **存储数据** | JWT token 的 `jti` 标识，用于登出/失效 |
| **引用场景** | `verify_token()` 查询黑名单 (line 122)、`add_token_to_blacklist()` 添加 (line 138) |
| **风险** | 服务重启后黑名单清空，已注销的 token 可继续使用→**权限绕过** |
| **行代码** | `_token_blacklist: set[str] = set()` |

#### #2 `circuit_breaker.py` — 熔断器注册表

| 字段 | 值 |
|------|-----|
| **变量名** | `CircuitBreakerRegistry._breakers` (line 134) |
| **类型** | `dict[str, CircuitBreakerInstance]` |
| **存储数据** | 熔断器状态 (CLOSED/OPEN/HALF_OPEN)、失败计数、统计数据、滑动窗口 |
| **引用场景** | `get_or_create()`, `record_success()`, `record_failure()`, `should_allow()` |
| **风险** | 重启后所有熔断器回到 CLOSED，下游服务可能被突发流量冲垮 |
| **行代码** | `self._breakers: dict[str, CircuitBreakerInstance] = {}` |

#### #3 `circuit_breaker.py` — 熔断器滑动窗口

| 字段 | 值 |
|------|-----|
| **变量名** | `CircuitBreakerInstance.recent_results` (line 79) |
| **类型** | `list[bool]` (field in dataclass) |
| **存储数据** | 最近 N 次调用的成功/失败记录 |
| **行代码** | `recent_results: list[bool] = field(default_factory=list)` |

---

### 2.2 P1 — 重要数据

#### #4 `rate_limiter.py` — 速率限制滑动窗口

| 字段 | 值 |
|------|-----|
| **变量名** | `MemoryRateLimiter._records` (line 33) |
| **类型** | `dict[str, tuple[int, deque]]` |
| **存储数据** | 每个 key (IP/用户) 的速率上限和时间戳队列 |
| **引用场景** | `check()`, `get_remaining()`, `reset_key()` |
| **风险** | 重启后限流状态丢失，短暂时间内可能被高频请求刷过 |
| **行代码** | `self._records: dict[str, tuple[int, deque]] = {}` |

#### #5 `rate_limiter.py` — 路由限流配置

| 字段 | 值 |
|------|-----|
| **变量名** | `ROUTE_LIMITS` (line 132) |
| **类型** | `list[tuple[str, int]]` |
| **存储数据** | 路径前缀 → 速率上限的硬编码配置 |
| **风险** | 修改限流规则需要改代码+重新部署 |
| **行代码** | `ROUTE_LIMITS = [...]` |

#### #6 `main.py` — 首页 Banner 数据

| 字段 | 值 |
|------|-----|
| **变量名** | `BANNERS` (line 497) |
| **类型** | `list[dict]` |
| **存储数据** | 小程序轮播图配置 (image URL, title, 跳转链接) |
| **风险** | 运营需改代码才能更新 Banner；多环境配置不一致 |
| **行代码** | `BANNERS = [...]` |

#### #7 `observability.py` — 指标收集器

| 字段 | 值 |
|------|-----|
| **变量名** | `MetricsCollector._response_times` (line 48) |
| **类型** | `deque` (maxlen=10000) |
| **引用场景** | `record_request()`, `snapshot()` |
| **风险** | 纯内存，重启后历史指标丢失 |

#### #8 `observability.py` — 请求分布统计

| 字段 | 值 |
|------|-----|
| **变量名** | `MetricsCollector._requests_by_path/_by_status/_by_method` (lines 49-51) |
| **类型** | `defaultdict(int)` |

---

### 2.3 P2 — 可优化（配置/模板/常量）

#### #9 `search_index.py` — 内存搜索引擎文档存储

| 字段 | 值 |
|------|-----|
| **变量名** | `MemorySearchEngine._documents` (line 327) |
| **类型** | `dict[int, SearchDocument]` |
| **存储数据** | 搜索索引的全部文档对象 |
| **风险** | 数据量大时内存占用高；重启后丢失需重建；已有 FTS5 替代方案 |
| **行代码** | `self._documents: dict[int, SearchDocument] = {}` |

#### #10 `search_index.py` — 内存倒排索引

| 字段 | 值 |
|------|-----|
| **变量名** | `MemorySearchEngine._inverted_index` (line 328) |
| **类型** | `dict[str, list[int]]` |
| **行代码** | `self._inverted_index: dict[str, list[int]] = {}` |

#### #11 `feature_flags.py` — 内置默认 Flags

| 字段 | 值 |
|------|-----|
| **变量名** | `BUILTIN_FLAGS` (line 79) |
| **类型** | `dict[str, dict[str, Any]]` |
| **存储数据** | 4 个预置 Feature Flag 的定义 |
| **备注** | 运行时会持久化到 `flags_config.json`，内存仅作为启动缓存和热加载 |
| **行代码** | `BUILTIN_FLAGS: dict[str, dict[str, Any]] = {...}` |

#### #12 `feature_flags.py` — Flags 运行时缓存

| 字段 | 值 |
|------|-----|
| **变量名** | `FlagsConfigManager._flags` (line 150) |
| **类型** | `dict[str, FeatureFlag]` |
| **备注** | 有 `_save_to_file()` 文件持久化 + mtime 热加载，现有方案已合理 |

#### #13 `i18n.py` — 翻译字典

| 字段 | 值 |
|------|-----|
| **变量名** | `TRANSLATIONS` (line 20) |
| **类型** | `dict[str, dict[str, str]]` |
| **存储数据** | 100+ 中英翻译键值对 |
| **行代码** | `TRANSLATIONS: dict[str, dict[str, str]] = {...}` |

#### #14 `business_card_ai.py` — 名片字段定义

| 字段 | 值 |
|------|-----|
| **变量名** | `CARD_FIELDS` (line 26) |
| **类型** | `list[str]` |
| **行代码** | `CARD_FIELDS = [...]` |

#### #15 `business_card_ai.py` — 公司后缀关键词

| 字段 | 值 |
|------|-----|
| **变量名** | `COMPANY_SUFFIXES` (line 336) |
| **类型** | `list[str]` |
| **行代码** | `COMPANY_SUFFIXES = [...]` |

#### #16 `business_card_ai.py` — 职位关键词

| 字段 | 值 |
|------|-----|
| **变量名** | `POSITION_KEYWORDS` (line 406) |
| **类型** | `list[str]` |
| **行代码** | `POSITION_KEYWORDS = [...]` |

#### #17 `feature_pipeline.py` — 停用词表

| 字段 | 值 |
|------|-----|
| **变量名** | `STOP_WORDS` (line 49) |
| **类型** | `set[str]` |
| **行代码** | `STOP_WORDS: set[str] = {...}` |

#### #18 `feature_pipeline.py` — 已知类目列表

| 字段 | 值 |
|------|-----|
| **变量名** | `KNOWN_CATEGORIES` (line 66) |
| **类型** | `list[str]` |
| **行代码** | `KNOWN_CATEGORIES: list[str] = [...]` |

#### #19 `feature_pipeline.py` — TF-IDF 向量器缓存

| 字段 | 值 |
|------|-----|
| **变量名** | `_TFIDF_VECTORIZER` / `_TFIDF_FITTED` (lines 238-239) |
| **类型** | 模块级全局变量 |
| **风险** | 模块级可变状态，多线程有竞态可能 |

#### #20 `enterprise_crawler.py` — User-Agent 轮换池

| 字段 | 值 |
|------|-----|
| **变量名** | `USER_AGENTS` (line 29) |
| **类型** | `list[str]` |
| **行代码** | `USER_AGENTS = [...]` |

#### #21 `geo/magic_words.py` — 张力关键词分类库

| 字段 | 值 |
|------|-----|
| **变量名** | `MAGIC_WORDS` (line 30) |
| **类型** | `Dict[str, List[Dict]]` |
| **存储数据** | 4 大类共 40+ 张力关键词及其用法示例 |
| **行代码** | `MAGIC_WORDS: Dict[str, List[Dict]] = {...}` |

#### #22 `geo/writing_style_guide.py` — 书面语→口语对照表

| 字段 | 值 |
|------|-----|
| **变量名** | `FORMAL_TO_COLLOQUIAL_MAP` (line 32) |
| **类型** | `Dict[str, List[Dict[str, str]]]` |
| **行代码** | `FORMAL_TO_COLLOQUIAL_MAP: ... = {...}` |

#### #23 `geo/content_tension_check.py` — 评分权重

| 字段 | 值 |
|------|-----|
| **变量名** | `SCORE_WEIGHTS` (line 35) |
| **类型** | `dict` |
| **行代码** | `SCORE_WEIGHTS = {...}` |

#### #24 `notifications.py` — 有效通知类型

| 字段 | 值 |
|------|-----|
| **变量名** | `VALID_TYPES` (line 21) |
| **类型** | `frozenset` |
| **备注** | 业务规则常量，修改频率极低 |
| **行代码** | `VALID_TYPES = frozenset({...})` |

#### #25 `circuit_breaker.py` — 默认配置常量

| 字段 | 值 |
|------|-----|
| **变量名** | `DEFAULT_FAILURE_THRESHOLD`, `DEFAULT_RECOVERY_TIMEOUT`, 等 (lines 32-35) |
| **类型** | `int` |
| **行代码** | `DEFAULT_FAILURE_THRESHOLD = 5` |

#### #26 `websocket_manager.py` — 在线连接状态

| 字段 | 值 |
|------|-----|
| **变量名** | `ConnectionManager._connections` (line 36) |
| **类型** | `Dict[int, Set[WebSocket]]` |
| **备注** | WebSocket 连接本质是进程内瞬态资源，多实例部署时需要 Redis Pub/Sub 做跨进程广播 |
| **行代码** | `self._connections: Dict[int, Set[WebSocket]] = {}` |

---

## 3. 优先级排序与迁移路线图

### Phase 1 — 紧急修复 (1-2 天)

| 优先级 | # | 数据源 | 建议方案 | 影响 |
|--------|---|--------|----------|------|
| **P0** | #1 | `_token_blacklist` | 迁移至 Redis 或新增 `token_blacklist` 表 | 安全漏洞修复 |
| **P0** | #2-3 | `CircuitBreakerRegistry` | 增加 SQLite/Redis 持久化 | 系统稳定性 |

### Phase 2 — 重要优化 (3-5 天)

| 优先级 | # | 数据源 | 建议方案 | 影响 |
|--------|---|--------|----------|------|
| **P1** | #4 | `MemoryRateLimiter._records` | 迁移至 Redis | 限流可靠性 |
| **P1** | #5 | `ROUTE_LIMITS` | 迁移至 DB/配置中心 | 免重启改配置 |
| **P1** | #6 | `BANNERS` | 新增 `banners` 表 + 管理 API | 运营效率 |
| **P1** | #7-8 | `MetricsCollector` | 对接 Prometheus / OpenTelemetry | 指标持久化 |

### Phase 3 — 长期改进 (1-2 周)

| 优先级 | # | 数据源 | 建议方案 | 影响 |
|--------|---|--------|----------|------|
| **P2** | #9-10 | `MemorySearchEngine` | 启用 FTS5 或 Elasticsearch | 搜索性能与持久化 |
| **P2** | #11-12 | Feature Flags | 已有 JSON 持久化，可选 DB 表 | 管理便利性 |
| **P2** | #13 | `TRANSLATIONS` | 迁移至 `.json` 文件 + 懒加载 | 模块化 |
| **P2** | #14-16 | AI 名片关键词 | 迁移至配置文件 | 运维便利 |
| **P2** | #17-18 | `STOP_WORDS`/`KNOWN_CATEGORIES` | 迁移至配置文件 | 运维便利 |
| **P2** | #21-23 | GEO 内容库 | 迁移至配置文件或 DB | 内容管理 |
| **P2** | #26 | WebSocket 跨进程 | 引入 Redis Pub/Sub | 多实例部署 |

---

## 4. 详细迁移方案

### 4.1 `_token_blacklist` → `token_blacklist` 表

**方案 A — DB 表（推荐，无需额外中间件）**

```sql
CREATE TABLE token_blacklist (
    id         BIGSERIAL PRIMARY KEY,
    jti        VARCHAR(64) NOT NULL UNIQUE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expired_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_token_blacklist_jti ON token_blacklist(jti);
CREATE INDEX idx_token_blacklist_expired_at ON token_blacklist(expired_at);
```

**迁移步骤:**
1. 新建 `TokenBlacklist` model
2. 修改 `verify_token()`: 查询 DB 替代内存 set
3. 修改 `add_token_to_blacklist()`: INSERT 替代 `set.add()`
4. 添加定时清理过期 token 的任务 (cron / celery beat)
5. 删除 `_token_blacklist` 全局变量

**方案 B — Redis（性能更优，依赖 Redis 部署）**
```
SET token_blacklist:{jti} 1 EX {token_ttl}
```

### 4.2 `CircuitBreakerRegistry` → SQLite/Redis 持久化

**关键字段：** breaker 名称、状态、连续失败次数、最后状态变更时间

```sql
CREATE TABLE circuit_breaker_states (
    name                     VARCHAR(64) PRIMARY KEY,
    state                    VARCHAR(16) NOT NULL DEFAULT 'CLOSED',
    consecutive_failures     INTEGER NOT NULL DEFAULT 0,
    consecutive_successes    INTEGER NOT NULL DEFAULT 0,
    total_requests           INTEGER NOT NULL DEFAULT 0,
    total_failures           INTEGER NOT NULL DEFAULT 0,
    total_successes          INTEGER NOT NULL DEFAULT 0,
    total_rejected           INTEGER NOT NULL DEFAULT 0,
    last_state_change_time   DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_failure_time        DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_success_time        DOUBLE PRECISION NOT NULL DEFAULT 0,
    updated_at               TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**迁移步骤:**
1. 在 `record_success/failure` 中增加 DB 写入
2. 在 `get_or_create()` 中增加 DB 读取
3. 添加内存 ↔ DB 的双向同步（启动时从 DB 加载，运行时异步写回）
4. 滑动窗口 `recent_results` 可保留在内存（重启丢失可接受）

### 4.3 `MemoryRateLimiter._records` → Redis

**Redis 数据结构:**
```
# 滑动窗口 - Sorted Set
ZADD rate_limit:{key} {timestamp} {timestamp}
ZREMRANGEBYSCORE rate_limit:{key} 0 {now-window_sec}
ZCARD rate_limit:{key}
EXPIRE rate_limit:{key} {window_sec * 2}
```

**降级方案:**
- 如无 Redis，可使用 SQLite 表存储，但性能低于 Redis
- 保持 `MemoryRateLimiter` 作为 fallback

### 4.4 `BANNERS` → `banners` 表

```sql
CREATE TABLE banners (
    id          SERIAL PRIMARY KEY,
    image_url   VARCHAR(512) NOT NULL,
    title       VARCHAR(256) NOT NULL,
    url         VARCHAR(512) NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

INSERT INTO banners (image_url, title, url, sort_order) VALUES
('https://www.go-aiport.com/static/banners/banner1.svg', '链客宝 · AI企业家生态', '/pages/pool/index', 1),
('https://www.go-aiport.com/static/banners/banner2.svg', 'GEO诊断 · 精准获客', '/pages/pool/index?cat=geo', 2),
('https://www.go-aiport.com/static/banners/banner3.svg', '数字分身 · 智能交互', '/pages/pool/index?cat=ai', 3);
```

### 4.5 `TRANSLATIONS` → i18n JSON 文件

将 `TRANSLATIONS` 字典拆分为 `locales/zh.json` 和 `locales/en.json`，启动时加载。

### 4.6 搜索引擎切换（Memory → FTS5）

项目已内置 `FTS5SearchEngine` 和 `MemorySearchEngine`。设置环境变量即可切换:
```
SEARCH_BACKEND=fts5
```

---

## 5. 工作量评估

| 阶段 | 条目 | 预估人天 | 说明 |
|------|------|----------|------|
| **Phase 1** | P0 #1 token_blacklist | 1d | Model + 逻辑替换 + 清理任务 |
| | P0 #2-3 circuit_breaker | 1d | DB 表 + 同步逻辑 |
| **Phase 2** | P1 #4 rate_limiter Redis | 1d | Redis 集成 |
| | P1 #5 ROUTE_LIMITS | 0.5d | 配置表 + 热加载 |
| | P1 #6 BANNERS | 1d | 表 + API + 管理后台 |
| | P1 #7-8 MetricsCollector | 1d | Prometheus 对接 |
| **Phase 3** | P2 #9-10 搜索引擎切换 | 1d | FTS5 启用与测试 |
| | P2 #13 i18n 文件化 | 0.5d | JSON 拆分 |
| | P2 #14-16 名片关键词 | 0.5d | 配置文件化 |
| | P2 #21-23 GEO 内容库 | 0.5d | 配置管理 |
| | P2 #26 WebSocket Pub/Sub | 1d | Redis 广播 |
| **测试+回归** | 全量 | 2d | 集成测试 + 性能测试 |
| **总计** | | **~10d** | |

---

## 6. 风险与注意事项

### 已使用 SQLite 的模块（无需迁移）

| 文件 | 数据库文件 | 说明 |
|------|-----------|------|
| `retry_engine.py` | `backend/data/retry_engine.db` | 重试任务队列+死信队列 |
| `notifications.py` | `backend/data/notifications.db` | 站内通知持久化 |

这两个模块已使用独立的 SQLite 持久化，不属于内存数据源。

### 迁移注意事项

1. **`_token_blacklist` 是最紧急的**: 当前实现存在安全风险，已注销的 token 在重启后仍然可用
2. **`CircuitBreakerRegistry` 重启重置**: 若熔断器在 OPEN 状态时重启，下游服务会瞬间接收全部流量
3. **`MemoryRateLimiter` 重启清零**: 短暂窗口（秒级）内限流失效，可接受但需监控
4. **`MemorySearchEngine` 已有替代**: 环境变量 `SEARCH_BACKEND=fts5` 即可启用持久化搜索，但需要 SQLite 支持 FTS5
5. **多实例部署**: WebSocket 和 Rate Limiter 在单实例时工作正常，多实例时必须引入 Redis
6. **滚动升级**: Phase 1 的 token 黑名单迁移建议在停服窗口或灰度环境中完成，避免新旧逻辑不一致
