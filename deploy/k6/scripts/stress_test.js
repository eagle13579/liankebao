/**
 * 链客宝AI — k6 压力测试 (Stress / Load Test)
 *
 * 目的: 评估系统在高并发下的性能表现，发现瓶颈
 * 场景: 阶梯式加压 10 → 50 → 100 → 200 并发用户，持续 2 分钟
 * 测试端点: /api/products, /api/search
 * 输出指标: 最大RPS, P50/P95/P99 延迟, 错误率
 *
 * 运行:
 *   k6 run deploy/k6/scripts/stress_test.js
 *   k6 run --summary-trend-stats="min,avg,med,p(50),p(95),p(99),max" deploy/k6/scripts/stress_test.js
 *   k6 run -e BASE_URL=http://localhost:8001 deploy/k6/scripts/stress_test.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { randomIntBetween, randomItem } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// =============================================================================
// 自定义指标
// =============================================================================
const failRate = new Rate('failed_requests');

// 各端点延迟细分
const productsLatency = new Trend('products_latency_ms');
const searchLatency = new Trend('search_latency_ms');

// 业务指标
const totalProductsRequests = new Counter('total_products_requests');
const totalSearchRequests = new Counter('total_search_requests');

// =============================================================================
// 配置
// =============================================================================
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';

// 搜索关键词池（模拟真实用户搜索行为）
const SEARCH_QUERIES = [
  'test', '产品', '服务', '咨询', '方案',
  '科技', '电商', '教育', '医疗', '金融',
  '食品', '饮料', '服装', '数码', '家电',
  '',           // 空搜索
];

// 搜索排序方式
const SORT_OPTIONS = ['relevance', 'price_asc', 'price_desc', 'newest'];

export const options = {
  // 阶梯式加压
  stages: [
    { duration: '15s', target: 10 },    // 初始 10 用户
    { duration: '15s', target: 50 },    // 爬升到 50
    { duration: '20s', target: 50 },    // 保持 50
    { duration: '15s', target: 100 },   // 爬升到 100
    { duration: '20s', target: 100 },   // 保持 100
    { duration: '15s', target: 200 },   // 爬升到 200
    { duration: '20s', target: 200 },   // 保持 200（峰值）
    { duration: '10s', target: 0 },     // 降载
  ],

  thresholds: {
    // ---------- 全局阈值 ----------
    http_req_failed: ['rate<0.05'],            // 错误率 < 5%（压力测试可适当放宽）
    http_req_duration: ['p(50)<500'],           // 中位数延迟 < 500ms
    http_req_duration: ['p(95)<3000'],          // P95 延迟 < 3s
    http_req_duration: ['p(99)<5000'],          // P99 延迟 < 5s

    // ---------- 各端点细化阈值 ----------
    // 产品列表: 在高并发下应保持响应
    'products_latency_ms': ['p(50)<800', 'p(95)<4000', 'p(99)<6000'],

    // 搜索: 涉及索引查询，允许稍高延迟
    'search_latency_ms': ['p(50)<1000', 'p(95)<5000', 'p(99)<8000'],

    // 失败率
    failed_requests: ['rate<0.05'],
  },

  tags: {
    test_name: 'stress_test',
    project: 'liankebao',
  },
};

// =============================================================================
// 辅助函数
// =============================================================================

function log(msg) {
  const ts = new Date().toISOString().slice(11, 23);
  console.log(`[${ts}] ${msg}`);
}

/**
 * 生成随机搜索查询
 */
function randomSearchQuery() {
  return randomItem(SEARCH_QUERIES);
}

/**
 * 生成随机排序
 */
function randomSort() {
  return randomItem(SORT_OPTIONS);
}

// =============================================================================
// 主场景
// =============================================================================

export default function () {
  // 用户行为模拟: 每个 VU 在两种 API 间交替请求

  // ---- 场景 A: GET /api/products (60% 概率) ----
  if (Math.random() < 0.6) {
    group('products', function () {
      // 随机添加筛选参数
      const params = new URLSearchParams();
      if (Math.random() < 0.3) {
        params.set('category', randomItem(['食品', '数码', '服装', '服务', '教育']));
      }
      if (Math.random() < 0.2) {
        params.set('page', String(randomIntBetween(1, 5)));
        params.set('page_size', String(randomIntBetween(10, 40)));
      }

      const queryStr = params.toString();
      const url = queryStr
        ? `${BASE_URL}/api/products?${queryStr}`
        : `${BASE_URL}/api/products`;

      const res = http.get(url, {
        tags: { endpoint: 'products' },
      });

      const ok = check(res, {
        'products 返回 200': (r) => r.status === 200,
        'products 是 JSON': (r) => {
          const ct = r.headers['Content-Type'] || r.headers['content-type'] || '';
          return ct.includes('json');
        },
      });

      failRate.add(!ok);
      productsLatency.add(res.timings.duration);
      totalProductsRequests.add(1);

      if (!ok) {
        log(`products 请求失败: status=${res.status}, body=${res.body.slice(0, 200)}`);
      }
    });
  }

  // ---- 场景 B: GET /api/search (40% 概率) ----
  else {
    group('search', function () {
      const q = randomSearchQuery();
      const sort_by = randomSort();

      const params = new URLSearchParams();
      if (q) params.set('q', q);
      params.set('sort_by', sort_by);

      // 部分请求访问搜索建议
      let url;
      if (Math.random() < 0.25 && q) {
        // 搜索建议端点
        url = `${BASE_URL}/api/search/suggestions?q=${encodeURIComponent(q.slice(0, 3))}`;
      } else {
        url = `${BASE_URL}/api/search?${params.toString()}`;
      }

      const res = http.get(url, {
        tags: { endpoint: 'search' },
      });

      const ok = check(res, {
        'search 返回 200': (r) => r.status === 200,
        'search 是 JSON': (r) => {
          const ct = r.headers['Content-Type'] || r.headers['content-type'] || '';
          return ct.includes('json');
        },
      });

      failRate.add(!ok);
      searchLatency.add(res.timings.duration);
      totalSearchRequests.add(1);

      if (!ok) {
        log(`search 请求失败: status=${res.status}, url=${url}`);
      }
    });
  }

  // 随机休眠 0.5~2 秒，模拟真实用户思考时间
  sleep(randomIntBetween(0.5, 2));
}

