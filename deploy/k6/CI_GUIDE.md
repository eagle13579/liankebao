# 链客宝AI — k6 CI 集成指南

## 目录

1. [GitHub Actions 集成](#github-actions-集成)
2. [阈值说明](#阈值说明)
3. [CI 失败排查步骤](#ci-失败排查步骤)

---

## GitHub Actions 集成

### 方式一：使用官方 k6 Action（推荐）

```yaml
# .github/workflows/performance.yml
name: 性能测试

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 6 * * 1'  # 每周一早上6点定时运行

jobs:
  smoke-test:
    name: 烟雾测试
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: 运行 k6 烟雾测试
        uses: grafana/k6-action@v0.3.1
        with:
          filename: deploy/k6/scripts/smoke_test.js
          flags: -e BASE_URL=${{ secrets.BASE_URL }}

      - name: 上传烟雾测试报告
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: smoke-test-report
          path: deploy/k6/reports/*.json
          retention-days: 30

  stress-test:
    name: 压力测试
    runs-on: ubuntu-latest
    needs: smoke-test  # 烟雾测试通过后才运行压力测试
    steps:
      - uses: actions/checkout@v4

      - name: 运行 k6 压力测试
        uses: grafana/k6-action@v0.3.1
        with:
          filename: deploy/k6/scripts/stress_test.js
          flags: >
            -e BASE_URL=${{ secrets.BASE_URL }}
            --summary-trend-stats="min,avg,med,p(50),p(95),p(99),max"
            --summary-export=deploy/k6/reports/stress_test_report.json

      - name: 上传压力测试报告
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: stress-test-report
          path: deploy/k6/reports/*.json
          retention-days: 30

      - name: 阈值失败告警
        if: failure()
        uses: slackapi/slack-github-action@v1.24.0
        with:
          payload: |
            {
              "text": "⚠️ k6 压力测试阈值未通过\n项目: 链客宝AI\n分支: ${{ github.ref_name }}\n详情: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

### 方式二：通过 Docker 运行（适合灵活配置）

```yaml
# .github/workflows/performance-docker.yml
name: 性能测试（Docker）

on:
  workflow_dispatch:  # 手动触发
  pull_request:
    paths:
      - 'deploy/k6/**'

jobs:
  k6-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: 运行 k6 测试
        run: |
          docker run --rm \
            -v ${{ github.workspace }}:/workspace \
            -e BASE_URL=${{ secrets.BASE_URL }} \
            -e TEST_USER=${{ secrets.TEST_USER }} \
            -e TEST_PASS=${{ secrets.TEST_PASS }} \
            grafana/k6 run /workspace/deploy/k6/scripts/stress_test.js \
            --summary-trend-stats="min,avg,med,p(50),p(95),p(99),max" \
            --summary-export=/workspace/deploy/k6/reports/stress_test_report.json

      - name: 上传报告
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: k6-report
          path: deploy/k6/reports/*.json
```

### 方式三：直接安装运行（适合自托管 Runner）

```yaml
# .github/workflows/performance-native.yml
name: 性能测试（自托管）

on:
  workflow_dispatch:

jobs:
  k6-native:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4

      - name: 安装 k6
        run: |
          curl -s https://dl.k6.io/install.sh | bash

      - name: 运行烟雾测试
        run: |
          k6 run deploy/k6/scripts/smoke_test.js \
            -e BASE_URL=${{ secrets.BASE_URL }}

      - name: 运行压力测试
        run: |
          k6 run deploy/k6/scripts/stress_test.js \
            -e BASE_URL=${{ secrets.BASE_URL }} \
            --summary-export=deploy/k6/reports/stress_test_report.json
```

### CI 配置注意事项

1. **Secrets 管理**：在 GitHub 仓库 Settings > Secrets and variables > Actions 中添加：
   - `BASE_URL` — 测试环境地址
   - `TEST_USER` — 测试账号
   - `TEST_PASS` — 测试密码
   - `SLACK_WEBHOOK_URL` — 告警通知（可选）

2. **Runner 资源**：k6 本身资源开销较小，但被测服务应在独立环境中运行。建议使用超过 2 核、4GB 内存的 Runner。

3. **定时测试**：使用 `schedule` 事件在低峰期自动运行压力测试，避免影响开发流水线。

4. **条件执行**：压力测试耗时较长（约 2 分钟），建议只在 main 分支或手动触发时运行。

---

## 阈值说明

### 什么是阈值 (Thresholds)

阈值是 k6 中定义的通过/失败标准。当测试指标超出阈值范围时，k6 返回非零退出码，CI 会将其标记为失败。

### 烟雾测试阈值 (`smoke_test.js`)

| 指标 | 阈值 | 说明 |
|------|------|------|
| `http_req_failed` | `< 1%` | 全局请求失败率不超过 1% |
| `http_req_duration` | `P95 < 2s` | 全局 95% 的请求在 2s 内完成 |
| `health_latency_ms` | `P95 < 1s` | 健康检查端点 P95 延迟 |
| `products_latency_ms` | `P95 < 2s` | 产品列表端点 P95 延迟 |
| `login_latency_ms` | `P95 < 2s` | 登录端点 P95 延迟 |
| `search_latency_ms` | `P95 < 2s` | 搜索建议端点 P95 延迟 |
| `failed_requests` | `< 1%` | 自定义失败率指标 |

### 压力测试阈值 (`stress_test.js`)

| 指标 | 阈值 | 说明 |
|------|------|------|
| `http_req_failed` | `< 5%` | 高并发下允许少量失败 |
| `http_req_duration` | `P50 < 500ms` | 中位数延迟 < 500ms |
| `http_req_duration` | `P95 < 3s` | 95% 请求在 3s 内 |
| `http_req_duration` | `P99 < 5s` | 99% 请求在 5s 内 |
| `products_latency_ms` | `P50 < 800ms` | 产品列表中位数 |
| `products_latency_ms` | `P95 < 4s` | 产品列表 P95 |
| `products_latency_ms` | `P99 < 6s` | 产品列表 P99 |
| `search_latency_ms` | `P50 < 1s` | 搜索中位数 |
| `search_latency_ms` | `P95 < 5s` | 搜索 P95 |
| `search_latency_ms` | `P99 < 8s` | 搜索 P99 |
| `failed_requests` | `< 5%` | 自定义失败率 |

### 阈值语法说明

```javascript
thresholds: {
  // 基本语法: '指标名': ['条件1', '条件2', ...]
  'http_req_duration': [
    'p(50)<500',    // 中位数 < 500ms
    'p(95)<3000',   // P95 < 3000ms
    'p(99)<5000',   // P99 < 5000ms
    'avg<1000',     // 平均值 < 1000ms
    'max<10000',     // 最大值 < 10000ms
  ],
  // 加 "{}" 可指定中止测试（abortOnFail）
  'http_req_failed': [
    { threshold: 'rate<0.05', abortOnFail: true },  // 超过 5% 立刻停止
  ],
}
```

### 建议调整策略

- **烟雾测试**：阈值较为严格，保证核心功能在低负载下的响应质量
- **压力测试**：阈值适当放宽，关注系统在高负载下的表现趋势
- **首次运行**：如果阈值频繁失败，先观察实际指标值，调整阈值到合理范围
- **持续优化**：每次 CI 运行后记录指标，建立基线，逐步收紧阈值

---

## CI 失败排查步骤

当 CI 中的 k6 测试失败时，按以下步骤排查：

### 第一步：查看测试报告

1. 在 GitHub Actions 运行页面，找到失败的 workflow
2. 展开 k6 步骤，查看控制台输出
3. 下载 Artifacts 中的 JSON 报告，分析具体指标

**关键检查项：**
```
- http_req_failed (错误率): 是否过高？
- http_req_duration (延迟): 哪个百分位超了？
- 具体端点延迟: products_latency_ms / search_latency_ms
```

### 第二步：区分问题类型

| 症状 | 可能原因 |
|------|----------|
| 所有请求都失败 (100% error) | 目标服务未启动 / 网络不通 / URL 配置错误 |
| 部分请求失败 (1-30% error) | 后端连接池耗尽 / 数据库过载 / 限流触发 |
| 延迟整体偏高 | 资源不足 (CPU/内存) / 数据库查询慢 / 网络带宽瓶颈 |
| 仅特定端点失败 | 该接口有 bug / 依赖服务异常 / 权限问题 |
| 延迟随并发攀升急剧增加 | 代码扩展性差 / 连接未复用 / 锁竞争 |
| 测试本身报错 (k6 崩溃) | 脚本语法错误 / 内存不足 / 文件描述符限制 |

### 第三步：具体排查操作

#### 3.1 确认被测服务状态

```bash
# 检查健康端点
curl -v http://<BASE_URL>/health

# 检查服务日志
kubectl logs -n <namespace> <pod-name> --tail=100
# 或
docker logs <container-name> --tail=100
```

#### 3.2 检查服务端资源

```bash
# CPU 和内存
kubectl top pod -n <namespace>
# 或
docker stats

# 数据库连接数
# PostgreSQL:
kubectl exec <db-pod> -- psql -c "SELECT count(*) FROM pg_stat_activity;"
```

#### 3.3 本地复现测试

```bash
# 安装 k6（如果未安装）
# 参见 README.md

# 运行烟雾测试，排除 CI 环境差异
BASE_URL=http://localhost:8001 k6 run deploy/k6/scripts/smoke_test.js

# 以更低的并发量测试，确认基线
k6 run --vus 1 --duration 10s deploy/k6/scripts/smoke_test.js

# 逐步增加并发，找到拐点
k6 run --vus 5 --duration 30s deploy/k6/scripts/stress_test.js
k6 run --vus 20 --duration 30s deploy/k6/scripts/stress_test.js
k6 run --vus 50 --duration 30s deploy/k6/scripts/stress_test.js
```

#### 3.4 检查网络延迟

```bash
# 测量到目标服务的网络延迟
ping -c 5 <BASE_URL_HOST>

# TCP 连接时延
time curl -s -o /dev/null -w "Connect: %{time_connect}s, TTFB: %{time_starttransfer}s, Total: %{time_total}s\n" \
  http://<BASE_URL>/health
```

#### 3.5 检查环境变量

确认 CI Secrets 中的 `BASE_URL`、`TEST_USER`、`TEST_PASS` 配置正确：

```yaml
# 在 CI workflow 中添加调试步骤（注意：不要泄露密码）
- name: 调试环境变量
  run: |
    echo "BASE_URL=${{ secrets.BASE_URL }}"
    echo "测试脚本: deploy/k6/scripts/smoke_test.js"
  # 敏感信息在 GitHub Actions 中会自动脱敏
```

### 第四步：阈值调整决策

分析历史数据后，判断是否需要调整阈值：

| 情况 | 操作 |
|------|------|
| 阈值过于严格，正常波动导致频繁失败 | 适当放宽阈值，取 P95 的 1.5 倍 |
| 性能确实下降，阈值合理 | 排查性能问题，优化代码，暂不调整阈值 |
| 被测服务硬件变更（如扩缩容） | 重新建立基线，调整阈值 |
| 新增功能导致延迟合理增加 | 按新版基线更新阈值 |

### 第五步：上报与跟踪

- 在 CI 失败评论中标记相关开发人员
- 创建 Issue 跟踪性能回归，附上测试报告
- 每次修复后在 PR 中重新运行 k6 测试验证

---

## 参考

- [k6 官方文档](https://k6.io/docs/)
- [k6 GitHub Actions](https://github.com/marketplace/actions/k6-action)
- [k6 阈值文档](https://k6.io/docs/using-k6/thresholds/)
- [k6 检查点文档](https://k6.io/docs/using-k6/checks/)
