# k6 测试结果

此目录存放 k6 性能测试的执行结果和报告文件。

## 目录结构

```
deploy/k6/results/
├── README.md              # 本文件
├── smoke_test_*.json      # 烟雾测试报告
├── stress_test_*.json     # 压力测试报告
└── archive/               # 历史报告归档
```

## 预期性能指标

### 烟雾测试（Smoke Test）

**场景**：10 并发虚拟用户，持续约 30 秒

```
测试时长:       30s
并发用户数:     10
目标错误率:     < 1%
```

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 全局错误率 | < 1% | 请求失败率 |
| 全局 P95 延迟 | < 2,000ms | 95% 请求完成时间 |
| 健康检查 P95 | < 1,000ms | GET /health |
| 产品列表 P95 | < 2,000ms | GET /api/products |
| 登录 P95 | < 2,000ms | POST /api/auth/login |
| 搜索建议 P95 | < 2,000ms | GET /api/search/suggestions |

### 压力测试（Stress Test）

**场景**：阶梯式加压 10 → 50 → 100 → 200 并发，持续约 2 分钟

```
测试时长:       约 110s
并发范围:       10 → 200 (阶梯递增)
峰值并发:       200
目标错误率:     < 5%
```

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 全局错误率 | < 5% | 高并发下允许少量失败 |
| 全局 P50 延迟 | < 500ms | 中位数响应时间 |
| 全局 P95 延迟 | < 3,000ms | 95% 请求完成时间 |
| 全局 P99 延迟 | < 5,000ms | 99% 请求完成时间 |
| 产品列表 P50 | < 800ms | 产品查询中位数 |
| 产品列表 P95 | < 4,000ms | 产品查询 P95 |
| 产品列表 P99 | < 6,000ms | 产品查询 P99 |
| 搜索 P50 | < 1,000ms | 搜索中位数 |
| 搜索 P95 | < 5,000ms | 搜索 P95 |
| 搜索 P99 | < 8,000ms | 搜索 P99 |

## 生成报告

### 运行测试并导出 JSON 报告

```bash
# 烟雾测试 + JSON 导出
k6 run --summary-export=deploy/k6/results/smoke_test_$(date +%Y%m%d_%H%M%S).json \
  deploy/k6/scripts/smoke_test.js

# 压力测试 + JSON 导出
k6 run --summary-export=deploy/k6/results/stress_test_$(date +%Y%m%d_%H%M%S).json \
  --summary-trend-stats="min,avg,med,p(50),p(95),p(99),max" \
  deploy/k6/scripts/stress_test.js
```

### 输出示例

烟雾测试报告 (`smoke_test_20250101_120000.json`):
```json
{
  "metrics": {
    "http_reqs": { "values": { "count": 300, "rate": 10.2 } },
    "http_req_duration": { "values": { "avg": 150, "p(95)": 450 } },
    "http_req_failed": { "values": { "rate": 0.0 } }
  }
}
```

压力测试报告 (`stress_test_20250101_120000.json`):
```json
{
  "metrics": {
    "http_reqs": { "values": { "count": 8500, "rate": 120.5 } },
    "http_req_duration": { "values": { "avg": 320, "p(50)": 180, "p(95)": 2100, "p(99)": 4200 } },
    "http_req_failed": { "values": { "rate": 0.02 } },
    "products_latency_ms": { "values": { "p(50)": 250, "p(95)": 2800, "p(99)": 5100 } },
    "search_latency_ms": { "values": { "p(50)": 400, "p(95)": 3500, "p(99)": 6200 } }
  }
}
```

## 历史数据对比

建议在 CI 流程中定期运行测试并归档结果。通过对比历史数据可发现性能退化：

- **对比维度**：P50、P95、P99 延迟变化趋势
- **告警条件**：P95 延迟相比基线上升超过 30%
- **归档建议**：保留最近 30 天的报告，按月清理

## 性能基线

基线数据应记录在项目 Wiki 或 Notion 中，包含：

1. 测试环境信息（服务规格、数据库配置、网络拓扑）
2. 测试时间
3. 各端点各百分位的延迟数据
4. 最大吞吐量（RPS）
5. 错误率

## 注意事项

1. **环境一致性**：测试环境应尽量与生产环境保持同规格
2. **数据预热**：首次测试前建议预热数据库缓存
3. **外部依赖**：注意第三方 API 的限流可能影响测试结果
4. **Git 忽略**：建议将 `*.json` 报告文件加入 `.gitignore`（仅保留模板和 README）

```gitignore
# .gitignore
deploy/k6/results/*.json
```