// =============================================================================
// 测试报告摘要增强
// =============================================================================

export function handleSummary(data) {
  const stats = {
    // 时间指标
    duration_sec: Math.round((data.state?.testRunDurationMs || 0) / 1000),

    // 全局 HTTP 指标
    total_requests: data.metrics?.http_reqs?.values?.count || 0,
    max_rps: data.metrics?.http_reqs?.values?.rate || 0,

    // 延迟统计
    latency_p50_ms: Math.round(data.metrics?.http_req_duration?.values?.['p(50)'] || 0),
    latency_p95_ms: Math.round(data.metrics?.http_req_duration?.values?.['p(95)'] || 0),
    latency_p99_ms: Math.round(data.metrics?.http_req_duration?.values?.['p(99)'] || 0),
    latency_avg_ms: Math.round(data.metrics?.http_req_duration?.values?.avg || 0),
    latency_max_ms: Math.round(data.metrics?.http_req_duration?.values?.max || 0),

    // 错误率
    error_rate: ((data.metrics?.http_req_failed?.values?.rate || 0) * 100).toFixed(2) + '%',

    // 各端点延迟
    products_p50_ms: Math.round(data.metrics?.['products_latency_ms']?.values?.['p(50)'] || 0),
    products_p95_ms: Math.round(data.metrics?.['products_latency_ms']?.values?.['p(95)'] || 0),
    products_p99_ms: Math.round(data.metrics?.['products_latency_ms']?.values?.['p(99)'] || 0),

    search_p50_ms: Math.round(data.metrics?.['search_latency_ms']?.values?.['p(50)'] || 0),
    search_p95_ms: Math.round(data.metrics?.['search_latency_ms']?.values?.['p(95)'] || 0),
    search_p99_ms: Math.round(data.metrics?.['search_latency_ms']?.values?.['p(99)'] || 0),

    // 业务量
    total_products_requests: data.metrics?.total_products_requests?.values?.count || 0,
    total_search_requests: data.metrics?.total_search_requests?.values?.count || 0,
  };

  // 控制台输出摘要
  console.log('='.repeat(60));
  console.log('  链客宝AI 压力测试结果摘要');
  console.log('='.repeat(60));
  console.log(`  测试时长:       ${stats.duration_sec}s`);
  console.log(`  总请求数:       ${stats.total_requests}`);
  console.log(`  最大 RPS:       ${stats.max_rps.toFixed(0)} req/s`);
  console.log(`  错误率:         ${stats.error_rate}`);
  console.log('');
  console.log(`  全局延迟:`);
  console.log(`    Avg: ${stats.latency_avg_ms}ms`);
  console.log(`    P50: ${stats.latency_p50_ms}ms`);
  console.log(`    P95: ${stats.latency_p95_ms}ms`);
  console.log(`    P99: ${stats.latency_p99_ms}ms`);
  console.log(`    Max: ${stats.latency_max_ms}ms`);
  console.log('');
  console.log(`  产品列表延迟:`);
  console.log(`    P50: ${stats.products_p50_ms}ms | P95: ${stats.products_p95_ms}ms | P99: ${stats.products_p99_ms}ms`);
  console.log(`  搜索延迟:`);
  console.log(`    P50: ${stats.search_p50_ms}ms | P95: ${stats.search_p95_ms}ms | P99: ${stats.search_p99_ms}ms`);
  console.log('');
  console.log(`  产品请求数:     ${stats.total_products_requests}`);
  console.log(`  搜索请求数:     ${stats.total_search_requests}`);
  console.log('='.repeat(60));

  // 返回 JSON 报告文件
  return {
    'stdout': '',  // 上面已经打印
    'deploy/k6/reports/stress_test_summary.json': JSON.stringify(stats, null, 2),
  };
}
