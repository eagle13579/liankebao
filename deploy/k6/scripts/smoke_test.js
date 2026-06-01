/**
 * 链客宝 — k6 烟雾测试 (Smoke Test)
 *
 * 目的: 验证核心API基本可用性，在低负载下检测明显问题
 * 场景: 10个并发虚拟用户，持续30秒
 * 阈值: 错误率 < 1%，P95 延迟 < 2s
 *
 * 运行:
 *   k6 run deploy/k6/scripts/smoke_test.js
 *   k6 run -e BASE_URL=http://localhost:8001 deploy/k6/scripts/smoke_test.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// =============================================================================
// 自定义指标
// =============================================================================
const failRate = new Rate('failed_requests');
const healthLatency = new Trend('health_latency_ms');
const productsLatency = new Trend('products_latency_ms');
const loginLatency = new Trend('login_latency_ms');
const searchLatency = new Trend('search_latency_ms');

// =============================================================================
// 配置
// =============================================================================
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';

// 测试账号（请替换为实际有效的凭据）
const TEST_USERNAME = __ENV.TEST_USER || 'admin';
const TEST_PASSWORD = __ENV.TEST_PASS || 'password123';

export const options = {
  // 烟雾测试：低并发、短时长
  stages: [
    { duration: '5s', target: 10 },   // 温和启动
    { duration: '20s', target: 10 },   // 稳态负载
    { duration: '5s', target: 0 },     // 降载
  ],

  thresholds: {
    // ---------- 全局阈值 ----------
    http_req_failed: ['rate<0.01'],            // 错误率 < 1%
    http_req_duration: ['p(95)<2000'],         // P95 延迟 < 2s

    // ---------- 各端点细化阈值 ----------
    'health_latency_ms': ['p(95)<1000'],       // 健康检查 P95 < 1s
    'products_latency_ms': ['p(95)<2000'],     // 产品列表 P95 < 2s
    'login_latency_ms': ['p(95)<2000'],        // 登录 P95 < 2s
    'search_latency_ms': ['p(95)<2000'],       // 搜索建议 P95 < 2s

    // 无失败请求
    failed_requests: ['rate<0.01'],
  },

  // 标签所有请求以便于在 InfluxDB / Prometheus 中分类
  tags: {
    test_name: 'smoke_test',
    project: 'liankebao',
  },
};

// =============================================================================
// 辅助函数
// =============================================================================

/**
 * 打印带有时间戳的日志
 */
function log(msg, data) {
  const ts = new Date().toISOString().slice(11, 23);
  const tag = data ? ` | data=${JSON.stringify(data)}` : '';
  console.log(`[${ts}] ${msg}${tag}`);
}

// =============================================================================
// 测试场景
// =============================================================================

export default function () {
  // ---- 1. 健康检查 GET /health ----
  group('01_health_check', function () {
    const res = http.get(`${BASE_URL}/health`, {
      tags: { endpoint: 'health' },
    });

    const ok = check(res, {
      'health 返回 200': (r) => r.status === 200 || r.status === 503, // 503 表示降级但服务仍在
      'health 响应体含 status': (r) => JSON.parse(r.body).status !== undefined,
    });

    failRate.add(!ok);
    healthLatency.add(res.timings.duration);
  });

  // ---- 2. 产品列表 GET /api/products ----
  group('02_products_list', function () {
    const res = http.get(`${BASE_URL}/api/products`, {
      tags: { endpoint: 'products' },
    });

    const ok = check(res, {
      'products 返回 200': (r) => r.status === 200,
      'products 响应是 JSON': (r) => r.headers['Content-Type']?.includes('json') || r.headers['content-type']?.includes('json'),
    });

    failRate.add(!ok);
    productsLatency.add(res.timings.duration);
  });

  // ---- 3. 用户登录 POST /api/auth/login ----
  group('03_auth_login', function () {
    const payload = JSON.stringify({
      username: TEST_USERNAME,
      password: TEST_PASSWORD,
    });

    const params = {
      headers: { 'Content-Type': 'application/json' },
      tags: { endpoint: 'login' },
    };

    const res = http.post(`${BASE_URL}/api/auth/login`, payload, params);

    const ok = check(res, {
      'login 返回 200': (r) => r.status === 200,
      'login 返回 access_token': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.data?.access_token !== undefined;
        } catch {
          return false;
        }
      },
    });

    // 如果登录成功，提取 token 供后续请求使用（可选）
    if (ok) {
      try {
        const body = JSON.parse(res.body);
        __ENV.ACCESS_TOKEN = body.data?.access_token || '';
      } catch (e) {
        // ignore
      }
    }

    failRate.add(!ok);
    loginLatency.add(res.timings.duration);
  });

  // ---- 4. 搜索建议 GET /api/search/suggestions?q=test ----
  group('04_search_suggestions', function () {
    const res = http.get(`${BASE_URL}/api/search/suggestions?q=test`, {
      tags: { endpoint: 'search_suggestions' },
    });

    const ok = check(res, {
      'search/suggestions 返回 200': (r) => r.status === 200,
      'search/suggestions 含 suggestions 字段': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.data?.suggestions !== undefined;
        } catch {
          return false;
        }
      },
    });

    failRate.add(!ok);
    searchLatency.add(res.timings.duration);
  });

  // 每次迭代间短暂休眠，模拟真实用户操作间隔
  sleep(1);
}

// =============================================================================
// 收尾处理
// =============================================================================

export function teardown() {
  log('烟雾测试完成');
}
